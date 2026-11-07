---
name: manga_translation_pipeline
description: Verification and execution workflow for manga speech bubble detection, local OCR, batch translation, typography fitting, and interactive overlay rendering.
---

# Workflow: Manga OCR & Translation Pipeline

This workflow defines the complete procedural steps for implementing, testing, and verifying features across the manga speech bubble detection and translation pipeline.

---

## 1. Pipeline Architecture Overview

The translation pipeline operates in 5 strictly decoupled stages:
1. **Bubble Detection (`OnnxBubbleDetector`)**: Offline ONNX inference identifying text bounding boxes.
2. **Text OCR (`MangaOcrDetector`)**: Offline neural character recognition of Japanese text crops.
3. **Dialogue Translation (`TranslationClient`)**: Structured dialogue batching to Gemini or OpenAI-compatible endpoints.
4. **Typography & Inpainting Engine**: Morphological contour floodfill, moment centroid calculation, dynamic text scaling, and `pyphen` hyphenation.
5. **Interactive Overlay (`TranslationOverlay`)**: PyQt6 paint canvas rendering over `PreviewPane` with hover inspection tooltips.

---

## 2. Step-by-Step Implementation & Verification

### Step 1: Bubble Detection Verification
- Verify that `OnnxBubbleDetector` correctly locates speech bubbles and returns pixel coordinates `[x, y, w, h]`.
- Check fallback: If ONNX weights are missing, verify that `detector.is_available()` returns `False` without raising an exception.

### Step 2: Japanese Neural OCR Verification
- Ensure bubble image crops are passed cleanly to `MangaOcrDetector`.
- Verify extracted strings are trimmed and associated with deterministic bubble IDs (`p<page>_b<index>`).

### Step 3: Batch Translation Verification
- Verify that `TranslationClient` formats requests as a dictionary mapping bubble IDs to original Japanese text:
  ```json
  {"p1_b1": "こんにちは", "p1_b2": "さようなら"}
  ```
- Ensure the API response preserves all keys and returns corresponding translated strings.
- Verify error handling: network timeouts or missing API keys must update the job status cleanly without crashing the UI.

### Step 4: Typography Fit & Centroid Invariant
- Morphological boundaries must use elliptical structuring elements to bridge gaps without leaking into character art.
- Moment centroids (`M10 / M00`, `M01 / M00`) must be used for text alignment to ensure text is naturally centered within curved balloons.
- Validate that long words hyphenate cleanly with `pyphen` rather than overflowing balloon borders.

### Step 5: Atomic Workspace Storage Verification
- Ensure `TranslationWorkspace` persists data inside `<folder_path>/temp/`:
  - `ocr_results.json`
  - `translation_results.json`
  - `translation.log`
- Verify that existing cache files are read on subsequent folder loads, eliminating redundant API calls.

### Step 6: Interactive Overlay Testing
- Run test suite:
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_translation_*.py tests/test_manga_ocr_detector.py tests/test_onnx_bubble_detector.py
  ```
- Confirm all overlay toggle (`T`), hover inspection, and queue operations pass cleanly.
