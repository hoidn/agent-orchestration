from __future__ import annotations

import hashlib
import io
import json
import os
import re
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import CallExpr, ProcedureCallExpr


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows"
EXAMPLE = WORKFLOWS / "examples" / "design_plan_impl_review_stack_v2_call.orc"
MIGRATION_INPUTS = WORKFLOWS / "examples" / "inputs" / "workflow_lisp_migrations"
BASELINE = REPO_ROOT / "tests" / "baselines" / "procedure_first" / "tracked_plan_phase.json"
PILOT_EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "evidence"
    / "procedure-first-pilot"
    / "tracked-plan-phase"
)
REUSE_INVENTORY = (
    REPO_ROOT / "docs" / "plans" / "2026-07-13-procedure-first-reuse-inventory.json"
)
REUSE_INVENTORY_NARRATIVE = REUSE_INVENTORY.with_suffix(".md")
TRACKED_DESIGN_ELIGIBILITY_STOP = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "evidence"
    / "procedure-first-migration-waves"
    / "tracked-design-phase"
    / "eligibility_stop.json"
)
TRACKED_DESIGN_KNOWN_STORE_SCAN = (
    TRACKED_DESIGN_ELIGIBILITY_STOP.parent / "known_store_scan.json"
)
TRACKED_DESIGN_IDENTITY_WITNESS = (
    TRACKED_DESIGN_ELIGIBILITY_STOP.parent / "identity_delta_witness.json"
)
TRACKED_DESIGN_INPUTS = TRACKED_DESIGN_ELIGIBILITY_STOP.parent / "inputs"
STACK_IMPLEMENTATION_ELIGIBILITY_STOP = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "evidence"
    / "procedure-first-migration-waves"
    / "design-plan-impl-implementation-phase"
    / "eligibility_stop.json"
)
STACK_IMPLEMENTATION_KNOWN_STORE_SCAN = (
    STACK_IMPLEMENTATION_ELIGIBILITY_STOP.parent / "known_store_scan.json"
)
STACK_IMPLEMENTATION_IDENTITY_WITNESS = (
    STACK_IMPLEMENTATION_ELIGIBILITY_STOP.parent / "identity_delta_witness.json"
)
SAME_FILE_EXAMPLE = WORKFLOWS / "examples" / "same_file_record_call_binding.orc"
SAME_FILE_RETIREMENT_DECISION = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "2026-07-16-same-file-build-checks-identity-retirement-plan.md"
)
ROUTE_READINESS_REGISTRY = REPO_ROOT / "docs" / "workflow_lisp_route_readiness_registry.json"
DESIGN_DELTA_DRAIN = (
    WORKFLOWS / "library" / "lisp_frontend_design_delta" / "drain.orc"
)
DESIGN_DELTA_SELECTOR = (
    WORKFLOWS / "library" / "lisp_frontend_design_delta" / "selector.orc"
)
DESIGN_DELTA_ARCHITECT = (
    WORKFLOWS / "library" / "lisp_frontend_design_delta" / "design_gap_architect.orc"
)
DESIGN_DELTA_WORK_ITEM = (
    WORKFLOWS / "library" / "lisp_frontend_design_delta" / "work_item.orc"
)
DESIGN_DELTA_BOOTSTRAP = (
    WORKFLOWS / "library" / "lisp_frontend_design_delta" / "bootstrap.orc"
)
DESIGN_DELTA_PLAN_PHASE = (
    WORKFLOWS / "library" / "lisp_frontend_design_delta" / "plan_phase.orc"
)
DESIGN_DELTA_IMPLEMENTATION_PHASE = (
    WORKFLOWS / "library" / "lisp_frontend_design_delta" / "implementation_phase.orc"
)
DESIGN_DELTA_PROJECTIONS = (
    WORKFLOWS / "library" / "lisp_frontend_design_delta" / "projections.orc"
)
DESIGN_DELTA_FINALIZER_RETENTION_DECISION = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md"
)
DESIGN_DELTA_BLOCKED_RECOVERY_RETENTION_DECISION = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md"
)
DESIGN_DELTA_PHASE_ORCHESTRATION_RETENTION_DECISION = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "2026-07-16-design-delta-phase-orchestration-retention-plan.md"
)
DESIGN_DELTA_COMPLETED_FINALIZATION_RETENTION_DECISION = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md"
)
DESIGN_DELTA_DRAIN_BUILDER_RETENTION_DECISION = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md"
)
DESIGN_DELTA_PUBLIC_ENTRY = "lisp_frontend_design_delta/drain::drain"
_DESIGN_DELTA_RUNTIME_PROJECTION_DIGESTS = {
    "artifacts": "sha256:067f99dcd6c90cc9057b99a2904421cba224d74057f3a7d572e292f314a93ae1",
    "publications": "sha256:05496b544363c9d5b04dcda52e4d73e2b393c0114947efc8956d9c500f238442",
    "resource_transitions": "sha256:b8faac2156c83c89a400c4b8f58c323081871d4982700df810fbe420f62470b8",
    "source_owners": "sha256:f9d41e95505f2577b3ebe84b01974c4273e712a7ae5831bceb60cb1fe0c3b525",
    "checkpoint_ids": "sha256:d0c2ef05da988b3fb6bd93a30f426ee6dec55ed4f905b72ae6efeaa63c12e8a8",
}
MODULE_NAME = "examples/design_plan_impl_review_stack_v2_call"
PUBLIC_ENTRY = f"{MODULE_NAME}::design-plan-impl-review-stack"
TRACKED_PLAN = f"{MODULE_NAME}::tracked-plan-phase"
MODULE_TOKEN = "$module"
MODULE_SLUG = "examples_design_plan_impl_review_stack_v2_call"
PUBLIC_ENTRY_TOKEN = "$module::design-plan-impl-review-stack"
TRACKED_PLAN_TOKEN = "$module::tracked-plan-phase"
_OLD_CALL_NODE_ID = (
    "root.$module_slug_design_plan_impl_review_stack__plan__call_"
    "$module_slug_tracked_plan_phase"
)
_OLD_PRIVATE_NODE_BASE = "root.$module_slug_tracked_plan_phase"
_OLD_PRIVATE_STEP_ID_BASE = "$module_slug_tracked_plan_phase"
_OLD_PRIVATE_PRESENTATION_BASE = TRACKED_PLAN_TOKEN
_NEW_INLINE_STEP_ID_BASE = (
    "$module_slug_design_plan_impl_review_stack__plan__"
    "$module_slug_tracked_plan_phase_1"
)
_NEW_INLINE_NODE_BASE = f"root.{_NEW_INLINE_STEP_ID_BASE}"
_NEW_INLINE_PRESENTATION_BASE = (
    f"{PUBLIC_ENTRY_TOKEN}__plan__$module::tracked-plan-phase_1"
)


def _phase_resume_identities(
    *,
    node_base: str,
    step_id_base: str,
    presentation_base: str,
) -> tuple[tuple[str, str], ...]:
    match_node = f"{node_base}__match_review"
    match_presentation = f"{presentation_base}__match_review"
    rows = [
        (f"{node_base}__draft", f"{presentation_base}__draft"),
        (f"{node_base}__review", f"{presentation_base}__review"),
    ]
    for variant in ("APPROVE", "REVISE"):
        branch_id = f"{step_id_base}__match_review__{variant.lower()}"
        branch_presentation = f"{match_presentation}.{variant}"
        rows.extend(
            (
                (f"{match_node}.{branch_id}", branch_presentation),
                (
                    f"{match_node}.{branch_id}.{branch_id}__projection_anchor",
                    f"{branch_presentation}."
                    f"{presentation_base}__match_review__{variant.lower()}__projection_anchor",
                ),
            )
        )
    rows.append((match_node, match_presentation))
    return tuple(rows)


_RETIRED_OLD_WRITE_ROOT_KEYS = (
    "schema:2/$module::design-plan-impl-review-stack/"
    "$module::design-plan-impl-review-stack__plan__call_$module::tracked-plan-phase/"
    "$module::tracked-plan-phase/__write_root__$module_slug_tracked_plan_phase__draft__result_bundle",
    "schema:2/$module::design-plan-impl-review-stack/"
    "$module::design-plan-impl-review-stack__plan__call_$module::tracked-plan-phase/"
    "$module::tracked-plan-phase/__write_root__$module_slug_tracked_plan_phase__review__result_bundle",
    "schema:2/$module::tracked-plan-phase/"
    "$module::tracked-plan-phase__draft/result_bundle/entry",
    "schema:2/$module::tracked-plan-phase/"
    "$module::tracked-plan-phase__review/result_bundle/entry",
)
_RETIRED_OLD_RESUME_KEYS = (
    ("top_level_node", _OLD_CALL_NODE_ID),
    ("call_boundary", _OLD_CALL_NODE_ID),
    *(
        ("top_level_node", node_id)
        for node_id, _ in _phase_resume_identities(
            node_base=_OLD_PRIVATE_NODE_BASE,
            step_id_base=_OLD_PRIVATE_STEP_ID_BASE,
            presentation_base=_OLD_PRIVATE_PRESENTATION_BASE,
        )
    ),
)
_RETIRED_OLD_LEXICAL_KEYS = (
    "ckpt:8d1ba7e4a3f6208430f45807",
    "ckpt:7315195dfee583a7a632b770",
    "ckpt:18fd9e37be5bddb772f62f7e",
)

_NEW_INLINE_WRITE_ROOT_ROWS = (
    {
        "workflow": PUBLIC_ENTRY_TOKEN,
        "semantic_role": "entrypoint_managed_write_root",
        "stable_identity": f"schema:2/{PUBLIC_ENTRY_TOKEN}/"
        f"{_NEW_INLINE_PRESENTATION_BASE}__draft/result_bundle/entry",
    },
    {
        "workflow": PUBLIC_ENTRY_TOKEN,
        "semantic_role": "entrypoint_managed_write_root",
        "stable_identity": f"schema:2/{PUBLIC_ENTRY_TOKEN}/"
        f"{_NEW_INLINE_PRESENTATION_BASE}__review/result_bundle/entry",
    },
)
_NEW_INLINE_RESUME_IDENTITIES = _phase_resume_identities(
    node_base=_NEW_INLINE_NODE_BASE,
    step_id_base=_NEW_INLINE_STEP_ID_BASE,
    presentation_base=_NEW_INLINE_PRESENTATION_BASE,
)
_NEW_INLINE_RESUME_ROWS = tuple(
    {
        "checkpoint_kind": "top_level_node",
        "node_id": node_id,
        "presentation_key": presentation_key,
        "runtime_step_id_mode": "static",
    }
    for node_id, presentation_key in _NEW_INLINE_RESUME_IDENTITIES
)
_NEW_INLINE_LEXICAL_ROWS = (
    {
        "checkpoint_id": "ckpt:85bebe726bc9eed0e4ee7c63",
        "program_point_id": "pp:e3313af95c03607cfd0291b1",
        "point_kind": "effect_boundary",
        "origin_key": f"{PUBLIC_ENTRY_TOKEN}::step_id::{_NEW_INLINE_STEP_ID_BASE}__draft",
        "presentation_key": f"{_NEW_INLINE_PRESENTATION_BASE}__draft",
        "step_kind": "provider",
        "resume_policy_kind": "reuse_validated_structured_output",
    },
    {
        "checkpoint_id": "ckpt:da29481dd96843184de8136f",
        "program_point_id": "pp:1ce01c3ef1f9efb56700de21",
        "point_kind": "effect_boundary",
        "origin_key": f"{PUBLIC_ENTRY_TOKEN}::step_id::{_NEW_INLINE_STEP_ID_BASE}__review",
        "presentation_key": f"{_NEW_INLINE_PRESENTATION_BASE}__review",
        "step_kind": "provider",
        "resume_policy_kind": "reuse_validated_structured_output",
    },
)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


_YAML_RETIREMENT_QUEUE_COUNTS = {
    "delete_non_survivor_estate": (100, 53),
    "archive_design_delta_yaml_twin": (7, 10),
    "port_verified_iteration": (1, 0),
    "port_generic_run_watchdog": (1, 0),
    "hold_non_progress_step_back": (1, 0),
}
_YAML_RETIREMENT_QUEUE_DISPOSITIONS = {
    "delete_non_survivor_estate": ("delete", "none"),
    "archive_design_delta_yaml_twin": ("archive", "existing_orc_primary"),
    "port_verified_iteration": ("port", "new_orc_port"),
    "port_generic_run_watchdog": ("port", "new_orc_port"),
    "hold_non_progress_step_back": ("delete", "none"),
}
_YAML_RETIREMENT_QUEUE_GATES = {
    "delete_non_survivor_estate": (
        "Task 6: dependency-aware estate deletion batches",
        [],
    ),
    "archive_design_delta_yaml_twin": (
        "Design Delta archive gate and Task 6",
        ["delete_non_survivor_estate"],
    ),
    "port_verified_iteration": (
        "Task 6: verified-iteration YAML deletion gate",
        [],
    ),
    "port_generic_run_watchdog": (
        "Task 6: generic-run-watchdog YAML deletion gate",
        [],
    ),
    "hold_non_progress_step_back": (
        "Task 6: non-progress-step-back YAML deletion gate",
        [],
    ),
}
_YAML_RETIREMENT_REPLACEMENT_PATHS = {
    "delete_non_survivor_estate": [],
    "archive_design_delta_yaml_twin": [
        "workflows/library/lisp_frontend_design_delta/drain.orc"
    ],
    "port_verified_iteration": [
        "workflows/library/verified_iteration_drain/drain.orc"
    ],
    "port_generic_run_watchdog": [
        "workflows/library/generic_run_watchdog/watchdog.orc"
    ],
    "hold_non_progress_step_back": [],
}
_YAML_RETIREMENT_EVIDENCE = {
    "delete_non_survivor_estate": [],
    "archive_design_delta_yaml_twin": [
        {
            "role": "existing_orc_primary",
            "path": "workflows/library/lisp_frontend_design_delta/drain.orc",
        },
        {
            "role": "route_readiness_registry",
            "path": "docs/workflow_lisp_route_readiness_registry.json",
        },
        {
            "role": "historical_parity_report",
            "path": (
                "artifacts/work/review-parity-check/design_delta_parent_drain.json"
            ),
        },
        {
            "role": "drain_migration_plan",
            "path": "docs/plans/2026-07-07-drain-migration-g8-retirement.md",
        },
    ],
    "port_verified_iteration": [
        {
            "role": "promoted_orc_primary",
            "path": "workflows/library/verified_iteration_drain/drain.orc",
        },
        {
            "role": "route_readiness_registry",
            "path": "docs/workflow_lisp_route_readiness_registry.json",
        },
        {
            "role": "family_contract_tests",
            "path": "tests/test_workflow_lisp_verified_iteration_drain.py",
        },
        {
            "role": "task_5_execution_plan",
            "path": (
                "docs/plans/"
                "2026-07-18-yaml-retirement-task-5-two-port-execution-plan.md"
            ),
        },
    ],
    "port_generic_run_watchdog": [
        {
            "role": "promoted_orc_primary",
            "path": "workflows/library/generic_run_watchdog/watchdog.orc",
        },
        {
            "role": "route_readiness_registry",
            "path": "docs/workflow_lisp_route_readiness_registry.json",
        },
        {
            "role": "family_contract_tests",
            "path": "tests/test_workflow_lisp_generic_run_watchdog.py",
        },
        {
            "role": "task_5_execution_plan",
            "path": (
                "docs/plans/"
                "2026-07-18-yaml-retirement-task-5-two-port-execution-plan.md"
            ),
        },
    ],
    "hold_non_progress_step_back": [],
}
_YAML_RETIREMENT_SINGLETONS = {
    "port_verified_iteration": "workflows/examples/verified_iteration_drain.yaml",
    "port_generic_run_watchdog": "workflows/examples/generic_run_watchdog.yaml",
    "hold_non_progress_step_back": (
        "workflows/examples/non_progress_step_back_demo.yaml"
    ),
}
_DESIGN_DELTA_YAML_TWIN_PATHS = {
    "workflows/examples/lisp_frontend_design_delta_drain.yaml",
    "workflows/library/lisp_frontend_design_delta_selector.v214.yaml",
    (
        "workflows/library/"
        "lisp_frontend_design_delta_design_gap_architect.v214.yaml"
    ),
    "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml",
    "workflows/library/lisp_frontend_design_delta_done_review.v214.yaml",
    "workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml",
    (
        "workflows/library/"
        "lisp_frontend_design_delta_implementation_phase.v214.yaml"
    ),
}


def _authored_yaml_estate_paths() -> set[str]:
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for suffix in ("*.yaml", "*.yml")
        for path in WORKFLOWS.rglob(suffix)
    }


