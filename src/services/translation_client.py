import json
import logging
import re
import urllib.request
from urllib.error import HTTPError, URLError
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import unicodedata
from src.models.translation_item import PageTranslation, BubbleBlock
from src.services.image_compression import compress_image_to_webp

logger = logging.getLogger(__name__)

class TranslationError(Exception):
    pass

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
                text = re.sub(r"([ー\u2014―\-\.~…・])\1{3,}", r"\1\1\1", text).strip()
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
            "3. Keep emotional punctuation (e.g. '...!', '?!', '--') natural and intact.\n\n"
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
            if "gpt" in self.model.lower() or "gemini" in self.model.lower():
                body["response_format"] = {"type": "json_object"}

        resp_json = self._execute_post_request(body)
        return self._parse_response(resp_json)

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
            if "gpt" in self.model.lower() or "gemini" in self.model.lower():
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

    def _parse_response(self, resp_json: Dict[str, Any]) -> Dict[str, str]:
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
            if "gpt" in self.model.lower() or "gemini" in self.model.lower():
                body["response_format"] = {"type": "json_object"}

        resp_json = self._execute_post_request(body, timeout=timeout)
        return self._parse_response(resp_json)

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
            if "gpt" in self.model.lower() or "gemini" in self.model.lower():
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
