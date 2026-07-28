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
    FRAGMENT_SUCCESS_SCHEMA_V3,
    PROMPT_FRAGMENT_PREPARATION_FAILURE_SCHEMA,
    _attempt,
    canonical_record_bytes,
    evidence_relative_path,
)
from .prompt_identity import (
    PROMPT_ATTEMPT_IDENTITY_V2_VERSION,
    PROMPT_ATTEMPT_IDENTITY_VERSION,
    PromptComparisonRecord,
    ROLE_ORDER,
    canonical_json_bytes,
    compare_prompt_attempt_history,
    validate_prompt_attempt_identity,
)
from .provider_attempts import (
    ProviderAttemptScope,
    validate_provider_attempt_allocations,
)


PROMPT_CONTEXT_REPORT_SCHEMA = "workflow_prompt_context_report.v1"
PROMPT_CONTEXT_REPORT_V2_SCHEMA = "workflow_prompt_context_report.v2"
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


def _empty_report(
    schema_version: str = PROMPT_CONTEXT_REPORT_SCHEMA,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
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
    report_schema: str,
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
        if (
            report_schema == PROMPT_CONTEXT_REPORT_V2_SCHEMA
            and schema == FRAGMENT_SUCCESS_SCHEMA_V3
        ):
            identity = record["prompt_attempt_identity"]
            return _ProjectedAttempt(
                scope=scope,
                ordinal=ordinal,
                event_kind=event_kind,
                outcome="v3_snapshot",
                record_status="snapshot",
                record_sha256=record_sha256,
                identity=identity,
                qualifies_scope=True,
            )
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
    *,
    report_schema: str,
) -> dict[str, Any] | None:
    if identity is None:
        return None
    validated = validate_prompt_attempt_identity(identity)
    roles = validated["roles"]
    if report_schema == PROMPT_CONTEXT_REPORT_V2_SCHEMA:
        identity_version = validated["schema_version"]
        if identity_version == PROMPT_ATTEMPT_IDENTITY_VERSION:
            legacy_final_prompt_sha256: str | None = validated[
                "final_prompt"
            ]["sha256"]
            canonical_composed: Mapping[str, Any] | None = None
            actual_deliveries: list[Mapping[str, Any]] | None = None
        elif identity_version == PROMPT_ATTEMPT_IDENTITY_V2_VERSION:
            legacy_final_prompt_sha256 = None
            canonical_composed = json.loads(
                canonical_json_bytes(validated["canonical_composed"])
            )
            actual_deliveries = json.loads(
                canonical_json_bytes(validated["actual_deliveries"])
            )
        else:  # pragma: no cover - version validator owns this closure.
            raise ValueError("prompt attempt identity version is invalid")
        return {
            "identity_version": identity_version,
            "composition_sha256": validated["composition_sha256"],
            "legacy_final_prompt_sha256": (
                legacy_final_prompt_sha256
            ),
            "canonical_composed": canonical_composed,
            "actual_deliveries": actual_deliveries,
            "role_sha256": {
                role_key: roles[role_key]["sha256"]
                for role_key in ROLE_ORDER
            },
        }
    return {
        "composition_sha256": validated["composition_sha256"],
        "final_prompt_sha256": validated["final_prompt"]["sha256"],
        "role_sha256": {
            role_key: roles[role_key]["sha256"]
            for role_key in ROLE_ORDER
        },
    }


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )


