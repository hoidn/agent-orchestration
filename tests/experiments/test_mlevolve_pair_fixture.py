"""Current feasibility boundary and reference trace for the paired search."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from experiments.mlevolve_pair.search import run_search
from tests.test_workflow_lisp_generic_unions_runtime import _public_run

ROOT = Path(__file__).resolve().parents[2]
PAIR = ROOT / "experiments" / "mlevolve_pair"


def _public_run_diagnostic(source_name: str, tmp_path: Path, caplog) -> tuple[int, list[tuple[str, str]]]:
    source_dir = tmp_path / "experiments" / "mlevolve_pair"
    source_dir.mkdir(parents=True)
    source = source_dir / source_name
    source.write_text(
        (PAIR / source_name).read_text(encoding="utf-8").replace("run-search", "run"),
        encoding="utf-8",
    )
    command_manifest = "commands_compact.json" if source_name == "search_compact.orc" else "commands.json"
    shutil.copy2(PAIR / command_manifest, source_dir / "commands.json")
    shutil.copy2(PAIR / "leaves.py", source_dir / "leaves.py")
    providers, prompts = tmp_path / "providers.json", tmp_path / "prompts.json"
    providers.write_text("{}", encoding="utf-8")
    prompts.write_text("{}", encoding="utf-8")
    files = {
        "source": source,
        "source_root": tmp_path / "experiments",
        "providers": providers,
        "prompts": prompts,
        "commands": source_dir / "commands.json",
    }

    result = _public_run(files)
    diagnostics = []
    for record in caplog.records:
        rendered = record.getMessage()
        code = re.search(r"\[([a-z][a-z0-9_]*)\]", rendered)
        form = re.search(r"^form: (.+)$", rendered, re.MULTILINE)
        if code:
            diagnostics.append((code.group(1), form.group(1) if form else ""))
    return result.exit_code, diagnostics


def test_python_reference_trace_records_each_decision_and_the_budget_spent() -> None:
    result = run_search(max_evaluations=12)
    trace = result["trace"]
    assert isinstance(trace, list)
    assert [
        (
            spent,
            row["action"],
            row["branch"],
            row["parents"],
            row["candidate"],
            row["evaluation"],
            row["accepted"],
        )
        for spent, row in enumerate(trace, start=1)
    ] == [
        (1, "seed", "A", [], {"a": 1, "b": 0}, {"valid": True, "score": 316.0, "error": ""}, True),
        (2, "seed", "B", [], {"a": 0, "b": 1}, {"valid": True, "score": 176.0, "error": ""}, True),
        (3, "improve", "A", [{"a": 1, "b": 0}], {"a": 99, "b": 0}, {"valid": False, "score": 0.0, "error": "coefficient_out_of_domain"}, False),
        (4, "repair", "A", [{"a": 99, "b": 0}], {"a": 2, "b": 0}, {"valid": True, "score": 306.0, "error": ""}, True),
        (5, "improve", "B", [{"a": 0, "b": 1}], {"a": 0, "b": 3}, {"valid": True, "score": 40.0, "error": ""}, True),
        (6, "improve", "A", [{"a": 2, "b": 0}], {"a": 2, "b": 0}, {"valid": True, "score": 306.0, "error": ""}, False),
        (7, "improve", "B", [{"a": 0, "b": 3}], {"a": 0, "b": 3}, {"valid": True, "score": 40.0, "error": ""}, False),
        (8, "improve", "A", [{"a": 2, "b": 0}], {"a": 2, "b": 0}, {"valid": True, "score": 306.0, "error": ""}, False),
        (9, "improve", "B", [{"a": 0, "b": 3}], {"a": 0, "b": 3}, {"valid": True, "score": 40.0, "error": ""}, False),
        (10, "fuse", "both", [{"a": 2, "b": 0}, {"a": 0, "b": 3}], {"a": 2, "b": 3}, {"valid": True, "score": 0.0, "error": ""}, True),
    ]
    assert result == {
        "candidate": {"a": 2, "b": 3},
        "evaluation": {"valid": True, "score": 0.0, "error": ""},
        "evaluations": 10,
        "status": "solved",
        "trace": trace,
    }
    for budget, expected in (
        (2, (2, "budget_exhausted", {"a": 0, "b": 1}, {"valid": True, "score": 176.0, "error": ""})),
        (3, (3, "budget_exhausted", {"a": 0, "b": 1}, {"valid": True, "score": 176.0, "error": ""})),
        (4, (4, "budget_exhausted", {"a": 0, "b": 1}, {"valid": True, "score": 176.0, "error": ""})),
        (7, (7, "budget_exhausted", {"a": 0, "b": 3}, {"valid": True, "score": 40.0, "error": ""})),
        (12, (10, "solved", {"a": 2, "b": 3}, {"valid": True, "score": 0.0, "error": ""})),
    ):
        bounded = run_search(max_evaluations=budget)
        assert (
            bounded["evaluations"],
            bounded["status"],
            bounded["candidate"],
            bounded["evaluation"],
        ) == expected


def test_branch_expanded_controller_reports_its_current_diagnostic_code(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _public_run_diagnostic("search.orc", tmp_path, caplog) == (
        2,
        # Bound values are shared in the payload, so the state update passes the size bound.
        # The form meets the next rule: a loop inside a branch.
        [("workflow_boundary_type_invalid", "workflow-lisp > defworkflow > run")],
    )


def test_compact_controller_reports_its_current_diagnostic_code(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _public_run_diagnostic("search_compact.orc", tmp_path, caplog) == (
        2,
        [("workflow_return_not_exportable", "workflow-lisp > defproc > branch-step")],
    )
