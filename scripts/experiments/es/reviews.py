"""Closed review and adjudication records for the ES F1 study.

The evaluator emits role-specific payloads.  This module validates those
payloads against their frozen schemas, binds them to controller call context,
and applies the fail-closed adjudication rules without mutating source records.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator


SCIENTIFIC_APPLICATION_SEMANTICS = "SCIENTIFIC_APPLICATION_SEMANTICS"
API_PERSISTENCE_MIGRATION_MAINTAINABILITY = (
    "API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
)
INITIAL = "INITIAL"
ADJUDICATOR = "ADJUDICATOR"
INTEGRATED = "INTEGRATED"
WRAPPER_SCHEMA_VERSION = "es-f1-review-record.v1"
MAX_RATIONALE_LENGTH = 4_096

PERSPECTIVE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    SCIENTIFIC_APPLICATION_SEMANTICS: (
        "SEMANTIC_AND_SCIENTIFIC_CORRECTNESS",
        "TASK_INTENT_COMPLETENESS",
        "DIAGNOSIS_OF_CURRENT_DESIGN_SMELL",
        "OWNERSHIP_AND_BOUNDARY_COHERENCE",
    ),
    API_PERSISTENCE_MIGRATION_MAINTAINABILITY: (
        "ARTIFACT_RELOAD_AND_MIGRATION_REASONING",
        "MAINTAINABILITY_AND_SIMPLICITY",
        "EXTENSION_EDIT_LOCALITY",
        "TEST_AND_EVIDENCE_QUALITY",
        "SCOPE_DISCIPLINE",
        "FAILURE_DIAGNOSTICS",
        "DOCUMENTATION_SUFFICIENCY",
        "LIKELY_LATENT_DEFECTS",
    ),
}

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_ROOT = _REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/evaluator"
REVIEW_SCHEMA_PATHS: dict[tuple[str, str | None], Path] = {
    (INITIAL, SCIENTIFIC_APPLICATION_SEMANTICS): (
        _SCHEMA_ROOT
        / "initial-scientific-application-semantics-review.schema.json"
    ),
    (INITIAL, API_PERSISTENCE_MIGRATION_MAINTAINABILITY): (
        _SCHEMA_ROOT
        / "initial-api-persistence-migration-maintainability-review.schema.json"
    ),
    (ADJUDICATOR, None): _SCHEMA_ROOT / "adjudicator-review.schema.json",
    (INTEGRATED, None): _SCHEMA_ROOT / "integrated-review.schema.json",
}

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OPAQUE_LABEL_RE = re.compile(r"opaque-[0-9a-f]{64}\Z")
_WRAPPER_KEYS = frozenset(
    {
        "schema_version",
        "attempt_id",
        "review_kind",
        "perspective_id",
        "session_id",
        "provider_attempt_id",
        "receipt_digest",
        "packet_set_digest",
        "presentation_order",
        "payload",
        "payload_digest",
    }
)


class ReviewContractError(ValueError):
    """A review payload, binding, or resolution invariant failed closed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _raise(code: str, detail: str = "") -> NoReturn:
    raise ReviewContractError(code, detail)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8", "strict")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ReviewContractError("review_json_invalid", str(exc)) from exc


def _clone_json(value: object) -> Any:
    try:
        return json.loads(_canonical_json_bytes(value))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:  # pragma: no cover
        raise ReviewContractError("review_json_invalid", str(exc)) from exc


def canonical_payload_digest(payload: object) -> str:
    """Return the canonical SHA-256 binding for one review payload."""

    return "sha256:" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        _raise("review_binding_invalid", field)
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise ReviewContractError("review_binding_invalid", field) from exc
    return value


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _raise("review_binding_invalid", field)
    return value


def _normalized_presentation_order(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 4
    ):
        _raise("review_presentation_order_invalid")
    labels: list[str] = []
    for label in value:
        if (
            not isinstance(label, str)
            or _OPAQUE_LABEL_RE.fullmatch(label) is None
        ):
            _raise("review_presentation_order_invalid", "opaque_label")
        labels.append(label)
    if len(set(labels)) != 4:
        _raise("review_presentation_order_invalid", "labels_not_unique")
    return tuple(labels)


