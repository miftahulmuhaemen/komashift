import json
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


def test_graph_baseline_exists_and_is_valid():
    """Verify the committed graphify graph baseline exists and parses."""
    assert GRAPH_PATH.exists(), "graphify-out/graph.json baseline must exist and be committed!"
    data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    assert "nodes" in data and "links" in data
    assert len(data["nodes"]) > 0


def test_every_src_node_belongs_to_allowed_architectural_tier():
    """Verify all source nodes belong strictly to one of the 6 canonical tiers."""
    data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])

    unmapped = []
    for node in nodes:
        src_file = node.get("source_file", "")
        if src_file.startswith("src/"):
            if not any(src_file == allowed or src_file.startswith(allowed + "/") for allowed in ALLOWED_TIERS):
                unmapped.append((node.get("id"), src_file))

    assert not unmapped, f"Found nodes outside the canonical architectural tiers: {unmapped}"
