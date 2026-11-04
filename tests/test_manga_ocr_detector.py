import json
from unittest.mock import patch, MagicMock
from pathlib import Path
from PIL import Image
from src.services.manga_ocr_detector import MangaOcrDetector

def test_vision_ocr_detection(tmp_path: Path):
    img_path = tmp_path / "01.png"
    img = Image.new("RGB", (500, 800), color="white")
    img.save(img_path)

    detector = MangaOcrDetector(
        api_key="test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-3.5-flash-lite"
    )

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{
            "message": {
                "content": json.dumps({
                    "bubbles": [
                        {"id": "b1", "bbox": [50, 100, 150, 80], "text_ja": "助けて", "text_en": "Help"}
                    ]
                })
            }
        }]
    }).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        page = detector.detect_page(img_path, page_index=1)
        assert len(page.bubbles) == 1
        assert page.bubbles[0].id == "p1_b1"
        assert page.bubbles[0].text_ja == "助けて"
        assert page.bubbles[0].text_en == "Help"
        assert page.bubbles[0].bbox == (50, 100, 150, 80)
