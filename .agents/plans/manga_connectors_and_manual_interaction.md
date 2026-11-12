# Implementation Plan: Universal Manga Connectors & Manual Website Interaction

**Plan file:** `.agents/plans/manga_connectors_and_manual_interaction.md`  
**Drafted:** 2026-11-12  
**Status:** `[-]` Awaiting User Approval (plan_lifecycle.md Step 2)  
**Priority:** High / Feature Expansion  

---

## 1. Goal & Scope

### Goal
Implement a modular, extensible **Universal Manga Connector System** inspired by HakuNeko's architecture, enabling KomaShift users to search, browse, and download manga chapters directly into their local library from online sources. Include HakuNeko's signature **Manual Website Interaction** pattern to allow users to handle bot challenges (Cloudflare Turnstile, CAPTCHAs, or account logins) directly in an interactive browser window without breaking automated background downloads.

### In Scope
1. **Ports & Adapters Hierarchy**:
   - `src/models/connector_item.py`: Dataclasses for `MangaInfo`, `ChapterInfo`, `PageMedia`, and `DownloadTask`.
   - `src/ports/connector.py`: Pure `typing.Protocol` defining the `MangaConnector` contract.
   - `src/services/connector_registry.py`: Headless catalog of registered scrapers/connectors.
   - `src/services/manga_download_service.py`: Headless chapter downloader with rate-limiting, progress calculation, and disk persistence matching KomaShift folder structures.
   - `src/infra/connectors/`: Concrete connector adapters (e.g. MangaDex API, plus generic HTML/CSS scraper base).
   - `src/infra/cookie_jar_store.py`: Persistent session cookie storage per connector domain.
   - `src/infra/download_worker.py`: Background `QThread` workers for asynchronous queries and chapter downloads.
   - `src/viewmodels/connector_viewmodel.py`: Headless ViewModel managing search state, chapter checklists, and manual interaction signals.
   - `src/ui/connector_dialog.py`: Dark-themed modal dialog for searching manga, viewing chapters, and queuing downloads.
   - `src/ui/manual_interaction_dialog.py`: Interactive web view for user-solved Cloudflare/CAPTCHA challenges and login sessions.
2. **HakuNeko Team Attribution**:
   - Explicitly credit Ronny, mranest, and the HakuNeko open-source community across documentation, code headers, and UI dialogs.

### Explicit Non-Goals
- Autonomous CAPTCHA or bot solving: The system strictly delegates anti-bot challenges to the human user via visible interactive UI, honoring security and behavioral guardrails.
- Altering existing OCR, translation algorithms, or prompt pipelines.
- Direct disk writes inside UI widgets: All downloads and cookie caches route through `src/services/` and `src/infra/`.

### Acceptance Criteria
- [ ] Connectors implement pure `typing.Protocol` without UI or PyQt6 dependencies in `src/ports/`.
- [ ] Multiple connectors can register dynamically into `ConnectorRegistry`.
- [ ] Manual Website Interaction launches an interactive window to capture cookies upon Cloudflare/CAPTCHA detection or manual request.
- [ ] Downloaded chapters seamlessly index into KomaShift's library and are immediately readable and translatable.
- [ ] Headless test suite (`QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`) passes 100% with dedicated unit and architecture tests.

---

## 2. Technical Design & Architecture

### Six-Tier Hexagonal Package Distribution

```
src/ui/connector_dialog.py, manual_interaction_dialog.py
         ↓
src/viewmodels/connector_viewmodel.py
         ↓
src/services/connector_registry.py, manga_download_service.py
         ↓
src/ports/connector.py, browser_session_provider.py
    ↑                ↑
src/models/          src/infra/connectors/, cookie_jar_store.py, download_worker.py
```

### A. Models (`src/models/connector_item.py`)
```python
@dataclass(frozen=True)
class MangaInfo:
    id: str
    title: str
    connector_id: str
    cover_url: str = ""
    description: str = ""

@dataclass(frozen=True)
class ChapterInfo:
    id: str
    manga_id: str
    connector_id: str
    title: str
    chapter_number: str = ""
    language: str = "ja"

@dataclass(frozen=True)
class PageMedia:
    index: int
    url: str
    headers: dict[str, str] = field(default_factory=dict)
```

