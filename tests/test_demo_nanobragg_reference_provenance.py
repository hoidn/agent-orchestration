from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / "scripts" / "demo" / "build_nanobragg_reference_cases.py"
RUN_REFERENCE = ROOT / "scripts" / "demo" / "nanobragg_reference" / "run_reference_case.py"
CASES = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_accumulation" / "cases.json"


def test_builder_does_not_contain_literal_reference_tensor_lookup_table():
    source = BUILDER.read_text()

    assert "REFERENCE_TENSORS" not in source
    assert "torch.full((2, 3), 1.25" not in source
    assert "torch.tensor([[0.75, 1.0], [1.25, 1.5]]" not in source


def test_hidden_cases_record_reference_provenance_fields():
    payload = json.loads(CASES.read_text())

    for case in payload["cases"]:
        assert case["reference_method"] == "offline_reference_harness"
        assert case["reference_source"].endswith("nanoBragg.c")
        assert case["reference_snapshot"]


def test_builder_uses_reference_runner_backend():
    source = BUILDER.read_text()

    assert "RUN_REFERENCE" in source
    assert "run_reference_case.py" in source
