"""Reserved public entries compile physically and persist logical recipes."""

from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from orchestrator.cli.commands.prompt_run_service import run_namespace
from orchestrator.cli.commands.run import run_workflow
from orchestrator.run_lock import reserved_run_writer_lock
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_evaluated_cli import PROGRAM
from tests.test_cli_prompt import fake_runtime, MODEL, TASK_TEXT


@pytest.fixture
def reserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".orchestrate/runs/reserved"
    snapshot = root / "snapshot"
    snapshot.mkdir(parents=True)
    (snapshot / "inputs.orc").write_text(PROGRAM.replace("(defmodule evaluated/inputs)", "(defmodule inputs)"))
    (snapshot / "providers.json").write_text("{}")
    (snapshot / "prompts.json").write_text("{}")
    snapshot_fd = os.open(snapshot, os.O_RDONLY | os.O_DIRECTORY)
    physical_root = Path(f"/proc/self/fd/{snapshot_fd}")
    logical = FrontendBuildRequest(
        source_path=snapshot / "inputs.orc", source_roots=(snapshot,),
        provider_externs_path=snapshot / "providers.json",
        prompt_externs_path=snapshot / "prompts.json", workspace_root=tmp_path,
    )
    physical = replace(logical, source_path=physical_root / "inputs.orc",
        source_roots=(physical_root,), provider_externs_path=physical_root / "providers.json",
        prompt_externs_path=physical_root / "prompts.json")
    args = run_namespace(workflow=str(physical.source_path), state_dir=str(root.parent),
        source_root=[str(physical_root)], provider_externs_file=str(physical.provider_externs_path),
        prompt_externs_file=str(physical.prompt_externs_path), input=["score=0.75"],
        physical_build_request=physical, logical_build_request=logical, logical_input_file=None)
    info = root.stat()
    try:
        with reserved_run_writer_lock(root, (info.st_dev, info.st_ino)) as fd:
            yield args, root, snapshot, fd, (info.st_dev, info.st_ino)
            assert os.fstat(fd).st_ino == info.st_ino
    finally:
        os.close(snapshot_fd)


def _run(reserved):
    args, root, snapshot, fd, identity = reserved
    return run_workflow(args, run_id=root.name, expected_run_identity=identity,
        reserved_run_fd=fd, logical_workflow_path=snapshot / "inputs.orc")


def test_reserved_publication_and_runtime_keep_retained_root(reserved):
    result = _run(reserved)
    assert result.exit_code == 0
    args, root, snapshot, fd, identity = reserved
    assert dict(result.workflow_outputs) == {"accepted": True, "score": 0.75}
    assert result.run_root == root
    header = json.loads((root / "run.json").read_bytes())
    assert header["bound_inputs"] == {"score": 0.75, "threshold": 0.5}
    assert read_memo(root / "memo.jsonl", {}).terminal.data["value"] == dict(result.workflow_outputs)
    assert (root / "closed_program.json").is_file()
    assert not (root / "state.json").exists()
    assert not (root / "build").exists()


