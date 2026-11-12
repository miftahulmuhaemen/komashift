import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = REPO_ROOT / "graphify-out" / "graph.json"

ALLOWED_TIERS = {
    "src/models",
    "src/ports",
    "src/services",
    "src/infra",
    "src/viewmodels",
    "src/ui",
    "src/main.py",
    "src/version.py",
    "src/__init__.py",
}


def test_every_src_file_belongs_to_allowed_architectural_tier():
    """Verify all source files belong strictly to one of the canonical tiers."""
    src_dir = REPO_ROOT / "src"
    unmapped = []
    for py_file in src_dir.rglob("*.py"):
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        if "__pycache__" in rel:
            continue
        if not any(rel == allowed or rel.startswith(allowed + "/") for allowed in ALLOWED_TIERS):
            unmapped.append(rel)

    assert not unmapped, f"Found source files outside canonical architectural tiers: {unmapped}"


def test_graph_baseline_when_present():
    """If local graphify baseline exists, verify it parses and adheres to tiers."""
    if not GRAPH_PATH.exists():
        pytest.skip("Local graphify-out/graph.json not present (ephemeral local artifact).")

    data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    assert "nodes" in data and "links" in data
    assert len(data["nodes"]) > 0
