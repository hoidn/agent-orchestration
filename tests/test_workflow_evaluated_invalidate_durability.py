from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

import orchestrator.cli.commands.invalidate as invalidate_module
import orchestrator.workflow.evaluated.memo as memo_module
from orchestrator.workflow.evaluated.authority import (
    load_run_authority,
    publish_run_authority,
)
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import (
    MemoError,
    append_record,
    memo_writer_lock,
)
from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow_lisp.closed.sites import assign_sites
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.config import encode_run_ref_static_config
from orchestrator.workflow_lisp.closed.names import canonical_run_ref_signature
from tests.test_workflow_evaluated_invalidate import (
    _cli,
    _completed_run,
    _memo,
    _tree_bytes,
)
from tests.test_workflow_evaluated_memo_writes import (
    _committed,
    _run_ref_proof,
    _started,
)
from tests.test_workflow_lisp_closed_program_artifact import _closed
from tests.test_workflow_lisp_closed_program_check import (
    INT,
    _build_run_ref_config,
    _register_nominal_types,
    _run_ref_tree,
)
from orchestrator.workflow_lisp.closed.check import validate


def _command_then_coordinator_program(root: Path):
    command_root = root / "command-source"
    command_root.mkdir()
    command_run = _completed_run(command_root)
    command_program = load_run_authority(command_run).program
    command_effect = deepcopy(command_program.tree["body"]["value"])
    assert command_effect["k"] == "perform"

    tree, run_ref, original_config = _run_ref_tree()
    tree["configuration"]["commands"] = deepcopy(
        command_program.tree["configuration"]["commands"]
    )
    tree["body"] = {
        "k": "let",
        "name": "prior_command",
        "value": command_effect,
        "body": tree["body"],
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    inputs = tuple((row.name, row.type_descriptor) for row in original_config.inputs)
    signature = canonical_run_ref_signature(
        inputs,
        original_config.result_descriptor,
        run_ref_signatures={},
    )
    site_digest = sha256(
        canonical_json_for_pure_value(
            ["workflow-lisp/run-ref-site/1", tree["entry"], run_ref["site"], signature]
        ).encode("utf-8")
    ).hexdigest()
    config = _build_run_ref_config(site_digest, inputs, value_type=INT)
    run_ref["config"] = base64.b64encode(encode_run_ref_static_config(config)).decode("ascii")
    run_ref["result"] = deepcopy(config.result_descriptor["envelope"])
    tree["result"] = deepcopy(run_ref["result"])
    tree["types"].pop(original_config.generated_result_type, None)
    _register_nominal_types(run_ref["result"], tree["types"])
    validate(tree)
    return _closed(tree)


def _publish_command_then_coordinator(root: Path) -> tuple[Path, str, str]:
    program = _command_then_coordinator_program(root)
    run_root = root / ".orchestrate" / "runs" / "coordinator-suffix"
    recipe = {
        "source_roots": [], "entry_workflow": None,
        "provider_externs_path": None, "prompt_externs_path": None,
        "imported_workflow_bundles_path": None, "command_boundaries_path": None,
        "input_file": None, "input_overrides": {},
    }
    with publish_run_authority(
        run_root,
        program,
        run_id=run_root.name,
        workflow_file="coordinator-suffix.orc",
        workflow_checksum=canonical_sha256("coordinator suffix"),
        bound_inputs={"source": 3},
        resume_request=recipe,
    ) as authority:
        classes = site_classes(authority.program)
        command_id = next(identity for identity, kind in classes.items() if kind == "command")
        coordinator_id = next(identity for identity, kind in classes.items() if kind == "run_ref")
        append_record(authority.memo_path, _started(command_id))
        append_record(authority.memo_path, _committed(command_id))
        append_record(authority.memo_path, _started(coordinator_id))
        append_record(
            authority.memo_path,
            _committed(
                coordinator_id,
                effect_class="run_ref",
                proof=_run_ref_proof(coordinator_id, root),
            ),
        )
    return run_root, command_id, coordinator_id


def test_public_invalidate_refuses_checked_coordinator_after_command_before_tail_repair(
    tmp_path: Path,
) -> None:
    run_root, command_id, coordinator_id = _publish_command_then_coordinator(tmp_path)
    _rows, snapshot = _memo(run_root)
    assert snapshot.active_commits[command_id].offset < snapshot.active_commits[coordinator_id].offset
    with (run_root / "memo.jsonl").open("ab") as stream:
        stream.write(b'{"record":"partial"')
    (run_root / "state.json").write_text('{"status":"stale"}', encoding="utf-8")
    before = _tree_bytes(tmp_path / ".orchestrate")
    memo_before = (run_root / "memo.jsonl").read_bytes()

    command_target = _cli(tmp_path, "invalidate", run_root.name, command_id)
    coordinator_target = _cli(tmp_path, "invalidate", run_root.name, coordinator_id)

    assert command_target.returncode == 2
    assert coordinator_target.returncode == 2
    assert "invalidate_coordinator_committed" in command_target.stderr
    assert "invalidate_coordinator_committed" in coordinator_target.stderr
    assert (run_root / "memo.jsonl").read_bytes() == memo_before
    assert _tree_bytes(tmp_path / ".orchestrate") == before


def test_public_invalidate_service_acquires_the_run_writer_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = _completed_run(tmp_path)
    _rows, snapshot = _memo(run_root)
    identity = next(iter(snapshot.active_commits))
    before = _tree_bytes(tmp_path / ".orchestrate")
    monkeypatch.chdir(tmp_path)

    with memo_writer_lock(run_root):
        with pytest.raises(MemoError) as error:
            invalidate_module.invalidate_run(run_root.name, identity)

    assert error.value.code == "memo_busy"
    assert _tree_bytes(tmp_path / ".orchestrate") == before


def test_public_service_partial_write_leaves_tail_then_next_call_preflights_and_repairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = _completed_run(tmp_path)
    _rows, snapshot = _memo(run_root)
    identity = next(iter(snapshot.active_commits))
    journal = run_root / "memo.jsonl"
    prefix = journal.read_bytes()

    real_write = memo_module.os.write

    def short_write(fd: int, data: bytes) -> int:
        return real_write(fd, data[:5])

    with monkeypatch.context() as patched:
        patched.setattr(memo_module.os, "write", short_write)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(MemoError) as error:
            invalidate_module.invalidate_run(run_root.name, identity)
    assert error.value.code == "memo_write_failed"
    partial = journal.read_bytes()
    assert partial.startswith(prefix)
    assert len(partial[len(prefix):]) == 5
    assert partial[len(prefix):].startswith(b'{')
    _rows, pending = _memo(run_root)
    assert pending.tail == partial[len(prefix):]
    assert identity in pending.active_commits

    monkeypatch.chdir(tmp_path)
    record = invalidate_module.invalidate_run(run_root.name, identity)

    assert record["record"] == "invalidated"
    assert journal.read_bytes().startswith(prefix)
    _rows, repaired = _memo(run_root)
    assert repaired.tail == b""
    assert not repaired.active_commits


def test_public_service_fsync_failure_leaves_one_complete_visible_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = _completed_run(tmp_path)
    _rows, snapshot = _memo(run_root)
    identity = next(iter(snapshot.active_commits))
    journal = run_root / "memo.jsonl"

    def fail_fsync(_fd: int) -> None:
        raise OSError("injected fsync failure")

    with monkeypatch.context() as patched:
        patched.setattr(memo_module.os, "fsync", fail_fsync)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(MemoError) as error:
            invalidate_module.invalidate_run(run_root.name, identity)

    assert error.value.code == "memo_sync_failed"
    _rows, after = _memo(run_root)
    assert not after.tail
    assert not after.active_commits
    assert [entry.data["record"] for entry in after.entries].count("invalidated") == 1
