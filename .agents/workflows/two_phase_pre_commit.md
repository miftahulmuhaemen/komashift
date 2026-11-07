---
name: two_phase_pre_commit
description: Sequential lifecycle for development verification, user commit directives, test execution, and pull request generation.
---

# Workflow: Two-Phase Pre-Commit & Release Lifecycle

This workflow governs the exact sequence required when implementing code changes and preparing git commits for the Windows Folder Image Previewer.

---

## Phase 1: Implementation & Local Validation

1. **Implement Changes**: Make working tree edits in accordance with active plan tasks.
2. **Static Compilation Check**: Run lightweight Python syntax compilation checks:
   ```bash
   .venv/bin/python -m py_compile src/main.py
   ```
   Confirm zero syntax or import errors.
3. **Strict Prohibition on Premature Tests**:
   - NEVER execute test suites (`pytest`) or build scripts (`build.py`) during Phase 1.
4. **Working Tree Cleanliness Check**:
   - Run `git status` to verify:
     - No binaries (`*.exe`, `FolderImagePreviewer*`), models (`assets/models/*.onnx`), logs, or translation caches (`temp/`, `*results*.json`) appear as untracked files.
     - Only intended source files and tests are modified.
5. **Report & Halt**:
   - Present the modified files in the working tree.
   - Confirm clean static syntax check.
   - **HALT immediately**.
   - **Prohibition on Commit Solicitation**: The agent MUST NEVER ask "Are we ready to commit?", "Should I commit?", or nudge the user toward committing. Stop and await user instruction.

---

## Phase 2: Pre-Commit Verification Gate (User-Directed Only)

1. **Trigger Condition**: Triggered EXCLUSIVELY when the user explicitly issues an unsolicited directive to commit (e.g. "commit", "commit this", "yes to commit").
2. **Execute Automated Verification**:
   - Run the full unit and Qt test suite in headless mode:
     ```bash
     QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/
     ```
3. **Halt on Findings**:
   - Present test suite results (total passed, duration).
   - If any test fails, **HALT immediately** for diagnosis and user review before modifying code.
   - Only when all tests are green and confirmed, advance to Step 4.
4. **Commit & Release Execution**:
   - Stage modified files: `git add <files>`.
   - Format commit message according to Conventional Commits:
     - `feat(<scope>): <description>` for new features
     - `fix(<scope>): <description>` for bug fixes
     - `chore(<scope>): <description>` for maintenance or dependency updates
     - `test(<scope>): <description>` for test additions or updates
   - Commit: `git commit -m "<type>(<scope>): <subject>"`.
   - Check current branch via `git rev-parse --abbrev-ref HEAD`:
     - If on a feature branch: Push branch via `git push origin <branch>`.
     - If directed by user, open a PR via `gh pr create`.
