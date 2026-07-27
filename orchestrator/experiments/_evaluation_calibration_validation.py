"""Calibration round and retained-predecessor validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from .contracts import PilotContractError, canonical_sha256, validate_record
from ._evaluation_calibration_mapping import _validate_calibration_controller_mapping
from ._evaluation_calibration_support import _calibration_shape
from ._evaluation_support import EvaluationError, _fail


def _calibration_failure(round_number: int, code: str, detail: str = "") -> None:
    if round_number == 2 and code in {
        "calibration_reference_not_preferred",
        "calibration_label_order_inconsistent",
        "calibration_identity_not_tie",
    }:
        _fail("CALIBRATION_FAILED", code)
    _fail(code, detail)
_SUBSTANTIVE_CALIBRATION_FAILURES = {
    "calibration_reference_not_preferred",
    "calibration_label_order_inconsistent",
    "calibration_identity_not_tie",
}


def _validate_calibration_predecessor(
    *,
    calibration_lock: Mapping[str, object],
    round_number: int,
    predecessor_lock: Mapping[str, object] | None,
    predecessor_controller_mapping: Mapping[str, object] | None,
    predecessor_controller_root: Path | None,
    predecessor_reviews: Sequence[Mapping[str, object]] | None,
) -> None:
    supplied = (
        predecessor_lock,
        predecessor_controller_mapping,
        predecessor_controller_root,
        predecessor_reviews,
    )
    if round_number == 1:
        if any(value is not None for value in supplied):
            _fail("calibration_predecessor_invalid", "round one has no predecessor")
        return
    if (
        not isinstance(predecessor_lock, Mapping)
        or not isinstance(predecessor_controller_mapping, Mapping)
        or not isinstance(predecessor_controller_root, Path)
        or not isinstance(predecessor_reviews, Sequence)
    ):
        _fail("calibration_predecessor_invalid", "complete predecessor required")
    try:
        (
            predecessor_calibration_id,
            predecessor_round,
            predecessor_revision,
            _reviewers,
            _packages,
        ) = _calibration_shape(predecessor_lock)
    except EvaluationError as exc:
        raise EvaluationError(
            "calibration_predecessor_invalid",
            exc.code,
        ) from exc
    descriptor = calibration_lock.get("predecessor")
    if (
        predecessor_round != 1
        or predecessor_revision != 0
        or predecessor_calibration_id != calibration_lock.get("calibration_id")
        or not isinstance(descriptor, Mapping)
        or descriptor.get("status") != "FAILED"
        or descriptor.get("lock_digest") != canonical_sha256(predecessor_lock)
    ):
        _fail("calibration_predecessor_invalid", "identity")
    try:
        _validate_calibration_round(
            calibration_lock=predecessor_lock,
            controller_mapping=predecessor_controller_mapping,
            controller_root=predecessor_controller_root,
            reviews=predecessor_reviews,
        )
    except EvaluationError as exc:
        if exc.code in _SUBSTANTIVE_CALIBRATION_FAILURES:
            return
        raise EvaluationError(
            "calibration_predecessor_invalid",
            exc.code,
        ) from exc
    _fail("calibration_predecessor_invalid", "predecessor passed")


def _validate_calibration_round(
    *,
    calibration_lock: Mapping[str, object],
    controller_mapping: Mapping[str, object],
    controller_root: Path,
    reviews: Sequence[Mapping[str, object]],
) -> None:
    """Validate the exact two-reviewer, three-package calibration contract."""

    (
        calibration_id,
        round_number,
        _revision,
        reviewer_ids,
        package_ids,
    ) = _calibration_shape(calibration_lock)
    lock_digest = canonical_sha256(calibration_lock)
    packages, review_bindings = _validate_calibration_controller_mapping(
        calibration_lock=calibration_lock,
        controller_mapping=controller_mapping,
        controller_root=controller_root,
        calibration_id=calibration_id,
        reviewer_ids=reviewer_ids,
        package_ids=package_ids,
    )
    if len(reviews) != 6:
        _fail("calibration_reviewer_mismatch", "expected six reviews")

    reviewer_set = {
        review.get("reviewer_id")
        for review in reviews
        if isinstance(review, Mapping)
    }
    if reviewer_set != set(reviewer_ids):
        _fail("calibration_reviewer_mismatch", "reviewer IDs")
    session_ids = [
        review.get("session_id")
        for review in reviews
        if isinstance(review, Mapping)
    ]
    if (
        any(not isinstance(value, str) or not value for value in session_ids)
        or len(set(session_ids)) != 6
    ):
        _fail("calibration_reviewer_session_reused")

    by_reviewer_package: dict[tuple[str, str], Mapping[str, object]] = {}
    rubric_value = calibration_lock.get("rubric")
    if not isinstance(rubric_value, Mapping):
        _fail("calibration_lock_invalid", "rubric")
    rubric_digest = rubric_value.get("digest")
    for review in reviews:
        if not isinstance(review, Mapping):
            _fail("calibration_review_invalid")
        try:
            validate_record(review)
        except PilotContractError as exc:
            raise EvaluationError("calibration_review_invalid", str(exc)) from exc
        binding = review_bindings.get(review.get("review_id"))
        if not isinstance(binding, Mapping):
            _fail("calibration_mapping_mismatch", "review binding")
        reviewer_id = binding.get("reviewer_id")
        package_id = binding.get("package_id")
        if (
            reviewer_id != review.get("reviewer_id")
            or package_id not in package_ids
            or review.get("review_class") != "CALIBRATION"
            or review.get("rubric_digest") != rubric_digest
            or review.get("pilot_lock_digest") != lock_digest
        ):
            _fail("calibration_mapping_mismatch", "review")
        package = packages[package_id]
        labels = package.get("labels") if isinstance(package, Mapping) else None
        candidate_labels = (
            package.get("candidate_labels") if isinstance(package, Mapping) else None
        )
        package_manifest_digest = (
            package.get("manifest_digest") if isinstance(package, Mapping) else None
        )
        if (
            binding.get("rubric_digest") != rubric_digest
            or binding.get("package_manifest_digest") != package_manifest_digest
        ):
            _fail("calibration_mapping_mismatch", "review binding")
        candidates = review.get("candidates")
        if (
            not isinstance(labels, Mapping)
            or not isinstance(candidate_labels, list)
            or len(candidate_labels) != 2
            or len(set(candidate_labels)) != 2
            or set(candidate_labels) != set(labels)
            or not isinstance(candidates, list)
            or len(candidates) != 2
            or [
                candidate.get("opaque_label")
                for candidate in candidates
                if isinstance(candidate, Mapping)
            ] != candidate_labels
        ):
            _fail("calibration_mapping_mismatch", "candidate labels")
        key = (reviewer_id, package_id)
        if key in by_reviewer_package:
            _fail("calibration_reviewer_session_reused", "duplicate package")
        by_reviewer_package[key] = review
    if set(by_reviewer_package) != {
        (reviewer_id, package_id)
        for reviewer_id in reviewer_ids
        for package_id in package_ids
    }:
        _fail("calibration_reviewer_mismatch", "incomplete matrix")

    for reviewer_id in reviewer_ids:
        directional_winners: list[str] = []
        directional_roles: list[str] = []
        for package_id in package_ids[:2]:
            review = by_reviewer_package[(reviewer_id, package_id)]
            pairwise = review.get("pairwise_results")
            if not isinstance(pairwise, list) or len(pairwise) != 1:
                _fail("calibration_review_invalid", "pairwise result")
            result = pairwise[0]
            if not isinstance(result, Mapping):
                _fail("calibration_review_invalid", "pairwise result")
            package = packages[package_id]
            if not isinstance(package, Mapping):
                _fail("calibration_mapping_mismatch", package_id)
            candidate_labels = package.get("candidate_labels")
            if (
                not isinstance(candidate_labels, list)
                or result.get("candidate_a_label") != candidate_labels[0]
                or result.get("candidate_b_label") != candidate_labels[1]
                or candidate_labels[0] == candidate_labels[1]
            ):
                _fail("calibration_mapping_mismatch", "pairwise labels")
            outcome = result.get("outcome")
            if outcome not in {"A", "B"}:
                _calibration_failure(
                    round_number,
                    "calibration_reference_not_preferred",
                )
            winner_key = (
                "candidate_a_label" if outcome == "A" else "candidate_b_label"
            )
            winner = result.get(winner_key)
            labels = package.get("labels")
            if not isinstance(labels, Mapping) or winner not in labels:
                _fail("calibration_mapping_mismatch", "candidate label")
            directional_winners.append(winner)
            directional_roles.append(labels[winner])

        if directional_winners[0] == directional_winners[1]:
            _calibration_failure(
                round_number,
                "calibration_label_order_inconsistent",
            )
        if directional_roles != ["REFERENCE", "REFERENCE"]:
            _calibration_failure(
                round_number,
                "calibration_reference_not_preferred",
            )

        identity = by_reviewer_package[(reviewer_id, package_ids[2])]
        pairwise = identity.get("pairwise_results")
        if (
            not isinstance(pairwise, list)
            or len(pairwise) != 1
            or not isinstance(pairwise[0], Mapping)
            or pairwise[0].get("outcome") not in {"TIE", "INDETERMINATE"}
        ):
            _calibration_failure(
                round_number,
                "calibration_identity_not_tie",
            )


def validate_calibration(
    *,
    calibration_lock: Mapping[str, object],
    controller_mapping: Mapping[str, object],
    controller_root: Path,
    reviews: Sequence[Mapping[str, object]],
    predecessor_lock: Mapping[str, object] | None,
    predecessor_controller_mapping: Mapping[str, object] | None,
    predecessor_controller_root: Path | None,
    predecessor_reviews: Sequence[Mapping[str, object]] | None,
) -> None:
    """Validate one prospective calibration round without relaxing round two."""

    _calibration_id, round_number, _revision, _reviewers, _packages = (
        _calibration_shape(calibration_lock)
    )
    _validate_calibration_predecessor(
        calibration_lock=calibration_lock,
        round_number=round_number,
        predecessor_lock=predecessor_lock,
        predecessor_controller_mapping=predecessor_controller_mapping,
        predecessor_controller_root=predecessor_controller_root,
        predecessor_reviews=predecessor_reviews,
    )
    try:
        _validate_calibration_round(
            calibration_lock=calibration_lock,
            controller_mapping=controller_mapping,
            controller_root=controller_root,
            reviews=reviews,
        )
    except EvaluationError as exc:
        if round_number == 2 and exc.code != "CALIBRATION_FAILED":
            raise EvaluationError("CALIBRATION_FAILED", exc.code) from exc
        raise
