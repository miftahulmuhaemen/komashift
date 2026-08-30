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
    version_str = increment_version()
    app_name = f"FolderImagePreviewer_v{version_str}"

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        f"--name={app_name}",
        "--windowed",
        "--onefile",
        "src/main.py"
    ]
    print(f"Running build command: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    dist_dir = Path(__file__).parent / "dist"
    ext = ".exe" if sys.platform.startswith("win") else ""
    versioned_exe = dist_dir / f"{app_name}{ext}"
    generic_exe = dist_dir / f"FolderImagePreviewer{ext}"

    if versioned_exe.exists():
        shutil.copy2(versioned_exe, generic_exe)
        print(f"\nSuccessfully built:\n  -> {versioned_exe}\n  -> {generic_exe}\n")

if __name__ == "__main__":
    build()
