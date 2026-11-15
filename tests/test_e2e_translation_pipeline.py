import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pytest

from src.infra.json_workspace import JsonTempWorkspace
from src.services.translation_client import OpenAITranslator
from src.services.scanner import natural_sort_key

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_test_env() -> Dict[str, str]:
    """Loads configuration from .env file or system environment."""
    config: Dict[str, str] = {}
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                config[key.strip()] = val.strip()

    # System environment variables take precedence
    for k in (
        "KOMASHIFT_TEST_API_KEY",
        "KOMASHIFT_TEST_BASE_URL",
        "KOMASHIFT_TEST_MODEL",
        "KOMASHIFT_TEST_PROTOCOL",
        "KOMASHIFT_TEST_LANG",
        "KOMASHIFT_TEST_MANGA_DIR",
    ):
        if k in os.environ:
            config[k] = os.environ[k]

    return config


def _check_developer_setlist(config: Dict[str, str]) -> Tuple[bool, List[str]]:
    """Validates pre-flight developer setlist requirements."""
    checklist = []
    ready = True

    # 1. API Key
    api_key = config.get("KOMASHIFT_TEST_API_KEY", "").strip()
    if api_key and api_key != "your_api_key_here":
        checklist.append(f"[x] API Key configured ({api_key[:6]}...{api_key[-4:]})")
    else:
        checklist.append("[ ] API Key missing (set KOMASHIFT_TEST_API_KEY in .env)")
        ready = False

    # 2. Endpoint / Base URL
    base_url = config.get("KOMASHIFT_TEST_BASE_URL", "").strip()
    if base_url:
        checklist.append(f"[x] Base URL configured ({base_url})")
    else:
        checklist.append("[ ] Base URL missing (set KOMASHIFT_TEST_BASE_URL in .env)")
        ready = False

    # 3. Model
    model = config.get("KOMASHIFT_TEST_MODEL", "").strip()
    if model:
        checklist.append(f"[x] Model configured ({model})")
    else:
        checklist.append("[ ] Model missing (set KOMASHIFT_TEST_MODEL in .env)")
        ready = False

    # 4. Manga Dataset Directory
    manga_dir_str = config.get("KOMASHIFT_TEST_MANGA_DIR", "").strip()
    manga_dir = Path(manga_dir_str) if manga_dir_str else None
    if manga_dir and not manga_dir.is_absolute():
        manga_dir = REPO_ROOT / manga_dir

    if manga_dir and manga_dir.exists() and manga_dir.is_dir():
        imgs = (
            list(manga_dir.glob("*.webp"))
            + list(manga_dir.glob("*.png"))
            + list(manga_dir.glob("*.jpg"))
        )
        if imgs:
            checklist.append(f"[x] Manga dataset found ({manga_dir.name}, {len(imgs)} pages)")
        else:
            checklist.append(f"[ ] Manga directory contains no image files: {manga_dir}")
            ready = False
    else:
        checklist.append(f"[ ] Manga directory missing ({manga_dir_str})")
        ready = False

    return ready, checklist


