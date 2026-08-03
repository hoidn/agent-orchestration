from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PERSPECTIVES_PATH = (
    REPOSITORY_ROOT
    / "experiments/orc_effectiveness/f1_es/evaluator/reviewer-perspectives.json"
)
SCHEMA_ROOT = PERSPECTIVES_PATH.parent
SCIENTIFIC = "SCIENTIFIC_APPLICATION_SEMANTICS"
API = "API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
LABELS = tuple(f"opaque-{index:064x}" for index in range(1, 5))
SCHEMA_VERSIONS = {
    SCIENTIFIC: "es-f1-initial-scientific-application-semantics-review.v1",
    API: "es-f1-initial-api-persistence-migration-maintainability-review.v1",
    "ADJUDICATOR": "es-f1-adjudicator-review.v1",
    "INTEGRATED": "es-f1-integrated-review.v1",
}


def _load_reviews() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/experiments/es/reviews.py"
    spec = importlib.util.spec_from_file_location("es_reviews", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reviews = _load_reviews()


def _sha(fill: str) -> str:
    return "sha256:" + fill * 64


def _perspectives() -> dict[str, tuple[str, ...]]:
    record = json.loads(PERSPECTIVES_PATH.read_text(encoding="utf-8"))
    return {
        row["perspective_id"]: tuple(row["owned_dimensions"])
        for row in record["perspectives"]
    }


def _citable_items_for(
    labels: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    return {label: ("task_spec", "result") for label in labels}


def _citable_items() -> dict[str, tuple[str, ...]]:
    return _citable_items_for(LABELS)


def _citation(label: str, item_id: str = "task_spec") -> dict[str, str]:
    return {"opaque_label": label, "citable_item_id": item_id}


def _assert_object_schemas_are_closed(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
        for child in value.values():
            _assert_object_schemas_are_closed(child)
    elif isinstance(value, list):
        for child in value:
            _assert_object_schemas_are_closed(child)


def _pairs(
    outcomes: tuple[str, ...] | None = None,
    *,
    rationale_prefix: str = "pair",
) -> list[dict[str, Any]]:
    selected = outcomes or ("TIE",) * 6
    return [
        {
            "candidate_a_label": left,
            "candidate_b_label": right,
            "outcome": outcome,
            "rationale": f"{rationale_prefix}-{index}",
            "citations": [_citation(left), _citation(right, "result")],
        }
        for index, ((left, right), outcome) in enumerate(
            zip(reviews.canonical_pair_order(LABELS), selected, strict=True),
            start=1,
        )
    ]


def _initial_payload(
    perspective: str,
    *,
    outcomes: tuple[str, ...] | None = None,
    rationale_prefix: str = "pair",
) -> dict[str, Any]:
    dimensions = _perspectives()[perspective]
    return {
        "schema_version": SCHEMA_VERSIONS[perspective],
        "candidates": [
            {
                "opaque_label": label,
                "dimensions": [
                    {
                        "dimension": dimension,
                        "assessment": "PASS",
                        "rationale": f"{label}-{dimension}",
                        "citations": [_citation(label)],
                    }
                    for dimension in dimensions
                ],
            }
            for label in LABELS
        ],
        "pairwise_results": _pairs(
            outcomes,
            rationale_prefix=rationale_prefix,
        ),
    }


def _pair_payload(kind: str, outcomes: tuple[str, ...]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSIONS[kind],
        "pairwise_results": _pairs(outcomes, rationale_prefix=kind.lower()),
    }


def _seal_initial(
    perspective: str,
    *,
    outcomes: tuple[str, ...] | None = None,
    session_suffix: str = "1",
    rationale_prefix: str = "pair",
    existing_records: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    return reviews.seal_review_record(
        _initial_payload(
            perspective,
            outcomes=outcomes,
            rationale_prefix=rationale_prefix,
        ),
        attempt_id="ES-ATTEMPT-01",
        review_kind="INITIAL",
        perspective_id=perspective,
        session_id=f"session-{session_suffix}",
        provider_attempt_id=f"provider-attempt-{session_suffix}",
        receipt_digest=_sha(session_suffix),
        packet_set_digest=_sha("a"),
        presentation_order=LABELS,
        citable_item_ids_by_label=_citable_items(),
        existing_records=existing_records,
    )


def _seal_pair_review(
    kind: str,
    outcomes: tuple[str, ...],
    *,
    session_suffix: str,
    existing_records: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    return reviews.seal_review_record(
        _pair_payload(kind, outcomes),
        attempt_id="ES-ATTEMPT-01",
        review_kind=kind,
        perspective_id=None,
        session_id=f"session-{session_suffix}",
        provider_attempt_id=f"provider-attempt-{session_suffix}",
        receipt_digest=_sha(session_suffix),
        packet_set_digest=_sha("a"),
        presentation_order=LABELS,
        citable_item_ids_by_label=_citable_items(),
        existing_records=existing_records,
    )


def test_four_role_specific_schemas_are_closed_and_valid() -> None:
    expected = {
        "initial-scientific-application-semantics-review.schema.json",
        "initial-api-persistence-migration-maintainability-review.schema.json",
        "adjudicator-review.schema.json",
        "integrated-review.schema.json",
    }

    assert set(reviews.REVIEW_SCHEMA_PATHS.values()) == {
        SCHEMA_ROOT / name for name in expected
    }
    for path in reviews.REVIEW_SCHEMA_PATHS.values():
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        _assert_object_schemas_are_closed(schema)


@pytest.mark.parametrize("perspective", [SCIENTIFIC, API])
def test_initial_payload_requires_four_candidates_and_exact_perspective_dimensions(
    perspective: str,
) -> None:
    payload = _initial_payload(perspective)

    normalized = reviews.validate_review_payload(
        payload,
        review_kind="INITIAL",
        perspective_id=perspective,
        presentation_order=LABELS,
        citable_item_ids_by_label=_citable_items(),
    )

    assert normalized == payload
    assert [row["opaque_label"] for row in normalized["candidates"]] == list(LABELS)
    assert [
        row["dimension"] for row in normalized["candidates"][0]["dimensions"]
    ] == list(_perspectives()[perspective])


@pytest.mark.parametrize(
    "mutation",
    [
        "candidate_missing",
        "candidate_reordered",
        "dimension_missing",
        "dimension_reordered",
        "treatment_guess",
        "pair_reordered",
        "outcome_unknown",
        "rationale_blank",
        "rationale_unbounded",
        "citation_unknown_label",
        "citation_unknown_item",
        "citation_empty",
    ],
)
def test_review_payload_rejects_every_shape_order_bound_and_citation_drift(
    mutation: str,
) -> None:
    payload = _initial_payload(SCIENTIFIC)
    if mutation == "candidate_missing":
        payload["candidates"].pop()
    elif mutation == "candidate_reordered":
        payload["candidates"].reverse()
    elif mutation == "dimension_missing":
        payload["candidates"][0]["dimensions"].pop()
    elif mutation == "dimension_reordered":
        payload["candidates"][0]["dimensions"].reverse()
    elif mutation == "treatment_guess":
        payload["candidates"][0]["treatment_guess"] = "RICH"
    elif mutation == "pair_reordered":
        payload["pairwise_results"].reverse()
    elif mutation == "outcome_unknown":
        payload["pairwise_results"][0]["outcome"] = "MAYBE"
    elif mutation == "rationale_blank":
        payload["pairwise_results"][0]["rationale"] = "  \n"
    elif mutation == "rationale_unbounded":
        payload["candidates"][0]["dimensions"][0]["rationale"] = "x" * 4_097
    elif mutation == "citation_unknown_label":
        payload["pairwise_results"][0]["citations"][0]["opaque_label"] = "OTHER"
    elif mutation == "citation_unknown_item":
        payload["pairwise_results"][0]["citations"][0]["citable_item_id"] = "nope"
    else:
        payload["pairwise_results"][0]["citations"] = []

    with pytest.raises(reviews.ReviewContractError):
        reviews.validate_review_payload(
            payload,
            review_kind="INITIAL",
            perspective_id=SCIENTIFIC,
            presentation_order=LABELS,
            citable_item_ids_by_label=_citable_items(),
        )


def test_citations_may_reference_any_item_in_the_bound_packet_set() -> None:
    payload = _initial_payload(SCIENTIFIC)
    payload["candidates"][0]["dimensions"][0]["citations"] = [
        _citation(LABELS[3], "result")
    ]
    payload["pairwise_results"][0]["citations"] = [_citation(LABELS[2])]

    assert reviews.validate_review_payload(
        payload,
        review_kind="INITIAL",
        perspective_id=SCIENTIFIC,
        presentation_order=LABELS,
        citable_item_ids_by_label=_citable_items(),
    ) == payload


def test_review_contract_rejects_non_e2_opaque_labels() -> None:
    legacy_labels = tuple(f"CANDIDATE-{index:02d}" for index in range(1, 5))
    replacements = dict(zip(LABELS, legacy_labels, strict=True))
    payload = _initial_payload(SCIENTIFIC)

    def replace_labels(value: object) -> object:
        if isinstance(value, str):
            return replacements.get(value, value)
        if isinstance(value, list):
            return [replace_labels(item) for item in value]
        if isinstance(value, dict):
            return {key: replace_labels(item) for key, item in value.items()}
        return value

    with pytest.raises(reviews.ReviewContractError):
        reviews.validate_review_payload(
            replace_labels(payload),
            review_kind="INITIAL",
            perspective_id=SCIENTIFIC,
            presentation_order=legacy_labels,
            citable_item_ids_by_label=_citable_items_for(legacy_labels),
        )


def test_wrapper_binds_context_payload_digest_and_fresh_identities() -> None:
    first = _seal_initial(SCIENTIFIC)

    assert set(first) == {
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
    assert first["payload_digest"] == reviews.canonical_payload_digest(
        first["payload"]
    )
    assert reviews.validate_review_record(
        first,
        citable_item_ids_by_label=_citable_items(),
    ) == first

    with pytest.raises(reviews.ReviewContractError, match="identity"):
        _seal_initial(
            API,
            session_suffix="1",
            existing_records=(first,),
        )


@pytest.mark.parametrize(
    "mutation",
    ["extra", "payload", "perspective", "digest", "kind_shape"],
)
def test_wrapper_rejects_tampering_and_kind_perspective_mismatch(
    mutation: str,
) -> None:
    record = _seal_initial(SCIENTIFIC)
    if mutation == "extra":
        record["extra"] = True
    elif mutation == "payload":
        record["payload"]["pairwise_results"][0]["outcome"] = "A"
    elif mutation == "perspective":
        record["perspective_id"] = None
    elif mutation == "kind_shape":
        record["review_kind"] = []
    else:
        record["packet_set_digest"] = "not-a-digest"

    with pytest.raises(reviews.ReviewContractError):
        reviews.validate_review_record(
            record,
            citable_item_ids_by_label=_citable_items(),
        )


def test_material_disagreement_uses_only_normalized_pair_outcomes() -> None:
    first = _seal_initial(SCIENTIFIC, rationale_prefix="first")
    rationale_only = _seal_initial(API, session_suffix="2", rationale_prefix="second")

    assert reviews.material_disagreements(
        first,
        rationale_only,
        citable_item_ids_by_label=_citable_items(),
    ) == ()

    outcomes = ("A", "TIE", "TIE", "TIE", "TIE", "TIE")
    different = _seal_initial(API, outcomes=outcomes, session_suffix="3")
    assert reviews.material_disagreements(
        first,
        different,
        citable_item_ids_by_label=_citable_items(),
    ) == ((LABELS[0], LABELS[1]),)


@pytest.mark.parametrize("missing_side", ["first", "second", "invalid"])
def test_missing_or_invalid_initial_review_is_failure_not_disagreement(
    missing_side: str,
) -> None:
    first: object = _seal_initial(SCIENTIFIC)
    second: object = _seal_initial(API, session_suffix="2")
    if missing_side == "first":
        first = None
    elif missing_side == "second":
        second = None
    else:
        second["payload_digest"] = _sha("f")

    with pytest.raises(reviews.ReviewContractError) as caught:
        reviews.material_disagreements(
            first,
            second,
            citable_item_ids_by_label=_citable_items(),
        )

    assert caught.value.code == "initial_review_failure"


def test_no_dispute_rejects_adjudication_before_a_call_record_is_consulted() -> None:
    first = _seal_initial(SCIENTIFIC)
    second = _seal_initial(API, session_suffix="2")

    with pytest.raises(reviews.ReviewContractError) as caught:
        reviews.resolve_adjudication(
            first,
            second,
            None,
            citable_item_ids_by_label=_citable_items(),
        )

    assert caught.value.code == "adjudication_not_required"


def test_adjudicator_reproduces_agreed_rows_and_decides_only_disputes() -> None:
    scientific = _seal_initial(SCIENTIFIC)
    api_outcomes = ("A", "TIE", "TIE", "TIE", "TIE", "TIE")
    api = _seal_initial(API, outcomes=api_outcomes, session_suffix="2")
    adjudicator_outcomes = ("B", "TIE", "TIE", "TIE", "TIE", "TIE")
    adjudicator = _seal_pair_review(
        "ADJUDICATOR",
        adjudicator_outcomes,
        session_suffix="3",
        existing_records=(scientific, api),
    )
    for index in range(1, 6):
        adjudicator["payload"]["pairwise_results"][index] = deepcopy(
            scientific["payload"]["pairwise_results"][index]
        )
    adjudicator["payload_digest"] = reviews.canonical_payload_digest(
        adjudicator["payload"]
    )
    before = deepcopy((scientific, api, adjudicator))

    resolved = reviews.resolve_adjudication(
        scientific,
        api,
        adjudicator,
        citable_item_ids_by_label=_citable_items(),
    )

    assert resolved["pairwise_results"][0]["outcome"] == "B"
    assert resolved["pairwise_results"][1:] == scientific["payload"][
        "pairwise_results"
    ][1:]
    assert (scientific, api, adjudicator) == before


@pytest.mark.parametrize("failure", ["missing", "invalid", "edits_agreed"])
def test_adjudicator_failure_preserves_agreement_and_seals_disputes_indeterminate(
    failure: str,
) -> None:
    scientific = _seal_initial(SCIENTIFIC)
    api = _seal_initial(
        API,
        outcomes=("A", "TIE", "TIE", "TIE", "TIE", "TIE"),
        session_suffix="2",
    )
    adjudicator = None
    if failure != "missing":
        adjudicator = _seal_pair_review(
            "ADJUDICATOR",
            ("B", "TIE", "TIE", "TIE", "TIE", "TIE"),
            session_suffix="3",
            existing_records=(scientific, api),
        )
        if failure == "invalid":
            adjudicator["payload_digest"] = _sha("f")
        else:
            adjudicator["payload"]["pairwise_results"][1]["outcome"] = "A"
            adjudicator["payload_digest"] = reviews.canonical_payload_digest(
                adjudicator["payload"]
            )

    resolved = reviews.resolve_adjudication(
        scientific,
        api,
        adjudicator,
        citable_item_ids_by_label=_citable_items(),
    )

    assert resolved["pairwise_results"][0]["outcome"] == "INDETERMINATE"
    assert resolved["pairwise_results"][1:] == scientific["payload"][
        "pairwise_results"
    ][1:]
    reviews.validate_review_payload(
        resolved,
        review_kind="ADJUDICATOR",
        perspective_id=None,
        presentation_order=LABELS,
        citable_item_ids_by_label=_citable_items(),
    )


def test_integrated_review_failure_seals_all_six_pairs_indeterminate() -> None:
    initial = _seal_initial(SCIENTIFIC)
    adjudicator = _seal_pair_review(
        "ADJUDICATOR",
        ("TIE",) * 6,
        session_suffix="3",
        existing_records=(initial,),
    )
    existing_records = (initial, adjudicator)
    valid = _seal_pair_review(
        "INTEGRATED",
        ("A", "B", "TIE", "A", "B", "TIE"),
        session_suffix="4",
        existing_records=existing_records,
    )
    assert reviews.resolve_integrated_review(
        valid,
        attempt_id="ES-ATTEMPT-01",
        packet_set_digest=_sha("a"),
        presentation_order=LABELS,
        citable_item_ids_by_label=_citable_items(),
        existing_records=existing_records,
    ) == valid["payload"]

    invalid = deepcopy(valid)
    invalid["payload_digest"] = _sha("f")
    for failed in (None, invalid):
        resolved = reviews.resolve_integrated_review(
            failed,
            attempt_id="ES-ATTEMPT-01",
            packet_set_digest=_sha("a"),
            presentation_order=LABELS,
            citable_item_ids_by_label=_citable_items(),
            existing_records=existing_records,
        )
        assert len(resolved["pairwise_results"]) == 6
        assert {row["outcome"] for row in resolved["pairwise_results"]} == {
            "INDETERMINATE"
        }
        reviews.validate_review_payload(
            resolved,
            review_kind="INTEGRATED",
            perspective_id=None,
            presentation_order=LABELS,
            citable_item_ids_by_label=_citable_items(),
        )


@pytest.mark.parametrize(
    ("prior_index", "identity_field"),
    [
        (0, "session_id"),
        (0, "provider_attempt_id"),
        (1, "session_id"),
        (1, "provider_attempt_id"),
    ],
)
def test_integrated_review_identity_reuse_seals_indeterminate(
    prior_index: int,
    identity_field: str,
) -> None:
    initial = _seal_initial(SCIENTIFIC)
    adjudicator = _seal_pair_review(
        "ADJUDICATOR",
        ("TIE",) * 6,
        session_suffix="3",
        existing_records=(initial,),
    )
    existing_records = (initial, adjudicator)
    integrated = _seal_pair_review(
        "INTEGRATED",
        ("A", "B", "TIE", "A", "B", "TIE"),
        session_suffix="4",
        existing_records=existing_records,
    )
    integrated[identity_field] = existing_records[prior_index][identity_field]

    resolved = reviews.resolve_integrated_review(
        integrated,
        attempt_id="ES-ATTEMPT-01",
        packet_set_digest=_sha("a"),
        presentation_order=LABELS,
        citable_item_ids_by_label=_citable_items(),
        existing_records=existing_records,
    )

    assert {row["outcome"] for row in resolved["pairwise_results"]} == {
        "INDETERMINATE"
    }
