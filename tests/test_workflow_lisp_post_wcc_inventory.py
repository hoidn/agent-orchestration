from __future__ import annotations

import importlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "LISP-FRONTEND-AUTONOMOUS-DRAIN"
    / "post_wcc_current_state_inventory.json"
)
MARKDOWN_VIEW_PATH = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "LISP-FRONTEND-AUTONOMOUS-DRAIN"
    / "design-gaps"
    / "post_wcc_reconciliation_index.md"
)
SELECTOR_PROMPT_PATH = (
    REPO_ROOT
    / "workflows"
    / "library"
    / "prompts"
    / "lisp_frontend_selector"
    / "select_next_design_delta_work.md"
)
DONE_REVIEW_PROMPT_PATH = (
    REPO_ROOT
    / "workflows"
    / "library"
    / "prompts"
    / "lisp_frontend_selector"
    / "review_done_design_delta.md"
)

MANDATORY_TRANCHE_3A_SURFACE_IDS = {
    "workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr",
    "workflow-lisp-phase-family-boundary-rehabilitation",
}


def _inventory_module():
    return importlib.import_module("orchestrator.workflow_lisp.post_wcc_inventory")


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _checked_in_payload() -> dict[str, object]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _surface(payload: dict[str, object], surface_id: str) -> dict[str, object]:
    return next(
        surface
        for surface in payload["surfaces"]
        if surface["surface_id"] == surface_id
    )


def _mutated_inventory_path(
    tmp_path: Path,
    *,
    transform,
) -> Path:
    payload = deepcopy(_checked_in_payload())
    transform(payload)
    return _write_json(tmp_path / "post_wcc_inventory.json", payload)


def _codes(validation) -> set[str]:
    return {issue.code for issue in validation.issues}


def _run_inventory_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "workflow-lisp-post-wcc-inventory",
            *args,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_checked_in_inventory_loads_and_validates() -> None:
    inventory_module = _inventory_module()
    inventory = inventory_module.load_post_wcc_inventory(INVENTORY_PATH)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)
    surfaces = {surface.surface_id: surface for surface in inventory.surfaces}

    assert inventory.schema_version == inventory_module.POST_WCC_INVENTORY_SCHEMA_VERSION
    assert surfaces[
        "workflow-lisp-parent-backlog-drain-composition-parity"
    ].status == "completed_post_wcc"
    assert surfaces[
        "workflow-lisp-yaml-primary-promotion-gate"
    ].status == "completed_post_wcc"
    assert validation.overall_pass is True
    assert validation.issues == ()


def test_missing_explicit_tranche_3a_coverage_emits_stable_code(tmp_path: Path) -> None:
    inventory_module = _inventory_module()
    inventory_path = _mutated_inventory_path(
        tmp_path,
        transform=lambda payload: payload.__setitem__(
            "surfaces",
            [
                surface
                for surface in payload["surfaces"]
                if surface["surface_id"] not in MANDATORY_TRANCHE_3A_SURFACE_IDS
            ],
        ),
    )

    inventory = inventory_module.load_post_wcc_inventory(inventory_path)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)

    assert "post_wcc_inventory_schema_invalid" in _codes(validation)


def test_unknown_status_emits_stable_code(tmp_path: Path) -> None:
    inventory_module = _inventory_module()
    inventory_path = _mutated_inventory_path(
        tmp_path,
        transform=lambda payload: _surface(
            payload, "workflow-lisp-private-exec-context-bridge-generalization"
        ).__setitem__("status", "unknown_status"),
    )

    inventory = inventory_module.load_post_wcc_inventory(inventory_path)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)

    assert "post_wcc_inventory_unknown_status" in _codes(validation)


