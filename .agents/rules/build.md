# Build & Compilation Instructions (.exe)

## Mandatory Target: Windows .exe Only
This repository is a **Windows desktop application**. All builds must target **Windows** and produce a single standalone **`.exe`** binary in `dist/FolderImagePreviewer_v<version>.exe`.
- **NEVER** build or deliver a Linux ELF binary.
- **NEVER** run PyInstaller under the Linux Python environment.
- **NEVER** tell the user they need to run build on Windows or wait for GitHub Actions. The Windows build tools are accessible directly from this shell.
- **NEVER run the build automatically, proactively, or as part of verification.** Building takes several minutes and must ONLY be executed when the user gives an explicit command (e.g. "build", "build it", "compile", "make exe").

---

## How to Build (Zero Investigation Required)
Execute the build command ONLY when the user explicitly requests it (e.g. "build", "build it", "compile", "make exe"). Never trigger it autonomously.
Execution without `--explicit-user-request` is physically blocked by a mechanical guard in `build.py`:

```bash
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command "Set-Location '\\\\wsl.localhost\\Ubuntu\\home\\sahana\\Code_Repository\\personal\\win-folder-thumbnail'; python build.py --explicit-user-request" < /dev/null
```

### Critical Rules for Execution:
1. **Full PowerShell Path**: Do NOT call bare `powershell.exe`; it is not in Linux `$PATH`. Always use the absolute path `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`.
2. **Redirect Stdin (`< /dev/null`)**: Always append `< /dev/null` at the end to prevent PowerShell from hanging waiting on input.
3. **UNC Path**: The project is accessed from Windows via `\\wsl.localhost\Ubuntu\home\sahana\Code_Repository\personal\win-folder-thumbnail`.
4. **Pre-configured Windows Environment**: The Windows Python environment (`hermes-agent\venv` / Python 3.11) already has PyInstaller, PyQt6, ONNX Runtime, manga-ocr, unidic-lite, and transformers installed. Do not attempt to reinstall or check dependencies.
5. **Automatic Version Bumping**: `build.py` automatically increments `PATCH` and `BUILD` in `src/version.py`, runs PyInstaller with `--onefile --windowed`, and outputs `dist/FolderImagePreviewer_v<version>.exe`.

---

## Post-Build Verification
After the background build task finishes:
1. Verify the `.exe` exists:
   ```bash
   ls -lh dist/FolderImagePreviewer_v*.exe
   ```
2. Confirm the exact file size (~285MB–295MB) and version to the user with a clickable link: `dist/FolderImagePreviewer_v<version>.exe`.
