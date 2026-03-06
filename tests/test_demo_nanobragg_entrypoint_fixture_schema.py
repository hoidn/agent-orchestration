from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VISIBLE_ROOT = ROOT / "examples" / "demo_task_nanobragg_entrypoint_port" / "fixtures" / "visible"
HIDDEN_ROOT = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_entrypoint"
VISIBLE_README = VISIBLE_ROOT / "README.md"
HIDDEN_README = HIDDEN_ROOT / "README.md"
VISIBLE_CASE = VISIBLE_ROOT / "case_basic.json"
HIDDEN_CASES = HIDDEN_ROOT / "cases.json"


def test_entrypoint_fixture_docs_exist():
    assert VISIBLE_README.is_file()
    assert HIDDEN_README.is_file()


def test_visible_fixture_uses_entrypoint_case_shape():
    payload = json.loads(VISIBLE_CASE.read_text())

    assert payload["case_id"] == "case_basic"
    assert isinstance(payload["argv"], list)
    assert payload["argv"]
    assert payload["output_shape"] == [4, 4]


def test_hidden_cases_include_shape_and_provenance():
    payload = json.loads(HIDDEN_CASES.read_text())
    assert payload["entrypoint"] == "nanobragg_run"
    assert payload["reference_method"] == "nanobragg_main_wrapper"
    assert len(payload["cases"]) >= 10

    hidden_only_cases = []
    output_shapes = set()

    for case in payload["cases"]:
        assert case["case_id"]
        assert case["input_fixture_relpath"]
        assert case["input_fixture_origin"] in {"workspace", "evaluator_fixture_root"}
        assert case["expected_output_path"]
        assert case["output_shape"]
        assert case["probe_sites"]
        assert case["reference_source"].endswith("nanoBragg.c")
        output_shapes.add(tuple(case["output_shape"]))
        if case["input_fixture_origin"] == "evaluator_fixture_root":
            hidden_only_cases.append(case["case_id"])

    assert len(hidden_only_cases) >= 5
    assert len(output_shapes) >= 2