def _normalized_string_digest(values: set[str] | list[str]) -> str:
    payload = "".join(f"{value}\n" for value in sorted(values))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _validate_yaml_retirement_handoff(inventory: dict[str, object]) -> None:
    handoff = inventory["yaml_retirement_handoff"]
    assert set(handoff) == {
        "schema_version",
        "captured_at_commit",
        "governing_plan",
        "claim_scope",
        "estate",
        "queues",
        "preserved_workflow_lisp_boundaries",
        "reference_scan_contract",
        "run_consumer_scan_contract",
        "reconciliation",
    }
    assert handoff["schema_version"] == "procedure_first_yaml_retirement_handoff.v1"
    assert handoff["captured_at_commit"] == (
        "56a832bffc11ea4572eae3e6285690a74db7d990"
    )
    assert handoff["governing_plan"] == (
        "docs/plans/2026-07-07-yaml-retirement-program.md"
    )
    assert set(handoff["claim_scope"]) == {
        "authoring_roots",
        "suffixes",
        "downstream_clones_discovered",
    }
    assert handoff["claim_scope"] == {
        "authoring_roots": ["workflows"],
        "suffixes": [".yaml", ".yml"],
        "downstream_clones_discovered": False,
    }

    estate = handoff["estate"]
    assert set(estate) == {"path_count", "normalized_path_sha256", "paths"}
    estate_paths = estate["paths"]
    assert estate_paths == sorted(estate_paths)
    assert len(estate_paths) == len(set(estate_paths)) == 110
    assert _authored_yaml_estate_paths() <= set(estate_paths)
    assert estate["path_count"] == 110
    assert estate["normalized_path_sha256"] == _normalized_string_digest(estate_paths)
    assert "workflows/examples/test_validation.yml" in estate_paths

    queues = handoff["queues"]
    assert [queue["queue_id"] for queue in queues] == list(
        _YAML_RETIREMENT_QUEUE_COUNTS
    )
    queued_paths: list[str] = []
    queued_legacy_ids: list[str] = []
    for queue in queues:
        assert set(queue) == {
            "queue_id",
            "status",
            "disposition",
            "paths",
            "legacy_retire_record_ids",
            "replacement",
            "evidence_paths",
            "archive_destination",
            "stage_6_gate",
            "prerequisite_queue_ids",
            "reference_gate",
            "run_consumer_gate",
        }
        queue_id = queue["queue_id"]
        expected_paths, expected_legacy = _YAML_RETIREMENT_QUEUE_COUNTS[queue_id]
        assert queue["status"] == "pending"
        expected_disposition, expected_replacement = (
            _YAML_RETIREMENT_QUEUE_DISPOSITIONS[queue_id]
        )
        assert queue["disposition"] == expected_disposition
        assert set(queue["replacement"]) == {"kind", "paths", "rationale"}
        assert queue["replacement"]["kind"] == expected_replacement
        assert queue["replacement"]["paths"] == (
            _YAML_RETIREMENT_REPLACEMENT_PATHS[queue_id]
        )
        assert isinstance(queue["replacement"]["rationale"], str)
        assert queue["replacement"]["rationale"].strip()
        assert queue["evidence_paths"] == _YAML_RETIREMENT_EVIDENCE[queue_id]
        for evidence in queue["evidence_paths"]:
            assert set(evidence) == {"role", "path"}
            assert (REPO_ROOT / evidence["path"]).is_file()
        expected_gate, expected_prerequisites = _YAML_RETIREMENT_QUEUE_GATES[
            queue_id
        ]
        assert queue["stage_6_gate"] == expected_gate
        assert queue["prerequisite_queue_ids"] == expected_prerequisites
        assert queue["paths"] == sorted(queue["paths"])
        assert queue["legacy_retire_record_ids"] == sorted(
            queue["legacy_retire_record_ids"]
        )
        assert len(queue["paths"]) == expected_paths
        assert len(queue["legacy_retire_record_ids"]) == expected_legacy
        assert queue["archive_destination"] == {
            "kind": "git_history",
            "require_predelete_blob_ids": True,
        }
        assert queue["reference_gate"] == "zero_unclassified_active_references"
        assert queue["run_consumer_gate"] == (
            "zero_supported_matching_nonterminal_consumers"
        )
        queued_paths.extend(queue["paths"])
        queued_legacy_ids.extend(queue["legacy_retire_record_ids"])

    assert len(queued_paths) == len(set(queued_paths)) == 110
    assert set(queued_paths) == set(estate_paths)
    assert set(
        next(
            queue["paths"]
            for queue in queues
            if queue["queue_id"] == "archive_design_delta_yaml_twin"
        )
    ) == _DESIGN_DELTA_YAML_TWIN_PATHS
    for queue_id, path in _YAML_RETIREMENT_SINGLETONS.items():
        queue = next(queue for queue in queues if queue["queue_id"] == queue_id)
        assert queue["paths"] == [path]

    records = inventory["records"]
    legacy_records = {
        row["id"]: row
        for row in records
        if row["record_kind"] == "internal-call"
        and row["classification"] == "legacy-retire"
    }
    assert len(queued_legacy_ids) == len(set(queued_legacy_ids)) == 63
    assert set(queued_legacy_ids) == set(legacy_records)
    for queue in queues:
        queue_paths = set(queue["paths"])
        for record_id in queue["legacy_retire_record_ids"]:
            assert legacy_records[record_id]["source_path"] in queue_paths

    preserved = handoff["preserved_workflow_lisp_boundaries"]
    assert set(preserved) == {
        "disposition",
        "effect_adapter_record_ids",
        "public_entry_record_ids",
    }
    assert preserved["disposition"] == "preserve_workflow_lisp_boundary"
    effect_ids = {
        row["id"]
        for row in records
        if row["record_kind"] == "internal-call"
        and row["classification"] == "effect-adapter"
    }
    public_ids = {
        row["id"] for row in records if row["record_kind"] == "public-entry"
    }
    assert len(effect_ids) == 32
    assert len(public_ids) == 13
    assert preserved["effect_adapter_record_ids"] == sorted(effect_ids)
    assert preserved["public_entry_record_ids"] == sorted(public_ids)
    assert not (set(queued_legacy_ids) & (effect_ids | public_ids))

    reference = handoff["reference_scan_contract"]
    assert set(reference) == {
        "capture_status",
        "scopes",
        "allowed_classifications",
        "deletion_rule",
        "records",
        "normalized_records_sha256",
    }
    assert reference["capture_status"] == "pending_stage_6_scan"
    assert reference["scopes"] == [
        "tracked_repository",
        "working_tree",
        "yaml_import_graph",
    ]
    assert reference["deletion_rule"] == "zero_unclassified_active_references"
    assert set(reference["allowed_classifications"]) == {
        "delete_with_source",
        "reroute_to_orc",
        "temporary_yaml_frontend_test",
        "historical_reference_retained",
    }
    assert reference["records"] == []
    assert reference["normalized_records_sha256"] == _normalized_string_digest([])
    run_scan = handoff["run_consumer_scan_contract"]
    assert set(run_scan) == {
        "capture_status",
        "root_scope_status",
        "matching_scope",
        "missing_or_unreadable_status",
        "gate_fields",
        "non_gating_store_fields",
        "deletion_rule",
        "observed_nonterminal_label_count",
        "observed_nonterminal_label_claim",
    }
    assert run_scan["capture_status"] == (
        "owner_disposition_recorded_in_proportionality_ruling"
    )
    assert run_scan["root_scope_status"] == "owner_bound_complete"
    assert run_scan["missing_or_unreadable_status"] == "nonterminal"
    assert run_scan["gate_fields"] == [
        "matching_terminal_run_count",
        "matching_nonterminal_run_count",
        "matching_call_frame_count",
    ]
    assert run_scan["non_gating_store_fields"] == [
        "store_terminal_run_count",
        "store_nonterminal_run_count",
    ]
    assert run_scan["observed_nonterminal_label_count"] == 84
    assert run_scan["observed_nonterminal_label_claim"] == "hygiene_only"

    assert handoff["reconciliation"] == {
        "estate_path_count": 110,
        "queued_path_count": 110,
        "legacy_retire_record_count": 63,
        "queued_legacy_retire_record_count": 63,
        "effect_adapter_record_count": 32,
        "preserved_effect_adapter_record_count": 32,
        "public_entry_record_count": 13,
        "preserved_public_entry_record_count": 13,
    }


def test_yaml_retirement_handoff_partitions_estate_records_and_boundaries() -> None:
    _validate_yaml_retirement_handoff(_load_json(REUSE_INVENTORY))


def test_yaml_retirement_handoff_names_both_promoted_port_replacements() -> None:
    handoff = _load_json(REUSE_INVENTORY)["yaml_retirement_handoff"]
    queues = {queue["queue_id"]: queue for queue in handoff["queues"]}

    expected_replacements = {
        "port_verified_iteration": (
            "workflows/library/verified_iteration_drain/drain.orc",
            "tests/test_workflow_lisp_verified_iteration_drain.py",
        ),
        "port_generic_run_watchdog": (
            "workflows/library/generic_run_watchdog/watchdog.orc",
            "tests/test_workflow_lisp_generic_run_watchdog.py",
        ),
    }
    for queue_id, (orc_path, contract_tests) in expected_replacements.items():
        queue = queues[queue_id]
        assert queue["replacement"]["kind"] == "new_orc_port"
        assert queue["replacement"]["paths"] == [orc_path]
        evidence_by_role = {
            row["role"]: row["path"] for row in queue["evidence_paths"]
        }
        assert evidence_by_role == {
            "promoted_orc_primary": orc_path,
            "route_readiness_registry": (
                "docs/workflow_lisp_route_readiness_registry.json"
            ),
            "family_contract_tests": contract_tests,
            "task_5_execution_plan": (
                "docs/plans/"
                "2026-07-18-yaml-retirement-task-5-two-port-execution-plan.md"
            ),
        }


def test_non_progress_step_back_frozen_handoff_survives_live_retirement() -> None:
    handoff = _load_json(REUSE_INVENTORY)["yaml_retirement_handoff"]
    queue = next(
        queue
        for queue in handoff["queues"]
        if queue["queue_id"] == "hold_non_progress_step_back"
    )
    rationale = " ".join(queue["replacement"]["rationale"].lower().split())

    assert queue["status"] == "pending"
    assert queue["disposition"] == "delete"
    assert queue["replacement"]["kind"] == "none"
    assert queue["replacement"]["paths"] == []
    assert "2026-07-23t16:06:20-07:00" in rationale
    assert "delete" in rationale
    assert "not port" in rationale
    assert queue["reference_gate"] == "zero_unclassified_active_references"
    assert queue["run_consumer_gate"] == (
        "zero_supported_matching_nonterminal_consumers"
    )
    assert not (
        REPO_ROOT / "workflows/examples/non_progress_step_back_demo.yaml"
    ).exists()


def test_yaml_task_5_handoff_retains_both_retired_source_identities() -> None:
    handoff = _load_json(REUSE_INVENTORY)["yaml_retirement_handoff"]
    queues = {queue["queue_id"]: queue for queue in handoff["queues"]}
    expected_sources = {
        "port_verified_iteration": (
            "workflows/examples/verified_iteration_drain.yaml"
        ),
        "port_generic_run_watchdog": (
            "workflows/examples/generic_run_watchdog.yaml"
        ),
    }

    for queue_id, yaml_path in expected_sources.items():
        queue = queues[queue_id]
        assert queue["status"] == "pending"
        assert queue["paths"] == [yaml_path]
        assert not (REPO_ROOT / yaml_path).exists()
        assert queue["reference_gate"] == "zero_unclassified_active_references"
        assert queue["run_consumer_gate"] == (
            "zero_supported_matching_nonterminal_consumers"
        )
        assert queue["stage_6_gate"].startswith("Task 6:")


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_estate_path",
        "extra_nonexistent_estate_path",
        "duplicate_queue_path",
        "missing_yml_path",
        "missing_legacy_id",
        "duplicate_legacy_id",
        "wrong_queue_legacy_id",
        "retire_effect_adapter",
        "retire_public_entry",
        "missing_public_boundary",
        "sixth_queue",
        "renamed_queue",
        "changed_design_delta_set",
        "wrong_port_replacement",
        "store_total_used_as_gate",
        "missing_status_treated_terminal",
        "reference_gate_weakened",
        "extra_handoff_key",
        "wrong_governing_plan",
        "wrong_queue_gate",
        "wrong_queue_prerequisite",
        "missing_evidence_path",
        "wrong_reference_scope",
        "wrong_reference_status",
        "wrong_reference_digest",
    ),
)
def test_yaml_retirement_handoff_rejects_missing_extra_or_crossed_membership(
    mutation: str,
) -> None:
    inventory = _load_json(REUSE_INVENTORY)
    handoff = inventory["yaml_retirement_handoff"]
    queues = handoff["queues"]
    delete_queue = queues[0]
    design_delta_queue = queues[1]
    if mutation == "missing_estate_path":
        handoff["estate"]["paths"].pop()
    elif mutation == "extra_nonexistent_estate_path":
        handoff["estate"]["paths"].append("workflows/examples/absent.yaml")
    elif mutation == "duplicate_queue_path":
        queues[2]["paths"] = [delete_queue["paths"][0]]
    elif mutation == "missing_yml_path":
        handoff["estate"]["paths"].remove(
            "workflows/examples/test_validation.yml"
        )
    elif mutation == "missing_legacy_id":
        delete_queue["legacy_retire_record_ids"].pop()
    elif mutation == "duplicate_legacy_id":
        delete_queue["legacy_retire_record_ids"].append(
            delete_queue["legacy_retire_record_ids"][0]
        )
    elif mutation == "wrong_queue_legacy_id":
        record_id = delete_queue["legacy_retire_record_ids"].pop()
        design_delta_queue["legacy_retire_record_ids"].append(record_id)
        design_delta_queue["legacy_retire_record_ids"].sort()
    elif mutation == "retire_effect_adapter":
        delete_queue["legacy_retire_record_ids"][0] = handoff[
            "preserved_workflow_lisp_boundaries"
        ]["effect_adapter_record_ids"][0]
        delete_queue["legacy_retire_record_ids"].sort()
    elif mutation == "retire_public_entry":
        delete_queue["legacy_retire_record_ids"][0] = handoff[
            "preserved_workflow_lisp_boundaries"
        ]["public_entry_record_ids"][0]
        delete_queue["legacy_retire_record_ids"].sort()
    elif mutation == "missing_public_boundary":
        handoff["preserved_workflow_lisp_boundaries"][
            "public_entry_record_ids"
        ].pop()
    elif mutation == "sixth_queue":
        queues.append(deepcopy(queues[-1]))
        queues[-1]["queue_id"] = "unexpected_queue"
    elif mutation == "renamed_queue":
        queues[0]["queue_id"] = "renamed_delete_queue"
    elif mutation == "changed_design_delta_set":
        design_delta_queue["paths"][0] = delete_queue["paths"][0]
        design_delta_queue["paths"].sort()
    elif mutation == "wrong_port_replacement":
        queues[2]["replacement"]["kind"] = "none"
    elif mutation == "store_total_used_as_gate":
        handoff["run_consumer_scan_contract"]["gate_fields"][1] = (
            "store_nonterminal_run_count"
        )
    elif mutation == "missing_status_treated_terminal":
        handoff["run_consumer_scan_contract"]["missing_or_unreadable_status"] = (
            "terminal"
        )
    elif mutation == "reference_gate_weakened":
        handoff["reference_scan_contract"]["deletion_rule"] = (
            "classified_references_may_remain_active"
        )
    elif mutation == "extra_handoff_key":
        handoff["unexpected"] = True
    elif mutation == "wrong_governing_plan":
        handoff["governing_plan"] = "docs/plans/wrong.md"
    elif mutation == "wrong_queue_gate":
        delete_queue["stage_6_gate"] = "Task 5"
    elif mutation == "wrong_queue_prerequisite":
        design_delta_queue["prerequisite_queue_ids"] = []
    elif mutation == "missing_evidence_path":
        design_delta_queue["evidence_paths"].pop()
    elif mutation == "wrong_reference_scope":
        handoff["reference_scan_contract"]["scopes"].pop()
    elif mutation == "wrong_reference_status":
        handoff["reference_scan_contract"]["capture_status"] = "complete"
    elif mutation == "wrong_reference_digest":
        handoff["reference_scan_contract"]["normalized_records_sha256"] = (
            "sha256:" + "0" * 64
        )

    with pytest.raises((AssertionError, KeyError)):
        _validate_yaml_retirement_handoff(inventory)


_YAML_REFERENCE_CLASSIFICATIONS = {
    "delete_with_source",
    "reroute_to_orc",
    "temporary_yaml_frontend_test",
    "historical_reference_retained",
}
_YAML_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}


def _yaml_retirement_reference_gate_passes(
    records: list[dict[str, object]],
) -> bool:
    return all(
        not record.get("active", False)
        or record.get("classification") in _YAML_REFERENCE_CLASSIFICATIONS
        for record in records
    )


def _yaml_retirement_run_gate_passes(runs: list[dict[str, object]]) -> bool:
    for run in runs:
        if not run.get("supported", False):
            continue
        matches = bool(run.get("matches_top_level", False)) or bool(
            run.get("matching_nested_call_frame_count", 0)
        )
        if not matches:
            continue
        if run.get("status") not in _YAML_TERMINAL_RUN_STATUSES:
            return False
    return True


@pytest.mark.parametrize(
    ("references", "runs", "expected"),
    (
        ([], [], True),
        ([], [{"supported": True, "matches_top_level": True, "status": "running"}], False),
        (
            [],
            [
                {
                    "supported": True,
                    "matches_top_level": False,
                    "matching_nested_call_frame_count": 1,
                    "status": "suspended",
                }
            ],
            False,
        ),
        ([], [{"supported": True, "matches_top_level": True}], False),
        (
            [],
            [{"supported": True, "matches_top_level": False, "status": "running"}],
            True,
        ),
        (
            [],
            [{"supported": True, "matches_top_level": True, "status": "completed"}],
            True,
        ),
        ([{"active": True}], [], False),
        (
            [
                {
                    "active": True,
                    "classification": "historical_reference_retained",
                }
            ],
            [],
            True,
        ),
    ),
    ids=(
        "empty-positive-control",
        "matching-top-level-nonterminal-rejects",
        "matching-nested-nonterminal-rejects-containing-run",
        "missing-status-rejects",
        "unrelated-store-nonterminal-passes",
        "matching-terminal-passes",
        "unclassified-active-reference-rejects",
        "classified-historical-reference-passes",
    ),
)
def test_yaml_retirement_pending_gate_semantics(
    references: list[dict[str, object]],
    runs: list[dict[str, object]],
    expected: bool,
) -> None:
    assert (
        _yaml_retirement_reference_gate_passes(references)
        and _yaml_retirement_run_gate_passes(runs)
    ) is expected


def test_yaml_estate_triage_projects_every_handoff_path_and_queue() -> None:
    inventory = _load_json(REUSE_INVENTORY)
    handoff = inventory["yaml_retirement_handoff"]
    triage = (
        REPO_ROOT / "docs" / "workflow_yaml_estate_triage.md"
    ).read_text(encoding="utf-8")
    projected_rows: list[list[str]] = []
    for line in triage.splitlines():
        if not line.startswith("| workflows/"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) == 8
        projected_rows.append(cells)

    projected_paths = [cells[0] for cells in projected_rows]
    assert len(projected_paths) == len(set(projected_paths)) == 110
    rows = {cells[0]: cells for cells in projected_rows}

    assert set(rows) == set(handoff["estate"]["paths"])
    assert "workflows/examples/test_validation.yml" in rows
    queues = {
        queue["queue_id"]: queue for queue in handoff["queues"]
    }
    for queue_id, queue in queues.items():
        for path in queue["paths"]:
            cells = rows[path]
            assert cells[1] == queue_id
            assert cells[2] == queue["disposition"]
            expected_replacement_or_rationale = (
                queue["replacement"]["paths"][0]
                if queue["replacement"]["paths"]
                else queue["replacement"]["rationale"]
            )
            if path == "workflows/examples/non_progress_step_back_demo.yaml":
                assert "no `.orc` port was built" in cells[3]
                assert "frozen historical queue identity" in cells[3]
            else:
                assert cells[3] == expected_replacement_or_rationale
            assert cells[4] == str(
                sum(
                    record_id.startswith(f"internal-call:{path}:")
                    for record_id in queue["legacy_retire_record_ids"]
                )
            )
            assert cells[5] == "git_history"
            if path == "workflows/examples/non_progress_step_back_demo.yaml":
                assert cells[6] == "complete"
                assert cells[7] == "retired"
            else:
                assert cells[6] == "pending"
                assert cells[7] == "reference + supported-run-consumer"

    assert "YAML Workflow Estate Triage (DRAFT)" not in triage
    assert handoff["estate"]["normalized_path_sha256"] in triage
    assert "all five queues are drained" in triage.lower()
    assert "authored yaml/yml estate is empty" in triage.lower()
    assert "task 7 is current and eligible but not implemented" in triage.lower()


