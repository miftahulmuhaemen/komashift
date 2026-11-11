---
name: independent_audit
description: Procedure for dispatching an independent verification subagent to audit code quality, Qt thread safety, translation data integrity, and Git repository hygiene.
---

# Workflow: Independent Adversarial Quality Audit

This workflow defines the procedure for running an independent verification audit before presenting feature results or completed development tasks to the user.

---

## Step 1: Subagent Dispatch

1. The primary agent launches an independent verification subagent:
   - Tool: `invoke_subagent`
   - Role: `Adversarial Quality Auditor`
   - TypeName: `research` (or `self`)
2. The subagent operates in a separate context to prevent confirmation bias from the implementation run.

---

## Step 2: PyQt6 Thread Safety & UI Responsiveness Audit

The subagent inspects the modified code:
1. **Zero Main Thread Blocking**: Verify that file system scanning, image thumbnail decoding, ONNX inference, and network calls are strictly offloaded to worker threads.
2. **Signal-Slot Correctness**: Ensure UI updates pass through Qt signals; verify that background workers never invoke widget methods directly.
3. **Thread Lifecycle**: Check that workers implement clean `stop()` methods and that parent dialogs call `wait()` on close.

---

## Step 3: OCR & Translation Workspace Integrity Audit

The subagent checks translation logic:
1. **Atomic File Operations**: Verify that cache writes to `ocr_results.json` and `translation_results.json` write to temporary files before atomic replacement.
2. **Path Isolation**: Confirm that all cache files and execution logs are confined strictly to `<folder>/temp/` and never written to repository root.
3. **Zero Fabricated Placeholders**: Confirm that missing detections cleanly result in empty lists (`[]`) rather than fabricated mock translations or fake bounding boxes.

---

## Step 4: Git Repository & Binary Hygiene Audit

The subagent verifies `git status` and staged files:
1. **Zero Large Binary Commits**: Confirm that no `assets/models/*.onnx`, `*.pt`, `*.bin`, or `dist/*.exe` files are staged or untracked.
2. **Zero Scratch Media**: Verify that no visual debug dumps (`debug_*.png`), review images (`*_review.*`, `*_whitened.*`), or sample test images (`1.webp`) appear in `git status`.
3. **`.gitignore` Enforcement**: Verify all patterns match rules specified in `.gitignore`.

---

## Step 5: Test Suite Verification

1. Execute full headless test suite:
   ```bash
   QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/
   ```
2. Confirm 100% test pass rate with zero unexpected regressions or warnings.

---

## Step 6: Report Disposition

1. The auditor subagent returns a concise report:
   - **PASS**: All dimensions meet quality, safety, and hygiene invariants.
   - **FAIL**: Defect list detailing exact files, line numbers, or broken invariants.
2. If any failure is reported, the primary agent must resolve the defect before presenting the work to the user.
