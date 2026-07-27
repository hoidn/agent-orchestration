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
    _execution_roles,
    _fail,
    _lock_seed,
    _opaque_labels,
    _reject_identity_leak,
    _relative_path,
    _role_order,
    _safe_component,
    _sha256_bytes,
    _source_file,
    _validate_roots,
    _write_payload,
)


def _validate_live_lineage(
    *,
    lock: Mapping[str, object],
    block: Mapping[str, object],
    base_root: Path,
    product_roots: Mapping[str, Path],
    task_path: str,
) -> tuple[tuple[str, ...], tuple[PurePosixPath, ...]]:
    try:
        validate_record(lock)
        validate_record(block)
    except PilotContractError as exc:
        raise EvaluationError("evaluation_lock_or_block_invalid", str(exc)) from exc
    if block.get("attempt_class") != "LIVE" or block.get("status") != "VALID":
        _fail("evaluation_block_invalid", "requires VALID LIVE block")
    _safe_component(block.get("block_id"))
    lock_digest = canonical_sha256(lock)
    if block.get("pilot_lock_digest") != lock_digest:
        _fail("evaluation_lock_digest_mismatch")
    sequence_index = block.get("sequence_index")
    live_attempt_ids = lock.get("live_attempt_ids")
    if (
        isinstance(sequence_index, bool)
        or not isinstance(sequence_index, int)
        or not isinstance(live_attempt_ids, list)
        or sequence_index >= len(live_attempt_ids)
        or block.get("block_id") != live_attempt_ids[sequence_index]
    ):
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
    task_relative = _relative_path(task_path)
    _task_source, task_bytes, _task_mode = _source_file(base_root, task_relative)
    task_lock = lock.get("task")
    if (
        not isinstance(task_lock, Mapping)
        or task_lock.get("brief_digest") != _sha256_bytes(task_bytes)
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
    return roles, exclusions


def _validated_allowlists(
    *,
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
    selected: dict[str, tuple[PurePosixPath, ...]] = {}
    checks: dict[str, tuple[PurePosixPath, ...]] = {}
    for role in roles:
        selected[role] = tuple(
            _relative_path(value) for value in selected_final_files[role]
        )
        checks[role] = tuple(
            _relative_path(value) for value in permitted_check_evidence[role]
        )
        if (
            not selected[role]
            or len(set(selected[role])) != len(selected[role])
            or len(set(checks[role])) != len(checks[role])
        ):
            _fail("evaluation_product_binding_invalid", f"{role} final files")
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
    roles, exclusions = _validate_live_lineage(
        lock=lock,
        block=block,
        base_root=base,
        product_roots=products,
        task_path=task_path,
    )
    package_id = _safe_component(block.get("block_id"))
    task = _relative_path(task_path)
    selected, checks = _validated_allowlists(
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
    _write_payload(
        controller / "label-map.json",
        canonical_json_bytes(mapping),
    )
    return {package_id: package_root}