def test_reserved_recipe_preserves_complete_logical_request(reserved, monkeypatch):
    import builtins
    args, root, snapshot, fd, identity = reserved
    (snapshot / "commands.json").write_text("{}")
    (snapshot / "producer.orc").write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule producer) (export run) (defworkflow run () -> String "unused"))')
    (snapshot / "imports.json").write_text(json.dumps({"unused": {"kind": "compiled", "path": "producer.orc"}}))
    (snapshot / "inputs.json").write_text('{"score":"0.1"}')
    physical_root = args.physical_build_request.source_roots[0]
    args.imported_workflow_bundles_file = str(physical_root / "imports.json")
    args.command_boundaries_file = str(physical_root / "commands.json")
    args.input_file = str(physical_root / "inputs.json")
    args.logical_input_file = snapshot / "inputs.json"
    args.physical_build_request = replace(args.physical_build_request,
        source_roots=(physical_root, physical_root),
        imported_workflow_bundles_path=physical_root / "imports.json",
        command_boundaries_path=physical_root / "commands.json")
    args.logical_build_request = replace(args.logical_build_request,
        source_roots=(snapshot, snapshot),
        imported_workflow_bundles_path=snapshot / "imports.json",
        command_boundaries_path=snapshot / "commands.json")
    args.source_root *= 2
    args.input = ["score=0.2", "score=0.75"]
    reads = []
    real_open = builtins.open

    def observe_input_read(path, *open_args, **kwargs):
        if Path(path) == Path(args.input_file):
            reads.append(path)
        assert Path(path) != args.logical_input_file
        return real_open(path, *open_args, **kwargs)

    monkeypatch.setattr(builtins, "open", observe_input_read)
    result = _run(reserved)
    assert result.exit_code == 0
    assert len(reads) == 1
    header = json.loads((root / "run.json").read_bytes())
    base = ".orchestrate/runs/reserved/snapshot"
    assert header["workflow_file"] == base + "/inputs.orc"
    assert header["resume_request"] == {
        "source_roots": [base, base], "entry_workflow": None,
        "provider_externs_path": base + "/providers.json",
        "prompt_externs_path": base + "/prompts.json",
        "imported_workflow_bundles_path": base + "/imports.json",
        "command_boundaries_path": base + "/commands.json",
        "input_file": base + "/inputs.json", "input_overrides": {"score": "0.75"},
    }
    assert header["bound_inputs"] == {"score": 0.75, "threshold": 0.5}
    # Source diagnostic provenance is not a durable locator or compiler request.
    for path in (root / "run.json", *(snapshot / name for name in
            ("providers.json", "prompts.json", "imports.json", "commands.json"))):
        assert b"/proc/self/fd/" not in path.read_bytes()
        assert b"/dev/fd/" not in path.read_bytes()
    assert not (Path.cwd() / ".orchestrate/build").exists()


def test_snapshot_swap_keeps_original_fd_and_never_reopens_logical_paths(reserved, monkeypatch):
    args, root, snapshot, fd, identity = reserved
    snapshot.rename(root / "original-snapshot")
    snapshot.mkdir()
    (snapshot / "inputs.orc").write_text("malicious replacement")
    real_resolve = Path.resolve

    def reject_logical_resolve(path, *args, **kwargs):
        assert path != snapshot and snapshot not in path.parents
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", reject_logical_resolve)
    result = _run(reserved)
    assert result.exit_code == 0
    assert dict(result.workflow_outputs) == {"accepted": True, "score": 0.75}


@pytest.mark.parametrize("missing", ["physical_build_request", "logical_build_request", "logical_input_file"])
def test_reserved_missing_pair_refuses_before_publication(reserved, missing):
    args, root, *_ = reserved
    delattr(args, missing)
    assert _run(reserved).exit_code != 0
    assert not (root / "run.json").exists()
    assert not (root / "memo.jsonl").exists()


@pytest.mark.parametrize("change", ["roots", "order", "manifest", "source", "entry", "options", "input"])
def test_reserved_incoherent_pair_refuses_before_publication(reserved, change):
    args, root, snapshot, *_ = reserved
    changes = {
        "roots": {"source_roots": (snapshot, snapshot)},
        "order": {"source_roots": (snapshot / "other", snapshot)},
        "manifest": {"provider_externs_path": None},
        "source": {"source_path": snapshot / "different.orc"},
        "entry": {"entry_workflow": "run"},
        "options": {"emit_debug_yaml": True},
        "input": {},
    }
    args.logical_build_request = replace(args.logical_build_request, **changes[change])
    if change == "order":
        physical_root = args.physical_build_request.source_roots[0]
        args.physical_build_request = replace(args.physical_build_request,
            source_roots=(physical_root, physical_root / "other"))
        args.source_root = [str(path) for path in args.physical_build_request.source_roots]
    if change == "input":
        args.input_file = str(args.physical_build_request.source_roots[0] / "missing.json")
    assert _run(reserved).exit_code != 0
    assert not (root / "run.json").exists()
    assert not (root / "memo.jsonl").exists()


@pytest.mark.parametrize("parent_swap", [False, True])
def test_run_root_swap_during_publication_only_writes_original(reserved, monkeypatch, parent_swap):
    args, root, snapshot, *_ = reserved
    real_write = WorkspaceFiles.write_atomic
    original = root.parent.parent / "moved"
    target = root.parent if parent_swap else root

    def swap_then_write(owner, path, content, **kwargs):
        if owner.workspace == root and path == "closed_program.json":
            target.rename(original)
            root.mkdir(parents=True)
        return real_write(owner, path, content, **kwargs)

    monkeypatch.setattr(WorkspaceFiles, "write_atomic", swap_then_write)
    result = _run(reserved)
    assert result.exit_code != 0
    assert list(root.iterdir()) == []
    original_root = original / root.name if parent_swap else original
    assert (original_root / "closed_program.json").is_file()
    assert not (original_root / "run.json").exists()


