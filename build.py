import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "src" / "version.py"


def bump_version(part: str = "patch") -> str:
    content = VERSION_FILE.read_text(encoding="utf-8")

    major_m = re.search(r'MAJOR\s*=\s*(\d+)', content)
    minor_m = re.search(r'MINOR\s*=\s*(\d+)', content)
    patch_m = re.search(r'PATCH\s*=\s*(\d+)', content)
    build_m = re.search(r'BUILD\s*=\s*(\d+)', content)

    major = int(major_m.group(1)) if major_m else 1
    minor = int(minor_m.group(1)) if minor_m else 0
    patch = int(patch_m.group(1)) if patch_m else 0
    build_num = int(build_m.group(1)) if build_m else 0

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:
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
    print(f"Bumped version ({part}) to v{version_str} (build {build_num})")
    return version_str


def find_iscc() -> Path | None:
    which = shutil.which("iscc")
    if which:
        return Path(which)

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


EXPLICIT_FLAG = "--explicit-user-request"


def build():
    if EXPLICIT_FLAG not in sys.argv:
        sys.exit(
            f"CRITICAL ERROR: Automated build rejected!\n"
            f"build.py is strictly restricted and cannot be executed autonomously.\n"
            f"It requires an explicit user command in the current prompt and the flag '{EXPLICIT_FLAG}'.\n"
            f"See .agents/rules/build.md."
        )

    if not sys.platform.startswith("win"):
        ps_path = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        if ps_path.exists():
            print("Detected Linux/WSL environment. Auto-delegating build to Windows PowerShell to produce .exe...")
            real_parent = Path(__file__).resolve().parent
            unc_subpath = str(real_parent).replace("/", "\\")
            unc_path = f"\\\\wsl.localhost\\Ubuntu{unc_subpath}"
            forward_flags = [arg for arg in sys.argv[1:] if arg != EXPLICIT_FLAG]
            extra = (" " + " ".join(forward_flags)) if forward_flags else ""
            cmd = [str(ps_path), "-NoProfile", "-Command", f"Set-Location '{unc_path}'; python build.py {EXPLICIT_FLAG}{extra}"]
            with open("/dev/null", "r") as devnull:
                sys.exit(subprocess.call(cmd, stdin=devnull))
        else:
            sys.exit("ERROR: build.py must be executed in Windows environment to produce a Windows .exe binary.")

    # Version management: static by default (governed exclusively via PRs)
    if "--bump-major" in sys.argv:
        version_str = bump_version("major")
    elif "--bump-minor" in sys.argv:
        version_str = bump_version("minor")
    elif "--bump-patch" in sys.argv or "--bump" in sys.argv:
        version_str = bump_version("patch")
    else:
        from src.version import __version__
        version_str = __version__
        print(f"Building version v{version_str} (static, no auto-bump)")

    app_name = f"KomaShift_v{version_str}"
    dist_dir = Path(__file__).parent / "dist"

    # Clean previous build artifacts for this version so next build cleanly replaces it
    target_dir = dist_dir / app_name
    if target_dir.exists():
        print(f"Cleaning previous build directory: {target_dir}")
        shutil.rmtree(target_dir, ignore_errors=True)
    target_exe = dist_dir / f"{app_name}.exe"
    if target_exe.exists():
        print(f"Cleaning previous binary: {target_exe}")
        target_exe.unlink(missing_ok=True)
    target_setup = dist_dir / f"KomaShift-Setup-v{version_str}.exe"
    if target_setup.exists():
        print(f"Cleaning previous installer: {target_setup}")
        target_setup.unlink(missing_ok=True)

    onedir = "--onedir" in sys.argv or "--installer" in sys.argv
    build_installer = "--installer" in sys.argv or onedir
    no_model = "--no-model" in sys.argv
    packaging_mode = "--onedir" if onedir else "--onefile"

    sep = ";" if sys.platform.startswith("win") else ":"
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        f"--name={app_name}",
        "--noconfirm",
        "--windowed",
        packaging_mode,
        "--icon=assets/icon.ico",
    ]

    if no_model:
        # Exclude 95 MB comic-text-detector.onnx from core bundle (streamed on demand via AiAssetsManager)
        cmd.extend([
            f"--add-data=assets/icon.ico{sep}assets",
            f"--add-data=assets/icon.png{sep}assets",
            f"--add-data=assets/fonts{sep}assets/fonts",
            f"--add-data=assets/checkbox_checked.png{sep}assets",
            f"--add-data=assets/checkbox_checked_disabled.png{sep}assets",
        ])
    else:
        cmd.append(f"--add-data=assets{sep}assets")

    cmd.extend([
        "--collect-all=onnxruntime",
        "--collect-all=manga_ocr",
        "--collect-all=unidic_lite",
        "--collect-all=pyphen",
        "--copy-metadata=transformers",
        "--copy-metadata=tokenizers",
        "--copy-metadata=huggingface_hub",
        "--exclude-module=botocore",
        "--exclude-module=boto3",
        "--exclude-module=Pythonwin",
        "--exclude-module=win32ui",
        "--exclude-module=PyQt6.QtPdf",
        "--exclude-module=PyQt6.QtQml",
        "--exclude-module=PyQt6.QtQuick",
        "--exclude-module=PyQt6.QtSql",
        "--exclude-module=PyQt6.QtTest",
        "src/main.py"
    ])

    print(f"Running build command: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    dist_dir = Path(__file__).parent / "dist"
    ext = ".exe" if sys.platform.startswith("win") else ""
    versioned_target = (dist_dir / app_name / f"{app_name}{ext}") if onedir else (dist_dir / f"{app_name}{ext}")

    if versioned_target.exists():
        print(f"\nSuccessfully built binary:\n  -> {versioned_target}\n")

    if onedir:
        internal_dir = dist_dir / app_name / "_internal"
        if internal_dir.exists():
            prune_patterns = [
                "cv2/opencv_videoio_ffmpeg*.dll",
                "PyQt6/Qt6/bin/opengl32sw.dll",
                "PyQt6/Qt6/bin/Qt6Pdf.dll",
                "PyQt6/Qt6/translations",
                "Pythonwin",
            ]
            pruned_bytes = 0
            for pattern in prune_patterns:
                for match in internal_dir.glob(pattern):
                    if match.is_file():
                        size = match.stat().st_size
                        match.unlink()
                        pruned_bytes += size
                        print(f"Pruned deadweight file: {match.relative_to(internal_dir)} ({size / (1024*1024):.1f} MB)")
                    elif match.is_dir():
                        size = sum(f.stat().st_size for f in match.rglob("*") if f.is_file())
                        shutil.rmtree(match)
                        pruned_bytes += size
                        print(f"Pruned deadweight directory: {match.relative_to(internal_dir)} ({size / (1024*1024):.1f} MB)")
            if pruned_bytes > 0:
                print(f"Total deadweight pruned: {pruned_bytes / (1024*1024):.1f} MB\n")

    # If building installer, compile Inno Setup script
    if build_installer:
        iscc = find_iscc()
        iss_file = Path(__file__).parent / "installer" / "komashift_setup.iss"
        if iscc and iss_file.is_file():
            print(f"Compiling Inno Setup installer using {iscc}...")
            iscc_cmd = [str(iscc), f"/DMyAppVersion={version_str}", str(iss_file)]
            subprocess.check_call(iscc_cmd)
            setup_exe = dist_dir / f"KomaShift-Setup-v{version_str}.exe"
            if setup_exe.exists():
                size_mb = setup_exe.stat().st_size / (1024 * 1024)
                print(f"\nSuccessfully built Inno Setup installer ({size_mb:.1f} MB):\n  -> {setup_exe}\n")
        else:
            print(f"Notice: ISCC.exe not found or iss script missing. Skipped installer compilation.")


if __name__ == "__main__":
    build()
