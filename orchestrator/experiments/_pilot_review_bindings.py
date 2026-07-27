"""Canonical sealed-review and later unblinding publication."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from ._evaluation_support import (
    EvaluationError,
    _canonical_root,
    _fail,
    _relative_path,
    _source_file,
)
from ._pilot_review_support import _package_contract, _publish
from ._reporting_reviews import _locked_label_assignments
from ._reporting_types import TREATMENTS
from .contracts import (
    PilotContractError,
    canonical_json_bytes,
    canonical_sha256,
    validate_record,
)


def _canonical_file(root: Path, relative: str, *, code: str) -> object:
    try:
        _path, data, _mode = _source_file(root, _relative_path(relative))
        value = json.loads(data)
    except (EvaluationError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(code, str(exc)) from exc
    if canonical_json_bytes(value) != data:
        _fail(code, "noncanonical file")
    return value


def _ordered_blocks(
    lock: Mapping[str, object],
    block_packages: Mapping[str, Path],
) -> tuple[str, ...]:
    live_ids = lock.get("live_attempt_ids")
    if (
        not isinstance(live_ids, list)
        or not set(block_packages).issubset(live_ids)
    ):
        _fail("review_bindings_invalid", "block set")
    return tuple(item for item in live_ids if item in block_packages)


def _review_rows(
    *,
    lock: Mapping[str, object],
    block_packages: Mapping[str, Path],
    reviews: Sequence[Mapping[str, object]],
    evidence: Path,
) -> list[dict[str, object]]:
    blocks = _ordered_blocks(lock, block_packages)
    reviewer_ids = tuple(lock["review"]["reviewer_ids"])  # type: ignore[index]
    by_slot: dict[tuple[str, str], Mapping[str, object]] = {}
    seen_sessions: set[str] = set()
    for review in reviews:
        try:
            record = dict(review)
            validate_record(record)
        except PilotContractError as exc:
            raise EvaluationError("review_bindings_invalid", str(exc)) from exc
        if record.get("record_kind") != "review_result.v1":
            _fail("review_bindings_invalid", "record kind")
        review_id = record["review_id"]
        slot = next(
            (
                (block, reviewer)
                for block in blocks
                for reviewer in reviewer_ids
                if review_id == f"{block}-{reviewer}"
            ),
            None,
        )
        if (
            slot is None
            or slot in by_slot
            or record["session_id"] in seen_sessions
        ):
            _fail("review_bindings_invalid", "review coverage")
        by_slot[slot] = record
        seen_sessions.add(record["session_id"])
    expected_slots = {
        (block, reviewer) for block in blocks for reviewer in reviewer_ids
    }
    if set(by_slot) != expected_slots:
        _fail("review_bindings_invalid", "review coverage")
    rows: list[dict[str, object]] = []
    for block in blocks:
        package = _package_contract(block_packages[block], block)
        for reviewer in reviewer_ids:
            record = by_slot[(block, reviewer)]
            relative = f"{block}/reviews/{reviewer}/review-result.json"
            try:
                _path, data, _mode = _source_file(
                    evidence,
                    _relative_path(relative),
                )
            except EvaluationError as exc:
                raise EvaluationError("review_bindings_invalid", str(exc)) from exc
            if (
                canonical_json_bytes(record) != data
                or record["pilot_lock_digest"] != canonical_sha256(lock)
                or record["rubric_digest"]
                != lock["review"]["rubric_digest"]  # type: ignore[index]
                or record["reviewer_id"] != reviewer
                or record["review_class"] != "LIVE"
                or tuple(
                    item["opaque_label"] for item in record["candidates"]  # type: ignore[index]
                )
                != tuple(
                    package["manifest"]["candidate_labels"]  # type: ignore[index]
                )
            ):
                _fail("review_bindings_invalid", "review binding")
            rows.append(
                {
                    "block_id": block,
                    "package_id": block,
                    "package_manifest_digest": package["manifest_digest"],
                    "review_id": record["review_id"],
                    "review_result_digest": canonical_sha256(record),
                    "review_path": relative,
                    "reviewer_id": reviewer,
                    "reviewer_role": "INITIAL",
                }
            )
    return rows


def publish_review_bindings(
    *,
    lock: Mapping[str, object],
    block_packages: Mapping[str, Path],
    reviews: Sequence[Mapping[str, object]],
    evidence_root: Path,
) -> Path:
    """Publish the exact block/reviewer-ordered initial-review bindings."""

    evidence = _canonical_root(evidence_root, must_exist=True)
    if evidence.as_posix() != lock.get("evidence_root"):
        _fail("review_bindings_invalid", "evidence root")
    rows = _review_rows(
        lock=lock,
        block_packages=block_packages,
        reviews=reviews,
        evidence=evidence,
    )
    _publish(
        evidence,
        "review-bindings.json",
        canonical_json_bytes(rows),
        code="review_bindings_exist",
    )
    return evidence / "review-bindings.json"


def publish_unblinding_bindings(
    *,
    lock: Mapping[str, object],
    block_packages: Mapping[str, Path],
    evidence_root: Path,
    review_bindings_path: Path,
) -> Path:
    """Verify every sealed review before reading immutable label maps."""

    evidence = _canonical_root(evidence_root, must_exist=True)
    expected_path = evidence / "review-bindings.json"
    if review_bindings_path != expected_path:
        _fail("review_bindings_invalid", "path")
    blocks = _ordered_blocks(lock, block_packages)
    reviews: list[dict[str, object]] = []
    for block in blocks:
        for reviewer in lock["review"]["reviewer_ids"]:  # type: ignore[index]
            value = _canonical_file(
                evidence,
                f"{block}/reviews/{reviewer}/review-result.json",
                code="review_bindings_invalid",
            )
            if not isinstance(value, dict):
                _fail("review_bindings_invalid", "review")
            reviews.append(value)
    expected_rows = _review_rows(
        lock=lock,
        block_packages=block_packages,
        reviews=reviews,
        evidence=evidence,
    )
    actual_rows = _canonical_file(
        evidence,
        "review-bindings.json",
        code="review_bindings_invalid",
    )
    if actual_rows != expected_rows:
        _fail("review_bindings_invalid", "sealed binding set")

    rows: list[dict[str, object]] = []
    for block in blocks:
        package = _package_contract(block_packages[block], block)
        mapping = _canonical_file(
            evidence,
            f"label-maps/{block}.json",
            code="unblinding_bindings_invalid",
        )
        if not isinstance(mapping, dict):
            _fail("unblinding_bindings_invalid", "label map")
        expected_assignments = _locked_label_assignments(lock, block)
        try:
            package_mapping = mapping["packages"][block]
            observed = package_mapping["labels"]
            observed_digest = package_mapping["manifest_digest"]
        except (KeyError, TypeError):
            _fail("unblinding_bindings_invalid", "label map")
        if (
            observed
            != {
                label: treatment
                for treatment, label in expected_assignments.items()
            }
            or observed_digest != package["manifest_digest"]
        ):
            _fail("unblinding_bindings_invalid", "label map")
        for treatment in TREATMENTS:
            rows.append(
                {
                    "block_id": block,
                    "package_id": block,
                    "package_manifest_digest": package["manifest_digest"],
                    "opaque_label": expected_assignments[treatment],
                    "treatment_id": treatment,
                }
            )
    _publish(
        evidence,
        "unblinding-bindings.json",
        canonical_json_bytes(rows),
        code="unblinding_bindings_exist",
    )
    return evidence / "unblinding-bindings.json"