def test_e2e_developer_setlist_and_pipeline_execution():
    """
    Executes full multi-batch translation on the 76-page chapter dataset.
    Verifies smart cache reuse, calibrated batching, and 100% translation coverage.
    """
    env = _load_test_env()
    ready, checklist = _check_developer_setlist(env)
    if not ready:
        pytest.skip(
            "Developer pre-flight setlist incomplete. Checklist:\n"
            + "\n".join(checklist)
            + "\nConfigure credentials in .env (copy from .env.example)."
        )

    manga_dir_str = env["KOMASHIFT_TEST_MANGA_DIR"]
    manga_dir = Path(manga_dir_str) if Path(manga_dir_str).is_absolute() else REPO_ROOT / manga_dir_str
    target_lang = env.get("KOMASHIFT_TEST_LANG", "en")

    ws = JsonTempWorkspace(manga_dir)
    # Smart Cache Reuse: Read cached OCR results
    ocr_results = ws.load_ocr_results()
    assert ocr_results, f"OCR cache missing in {manga_dir}/temp/ocr_results.json"

    sorted_pages = [ocr_results[k] for k in sorted(ocr_results.keys(), key=natural_sort_key)]
    total_bubbles = sum(len(p.bubbles) for p in sorted_pages)
    assert total_bubbles > 0, "No speech bubbles detected in chapter OCR results"

    translator = OpenAITranslator(
        api_key=env["KOMASHIFT_TEST_API_KEY"],
        base_url=env["KOMASHIFT_TEST_BASE_URL"],
        model=env["KOMASHIFT_TEST_MODEL"],
        protocol=env.get("KOMASHIFT_TEST_PROTOCOL", "openai"),
        batch_size=0,
    )

    batch_progress_events: List[Tuple[int, int, int]] = []

    def _on_batch_progress(batch_num: int, total_batches: int, count: int, part: Any = None):
        batch_progress_events.append((batch_num, total_batches, count))
        logger.info("E2E Batch Progress: %d/%d (%d bubbles translated)", batch_num, total_batches, count)

    translations = translator.translate_chapter(
        sorted_pages,
        target_lang=target_lang,
        on_batch_progress=_on_batch_progress,
    )

    print(f"\n[E2E Diagnostic] Total translation keys returned: {len(translations)}")
    print(f"[E2E Diagnostic] Total batch events: {len(batch_progress_events)}: {batch_progress_events}")

    # 1. Multi-batch assertion: chapter must split into multiple batches (calibrated <= 180 bubbles)
    assert len(batch_progress_events) >= 3, (
        f"Expected at least 3 adaptive batches for ~670 bubbles, got {len(batch_progress_events)}"
    )

    # 2. 100% bubble coverage assertion
    missing_bubbles = []
    for p in sorted_pages:
        for b in p.bubbles:
            text = translator._clamp_repeated_symbols(b.text_ja.strip())
            if text and not translator._is_pure_punctuation_or_symbol(text):
                if b.id not in translations or not translations[b.id].strip():
                    missing_bubbles.append((p.page_filename, b.id, text))

    assert not missing_bubbles, (
        f"Translation coverage incomplete! Missing {len(missing_bubbles)} bubbles:\n"
        f"{missing_bubbles[:5]}..."
    )

    # 3. Save translations to workspace atomically
    ws.save_translations(translations, target_lang=target_lang)
    saved_translations = ws.load_translations(target_lang=target_lang)
    assert len(saved_translations) == len(translations)


