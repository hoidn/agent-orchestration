"""Target 2.35 registration and public entry behavior during rollout."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.workflow.run_ref import config as run_ref_config
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.target import entry_target_dsl_version
from orchestrator.cli.commands.run import run_workflow
from tests.test_workflow_lisp_target_234 import (
    GATES_FROM_234,
    GATES_FROM_EVALUATED_EXECUTION,
    GATE_PREDICATES,
    _log,
    _write_program,
    _public_run,
)
from tests.workflow_evaluated_totality_helpers import _public_run_files
from tests.test_workflow_evaluated_cli import _run_args, _run_argv

TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION


@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
        pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
    ],
)
def test_target_235_is_registered(registry) -> None:
    assert TARGET in registry




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




def _assert_public_run_dependency_result(tmp_path: Path, result) -> None:
    assert (result.exit_code, dict(result.workflow_outputs)) == (
        0,
        {"title": "seed+r+r", "score": 2},
    )
    assert _log(tmp_path / "probe_revise.py") == [
        "seed tidy fb",
        "seed+r tidy fb",
    ]


def _committed_rows_from_run(tmp_path: Path):
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert (run_root / "run.json").is_file()
    memo = [
        json.loads(line)
        for line in (run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    committed = [row for row in memo if row["record"] == "committed"]
    assert len(committed) == 2
    return memo, committed


def _assert_committed_argv_digests(committed, probe: str) -> None:
    assert [row["input_parts"]["argv"] for row in committed] == [
        canonical_sha256(["python", probe, "seed", "tidy", "fb"]),
        canonical_sha256(["python", probe, "seed+r", "tidy", "fb"]),
    ]


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

    _assert_public_run_dependency_result(tmp_path, result)
    memo, committed = _committed_rows_from_run(tmp_path)
    first, second = committed
    probe = str(tmp_path / "probe_revise.py")
    _assert_committed_argv_digests(committed, probe)
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
        "orchestrator.workflow.workspace_files.shutil.copyfileobj", fail_authority_write
    )

    result = _public_run(files)

    assert result.exit_code == 1
    assert _log(tmp_path / "probe_revise.py") == []
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert not (run_root / "run.json").exists()
    assert (run_root / "memo.jsonl").read_bytes() == b""








def test_evaluated_run_imports_original_old_external_source_root(
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
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule grt/entry) (import shared/types :only (Out)) (export run) '
        '(defworkflow run () -> Out (record Out :value "ok")))\n',
        encoding="utf-8",
    )
    assert entry_target_dsl_version(files["source"]) == "2.35"
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
