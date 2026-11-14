import json
import pytest
from pathlib import Path
from PIL import Image
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


def test_translate_page_multimodal_success(tmp_path: Path):
    from PIL import Image
    img_path = tmp_path / "page_01.png"
    Image.new("RGB", (1000, 2000), color=(255, 255, 255)).save(img_path)

    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gemini-2.5-flash")

    llm_payload = {
        "bubbles": [
            {
                "box_2d": [100, 200, 300, 600],
                "text_ja": "こんにちは",
                "text_en": "Hello!"
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": json.dumps(llm_payload)}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        page_trans = translator.translate_page_multimodal(
            img_path, page_index=1, target_lang="en", scale_pct=50, quality=75
        )

        assert mock_url.called
        req_sent = mock_url.call_args[0][0]
        body = json.loads(req_sent.data.decode("utf-8"))
        user_contents = body["messages"][1]["content"]
        image_content = next(c for c in user_contents if c["type"] == "image_url")
        assert image_content["image_url"]["url"].startswith("data:image/webp;base64,")

        assert page_trans.page_filename == "page_01.png"
        assert page_trans.page_width == 1000
        assert page_trans.page_height == 2000
        assert len(page_trans.bubbles) == 1

        b = page_trans.bubbles[0]
        assert b.id == "p1_b1"
        assert b.text_ja == "こんにちは"
        assert b.text_en == "Hello!"
        assert b.bbox == (200, 200, 400, 400)
        assert b.centroid == (400, 400)
        assert b.expanded_bbox == (200, 200, 400, 400)


def test_translate_page_visual_hybrid_success(tmp_path: Path):
    from PIL import Image
    img_path = tmp_path / "page_02.png"
    Image.new("RGB", (1000, 2000), color=(255, 255, 255)).save(img_path)

    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gemini-2.5-flash")

    page = PageTranslation(
        page_filename="page_02.png",
        page_width=1000,
        page_height=2000,
        bubbles=[
            BubbleBlock("p2_b1", (100, 100, 200, 200), "おはよう", expanded_bbox=(90, 90, 220, 220))
        ]
    )

    llm_payload = {"p2_b1": "Good morning!"}
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": json.dumps(llm_payload)}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        res = translator.translate_page_visual_hybrid(
            img_path, page, target_lang="en", scale_pct=50, quality=75
        )

        assert mock_url.called
        assert res == {"p2_b1": "Good morning!"}

        req_sent = mock_url.call_args[0][0]
        body = json.loads(req_sent.data.decode("utf-8"))
        user_text = body["messages"][1]["content"][0]["text"]
        assert "p2_b1" in user_text
        assert "location=[ymin:45, xmin:90, ymax:155, xmax:310]" in user_text


def test_translate_single_text_with_context():
    translator = OpenAITranslator(api_key="test-key", base_url="https://api.openai.com/v1", model="gemini-2.5-flash")

    llm_payload = {"target_translation": "No way, definitely not!"}
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": json.dumps(llm_payload)}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        res = translator.translate_single_text_with_context(
            text_ja="當然不行！",
            target_lang="en",
            prev_context="- Hey there\n- You look nice",
            curr_context="- Can I take a picture?",
            next_context="- Let's go together"
        )

        assert res == "No way, definitely not!"
        assert mock_url.called
        req_sent = mock_url.call_args[0][0]
        body = json.loads(req_sent.data.decode("utf-8"))
        user_content = body["messages"][1]["content"]
        assert "Context from Previous Page" in user_content
        assert "Context from Current Page" in user_content
        assert "Context from Next Page" in user_content
        assert "當然不行！" in user_content


