---
trigger: always_on
description: Prohibition of synthetic/fabricated OCR and translation data, dual-mode OCR contracts, atomic workspace storage, offline-first privacy standards, and ONNX model binary protection.
---

# Data Integrity, OCR & Translation Verification Standards

Strict rules governing data authenticity, OCR bounding box accuracy, translation workspace contracts, offline-first privacy standards, and model binary protection for the Windows Folder Image Previewer.

---

## 1. Prohibition of Fabricated, Mock & Synthetic Data

1. **Absolute Prohibition of Plausible Fakes**:
   - The agent is STRICTLY PROHIBITED from synthesizing fake OCR results, artificial Japanese transcriptions, imaginary dialogue translations, or hallucinated bounding box coordinates.
   - Deceptive filler content to make translation overlays, preview panels, or queue dialogs look populated is prohibited. Plausible fake data disguises detection failures or OCR regressions.
2. **Explicit Empty & Unmistakable States**:
   - When an image contains no speech bubbles or text, the page data must record strictly `bubbles: []`.
   - The UI must handle zero-bubble pages gracefully with clean empty states ("No text detected") rather than throwing exceptions or fabricating dummy rectangles.
3. **Dual-Mode Verification Grounding**:
   - Every recorded bubble and translation must originate from an authentic pipeline execution:
     1. **Offline Bubble Detection**: `OnnxBubbleDetector` executing local inference on image pixel arrays.
     2. **Offline Japanese OCR**: `MangaOcrDetector` running neural OCR on extracted bubble crops.
     3. **Verified Translation Engine**: `TranslationClient` receiving structured responses from the user's configured endpoint (Gemini or OpenAI-compatible).

---

## 2. OCR & Translation Workspace Contracts

1. **Canonical Bubble Schema & ID Invariant**:
   - Bounding boxes must strictly follow integer pixel coordinates `[x, y, w, h]` within original image dimensions.
   - Every detected bubble within a page must receive a deterministic, unique identifier: `p<page_number>_b<bubble_index>` (e.g. `p1_b1`, `p1_b2`).
   - Translation batches must preserve bubble IDs exactly in JSON keys to ensure mapped overlay rendering.
2. **Atomic Storage & Integrity Guarantee**:
   - `TranslationWorkspace` MUST write `ocr_results.json` and `translation_results.json` atomically:
     Write to a temporary file (`.tmp`) first, followed by an atomic rename/replace.
   - Partial or interrupted writes must never corrupt existing cache files.
3. **Workspace Isolation Standard**:
   - OCR results, translation results, and execution logs must reside strictly inside the targeted folder's `temp/` directory:
     - `<folder_path>/temp/ocr_results.json`
     - `<folder_path>/temp/translation_results.json`
     - `<folder_path>/temp/translation.log`
   - Dumping translation or OCR cache files in the application root directory or parent folders is strictly prohibited.

---

## 3. Offline-First Privacy & API Key Protection

1. **Offline-First Privacy Standard**:
   - Speech bubble segmentation and Japanese text recognition are 100% offline by design. Raw comic images must NEVER be transmitted to external servers or cloud services unless the user explicitly enables multimodal cloud vision in settings.
   - For standard translations, only extracted text dialogue strings are dispatched to translation APIs.
2. **API Key Protection**:
   - Translation API keys must be loaded securely from `QSettings` (`settings.value("translation/api_key")`).
   - API keys must NEVER be logged to `translation.log`, printed to stdout, or committed to repository files.

---

## 4. Large Model Binary & Weight Protection

1. **Absolute Prohibition of Model Commits**:
   - Machine learning model weights (such as `assets/models/comic-text-detector.onnx`, 94.6 MB, or any `*.onnx`, `*.pt`, `*.bin`, `*.weights`) must NEVER be committed to Git.
   - Model files must be excluded via `.gitignore`.
2. **Graceful Fallback on Missing Models**:
   - If `comic-text-detector.onnx` is missing from `assets/models/`, `OnnxBubbleDetector.is_available()` must return `False` cleanly without throwing unhandled exceptions.
   - The UI must notify the user with actionable guidance rather than crashing.

---

## 5. Mandatory Translation Feature Proof Standards

Whenever changes are made to the core translation logic, prompts, models, OCR algorithms, bubble detection, or typography rendering (changes that alter translated text, bounding coordinates, or visual rendering):

1. **Mandatory Visual Proof**:
   - The agent MUST render and display the full-page image result preview for both translation approaches directly in the report:
     - **Approach 1: Token-Efficient Hybrid (Local ONNX + Manga OCR + Text LLM)**
     - **Approach 2: Highest Quality Visual Hybrid (Local ONNX Segmentation + Vision LLM)**
   - Both full-page preview images must be generated using the application's actual rendering engine and the configured translation model.

2. **Mandatory Token Expenditure Report**:
   - The agent MUST report the exact token spend for every approach:
     - Prompt Tokens
     - Completion Tokens
     - Total Tokens

3. **Scope Clarification**:
   - Do NOT serve this proof for unrelated UI, queue management, or file system changes where translation algorithms and prompts remain untouched.
   - Do NOT provide granular side-by-side bubble crops or text diff breakdowns unless explicitly requested. The required proof is strictly the full-page rendered image previews of both approaches and their corresponding token consumption metrics.
