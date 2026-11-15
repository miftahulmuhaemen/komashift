import json
import logging
import re
import time
import urllib.request
from urllib.error import HTTPError, URLError
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import unicodedata
from src.models.translation_item import PageTranslation, BubbleBlock
from src.services.image_compression import compress_image_to_webp
from src.ports.translation_provider import TranslationError

logger = logging.getLogger(__name__)

class OpenAITranslator:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        model: str = "gemini-3.5-flash-lite",
        timeout: float = 300.0,
        batch_size: int = 0,
        protocol: str = "openai"
    ):
        self.api_key = api_key.strip()
        self.protocol = (protocol or "openai").lower().strip()
        self.base_url = self._normalize_endpoint(base_url.strip())
        self.model = model.strip() or "gemini-3.5-flash-lite"
        self.timeout = max(300.0, float(timeout)) if timeout else 300.0
        self.batch_size = max(0, int(batch_size)) if batch_size is not None else 0

    def _normalize_endpoint(self, url: str) -> str:
        url = url.rstrip("/")
        if self.protocol == "anthropic":
            if not url:
                return "https://api.anthropic.com/v1/messages"
            if not url.endswith("/messages"):
                url = f"{url}/messages"
            return url
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
        norm = re.sub(r"~{4,}", "~~~", norm)
        return norm

    @staticmethod
    def _clamp_repeated_symbols(text: str) -> str:
        """Clamps long repetitive sound markers, punctuation, and Japanese wave dashes."""
        return re.sub(r"([ー\u2014―\-\.~…・\u301c\uff5e])\1{2,}", r"\1\1\1", text.strip())

    def _split_pages_into_adaptive_batches(
        self,
        pages: List[PageTranslation],
        target_bubbles: int = 90,
        max_tolerance: int = 110
    ) -> List[List[PageTranslation]]:
        """
        Splits chapter pages into adaptive batches aligned to page boundaries.
        Target threshold: ~90 bubbles. Max tolerance: 110 bubbles.
        Accumulates full pages; if adding the next page would cause total bubbles to exceed
        max_tolerance, falls back and cuts cleanly at the previous page boundary.
        Never splits a single page across batches.
        """
        if not pages:
            return []

        batches: List[List[PageTranslation]] = []
        current_batch: List[PageTranslation] = []
        current_count = 0

        for p in pages:
            p_count = sum(
                1 for b in p.bubbles
                if b.text_ja.strip() and not self._is_pure_punctuation_or_symbol(
                    self._clamp_repeated_symbols(b.text_ja)
                )
            )

            if not current_batch:
                current_batch.append(p)
                current_count += p_count
                continue

            if current_count + p_count <= max_tolerance:
                current_batch.append(p)
                current_count += p_count
            else:
                batches.append(current_batch)
                current_batch = [p]
                current_count = p_count

        if current_batch:
            batches.append(current_batch)

        return batches

    def translate_chapter(
        self,
        pages: List[PageTranslation],
        target_lang: str = "en",
        on_batch_progress = None
    ) -> Dict[str, str]:
        all_translations: Dict[str, str] = {}
        if not pages:
            return all_translations

        # 1. Local resolution for pure punctuation/symbol bubbles (0 token, 0 latency)
        for p in pages:
            for b in p.bubbles:
                text = b.text_ja.strip()
                if not text:
                    continue
                norm_punct = self._clamp_repeated_symbols(text)
                if not norm_punct:
                    continue
                if self._is_pure_punctuation_or_symbol(norm_punct):
                    all_translations[b.id] = self._normalize_punctuation_text(norm_punct)

        # 2. Check batching mode: fixed-size slicing if batch_size > 0
        if self.batch_size > 0:
            return self._translate_chapter_fixed_slices(
                pages, all_translations, target_lang=target_lang, on_batch_progress=on_batch_progress
            )

        # 3. Page-Boundary Adaptive Batching (target ~90 bubbles, max tolerance 110 bubbles)
        page_batches = self._split_pages_into_adaptive_batches(pages, target_bubbles=90, max_tolerance=110)
        total_batches = len(page_batches)

        summaries_list: List[str] = []
        recent_dialogue_lines: List[str] = []

        for i, batch_pages in enumerate(page_batches, 1):
            batch_payload: Dict[str, Any] = {}
            batch_bid_to_text: Dict[str, str] = {}
            batch_unique_to_bids: Dict[str, List[str]] = {}

            for p in batch_pages:
                for b in p.bubbles:
                    text = b.text_ja.strip()
                    if not text:
                        continue
                    text = self._clamp_repeated_symbols(text)
                    if not text or self._is_pure_punctuation_or_symbol(text):
                        continue

                    batch_bid_to_text[b.id] = text
                    if text in batch_unique_to_bids:
                        batch_unique_to_bids[text].append(b.id)
                    else:
                        batch_unique_to_bids[text] = [b.id]
                        if getattr(b, "speaker", "") or getattr(b, "expression", "") or getattr(b, "speech_type", ""):
                            payload = {"text": text}
                            if b.speaker:
                                payload["speaker"] = b.speaker
                            if b.expression:
                                payload["expression"] = b.expression
                            if b.speech_type:
                                payload["speech_type"] = b.speech_type
                            batch_payload[b.id] = payload
                        else:
                            batch_payload[b.id] = text

            if not batch_payload:
                continue

            prev_summary = "\n\n".join(summaries_list[-3:]) if summaries_list else ""
            logger.info("Translating batch %d/%d (%d pages, %d unique bubbles)...", i, total_batches, len(batch_pages), len(batch_payload))

            max_retries = 3
            batch_res = None
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    try:
                        batch_res = self._translate_single_batch(
                            batch_payload,
                            target_lang=target_lang,
                            prev_summary=prev_summary,
                            recent_lines=recent_dialogue_lines,
                            is_multi_batch=(total_batches > 1),
                            return_summary=True
                        )
                    except TypeError:
                        batch_res = self._translate_single_batch(batch_payload, target_lang=target_lang)

                    res_dict = batch_res[0] if isinstance(batch_res, tuple) else batch_res
                    if isinstance(res_dict, dict) and len(res_dict) < len(batch_payload) * 0.85:
                        raise TranslationError(f"Model omitted bubbles: received {len(res_dict)}/{len(batch_payload)}")
                    break
                except Exception as e:
                    last_err = e
                    if attempt < max_retries:
                        backoff = 2 ** (attempt - 1) * 2
                        logger.warning(
                            "Batch %d/%d translation failed or incomplete (attempt %d/%d): %s. Retrying in %ds...",
                            i, total_batches, attempt, max_retries, e, backoff
                        )
                        time.sleep(backoff)
                    else:
                        logger.error("Batch %d/%d failed after %d attempts: %s", i, total_batches, max_retries, e)
                        raise last_err

            if isinstance(batch_res, tuple):
                chunk_results, new_summary = batch_res
            elif isinstance(batch_res, dict):
                chunk_results, new_summary = batch_res, ""
            else:
                chunk_results, new_summary = {}, ""

            if new_summary:
                summaries_list.append(new_summary)

            batch_translations: Dict[str, str] = {}
            for b_id, translated in chunk_results.items():
                batch_translations[b_id] = translated
                all_translations[b_id] = translated
                text_ja = batch_bid_to_text.get(b_id)
                if text_ja and text_ja in batch_unique_to_bids:
                    for duplicate_id in batch_unique_to_bids[text_ja]:
                        batch_translations[duplicate_id] = translated
                        all_translations[duplicate_id] = translated

            # Extract last 3 translated dialogue lines from this batch for context chaining
            batch_lines = []
            for p in reversed(batch_pages):
                for b in reversed(p.bubbles):
                    trans = all_translations.get(b.id)
                    if trans and not self._is_pure_punctuation_or_symbol(trans):
                        spk = getattr(b, "speaker", "")
                        line_str = f'{spk}: "{trans}"' if spk else f'"{trans}"'
                        batch_lines.insert(0, f"[{b.id}] {line_str}")
                        if len(batch_lines) >= 3:
                            break
                if len(batch_lines) >= 3:
                    break
            if batch_lines:
                recent_dialogue_lines = batch_lines

            if on_batch_progress:
                try:
                    on_batch_progress(i, total_batches, len(all_translations), all_translations)
                except TypeError:
                    on_batch_progress(i, total_batches, len(all_translations))

        return all_translations

    def _translate_chapter_fixed_slices(
        self,
        pages: List[PageTranslation],
        all_translations: Dict[str, str],
        target_lang: str = "en",
        on_batch_progress = None
    ) -> Dict[str, str]:
        unique_to_translate: Dict[str, List[str]] = {}
        pending_bubbles: List[Tuple[str, Any]] = []
        bid_to_text_ja: Dict[str, str] = {}

        for p in pages:
            for b in p.bubbles:
                text = b.text_ja.strip()
                if not text:
                    continue
                text = self._clamp_repeated_symbols(text)
                if not text or self._is_pure_punctuation_or_symbol(text):
                    continue

                if text in unique_to_translate:
                    unique_to_translate[text].append(b.id)
                else:
                    unique_to_translate[text] = [b.id]
                    if getattr(b, "speaker", "") or getattr(b, "expression", "") or getattr(b, "speech_type", ""):
                        payload = {"text": text}
                        if b.speaker:
                            payload["speaker"] = b.speaker
                        if b.expression:
                            payload["expression"] = b.expression
                        if b.speech_type:
                            payload["speech_type"] = b.speech_type
                        pending_bubbles.append((b.id, payload))
                    else:
                        pending_bubbles.append((b.id, text))
                    bid_to_text_ja[b.id] = text

        if not pending_bubbles:
            return all_translations

        batches = [
            dict(pending_bubbles[i : i + self.batch_size])
            for i in range(0, len(pending_bubbles), self.batch_size)
        ]
        total_batches = len(batches)

        for i, batch in enumerate(batches, 1):
            logger.info("Translating fixed batch %d/%d (%d bubbles)...", i, total_batches, len(batch))
            chunk_results = self._translate_single_batch(batch, target_lang=target_lang)
            for b_id, translated in chunk_results.items():
                all_translations[b_id] = translated
                text_ja = bid_to_text_ja.get(b_id)
                if text_ja and text_ja in unique_to_translate:
                    for duplicate_id in unique_to_translate[text_ja]:
                        all_translations[duplicate_id] = translated

            if on_batch_progress:
                try:
                    on_batch_progress(i, total_batches, len(all_translations), all_translations)
                except TypeError:
                    on_batch_progress(i, total_batches, len(all_translations))

        return all_translations

    def _translate_single_batch(
        self,
        payload_items: Union[Dict[str, str], List[Dict[str, Any]]],
        target_lang: str = "en",
        prev_summary: str = "",
        recent_lines: Optional[List[str]] = None,
        is_multi_batch: bool = False,
        return_summary: bool = False
    ) -> Union[Dict[str, str], Tuple[Dict[str, str], str]]:
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
            return ({}, "") if return_summary else {}

        lang_desc = (
            "Indonesian (Bahasa Indonesia santai/alami sesuai konteks manga/komik)"
            if target_lang.lower() in ("id", "indonesian")
            else "English"
        )

        has_visual_cues = any(isinstance(v, dict) and any(v.get(k) for k in ("speaker", "expression", "speech_type")) for v in flat_dict.values())
        if has_visual_cues:
            system_prompt = (
                "You are an expert manga localization translator.\n"
                f"Translate each extracted dialogue speech bubble into natural, fluent {lang_desc}.\n"
                "You are provided with visual context tags (speaker character, emotional expression, speech type).\n"
                "Rules:\n"
                "1. Use character voice, emotional expressions, and speech types to guide accurate tone, pronouns, and natural manga dialogue.\n"
                "2. Maintain narrative continuity, character voices, and terminology with any preceding context provided.\n"
                "3. Correct minor OCR artifacts or slurred sounds into natural dialogue fitting the scene context (never translate distorted sounds literally as food items or bizarre non-sequiturs).\n"
            )
            if is_multi_batch:
                system_prompt += (
                    "4. Output strictly a valid JSON object with two top-level keys: 'narrative_summary' (2-3 sentences summarizing key narrative events, character interactions, and story progression in this batch) and 'translations' (mapping each bubble ID to its localized translation). Do not include markdown codeblocks or explanations.\n"
                )
            else:
                system_prompt += (
                    "4. Output strictly a valid JSON object mapping each bubble ID to its translation, and nothing else. Do not include markdown or explanations.\n"
                )
            system_prompt += (
                "5. Preserve every bubble ID key exactly as given in the input without omitting any bubble.\n"
                "6. Keep emotional punctuation intact."
            )
        else:
            system_prompt = (
                "You are a professional manga localization translator.\n"
                f"Translate each extracted dialogue speech bubble into natural, fluent {lang_desc} that accurately reflects character voice, emotion, and manga context.\n"
                "Rules:\n"
                "1. Maintain narrative continuity, character voices, and terminology with any preceding context provided.\n"
                "2. Correct minor OCR artifacts or slurred sounds into natural dialogue fitting the scene context (never translate distorted sounds literally as food items or bizarre non-sequiturs).\n"
            )
            if is_multi_batch:
                system_prompt += (
                    "3. Output strictly a valid JSON object with two top-level keys: 'narrative_summary' (2-3 sentences summarizing key narrative events, character interactions, and story progression in this batch) and 'translations' (mapping each bubble ID to its localized translation). Do not include markdown codeblocks, conversational preambles, or explanations.\n"
                )
            else:
                system_prompt += (
                    "3. Output strictly a valid JSON object mapping each bubble ID to its translation, and nothing else. Do not include markdown codeblocks, conversational preambles, or explanations.\n"
                )
            system_prompt += (
                "4. Preserve every bubble ID key exactly as given in the input without omitting any bubble.\n"
                "5. Keep emotional punctuation (e.g. '...!', '?!', '--') natural and intact."
            )

        context_parts = []
        if prev_summary and prev_summary.strip():
            context_parts.append(f"--- Preceding Story Context ---\n{prev_summary.strip()}")
        if recent_lines:
            dialogue_text = "\n".join(f"- {line}" for line in recent_lines if line.strip())
            if dialogue_text:
                context_parts.append(f"--- Immediately Preceding Dialogue ---\n{dialogue_text}")

        context_header = ("\n\n".join(context_parts) + "\n\n") if context_parts else ""

        if is_multi_batch:
            user_content = (
                f"{context_header}"
                f"Translate the following speech bubbles into natural, fluent {lang_desc}.\n"
                'Output strictly in this JSON format:\n'
                '{\n  "narrative_summary": "<2-3 sentences summarizing key narrative events in this batch>",\n  "translations": {"<bubble_id>": "<translated text>"}\n}\n\n'
                + json.dumps(flat_dict, ensure_ascii=False)
            )
        else:
            user_content = (
                f"{context_header}"
                f"Translate the following speech bubbles into natural, fluent {lang_desc}.\n"
                'Output strictly in this JSON format: {"<bubble_id>": "<translated text>"}\n\n'
                + json.dumps(flat_dict, ensure_ascii=False)
            )

        if self.protocol == "anthropic":
            body = {
                "model": self.model,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_content}
                ],
                "max_tokens": 4096,
                "temperature": 0.3
            }
        else:
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.3
            }
            if self.protocol == "openai":
                body["response_format"] = {"type": "json_object"}

        resp_json = self._execute_post_request(body)
        translations, summary = self._parse_batch_translation_response(resp_json)
        if return_summary:
            return translations, summary
        return translations

    def translate_single_text_with_context(
        self,
        text_ja: str,
        target_lang: str = "en",
        prev_context: Optional[str] = None,
        curr_context: Optional[str] = None,
        next_context: Optional[str] = None
    ) -> str:
        """
        Translates a single dialogue line using surrounding page context (texts only, no images)
        for high-accuracy manga localization.
        """
        if not text_ja.strip():
            return ""

        if self._is_pure_punctuation_or_symbol(text_ja):
            return self._normalize_punctuation_text(text_ja)

        lang_desc = (
            "Indonesian (Bahasa Indonesia santai/alami sesuai konteks manga/komik)"
            if target_lang.lower() in ("id", "indonesian")
            else "English"
        )

        system_prompt = (
            "You are a professional manga localization translator and proofreader.\n"
            f"You will translate a specific dialogue line into natural, fluent {lang_desc}.\n"
            "You are provided with surrounding scene context from the previous page, current page, and next page.\n"
            "Use this contextual dialogue to ensure accurate tone, character voice, gender, and narrative continuity.\n"
            "Return strictly a valid JSON object mapping the target line to its translation: "
            '{"target_translation": "<translated text>"}'
        )

        context_sections = []
        if prev_context and prev_context.strip():
            context_sections.append(f"--- Context from Previous Page ---\n{prev_context.strip()}")
        if curr_context and curr_context.strip():
            context_sections.append(f"--- Context from Current Page (Other bubbles) ---\n{curr_context.strip()}")
        if next_context and next_context.strip():
            context_sections.append(f"--- Context from Next Page ---\n{next_context.strip()}")

        context_str = "\n\n".join(context_sections) if context_sections else "(No additional surrounding context available)"

        user_content = (
            f"Surrounding Scene Context:\n{context_str}\n\n"
            f"Target Japanese Text to Translate:\n{text_ja.strip()}\n\n"
            f"Translate the target Japanese text into natural, fluent {lang_desc} matching the scene context.\n"
            'Output strictly in this JSON format: {"target_translation": "<translated text>"}'
        )

        if self.protocol == "anthropic":
            body = {
                "model": self.model,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_content}
                ],
                "max_tokens": 1024,
                "temperature": 0.3
            }
        else:
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.3
            }
            if self.protocol == "openai":
                body["response_format"] = {"type": "json_object"}

        resp_json = self._execute_post_request(body)
        parsed = self._parse_response(resp_json)
        if isinstance(parsed, dict):
            if "target_translation" in parsed:
                return str(parsed["target_translation"]).strip()
            # If model returned bubble-like mapping
            for val in parsed.values():
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return text_ja

    def _execute_post_request(self, body: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        req_data = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if self.protocol == "anthropic":
            if self.api_key:
                headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

        req_timeout = float(timeout) if timeout else self.timeout
        req = urllib.request.Request(self.base_url, data=req_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                resp_bytes = response.read()
                return json.loads(resp_bytes.decode("utf-8"))
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

    @staticmethod
    def _extract_json_from_content(content: str) -> Any:
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

        try:
            return json.loads(content, strict=False)
        except json.JSONDecodeError:
            # Fallback: extract the JSON structure within the text
            match = re.search(r"[\{\[][\s\S]*[\}\]]", content)
            if match:
                json_str = match.group(0)
                try:
                    return json.loads(json_str, strict=False)
                except json.JSONDecodeError:
                    cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)
                    return json.loads(cleaned, strict=False)
            raise

    def _parse_batch_translation_response(
        self, resp_json: Dict[str, Any]
    ) -> Tuple[Dict[str, str], str]:
        try:
            if "content" in resp_json and isinstance(resp_json["content"], list):
                text_blocks = [b.get("text", "") for b in resp_json["content"] if isinstance(b, dict) and b.get("type") == "text"]
                content = "\n".join(text_blocks)
            else:
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

            parsed = self._extract_json_from_content(content)
            translations: Dict[str, str] = {}
            summary = ""

            if isinstance(parsed, dict):
                summary = str(parsed.get("narrative_summary") or "").strip()
                raw_trans = parsed.get("translations")

                if isinstance(raw_trans, dict):
                    for k, v in raw_trans.items():
                        if isinstance(v, str):
                            translations[str(k)] = v
                        elif isinstance(v, dict):
                            ten = v.get("text_en") or v.get("text") or v.get("translation", "")
                            if ten:
                                translations[str(k)] = str(ten)
                elif isinstance(raw_trans, list):
                    for item in raw_trans:
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
                        if k == "narrative_summary":
                            continue
                        if isinstance(v, str):
                            translations[str(k)] = v
                        elif isinstance(v, dict):
                            ten = v.get("text_en") or v.get("text") or v.get("translation", "")
                            if ten:
                                translations[str(k)] = str(ten)
            return translations, summary
        except json.JSONDecodeError as e:
            raise TranslationError(f"Failed to parse LLM response JSON: {e}") from e
        except Exception as e:
            if isinstance(e, TranslationError):
                raise
            raise TranslationError(f"Error extracting translations: {e}") from e

    def _parse_response(self, resp_json: Dict[str, Any]) -> Dict[str, str]:
        translations, _ = self._parse_batch_translation_response(resp_json)
        return translations

    def translate_page_visual_hybrid(
        self,
        image_path: Union[str, Path],
        page: PageTranslation,
        target_lang: str = "en",
        scale_pct: int = 75,
        quality: int = 75,
        timeout: Optional[float] = None
    ) -> Dict[str, str]:
        if not page.bubbles:
            return {}

        image_path = Path(image_path)
        data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
            image_path, scale_pct=scale_pct, quality=quality
        )

        lang_desc = (
            "Indonesian"
            if target_lang.lower().startswith("id")
            else "English"
        )

        bubbles_prompt_list = []
        for b in page.bubbles:
            bx, by, bw, bh = b.expanded_bbox if b.expanded_bbox else b.bbox
            ymin = int(by * 1000 / orig_h) if orig_h > 0 else 0
            xmin = int(bx * 1000 / orig_w) if orig_w > 0 else 0
            ymax = int((by + bh) * 1000 / orig_h) if orig_h > 0 else 1000
            xmax = int((bx + bw) * 1000 / orig_w) if orig_w > 0 else 1000
            hint = f" (OCR hint: '{b.text_ja}')" if b.text_ja else ""
            bubbles_prompt_list.append(f"- {b.id}: location=[ymin:{ymin}, xmin:{xmin}, ymax:{ymax}, xmax:{xmax}]{hint}")

        bubbles_text = "\n".join(bubbles_prompt_list)

        system_prompt = (
            "You are an expert manga localization translator and proofreader. "
            "You are provided with a manga page image and the exact detected speech bubble regions on the page. "
            f"For each bubble ID, examine the dialogue at that location in context of the artwork, character expressions, and story flow. "
            f"Correct any OCR mistakes using your visual comprehension, and translate each dialogue bubble into natural, fluent {lang_desc}. "
            f"Return strictly a valid JSON object mapping each bubble ID to its {lang_desc} translation: {{\"<bubble_id>\": \"<translation>\"}}."
        )

        user_prompt = (
            "Here are the detected speech bubbles on this page:\n"
            f"{bubbles_text}\n\n"
            f"Look at each speech bubble location on the image, read the true text, and translate it into natural, fluent {lang_desc}.\n"
            "Output strictly in JSON format: {\"<bubble_id>\": \"<translated text>\"}"
        )

        if self.protocol == "anthropic":
            media_type = "image/webp"
            b64_data = data_url
            if "," in data_url:
                header, b64_data = data_url.split(",", 1)
                if ":" in header and ";" in header:
                    media_type = header.split(":", 1)[1].split(";", 1)[0]
            body = {
                "model": self.model,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data
                                }
                            },
                            {
                                "type": "text",
                                "text": user_prompt
                            }
                        ]
                    }
                ],
                "max_tokens": 4096,
                "temperature": 0.3
            }
        else:
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }
                ],
                "temperature": 0.3
            }
            if self.protocol == "openai":
                body["response_format"] = {"type": "json_object"}

        resp_json = self._execute_post_request(body, timeout=timeout)
        return self._parse_response(resp_json)

    def perceive_page_visual_context(
        self,
        image_path: Union[str, Path],
        page: PageTranslation,
        scale_pct: int = 75,
        quality: int = 75,
        timeout: Optional[float] = None
    ) -> Dict[str, Dict[str, str]]:
        """
        Pass 1 Perception: Inspects speech bubble locations on the image and extracts
        accurate Japanese dialogue (text_ja) along with visual context (speaker, expression, speech_type).
        """
        if not page.bubbles:
            return {}

        image_path = Path(image_path)
        data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
            image_path, scale_pct=scale_pct, quality=quality
        )

        bubbles_prompt_list = []
        for b in page.bubbles:
            bx, by, bw, bh = b.expanded_bbox if b.expanded_bbox else b.bbox
            ymin = int(by * 1000 / orig_h) if orig_h > 0 else 0
            xmin = int(bx * 1000 / orig_w) if orig_w > 0 else 0
            ymax = int((by + bh) * 1000 / orig_h) if orig_h > 0 else 1000
            xmax = int((bx + bw) * 1000 / orig_w) if orig_w > 0 else 1000
            hint = f" (OCR hint: '{b.text_ja}')" if b.text_ja else ""
            bubbles_prompt_list.append(f"- {b.id}: location=[ymin:{ymin}, xmin:{xmin}, ymax:{ymax}, xmax:{xmax}]{hint}")

        bubbles_text = "\n".join(bubbles_prompt_list)
        system_prompt = (
            "You are an expert manga visual editor and Japanese transcriptionist.\n"
            "For each detected speech bubble on this page:\n"
            "1. Transcribe the accurate Japanese dialogue (text_ja) from the artwork, correcting any OCR defects.\n"
            "2. Identify the character/speaker (e.g. 'Male student', 'Female protagonist', 'Teacher', 'Narrator').\n"
            "3. Identify the emotional expression or tone (e.g. 'Angry / shouting', 'Whispering', 'Blushing', 'Casual', 'Shocked').\n"
            "4. Identify the speech type ('Spoken dialogue', 'Internal thought', 'Narration', 'SFX').\n"
            "Return strictly a valid JSON object mapping each bubble ID to its details:\n"
            '{"<bubble_id>": {"text_ja": "...", "speaker": "...", "expression": "...", "speech_type": "..."}}'
        )
        user_prompt = (
            f"Detected speech bubbles on this page:\n{bubbles_text}\n\n"
            "Inspect each bubble on the artwork. Extract the accurate Japanese text, speaker, expression, and speech type.\n"
            'Output strictly JSON: {"<bubble_id>": {"text_ja": "...", "speaker": "...", "expression": "...", "speech_type": "..."}}'
        )

        if self.protocol == "anthropic":
            media_type = "image/webp"
            b64_data = data_url
            if "," in data_url:
                header, b64_data = data_url.split(",", 1)
                if ":" in header and ";" in header:
                    media_type = header.split(":", 1)[1].split(";", 1)[0]
            body = {
                "model": self.model,
                "system": system_prompt,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
                        {"type": "text", "text": user_prompt}
                    ]
                }],
                "max_tokens": 4096,
                "temperature": 0.2
            }
        else:
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }
                ],
                "temperature": 0.2
            }
            if self.protocol == "openai":
                body["response_format"] = {"type": "json_object"}

        resp_json = self._execute_post_request(body, timeout=timeout)
        content = ""
        if "content" in resp_json and isinstance(resp_json["content"], list):
            text_blocks = [b.get("text", "") for b in resp_json["content"] if isinstance(b, dict) and b.get("type") == "text"]
            content = "\n".join(text_blocks)
        else:
            choices = resp_json.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning_content") or ""

        parsed = self._extract_json_from_content(content)
        results: Dict[str, Dict[str, str]] = {}
        if isinstance(parsed, dict):
            for bid, val in parsed.items():
                if isinstance(val, dict):
                    results[str(bid)] = {
                        "text_ja": str(val.get("text_ja", "")).strip(),
                        "speaker": str(val.get("speaker", "")).strip(),
                        "expression": str(val.get("expression", "")).strip(),
                        "speech_type": str(val.get("speech_type", "")).strip(),
                    }
                elif isinstance(val, str):
                    results[str(bid)] = {
                        "text_ja": str(val).strip(),
                        "speaker": "",
                        "expression": "",
                        "speech_type": "",
                    }
        return results

    def translate_page_multimodal(
        self,
        image_path: Union[str, Path],
        page_index: int = 1,
        target_lang: str = "en",
        scale_pct: int = 75,
        quality: int = 75,
        timeout: Optional[float] = None
    ) -> PageTranslation:
        image_path = Path(image_path)
        data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
            image_path, scale_pct=scale_pct, quality=quality
        )

        lang_desc = (
            "Indonesian"
            if target_lang.lower().startswith("id")
            else "English"
        )

        system_prompt = (
            "You are a professional manga localization engine. "
            "Detect all speech bubbles, narration boxes, and text on the manga page in natural comic reading order (right-to-left, top-to-bottom across panels). "
            f"Transcribe the original Japanese text and translate it into natural, fluent {lang_desc}. "
            "Return strictly a valid JSON object matching the requested schema."
        )

        user_prompt = (
            f"Analyze this manga page. Detect every dialogue bubble or text block in natural reading order.\n"
            f"Translate each text into natural, fluent {lang_desc}.\n"
            "Return strictly a JSON object with this exact structure:\n"
            "{\n"
            '  "bubbles": [\n'
            "    {\n"
            '      "box_2d": [ymin, xmin, ymax, xmax],\n'
            '      "text_ja": "original Japanese text",\n'
            '      "text_en": "translated text"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Important: box_2d coordinates must be normalized integers from 0 to 1000 representing the bounding box [ymin, xmin, ymax, xmax] (where ymin is top, xmin is left, ymax is bottom, xmax is right)."
        )

        if self.protocol == "anthropic":
            media_type = "image/webp"
            b64_data = data_url
            if "," in data_url:
                header, b64_data = data_url.split(",", 1)
                if ":" in header and ";" in header:
                    media_type = header.split(":", 1)[1].split(";", 1)[0]
            body = {
                "model": self.model,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_data
                                }
                            },
                            {
                                "type": "text",
                                "text": user_prompt
                            }
                        ]
                    }
                ],
                "max_tokens": 4096,
                "temperature": 0.3
            }
        else:
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }
                ],
                "temperature": 0.3
            }
            if self.protocol == "openai":
                body["response_format"] = {"type": "json_object"}

        resp_json = self._execute_post_request(body, timeout=timeout)
        return self._parse_multimodal_response(resp_json, image_path.name, orig_w, orig_h, page_index=page_index)

    def _parse_multimodal_response(
        self,
        resp_json: Dict[str, Any],
        page_filename: str,
        orig_w: int,
        orig_h: int,
        page_index: int = 1
    ) -> PageTranslation:
        if "content" in resp_json and isinstance(resp_json["content"], list):
            text_blocks = [b.get("text", "") for b in resp_json["content"] if isinstance(b, dict) and b.get("type") == "text"]
            content = "\n".join(text_blocks)
        else:
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

        try:
            parsed = self._extract_json_from_content(content)
        except Exception as e:
            raise TranslationError(f"Failed to parse multimodal JSON response: {e}") from e

        bubble_items = []
        if isinstance(parsed, dict):
            bubble_items = (
                parsed.get("bubbles")
                or parsed.get("boxes")
                or parsed.get("translations")
                or []
            )
        elif isinstance(parsed, list):
            bubble_items = parsed

        bubbles: List[BubbleBlock] = []
        for idx, item in enumerate(bubble_items, start=1):
            if not isinstance(item, dict):
                continue

            box = item.get("box_2d") or item.get("bbox") or item.get("box") or [0, 0, 1000, 1000]
            if isinstance(box, (list, tuple)) and len(box) >= 4:
                b_coords = [float(v) for v in box[:4]]
                if all(0.0 <= v <= 1.0 for v in b_coords) and any(v > 0 for v in b_coords):
                    b_coords = [v * 1000.0 for v in b_coords]

                ymin = max(0.0, min(1000.0, b_coords[0]))
                xmin = max(0.0, min(1000.0, b_coords[1]))
                ymax = max(ymin, min(1000.0, b_coords[2]))
                xmax = max(xmin, min(1000.0, b_coords[3]))

                x = int(xmin * orig_w / 1000.0)
                y = int(ymin * orig_h / 1000.0)
                w = max(1, int((xmax - xmin) * orig_w / 1000.0))
                h = max(1, int((ymax - ymin) * orig_h / 1000.0))
            else:
                x, y, w, h = 0, 0, orig_w, orig_h

            text_ja = str(item.get("text_ja") or item.get("original") or item.get("text") or "").strip()
            text_en = str(item.get("text_en") or item.get("translation") or item.get("translated") or "").strip()

            b_id = f"p{page_index}_b{idx}"
            centroid = (x + w // 2, y + h // 2)
            expanded_bbox = (x, y, w, h)

            bubble = BubbleBlock(
                id=b_id,
                bbox=(x, y, w, h),
                text_ja=text_ja,
                text_en=text_en,
                expanded_bbox=expanded_bbox,
                centroid=centroid,
                shape="oval"
            )
            bubbles.append(bubble)

        return PageTranslation(
            page_filename=page_filename,
            page_width=orig_w,
            page_height=orig_h,
            bubbles=bubbles
        )
