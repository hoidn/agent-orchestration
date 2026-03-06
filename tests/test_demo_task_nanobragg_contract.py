from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TASK = (
    ROOT
    / "examples"
    / "demo_task_nanobragg_accumulation_port"
    / "docs"
    / "tasks"
    / "port_nanobragg_accumulation_to_pytorch.md"
)
SEED_INDEX = ROOT / "examples" / "demo_task_nanobragg_accumulation_port" / "docs" / "index.md"
SUBSYSTEM_SPEC = ROOT / "docs" / "plans" / "2026-03-05-nanobragg-subsystem-task-spec.md"
CONTRACT = (
    ROOT
    / "examples"
    / "demo_task_nanobragg_accumulation_port"
    / "docs"
    / "tasks"
    / "nanobragg_accumulation_contract.md"
)


def test_nanobragg_scoped_contract_doc_exists_and_defines_required_sections():
    assert CONTRACT.is_file(), f"missing contract doc: {CONTRACT}"

    text = CONTRACT.read_text(encoding="utf-8").lower()

    required_phrases = [
        "included math",
        "excluded math",
        "input contract",
        "normalization rules",
        "oversample semantics",
        "restructuring constraints",
        "source directions",
        "phi values",
        "mosaic domains",
        "polarization",
        "scattering vectors",
        "lattice factors",
    ]

    for phrase in required_phrases:
        assert phrase in text, f"contract doc missing required phrase: {phrase}"


def test_task_and_spec_point_to_scoped_contract_instead_of_broader_physics_scope():
    task_text = TASK.read_text(encoding="utf-8").lower()
    spec_text = SUBSYSTEM_SPEC.read_text(encoding="utf-8").lower()
    index_text = SEED_INDEX.read_text(encoding="utf-8").lower()

    assert "nanobragg_accumulation_contract.md" in task_text
    assert "authoritative" in task_text
    assert "scattering-vector" not in task_text
    assert "polarization" not in task_text
    assert "lattice-related" not in task_text

    assert "narrowed contract" in spec_text
    assert "future work" in spec_text
    assert "nanobragg_accumulation_contract.md" in index_text
