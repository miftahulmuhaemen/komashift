import json
import logging
import re
import urllib.request
from urllib.error import HTTPError, URLError
from typing import List, Dict, Any, Optional
from src.models.translation_item import PageTranslation

logger = logging.getLogger(__name__)

class TranslationError(Exception):
    pass

class OpenAITranslator:
    def __init__(self, api_key: str, base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/", model: str = "gemini-3.5-flash-lite", timeout: float = 60.0):
        self.api_key = api_key.strip()
        self.base_url = self._normalize_endpoint(base_url.strip())
        self.model = model.strip() or "gemini-3.5-flash-lite"
        self.timeout = timeout

    def _normalize_endpoint(self, url: str) -> str:
        url = url.rstrip("/")
        if not url:
            return "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        return url

    def translate_chapter(self, pages: List[PageTranslation]) -> Dict[str, str]:
        # Collect all bubbles that have Japanese text
        payload_items = []
        for p in pages:
            page_bubbles = []
            for b in p.bubbles:
                text = b.text_ja.strip()
                if text:
                    page_bubbles.append({"id": b.id, "text_ja": text})
            if page_bubbles:
                payload_items.append({
                    "page": p.page_filename,
                    "bubbles": page_bubbles
                })

        if not payload_items:
            return {}

        system_prompt = (
            "You are a professional manga localization translator. "
            "You will receive extracted Japanese dialogue blocks grouped by page for an entire manga chapter. "
            "Translate each speech bubble into natural, fluent English that accurately reflects character voice and emotion. "
            "Maintain narrative and pronoun consistency across all pages. "
            "Respond strictly with valid JSON in this exact structure:\n"
            '{\n  "translations": [\n    {"id": "<bubble_id>", "text_en": "<translated English text>"}\n  ]\n}'
        )

        user_content = json.dumps({"chapter": payload_items}, ensure_ascii=False)

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
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "FolderImagePreviewer-Translator"
        }

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
                raise TranslationError("No choices in API response")
            content = choices[0].get("message", {}).get("content", "").strip()
            
            # Clean possible markdown formatting
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            
            parsed = json.loads(content)
            translations = {}
            for item in parsed.get("translations", []):
                bid = item.get("id")
                ten = item.get("text_en", "")
                if bid:
                    translations[bid] = ten
            return translations
        except json.JSONDecodeError as e:
            raise TranslationError(f"Failed to parse LLM response JSON: {e}") from e
        except Exception as e:
            raise TranslationError(f"Error extracting translations: {e}") from e
