"""Functional content-free evidence for provider prompt dependencies."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
from typing import Any, Callable, Mapping

from orchestrator.deps.content_snapshot import (
    MAX_INJECTION_BYTES,
    MAX_INSTRUCTION_BYTES,
    TRUNCATION_SUMMARY_RESERVE_BYTES,
    DependencyContentSnapshot,
    RenderedContentSnapshot,
    render_content_snapshot,
)
from orchestrator.state import RunState, StateManager
from orchestrator.state_locking import provider_attempt_process_locks
from orchestrator.workflow.prompt_dependency_contract import (
    COMPILER_PROMPT_DEPENDENCY_CONTRACT_SCHEMA,
    CompilerPromptDependencyContract,
    PromptDependencyOriginKind,
    PromptDependencyPathInterpretation,
    PromptDependencyPosition,
    _normalized_contract_sha256,
    serialize_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.provider_attempts import (
    ProviderAttemptScope,
    resolve_aggregate_run_owner,
    validate_provider_attempt_allocations,
)


SUCCESS_SCHEMA = "workflow_prompt_dependency_evidence.functional.v1"
FAILURE_SCHEMA = "workflow_prompt_dependency_failure_evidence.functional.v1"
INDEX_SCHEMA = "workflow_prompt_dependency_validated_index.functional.v1"
ALLOCATION_PROJECTION_SCHEMA = "workflow_provider_attempt_allocation_projection.v1"

_SUCCESS_KEYS = {
    "schema", "record_kind", "run", "compiler_contract", "attempt",
    "authored_rows", "canonical_groups", "instruction", "injection",
    "final_prompt", "record_sha256",
}
_FAILURE_KEYS = {
    "schema", "record_kind", "run", "compiler_contract", "attempt",
    "failure", "provider_calls", "record_sha256",
}
_CONTRACT_KEYS = {
    "schema", "origin_kind", "path_interpretation", "evidence_required",
    "source_origin_key", "source_workflow_sha256", "required_binding_refs",
    "optional_binding_refs", "position", "instruction_utf8_sha256_or_null",
    "normalized_contract_sha256",
}
_INJECTION_KEYS = {
    "mode", "max_bytes", "instruction_max_bytes", "summary_reserve_bytes",
    "position", "was_truncated", "pre_truncation_bytes", "block_bytes",
    "block_sha256", "normalized_total_bytes", "retained_bytes", "shown_bytes",
    "files_total", "files_shown", "files_truncated", "files_omitted",
    "summary_bytes", "summary_sha256",
}
_FAILURE_OPERATIONS = {
    "missing_required_dependency": "resolve",
    "unreadable_dependency": "read",
    "invalid_utf8_dependency": "decode",
    "invalid_injection_contract": "render",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _closed(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{label} must be a closed object")
    return value


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty")
    return value


def _seal(record: dict[str, Any]) -> dict[str, Any]:
    body = dict(record)
    body.pop("record_sha256", None)
    record["record_sha256"] = _sha(_canonical_bytes(body))
    return record


def _validate_seal(record: Mapping[str, Any]) -> None:
    body = dict(record)
    claimed = body.pop("record_sha256", None)
    if not _is_sha(claimed) or claimed != _sha(_canonical_bytes(body)):
        raise ValueError("record_sha256 does not match record")


def _run(run_state: RunState, scope: ProviderAttemptScope) -> dict[str, str]:
    if not isinstance(run_state, RunState):
        raise TypeError("RunState required")
    if run_state.run_id != scope.run_id:
        raise ValueError("run state run_id contradicts attempt scope")
    if run_state.workflow_file != scope.resume_scope.root_workflow_file:
        raise ValueError("run state workflow_file contradicts attempt scope")
    if not _is_sha(run_state.workflow_checksum):
        raise ValueError("run state workflow checksum is invalid")
    return {
        "run_id": run_state.run_id,
        "workflow_file": run_state.workflow_file,
        "workflow_checksum": run_state.workflow_checksum,
    }


def _attempt(scope: ProviderAttemptScope, ordinal: int) -> dict[str, Any]:
    if not isinstance(scope, ProviderAttemptScope):
        raise TypeError("ProviderAttemptScope required")
    _integer(ordinal, "attempt ordinal", 1)
    return {
        "scope": scope.to_dict(),
        "scope_sha256": scope.key,
        "step_key": hashlib.sha256(scope.runtime_step_id.encode("utf-8")).hexdigest()[:24],
        "visit_key": scope.key[7:31],
        "ordinal": ordinal,
    }


def _row_id(contract: Mapping[str, Any], role: str, index: int, binding_ref: str) -> str:
    return _sha(
        _canonical_bytes(
            {
                "source_origin_key": contract["source_origin_key"],
                "role": role,
                "authored_index": index,
                "binding_ref": binding_ref,
            }
        )
    )


def authored_row_id(
    compiler_contract: CompilerPromptDependencyContract,
    *,
    role: str,
    authored_index: int,
) -> str:
    """Return the canonical evidence identity for one compiler-authored row."""

    contract = serialize_compiler_prompt_dependency_contract(compiler_contract)
    refs_key = {"required": "required_binding_refs", "optional": "optional_binding_refs"}.get(
        role
    )
    if refs_key is None:
        raise ValueError("dependency role is invalid")
    if isinstance(authored_index, bool) or not isinstance(authored_index, int):
        raise TypeError("authored_index must be an integer")
    refs = contract[refs_key]
    if authored_index < 0 or authored_index >= len(refs):
        raise ValueError("authored_index is outside the compiler contract")
    return _row_id(contract, role, authored_index, refs[authored_index])


def _instruction_source(contract: Mapping[str, Any]) -> str:
    if contract["instruction_utf8_sha256_or_null"] is not None:
        return "authored"
    return "default_required" if contract["required_binding_refs"] else "default_optional"


@dataclass(frozen=True)
class SuccessEvidenceBuild:
    """One authoritative render and the content-free evidence derived from it."""

    rendered: RenderedContentSnapshot
    final_prompt: bytes
    evidence: dict[str, Any]


def build_success_evidence(
    *,
    run_state: RunState,
    scope: ProviderAttemptScope,
    ordinal: int,
    compiler_contract: CompilerPromptDependencyContract,
    snapshot: DependencyContentSnapshot,
    instruction: str,
    instruction_source: str,
    compose_final_prompt: Callable[[RenderedContentSnapshot], bytes],
) -> SuccessEvidenceBuild:
    """Render exactly once and build its closed content-free success record."""

    contract = serialize_compiler_prompt_dependency_contract(compiler_contract)
    if not isinstance(snapshot, DependencyContentSnapshot):
        raise TypeError("DependencyContentSnapshot required")
    if not isinstance(instruction, str):
        raise TypeError("instruction must be a string")
    if not callable(compose_final_prompt):
        raise TypeError("compose_final_prompt must be callable")
    instruction_bytes = instruction.encode("utf-8")
    expected_source = _instruction_source(contract)
    if instruction_source != expected_source:
        raise ValueError("instruction source contradicts compiler contract")
    if expected_source == "authored" and _sha(instruction_bytes) != contract["instruction_utf8_sha256_or_null"]:
        raise ValueError("authored instruction contradicts compiler contract")
    rendered = render_content_snapshot(snapshot, instruction)

    row_ids: dict[tuple[str, int], str] = {}
    rows: list[dict[str, Any]] = []
    for row in snapshot.authored_rows:
        identity = _row_id(contract, row.role, row.authored_index, row.binding_ref)
        row_ids[(row.role, row.authored_index)] = identity
        rows.append(
            {
                "row_id": identity,
                "role": row.role,
                "authored_index": row.authored_index,
                "binding_ref": row.binding_ref,
                "evaluated_relpath": row.evaluated_relpath,
                "status": "absent" if row.canonical_target is None else "present",
                "canonical_target": row.canonical_target,
            }
        )
    if len(rendered.group_truncations) != len(snapshot.canonical_groups):
        raise ValueError("render metadata cardinality contradicts snapshot")
    groups: list[dict[str, Any]] = []
    for order, (group, render) in enumerate(zip(snapshot.canonical_groups, rendered.group_truncations)):
        if group.canonical_target != render.canonical_target:
            raise ValueError("render metadata order contradicts snapshot")
        if render.total_bytes != group.normalized_total_bytes:
            raise ValueError("render metadata total bytes contradict snapshot")
        shown = group.normalized_bytes[: render.shown_bytes]
        groups.append(
            {
                "order": order,
                "canonical_target": group.canonical_target,
                "effective_role": group.effective_role,
                "authored_row_ids": [row_ids[(row.role, row.authored_index)] for row in group.authored_rows],
                "normalized_total_bytes": group.normalized_total_bytes,
                "retained_bytes": len(group.normalized_bytes),
                "retained_sha256": _sha(group.normalized_bytes),
                "render_status": render.status,
                "shown_bytes": render.shown_bytes,
                "shown_sha256": None if render.status == "omitted" else _sha(shown),
            }
        )
    complete = sum(row.status == "complete" for row in rendered.group_truncations)
    truncated = sum(row.status == "truncated" for row in rendered.group_truncations)
    omitted = sum(row.status == "omitted" for row in rendered.group_truncations)
    final = compose_final_prompt(rendered)
    if type(final) is not bytes:
        raise TypeError("compose_final_prompt must return final_prompt bytes")
    record = {
        "schema": SUCCESS_SCHEMA,
        "record_kind": "prompt_snapshot",
        "run": _run(run_state, scope),
        "compiler_contract": contract,
        "attempt": _attempt(scope, ordinal),
        "authored_rows": rows,
        "canonical_groups": groups,
        "instruction": {"source": instruction_source, "bytes": len(instruction_bytes), "sha256": _sha(instruction_bytes)},
        "injection": {
            "mode": "content",
            "max_bytes": MAX_INJECTION_BYTES,
            "instruction_max_bytes": MAX_INSTRUCTION_BYTES,
            "summary_reserve_bytes": TRUNCATION_SUMMARY_RESERVE_BYTES,
            "position": contract["position"],
            "was_truncated": rendered.was_truncated,
            "pre_truncation_bytes": rendered.pre_truncation_bytes,
            "block_bytes": len(rendered.block),
            "block_sha256": _sha(rendered.block),
            "normalized_total_bytes": sum(group.normalized_total_bytes for group in snapshot.canonical_groups),
            "retained_bytes": snapshot.retained_content_bytes,
            "shown_bytes": sum(row.shown_bytes for row in rendered.group_truncations),
            "files_total": len(rendered.group_truncations),
            "files_shown": complete + truncated,
            "files_truncated": truncated,
            "files_omitted": omitted,
            "summary_bytes": len(rendered.summary),
            "summary_sha256": _sha(rendered.summary) if rendered.summary else None,
        },
        "final_prompt": {"bytes": len(final), "sha256": _sha(final)},
    }
    return SuccessEvidenceBuild(
        rendered=rendered,
        final_prompt=final,
        evidence=validate_success_evidence(_seal(record)),
    )


def _validate_contract(value: Any) -> Mapping[str, Any]:
    contract = _closed(value, _CONTRACT_KEYS, "compiler contract")
    if (
        contract["schema"] != COMPILER_PROMPT_DEPENDENCY_CONTRACT_SCHEMA
        or contract["origin_kind"] != PromptDependencyOriginKind.WORKFLOW_LISP_PROVIDER_RESULT_PROMPT_DEPENDENCIES.value
        or contract["path_interpretation"] != PromptDependencyPathInterpretation.EXACT.value
        or contract["evidence_required"] is not True
    ):
        raise ValueError("compiler contract constants are invalid")
    _text(contract["source_origin_key"], "compiler source origin")
    if not _is_sha(contract["source_workflow_sha256"]):
        raise ValueError("compiler source digest is invalid")
    for name in ("required_binding_refs", "optional_binding_refs"):
        refs = contract[name]
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs):
            raise ValueError("compiler binding refs are invalid")
    if not contract["required_binding_refs"] and not contract["optional_binding_refs"]:
        raise ValueError("compiler contract has no dependency rows")
    try:
        position = PromptDependencyPosition(contract["position"])
    except (TypeError, ValueError) as exc:
        raise ValueError("compiler position is invalid") from exc
    instruction_digest = contract["instruction_utf8_sha256_or_null"]
    if instruction_digest is not None and not _is_sha(instruction_digest):
        raise ValueError("compiler instruction digest is invalid")
    expected = _normalized_contract_sha256(
        required_binding_refs=tuple(contract["required_binding_refs"]),
        optional_binding_refs=tuple(contract["optional_binding_refs"]),
        position=position,
        instruction_utf8_sha256_or_null=instruction_digest,
    )
    if contract["normalized_contract_sha256"] != expected:
        raise ValueError("compiler normalized digest is invalid")
    return contract


def _validate_attempt(value: Any) -> ProviderAttemptScope:
    node = _closed(value, {"scope", "scope_sha256", "step_key", "visit_key", "ordinal"}, "attempt")
    try:
        scope = ProviderAttemptScope.from_dict(node["scope"])
    except (TypeError, ValueError) as exc:
        raise ValueError("attempt scope is invalid") from exc
    if node != _attempt(scope, _integer(node["ordinal"], "attempt ordinal", 1)):
        raise ValueError("attempt metadata contradicts scope")
    return scope


def _validate_run(value: Any, scope: ProviderAttemptScope) -> Mapping[str, Any]:
    run = _closed(value, {"run_id", "workflow_file", "workflow_checksum"}, "run")
    if run["run_id"] != scope.run_id or run["workflow_file"] != scope.resume_scope.root_workflow_file:
        raise ValueError("run metadata contradicts scope")
    if not _is_sha(run["workflow_checksum"]):
        raise ValueError("run workflow checksum is invalid")
    return run


def validate_success_evidence(value: Any) -> dict[str, Any]:
    record = _closed(value, _SUCCESS_KEYS, "success evidence")
    if record["schema"] != SUCCESS_SCHEMA or record["record_kind"] != "prompt_snapshot":
        raise ValueError("success schema or record kind is invalid")
    contract = _validate_contract(record["compiler_contract"])
    scope = _validate_attempt(record["attempt"])
    _validate_run(record["run"], scope)
    expected_rows = [
        ("required", index, ref) for index, ref in enumerate(contract["required_binding_refs"])
    ] + [("optional", index, ref) for index, ref in enumerate(contract["optional_binding_refs"])]
    rows = record["authored_rows"]
    if not isinstance(rows, list) or len(rows) != len(expected_rows):
        raise ValueError("authored row cardinality is invalid")
    by_id: dict[str, Mapping[str, Any]] = {}
    present_ids: list[str] = []
    for raw, (role, index, ref) in zip(rows, expected_rows):
        row = _closed(raw, {"row_id", "role", "authored_index", "binding_ref", "evaluated_relpath", "status", "canonical_target"}, "authored row")
        identity = _row_id(contract, role, index, ref)
        _integer(row["authored_index"], "authored row index")
        if (row["row_id"], row["role"], row["authored_index"], row["binding_ref"]) != (identity, role, index, ref):
            raise ValueError("authored row contradicts compiler contract")
        _text(row["evaluated_relpath"], "evaluated path")
        if row["status"] not in {"present", "absent"}:
            raise ValueError("authored row status is invalid")
        if role == "required" and row["status"] == "absent":
            raise ValueError("required dependency cannot be absent")
        if (row["canonical_target"] is None) != (row["status"] == "absent"):
            raise ValueError("authored row target contradicts status")
        if row["canonical_target"] is not None:
            _text(row["canonical_target"], "canonical target")
            present_ids.append(identity)
        by_id[identity] = row

    groups = record["canonical_groups"]
    if not isinstance(groups, list):
        raise ValueError("canonical groups must be a list")
    prior_target = ""
    grouped_ids: list[str] = []
    totals = {"normalized": 0, "retained": 0, "shown": 0, "truncated": 0, "omitted": 0}
    render_phase = "complete"
    for order, raw in enumerate(groups):
        group = _closed(raw, {"order", "canonical_target", "effective_role", "authored_row_ids", "normalized_total_bytes", "retained_bytes", "retained_sha256", "render_status", "shown_bytes", "shown_sha256"}, "canonical group")
        target = _text(group["canonical_target"], "canonical target")
        _integer(group["order"], "canonical group order")
        if group["order"] != order or target <= prior_target:
            raise ValueError("canonical groups are duplicate or not lexically ordered")
        prior_target = target
        ids = group["authored_row_ids"]
        if not isinstance(ids, list) or not ids or any(identity not in by_id for identity in ids):
            raise ValueError("canonical group row membership is invalid")
        expected_ids = [row["row_id"] for row in rows if row["canonical_target"] == target]
        if ids != expected_ids:
            raise ValueError("canonical group row membership/order is invalid")
        expected_role = "required" if any(by_id[identity]["role"] == "required" for identity in ids) else "optional"
        if group["effective_role"] != expected_role:
            raise ValueError("canonical group effective role is invalid")
        normalized = _integer(group["normalized_total_bytes"], "normalized bytes")
        retained = _integer(group["retained_bytes"], "retained bytes")
        shown = _integer(group["shown_bytes"], "shown bytes")
        if not 0 <= shown <= retained <= normalized or not _is_sha(group["retained_sha256"]):
            raise ValueError("canonical group digest/byte disposition is invalid")
        status = group["render_status"]
        if status == "complete":
            if render_phase != "complete":
                raise ValueError("canonical group render status order is invalid")
            if shown != normalized or not _is_sha(group["shown_sha256"]):
                raise ValueError("complete group digest/bytes are invalid")
        elif status == "truncated":
            if render_phase == "truncated":
                raise ValueError("canonical groups contain multiple truncated groups")
            if render_phase == "omitted":
                raise ValueError("canonical group render status order is invalid")
            render_phase = "truncated"
            if not 0 < shown < normalized or not _is_sha(group["shown_sha256"]):
                raise ValueError("truncated group digest/bytes are invalid")
            totals["truncated"] += 1
        elif status == "omitted":
            render_phase = "omitted"
            if shown != 0 or group["shown_sha256"] is not None:
                raise ValueError("omitted group digest/bytes are invalid")
            totals["omitted"] += 1
        else:
            raise ValueError("canonical group render status is invalid")
        grouped_ids.extend(ids)
        totals["normalized"] += normalized
        totals["retained"] += retained
        totals["shown"] += shown
    if len(grouped_ids) != len(present_ids) or set(grouped_ids) != set(present_ids):
        raise ValueError("canonical group coverage is invalid")

    instruction = _closed(record["instruction"], {"source", "bytes", "sha256"}, "instruction")
    if instruction["source"] != _instruction_source(contract):
        raise ValueError("instruction source contradicts compiler contract")
    _integer(instruction["bytes"], "instruction bytes")
    if instruction["bytes"] > MAX_INSTRUCTION_BYTES or not _is_sha(instruction["sha256"]):
        raise ValueError("instruction digest is invalid")
    if instruction["source"] == "authored" and instruction["sha256"] != contract["instruction_utf8_sha256_or_null"]:
        raise ValueError("instruction digest contradicts compiler contract")

    injection = _closed(record["injection"], _INJECTION_KEYS, "injection")
    if (
        injection["mode"] != "content"
        or injection["max_bytes"] != MAX_INJECTION_BYTES
        or injection["instruction_max_bytes"] != MAX_INSTRUCTION_BYTES
        or injection["summary_reserve_bytes"] != TRUNCATION_SUMMARY_RESERVE_BYTES
        or injection["position"] != contract["position"]
    ):
        raise ValueError("injection constants are invalid")
    if not isinstance(injection["was_truncated"], bool):
        raise ValueError("injection truncation flag is invalid")
    for name in ("pre_truncation_bytes", "block_bytes", "normalized_total_bytes", "retained_bytes", "shown_bytes", "files_total", "files_shown", "files_truncated", "files_omitted", "summary_bytes"):
        _integer(injection[name], f"injection {name}")
    if injection["block_bytes"] > MAX_INJECTION_BYTES or not _is_sha(injection["block_sha256"]):
        raise ValueError("injection block is invalid")
    if injection["summary_bytes"] > TRUNCATION_SUMMARY_RESERVE_BYTES:
        raise ValueError("injection summary exceeds reserve")
    if (
        injection["pre_truncation_bytes"] < instruction["bytes"]
        or injection["block_bytes"] < instruction["bytes"] + injection["summary_bytes"]
        or injection["pre_truncation_bytes"] < injection["block_bytes"]
    ):
        raise ValueError("injection byte relationships are invalid")
    expected_injection = {
        "normalized_total_bytes": totals["normalized"],
        "retained_bytes": totals["retained"],
        "shown_bytes": totals["shown"],
        "files_total": len(groups),
        "files_shown": len(groups) - totals["omitted"],
        "files_truncated": totals["truncated"],
        "files_omitted": totals["omitted"],
    }
    if any(injection[name] != expected for name, expected in expected_injection.items()):
        raise ValueError("injection totals contradict canonical groups")
    expected_truncated = totals["truncated"] > 0 or totals["omitted"] > 0
    if injection["was_truncated"] != expected_truncated:
        raise ValueError("injection truncation flag contradicts groups")
    if (
        (not expected_truncated and injection["pre_truncation_bytes"] != injection["block_bytes"])
        or (expected_truncated and injection["pre_truncation_bytes"] <= injection["block_bytes"])
    ):
        raise ValueError("injection pre-truncation bytes contradict truncation status")
    if expected_truncated:
        if injection["summary_bytes"] <= 0 or not _is_sha(injection["summary_sha256"]):
            raise ValueError("truncated injection summary is invalid")
    elif injection["summary_bytes"] != 0 or injection["summary_sha256"] is not None:
        raise ValueError("complete injection summary must be absent")
    final = _closed(record["final_prompt"], {"bytes", "sha256"}, "final prompt")
    _integer(final["bytes"], "final prompt bytes")
    if not _is_sha(final["sha256"]):
        raise ValueError("final prompt digest is invalid")
    _validate_seal(record)
    return dict(record)


def build_failure_evidence(
    *,
    run_state: RunState,
    scope: ProviderAttemptScope,
    ordinal: int,
    compiler_contract: CompilerPromptDependencyContract,
    category: str,
    operation: str,
    authored_row_id: str | None = None,
    evaluated_relpath: str | None = None,
) -> dict[str, Any]:
    if _FAILURE_OPERATIONS.get(category) != operation:
        raise ValueError("failure category and operation are invalid")
    contract = serialize_compiler_prompt_dependency_contract(compiler_contract)
    valid_row_ids = {
        _row_id(contract, role, index, ref)
        for role, refs in (
            ("required", contract["required_binding_refs"]),
            ("optional", contract["optional_binding_refs"]),
        )
        for index, ref in enumerate(refs)
    }
    if authored_row_id is not None and authored_row_id not in valid_row_ids:
        raise ValueError("failure authored row id is invalid")
    if evaluated_relpath is not None:
        _text(evaluated_relpath, "failure evaluated path")
    if (authored_row_id is None) != (evaluated_relpath is None):
        raise ValueError("failure authored row context must be wholly present or absent")
    record = {
        "schema": FAILURE_SCHEMA,
        "record_kind": "failure",
        "run": _run(run_state, scope),
        "compiler_contract": contract,
        "attempt": _attempt(scope, ordinal),
        "failure": {"category": category, "operation": operation, "authored_row_id": authored_row_id, "evaluated_relpath": evaluated_relpath},
        "provider_calls": {"preparation": False, "execution": False},
    }
    return validate_failure_evidence(_seal(record))


def validate_failure_evidence(value: Any) -> dict[str, Any]:
    record = _closed(value, _FAILURE_KEYS, "failure evidence")
    if record["schema"] != FAILURE_SCHEMA or record["record_kind"] != "failure":
        raise ValueError("failure schema or record kind is invalid")
    contract = _validate_contract(record["compiler_contract"])
    scope = _validate_attempt(record["attempt"])
    _validate_run(record["run"], scope)
    failure = _closed(record["failure"], {"category", "operation", "authored_row_id", "evaluated_relpath"}, "failure")
    if _FAILURE_OPERATIONS.get(failure["category"]) != failure["operation"]:
        raise ValueError("failure category or operation is invalid")
    valid_row_ids = {
        _row_id(contract, role, index, ref)
        for role, refs in (
            ("required", contract["required_binding_refs"]),
            ("optional", contract["optional_binding_refs"]),
        )
        for index, ref in enumerate(refs)
    }
    if failure["authored_row_id"] is not None and failure["authored_row_id"] not in valid_row_ids:
        raise ValueError("failure authored row id is invalid")
    if failure["evaluated_relpath"] is not None:
        _text(failure["evaluated_relpath"], "failure evaluated path")
    if (failure["authored_row_id"] is None) != (failure["evaluated_relpath"] is None):
        raise ValueError("failure authored row context is incomplete")
    if record["provider_calls"] != {"preparation": False, "execution": False}:
        raise ValueError("failure provider calls must both be false")
    _validate_seal(record)
    return dict(record)


def canonical_record_bytes(record: Mapping[str, Any]) -> bytes:
    if record.get("schema") == SUCCESS_SCHEMA:
        normalized = validate_success_evidence(record)
    elif record.get("schema") == FAILURE_SCHEMA:
        normalized = validate_failure_evidence(record)
    else:
        raise ValueError("unsupported evidence schema")
    return _canonical_bytes(normalized)


def evidence_relative_path(scope: ProviderAttemptScope, ordinal: int) -> Path:
    attempt = _attempt(scope, ordinal)
    return Path("workflow_lisp", "prompt_dependencies", attempt["step_key"], attempt["visit_key"], f"attempt-{ordinal:06d}.json")


@dataclass(frozen=True)
class PublicationResult:
    relative_path: Path
    file_sha256: str
    payload: bytes
    record_kind: str


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_durable_directory_chain(path: Path, durable_anchor: Path) -> None:
    anchor = Path(os.path.abspath(durable_anchor))
    target = Path(os.path.abspath(path))
    if not anchor.is_dir():
        raise NotADirectoryError(anchor)
    try:
        relative = target.relative_to(anchor)
    except ValueError as exc:
        raise ValueError("directory chain must be below durable anchor") from exc
    current = anchor
    for component in relative.parts:
        current = current / component
        if current.exists():
            if not current.is_dir():
                raise NotADirectoryError(current)
        else:
            try:
                current.mkdir()
            except FileExistsError:
                if not current.is_dir():
                    raise
        _fsync_directory(current)
        _fsync_directory(current.parent)


def _write_current_no_replace(
    destination: Path, payload: bytes, durable_anchor: Path
) -> None:
    _ensure_durable_directory_chain(destination.parent, durable_anchor)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    fd: int | None = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("evidence write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.link(temporary, destination)
        _fsync_directory(destination.parent)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        else:
            _fsync_directory(destination.parent)


def publish_evidence_file(
    manager: Any,
    scope: ProviderAttemptScope,
    ordinal: int,
    record: Mapping[str, Any],
) -> PublicationResult:
    """Link a current record and persist its event under one lock interval."""

    payload = canonical_record_bytes(record)
    if record["attempt"] != _attempt(scope, ordinal):
        raise ValueError("record attempt contradicts publication identity")
    owner = resolve_aggregate_run_owner(manager)
    root: StateManager = owner.root_manager
    relative = evidence_relative_path(scope, ordinal)
    kind = record["record_kind"]
    digest = _sha(payload)
    root.enable_durable_state_writes()
    with provider_attempt_process_locks(root.run_root):
        with root._lock:
            root._reload_state_for_coordinated_mutation()
            owner = resolve_aggregate_run_owner(manager)
            if record["run"] != _run(root.state, scope):
                raise ValueError("record run identity contradicts current state")
            root._validate_provider_attempt_publication_already_process_locked(
                manager, scope, ordinal
            )
            destination = root.run_root / relative
            _write_current_no_replace(destination, payload, root.run_root)
            root._record_provider_attempt_publication_already_process_locked(
                manager,
                scope,
                ordinal,
                relative_path=str(relative),
                file_sha256=digest,
                record_kind=kind,
            )
    return PublicationResult(relative, digest, payload, kind)


def _state_run(state: RunState) -> dict[str, str]:
    if not isinstance(state, RunState):
        raise TypeError("RunState required")
    if not _is_sha(state.workflow_checksum):
        raise ValueError("state workflow checksum is invalid")
    return {
        "run_id": state.run_id,
        "workflow_file": state.workflow_file,
        "workflow_checksum": state.workflow_checksum,
    }


def build_allocator_projection(state: RunState) -> dict[str, Any]:
    """Project the complete root-owned allocator without embedding its digest."""

    allocations = validate_provider_attempt_allocations(state.provider_attempt_allocations)
    scopes = [
        {
            "scope_sha256": scope_sha256,
            "scope": entry["scope"],
            "last_allocated_ordinal": entry["last_allocated_ordinal"],
            "events": entry["events"],
        }
        for scope_sha256, entry in sorted(allocations.items())
    ]
    return validate_allocator_projection(
        {"schema": ALLOCATION_PROJECTION_SCHEMA, "run": _state_run(state), "scopes": scopes}
    )


def validate_allocator_projection(value: Any) -> dict[str, Any]:
    projection = _closed(value, {"schema", "run", "scopes"}, "allocator projection")
    if projection["schema"] != ALLOCATION_PROJECTION_SCHEMA:
        raise ValueError("allocator projection schema is invalid")
    run = _closed(projection["run"], {"run_id", "workflow_file", "workflow_checksum"}, "projection run")
    _text(run["run_id"], "projection run_id")
    _text(run["workflow_file"], "projection workflow_file")
    if not _is_sha(run["workflow_checksum"]):
        raise ValueError("projection workflow checksum is invalid")
    scopes = projection["scopes"]
    if not isinstance(scopes, list):
        raise ValueError("projection scopes must be a list")
    allocations: dict[str, Any] = {}
    prior = ""
    for raw in scopes:
        row = _closed(raw, {"scope_sha256", "scope", "last_allocated_ordinal", "events"}, "projection scope")
        key = _text(row["scope_sha256"], "projection scope digest")
        if key <= prior:
            raise ValueError("projection scopes are duplicate or unsorted")
        prior = key
        try:
            scope = ProviderAttemptScope.from_dict(row["scope"])
        except (TypeError, ValueError) as exc:
            raise ValueError("projection scope is invalid") from exc
        if scope.key != key:
            raise ValueError("projection scope digest is invalid")
        if scope.run_id != run["run_id"] or scope.resume_scope.root_workflow_file != run["workflow_file"]:
            raise ValueError("projection scope contradicts run")
        allocations[key] = {
            "scope": row["scope"],
            "last_allocated_ordinal": row["last_allocated_ordinal"],
            "events": row["events"],
        }
    validate_provider_attempt_allocations(allocations)
    return dict(projection)


def allocator_projection_sha256(projection: Mapping[str, Any]) -> str:
    return _sha(_canonical_bytes(validate_allocator_projection(projection)))


def _index_sort(row: Mapping[str, Any]) -> tuple[bytes, str, int]:
    return (
        row["runtime_step_id"].encode("utf-8"),
        row["visit_key"],
        row["attempt_ordinal"],
    )


def _seal_index(index: dict[str, Any]) -> dict[str, Any]:
    body = dict(index)
    body.pop("index_sha256", None)
    index["index_sha256"] = _sha(_canonical_bytes(body))
    return index


def validate_index(value: Any) -> dict[str, Any]:
    index = _closed(
        value,
        {"schema", "run", "allocator_projection", "publications", "allocation_only_gaps", "index_sha256"},
        "validated index",
    )
    if index["schema"] != INDEX_SCHEMA:
        raise ValueError("validated index schema is invalid")
    run = _closed(index["run"], {"run_id", "workflow_file", "workflow_checksum"}, "index run")
    _text(run["run_id"], "index run_id")
    _text(run["workflow_file"], "index workflow_file")
    if not _is_sha(run["workflow_checksum"]):
        raise ValueError("index workflow checksum is invalid")
    summary = _closed(index["allocator_projection"], {"schema", "sha256", "scope_count", "event_count"}, "index projection")
    if summary["schema"] != ALLOCATION_PROJECTION_SCHEMA or not _is_sha(summary["sha256"]):
        raise ValueError("index allocator projection is invalid")
    _integer(summary["scope_count"], "index scope count")
    _integer(summary["event_count"], "index event count")
    publications = index["publications"]
    gaps = index["allocation_only_gaps"]
    if not isinstance(publications, list) or not isinstance(gaps, list):
        raise ValueError("index rows must be lists")
    publication_keys = {"scope_sha256", "runtime_step_id", "visit_key", "attempt_ordinal", "record_kind", "relative_path", "record_sha256", "record_file_sha256"}
    gap_keys = {"scope_sha256", "runtime_step_id", "visit_key", "attempt_ordinal"}
    scope_runtime_steps: dict[str, str] = {}
    for rows, keys, label in ((publications, publication_keys, "publication"), (gaps, gap_keys, "gap")):
        prior: tuple[bytes, str, int] | None = None
        for raw in rows:
            row = _closed(raw, keys, f"index {label}")
            if not _is_sha(row["scope_sha256"]):
                raise ValueError(f"index {label} scope digest is invalid")
            _text(row["runtime_step_id"], f"index {label} runtime step")
            visit = _text(row["visit_key"], f"index {label} visit key")
            if len(visit) != 24 or any(character not in "0123456789abcdef" for character in visit):
                raise ValueError(f"index {label} visit key is invalid")
            if visit != row["scope_sha256"][7:31]:
                raise ValueError(f"index {label} visit key contradicts scope digest")
            prior_runtime_step = scope_runtime_steps.setdefault(
                row["scope_sha256"], row["runtime_step_id"]
            )
            if prior_runtime_step != row["runtime_step_id"]:
                raise ValueError("index scope has conflicting runtime step identities")
            _integer(row["attempt_ordinal"], f"index {label} ordinal", 1)
            current = _index_sort(row)
            if prior is not None and current <= prior:
                raise ValueError(f"index {label} rows are duplicate or unsorted")
            prior = current
            if label == "publication":
                if row["record_kind"] not in {"prompt_snapshot", "failure"}:
                    raise ValueError("index publication kind is invalid")
                _text(row["relative_path"], "index publication path")
                if not _is_sha(row["record_sha256"]) or not _is_sha(row["record_file_sha256"]):
                    raise ValueError("index publication digest is invalid")
    identities = {
        (row["scope_sha256"], row["attempt_ordinal"]) for row in publications
    } | {(row["scope_sha256"], row["attempt_ordinal"]) for row in gaps}
    if len(identities) != len(publications) + len(gaps):
        raise ValueError("index attempt identities overlap")
    scope_count = len(
        {row["scope_sha256"] for row in publications}
        | {row["scope_sha256"] for row in gaps}
    )
    event_count = len(gaps) + 2 * len(publications)
    if summary["scope_count"] != scope_count or summary["event_count"] != event_count:
        raise ValueError("index allocator projection count is invalid")
    body = dict(index)
    claimed = body.pop("index_sha256", None)
    if not _is_sha(claimed) or claimed != _sha(_canonical_bytes(body)):
        raise ValueError("index_sha256 does not match index")
    return dict(index)


def _read_manifest_record(path: Path, kind: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("manifest-bound evidence record is missing") from exc
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest-bound evidence record is corrupt") from exc
    if not isinstance(value, Mapping):
        raise ValueError("manifest-bound evidence record is corrupt")
    if value.get("record_kind") != kind:
        raise ValueError("manifest-bound evidence record has wrong kind")
    canonical = canonical_record_bytes(value)
    if payload != canonical:
        raise ValueError("manifest-bound evidence record bytes are not canonical")
    return dict(value), payload


def _build_terminal_index(state: RunState, projection: Mapping[str, Any], root: Path) -> dict[str, Any]:
    publications: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    claimed_paths: set[str] = set()
    for entry in projection["scopes"]:
        scope = ProviderAttemptScope.from_dict(entry["scope"])
        if scope.run_id != state.run_id or scope.resume_scope.root_workflow_file != state.workflow_file:
            raise ValueError("allocator scope contradicts terminal run")
        visit_key = scope.key[7:31]
        published = {
            event["ordinal"]: event
            for event in entry["events"]
            if event["event"] == "evidence_published"
        }
        for ordinal in range(1, entry["last_allocated_ordinal"] + 1):
            base = {
                "scope_sha256": scope.key,
                "runtime_step_id": scope.runtime_step_id,
                "visit_key": visit_key,
                "attempt_ordinal": ordinal,
            }
            event = published.get(ordinal)
            if event is None:
                gaps.append(base)
                continue
            expected_path = str(evidence_relative_path(scope, ordinal))
            if event["relative_path"] != expected_path:
                raise ValueError("manifest evidence path contradicts attempt identity")
            if expected_path in claimed_paths:
                raise ValueError("duplicate manifest evidence path")
            claimed_paths.add(expected_path)
            record, payload = _read_manifest_record(root / expected_path, event["record_kind"])
            file_digest = _sha(payload)
            if file_digest != event["file_sha256"]:
                raise ValueError("manifest evidence file digest is invalid")
            if record["attempt"] != _attempt(scope, ordinal):
                raise ValueError("manifest evidence record identity is invalid")
            if record["run"] != _state_run(state):
                raise ValueError("manifest evidence run identity is invalid")
            publications.append(
                {
                    **base,
                    "record_kind": event["record_kind"],
                    "relative_path": expected_path,
                    "record_sha256": record["record_sha256"],
                    "record_file_sha256": file_digest,
                }
            )
    evidence_root = root / "workflow_lisp" / "prompt_dependencies"
    actual_paths = {
        str(path.relative_to(root))
        for path in evidence_root.rglob("attempt-*.json")
        if path.is_file()
    } if evidence_root.exists() else set()
    orphans = sorted(actual_paths - claimed_paths)
    if orphans:
        raise ValueError(f"orphan prompt dependency evidence: {orphans[0]}")
    publications.sort(key=_index_sort)
    gaps.sort(key=_index_sort)
    projection_digest = allocator_projection_sha256(projection)
    index = {
        "schema": INDEX_SCHEMA,
        "run": _state_run(state),
        "allocator_projection": {
            "schema": ALLOCATION_PROJECTION_SCHEMA,
            "sha256": projection_digest,
            "scope_count": len(projection["scopes"]),
            "event_count": sum(len(entry["events"]) for entry in projection["scopes"]),
        },
        "publications": publications,
        "allocation_only_gaps": gaps,
    }
    return validate_index(_seal_index(index))


def _write_index_no_replace(
    destination: Path, payload: bytes, durable_anchor: Path
) -> bool:
    _ensure_durable_directory_chain(destination.parent, durable_anchor)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    fd: int | None = None
    created = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("index write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        try:
            os.link(temporary, destination)
            created = True
            _fsync_directory(destination.parent)
        except FileExistsError:
            if destination.read_bytes() != payload:
                raise
        return created
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        else:
            _fsync_directory(destination.parent)


@dataclass(frozen=True)
class TerminalValidationResult:
    path: Path
    payload: bytes
    index: dict[str, Any]
    created: bool
    initial_state_bytes: int
    initial_state_sha256: str


def _read_terminal_state(state_path: Path) -> tuple[bytes, RunState]:
    payload = state_path.read_bytes()
    try:
        decoded = json.loads(payload)
        state = RunState.from_dict(decoded)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("terminal state file is invalid") from exc
    return payload, state


def validate_terminal_evidence(
    aggregate_root: str | Path,
    state_file: str | Path,
    *,
    _after_initial_read: Any = None,
    _after_index_publish: Any = None,
) -> TerminalValidationResult:
    """Validate a quiescent terminal allocator and publish its functional index."""

    root = Path(aggregate_root)
    state_path = Path(state_file)
    if state_path.absolute() != (root / "state.json").absolute():
        raise ValueError("state_file must be the authoritative aggregate-root state.json")
    with provider_attempt_process_locks(root):
        initial_bytes, state = _read_terminal_state(state_path)
        if state.status not in {"completed", "failed"}:
            raise ValueError("prompt dependency evidence validation requires terminal state")
        if state.run_root is None or Path(state.run_root).absolute() != root.absolute():
            raise ValueError("terminal state run root contradicts aggregate root")
        projection = build_allocator_projection(state)
        if _after_initial_read is not None:
            _after_initial_read()
        index = _build_terminal_index(state, projection, root)
        payload = _canonical_bytes(index)
        before_link, before_state = _read_terminal_state(state_path)
        if before_link != initial_bytes or build_allocator_projection(before_state) != projection:
            raise ValueError("terminal state changed during evidence validation")
        projection_digest = allocator_projection_sha256(projection)
        destination = root / "workflow_lisp" / "prompt_dependencies" / "validated-indexes" / f"{projection_digest[7:]}.json"
        created = _write_index_no_replace(destination, payload, root)
        if _after_index_publish is not None:
            _after_index_publish()
        final_bytes, final_state = _read_terminal_state(state_path)
        if final_bytes != initial_bytes or build_allocator_projection(final_state) != projection:
            if created:
                destination.unlink()
                _fsync_directory(destination.parent)
            raise ValueError("terminal state changed during evidence validation")
        return TerminalValidationResult(
            destination,
            payload,
            index,
            created,
            len(initial_bytes),
            _sha(initial_bytes),
        )


__all__ = [
    "SUCCESS_SCHEMA", "FAILURE_SCHEMA", "INDEX_SCHEMA", "ALLOCATION_PROJECTION_SCHEMA",
    "PublicationResult", "SuccessEvidenceBuild", "authored_row_id", "build_success_evidence", "validate_success_evidence",
    "build_failure_evidence", "validate_failure_evidence", "canonical_record_bytes",
    "evidence_relative_path", "publish_evidence_file",
    "build_allocator_projection", "validate_allocator_projection",
    "allocator_projection_sha256", "validate_index", "TerminalValidationResult",
    "validate_terminal_evidence",
]
