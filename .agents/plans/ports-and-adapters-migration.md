# Plan: Ports & Adapters Migration + Test Hardening

**Plan file (repo):** `.agents/plans/ports-and-adapters-migration.md`
**Drafted:** 2026-11-10
**Status:** `[-]` Awaiting approval (plan_lifecycle.md Step 2)
**Revision:** R2 — re-reviewed against the codebase with the deep-module vocabulary (module / interface / implementation / depth / seam / adapter / leverage / locality).

---

## 1. Goal & Scope

### Goal

Move `win-folder-thumbnail` from an informal 3-tier layout to **Ports & Adapters (hexagonal-lite) with thin, widget-free ViewModels**, so the translation pipeline is testable through its interfaces and new code has an obvious home, then **mechanically prevent regression** by LLM or human contributors.

### In scope

1. Six packages: `models/`, `ports/`, `services/`, `infra/`, `viewmodels/`, `ui/`.
2. Five ports (four new, one already latent): `PageRepository`, `TranslationProvider`, `LogSink`, `ComicTextRenderer`.
3. Extraction of `MainWindow` (1,511 LOC) into ViewModels, one slice per commit.
4. Test hardening: missing unit tests, a real end-to-end test, and mutation testing on pure-logic modules.
5. Mechanical enforcement: `import-linter` contracts + LOC ratchet + agent-facing rule.

### Explicit non-goals

| Non-goal | Reason |
|---|---|
| Any user-visible behaviour change | Parity is the acceptance bar (Round 1, Q9). A behaviour change makes every regression ambiguous, and would trigger `data_integrity_and_verification.md` §5 (mandatory full-page visual proof + token report for **both** translation approaches). |
| Changing `QSettings` keys (`llm_*`, `last_root_folder`) | Existing user installs must keep their config. |
| Changing the on-disk `temp/` schema | Existing `temp/ocr_results.json` caches must keep resuming. |
| Changing translation prompts, models, OCR math, or typography output | Out of scope; separate changeset with its own proof obligations. |
| Full Clean Architecture (use-case/interactor objects, DTO mappers) | Round 1, Q5. `TranslationWorker` already *is* the use case at 491 LOC; a second orchestration layer would delegate to the first. |
| Rewriting the preview domain first | Round 1, Q4. It is already ~95% clean. |

### Acceptance criteria

- [ ] `lint-imports` passes and is executed by `pytest`.
- [ ] No module in `services/` imports `PyQt6.QtWidgets`, `PyQt6.QtGui` widgets, `infra/`, `viewmodels/`, or `ui/`.
- [ ] `services/image_rasterizer.py` no longer imports `src.ui`.
- [ ] `ui/` contains zero direct filesystem I/O (currently 6 sites) and zero `TranslationWorkspace` instantiation (currently 12).
- [ ] `main_window.py` ≤ 400 LOC, enforced by a ratchet test.
- [ ] `pytest tests/` green, including the new E2E test.
- [ ] Mutation score ≥ 80% on the scoped pure-logic set.
- [ ] `README.md` architecture section updated; `governance_and_workflow.md` §4 rewritten.

---

## 2. Current State — Evidence

| Fact | Value | Source |
|---|---|---|
| `src/` size | 7,535 LOC / 31 files | `wc -l` |
| `src/ui/main_window.py` | 1,511 LOC ≈ 20% of `src/`, ~45 handlers | `grep -n 'def '` |
| Tests | 115 tests, 18 files, **5.6 s**, but **1 SIGSEGV in 23 sequential runs (≈4.3%)** | `.venv/bin/pytest` ×23 |
| Shared fixtures | **none** — no `conftest.py`, zero `@pytest.fixture`, ~90 duplicated lines | `grep` |
| Test doubles | **none** — every test monkeypatches internals (`MagicMock` on `worker.translator`, `worker.detector`) | `test_translation_worker.py:21,36` |
| Lint/type/arch gate | **none** — no `pyproject.toml`, `ruff`, `mypy`, `pre-commit`, `import-linter` | `ls` |
| CI gate | `pytest` only, then PyInstaller | `.github/workflows/build.yml` |

### 2.1 The decisive finding

`git log --diff-filter=A` proves that **every architectural violation arrived with new feature work**, not with the original codebase:

| File | Introduced in |
|---|---|
| `translation_queue.py`, `translation_overlay.py` | `1e003f1` — *implement Japanese manga OCR, batch translation, and zoom overlay* |
| `image_rasterizer.py`, `translation_workspace.py` | `4d02813` — *local ONNX bubble detection, robust OCR segmentation, comic typography overlay* |

The `.agents/rules` held for the original app. They failed exactly where they gave no answer to **"where does this new thing go?"** — not "don't import X". This drives §7.

### 2.2 The two leaks

**Leak A — `services → ui`, exactly once.**

```
src/services/image_rasterizer.py:13  from src.ui.translation_overlay import TranslationOverlayWidget
src/services/image_rasterizer.py:10  from PyQt6.QtWidgets import QApplication
```

The rasterizer constructs a widget, forces `scaled_size=orig_size` and `offset=(0,0)` (`:64-65`), and boots a `QApplication` (`:41-43`) — to borrow a text-fitting algorithm and a shape→brush policy that have nothing to do with widgets.

**Leak B — `ui → service privates`, six times.**

```
translation_worker.py:270  detector._init_engine()
translation_worker.py:271  detector._engine
translation_worker.py:273  detector._engine
translation_worker.py:277  detector._segment_bubble(...)
main_window.py:819         queue_manager._emit_overall_progress()
main_window.py:899         queue_manager._emit_overall_progress()
```

Each exists because the target's interface lacks a verb the caller needs.

### 2.3 `TranslationWorkspace` — the widest interface in the tree

- **18 public methods**, 238 LOC.
- **Deletion test:** complexity reappears across **N = 9 call sites in `src/`** plus 3 in `queue_dialog`, so N(src)=9, N(with tests)=13. It earns its keep.
- **But ~5 of its 18 methods do not.** `get_temp_dir`, `ocr_file`, `translation_file`, `log_file`, `get_translation_file` are pure **layout disclosure** — they exist so `queue_dialog` (`:659`, `:867`) can rebuild paths instead of calling a reader.
- **Undocumented invariants a caller must know:** `<folder>/temp/` layout; three exact filenames; language-suffixed names with a special case where `"en"` prefers `translation_results_en.json` **only if it already exists**, else falls back to the unsuffixed file (`:79-83`) — so a caller cannot predict which file a write lands in without checking `exists()`; the `("mix","mixed","mix-lang","all")` alias set (`:77`); `save_translations` **merges** rather than replaces and writes **twice** (`:95`, `:113`); `load_translations` globs every `translation_results_*.json` and merges missing keys (`:128-135`), letting stale language files pollute any load.
- **Log-append is welded to persistence:** `save_page_ocr` calls `append_log` (`:52`), `save_translations` at (`:115`), `clear_cache` at (`:241`).

### 2.4 Latent crash in the test harness

`ThumbnailCache` grabs `QThreadPool.globalInstance()` (`thumbnail_cache.py:66`) and connects a closure that captures `self` (`:90-101`). `MainWindow` constructs one cache per window (`main_window.py:125`); `tests/test_ui.py` builds ~22 windows; `qtbot.addWidget` deletes each at teardown. Nothing ever calls `waitForDone()`. A queued `finished` signal therefore lands on a cache whose C++ object is gone.

**Reproduction status: CONFIRMED, and worse than first reported.**

Sequential full-suite runs from a clean shell:

| Batch | Result |
|---|---|
| Batch 1 (12 runs) | 12/12 exit 0 |
| Batch 2 (6 runs) | 5/6 exit 0, **1 × exit 139 (SIGSEGV)** |
| **Cumulative** | **1 crash in 23 sequential runs ≈ 4.3%** |

Not load-induced. A *single* run in an otherwise-idle shell crashes.

Captured stack (`/tmp/seg_6.txt`):

```
Fatal Python error: Segmentation fault
Current thread (most recent call first):
  File "src/services/thumbnail_cache.py", line ??? in handle_finished
  File ".venv/.../pytestqt/plugin.py", line 220 in _process_events
  File ".venv/.../pytestqt/plugin.py", line 188 in pytest_runtest_call
```

**The crashing test is not the guilty test.** The run dies at **test 113 of 115 — `tests/test_ui_translation_workflow.py::test_toggle_overlay_shortcut`** (112 dots printed, then the fault). That test takes only `qtbot`: no `tmp_path`, no images, so it loads **no thumbnails of its own**. The pending queued `finished` signal belongs to a `ThumbnailCache` from an *earlier* window, already destroyed by `qtbot.addWidget` teardown, and Qt delivers it during whichever test owns the event loop at that moment.

That deferral is why this defect has survived: the fault surfaces in an unrelated test, so the failure looks like flakiness rather than the deterministic lifetime bug it is. **12 `qtbot.addWidget(window)` sites in `test_ui.py` each leave a possible pending signal.**

**Consequence for this plan:** every green run today is a ~96% coin flip. Mutation testing (which needs thousands of deterministic runs) is impossible until Phase 0 lands, and any test-count or coverage claim made before then is unreliable. This is now the **top-priority** item, not a hygiene task.

---

## 3. Review Correction — The Ports Ledger

> This section is the direct output of the deep-module review. The Round-1 plan listed four ports. Applying **"one adapter means a hypothetical seam, two adapters means a real one"** and the **deletion test** prunes two of them.

