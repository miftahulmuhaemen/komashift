import base64
import io
import json
import logging
import re
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.error import HTTPError, URLError
from PIL import Image
from src.models.translation_item import PageTranslation, BubbleBlock

logger = logging.getLogger(__name__)

class MangaOcrDetector:
    """
    Detector and OCR engine for speech bubbles in manga images.
    Supports local engines or Vision LLM endpoints (e.g. Gemini / OpenAI Vision).
    """
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        model: str = "gemini-3.5-flash-lite",
        ocr_engine=None
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.strip()
        self.model = model.strip() or "gemini-3.5-flash-lite"
        self._engine = ocr_engine
        self._init_engine()

    def _init_engine(self):
        if self._engine is not None:
            return
        try:
            from manga_ocr import MangaOcr  # type: ignore
            self._engine = MangaOcr()
            logger.info("Loaded local manga-ocr engine successfully.")
        except Exception:
            self._engine = None

    def detect_page(self, image_path: Path, page_index: int = 1, log_callback=None) -> PageTranslation:
        """
        Detect speech bubbles and extract Japanese text from the image.
        Uses local manga-ocr if present; otherwise calls Vision API with the configured key.
        """
        try:
            with Image.open(image_path) as img:
                orig_width, orig_height = img.size
                image_mode = img.mode
                # Convert to RGB if needed
                if image_mode not in ("RGB", "L"):
                    img = img.convert("RGB")
        except Exception as e:
            err = f"Failed to open image {image_path}: {e}"
            logger.error(err)
            if log_callback:
                log_callback(err)
            return PageTranslation(page_filename=image_path.name, page_width=0, page_height=0, bubbles=[])

        # If we have an API key and no local engine, use Vision LLM detection
        if self._engine is None and self.api_key:
            return self._detect_with_vision(image_path, orig_width, orig_height, page_index, log_callback)

        return PageTranslation(
            page_filename=image_path.name,
            page_width=orig_width,
            page_height=orig_height,
            bubbles=[]
        )

    def _detect_with_vision(
        self,
        image_path: Path,
        orig_width: int,
        orig_height: int,
        page_index: int,
        log_callback=None
    ) -> PageTranslation:
        """
        Call OpenAI/Gemini Vision API to identify bubbles, text, and English translations.
        """
        msg = f"Scanning {image_path.name} with Vision model ({self.model})..."
        logger.info(msg)
        if log_callback:
            log_callback(msg)

        # Downscale for API payload if larger than 1600px
        max_dim = 1600
        scale_ratio = 1.0
        with Image.open(image_path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > max_dim:
                scale_ratio = max_dim / float(max(w, h))
                new_w = int(w * scale_ratio)
                new_h = int(h * scale_ratio)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
            cur_w, cur_h = img.size

        prompt = (
            "You are a specialized manga OCR and localization engine. "
            "Inspect this manga page carefully and detect all speech bubbles, thought bubbles, and dialogue text regions.\n"
            f"Image dimensions: {cur_w}x{cur_h} pixels.\n"
            "For each dialogue bubble found, return:\n"
            "- 'id': unique id (e.g. 'b1', 'b2')\n"
            f"- 'bbox': [x, y, width, height] bounding box rectangle in pixel coordinates (0 to {cur_w} for x, 0 to {cur_h} for y)\n"
            "- 'text_ja': original Japanese text\n"
            "- 'text_en': natural English translation of the dialogue\n\n"
            "Respond strictly in valid JSON matching this schema:\n"
            "{\n  \"bubbles\": [\n    {\"id\": \"b1\", \"bbox\": [x, y, w, h], \"text_ja\": \"...\", \"text_en\": \"...\"}\n  ]\n}"
        )

        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}
                ]
            }],
            "temperature": 0.2
        }

        if "gpt" in self.model.lower() or "gemini" in self.model.lower():
            body["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "FolderImagePreviewer-Vision"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=90.0) as response:
                resp_bytes = response.read()
                resp_json = json.loads(resp_bytes.decode("utf-8"))
        except HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            err_msg = f"Vision API HTTP Error {e.code}: {e.reason} - {err_body}"
            logger.error(err_msg)
            if log_callback:
                log_callback(err_msg)
            raise RuntimeError(err_msg) from e
        except Exception as e:
            err_msg = f"Vision API request failed: {e}"
            logger.error(err_msg)
            if log_callback:
                log_callback(err_msg)
            raise RuntimeError(err_msg) from e

        bubbles = self._parse_vision_response(resp_json, scale_ratio, page_index, log_callback)
        success_msg = f"Detected {len(bubbles)} bubbles on {image_path.name}"
        logger.info(success_msg)
        if log_callback:
            log_callback(success_msg)

        return PageTranslation(
            page_filename=image_path.name,
            page_width=orig_width,
            page_height=orig_height,
            bubbles=bubbles
        )

    def _parse_vision_response(
        self,
        resp_json: Dict[str, Any],
        scale_ratio: float,
        page_index: int,
        log_callback=None
    ) -> List[BubbleBlock]:
        bubbles: List[BubbleBlock] = []
        try:
            choices = resp_json.get("choices", [])
            if not choices:
                return []
            content = choices[0].get("message", {}).get("content", "").strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)

            data = json.loads(content)
            raw_bubbles = data.get("bubbles", [])
            for idx, item in enumerate(raw_bubbles):
                b_id = f"p{page_index}_{item.get('id', f'b{idx+1}')}"
                raw_bbox = item.get("bbox", [0, 0, 0, 0])
                if len(raw_bbox) == 4:
                    # Rescale coordinates to original image size
                    inv_scale = 1.0 / scale_ratio if scale_ratio > 0 else 1.0
                    x = int(round(raw_bbox[0] * inv_scale))
                    y = int(round(raw_bbox[1] * inv_scale))
                    w = int(round(raw_bbox[2] * inv_scale))
                    h = int(round(raw_bbox[3] * inv_scale))
                    bbox = (x, y, w, h)
                else:
                    bbox = (0, 0, 0, 0)

                text_ja = str(item.get("text_ja", item.get("text", ""))).strip()
                text_en = str(item.get("text_en", "")).strip()
                bubbles.append(BubbleBlock(id=b_id, bbox=bbox, text_ja=text_ja, text_en=text_en))
        except Exception as e:
            err = f"Failed to parse Vision response: {e}"
            logger.error(err)
            if log_callback:
                log_callback(err)

        return bubbles
