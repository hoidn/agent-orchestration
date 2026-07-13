"""Workflow Lisp post-WCC current-state inventory validation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orchestrator.workflow_lisp.route_readiness import (
    RouteReadinessRegistry,
    load_route_readiness_registry,
    registry_entry_for_path,
)


POST_WCC_INVENTORY_SCHEMA_VERSION = "workflow_lisp_post_wcc_current_state_inventory.v1"
DEFAULT_INVENTORY_RELPATH = (
    "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json"
)
DEFAULT_MARKDOWN_VIEW_RELPATH = (
    "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md"
)
DEFAULT_ROUTE_READINESS_RELPATH = "docs/workflow_lisp_route_readiness_registry.json"
DEFAULT_PARENT_PARITY_REPORT_RELPATH = "artifacts/work/review-parity-check/design_delta_parent_drain.json"
DEFAULT_RUN_STATE_RELPATH = "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json"
DEFAULT_PROGRESS_LEDGER_RELPATH = "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json"

STATUS_VALUES = frozenset(
    {
        "superseded_by_wcc",
        "implemented_by_wcc",
        "completed_post_wcc",
        "remaining_post_wcc",
        "deferred_promotion_gate",
    }
)

MANDATORY_SURFACE_IDS = frozenset(
    {
        "workflow-lisp-imported-child-returned-variant-work-item-prerequisite",
        "workflow-lisp-nested-structured-control-helper-hoisting-retirement",
        "workflow-lisp-parent-callable-implementation-phase-composition",
        "workflow-lisp-plan-phase-parent-callable-route",
        "workflow-lisp-wcc-ifexpr-work-item-route",
        "workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr",
        "workflow-lisp-phase-family-boundary-rehabilitation",
        "workflow-lisp-private-exec-context-bridge-generalization",
        "workflow-lisp-selector-bundle-typed-projection",
        "workflow-lisp-certified-adapter-declaration-surface",
        "workflow-lisp-resource-transition-ownership",
        "workflow-lisp-parent-backlog-drain-composition-parity",
        "workflow-lisp-route-readiness-classification-registry",
        "workflow-lisp-yaml-primary-promotion-gate",
    }
)
MANDATORY_TRANCHE_3A_SURFACE_IDS = frozenset(
    {
        "workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr",
        "workflow-lisp-phase-family-boundary-rehabilitation",
    }
)
ROW_ISSUE_CODES_THAT_NEGATE_COMPLETION = frozenset(
    {
        "post_wcc_inventory_evidence_missing",
        "post_wcc_inventory_registry_mismatch",
        "post_wcc_inventory_parity_mismatch",
        "post_wcc_inventory_completed_gap_missing_from_run_state",
    }
)


class PostWccInventoryError(ValueError):
    """Raised for unreadable or structurally malformed inventory input."""


@dataclass(frozen=True)
class InventoryRouteIdentity:
    lowering_route: str
    lowering_schema_version: int


@dataclass(frozen=True)
class InventoryEvidenceRef:
    kind: str
    path: str
    surface_id: str | None = None


@dataclass(frozen=True)
class PostWccSurface:
    surface_id: str
    display_name: str
    surface_kind: str
    target_sections: tuple[str, ...]
    status: str
    blocks_done: bool
    selector_guidance: str
    evidence: tuple[InventoryEvidenceRef, ...]
    owning_design_gap_id: str | None = None
    route_identity: InventoryRouteIdentity | None = None
    raw: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class PostWccInventory:
    schema_version: str
    updated: str
    target_design_path: str
    surfaces: tuple[PostWccSurface, ...]
    path: Path | None = None


@dataclass(frozen=True)
class InventoryIssue:
    code: str
    message: str
    path: str | None = None
    surface_id: str | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"code": self.code, "message": self.message}
        if self.path is not None:
            payload["path"] = self.path
        if self.surface_id is not None:
            payload["surface_id"] = self.surface_id
        if self.field is not None:
            payload["field"] = self.field
        return payload


@dataclass(frozen=True)
class InventoryEvidenceBundle:
    route_registry: RouteReadinessRegistry
    parent_parity_report: Mapping[str, Any]
    run_state: Mapping[str, Any]
    progress_ledger: Mapping[str, Any]
    markdown_view_path: Path


@dataclass(frozen=True)
class InventoryValidationResult:
    inventory: PostWccInventory
    issues: tuple[InventoryIssue, ...]

    @property
    def overall_pass(self) -> bool:
        return not self.issues


def load_post_wcc_inventory(path: Path) -> PostWccInventory:
    """Load and parse a checked-in post-WCC current-state inventory."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PostWccInventoryError(f"invalid JSON in post-WCC inventory `{path}`: {exc}") from exc
    except OSError as exc:
        raise PostWccInventoryError(f"unable to read post-WCC inventory `{path}`: {exc}") from exc

    if not isinstance(payload, Mapping):
        raise PostWccInventoryError("post-WCC inventory must be a JSON object")
    if payload.get("schema_version") != POST_WCC_INVENTORY_SCHEMA_VERSION:
        raise PostWccInventoryError(
            f"expected schema_version {POST_WCC_INVENTORY_SCHEMA_VERSION}"
        )

    updated = payload.get("updated")
    target_design_path = payload.get("target_design_path")
    raw_surfaces = payload.get("surfaces")
    if not isinstance(updated, str) or not updated:
        raise PostWccInventoryError("post-WCC inventory must declare non-empty `updated`")
    if not isinstance(target_design_path, str) or not target_design_path:
        raise PostWccInventoryError("post-WCC inventory must declare non-empty `target_design_path`")
    if not isinstance(raw_surfaces, list):
        raise PostWccInventoryError("post-WCC inventory must declare `surfaces` as an array")

    surfaces = tuple(_parse_surface(raw_surface, index=index) for index, raw_surface in enumerate(raw_surfaces))
    return PostWccInventory(
        schema_version=POST_WCC_INVENTORY_SCHEMA_VERSION,
        updated=updated,
        target_design_path=target_design_path,
        surfaces=surfaces,
        path=path.resolve(),
    )