| Port | Decision | Two-adapter justification | Evidence |
|---|---|---|---|
| `PageRepository` | **KEEP** | on-disk `JsonTempWorkspace` + in-memory fake | 18 public methods, 12 UI call sites, 5 layout-disclosure methods |
| `TranslationProvider` | **KEEP** | `OpenAiProvider` + `AnthropicProvider` + `FakeProvider` | protocol already branched on a string at `translation_client.py:36`; tests already stub adapter #3 at `test_translation_worker.py:36` |
| `ComicTextRenderer` | **KEEP** | two callers need one verb (rasterizer + overlay widget) | `fit_comic_text` ~98 LOC already parameterised by `scale_factor` |
| `LogSink` | **KEEP** | file sink + in-memory sink; written and read across a seam | worker writes via `workspace.append_log`; `queue_dialog:659,867` reads/truncates by **rebuilding the path** |
| `BubbleDetector` | **DROP** | **one** production adapter only | `OnnxBubbleDetector` constructed at `manga_ocr_detector.py:31`; `is_available()` degradation is *forced*, not chosen |
| `OcrEngine` | **DROP** | **one** production adapter only | `ocr_engine=None` already exists as an internal seam at `manga_ocr_detector.py:23` |

### Consequence of dropping the two

`BubbleDetector` and `OcrEngine` stay **internal seams** of `MangaOcrDetector`. They become optional constructor parameters (defaulting to the real thing) purely for testability — not ports, not exported from `ports/`. This also fixes an existing asymmetry: the OCR half already has the slot (`ocr_engine=None`, `:23`) while the detection half does not (`:31`).

### Three seams deliberately NOT created

| Rejected seam | Why it would not earn its keep |
|---|---|
| `ThumbnailCache.load_async` callback → signal | One consumer (`queue_dialog.PageThumbnailHoverPopup`), one producer, same file. Deleting the callback dict would make complexity vanish, not redistribute. |
| `ImageRasterizer` `QApplication` bootstrap | Only two states (offscreen/real). `QApplication.instance()` is already the process-wide injector. Extracting it moves the same `if not app` elsewhere. |
| `MainWindow` → a `Presenter` holding a view reference | Re-creates today's coupling under a new name. Round 1, Q2 already settled on widget-free ViewModels instead. |

---

## 4. Target State

### 4.1 Package map

```
src/
├── main.py                  entry point (unchanged)
├── version.py               (unchanged)
├── models/                  pure dataclasses — zero Qt (unchanged)
│   ├── folder_item.py  translation_item.py  translation_job.py
├── ports/                   NEW — Protocol definitions only, zero logic
│   ├── page_repository.py     PageRepository, ChapterStatus
│   ├── translation_provider.py TranslationProvider, TranslationError
│   ├── log_sink.py            LogSink
│   └── comic_text_renderer.py ComicTextRenderer (QPainter contract)
├── services/                business logic — NO PyQt6.QtWidgets, NO infra, NO ui
│   ├── scanner.py  folder_service.py  trash_service.py   (unchanged, already clean)
│   ├── translation_sequence.py  NEW — extracted from TranslationWorker.run()
│   ├── comic_text.py            NEW — extracted from TranslationOverlayWidget
│   ├── manga_ocr_detector.py    (Qt-free already; internal seams)
│   └── image_compression.py
├── infra/                   NEW — everything that touches the outside world
│   ├── qt_threads.py            TranslationWorker (QThread), ThumbnailCache
│   ├── json_workspace.py        JsonTempWorkspace adapter for PageRepository
│   ├── file_log_sink.py         FileLogSink adapter
│   ├── qt_comic_renderer.py     QtComicTextRenderer adapter
│   ├── openai_provider.py       OpenAiProvider adapter
│   ├── anthropic_provider.py    AnthropicProvider adapter
│   ├── onnx_bubble_detector.py  (moved)
│   └── image_rasterizer.py      (moved; now Qt-widget-free)
├── viewmodels/              NEW — QObject, signals, ZERO widgets
│   ├── library_viewmodel.py     folders, selection, rename/delete
│   ├── translation_viewmodel.py queue, jobs, credentials
│   └── settings_viewmodel.py    QSettings read/write
└── ui/                      widgets only — no I/O, no service internals
    ├── main_window.py           ≤400 LOC: wiring + layout
    └── ... (10 widgets/dialogs)
```

### 4.2 Dependency rule (the one line that matters)

```
ui  →  viewmodels  →  services  →  ports  ←  infra
                                        ↑
                                     models
```

`infra` implements `ports` and may import `services`/`models`. **Nothing** imports `infra` except `main.py` (composition root) and `viewmodels`.

---

## 5. Phases

Each phase leaves the app launchable and the suite green. No phase mixes a structural change with a behaviour change.

### Phase 0 — Test foundations and latent crash

> Must land first: no migration is verifiable on an unstable oracle.