def test_missing_evidence_path_emits_stable_code(tmp_path: Path) -> None:
    inventory_module = _inventory_module()

    def _transform(payload: dict[str, object]) -> None:
        surface = _surface(payload, "workflow-lisp-parent-backlog-drain-composition-parity")
        surface["evidence"][0]["path"] = "state/does-not-exist.json"

    inventory_path = _mutated_inventory_path(tmp_path, transform=_transform)
    inventory = inventory_module.load_post_wcc_inventory(inventory_path)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)

    assert "post_wcc_inventory_evidence_missing" in _codes(validation)


def test_completed_row_requires_completed_gap_history(tmp_path: Path) -> None:
    inventory_module = _inventory_module()

    def _transform(payload: dict[str, object]) -> None:
        _surface(payload, "workflow-lisp-private-exec-context-bridge-generalization")[
            "owning_design_gap_id"
        ] = "workflow-lisp-gap-that-does-not-exist"

    inventory_path = _mutated_inventory_path(tmp_path, transform=_transform)
    inventory = inventory_module.load_post_wcc_inventory(inventory_path)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)

    assert "post_wcc_inventory_completed_gap_missing_from_run_state" in _codes(validation)


def test_implemented_by_wcc_row_requires_completed_gap_history(tmp_path: Path) -> None:
    inventory_module = _inventory_module()

    def _transform(payload: dict[str, object]) -> None:
        _surface(payload, "workflow-lisp-parent-callable-implementation-phase-composition")[
            "owning_design_gap_id"
        ] = "workflow-lisp-gap-that-does-not-exist"

    inventory_path = _mutated_inventory_path(tmp_path, transform=_transform)
    inventory = inventory_module.load_post_wcc_inventory(inventory_path)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)

    assert "post_wcc_inventory_completed_gap_missing_from_run_state" in _codes(validation)


def test_remaining_row_contradicted_by_repo_evidence_emits_status_conflict(tmp_path: Path) -> None:
    inventory_module = _inventory_module()
    inventory_path = _mutated_inventory_path(
        tmp_path,
        transform=lambda payload: _surface(
            payload, "workflow-lisp-parent-backlog-drain-composition-parity"
        ).__setitem__("status", "remaining_post_wcc"),
    )

    inventory = inventory_module.load_post_wcc_inventory(inventory_path)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)

    assert "post_wcc_inventory_status_conflict" in _codes(validation)


def test_promotion_gate_rows_cannot_block_done(tmp_path: Path) -> None:
    inventory_module = _inventory_module()

    def _transform(payload: dict[str, object]) -> None:
        promotion_gate = _surface(payload, "workflow-lisp-yaml-primary-promotion-gate")
        promotion_gate["status"] = "deferred_promotion_gate"
        promotion_gate["blocks_done"] = True

    inventory_path = _mutated_inventory_path(tmp_path, transform=_transform)
    inventory = inventory_module.load_post_wcc_inventory(inventory_path)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)

    assert "post_wcc_inventory_promotion_gate_misclassified" in _codes(validation)


def test_markdown_guard_drift_emits_stable_code(tmp_path: Path) -> None:
    inventory_module = _inventory_module()
    inventory_path = _mutated_inventory_path(
        tmp_path,
        transform=lambda payload: _surface(
            payload, "workflow-lisp-certified-adapter-declaration-surface"
        ).__setitem__("status", "remaining_post_wcc"),
    )

    inventory = inventory_module.load_post_wcc_inventory(inventory_path)
    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)

    assert MARKDOWN_VIEW_PATH.is_file()
    assert "post_wcc_inventory_markdown_view_drift" in _codes(validation)


