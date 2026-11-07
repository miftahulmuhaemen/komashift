import json
import logging
import re
import urllib.request
from urllib.error import HTTPError, URLError
from typing import List, Dict, Any, Optional, Tuple, Union
import unicodedata
from src.models.translation_item import PageTranslation

logger = logging.getLogger(__name__)

class TranslationError(Exception):
    pass

class OpenAITranslator:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        model: str = "gemini-3.5-flash-lite",
        timeout: float = 120.0,
        batch_size: int = 0
    ):
        self.api_key = api_key.strip()
        self.base_url = self._normalize_endpoint(base_url.strip())
        self.model = model.strip() or "gemini-3.5-flash-lite"
        self.timeout = float(timeout) if timeout else 120.0
        self.batch_size = max(0, int(batch_size)) if batch_size is not None else 0

    def _normalize_endpoint(self, url: str) -> str:
        url = url.rstrip("/")
        if not url:
            return "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        return url

    @staticmethod
    def _is_pure_punctuation_or_symbol(text: str) -> bool:
        """
        Check if text consists exclusively of punctuation, emoji, or non-linguistic symbols.
        Returns True if no Japanese (Hiragana, Katakana, Kanji) or alphanumeric characters exist.
        """
        norm = unicodedata.normalize("NFKC", text.strip())
        letters = re.findall(r"[\u3041-\u3096\u30a1-\u30fa\u3400-\u4dbf\u4e00-\u9fffA-Za-z0-9]", norm)
        return len(letters) == 0

    @staticmethod
    def _normalize_punctuation_text(text: str) -> str:
        """
        Normalizes pure Japanese punctuation/symbols to standard clean punctuation.
        e.g. '！' -> '!', '？？' -> '??', '．．．．．．' -> '...'
        """
        norm = unicodedata.normalize("NFKC", text.strip())
        norm = re.sub(r"\.{4,}", "...", norm)
        norm = re.sub(r"-{4,}", "---", norm)
        return norm

    def translate_chapter(
        self,
        pages: List[PageTranslation],
        target_lang: str = "en",
        on_batch_progress = None
    ) -> Dict[str, str]:
        all_translations: Dict[str, str] = {}
        unique_to_translate: Dict[str, List[str]] = {}  # text_ja -> list of bubble IDs
        pending_bubbles: List[Tuple[str, str]] = []     # [(bubble_id, text_ja), ...]
        bid_to_text_ja: Dict[str, str] = {}             # bubble_id -> text_ja

        for p in pages:
            for b in p.bubbles:
                text = b.text_ja.strip()
                if not text:
                    continue
                # Collapse excessive repeated punctuation/symbols (e.g. 50+ dashes or dots) to prevent LLM degeneration loops
                text = re.sub(r"([ー—―\-\.~…・])\1{3,}", r"\1\1\1", text).strip()
                if not text:
                    continue

                # 1. Local resolution for pure punctuation/symbol bubbles (0 token, 0 latency)
                if self._is_pure_punctuation_or_symbol(text):
                    all_translations[b.id] = self._normalize_punctuation_text(text)
                    continue

                # 2. In-chapter deduplication: only send unique strings to the LLM
                if text in unique_to_translate:
                    unique_to_translate[text].append(b.id)
                else:
                    unique_to_translate[text] = [b.id]
                    pending_bubbles.append((b.id, text))
                    bid_to_text_ja[b.id] = text

        if not pending_bubbles:
            return all_translations

        # Prepare batches: if batch_size <= 0, send whole chapter at once (no batching)
        batches: List[Dict[str, str]] = []
        if self.batch_size <= 0:
            batches = [dict(pending_bubbles)]
        else:
            for i in range(0, len(pending_bubbles), self.batch_size):
                batch_slice = pending_bubbles[i : i + self.batch_size]
                batches.append(dict(batch_slice))

        total_batches = len(batches)

        for i, batch in enumerate(batches, 1):
            logger.info("Translating batch %d/%d (%d unique bubbles)...", i, total_batches, len(batch))
            chunk_results = self._translate_single_batch(batch, target_lang=target_lang)

            for b_id, translated in chunk_results.items():
                all_translations[b_id] = translated
                # Propagate translation to identical duplicate bubbles in the chapter
                text_ja = bid_to_text_ja.get(b_id)
                if text_ja and text_ja in unique_to_translate:
                    for duplicate_id in unique_to_translate[text_ja]:
                        all_translations[duplicate_id] = translated

            if on_batch_progress:
                on_batch_progress(i, total_batches, len(all_translations))

        return all_translations

    def _translate_single_batch(
        self,
        payload_items: Union[Dict[str, str], List[Dict[str, Any]]],
        target_lang: str = "en"
    ) -> Dict[str, str]:
        # Normalize payload to flat dict: {bubble_id: text_ja}
        if isinstance(payload_items, dict):
            flat_dict = payload_items
        elif isinstance(payload_items, list):
            flat_dict = {}
            for item in payload_items:
                if isinstance(item, dict):
                    if "bubbles" in item:
                        for b in item["bubbles"]:
                            flat_dict[b["id"]] = b.get("text_ja", "")
                    elif "id" in item and "text_ja" in item:
                        flat_dict[item["id"]] = item["text_ja"]
        else:
            flat_dict = {}

        if not flat_dict:
            return {}

        lang_desc = (
            "Indonesian (Bahasa Indonesia santai/alami sesuai konteks manga/komik)"
            if target_lang.lower() in ("id", "indonesian")
            else "English"
        )

        system_prompt = (
            "You are a professional manga localization translator.\n"
            f"Translate each extracted dialogue speech bubble into natural, fluent {lang_desc} that accurately reflects character voice, emotion, and manga context.\n"
            "Rules:\n"
            "1. Output strictly a valid JSON object mapping each bubble ID to its translation, and nothing else. Do not include markdown codeblocks, conversational preambles, or explanations.\n"
            "2. Preserve every bubble ID key exactly as given in the input.\n"
            "3. Keep emotional punctuation (e.g. '...!', '?!', '—') natural and intact.\n\n"
            "Example Input:\n"
            '{"p1_b1": "こんにちは！", "p1_b2": "大丈夫ですか？"}\n\n'
            "Example Output:\n"
            '{"p1_b1": "Hello!", "p1_b2": "Are you alright?"}'
        )

        user_content = (
            f"Translate the following speech bubbles into natural, fluent {lang_desc}.\n"
            'Output strictly in this JSON format: {"<bubble_id>": "<translated text>"}\n\n'
            + json.dumps(flat_dict, ensure_ascii=False)
        )

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.3
        }

        # Try to enforce JSON mode if compatible
        if "gpt" in self.model.lower() or "gemini" in self.model.lower():
            body["response_format"] = {"type": "json_object"}

        req_data = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(self.base_url, data=req_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                resp_bytes = response.read()
                resp_json = json.loads(resp_bytes.decode("utf-8"))
        except HTTPError as e:
            err_msg = f"HTTP Error {e.code}: {e.reason}"
            try:
                err_body = e.read().decode("utf-8")
                err_msg += f" - {err_body}"
            except Exception:
                pass
            logger.error(err_msg)
            raise TranslationError(err_msg) from e
        except URLError as e:
            err_msg = f"Network Connection Error: {e.reason}"
            logger.error(err_msg)
            raise TranslationError(err_msg) from e
        except Exception as e:
            logger.error(f"Translation request failed: {e}")
            raise TranslationError(str(e)) from e

        return self._parse_response(resp_json)

    def _parse_response(self, resp_json: Dict[str, Any]) -> Dict[str, str]:
        try:
            choices = resp_json.get("choices", [])
            if not choices:
                raise TranslationError(f"API returned no choices: {resp_json}")
            msg = choices[0].get("message", {})
            content = msg.get("content") or ""
            if not content.strip() and msg.get("reasoning_content"):
                content = msg.get("reasoning_content") or ""

            refusal = msg.get("refusal")
            if refusal:
                raise TranslationError(f"Model refused translation: {refusal}")

            content = content.strip()
            if not content:
                raise TranslationError("Model returned an empty response.")

            # Remove reasoning / thought blocks if emitted by reasoning models
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

            # Clean possible markdown formatting anywhere in content
            md_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if md_match:
                content = md_match.group(1).strip()
            elif content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content).strip()

            parsed = None
            try:
                parsed = json.loads(content, strict=False)
            except json.JSONDecodeError:
                # Fallback: extract the JSON object within the text
                match = re.search(r"\{[\s\S]*\}", content)
                if match:
                    json_str = match.group(0)
                    try:
                        parsed = json.loads(json_str, strict=False)
                    except json.JSONDecodeError:
                        # Clean trailing commas before closing braces/brackets
                        cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)
                        parsed = json.loads(cleaned, strict=False)
                else:
                    raise

            translations = {}
            if isinstance(parsed, dict):
                if "translations" in parsed and isinstance(parsed["translations"], list):
                    for item in parsed["translations"]:
                        if isinstance(item, dict):
                            bid = item.get("id")
                            ten = item.get("text_en") or item.get("text") or item.get("translation", "")
                            if bid:
                                translations[str(bid)] = str(ten)
                elif "chapter" in parsed and isinstance(parsed["chapter"], list):
                    for page in parsed["chapter"]:
                        if isinstance(page, dict):
                            for b in page.get("bubbles", []):
                                if isinstance(b, dict):
                                    bid = b.get("id")
                                    ten = b.get("text_en") or b.get("text") or b.get("translation", "")
                                    if bid:
                                        translations[str(bid)] = str(ten)
                else:
                    for k, v in parsed.items():
                        if isinstance(v, str):
                            translations[str(k)] = v
                        elif isinstance(v, dict):
                            ten = v.get("text_en") or v.get("text") or v.get("translation", "")
                            if ten:
                                translations[str(k)] = str(ten)
            return translations
        except json.JSONDecodeError as e:
            raise TranslationError(f"Failed to parse LLM response JSON: {e}") from e
        except Exception as e:
            if isinstance(e, TranslationError):
                raise
            raise TranslationError(f"Error extracting translations: {e}") from e