def test_procedure_first_reuse_inventory_rebaselines_active_and_history_counts() -> None:
    inventory = _load_json(REUSE_INVENTORY)
    narrative = REUSE_INVENTORY.with_suffix(".md").read_text(encoding="utf-8")

    assert inventory["schema_version"] == "procedure_first_reuse_inventory.v2"
    assert inventory["source_commit"] == "db9889937a895d67810dee1ea0b1b53552d30eca"
    records = inventory["records"]
    history = inventory["history"]
    assert len(records) == 108
    assert len(history) == 1
    assert len({record["id"] for record in records}) == len(records)
    assert not ({record["id"] for record in records} & {row["id"] for row in history})

    internal_records = [
        record for record in records if record["record_kind"] == "internal-call"
    ]
    public_records = [
        record for record in records if record["record_kind"] == "public-entry"
    ]
    assert len(internal_records) == 95
    assert len(public_records) == 13
    assert inventory["counts"]["separate_public_entries"] == len(public_records)
    assert inventory["counts"]["raw_authored_call_sites"] == {
        "yaml": 67,
        "workflow_lisp": 34,
        "total": 101,
    }
    assert inventory["counts"]["actionable_internal_calls"] == {
        "total": 95,
        "by_classification": {
            "procedure-candidate": 0,
            "effect-adapter": 32,
            "legacy-retire": 63,
            "public-boundary": 0,
        },
    }
    assert inventory["history_counts"] == {
        "total": 1,
        "by_disposition": {
            "migrated": 1,
            "retired": 0,
            "retained-public": 0,
        },
    }
    exclusions_section = narrative.split("## Exclusions", 1)[1].split(
        "## Provenance And Reproduction", 1
    )[0]
    assert {
        int(value) for value in re.findall(r"\bfrom\s+(\d+)\b", exclusions_section)
    } == {inventory["counts"]["raw_authored_call_sites"]["total"]}

    migrated = history[0]
    assert migrated["id"] == (
        "internal-call:workflows/examples/design_plan_impl_review_stack_v2_call.orc:"
        "tracked-plan-phase:1"
    )
    assert migrated["disposition"] == "migrated"
    assert migrated["completed_at_commit"] == (
        "e6a85cb7e9c4499a4c76ee702654b2e9a4c2b328"
    )
    assert migrated["last_active_record"]["id"] == migrated["id"]
    assert migrated["last_active_record"]["source_line"] == 237
    assert migrated["evidence_paths"]


def test_generic_yaml_effect_adapter_inventory_rows_retire_with_families() -> None:
    inventory = _load_json(REUSE_INVENTORY)
    records_by_id = {row["id"]: row for row in inventory["records"]}
    expected_ids = {
        "internal-call:workflows/examples/"
        "dsl_follow_on_plan_impl_review_loop_v2_call.yaml:plan_phase:1",
        "internal-call:workflows/examples/"
        "dsl_follow_on_plan_impl_review_loop_v2_call.yaml:implementation_phase:1",
        "internal-call:workflows/examples/"
        "lisp_frontend_autonomous_drain.yaml:selector:1",
        "internal-call:workflows/examples/"
        "lisp_frontend_autonomous_drain.yaml:work_item:1",
        "internal-call:workflows/examples/"
        "lisp_frontend_autonomous_drain.yaml:design_gap_architect:1",
        "internal-call:workflows/examples/"
        "lisp_frontend_autonomous_drain.yaml:work_item:2",
        "internal-call:workflows/examples/"
        "lisp_frontend_proc_refs_partial_application_drain.yaml:"
        "proc_ref_delta_drain:1",
    }
    audit_path = REUSE_INVENTORY_NARRATIVE.relative_to(REPO_ROOT).as_posix()
    governing_plan = "docs/plans/2026-07-07-yaml-retirement-program.md"
    selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_generic_yaml_effect_adapter_inventory_rows_retire_with_families"
    )
    generic_sources = {
        "workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml",
        "workflows/examples/lisp_frontend_autonomous_drain.yaml",
        "workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml",
    }
    observed_ids = {
        row["id"]
        for row in inventory["records"]
        if row["source_path"] in generic_sources
    }

    assert observed_ids == expected_ids
    for record_id in expected_ids:
        record = records_by_id[record_id]
        assert record["record_kind"] == "internal-call"
        assert record["frontend"] == "yaml"
        assert record["classification"] == "legacy-retire"
        assert record["classification"] not in {
            "procedure-candidate",
            "public-boundary",
        }
        assert record["live_status"] == "retained-compatibility"
        assert "workflow-call" in record["effect_summary"]
        assert record["public_boundary_evidence"] == []
        assert record["named_substrate_gap"] is None
        assert governing_plan in record["evidence_paths"]
        assert audit_path in record["evidence_paths"]
        assert selector in record["evidence_paths"]

    proc_ref_id = (
        "internal-call:workflows/examples/"
        "lisp_frontend_proc_refs_partial_application_drain.yaml:"
        "proc_ref_delta_drain:1"
    )
    assert (
        "artifacts/work/review-parity-check/design_delta_parent_drain.json"
        in records_by_id[proc_ref_id]["evidence_paths"]
    )


def test_neurips_yaml_effect_adapter_inventory_rows_retire_with_finished_campaign() -> None:
    inventory = _load_json(REUSE_INVENTORY)
    records_by_id = {row["id"]: row for row in inventory["records"]}
    expected_records = {
        "internal-call:workflows/examples/"
        "neurips_hybrid_resnet_plan_impl_review.yaml:tranche_selector:1": (
            179,
            "tranche_selector",
            "workflows/library/roadmap_tranche_selector.yaml",
        ),
        "internal-call:workflows/examples/"
        "neurips_hybrid_resnet_plan_impl_review.yaml:plan_phase:1": (
            285,
            "plan_phase",
            "workflows/library/roadmap_seeded_plan_phase.yaml",
        ),
        "internal-call:workflows/examples/"
        "neurips_hybrid_resnet_plan_impl_review.yaml:implementation_phase:1": (
            302,
            "implementation_phase",
            "workflows/library/design_plan_impl_implementation_phase.yaml",
        ),
        "internal-call:workflows/examples/"
        "neurips_steered_backlog_drain.yaml:selector:1": (
            393,
            "selector",
            "workflows/library/neurips_backlog_selector.v214.yaml",
        ),
        "internal-call:workflows/examples/"
        "neurips_steered_backlog_drain.yaml:gap_drafter:1": (
            447,
            "gap_drafter",
            "workflows/library/neurips_backlog_gap_drafter.v214.yaml",
        ),
        "internal-call:workflows/examples/"
        "neurips_steered_backlog_drain.yaml:selected_item:1": (
            564,
            "selected_item",
            "workflows/library/neurips_selected_backlog_item.v214.yaml",
        ),
        "internal-call:workflows/library/"
        "neurips_selected_backlog_item.v214.yaml:roadmap_sync_phase:1": (
            182,
            "roadmap_sync_phase",
            "workflows/library/neurips_backlog_roadmap_sync.v214.yaml",
        ),
        "internal-call:workflows/library/"
        "neurips_selected_backlog_item.v214.yaml:plan_phase:1": (
            322,
            "plan_phase",
            "workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml",
        ),
        "internal-call:workflows/library/"
        "neurips_selected_backlog_item.v214.yaml:implementation_phase:1": (
            501,
            "implementation_phase",
            "workflows/library/neurips_backlog_implementation_phase.v214.yaml",
        ),
        "internal-call:workflows/library/"
        "neurips_selected_backlog_item.yaml:roadmap_sync_phase:1": (
            176,
            "roadmap_sync_phase",
            "workflows/library/neurips_backlog_roadmap_sync_phase.yaml",
        ),
        "internal-call:workflows/library/"
        "neurips_selected_backlog_item.yaml:plan_phase:1": (
            316,
            "plan_phase",
            "workflows/library/neurips_backlog_seeded_plan_phase.yaml",
        ),
        "internal-call:workflows/library/"
        "neurips_selected_backlog_item.yaml:implementation_phase:1": (
            495,
            "implementation_phase",
            "workflows/library/neurips_backlog_implementation_phase.yaml",
        ),
    }
    audit_path = REUSE_INVENTORY_NARRATIVE.relative_to(REPO_ROOT).as_posix()
    governing_plan = "docs/plans/2026-07-07-yaml-retirement-program.md"
    selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_neurips_yaml_effect_adapter_inventory_rows_retire_with_finished_campaign"
    )
    neurips_sources = {
        "workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml",
        "workflows/examples/neurips_steered_backlog_drain.yaml",
        "workflows/library/neurips_selected_backlog_item.v214.yaml",
        "workflows/library/neurips_selected_backlog_item.yaml",
    }
    observed_ids = {
        row["id"]
        for row in inventory["records"]
        if row["source_path"] in neurips_sources
    }

    assert observed_ids == set(expected_records)
    for record_id, (
        source_line,
        call_alias,
        callee_evidence,
    ) in expected_records.items():
        record = records_by_id[record_id]
        assert record["record_kind"] == "internal-call"
        assert record["frontend"] == "yaml"
        assert record["source_line"] == source_line
        assert record["call_alias"] == call_alias
        assert record["callee"] == call_alias
        assert record["resolution"] == "yaml-import-alias"
        assert record["classification"] == "legacy-retire"
        assert record["classification"] not in {
            "procedure-candidate",
            "public-boundary",
        }
        assert record["live_status"] == "retained-compatibility"
        assert record["effect_summary"] == ["workflow-call"]
        assert record["public_boundary_evidence"] == []
        assert record["named_substrate_gap"] is None
        assert {
            record["source_path"],
            callee_evidence,
            governing_plan,
            audit_path,
            selector,
        } <= set(record["evidence_paths"])


def test_design_delta_library_yaml_effect_adapter_rows_retire_with_twins() -> None:
    inventory = _load_json(REUSE_INVENTORY)
    records_by_id = {row["id"]: row for row in inventory["records"]}
    expected_records = {
        "internal-call:workflows/library/"
        "lisp_frontend_design_delta_done_review.v214.yaml:design_gap_architect:1": (
            258,
            "design_gap_architect",
            "workflows/library/"
            "lisp_frontend_design_delta_design_gap_architect.v214.yaml",
            True,
        ),
        "internal-call:workflows/library/"
        "lisp_frontend_design_delta_done_review.v214.yaml:work_item:1": (
            284,
            "work_item",
            "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml",
            True,
        ),
        "internal-call:workflows/library/"
        "lisp_frontend_design_delta_work_item.v214.yaml:plan_phase:1": (
            222,
            "plan_phase",
            "workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml",
            True,
        ),
        "internal-call:workflows/library/"
        "lisp_frontend_design_delta_work_item.v214.yaml:implementation_phase:1": (
            255,
            "implementation_phase",
            "workflows/library/"
            "lisp_frontend_design_delta_implementation_phase.v214.yaml",
            True,
        ),
        "internal-call:workflows/library/"
        "lisp_frontend_work_item.v214.yaml:plan_phase:1": (
            172,
            "plan_phase",
            "workflows/library/lisp_frontend_plan_phase.v214.yaml",
            False,
        ),
        "internal-call:workflows/library/"
        "lisp_frontend_work_item.v214.yaml:implementation_phase:1": (
            199,
            "implementation_phase",
            "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
            False,
        ),
    }
    source_paths = {
        "workflows/library/lisp_frontend_design_delta_done_review.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml",
        "workflows/library/lisp_frontend_work_item.v214.yaml",
    }
    audit_path = REUSE_INVENTORY_NARRATIVE.relative_to(REPO_ROOT).as_posix()
    governing_plan = "docs/plans/2026-07-07-yaml-retirement-program.md"
    selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_library_yaml_effect_adapter_rows_retire_with_twins"
    )
    promoted_evidence = {
        "workflows/library/lisp_frontend_design_delta/drain.orc",
        "docs/workflow_lisp_route_readiness_registry.json",
        "artifacts/work/review-parity-check/design_delta_parent_drain.json",
        "docs/plans/2026-07-07-drain-migration-g8-retirement.md",
    }

    observed_ids = {
        row["id"]
        for row in inventory["records"]
        if row["source_path"] in source_paths
    }
    assert observed_ids == set(expected_records)

    for record_id, (
        source_line,
        call_alias,
        callee_evidence,
        design_delta_twin,
    ) in expected_records.items():
        record = records_by_id[record_id]
        assert record["record_kind"] == "internal-call"
        assert record["frontend"] == "yaml"
        assert record["source_line"] == source_line
        assert record["call_alias"] == call_alias
        assert record["callee"] == call_alias
        assert record["resolution"] == "yaml-import-alias"
        assert record["classification"] == "legacy-retire"
        assert record["classification"] not in {
            "procedure-candidate",
            "public-boundary",
        }
        assert record["live_status"] == "retained-compatibility"
        assert record["effect_summary"] == ["workflow-call"]
        assert record["public_boundary_evidence"] == []
        assert record["named_substrate_gap"] is None
        required_evidence = {
            record["source_path"],
            callee_evidence,
            governing_plan,
            audit_path,
            selector,
        }
        if design_delta_twin:
            required_evidence |= promoted_evidence
        assert required_evidence <= set(record["evidence_paths"])

def _tracked_design_phase_proposed_inline_source(old_source: bytes) -> bytes:
    source = old_source.decode("utf-8")
    replacements = (
        (
            "  (defworkflow tracked-design-phase\n    ((brief_path BriefPath)",
            "  (defproc tracked-design-phase\n    ((brief_path BriefPath)",
        ),
        (
            "    -> DesignPhaseOutput\n    (let* ((draft",
            "    -> DesignPhaseOutput\n"
            "    :effects ((uses-provider providers.design.draft)\n"
            "              (uses-provider providers.design.review))\n"
            "    :lowering inline\n"
            "    (let* ((draft",
        ),
        (
            "             (call tracked-design-phase\n"
            "               :brief_path brief_path\n"
            "               :design_target_path design_target_path\n"
            "               :design_review_report_target_path "
            "design_review_report_target_path))",
            "             (tracked-design-phase\n"
            "               brief_path\n"
            "               design_target_path\n"
            "               design_review_report_target_path))",
        ),
    )
    for old, new in replacements:
        assert source.count(old) == 1
        source = source.replace(old, new)
    return source.encode("utf-8")


def _stack_implementation_phase_proposed_inline_source(old_source: bytes) -> bytes:
    source = old_source.decode("utf-8")
    replacements = (
        (
            "  (defworkflow design-plan-impl-implementation-phase\n"
            "    ((design_path DesignDocPath)",
            "  (defproc design-plan-impl-implementation-phase\n"
            "    ((design_path DesignDocPath)",
        ),
        (
            "    -> ImplementationPhaseOutput\n    (let* ((attempt",
            "    -> ImplementationPhaseOutput\n"
            "    :effects ((uses-provider providers.implementation.execute)\n"
            "              (uses-provider providers.implementation.review))\n"
            "    :lowering inline\n"
            "    (let* ((attempt",
        ),
        (
            "             (call design-plan-impl-implementation-phase\n"
            "               :design_path design.design_path\n"
            "               :plan_path plan.plan_path\n"
            "               :execution_report_target_path execution_report_target_path\n"
            "               :implementation_review_report_target_path "
            "implementation_review_report_target_path))",
            "             (design-plan-impl-implementation-phase\n"
            "               design.design_path\n"
            "               plan.plan_path\n"
            "               execution_report_target_path\n"
            "               implementation_review_report_target_path))",
        ),
    )
    for old, new in replacements:
        assert source.count(old) == 1
        source = source.replace(old, new)
    return source.encode("utf-8")