### B. Ports (`src/ports/connector.py`)
```python
class MangaConnector(Protocol):
    id: str
    label: str
    base_url: str

    def search(self, query: str, session: requests.Session) -> list[MangaInfo]: ...
    def get_chapters(self, manga: MangaInfo, session: requests.Session) -> list[ChapterInfo]: ...
    def get_pages(self, chapter: ChapterInfo, session: requests.Session) -> list[PageMedia]: ...
```

### C. Manual Website Interaction (Inspired by HakuNeko)
1. **Trigger Condition**:
   - Explicit: User clicks the globe / interaction icon next to a connector in the UI.
   - Reactive: Connector catches HTTP 403, Cloudflare challenge signatures, or CAPTCHA blocks.
2. **Resolution Workflow**:
   - `ConnectorViewModel` emits `manual_interaction_requested(url: str, connector_id: str)`.
   - `ManualInteractionDialog` opens displaying the target website in an embedded web engine.
   - User solves the challenge or completes login.
   - On dialog close, extracted cookies and User-Agent are persisted by `CookieJarStore` and applied to the connector's HTTP session.
   - Pending download or query is automatically resumed.

### D. Credits & Attribution
- Attribution displayed in `src/ui/connector_dialog.py`:
  > *"Manga connector architecture and manual website interaction workflow adapted from HakuNeko (https://github.com/manga-download/hakuneko) created by Ronny, mranest, and the HakuNeko open-source team."*
- Documented in `README.md` and source docstrings.

---

## 3. Step-by-Step Task Breakdown

- [ ] **Task 1: Define Connector Models & Protocols**
  - Create `src/models/connector_item.py` (`MangaInfo`, `ChapterInfo`, `PageMedia`, `DownloadTask`).
  - Create `src/ports/connector.py` (`MangaConnector`, `BrowserSessionProvider`).
  - Unit tests in `tests/test_connector_models.py`.

- [ ] **Task 2: Implement Headless Connector Registry & Download Service**
  - Create `src/services/connector_registry.py` with registration and lookup capabilities.
  - Create `src/services/manga_download_service.py` to handle chunked page downloads, image verification, and folder creation in the user's library.
  - Unit tests in `tests/test_connector_services.py`.

- [ ] **Task 3: Implement Core Connector Adapters & Cookie Storage**
  - Create `src/infra/cookie_jar_store.py` for persistent session cookies per domain.
  - Create `src/infra/connectors/mangadex_connector.py` (REST API).
  - Create `src/infra/connectors/base_html_connector.py` (declarative HTML scraper base).
  - Unit tests in `tests/test_connectors.py` (with mocked HTTP fixtures).

- [ ] **Task 4: Implement Asynchronous Workers & Headless ViewModel**
  - Create `src/infra/connector_workers.py` (`ConnectorSearchWorker`, `ChapterFetchWorker`, `PageDownloadWorker`).
  - Create `src/viewmodels/connector_viewmodel.py` with signals for search results, progress, and manual interaction prompts.
  - Unit tests in `tests/test_connector_viewmodel.py`.

- [ ] **Task 5: Implement UI Dialogs & Manual Interaction Window**
  - Create `src/ui/manual_interaction_dialog.py` for user challenge completion.
  - Create `src/ui/connector_dialog.py` with dark palette, source selector, search bar, chapter checklist, and queue integration.
  - Add "Browse / Download Manga..." action to `src/ui/main_window.py` toolbar and menu bar.
  - UI tests in `tests/test_connector_dialog.py`.

- [ ] **Task 6: Documentation & Team Attribution**
  - Update `README.md` with new acquisition features and attribution to HakuNeko team.
  - Verify architecture conformance via `tests/test_architecture.py`.

---

## 4. Verification Protocol

1. **Architecture & Lint Invariants**:
   - `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_architecture.py`
   - `.venv/bin/python -m py_compile src/**/*.py`
2. **Unit & Integration Suite**:
   - `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_connector_*.py tests/test_connectors.py`
   - Full test suite: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`
3. **End-to-End Ingestion Validation**:
   - Verify that downloading a chapter saves into `<library_root>/<manga_title>/<chapter_title>/` and immediately shows up in KomaShift's folder list.
