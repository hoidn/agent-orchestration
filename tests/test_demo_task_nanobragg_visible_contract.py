from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VISIBLE_README = (
    ROOT / "examples" / "demo_task_nanobragg_accumulation_port" / "fixtures" / "visible" / "README.md"
)
SRC_README = ROOT / "examples" / "demo_task_nanobragg_accumulation_port" / "src_c" / "README.md"
SMOKE_TEST = ROOT / "examples" / "demo_task_nanobragg_accumulation_port" / "tests" / "test_smoke_accumulation.py"


def test_visible_seed_docs_are_scoped_to_the_contract():
    visible_text = VISIBLE_README.read_text(encoding="utf-8").lower()
    src_text = SRC_README.read_text(encoding="utf-8").lower()
    smoke_text = SMOKE_TEST.read_text(encoding="utf-8").lower()

    assert "nanobragg_accumulation_contract.md" in visible_text
    assert "nanobragg_accumulation_contract.md" in src_text
    assert "source/scattering/polarization" not in src_text
    assert "smoke checks only" in visible_text
    assert "contract smoke" in smoke_text or "scoped contract" in smoke_text
