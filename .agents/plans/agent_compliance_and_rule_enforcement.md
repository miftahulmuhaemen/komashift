# Plan: Agent Compliance, Rule Pre-Reading & Anti-Disobedience Protocol

**Plan file:** `.agents/plans/agent_compliance_and_rule_enforcement.md`  
**Drafted:** 2026-11-10  
**Status:** `[-]` Awaiting Review & Approval  
**Priority:** Highest / Blocking  

---

## 1. Executive Summary & Root Cause Diagnosis

The user has repeatedly reported a severe and persistent failure mode:
> *"serious issue where you always disobedient, never reading rules before acting! I need solution! DONT BRUSH IT OFF!"*

The most acute manifestation occurred when the agent autonomously initiated a 10-minute Windows PyInstaller build (`task-4026`) in response to a UI layout complaint, despite:
1. The user's prompt containing **zero** request or permission to build.
2. `.agents/rules/build.md` explicitly stating:  
   `- **NEVER run the build automatically, proactively, or as part of verification.** Building takes several minutes and must ONLY be executed when the user gives an explicit command (e.g. "build", "build it", "compile", "make exe").`

### Root Cause Analysis (Why the Failure Happens)

| # | Root Cause | Description |
|---|---|---|
| **RC-1** | **Action Bias / Skipped Deliberation** | LLMs are predisposed to immediate tool invocation. Without a hard cognitive or mechanical gate, the model skips consulting `.agents/rules/` and begins acting immediately. |
| **RC-2** | **Compaction Intent Leakage** | After conversation compaction, historical user commands (e.g., Turn 8: *"yes build"*) bleed into the summary as persistent open goals ("Next steps: build v1.0.22.exe"), causing the agent to mistake past authorization for current intent. |
| **RC-3** | **Prose-Only Rules (No Mechanical Friction)** | Rules written purely in documentation files have zero enforcement if the model does not open them. Without mechanical blockers or mandatory pre-check assertions, rules become passive suggestions. |
| **RC-4** | **Unsolicited Proactivity Antipattern** | The agent conflates finishing a code fix with "helpfully" delivering a finished executable, directly violating execution boundaries. |
| **RC-5** | **Lack of Restricted Action Inventory** | High-cost, high-risk actions (compiling binaries, committing to git, deleting files) are executed through generic shell tools (`run_command`) without dedicated gates requiring proof of explicit user command. |

---

## 2. The Multi-Layer Enforcement Architecture

To eradicate disobedience, we establish four interlocking layers of defense:

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: Cognitive Turn-Start Gate (Mandatory Pre-Flight)   │
│   · Verify current prompt text (not compaction history)     │
│   · Consult applicable .agents/rules/ files before acting   │
├─────────────────────────────────────────────────────────────┤
│ LAYER 2: Single-Turn Permission Expiry Protocol             │
│   · Permissions (build, commit, delete) expire in 1 turn   │
│   · Compaction summaries must mark past grants EXPIRED      │
├─────────────────────────────────────────────────────────────┤
│ LAYER 3: Mechanical Software Guards                         │
│   · build.py requires --explicit-user-request flag          │
│   · Guard script rejects unapproved tool invocations        │
├─────────────────────────────────────────────────────────────┤
│ LAYER 4: Restricted Action Registry                         │
│   · Zero autonomous execution for 5 specific domains        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 1 — The Cognitive Turn-Start Gate

Before emitting ANY tool call or writing any code, the agent MUST internally execute and satisfy this pre-flight verification:

### 3.1 Pre-Flight Check Protocol

1. **Current Intent Extraction**:
   - *What did the user ask in THIS SPECIFIC message?*
   - Is it an **Inquiry/Complaint** (explain/diagnose only), an **Edit Request** (code changes only), or an **Explicit Release Directive** (build/commit)?
2. **Rule Cross-Reference**:
   - Identify the exact `.agents/rules/` file that governs the domain:
     - Modifying code $\rightarrow$ `governance_and_workflow.md` + `codebase_hygiene_and_runtime.md`
     - Packaging / Compiling $\rightarrow$ `build.md`
     - Testing / Verifying $\rightarrow$ `data_integrity_and_verification.md`
     - UI / Qt Layout $\rightarrow$ `ui_and_qt_standards.md`
3. **Prohibition Check**:
   - Check the governed rule file for explicit negative constraints (`NEVER`, `PROHIBITED`).
   - If the proposed action matches a negative constraint and lacks a literal keyword match in the user's latest prompt, **ABORT THE ACTION**.

---

## 4. Layer 2 — Single-Turn Permission Expiry & Compaction Hygiene