def test_e2e_llm_judge_narrative_coherence():
    """
    Acts as an impartial narrative judge evaluating the chronological English translation.
    Scores narrative coherence and dialogue naturalness (requires score >= 6.0 and makes_sense is True).
    """
    env = _load_test_env()
    ready, checklist = _check_developer_setlist(env)
    if not ready:
        pytest.skip("Developer pre-flight setlist incomplete:\n" + "\n".join(checklist))

    manga_dir_str = env["KOMASHIFT_TEST_MANGA_DIR"]
    manga_dir = Path(manga_dir_str) if Path(manga_dir_str).is_absolute() else REPO_ROOT / manga_dir_str
    target_lang = env.get("KOMASHIFT_TEST_LANG", "en")

    ws = JsonTempWorkspace(manga_dir)
    ocr_results = ws.load_ocr_results()
    translations = ws.load_translations(target_lang=target_lang)

    assert ocr_results, "Missing OCR results for narrative evaluation"
    assert translations, "Missing translation results for narrative evaluation"

    translator = OpenAITranslator(
        api_key=env["KOMASHIFT_TEST_API_KEY"],
        base_url=env["KOMASHIFT_TEST_BASE_URL"],
        model=env["KOMASHIFT_TEST_MODEL"],
        protocol=env.get("KOMASHIFT_TEST_PROTOCOL", "openai"),
    )

    # Compile sequential reading script
    sorted_pages = [ocr_results[k] for k in sorted(ocr_results.keys(), key=natural_sort_key)]
    dialogue_lines: List[str] = []

    for p in sorted_pages:
        for b in p.bubbles:
            trans = translations.get(b.id, "").strip()
            if not trans or translator._is_pure_punctuation_or_symbol(trans):
                continue
            line = f'[{p.page_filename}] "{trans}"'
            dialogue_lines.append(line)

    assert len(dialogue_lines) >= 100, f"Dialogue script too short ({len(dialogue_lines)} lines)"
    script_text = "\n".join(dialogue_lines)

    judge_prompt = (
        'You are an expert manga localization editor evaluating an English translation of a manga chapter.\n'
        'Context: This is translated dialogue from Japanese OCR following multiple characters with frequent scene cuts, monologues, and dialogue exchanges.\n\n'
        'Evaluation Criteria:\n'
        '1. Translation Readability: Is the English translation readable, grammatically coherent, and understandable in context?\n'
        '2. Manga Localization Sense: Does the dialogue make sense as localized manga speech, allowing for genre tropes, passion moans, and rapid scene cuts?\n'
        '3. Integrity: Is the chapter free of untranslated Japanese or broken text?\n\n'
        'Scoring Guide:\n'
        '- 1.0 to 3.9: Broken, corrupt, or incomprehensible gibberish\n'
        '- 4.0 to 6.9: Understandable and readable manga translation with minor OCR/genre quirks\n'
        '- 7.0 to 10.0: Fluent, publication-grade localization\n\n'
        'Manga Dialogue Script:\n'
        f'{script_text}\n\n'
        'Respond strictly with a JSON object in this exact schema (no markdown fences, no other commentary):\n'
        '{\n'
        '  "coherence_score": <float between 1.0 and 10.0>,\n'
        '  "readability_score": <float between 1.0 and 10.0>,\n'
        '  "overall_score": <float between 1.0 and 10.0>,\n'
        '  "translation_acceptable": <true or false>,\n'
        '  "rationale": "<concise paragraph explaining whether the translation makes sense and communicates the chapter dialogue>"\n'
        '}'
    )

    body = {
        "model": translator.model,
        "messages": [
            {"role": "system", "content": "You are an objective editorial judge for comic translation quality."},
            {"role": "user", "content": judge_prompt},
        ],
        "temperature": 0.2,
    }
    if translator.protocol == "openai":
        body["response_format"] = {"type": "json_object"}

    raw_resp = translator._execute_post_request(body)
    if "content" in raw_resp and isinstance(raw_resp["content"], list):
        content = "\n".join(b.get("text", "") for b in raw_resp["content"] if isinstance(b, dict) and b.get("type") == "text")
    else:
        choices = raw_resp.get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""

    evaluation = translator._extract_json_from_content(content)

    print("\n--- LLM Narrative Quality Evaluation ---")
    print(f"Overall Score: {evaluation.get('overall_score')}/10.0")
    print(f"Coherence Score: {evaluation.get('coherence_score')}/10.0")
    print(f"Readability Score: {evaluation.get('readability_score')}/10.0")
    print(f"Translation Acceptable: {evaluation.get('translation_acceptable')}")
    print(f"Rationale: {evaluation.get('rationale')}")
    print("----------------------------------------\n")

    overall = float(evaluation.get("overall_score", 0.0))
    acceptable = evaluation.get("translation_acceptable")
    if isinstance(acceptable, str):
        acceptable = acceptable.lower() in ("true", "yes")

    assert acceptable is True, f"Translation was judged unacceptable:\n{evaluation.get('rationale')}"
    assert overall >= 6.5, (
        f"Translation narrative coherence score {overall} is below threshold 6.5!\n"
        f"Rationale: {evaluation.get('rationale')}"
    )
