"""Read-only, content-free projection of persisted prompt-attempt identity."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .prompt_dependency_contract import PromptDependencyOriginKind
from .prompt_dependency_evidence import (
    FAILURE_SCHEMA,
    FRAGMENT_SUCCESS_SCHEMA,
    FRAGMENT_SUCCESS_SCHEMA_V2,
    PROMPT_FRAGMENT_PREPARATION_FAILURE_SCHEMA,
    _attempt,
    canonical_record_bytes,
    evidence_relative_path,
)
from .prompt_identity import (
    PromptComparisonRecord,
    ROLE_ORDER,
    compare_prompt_attempt_history,
)
from .provider_attempts import (
    ProviderAttemptScope,
    validate_provider_attempt_allocations,
)


PROMPT_CONTEXT_REPORT_SCHEMA = "workflow_prompt_context_report.v1"
_FRAGMENT_ORIGIN = (
    PromptDependencyOriginKind.WORKFLOW_LISP_PROMPT_FRAGMENT.value
)


@dataclass(frozen=True)
class _ProjectedAttempt:
    scope: ProviderAttemptScope
    ordinal: int
    event_kind: str | None
    outcome: str
    record_status: str
    record_sha256: str | None
    identity: Mapping[str, Any] | None
    qualifies_scope: bool


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _empty_report() -> dict[str, Any]:
    return {
        "schema_version": PROMPT_CONTEXT_REPORT_SCHEMA,
        "attempts": [],
    }


def _invalid_attempt(
    scope: ProviderAttemptScope,
    ordinal: int,
    event_kind: str | None,
) -> _ProjectedAttempt:
    return _ProjectedAttempt(
        scope=scope,
        ordinal=ordinal,
        event_kind=event_kind,
        outcome="invalid_snapshot",
        record_status="invalid",
        record_sha256=None,
        identity=None,
        qualifies_scope=False,
    )


def _load_publication(
    *,
    state: Mapping[str, Any],
    root: Path,
    scope: ProviderAttemptScope,
    ordinal: int,
    event: Mapping[str, Any] | None,
    authority: str | None,
) -> _ProjectedAttempt:
    if event is None:
        return _ProjectedAttempt(
            scope=scope,
            ordinal=ordinal,
            event_kind=None,
            outcome="allocation_only",
            record_status="allocation_only",
            record_sha256=None,
            identity=None,
            qualifies_scope=False,
        )
    event_kind = event["record_kind"]
    try:
        expected_relative = str(evidence_relative_path(scope, ordinal))
        if event["relative_path"] != expected_relative:
            raise ValueError("publication path contradicts attempt identity")
        payload = (root / expected_relative).read_bytes()
        if _sha(payload) != event["file_sha256"]:
            raise ValueError("publication digest is invalid")
        record = json.loads(payload)
        if not isinstance(record, Mapping):
            raise ValueError("publication record is invalid")
        if record.get("record_kind") != event_kind:
            raise ValueError("publication record kind is invalid")
        canonical = canonical_record_bytes(
            record,
            compiler_fragment_identity_schema_version=authority,
        )
        if canonical != payload:
            raise ValueError("publication record is not canonical")
        if record.get("attempt") != _attempt(scope, ordinal):
            raise ValueError("publication attempt identity is invalid")
        if record.get("run") != {
            "run_id": state.get("run_id"),
            "workflow_file": state.get("workflow_file"),
            "workflow_checksum": state.get("workflow_checksum"),
        }:
            raise ValueError("publication run identity is invalid")

        schema = record.get("schema")
        record_sha256 = record.get("record_sha256")
        if schema == FRAGMENT_SUCCESS_SCHEMA_V2:
            identity = record["prompt_attempt_identity"]
            return _ProjectedAttempt(
                scope=scope,
                ordinal=ordinal,
                event_kind=event_kind,
                outcome="v2_snapshot",
                record_status="snapshot",
                record_sha256=record_sha256,
                identity=identity,
                qualifies_scope=True,
            )
        if schema == FRAGMENT_SUCCESS_SCHEMA:
            return _ProjectedAttempt(
                scope=scope,
                ordinal=ordinal,
                event_kind=event_kind,
                outcome="legacy_snapshot",
                record_status="legacy_snapshot",
                record_sha256=record_sha256,
                identity=None,
                qualifies_scope=True,
            )
        if schema == PROMPT_FRAGMENT_PREPARATION_FAILURE_SCHEMA:
            fragment = record.get("fragment")
            if (
                authority is None
                or not isinstance(fragment, Mapping)
                or fragment.get("identity_schema_version") != authority
            ):
                raise ValueError(
                    "preparation failure contradicts persisted authority"
                )
            return _ProjectedAttempt(
                scope=scope,
                ordinal=ordinal,
                event_kind=event_kind,
                outcome="preparation_failure",
                record_status="failure",
                record_sha256=record_sha256,
                identity=None,
                qualifies_scope=True,
            )
        if (
            schema == FAILURE_SCHEMA
            and isinstance(record.get("compiler_contract"), Mapping)
            and record["compiler_contract"].get("origin_kind")
            == _FRAGMENT_ORIGIN
        ):
            return _ProjectedAttempt(
                scope=scope,
                ordinal=ordinal,
                event_kind=event_kind,
                outcome="failure",
                record_status="failure",
                record_sha256=record_sha256,
                identity=None,
                qualifies_scope=True,
            )
    except (
        FileNotFoundError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return _invalid_attempt(scope, ordinal, event_kind)
    return _invalid_attempt(scope, ordinal, event_kind)


def _comparison_record(
    attempt: _ProjectedAttempt,
) -> PromptComparisonRecord:
    return PromptComparisonRecord(
        scope=attempt.scope,
        ordinal=attempt.ordinal,
        outcome=attempt.outcome,
        prompt_attempt_identity=attempt.identity,
    )


def _comparison(
    current: _ProjectedAttempt,
    attempts: tuple[_ProjectedAttempt, ...],
) -> dict[str, Any]:
    candidates = [
        _comparison_record(candidate)
        for candidate in attempts
        if (
            candidate.ordinal < current.ordinal
            and candidate.event_kind == "prompt_snapshot"
        )
    ]
    projected = compare_prompt_attempt_history(
        _comparison_record(current),
        candidates,
    )
    return {
        "status": projected["status"],
        "previous_attempt_ordinal": projected[
            "previous_attempt_ordinal"
        ],
        "classifications": list(projected["classifications"]),
        "reason": projected["reason"],
    }


def _identity_projection(
    identity: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if identity is None:
        return None
    roles = identity["roles"]
    return {
        "composition_sha256": identity["composition_sha256"],
        "final_prompt_sha256": identity["final_prompt"]["sha256"],
        "role_sha256": {
            role_key: roles[role_key]["sha256"]
            for role_key in ROLE_ORDER
        },
    }


def project_prompt_context(
    state: Mapping[str, Any],
    run_root: str | Path,
) -> dict[str, Any]:
    """Project allocator-domain prompt context without mutating run state."""

    if not isinstance(state, Mapping):
        raise TypeError("persisted run state must be a mapping")
    raw_allocations = state.get("provider_attempt_allocations", {})
    allocations = validate_provider_attempt_allocations(raw_allocations)
    if not allocations:
        return _empty_report()

    root = Path(run_root)
    qualified_attempts: list[
        tuple[ProviderAttemptScope, tuple[_ProjectedAttempt, ...]]
    ] = []
    for scope_key, allocation in allocations.items():
        scope = ProviderAttemptScope.from_dict(allocation["scope"])
        if scope.key != scope_key:
            raise ValueError("allocator scope identity is invalid")
        publications = {
            event["ordinal"]: event
            for event in allocation["events"]
            if event["event"] == "evidence_published"
        }
        authority = allocation.get(
            "prompt_fragment_identity_schema_version"
        )
        attempts = tuple(
            _load_publication(
                state=state,
                root=root,
                scope=scope,
                ordinal=ordinal,
                event=publications.get(ordinal),
                authority=authority,
            )
            for ordinal in range(
                1,
                allocation["last_allocated_ordinal"] + 1,
            )
        )
        if any(attempt.qualifies_scope for attempt in attempts):
            qualified_attempts.append((scope, attempts))

    rows: list[dict[str, Any]] = []
    for scope, attempts in qualified_attempts:
        for attempt in attempts:
            rows.append(
                {
                    "runtime_step_id": scope.runtime_step_id,
                    "visit_key": scope.key[7:31],
                    "attempt_ordinal": attempt.ordinal,
                    "record_status": attempt.record_status,
                    "record_sha256": attempt.record_sha256,
                    "identity": _identity_projection(attempt.identity),
                    "comparison": _comparison(attempt, attempts),
                }
            )
    rows.sort(
        key=lambda row: (
            row["runtime_step_id"].encode("utf-8"),
            row["visit_key"],
            row["attempt_ordinal"],
        )
    )
    return {
        "schema_version": PROMPT_CONTEXT_REPORT_SCHEMA,
        "attempts": rows,
    }


__all__ = [
    "PROMPT_CONTEXT_REPORT_SCHEMA",
    "project_prompt_context",
]
