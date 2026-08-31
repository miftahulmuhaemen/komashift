# Build Guidelines

- **Explicit Build Trigger Only**: NEVER run `build.py` or compile binaries unless the user explicitly requests to build / rebuild.
- **Target OS**: Always build for **Windows (.exe)** only. Never produce or deliver Linux executables for this repository.
- **Single Executable Output**: Only produce a single versioned `.exe` binary (`FolderImagePreviewer_v<version>.exe`).
- **Build Execution**:
  - When on a WSL/Linux environment, execute `build.py` exclusively via Windows PowerShell (`powershell.exe -NoProfile -Command "Set-Location '<wsl_path>'; python build.py"`).
  - If Windows Python / PowerShell build is unavailable or fails, notify the user immediately instead of falling back to a Linux build.
