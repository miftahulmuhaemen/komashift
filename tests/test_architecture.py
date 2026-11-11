import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Ratchet ceilings: actual <= ceiling, and ceilings may only ever decrease!
LOC_CEILINGS = {
    "src/ui/main_window.py": 1430,
    "src/ui/queue_dialog.py": 950,
    "src/services/translation_worker.py": 520,
    "src/infra/json_workspace.py": 280,
    "src/viewmodels/settings_viewmodel.py": 250,
    "src/viewmodels/library_viewmodel.py": 250,
    "src/viewmodels/translation_viewmodel.py": 250,
}


def test_import_linter_architecture_contracts():
    """Verify hexagonal architecture contracts using import-linter."""
    res = subprocess.run(
        [sys.executable, "-m", "importlinter.cli"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True
    )
    assert res.returncode == 0, f"Architecture contracts broken!\n{res.stdout}\n{res.stderr}"


def test_loc_ratchet_enforcement():
    """Assert LOC of monolithic files do not exceed ratchet ceilings."""
    for rel_path, ceiling in LOC_CEILINGS.items():
        file_path = REPO_ROOT / rel_path
        if file_path.exists():
            line_count = len(file_path.read_text(encoding="utf-8").splitlines())
            assert line_count <= ceiling, (
                f"{rel_path} exceeded LOC ceiling! Current: {line_count}, Ceiling: {ceiling}. "
                f"Do not add bloat to existing files. Extract into viewmodels or services."
            )


def test_no_qt_widgets_in_services():
    """Verify services never import PyQt6.QtWidgets (Phase 5 eliminated the image_rasterizer leak)."""
    services_dir = REPO_ROOT / "src" / "services"
    violations = []
    for py_file in services_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if "PyQt6.QtWidgets" in text:
            violations.append(py_file.name)
    assert not violations, f"Services importing PyQt6.QtWidgets: {violations}"


def test_no_private_cross_module_access():
    """Verify no collaborator private member access across boundaries (Leak B eliminated in Phase 6)."""
    import re
    src_dir = REPO_ROOT / "src"
    pattern = re.compile(r"\.(detector|translator|workspace|queue_manager)\._[a-zA-Z]")
    violations = []
    for py_file in src_dir.rglob("*.py"):
        for line_no, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(line):
                violations.append(f"{py_file.relative_to(REPO_ROOT)}:{line_no} -> {line.strip()}")
    assert not violations, f"Forbidden private collaborator access found:\n" + "\n".join(violations)


def test_viewmodels_are_widget_free():
    """Verify ViewModels are thin, headless QObjects with zero PyQt6.QtWidgets imports."""
    vm_dir = REPO_ROOT / "src" / "viewmodels"
    violations = []
    for py_file in vm_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if "PyQt6.QtWidgets" in text:
            violations.append(py_file.name)
    assert not violations, f"ViewModels importing PyQt6.QtWidgets: {violations}"