def test_run_root_swap_during_terminal_append_only_writes_original(reserved, monkeypatch):
    from orchestrator.workflow.evaluated import runtime
    args, root, *_ = reserved
    original = root.parent / "moved"
    real_append = runtime.append_record

    def swap_then_append(path, row, **kwargs):
        if row["record"] == "terminal":
            root.rename(original)
            root.mkdir()
        return real_append(path, row, **kwargs)

    monkeypatch.setattr(runtime, "append_record", swap_then_append)
    assert _run(reserved).exit_code != 0
    assert list(root.iterdir()) == []
    assert read_memo(original / "memo.jsonl", {}).terminal.data["outcome"] == "completed"


def test_public_resume_repair_root_swap_never_truncates_replacement(tmp_path, monkeypatch):
    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.workflow.evaluated import memo
    from tests.test_workflow_evaluated_resume import _completed
    _, root = _completed(tmp_path)
    monkeypatch.chdir(tmp_path)
    journal = root / "memo.jsonl"
    journal.write_bytes(b'{"record":')
    original = root.with_name("original")
    real_open = memo._open_append
    owners = []

    def open_then_swap(path, run_files=None):
        owners.append(run_files)
        fd = real_open(path, run_files)
        root.rename(original)
        root.mkdir()
        journal.write_bytes(b"replacement")
        return fd

    monkeypatch.setattr(memo, "_open_append", open_then_swap)
    assert resume_workflow(root.name) != 0
    assert owners and owners[0] is not None and owners[0].closed
    assert (original / "memo.jsonl").read_bytes() == b""
    assert journal.read_bytes() == b"replacement"
    assert sorted(path.name for path in root.iterdir()) == ["memo.jsonl"]


@pytest.mark.parametrize("stage", ["pre-lock", "post-lock", "wrong-fd"])
def test_reserved_root_checks_refuse_before_publication(reserved, stage):
    args, root, snapshot, fd, identity = reserved
    if stage == "wrong-fd":
        wrong_fd = os.open(snapshot, os.O_RDONLY | os.O_DIRECTORY)
        try:
            result = run_workflow(args, run_id=root.name, expected_run_identity=identity, reserved_run_fd=wrong_fd)
        finally:
            os.close(wrong_fd)
    else:
        root.rename(root.parent / "original")
        root.mkdir()
        result = run_workflow(args, run_id=root.name, expected_run_identity=identity,
            reserved_run_fd=None if stage == "pre-lock" else fd)
    assert result.exit_code != 0
    assert not (root / "run.json").exists()
    assert not (root / "memo.jsonl").exists()
    if stage != "wrong-fd":
        assert list(root.iterdir()) == []


def test_reserved_completed_public_resume_uses_same_recipe_without_writes(tmp_path, monkeypatch):
    from orchestrator.cli.commands.resume import resume_workflow
    from tests.test_workflow_evaluated_resume import _snapshot
    from tests.test_workflow_evaluated_cli import _build
    source, _ = _build(tmp_path)
    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".orchestrate/runs/reserved"
    root.mkdir(parents=True)
    info = root.stat()
    request = FrontendBuildRequest(source_path=source, workspace_root=tmp_path)
    args = run_namespace(workflow=str(source), state_dir=str(root.parent), input=["score=0.75"],
        physical_build_request=request, logical_build_request=request, logical_input_file=None)
    with reserved_run_writer_lock(root, (info.st_dev, info.st_ino)) as fd:
        assert run_workflow(args, run_id=root.name, expected_run_identity=(info.st_dev, info.st_ino),
            reserved_run_fd=fd).exit_code == 0
    before = _snapshot(root)
    for _ in range(2):
        assert resume_workflow(root.name) == 0
        assert _snapshot(root) == before