def test_anthropic_protocol_batch_translation():
    translator = OpenAITranslator(
        api_key="sk-ant-test12345",
        base_url="https://api.anthropic.com/v1",
        model="claude-3-5-sonnet-20241022",
        protocol="anthropic"
    )

    pages = [
        PageTranslation(
            page_filename="01.png", page_width=1000, page_height=1400,
            bubbles=[BubbleBlock(id="p1_b1", bbox=(0, 0, 10, 10), text_ja="こんにちは")]
        )
    ]

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "content": [
            {
                "type": "text",
                "text": json.dumps({"p1_b1": "Hello!"})
            }
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        res = translator.translate_chapter(pages)
        assert res["p1_b1"] == "Hello!"
        assert mock_url.called
        req = mock_url.call_args[0][0]
        assert req.headers["X-api-key"] == "sk-ant-test12345"
        assert req.headers["Anthropic-version"] == "2023-06-01"
        assert req.full_url == "https://api.anthropic.com/v1/messages"

        sent_body = json.loads(req.data.decode("utf-8"))
        assert sent_body["model"] == "claude-3-5-sonnet-20241022"
        assert sent_body["max_tokens"] == 4096
        assert "system" in sent_body
        assert isinstance(sent_body["messages"], list)


def test_anthropic_protocol_visual_hybrid(tmp_path: Path):
    from PIL import Image
    img_path = tmp_path / "page_01.png"
    Image.new("RGB", (800, 1200), color=(255, 255, 255)).save(img_path)

    translator = OpenAITranslator(
        api_key="sk-ant-test12345",
        base_url="https://api.anthropic.com/v1",
        model="claude-3-5-sonnet-20241022",
        protocol="anthropic"
    )

    page = PageTranslation(
        page_filename="page_01.png",
        page_width=800,
        page_height=1200,
        bubbles=[
            BubbleBlock("p1_b1", (50, 50, 100, 100), "助けて", expanded_bbox=(40, 40, 110, 110))
        ]
    )

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "content": [
            {
                "type": "text",
                "text": json.dumps({"p1_b1": "Help me!"})
            }
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        res = translator.translate_page_visual_hybrid(img_path, page, target_lang="en")
        assert res == {"p1_b1": "Help me!"}
        assert mock_url.called
        req = mock_url.call_args[0][0]
        sent_body = json.loads(req.data.decode("utf-8"))
        user_blocks = sent_body["messages"][0]["content"]
        img_block = next(b for b in user_blocks if b["type"] == "image")
        assert img_block["source"]["type"] == "base64"
        assert img_block["source"]["media_type"] == "image/webp"
        assert len(img_block["source"]["data"]) > 0


def test_perceive_page_visual_context(tmp_path: Path):
    translator = OpenAITranslator(
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        protocol="openai"
    )
    img_path = tmp_path / "page_01.png"
    Image.new("RGB", (800, 1200), color="white").save(img_path)

    page = PageTranslation(
        page_filename="page_01.png",
        page_width=800,
        page_height=1200,
        bubbles=[
            BubbleBlock("p1_b1", (50, 50, 100, 100), "おい、どこ行くんだよ？")
        ]
    )

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "p1_b1": {
                            "text_ja": "おい、どこ行くんだよ？",
                            "speaker": "Male classmate",
                            "expression": "Annoyed, shouting",
                            "speech_type": "Spoken dialogue"
                        }
                    })
                }
            }
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = translator.perceive_page_visual_context(img_path, page)
        assert "p1_b1" in res
        info = res["p1_b1"]
        assert info["text_ja"] == "おい、どこ行くんだよ？"
        assert info["speaker"] == "Male classmate"
        assert info["expression"] == "Annoyed, shouting"
        assert info["speech_type"] == "Spoken dialogue"


def test_translate_chapter_with_visual_cues(tmp_path: Path):
    translator = OpenAITranslator(
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        protocol="openai"
    )
    b1 = BubbleBlock("p1_b1", (10, 10, 50, 50), "おい", speaker="Male student", expression="Angry shouting")
    page = PageTranslation("01.png", 800, 1200, [b1])

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"content": json.dumps({"p1_b1": "Hey!"})}}]
    }).encode("utf-8")
    mock_resp.__enter__.return_value.status = 200

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        trans = translator.translate_chapter([page], target_lang="en")
        assert trans == {"p1_b1": "Hey!"}
        # Verify sent payload contained visual context
        req = mock_url.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        user_msg = body["messages"][1]["content"]
        assert "Angry shouting" in user_msg
        assert "Male student" in user_msg