def _retained_scan_digest(scan: Mapping[str, object]) -> str:
    normalized = {
        key: value
        for key, value in scan.items()
        if key not in {"root", "normalized_scan_digest"}
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def test_tracked_design_phase_identity_retirement_eligibility_stop_replays() -> None:
    evidence = _load_json(TRACKED_DESIGN_ELIGIBILITY_STOP)
    scan = _load_json(TRACKED_DESIGN_KNOWN_STORE_SCAN)
    witness = _load_json(TRACKED_DESIGN_IDENTITY_WITNESS)
    query = evidence["query"]
    store = evidence["known_state_store"]
    assert isinstance(query, dict)
    assert isinstance(store, dict)
    retired_identities = [
        row["identity"] for row in witness["retired_identity_witnesses"]
    ]
    assert isinstance(retired_identities, list)
    canonical_query = json.dumps(
        sorted(retired_identities),
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert "sha256:" + hashlib.sha256(canonical_query).hexdigest() == (
        query["canonical_sorted_query_sha256"]
    )
    assert _sha256_path(TRACKED_DESIGN_IDENTITY_WITNESS) == (
        query["identity_delta_witness_sha256"]
    )

    assert _sha256_path(TRACKED_DESIGN_KNOWN_STORE_SCAN) == (
        store["retained_scan_sha256"]
    )
    assert _retained_scan_digest(scan) == scan["normalized_scan_digest"]
    assert scan["normalized_scan_digest"] == store["normalized_scan_digest"]
    assert {
        key: scan[key]
        for key in store["counts"]
    } == store["counts"]
    assert scan["terminal_run_count"] == 2
    assert scan["nonterminal_run_count"] == 0
    assert scan["consumer_count"] == 26
    assert len(scan["matches"]) == scan["consumer_count"]
    assert len(scan["scanned_files"]) == scan["scanned_file_count"]

    assert scan["retired_identities"] == sorted(retired_identities)
    current_source = (TRACKED_DESIGN_INPUTS / "source.orc").read_bytes()
    proposed_source = _tracked_design_phase_proposed_inline_source(current_source)
    assert witness["source"] == {
        "current_sha256": _sha256_path(TRACKED_DESIGN_INPUTS / "source.orc"),
        "proposed_inline_sha256": "sha256:"
        + hashlib.sha256(proposed_source).hexdigest(),
    }
    assert witness["input_sha256"] == {
        name: _sha256_path(TRACKED_DESIGN_INPUTS / name)
        for name in (
            "design_plan_impl_stack.providers.json",
            "design_plan_impl_stack.prompts.json",
            "design_plan_impl_stack.commands.json",
        )
    }
    assert witness["witness_projection_sha256"] == _projection_sha256(
        witness["retired_identity_witnesses"]
    )
    match_counts: dict[str, int] = {}
    for match in scan["matches"]:
        match_counts[match["identity"]] = match_counts.get(match["identity"], 0) + 1
    for row in witness["retired_identity_witnesses"]:
        identity = row["identity"]
        identity_kind = row["identity_kind"]
        assert row["old_domains"] == [identity_kind]
        assert row["proposed_production_domains"] == []
        assert row["proposed_leak_domains"] == []
        assert row["old_present"] is True
        assert row["proposed_leak_present"] is False
        assert row["store_match_count"] == match_counts[identity]
    assert sorted(match_counts) == sorted(retired_identities)
    assert sum(match_counts.values()) == 26
    assert evidence["source_edit_authorized"] is False
    assert evidence["decision"]["disposition"].startswith(
        "retain tracked-design-phase as a workflow"
    )

    scanned_file_digests = {
        row["path"]: row["sha256"] for row in scan["scanned_files"]
    }
    for binding in store["retained_run_state_bindings"]:
        assert binding["status"] == "completed"
        assert scanned_file_digests[f'{binding["run_id"]}/state.json'] == (
            binding["state_sha256"]
        )


def test_tracked_design_phase_live_source_retains_the_stopped_boundary() -> None:
    source = EXAMPLE.read_text(encoding="utf-8")
    assert source.count("(defworkflow tracked-design-phase") == 1
    assert source.count("(call tracked-design-phase") == 1


def test_stack_implementation_phase_identity_retirement_eligibility_stop_replays() -> None:
    evidence = _load_json(STACK_IMPLEMENTATION_ELIGIBILITY_STOP)
    scan = _load_json(STACK_IMPLEMENTATION_KNOWN_STORE_SCAN)
    witness = _load_json(STACK_IMPLEMENTATION_IDENTITY_WITNESS)
    query = evidence["query"]
    store = evidence["known_state_store"]
    retired_identities = [
        row["identity"] for row in witness["retired_identity_witnesses"]
    ]
    canonical_query = json.dumps(
        sorted(retired_identities),
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert "sha256:" + hashlib.sha256(canonical_query).hexdigest() == (
        query["canonical_sorted_query_sha256"]
    )
    assert _sha256_path(STACK_IMPLEMENTATION_IDENTITY_WITNESS) == (
        query["identity_delta_witness_sha256"]
    )
    assert _sha256_path(STACK_IMPLEMENTATION_KNOWN_STORE_SCAN) == (
        store["retained_scan_sha256"]
    )
    assert _retained_scan_digest(scan) == scan["normalized_scan_digest"]
    assert scan["normalized_scan_digest"] == store["normalized_scan_digest"]
    assert {key: scan[key] for key in store["counts"]} == store["counts"]
    assert scan["terminal_run_count"] == 2
    assert scan["nonterminal_run_count"] == 0
    assert scan["consumer_count"] == 24
    assert len(scan["matches"]) == scan["consumer_count"]
    assert len(scan["scanned_files"]) == scan["scanned_file_count"]
    assert scan["retired_identities"] == sorted(retired_identities)

    retained_source = TRACKED_DESIGN_INPUTS / "source.orc"
    current_source = retained_source.read_bytes()
    proposed_source = _stack_implementation_phase_proposed_inline_source(
        current_source
    )
    assert witness["retained_inputs"]["source"] == {
        "path": retained_source.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_path(retained_source),
    }
    assert witness["source"] == {
        "current_sha256": _sha256_path(retained_source),
        "proposed_inline_sha256": "sha256:"
        + hashlib.sha256(proposed_source).hexdigest(),
    }
    for name in (
        "design_plan_impl_stack.providers.json",
        "design_plan_impl_stack.prompts.json",
        "design_plan_impl_stack.commands.json",
    ):
        retained = TRACKED_DESIGN_INPUTS / name
        assert witness["retained_inputs"][name] == {
            "path": retained.relative_to(REPO_ROOT).as_posix(),
            "sha256": _sha256_path(retained),
        }
    assert witness["witness_projection_sha256"] == _projection_sha256(
        witness["retired_identity_witnesses"]
    )

    match_counts: dict[str, int] = {}
    for match in scan["matches"]:
        match_counts[match["identity"]] = match_counts.get(match["identity"], 0) + 1
    for row in witness["retired_identity_witnesses"]:
        identity = row["identity"]
        assert row["old_domains"] == [row["identity_kind"]]
        assert row["proposed_production_domains"] == []
        assert row["proposed_leak_domains"] == []
        assert row["old_present"] is True
        assert row["proposed_leak_present"] is False
        assert row["store_match_count"] == match_counts[identity]
    assert sorted(match_counts) == sorted(retired_identities)
    assert sum(match_counts.values()) == 24
    assert evidence["source_edit_authorized"] is False
    assert evidence["decision"]["disposition"].startswith(
        "retain design-plan-impl-implementation-phase as a workflow"
    )

    scanned_file_digests = {
        row["path"]: row["sha256"] for row in scan["scanned_files"]
    }
    for binding in store["retained_run_state_bindings"]:
        assert binding["status"] == "completed"
        assert scanned_file_digests[f'{binding["run_id"]}/state.json'] == (
            binding["state_sha256"]
        )


def test_stack_implementation_phase_live_source_retains_the_stopped_boundary() -> None:
    source = EXAMPLE.read_text(encoding="utf-8")
    assert source.count("(defworkflow design-plan-impl-implementation-phase") == 1
    assert source.count("(call design-plan-impl-implementation-phase") == 1


def test_procedure_first_public_boundary_inventory_keeps_exported_wrappers(
    tmp_path: Path,
) -> None:
    inventory = _load_json(REUSE_INVENTORY)
    registry = _load_json(ROUTE_READINESS_REGISTRY)
    active_by_id = {record["id"]: record for record in inventory["records"]}

    drain_id = "public-entry:lisp_frontend_design_delta/drain::drain"
    stack_id = (
        "public-entry:examples/design_plan_impl_review_stack_v2_call::"
        "design-plan-impl-review-stack"
    )
    classifier_id = (
        "public-entry:lisp_frontend_design_delta/work_item::"
        "classify-blocked-implementation-recovery"
    )
    assert {drain_id, stack_id, classifier_id} <= set(active_by_id)
    for record_id in (drain_id, stack_id, classifier_id):
        record = active_by_id[record_id]
        assert record["record_kind"] == "public-entry"
        assert record["classification"] == "public-boundary"
        assert record["public_boundary_evidence"]
        assert record_id not in {
            candidate["id"]
            for candidate in inventory["records"]
            if candidate["classification"] == "procedure-candidate"
        }

    drain_source = DESIGN_DELTA_DRAIN.read_text(encoding="utf-8")
    stack_source = EXAMPLE.read_text(encoding="utf-8")
    assert "(export drain)" in drain_source
    assert re.search(r"\(defworkflow\s+drain\b", drain_source)
    assert "(export design-plan-impl-review-stack)" in stack_source
    assert re.search(r"\(defworkflow\s+design-plan-impl-review-stack\b", stack_source)


    readiness_paths = {row["path"] for row in registry["surfaces"]}
    assert active_by_id[drain_id]["source_path"] in readiness_paths
    assert active_by_id[stack_id]["source_path"] in readiness_paths


def test_same_file_build_checks_stays_workflow_on_live_route() -> None:
    inventory = _load_json(REUSE_INVENTORY)
    registry = _load_json(ROUTE_READINESS_REGISTRY)
    source = SAME_FILE_EXAMPLE.read_text(encoding="utf-8")
    decision = SAME_FILE_RETIREMENT_DECISION.read_text(encoding="utf-8")

    record_id = (
        "internal-call:workflows/examples/same_file_record_call_binding.orc:"
        "build-checks:1"
    )
    record = next(row for row in inventory["records"] if row["id"] == record_id)
    route = next(
        row
        for row in registry["surfaces"]
        if row["path"] == "workflows/examples/same_file_record_call_binding.orc"
    )

    assert record["classification"] == "effect-adapter"
    assert record["live_status"] == "live"
    assert "strict_compatibility" in record["named_substrate_gap"]
    assert route["path"] == "workflows/examples/same_file_record_call_binding.orc"
    assert route["route_label"] == "historical_negative"
    assert "readiness_label" not in route
    assert route["copy_safety"] == "not_current_guidance"
    assert re.search(r"\(defworkflow\s+build-checks\b", source)
    assert "(call build-checks :input input)" in source
    assert re.search(
        r"evaluated against source\s+baseline commit `174b7351`",
        decision,
    )
    assert "Task 2 Step 4 is the next sub-selector" in decision


def test_design_delta_exported_workflows_remain_public_boundaries(
    tmp_path: Path,
) -> None:
    inventory = _load_json(REUSE_INVENTORY)
    records_by_id = {row["id"]: row for row in inventory["records"]}
    internal_prefix = "internal-call:workflows/library/lisp_frontend_design_delta/"
    retained_ids = {
        f"{internal_prefix}stdlib_adapters.orc:select-next-work:1",
        f"{internal_prefix}stdlib_adapters.orc:draft-design-gap-architecture-stdlib:1",
        f"{internal_prefix}stdlib_adapters.orc:validate-design-gap-architecture-stdlib:1",
        f"{internal_prefix}design_gap_architect.orc:project-design-gap-architecture-targets:1",
        f"{internal_prefix}design_gap_architect.orc:project-design-gap-architecture-targets:2",
        f"{internal_prefix}design_gap_architect.orc:project-design-gap-architecture-targets-stdlib:1",
        f"{internal_prefix}design_gap_architect.orc:project-design-gap-architecture-targets-stdlib:2",
    }
    exported_callees = {
        "lisp_frontend_design_delta/selector::select-next-work",
        (
            "lisp_frontend_design_delta/design_gap_architect::"
            "draft-design-gap-architecture-stdlib"
        ),
        (
            "lisp_frontend_design_delta/design_gap_architect::"
            "validate-design-gap-architecture-stdlib"
        ),
        (
            "lisp_frontend_design_delta/design_gap_architect::"
            "project-design-gap-architecture-targets"
        ),
        (
            "lisp_frontend_design_delta/design_gap_architect::"
            "project-design-gap-architecture-targets-stdlib"
        ),
    }

    assert retained_ids <= set(records_by_id)
    for record_id in retained_ids:
        record = records_by_id[record_id]
        assert record["classification"] == "effect-adapter"
        assert "export" in record["named_substrate_gap"].lower()
        assert "strict_compatibility" in record["named_substrate_gap"]

    for callee in exported_callees:
        record = records_by_id[f"public-entry:{callee}"]
        assert record["record_kind"] == "public-entry"
        assert record["classification"] == "public-boundary"
        assert record["callee"] == callee
        assert record["resolution"] == "exported-entry"
        assert "exported workflow" in record["public_boundary_evidence"]
        assert "CLI-selectable entry" in record["public_boundary_evidence"]

    selector_source = DESIGN_DELTA_SELECTOR.read_text(encoding="utf-8")
    architect_source = DESIGN_DELTA_ARCHITECT.read_text(encoding="utf-8")
    assert re.search(r"\(defworkflow\s+select-next-work\b", selector_source)
    for name in (
        "draft-design-gap-architecture-stdlib",
        "validate-design-gap-architecture-stdlib",
        "project-design-gap-architecture-targets",
        "project-design-gap-architecture-targets-stdlib",
    ):
        assert re.search(rf"\(defworkflow\s+{name}\b", architect_source)



def test_design_delta_finalizer_projection_rows_retain_workflow_checkpoints() -> None:
    inventory = _load_json(REUSE_INVENTORY)
    records_by_id = {row["id"]: row for row in inventory["records"]}
    prefix = (
        "internal-call:workflows/library/lisp_frontend_design_delta/"
        "work_item.orc:"
    )
    retained_ids = {
        f"{prefix}project-selected-item-finalizer-approved-plan:1",
        f"{prefix}project-selected-item-finalizer-approved-plan:2",
        f"{prefix}project-selected-item-finalizer-completed-implementation:1",
        f"{prefix}project-selected-item-finalizer-blocked-implementation:1",
    }
    decision_path = DESIGN_DELTA_FINALIZER_RETENTION_DECISION.relative_to(
        REPO_ROOT
    ).as_posix()
    inventory_path = REUSE_INVENTORY_NARRATIVE.relative_to(REPO_ROOT).as_posix()
    selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_finalizer_projection_rows_retain_workflow_checkpoints"
    )
    comparison_selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_finalizer_hypothetical_removes_four_public_wrapper_checkpoints"
    )

    observed_ids = {
        row["id"]
        for row in inventory["records"]
        if row["source_path"] == DESIGN_DELTA_WORK_ITEM.relative_to(REPO_ROOT).as_posix()
        and row["callee"]
        in {
            "project-selected-item-finalizer-approved-plan",
            "project-selected-item-finalizer-completed-implementation",
            "project-selected-item-finalizer-blocked-implementation",
        }
    }
    assert observed_ids == retained_ids
    for record_id in retained_ids:
        record = records_by_id[record_id]
        assert record["record_kind"] == "internal-call"
        assert record["classification"] == "effect-adapter"
        assert "strict_compatibility" in record["named_substrate_gap"]
        assert "checkpoint" in record["named_substrate_gap"].lower()
        assert {
            record["source_path"],
            decision_path,
            inventory_path,
            selector,
            comparison_selector,
        } <= set(record["evidence_paths"])

    source = DESIGN_DELTA_WORK_ITEM.read_text(encoding="utf-8")
    for callee in (
        "project-selected-item-finalizer-approved-plan",
        "project-selected-item-finalizer-completed-implementation",
        "project-selected-item-finalizer-blocked-implementation",
    ):
        assert len(re.findall(rf"\(defworkflow\s+{callee}\b", source)) == 1
        assert not re.search(rf"\(defproc\s+{callee}\b", source)
    assert len(
        re.findall(
            r"\(call\s+project-selected-item-finalizer-approved-plan\b", source
        )
    ) == 2
    assert len(
        re.findall(
            r"\(call\s+project-selected-item-finalizer-completed-implementation\b",
            source,
        )
    ) == 1
    assert len(
        re.findall(
            r"\(call\s+project-selected-item-finalizer-blocked-implementation\b",
            source,
        )
    ) == 1
    assert re.search(r"\(export[\s\S]*?\brun-work-item\b[\s\S]*?\)", source)
    assert len(re.findall(r"\(defworkflow\s+run-work-item(?=\s)", source)) == 1


def test_design_delta_blocked_recovery_rows_retain_workflow_boundaries(
    tmp_path: Path,
) -> None:
    inventory = _load_json(REUSE_INVENTORY)
    decision = DESIGN_DELTA_BLOCKED_RECOVERY_RETENTION_DECISION.read_text(
        encoding="utf-8"
    )
    records_by_id = {row["id"]: row for row in inventory["records"]}
    prefix = (
        "internal-call:workflows/library/lisp_frontend_design_delta/"
        "work_item.orc:"
    )
    retained_ids = {
        f"{prefix}classify-blocked-implementation-recovery:1",
        *(
            f"{prefix}finalize-selected-item-from-blocked-implementation:{index}"
            for index in range(1, 6)
        ),
    }
    decision_path = DESIGN_DELTA_BLOCKED_RECOVERY_RETENTION_DECISION.relative_to(
        REPO_ROOT
    ).as_posix()
    inventory_path = REUSE_INVENTORY_NARRATIVE.relative_to(REPO_ROOT).as_posix()
    selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_blocked_recovery_rows_retain_workflow_boundaries"
    )
    compile_selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_blocked_recovery_hypothetical_fails_closed_at_typecheck"
    )

    observed_ids = {
        row["id"]
        for row in inventory["records"]
        if row["source_path"] == DESIGN_DELTA_WORK_ITEM.relative_to(REPO_ROOT).as_posix()
        and row["callee"]
        in {
            "classify-blocked-implementation-recovery",
            "finalize-selected-item-from-blocked-implementation",
        }
    }
    assert observed_ids == retained_ids
    classifier_id = f"{prefix}classify-blocked-implementation-recovery:1"
    finalizer_ids = retained_ids - {classifier_id}
    for record_id in retained_ids:
        record = records_by_id[record_id]
        assert record["record_kind"] == "internal-call"
        assert record["classification"] == "effect-adapter"
        assert {
            record["source_path"],
            decision_path,
            inventory_path,
            selector,
        } <= set(record["evidence_paths"])
    classifier = records_by_id[classifier_id]
    assert "export" in classifier["named_substrate_gap"].lower()
    assert "strict_compatibility" in classifier["named_substrate_gap"]
    assert "pure_expr_operand_type_mismatch" not in classifier["named_substrate_gap"]
    assert {
        "orchestrator/workflow_lisp/build.py",
        (
            "tests/test_workflow_lisp_procedure_first_migrations.py::"
            "test_procedure_first_public_boundary_inventory_keeps_exported_wrappers"
        ),
    } <= set(classifier["evidence_paths"])
    public_classifier = records_by_id[
        "public-entry:lisp_frontend_design_delta/work_item::"
        "classify-blocked-implementation-recovery"
    ]
    assert public_classifier["classification"] == "public-boundary"
    assert public_classifier["resolution"] == "exported-entry"
    assert {
        "exported workflow",
        "CLI-selectable entry",
        "compiled workflows_by_name export",
    } <= set(public_classifier["public_boundary_evidence"])
    for record_id in finalizer_ids:
        record = records_by_id[record_id]
        assert "pure_expr_operand_type_mismatch" in record["named_substrate_gap"]
        assert compile_selector in record["evidence_paths"]
        assert "six-call" not in record["reason"]
        assert "classify-blocked-implementation-recovery" not in record["reason"]
        assert classifier_id not in record["reason"]
    assert classifier["named_substrate_gap"].startswith("strict_compatibility")
    assert {
        record["named_substrate_gap"].split(":", 1)[0]
        for record_id in finalizer_ids
        for record in (records_by_id[record_id],)
    } == {"pure_expr_operand_type_mismatch"}

    source = DESIGN_DELTA_WORK_ITEM.read_text(encoding="utf-8")
    expected_calls = {
        "classify-blocked-implementation-recovery": 1,
        "finalize-selected-item-from-blocked-implementation": 5,
    }
    for callee, expected_count in expected_calls.items():
        assert len(re.findall(rf"\(defworkflow\s+{callee}\b", source)) == 1
        assert not re.search(rf"\(defproc\s+{callee}\b", source)
        assert len(re.findall(rf"\(call\s+{callee}\b", source)) == expected_count
    assert sum(expected_calls.values()) == 6
    assert len(re.findall(r"\(defworkflow\s+run-work-item(?=\s)", source)) == 1
    normalized_decision = " ".join(decision.split())
    assert "no finalizer hypothetical executable exists" in (
        normalized_decision.lower()
    )
    assert "neither an added/removed checkpoint delta" in normalized_decision
    assert "nor affected-route runtime parity" in normalized_decision
    assert "process-local exploratory probe" in normalized_decision
    assert "This type rejection, not the process-local exploratory probe" in (
        normalized_decision
    )
    assert "five finalizer calls only" in normalized_decision
    assert "diagnostic is not evidence for classifier retention" in normalized_decision


def test_design_delta_phase_orchestration_rows_retain_workflow_boundaries(
    tmp_path: Path,
) -> None:
    inventory = _load_json(REUSE_INVENTORY)
    records_by_id = {row["id"]: row for row in inventory["records"]}
    prefix = (
        "internal-call:workflows/library/lisp_frontend_design_delta/"
        "work_item.orc:"
    )
    retained_ids = {
        *(f"{prefix}project-work-item-inputs:{index}" for index in range(1, 3)),
        *(f"{prefix}run-plan-phase:{index}" for index in range(1, 3)),
        *(f"{prefix}implementation-phase:{index}" for index in range(1, 3)),
        *(
            f"{prefix}classify-work-item-terminal:{index}"
            for index in range(1, 3)
        ),
        f"{prefix}run-work-item-pending:1",
    }
    expected_public_entries = {
        "lisp_frontend_design_delta/bootstrap::project-work-item-inputs": {
            "source_path": (
                "workflows/library/lisp_frontend_design_delta/bootstrap.orc"
            ),
            "source_line": 11,
        },
        "lisp_frontend_design_delta/plan_phase::run-plan-phase": {
            "source_path": (
                "workflows/library/lisp_frontend_design_delta/plan_phase.orc"
            ),
            "source_line": 168,
        },
        "lisp_frontend_design_delta/implementation_phase::implementation-phase": {
            "source_path": (
                "workflows/library/lisp_frontend_design_delta/implementation_phase.orc"
            ),
            "source_line": 186,
        },
        "lisp_frontend_design_delta/projections::classify-work-item-terminal": {
            "source_path": (
                "workflows/library/lisp_frontend_design_delta/projections.orc"
            ),
            "source_line": 50,
        },
    }
    public_callees = set(expected_public_entries)
    decision_path = (
        DESIGN_DELTA_PHASE_ORCHESTRATION_RETENTION_DECISION.relative_to(REPO_ROOT)
        .as_posix()
    )
    selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_phase_orchestration_rows_retain_workflow_boundaries"
    )

    observed_ids = {
        row["id"]
        for row in inventory["records"]
        if row["source_path"] == DESIGN_DELTA_WORK_ITEM.relative_to(REPO_ROOT).as_posix()
        and row["callee"]
        in {
            "project-work-item-inputs",
            "run-plan-phase",
            "implementation-phase",
            "classify-work-item-terminal",
            "run-work-item-pending",
        }
    }
    assert observed_ids == retained_ids
    assert retained_ids <= set(records_by_id)

    expected_sources = {
        "project-work-item-inputs": DESIGN_DELTA_BOOTSTRAP,
        "run-plan-phase": DESIGN_DELTA_PLAN_PHASE,
        "implementation-phase": DESIGN_DELTA_IMPLEMENTATION_PHASE,
        "classify-work-item-terminal": DESIGN_DELTA_PROJECTIONS,
    }

    work_item_source = DESIGN_DELTA_WORK_ITEM.read_text(encoding="utf-8")
    assert len(re.findall(r"\(defworkflow\s+run-work-item-pending\b", work_item_source)) == 1
    assert not re.search(r"\(defproc\s+run-work-item-pending\b", work_item_source)



