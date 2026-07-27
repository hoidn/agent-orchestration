"""Live blinded-package construction internals."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from pathlib import Path, PurePosixPath

from .contracts import (
    PilotContractError,
    canonical_json_bytes,
    canonical_sha256,
    validate_record,
)
from .workspace import WorkspaceError, freeze_product
from ._evaluation_support import (
    EvaluationError,
    _build_package,
    _canonical_root,
    _execution_roles,
    _fail,
    _lock_seed,
    _opaque_labels,
    _overlaps,
    _publish_new_payload,
    _reject_identity_leak,
    _relative_path,
    _role_order,
    _safe_component,
    _sha256_bytes,
    _source_file,
    _validate_roots,
)


def _validate_live_lineage(
    *,
    lock: Mapping[str, object],
    block: Mapping[str, object],
    base_root: Path,
    product_roots: Mapping[str, Path],
    output_root: Path,
    controller_root: Path,
    task_path: str,
) -> tuple[
    tuple[str, ...],
    tuple[PurePosixPath, ...],
    Path,
    PurePosixPath,
]:
    try:
        validate_record(lock)
        validate_record(block)
    except PilotContractError as exc:
        raise EvaluationError("evaluation_lock_or_block_invalid", str(exc)) from exc
    attempt_class = block.get("attempt_class")
    if attempt_class not in {"SMOKE", "LIVE"} or block.get("status") != "VALID":
        _fail("evaluation_block_invalid", "requires locked VALID block")
    _safe_component(block.get("block_id"))
    lock_digest = canonical_sha256(lock)
    if block.get("pilot_lock_digest") != lock_digest:
        _fail("evaluation_lock_digest_mismatch")
    sequence_index = block.get("sequence_index")
    live_attempt_ids = lock.get("live_attempt_ids")
    if isinstance(sequence_index, bool) or not isinstance(sequence_index, int):
        _fail("evaluation_block_identity_mismatch")
    if attempt_class == "SMOKE":
        identity_matches = (
            sequence_index == 0 and block.get("block_id") == lock.get("smoke_id")
        )
    else:
        identity_matches = (
            isinstance(live_attempt_ids, list)
            and 0 <= sequence_index < len(live_attempt_ids)
            and block.get("block_id") == live_attempt_ids[sequence_index]
        )
    if not identity_matches:
        _fail("evaluation_block_identity_mismatch")
    archive = lock.get("archive")
    try:
        base_manifest = freeze_product(base_root, ())
    except WorkspaceError as exc:
        raise EvaluationError("evaluation_archive_digest_mismatch", str(exc)) from exc
    if (
        not isinstance(archive, Mapping)
        or archive.get("archive_digest") != base_manifest.digest
    ):
        _fail("evaluation_archive_digest_mismatch")
    locked_treatments = {
        item["treatment_id"]: item
        for item in lock["treatments"]  # type: ignore[index]
    }
    locked_roles = tuple(locked_treatments)
    roles = _execution_roles(block)
    if set(roles) != set(locked_roles) or set(product_roots) != set(locked_roles):
        _fail("evaluation_product_binding_invalid", "locked treatments")
    apparatus = lock["apparatus"]
    if not isinstance(apparatus, Mapping):
        _fail("evaluation_lock_invalid", "apparatus")
    if apparatus.get("task_path") != task_path:
        _fail("evaluation_lock_invalid", "task path")
    apparatus_task = _relative_path(task_path)
    task_lock = lock.get("task")
    if not isinstance(task_lock, Mapping):
        _fail("evaluation_lock_invalid", "task digest")
    source_task = _relative_path(task_lock.get("source_path"))
    _source_task, source_task_bytes, _source_task_mode = _source_file(
        base_root,
        source_task,
    )
    apparatus_root_value = apparatus.get("control_root")
    if not isinstance(apparatus_root_value, str):
        _fail("evaluation_lock_invalid", "apparatus root")
    apparatus_root = _canonical_root(
        Path(apparatus_root_value),
        must_exist=True,
    )
    if any(
        _overlaps(apparatus_root, root)
        for root in (
            base_root,
            *product_roots.values(),
            output_root,
            controller_root,
        )
    ):
        _fail("evaluation_root_overlap", "apparatus overlaps evaluation root")
    _apparatus_task, apparatus_task_bytes, _apparatus_task_mode = _source_file(
        apparatus_root,
        apparatus_task,
    )
    brief_digest = task_lock.get("brief_digest")
    if (
        brief_digest != _sha256_bytes(source_task_bytes)
        or brief_digest != _sha256_bytes(apparatus_task_bytes)
    ):
        _fail("evaluation_lock_invalid", "task digest")
    exclusions_value = apparatus.get("product_projection_exclusions")
    if not isinstance(exclusions_value, list):
        _fail("evaluation_lock_invalid", "product exclusions")
    exclusions = tuple(_relative_path(value) for value in exclusions_value)
    executions = {
        item["treatment_id"]: item
        for item in block["treatment_executions"]  # type: ignore[index]
    }
    for role in locked_roles:
        execution = executions[role]
        if execution.get("command_digest") != locked_treatments[role].get(
            "command_digest"
        ):
            _fail("evaluation_command_digest_mismatch", role)
        try:
            manifest = freeze_product(product_roots[role], exclusions)
        except WorkspaceError as exc:
            raise EvaluationError(
                "evaluation_product_manifest_invalid", str(exc)
            ) from exc
        if (
            execution.get("product_frozen") is not True
            or execution.get("product_manifest_digest") != manifest.digest
        ):
            _fail("evaluation_product_manifest_mismatch", role)
    return roles, exclusions, apparatus_root, apparatus_task


def _validated_allowlists(
    *,
    lock: Mapping[str, object],
    block: Mapping[str, object],
    roles: Collection[str],
    selected_final_files: Mapping[str, Sequence[str]],
    permitted_check_evidence: Mapping[str, Sequence[str]],
) -> tuple[
    dict[str, tuple[PurePosixPath, ...]],
    dict[str, tuple[PurePosixPath, ...]],
]:
    expected = set(roles)
    if (
        set(selected_final_files) != expected
        or set(permitted_check_evidence) != expected
    ):
        _fail("evaluation_product_binding_invalid", "allowlist keys")
    review = lock.get("review")
    if not isinstance(review, Mapping):
        _fail("evaluation_product_binding_invalid", "review allowlists")
    locked_selected_value = review.get("selected_final_files")
    locked_check_names_value = review.get("permitted_check_evidence_names")
    if (
        not isinstance(locked_selected_value, list)
        or not isinstance(locked_check_names_value, list)
    ):
        _fail("evaluation_product_binding_invalid", "review allowlists")
    locked_selected = tuple(
        _relative_path(value) for value in locked_selected_value
    )
    block_id = _safe_component(block.get("block_id"))
    executions = {
        execution["treatment_id"]: execution
        for execution in block["treatment_executions"]  # type: ignore[index]
    }
    selected: dict[str, tuple[PurePosixPath, ...]] = {}
    checks: dict[str, tuple[PurePosixPath, ...]] = {}
    for role in roles:
        opaque_arm_label = _safe_component(
            executions[role].get("opaque_arm_label")
        )
        locked_checks = tuple(
            _relative_path(f"{block_id}/{opaque_arm_label}/{_safe_component(name)}")
            for name in locked_check_names_value
        )
        selected[role] = tuple(
            _relative_path(value) for value in selected_final_files[role]
        )
        checks[role] = tuple(
            _relative_path(value) for value in permitted_check_evidence[role]
        )
        if (
            selected[role] != locked_selected
            or checks[role] != locked_checks
        ):
            _fail("evaluation_product_binding_invalid", f"{role} allowlists")
    return selected, checks


def build_blind_packages(
    *,
    lock: Mapping[str, object],
    block: Mapping[str, object],
    product_roots: Mapping[str, Path],
    base_root: Path,
    task_path: str,
    selected_final_files: Mapping[str, Sequence[str]],
    permitted_check_evidence: Mapping[str, Sequence[str]],
    output_root: Path,
    controller_root: Path,
) -> dict[str, Path]:
    """Build one deterministic blinded live package from explicit roots."""

    base, products, output, controller = _validate_roots(
        base_root=base_root,
        product_roots=product_roots,
        output_root=output_root,
        controller_root=controller_root,
    )
    locked_evidence_root = lock.get("evidence_root")
    if (
        not isinstance(locked_evidence_root, str)
        or controller
        != _canonical_root(Path(locked_evidence_root), must_exist=True)
    ):
        _fail("evaluation_product_binding_invalid", "evidence root")
    roles, exclusions, task_root, task = _validate_live_lineage(
        lock=lock,
        block=block,
        base_root=base,
        product_roots=products,
        output_root=output,
        controller_root=controller,
        task_path=task_path,
    )
    package_id = _safe_component(block.get("block_id"))
    selected, checks = _validated_allowlists(
        lock=lock,
        block=block,
        roles=roles,
        selected_final_files=selected_final_files,
        permitted_check_evidence=permitted_check_evidence,
    )
    seed = _lock_seed(lock)
    ordered_roles = _role_order(seed, package_id, roles)
    labels = _opaque_labels(seed, package_id, len(roles))
    label_roles = dict(zip(labels, ordered_roles, strict=True))
    output.mkdir(parents=True, exist_ok=False)
    controller.mkdir(parents=True, exist_ok=True)
    package_root = _build_package(
        package_id=package_id,
        candidate_labels=labels,
        roots_by_label={
            label: products[role] for label, role in label_roles.items()
        },
        base_root=base,
        task_root=task_root,
        task_path=task,
        selected_by_label={
            label: selected[role] for label, role in label_roles.items()
        },
        checks_by_label={
            label: checks[role] for label, role in label_roles.items()
        },
        product_exclusions=exclusions,
        controller_root=controller,
        output_root=output,
    )
    _reject_identity_leak(package_root, roles)
    mapping = {
        "packages": {
            package_id: {
                "labels": label_roles,
                "manifest_digest": _sha256_bytes(
                    (package_root / "manifest.json").read_bytes()
                ),
            }
        }
    }
    _publish_new_payload(
        root=controller,
        relative=_relative_path(f"label-maps/{package_id}.json"),
        data=canonical_json_bytes(mapping),
    )
    return {package_id: package_root}
