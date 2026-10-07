from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestrator._common import io_atomic
import orchestrator.workflow.workspace_files as workspace_files_module
import orchestrator.workflow.evaluated.authority as authority_module
from orchestrator.workflow.evaluated.authority import (
    RunAuthorityError,
    load_run_authority,
    publish_run_authority,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from tests.test_workflow_evaluated_cli import _build
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle


@pytest.fixture(scope="module")
def program(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("closed-authority-program")
    source = workspace / "authority" / "pure.orc"
    source.parent.mkdir()
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule authority/pure) (export run) '
        '(defworkflow run () -> String "ok"))\n',
        encoding="utf-8",
    )
    return build_closed_program_bundle(
        FrontendBuildRequest(source_path=source, workspace_root=workspace)
    ).program


def _publish(run_root: Path, program) -> None:
    source_digest = "sha256:" + hashlib.sha256(b"source").hexdigest()
    with publish_run_authority(
        run_root,
        program,
        run_id=run_root.name,
        workflow_file="pure.orc",
        workflow_checksum=source_digest,
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs={},
    ):
        pass


def _float_input_program(root: Path):
    source = root / "authority" / "inputs.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule authority/inputs) (export run) '
        '(defworkflow run ((score Float)) -> Float score))\n',
        encoding="utf-8",
    )
    return build_closed_program_bundle(
        FrontendBuildRequest(source_path=source, workspace_root=root)
    ).program


def test_publish_pins_the_checked_program_and_empty_memo(tmp_path: Path, program) -> None:
    run_root = tmp_path / "runs" / "pure-1"

    _publish(run_root, program)
    authority = load_run_authority(run_root)

    assert authority.header["result_persistence_profile"] == "evaluated_execution.v1"
    assert authority.header["schema_version"] == "3.0"
    assert authority.header["program_digest"] == program.digest
    assert authority.header["representation"] == "table/1"
    assert authority.header["bound_inputs"] == {}
    assert authority.header["interpreters"] == {}
    assert authority.program.digest == program.digest
    assert authority.memo_path.read_bytes() == b""


def test_publish_syncs_ancestors_created_by_the_preceding_build(
    tmp_path: Path, program, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / ".orchestrate"
    (state_root / "build").mkdir(parents=True)
    synced: list[Path] = []
    original = authority_module._sync_directory

    def record_sync(path: Path) -> None:
        synced.append(path)
        original(path)

    monkeypatch.setattr(authority_module, "_sync_directory", record_sync)
    run_root = state_root / "runs" / "prior-build-root"

    _publish(run_root, program)

    assert state_root in synced
    assert tmp_path in synced
    assert synced.index(state_root) < synced.index(tmp_path)
    assert run_root.parent in synced
    assert run_root in synced


def test_corrupt_authority_refuses_without_rewriting_evidence(tmp_path: Path, program) -> None:
    run_root = tmp_path / "runs" / "pure-2"
    _publish(run_root, program)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["program_digest"] = "sha256:" + "0" * 64
    header_path.write_text(json.dumps(header), encoding="utf-8")
    before = {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }

    with pytest.raises(RunAuthorityError) as excinfo:
        load_run_authority(run_root)

    assert excinfo.value.code == "memo_inconsistent"
    assert before == {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "9.0"),
        ("result_persistence_profile", "legacy"),
        ("runtime_selector", "legacy"),
    ],
)
def test_unknown_authority_selectors_refuse_without_rewriting_evidence(
    tmp_path: Path, program, field: str, value: str
) -> None:
    run_root = tmp_path / "runs" / field
    _publish(run_root, program)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header[field] = value
    header_path.write_text(json.dumps(header), encoding="utf-8")
    before = {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }

    with pytest.raises(RunAuthorityError):
        load_run_authority(run_root)

    assert before == {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }


def test_missing_header_with_journal_activity_is_inconsistent_without_repair(
    tmp_path: Path, program
) -> None:
    run_root = tmp_path / "runs" / "missing-header"
    _publish(run_root, program)
    header_path = run_root / "run.json"
    header_path.unlink()
    memo_path = run_root / "memo.jsonl"
    memo_path.write_bytes(b"unrecognized but nonempty activity\n")
    before_memo = memo_path.read_bytes()
    before_program = (run_root / "closed_program.json").read_bytes()

    with pytest.raises(RunAuthorityError) as excinfo:
        load_run_authority(run_root)

    assert excinfo.value.code == "memo_inconsistent"
    assert not header_path.exists()
    assert memo_path.read_bytes() == before_memo
    assert (run_root / "closed_program.json").read_bytes() == before_program


