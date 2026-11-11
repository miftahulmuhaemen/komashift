---
trigger: always_on
description: Operating safety, plan governance, two-phase pre-commit verification, architectural standards, and git release conventions.
---

# Governance, Safety & Release Standards

Strict rules governing execution safety, planning invariants, verification cadence, architectural layering, and git release conventions for KomaShift.

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
4. **Single-Turn Permission Expiry Invariant**:
   - Any user authorization (e.g. "build", "commit", "push", "delete", "proceed") is strictly valid EXCLUSIVELY for the single turn in which it was issued.
   - The moment that command finishes or fails, the authorization INSTANTLY EXPIRES.
   - It is STRICTLY FORBIDDEN to carry forward permissions across subsequent turns or across conversation compactions.
5. **Mandatory Pre-Flight Intent Deliberation**:
   - Before executing any tool call, the agent MUST explicitly cross-reference the user's current message against `.agents/rules/`.
   - The agent must verify whether the proposed action is governed by negative constraints (`NEVER`, `PROHIBITED`).
6. **Restricted Action Registry (Zero Autonomous Execution)**:
   - **Standalone .exe Build**: Requires explicit trigger (`"build"`, `"compile"`, `"make exe"`) in the CURRENT prompt. Autonomous execution is physically blocked by `build.py --explicit-user-request`.
   - **Git Commit / Push**: Requires unsolicited, explicit user command in the current prompt.
   - **File Deletions**: Requires explicit confirmation.
   - If the trigger is absent, the agent must NEVER perform the action.

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

## 4. Architectural Layering & Separation of Concerns (Ports & Adapters)

1. **Strict Six-Tier Hexagonal Architecture**:
   - **`src/models/`**: Pure data models, dataclasses, and serialization logic (`folder_item.py`, `translation_item.py`, `translation_job.py`). Models have zero dependencies on PyQt6 or external frameworks.
   - **`src/ports/`**: Pure `typing.Protocol` interfaces defining contracts (`page_repository.py`, `translation_provider.py`, `log_sink.py`, `comic_text_renderer.py`). Zero implementation logic.
   - **`src/services/`**: Headless business logic, pure transformers, and typography algorithms (`comic_text.py`, `folder_service.py`, `scanner.py`, `trash_service.py`, `image_compression.py`, `manga_ocr_detector.py`). Services never import `PyQt6.QtWidgets`, `src.infra`, `src.viewmodels`, or `src.ui`.
   - **`src/infra/`**: Outside-world adapters implementing ports (`json_workspace.py`, `file_log_sink.py`, `qt_comic_renderer.py`, `image_rasterizer.py`, `openai_provider.py`). Infra never imports presentation tiers (`src.ui`, `src.viewmodels`).
   - **`src/viewmodels/`**: Headless presentation logic and state binding (`settings_viewmodel.py`, `library_viewmodel.py`, `translation_viewmodel.py`). ViewModels inherit from `QObject`, emit signals with primitive/object payloads, and contain ZERO widgets (`PyQt6.QtWidgets`).
   - **`src/ui/`**: PyQt6 GUI components, dialogs, custom widgets, and event handlers (`main_window.py`, `preview_pane.py`, `folder_list.py`, `thumbnail_strip.py`, `translation_overlay.py`, `settings_dialog.py`, `queue_dialog.py`, `log_dialog.py`).
2. **Decoupling Invariants**:
   - UI widgets must never perform direct disk I/O, heavy mathematical processing, or direct network calls. All operations route through viewmodels, services, and ports.
   - State persistence is managed through `SettingsViewModel` via `QSettings`.
   - Architectural enforcement is mechanically guarded by `lint-imports` and `tests/test_architecture.py`. See [`.agents/rules/architecture_ports_adapters.md`](file:///home/sahana/Code_Repository/personal/win-folder-thumbnail/.agents/rules/architecture_ports_adapters.md) for the placement decision table.
