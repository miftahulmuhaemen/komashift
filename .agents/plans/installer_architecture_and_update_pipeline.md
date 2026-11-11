# Implementation Plan: KomaShift Modular Installer & Update Pipeline

**Status:** Draft / Pending User Approval  
**Created:** 2026-11-11  
**Goal:** Transition KomaShift from a monolithic, slow-launching 290 MB `--onefile` executable to an Inno Setup-based modular installer architecture (~50–60 MB initial download) with sub-second launch times, on-demand AI package streaming, and seamless automated GitHub Release updates.

---

## 1. Architecture Overview

### Current State vs. Target State

| Dimension | Current Monolithic Executable | Target Modular Installer Architecture |
|---|---|---|
| **Packaging Mode** | PyInstaller `--onefile` (290 MB compressed) | PyInstaller `--onedir` bundled into Inno Setup Setup.exe (~55 MB) |
| **Startup Latency** | 1 to 3+ minutes (unpacks 775 MB to `%TEMP%` every run) | **< 1.0 second** (files already unpacked in Program Files/AppData) |
| **Initial Download Size** | 290 MB per release | **~50–60 MB** (Core app + UI + Pillow + OpenCV headless) |
| **Heavy AI Footprint** | Bundled unconditionally (ComicText ONNX 57MB, unidic 45MB) | Streamed on-demand or selected as optional install component |
| **Update Mechanism** | Redownload full 290 MB `.exe` every time | In-app check against GitHub Releases API + one-click silent patcher |

---

## 2. Technical Design

### A. Packaging & Build Pipeline (`--onedir` + Deadweight Pruning)
In `build.py`, change from `--onefile` to `--onedir`:
1. **Output Structure:** `dist/KomaShift/` containing `KomaShift.exe` and a clean `_internal/` directory.
2. **Exclusions in PyInstaller:**
   - `--exclude-module=botocore` & `--exclude-module=boto3` (saves 17 MB raw)
   - `--exclude-module=PyQt6.QtPdf` & `--exclude-module=PyQt6.QtQml` (saves 20 MB raw)
   - Exclude `cv2/opencv_videoio_ffmpeg*.dll` (saves 29.5 MB raw)
   - Exclude `PyQt6/Qt6/bin/opengl32sw.dll` (saves 19.7 MB raw)
3. **Core vs. AI Separation:**
   - **Core Bundle:** Python runtime, PyQt6, Pillow, OpenCV headless, KomaShift code.
   - **AI Package (`assets/models/` + `unidic_lite`):** Packaged into a standalone `.tar.zst` or `.7z` archive (~70 MB compressed) hosted as a separate GitHub Release asset: `komashift-ai-models-v1.zip`.

### B. Windows Installer (Inno Setup)
We generate an Inno Setup script (`installer/komashift_setup.iss`):
1. **Per-User Installation (Zero UAC Prompt / No Admin Required):**
   - Installs to `{localappdata}\Programs\KomaShift` (`C:\Users\<User>\AppData\Local\Programs\KomaShift`).
   - Writes start menu shortcut and optional desktop icon.
2. **Components Selection Screen:**
   - `[x] KomaShift Core Application` (Mandatory, ~130 MB installed).
   - `[x] Offline Manga OCR & Bubble Detection` (Optional, downloads `komashift-ai-models-v1.zip` via Inno Setup Downloader if checked).
3. **Registry & Uninstall:**
   - Clean Windows Add/Remove Programs integration.
   - Preserves user settings in `HKCU\Software\KomaShift\KomaShift` on uninstall/upgrade unless user explicitly selects "Wipe user settings".

### C. Clean In-App Update Architecture (GitHub Releases)
How updates work for the user:

```
[User Launches KomaShift]
          │
          ▼
Background QThread checks GitHub API:
GET https://api.github.com/repos/<owner>/<repo>/releases/latest
          │
          ├── No update ──► Continues silently (no popups)
          │
          └── New version available (e.g. v1.1.0 > v1.0.24)
                    │
                    ▼
          Subtle banner/indicator in Top Bar / Status Bar:
          "Update v1.1.0 available [View Changes] [Install Update]"
                    │
                    ▼
          User clicks [Install Update]
                    │
                    ▼
          KomaShift downloads "KomaShift-Patch-v1.1.0.exe" or "KomaShift-Setup.exe" 
          to %TEMP% with download progress bar in UI
                    │
                    ▼
          Spawns updater with /SILENT flag, closes KomaShift, 
          replaces modified binaries, and relaunches KomaShift!
```

1. **GitHub Releases as Backend:**
   - Releases store two artifacts:
     1. `KomaShift-Setup-vX.X.X.exe` (~55 MB full installer).
     2. `manifest.json` containing version, changelog summary, and SHA256 checksums.
2. **Why this is completely hassle-free:**
   - Users don't need to manually visit GitHub, navigate assets, or download `.zip` files.
   - If they are offline or disable updates, the app works normally.
   - The installer automatically detects existing installation path and updates in-place in 2 seconds.

---

## 3. Step-by-Step Task Breakdown

- [x] **Task 1: Optimize Build Pipeline to `--onedir` & Apply Excludes**
  - Update `build.py` to support building `--onedir` distribution directory.
  - Add explicit exclusions for `botocore`, `boto3`, OpenCV video ffmpeg, and Qt software OpenGL/PDF.
  - Support packaging mode selection (`--onedir` / `--onefile`).

- [x] **Task 2: Implement On-Demand AI Asset Manager**
  - Create `src/services/ai_assets_manager.py` with port/adapter design.
  - Check if `assets/models/comic-text-detector.onnx` and `manga-ocr` weights are present.
  - Provide fallback to user cache directory `~/.cache/komashift/models` and automatic on-demand streaming.
  - Verify seamless offline operation once downloaded.

- [x] **Task 3: Inno Setup Script Creation**
  - Create `installer/komashift_setup.iss` with Inno Setup modern UI styling.
  - Configure `{localappdata}` target (`lowest` privileges, no admin needed), desktop/start menu shortcuts, and uninstaller.
  - Configure LZMA2 ultra compression for maximum compression ratio.

- [x] **Task 4: Implement In-App Update Checker & Updater Service**
  - Create `src/services/update_checker.py` to query GitHub Releases API asynchronously on app launch.
  - Hook background update notifier in `src/ui/main_window.py` via `SettingsViewModel`.
  - Validate semver comparison and asset identification.

- [x] **Task 5: End-to-End Testing & Verification**
  - Run headless pytest suite (`QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/`).
  - Passed 100% across all 149 unit, UI, and architectural ratchet tests.

---

## 4. Verification Protocol

1. **Startup Latency Benchmark**:
   - Compare startup time: Current `.exe` (~90s on cold start) vs. `--onedir` installed binary (< 1.0s).
2. **Download Footprint Benchmark**:
   - Measure `KomaShift-Setup.exe` size: target $\le 60 \text{ MB}$.
3. **Automated Testing**:
   - `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/` must pass 100% across all 145+ tests.