def canonical_pair_order(labels: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Return the six canonical upper-triangle pairs for four labels."""

    normalized = _normalized_presentation_order(labels)
    return tuple(
        (normalized[left], normalized[right])
        for left in range(4)
        for right in range(left + 1, 4)
    )


def _normalized_citable_items(
    value: object,
    *,
    presentation_order: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, Mapping) or set(value) != set(presentation_order):
        _raise("review_citable_items_invalid", "labels")
    result: dict[str, tuple[str, ...]] = {}
    for label in presentation_order:
        item_ids = value[label]
        if (
            not isinstance(item_ids, Sequence)
            or isinstance(item_ids, (str, bytes, bytearray))
            or not item_ids
        ):
            _raise("review_citable_items_invalid", label)
        normalized = tuple(
            _identifier(item_id, field="citable_item_id") for item_id in item_ids
        )
        if len(normalized) != len(set(normalized)):
            _raise("review_citable_items_invalid", f"{label}:duplicate")
        result[label] = normalized
    return result


def _schema_path(review_kind: object, perspective_id: object) -> Path:
    if not isinstance(review_kind, str):
        _raise("review_role_invalid", "review_kind")
    if review_kind == INITIAL:
        if not isinstance(perspective_id, str):
            _raise("review_role_invalid", "initial_perspective")
        key = (INITIAL, perspective_id)
    elif review_kind in {ADJUDICATOR, INTEGRATED}:
        if perspective_id is not None:
            _raise("review_role_invalid", "non_initial_perspective")
        key = (str(review_kind), None)
    else:
        _raise("review_role_invalid", "review_kind")
    try:
        return REVIEW_SCHEMA_PATHS[key]
    except KeyError as exc:
        raise ReviewContractError("review_role_invalid", str(key)) from exc


def _load_schema(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(value)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ReviewContractError("review_schema_invalid", str(path)) from exc
    if not isinstance(value, dict):
        _raise("review_schema_invalid", str(path))
    return value


def _validate_rationale(value: object, *, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_RATIONALE_LENGTH
    ):
        _raise("review_rationale_invalid", field)


def _validate_citations(
    citations: object,
    *,
    citable_items: Mapping[str, tuple[str, ...]],
    field: str,
) -> None:
    if not isinstance(citations, list) or not citations:
        _raise("review_citation_invalid", field)
    for index, citation in enumerate(citations):
        if not isinstance(citation, dict):
            _raise("review_citation_invalid", f"{field}[{index}]")
        label = citation.get("opaque_label")
        item_id = citation.get("citable_item_id")
        if not isinstance(label, str) or label not in citable_items:
            _raise("review_citation_invalid", f"{field}[{index}].opaque_label")
        if item_id not in citable_items[label]:
            _raise("review_citation_invalid", f"{field}[{index}].citable_item_id")


def validate_review_payload(
    payload: object,
    *,
    review_kind: str,
    perspective_id: str | None,
    presentation_order: Sequence[str],
    citable_item_ids_by_label: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Validate and normalize one closed role-specific review payload."""

    order = _normalized_presentation_order(presentation_order)
    citable_items = _normalized_citable_items(
        citable_item_ids_by_label,
        presentation_order=order,
    )
    path = _schema_path(review_kind, perspective_id)
    normalized = _clone_json(payload)
    schema = _load_schema(path)
    errors = sorted(Draft202012Validator(schema).iter_errors(normalized), key=str)
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path)
        _raise("review_payload_invalid", f"{location}:{first.message}")
    if not isinstance(normalized, dict):  # Guaranteed by the schema.
        _raise("review_payload_invalid", "not_object")

    if review_kind == INITIAL:
        if perspective_id is None:  # _schema_path rejects this; narrow for typing.
            _raise("review_role_invalid", "initial_perspective")
        candidates = normalized["candidates"]
        if [candidate["opaque_label"] for candidate in candidates] != list(order):
            _raise("review_candidate_order_invalid")
        expected_dimensions = PERSPECTIVE_DIMENSIONS[perspective_id]
        for candidate in candidates:
            label = candidate["opaque_label"]
            dimensions = candidate["dimensions"]
            if [row["dimension"] for row in dimensions] != list(
                expected_dimensions
            ):
                _raise("review_dimension_order_invalid", label)
            for index, row in enumerate(dimensions):
                field = f"candidates.{label}.dimensions[{index}]"
                _validate_rationale(row["rationale"], field=f"{field}.rationale")
                _validate_citations(
                    row["citations"],
                    citable_items=citable_items,
                    field=f"{field}.citations",
                )

    expected_pairs = canonical_pair_order(order)
    pairwise_results = normalized["pairwise_results"]
    actual_pairs = tuple(
        (row["candidate_a_label"], row["candidate_b_label"])
        for row in pairwise_results
    )
    if actual_pairs != expected_pairs:
        _raise("review_pair_order_invalid")
    for index, row in enumerate(pairwise_results):
        field = f"pairwise_results[{index}]"
        _validate_rationale(row["rationale"], field=f"{field}.rationale")
        _validate_citations(
            row["citations"],
            citable_items=citable_items,
            field=f"{field}.citations",
        )
    return normalized