def collect_inventory_evidence(repo_root: Path) -> InventoryEvidenceBundle:
    """Collect authoritative evidence inputs used by the post-WCC inventory."""

    repo_root = repo_root.resolve()
    return InventoryEvidenceBundle(
        route_registry=load_route_readiness_registry(repo_root / DEFAULT_ROUTE_READINESS_RELPATH),
        parent_parity_report=_load_json_mapping(repo_root / DEFAULT_PARENT_PARITY_REPORT_RELPATH),
        run_state=_load_json_mapping(repo_root / DEFAULT_RUN_STATE_RELPATH),
        progress_ledger=_load_json_mapping(repo_root / DEFAULT_PROGRESS_LEDGER_RELPATH),
        markdown_view_path=repo_root / DEFAULT_MARKDOWN_VIEW_RELPATH,
    )


def validate_post_wcc_inventory(
    inventory: PostWccInventory,
    repo_root: Path,
) -> InventoryValidationResult:
    """Validate inventory content against the current checkout."""

    repo_root = repo_root.resolve()
    evidence = collect_inventory_evidence(repo_root)
    issues = _validate_inventory_against_evidence(inventory, evidence, repo_root)

    try:
        checked_in_markdown = evidence.markdown_view_path.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(
            InventoryIssue(
                code="post_wcc_inventory_evidence_missing",
                message=f"unable to read selector-guard markdown view `{evidence.markdown_view_path}`: {exc}",
                path=_repo_relative(evidence.markdown_view_path, repo_root),
            )
        )
    else:
        rendered = render_post_wcc_inventory_markdown_view(inventory)
        if _normalize_text(rendered) != _normalize_text(checked_in_markdown):
            issues.append(
                InventoryIssue(
                    code="post_wcc_inventory_markdown_view_drift",
                    message="selector-guard markdown view does not match the checked-in inventory authority",
                    path=_repo_relative(evidence.markdown_view_path, repo_root),
                )
            )

    return InventoryValidationResult(inventory=inventory, issues=tuple(issues))