- [ ] **[ENTRY GATE — B5, owned by the separate cleanup agent]** Confirm the working tree is committed and clean: `git status --porcelain -- src tests` returns empty; the 33 root artifacts are purged; `image_rasterizer.py` and `image_compression.py` are committed. **Do not start Phase 0 until this holds** — see §9 B5 and F.1.
- [ ] Create `tests/conftest.py` with fixtures: `qapp`, `drain_threadpool` (autouse — cancels and waits on `QThreadPool.globalInstance()` before teardown), `isolated_qsettings` (autouse — `QSettings.setDefaultFormat(IniFormat)` + `setPath` to `tmp_path`, then `clear()`), `tmp_library` (a 2-chapter × 2-page image tree).
- [ ] Add `ThumbnailCache.shutdown()` (`cancel` + `waitForDone`) and call it from `MainWindow.closeEvent`.
- [ ] Replace `tests/test_ui.py:352-353` production-namespace `QSettings` writes with the `isolated_qsettings` fixture.
- [ ] Delete the two proven-dead imports `main_window.py:24-25` (`MangaOcrDetector`, `OpenAITranslator`).
- [ ] Delete the unreachable block `translation_worker.py:75-80` (re-assigns `self.detector` after `__init__` already guaranteed non-`None`).
- [ ] Add `requirements-dev.txt`: `pytest-cov>=7.0`, `import-linter>=2.0`, `mutmut>=3.8`.
- [ ] Confirm `graphify` is on PATH and record its version: `graphify --version` (expected `0.9.24`). It is an external CLI (`uv` tool `graphifyy`), **not** a pip dependency of this project — do not add it to `requirements*.txt`.`,
- [ ] Run `graphify extract .` (AST only, **no** `--mode deep`) and commit `graphify-out/graph.json` as the frozen pre-migration baseline. Add `graphify-out/*` + `!graphify-out/graph.json` to `.gitignore`. See Appendix E.6.
- [ ] Verify: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/ -q` ×**30** → 30/30 exit 0. (30 runs, not 10: at the measured 4.3% rate, 10 runs would pass 64% of the time by luck. 30 runs gives ~73% detection power, and the crash must be *proven gone*, not unobserved.)

**Files:** `tests/conftest.py` (new), `src/services/thumbnail_cache.py`, `src/ui/main_window.py`, `src/services/translation_worker.py`, `tests/test_ui.py`, `requirements-dev.txt` (new).

---

### Phase 1 — Skeleton + enforcement (turn the gate on before refactoring)

> Enforce first, migrate second. If the gate lands after the refactor, there is nothing stopping drift during the refactor.

- [ ] Create `src/ports/`, `src/infra/`, `src/viewmodels/` with `__init__.py` re-exports.
- [ ] Add `.importlinter` (INI style — no `pyproject.toml` required):

```ini
[importlinter]
root_package = src
include_external_packages = True

[importlinter:contract:layers]
name = Layered architecture
layers =
    src.ui
    src.viewmodels
    src.infra
    src.services
    src.ports
    src.models

[importlinter:contract:no-qt-in-services]
name = Services are headless
type = forbidden
source_modules = src.services
forbidden_modules = PyQt6.QtWidgets, PyQt6.QtGui

[importlinter:contract:no-ui-in-services]
name = Services never depend on ui, viewmodels, or infra
source_modules = src.services
forbidden_modules = src.ui, src.viewmodels, src.infra

[importlinter:contract:no-infra-in-ui]
name = UI depends on viewmodels, not adapters
source_modules = src.ui
forbidden_modules = src.infra
```

- [ ] Add `tests/test_architecture.py` that shells `lint-imports` and fails on non-zero — so the existing `pytest` CI step becomes the gate with **no workflow-file change**.
- [ ] Add the LOC ratchet test: ceilings seeded from today's sizes +5%, asserting `actual <= ceiling` and `ceiling` **may only decrease**.
- [ ] Seed the ratchet with a `baseline` dict so the gate is green on day one.
- [ ] Add `tests/test_architecture_graph.py` — Graphify drift gate (Appendix E.4): `graphify update . --force`, diff `graphify-out/graph.json` vs the committed baseline; assert no cycles; assert `graphify god-nodes --top 20 --json` degrees <= frozen ceiling; assert every node path starts with one of the six tiers.
- [ ] Capture the pre-migration `graphify god-nodes --top 20 --json` output as the hub-ceiling source.
- [ ] `graphify hook status`; inspect what `graphify install --platform agents` would write **before** running it (E.5.3 — it must not overwrite the 9 tracked governance files). Then `graphify hook install`.
- [ ] Verify: `pytest` green; deliberately add `from src.ui import main_window` to a service and confirm red; deliberately add a 7th top-level package under `src/` and confirm the graph gate goes red.

**Files:** `.importlinter` (new), `tests/test_architecture.py` (new), 3 × `__init__.py` (new), `requirements-dev.txt`.

---

### Phase 2 — `PageRepository` (highest leverage)

- [ ] Write `src/ports/page_repository.py`: five methods — `load_pages()`, `save_page(page)`, `load_translations(target_lang)`, `save_translations(translations, target_lang)`, `status(target_lang, image_paths)` → `ChapterStatus` (frozen dataclass: `ocr_complete`, `translated_filenames`, `manual_filenames`).
- [ ] Implement `src/infra/json_workspace.py` — move the body of `TranslationWorkspace` here, unchanged in behaviour.
- [ ] Fix the **merge-vs-replace** and **double-write** defects only if a parity test proves they are unreachable in normal flow; otherwise preserve behaviour exactly and record the defect as a follow-up issue.
- [ ] Rewrite the 12 UI call sites to use the port, deleting the 5 layout-disclosure methods.
- [ ] Delete `src/services/translation_workspace.py`.
- [ ] Port `tests/test_translation_workspace.py` (4 tests) to the new adapter.
- [ ] Verify: all 12 sites compile; `pytest` green; `lint-imports` green.

**Effort:** 1 of the 8 phases, and the largest single win: interface 18 → 5.

---

### Phase 3 — `LogSink`

- [ ] `src/ports/log_sink.py`: `append(message)`, `read()`, `clear()`.
- [ ] `src/infra/file_log_sink.py`; `tests/fakes/memory_log_sink.py`.
- [ ] Remove path rebuilding at `queue_dialog.py:659,867` in favour of the port.
- [ ] Verify: log viewer still renders; `pytest` green.

---

### Phase 4 — `TranslationProvider` split

- [ ] `src/ports/translation_provider.py`: `translate_text_batch(bubbles, target_lang)`, `translate_page_visual(page, image, target_lang)`, `translate_text_with_context(text, context, target_lang)`.
- [ ] `src/infra/openai_provider.py` + `src/infra/anthropic_provider.py`, splitting `translation_client.py:36,290,359,612` branch points.
- [ ] Keep the pure helpers (`_is_pure_punctuation_or_symbol`, `_normalize_punctuation_text`, `_extract_json_from_content`, `_parse_response`) in `services/` — they are logic, not transport.
- [ ] Delete the `protocol` string parameter; select the adapter at the composition root.
- [ ] Port 16 tests from `tests/test_translation_client.py` to the adapters.
- [ ] Verify: both protocols still translate; `pytest` green.

---

### Phase 5 — `ComicTextRenderer` (kills Leak A)

- [ ] `src/ports/comic_text_renderer.py`: `render(painter, page, translations, scale_factor, offset)`.
- [ ] `src/services/comic_text.py`: `fit_comic_text` (~98 LOC) + shape→brush policy — pure, no Qt widgets.
- [ ] `src/infra/qt_comic_renderer.py`: the `QPainter` adapter.
- [ ] Rewrite `TranslationOverlayWidget.paintEvent` to be a thin caller.
- [ ] Rewrite `ImageRasterizer` to use the renderer — **this deletes `image_rasterizer.py:13`, the only `services → ui` import in the tree.**
- [ ] Verify: a **pixel oracle** now exists — render a known page, assert the bubble region changed and the panel border did not. This replaces the current "file exists + dimensions" assertion (`test_image_rasterizer.py:33-39`).

---

### Phase 6 — Worker dependency injection (kills Leak B’s first four)

- [ ] `TranslationWorker.__init__` accepts `provider`, `detector`, `repository`, `log_sink`; all four default to `None` → constructed once at the composition root.
- [ ] Add a public verb to `MangaOcrDetector` for `translation_worker.py:277` — e.g. `detect_region(image_path, bbox, page_index)` — instead of reaching into `_segment_bubble`.
- [ ] Add public `TranslationQueueManager.notify_overall_progress()` for `main_window.py:819,899` instead of `_emit_overall_progress()`.
- [ ] Replace the 3-way `engine_mode`/`job_type` if-chain with a strategy choice at construction.
- [ ] Verify: `pytest` green; no `_`-prefixed attribute access across a module boundary (`grep`).

---

### Phase 7 — ViewModels + `MainWindow` drain

> **One ViewModel per commit.** `MainWindow` is split last.

- [ ] `settings_viewmodel.py` — absorb `_get_api_credentials` (10-key read, `main_window.py:976-987`) and all `setValue` calls.
- [ ] `library_viewmodel.py` — absorb folder load/scan, selection, rename, batch rename, delete-to-trash, navigation.
- [ ] `translation_viewmodel.py` — own `TranslationQueueManager`, job construction, overlay toggle state, manual-box dispatch.
- [ ] Delete each corresponding handler group from `MainWindow` **in the same commit** that adds the VM method.
- [ ] Lower the LOC ratchet ceiling after each commit.
- [ ] Verify after each: `pytest` green; ratchet green; `main_window.py` LOC strictly decreasing.

---

### Phase 8 — Preview domain + documentation

- [ ] Move `thumbnail_cache.py` to `src/infra/qt_threads.py`; keep `create_thumbnail_image` (pure) in `services/`.
- [ ] Apply the same ViewModel treatment to `folder_list` / `thumbnail_strip` only where it removes real coupling — do not manufacture symmetry.
- [ ] Rewrite `governance_and_workflow.md` §4 with the six tiers and the dependency rule.
- [ ] Add `.agents/rules/architecture_ports_adapters.md` (`trigger: always_on`) containing the **placement decision table** (§7.3).
- [ ] Update `README.md` Architecture section (required by `codebase_hygiene_and_runtime.md` §5).
- [ ] Verify: full suite + `lint-imports` + ratchet + 10× stability run.

---

## 6. Test Strategy

### 6.1 Missing unit tests for core integral functionality

These are behaviours the pipeline depends on but no test proves today.

| # | Behaviour | Module | Why it matters |
|---|---|---|---|
| T1 | Atomic write: `.tmp` then `replace`; interrupted write leaves the previous file intact | `JsonTempWorkspace` | `data_integrity_and_verification.md` §2.2 mandates it; unproven |
| T2 | Corrupt-JSON recovery returns `{}` and logs, never raises | `JsonTempWorkspace` | A truncated cache must not brick a chapter |
| T3 | Per-language file resolution: `en`, `id`, `mix`/`mixed`/`all`, and the `en`-specific-file-exists branch | `JsonTempWorkspace` | `:79-83` is unpredictable by inspection — it *needs* a test |
| T4 | `clear_cache()` scoped to `temp/` only | `JsonTempWorkspace` | Destructive path |
| T5 | `BubbleBlock`/`PageTranslation` round-trip incl. `None` `expanded_bbox`/`centroid`, `is_manual`, `target_lang` | `models/translation_item.py` | `test_models.py` is 16 LOC — near-empty |
| T6 | `TranslationJob.toggle_image` preserves folder ordering; `update_progress` clamps at `total == 0` | `models/translation_job.py` | `:96` divides by `total` |
| T7 | Queue cancel path and the `queue_state_changed` transitions | `TranslationQueueManager` | Cancel is the one path a user hits on a mistake |
| T8 | Worker cancellation via `isInterruptionRequested()` | `TranslationWorker` | **Unproven** — 5 interruption sites, zero tests |
| T9 | Rasterizer **pixel** correctness, not "file exists" | `ImageRasterizer` | Current oracle cannot fail |
| T10 | ONNX-unavailable fallback (`is_available() == False`) | `MangaOcrDetector` | Rule §4.2 requires graceful degradation |
| T11 | `_segment_bubble` geometry + `_split_multi_lobe_bubble` | `MangaOcrDetector` | 126 `BinOp` whose outputs are never asserted |
| T12 | Scanner: hidden/system folders, no-image folders, permission error, natural sort | `scanner.py` | Core navigation correctness |
| T13 | `image_compression` scale/quality clamping and mode conversion | `image_compression.py` | Vision-path payload correctness |

**Target:** +35 to +45 tests; `pytest-cov` with `--cov=src --cov-fail-under=85` on `models/`, `services/`, `ports/` only (UI excluded).

### 6.2 End-to-end test

New file `tests/test_e2e_translation_pipeline.py`. Only the network is faked.

```
real MainWindow → real TranslationQueueManager → real TranslationWorker (QThread)
  → real MangaOcrDetector with FakeBubbleDetector  (internal seam, not a port)
  → FakeTranslationProvider (returns deterministic map)
  → real JsonTempWorkspace on tmp_path     → temp/ocr_results.json
  → real ImageRasterizer → ComicTextRenderer → output PNG
```

Assertions: `temp/ocr_results.json` and `translation_results_en.json` exist with the expected bubble IDs; the rasterized PNG differs from the source **inside** the bubble bbox and is **identical outside** it; the queue reports `COMPLETED`; `overall_progress` reaches `(1, 1)`.

Second E2E case: kill the worker mid-run (`isInterruptionRequested`), assert `paused`/`stopped` state and that the cache is resumable.

**Prerequisites (all Phase 0):** isolated `QSettings`, drained thread pool, tmp library fixture.

> `tests/test_ui.py` and `tests/test_ui_translation_workflow.py` are *widget-level integration* tests, not E2E: neither crosses the queue→worker→persistence→render chain.

### 6.3 Mutation testing

**Tool:** `mutmut 3.8.1` (verified available; `cosmic-ray 8.8.0` is the fallback).
**Why mutmut:** pytest-native, per-mutant diff output, and the suite is 5.6 s — fast enough to make thousands of runs tractable.

**Scope — deliberately narrow.** Do **not** mutation-test the whole tree; the survivor report would restate the test-gap list.

| Rank | Module | Rationale |
|---|---|---|
| 1 | `ports/` + `models/` (after Phases 2–5) | pure, deterministic, no I/O |
| 2 | `services/comic_text.py` (new) | pure math, real pixel oracle after Phase 5 |
| 3 | `services/scanner.py`, `folder_service.py` | pure fs logic, `tmp_path` oracle |
| 4 | `services/image_compression.py` | pure transform, assertable |
| 5 | `infra/json_workspace.py` | the atomic-write + language-resolution logic |
| 6 | `services/translation_client.py` pure parsers | `_parse_response`, `_extract_json_from_content` |
| **✗** | `translation_worker.py` | `QThread` + `time.sleep` (`:74`, `:405`) + `uuid4`; cost-per-finding is worst in repo |
| **✗** | `main_window.py` | 932 statements, 26 zero-test handlers, each mutant rebuilds a window |
| **✗** | `translation_overlay.py` | 104 `BinOp`; layout mutants are visually invisible and font-dependent |
| **✗** | `manga_ocr_detector.py` | ~100% survival by construction until §6.1 T11 lands |
| **✗** | `thumbnail_cache.py` | blocked on Phase 0 |

**Config** (`setup.cfg`, no `pyproject.toml` needed):

```ini
[mutmut]
paths_to_mutate=src/ports,src/models,src/services/scanner.py,src/services/folder_service.py,src/services/image_compression.py,src/services/comic_text.py,src/infra/json_workspace.py
runner=python -m pytest -x -q -p no:cacheprovider tests/
```

**Gate:** `mutmut results` → **≥ 80% killed** on the scoped set. Run **nightly**, not per-push (minutes, not seconds). Add `.github/workflows/mutation.yml` on `schedule:` + `workflow_dispatch`.

**Known unreliability factors to control:** `uuid4` (`translation_job.py:31`), wall-clock timestamps (`translation_workspace.py:35,93,105`), `QSettings` (`main_window.py:124`), `QThreadPool.globalInstance()` (`thumbnail_cache.py:66`), the 94 MB model asset (`onnx_bubble_detector.py:19-31`), order-dependent global writes (`test_ui.py:352-353`).

### 6.4 Test doubles (`tests/fakes/`)

| Fake | Satisfies | Replaces |
|---|---|---|
| `FakeTranslationProvider` | `TranslationProvider` | HTTP + protocol branching |
| `InMemoryPageRepository` | `PageRepository` | `temp/*.json` (deterministic, no disk) |
| `MemoryLogSink` | `LogSink` | `translation.log` |
| `FakeBubbleDetector` | internal seam of `MangaOcrDetector` | 94 MB ONNX inference |
| `FakeOcrEngine` | internal seam of `MangaOcrDetector` | `manga-ocr` model load |

After Phase 6, **no test may monkeypatch a collaborator's private attribute**. `grep -n 'MagicMock' tests/` must only appear against fakes.

---

## 7. Enforcement — Keeping ViewModels Thin and Preventing LLM Drift

> The evidence in §2.1 says rules failed on **placement**, not on **permission**. So enforcement needs three independent layers, because each fails differently.

### 7.1 Layer 1 — Mechanical gate (cannot be argued with)

| Gate | Catches | Where it runs |
|---|---|---|
| `import-linter` contracts (Phase 1) | Any dependency-direction violation | `tests/test_architecture.py` → existing `pytest` CI step |
| LOC ratchet (Phase 1) | "Just append to `MainWindow`" | same |
| `grep` guard: no `from src.ui` in `src/services` | The exact leak that already happened | same |
| `grep` guard: no `_private` attribute access across module boundaries | Leak B recurrence | same |
| `pytest-cov --cov-fail-under=85` on `models/ services/ ports/` | Untested new logic | same |
| `mutmut` ≥ 80% killed | Assertion-free tests | nightly workflow |

**Why a pytest wrapper and not a new CI step:** `.github/workflows/build.yml` runs `pytest` and nothing else before packaging. Putting the gate behind `pytest` makes it impossible to bypass without deleting a test file — which is itself a reviewable diff.

**Ratchet semantics:**

```python
CEILINGS = {"src/ui/main_window.py": 1580, "src/ui/queue_dialog.py": 750, ...}
# assert actual <= ceiling  AND  ceiling may only ever decrease
```

Seeded at today's size +5% so the gate is green **before** any refactoring; every phase in §5 lowers exactly one ceiling. Raising a ceiling requires editing a dict in a test file — visible, deliberate, reviewable.

### 7.2 Layer 2 — Interface shape makes the wrong thing hard

If a contributor wants to add a translation feature, the path of least resistance should already be the correct one:

- The VM already owns the queue and emits signals → **there is nothing to bolt onto `MainWindow`.**
- Every collaborator arrives by injection → **there is no `new` statement to add.**
- Every persistence need is a `PageRepository` verb → **there is no path to build.**
- `ui/` has no I/O helpers → **inventing one means importing something the gate forbids.**

This is the difference from today: currently `MainWindow` is the path of least resistance because it already holds `QSettings`, the queue, and a `ThumbnailCache`.

### 7.3 Layer 3 — Placement decision table (`.agents/rules/architecture_ports_adapters.md`)

The missing artifact. `trigger: always_on`.

| If the new code… | It goes in | Never in |
|---|---|---|
| Reads/writes a file, socket, or model | `infra/` behind a `ports/` Protocol | `ui/`, `services/` |
| Names a Qt class (`QThread`, `QWidget`, `QPixmap`, `QSettings`) | `infra/` or `ui/` | `services/`, `ports/`, `models/` |
| Contains orchestration/sequencing of injected collaborators | `services/` or a ViewModel | `ui/` |
| Is pure computation over data | `services/` | `infra/` |
| Is a plain data structure + serialization | `models/` | anywhere else |
| Is a new screen, dialog, widget, or signal wiring | `ui/` | — |
| Mutates UI state or holds a user-facing command | `viewmodels/` | `ui/` |
| Is used by exactly one module | stays **private** in that module | `ports/` |
| Would need a *second* implementation to be testable | `ports/` + two adapters | — |

Plus two hard invariants stated as prohibitions:

1. **`ui/` contains no `open()`, `Path.read_text`, `Path.write_text`, `Image.open`, `urllib`, or `requests`.**
2. **`services/` contains no import of `PyQt6.QtWidgets`, `src.infra`, `src.viewmodels`, or `src.ui`.**

Plus one **stop rule** for agents, mirroring `governance_and_workflow.md` §1.3:

> If a task cannot be placed using this table, **stop and ask**. Do not append to `main_window.py` to make progress.

### 7.4 Why three layers and not one

| Failure mode observed in this repo | Layer that catches it |
|---|---|
| New feature imported a widget into `services/` (`image_rasterizer.py:13`) | 1 (import-linter) |
| New handler appended to the biggest file (`main_window.py` → 1,511 LOC) | 1 (ratchet) |
| Agent reached into `_segment_bubble` instead of adding a verb | 1 (private-access guard) |
| Feature landed without tests (`_segment_bubble`, 126 unasserted `BinOp`) | 1 (coverage) + mutation |
| Agent did not know **where** to put it | 3 (decision table) |
| **Layer 1 and 3 can be satisfied while still producing a fat VM** | 2 + 7.5 below |

### 7.5 Keeping the ViewModels thin (the specific risk you asked about)

Ports & Adapters does not, by itself, keep ViewModels thin — a VM can become a new `MainWindow`. Four concrete rules, all mechanically checkable:

1. **LOC ceiling per VM (~250), in the same ratchet.** `viewmodels/*.py` added to `CEILINGS`.
2. **No filesystem, network, or Qt-widget symbol in `viewmodels/`.** Note this cannot be an `import-linter` `layers` rule alone — it needs an *external* forbidden contract (`PyQt6.QtWidgets`, `PyQt6.QtGui`) plus a `Path`/`open` grep. `QObject`/`pyqtSignal`/`QSettings` from `PyQt6.QtCore` are allowed.
3. **Signal-signature test:** each VM exposes ≤ N signals, each with primitive/`object` payloads — no widget in a signal. A test asserts every `pyqtSignal` arg type in `viewmodels/` is `{str, int, bool, object, list}`. This is what keeps a VM from smuggling UI types.
4. **The "no orchestration in a VM" test:** a VM method must not call more than one port per command. If it does, the sequencing belongs in `services/`. Enforced by review + a checklist item, since AST counting here would be brittle.

### 7.6 Enforcement rollout order (non-negotiable)

```
Phase 0: fixtures + crash fix      → oracle stable
Phase 1: import-linter + ratchet   → gate ON, green on today's code
Phase 2+: one phase = one ceiling lowered
```

Turning the gate on **after** refactoring is how the original drift happened: `governance_and_workflow.md` §4 was written as prose, so nothing verified it.

---

## 8. Impact on the Final Product

### 8.1 User-visible impact: none, by construction

| Surface | Impact |
|---|---|
| Keyboard shortcuts, navigation, rollover | unchanged — handlers move, key map does not |
| Overlay rendering | unchanged — the same `fit_comic_text` math, moved |
| Translation output, prompts, models | unchanged — provider split is transport-only |
| `QSettings` keys and values | unchanged — read/written through `SettingsViewModel` with identical keys |
| `temp/` on-disk schema | unchanged — same files, same JSON shape |
| Queue behaviour, retries, resume | unchanged — sequencing logic is moved, not rewritten |
| Startup time | unchanged (±one object construction) |
| Memory | unchanged |
| Thumbnail/preview latency | unchanged — `Protocol` is static-only, zero runtime cost; the cache keeps its own thread pool |
| `.exe` packaging | unchanged — `src` is already a package tree; PyInstaller's `--add-data assets` is untouched |

### 8.2 Engineering impact

| Dimension | Before | After |
|---|---|---|
| Files in `src/` | 31 | ~36 |
| Files touched by migration | — | ~24 of 31 |
| LOC relocated/refactored | — | ~2,700 / 7,535 (≈36%) |
| `main_window.py` | 1,511 LOC | ≤400 LOC |
| `TranslationWorkspace` public methods | 18 | 5 (port) |
| UI sites doing disk I/O | 6 | 0 |
| UI sites instantiating persistence | 12 | 0 |
| `services → ui` imports | 1 | 0 |
| `ui → service-private` accesses | 6 | 0 |
| Shared test fixtures | 0 | ~8 |
| Test doubles | 0 | 5 |
| Tests | 115 | ~160–170 |
| Architectural gate | none | 6 mechanisms |

### 8.3 Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Silent behaviour drift during `PageRepository` extraction | Medium | High — users lose cached chapters | Extract by **move, not rewrite**; keep `merge`/double-write semantics; parity test comparing old vs new output for a fixture chapter |
| `QThread` ownership moved into `infra/` breaks cancellation | Medium | High — hung app | Phase 6 keeps the thread object internal; cancellation test (T8) lands **before** the move |
| `import-linter` false positives on `infra ↔ services` | Medium | Low | Composition-root exception documented in `.importlinter`; refines in Phase 1 |
| LOC ratchet blocks a legitimate emergency fix | Low | Medium | Raising a ceiling is a one-line, deliberate edit — never a silent one |
| Mutation testing is slow / noisy | Medium | Low | Scoped module list + nightly cadence + explicit non-targets |
| Font/asset path resolution differs under PyInstaller | Low | Medium | `ComicTextRenderer` keeps the existing `sys._MEIPASS` lookup; add a frozen-path test |
| The window count in `test_ui.py` makes the E2E slow | Low | Low | `drain_threadpool` fixture from Phase 0 |

---

## 9. Dependencies & Blockers

**Hard ordering constraints**

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7 ──► Phase 8
   │                        │                                          │
   └─ E2E needs fixtures     └─ PageRepository is the port           └─ VM extraction needs
                                every later phase reuses                 injected collaborators
```

- Phase 2 must precede Phase 3 (the log is welded into the workspace, `:52,:115,:241`).
- Phase 4 and Phase 5 are independent of each other; either can be reordered.
- Phase 6 must precede Phase 7 (a VM cannot own a worker that builds its own collaborators).
- Mutation-testing gate (§6.3) can only be trusted **after** Phase 0.

**Blockers to resolve with the user**

| # | Blocker | Default if unanswered |
|---|---|---|
| B1 | Should the `save_translations` merge/double-write defect be fixed in-scope or deferred? | **Defer** — parity wins; file a follow-up issue |
| B2 | `pytest-cov --cov-fail-under=85` on a floor that does not exist yet — accept the number? | Accept; tune after Phase 2 |
| B3 | Ship Phases 0–2 as `v1.1.0`, or keep `v1.0.x` while internal-only? | `v1.1.0` at Phase 2 (first user-invisible structural release) |
| B4 | Mutation workflow: nightly `schedule:` in GitHub Actions (costs CI minutes)? | Yes, nightly + `workflow_dispatch` |

---

## 10. Verification Protocol

**Per phase (Phase 1 = *static check only*, per `two_phase_pre_commit.md` Phase 1):**

```bash
.venv/bin/python -m py_compile $(find src -name '*.py')
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/ -q
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_architecture.py -q
```

**Pre-commit gate (Phase 2 = user-directed only):**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/ -q
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/ --cov=src --cov-report=term-missing
```

**Phase 0 stability proof (must be run, not assumed):**

```bash
for i in $(seq 1 10); do QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/ -q -p no:cacheprovider >/tmp/run_$i.txt 2>&1; echo "$i exit=$?"; done
```

Expected: 10/10 `exit=0`. Baseline already measured today: 12/12 `exit=0`, 115 passed, 5.6 s.

**Architecture gate:**

```bash
.venv/bin/lint-imports
```

**Mutation gate (nightly):**

```bash
.venv/bin/mutmut run --use-coverage && .venv/bin/mutmut results
```

Expected: `killed / (killed + survived)` ≥ 0.80 on the scoped set.

**Final acceptance (Phase 8):**

- [ ] `main_window.py` ≤ 400 LOC and every ceiling lowered
- [ ] `lint-imports` green, plus 3 adversarial checks (reintroduce each leak → red)
- [ ] `pytest` ≥ 160 tests green, 10/10 stability
- [ ] Mutation score ≥ 0.80
- [ ] `README.md` + `governance_and_workflow.md` §4 + new rule file all updated
- [ ] Manual smoke: launch `.venv/bin/python src/main.py`, open a library, translate one chapter, rasterize, toggle overlay

---

## 11. Rollback

- Every phase is an independent commit series on a branch; `git revert` of a phase restores the previous shape with no migration state to unwind (no schema change, no data migration, no settings migration).
- The one phase that is *not* independently revertible is Phase 2 (`PageRepository`), because Phase 3+ build on it. Land Phase 2 as a single squashed commit so reverting is one operation.
- No on-disk artefact changes at any point — a rolled-back build still reads `temp/` written by a migrated build.

---

## 12. Open Questions for Round 3

Deferred because they depend on decisions above:

1. Exact signatures of the five port methods (needs B1 resolved).
2. The `ChapterStatus` dataclass shape — does it replace `is_translation_complete` + `get_translated_page_filenames` + `get_manual_labeled_page_filenames` in one call?
3. Whether `settings_viewmodel` should expose one typed `AppSettings` dataclass instead of 10 individual getters.
4. Whether `TranslationQueueManager` becomes a VM or stays a service with the VM wrapping it.
5. Split of `tests/test_ui.py` (729 LOC, 22 tests) once `MainWindow` shrinks.

---

## Appendix A — Skill-review trail

| Step | Tool / skill | Output |
|---|---|---|
| Relentless interview | `grill-me` → `grilling` | Round 1, 9 questions, all approved |
| Deep-module review | `improve-codebase-architecture` → `codebase-design` | HTML report: `/tmp/architecture-review-20261110.html` |
| Fresh-context walk | sub-agent, architecture lens | 11-section friction report; 3 rejected seams |
| Fresh-context audit | sub-agent, test lens | coverage matrix, mutation ranking, E2E verdict |
| Baseline measured | `.venv/bin/pytest` ×12 | 115 passed, 5.6 s, 12/12 exit 0 |

## Appendix B — Vocabulary used in this plan

**module** (not component/service) · **interface** (not API/signature) · **implementation** · **depth** · **deep** / **shallow** · **seam** (not boundary) · **adapter** · **leverage** · **locality**.

**Deletion test applied to:** `TranslationWorkspace` (N=9 src call sites → earns its keep, but 5 methods do not), `BubbleDetector` (1 adapter → hypothetical seam, dropped), `OcrEngine` (1 adapter → hypothetical seam, dropped).

**Two-adapter rule applied to:** `PageRepository` ✓, `TranslationProvider` ✓, `ComicTextRenderer` ✓, `LogSink` ✓, `BubbleDetector` ✗, `OcrEngine` ✗, `ThumbnailCache` callback ✗, `ImageRasterizer` bootstrap ✗.

---

## Appendix C — Layering nuance to resolve in Phase 1

The single linear `layers` contract in §5 Phase 1 is a **first cut, not the final contract**. It cannot express one legitimate dependency:

```
infra/qt_threads.py (TranslationWorker, a QThread)
        needs →  services/translation_sequence.py (the pure sequencing logic)
```

A linear `layers` chain places `infra` above `services` and would therefore flag that import as a violation — while the dependency is architecturally correct: the threading adapter must delegate to service logic, otherwise the sequencing would have to be duplicated into the adapter.

**Resolution (Phase 1 task, not a blocker):** replace the single chain with contracts that describe the real shape:

```ini
[importlinter:contract:services-are-headless]
type = forbidden
source_modules = src.services
forbidden_modules = src.infra, src.viewmodels, src.ui, PyQt6.QtWidgets

[importlinter:contract:models-are-pure]
type = forbidden
source_modules = src.models
forbidden_modules = src.infra, src.services, src.viewmodels, src.ui, PyQt6

[importlinter:contract:ui-never-touches-adapters]
type = forbidden
source_modules = src.ui
forbidden_modules = src.infra, PyQt6.QtWidgets.QApplication   # wiring lives in main.py

[importlinter:contract:ports-are-pure]
type = forbidden
source_modules = src.ports
forbidden_modules = src.infra, src.services, src.viewmodels, src.ui

[importlinter:contract:infra-implements-ports-only]
name = infra may depend on models + services + ports, nothing above
type = forbidden
source_modules = src.infra
forbidden_modules = src.viewmodels, src.ui
```

`main.py` is the composition root and is deliberately outside every contract; it is the only module allowed to import `infra` and `ui` together.

**Acceptance for this task:** the adversarial check in §5 Phase 1 must confirm that re-introducing each of the two real leaks (`services → ui` and `services → PyQt6.QtWidgets`) makes `lint-imports` fail. A gate that cannot fail is not a gate.

---

## Appendix D — Extraction of every change made by an LLM

> **Provenance caveat, stated up front.** `git log` authors every commit to `miftahulmuhaemen <miftahulmuhaemen@gmail.com>`. A trailer scan (`Co-authored-by|generated-by|claude|copilot|chatgpt|gpt-|codex|gemini|assisted|llm|ai-`) returns **zero** LLM-attribution trailers. The two hits it does return are the literal string `gemini-3.5-flash-lite` in commit *subjects*, which is the configured model name, not an authorship claim. So **attribution here is inferred from artifacts and telemetry, not declared.** Every inference below names the artifact it rests on.

### D.1 The inference chain

| Evidence | Value | Inference |
|---|---|---|
| `.agents/` tree exists | 5 rules, 4 workflows, 2 active plans | Repo is operated by an agent-rule harness |
| `.agents/` added in | `2be442a`, expanded in `4d02813` | Harness introduced after the initial commit |
| `.agent` symlink → `.agents` | present | Tooling expects a `.agent` dir |
| `.gitignore` §"Orca & Agent Workspace Artifacts" | `skills/` ignored | Agent runtime called **Orca**; workspace artifacts excluded from git |
| `skills/system/run-workflow/SKILL.md` | `run_workflow` orchestration primitive | Multi-agent fan-out was actually used |
| Rule docs written as **prohibitions addressed to an agent** | "The agent is STRICTLY PROHIBITED from…" | Rules are LLM guardrails, not human style docs |
| `2a07473` | `fix(test): use qtbot.waitUntil for async window state transitions on Windows` | A *test-only* fix for an async race — classic agent-generated flaky-test remediation |
| Commit granularity | 13 commits, 7 of them ≤10 files | Agent-sized changesets, not human feature batches |

**Conclusion:** commit history **cannot** be used as an LLM-attribution oracle for this repo. The second channel — the working tree — is far more informative.

### D.2 The finding that changes the plan's starting conditions

**`HEAD` is not the codebase I analysed.** The working tree is **4,432 insertions / 698 deletions across 28 tracked files** ahead of `HEAD`, plus **5 untracked paths**. `HEAD` (`4d02813`) is stale.

| Signal | `HEAD` (`4d02813`) | Working tree |
|---|---|---|
| `main_window.py` | 942 LOC | **1,497 LOC** |
| Uncommitted churn | — | **+4,432 / −698, 28 files** |
| `src/services/image_rasterizer.py` | *absent* | **present, 87 LOC, untracked** |
| `src/services/image_compression.py` | *absent* | **present, 51 LOC, untracked** |
| `tests/test_image_rasterizer.py` | *absent* | **present, untracked** |
| `tests/test_image_compression.py` | *absent* | **present, untracked** |
| `src/version.py` | `1.0.14` | `1.0.19` |

Everything in §1–§8 of this plan was measured against the **working tree**, so the plan's facts are correct. But note the shape of it: **`1e003f1` → `4d02813` added 905 + 2,594 = 3,499 `src` LOC on top of a 940-LOC app, and then a further ~1,500 LOC was added without a commit.**

### D.3 Product INSPECTION vs product EVIDENCE

This is the most consequential inferential boundary in the extraction, so it is stated explicitly rather than smuggled in.

**Product-INSPECTION set — code produced by an LLM and reviewed by a human. Treated as ground truth.**

Committed: `c96b553`, `e6cced6`, `2be442a`, `9550c9c`, `1e003f1`, `4d02813`. These carry agent-footprint artifacts in the *same* commits — `2be442a` adds `.agents/`; `4d02813` adds `.agents/plans/typography_overflow_fix.md` and `queue_page_selection.md`, plus the untracked-in-HEAD `image_rasterizer.py`.

**Product-EVIDENCE set — LLM agent output: machine-verified only (compiles, tests pass, artifacts generated), never human-reviewed, never committed.**

All 33 root-level items, plus 2 agent plan docs. Counts below are verified with `ls`/`find`, not estimated:

| Artifact class | Count | In working tree only | Example |
|---|---|---|---|
| `debug_*.png` dumps | **19** | yes | `debug_p3_narration_box_isolated.png`, `debug_crop_p1_b1.png` |
| Full-page render previews | **3** | yes | `preview_hybrid.png`, `preview_multimodal.png`, `preview_visual_hybrid.png` |
| `1_*` stage + review PNGs | **4** | yes | `1_whitened.png`, `1_translated.png`, `1_box_review.png`, `1_verified_deepseek.png` |
| Verified-bubble crops | **2** | yes | `crop_narration_verified.png`, `crop_top_right_verified.png` |
| Source sample pages | **3** | yes | `1.webp`, `11.webp`, `12.webp` |
| **Agent-written plan docs** | **2** | yes | `.agents/plans/typography_overflow_fix.md`, `queue_page_selection.md` |
| Verification JSON dumps | **2** | **ignored by `.gitignore`** | `ocr_results.json`, `translation_results.json` |
| **Total root-level artifacts** | **33 files** | yes | `ls *.png *.json *.webp \| sort -u \| wc -l` → 33 (31 images + 2 JSON) |

**The tell.** The deliverable names are `debug_crop_p1_b1.png`, `crop_narration_verified.png`, `debug_p3_narration_box_isolated.png` — an agent extracting specific bubble crops, inspecting them, naming the file after its own verification claim, then iterating. That is agent self-verification, and `4d02813`'s own message describes exactly this loop: *"robust OCR segmentation, and comic typography overlay"*.

**Corroborating tell:** `.gitignore` already contains `debug_*`, `*_review.*`, `*_whitened.*`, `*_translated.*`, `/(*.png|*.jpg|*.jpeg|*.webp)`, `*ocr_results*.json`, `*translation_results*.json`. The ignore rules are shaped around **this exact pattern class** — a `.gitignore` retrofitted after the fact to contain an agent's scratch output.

### D.4 Extracted change ledger

| # | Change | Commit | Set | Architectural effect |
|---|---|---|---|---|
| E1 | App scaffolding: `models/`, `services/`, `ui/`, `main.py` | `c96b553` | INSPECTION | Baseline 3-tier, ~95% compliant |
| E2 | README simplification | `e6cced6` | INSPECTION | none |
| E3 | Batch-rename, natural sort, app icon, perf | `2be442a` | INSPECTION | introduces `.agents/` harness; `main_window` 302→419 |
| E4 | Fullscreen state preservation | `9550c9c` | INSPECTION | `main_window` 419→428; **adds 54 test LOC vs 35 src** |
| E5 | CI scope change | `e742a94` | — | likely human; 3 deletions |
| E6 | `qtbot.waitUntil` async-test fix | `2a07473` | INSPECTION | removes a race rather than hiding it — good practice |
| E7 | Manga OCR + batch translation + zoom overlay | `1e003f1` | INSPECTION | **introduces leak A predecessor + `TranslationWorkspace`**; `main_window` 428→523 |
| E8 | Version bumps ×2 | `83acda7`, `bec4518` | — | mechanical |
| E9 | Gemini default + visible API-key field | `4902d48` | INSPECTION | +17 src / +14 tests |
| E10 | Log viewer + multimodal vision OCR | `a60d365` | INSPECTION | introduces `log_dialog.py`; `main_window` 523→545 |
| E11 | Auto-purge stale empty OCR cache | `ed44d78` | INSPECTION | cache-lifetime logic; +43 src / +30 tests |
| E12 | ONNX detection + segmentation + typography | `4d02813` | INSPECTION | **largest: 38 files, +3,982/−449**; adds `.agents/plans/`, ONNX detector, `translation_queue`, `image_rasterizer`, `manga_ocr_detector`; `main_window` 565→942 |
| E13 | Uncommitted translation rework | *none* | **EVIDENCE** | `main_window` 942→**1,497**; +10 new service methods; `local-substitution` manual-annotation flow |
| E14 | Untracked `image_compression.py` + tests | *none* | **EVIDENCE** | vision-path WebP downscale |
| E15 | Untracked `image_rasterizer.py` + tests | *none* | **EVIDENCE** | **the only `services → ui` import in the repo** |
| E16 | 33 root-level verification artifacts (31 images + 2 JSON) | *none* | **EVIDENCE** | agent self-verification trail |
| E17 | 2 agent plan docs | *none* | **EVIDENCE** | live plan_lifecycle usage |

### D.5 The drift curve — where the LLM actually cost us

`main_window.py` as a share of `src` LOC, per commit. The initial 302-LOC window was **32.1%** of a 940-LOC app and was considered acceptable. Watch the two jumps:

| Commit | `src` LOC | `main_window` | Share | Delta |
|---|---|---|---|---|
| `c96b553` | 940 | 302 | 32.1% | baseline |
| `2be442a` | 1,679 | 419 | 25.0% | **+117 LOC** in one commit |
| `1e003f1` | 2,613 | 523 | 20.0% | **+95 LOC** |
| `a60d365` | 2,925 | 545 | 18.6% | +22 |
| `ed44d78` | 2,965 | 565 | 19.1% | +20 |
| `4d02813` | 5,155 | 942 | 18.3% | **+377 LOC in one commit** |
| *working tree* | ~5,155+1,500 | **1,497** | ~29% | **+555 LOC, uncommitted** |

**Three observations that change the enforcement design:**

1. **The percentage was never the problem; the absolute was.** `main_window` *shrank* as a share (32.1% → 18.3%) while growing 302 → 942 LOC. A percentage-based rule would have flagged nothing. This is direct evidence for the plan's **absolute LOC ceiling with a ratchet** (§7.1) over any ratio-based heuristic.
2. **Drift is concentrated in two commits.** `2be442a` (+117) and `4d02813` (+377) account for **494 of the 640 committed LOC growth (77%)**. Both are large multi-feature commits. Enforcement aimed at *commit shape* (reject a single commit mixing a new tier, a new dependency, and a UI feature) would have caught 77% of it.
3. **The worst growth is uncommitted** (+555 LOC, E13). No commit gate of any kind can catch it — only a working-tree gate can. This is why §7.1 puts the architecture check **inside `pytest`**, not in a pre-commit hook or a CI-only step: pytest runs on the working tree.

### D.6 What the extraction proves about the "discipline" question

| Question you asked | Answer the extraction gives |
|---|---|
| Did agents write undisciplined code? | **No.** Every large commit carried tests: `c96b553` +440, `2be442a` +211, `1e003f1` +338, `4d02813` +787. Test-to-src ratio per feature commit: **27–58%**. |
| Did agents break the rules they were given? | **No.** They followed every rule that existed. Rules were written as prohibitions; no prohibition was violated in the original 940 LOC. |
| Then why did architecture degrade? | **The rules had no answer to placement.** Every violation entered through a new file (`translation_workspace.py`, `translation_overlay.py`, `image_rasterizer.py`) or a new handler appended to the largest existing file. Neither is a prohibition. |
| Did agents test their work? | **Yes, aggressively** — 33 verification artifacts in the working tree (19 `debug_*`, 3 `preview_*`, 4 `1_*` stages, 2 `crop_*_verified`, 3 source `.webp`, 2 JSON dumps). Verification was *visual and self-declared*, not asserted, which is why `_segment_bubble`'s 126 `BinOp` remain unasserted. |
| Is there a discipline problem to solve? | **No. There is a specification problem.** The plan's answer — a placement decision table (§7.3) plus an absolute LOC ratchet (§7.1) — targets the actual failure, not a misdiagnosed one. |

**Corollary for §6.3 mutation testing:** an agent that verifies by generating `crop_narration_verified.png` will produce code whose *assertions* are weak even when its *behaviour* is good. That is precisely the survivor profile mutation testing detects, and precisely why the mutation gate is not redundant with the 115 passing tests.

---

## Appendix E — Graphify (real CLI, verified)

### E.1 The tool — confirmed, not assumed

| Fact | Value |
|---|---|
| Binary | `graphify` -> `/home/sahana/.local/share/uv/tools/graphifyy/bin/graphify` |
| Version | **0.9.24** |
| Install method | `uv` tool (package name `graphifyy`) |
| Companion binary | `graphify-mcp` (MCP server; needs the `mcp` extra) |
| Config dir | `~/.graphify/` (not created yet) |
| Output dir | `graphify-out/` — **not yet present in this repo** |

> **Correction — the previous revision of this appendix is withdrawn.**
> It specified a hand-rolled `ast` parser at `tools/graphify.py` under an assumed interpretation A, because I could not find the tool. The CLI exists and does the job properly. **`tools/graphify.py` is never created, and every reference to it in Appendix F and §12 is void.**

### E.2 Commands this plan actually uses

| Command | Purpose here |
|---|---|
| `graphify extract <path>` | headless full extraction (AST + optional semantic LLM) for CI/scripts. Flags: `--mode deep`, `--force`, `--max-workers N`, `--token-budget N` |
| `graphify update <path>` | re-extract code files and update the graph, **no LLM needed**. `--force` to overwrite when the rebuild has fewer nodes; `--no-cluster` for raw extraction only |
| `graphify god-nodes --top N --json` | **most connected nodes = architectural hubs.** Implements the hub-ceiling gate |
| `graphify affected "X" --depth N` | reverse traversal: what is impacted if X changes |
| `graphify path "A" "B"` | shortest path between two nodes |
| `graphify query "<question>" --budget N` | BFS traversal of `graph.json` for a question |
| `graphify explain "X"` | plain-language explanation of a node and its neighbours |
| `graphify diagnose multigraph --json` | same-endpoint edge-collapse risk |
| `graphify hook install` / `hook status` / `hook uninstall` | post-commit + post-checkout git hooks |
| `graphify merge-driver <base> <current> <other>` | git merge driver: union-merge two `graph.json` files |
| `graphify install --platform agents` | copy the skill into the platform config dir |
| `graphify antigravity install` | write `.agents/rules` + `.agents/workflows` + skill |
| `graphify export callflow-html` | emit Mermaid-based architecture / call-flow HTML |
| `graphify cluster-only <path>` / `label <path>` | re-cluster and re-name communities; `--no-viz` for CI |

Artifacts: **`graphify-out/graph.json`** (the graph), **`graphify-out/graph.html`** (visualisation), plus `graphify-out/memory/` and `graphify-out/reflections/LESSONS.md` from the `save-result` / `reflect` feedback loop.

### E.3 Why the CLI beats the hand-rolled version

The hand-rolled generator would have produced one artifact and one gate. The CLI produces three things this plan needs at three different phases:

| Need | Hand-rolled | `graphify` |
|---|---|---|
| Frozen dependency baseline | yes | yes — `graph.json` |
| **Hub detection** | no | yes — `god-nodes` |
| **Impact analysis per phase** | no | yes — `affected` |
| New-package / new-tier detection | yes | yes |
| Cycle detection | yes | yes |
| Visual review surface | no | yes — `graph.html` |
| Agent-readable architecture context | partial | yes — `query` / `explain` / `path` |

**`god-nodes` is the important one.** The §7.1 LOC ratchet catches `main_window.py` growing by *lines*. `god-nodes` catches a module becoming a *hub* by **in-degree** — the structural signature of the actual defect — and it fires even when the file does not grow. The two gates measure different failure modes; neither subsumes the other.

**`affected` is the phase-level win.** Before each phase in §5, `graphify affected "<module>"` answers *"what breaks if I move this?"*, turning the strangler plan's risk assessment from a judgement call into a query.

### E.4 Revised gates

`tests/test_architecture_graph.py` shells the CLI — no custom parser:

| Assertion | How |
|---|---|
| Graph unchanged vs baseline | `graphify update . --force`, then diff `graphify-out/graph.json` against the committed copy |
| No cycles | inspect `graph.json`, or `graphify diagnose multigraph --json` |
| Hub ceilings hold | `graphify god-nodes --top 20 --json`; assert each node degree <= frozen ceiling |
| Every node in one of six tiers | node-path prefix check against `{models, ports, services, infra, viewmodels, ui}` |

`--force` is a **hard requirement of Phase 7**, not a nicety: a refactor that deletes code (`main_window` 1,497 -> 400 LOC) *shrinks* the graph, and without `--force` the tool refuses to overwrite the larger existing `graph.json`.

### E.5 Integration decisions

**E.5.1 — Commit `graphify-out/graph.json`; ignore the rest of `graphify-out/`.** The gate is a diff against a committed baseline, so the baseline must be tracked. Add to `.gitignore`:

```gitignore
# graphify: keep the baseline graph, ignore the heavy generated viz
graphify-out/*
!graphify-out/graph.json
```

`graph.html` is a build artifact. `graph.json` is the baseline.

**E.5.2 — The `docs/` ignore no longer blocks this — that blocker is withdrawn.** The previous revision needed a `!docs/architecture/` negation because the graph was going to live under `docs/`, which `.gitignore` excludes wholesale. Graphify writes to `graphify-out/` at the repo root instead, so no `docs/` change is required.

*Still worth flagging to whoever cleans the working tree:* `docs/` remains untracked, so `GLOSSARY.md` and `docs/adr/` do not exist on disk even though the `improve-codebase-architecture` skill expects them.

**E.5.3 — `graphify install --platform agents` must be verified before it runs.**

`graphify --help` lists `agents` among supported install platforms, and `antigravity install` is documented as writing to exactly `.agents/rules` + `.agents/workflows` — this repo's convention (5 rules, 4 workflows, all tracked).

The previous revision claimed `4d02813` added `.agents/`, which would suggest an install already happened. **A direct check contradicts that:** `git log --diff-filter=A -- .agents skills` returns `4d02813` and `2be442a`, but those two commits' numstat contains **no `.agents/` paths at all**. So that filter result is not evidence of authorship, and **how `.agents/` entered this repo is not established.**

Therefore: run `graphify hook status`, and inspect what `install` would write, **before** installing anything — so this plan cannot silently overwrite 9 hand-maintained governance files. Record the outcome either way.

**E.5.4 — Git hooks.** `graphify hook install` adds post-commit/post-checkout hooks so the graph rebuilds on checkout; otherwise a branch switch leaves a stale baseline and the gate fails spuriously. `graphify merge-driver` union-merges two `graph.json` files so concurrent branches do not produce an unmergeable baseline.

Caveat: this repo had no git hooks before, and `governance_and_workflow.md` §2.3 requires tracked, cleanly-terminated subprocesses. **Install hooks only after the working tree is committed (B5)**, so the first hook run has a stable baseline.

**E.5.5 — Do not use `--mode deep`.** `extract --mode deep` and `label` require a configured LLM backend (auto-detected from API keys). AST-only extraction is deterministic, needs no key, and makes no network calls — which keeps the gate honest under `data_integrity_and_verification.md` §3.1 (offline-first) and avoids burning tokens on every commit. Semantic enrichment can be a separate, manual, opt-in run.

### E.6 Phase placement

Graphify lands in **Phase 1**, in the **same commit** as `.importlinter` and `tests/test_architecture.py` — one gate, one commit — and **before Phase 2**, so each later phase lowers a ceiling in the same commit as its refactor.

Revised Phase 1 task list:

- [ ] `graphify extract .` (AST only — **no** `--mode deep`) -> `graphify-out/graph.json`
- [ ] Commit `graphify-out/graph.json` as the frozen pre-migration baseline; gitignore `graphify-out/*` except it
- [ ] `tests/test_architecture_graph.py` asserting baseline-equality, no cycles, hub ceilings via `graphify god-nodes --json`, tier membership
- [ ] `graphify hook status`; inspect what `graphify install --platform agents` would write; decide (E.5.3)
- [ ] `graphify hook install` **only after** B5 is resolved
- [ ] Capture pre-migration `graphify god-nodes --top 20 --json` as the hub-ceiling source
- [ ] Confirm `tools/graphify.py` is absent — it is never created (E.1)

---

## Appendix F — Amendments to §5 and §9

> Superseding edits from the extraction (Appendix D) and Graphify (Appendix E). Apply these to §5 Phase 0/1 and §9 when the plan is committed to the repo.

### F.1 Phase 0 gains three prerequisites

**F.1.1 — Commit the working tree first. This is a hard prerequisite.**

The extraction found that `HEAD` (`4d02813`) is **stale by 4,432 insertions / 698 deletions across 28 files**, with 5 untracked paths including `image_rasterizer.py` (the repo's only `services → ui` import) and `image_compression.py`. Migration cannot start from an uncommitted tree: the strangler strategy needs a commit boundary to revert to, and §11 Rollback is meaningless without one.

```bash
# Verification of the claim, before any decision:
git --no-pager diff HEAD --stat -- src tests | tail -1   # 28 files changed, 4432 insertions(+), 698 deletions(-)
git status --porcelain | grep '^??'                       # 5 untracked paths
```

**F.1.2 — Purge the agent verification artifacts (31 images + 2 JSON dumps = 33 files).**

`codebase_hygiene_and_runtime.md` §2.2 already requires this and these have survived uncommitted since 2026-11-07. Paths:

```
debug_*.png (19)   1_box_review.png   1_translated.png   1_whitened.png
1_verified_deepseek.png   crop_narration_verified.png   crop_top_right_verified.png
preview_hybrid.png  preview_multimodal.png  preview_visual_hybrid.png
1.webp  11.webp  12.webp                      # source sample pages
ocr_results.json    translation_results.json
```

These are **evidence, not product** (Appendix D.3). Preserve any you still need outside the repo, then delete. They are all `.gitignore`d, which is why no rule ever caught them — an untracked file is invisible to every gate in §7.

**F.1.3 — ~~Resolve the `docs/` ignore.~~ WITHDRAWN.** Graphify writes to `graphify-out/` at the repo root, not under `docs/`, so the `docs/` exclusion no longer blocks the graph gate (E.5.2). The untracked `docs/` tree is still worth noting to the working-tree cleanup agent, but this plan no longer depends on it.

### F.2 Phase 1 gains the Graphify tasks

Per Appendix E.6, using the real CLI (**not** a hand-rolled generator):

- [ ] `graphify extract .` (AST only, **no** `--mode deep`) -> commit `graphify-out/graph.json` as the frozen baseline
- [ ] `tests/test_architecture_graph.py` — baseline-equality, no cycles, `god-nodes` hub ceilings, tier membership
- [ ] `.gitignore`: `graphify-out/*` with `!graphify-out/graph.json`
- [ ] `graphify hook status`, then decide on `install --platform agents` / `hook install` (E.5.3, E.5.4)

All land **in the same commit** as `.importlinter` and `tests/test_architecture.py` — one gate, one commit.

### F.3 §7 gains a seventh gate

| Gate | Catches | Where it runs |
|---|---|---|
| Graph drift (`tests/test_architecture_graph.py`) | A new tier appearing; a module becoming a hub; fan-out growth; cycles; any undeclared structural change | existing `pytest` step |

### F.4 §6.2 E2E gains a baseline note

The E2E test described in §6.2 must be written against the **committed** tree (F.1.1), not the working tree, or its expected `temp/*.json` values will not correspond to any reproducible state.

### F.5 §9 blockers — three added

| # | Blocker | Default if unanswered |
|---|---|---|
| **B5** | `HEAD` is stale by +4,432/-698 across 28 files and 5 untracked paths. Commit before migrating? | **OWNED ELSEWHERE (2026-11-10).** You are delegating working-tree cleanup to a separate agent. This plan does **not** own the cleanup; it only *requires* B5 closed before Phase 0 starts. Entry gate: `git status --porcelain -- src tests` clean, 33 root artifacts purged, `image_rasterizer.py` + `image_compression.py` committed or deleted |
| **B6** | 33 root artifacts (31 images + 2 JSON) to delete — 19 `debug_*`, 3 `preview_*`, 4 `1_*`, 2 `crop_*_verified`, 3 `.webp`, 2 JSON. Delete now, or archive outside the repo first? | **Archive to `/tmp/wft-artifacts/` then delete** — they are agent evidence, not product |
| **B7** | ~~Which Graphify interpretation?~~ **RESOLVED 2026-11-10.** The CLI is `graphify` v0.9.24 at `~/.local/bin/graphify`; Appendix E rewritten against its real interface | Closed — no action needed |

### F.6 §12 open questions — one resolved, one added

- **Resolved:** "whether `main_window.py` can be split incrementally" — yes; the drift curve (D.5) shows growth arrives in two large jumps plus one uncommitted jump, so the split can follow those three seams rather than 45 handlers.
- **Added:** should the §7.1 LOC ratchet derive per-tier LOC from `graphify-out/graph.json` instead of a hand-maintained dict? (Removes one place to edit, but couples two gates — a graph regeneration and a ceiling bump would become the same operation.)

---

---

## Appendix G — Plan status after this revision

| § | State |
|---|---|
| 1–8 | **Unchanged facts**, measured on the working tree |
| 9 | B5 reclassified as **owned by the cleanup agent**; B6 unchanged; **B7 closed** (CLI verified) |
| 5 Phase 0 | entry gate added (B5); Graphify baseline task added; `graphify --version` check added |
| 5 Phase 1 | Graphify drift gate + `hook install` + adversarial 7th-package check added |
| 7 | 7th gate added — Graphify drift (`tests/test_architecture_graph.py`) |
| D | **New** — LLM change extraction re-run |
| E | **Rewritten against the real CLI** (was: assumed interpretation A) |
| F | **New** — amendments |
| H | **New** — execution order (which plan, which step) |

**Counts:** 1,149 lines · 84 tasks · 44 code fences (balanced) · 33 sections.

**Status:** `[-]` AWAITING APPROVAL. Nothing in this revision executed: no file in the repository was created, modified, or deleted. The only artefact produced by this planning session is this document.

**Resolved this revision:** B7 (Graphify identified as `graphify` v0.9.24, CLI verified, Appendix E rewritten against its real interface). **Transferred:** B5 (working-tree cleanup to a separate agent; remains a hard entry gate on Phase 0). **Withdrawn:** the `docs/` ignore blocker (E.5.2) and `tools/graphify.py` (E.1).

---

## Appendix H — Which plan to execute, and in what order

> Added 2026-11-10 in response to "Update the plan and point me which plan that need to be executed."

### H.1 There are three plans on disk. Only one is this one.

| Plan file | Status | Owner | Action |
|---|---|---|---|
| `.agents/plans/ports-and-adapters-migration.md` | **`[-]` AWAITING APPROVAL** — this document | you + me | **Execute, after approval.** 9 phases, 84 tasks |
| `.agents/plans/queue_page_selection.md` | 6,707 bytes, dated 2026-11-09 | prior agent session | **Read, then prune.** `plan_lifecycle.md` §4.3 says completed plans are deleted immediately. Verify it is complete, then delete per active-only governance |
| `.agents/plans/typography_overflow_fix.md` | 4,422 bytes, dated 2026-11-09 | prior agent session | **Read, then prune.** Same rule |

**Neither of the other two is an input to this migration.** They are leftovers from the uncommitted LLM session (Appendix D, set EVIDENCE), and their subject matter — queue page selection, typography overflow — is already shipped in the uncommitted working tree. Read them only to confirm they are done, then remove them, or this plan's Phase 0 entry gate will inherit their ambiguity.

### H.2 Execution order

```
  ┌──────────────────────────────────────────────────────────────┐
  │ STEP 0  — CLEANUP AGENT  (separate session, NOT this plan)    │
  │  · resolve B5: commit the working tree (+4,432/-698, 28 files)│
  │  · purge 33 root artifacts                                    │
  │  · decide image_rasterizer.py / image_compression.py          │
  │  · prune the 2 stale plan files (H.1)                         │
  │  EXIT GATE: git status --porcelain -- src tests  ==  EMPTY    │
  └───────────────────────────┬──────────────────────────────────┘
                              │  B5 must be GREEN before anything below
                              v
  ┌──────────────────────────────────────────────────────────────┐
  │ STEP 1  — THIS PLAN, PHASE 0   (test foundations + crash fix) │
  │  · conftest.py (5 fixtures) · ThumbnailCache.shutdown()       │
  │  · purge dead code · requirements-dev.txt                     │
  │  · graphify extract . -> commit graph.json baseline           │
  │  EXIT GATE: 30/30 sequential pytest runs exit 0               │
  └───────────────────────────┬──────────────────────────────────┘
                              v
  ┌──────────────────────────────────────────────────────────────┐
  │ STEP 2  — THIS PLAN, PHASE 1   (turn the gate ON, green)      │
  │  · src/{ports,infra,viewmodels}/ skeleton                     │
  │  · .importlinter (5 forbidden contracts, Appendix C)          │
  │  · tests/test_architecture.py · LOC ratchet                   │
  │  · tests/test_architecture_graph.py · graphify hook install   │
  │  EXIT GATE: pytest green AND 3 adversarial checks go RED      │
  └───────────────────────────┬──────────────────────────────────┘
                              v
  ┌──────────────────────────────────────────────────────────────┐
  │ STEP 3  — THIS PLAN, PHASES 2..8  (strangler migration)       │
  │  2 PageRepository -> 3 LogSink -> 4 TranslationProvider       │
  │  -> 5 ComicTextRenderer -> 6 worker DI -> 7 ViewModels        │
  │  -> 8 preview domain + docs                                   │
  │  ONE PHASE PER COMMIT, lowering exactly one ceiling each time │
  │  EXIT GATE: main_window <= 400 LOC, mutation >= 80%           │
  └──────────────────────────────────────────────────────────────┘
```

### H.3 Why Step 0 cannot be this plan

Rollback (§11) is per-phase `git revert`. On an uncommitted tree there is **nothing to revert to** — `HEAD` (`4d02813`) is 4,432 insertions behind reality, and it does not even contain `image_rasterizer.py`. Committing is not bookkeeping here; it is the precondition that makes every later phase reversible. That is why B5 is an **entry gate on Phase 0**, not a task inside it.

### H.4 The single next action

**Approve this plan, then start the cleanup agent.** Concretely:

1. Reply **approved** (or name what to change).
2. Start the separate agent and hand it **§9 B5** plus **Appendix F.1** — those two sections are the complete specification of the cleanup, including the entry gate text and the exact 33 artifact classes.
3. When the cleanup agent reports `git status --porcelain -- src tests` empty, Phase 0 begins.

**Nothing in this plan executes before step 3.** No source file has been modified by this planning session — the only artefact created is this document.