@pytest.mark.parametrize("invalid", ["wrong-type", "overflow-float"])
def test_rehashed_incompatible_or_nonfinite_inputs_refuse_without_mutation(
    tmp_path: Path, invalid: str
) -> None:
    program = _float_input_program(tmp_path)
    run_root = tmp_path / "runs" / invalid
    with publish_run_authority(
        run_root,
        program,
        run_id=run_root.name,
        workflow_file="inputs.orc",
        workflow_checksum="sha256:" + "0" * 64,
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs={"score": 0.5},
    ):
        pass
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    bad_value = "not-float" if invalid == "wrong-type" else float("inf")
    header["bound_inputs"] = {"score": bad_value}
    header["input_digest"] = canonical_sha256(header["bound_inputs"])
    raw = canonical_json_bytes(header)
    if invalid == "overflow-float":
        raw = raw.replace(b'"score":Infinity', b'"score":1e999')
    header_path.write_bytes(raw)
    before = {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }

    with pytest.raises(RunAuthorityError):
        load_run_authority(run_root)

    assert before == {
        path.name: path.read_bytes()
        for path in (header_path, run_root / "closed_program.json", run_root / "memo.jsonl")
    }


@pytest.mark.parametrize("fail_at", [1, 2])
def test_each_authority_file_write_failure_prevents_memo_activity(
    tmp_path: Path, program, monkeypatch: pytest.MonkeyPatch, fail_at: int
) -> None:
    original = workspace_files_module.shutil.copyfileobj
    calls = 0

    def fail_selected_write(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise OSError("injected file-write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(workspace_files_module.shutil, "copyfileobj", fail_selected_write)
    run_root = tmp_path / "runs" / f"write-{fail_at}"

    with pytest.raises(OSError, match="injected file-write failure"):
        _publish(run_root, program)

    memo = run_root / "memo.jsonl"
    assert not memo.exists() or memo.read_bytes() == b""


def test_each_authority_fsync_failure_prevents_memo_activity(
    tmp_path: Path, program, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = tmp_path / "runs" / "fsync-count"
    original = io_atomic.os.fsync
    calls = 0

    def count_sync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        original(descriptor)

    monkeypatch.setattr(io_atomic.os, "fsync", count_sync)
    _publish(run_root, program)
    boundary_count = calls
    assert boundary_count >= 8

    for fail_at in range(1, boundary_count + 1):
        case_root = tmp_path / "runs" / f"fsync-{fail_at}"
        calls = 0

        def fail_selected_sync(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == fail_at:
                raise OSError("injected fsync failure")
            original(descriptor)

        monkeypatch.setattr(io_atomic.os, "fsync", fail_selected_sync)
        with pytest.raises(OSError, match="injected fsync failure"):
            _publish(case_root, program)
        memo = case_root / "memo.jsonl"
        assert not memo.exists() or memo.read_bytes() == b""


@pytest.mark.parametrize("fail_at", [1, 2])
def test_each_authority_rename_failure_prevents_memo_activity(
    tmp_path: Path, program, monkeypatch: pytest.MonkeyPatch, fail_at: int
) -> None:
    original = io_atomic.os.replace
    calls = 0

    def fail_selected_rename(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise OSError("injected rename failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(io_atomic.os, "replace", fail_selected_rename)
    run_root = tmp_path / "runs" / f"rename-{fail_at}"

    with pytest.raises(OSError, match="injected rename failure"):
        _publish(run_root, program)

    memo = run_root / "memo.jsonl"
    assert not memo.exists() or memo.read_bytes() == b""


@pytest.mark.parametrize('locator', ['', 'a/../b', '../a', './a', 'a//b', 'a/', '/tmp/../a',
                                      '/proc/self/fd/4/a', '/dev/fd/4/a', 'a\x00b'])
def test_malformed_recipe_locators_refuse_at_publication_before_root(tmp_path, locator):
    from orchestrator.workflow.evaluated.authority import publish_run_authority, RunAuthorityError
    _, program = _build(tmp_path)
    recipe = {'source_roots': [locator], 'entry_workflow': None,
              'provider_externs_path': None, 'prompt_externs_path': None,
              'command_boundaries_path': None, 'imported_workflow_bundles_path': None,
              'input_file': None, 'input_overrides': {}}
    root = tmp_path / 'absent-parent' / 'run'
    with pytest.raises(RunAuthorityError):
        with publish_run_authority(root, program, run_id='run', workflow_file='evaluated/inputs.orc',
                                   workflow_checksum='sha256:' + '0' * 64,
                                   bound_inputs={'score': 0.75, 'threshold': 0.5}, resume_request=recipe):
            pytest.fail('invalid recipe was published')
    assert not root.parent.exists()


def test_nontransportable_override_refuses_before_creating_any_run_directory(tmp_path):
    from orchestrator.workflow.evaluated.authority import publish_run_authority, RunAuthorityError
    _, program = _build(tmp_path)
    recipe = {'source_roots': [], 'entry_workflow': None, 'provider_externs_path': None,
              'prompt_externs_path': None, 'command_boundaries_path': None,
              'imported_workflow_bundles_path': None, 'input_file': None,
              'input_overrides': {'unused': '\ud800'}}
    root = tmp_path / 'absent-parent' / 'run'
    with pytest.raises(RunAuthorityError):
        with publish_run_authority(root, program, run_id='run', workflow_file='evaluated/inputs.orc',
                                   workflow_checksum='sha256:' + '0' * 64,
                                   bound_inputs={'score': 0.75, 'threshold': 0.5}, resume_request=recipe):
            pytest.fail('invalid UTF-8 JSON was published')
    assert not root.parent.exists()