def test_newer_progress_ledger_event_overrides_older_status_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    inventory_module = _inventory_module()
    inventory = inventory_module.load_post_wcc_inventory(INVENTORY_PATH)
    base_evidence = inventory_module.collect_inventory_evidence(REPO_ROOT)
    markdown_view_path = tmp_path / "post_wcc_reconciliation_index.md"
    markdown_view_path.write_text(
        inventory_module.render_post_wcc_inventory_markdown_view(inventory),
        encoding="utf-8",
    )
    evidence = inventory_module.InventoryEvidenceBundle(
        route_registry=base_evidence.route_registry,
        parent_parity_report=base_evidence.parent_parity_report,
        run_state=base_evidence.run_state,
        progress_ledger={
            "ledger_version": 1,
            "events": [
                {
                    "surface_id": "workflow-lisp-parent-backlog-drain-composition-parity",
                    "status": "remaining_post_wcc",
                    "recorded_at": "2026-06-11T00:00:00Z",
                }
            ],
        },
        markdown_view_path=markdown_view_path,
    )

    monkeypatch.setattr(inventory_module, "collect_inventory_evidence", lambda repo_root: evidence)

    validation = inventory_module.validate_post_wcc_inventory(inventory, REPO_ROOT)
    done_validation = inventory_module.validate_selector_done_preconditions(
        inventory,
        evidence,
    )

    assert "post_wcc_inventory_status_conflict" in _codes(validation)
    assert "post_wcc_inventory_done_blocked_by_remaining_surface" in _codes(done_validation)


def test_prompt_assets_reference_inventory_authority_path() -> None:
    authority_path = (
        "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json"
    )

    assert authority_path in SELECTOR_PROMPT_PATH.read_text(encoding="utf-8")
    assert authority_path in DONE_REVIEW_PROMPT_PATH.read_text(encoding="utf-8")


def test_done_preconditions_follow_remaining_surface_state(tmp_path: Path) -> None:
    inventory_module = _inventory_module()
    checked_in_inventory = inventory_module.load_post_wcc_inventory(INVENTORY_PATH)
    evidence = inventory_module.collect_inventory_evidence(REPO_ROOT)

    approved = inventory_module.validate_selector_done_preconditions(
        checked_in_inventory,
        evidence,
    )

    assert approved.overall_pass is True
    assert "post_wcc_inventory_done_blocked_by_remaining_surface" not in _codes(approved)

    blocked_inventory_path = _mutated_inventory_path(
        tmp_path,
        transform=lambda payload: _surface(
            payload, "workflow-lisp-phase-family-boundary-rehabilitation"
        ).__setitem__("status", "remaining_post_wcc"),
    )
    blocked_inventory = inventory_module.load_post_wcc_inventory(blocked_inventory_path)
    blocked = inventory_module.validate_selector_done_preconditions(
        blocked_inventory,
        evidence,
    )

    assert "post_wcc_inventory_done_blocked_by_remaining_surface" in _codes(blocked)


def test_cli_inventory_check_succeeds_for_checked_in_inventory() -> None:
    result = _run_inventory_cli(
        "--inventory",
        INVENTORY_PATH.relative_to(REPO_ROOT).as_posix(),
        "--check",
    )

    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["overall_pass"] is True
    assert summary["done_allowed"] is True
    assert summary["blocking_remaining_surfaces"] == 0
    assert summary["missing_evidence_issues"] == 0
    assert summary["status_conflict_issues"] == 0


def test_cli_inventory_check_reports_drift_or_missing_evidence(tmp_path: Path) -> None:
    inventory_path = _mutated_inventory_path(
        tmp_path,
        transform=lambda payload: _surface(
            payload, "workflow-lisp-parent-backlog-drain-composition-parity"
        )["evidence"][0].__setitem__("path", "state/does-not-exist.json"),
    )

    result = _run_inventory_cli(
        "--inventory",
        inventory_path.relative_to(REPO_ROOT).as_posix()
        if inventory_path.is_relative_to(REPO_ROOT)
        else str(inventory_path),
        "--check",
    )

    assert result.returncode == 1
    summary = json.loads(result.stdout)
    assert summary["overall_pass"] is False
    assert summary["missing_evidence_issues"] >= 1


def test_cli_inventory_check_returns_2_for_invalid_json(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid_inventory.json"
    invalid_path.write_text("{", encoding="utf-8")

    result = _run_inventory_cli("--inventory", str(invalid_path), "--check")

    assert result.returncode == 2
    assert result.stdout == ""