def _reject_reused_identity(
    *,
    session_id: str,
    provider_attempt_id: str,
    existing_records: Sequence[object],
) -> None:
    for index, existing in enumerate(existing_records):
        if not isinstance(existing, Mapping):
            _raise("review_identity_invalid", f"existing_records[{index}]")
        if existing.get("session_id") == session_id:
            _raise("review_identity_reused", "session identity")
        if existing.get("provider_attempt_id") == provider_attempt_id:
            _raise("review_identity_reused", "provider-attempt identity")


def seal_review_record(
    payload: object,
    *,
    attempt_id: str,
    review_kind: str,
    perspective_id: str | None,
    session_id: str,
    provider_attempt_id: str,
    receipt_digest: str,
    packet_set_digest: str,
    presentation_order: Sequence[str],
    citable_item_ids_by_label: Mapping[str, Sequence[str]],
    existing_records: Sequence[object] = (),
) -> dict[str, Any]:
    """Seal a validated payload into its immutable controller binding."""

    attempt = _identifier(attempt_id, field="attempt_id")
    session = _identifier(session_id, field="session_id")
    provider_attempt = _identifier(
        provider_attempt_id,
        field="provider_attempt_id",
    )
    receipt = _digest(receipt_digest, field="receipt_digest")
    packet_set = _digest(packet_set_digest, field="packet_set_digest")
    order = _normalized_presentation_order(presentation_order)
    normalized_payload = validate_review_payload(
        payload,
        review_kind=review_kind,
        perspective_id=perspective_id,
        presentation_order=order,
        citable_item_ids_by_label=citable_item_ids_by_label,
    )
    _reject_reused_identity(
        session_id=session,
        provider_attempt_id=provider_attempt,
        existing_records=existing_records,
    )
    return {
        "schema_version": WRAPPER_SCHEMA_VERSION,
        "attempt_id": attempt,
        "review_kind": review_kind,
        "perspective_id": perspective_id,
        "session_id": session,
        "provider_attempt_id": provider_attempt,
        "receipt_digest": receipt,
        "packet_set_digest": packet_set,
        "presentation_order": list(order),
        "payload": normalized_payload,
        "payload_digest": canonical_payload_digest(normalized_payload),
    }


def validate_review_record(
    record: object,
    *,
    citable_item_ids_by_label: Mapping[str, Sequence[str]],
    existing_records: Sequence[object] = (),
) -> dict[str, Any]:
    """Validate a closed controller wrapper and all of its payload bindings."""

    normalized = _clone_json(record)
    if not isinstance(normalized, dict) or set(normalized) != _WRAPPER_KEYS:
        _raise("review_record_invalid", "wrapper_keys")
    if normalized["schema_version"] != WRAPPER_SCHEMA_VERSION:
        _raise("review_record_invalid", "schema_version")
    attempt = _identifier(normalized["attempt_id"], field="attempt_id")
    session = _identifier(normalized["session_id"], field="session_id")
    provider_attempt = _identifier(
        normalized["provider_attempt_id"],
        field="provider_attempt_id",
    )
    receipt = _digest(normalized["receipt_digest"], field="receipt_digest")
    packet_set = _digest(
        normalized["packet_set_digest"],
        field="packet_set_digest",
    )
    order = _normalized_presentation_order(normalized["presentation_order"])
    review_kind = normalized["review_kind"]
    perspective_id = normalized["perspective_id"]
    payload = validate_review_payload(
        normalized["payload"],
        review_kind=review_kind,
        perspective_id=perspective_id,
        presentation_order=order,
        citable_item_ids_by_label=citable_item_ids_by_label,
    )
    if normalized["payload_digest"] != canonical_payload_digest(payload):
        _raise("review_payload_digest_mismatch")
    _reject_reused_identity(
        session_id=session,
        provider_attempt_id=provider_attempt,
        existing_records=existing_records,
    )
    return {
        "schema_version": WRAPPER_SCHEMA_VERSION,
        "attempt_id": attempt,
        "review_kind": review_kind,
        "perspective_id": perspective_id,
        "session_id": session,
        "provider_attempt_id": provider_attempt,
        "receipt_digest": receipt,
        "packet_set_digest": packet_set,
        "presentation_order": list(order),
        "payload": payload,
        "payload_digest": normalized["payload_digest"],
    }