def render_post_wcc_inventory_markdown_view(inventory: PostWccInventory) -> str:
    """Render the selector-facing markdown guard view from the inventory."""

    lines = [
        "# Post-WCC Reconciliation Index",
        "",
        "Status: selector guard view",
        f"Updated: {inventory.updated}",
        f"Target design: `{inventory.target_design_path}`",
        f"Inventory authority: `{DEFAULT_INVENTORY_RELPATH}`",
        "",
        "Compiler substrate: WCC is the default route for new Workflow Lisp compiles in",
        "the migrated subset. New post-foundation compiler-lane gaps must extend WCC or",
        "provide explicit legacy/schema-1 retirement evidence. They must not add new",
        "nested-control behavior to legacy lowerers.",
        "",
        "This file is a selector-facing markdown view over",
        f"`{DEFAULT_INVENTORY_RELPATH}`. `remaining_post_wcc` blocks `DONE`;",
        "`deferred_promotion_gate` does not.",
        "",
        "| Surface | Current inventory status | Required action before drain may select it |",
        "| --- | --- | --- |",
    ]
    for surface in inventory.surfaces:
        lines.append(
            f"| {surface.display_name} | `{surface.status}` | {surface.selector_guidance} |"
        )

    lines.extend(
        [
            "",
            "Selector rule:",
            "",
            "- Do not select surfaces marked `superseded_by_wcc`.",
            "- Do not select `implemented_by_wcc` or `completed_post_wcc` surfaces as fresh work unless the selected item is explicitly regression or retirement evidence.",
            "- Treat `deferred_promotion_gate` as non-blocking for `DONE`; it governs YAML-primary replacement only.",
            "- Prefer any future `remaining_post_wcc` gap only when it is the highest-authority unresolved target-design obligation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _validate_inventory_against_evidence(
    inventory: PostWccInventory,
    evidence: InventoryEvidenceBundle,
    repo_root: Path,
) -> list[InventoryIssue]:
    issues: list[InventoryIssue] = []
    completed_design_gaps = {
        item
        for item in evidence.run_state.get("completed_design_gaps", ())
        if isinstance(item, str)
    }
    ledger_status_overrides = _collect_progress_ledger_status_overrides(
        inventory,
        evidence.progress_ledger,
    )

    if inventory.schema_version != POST_WCC_INVENTORY_SCHEMA_VERSION:
        issues.append(
            InventoryIssue(
                code="post_wcc_inventory_schema_invalid",
                message=f"schema_version must be {POST_WCC_INVENTORY_SCHEMA_VERSION}",
                field="schema_version",
            )
        )

    seen_surface_ids: set[str] = set()
    inventory_surface_ids = {surface.surface_id for surface in inventory.surfaces}
    missing_required_surface_ids = MANDATORY_SURFACE_IDS - inventory_surface_ids
    if missing_required_surface_ids:
        issues.append(
            InventoryIssue(
                code="post_wcc_inventory_schema_invalid",
                message=(
                    "inventory is missing required tracked surfaces: "
                    + ", ".join(sorted(missing_required_surface_ids))
                ),
                field="surfaces",
            )
        )

    if not MANDATORY_TRANCHE_3A_SURFACE_IDS.issubset(inventory_surface_ids):
        issues.append(
            InventoryIssue(
                code="post_wcc_inventory_schema_invalid",
                message=(
                    "inventory must explicitly track the remaining Tranche 3A "
                    "plan/work-item phase-family obligation"
                ),
                field="surfaces",
            )
        )

    for surface in inventory.surfaces:
        resolved_status = ledger_status_overrides.get(surface.surface_id, surface.status)
        if surface.surface_id in seen_surface_ids:
            issues.append(
                _issue(
                    "post_wcc_inventory_schema_invalid",
                    surface,
                    f"duplicate surface_id `{surface.surface_id}`",
                    field="surface_id",
                )
            )
        else:
            seen_surface_ids.add(surface.surface_id)

        if resolved_status != surface.status:
            issues.append(
                _issue(
                    "post_wcc_inventory_status_conflict",
                    surface,
                    "row status is stale relative to a newer progress-ledger event",
                    field="status",
                )
            )

        if surface.status not in STATUS_VALUES:
            issues.append(
                _issue(
                    "post_wcc_inventory_unknown_status",
                    surface,
                    f"unknown status `{surface.status}`",
                    field="status",
                )
            )

        if surface.status == "deferred_promotion_gate" and surface.blocks_done:
            issues.append(
                _issue(
                    "post_wcc_inventory_promotion_gate_misclassified",
                    surface,
                    "promotion-only gate must not block DONE",
                    field="blocks_done",
                )
            )

        row_issues_before = len(issues)
        for evidence_ref in surface.evidence:
            evidence_path = repo_root / evidence_ref.path
            if not evidence_path.exists():
                issues.append(
                    _issue(
                        "post_wcc_inventory_evidence_missing",
                        surface,
                        f"referenced evidence path `{evidence_ref.path}` does not exist",
                        path=evidence_ref.path,
                    )
                )
                continue
            if evidence_ref.kind == "route_readiness_registry":
                issues.extend(
                    _validate_route_registry_ref(
                        surface=surface,
                        evidence_ref=evidence_ref,
                        registry=evidence.route_registry,
                    )
                )
            elif evidence_ref.kind == "migration_parity_report":
                issues.extend(
                    _validate_parity_ref(
                        surface=surface,
                        parity_report=evidence.parent_parity_report,
                    )
                )

        if surface.status in {"completed_post_wcc", "implemented_by_wcc"}:
            owning_gap_id = surface.owning_design_gap_id
            if not owning_gap_id or owning_gap_id not in completed_design_gaps:
                issues.append(
                    _issue(
                        "post_wcc_inventory_completed_gap_missing_from_run_state",
                        surface,
                        "completed_post_wcc or implemented_by_wcc surface must name a completed owning design gap",
                        field="owning_design_gap_id",
                    )
                )

        if surface.status == "remaining_post_wcc":
            row_issues = issues[row_issues_before:]
            row_issue_codes = {issue.code for issue in row_issues if issue.surface_id == surface.surface_id}
            if (
                resolved_status == "remaining_post_wcc"
                and surface.owning_design_gap_id in completed_design_gaps
                and _surface_has_completion_authority(surface)
                and not row_issue_codes.intersection(ROW_ISSUE_CODES_THAT_NEGATE_COMPLETION)
            ):
                issues.append(
                    _issue(
                        "post_wcc_inventory_status_conflict",
                        surface,
                        "row is marked remaining_post_wcc even though current run-state and authority evidence support completion",
                        field="status",
                    )
                )

    return issues


def _collect_progress_ledger_status_overrides(
    inventory: PostWccInventory,
    progress_ledger: Mapping[str, Any],
) -> dict[str, str]:
    events = progress_ledger.get("events")
    inventory_updated_at = _parse_inventory_timestamp(inventory.updated)
    if inventory_updated_at is None or not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        return {}

    surfaces_by_gap_id: dict[str, list[str]] = {}
    for surface in inventory.surfaces:
        if surface.owning_design_gap_id is None:
            continue
        surfaces_by_gap_id.setdefault(surface.owning_design_gap_id, []).append(surface.surface_id)

    overrides: dict[str, tuple[datetime, str]] = {}
    for event in events:
        if not isinstance(event, Mapping):
            continue
        status = event.get("status")
        if status not in STATUS_VALUES:
            continue
        recorded_at = _parse_progress_event_timestamp(event)
        if recorded_at is None or recorded_at <= inventory_updated_at:
            continue

        target_surface_ids: list[str] = []
        surface_id = event.get("surface_id")
        if isinstance(surface_id, str) and surface_id:
            target_surface_ids.append(surface_id)

        design_gap_id = event.get("design_gap_id")
        if isinstance(design_gap_id, str) and design_gap_id:
            target_surface_ids.extend(surfaces_by_gap_id.get(design_gap_id, ()))

        for target_surface_id in target_surface_ids:
            current = overrides.get(target_surface_id)
            if current is None or recorded_at > current[0]:
                overrides[target_surface_id] = (recorded_at, status)

    return {surface_id: status for surface_id, (_, status) in overrides.items()}


def _parse_inventory_timestamp(value: str) -> datetime | None:
    return _parse_iso_timestamp(value)


def _parse_progress_event_timestamp(event: Mapping[str, Any]) -> datetime | None:
    for field in ("recorded_at", "timestamp", "updated_at", "occurred_at", "created_at"):
        value = event.get(field)
        if isinstance(value, str) and value:
            parsed = _parse_iso_timestamp(value)
            if parsed is not None:
                return parsed
    return None


def _parse_iso_timestamp(value: str) -> datetime | None:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _resolved_surface_statuses(
    inventory: PostWccInventory,
    evidence: InventoryEvidenceBundle,
) -> dict[str, str]:
    overrides = _collect_progress_ledger_status_overrides(inventory, evidence.progress_ledger)
    return {
        surface.surface_id: overrides.get(surface.surface_id, surface.status)
        for surface in inventory.surfaces
    }


def validate_selector_done_preconditions(
    inventory: PostWccInventory,
    evidence: InventoryEvidenceBundle,
) -> InventoryValidationResult:
    """Validate whether the reconciled inventory permits selector `DONE`."""

    issues: list[InventoryIssue] = []
    resolved_statuses = _resolved_surface_statuses(inventory, evidence)
    for surface in inventory.surfaces:
        resolved_status = resolved_statuses[surface.surface_id]
        if resolved_status == "deferred_promotion_gate" and surface.blocks_done:
            issues.append(
                _issue(
                    "post_wcc_inventory_promotion_gate_misclassified",
                    surface,
                    "promotion-only gate must not block DONE",
                    field="blocks_done",
                )
            )
        if resolved_status == "remaining_post_wcc":
            issues.append(
                _issue(
                    "post_wcc_inventory_done_blocked_by_remaining_surface",
                    surface,
                    f"surface `{surface.surface_id}` is still marked remaining_post_wcc",
                    field="status",
                )
            )
    return InventoryValidationResult(inventory=inventory, issues=tuple(issues))


def _validate_route_registry_ref(
    *,
    surface: PostWccSurface,
    evidence_ref: InventoryEvidenceRef,
    registry: RouteReadinessRegistry,
) -> list[InventoryIssue]:
    issues: list[InventoryIssue] = []
    registry_surface_id = evidence_ref.surface_id
    if registry_surface_id is None:
        issues.append(
            _issue(
                "post_wcc_inventory_registry_mismatch",
                surface,
                "route_readiness_registry evidence must declare a registry surface_id",
                field="evidence.surface_id",
            )
        )
        return issues

    entry = next(
        (candidate for candidate in registry.surfaces if candidate.surface_id == registry_surface_id),
        None,
    )
    if entry is None:
        issues.append(
            _issue(
                "post_wcc_inventory_registry_mismatch",
                surface,
                f"registry surface `{registry_surface_id}` is missing",
                field="evidence.surface_id",
            )
        )
        return issues

    if surface.route_identity is not None:
        if entry.lowering_route != surface.route_identity.lowering_route:
            issues.append(
                _issue(
                    "post_wcc_inventory_registry_mismatch",
                    surface,
                    "registry lowering route does not match inventory route identity",
                    field="route_identity.lowering_route",
                )
            )
        if entry.lowering_schema_version != surface.route_identity.lowering_schema_version:
            issues.append(
                _issue(
                    "post_wcc_inventory_registry_mismatch",
                    surface,
                    "registry lowering schema version does not match inventory route identity",
                    field="route_identity.lowering_schema_version",
                )
            )
    if surface.surface_id == "workflow-lisp-parent-backlog-drain-composition-parity":
        if entry.readiness_label != "promotion_eligible":
            issues.append(
                _issue(
                    "post_wcc_inventory_registry_mismatch",
                    surface,
                    "parent backlog-drain parity requires promotion_eligible registry evidence",
                    field="readiness_label",
                )
            )
    return issues


def _validate_parity_ref(
    *,
    surface: PostWccSurface,
    parity_report: Mapping[str, Any],
) -> list[InventoryIssue]:
    issues: list[InventoryIssue] = []
    route_identity = parity_report.get("route_identity")
    promotion = parity_report.get("promotion_eligibility")
    evidence = parity_report.get("evidence")

    if surface.route_identity is not None:
        if not isinstance(route_identity, Mapping):
            issues.append(
                _issue(
                    "post_wcc_inventory_parity_mismatch",
                    surface,
                    "parity report is missing route_identity",
                    field="route_identity",
                )
            )
            return issues
        if route_identity.get("lowering_route") != surface.route_identity.lowering_route:
            issues.append(
                _issue(
                    "post_wcc_inventory_parity_mismatch",
                    surface,
                    "parity report lowering route does not match inventory route identity",
                    field="route_identity.lowering_route",
                )
            )
        if route_identity.get("lowering_schema_version") != surface.route_identity.lowering_schema_version:
            issues.append(
                _issue(
                    "post_wcc_inventory_parity_mismatch",
                    surface,
                    "parity report lowering schema version does not match inventory route identity",
                    field="route_identity.lowering_schema_version",
                )
            )

    if surface.surface_id == "workflow-lisp-parent-backlog-drain-composition-parity":
        if parity_report.get("non_regressive") is not True:
            issues.append(
                _issue(
                    "post_wcc_inventory_parity_mismatch",
                    surface,
                    "parent backlog-drain parity requires non_regressive=true",
                    field="non_regressive",
                )
            )
    if surface.surface_id == "workflow-lisp-resource-transition-ownership":
        status = None
        if isinstance(evidence, Mapping):
            resource_transition = evidence.get("resource_transition_parity")
            if isinstance(resource_transition, Mapping):
                status = resource_transition.get("status")
        if status != "pass":
            issues.append(
                _issue(
                    "post_wcc_inventory_parity_mismatch",
                    surface,
                    "resource-transition ownership requires passing resource_transition_parity evidence",
                    field="evidence.resource_transition_parity.status",
                )
            )
    if surface.surface_id == "workflow-lisp-yaml-primary-promotion-gate":
        if parity_report.get("non_regressive") is not True:
            issues.append(
                _issue(
                    "post_wcc_inventory_parity_mismatch",
                    surface,
                    "promotion gate requires non_regressive=true family evidence",
                    field="non_regressive",
                )
            )
        eligible = None
        if isinstance(promotion, Mapping):
            eligible = promotion.get("eligible_for_primary_surface")
        if eligible is not True:
            issues.append(
                _issue(
                    "post_wcc_inventory_parity_mismatch",
                    surface,
                    "completed promotion gate requires eligible_for_primary_surface=true",
                    field="promotion_eligibility.eligible_for_primary_surface",
                )
            )
    return issues


def _parse_surface(raw_surface: Mapping[str, Any], *, index: int) -> PostWccSurface:
    if not isinstance(raw_surface, Mapping):
        raise PostWccInventoryError(f"surfaces[{index}] must be a JSON object")

    raw_route_identity = raw_surface.get("route_identity")
    route_identity: InventoryRouteIdentity | None = None
    if raw_route_identity is not None:
        if not isinstance(raw_route_identity, Mapping):
            raise PostWccInventoryError(f"surfaces[{index}].route_identity must be an object")
        route_identity = InventoryRouteIdentity(
            lowering_route=_require_non_empty_string(raw_route_identity, "lowering_route", f"surfaces[{index}].route_identity"),
            lowering_schema_version=_require_int(
                raw_route_identity,
                "lowering_schema_version",
                f"surfaces[{index}].route_identity",
            ),
        )

    raw_evidence = raw_surface.get("evidence")
    if not isinstance(raw_evidence, list):
        raise PostWccInventoryError(f"surfaces[{index}].evidence must be an array")
    evidence = tuple(_parse_evidence_ref(raw_entry, surface_index=index, evidence_index=evidence_index) for evidence_index, raw_entry in enumerate(raw_evidence))

    return PostWccSurface(
        surface_id=_require_non_empty_string(raw_surface, "surface_id", f"surfaces[{index}]"),
        display_name=_require_non_empty_string(raw_surface, "display_name", f"surfaces[{index}]"),
        surface_kind=_require_non_empty_string(raw_surface, "surface_kind", f"surfaces[{index}]"),
        target_sections=tuple(
            _require_string_list(raw_surface, "target_sections", f"surfaces[{index}]")
        ),
        status=_require_non_empty_string(raw_surface, "status", f"surfaces[{index}]"),
        blocks_done=_require_bool(raw_surface, "blocks_done", f"surfaces[{index}]"),
        selector_guidance=_require_non_empty_string(
            raw_surface,
            "selector_guidance",
            f"surfaces[{index}]",
        ),
        evidence=evidence,
        owning_design_gap_id=_optional_string(raw_surface, "owning_design_gap_id"),
        route_identity=route_identity,
        raw=raw_surface,
    )


def _parse_evidence_ref(
    raw_entry: Mapping[str, Any],
    *,
    surface_index: int,
    evidence_index: int,
) -> InventoryEvidenceRef:
    if not isinstance(raw_entry, Mapping):
        raise PostWccInventoryError(
            f"surfaces[{surface_index}].evidence[{evidence_index}] must be a JSON object"
        )
    return InventoryEvidenceRef(
        kind=_require_non_empty_string(
            raw_entry,
            "kind",
            f"surfaces[{surface_index}].evidence[{evidence_index}]",
        ),
        path=_require_non_empty_string(
            raw_entry,
            "path",
            f"surfaces[{surface_index}].evidence[{evidence_index}]",
        ),
        surface_id=_optional_string(raw_entry, "surface_id"),
    )


def _issue(
    code: str,
    surface: PostWccSurface,
    message: str,
    *,
    field: str | None = None,
    path: str | None = None,
) -> InventoryIssue:
    return InventoryIssue(
        code=code,
        message=message,
        path=path,
        surface_id=surface.surface_id,
        field=field,
    )


def _surface_has_completion_authority(surface: PostWccSurface) -> bool:
    return any(
        evidence_ref.kind in {"run_state_completion", "route_readiness_registry", "migration_parity_report"}
        for evidence_ref in surface.evidence
    )


def _load_json_mapping(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise PostWccInventoryError(f"expected JSON object at `{path}`")
    return payload


def _repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _normalize_text(text: str) -> str:
    return text.strip().replace("\r\n", "\n")


def _require_non_empty_string(payload: Mapping[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise PostWccInventoryError(f"{context}.{field} must be a non-empty string")
    return value


def _require_int(payload: Mapping[str, Any], field: str, context: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int):
        raise PostWccInventoryError(f"{context}.{field} must be an integer")
    return value


def _require_bool(payload: Mapping[str, Any], field: str, context: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise PostWccInventoryError(f"{context}.{field} must be a boolean")
    return value


def _require_string_list(payload: Mapping[str, Any], field: str, context: str) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PostWccInventoryError(f"{context}.{field} must be an array of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise PostWccInventoryError(f"{context}.{field}[{index}] must be a non-empty string")
        result.append(item)
    return result


def _optional_string(payload: Mapping[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise PostWccInventoryError(f"{field} must be a non-empty string when provided")
    return value
