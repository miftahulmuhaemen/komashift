# Implementation Plan: Manga OCR Model Download Manager & Queue Interlock

**Status:** Draft / Pending User Approval  
**Created:** 2026-11-11  
**Goal:** Enhance the Manga OCR model configuration in Settings so that custom Hugging Face models are checked against local cache upon input, provide a "Download" button with a circular spinner during cache checking, support pause/cancel during downloading, block the translation queue until download completes, and automatically fall back to the default working model if cancelled.

---

## 1. Architecture & Scope

### Current State vs. Target State

| Dimension | Current State | Target State |
|---|---|---|
| **Cache Verification** | Lazy check inside background worker at translation runtime | Immediate asynchronous check when model name is typed or selected |
| **Check Indicator** | None | Circular progress spinner next to the input while checking cache |
| **Download Trigger** | Automatic blocking download during first page OCR in translation worker | Explicit "Download" button enabled only when an uncached model is specified |
| **Download Control** | Synchronous, non-cancellable, no UI progress | Full progress feedback with Pause, Resume, and Cancel buttons |
| **Queue Handling** | Queue starts immediately and blocks inside worker | Queue is interlocked with status "Waiting for model download..." |
| **Cancellation Fallback** | N/A (worker crashes or times out) | Aborts download, reverts input and settings to default working model (`mayocream/manga-ocr-onnx`), and unblocks queue |

---

## 2. Technical Design

### A. Ports, Services & Infra Layering (Hexagonal Architecture)
1. **`src/services/ai_assets_manager.py` (Headless Service)**:
   - `is_ocr_model_cached(model_id_or_path: str) -> bool`: Checks local directory or Hugging Face cache (`try_to_load_from_cache`).
   - `download_ocr_model(repo_id: str, progress_cb, cancel_check, pause_check) -> Path`: Headless downloader supporting progress reporting, pause tokens, and clean cancellation cleanup.
2. **`src/infra/model_download_worker.py` (Worker Adapter in Infra)**:
   - `ModelCacheCheckWorker(QThread)`: Checks cache off the GUI thread; emits `check_completed(str, bool)`.
   - `ModelDownloadWorker(QThread)`: Manages model file streaming; emits `progress(int, int, int)`, `status_changed(str)`, `finished(bool, str)`. Supports `pause()`, `resume()`, and `cancel()`.
3. **`src/ui/circular_progress.py` & `src/ui/settings_dialog.py` (Presentation Tier)**:
   - `CircularSpinner(QWidget)`: Smooth QPainter-based circular spinner indicator displayed during cache check.
   - Settings Dialog Manga OCR Row:
     - Model input line edit / preset selector.
     - "Browse..." button for local folders.
     - Circular spinner (active while checking).
     - "Download" button (visible when uncached).
     - Download progress bar with "Pause" / "Cancel" buttons.
4. **`src/services/translation_queue.py` (Queue Interlock)**:
   - `TranslationQueueManager`:
     - Tracks `_is_model_downloading: bool`.
     - In `_process_next()`: If model download is in progress, holds jobs with status `"Waiting for model download..."`.
     - Connects to download completion / cancellation signals to resume queue automatically.

---

## 3. Step-by-Step Task Breakdown

- [x] **Task 1: Implement Headless Cache Check & Downloader in `AiAssetsManager`**
  - Add `is_ocr_model_cached(model_id_or_path)` to check local directories and Hugging Face cache.
  - Add `download_ocr_model(repo_id, progress_cb, cancel_check, pause_check)` with atomic temporary download and cleanup on cancel.
  - Unit tests in `tests/test_ai_assets_manager.py`.

- [x] **Task 2: Implement QThread Workers in `src/infra/model_download_worker.py`**
  - Create `ModelCacheCheckWorker` and `ModelDownloadWorker` conforming to the infra tier rules.
  - Implement pause, resume, cancel, and progress signals.
  - Unit tests in `tests/test_model_download_worker.py`.

- [x] **Task 3: Implement Circular Spinner & Download UI in `SettingsDialog`**
  - Add `CircularSpinner` widget in `src/ui/`.
  - Connect text change events to debounced cache check with spinner.
  - Show "Download" button when model is uncached.
  - Show download progress bar with "Pause" / "Cancel" controls.
  - On "Cancel", automatically revert model field to default working model (`mayocream/manga-ocr-onnx`).

- [x] **Task 4: Implement Queue Interlock in `TranslationQueueManager`**
  - Add `set_model_download_in_progress(bool)` to `TranslationQueueManager`.
  - Hold job execution while downloading with `"Waiting for model download..."` status.
  - Release hold when download finishes or cancels back to default.
  - Unit tests in `tests/test_translation_queue.py`.

- [x] **Task 5: End-to-End Verification & Hygiene**
  - Run full test suite: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`.
  - Validate architecture compliance: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_architecture.py`.
  - Verify static type and compilation checks.

---

## 4. Verification Protocol

1. **Unit & Integration Tests**:
   - Cache check logic for local folders, cached HF models, and uncached HF models.
   - Pause, resume, and cancellation mechanics.
   - Fallback to default model on cancellation.
   - Queue holding and resuming behavior.
2. **Commands**:
   - `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`
   - `.venv/bin/python -m py_compile src/**/*.py`