def _validated_initial_pair(
    first: object,
    second: object,
    *,
    citable_item_ids_by_label: Mapping[str, Sequence[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        left = validate_review_record(
            first,
            citable_item_ids_by_label=citable_item_ids_by_label,
        )
        right = validate_review_record(
            second,
            citable_item_ids_by_label=citable_item_ids_by_label,
        )
        perspectives = {left["perspective_id"], right["perspective_id"]}
        if (
            left["review_kind"] != INITIAL
            or right["review_kind"] != INITIAL
            or perspectives != set(PERSPECTIVE_DIMENSIONS)
            or left["attempt_id"] != right["attempt_id"]
            or left["packet_set_digest"] != right["packet_set_digest"]
            or left["presentation_order"] != right["presentation_order"]
            or left["session_id"] == right["session_id"]
            or left["provider_attempt_id"] == right["provider_attempt_id"]
        ):
            _raise("initial_review_failure", "initial_pair_binding")
    except ReviewContractError as exc:
        if exc.code == "initial_review_failure":
            raise
        raise ReviewContractError("initial_review_failure", str(exc)) from exc
    return left, right


def material_disagreements(
    first: object,
    second: object,
    *,
    citable_item_ids_by_label: Mapping[str, Sequence[str]],
) -> tuple[tuple[str, str], ...]:
    """Return only pairs whose normalized outcomes differ."""

    left, right = _validated_initial_pair(
        first,
        second,
        citable_item_ids_by_label=citable_item_ids_by_label,
    )
    pairs = canonical_pair_order(left["presentation_order"])
    left_rows = left["payload"]["pairwise_results"]
    right_rows = right["payload"]["pairwise_results"]
    return tuple(
        pair
        for pair, left_row, right_row in zip(
            pairs,
            left_rows,
            right_rows,
            strict=True,
        )
        if left_row["outcome"] != right_row["outcome"]
    )


def _failed_adjudication_payload(
    first: Mapping[str, Any],
    *,
    disputed_indices: frozenset[int],
    citable_item_ids_by_label: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    rows = deepcopy(first["payload"]["pairwise_results"])
    for index in disputed_indices:
        original = rows[index]
        rows[index] = {
            "candidate_a_label": original["candidate_a_label"],
            "candidate_b_label": original["candidate_b_label"],
            "outcome": "INDETERMINATE",
            "rationale": (
                "Adjudication failed; the disputed pair is sealed "
                "INDETERMINATE."
            ),
            "citations": deepcopy(original["citations"]),
        }
    payload = {
        "schema_version": "es-f1-adjudicator-review.v1",
        "pairwise_results": rows,
    }
    return validate_review_payload(
        payload,
        review_kind=ADJUDICATOR,
        perspective_id=None,
        presentation_order=first["presentation_order"],
        citable_item_ids_by_label=citable_item_ids_by_label,
    )


def resolve_adjudication(
    first: object,
    second: object,
    adjudicator_record: object,
    *,
    citable_item_ids_by_label: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Resolve disputed rows or return the prescribed fail-closed vector."""

    left, right = _validated_initial_pair(
        first,
        second,
        citable_item_ids_by_label=citable_item_ids_by_label,
    )
    left_rows = left["payload"]["pairwise_results"]
    right_rows = right["payload"]["pairwise_results"]
    disputed_indices = frozenset(
        index
        for index, (left_row, right_row) in enumerate(
            zip(left_rows, right_rows, strict=True)
        )
        if left_row["outcome"] != right_row["outcome"]
    )
    if not disputed_indices:
        _raise("adjudication_not_required")

    try:
        adjudicator = validate_review_record(
            adjudicator_record,
            citable_item_ids_by_label=citable_item_ids_by_label,
            existing_records=(left, right),
        )
        if (
            adjudicator["review_kind"] != ADJUDICATOR
            or adjudicator["attempt_id"] != left["attempt_id"]
            or adjudicator["packet_set_digest"] != left["packet_set_digest"]
            or adjudicator["presentation_order"] != left["presentation_order"]
        ):
            _raise("adjudicator_record_invalid", "context_binding")
        adjudicated_rows = adjudicator["payload"]["pairwise_results"]
        for index, row in enumerate(adjudicated_rows):
            if index not in disputed_indices and row != left_rows[index]:
                _raise("adjudicator_record_invalid", "agreed_row_changed")
    except ReviewContractError:
        return _failed_adjudication_payload(
            left,
            disputed_indices=disputed_indices,
            citable_item_ids_by_label=citable_item_ids_by_label,
        )
    return deepcopy(adjudicator["payload"])


def _failed_integrated_payload(
    *,
    presentation_order: tuple[str, ...],
    citable_items: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    rows = []
    for left, right in canonical_pair_order(presentation_order):
        rows.append(
            {
                "candidate_a_label": left,
                "candidate_b_label": right,
                "outcome": "INDETERMINATE",
                "rationale": (
                    "Integrated review failed; this pair is sealed "
                    "INDETERMINATE."
                ),
                "citations": [
                    {
                        "opaque_label": left,
                        "citable_item_id": citable_items[left][0],
                    },
                    {
                        "opaque_label": right,
                        "citable_item_id": citable_items[right][0],
                    },
                ],
            }
        )
    return {
        "schema_version": "es-f1-integrated-review.v1",
        "pairwise_results": rows,
    }


def resolve_integrated_review(
    integrated_record: object,
    *,
    attempt_id: str,
    packet_set_digest: str,
    presentation_order: Sequence[str],
    citable_item_ids_by_label: Mapping[str, Sequence[str]],
    existing_records: Sequence[object],
) -> dict[str, Any]:
    """Return a valid integrated vector or seal all six rows indeterminate."""

    expected_attempt = _identifier(attempt_id, field="attempt_id")
    expected_packet_set = _digest(
        packet_set_digest,
        field="packet_set_digest",
    )
    order = _normalized_presentation_order(presentation_order)
    citable_items = _normalized_citable_items(
        citable_item_ids_by_label,
        presentation_order=order,
    )
    try:
        integrated = validate_review_record(
            integrated_record,
            citable_item_ids_by_label=citable_item_ids_by_label,
            existing_records=existing_records,
        )
        if (
            integrated["review_kind"] != INTEGRATED
            or integrated["attempt_id"] != expected_attempt
            or integrated["packet_set_digest"] != expected_packet_set
            or integrated["presentation_order"] != list(order)
        ):
            _raise("integrated_record_invalid", "context_binding")
        return deepcopy(integrated["payload"])
    except ReviewContractError:
        payload = _failed_integrated_payload(
            presentation_order=order,
            citable_items=citable_items,
        )
        return validate_review_payload(
            payload,
            review_kind=INTEGRATED,
            perspective_id=None,
            presentation_order=order,
            citable_item_ids_by_label=citable_item_ids_by_label,
        )


__all__ = [
    "ADJUDICATOR",
    "API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    "INITIAL",
    "INTEGRATED",
    "MAX_RATIONALE_LENGTH",
    "PERSPECTIVE_DIMENSIONS",
    "REVIEW_SCHEMA_PATHS",
    "ReviewContractError",
    "SCIENTIFIC_APPLICATION_SEMANTICS",
    "WRAPPER_SCHEMA_VERSION",
    "canonical_pair_order",
    "canonical_payload_digest",
    "material_disagreements",
    "resolve_adjudication",
    "resolve_integrated_review",
    "seal_review_record",
    "validate_review_payload",
    "validate_review_record",
]
