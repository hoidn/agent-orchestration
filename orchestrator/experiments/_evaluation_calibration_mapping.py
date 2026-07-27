"""Closed calibration controller-mapping validation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from .contracts import canonical_json_bytes, canonical_sha256
from ._evaluation_support import (
    EvaluationError,
    _canonical_root,
    _fail,
    _relative_path,
    _sha256_bytes,
    _source_file,
    _strict_json,
)


def _validate_calibration_file_binding(
    *,
    controller_root: Path,
    value: object,
    label: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "evidence_path",
        "mode",
        "size",
        "sha256",
    }:
        _fail("calibration_mapping_mismatch", label)
    relative = _relative_path(value.get("evidence_path"))
    try:
        source, data, mode = _source_file(controller_root, relative)
    except EvaluationError as exc:
        raise EvaluationError("calibration_mapping_mismatch", label) from exc
    if (
        source != controller_root.joinpath(*relative.parts)
        or value.get("mode") != mode
        or value.get("size") != len(data)
        or value.get("sha256") != _sha256_bytes(data)
    ):
        _fail("calibration_mapping_mismatch", label)
    return dict(value)


def _validate_calibration_controller_mapping(
    *,
    calibration_lock: Mapping[str, object],
    controller_mapping: Mapping[str, object],
    controller_root: Path,
    calibration_id: str,
    reviewer_ids: tuple[str, str],
    package_ids: tuple[str, str, str],
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    try:
        controller = _canonical_root(controller_root, must_exist=True)
        mapping_path = controller / "controller-mapping.json"
        mapping_bytes = mapping_path.read_bytes()
        disk_mapping = _strict_json(
            mapping_path,
            code="calibration_mapping_mismatch",
        )
    except (OSError, EvaluationError) as exc:
        if isinstance(exc, EvaluationError) and exc.code == "calibration_mapping_mismatch":
            raise
        raise EvaluationError("calibration_mapping_mismatch", "mapping file") from exc
    if (
        canonical_json_bytes(disk_mapping) != mapping_bytes
        or canonical_json_bytes(disk_mapping)
        != canonical_json_bytes(controller_mapping)
        or set(controller_mapping)
        != {
            "calibration_id",
            "calibration_lock_digest",
            "bindings",
            "evaluation",
            "packages",
            "review_bindings",
            "reviewer_execution",
        }
        or controller_mapping.get("calibration_id") != calibration_id
        or controller_mapping.get("calibration_lock_digest")
        != canonical_sha256(calibration_lock)
        or controller_mapping.get("reviewer_execution")
        != calibration_lock.get("reviewer_execution")
    ):
        _fail("calibration_mapping_mismatch", "mapping")

    bindings = controller_mapping.get("bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != {
        "evaluator_module",
        "oracle_module",
        "reference_patch",
        "rubric",
        "reviewer_cli_entry",
        "environment_identity",
    }:
        _fail("calibration_mapping_mismatch", "bindings")
    lock_binding_digests = {
        "evaluator_module": calibration_lock["evaluator"]["module_digest"],  # type: ignore[index]
        "oracle_module": calibration_lock["oracle"]["digest"],  # type: ignore[index]
        "reference_patch": calibration_lock["reference_patch"]["digest"],  # type: ignore[index]
        "rubric": calibration_lock["rubric"]["digest"],  # type: ignore[index]
        "reviewer_cli_entry": calibration_lock["reviewer_execution"]["cli"][  # type: ignore[index]
            "entry_sha256"
        ],
    }
    for name, expected_digest in lock_binding_digests.items():
        binding = _validate_calibration_file_binding(
            controller_root=controller,
            value=bindings.get(name),
            label=f"bindings.{name}",
        )
        if binding["sha256"] != expected_digest:
            _fail("calibration_mapping_mismatch", f"bindings.{name}")
    if bindings.get("environment_identity") != calibration_lock.get(
        "environment_identity"
    ):
        _fail("calibration_mapping_mismatch", "bindings.environment_identity")

    evaluation = controller_mapping.get("evaluation")
    if not isinstance(evaluation, Mapping) or set(evaluation) != {
        "visible_check",
        "hidden_evaluator_class",
        "raw_evidence",
        "base",
        "reference",
    }:
        _fail("calibration_mapping_mismatch", "evaluation")
    if (
        evaluation.get("visible_check") != calibration_lock.get("visible_check")
        or evaluation.get("hidden_evaluator_class")
        != calibration_lock.get("hidden_evaluator_class")
    ):
        _fail("calibration_mapping_mismatch", "evaluation contract")
    raw_evidence = evaluation.get("raw_evidence")
    if not isinstance(raw_evidence, Mapping) or set(raw_evidence) != {
        "base_hidden",
        "reference_hidden",
    }:
        _fail("calibration_mapping_mismatch", "evaluation.raw_evidence")
    for name in ("base_hidden", "reference_hidden"):
        _validate_calibration_file_binding(
            controller_root=controller,
            value=raw_evidence.get(name),
            label=f"evaluation.raw_evidence.{name}",
        )
    expected_contrast = calibration_lock.get("expected_contrast")
    if not isinstance(expected_contrast, Mapping):
        _fail("calibration_mapping_mismatch", "expected contrast")
    expected_evaluation = {
        "base": {
            "visible_check": expected_contrast.get("base_visible"),
            "hidden_evaluator": expected_contrast.get("base_hidden"),
        },
        "reference": {
            "visible_check": expected_contrast.get("reference_visible"),
            "hidden_evaluator": expected_contrast.get("reference_hidden"),
        },
    }
    for role, expected in expected_evaluation.items():
        value = evaluation.get(role)
        if (
            not isinstance(value, Mapping)
            or set(value) != {"visible_check", "hidden_evaluator"}
            or value != expected
        ):
            _fail("calibration_mapping_mismatch", f"evaluation.{role}")

    packages = controller_mapping.get("packages")
    if not isinstance(packages, Mapping) or set(packages) != set(package_ids):
        _fail("calibration_mapping_mismatch", "packages")
    for package_id in package_ids:
        package = packages.get(package_id)
        if not isinstance(package, Mapping) or set(package) != {
            "labels",
            "candidate_labels",
            "manifest_digest",
        }:
            _fail("calibration_mapping_mismatch", f"packages.{package_id}")
        labels = package.get("labels")
        candidate_labels = package.get("candidate_labels")
        digest = package.get("manifest_digest")
        if (
            not isinstance(labels, Mapping)
            or not isinstance(candidate_labels, list)
            or len(candidate_labels) != 2
            or len(set(candidate_labels)) != 2
            or set(labels) != set(candidate_labels)
            or any(not isinstance(value, str) or not value for value in candidate_labels)
            or not isinstance(digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        ):
            _fail("calibration_mapping_mismatch", f"packages.{package_id}")

    directional_labels = packages[package_ids[0]]["candidate_labels"]
    label_a, label_b = directional_labels
    expected_package_roles = {
        package_ids[0]: {label_a: "REFERENCE", label_b: "BASE"},
        package_ids[1]: {label_a: "BASE", label_b: "REFERENCE"},
        package_ids[2]: {label_a: "REFERENCE", label_b: "REFERENCE"},
    }
    for package_id, expected_roles in expected_package_roles.items():
        package = packages[package_id]
        if (
            package["candidate_labels"] != directional_labels
            or package["labels"] != expected_roles
        ):
            _fail(
                "calibration_mapping_mismatch",
                f"packages.{package_id}.roles",
            )

    review_bindings = controller_mapping.get("review_bindings")
    expected_review_ids = {
        f"{package_id}-{reviewer_id}"
        for reviewer_id in reviewer_ids
        for package_id in package_ids
    }
    if (
        not isinstance(review_bindings, Mapping)
        or set(review_bindings) != expected_review_ids
    ):
        _fail("calibration_mapping_mismatch", "review bindings")
    rubric = calibration_lock.get("rubric")
    rubric_digest = rubric.get("digest") if isinstance(rubric, Mapping) else None
    for review_id, value in review_bindings.items():
        if not isinstance(value, Mapping) or set(value) != {
            "package_id",
            "reviewer_id",
            "rubric_digest",
            "package_manifest_digest",
        }:
            _fail("calibration_mapping_mismatch", f"review binding {review_id}")
        package_id = value.get("package_id")
        reviewer_id = value.get("reviewer_id")
        package = packages.get(package_id)
        if (
            package_id not in package_ids
            or reviewer_id not in reviewer_ids
            or review_id != f"{package_id}-{reviewer_id}"
            or value.get("rubric_digest") != rubric_digest
            or not isinstance(package, Mapping)
            or value.get("package_manifest_digest")
            != package.get("manifest_digest")
        ):
            _fail("calibration_mapping_mismatch", f"review binding {review_id}")
    return packages, review_bindings
