"""Target 2.35 registration and run/resume refusal before evaluated execution lands."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow import validation
from orchestrator.workflow.run_ref import bundle_transport, config as run_ref_config
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.target import (
    entry_target_dsl_version,
    refuse_run_at_evaluated_execution_target,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from tests.test_workflow_lisp_target_234 import (
    GATES_FROM_234,
    GATES_FROM_EVALUATED_EXECUTION,
    GATE_PREDICATES,
    _log,
    _write_program,
    _public_run,
)
from tests.test_workflow_lisp_generic_unions_runtime import _public_run_files
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv

TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION


@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
        pytest.param(validation.DEFAULT_SUPPORTED_VERSIONS, id="shared-validation"),
        pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
        pytest.param(bundle_transport._SUPPORTED_TARGET_DSL_VERSIONS, id="bundle-transport"),
    ],
)
def test_target_235_is_registered(registry) -> None:
    assert TARGET in registry


def test_shared_validation_orders_235_last() -> None:
    assert validation.DEFAULT_VERSION_ORDER[-2:] == ("2.34", TARGET)


def test_evaluated_execution_gate_starts_at_235() -> None:
    assert TARGET == "2.35"
    predicate = syntax.target_dsl_uses_evaluated_execution
    assert (predicate("2.34"), predicate(TARGET)) == (False, True)


@pytest.mark.parametrize("gate", sorted(GATE_PREDICATES | GATES_FROM_234))
def test_every_prior_gate_holds_at_235(gate: str) -> None:
    predicate = (GATE_PREDICATES | GATES_FROM_234)[gate]

    assert predicate(TARGET)


def test_new_gate_is_in_target_gate_completeness_audit() -> None:
    assert set(GATES_FROM_EVALUATED_EXECUTION) == {
        "EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION"
    }


def test_entry_target_version_and_refusal_diagnostic(tmp_path: Path) -> None:
    files = _write_program(tmp_path, TARGET)
    line = next(
        n for n, source_line in enumerate(files["source"].read_text().splitlines(), 1)
        if ":target-dsl" in source_line
    )

    assert entry_target_dsl_version(files["source"]) == TARGET
    with pytest.raises(LispFrontendCompileError) as excinfo:
        refuse_run_at_evaluated_execution_target(files["source"])

    assert len(excinfo.value.diagnostics) == 1
    diagnostic = excinfo.value.diagnostics[0]
    assert (
        diagnostic.code,
        diagnostic.phase,
        Path(diagnostic.span.start.path),
        diagnostic.span.start.line,
    ) == ("evaluated_execution_unavailable", "lowering", files["source"], line)


def test_public_run_refuses_target_235_before_command_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    files = _write_program(tmp_path, TARGET)
    line = next(
        n for n, source_line in enumerate(files["source"].read_text().splitlines(), 1)
        if ":target-dsl" in source_line
    )
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert result.exit_code == 2
    assert _log(tmp_path / "probe_revise.py") == []
    assert caplog.text.count("[evaluated_execution_unavailable]") == 1
    assert f"{files['source']}:{line}:" in caplog.text


def test_legacy_run_keeps_external_source_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    external_root = tmp_path / "external"
    project_root.mkdir()
    files = _public_run_files(project_root, {})
    external_module = external_root / "shared" / "types.orc"
    external_module.parent.mkdir(parents=True)
    external_module.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.34") '
        '(defmodule shared/types) (export Out) (defrecord Out (value String)))\n',
        encoding="utf-8",
    )
    files["source"].parent.mkdir(parents=True)
    files["source"].write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.34") '
        '(defmodule grt/entry) (import shared/types :only (Out)) (export run) '
        '(defworkflow run () -> Out (record Out :value "ok")))\n',
        encoding="utf-8",
    )
    assert entry_target_dsl_version(files["source"]) == "2.34"
    args = _run_args(files)
    args.source_root.append(str(external_root))
    argv = [*_run_argv(files), "--source-root", str(external_root)]
    monkeypatch.chdir(tmp_path)

    with patch.object(sys, "argv", argv):
        result = run_workflow(args)

    assert result.exit_code == 0


def test_public_resume_refuses_target_235_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    files = _write_program(tmp_path, TARGET)
    line = next(
        n for n, source_line in enumerate(files["source"].read_text().splitlines(), 1)
        if ":target-dsl" in source_line
    )
    manager = StateManager(tmp_path, run_id="evaluated-execution-refusal")
    state = manager.initialize(files["source"].relative_to(tmp_path).as_posix())
    state.status = "failed"
    manager._write_state()
    monkeypatch.chdir(tmp_path)

    exit_code = resume_workflow(run_id=manager.run_id, retry_delay_ms=0)

    assert exit_code == 2
    assert _log(tmp_path / "probe_revise.py") == []
    assert caplog.text.count("[evaluated_execution_unavailable]") == 1
    assert f"{files['source']}:{line}:" in caplog.text
