---
trigger: always_on
description: Python virtual environment standards, PyQt6 offscreen test runtime, zero dead code policy, documentation synchronization, async threading invariants, and Recycle Bin safety.
---

# Codebase Hygiene, Tooling & Runtime Standards

Strict rules governing execution runtimes, repository cleanliness, documentation synchronization, PyQt6 threading safety, and file system invariants for the Windows Folder Image Previewer.

---

## 1. Runtime & Environment Management (Python & PyQt6)

1. **Mandatory Virtual Environment**:
   - Primary Python runtime: Local virtual environment at `.venv` (`.venv/bin/python`, `.venv/bin/pip`, `.venv/bin/pytest`).
   - Never invoke global system Python (`python3` or `/usr/bin/python3`) for test execution or dependency installation.
2. **Canonical Execution Commands**:
   - **Launch Desktop Application**: `.venv/bin/python src/main.py`
   - **Run Test Suite**: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`
   - **Syntax & Compilation Validation**: `.venv/bin/python -m py_compile src/main.py`
   - **Build Standalone Windows .exe**: Follow [`.agents/rules/build.md`](file:///home/sahana/Code_Repository/personal/win-folder-thumbnail/.agents/rules/build.md) strictly using `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`.
3. **Headless Qt Testing Invariant**:
   - On Linux/WSL environments, Qt applications require an offscreen platform plugin when no X11/Wayland display server is available.
   - All automated test executions must pass `QT_QPA_PLATFORM=offscreen` (e.g. `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`).

---

## 2. Zero Dead Code & Working Tree Hygiene

1. **Immediate Purge of Superseded Assets**:
   - The repository maintains zero dead code, obsolete feature scaffolding, or abandoned prototypes.
   - When any service, model, or UI component is refactored, the superseded code MUST be completely purged in the same changeset. Git history preserves past versions.
2. **Scratch & Test Asset Hygiene**:
   - Visual inspection scripts, temporary debug dumps (`debug_*.png`, `debug_crop_*.png`), review images (`*_review.*`, `*_whitened.*`, `*_translated.*`), and root-level OCR/translation JSON dumps must be purged immediately after verification.
   - One-off scripts are prohibited in root; persistent operational utilities must reside in dedicated tool modules.
3. **Continuous Working Tree Hygiene**:
   - Never commit build outputs (`dist/`, `build/`), compiled binaries (`*.exe`, `FolderImagePreviewer*`), deep learning models (`assets/models/*.onnx`), or temporary workspace directories (`temp/`).
   - Always verify `git status` before completing any development task.

---

## 3. PyQt6 Threading & Event Loop Hygiene

1. **Zero Blocking on Main GUI Thread**:
   - Heavy image decoding, thumbnail scaling, directory walking, ONNX inference, Japanese OCR (`manga-ocr`), and translation API HTTP requests must NEVER execute on the main GUI thread.
   - All intensive background tasks must be dispatched to dedicated `QThread` workers (e.g. `ThumbnailCache`, `TranslationWorker`, `TranslationQueue`).
2. **Signal-Slot Communication Invariant**:
   - Background threads must communicate with UI components strictly through PyQt signals and slots. Never read or mutate GUI widgets directly from a background thread.
3. **Anti-Crash Worker Lifecycle Management**:
   - All `QThread` and worker instances must handle cancellation gracefully.
   - During dialog close, application shutdown, or folder navigation changes, active workers must be stopped and waited upon (`thread.quit(); thread.wait()`) to prevent fatal `QThread: Destroyed while thread is still running` errors.

---

## 4. Safe Deletion & Recycle Bin Invariant

1. **Strict Recycle Bin Protection**:
   - User folder deletion must NEVER permanently delete files with `shutil.rmtree` or `os.remove`.
   - All deletion actions must route strictly through `src.services.trash_service.send_folder_to_trash()` using `Send2Trash`, ensuring files are recoverable in the Windows Recycle Bin.
2. **Mandatory User Confirmation Dialog**:
   - Deletion of single or batch folders must always prompt the user with a modal confirmation dialog specifying the folder name(s) and count before executing the trash action.

---

## 5. Documentation Synchronization Standard

1. **Mandatory Continuous README Synchronization**:
   - Whenever keyboard shortcuts, CLI flags, configuration settings, architectural topology, or new dependencies are introduced or altered, `README.md` MUST be updated in the same changeset.
2. **README Structure Standards**:
   - System Overview, Core Feature List, Keyboard Shortcuts Table, Requirements, Installation & Local Run, Building Executable (.exe), Running Tests, License.