def test_design_delta_completed_finalization_rows_retain_private_workflow_boundary(
    tmp_path: Path,
) -> None:
    inventory = _load_json(REUSE_INVENTORY)
    records_by_id = {row["id"]: row for row in inventory["records"]}
    prefix = (
        "internal-call:workflows/library/lisp_frontend_design_delta/"
        "work_item.orc:"
    )
    retained_ids = {
        f"{prefix}finalize-selected-item-from-completed-implementation:1",
        f"{prefix}finalize-selected-item-from-completed-implementation:2",
    }
    decision_path = (
        DESIGN_DELTA_COMPLETED_FINALIZATION_RETENTION_DECISION.relative_to(
            REPO_ROOT
        ).as_posix()
    )
    inventory_path = REUSE_INVENTORY_NARRATIVE.relative_to(REPO_ROOT).as_posix()
    selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_completed_finalization_rows_retain_private_workflow_boundary"
    )
    compile_selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_completed_finalization_hypothetical_fails_shared_validation"
    )

    observed_ids = {
        row["id"]
        for row in inventory["records"]
        if row["source_path"]
        == DESIGN_DELTA_WORK_ITEM.relative_to(REPO_ROOT).as_posix()
        and row["callee"]
        == "finalize-selected-item-from-completed-implementation"
    }
    assert observed_ids == retained_ids
    for record_id in retained_ids:
        record = records_by_id[record_id]
        assert record["record_kind"] == "internal-call"
        assert record["classification"] == "effect-adapter"
        assert record["classification"] != "public-boundary"
        assert record["named_substrate_gap"].startswith(
            "workflow_boundary_type_invalid"
        )
        assert {
            record["source_path"],
            decision_path,
            inventory_path,
            selector,
            compile_selector,
        } <= set(record["evidence_paths"])

    source = DESIGN_DELTA_WORK_ITEM.read_text(encoding="utf-8")
    callee = "finalize-selected-item-from-completed-implementation"
    assert len(re.findall(rf"\(defworkflow\s+{callee}\b", source)) == 1
    assert not re.search(rf"\(defproc\s+{callee}\b", source)
    assert len(re.findall(rf"\(call\s+{callee}\b", source)) == 2



def test_design_delta_drain_builder_row_retains_private_workflow_boundary(
    tmp_path: Path,
) -> None:
    inventory = _load_json(REUSE_INVENTORY)
    registry = _load_json(ROUTE_READINESS_REGISTRY)
    record_id = (
        "internal-call:workflows/library/lisp_frontend_design_delta/drain.orc:"
        "build-drain-runtime-owned:1"
    )
    matching = [row for row in inventory["records"] if row["id"] == record_id]
    assert len(matching) == 1
    record = matching[0]
    decision_path = DESIGN_DELTA_DRAIN_BUILDER_RETENTION_DECISION.relative_to(
        REPO_ROOT
    ).as_posix()
    structural_selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_drain_builder_row_retains_private_workflow_boundary"
    )
    audit_selector = (
        "tests/test_workflow_lisp_procedure_first_migrations.py::"
        "test_design_delta_drain_builder_hypothetical_changes_checkpoint_identity"
    )
    public_entry_id = f"public-entry:{DESIGN_DELTA_PUBLIC_ENTRY}"
    public_entry = next(
        row for row in inventory["records"] if row["id"] == public_entry_id
    )
    route = next(
        row
        for row in registry["surfaces"]
        if row["path"] == record["source_path"]
    )

    assert record["record_kind"] == "internal-call"
    assert record["classification"] == "effect-adapter"
    assert record["classification"] != "public-boundary"
    assert "strict_compatibility" in record["named_substrate_gap"]
    assert "checkpoint" in record["named_substrate_gap"].lower()
    assert "promoted/live" in record["named_substrate_gap"]
    assert "reviewed_internal_identity_retirement" not in json.dumps(record)
    assert any(
        "identity-preserving lowering or a general atomic upgrader" in note
        for note in record["uncertainty"]["notes"]
    )
    assert {
        record["source_path"],
        decision_path,
        "docs/workflow_lisp_route_readiness_registry.json",
        structural_selector,
        audit_selector,
        (
            "tests/test_workflow_lisp_procedure_first_migrations.py::"
            "test_procedure_first_public_boundary_inventory_keeps_exported_wrappers"
        ),
    } <= set(record["evidence_paths"])
    assert public_entry["live_status"] == "live"
    assert public_entry["classification"] == "public-boundary"
    assert "promoted route-readiness identity" in public_entry[
        "public_boundary_evidence"
    ]
    assert "readiness_label" not in route
    assert route["route_label"] == "historical_negative"
    assert route["copy_safety"] == "not_current_guidance"

    source = DESIGN_DELTA_DRAIN.read_text(encoding="utf-8")
    builder = "build-drain-runtime-owned"
    assert len(re.findall(rf"\(defworkflow\s+{builder}\b", source)) == 1
    assert not re.search(rf"\(defproc\s+{builder}\b", source)
    drain_definition = source.split("  (defworkflow drain\n", 1)[1]
    assert len(re.findall(rf"\(call\s+{builder}\b", drain_definition)) == 1
    assert re.search(r"\(export\s+drain\)", source)
    assert len(re.findall(r"\(defworkflow\s+drain(?=\s)", source)) == 1



def test_design_delta_drain_builder_hypothetical_changes_checkpoint_identity(
    tmp_path: Path,
) -> None:
    retained_source = DESIGN_DELTA_DRAIN.read_bytes()
    proposed_source = _design_delta_drain_builder_proposed_inline_source(
        retained_source
    )
    retained_sha256 = "sha256:" + hashlib.sha256(retained_source).hexdigest()
    proposed_sha256 = "sha256:" + hashlib.sha256(proposed_source).hexdigest()
    assert retained_sha256 == (
        "sha256:e321e84e80342ff8757ab8f166530af5fdefd23807eab55f16c1a22c095da5fd"
    )
    assert proposed_sha256 == (
        "sha256:189666db8d4638a116a700079d6f1129b008ef8bdff91060201bc7e10b8ca9be"
    )
    proposed_text = proposed_source.decode("utf-8")
    builder = "build-drain-runtime-owned"
    assert len(re.findall(rf"\(defproc\s+{builder}\b", proposed_text)) == 1
    assert not re.search(rf"\(defworkflow\s+{builder}\b", proposed_text)
    assert ":effects ()" in proposed_text
    assert ":lowering inline" in proposed_text
    assert len(re.findall(rf"\({builder}\s+run\)", proposed_text)) == 1
    assert not re.search(rf"\(call\s+{builder}\b", proposed_text)
    proposed_drain = proposed_text.split("  (defworkflow drain\n", 1)[1]
    assert proposed_drain.startswith("    ((run RunCtx)\n")

    retained_dir = tmp_path / "retained"
    proposed_dir = tmp_path / "proposed"
    retained_dir.mkdir()
    proposed_dir.mkdir()
    assert DESIGN_DELTA_DRAIN.read_bytes() == retained_source


    builder_bundle = "lisp_frontend_design_delta/drain::build-drain-runtime-owned"

    removed_checkpoint_id = "ckpt:4dc584b1d0c80e14d36a3d5e"
    call_node = (
        "root.lisp_frontend_design_delta_drain_drain__runtime_owned__call_"
        "lisp_frontend_design_delta_drain_build_drain_runtime_owned"
    )



    builder_effect = f"effect:{DESIGN_DELTA_PUBLIC_ENTRY}:{call_node}:workflow_call"
























def _design_delta_finalizer_proposed_inline_source(old_source: bytes) -> bytes:
    source = old_source.decode("utf-8")
    replacements = (
        (
            "  (defworkflow project-selected-item-finalizer-approved-plan\n",
            "  (defproc project-selected-item-finalizer-approved-plan\n",
        ),
        (
            "    -> SelectedItemFinalizerPlan\n"
            "    (variant SelectedItemFinalizerPlan APPROVED",
            "    -> SelectedItemFinalizerPlan\n"
            "    :effects ()\n"
            "    :lowering inline\n"
            "    (variant SelectedItemFinalizerPlan APPROVED",
        ),
        (
            "  (defworkflow project-selected-item-finalizer-completed-implementation\n",
            "  (defproc project-selected-item-finalizer-completed-implementation\n",
        ),
        (
            "    -> SelectedItemFinalizerImplementation\n"
            "    (variant SelectedItemFinalizerImplementation COMPLETED",
            "    -> SelectedItemFinalizerImplementation\n"
            "    :effects ()\n"
            "    :lowering inline\n"
            "    (variant SelectedItemFinalizerImplementation COMPLETED",
        ),
        (
            "  (defworkflow project-selected-item-finalizer-blocked-implementation\n",
            "  (defproc project-selected-item-finalizer-blocked-implementation\n",
        ),
        (
            "    -> SelectedItemFinalizerImplementation\n"
            "    (variant SelectedItemFinalizerImplementation BLOCKED",
            "    -> SelectedItemFinalizerImplementation\n"
            "    :effects ()\n"
            "    :lowering inline\n"
            "    (variant SelectedItemFinalizerImplementation BLOCKED",
        ),
        (
            "             (call project-selected-item-finalizer-approved-plan\n"
            "               :implementation_phase_result implementation_phase_result)",
            "             (project-selected-item-finalizer-approved-plan\n"
            "               implementation_phase_result)",
        ),
        (
            "             (call project-selected-item-finalizer-completed-implementation\n"
            "               :implementation_phase_result implementation_phase_result)",
            "             (project-selected-item-finalizer-completed-implementation\n"
            "               implementation_phase_result)",
        ),
        (
            "             (call project-selected-item-finalizer-blocked-implementation\n"
            "               :implementation_phase_result implementation_phase_result\n"
            "               :blocker-class blocker-class)",
            "             (project-selected-item-finalizer-blocked-implementation\n"
            "               implementation_phase_result\n"
            "               blocker-class)",
        ),
        (
            "              (calls-workflow lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-approved-plan)\n",
            "",
        ),
        (
            "              (calls-workflow lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-completed-implementation)\n",
            "",
        ),
        (
            "              (calls-workflow lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-blocked-implementation)\n",
            "",
        ),
    )
    expected_counts = (1, 1, 1, 1, 1, 1, 2, 1, 1, 3, 1, 3)
    for (old, new), expected_count in zip(replacements, expected_counts, strict=True):
        assert source.count(old) == expected_count
        source = source.replace(old, new)
    return source.encode("utf-8")


def _design_delta_blocked_finalizer_proposed_inline_source(old_source: bytes) -> bytes:
    source = old_source.decode("utf-8")
    replacements = (
        (
            "  (defworkflow finalize-selected-item-from-blocked-implementation\n",
            "  (defproc finalize-selected-item-from-blocked-implementation\n",
            1,
        ),
        (
            "  (defproc finalize-selected-item-from-blocked-implementation\n"
            "    ((implementation_phase_result ImplementationPhaseResult)\n"
            "     (blocker-class std/resource/BlockerClass))\n"
            "    -> SelectedItemResult\n"
            "    (let* ((plan\n",
            "  (defproc finalize-selected-item-from-blocked-implementation\n"
            "    ((implementation_phase_result ImplementationPhaseResult)\n"
            "     (blocker-class std/resource/BlockerClass))\n"
            "    -> SelectedItemResult\n"
            "    :effects ((calls-workflow lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-approved-plan)\n"
            "              (calls-workflow lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-blocked-implementation)\n"
            "              (uses-command apply_resource_transition))\n"
            "    :lowering inline\n"
            "    (let* ((plan\n",
            1,
        ),
        (
            "                  (call finalize-selected-item-from-blocked-implementation\n"
            "                    :implementation_phase_result implementation_phase_result\n"
            "                    :blocker-class BlockerClass.roadmap_conflict)",
            "                  (finalize-selected-item-from-blocked-implementation\n"
            "                    implementation_phase_result\n"
            "                    BlockerClass.roadmap_conflict)",
            1,
        ),
        (
            "              (call finalize-selected-item-from-blocked-implementation\n"
            "                :implementation_phase_result implementation\n"
            "                :blocker-class BlockerClass.unrecoverable_after_fix_attempt)",
            "              (finalize-selected-item-from-blocked-implementation\n"
            "                implementation\n"
            "                BlockerClass.unrecoverable_after_fix_attempt)",
            2,
        ),
        (
            "                              (call "
            "finalize-selected-item-from-blocked-implementation\n"
            "                                :implementation_phase_result implementation\n"
            "                                :blocker-class "
            "BlockerClass.unrecoverable_after_fix_attempt)",
            "                              (finalize-selected-item-from-blocked-implementation\n"
            "                                implementation\n"
            "                                BlockerClass.unrecoverable_after_fix_attempt)",
            2,
        ),
        (
            "              (calls-workflow lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-blocked-implementation)\n",
            "",
            3,
        ),
    )
    for old, new, expected_count in replacements:
        assert source.count(old) == expected_count
        source = source.replace(old, new)
    return source.encode("utf-8")


def _design_delta_pending_proposed_inline_source(old_source: bytes) -> bytes:
    source = old_source.decode("utf-8")
    replacements = (
        (
            "  (defworkflow run-work-item-pending\n",
            "  (defproc run-work-item-pending\n",
            1,
        ),
        (
            "    -> PendingWorkItemResult\n"
            "    (with-phase phase-ctx work-item\n",
            "    -> PendingWorkItemResult\n"
            "    :effects ((calls-workflow lisp_frontend_design_delta/bootstrap::project-work-item-inputs)\n"
            "              (calls-workflow lisp_frontend_design_delta/implementation_phase::implementation-phase)\n"
            "              (calls-workflow lisp_frontend_design_delta/plan_phase::run-plan-phase)\n"
            "              (calls-workflow lisp_frontend_design_delta/projections::classify-work-item-terminal)\n"
            "              (calls-workflow lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery)\n"
            "              (calls-workflow lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation)\n"
            "              (calls-workflow lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation)\n"
            "              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-approved-plan)\n"
            "              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-blocked-implementation)\n"
            "              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-completed-implementation)\n"
            "              (uses-command apply_resource_transition)\n"
            "              (uses-provider providers.work-item.recovery-classifier))\n"
            "    :lowering inline\n"
            "    (with-phase phase-ctx work-item\n",
            1,
        ),
        (
            "               (call run-work-item-pending\n"
            "                 :phase-ctx phase-ctx\n"
            "                 :work_item_bootstrap work_item_bootstrap\n"
            "                 :steering_path steering_path\n"
            "                 :target_design_path target_design_path\n"
            "                 :baseline_design_path baseline_design_path\n"
            "                 :progress_ledger_path progress_ledger_path)",
            "               (run-work-item-pending\n"
            "                 phase-ctx\n"
            "                 work_item_bootstrap\n"
            "                 steering_path\n"
            "                 target_design_path\n"
            "                 baseline_design_path\n"
            "                 progress_ledger_path)",
            1,
        ),
    )
    for old, new, expected_count in replacements:
        assert source.count(old) == expected_count
        source = source.replace(old, new)
    return source.encode("utf-8")




def _design_delta_drain_builder_proposed_inline_source(old_source: bytes) -> bytes:
    source = old_source.decode("utf-8")
    replacements = (
        (
            "  (defworkflow build-drain-runtime-owned\n",
            "  (defproc build-drain-runtime-owned\n",
            1,
        ),
        (
            "    -> DrainRuntimeOwned\n"
            "    (record DrainRuntimeOwned\n",
            "    -> DrainRuntimeOwned\n"
            "    :effects ()\n"
            "    :lowering inline\n"
            "    (record DrainRuntimeOwned\n",
            1,
        ),
        (
            "  (defworkflow drain\n"
            "    ((steering_path SteeringDoc)\n",
            "  (defworkflow drain\n"
            "    ((run RunCtx)\n"
            "     (steering_path SteeringDoc)\n",
            1,
        ),
        (
            "           (runtime-owned\n"
            "             (call build-drain-runtime-owned))\n",
            "           (runtime-owned\n"
            "             (build-drain-runtime-owned run))\n",
            1,
        ),
    )
    for old, new, expected_count in replacements:
        assert source.count(old) == expected_count
        source = source.replace(old, new)
    return source.encode("utf-8")


