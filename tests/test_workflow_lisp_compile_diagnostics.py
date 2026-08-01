from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from orchestrator.cli.commands.compile import compile_workflow
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.compile_diagnostics import (
    build_accepted_compile_diagnostics_document,
    build_rejected_compile_diagnostics_document,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


def _source(*, return_type: str = "Result") -> str:
    return f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export Result run)
  (defrecord Result
    (value String))
  (defworkflow run
    ()
    -> {return_type}
    (record Result
      :value "ok")))
"""


def _request(source_path: Path, workspace_root: Path) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=source_path,
        source_roots=(workspace_root,),
        entry_workflow="run",
        workspace_root=workspace_root,
    )


def _cli_args(source_path: Path, workspace_root: Path) -> Namespace:
    return Namespace(
        workflow=str(source_path),
        diagnostics_json=True,
        entry_workflow="run",
        source_root=[str(workspace_root)],
        provider_externs_file=None,
        prompt_externs_file=None,
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_executable_ir=[],
        emit_core_ast=[],
        emit_runtime_plan=[],
        emit_semantic_ir=[],
        emit_source_map=[],
        emit_debug_yaml=[],
    )


def test_cli_and_library_emit_identical_accepted_full_compile_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_path = tmp_path / "candidate.orc"
    source_path.write_text(_source(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    build_result = build_frontend_bundle(_request(source_path, tmp_path))
    library_document = build_accepted_compile_diagnostics_document(
        build_result
    )

    exit_code = compile_workflow(_cli_args(source_path, tmp_path))
    captured = capsys.readouterr()

    assert exit_code == 0
    assert library_document["status"] == "accepted"
    assert captured.err == ""
    assert captured.out == (
        canonical_json_bytes(library_document).decode("utf-8") + "\n"
    )


def test_cli_and_library_emit_identical_rejected_full_compile_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_path = tmp_path / "candidate.orc"
    source_path.write_text(
        _source(return_type="MissingResult"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(_request(source_path, tmp_path))
    library_document = build_rejected_compile_diagnostics_document(
        excinfo.value.diagnostics
    )

    exit_code = compile_workflow(_cli_args(source_path, tmp_path))
    captured = capsys.readouterr()

    assert exit_code == 2
    assert library_document["status"] == "rejected"
    assert [row["code"] for row in library_document["diagnostics"]] == [
        "type_unknown"
    ]
    assert captured.err == ""
    assert captured.out == (
        canonical_json_bytes(library_document).decode("utf-8") + "\n"
    )
