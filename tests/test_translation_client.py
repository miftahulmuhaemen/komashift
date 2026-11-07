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


def test_translate_handles_think_tags_and_preamble():
    translator = OpenAITranslator(api_key="test-key", base_url="https://opencode.ai/inference/openai/v1", model="deepseek-v4.1-flash-free")
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="こんにちは")]
        )
    ]

    raw_content = "<think>\nAnalyzing the context of the speech bubble...\n</think>\nHere is the translated dialogue:\n```json\n{\"translations\": [{\"id\": \"p1_b1\", \"text_en\": \"Hello!\"}]}\n```"
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": raw_content}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = translator.translate_chapter(pages)
        assert res["p1_b1"] == "Hello!"


def test_batch_chunking_and_progress_callback():
    # Configure translator with batch_size=2
    translator = OpenAITranslator(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout=45.0,
        batch_size=2
    )

    # 5 bubbles total -> should split into 3 batches (2, 2, 1)
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[
                BubbleBlock(id="b1", bbox=(0, 0, 10, 10), text_ja="B1"),
                BubbleBlock(id="b2", bbox=(0, 0, 10, 10), text_ja="B2"),
                BubbleBlock(id="b3", bbox=(0, 0, 10, 10), text_ja="B3"),
            ]
        ),
        PageTranslation(
            page_filename="02.png", page_width=1000, page_height=1400,
            bubbles=[
                BubbleBlock(id="b4", bbox=(0, 0, 10, 10), text_ja="B4"),
                BubbleBlock(id="b5", bbox=(0, 0, 10, 10), text_ja="B5"),
            ]
        )
    ]

    calls = []
    def fake_translate_single_batch(chunk, target_lang="en"):
        calls.append(chunk)
        res = {}
        if isinstance(chunk, dict):
            for bid in chunk:
                res[bid] = f"trans_{bid}"
        else:
            for p in chunk:
                for b in p["bubbles"]:
                    res[b["id"]] = f"trans_{b['id']}"
        return res

    progress_events = []
    def on_progress(batch_num, total_batches, translated_count):
        progress_events.append((batch_num, total_batches, translated_count))

    with patch.object(translator, "_translate_single_batch", side_effect=fake_translate_single_batch):
        res = translator.translate_chapter(pages, target_lang="en", on_batch_progress=on_progress)

    # 3 batches expected: [b1, b2], [b3, b4], [b5]
    assert len(calls) == 3
    assert len(res) == 5
    assert res["b1"] == "trans_b1"
    assert res["b5"] == "trans_b5"

    assert progress_events == [
        (1, 3, 2),
        (2, 3, 4),
        (3, 3, 5)
    ]


def test_batch_size_zero_sends_full_chapter_at_once():
    translator = OpenAITranslator(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        batch_size=0
    )

    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[
                BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="こんにちは"),
                BubbleBlock(id="p1_b2", bbox=(0, 0, 10, 10), text_ja="元気？"),
            ]
        ),
        PageTranslation(
            page_filename="02.png", page_width=1000, page_height=1400,
            bubbles=[
                BubbleBlock(id="p2_b1", bbox=(0, 0, 10, 10), text_ja="大丈夫"),
            ]
        )
    ]

    calls = []
    def fake_translate_single_batch(chunk, target_lang="en"):
        calls.append(chunk)
        return {bid: f"trans_{bid}" for bid in chunk}

    translator._translate_single_batch = fake_translate_single_batch
    results = translator.translate_chapter(pages, target_lang="en")

    # Should only execute 1 single request containing all bubbles
    assert len(calls) == 1
    assert len(calls[0]) == 3
    assert set(calls[0].keys()) == {"p1_b1", "p1_b2", "p2_b1"}
    assert len(results) == 3


def test_translate_handles_nested_chapter_response():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="deepseek-v4.1")
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="こんにちは")]
        )
    ]

    raw_content = "Here is the translated chapter:\n```json\n{\"chapter\": [{\"bubbles\": [{\"id\": \"p1_b1\", \"text_en\": \"Hello!\"}]}]}\n```\nAll done."
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": raw_content}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = translator.translate_chapter(pages)
        assert res["p1_b1"] == "Hello!"


def test_translate_handles_empty_response():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="deepseek-v4.1")
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="こんにちは")]
        )
    ]

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": ""}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(TranslationError, match="Model returned an empty response"):
            translator.translate_chapter(pages)


def test_translate_punctuation_bypass():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[
                BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="！"),
                BubbleBlock(id="p1_b2", bbox=(0, 0, 10, 10), text_ja="？？"),
                BubbleBlock(id="p1_b3", bbox=(0, 0, 10, 10), text_ja="．．．．．．"),
                BubbleBlock(id="p1_b4", bbox=(0, 0, 10, 10), text_ja="……！"),
                BubbleBlock(id="p1_b5", bbox=(0, 0, 10, 10), text_ja="こんにちは"),
            ]
        )
    ]

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": json.dumps({"p1_b5": "Hello"})}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        res = translator.translate_chapter(pages)

        # 4 pure punctuation bubbles resolved locally without hitting LLM
        assert res["p1_b1"] == "!"
        assert res["p1_b2"] == "??"
        assert res["p1_b3"] == "..."
        assert res["p1_b4"] == "...!"
        assert res["p1_b5"] == "Hello"

        # Verify only p1_b5 was sent in the HTTP payload
        assert mock_url.called
        req_sent = mock_url.call_args[0][0]
        body = json.loads(req_sent.data.decode("utf-8"))
        user_text = body["messages"][1]["content"]
        assert "p1_b5" in user_text
        assert "p1_b1" not in user_text


def test_translate_chapter_deduplication():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[
                BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="げー"),
                BubbleBlock(id="p1_b2", bbox=(0, 0, 10, 10), text_ja="こんにちは"),
            ]
        ),
        PageTranslation(
            page_filename="02.png", page_width=1000, page_height=1400,
            bubbles=[
                BubbleBlock(id="p2_b1", bbox=(0, 0, 10, 10), text_ja="げー"),
                BubbleBlock(id="p2_b2", bbox=(0, 0, 10, 10), text_ja="げー"),
            ]
        )
    ]

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": json.dumps({"p1_b1": "Ugh", "p1_b2": "Hello"})}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        res = translator.translate_chapter(pages)

        # All 3 occurrences of 'げー' receive the translated string
        assert res["p1_b1"] == "Ugh"
        assert res["p2_b1"] == "Ugh"
        assert res["p2_b2"] == "Ugh"
        assert res["p1_b2"] == "Hello"

        # Only 2 unique items sent in HTTP request
        req_sent = mock_url.call_args[0][0]
        body = json.loads(req_sent.data.decode("utf-8"))
        user_text = body["messages"][1]["content"]
        assert "p1_b1" in user_text
        assert "p1_b2" in user_text
        assert "p2_b1" not in user_text
        assert "p2_b2" not in user_text