@contextmanager
def _design_delta_same_path_source_io(source_path: Path, source_bytes: bytes):
    selected_path = source_path.resolve()
    selected_sha256 = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    counts = {"read_bytes": 0, "read_text": 0, "open": 0}
    served_sha256: list[str] = []
    rejected_writes: list[str] = []
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    original_open = Path.open
    original_write_bytes = Path.write_bytes
    original_write_text = Path.write_text
    disk_before = original_read_bytes(selected_path)
    disk_before_sha256 = "sha256:" + hashlib.sha256(disk_before).hexdigest()
    evidence = {
        "path": str(selected_path),
        "selected_sha256": selected_sha256,
        "counts": counts,
        "served_sha256": served_sha256,
        "rejected_writes": rejected_writes,
        "disk_before_sha256": disk_before_sha256,
    }

    def is_selected_path(path: Path) -> bool:
        return path.resolve() == selected_path

    def record_read(method: str) -> None:
        counts[method] += 1
        served_sha256.append(selected_sha256)

    def read_bytes(path: Path) -> bytes:
        if is_selected_path(path):
            record_read("read_bytes")
            return source_bytes
        return original_read_bytes(path)

    def read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        if is_selected_path(path):
            record_read("read_text")
            return source_bytes.decode(encoding or "utf-8", errors or "strict")
        return original_read_text(
            path,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    def open_path(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ):
        if is_selected_path(path):
            if {"w", "a", "x", "+"} & set(mode):
                rejected_writes.append(mode)
                raise AssertionError(
                    f"read-only source override rejected Path.open mode {mode!r}"
                )
            if "r" in mode:
                record_read("open")
                if "b" in mode:
                    return io.BytesIO(source_bytes)
                return io.StringIO(
                    source_bytes.decode(encoding or "utf-8", errors or "strict"),
                    newline=newline,
                )
        return original_open(
            path,
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    def reject_write_bytes(path: Path, data: bytes) -> int:
        if is_selected_path(path):
            rejected_writes.append("write_bytes")
            raise AssertionError("read-only source override rejected Path.write_bytes")
        return original_write_bytes(path, data)

    def reject_write_text(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if is_selected_path(path):
            rejected_writes.append("write_text")
            raise AssertionError("read-only source override rejected Path.write_text")
        return original_write_text(
            path,
            data,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    try:
        with patch.object(Path, "read_bytes", read_bytes), patch.object(
            Path,
            "read_text",
            read_text,
        ), patch.object(Path, "open", open_path), patch.object(
            Path,
            "write_bytes",
            reject_write_bytes,
        ), patch.object(Path, "write_text", reject_write_text):
            yield evidence
    finally:
        disk_after = original_read_bytes(selected_path)
        disk_after_sha256 = "sha256:" + hashlib.sha256(disk_after).hexdigest()
        evidence["disk_after_sha256"] = disk_after_sha256
        evidence["total"] = sum(counts.values())
        assert disk_after == disk_before, (
            "same-path source override changed production bytes",
            disk_before_sha256,
            disk_after_sha256,
        )


@contextmanager
def _design_delta_same_path_work_item_io(work_item_source: bytes):
    with _design_delta_same_path_source_io(
        DESIGN_DELTA_WORK_ITEM,
        work_item_source,
    ) as evidence:
        yield evidence


















def test_design_delta_finalizer_hypothetical_removes_four_public_wrapper_checkpoints(
    tmp_path: Path,
) -> None:
    retained_source = DESIGN_DELTA_WORK_ITEM.read_bytes()
    proposed_source = _design_delta_finalizer_proposed_inline_source(retained_source)

    retained_source_sha256 = "sha256:" + hashlib.sha256(retained_source).hexdigest()
    proposed_source_sha256 = "sha256:" + hashlib.sha256(proposed_source).hexdigest()
    assert retained_source_sha256 != proposed_source_sha256
    assert DESIGN_DELTA_WORK_ITEM.read_bytes() == retained_source



    affected_names = {
        "project-selected-item-finalizer-approved-plan",
        "project-selected-item-finalizer-completed-implementation",
        "project-selected-item-finalizer-blocked-implementation",
    }

    # This run exercises only the unaffected selector/architect route. These
    # equalities characterize that route; they do not establish finalizer parity.


def test_design_delta_blocked_recovery_hypothetical_fails_closed_at_typecheck(
    tmp_path: Path,
) -> None:
    retained_source = DESIGN_DELTA_WORK_ITEM.read_bytes()
    proposed_source = _design_delta_blocked_finalizer_proposed_inline_source(
        retained_source
    )
    retained_sha256 = "sha256:" + hashlib.sha256(retained_source).hexdigest()
    proposed_sha256 = "sha256:" + hashlib.sha256(proposed_source).hexdigest()
    assert retained_sha256 != proposed_sha256
    proposed_text = proposed_source.decode("utf-8")
    assert len(
        re.findall(
            r"\(defworkflow\s+classify-blocked-implementation-recovery\b",
            proposed_text,
        )
    ) == 1
    assert len(
        re.findall(
            r"\(call\s+classify-blocked-implementation-recovery\b",
            proposed_text,
        )
    ) == 1
    assert len(
        re.findall(
            r"\(defproc\s+finalize-selected-item-from-blocked-implementation\b",
            proposed_text,
        )
    ) == 1
    assert not re.search(
        r"\(call\s+finalize-selected-item-from-blocked-implementation\b",
        proposed_text,
    )

    (tmp_path / "retained").mkdir()

    (tmp_path / "proposed").mkdir()

    assert "(blocker-class std/resource/BlockerClass)" in proposed_text

    assert DESIGN_DELTA_WORK_ITEM.read_bytes() == retained_source




def test_design_delta_pending_hypothetical_changes_checkpoint_identity(
    tmp_path: Path,
) -> None:
    retained_source = DESIGN_DELTA_WORK_ITEM.read_bytes()
    proposed_source = _design_delta_pending_proposed_inline_source(retained_source)
    retained_sha256 = "sha256:" + hashlib.sha256(retained_source).hexdigest()
    proposed_sha256 = "sha256:" + hashlib.sha256(proposed_source).hexdigest()
    assert retained_sha256 != proposed_sha256

    (tmp_path / "retained").mkdir()
    (tmp_path / "proposed").mkdir()
    assert DESIGN_DELTA_WORK_ITEM.read_bytes() == retained_source

    expected_effects = {
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/bootstrap::project-work-item-inputs"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/implementation_phase::implementation-phase"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/plan_phase::run-plan-phase"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/projections::classify-work-item-terminal"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/work_item::project-selected-item-finalizer-approved-plan"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/work_item::project-selected-item-finalizer-blocked-implementation"),
        ("CallsWorkflowEffect", "lisp_frontend_design_delta/work_item::project-selected-item-finalizer-completed-implementation"),
        ("UsesCommandEffect", "apply_resource_transition"),
        ("UsesProviderEffect", "providers.work-item.recovery-classifier"),
    }

    caller_owner = "lisp_frontend_design_delta/work_item::run-work-item"
    new_presentation_prefix = (
        "lisp_frontend_design_delta/work_item::run-work-item__pending__"
        "lisp_frontend_design_delta/work_item::run-work-item-pending_1__"
    )
    caller_namespace = f"{caller_owner}::{new_presentation_prefix}"


@pytest.mark.parametrize(
    ("operation", "expected_mode"),
    (
        (lambda path: path.open("w"), "w"),
        (lambda path: path.open("a"), "a"),
        (lambda path: path.open("x"), "x"),
        (lambda path: path.open("r+"), "r+"),
        (
            lambda path: path.write_text("mutated", encoding="utf-8"),
            "write_text",
        ),
        (lambda path: path.write_bytes(b"mutated"), "write_bytes"),
    ),
)
def test_design_delta_same_path_source_override_rejects_target_writes(
    operation,
    expected_mode: str,
) -> None:
    retained_source = DESIGN_DELTA_WORK_ITEM.read_bytes()
    retained_sha256 = "sha256:" + hashlib.sha256(retained_source).hexdigest()

    with _design_delta_same_path_work_item_io(retained_source) as evidence:
        with pytest.raises(AssertionError, match="read-only source override"):
            operation(DESIGN_DELTA_WORK_ITEM)

    assert evidence["rejected_writes"] == [expected_mode]
    assert evidence["disk_before_sha256"] == retained_sha256
    assert evidence["disk_after_sha256"] == retained_sha256
    assert DESIGN_DELTA_WORK_ITEM.read_bytes() == retained_source


def test_design_delta_same_path_source_override_reads_and_failure_cleanup() -> None:
    retained_source = DESIGN_DELTA_WORK_ITEM.read_bytes()
    selected_source = _design_delta_finalizer_proposed_inline_source(retained_source)
    retained_sha256 = "sha256:" + hashlib.sha256(retained_source).hexdigest()
    selected_sha256 = "sha256:" + hashlib.sha256(selected_source).hexdigest()

    with pytest.raises(RuntimeError, match="synthetic compile failure"):
        with _design_delta_same_path_work_item_io(selected_source) as evidence:
            assert DESIGN_DELTA_WORK_ITEM.read_bytes() == selected_source
            assert DESIGN_DELTA_WORK_ITEM.read_text(encoding="utf-8") == (
                selected_source.decode("utf-8")
            )
            with DESIGN_DELTA_WORK_ITEM.open("rb") as binary_stream:
                assert binary_stream.read() == selected_source
            with DESIGN_DELTA_WORK_ITEM.open("r", encoding="utf-8") as text_stream:
                assert text_stream.read() == selected_source.decode("utf-8")
            raise RuntimeError("synthetic compile failure")

    assert evidence["selected_sha256"] == selected_sha256
    assert all(evidence["counts"][method] > 0 for method in evidence["counts"])
    assert set(evidence["served_sha256"]) == {selected_sha256}
    assert evidence["disk_before_sha256"] == retained_sha256
    assert evidence["disk_after_sha256"] == retained_sha256
    assert DESIGN_DELTA_WORK_ITEM.read_bytes() == retained_source


def _projection_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _assert_tracked_plan_retirement_claim_bindings(payload: Mapping[str, object]) -> None:
    labels = payload.get("supporting_labels")
    assert isinstance(labels, list)
    assert (
        "correction_authorization="
        "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/attestations/"
        "task-3/artifact-parity-evidence-correction-authorization.json#"
        "sha256:5dcec17ccd0ebef24f8b0025501df2acf8ac90517227a6161e9e32d26aa1963d"
    ) in labels, "correction authorization binding is missing"
    equality_labels = [
        label
        for label in labels
        if isinstance(label, str) and label.startswith("historical_clean_artifact_equality=")
    ]
    assert equality_labels == ["historical_clean_artifact_equality=not_asserted"], (
        "historical clean artifact equality must be exactly not_asserted"
    )
    labels = set(labels)
    assert "checksum_scope=accepted_generic_guard_characterization_bound_to_actual_pilot_checksum_delta" not in labels
    assert (
        "checksum_scope.root=generic_characterization;actual_subject_rejection="
        "not_asserted;cross_source_compatibility=not_asserted;runtime_authority=none"
    ) in labels
    assert (
        "checksum_scope.callee=accepted_generic_guard_characterization_bound_to_"
        "actual_pilot_checksum_delta;not_live_old_run_resume;"
        "not_actual_pilot_rejection_negative;not_cross_source_compatibility"
    ) in labels


def _sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()




def _run_tree_facts(root: Path) -> dict[str, object]:
    rows: list[tuple[str, str, str | None]] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        directories.sort()
        filenames.sort()
        current_path = Path(current)
        for name in (*directories, *filenames):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if relative == "run.lock":
                # The command-lifetime coordination inode is not persisted
                # workflow state or evidence.
                continue
            assert not path.is_symlink()
            rows.append(
                (relative, "directory", None)
                if path.is_dir()
                else (relative, "file", _sha256_path(path))
            )
    canonical = json.dumps(
        sorted(rows), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "run_tree_sha256": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "run_tree_entry_count": len(rows),
    }


def _assert_final_owner_scan_run_chain(
    payload: Mapping[str, object],
    *,
    scan_candidate_path: Path | None = None,
    owner_record: Mapping[str, object] | None = None,
) -> None:
    scan_path = PILOT_EVIDENCE / "final_known_store_scans.json"
    owner_path = PILOT_EVIDENCE / "attestations" / "final" / "dedicated-evidence-root.json"
    candidate_path = scan_candidate_path or scan_path
    scan = _load_json(candidate_path)
    owner = dict(owner_record or _load_json(owner_path))
    assert set(scan["scans"]) == {
        "legacy_repository_root",
        "dedicated_runtime_evidence_root",
    }
    assert set(owner) == {
        "record_type", "version", "evidence_status", "authorized_disposition",
        "bindings", "claims_not_made", "owner", "owner_confirmations",
        "prepared_by", "prepared_at", "owner_adoption", "template_prepared_by",
    }
    assert owner["evidence_status"] == "owner_confirmed"
    assert owner["owner_adoption"]["owner"] == owner["owner"]
    bindings = owner["bindings"]
    assert bindings["final_known_store_scans"] == {
        "path": scan_path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_path(candidate_path),
    }
    expected_roots = {
        "legacy_repository_root": scan["root_scope"]["legacy_repository_root"],
        "dedicated_runtime_evidence_root": scan["root_scope"][
            "dedicated_runtime_evidence_root"
        ],
    }
    known_roots = {row["root"] for row in payload["known_state_stores"]}
    assert known_roots == set(expected_roots.values())
    for key, root in expected_roots.items():
        assert scan["scans"][key]["scanner_result"]["root"] == root
    dedicated = scan["scans"]["dedicated_runtime_evidence_root"]
    scanner = dedicated["scanner_result"]
    assert scanner["root"] == bindings["canonical_dedicated_root"]
    snapshot = bindings["final_normalized_snapshot"]
    assert snapshot["query_version"] == scan["old_identity_query"]["query_version"]
    assert snapshot["query_identity_count"] == scan["old_identity_query"]["identity_count"]
    assert snapshot["query_identity_list_sha256"] == scan["old_identity_query"]["query_list_sha256"]
    assert snapshot["query_started_at"] == dedicated["query_started_at"]
    assert snapshot["query_finished_at"] == dedicated["query_finished_at"]
    assert snapshot["normalized_scan_digest"] == scanner["normalized_scan_digest"]
    assert snapshot["counts"] == {key: scanner[key] for key in snapshot["counts"]}
    dedicated_store = next(
        row for row in payload["known_state_stores"] if row["root"] == scanner["root"]
    )
    assert dedicated_store["attestation"] == (
        owner_path.relative_to(REPO_ROOT).as_posix() + "#" + _sha256_path(owner_path)
    )
    assert dedicated_store["normalized_scan_digest"] == scanner["normalized_scan_digest"]
    for key in snapshot["counts"]:
        assert dedicated_store[key] == scanner[key]
    projections = {
        "tracked-plan-phase-clean-new-id": _load_json(PILOT_EVIDENCE / "evidence" / "clean_run.json"),
        "tracked-plan-phase-interrupted-new-id": _load_json(PILOT_EVIDENCE / "evidence" / "interruption_resume.json"),
    }
    run_root = Path(bindings["canonical_dedicated_root"])
    for bound in bindings["retained_runs"]:
        projection_path = REPO_ROOT / bound["projection_path"]
        projection = projections[bound["run_id"]]
        run_path = run_root / bound["run_id"]
        assert _sha256_path(projection_path) == bound["projection_sha256"]
        assert projection["run_id"] == projection["run"]["id"] == bound["run_id"]
        facts = _run_tree_facts(run_path)
        assert facts == {
            "run_tree_sha256": bound["run_tree_sha256"],
            "run_tree_entry_count": bound["run_tree_entry_count"],
        }
        assert projection["run"]["tree_sha256"] == bound["run_tree_sha256"]
        assert projection["run"]["entry_count"] == bound["run_tree_entry_count"]
        assert _sha256_path(run_path / "state.json") == bound["state_sha256"]
        assert json.loads((run_path / "state.json").read_text())["status"] == bound["status"] == "completed"
        record_run = (
            payload["new_id_evidence"]["clean_run"]
            if "clean" in bound["run_id"]
            else payload["new_id_evidence"]["interruption_resume"]
        )
        assert record_run["run_id"] == bound["run_id"]
        assert record_run["status"] == bound["status"]
        if "interrupted" in bound["run_id"]:
            assert bound["resume_completed_under_same_run_id"] is True
            assert projection["resume"]["status"] == "completed"


def _assert_callee_characterization(
    payload: Mapping[str, object],
    *,
    callee_characterization: Mapping[str, object] | None = None,
    observed_outer_sha256: str | None = None,
) -> None:
    path = PILOT_EVIDENCE / "evidence" / "callee_checksum_characterization.json"
    callee = dict(callee_characterization or _load_json(path))
    outer_sha256 = observed_outer_sha256 or _sha256_path(path)
    assert set(callee) == {
        "schema", "scope", "projection", "projection_sha256",
        "generic_guard_details", "claims_not_made",
    }
    assert set(callee["projection"]) == {"guard_provenance", "pilot_checksum_delta"}
    assert set(callee["generic_guard_details"]) == {
        "checksum_mismatch_observed", "child_workflow_executed", "provider_executed",
        "command_executed", "child_state_identity_remapped", "parent_metadata_delta",
    }
    assert callee["scope"] == {
        "classification": "accepted generic guard characterization bound to actual pilot checksum delta",
        "not_live_old_run_resume": True,
        "not_actual_pilot_rejection_negative": True,
        "not_cross_source_compatibility": True,
    }
    assert callee["claims_not_made"] == [
        "This is not evidence from a live resume of any retained old-ID pilot run.",
        "This is not an actual-pilot rejection negative and does not assert that either retained new-ID run was resumed against the old source.",
        "This does not establish cross-source compatibility, remapping authority, retirement release, or completion.",
    ]
    assert callee["projection_sha256"] == _projection_sha256(callee["projection"])
    record_callee = payload["checksum_evidence"]["callee"]
    command_commit, command_nodeid = record_callee["command"].split(" ", 1)
    assert callee["projection"]["guard_provenance"]["commit"].startswith(command_commit)
    assert command_nodeid == callee["projection"]["guard_provenance"]["nodeid"]
    assert {
        key: record_callee[key] for key in callee["generic_guard_details"]
    } == callee["generic_guard_details"]
    assert (
        "checksum_provenance.callee=evidence/callee_checksum_characterization.json#"
        + outer_sha256
    ) in payload["supporting_labels"]


@pytest.fixture(scope="module")
def tracked_plan_compile():
    return compile_stage3_entrypoint(
        EXAMPLE,
        source_roots=(WORKFLOWS,),
        provider_externs=_load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json"),
        prompt_externs=_load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json"),
        command_boundaries=_load_json(MIGRATION_INPUTS / "design_plan_impl_stack.commands.json"),
        validate_shared=True,
        workspace_root=REPO_ROOT,
    )




























def test_tracked_plan_phase_is_explicit_inline_procedure(tracked_plan_compile) -> None:
    compile_result = tracked_plan_compile.entry_result
    procedure = next(
        (
            procedure
            for procedure in compile_result.typed_procedures
            if procedure.definition.name == TRACKED_PLAN
        ),
        None,
    )

    assert procedure is not None, (
        "tracked-plan-phase remains a defworkflow; expected defproc with requested/resolved "
        "lowering inline"
    )
    assert procedure.signature.requested_lowering_mode.value == "inline"
    assert procedure.resolved_lowering_mode.value == "inline"




def test_tracked_plan_phase_wrapper_uses_procedure_call(tracked_plan_compile) -> None:
    compile_result = tracked_plan_compile.entry_result
    public_workflow = next(
        workflow
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == PUBLIC_ENTRY
    )
    expression_nodes = tuple(walk_expr(public_workflow.typed_body.expr))
    workflow_calls = {
        node.callee_name for node in expression_nodes if isinstance(node, CallExpr)
    }
    procedure_calls = {
        node.callee_name for node in expression_nodes if isinstance(node, ProcedureCallExpr)
    }

    assert TRACKED_PLAN in procedure_calls and TRACKED_PLAN not in workflow_calls, (
        "design-plan-impl-review-stack still uses (call tracked-plan-phase ...); expected "
        "an ordinary positional procedure call"
    )


def test_tracked_plan_phase_contract_matches_frozen_pre_migration_baseline(
    tracked_plan_compile,
) -> None:
    expected = _load_json(BASELINE)

    assert expected["schema_version"] == "procedure_first.tracked_plan_phase_contract.v1"
    assert expected["public_contract"]["entry_workflow"] == PUBLIC_ENTRY_TOKEN
    assert len(expected["public_contract"]["inputs"]) == 7
    assert len(expected["public_contract"]["outputs"]) == 9
    assert {row["subject"] for row in expected["caller_visible_effects"]} >= {
        "providers.plan.draft",
        "providers.plan.review",
    }
    assert expected["runtime_contract"]["resume_checkpoints"]
    assert expected["runtime_contract"]["lexical_checkpoints"]
    expected_route = expected.pop("internal_route")
    expected_runtime = expected.pop("runtime_contract")








def test_tracked_plan_phase_retirement_record_replays_final_scan_evidence() -> None:
    scan_evidence = _load_json(PILOT_EVIDENCE / "final_known_store_scans.json")
    record_path = PILOT_EVIDENCE / "retirement_record.json"
    payload = _load_json(record_path)
    _assert_tracked_plan_retirement_claim_bindings(payload)
    _assert_final_owner_scan_run_chain(payload)
    identity_projection = _load_json(PILOT_EVIDENCE / "evidence" / "identity_delta.json")
    assert identity_projection["identity_delta"] == payload["identity_delta"]
    query_binding = payload["retired_identity_query_evidence"]
    assert identity_projection["derived_from"]["retired_identity_query"] == {
        "evidence_path": query_binding["evidence_path"],
        "evidence_sha256": query_binding["evidence_sha256"],
        "identities_by_domain_sha256": query_binding[
            "identities_by_domain_sha256"
        ],
        "identity_count": query_binding["identity_count"],
        "membership_count": sum(
            len(identities)
            for identities in scan_evidence["old_identity_query"][
                "identities_by_domain"
            ].values()
        ),
        "query_list_sha256": query_binding["query_list_sha256"],
        "query_version": query_binding["query_version"],
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_correction_authorization",
        "asserted_historical_equality",
        "missing_historical_equality",
    ),
)
def test_tracked_plan_phase_retirement_record_claim_bindings_reject_overclaim(
    mutation: str,
) -> None:
    payload = _load_json(PILOT_EVIDENCE / "retirement_record.json")
    labels = payload["supporting_labels"]
    if mutation == "missing_correction_authorization":
        payload["supporting_labels"] = [
            label for label in labels if not label.startswith("correction_authorization=")
        ]
    else:
        payload["supporting_labels"] = [
            label
            for label in labels
            if not label.startswith("historical_clean_artifact_equality=")
        ]
        if mutation == "asserted_historical_equality":
            payload["supporting_labels"].append(
                "historical_clean_artifact_equality=asserted"
            )

    with pytest.raises(AssertionError):
        _assert_tracked_plan_retirement_claim_bindings(payload)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_scan_root",
        "extra_scan_root",
        "legacy_scan_root",
        "owner_outer_digest",
        "run_binding",
    ),
)
def test_tracked_plan_phase_final_chain_rejects_tamper(
    mutation: str, tmp_path: Path
) -> None:
    payload = _load_json(PILOT_EVIDENCE / "retirement_record.json")
    scan = _load_json(PILOT_EVIDENCE / "final_known_store_scans.json")
    if mutation == "missing_scan_root":
        scan["scans"].pop("legacy_repository_root")
    elif mutation == "extra_scan_root":
        scan["scans"]["unexpected"] = deepcopy(
            scan["scans"]["legacy_repository_root"]
        )
    elif mutation == "legacy_scan_root":
        scan["scans"]["legacy_repository_root"]["scanner_result"]["root"] = (
            "/unexpected/legacy/root"
        )
    elif mutation == "owner_outer_digest":
        dedicated = next(
            row for row in payload["known_state_stores"] if "procedure-first-pilot-evidence" in row["root"]
        )
        dedicated["attestation"] = dedicated["attestation"].split("#")[0] + "#sha256:" + "0" * 64
    else:
        owner = _load_json(
            PILOT_EVIDENCE / "attestations" / "final" / "dedicated-evidence-root.json"
        )
        owner["bindings"]["retained_runs"][0]["state_sha256"] = "sha256:" + "0" * 64
        with pytest.raises(AssertionError):
            _assert_final_owner_scan_run_chain(payload, owner_record=owner)
        return
    if mutation in {"missing_scan_root", "extra_scan_root", "legacy_scan_root"}:
        candidate_path = tmp_path / "final_known_store_scans.json"
        candidate_path.write_text(json.dumps(scan, sort_keys=True), encoding="utf-8")
        owner = _load_json(
            PILOT_EVIDENCE / "attestations" / "final" / "dedicated-evidence-root.json"
        )
        owner["bindings"]["final_known_store_scans"]["sha256"] = _sha256_path(
            candidate_path
        )
        with pytest.raises(AssertionError):
            _assert_final_owner_scan_run_chain(
                payload, scan_candidate_path=candidate_path, owner_record=owner
            )
        return
    with pytest.raises(AssertionError):
        _assert_final_owner_scan_run_chain(payload)


