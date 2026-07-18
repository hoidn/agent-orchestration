"""Functional immutable evidence for provider prompt dependencies."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import multiprocessing
from pathlib import Path
import time

import pytest

from orchestrator.deps.content_snapshot import (
    AuthoredDependencyRow,
    DependencyContent,
    build_content_snapshot,
    render_content_snapshot,
)
from orchestrator.state import RunState, StateManager
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _reseal(record: dict) -> dict:
    payload = deepcopy(record)
    payload.pop("record_sha256", None)
    record["record_sha256"] = _sha(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    )
    return record


def _reseal_index(index: dict) -> dict:
    payload = deepcopy(index)
    payload.pop("index_sha256", None)
    index["index_sha256"] = _sha(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    )
    return index


def _contract(*, authored_instruction: bool = True):
    return _build_compiler_prompt_dependency_contract(
        required_binding_refs=("required-document",),
        optional_binding_refs=("optional-notes",),
        position=PromptDependencyPosition.PREPEND,
        instruction="Read these inputs." if authored_instruction else None,
        source_origin_key="provider-result",
        source_workflow_bytes=b"(workflow evidence)",
    )


def _scope() -> ProviderAttemptScope:
    return ProviderAttemptScope.from_dict(
        {
            "run_id": "20260718T000000Z-evid1",
            "resume_scope": {
                "root_workflow_file": "workflow.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "ProviderStep",
            "enclosing_step": {
                "step_name": "Provider",
                "step_id": "ProviderStep",
                "visit_count": 2,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )


def _snapshot_and_render():
    rows = (
        AuthoredDependencyRow(
            "required", 0, "required-document", "inputs/document.md", "inputs/document.md"
        ),
        AuthoredDependencyRow(
            "optional", 0, "optional-notes", "inputs/missing.md", None
        ),
    )
    snapshot = build_content_snapshot(
        rows,
        (DependencyContent("inputs/document.md", b"alpha\r\nbeta\n"),),
    )
    rendered = render_content_snapshot(snapshot, "Read these inputs.")
    return snapshot, rendered


def _run_state(root: str | Path = "/tmp/aggregate-run") -> RunState:
    return RunState(
        schema_version="2.1",
        run_id=_scope().run_id,
        workflow_file="workflow.orc",
        workflow_checksum="sha256:" + "1" * 64,
        started_at="2026-07-18T00:00:00+00:00",
        updated_at="2026-07-18T00:00:00+00:00",
        status="running",
        run_root=str(root),
    )


def _success_record(
    *,
    ordinal: int = 3,
    root: str | Path = "/tmp/aggregate-run",
    run_state: RunState | None = None,
    final_prompt: bytes = b"Read these inputs.\n\nbase prompt",
):
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    snapshot, _ = _snapshot_and_render()
    return build_success_evidence(
        run_state=run_state or _run_state(root),
        scope=_scope(),
        ordinal=ordinal,
        compiler_contract=_contract(),
        snapshot=snapshot,
        instruction="Read these inputs.",
        instruction_source="authored",
        compose_final_prompt=lambda _rendered: final_prompt,
    ).evidence


def test_success_record_is_closed_content_free_and_self_validating() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        SUCCESS_SCHEMA,
        canonical_record_bytes,
        validate_success_evidence,
    )

    record = _success_record()
    assert set(record) == {
        "schema", "record_kind", "run", "compiler_contract", "attempt", "authored_rows",
        "canonical_groups", "instruction", "injection", "final_prompt",
        "record_sha256",
    }
    assert record["schema"] == SUCCESS_SCHEMA
    assert record["record_kind"] == "prompt_snapshot"
    assert record["run"] == {
        "run_id": _scope().run_id,
        "workflow_file": "workflow.orc",
        "workflow_checksum": "sha256:" + "1" * 64,
    }
    assert record["authored_rows"][0]["row_id"].startswith("sha256:")
    assert record["attempt"]["ordinal"] == 3
    assert record["authored_rows"][1]["status"] == "absent"
    assert record["canonical_groups"][0]["retained_sha256"] == _sha(b"alpha\r\nbeta\n")
    assert record["instruction"] == {
        "source": "authored",
        "bytes": len(b"Read these inputs."),
        "sha256": _sha(b"Read these inputs."),
    }
    assert canonical_record_bytes(record).endswith(b"}")
    assert not canonical_record_bytes(record).endswith(b"\n")
    serialized = canonical_record_bytes(record)
    assert b"alpha" not in serialized
    assert b"base prompt" not in serialized
    assert validate_success_evidence(record) == record


def test_success_build_operation_renders_exactly_once_and_returns_authoritative_render(
    monkeypatch,
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    snapshot, _ = _snapshot_and_render()
    actual_render = evidence.render_content_snapshot
    calls: list[tuple[object, object]] = []

    def counted_render(snapshot_arg, instruction_arg):
        calls.append((snapshot_arg, instruction_arg))
        return actual_render(snapshot_arg, instruction_arg)

    monkeypatch.setattr(evidence, "render_content_snapshot", counted_render)
    result = evidence.build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=_contract(), snapshot=snapshot,
        instruction="Read these inputs.", instruction_source="authored",
        compose_final_prompt=lambda authoritative: authoritative.block + b"\n\nbase",
    )
    assert len(calls) == 1
    assert result.rendered == actual_render(snapshot, "Read these inputs.")
    assert result.final_prompt == result.rendered.block + b"\n\nbase"
    assert result.evidence["injection"]["block_sha256"] == _sha(result.rendered.block)
    assert result.evidence["final_prompt"]["sha256"] == _sha(result.final_prompt)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("attempt", "ordinal"), 0),
        (("authored_rows", 0, "binding_ref"), "wrong"),
        (("canonical_groups", 0, "shown_bytes"), 999),
        (("instruction", "source"), "default_optional"),
        (("injection", "position"), "append"),
        (("final_prompt", "sha256"), "sha256:" + "0" * 64),
    ],
)
def test_success_validator_rejects_cross_field_or_digest_tampering(path, replacement) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = deepcopy(_success_record())
    cursor = record
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = replacement
    with pytest.raises(ValueError):
        validate_success_evidence(record)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda record: record["compiler_contract"].__setitem__("origin_kind", "other"), "compiler"),
        (lambda record: record["authored_rows"][0].__setitem__("status", "absent"), "required"),
        (lambda record: record["canonical_groups"][0].__setitem__("effective_role", "optional"), "role"),
        (lambda record: record["canonical_groups"][0].__setitem__("shown_sha256", None), "digest"),
        (lambda record: record["injection"].__setitem__("mode", "list"), "injection"),
    ],
)
def test_success_validator_rejects_internally_resealed_contract_tampering(mutate, message) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = _success_record()
    mutate(record)
    _reseal(record)
    with pytest.raises(ValueError, match=message):
        validate_success_evidence(record)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: record["instruction"].__setitem__("bytes", 261631),
        lambda record: record["injection"].__setitem__("summary_bytes", 513),
        lambda record: record["injection"].__setitem__("pre_truncation_bytes", 1),
        lambda record: record["injection"].__setitem__("block_bytes", 1),
        lambda record: record["injection"].__setitem__(
            "pre_truncation_bytes", record["injection"]["block_bytes"] + 1
        ),
        lambda record: record["authored_rows"][0].__setitem__("authored_index", False),
        lambda record: record["canonical_groups"][0].__setitem__("order", False),
    ],
)
def test_success_validator_rejects_internally_resealed_byte_cap_violations(mutate) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = _success_record()
    mutate(record)
    _reseal(record)
    with pytest.raises(ValueError):
        validate_success_evidence(record)


def test_success_groups_may_be_lexical_when_authored_target_order_differs() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=("z-binding", "a-binding"), optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND, instruction="Read.",
        source_origin_key="provider-result", source_workflow_bytes=b"workflow",
    )
    snapshot = build_content_snapshot(
        (
            AuthoredDependencyRow("required", 0, "z-binding", "z.txt", "z.txt"),
            AuthoredDependencyRow("required", 1, "a-binding", "a.txt", "a.txt"),
        ),
        (DependencyContent("z.txt", b"z"), DependencyContent("a.txt", b"a")),
    )
    record = build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=contract, snapshot=snapshot,
        instruction="Read.", instruction_source="authored",
        compose_final_prompt=lambda _rendered: b"final",
    ).evidence
    assert [group["canonical_target"] for group in record["canonical_groups"]] == ["a.txt", "z.txt"]


def _three_group_success_record() -> dict:
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=("a", "b", "c"), optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND, instruction="Read.",
        source_origin_key="provider-result", source_workflow_bytes=b"workflow",
    )
    snapshot = build_content_snapshot(
        tuple(
            AuthoredDependencyRow("required", index, name, f"{name}.txt", f"{name}.txt")
            for index, name in enumerate(("a", "b", "c"))
        ),
        tuple(DependencyContent(f"{name}.txt", name.encode() * 2) for name in ("a", "b", "c")),
    )
    return build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=contract, snapshot=snapshot, instruction="Read.",
        instruction_source="authored",
        compose_final_prompt=lambda rendered: rendered.block + b"\nbase",
    ).evidence


def _make_resealed_truncated_injection(record: dict) -> None:
    injection = record["injection"]
    injection["was_truncated"] = True
    injection["pre_truncation_bytes"] = injection["block_bytes"] + 1
    injection["summary_bytes"] = 1
    injection["summary_sha256"] = _sha(b"s")


def test_success_validator_rejects_omitted_group_before_complete_group() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = _three_group_success_record()
    first = record["canonical_groups"][0]
    first["render_status"] = "omitted"
    first["shown_bytes"] = 0
    first["shown_sha256"] = None
    injection = record["injection"]
    injection["shown_bytes"] -= first["normalized_total_bytes"]
    injection["files_shown"] = 2
    injection["files_omitted"] = 1
    _make_resealed_truncated_injection(record)
    _reseal(record)
    with pytest.raises(ValueError, match="order"):
        validate_success_evidence(record)


def test_success_validator_rejects_multiple_truncated_groups() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = _three_group_success_record()
    for group in record["canonical_groups"][1:]:
        group["render_status"] = "truncated"
        group["shown_bytes"] = 1
        group["shown_sha256"] = _sha(group["canonical_target"][0].encode())
    injection = record["injection"]
    injection["shown_bytes"] = 4
    injection["files_truncated"] = 2
    _make_resealed_truncated_injection(record)
    _reseal(record)
    with pytest.raises(ValueError, match="truncated"):
        validate_success_evidence(record)


@pytest.mark.parametrize(
    ("sizes", "expected_statuses"),
    [
        ((16, 262144, 10), ["complete", "truncated", "omitted"]),
        ((261960, 1000), ["complete", "omitted"]),
    ],
)
def test_success_builder_accepts_real_renderer_disposition_sequences(
    sizes, expected_statuses
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_success_evidence,
        validate_success_evidence,
    )

    names = tuple(chr(ord("a") + index) for index in range(len(sizes)))
    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=names, optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND, instruction="Read.",
        source_origin_key="provider-result", source_workflow_bytes=b"workflow",
    )
    snapshot = build_content_snapshot(
        tuple(
            AuthoredDependencyRow("required", index, name, f"{name}.txt", f"{name}.txt")
            for index, name in enumerate(names)
        ),
        tuple(
            DependencyContent(f"{name}.txt", name.encode() * size)
            for name, size in zip(names, sizes)
        ),
    )
    result = build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=contract, snapshot=snapshot, instruction="Read.",
        instruction_source="authored",
        compose_final_prompt=lambda rendered: rendered.block + b"\nbase",
    )
    assert [row.status for row in result.rendered.group_truncations] == expected_statuses
    assert [group["render_status"] for group in result.evidence["canonical_groups"]] == expected_statuses
    assert validate_success_evidence(result.evidence) == result.evidence


@pytest.mark.parametrize("invalid", [3, True, [65, 66]])
def test_success_builder_requires_exact_final_prompt_bytes(invalid) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    snapshot, _ = _snapshot_and_render()
    with pytest.raises(TypeError, match="final_prompt"):
        build_success_evidence(
            run_state=_run_state(), scope=_scope(), ordinal=1,
            compiler_contract=_contract(), snapshot=snapshot,
            instruction="Read these inputs.", instruction_source="authored",
            compose_final_prompt=lambda _rendered: invalid,
        )

def test_default_instruction_source_is_derived_from_compiler_contract() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    snapshot, _ = _snapshot_and_render()
    contract = _contract(authored_instruction=False)
    instruction = "Default required instruction."
    rendered = render_content_snapshot(snapshot, instruction)
    build = build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=contract, snapshot=snapshot,
        instruction=instruction, instruction_source="default_required",
        compose_final_prompt=lambda authoritative: authoritative.block + b"\n\nbase",
    )
    assert build.evidence["instruction"]["source"] == "default_required"
    assert build.rendered == rendered
    with pytest.raises(ValueError, match="source"):
        build_success_evidence(
            run_state=_run_state(), scope=_scope(), ordinal=1,
            compiler_contract=contract, snapshot=snapshot,
            instruction=instruction, instruction_source="default_optional",
            compose_final_prompt=lambda _rendered: b"base",
        )

    optional_contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=(),
        optional_binding_refs=("optional-notes",),
        position=PromptDependencyPosition.PREPEND,
        instruction=None,
        source_origin_key="provider-result",
        source_workflow_bytes=b"(workflow evidence)",
    )
    optional_snapshot = build_content_snapshot(
        (
            AuthoredDependencyRow(
                "optional", 0, "optional-notes", "inputs/notes.md", "inputs/notes.md"
            ),
        ),
        (DependencyContent("inputs/notes.md", b"notes"),),
    )
    optional_instruction = "Default optional instruction."
    optional = build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=optional_contract, snapshot=optional_snapshot,
        instruction=optional_instruction,
        instruction_source="default_optional",
        compose_final_prompt=lambda _rendered: b"base",
    )
    assert optional.evidence["instruction"]["source"] == "default_optional"


def test_failure_record_is_closed_functional_and_self_validating() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        FAILURE_SCHEMA,
        build_failure_evidence,
        validate_failure_evidence,
    )

    record = build_failure_evidence(
        run_state=_run_state(),
        scope=_scope(),
        ordinal=3,
        compiler_contract=_contract(),
        category="missing_required_dependency",
        operation="resolve",
    )
    assert set(record) == {
        "schema", "record_kind", "run", "compiler_contract", "attempt", "failure",
        "provider_calls", "record_sha256",
    }
    assert record["schema"] == FAILURE_SCHEMA
    assert record["record_kind"] == "failure"
    assert record["provider_calls"] == {"preparation": False, "execution": False}
    assert record["failure"]["authored_row_id"] is None
    assert record["failure"]["evaluated_relpath"] is None
    assert validate_failure_evidence(record) == record

    for field, bad in (("category", "permission_denied"), ("operation", "stat")):
        tampered = deepcopy(record)
        tampered["failure"][field] = bad
        with pytest.raises(ValueError):
            validate_failure_evidence(tampered)

    with pytest.raises(ValueError, match="authored row"):
        build_failure_evidence(
            run_state=_run_state(), scope=_scope(), ordinal=3,
            compiler_contract=_contract(), category="unreadable_dependency",
            operation="read", authored_row_id="sha256:" + "0" * 64,
            evaluated_relpath="inputs/document.md",
        )


def test_evidence_path_is_derived_only_from_attempt_identity() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import evidence_relative_path

    path = evidence_relative_path(_scope(), 3)
    assert path.as_posix().startswith("workflow_lisp/prompt_dependencies/")
    assert path.as_posix().endswith("/attempt-000003.json")
    assert len(path.parts[-3]) == len(path.parts[-2]) == 24
    assert evidence_relative_path(_scope(), 3) == path


def _manager_with_allocations(tmp_path: Path, count: int = 3) -> StateManager:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "workflow.orc").write_text("(workflow evidence)\n", encoding="utf-8")
    manager = StateManager(
        workspace,
        run_id=_scope().run_id,
        state_dir=tmp_path / "runs",
    )
    manager.initialize("workflow.orc")
    assert manager.state is not None
    manager.state.step_visits["Provider"] = 2
    manager.state.current_step = {
        "name": "Provider", "step_id": "ProviderStep", "visit_count": 2,
    }
    manager._write_state()
    for expected in range(1, count + 1):
        assert manager.allocate_provider_attempt(_scope()) == expected
    return manager


def test_publish_is_no_clobber_and_records_event_only_after_complete_file(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import publish_evidence_file

    manager = _manager_with_allocations(tmp_path)
    assert manager.state is not None
    record = _success_record(run_state=manager.state)
    result = publish_evidence_file(
        manager,
        _scope(),
        3,
        record,
    )
    assert (manager.run_root / result.relative_path).read_bytes() == result.payload
    persisted = manager._read_state_from_disk()
    events = persisted.provider_attempt_allocations[_scope().key]["events"]
    assert events[-1] == {
        "ordinal": 3, "event": "evidence_published",
        "relative_path": str(result.relative_path),
        "file_sha256": result.file_sha256, "record_kind": "prompt_snapshot",
    }
    assert list((manager.run_root / result.relative_path.parent).glob(".*.tmp")) == []

    with pytest.raises(ValueError, match="already published"):
        publish_evidence_file(manager, _scope(), 3, record)


def test_publish_rejects_same_or_conflicting_crash_orphan(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
        evidence_relative_path,
        publish_evidence_file,
    )

    manager = _manager_with_allocations(tmp_path)
    record = _success_record(run_state=manager.state)
    destination = manager.run_root / evidence_relative_path(_scope(), 3)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(canonical_record_bytes(record))
    with pytest.raises(FileExistsError):
        publish_evidence_file(manager, _scope(), 3, record)
    changed = _success_record(
        ordinal=3, run_state=manager.state, final_prompt=b"different final prompt"
    )
    with pytest.raises(FileExistsError):
        publish_evidence_file(manager, _scope(), 3, changed)
    persisted = manager._read_state_from_disk()
    assert all(
        event["event"] != "evidence_published"
        for event in persisted.provider_attempt_allocations[_scope().key]["events"]
    )


def test_publish_failure_does_not_emit_event(tmp_path: Path, monkeypatch) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    manager = _manager_with_allocations(tmp_path)
    monkeypatch.setattr(evidence.os, "link", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("link failed")))
    with pytest.raises(OSError, match="link failed"):
        evidence.publish_evidence_file(
            manager, _scope(), 3, _success_record(run_state=manager.state),
        )
    persisted = manager._read_state_from_disk()
    assert all(event["event"] != "evidence_published" for event in persisted.provider_attempt_allocations[_scope().key]["events"])


def test_publish_rejects_unallocated_attempt_before_linking_record(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        evidence_relative_path,
        publish_evidence_file,
    )

    manager = _manager_with_allocations(tmp_path, count=2)
    with pytest.raises(ValueError, match="allocation ordinal"):
        publish_evidence_file(
            manager, _scope(), 3,
            _success_record(ordinal=3, run_state=manager.state),
        )
    assert not (manager.run_root / evidence_relative_path(_scope(), 3)).exists()


def test_publish_completes_short_writes_under_one_process_lock_interval(
    tmp_path: Path, monkeypatch
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    manager = _manager_with_allocations(tmp_path)
    actual_write = evidence.os.write
    lock_entries: list[str] = []

    def short_write(fd, payload):
        return actual_write(fd, payload[: max(1, len(payload) // 3)])

    original_locks = evidence.provider_attempt_process_locks

    from contextlib import contextmanager

    @contextmanager
    def counted_locks(root):
        lock_entries.append(str(root))
        with original_locks(root):
            yield

    monkeypatch.setattr(evidence.os, "write", short_write)
    monkeypatch.setattr(evidence, "provider_attempt_process_locks", counted_locks)
    result = evidence.publish_evidence_file(
        manager, _scope(), 3, _success_record(run_state=manager.state)
    )
    assert (manager.run_root / result.relative_path).read_bytes() == result.payload
    assert lock_entries == [str(manager.run_root)]


def test_publish_fsync_failure_propagates_without_manifest_event(
    tmp_path: Path, monkeypatch
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    manager = _manager_with_allocations(tmp_path)
    monkeypatch.setattr(
        evidence.os,
        "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("fsync failed")),
    )
    with pytest.raises(OSError, match="fsync failed"):
        evidence.publish_evidence_file(
            manager, _scope(), 3, _success_record(run_state=manager.state)
        )
    persisted = manager._read_state_from_disk()
    assert all(
        event["event"] != "evidence_published"
        for event in persisted.provider_attempt_allocations[_scope().key]["events"]
    )


def test_serialized_success_evidence_recursively_excludes_body_sentinels() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import canonical_record_bytes

    serialized = canonical_record_bytes(_success_record())
    for sentinel in (b"alpha", b"beta", b"base prompt", b"Read these inputs."):
        assert sentinel not in serialized


def _terminal_state(root: Path) -> RunState:
    scope = _scope()
    state = _run_state(root)
    state.status = "completed"
    state.provider_attempt_allocations = {
            scope.key: {
                "scope": scope.to_dict(),
                "last_allocated_ordinal": 1,
                "events": [{"ordinal": 1, "event": "allocated"}],
            }
        }
    return state


def test_allocator_projection_is_closed_sorted_and_externally_digestible(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        ALLOCATION_PROJECTION_SCHEMA,
        allocator_projection_sha256,
        build_allocator_projection,
        validate_allocator_projection,
    )

    projection = build_allocator_projection(_terminal_state(tmp_path))
    assert set(projection) == {"schema", "run", "scopes"}
    assert projection["schema"] == ALLOCATION_PROJECTION_SCHEMA
    assert projection["run"] == {
        "run_id": _scope().run_id,
        "workflow_file": "workflow.orc",
        "workflow_checksum": "sha256:" + "1" * 64,
    }
    assert projection["scopes"][0]["scope_sha256"] == _scope().key
    assert allocator_projection_sha256(projection).startswith("sha256:")
    assert validate_allocator_projection(projection) == projection
    tampered = deepcopy(projection)
    tampered["scopes"][0]["last_allocated_ordinal"] = 2
    with pytest.raises(ValueError):
        validate_allocator_projection(tampered)


def test_terminal_validation_builds_immutable_index_and_discloses_gap(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        INDEX_SCHEMA,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")

    result = validate_terminal_evidence(root, state_file)
    assert result.index["schema"] == INDEX_SCHEMA
    assert set(result.index) == {
        "schema", "run", "allocator_projection", "publications",
        "allocation_only_gaps", "index_sha256",
    }
    assert result.index["publications"] == []
    assert result.index["allocation_only_gaps"] == [
        {
            "scope_sha256": _scope().key,
            "runtime_step_id": "ProviderStep",
            "visit_key": _scope().key[7:31],
            "attempt_ordinal": 1,
        }
    ]
    assert result.initial_state_bytes == len(state_file.read_bytes())
    assert result.initial_state_sha256 == _sha(state_file.read_bytes())
    assert result.path.read_bytes() == result.payload
    assert validate_terminal_evidence(root, state_file).created is False


def test_index_rejects_conflicting_runtime_step_for_same_scope(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_index,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    entry = state.provider_attempt_allocations[_scope().key]
    entry["last_allocated_ordinal"] = 2
    entry["events"].append({"ordinal": 2, "event": "allocated"})
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    index = validate_terminal_evidence(root, state_file).index
    tampered = deepcopy(index)
    tampered["allocation_only_gaps"][1]["runtime_step_id"] = "ZProviderStep"
    _reseal_index(tampered)
    with pytest.raises(ValueError, match="runtime"):
        validate_index(tampered)


def test_index_rejects_unsorted_duplicate_and_self_digest_tampering(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_index,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    entry = state.provider_attempt_allocations[_scope().key]
    entry["last_allocated_ordinal"] = 2
    entry["events"].append({"ordinal": 2, "event": "allocated"})
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    index = validate_terminal_evidence(root, state_file).index

    unsorted = deepcopy(index)
    unsorted["allocation_only_gaps"].reverse()
    _reseal_index(unsorted)
    with pytest.raises(ValueError, match="unsorted"):
        validate_index(unsorted)

    duplicate = deepcopy(index)
    duplicate["allocation_only_gaps"].append(
        deepcopy(duplicate["allocation_only_gaps"][-1])
    )
    _reseal_index(duplicate)
    with pytest.raises(ValueError, match="duplicate|unsorted|overlap"):
        validate_index(duplicate)

    digest = deepcopy(index)
    digest["index_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="index_sha256"):
        validate_index(digest)


def test_later_allocator_projection_publishes_new_index_not_stale_one(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    first = validate_terminal_evidence(root, state_file)

    entry = state.provider_attempt_allocations[_scope().key]
    entry["last_allocated_ordinal"] = 2
    entry["events"].append({"ordinal": 2, "event": "allocated"})
    state.updated_at = "2026-07-18T02:00:00+00:00"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    second = validate_terminal_evidence(root, state_file)
    assert second.path != first.path
    assert second.index["allocator_projection"]["sha256"] != first.index["allocator_projection"]["sha256"]
    assert first.path.is_file() and second.path.is_file()


def _install_published_record(root: Path, state: RunState) -> Path:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
        evidence_relative_path,
    )

    record = _success_record(ordinal=1, run_state=state)
    relative = evidence_relative_path(_scope(), 1)
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_record_bytes(record)
    destination.write_bytes(payload)
    state.provider_attempt_allocations[_scope().key]["events"].append(
        {
            "ordinal": 1,
            "event": "evidence_published",
            "relative_path": str(relative),
            "file_sha256": _sha(payload),
            "record_kind": "prompt_snapshot",
        }
    )
    return destination


def test_terminal_validation_indexes_manifest_bound_publication(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    destination = _install_published_record(root, state)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    result = validate_terminal_evidence(root, state_file)
    publication = result.index["publications"][0]
    assert publication["runtime_step_id"] == "ProviderStep"
    assert publication["record_sha256"] == json.loads(destination.read_bytes())["record_sha256"]
    assert publication["record_file_sha256"] == _sha(destination.read_bytes())
    assert result.index["allocation_only_gaps"] == []

    from orchestrator.workflow.prompt_dependency_evidence import validate_index

    for field in ("scope_count", "event_count"):
        tampered = deepcopy(result.index)
        tampered["allocator_projection"][field] = 99
        _reseal_index(tampered)
        with pytest.raises(ValueError, match="count"):
            validate_index(tampered)
    tampered = deepcopy(result.index)
    tampered["publications"][0]["visit_key"] = "0" * 24
    _reseal_index(tampered)
    with pytest.raises(ValueError, match="visit"):
        validate_index(tampered)


def test_terminal_validation_rejects_nonterminal_missing_corrupt_and_orphan(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        publish_evidence_file,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state.status = "running"
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    with pytest.raises(ValueError, match="terminal"):
        validate_terminal_evidence(root, state_file)

    copied_terminal = _terminal_state(root)
    copied_state = root / "copied-state.json"
    copied_state.write_text(json.dumps(copied_terminal.to_dict()), encoding="utf-8")
    with pytest.raises(ValueError, match="authoritative"):
        validate_terminal_evidence(root, copied_state)

    state.status = "completed"
    published = _install_published_record(root, state)
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    published.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="digest|corrupt"):
        validate_terminal_evidence(root, state_file)

    state.provider_attempt_allocations[_scope().key]["events"] = [
        {"ordinal": 1, "event": "allocated"}
    ]
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    with pytest.raises(ValueError, match="orphan"):
        validate_terminal_evidence(root, state_file)


@pytest.mark.parametrize("fault", ["missing", "wrong_kind", "wrong_identity"])
def test_terminal_validation_rejects_manifest_record_mismatch(tmp_path: Path, fault: str) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    destination = _install_published_record(root, state)
    if fault == "missing":
        destination.unlink()
    elif fault == "wrong_kind":
        state.provider_attempt_allocations[_scope().key]["events"][-1]["record_kind"] = "failure"
    else:
        record = _success_record(ordinal=2, run_state=state)
        destination.write_bytes(canonical_record_bytes(record))
        state.provider_attempt_allocations[_scope().key]["events"][-1]["file_sha256"] = _sha(destination.read_bytes())
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    with pytest.raises(ValueError):
        validate_terminal_evidence(root, state_file)


def test_terminal_validation_rejects_recursive_wrong_depth_orphan(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    orphan = root / "workflow_lisp/prompt_dependencies/unexpected/depth/more/attempt-000001.json"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="orphan"):
        validate_terminal_evidence(root, state_file)


def test_terminal_validation_rejects_conflicting_existing_index(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    first = validate_terminal_evidence(root, state_file)
    first.path.write_bytes(b"conflict")
    with pytest.raises(FileExistsError):
        validate_terminal_evidence(root, state_file)


def test_terminal_validation_cli_emits_machine_readable_result(tmp_path: Path, capsys) -> None:
    from scripts.validate_prompt_dependency_evidence import main

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    assert main([str(root), "--state-file", str(state_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "passed"
    assert result["initial_state_sha256"] == _sha(state_file.read_bytes())
    assert Path(result["index_path"]).is_file()


def test_terminal_validation_detects_bypass_state_drift_and_removes_new_index(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

    def bypass() -> None:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        payload["updated_at"] = "2026-07-18T01:00:00+00:00"
        state_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="changed"):
        validate_terminal_evidence(root, state_file, _after_index_publish=bypass)
    indexes = root / "workflow_lisp/prompt_dependencies/validated-indexes"
    assert not indexes.exists() or list(indexes.glob("*.json")) == []


def _validate_with_hold(root: str, state_file: str, ready, release, results) -> None:
    try:
        from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

        def hold() -> None:
            ready.set()
            if not release.wait(10):
                raise TimeoutError("release timed out")

        validate_terminal_evidence(root, state_file, _after_initial_read=hold)
        results.put("validated")
    except BaseException as exc:  # pragma: no cover
        results.put(repr(exc))


def _conforming_status_write(workspace: str, state_dir: str, run_id: str, ready, results) -> None:
    try:
        manager = StateManager(Path(workspace), run_id=run_id, state_dir=Path(state_dir))
        manager.load()
        manager.enable_durable_state_writes()
        ready.set()
        manager.update_status("completed")
        results.put("written")
    except BaseException as exc:  # pragma: no cover
        results.put(repr(exc))


def _allocate_and_publish_after_resume(
    workspace: str, state_dir: str, run_id: str, scope_payload: dict, ready, results
) -> None:
    try:
        from orchestrator.workflow.prompt_dependency_evidence import publish_evidence_file

        manager = StateManager(Path(workspace), run_id=run_id, state_dir=Path(state_dir))
        manager.load()
        scope = ProviderAttemptScope.from_dict(scope_payload)
        ready.set()
        ordinal = manager.allocate_provider_attempt(scope)
        publish_evidence_file(
            manager, scope, ordinal,
            _success_record(ordinal=ordinal, run_state=manager.state),
        )
        results.put("allocated-published")
    except BaseException as exc:  # pragma: no cover
        results.put(repr(exc))


def _nested_frame_write_after_resume(
    workspace: str, state_dir: str, run_id: str, ready, results
) -> None:
    try:
        manager = StateManager(Path(workspace), run_id=run_id, state_dir=Path(state_dir))
        manager.load()
        assert manager.state is not None
        nested = _run_state(manager.run_root / "call_frames" / "frame")
        nested.run_id = run_id
        ready.set()
        manager.update_call_frame(
            "frame",
            {"call_frame_id": "frame", "state": nested.to_dict()},
        )
        results.put("nested-written")
    except BaseException as exc:  # pragma: no cover
        results.put(repr(exc))


def test_terminal_validator_blocks_conforming_writer_then_writer_proceeds(tmp_path: Path) -> None:
    manager = _manager_with_allocations(tmp_path, count=1)
    manager.update_status("completed")
    context = multiprocessing.get_context("fork")
    validation_ready = context.Event()
    release = context.Event()
    writer_started = context.Event()
    allocation_started = context.Event()
    nested_started = context.Event()
    results = context.Queue()
    validator = context.Process(
        target=_validate_with_hold,
        args=(str(manager.run_root), str(manager.state_file), validation_ready, release, results),
    )
    validator.start()
    assert validation_ready.wait(5)
    writer = context.Process(
        target=_conforming_status_write,
        args=(str(manager.workspace), str(manager.runs_root), manager.run_id, writer_started, results),
    )
    writer.start()
    assert writer_started.wait(5)
    allocator = context.Process(
        target=_allocate_and_publish_after_resume,
        args=(
            str(manager.workspace), str(manager.runs_root), manager.run_id,
            _scope().to_dict(), allocation_started, results,
        ),
    )
    nested_writer = context.Process(
        target=_nested_frame_write_after_resume,
        args=(
            str(manager.workspace), str(manager.runs_root), manager.run_id,
            nested_started, results,
        ),
    )
    allocator.start()
    nested_writer.start()
    assert allocation_started.wait(5)
    assert nested_started.wait(5)
    time.sleep(0.1)
    assert writer.is_alive() and allocator.is_alive() and nested_writer.is_alive()
    release.set()
    validator.join(10)
    writer.join(10)
    allocator.join(10)
    nested_writer.join(10)
    assert validator.exitcode == writer.exitcode == allocator.exitcode == nested_writer.exitcode == 0
    assert sorted([results.get(timeout=2) for _ in range(4)]) == [
        "allocated-published", "nested-written", "validated", "written",
    ]


def test_functional_allocation_publication_write_validation_stress_is_bounded(
    tmp_path: Path,
) -> None:
    manager = _manager_with_allocations(tmp_path, count=0)
    manager.update_status("completed")
    context = multiprocessing.get_context("fork")
    for ordinal in range(1, 4):
        validation_ready = context.Event()
        release = context.Event()
        allocation_started = context.Event()
        writer_started = context.Event()
        results = context.Queue()
        validator = context.Process(
            target=_validate_with_hold,
            args=(
                str(manager.run_root), str(manager.state_file),
                validation_ready, release, results,
            ),
        )
        allocator = context.Process(
            target=_allocate_and_publish_after_resume,
            args=(
                str(manager.workspace), str(manager.runs_root), manager.run_id,
                _scope().to_dict(), allocation_started, results,
            ),
        )
        writer = context.Process(
            target=_conforming_status_write,
            args=(
                str(manager.workspace), str(manager.runs_root), manager.run_id,
                writer_started, results,
            ),
        )
        validator.start()
        assert validation_ready.wait(5)
        allocator.start()
        writer.start()
        assert allocation_started.wait(5)
        assert writer_started.wait(5)
        time.sleep(0.05)
        assert allocator.is_alive() and writer.is_alive()
        release.set()
        validator.join(10)
        allocator.join(10)
        writer.join(10)
        assert validator.exitcode == allocator.exitcode == writer.exitcode == 0
        assert sorted([results.get(timeout=2) for _ in range(3)]) == [
            "allocated-published", "validated", "written",
        ]
        manager.load()
        assert manager.state is not None
        assert manager.state.provider_attempt_allocations[_scope().key][
            "last_allocated_ordinal"
        ] == ordinal


def _offline_validator_references(source: str) -> set[str]:
    forbidden = {
        "validate_terminal_evidence",
        "validate_index",
        "_build_terminal_index",
        "_write_index_no_replace",
        "build_allocator_projection",
        "validate_allocator_projection",
        "allocator_projection_sha256",
        "validate_prompt_dependency_evidence",
    }
    forbidden_modules = {"scripts.validate_prompt_dependency_evidence"}
    tree = ast.parse(source)
    referenced = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name in forbidden_modules
    }
    return referenced & (forbidden | forbidden_modules)


def test_runtime_ast_guard_rejects_aliased_offline_validator_import() -> None:
    source = (
        "from orchestrator.workflow.prompt_dependency_evidence "
        "import validate_terminal_evidence as v\nv('root', 'state')\n"
    )
    assert _offline_validator_references(source) == {"validate_terminal_evidence"}
    assert _offline_validator_references(
        "from orchestrator.workflow.prompt_dependency_evidence import validate_index as v\n"
    ) == {"validate_index"}
    assert _offline_validator_references(
        "import scripts.validate_prompt_dependency_evidence as validator\n"
    ) == {"scripts.validate_prompt_dependency_evidence"}


def test_runtime_modules_do_not_import_or_call_offline_prompt_dependency_validator() -> None:
    paths = [
        "orchestrator/workflow/executor.py",
        "orchestrator/workflow/prompting.py",
        "orchestrator/workflow/adjudication_runtime.py",
        "orchestrator/cli/commands/run.py",
        "orchestrator/cli/commands/resume.py",
    ]
    for relative in paths:
        assert not _offline_validator_references(
            Path(relative).read_text(encoding="utf-8")
        ), relative
