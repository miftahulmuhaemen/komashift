import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "src" / "version.py"

def increment_version() -> str:
    content = VERSION_FILE.read_text(encoding="utf-8")

    major_m = re.search(r'MAJOR\s*=\s*(\d+)', content)
    minor_m = re.search(r'MINOR\s*=\s*(\d+)', content)
    patch_m = re.search(r'PATCH\s*=\s*(\d+)', content)
    build_m = re.search(r'BUILD\s*=\s*(\d+)', content)

    major = int(major_m.group(1)) if major_m else 1
    minor = int(minor_m.group(1)) if minor_m else 0
    patch = int(patch_m.group(1)) if patch_m else 0
    build_num = int(build_m.group(1)) if build_m else 0

    patch += 1
    build_num += 1

    new_content = (
        f"MAJOR = {major}\n"
        f"MINOR = {minor}\n"
        f"PATCH = {patch}\n"
        f"BUILD = {build_num}\n\n"
        f'__version__ = f"{{MAJOR}}.{{MINOR}}.{{PATCH}}"\n'
    )
    VERSION_FILE.write_text(new_content, encoding="utf-8")
    version_str = f"{major}.{minor}.{patch}"
    print(f"Bumped version to v{version_str} (build {build_num})")
    return version_str

def build():
    no_bump = "--no-bump" in sys.argv
    if not sys.platform.startswith("win"):
        ps_path = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        if ps_path.exists():
            print("Detected Linux/WSL environment. Auto-delegating build to Windows PowerShell to produce .exe...")
            unc_path = r"\\wsl.localhost\Ubuntu\home\sahana\Code_Repository\personal\win-folder-thumbnail"
            extra = " --no-bump" if no_bump else ""
            cmd = [str(ps_path), "-NoProfile", "-Command", f"Set-Location '{unc_path}'; python build.py{extra}"]
            with open("/dev/null", "r") as devnull:
                sys.exit(subprocess.call(cmd, stdin=devnull))
        else:
            sys.exit("ERROR: build.py must be executed in Windows environment to produce a Windows .exe binary.")

    if no_bump:
        from src.version import __version__
        version_str = __version__
        print(f"Re-building current version v{version_str}")
    else:
        version_str = increment_version()
    app_name = f"FolderImagePreviewer_v{version_str}"

    sep = ";" if sys.platform.startswith("win") else ":"
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        f"--name={app_name}",
        "--windowed",
        "--onefile",
        "--icon=assets/icon.ico",
        f"--add-data=assets{sep}assets",
        "--collect-all=onnxruntime",
        "--collect-all=manga_ocr",
        "--collect-all=unidic_lite",
        "--collect-all=pyphen",
        "--copy-metadata=transformers",
        "--copy-metadata=tokenizers",
        "--copy-metadata=huggingface_hub",
        "src/main.py"
    ]
    print(f"Running build command: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    dist_dir = Path(__file__).parent / "dist"
    ext = ".exe" if sys.platform.startswith("win") else ""
    versioned_exe = dist_dir / f"{app_name}{ext}"

    if versioned_exe.exists():
        print(f"\nSuccessfully built:\n  -> {versioned_exe}\n")

if __name__ == "__main__":
    build()