@pytest.mark.parametrize("mutation", ("outer", "inner", "label"))
def test_tracked_plan_phase_callee_characterization_rejects_tamper(mutation: str) -> None:
    payload = _load_json(PILOT_EVIDENCE / "retirement_record.json")
    callee = _load_json(
        PILOT_EVIDENCE / "evidence" / "callee_checksum_characterization.json"
    )
    if mutation == "label":
        payload["supporting_labels"] = [
            label for label in payload["supporting_labels"]
            if not label.startswith("checksum_provenance.callee=")
        ]
    elif mutation == "inner":
        callee["projection"]["guard_provenance"]["guard_result"] = "changed"
    with pytest.raises(AssertionError):
        _assert_callee_characterization(
            payload,
            callee_characterization=callee,
            observed_outer_sha256=("sha256:" + "0" * 64) if mutation == "outer" else None,
        )


def _assert_task_4a_index_key_sets(
    attestation_index: Mapping[str, object], evidence_index: Mapping[str, object]
) -> None:
    assert set(attestation_index) == {
        "schema", "external_store_absence", "known_store_records",
        "pre_edit_known_store_scans", "scratch_provenance_record",
        "final_dedicated_evidence_root", "hold_release",
    }
    assert {
        row["canonical_root"] for row in attestation_index["known_store_records"]
    } == {
        "/home/ollie/Documents/agent-orchestration/.orchestrate/runs",
        "/home/ollie/Documents/agent-orchestration/.orchestrate/procedure-first-pilot-evidence/tracked-plan-phase/workspace/.orchestrate/runs",
    }
    assert set(evidence_index["artifacts"]) == {
        "attestation_index", "final_known_store_scans", "final_owner_attestation",
        "live_validator_stdout", "live_validator_result", "old_build_manifest",
        "new_build", "retirement_record", "retirement_record_review", "projections",
        "hold_release",
    }
    assert set(evidence_index["artifacts"]["new_build"]) == {
        "build_manifest", "source", "typed_frontend_ast", "semantic_ir",
        "executable_ir", "runtime_plan", "lexical_checkpoint_points", "source_map",
    }
    assert set(evidence_index["artifacts"]["projections"]) == {
        "identity_delta", "artifact_contract_multiset", "execution_order",
        "retained_wrapper_inventory", "root_checksum_characterization",
        "callee_checksum_characterization", "clean_run", "interruption_resume",
    }


def test_tracked_plan_phase_task_4a_indexes_replay_content_addresses() -> None:
    attestation_index_path = PILOT_EVIDENCE / "attestations" / "index.json"
    attestation_index = _load_json(attestation_index_path)
    assert attestation_index["schema"] == "procedure_first_pilot_attestation_index.v1"
    final = attestation_index["final_dedicated_evidence_root"]
    assert final["evidence_status"] == "owner_confirmed"
    assert final["hold_status"] == "active"
    assert final["claim_boundary"] == {
        "hold_release": "not_asserted",
        "independent_review": "not_asserted",
        "live_validator": "not_asserted",
        "retirement_eligibility": "not_asserted",
        "scope": "exact_dedicated_root_and_final_snapshot_only",
    }
    attestation_rows = [
        *(record for record in attestation_index["known_store_records"]),
        attestation_index["scratch_provenance_record"],
        final,
    ]
    for row in attestation_rows:
        assert _sha256_path(REPO_ROOT / row.get("record_path", row.get("path"))) == row.get(
            "record_sha256", row.get("sha256")
        )
    evidence_index = _load_json(PILOT_EVIDENCE / "evidence_index.json")
    _assert_task_4a_index_key_sets(attestation_index, evidence_index)
    assert set(evidence_index) == {
        "schema", "phase", "status", "external_store_absence", "hold",
        "routing_only", "artifacts", "reviewed_predecessor", "claims_not_made",
    }
    assert evidence_index["phase"] == "task_4a_complete"
    assert evidence_index["status"] == "task_5_authorized"
    assert evidence_index["hold"] == {
        "status": "released", "live_validator": "passed",
        "independent_retirement_review": "passed", "hold_release": "owner_confirmed",
        "released_at": "2026-07-15T21:01:49-07:00",
        "confirmations": {
            "hold_explicitly_released_for_task_5_family_parity_focused_and_broad_gates": True,
            "validator_and_independent_review_complete": True,
        },
    }
    assert evidence_index["artifacts"]["attestation_index"]["sha256"] == _sha256_path(
        attestation_index_path
    )
    for row in evidence_index["artifacts"].values():
        rows = row.values() if isinstance(row, dict) and "path" not in row else (row,)
        for binding in rows:
            assert _sha256_path(REPO_ROOT / binding["path"]) == binding["sha256"]
    record = _load_json(PILOT_EVIDENCE / "retirement_record.json")
    assert "evidence_index" not in json.dumps(record)


_REVIEW_PREDECESSOR_SNAPSHOT_BINDINGS = {
    "evidence_index": {
        "path": (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/"
            "snapshots/review-predecessor-evidence-index.json"
        ),
        "sha256": (
            "sha256:b66ab3c024bc04a4a940a21f34d4adc0395f15879e1d1a7c2a88d602a7731cb6"
        ),
    },
    "attestation_index": {
        "path": (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/"
            "snapshots/review-predecessor-attestation-index.json"
        ),
        "sha256": (
            "sha256:5aed6854732dc9aea7860f2587d1ec6c206e246e18a90d8438a7fb8653709e57"
        ),
    },
}


def _assert_content_addressed_binding(binding: Mapping[str, object]) -> None:
    assert set(binding) == {"path", "sha256"}
    path_value = binding["path"]
    digest = binding["sha256"]
    assert isinstance(path_value, str)
    assert isinstance(digest, str)
    path = Path(path_value)
    assert not path.is_absolute()
    assert path.parts and all(part not in {"", ".", ".."} for part in path.parts)
    assert path.as_posix() == path_value
    resolved = (REPO_ROOT / path).resolve(strict=True)
    assert resolved.is_relative_to(REPO_ROOT.resolve())
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    assert _sha256_path(REPO_ROOT / path) == digest


def _assert_independent_review_chain(
    review: Mapping[str, object], evidence_index: Mapping[str, object]
) -> None:
    assert set(review) == {
        "schema", "reviewer_identity", "reviewer_role", "result", "reviewed_at",
        "reviewed_head", "approval_scope", "bindings", "verification",
        "frozen_root_facts", "retained_run_facts", "reviewed_facts",
        "reviewed_claim_boundaries", "claims_not_made",
    }
    assert review["schema"] == "procedure_first_pilot_retirement_record_review.v1"
    assert review["reviewer_identity"] == "Codex subagent /root/task4a_live_independent_review"
    assert review["reviewer_role"] == "independent specification and runtime-state reviewer"
    assert review["result"] == "approved"
    assert review["reviewed_at"] == "2026-07-15T20:31:46-07:00"
    _assert_rfc3339_offset(review["reviewed_at"])
    assert "owner" not in review["reviewer_role"].lower()
    required_bindings = {
        "retirement_record", "final_known_store_scans", "final_owner_attestation",
        "live_validator_stdout", "live_validator_result", "evidence_index",
        "attestation_index", "root_checksum_characterization",
        "callee_checksum_characterization", "identity_delta",
        "artifact_contract_multiset", "execution_order", "clean_run",
        "interruption_resume", "old_build_manifest", "new_build_manifest",
    }
    assert set(review["bindings"]) == required_bindings
    assert {
        name: review["bindings"][name]
        for name in _REVIEW_PREDECESSOR_SNAPSHOT_BINDINGS
    } == _REVIEW_PREDECESSOR_SNAPSHOT_BINDINGS
    for binding in review["bindings"].values():
        _assert_content_addressed_binding(binding)
    assert set(review["verification"]) == {
        "generic_retirement_validator_suite", "strengthened_default_selectors",
        "captured_live_validator", "content_addressing", "frozen_supported_store_files",
    }
    assert review["reviewed_claim_boundaries"]["independent_review_approval"] == (
        "asserted_only_by_this_review_artifact"
    )
    for key in (
        "owner_hold_release", "task_5_or_pilot_completion",
        "root_characterization_actual_subject_rejection",
        "callee_characterization_actual_pilot_rejection",
    ):
        assert review["reviewed_claim_boundaries"][key] == "not_asserted"
    assert review["reviewed_claim_boundaries"]["runtime_authority"] == "none"
    assert len(review["claims_not_made"]) == 7
    assert review["claims_not_made"][-1] == (
        "This reviewer identity is a Codex subagent, not a human identity or store owner."
    )
    assert evidence_index["phase"] == "task_4a_complete"
    assert evidence_index["status"] == "task_5_authorized"
    assert evidence_index["hold"] == {
        "status": "released", "live_validator": "passed",
        "independent_retirement_review": "passed", "hold_release": "owner_confirmed",
        "released_at": "2026-07-15T21:01:49-07:00",
        "confirmations": {
            "hold_explicitly_released_for_task_5_family_parity_focused_and_broad_gates": True,
            "validator_and_independent_review_complete": True,
        },
    }
    review_binding = evidence_index["artifacts"]["retirement_record_review"]
    review_path = PILOT_EVIDENCE / "evidence" / "retirement_record_review.json"
    assert review_binding == {
        "path": review_path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_path(review_path),
    }
    assert "retirement_record_review" not in review["bindings"]


def test_tracked_plan_phase_independent_review_chain_replays() -> None:
    review = _load_json(PILOT_EVIDENCE / "evidence" / "retirement_record_review.json")
    evidence_index = _load_json(PILOT_EVIDENCE / "evidence_index.json")
    _assert_independent_review_chain(review, evidence_index)


def test_tracked_plan_phase_review_predecessor_snapshots_replay_exact_bytes() -> None:
    for binding in _REVIEW_PREDECESSOR_SNAPSHOT_BINDINGS.values():
        _assert_content_addressed_binding(binding)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_binding", "extra_binding", "tampered_digest", "path_alias",
        "missing_evidence_snapshot", "missing_attestation_snapshot",
    ),
)
def test_tracked_plan_phase_review_predecessor_snapshots_reject_tamper(
    mutation: str,
) -> None:
    bindings = deepcopy(_REVIEW_PREDECESSOR_SNAPSHOT_BINDINGS)
    if mutation == "missing_binding":
        bindings.pop("attestation_index")
    elif mutation == "extra_binding":
        bindings["unexpected"] = deepcopy(bindings["evidence_index"])
    elif mutation == "tampered_digest":
        bindings["evidence_index"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "path_alias":
        bindings["evidence_index"]["path"] = bindings["evidence_index"]["path"].replace(
            "snapshots/review", "snapshots/../snapshots/review"
        )
    elif mutation == "missing_evidence_snapshot":
        bindings["evidence_index"]["path"] = (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/"
            "snapshots/missing-evidence-index.json"
        )
    else:
        bindings["attestation_index"]["path"] = (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/"
            "snapshots/missing-attestation-index.json"
        )
    with pytest.raises((AssertionError, FileNotFoundError)):
        assert set(bindings) == set(_REVIEW_PREDECESSOR_SNAPSHOT_BINDINGS)
        for binding in bindings.values():
            _assert_content_addressed_binding(binding)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_binding", "tampered_binding", "reviewer_owner", "not_approved",
        "overclaim", "extra_field", "missing_field", "index_status",
        "mutable_evidence_predecessor", "mutable_attestation_predecessor",
    ),
)
def test_tracked_plan_phase_independent_review_chain_rejects_tamper(
    mutation: str,
) -> None:
    review = _load_json(PILOT_EVIDENCE / "evidence" / "retirement_record_review.json")
    evidence_index = _load_json(PILOT_EVIDENCE / "evidence_index.json")
    if mutation == "missing_binding":
        review["bindings"].pop("retirement_record")
    elif mutation == "tampered_binding":
        review["bindings"]["retirement_record"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "reviewer_owner":
        review["reviewer_role"] = "owner"
    elif mutation == "not_approved":
        review["result"] = "rejected"
    elif mutation == "overclaim":
        review["reviewed_claim_boundaries"]["owner_hold_release"] = "asserted"
    elif mutation == "extra_field":
        review["unexpected"] = True
    elif mutation == "missing_field":
        review.pop("verification")
    elif mutation == "index_status":
        evidence_index["status"] = "pilot_complete"
    elif mutation == "mutable_evidence_predecessor":
        review["bindings"]["evidence_index"]["path"] = (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json"
        )
    else:
        review["bindings"]["attestation_index"]["path"] = (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/"
            "attestations/index.json"
        )
    with pytest.raises(AssertionError):
        _assert_independent_review_chain(review, evidence_index)


@pytest.mark.parametrize(
    "mutation",
    (
        "artifact_missing", "artifact_extra", "new_build_missing", "new_build_extra",
        "projection_missing", "projection_extra", "known_store_missing", "known_store_extra",
    ),
)
def test_tracked_plan_phase_task_4a_index_key_sets_reject_tamper(
    mutation: str,
) -> None:
    attestation_index = _load_json(PILOT_EVIDENCE / "attestations" / "index.json")
    evidence_index = _load_json(PILOT_EVIDENCE / "evidence_index.json")
    if mutation == "artifact_missing":
        evidence_index["artifacts"].pop("retirement_record")
    elif mutation == "artifact_extra":
        evidence_index["artifacts"]["unexpected"] = {}
    elif mutation == "new_build_missing":
        evidence_index["artifacts"]["new_build"].pop("source_map")
    elif mutation == "new_build_extra":
        evidence_index["artifacts"]["new_build"]["unexpected"] = {}
    elif mutation == "projection_missing":
        evidence_index["artifacts"]["projections"].pop("identity_delta")
    elif mutation == "projection_extra":
        evidence_index["artifacts"]["projections"]["unexpected"] = {}
    elif mutation == "known_store_missing":
        attestation_index["known_store_records"].pop()
    else:
        attestation_index["known_store_records"].append(
            deepcopy(attestation_index["known_store_records"][0])
        )
        attestation_index["known_store_records"][-1]["canonical_root"] = "/unexpected"
    with pytest.raises(AssertionError):
        _assert_task_4a_index_key_sets(attestation_index, evidence_index)


_HOLD_RELEASE_PATH = (
    PILOT_EVIDENCE / "attestations" / "final" / "hold-release.json"
)
_HOLD_RELEASE_SHA256 = (
    "sha256:d257a92d5b9d8d1eaf6a41a341e6990563c392f8cde199325c4fd1c057d77bf8"
)
_HOLD_RELEASED_AT = "2026-07-15T21:01:49-07:00"
_HOLD_RELEASE_PREPARED_BY = (
    "Claude Code session agent (Opus 4.8) — mechanical write at the owner's "
    "explicit direction after the owner re-adopted the release with the corrected "
    "review binding"
)
_HOLD_RELEASE_STATEMENT = (
    "I reviewed this complete record, confirm the bound live validator and "
    "independent review are complete, and explicitly release the legacy-root "
    "and dedicated-root hold for the deferred Task 5 family-parity, focused, "
    "and broad gates."
)
_HOLD_RELEASE_CONFIRMATIONS = {
    "hold_explicitly_released_for_task_5_family_parity_focused_and_broad_gates": True,
    "validator_and_independent_review_complete": True,
}
_HOLD_RELEASE_BINDINGS = {
    "retirement_record": {
        "path": "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/retirement_record.json",
        "sha256": "sha256:7c35069323e8dcf7ac9b17785492ed030d0088ec29489e5e3529f94c44dd4370",
    },
    "final_known_store_scans": {
        "path": "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/final_known_store_scans.json",
        "sha256": "sha256:05e5cea75338ea745cbbc165fc0934c174132555fae8b4d07f180c48b5f1ccc0",
    },
    "live_validator_result": {
        "path": "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/live_validator_result.json",
        "sha256": "sha256:8ff86cd084575fcd768f49622cd97e2c2b558c26bebd0e72d9c04cac5abdd0a4",
    },
    "retirement_record_review": {
        "path": "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/retirement_record_review.json",
        "sha256": "sha256:12b1f2f60b75628c536ec9fbe8cac548f7295588b22e01cff2dccc69a2179b30",
    },
}


def _assert_rfc3339_offset(value: object) -> datetime:
    assert isinstance(value, str)
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2}",
        value,
    )
    parsed = datetime.fromisoformat(value)
    assert parsed.utcoffset() is not None
    return parsed