def test_reserved_internal_snapshot_resume_reopens_only_through_new_root_fd(tmp_path, monkeypatch):
    import builtins
    import io
    from orchestrator.cli.commands.resume import resume_workflow
    from tests.test_workflow_evaluated_resume import _snapshot
    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".orchestrate/runs/reserved"
    snapshot = root / "snapshot"
    snapshot.mkdir(parents=True)
    (snapshot / "inputs.orc").write_text(PROGRAM.replace("(defmodule evaluated/inputs)", "(defmodule inputs)"))
    (snapshot / "providers.json").write_text("{}")
    (snapshot / "prompts.json").write_text("{}")
    (snapshot / "inputs.json").write_text('{"score":"0.75"}')
    info = root.stat()
    snapshot_fd = os.open(snapshot, os.O_RDONLY | os.O_DIRECTORY)
    physical_root = Path(f"/proc/self/fd/{snapshot_fd}")
    logical = FrontendBuildRequest(source_path=snapshot / "inputs.orc", source_roots=(snapshot,),
        provider_externs_path=snapshot / "providers.json", prompt_externs_path=snapshot / "prompts.json",
        workspace_root=tmp_path)
    physical = replace(logical, source_path=physical_root / "inputs.orc", source_roots=(physical_root,),
        provider_externs_path=physical_root / "providers.json", prompt_externs_path=physical_root / "prompts.json")
    args = run_namespace(workflow=str(physical.source_path), state_dir=str(root.parent),
        source_root=[str(physical_root)], provider_externs_file=str(physical.provider_externs_path),
        prompt_externs_file=str(physical.prompt_externs_path), input_file=str(physical_root / "inputs.json"),
        physical_build_request=physical, logical_build_request=logical, logical_input_file=snapshot / "inputs.json")
    try:
        with reserved_run_writer_lock(root, (info.st_dev, info.st_ino)) as fd:
            assert run_workflow(args, run_id=root.name, expected_run_identity=(info.st_dev, info.st_ino), reserved_run_fd=fd).exit_code == 0
    finally:
        os.close(snapshot_fd)
    before = _snapshot(root)
    real_open, real_builtin_open, real_io_open = os.open, builtins.open, io.open

    def reject_logical_open(path, *args, **kwargs):
        assert not Path(path).is_relative_to(snapshot)
        return real_open(path, *args, **kwargs)

    def reject_logical_builtin_open(path, *args, **kwargs):
        assert not Path(path).is_relative_to(snapshot)
        return real_builtin_open(path, *args, **kwargs)

    def reject_logical_io_open(path, *args, **kwargs):
        if not isinstance(path, int):
            assert not Path(path).is_relative_to(snapshot)
        return real_io_open(path, *args, **kwargs)

    for _ in range(2):
        with monkeypatch.context() as guard:
            guard.setattr(os, "open", reject_logical_open)
            guard.setattr(builtins, "open", reject_logical_builtin_open)
            guard.setattr(io, "open", reject_logical_io_open)
            assert resume_workflow(root.name) == 0
        assert _snapshot(root) == before


def test_both_prompt_callers_supply_complete_requests_at_target_227(tmp_path, monkeypatch, fake_runtime):
    from orchestrator.cli.main import main
    from orchestrator.cli.commands import prompt_run_service, prompt
    from orchestrator.workflow_lisp.closed.target import entry_target_dsl_version
    seen = []

    def record_request(args, **kwargs):
        seen.append((args, kwargs))
        assert isinstance(getattr(args, "physical_build_request", None), FrontendBuildRequest)
        assert isinstance(getattr(args, "logical_build_request", None), FrontendBuildRequest)
        physical, logical = args.physical_build_request, args.logical_build_request
        assert physical.source_path == Path(args.workflow)
        assert logical.source_path == kwargs["logical_workflow_path"]
        assert physical.source_roots == (physical.source_path.parent,)
        assert logical.source_roots == (logical.source_path.parent,)
        assert physical.provider_externs_path == physical.source_path.parent / "providers.json"
        assert logical.prompt_externs_path == logical.source_path.parent / "prompts.json"
        assert physical.imported_workflow_bundles_path is logical.imported_workflow_bundles_path is None
        assert physical.command_boundaries_path is logical.command_boundaries_path is None
        assert physical.entry_workflow is logical.entry_workflow is None
        assert args.input_file is args.logical_input_file is None
        assert entry_target_dsl_version(physical.source_path) == "2.27"
        return run_workflow(args, **kwargs)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(prompt_run_service, "run_workflow", record_request)
    monkeypatch.setattr(prompt, "run_workflow", record_request)
    exit_code = main(["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools", "--model", MODEL, "--output", "a text greeting"])
    assert exit_code == 0
    assert len(seen) == 2
    assert [Path(args.workflow).name for args, _ in seen] == ["infer-output-contract.orc", "run.orc"]
