import subprocess
import sys
from pathlib import Path

def test_build_script_rejects_unauthorized_execution():
    """Verify build.py cannot be executed without --explicit-user-request."""
    repo_root = Path(__file__).resolve().parent.parent
    build_script = repo_root / "build.py"

    proc = subprocess.run(
        [sys.executable, str(build_script)],
        capture_output=True,
        text=True
    )
    assert proc.returncode != 0
    assert "CRITICAL ERROR: Automated build rejected!" in proc.stderr or "CRITICAL ERROR: Automated build rejected!" in proc.stdout
    assert "--explicit-user-request" in (proc.stderr + proc.stdout)
