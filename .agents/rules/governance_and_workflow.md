---
trigger: always_on
description: Operating safety, plan governance, two-phase pre-commit verification, architectural standards, and git release conventions.
---

# Governance, Safety & Release Standards

Strict rules governing execution safety, planning invariants, verification cadence, architectural layering, and git release conventions for the Windows Folder Image Previewer.

---

## 1. Operating Safety & Execution Boundaries

1. **Root Privileges & Destructive Operations**:
   - **Never run `sudo`**: If a command requires root privileges, provide the command to the user and request manual execution.
   - **Explicit Confirmation for Destructive Actions**: Always ask explicit permission before performing destructive operations (e.g. deleting files, bulk disk modifications, resetting configuration).
   - **Respect Project Scope**: Never read, modify, or execute files outside the repository root without explicit consent.
2. **Single-Line CLI Commands for User Execution**:
   - Any shell command provided for the user to execute MUST strictly be formatted as a single atomic line (using `&&` chaining if multi-step). Multi-line blocks, unquoted breaks, and here-docs (`cat <<EOF`) are prohibited.
3. **Inquiry-First Protocol (Explain Before Mutating)**:
   - When the user asks a question, raises an inquiry, or reports an unexpected behavior, the agent MUST answer the question, diagnose the facts, and explain the root cause first.
   - The agent is STRICTLY PROHIBITED from modifying source code or applying unauthorized patches during an inquiry turn.
   - Any remediation must be proposed as a recommendation or plan, halting for the user's explicit direction or approval before any action is taken.

---

## 2. Plan Lifecycle & Pre-Execution Approval Gate

1. **Active-Only Plan Governance**:
   - Multi-step tasks must follow [`.agents/workflows/plan_lifecycle.md`](file:///home/sahana/Code_Repository/personal/win-folder-thumbnail/.agents/workflows/plan_lifecycle.md).
   - Dedicated active plans reside in `.agents/plans/<plan_name>.md`. Only active plans may exist; completed plans must be deleted or replaced immediately upon verified completion.
2. **Pre-Execution Approval Gate**:
   - Never execute code edits, file creations, or major refactorings until the user explicitly replies with unambiguous approval in chat (e.g. "approved", "proceed").
   - Present the plan path and concise summary, then halt immediately.
3. **Subprocess & Anti-Zombie Hygiene**:
   - Any spawned worker, build process (e.g. PowerShell PyInstaller build), or test process must be tracked and terminated upon task completion, failure, or timeout.
   - Background threads (`QThread`) and file handles must be cleanly closed to prevent dangling locks on Windows/WSL filesystems.

---

## 3. Two-Phase Pre-Commit Verification Workflow

All development and release actions strictly follow [`.agents/workflows/two_phase_pre_commit.md`](file:///home/sahana/Code_Repository/personal/win-folder-thumbnail/.agents/workflows/two_phase_pre_commit.md):

1. **Phase 1: Active Development (Build & Static Check Only)**:
   - Run ONLY static checks: `.venv/bin/python -m py_compile src/**/*.py`.
   - Test runners (`pytest`) are strictly PROHIBITED during Phase 1 to conserve resources and avoid test noise.
   - Upon completing implementation and static checks, review working tree cleanliness via `git status`, list modified files, and **HALT immediately**.
   - **Zero Autonomous Commits & Zero Nudging**: Never autonomously execute `git commit`, `git push`, or `gh pr create`. Never prompt or nudge the user ("Are you ready to commit?"). Keep edits in the working tree until explicitly directed.
2. **Phase 2: Pre-Commit Gate (User-Directed Only)**:
   - Triggered EXCLUSIVELY when the user explicitly issues an unsolicited directive to commit (e.g. "commit", "commit this", "yes to commit").
   - Execute verification: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`.
   - Stage verified files and commit using conventional commits format: `<type>(<scope>): <subject>`.

---

## 4. Architectural Layering & Separation of Concerns

1. **Strict Three-Tier Architecture**:
   - **`src/models/`**: Data models, dataclasses, and serialization logic (`folder_item.py`, `translation_item.py`, `translation_job.py`). Models must have zero dependencies on PyQt6 UI widgets or heavy external dependencies.
   - **`src/services/`**: Headless business logic, directory scanning, thumbnail caching, OCR engines, ONNX inference, and translation API clients (`folder_service.py`, `scanner.py`, `thumbnail_cache.py`, `onnx_bubble_detector.py`, `manga_ocr_detector.py`, `translation_client.py`, `translation_worker.py`, `translation_workspace.py`, `trash_service.py`). Services must never import Qt GUI widgets.
   - **`src/ui/`**: PyQt6 GUI components, dialogs, custom widgets, and event handlers (`main_window.py`, `preview_pane.py`, `folder_list.py`, `thumbnail_strip.py`, `translation_overlay.py`, `settings_dialog.py`, `queue_dialog.py`, `log_dialog.py`, `batch_rename_dialog.py`).
2. **Decoupling Invariants**:
   - UI widgets must never perform direct disk I/O, heavy mathematical processing, or direct network calls. All operations must route through the appropriate service layer.
   - State persistence is centralized via `QSettings` in `src/ui/main_window.py` and `src/ui/settings_dialog.py`.
