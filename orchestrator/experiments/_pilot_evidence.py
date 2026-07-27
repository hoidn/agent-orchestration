"""Pilot-specific copied-product evaluation and package preparation."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from . import _runner_apparatus as apparatus
from . import _runner_source as source
from .evaluation import EvaluationError, build_blind_packages
from ._evaluation_support import (
    _publish_new_payload,
    _relative_path,
    _safe_component,
    _sha256_bytes,
)
from ._pilot_evaluator_apparatus import _stage_evaluator_apparatus
from ._pilot_evidence_support import (
    PilotEvidenceError,
    _copy_projected_product,
    _fail,
    _product_roots,
    _run_evaluator,
    _validated_inputs,
)
from ._runner_types import RunnerError
from .workspace import (
    TreeManifest,
    WorkspaceError,
    freeze_product,
    materialize_git_archive,
)


def _validate_attempt_lineage(
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
) -> None:
    block_id = attempt.get("block_id")
    attempt_class = attempt.get("attempt_class")
    sequence_index = attempt.get("sequence_index")
    live_ids = lock.get("live_attempt_ids")
    if (
        not isinstance(block_id, str)
        or isinstance(sequence_index, bool)
        or not isinstance(sequence_index, int)
        or not isinstance(live_ids, list)
    ):
        _fail("pilot_evidence_lineage_invalid", "attempt identity")
    if attempt_class == "SMOKE":
        identity_valid = (
            sequence_index == 0 and block_id == lock.get("smoke_id")
        )
    else:
        identity_valid = (
            attempt_class == "LIVE"
            and 0 <= sequence_index < len(live_ids)
            and block_id == live_ids[sequence_index]
        )
    treatments = lock.get("treatments")
    executions = attempt.get("treatment_executions")
    if (
        not identity_valid
        or not isinstance(treatments, list)
        or not isinstance(executions, list)
    ):
        _fail("pilot_evidence_lineage_invalid", "attempt identity")
    locked = {
        item["treatment_id"]: item
        for item in treatments
        if isinstance(item, Mapping)
    }
    observed = {
        item["treatment_id"]: item
        for item in executions
        if isinstance(item, Mapping) and isinstance(item.get("treatment_id"), str)
    }
    if set(observed) != set(locked) or len(observed) != len(executions):
        _fail("pilot_evidence_lineage_invalid", "treatment coverage")
    seed = lock.get("randomization_seed")
    if not isinstance(seed, str):
        _fail("pilot_evidence_lineage_invalid", "randomization seed")
    for role, execution in observed.items():
        if (
            execution.get("command_digest")
            != locked[role].get("command_digest")
            or execution.get("opaque_arm_label")
            != apparatus.opaque_label(seed, block_id, role)
        ):
            _fail("pilot_evidence_lineage_invalid", role)


def prepare_block_package(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    work_root: Path,
    evaluation_root: Path,
    package_root: Path,
) -> dict[str, object]:
    """Prepare evaluator evidence and one blind package for a valid attempt."""

    (
        locked,
        terminal,
        work,
        evaluation,
        package,
        evidence,
        _control,
    ) = _validated_inputs(
        lock=lock,
        attempt=attempt,
        work_root=work_root,
        evaluation_root=evaluation_root,
        package_root=package_root,
    )
    _validate_attempt_lineage(locked, terminal)
    try:
        verified = apparatus.verified_assets(locked)
        binding = source.preflight_source(locked)
    except RunnerError as exc:
        raise PilotEvidenceError(
            "pilot_evidence_apparatus_invalid",
            str(exc),
        ) from exc
    products, executions = _product_roots(
        lock=locked,
        attempt=terminal,
        work_root=work,
    )
    exclusions = tuple(
        PurePosixPath(item)
        for item in locked["apparatus"]["product_projection_exclusions"]
    )
    manifests: dict[str, TreeManifest] = {}
    for role, product in products.items():
        try:
            manifest = freeze_product(product, exclusions)
        except WorkspaceError as exc:
            raise PilotEvidenceError(
                "pilot_evidence_product_invalid",
                role,
            ) from exc
        if (
            executions[role].get("product_frozen") is not True
            or executions[role].get("product_manifest_digest")
            != manifest.digest
        ):
            _fail("pilot_evidence_product_manifest_mismatch", role)
        manifests[role] = manifest

    evaluation.mkdir(parents=True)
    base_root = evaluation / "base"
    try:
        base_manifest = materialize_git_archive(
            binding.repo,
            binding.treeish,
            base_root,
        )
    except (OSError, subprocess.CalledProcessError, WorkspaceError) as exc:
        raise PilotEvidenceError(
            "pilot_evidence_archive_invalid",
            str(exc),
        ) from exc
    if base_manifest.digest != binding.archive_digest:
        _fail("pilot_evidence_archive_invalid", "manifest digest")

    copied: dict[str, Path] = {}
    candidates_root = evaluation / "candidates"
    candidates_root.mkdir()
    for role, execution in executions.items():
        label = _safe_component(execution.get("opaque_arm_label"))
        destination = candidates_root / label
        _copy_projected_product(products[role], destination, manifests[role])
        copied[role] = destination

    runtime_parent = evaluation / ".controller"
    runtime_parent.mkdir()
    module_path, timeout = _stage_evaluator_apparatus(
        lock=locked,
        verified=verified,
        root=runtime_parent / "evaluator-apparatus",
    )
    quiescence_grace = locked["apparatus"][
        "quiescence_grace_milliseconds"
    ]
    evaluator_evidence: dict[str, dict[str, object]] = {}
    block_id = _safe_component(terminal.get("block_id"))
    for role, execution in executions.items():
        label = _safe_component(execution.get("opaque_arm_label"))
        result, payload = _run_evaluator(
            module_path=module_path,
            product_root=copied[role],
            runtime_root=runtime_parent / label,
            timeout_milliseconds=timeout,
            quiescence_grace_milliseconds=quiescence_grace,
        )
        try:
            after = freeze_product(copied[role], ())
        except WorkspaceError as exc:
            raise PilotEvidenceError(
                "pilot_evidence_copy_manifest_mismatch",
                role,
            ) from exc
        if after != manifests[role]:
            _fail("pilot_evidence_copy_manifest_mismatch", role)
        relative = _relative_path(
            f"{block_id}/{label}/hidden-evaluator.json"
        )
        try:
            _publish_new_payload(
                root=evidence,
                relative=relative,
                data=payload,
            )
        except EvaluationError as exc:
            raise PilotEvidenceError(
                "pilot_evidence_publication_failed",
                str(exc),
            ) from exc
        evidence_path = evidence.joinpath(*relative.parts)
        evaluator_evidence[role] = {
            "path": evidence_path,
            "digest": _sha256_bytes(payload),
            "verdict": result["verdict"],
        }

    review = locked["review"]
    selected = tuple(review["selected_final_files"])
    names = tuple(review["permitted_check_evidence_names"])
    selected_by_role = {role: selected for role in copied}
    checks_by_role = {
        role: tuple(
            f"{block_id}/{executions[role]['opaque_arm_label']}/{name}"
            for name in names
        )
        for role in copied
    }
    try:
        packages = build_blind_packages(
            lock=locked,
            block=terminal,
            product_roots=copied,
            base_root=base_root,
            task_path=locked["apparatus"]["task_path"],
            selected_final_files=selected_by_role,
            permitted_check_evidence=checks_by_role,
            output_root=package,
            controller_root=evidence,
        )
    except EvaluationError as exc:
        raise PilotEvidenceError(
            "pilot_evidence_package_failed",
            str(exc),
        ) from exc
    package_path = packages[block_id]
    manifest_path = package_path / "manifest.json"
    label_map_path = evidence / "label-maps" / f"{block_id}.json"
    return {
        "package_id": block_id,
        "package_root": package_path,
        "package_manifest_digest": _sha256_bytes(manifest_path.read_bytes()),
        "label_map_path": label_map_path,
        "label_map_digest": _sha256_bytes(label_map_path.read_bytes()),
        "evaluation_product_roots": copied,
        "evaluator_evidence": evaluator_evidence,
    }
