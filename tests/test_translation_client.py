import json
import pytest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from src.models.translation_item import BubbleBlock, PageTranslation
from src.services.translation_client import OpenAITranslator, TranslationError

def test_batch_translate_chapter():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="助けて！")]
        ),
        PageTranslation(
            page_filename="02.png", page_width=1000, page_height=1400,
            bubbles=[BubbleBlock(id="p2_b1", bbox=(0, 0, 10, 10), text_ja="大丈夫？")]
        )
    ]

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{
            "message": {
                "content": json.dumps({
                    "translations": [
                        {"id": "p1_b1", "text_en": "Help me!"},
                        {"id": "p2_b1", "text_en": "Are you okay?"}
                    ]
                })
            }
        }]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = translator.translate_chapter(pages)
        assert res["p1_b1"] == "Help me!"
        assert res["p2_b1"] == "Are you okay?"

def test_translate_empty_bubbles():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    pages = [PageTranslation("01.png", 1000, 1400, [])]
    res = translator.translate_chapter(pages)
    assert res == {}

def test_translate_handles_markdown_codeblock():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="やあ")]
        )
    ]

    raw_content = "```json\n{\"translations\": [{\"id\": \"p1_b1\", \"text_en\": \"Hi\"}]}\n```"
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": raw_content}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = translator.translate_chapter(pages)
        assert res["p1_b1"] == "Hi"

def test_translate_api_error():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="テスト")]
        )
    ]

    with patch("urllib.request.urlopen", side_effect=HTTPError(url="https://api.openai.com/v1", code=401, msg="Unauthorized", hdrs={}, fp=None)):
        with pytest.raises(TranslationError):
            translator.translate_chapter(pages)
