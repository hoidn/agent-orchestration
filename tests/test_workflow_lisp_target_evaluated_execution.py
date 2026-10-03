"""Target 2.35 registration and public entry behavior during rollout."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow import validation
from orchestrator.workflow_lisp import build as workflow_lisp_build
from orchestrator.workflow.run_ref import bundle_transport, config as run_ref_config
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow_lisp import syntax
import orchestrator.workflow.evaluated.authority as evaluated_authority
from orchestrator.workflow_lisp.closed.target import (
    entry_target_dsl_version,
    refuse_run_at_evaluated_execution_target,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.monitor.process import write_process_metadata
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


def test_public_run_235_dispatches_commands_and_commits_dependency_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _write_program(tmp_path, TARGET)
    commands = json.loads(files["commands"].read_text(encoding="utf-8"))
    for command in commands.values():
        command["closure"] = []
    files["commands"].write_text(json.dumps(commands), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs)) == (
        0,
        {"title": "seed+r+r", "score": 2},
    )
    assert _log(tmp_path / "probe_revise.py") == [
        "seed tidy fb",
        "seed+r tidy fb",
    ]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert (run_root / "run.json").is_file()
    memo = [
        json.loads(line)
        for line in (run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    committed = [row for row in memo if row["record"] == "committed"]
    assert len(committed) == 2
    first, second = committed
    probe = str(tmp_path / "probe_revise.py")
    assert [row["input_parts"]["argv"] for row in committed] == [
        canonical_sha256(["python", probe, "seed", "tidy", "fb"]),
        canonical_sha256(["python", probe, "seed+r", "tidy", "fb"]),
    ]
    assert first["depends_on"] == []
    assert second["depends_on"] == [first["identity"]]
    assert memo[-1] == {
        "outcome": "completed",
        "record": "terminal",
        "value": {"title": "seed+r+r", "score": 2},
    }


def test_public_run_does_not_dispatch_when_authority_publication_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _write_program(tmp_path, TARGET)
    commands = json.loads(files["commands"].read_text(encoding="utf-8"))
    for command in commands.values():
        command["closure"] = []
    files["commands"].write_text(json.dumps(commands), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def fail_authority_write(*_args, **_kwargs):
        raise OSError("injected authority artifact publication failure")

    monkeypatch.setattr(
        evaluated_authority, "durable_atomic_write", fail_authority_write
    )

    result = _public_run(files)

    assert result.exit_code == 1
    assert _log(tmp_path / "probe_revise.py") == []
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert not (run_root / "run.json").exists()
    assert (run_root / "memo.jsonl").read_bytes() == b""


def _replace_target_header(source: Path, before: str, after: str) -> None:
    text = source.read_text(encoding="utf-8")
    old = f'(:target-dsl "{before}")'
    assert old in text
    source.write_text(text.replace(old, f'(:target-dsl "{after}")', 1), encoding="utf-8")


def _flip_after_early_guard_and_restore_after_compile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    command_module,
    source: Path,
) -> None:
    early_guard = command_module.refuse_run_at_evaluated_execution_target
    compile_entrypoint = workflow_lisp_build.compile_stage3_entrypoint

    def flip_after_guard(path: Path) -> None:
        early_guard(path)
        _replace_target_header(source, "2.34", TARGET)

    def compile_then_restore(*args, **kwargs):
        result = compile_entrypoint(*args, **kwargs)
        reads = kwargs["source_read_trace"].raw_bytes_by_path
        assert TARGET.encode() in reads[source.resolve()]
        _replace_target_header(source, TARGET, "2.34")
        return result

    monkeypatch.setattr(command_module, "refuse_run_at_evaluated_execution_target", flip_after_guard)
    monkeypatch.setattr(workflow_lisp_build, "compile_stage3_entrypoint", compile_then_restore)


def test_public_run_refuses_compiled_snapshot_changed_after_early_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from orchestrator.cli.commands import run as run_command

    files = _write_program(tmp_path, "2.34")
    line = next(
        n for n, source_line in enumerate(files["source"].read_text().splitlines(), 1)
        if ":target-dsl" in source_line
    )
    _flip_after_early_guard_and_restore_after_compile(
        monkeypatch,
        command_module=run_command,
        source=files["source"],
    )
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert _log(tmp_path / "probe_revise.py") == []
    assert result.exit_code == 2
    assert entry_target_dsl_version(files["source"]) == "2.34"
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


def test_evaluated_run_keeps_external_source_roots(
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
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule shared/types) (export Out) (defrecord Out (value String)))\n',
        encoding="utf-8",
    )
    files["source"].parent.mkdir(parents=True)
    files["source"].write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule grt/entry) (import shared/types :only (Out)) (export run) '
        '(defworkflow run () -> Out (record Out :value "ok")))\n',
        encoding="utf-8",
    )
    args = _run_args(files)
    args.source_root.append(str(external_root))
    argv = [*_run_argv(files), "--source-root", str(external_root)]
    monkeypatch.chdir(tmp_path)

    with patch.object(sys, "argv", argv):
        result = run_workflow(args)

    assert result.exit_code == 0
    assert dict(result.workflow_outputs) == {"value": "ok"}


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


def test_public_resume_refuses_compiled_snapshot_changed_after_early_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from orchestrator.cli.commands import resume as resume_command

    files = _write_program(tmp_path, "2.34")
    line = next(
        n for n, source_line in enumerate(files["source"].read_text().splitlines(), 1)
        if ":target-dsl" in source_line
    )
    manager = StateManager(tmp_path, run_id="evaluated-execution-race-resume")
    state = manager.initialize(files["source"].relative_to(tmp_path).as_posix())
    state.status = "failed"
    manager._write_state()
    argv = [*_run_argv(files), "--command-boundaries-file", str(files["commands"])]
    write_process_metadata(manager.run_root, argv=argv)
    _flip_after_early_guard_and_restore_after_compile(
        monkeypatch,
        command_module=resume_command,
        source=files["source"],
    )
    monkeypatch.chdir(tmp_path)

    exit_code = resume_workflow(
        run_id=manager.run_id,
        force_restart=True,
        retry_delay_ms=0,
    )

    assert _log(tmp_path / "probe_revise.py") == []
    assert exit_code == 2
    assert entry_target_dsl_version(files["source"]) == "2.34"
    assert caplog.text.count("[evaluated_execution_unavailable]") == 1
    assert f"{files['source']}:{line}:" in caplog.text