def _assert_owner_hold_release(release: Mapping[str, object]) -> None:
    assert set(release) == {
        "record_type", "version", "evidence_status", "owner", "released_at",
        "roots", "bindings", "confirmations", "prepared_by", "prepared_at",
        "owner_adoption",
    }
    assert release["record_type"] == "procedure_first_pilot_hold_release"
    assert release["version"] == 1
    assert release["evidence_status"] == "owner_confirmed"
    assert release["owner"] == {
        "name": "Ollie",
        "role": "owner of the legacy and dedicated tracked-plan pilot roots",
    }
    assert release["roots"] == {
        "legacy": "/home/ollie/Documents/agent-orchestration/.orchestrate/runs",
        "dedicated": (
            "/home/ollie/Documents/agent-orchestration/.orchestrate/"
            "procedure-first-pilot-evidence/tracked-plan-phase/workspace/"
            ".orchestrate/runs"
        ),
    }
    assert release["bindings"] == _HOLD_RELEASE_BINDINGS
    for binding in release["bindings"].values():
        assert _sha256_path(REPO_ROOT / binding["path"]) == binding["sha256"]
    assert release["confirmations"] == _HOLD_RELEASE_CONFIRMATIONS
    assert release["prepared_by"] == _HOLD_RELEASE_PREPARED_BY
    assert release["prepared_by"] != release["owner"]["name"]
    assert set(release["owner_adoption"]) == {"adopted_at", "owner", "statement"}
    assert release["owner_adoption"]["owner"] == "Ollie"
    assert release["owner_adoption"]["statement"] == _HOLD_RELEASE_STATEMENT
    for value in (
        release["released_at"], release["prepared_at"],
        release["owner_adoption"]["adopted_at"],
    ):
        _assert_rfc3339_offset(value)


def _assert_task_4a_chronology(
    live_validator_result: Mapping[str, object],
    review: Mapping[str, object],
    release: Mapping[str, object],
) -> None:
    live_completed_at = _assert_rfc3339_offset(live_validator_result["completed_at"])
    reviewed_at = _assert_rfc3339_offset(review["reviewed_at"])
    prepared_at = _assert_rfc3339_offset(release["prepared_at"])
    adopted_at = _assert_rfc3339_offset(release["owner_adoption"]["adopted_at"])
    released_at = _assert_rfc3339_offset(release["released_at"])
    assert live_completed_at <= reviewed_at < prepared_at
    assert prepared_at == adopted_at == released_at


def _assert_task_4a_release_indexes(
    release: Mapping[str, object],
    attestation_index: Mapping[str, object],
    evidence_index: Mapping[str, object],
) -> None:
    _assert_owner_hold_release(release)
    _assert_task_4a_index_key_sets(attestation_index, evidence_index)
    release_binding = {
        "path": _HOLD_RELEASE_PATH.relative_to(REPO_ROOT).as_posix(),
        "sha256": _HOLD_RELEASE_SHA256,
    }
    assert _sha256_path(_HOLD_RELEASE_PATH) == _HOLD_RELEASE_SHA256
    assert attestation_index["hold_release"] == {
        **release_binding,
        "evidence_status": "owner_confirmed",
        "owner": {
            "name": "Ollie",
            "role": "owner of the legacy and dedicated tracked-plan pilot roots",
        },
        "released_at": release["released_at"],
        "hold_status": "released",
        "authorized_task_5_gates": ["family_parity", "focused", "broad"],
        "confirmations": _HOLD_RELEASE_CONFIRMATIONS,
    }
    assert evidence_index["phase"] == "task_4a_complete"
    assert evidence_index["status"] == "task_5_authorized"
    assert evidence_index["hold"] == {
        "status": "released",
        "live_validator": "passed",
        "independent_retirement_review": "passed",
        "hold_release": "owner_confirmed",
        "released_at": release["released_at"],
        "confirmations": _HOLD_RELEASE_CONFIRMATIONS,
    }
    assert evidence_index["artifacts"]["hold_release"] == release_binding
    attestation_index_path = PILOT_EVIDENCE / "attestations" / "index.json"
    assert evidence_index["artifacts"]["attestation_index"] == {
        "path": attestation_index_path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_path(attestation_index_path),
    }
    for row in evidence_index["artifacts"].values():
        bindings = row.values() if isinstance(row, dict) and "path" not in row else (row,)
        for binding in bindings:
            _assert_content_addressed_binding(binding)
    assert evidence_index["reviewed_predecessor"] == {
        "path": (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence/"
            "snapshots/review-predecessor-evidence-index.json"
        ),
        "sha256": "sha256:b66ab3c024bc04a4a940a21f34d4adc0395f15879e1d1a7c2a88d602a7731cb6",
        "meaning": (
            "exact pre-review index bytes content-verified by the immutable "
            "independent review before this one-way review route was added"
        ),
    }
    _assert_content_addressed_binding(
        {
            key: evidence_index["reviewed_predecessor"][key]
            for key in ("path", "sha256")
        }
    )
    assert evidence_index["reviewed_predecessor"]["path"] != (
        "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json"
    )
    assert evidence_index["reviewed_predecessor"]["sha256"] != _sha256_path(
        PILOT_EVIDENCE / "evidence_index.json"
    )
    assert evidence_index["claims_not_made"] == [
        "This routing index is not owner authority and is not a run or resume input.",
        (
            "The owner-confirmed release authorizes only the deferred Task 5 "
            "family-parity, focused, and broad gates; it does not assert that "
            "any Task 5 gate ran."
        ),
        "Actual-pilot checksum negatives and pilot completion are not asserted.",
    ]


def test_tracked_plan_phase_owner_hold_release_replays_and_authorizes_task_5() -> None:
    release = _load_json(_HOLD_RELEASE_PATH)
    attestation_index = _load_json(PILOT_EVIDENCE / "attestations" / "index.json")
    evidence_index = _load_json(PILOT_EVIDENCE / "evidence_index.json")
    _assert_task_4a_release_indexes(release, attestation_index, evidence_index)


def test_tracked_plan_phase_task_4a_chronology_is_ordered() -> None:
    _assert_task_4a_chronology(
        _load_json(PILOT_EVIDENCE / "evidence" / "live_validator_result.json"),
        _load_json(PILOT_EVIDENCE / "evidence" / "retirement_record_review.json"),
        _load_json(_HOLD_RELEASE_PATH),
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "live_naive", "review_naive", "prepared_naive", "adopted_naive",
        "released_naive", "live_after_review", "reviewer_after_release",
        "prepared_after_adoption", "released_not_adopted",
    ),
)
def test_tracked_plan_phase_task_4a_chronology_rejects_tamper(
    mutation: str,
) -> None:
    live = _load_json(PILOT_EVIDENCE / "evidence" / "live_validator_result.json")
    review = _load_json(PILOT_EVIDENCE / "evidence" / "retirement_record_review.json")
    release = _load_json(_HOLD_RELEASE_PATH)
    if mutation == "live_naive":
        live["completed_at"] = "2026-07-15T19:14:46"
    elif mutation == "review_naive":
        review["reviewed_at"] = "2026-07-15T19:29:40"
    elif mutation == "prepared_naive":
        release["prepared_at"] = "2026-07-15T21:01:49"
    elif mutation == "adopted_naive":
        release["owner_adoption"]["adopted_at"] = "2026-07-15T21:01:49"
    elif mutation == "released_naive":
        release["released_at"] = "2026-07-15T21:01:49"
    elif mutation == "live_after_review":
        live["completed_at"] = "2026-07-15T20:32:00-07:00"
    elif mutation == "reviewer_after_release":
        review["reviewed_at"] = "2026-07-15T21:02:00-07:00"
    elif mutation == "prepared_after_adoption":
        release["prepared_at"] = "2026-07-15T21:02:00-07:00"
    else:
        release["released_at"] = "2026-07-15T21:01:48-07:00"
    with pytest.raises(AssertionError):
        _assert_task_4a_chronology(live, review, release)


@pytest.mark.parametrize(
    "field",
    (
        "intended_owner", "authorized_disposition", "owner_action_required",
        "owner_confirmation_statements_exact", "claims_not_made",
        "template_prepared_by", "template_prepared_at", "unexpected",
    ),
)
def test_tracked_plan_phase_owner_hold_release_rejects_pending_or_unknown_field(
    field: str,
) -> None:
    release = _load_json(_HOLD_RELEASE_PATH)
    release[field] = "unexpected"
    with pytest.raises(AssertionError):
        _assert_owner_hold_release(release)


@pytest.mark.parametrize(
    "mutation",
    (
        "false_release_confirmation", "false_review_confirmation",
        "retirement_binding", "scan_binding", "validator_binding", "review_binding",
        "owner_name", "owner_role", "adoption_owner", "statement",
        "legacy_root", "dedicated_root", "released_at", "prepared_at", "adopted_at",
        "status", "prepared_by_owner", "stale_review_binding",
    ),
)
def test_tracked_plan_phase_owner_hold_release_rejects_behavioral_tamper(
    mutation: str,
) -> None:
    release = _load_json(_HOLD_RELEASE_PATH)
    if mutation == "false_release_confirmation":
        release["confirmations"][
            "hold_explicitly_released_for_task_5_family_parity_focused_and_broad_gates"
        ] = False
    elif mutation == "false_review_confirmation":
        release["confirmations"]["validator_and_independent_review_complete"] = False
    elif mutation == "stale_review_binding":
        release["bindings"]["retirement_record_review"]["sha256"] = (
            "sha256:921dc20648c45a9cede63ccca1bc87ddbc0ee58c72345f2b01f5b7d677543e14"
        )
    elif mutation.endswith("_binding"):
        binding_name = {
            "retirement_binding": "retirement_record",
            "scan_binding": "final_known_store_scans",
            "validator_binding": "live_validator_result",
            "review_binding": "retirement_record_review",
        }[mutation]
        release["bindings"][binding_name]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "owner_name":
        release["owner"]["name"] = "Not Ollie"
    elif mutation == "owner_role":
        release["owner"]["role"] = "unexpected"
    elif mutation == "adoption_owner":
        release["owner_adoption"]["owner"] = "Not Ollie"
    elif mutation == "statement":
        release["owner_adoption"]["statement"] = "release"
    elif mutation == "legacy_root":
        release["roots"]["legacy"] = "/unexpected"
    elif mutation == "dedicated_root":
        release["roots"]["dedicated"] = "/unexpected"
    elif mutation == "released_at":
        release["released_at"] = "2026-07-15"
    elif mutation == "prepared_at":
        release["prepared_at"] = "not-a-timestamp"
    elif mutation == "adopted_at":
        release["owner_adoption"]["adopted_at"] = "2026-07-15T20:02:03"
    elif mutation == "status":
        release["evidence_status"] = "pending_owner_confirmation"
    elif mutation == "prepared_by_owner":
        release["prepared_by"] = "Ollie"
    else:
        release["prepared_by"] = "unexpected"
    with pytest.raises(AssertionError):
        _assert_owner_hold_release(release)


@pytest.mark.parametrize(
    "mutation",
    (
        "attestation_release_omission", "attestation_release_extra",
        "attestation_stale_status", "attestation_release_digest",
        "evidence_release_omission", "evidence_release_extra",
        "evidence_stale_status", "evidence_release_digest",
        "evidence_attestation_digest", "mutable_reviewed_predecessor",
        "stale_review_digest", "stale_release_digest", "stale_attestation_index_digest",
    ),
)
def test_tracked_plan_phase_task_4a_release_indexes_reject_tamper(
    mutation: str,
) -> None:
    release = _load_json(_HOLD_RELEASE_PATH)
    attestation_index = _load_json(PILOT_EVIDENCE / "attestations" / "index.json")
    evidence_index = _load_json(PILOT_EVIDENCE / "evidence_index.json")
    if mutation == "attestation_release_omission":
        attestation_index.pop("hold_release")
    elif mutation == "attestation_release_extra":
        attestation_index["hold_release"]["unexpected"] = True
    elif mutation == "attestation_stale_status":
        attestation_index["hold_release"]["hold_status"] = "active"
    elif mutation == "attestation_release_digest":
        attestation_index["hold_release"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "evidence_release_omission":
        evidence_index["artifacts"].pop("hold_release")
    elif mutation == "evidence_release_extra":
        evidence_index["artifacts"]["unexpected"] = {}
    elif mutation == "evidence_stale_status":
        evidence_index["status"] = "owner_hold_release_pending"
    elif mutation == "evidence_release_digest":
        evidence_index["artifacts"]["hold_release"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "evidence_attestation_digest":
        evidence_index["artifacts"]["attestation_index"]["sha256"] = (
            "sha256:" + "0" * 64
        )
    elif mutation == "mutable_reviewed_predecessor":
        evidence_index["reviewed_predecessor"]["path"] = (
            "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/evidence_index.json"
        )
    elif mutation == "stale_review_digest":
        evidence_index["artifacts"]["retirement_record_review"]["sha256"] = (
            "sha256:921dc20648c45a9cede63ccca1bc87ddbc0ee58c72345f2b01f5b7d677543e14"
        )
    elif mutation == "stale_release_digest":
        evidence_index["artifacts"]["hold_release"]["sha256"] = (
            "sha256:36ba90f20ca57cca243106ec3e4488caa527f3af75f85ada2425803bb78eb6b2"
        )
    else:
        evidence_index["artifacts"]["attestation_index"]["sha256"] = (
            "sha256:343f3b99b4248e7b85016a9ce3745a8b3d2c69d9c530ee86501fa440643dd841"
        )
    with pytest.raises(AssertionError):
        _assert_task_4a_release_indexes(release, attestation_index, evidence_index)


def _assert_live_validator_result(result: Mapping[str, object]) -> None:
    assert set(result) == {
        "schema", "status", "exit_status", "completed_at", "command", "nodeid",
        "bindings", "execution_boundary", "reconciled_store_facts", "claims_not_made",
    }
    assert result["schema"] == "procedure_first_pilot_live_validator_result.v1"
    assert result["status"] == "passed" and result["exit_status"] == 0
    assert result["nodeid"] in result["command"]
    assert set(result["bindings"]) == {
        "retirement_record", "final_known_store_scans", "final_owner_attestation", "stdout"
    }
    for binding in result["bindings"].values():
        assert _sha256_path(REPO_ROOT / binding["path"]) == binding["sha256"]
    stdout_binding = result["bindings"]["stdout"]
    stdout = (REPO_ROOT / stdout_binding["path"]).read_bytes()
    assert len(stdout) == stdout_binding["byte_count"] == 110
    stdout_text = stdout.decode("utf-8").lower()
    assert stdout_text.count("passed") == 1
    assert "failed" not in stdout_text and "error" not in stdout_text
    assert result["execution_boundary"] == {
        "scanner_only_live_store_access": True,
        "unpatched_public_validator": True,
        "workflow_run_invoked": False,
        "workflow_resume_invoked": False,
        "workflow_executor_constructed": False,
        "provider_executed": False,
        "workflow_command_executed": False,
        "runtime_authority": "none",
    }
    assert result["claims_not_made"] == {
        "independent_retirement_review": "not_asserted",
        "hold_release": "not_asserted",
        "task_5_or_pilot_completion": "not_asserted",
        "actual_pilot_checksum_negative": "not_asserted",
        "runtime_authority": "none",
        "separate_hidden_live_telemetry": "not_asserted",
    }
    scan = _load_json(PILOT_EVIDENCE / "final_known_store_scans.json")
    record = _load_json(PILOT_EVIDENCE / "retirement_record.json")
    facts = {row["store_role"]: row for row in result["reconciled_store_facts"]}
    assert set(facts) == {"legacy_repository_root", "dedicated_runtime_evidence_root"}
    for role, row in facts.items():
        retained = scan["scans"][role]
        scanner = retained["scanner_result"]
        assert row["root"] == scanner["root"]
        assert row["query_version"] == scanner["query_version"]
        assert row["retained_final_scan_query_started_at"] == retained["query_started_at"]
        assert row["retained_final_scan_query_finished_at"] == retained["query_finished_at"]
        assert row["normalized_scan_digest"] == scanner["normalized_scan_digest"]
        assert row["counts"] == {key: scanner[key] for key in row["counts"]}
        store = next(item for item in record["known_state_stores"] if item["root"] == row["root"])
        assert row["normalized_scan_digest"] == store["normalized_scan_digest"]
        for key, value in row["counts"].items():
            assert store[key] == value


def test_tracked_plan_phase_live_validator_result_replays() -> None:
    result_path = PILOT_EVIDENCE / "evidence" / "live_validator_result.json"
    assert result_path.is_file(), "one-time live validator result is missing"
    _assert_live_validator_result(_load_json(result_path))


@pytest.mark.parametrize("mutation", ("missing", "extra", "tamper", "overclaim"))
def test_tracked_plan_phase_live_validator_result_rejects_tamper(mutation: str) -> None:
    result = _load_json(PILOT_EVIDENCE / "evidence" / "live_validator_result.json")
    if mutation == "missing":
        result["reconciled_store_facts"].pop()
    elif mutation == "extra":
        extra = deepcopy(result["reconciled_store_facts"][0])
        extra["store_role"] = "unexpected"
        result["reconciled_store_facts"].append(extra)
    elif mutation == "tamper":
        result["bindings"]["stdout"]["sha256"] = "sha256:" + "0" * 64
    else:
        result["claims_not_made"]["hold_release"] = "asserted"
    with pytest.raises(AssertionError):
        _assert_live_validator_result(result)
