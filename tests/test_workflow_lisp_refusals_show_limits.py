from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_lisp_improve_stdlib import _public_run, _public_run_files




def _source(body: str, *, signature: str = "() -> Int", target: str = "2.35") -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target}")',
            "  (defmodule grt/entry)",
            "  (export run)",
            f"  (defworkflow run {signature} {body}))",
        )
    )






def test_public_pure_projection_overflow_prints_value_and_signed_64_bit_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    source = tmp_path / "grt" / "entry.orc"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(_source("(+ value 1)", signature="((value Int)) -> Int"), encoding="utf-8")
    input_file = tmp_path / "inputs.json"
    input_file.write_text(json.dumps({"value": 2**63 - 1}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}), input_file=input_file)
    from tests.workflow_evaluated_totality_helpers import checked_run
    _, snapshot = checked_run(tmp_path)
    state = snapshot.terminal.data

    assert result.exit_code == 1
    error = state
    assert "value=9223372036854775808" in error["message"]
    assert "minimum=-9223372036854775808" in error["message"]
    assert "maximum=9223372036854775807" in error["message"]
    assert error["code"] == "pure_expr_overflow"
    assert state["outcome"] == "failed"


def test_public_bounded_loop_without_fallback_records_failed_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(
        "(loop/recur :max 2 :state 0 (fn (state) "
        "(if (< state 10) (continue (+ state 1)) (done state))))"
    )
    entry = tmp_path / "grt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}))
    from tests.workflow_evaluated_totality_helpers import checked_run
    _, snapshot = checked_run(tmp_path)
    state = snapshot.terminal.data
    failure = state

    assert result.exit_code == 1
    assert failure["outcome"] == "failed"
    assert failure["code"] == "loop_exhausted"
    assert not snapshot.active_commits


def test_public_list_map_effect_cap_records_failed_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.35")',
            "  (defmodule grt/entry)",
            "  (export run)",
            "  (defworkflow child ((value Int)) -> Int value)",
            "  (defworkflow run ((values List[Int])) -> List[Int]",
            "    (list/map-effect ((item values)) :max 2",
            "      (call child :value item)))",
            ")",
        )
    )
    entry = tmp_path / "grt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(source, encoding="utf-8")
    input_file = tmp_path / "inputs.json"
    input_file.write_text(json.dumps({"values": [1, 2, 3]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}), input_file=input_file)
    from tests.workflow_evaluated_totality_helpers import checked_run
    _, snapshot = checked_run(tmp_path)
    state = snapshot.terminal.data
    failure = state

    assert result.exit_code == 1
    assert failure["outcome"] == "failed"
    assert failure["code"] == "list_map_effect_cap_exceeded"
    assert not snapshot.active_commits










@pytest.mark.xfail(strict=True, reason="F39: public transport byte refusals omit measured size and cap")
def test_public_transport_byte_refusal_prints_observed_size_and_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.workflow_evaluated_totality_helpers import _write_probe

    probe = _write_probe(
        tmp_path,
        "large_value",
        "import json, os\n"
        "from pathlib import Path\n"
        "output = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "value = {'items': [{'label': 'x' * 17_000_000}]}\n"
        "output.write_text(json.dumps(value), encoding='utf-8')\n",
    )
    entry = tmp_path / "grt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule grt/entry)",
                "  (export run)",
                "  (defrecord Item (label String))",
                "  (defrecord Big (items List[Item]))",
                "  (defproc produce () -> Big",
                "    :effects ((uses-command produce))",
                "    :lowering inline",
                f'    (command-result produce :argv ("python" "{probe}") :returns Big))',
                "  (defworkflow run () -> Big (produce)))",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {"produce": probe}))
    from tests.workflow_evaluated_totality_helpers import checked_run
    _, snapshot = checked_run(tmp_path)
    state = snapshot.terminal.data
    failure = state
    diagnostic = json.dumps(failure)
    expected_bytes = len(
        json.dumps(
            {"items": [{"label": "x" * 17_000_000}]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    assert result.exit_code == 1
    assert failure["type"] == "contract_violation"
    assert "invalid_transportable_value" in diagnostic
    violation = failure["context"]["violations"][0]
    origin = violation["source_origins"][0]
    assert origin["path"] == str(entry)
    assert (origin["line"], origin["column"]) == (11, 5)
    assert f"bytes={expected_bytes}" in diagnostic
    assert "maximum=16777216" in diagnostic
