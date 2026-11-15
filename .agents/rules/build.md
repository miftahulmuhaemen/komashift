# Build & Compilation Instructions (Windows Installer)

## Mandatory Target: Windows Setup Installer Only
This repository is a **Windows desktop application**. All "build" commands MUST target **Windows** and produce the **Inno Setup Installer** binary in `dist/KomaShift-Setup-v<version>.exe`.
- **"build" ALWAYS means building the Windows Setup Installer (`KomaShift-Setup-v<version>.exe`)**. It NEVER means a standalone portable single-file `.exe`.
- **NEVER** build or deliver a Linux ELF binary.
- **NEVER** run PyInstaller under the Linux Python environment.
- **NEVER** tell the user they need to run build on Windows or wait for GitHub Actions. The Windows build tools are accessible directly from this shell.
- **NEVER run the build automatically, proactively, or as part of verification.** Building takes several minutes and must ONLY be executed when the user gives an explicit command (e.g. "build", "build it", "compile", "make exe").

---

## How to Build (Zero Investigation Required)
Execute the build command ONLY when the user explicitly requests it (e.g. "build", "build it", "compile", "make exe"). Never trigger it autonomously.
Execution without `--explicit-user-request` is physically blocked by a mechanical guard in `build.py`:

```bash
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command "Set-Location '\\\\wsl.localhost\\Ubuntu\\home\\sahana\\Code_Repository\\personal\\komashift'; python build.py --explicit-user-request" < /dev/null
```

### Critical Rules for Execution:
1. **Full PowerShell Path**: Do NOT call bare `powershell.exe`; it is not in Linux `$PATH`. Always use the absolute path `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`.
2. **Redirect Stdin (`< /dev/null`)**: Always append `< /dev/null` at the end to prevent PowerShell from hanging waiting on input.
3. **UNC Path**: The project is accessed from Windows via `\\wsl.localhost\Ubuntu\home\sahana\Code_Repository\personal\komashift`.
4. **Default Packaging Mode**: `build.py` automatically defaults to building the onedir bundle, pruning deadweight binaries, and compiling the Inno Setup installer wizard (`dist/KomaShift-Setup-v<version>.exe`).
5. **Static Versioning & Clean Replacement**: `build.py` does NOT increment version numbers automatically. The version is statically controlled in `src/version.py` and bumped strictly via PRs following Semantic Versioning (MAJOR.MINOR.PATCH). Each build automatically cleans and replaces previous local outputs in `dist/`.

---

## Post-Build Verification
After the background build task finishes:
1. Verify the installer exists:
   ```bash
   ls -lh dist/KomaShift-Setup-v*.exe
   ```
2. Confirm the exact file size (~170MB-190MB) and version to the user with a clickable link: `dist/KomaShift-Setup-v<version>.exe`.
