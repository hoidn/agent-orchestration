"""Private sealed-review and unblinding resolution."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ._reporting_types import (
    COMPARISONS,
    TREATMENTS,
    ReviewBinding,
    UnblindingBinding,
)
from ._reporting_validation import _fail, _relative_path, _validate_record
from .contracts import canonical_sha256


@dataclass(frozen=True)
class ResolvedReviews:
    diagnostic_blocks: list[dict[str, object]]
    decided_outcomes: dict[tuple[str, str], tuple[str | None, list[str]]]
    agreement_count: int
    disagreement_count: int
    adjudication_count: int
    guess_counts: Counter[tuple[str, str]]
    correct_guesses: int
    total_guesses: int


def _review_reference(binding: ReviewBinding) -> dict[str, object]:
    return {
        "review_id": binding.review_id,
        "reviewer_id": binding.reviewer_id,
        "review_result_digest": binding.review_result_digest,
        "review_path": binding.review_path,
    }


def _result_for_labels(
    review: Mapping[str, object],
    label_a: str,
    label_b: str,
) -> str | None:
    for result in review["pairwise_results"]:  # type: ignore[index]
        first = result["candidate_a_label"]
        second = result["candidate_b_label"]
        if {first, second} != {label_a, label_b}:
            continue
        outcome = result["outcome"]
        if first == label_a or outcome not in {"A", "B"}:
            return outcome
        return "B" if outcome == "A" else "A"
    return None


def _locked_label_assignments(
    lock: Mapping[str, object],
    block_id: str,
) -> dict[str, str]:
    seed = lock["randomization_seed"]
    ordered_treatments = sorted(
        TREATMENTS,
        key=lambda treatment: hashlib.sha256(
            f"{seed}\0{block_id}\0role\0{treatment}".encode("utf-8")
        ).digest(),
    )
    labels = [
        "candidate-"
        + hashlib.sha256(
            f"{seed}\0{block_id}\0label\0{index}".encode("utf-8")
        ).hexdigest()[:12]
        for index in range(len(TREATMENTS))
    ]
    return {
        treatment: label
        for label, treatment in zip(labels, ordered_treatments, strict=True)
    }


def _sealed_inputs(
    *,
    lock: Mapping[str, object],
    valid_attempts: Sequence[Mapping[str, object]],
    reviews: Sequence[Mapping[str, object]],
    sealed_review_bindings: Sequence[ReviewBinding],
    unblinding: Sequence[UnblindingBinding],
) -> tuple[
    dict[str, list[tuple[ReviewBinding, dict[str, Any]]]],
    dict[str, dict[str, str]],
    dict[str, tuple[str, str]],
]:
    lock_digest = canonical_sha256(lock)
    rubric_digest = lock["review"]["rubric_digest"]  # type: ignore[index]
    review_by_id: dict[str, dict[str, Any]] = {}
    seen_session_ids: set[str] = set()
    for value in reviews:
        record = _validate_record(value, "review_result.v1")
        if record["review_id"] in review_by_id:
            _fail("review_binding_duplicate")
        if record["session_id"] in seen_session_ids:
            _fail("review_session_reused")
        seen_session_ids.add(record["session_id"])
        review_by_id[record["review_id"]] = record
    if len(sealed_review_bindings) != len(review_by_id):
        _fail("review_binding_coverage")
    valid_block_ids = [attempt["block_id"] for attempt in valid_attempts]
    by_block: dict[str, list[tuple[ReviewBinding, dict[str, Any]]]] = {
        block_id: [] for block_id in valid_block_ids
    }
    locked_assignments = {
        attempt["block_id"]: _locked_label_assignments(
            lock,
            attempt["block_id"],
        )
        for attempt in valid_attempts
    }
    seen_review_ids: set[str] = set()
    package_by_block: dict[str, tuple[str, str]] = {}
    for binding in sealed_review_bindings:
        if (
            not isinstance(binding, ReviewBinding)
            or binding.review_id in seen_review_ids
            or binding.block_id not in by_block
            or not _relative_path(binding.review_path)
            or binding.reviewer_role not in {"INITIAL", "ADJUDICATOR"}
        ):
            _fail("review_binding_invalid")
        seen_review_ids.add(binding.review_id)
        record = review_by_id.get(binding.review_id)
        if (
            record is None
            or canonical_sha256(record) != binding.review_result_digest
            or record["reviewer_id"] != binding.reviewer_id
            or record["pilot_lock_digest"] != lock_digest
            or record["rubric_digest"] != rubric_digest
            or record["review_class"] != "LIVE"
        ):
            _fail("review_binding_mismatch")
        package = (binding.package_id, binding.package_manifest_digest)
        prior_package = package_by_block.setdefault(binding.block_id, package)
        if package != prior_package or binding.package_id != binding.block_id:
            _fail("review_package_mismatch")
        by_block[binding.block_id].append((binding, record))
    if seen_review_ids != set(review_by_id):
        _fail("review_binding_coverage")

    labels_by_block: dict[str, dict[str, str]] = {
        block_id: {} for block_id in valid_block_ids
    }
    seen_unblind: set[tuple[str, str]] = set()
    seen_unblind_treatments: set[tuple[str, str]] = set()
    for binding in unblinding:
        if (
            not isinstance(binding, UnblindingBinding)
            or binding.block_id not in labels_by_block
            or binding.treatment_id not in TREATMENTS
            or (binding.block_id, binding.opaque_label) in seen_unblind
            or (binding.block_id, binding.treatment_id)
            in seen_unblind_treatments
            or package_by_block.get(binding.block_id)
            != (binding.package_id, binding.package_manifest_digest)
        ):
            _fail("unblinding_binding_invalid")
        if (
            locked_assignments[binding.block_id][binding.treatment_id]
            != binding.opaque_label
        ):
            _fail("unblinding_attempt_mismatch")
        seen_unblind.add((binding.block_id, binding.opaque_label))
        seen_unblind_treatments.add((binding.block_id, binding.treatment_id))
        labels_by_block[binding.block_id][binding.treatment_id] = (
            binding.opaque_label
        )
    for block_id, bound_reviews in by_block.items():
        candidate_labels = {
            candidate["opaque_label"]
            for _binding, review in bound_reviews
            for candidate in review["candidates"]
        }
        if set(labels_by_block[block_id].values()) != candidate_labels:
            _fail("unblinding_coverage")
    return by_block, labels_by_block, package_by_block


def resolve_reviews(
    *,
    lock: Mapping[str, object],
    valid_attempts: Sequence[Mapping[str, object]],
    reviews: Sequence[Mapping[str, object]],
    sealed_review_bindings: Sequence[ReviewBinding],
    unblinding: Sequence[UnblindingBinding],
) -> ResolvedReviews:
    reviews_by_block, labels_by_block, package_by_block = _sealed_inputs(
        lock=lock,
        valid_attempts=valid_attempts,
        reviews=reviews,
        sealed_review_bindings=sealed_review_bindings,
        unblinding=unblinding,
    )
    diagnostics_blocks: list[dict[str, object]] = []
    decided_outcomes: dict[tuple[str, str], tuple[str | None, list[str]]] = {}
    agreement_count = disagreement_count = adjudication_count = 0
    guess_counts: Counter[tuple[str, str]] = Counter()
    correct_guesses = total_guesses = 0
    initial_reviewers = tuple(lock["review"]["reviewer_ids"][:2])  # type: ignore[index]
    reviewer_ids = lock["review"]["reviewer_ids"]  # type: ignore[index]
    adjudicator_id = reviewer_ids[2] if len(reviewer_ids) == 3 else None

    for attempt in valid_attempts:
        block_id = attempt["block_id"]
        bound = reviews_by_block[block_id]
        initials = [
            pair for pair in bound if pair[0].reviewer_role == "INITIAL"
        ]
        adjudicators = [
            pair for pair in bound if pair[0].reviewer_role == "ADJUDICATOR"
        ]
        if (
            len(initials) != 2
            or {binding.reviewer_id for binding, _review in initials}
            != set(initial_reviewers)
            or any(
                binding.reviewer_id != adjudicator_id
                for binding, _review in adjudicators
            )
            or len(adjudicators) > 1
        ):
            _fail("reviewer_coverage_invalid")
        labels = labels_by_block[block_id]
        disagreements: list[str] = []
        for comparison, treatment_a, treatment_b in COMPARISONS:
            if treatment_a not in labels or treatment_b not in labels:
                decided_outcomes[(block_id, comparison)] = (None, [])
                continue
            outcomes = [
                _result_for_labels(review, labels[treatment_a], labels[treatment_b])
                for _binding, review in initials
            ]
            if None in outcomes:
                decided_outcomes[(block_id, comparison)] = (None, [])
                continue
            digests = [
                binding.review_result_digest for binding, _review in initials
            ]
            if outcomes[0] == outcomes[1]:
                agreement_count += 1
                decided_outcomes[(block_id, comparison)] = (outcomes[0], digests)
            else:
                disagreement_count += 1
                disagreements.append(comparison)
                if not adjudicators:
                    decided_outcomes[(block_id, comparison)] = (
                        "INDETERMINATE",
                        digests,
                    )
                else:
                    adjudication_count += 1
                    binding, review = adjudicators[0]
                    outcome = _result_for_labels(
                        review,
                        labels[treatment_a],
                        labels[treatment_b],
                    )
                    if outcome is None:
                        _fail("adjudicator_required")
                    decided_outcomes[(block_id, comparison)] = (
                        outcome,
                        [*digests, binding.review_result_digest],
                    )
        if adjudicators and not disagreements:
            _fail("adjudicator_unneeded")
        for _binding, review in initials:
            for candidate in review["candidates"]:
                actual = next(
                    treatment
                    for treatment, label in labels.items()
                    if label == candidate["opaque_label"]
                )
                guessed = candidate["sealed_treatment_guess"]
                guess_counts[(actual, guessed)] += 1
                total_guesses += 1
                correct_guesses += guessed == actual
        diagnostic: dict[str, object] = {
            "block_id": block_id,
            "package_id": package_by_block[block_id][0],
            "package_manifest_digest": package_by_block[block_id][1],
            "initial_reviews_agree": not disagreements,
            "disagreement_disposition": (
                "LOCKED_ADJUDICATOR"
                if disagreements and adjudicators
                else "INDETERMINATE"
                if disagreements
                else "NOT_APPLICABLE"
            ),
            "initial_review_references": [
                _review_reference(binding) for binding, _review in initials
            ],
        }
        if adjudicators:
            diagnostic["adjudicator_review_reference"] = _review_reference(
                adjudicators[0][0]
            )
        diagnostics_blocks.append(diagnostic)

    return ResolvedReviews(
        diagnostic_blocks=diagnostics_blocks,
        decided_outcomes=decided_outcomes,
        agreement_count=agreement_count,
        disagreement_count=disagreement_count,
        adjudication_count=adjudication_count,
        guess_counts=guess_counts,
        correct_guesses=correct_guesses,
        total_guesses=total_guesses,
    )
