"""Calibration package construction and controller evidence."""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

from .contracts import canonical_json_bytes, canonical_sha256
from .workspace import WorkspaceError, freeze_product
from ._evaluation_calibration_support import (
    _calibration_shape,
    _existing_file_binding,
    _file_binding,
    _json_evidence_bytes,
    _load_oracle,
    _reviewable_evaluator_result,
    _run_hidden_evaluator,
    _run_visible_check,
    _validate_base_identity,
    _validate_reviewer_execution,
)
from ._evaluation_calibration_validation import _validate_calibration_predecessor
from ._evaluation_support import (
    EvaluationError,
    _build_package,
    _fail,
    _opaque_labels,
    _relative_path,
    _sha256_bytes,
    _source_file,
    _validate_roots,
    _write_payload,
)


def build_calibration_packages(
    *,
    calibration_lock: Mapping[str, object],
    base_identity: Mapping[str, object],
    predecessor_lock: Mapping[str, object] | None,
    predecessor_controller_mapping: Mapping[str, object] | None,
    predecessor_controller_root: Path | None,
    predecessor_reviews: Sequence[Mapping[str, object]] | None,
    base_root: Path,
    task_path: str,
    reference_patch: Path,
    rubric_path: Path,
    selected_final_files: Sequence[str],
    visible_check_argv: Sequence[str],
    visible_check_timeout_milliseconds: int,
    visible_check_class: str,
    hidden_evaluator_class: str,
    evaluator_module: ModuleType,
    oracle_path: Path,
    environment: Mapping[str, str],
    reviewer_execution: Mapping[str, object],
    output_root: Path,
    controller_root: Path,
) -> dict[str, Path]:
    """Prove the A0 contrast and build two directions plus identity."""

    (
        calibration_id,
        round_number,
        _revision,
        reviewer_ids,
        package_ids,
    ) = _calibration_shape(calibration_lock)
    _validate_calibration_predecessor(
        calibration_lock=calibration_lock,
        round_number=round_number,
        predecessor_lock=predecessor_lock,
        predecessor_controller_mapping=predecessor_controller_mapping,
        predecessor_controller_root=predecessor_controller_root,
        predecessor_reviews=predecessor_reviews,
    )
    base, _products, output, controller = _validate_roots(
        base_root=base_root,
        product_roots={},
        output_root=output_root,
        controller_root=controller_root,
    )
    locked_base_identity = _validate_base_identity(
        calibration_lock.get("base_identity"),
        code="calibration_lock_invalid",
    )
    supplied_base_identity = _validate_base_identity(
        base_identity,
        code="calibration_binding_invalid",
    )
    if supplied_base_identity != locked_base_identity:
        _fail("calibration_binding_invalid", "base_identity")
    task = _relative_path(task_path)
    selected = tuple(_relative_path(value) for value in selected_final_files)
    if not selected:
        _fail("evaluation_product_binding_invalid", "selected final files")
    if (
        not visible_check_argv
        or any(not isinstance(value, str) or not value for value in visible_check_argv)
        or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            for key, value in environment.items()
        )
    ):
        _fail("calibration_binding_invalid")
    reviewer_cli_entry = _validate_reviewer_execution(
        reviewer_execution,
        code="calibration_binding_invalid",
    )
    if canonical_json_bytes(reviewer_execution) != canonical_json_bytes(
        calibration_lock["reviewer_execution"]
    ):
        _fail("calibration_binding_invalid", "reviewer_execution")

    evaluator_path_value = getattr(evaluator_module, "__file__", None)
    if not isinstance(evaluator_path_value, str):
        _fail("calibration_evaluator_invalid", "module path")
    evaluator_path = Path(evaluator_path_value).resolve(strict=True)
    oracle = oracle_path.resolve(strict=True)
    patch = reference_patch.resolve(strict=True)
    rubric = rubric_path.resolve(strict=True)
    try:
        calibration_exclusions = tuple(
            _relative_path(value)
            for value in calibration_lock["product_projection_exclusions"]  # type: ignore[index]
        )
        archive_manifest = freeze_product(base, ())
        base_manifest = freeze_product(base, calibration_exclusions)
        _task_source, task_bytes, _task_mode = _source_file(base, task)
    except WorkspaceError as exc:
        raise EvaluationError("calibration_binding_invalid", str(exc)) from exc
    expected_bindings = {
        "base_identity": {
            "repository_identity": supplied_base_identity[
                "repository_identity"
            ],
            "revision_identity": supplied_base_identity["revision_identity"],
            "archive_digest": archive_manifest.digest,
            "product_manifest_digest": base_manifest.digest,
        },
        "product_projection_exclusions": [
            value.as_posix() for value in calibration_exclusions
        ],
        "task": {"path": task_path, "digest": _sha256_bytes(task_bytes)},
        "reference_patch": {
            "path": calibration_lock.get("reference_patch", {}).get("path")
            if isinstance(calibration_lock.get("reference_patch"), Mapping)
            else None,
            "digest": _sha256_bytes(patch.read_bytes()),
        },
        "rubric": {
            "path": calibration_lock.get("rubric", {}).get("path")
            if isinstance(calibration_lock.get("rubric"), Mapping)
            else None,
            "digest": _sha256_bytes(rubric.read_bytes()),
        },
        "selected_final_files": list(selected_final_files),
        "evaluator": {
            "module_digest": _sha256_bytes(evaluator_path.read_bytes()),
            "class": getattr(evaluator_module, "__name__", "").rsplit(".", 1)[-1],
        },
        "oracle": {"digest": _sha256_bytes(oracle.read_bytes())},
        "environment_identity": canonical_sha256(
            [[key, environment[key]] for key in sorted(environment)]
        ),
        "visible_check": {
            "argv": list(visible_check_argv),
            "timeout_milliseconds": visible_check_timeout_milliseconds,
            "class": visible_check_class,
        },
        "hidden_evaluator_class": hidden_evaluator_class,
        "expected_contrast": {
            "base_visible": "FAIL",
            "reference_visible": "PASS",
            "base_hidden": "FAIL",
            "reference_hidden": "PASS",
        },
    }
    for key, actual in expected_bindings.items():
        locked = calibration_lock.get(key)
        if key in {"reference_patch", "rubric"}:
            source_path = patch if key == "reference_patch" else rubric
            locked_path = locked.get("path") if isinstance(locked, Mapping) else None
            if (
                not isinstance(locked, Mapping)
                or set(locked) != {"path", "digest"}
                or locked.get("digest") != actual["digest"]  # type: ignore[index]
                or not isinstance(locked_path, str)
                or not locked_path
                or not source_path.as_posix().endswith(
                    f"/{_relative_path(locked_path).as_posix()}"
                )
            ):
                _fail("calibration_binding_invalid", key)
        elif locked != actual:
            _fail("calibration_binding_invalid", key)

    output.mkdir(parents=True, exist_ok=False)
    controller.mkdir(parents=True, exist_ok=False)
    materialized = controller / "materialized"
    reference_root = materialized / "candidate"
    shutil.copytree(base, reference_root, symlinks=True)
    try:
        subprocess.run(
            (
                "git",
                "apply",
                "--unidiff-zero",
                "--check",
                str(patch),
            ),
            cwd=reference_root,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        subprocess.run(
            (
                "git",
                "apply",
                "--unidiff-zero",
                str(patch),
            ),
            cwd=reference_root,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EvaluationError("calibration_reference_patch_invalid") from exc

    oracle_module = _load_oracle(oracle)
    try:
        base_visible = _run_visible_check(
            root=base,
            argv=visible_check_argv,
            environment=environment,
            timeout_milliseconds=visible_check_timeout_milliseconds,
        )
        reference_visible = _run_visible_check(
            root=reference_root,
            argv=visible_check_argv,
            environment=environment,
            timeout_milliseconds=visible_check_timeout_milliseconds,
        )
        base_hidden = _run_hidden_evaluator(
            evaluator_module=evaluator_module,
            oracle_module=oracle_module,
            root=base,
            environment=environment,
        )
        reference_hidden = _run_hidden_evaluator(
            evaluator_module=evaluator_module,
            oracle_module=oracle_module,
            root=reference_root,
            environment=environment,
        )
    finally:
        sys.modules.pop(oracle_module.__name__, None)

    actual = (
        base_visible["verdict"],
        reference_visible["verdict"],
        base_hidden["verdict"],
        reference_hidden["verdict"],
    )
    if actual != ("FAIL", "PASS", "FAIL", "PASS"):
        _fail("calibration_a0_contrast_invalid", repr(actual))

    bindings_root = controller / "bindings"
    evaluator_binding = _file_binding(
        evaluator_path,
        bindings_root / "evaluator-module.py",
        relative_to=controller,
    )
    oracle_binding = _file_binding(
        oracle,
        bindings_root / "oracle-module.py",
        relative_to=controller,
    )
    patch_binding = _file_binding(
        patch,
        bindings_root / "reference.patch",
        relative_to=controller,
    )
    rubric_binding = _file_binding(
        rubric,
        bindings_root / "rubric.md",
        relative_to=controller,
    )
    reviewer_cli_binding = _file_binding(
        reviewer_cli_entry,
        bindings_root / "reviewer-cli-entry",
        relative_to=controller,
    )
    evaluation_root = controller / "evaluation"
    raw_base_hidden_path = evaluation_root / "raw-base-hidden.json"
    raw_reference_hidden_path = evaluation_root / "raw-reference-hidden.json"
    _write_payload(raw_base_hidden_path, _json_evidence_bytes(base_hidden))
    _write_payload(
        raw_reference_hidden_path,
        _json_evidence_bytes(reference_hidden),
    )
    base_evidence = {
        "visible_check": base_visible,
        "hidden_evaluator": _reviewable_evaluator_result(
            base_hidden,
            hidden_roots=(base,),
        ),
    }
    reference_evidence = {
        "visible_check": reference_visible,
        "hidden_evaluator": _reviewable_evaluator_result(
            reference_hidden,
            hidden_roots=(reference_root,),
        ),
    }
    base_evidence_path = evaluation_root / "candidate-evidence-001.json"
    reference_evidence_path = evaluation_root / "candidate-evidence-002.json"
    _write_payload(base_evidence_path, canonical_json_bytes(base_evidence))
    _write_payload(
        reference_evidence_path,
        canonical_json_bytes(reference_evidence),
    )

    seed = str(calibration_lock["mapping_seed"])
    labels = _opaque_labels(seed, calibration_id, 2)
    label_a, label_b = labels
    package_roles = {
        package_ids[0]: {label_a: "REFERENCE", label_b: "BASE"},
        package_ids[1]: {label_a: "BASE", label_b: "REFERENCE"},
        package_ids[2]: {label_a: "REFERENCE", label_b: "REFERENCE"},
    }
    role_roots = {"BASE": base, "REFERENCE": reference_root}
    role_checks = {
        "BASE": (
            _relative_path(base_evidence_path.relative_to(controller).as_posix()),
        ),
        "REFERENCE": (
            _relative_path(
                reference_evidence_path.relative_to(controller).as_posix()
            ),
        ),
    }
    packages: dict[str, Path] = {}
    for package_id in package_ids:
        roles = package_roles[package_id]
        packages[package_id] = _build_package(
            package_id=package_id,
            candidate_labels=labels,
            roots_by_label={
                label: role_roots[role] for label, role in roles.items()
            },
            base_root=base,
            task_path=task,
            selected_by_label={label: selected for label in labels},
            checks_by_label={
                label: role_checks[role] for label, role in roles.items()
            },
            product_exclusions=calibration_exclusions,
            controller_root=controller,
            output_root=output,
        )

    review_bindings = {}
    for reviewer_id in reviewer_ids:
        for package_id in package_ids:
            review_bindings[f"{package_id}-{reviewer_id}"] = {
                "package_id": package_id,
                "reviewer_id": reviewer_id,
                "rubric_digest": calibration_lock["rubric"]["digest"],
                "package_manifest_digest": _sha256_bytes(
                    (packages[package_id] / "manifest.json").read_bytes()
                ),
            }
    mapping = {
        "calibration_id": calibration_id,
        "calibration_lock_digest": canonical_sha256(calibration_lock),
        "bindings": {
            "evaluator_module": evaluator_binding,
            "oracle_module": oracle_binding,
            "reference_patch": patch_binding,
            "rubric": rubric_binding,
            "reviewer_cli_entry": reviewer_cli_binding,
            "environment_identity": canonical_sha256(
                [[key, environment[key]] for key in sorted(environment)]
            ),
        },
        "evaluation": {
            "visible_check": {
                "argv": list(visible_check_argv),
                "timeout_milliseconds": visible_check_timeout_milliseconds,
                "class": visible_check_class,
            },
            "hidden_evaluator_class": hidden_evaluator_class,
            "raw_evidence": {
                "base_hidden": _existing_file_binding(
                    raw_base_hidden_path,
                    relative_to=controller,
                ),
                "reference_hidden": _existing_file_binding(
                    raw_reference_hidden_path,
                    relative_to=controller,
                ),
            },
            "base": {
                "visible_check": base_visible["verdict"],
                "hidden_evaluator": base_hidden["verdict"],
            },
            "reference": {
                "visible_check": reference_visible["verdict"],
                "hidden_evaluator": reference_hidden["verdict"],
            },
        },
        "packages": {
            package_id: {
                "labels": package_roles[package_id],
                "candidate_labels": list(labels),
                "manifest_digest": _sha256_bytes(
                    (packages[package_id] / "manifest.json").read_bytes()
                ),
            }
            for package_id in package_ids
        },
        "review_bindings": review_bindings,
        "reviewer_execution": calibration_lock["reviewer_execution"],
    }
    _write_payload(
        controller / "controller-mapping.json",
        canonical_json_bytes(mapping),
    )
    return packages
