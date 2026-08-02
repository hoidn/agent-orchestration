"""Closed trial identity, blinding, and effect-scope contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import TYPE_CHECKING

from orchestrator.workflow.run_ref.contracts import canonical_sha256

if TYPE_CHECKING:
    from .config import TrialRuntimeRequest


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OPAQUE_LABEL_RE = re.compile(r"opaque-[0-9a-f]{64}\Z")
_SAFE_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class TrialCellKey:
    """One authored arm/repetition cell in canonical domain order."""

    arm_id: str
    rep: int

    def __post_init__(self) -> None:
        if not isinstance(self.arm_id, str) or not self.arm_id or "\0" in self.arm_id:
            raise ValueError("trial cell arm_id must be non-empty NUL-free text")
        if type(self.rep) is not int or self.rep < 1:
            raise ValueError("trial cell rep must be a positive integer")

    @property
    def record(self) -> dict[str, object]:
        return {"arm_id": self.arm_id, "rep": self.rep}


@dataclass(frozen=True, slots=True)
class TrialOpaqueLabelBinding:
    cell: TrialCellKey
    opaque_label: str

    def __post_init__(self) -> None:
        if type(self.cell) is not TrialCellKey:
            raise TypeError("opaque-label binding cell must be TrialCellKey")
        if not isinstance(self.opaque_label, str) or _OPAQUE_LABEL_RE.fullmatch(
            self.opaque_label
        ) is None:
            raise ValueError("trial opaque label is invalid")

    @property
    def record(self) -> dict[str, object]:
        return {"cell": self.cell.record, "opaque_label": self.opaque_label}


@dataclass(frozen=True, slots=True)
class SealedTrialOpaqueLabelMap:
    """Exact sealed cell-to-opaque-label bijection retained by the ledger."""

    bindings: tuple[TrialOpaqueLabelBinding, ...]
    digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple) or not self.bindings or any(
            type(binding) is not TrialOpaqueLabelBinding for binding in self.bindings
        ):
            raise ValueError("trial opaque-label map must contain exact bindings")
        cells = tuple(binding.cell for binding in self.bindings)
        labels = tuple(binding.opaque_label for binding in self.bindings)
        if len(set(cells)) != len(cells) or len(set(labels)) != len(labels):
            raise ValueError("trial opaque-label map is not a bijection")
        if self.digest != canonical_sha256(self.record):
            raise ValueError("trial opaque-label map digest is invalid")

    @property
    def record(self) -> dict[str, object]:
        return {
            "schema_version": "trial_opaque_label_map.v1",
            "bindings": [binding.record for binding in self.bindings],
        }


def build_sealed_opaque_label_map(
    cell_domain: tuple[TrialCellKey, ...],
    *,
    salt: bytes | None = None,
    labels: tuple[str, ...] | None = None,
) -> SealedTrialOpaqueLabelMap:
    """Build an exact opaque-label bijection without entering trial identity."""

    if not isinstance(cell_domain, tuple) or not cell_domain or any(
        type(cell) is not TrialCellKey for cell in cell_domain
    ):
        raise ValueError("trial cell domain must be a non-empty exact tuple")
    if len(set(cell_domain)) != len(cell_domain):
        raise ValueError("trial cell domain is not unique")
    if (salt is None) == (labels is None):
        raise ValueError("provide exactly one opaque-label source")
    if labels is None:
        if not isinstance(salt, bytes) or len(salt) < 32:
            raise ValueError("trial opaque-label salt must contain at least 32 bytes")
        labels = tuple(
            "opaque-"
            + hashlib.sha256(
                salt
                + b"\0"
                + str(index).encode("ascii")
                + b"\0"
                + canonical_sha256(cell.record).encode("ascii")
            ).hexdigest()
            for index, cell in enumerate(cell_domain)
        )
    if not isinstance(labels, tuple) or len(labels) != len(cell_domain):
        raise ValueError("trial opaque-label map is not a bijection")
    bindings = tuple(
        TrialOpaqueLabelBinding(cell=cell, opaque_label=label)
        for cell, label in zip(cell_domain, labels, strict=True)
    )
    record = {
        "schema_version": "trial_opaque_label_map.v1",
        "bindings": [binding.record for binding in bindings],
    }
    return SealedTrialOpaqueLabelMap(
        bindings=bindings,
        digest=canonical_sha256(record),
    )


@dataclass(frozen=True, slots=True)
class TrialCellEffectScope:
    """Path-neutral identity plus exact roots for one trial-owned E1 effect."""

    cell: TrialCellKey
    cell_index: int
    trial_root: Path
    effect_instance_digest: str
    effect_instance_root: Path
    run_ref_root: Path
    workspace_namespace: Path
    ledger_path: Path
    run_ref_step_config_digest: str
    result_contract_digest: str

    def __post_init__(self) -> None:
        if type(self.cell) is not TrialCellKey:
            raise TypeError("trial effect scope cell must be TrialCellKey")
        if type(self.cell_index) is not int or self.cell_index < 1:
            raise ValueError("trial effect scope index must be positive")
        for name in (
            "effect_instance_digest",
            "run_ref_step_config_digest",
            "result_contract_digest",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
                raise ValueError(f"trial effect scope {name} is invalid")
        roots = {
            name: _canonical_absolute(getattr(self, name), field=name)
            for name in (
                "trial_root",
                "effect_instance_root",
                "run_ref_root",
                "workspace_namespace",
                "ledger_path",
            )
        }
        if not _strict_child(roots["effect_instance_root"], roots["trial_root"]):
            raise ValueError("trial E1 effect root escapes trial root")
        if roots["ledger_path"] != roots["effect_instance_root"] / "run-ref-attempts.jsonl":
            raise ValueError("trial E1 ledger path disagrees with effect root")
        if roots["workspace_namespace"] != (
            roots["run_ref_root"]
            / "effect-instances"
            / self.effect_instance_digest.removeprefix("sha256:")
        ):
            raise ValueError("trial E1 workspace namespace disagrees with identity")
        for name, value in roots.items():
            object.__setattr__(self, name, value)

    @property
    def record(self) -> dict[str, object]:
        return {
            "cell": self.cell.record,
            "cell_index": self.cell_index,
            "effect_instance_digest": self.effect_instance_digest,
            "effect_instance_root": self.effect_instance_root.as_posix(),
            "run_ref_root": self.run_ref_root.as_posix(),
            "workspace_namespace": self.workspace_namespace.as_posix(),
            "ledger_path": self.ledger_path.as_posix(),
            "run_ref_step_config_digest": self.run_ref_step_config_digest,
            "result_contract_digest": self.result_contract_digest,
        }


def _canonical_absolute(value: Path, *, field: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or "\0" in path.as_posix():
        raise ValueError(f"{field} must be absolute")
    resolved = path.resolve(strict=False)
    if resolved != path:
        raise ValueError(f"{field} must be canonical and alias-free")
    return path


def _strict_child(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return relative != Path(".")


def _safe_segment(value: str, *, prefix: str) -> str:
    if _SAFE_SEGMENT_RE.fullmatch(value) is not None:
        return value
    return prefix + "-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def derive_trial_cell_effect_scopes(
    *,
    request: TrialRuntimeRequest,
    parent_run_root: Path,
    run_ref_root: Path,
) -> tuple[TrialCellEffectScope, ...]:
    """Derive strict, mutually disjoint E1 roots without hashing path bytes."""

    from .config import TrialRuntimeRequest

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be an exact TrialRuntimeRequest")
    parent = _canonical_absolute(parent_run_root, field="parent_run_root")
    external = _canonical_absolute(run_ref_root, field="run_ref_root")
    frame_digest = canonical_sha256(
        {
            "schema_version": "trial_frame_scope.v1",
            "execution_frame_id": request.visit.execution_frame_id,
            "call_frame_id": request.visit.call_frame_id,
        }
    ).removeprefix("sha256:")
    trial_root = (
        parent
        / "trials"
        / f"frame-{frame_digest[:32]}"
        / _safe_segment(request.visit.step_id, prefix="step")
        / f"visit-{request.visit.visit_count}"
    )
    if (
        trial_root == external
        or _strict_child(trial_root, external)
        or _strict_child(external, trial_root)
    ):
        raise ValueError(
            "trial ledger root and external workspace root overlap"
        )
    scopes: list[TrialCellEffectScope] = []
    arm_by_id = {arm.arm_id: arm for arm in request.step_config.arms}
    for index, cell in enumerate(request.cell_domain, start=1):
        effect_digest = canonical_sha256(
            {
                "schema_version": "effect_instance_identity.v1",
                "owner_request_digest": request.digest,
                "ordinal_domain": "authored_arm_outer_rep_inner",
                "cell": cell.record,
            }
        )
        segment = f"cell-{index:04d}"
        effect_root = trial_root / segment / "e1"
        workspace_namespace = (
            external
            / "effect-instances"
            / effect_digest.removeprefix("sha256:")
        )
        arm = arm_by_id[cell.arm_id]
        scopes.append(
            TrialCellEffectScope(
                cell=cell,
                cell_index=index,
                trial_root=trial_root,
                effect_instance_digest=effect_digest,
                effect_instance_root=effect_root,
                run_ref_root=external,
                workspace_namespace=workspace_namespace,
                ledger_path=effect_root / "run-ref-attempts.jsonl",
                run_ref_step_config_digest=arm.run_ref.step_config_digest,
                result_contract_digest=arm.run_ref.run_ref.result_digest,
            )
        )
    effect_roots = {scope.effect_instance_root for scope in scopes}
    workspace_namespaces = {scope.workspace_namespace for scope in scopes}
    if len(effect_roots) != len(scopes) or len(workspace_namespaces) != len(scopes):
        raise ValueError("trial cell E1 roots are not mutually disjoint")
    return tuple(scopes)


__all__ = [
    "SealedTrialOpaqueLabelMap",
    "TrialCellEffectScope",
    "TrialCellKey",
    "TrialOpaqueLabelBinding",
    "build_sealed_opaque_label_map",
    "derive_trial_cell_effect_scopes",
]