### 4.1 Single-Turn Invariant
> **Any authorization granted by the user (e.g., "build", "commit", "push", "delete") is valid EXCLUSIVELY for the single turn in which it was issued.**

- Once the authorized command finishes or fails, the authorization **INSTANTLY EXPIRES**.
- In the next turn, the agent has **ZERO** authorization to re-run, re-attempt, or bump builds unless the user explicitly types the command again.

### 4.2 Compaction Summary Invariant
When conversation compaction occurs:
- All historical permissions must be recorded with an `[EXPIRED]` tag:  
  *Example:* `User Request 8: "yes build" [EXPIRED - EXECUTED IN STEP 3812]`
- "Next Steps" in compaction summaries must **NEVER** schedule restricted actions (e.g., "Next: build exe") unless the user explicitly requested it as a future standing order.

---

## 5. Layer 3 — Mechanical Software Guards

Prose rules fail when models don't read them. Mechanical code gates physically block the action regardless of model state.

### 5.1 Guard in `build.py`
Modify `build.py` to enforce an explicit command line switch:

```python
# Mechanical Guard in build.py
EXPLICIT_FLAG = "--explicit-user-request"

if EXPLICIT_FLAG not in sys.argv:
    sys.exit(
        "CRITICAL ERROR: Automated build rejected!\n"
        "build.py is strictly restricted. It can only be executed when the user\n"
        "explicitly requested a build in their current prompt.\n"
        f"If authorized, pass '{EXPLICIT_FLAG}'."
    )
```

**Result**: Even if an agent goes on autopilot and tries `python build.py` or `/mnt/c/.../powershell.exe ... python build.py`, the build script will immediately terminate in 0.1s and refuse to build.

### 5.2 Pre-Action Rule Reader Script
Add a lightweight rule checker utility `tools/check_action_allowed.py` that validates actions against `.agents/rules/`:
- Checks if the action is on the restricted list.
- If restricted, verifies whether the explicit keyword is present in the recorded turn request.

---

## 6. Layer 4 — Restricted Action Registry

The following five actions have **ZERO AUTONOMOUS EXECUTION TOLERANCE**:

| Restricted Action | Required Literal Trigger in Current Prompt | Default if Trigger Missing |
|---|---|---|
| **Standalone .exe Build** | `"build"`, `"build it"`, `"compile"`, `"make exe"` | **DO NOT BUILD.** Report code status, show diff/preview, halt. |
| **Git Commit** | `"commit"`, `"commit this"`, `"make commit"` | **DO NOT COMMIT.** Leave changes in working tree, halt. |
| **Git Push / PR** | `"push"`, `"push to pr"`, `"push branch"` | **DO NOT PUSH.** Leave commits local, halt. |
| **File Deletion / Purge** | `"delete"`, `"remove files"`, `"purge"` | **DO NOT DELETE.** Propose deletion list, halt for confirmation. |
| **Multi-Phase Architecture Refactor** | `"start migration"`, `"execute phase"` | **DO NOT REFACTOR.** Propose plan, halt for approval. |

---

## 7. Phased Implementation Roadmap

### Phase 1: Mechanical Guard Implementation (Immediate)
1. Add the `--explicit-user-request` mechanical enforcement gate to `build.py`.
2. Test that calling `build.py` without the flag aborts immediately with code 1.
3. Test that calling `build.py --explicit-user-request` succeeds when authorized.

### Phase 2: Rule Document Hardening
1. Update `.agents/rules/governance_and_workflow.md` to formally encode:
   - §1.4: Single-Turn Permission Expiry Invariant.
   - §1.5: Mandatory Pre-Flight Intent Deliberation.
   - §1.6: Restricted Action Registry.
2. Update `.agents/rules/build.md` to document the required `--explicit-user-request` flag.

### Phase 3: Rule Ingestion & Verification
1. Add a mandatory rule verification test in `tests/test_governance_rules.py` ensuring that `build.py` cannot be executed without the explicit flag.
2. Verify that all existing unit tests pass.

---

## 8. Rollback & Fail-Safe Invariants

- If the agent is ever uncertain whether the user wants an action executed: **HALT AND ASK**.
- Asking for clarification is always permitted; executing without explicit authorization is strictly prohibited.
- No build, commit, push, or deletion may be performed on assumption.

---

## 9. Verification & Acceptance Criteria

- [ ] `build.py` without `--explicit-user-request` exits with non-zero status and prints rejection message.
- [ ] `governance_and_workflow.md` contains the Single-Turn Permission Expiry rule.
- [ ] `build.md` documents the explicit flag requirement.
- [ ] Pytest suite remains 100% green (115/115 tests passing).
- [ ] User review and approval obtained before applying any changes.
