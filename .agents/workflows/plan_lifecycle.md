---
name: plan_lifecycle
description: Sequential lifecycle for creating, executing, updating, and pruning task implementation plans.
---

# Workflow: Plan Lifecycle & Task Execution

This workflow defines the procedural steps for executing multi-step tasks across agent sessions for the Windows Folder Image Previewer.

---

## Step 1: Draft Active Plan

1. Create a dedicated plan file in `.agents/plans/<plan_name>.md`.
2. Follow the standard plan schema:
   - **Goal & Scope**: High-level problem statement, boundaries, and acceptance criteria.
   - **Technical Design**: Modules, PyQt6 widgets, services, signal signatures, and state management.
   - **Task Breakdown with Status Checkboxes**: Verifiable items (`[ ]` Pending, `[/]` In Progress, `[x]` Completed, `[-]` Blocked).
   - **Dependencies & Inter-Task Blockers**: Threading, model, or UI dependencies.
   - **Verification Protocol**: Exact commands, unit tests, and headless Qt validations required to confirm completion.

---

## Step 2: Pre-Execution Approval Gate

1. Present the plan file path and executive summary to the user in chat.
2. **HALT immediately**.
3. **Zero Action Without Explicit Approval**: The agent MUST NOT execute code edits, file creations, or refactorings until the user explicitly replies with unambiguous approval (e.g. "approved", "proceed").

---

## Step 3: Sequential Task Execution

1. Execute approved tasks sequentially.
2. Update the plan document checkboxes in `.agents/plans/<plan_name>.md` after each milestone is verified.
3. **Halt on Blockers**: If an error, threading lock, or ambiguous requirement prevents finishing an approved task, halt immediately, document the blocker in the plan file, and ask the user for guidance before switching tasks.

---

## Step 4: Verification & Completion Pruning

1. Execute the verification protocol specified in the plan (e.g. `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`).
2. Confirm all tasks are marked `[x]`.
3. **Prune Completed Plan**:
   - Delete the completed plan file from `.agents/plans/` once verified, or archive if historical audit trail is requested.
   - Never hoard obsolete completed plan files. Maintain an active-only plan directory.