def _validate_report_v2_shape(value: object) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"schema_version", "attempts"}
        or value.get("schema_version") != PROMPT_CONTEXT_REPORT_V2_SCHEMA
        or not isinstance(value.get("attempts"), list)
    ):
        raise ValueError("report-v2 projection top level is invalid")

    row_keys = {
        "runtime_step_id",
        "visit_key",
        "attempt_ordinal",
        "record_status",
        "record_sha256",
        "identity",
        "comparison",
    }
    identity_keys = {
        "identity_version",
        "composition_sha256",
        "legacy_final_prompt_sha256",
        "canonical_composed",
        "actual_deliveries",
        "role_sha256",
    }
    comparison_keys = {
        "status",
        "previous_attempt_ordinal",
        "classifications",
        "reason",
    }
    for row in value["attempts"]:
        if not isinstance(row, Mapping) or set(row) != row_keys:
            raise ValueError("report-v2 projection attempt row is invalid")
        status = row["record_status"]
        if status not in {
            "snapshot",
            "legacy_snapshot",
            "failure",
            "allocation_only",
            "invalid",
        }:
            raise ValueError("report-v2 projection status is invalid")
        record_sha256 = row["record_sha256"]
        if status in {"snapshot", "legacy_snapshot", "failure"}:
            if not _is_sha256(record_sha256):
                raise ValueError(
                    "report-v2 projection record digest is invalid"
                )
        elif record_sha256 is not None:
            raise ValueError(
                "report-v2 projection record digest is invalid"
            )

        identity = row["identity"]
        if status != "snapshot":
            if identity is not None:
                raise ValueError(
                    "report-v2 projection identity nullability is invalid"
                )
        else:
            if not isinstance(identity, Mapping) or set(identity) != (
                identity_keys
            ):
                raise ValueError(
                    "report-v2 projection identity shape is invalid"
                )
            identity_version = identity["identity_version"]
            if identity_version not in {
                PROMPT_ATTEMPT_IDENTITY_VERSION,
                PROMPT_ATTEMPT_IDENTITY_V2_VERSION,
            }:
                raise ValueError(
                    "report-v2 projection identity version is invalid"
                )
            if not _is_sha256(identity["composition_sha256"]):
                raise ValueError(
                    "report-v2 projection composition digest is invalid"
                )
            roles = identity["role_sha256"]
            if (
                not isinstance(roles, Mapping)
                or tuple(roles) != ROLE_ORDER
                or any(not _is_sha256(roles[role]) for role in ROLE_ORDER)
            ):
                raise ValueError(
                    "report-v2 projection role digests are invalid"
                )
            if identity_version == PROMPT_ATTEMPT_IDENTITY_VERSION:
                if (
                    not _is_sha256(identity["legacy_final_prompt_sha256"])
                    or identity["canonical_composed"] is not None
                    or identity["actual_deliveries"] is not None
                ):
                    raise ValueError(
                        "report-v2 projection v1 fields are invalid"
                    )
            elif (
                identity["legacy_final_prompt_sha256"] is not None
                or not isinstance(identity["canonical_composed"], Mapping)
                or set(identity["canonical_composed"]) != {"bytes", "sha256"}
                or not isinstance(
                    identity["canonical_composed"].get("bytes"),
                    int,
                )
                or isinstance(
                    identity["canonical_composed"].get("bytes"),
                    bool,
                )
                or identity["canonical_composed"]["bytes"] < 0
                or not _is_sha256(
                    identity["canonical_composed"].get("sha256")
                )
                or not isinstance(identity["actual_deliveries"], list)
            ):
                raise ValueError(
                    "report-v2 projection v2 fields are invalid"
                )

        comparison = row["comparison"]
        if (
            not isinstance(comparison, Mapping)
            or set(comparison) != comparison_keys
        ):
            raise ValueError(
                "report-v2 projection comparison shape is invalid"
            )


def _project_prompt_context(
    state: Mapping[str, Any],
    run_root: str | Path,
    *,
    report_schema: str,
) -> dict[str, Any]:
    """Project allocator-domain prompt context without mutating run state."""

    if report_schema not in {
        PROMPT_CONTEXT_REPORT_SCHEMA,
        PROMPT_CONTEXT_REPORT_V2_SCHEMA,
    }:
        raise ValueError("prompt context report schema is invalid")
    if not isinstance(state, Mapping):
        raise TypeError("persisted run state must be a mapping")
    raw_allocations = state.get("provider_attempt_allocations", {})
    allocations = validate_provider_attempt_allocations(raw_allocations)
    if not allocations:
        return _empty_report(report_schema)

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
                report_schema=report_schema,
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
                    "identity": _identity_projection(
                        attempt.identity,
                        report_schema=report_schema,
                    ),
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
        "schema_version": report_schema,
        "attempts": rows,
    }


def project_prompt_context(
    state: Mapping[str, Any],
    run_root: str | Path,
) -> dict[str, Any]:
    """Project the unchanged public Q3 report-v1 shape."""

    return _project_prompt_context(
        state,
        run_root,
        report_schema=PROMPT_CONTEXT_REPORT_SCHEMA,
    )


def project_prompt_context_v2(
    state: Mapping[str, Any],
    run_root: str | Path,
) -> dict[str, Any]:
    """Project the internal Q5 version-strict report-v2 shape."""

    candidate = _project_prompt_context(
        state,
        run_root,
        report_schema=PROMPT_CONTEXT_REPORT_V2_SCHEMA,
    )
    return validate_prompt_context_report_v2_projection(
        candidate,
        state=state,
        run_root=run_root,
    )


def validate_prompt_context_report_v2_projection(
    value: object,
    *,
    state: Mapping[str, Any],
    run_root: str | Path,
) -> dict[str, Any]:
    """Validate internal report v2 against its fixed evidence sources."""

    _validate_report_v2_shape(value)
    expected = _project_prompt_context(
        state,
        run_root,
        report_schema=PROMPT_CONTEXT_REPORT_V2_SCHEMA,
    )
    if value != expected:
        raise ValueError(
            "report-v2 projection disagrees with validated source records"
        )
    return json.loads(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )


__all__ = [
    "PROMPT_CONTEXT_REPORT_SCHEMA",
    "project_prompt_context",
]
