from __future__ import annotations

import hashlib
import io
import json
import os
import re
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from orchestrator.workflow_lisp import LispFrontendCompileError
from orchestrator.exec.output_capture import CaptureMode, CaptureResult
from orchestrator.exec.step_executor import ExecutionResult, StepExecutor
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_output_contracts,
    workflow_public_input_contracts,
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import CallExpr, ProcedureCallExpr
from orchestrator.workflow_lisp.lowering import procedures as procedure_lowering
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.procedure_identity_retirement import (
    _collect_production_identity_carriers,
    _collect_production_leak_carriers,
)
from tests.test_workflow_lisp_design_delta_smoke import (
    _compile_design_delta_parent_drain_entrypoint,
)
from tests.workflow_bundle_helpers import bundle_context_dict


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
PARITY_TARGETS = MIGRATION_INPUTS / "parity_targets.json"
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
    "artifacts": "sha256:0c0925b3d70fa64626186ecd608cf01c0039aae5d4edf2a74465f722157c3732",
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

    expected_imports = {
        "workflows/library/lisp_frontend_design_delta_done_review.v214.yaml": {
            "design_gap_architect": (
                "./lisp_frontend_design_delta_design_gap_architect.v214.yaml"
            ),
            "work_item": "./lisp_frontend_design_delta_work_item.v214.yaml",
        },
        "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml": {
            "plan_phase": "./lisp_frontend_design_delta_plan_phase.v214.yaml",
            "implementation_phase": (
                "./lisp_frontend_design_delta_implementation_phase.v214.yaml"
            ),
        },
        "workflows/library/lisp_frontend_work_item.v214.yaml": {
            "plan_phase": "./lisp_frontend_plan_phase.v214.yaml",
            "implementation_phase": "./lisp_frontend_implementation_phase.v214.yaml",
        },
    }
    for source_path, imports in expected_imports.items():
        document = yaml.safe_load((REPO_ROOT / source_path).read_text(encoding="utf-8"))
        assert document["imports"] == imports

        calls: list[str] = []

        def collect_calls(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "call":
                        calls.append(child)
                    collect_calls(child)
            elif isinstance(value, list):
                for child in value:
                    collect_calls(child)

        collect_calls(document["steps"])
        assert calls == list(imports)


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


def _tracked_design_production_identity_projections(
    workspace: Path,
    source: bytes,
    *,
    side: str,
    inputs_root: Path = TRACKED_DESIGN_INPUTS,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    source_path = workspace / "workflows" / "examples" / EXAMPLE.name
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(workspace / "workflows",),
            entry_workflow="design-plan-impl-review-stack",
            provider_externs_path=(
                inputs_root / "design_plan_impl_stack.providers.json"
            ),
            prompt_externs_path=inputs_root / "design_plan_impl_stack.prompts.json",
            command_boundaries_path=(
                inputs_root / "design_plan_impl_stack.commands.json"
            ),
            workspace_root=workspace,
            lowering_route="wcc_m4",
        )
    )
    artifact_roles = (
        "typed_frontend_ast",
        "semantic_ir",
        "executable_ir",
        "runtime_plan",
        "lexical_checkpoint_points",
        "source_map",
    )
    payloads = {
        (side, role): _load_json(result.artifact_paths[role])
        for role in artifact_roles
    }
    production = _collect_production_identity_carriers(payloads, side)
    leaks = _collect_production_leak_carriers(payloads, side)
    return (
        {kind: sorted(values) for kind, values in production.items()},
        {kind: sorted(values) for kind, values in leaks.items()},
    )


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


def test_tracked_design_phase_historical_projection_rebuild_is_opt_in(
    tmp_path: Path,
) -> None:
    if os.environ.get("ORCHESTRATOR_REBUILD_TRACKED_DESIGN_PROJECTIONS") != "1":
        pytest.skip("set ORCHESTRATOR_REBUILD_TRACKED_DESIGN_PROJECTIONS=1")

    current_source = (TRACKED_DESIGN_INPUTS / "source.orc").read_bytes()
    proposed_source = _tracked_design_phase_proposed_inline_source(current_source)
    witness = _load_json(TRACKED_DESIGN_IDENTITY_WITNESS)
    for clone in ("clone-a", "clone-b"):
        old_projection, _ = _tracked_design_production_identity_projections(
            tmp_path / f"{clone}-old",
            current_source,
            side="old",
        )
        new_projection, new_leaks = _tracked_design_production_identity_projections(
            tmp_path / f"{clone}-new",
            proposed_source,
            side="new",
        )
        for row in witness["retired_identity_witnesses"]:
            identity = row["identity"]
            identity_kind = row["identity_kind"]
            assert sorted(
                kind for kind, values in old_projection.items() if identity in values
            ) == row["old_domains"]
            assert sorted(
                kind for kind, values in new_projection.items() if identity in values
            ) == row["proposed_production_domains"]
            assert sorted(
                kind for kind, values in new_leaks.items() if identity in values
            ) == row["proposed_leak_domains"]


def test_tracked_design_phase_eligibility_stop_live_store_rescan_is_opt_in() -> None:
    if os.environ.get("ORCHESTRATOR_RESCAN_TRACKED_DESIGN_ELIGIBILITY") != "1":
        pytest.skip("set ORCHESTRATOR_RESCAN_TRACKED_DESIGN_ELIGIBILITY=1")

    from orchestrator.workflow_lisp.procedure_identity_retirement import (
        scan_known_state_store,
    )

    evidence = _load_json(TRACKED_DESIGN_ELIGIBILITY_STOP)
    witness = _load_json(TRACKED_DESIGN_IDENTITY_WITNESS)
    query = evidence["query"]
    store = evidence["known_state_store"]
    observed = scan_known_state_store(
        Path(store["canonical_root"]),
        retired_identities=[
            row["identity"] for row in witness["retired_identity_witnesses"]
        ],
        query_version=query["query_version"],
    )
    assert observed["normalized_scan_digest"] == store["normalized_scan_digest"]
    assert {
        key: observed[key]
        for key in store["counts"]
    } == store["counts"]


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


def test_stack_implementation_phase_historical_projection_rebuild_is_opt_in(
    tmp_path: Path,
) -> None:
    if os.environ.get("ORCHESTRATOR_REBUILD_STACK_IMPLEMENTATION_PROJECTIONS") != "1":
        pytest.skip(
            "set ORCHESTRATOR_REBUILD_STACK_IMPLEMENTATION_PROJECTIONS=1"
        )

    current_source = (TRACKED_DESIGN_INPUTS / "source.orc").read_bytes()
    proposed_source = _stack_implementation_phase_proposed_inline_source(
        current_source
    )
    witness = _load_json(STACK_IMPLEMENTATION_IDENTITY_WITNESS)
    for clone in ("clone-a", "clone-b"):
        old_projection, _ = _tracked_design_production_identity_projections(
            tmp_path / f"{clone}-old",
            current_source,
            side="old",
        )
        new_projection, new_leaks = _tracked_design_production_identity_projections(
            tmp_path / f"{clone}-new",
            proposed_source,
            side="new",
        )
        for row in witness["retired_identity_witnesses"]:
            identity = row["identity"]
            assert sorted(
                kind for kind, values in old_projection.items() if identity in values
            ) == row["old_domains"]
            assert sorted(
                kind for kind, values in new_projection.items() if identity in values
            ) == row["proposed_production_domains"]
            assert sorted(
                kind for kind, values in new_leaks.items() if identity in values
            ) == row["proposed_leak_domains"]


def test_stack_implementation_phase_eligibility_stop_live_store_rescan_is_opt_in() -> None:
    if os.environ.get("ORCHESTRATOR_RESCAN_STACK_IMPLEMENTATION_ELIGIBILITY") != "1":
        pytest.skip("set ORCHESTRATOR_RESCAN_STACK_IMPLEMENTATION_ELIGIBILITY=1")

    from orchestrator.workflow_lisp.procedure_identity_retirement import (
        scan_known_state_store,
    )

    evidence = _load_json(STACK_IMPLEMENTATION_ELIGIBILITY_STOP)
    witness = _load_json(STACK_IMPLEMENTATION_IDENTITY_WITNESS)
    query = evidence["query"]
    store = evidence["known_state_store"]
    observed = scan_known_state_store(
        Path(store["canonical_root"]),
        retired_identities=[
            row["identity"] for row in witness["retired_identity_witnesses"]
        ],
        query_version=query["query_version"],
    )
    assert observed["normalized_scan_digest"] == store["normalized_scan_digest"]
    assert {key: observed[key] for key in store["counts"]} == store["counts"]


def test_procedure_first_public_boundary_inventory_keeps_exported_wrappers(
    tmp_path: Path,
) -> None:
    inventory = _load_json(REUSE_INVENTORY)
    registry = _load_json(ROUTE_READINESS_REGISTRY)
    parity = _load_json(PARITY_TARGETS)
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

    linked_result, _ = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    work_item_exports = linked_result.graph.export_surfaces_by_name[
        "lisp_frontend_design_delta/work_item"
    ].workflows_by_name
    assert {
        "run-work-item",
        "classify-blocked-implementation-recovery",
    } <= set(work_item_exports)

    readiness_paths = {row["path"] for row in registry["surfaces"]}
    assert active_by_id[drain_id]["source_path"] in readiness_paths
    assert active_by_id[stack_id]["source_path"] in readiness_paths
    parity_entries = {
        (row["candidate"], row["entry_workflow"])
        for row in parity["targets"]
    }
    assert (
        active_by_id[stack_id]["source_path"],
        "design-plan-impl-review-stack",
    ) in parity_entries


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
    assert route["route_label"] == "wcc_default"
    assert route["readiness_label"] == "leaf_runtime_candidate"
    assert route["copy_safety"] == "preferred_current_guidance"
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

    linked_result, _ = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    selector_exports = linked_result.graph.export_surfaces_by_name[
        "lisp_frontend_design_delta/selector"
    ].workflows_by_name
    architect_exports = linked_result.graph.export_surfaces_by_name[
        "lisp_frontend_design_delta/design_gap_architect"
    ].workflows_by_name
    assert "select-next-work" in selector_exports
    assert {
        "draft-design-gap-architecture-stdlib",
        "validate-design-gap-architecture-stdlib",
        "project-design-gap-architecture-targets",
        "project-design-gap-architecture-targets-stdlib",
    } <= set(architect_exports)


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
    linked_result, _ = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    work_item_exports = linked_result.graph.export_surfaces_by_name[
        "lisp_frontend_design_delta/work_item"
    ].workflows_by_name
    assert {
        "run-work-item",
        "classify-blocked-implementation-recovery",
    } <= set(work_item_exports)
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
    public_ids = {f"public-entry:{callee}" for callee in public_callees}
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
    assert public_ids <= set(records_by_id)
    for record_id in retained_ids:
        record = records_by_id[record_id]
        assert record["record_kind"] == "internal-call"
        assert record["classification"] == "effect-adapter"
        assert record["classification"] != "public-boundary"
        assert {record["source_path"], decision_path, selector} <= set(
            record["evidence_paths"]
        )
    for callee in public_callees:
        record = records_by_id[f"public-entry:{callee}"]
        expected = expected_public_entries[callee]
        assert record["record_kind"] == "public-entry"
        assert record["classification"] == "public-boundary"
        assert record["callee"] == callee
        assert record["resolution"] == "exported-entry"
        assert record["source_path"] == expected["source_path"]
        assert record["callee_path"] == expected["source_path"]
        assert record["source_line"] == expected["source_line"]
        assert {
            "exported workflow",
            "CLI-selectable entry",
            "compiled workflows_by_name export",
        } <= set(record["public_boundary_evidence"])
        assert set(record["evidence_paths"]) == {
            expected["source_path"],
            "orchestrator/workflow_lisp/build.py",
            decision_path,
            selector,
        }

        source_lines = (REPO_ROOT / expected["source_path"]).read_text(
            encoding="utf-8"
        ).splitlines()
        definition_line = source_lines[expected["source_line"] - 1]
        local_name = callee.rsplit("::", 1)[-1]
        assert re.match(
            rf"\s*\(defworkflow\s+{re.escape(local_name)}\b",
            definition_line,
        )

    expected_sources = {
        "project-work-item-inputs": DESIGN_DELTA_BOOTSTRAP,
        "run-plan-phase": DESIGN_DELTA_PLAN_PHASE,
        "implementation-phase": DESIGN_DELTA_IMPLEMENTATION_PHASE,
        "classify-work-item-terminal": DESIGN_DELTA_PROJECTIONS,
    }
    for callee, source_path in expected_sources.items():
        source = source_path.read_text(encoding="utf-8")
        assert len(re.findall(rf"\(defworkflow\s+{callee}\b", source)) == 1
        assert not re.search(rf"\(defproc\s+{callee}\b", source)

    work_item_source = DESIGN_DELTA_WORK_ITEM.read_text(encoding="utf-8")
    assert len(re.findall(r"\(defworkflow\s+run-work-item-pending\b", work_item_source)) == 1
    assert not re.search(r"\(defproc\s+run-work-item-pending\b", work_item_source)
    assert {
        callee: len(re.findall(rf"\(call\s+{callee}\b", work_item_source))
        for callee in (*expected_sources, "run-work-item-pending")
    } == {
        "project-work-item-inputs": 2,
        "run-plan-phase": 2,
        "implementation-phase": 2,
        "classify-work-item-terminal": 2,
        "run-work-item-pending": 1,
    }

    linked_result, _ = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    for callee, module_name in {
        "project-work-item-inputs": "lisp_frontend_design_delta/bootstrap",
        "run-plan-phase": "lisp_frontend_design_delta/plan_phase",
        "implementation-phase": "lisp_frontend_design_delta/implementation_phase",
        "classify-work-item-terminal": "lisp_frontend_design_delta/projections",
    }.items():
        export_surface = linked_result.graph.export_surfaces_by_name[module_name]
        binding = export_surface.workflows_by_name[callee]
        assert binding.kind == "workflow"
        assert binding.canonical_name == f"{module_name}::{callee}"
        assert callee not in export_surface.procedures_by_name
    work_item_exports = linked_result.graph.export_surfaces_by_name[
        "lisp_frontend_design_delta/work_item"
    ]
    assert work_item_exports.workflows_by_name["run-work-item"].kind == "workflow"
    assert "run-work-item-pending" not in work_item_exports.workflows_by_name
    assert "run-work-item-pending" not in work_item_exports.procedures_by_name


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

    linked_result, _ = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    work_item_exports = linked_result.graph.export_surfaces_by_name[
        "lisp_frontend_design_delta/work_item"
    ]
    assert work_item_exports.workflows_by_name["run-work-item"].kind == "workflow"
    assert "run-work-item" not in work_item_exports.procedures_by_name
    assert callee not in work_item_exports.workflows_by_name
    assert callee not in work_item_exports.procedures_by_name
    work_item_compile = linked_result.compiled_results_by_name[
        "lisp_frontend_design_delta/work_item"
    ]
    assert callee in {
        workflow.definition.name.rsplit("::", 1)[-1]
        for workflow in work_item_compile.typed_workflows
    }
    assert callee not in {
        procedure.definition.name.rsplit("::", 1)[-1]
        for procedure in work_item_compile.typed_procedures
    }


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
    assert route["readiness_label"] == "promotion_eligible"
    assert route["route_label"] == "wcc_default"
    assert route["copy_safety"] == "preferred_current_guidance"
    assert route["parity_constrained"] is True

    source = DESIGN_DELTA_DRAIN.read_text(encoding="utf-8")
    builder = "build-drain-runtime-owned"
    assert len(re.findall(rf"\(defworkflow\s+{builder}\b", source)) == 1
    assert not re.search(rf"\(defproc\s+{builder}\b", source)
    drain_definition = source.split("  (defworkflow drain\n", 1)[1]
    assert len(re.findall(rf"\(call\s+{builder}\b", drain_definition)) == 1
    assert re.search(r"\(export\s+drain\)", source)
    assert len(re.findall(r"\(defworkflow\s+drain(?=\s)", source)) == 1

    linked_result, _ = _compile_design_delta_parent_drain_entrypoint(tmp_path)
    exports = linked_result.graph.export_surfaces_by_name[
        "lisp_frontend_design_delta/drain"
    ]
    assert exports.workflows_by_name["drain"].kind == "workflow"
    assert "drain" not in exports.procedures_by_name
    assert builder not in exports.workflows_by_name
    assert builder not in exports.procedures_by_name


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
    with _design_delta_same_path_drain_io(retained_source) as retained_reads:
        retained_result, _ = _compile_design_delta_parent_drain_entrypoint(
            retained_dir
        )
    with _design_delta_same_path_drain_io(proposed_source) as proposed_reads:
        proposed_result, _ = _compile_design_delta_parent_drain_entrypoint(
            proposed_dir
        )
    for reads, selected_sha256 in (
        (retained_reads, retained_sha256),
        (proposed_reads, proposed_sha256),
    ):
        assert reads["selected_sha256"] == selected_sha256
        assert set(reads["served_sha256"]) == {selected_sha256}
        assert reads["disk_before_sha256"] == retained_sha256
        assert reads["disk_after_sha256"] == retained_sha256
        assert reads["rejected_writes"] == []
    assert DESIGN_DELTA_DRAIN.read_bytes() == retained_source
    for result in (retained_result, proposed_result):
        assert result.diagnostics == ()
        assert result.retained_non_promotable_diagnostics == ()
        assert result.entry_result.validated_bundles[DESIGN_DELTA_PUBLIC_ENTRY]

    retained_module = retained_result.compiled_results_by_name[
        "lisp_frontend_design_delta/drain"
    ]
    proposed_module = proposed_result.compiled_results_by_name[
        "lisp_frontend_design_delta/drain"
    ]
    assert builder in {
        item.definition.name.rsplit("::", 1)[-1]
        for item in retained_module.typed_workflows
    }
    proposed_builder = next(
        item
        for item in proposed_module.typed_procedures
        if item.definition.name.rsplit("::", 1)[-1] == builder
    )
    assert proposed_builder.signature.requested_lowering_mode.value == "inline"
    assert proposed_builder.resolved_lowering_mode.value == "inline"
    assert _effect_rows(proposed_builder.transitive_effect_summary) == []

    retained_bundles = set(retained_result.validated_bundles_by_name)
    proposed_bundles = set(proposed_result.validated_bundles_by_name)
    builder_bundle = "lisp_frontend_design_delta/drain::build-drain-runtime-owned"
    assert (len(retained_bundles), len(proposed_bundles)) == (30, 29)
    assert retained_bundles - proposed_bundles == {builder_bundle}
    assert proposed_bundles - retained_bundles == set()

    retained_bundle = retained_result.entry_result.validated_bundles[
        DESIGN_DELTA_PUBLIC_ENTRY
    ]
    proposed_bundle = proposed_result.entry_result.validated_bundles[
        DESIGN_DELTA_PUBLIC_ENTRY
    ]
    retained_points = {
        point.checkpoint_id: _json_value(point)
        for point in retained_bundle.runtime_plan.lexical_checkpoint_points
    }
    proposed_points = {
        point.checkpoint_id: _json_value(point)
        for point in proposed_bundle.runtime_plan.lexical_checkpoint_points
    }
    removed_checkpoint_id = "ckpt:4dc584b1d0c80e14d36a3d5e"
    assert (len(retained_points), len(proposed_points)) == (11, 10)
    assert set(retained_points) - set(proposed_points) == {removed_checkpoint_id}
    assert set(proposed_points) - set(retained_points) == set()
    removed_checkpoint = retained_points[removed_checkpoint_id]
    call_node = (
        "root.lisp_frontend_design_delta_drain_drain__runtime_owned__call_"
        "lisp_frontend_design_delta_drain_build_drain_runtime_owned"
    )
    assert {
        "checkpoint_id": removed_checkpoint["checkpoint_id"],
        "program_point_id": removed_checkpoint["program_point_id"],
        "workflow_name": removed_checkpoint["workflow_name"],
        "presentation_key": removed_checkpoint["presentation_key"],
        "node_id": removed_checkpoint["node_id"],
        "storage": removed_checkpoint["details"]["storage"],
    } == {
        "checkpoint_id": removed_checkpoint_id,
        "program_point_id": "pp:970dd723219942ff6192649d",
        "workflow_name": DESIGN_DELTA_PUBLIC_ENTRY,
        "presentation_key": (
            "lisp_frontend_design_delta/drain::drain__runtime-owned__call_"
            "lisp_frontend_design_delta/drain::build-drain-runtime-owned"
        ),
        "node_id": call_node,
        "storage": {
            "allocation_id": (
                "alloc:lisp_frontend_design_delta_drain_drain:"
                "lexical_checkpoint_record:e7b8bf747452186a"
            ),
            "privacy": "runtime_sidecar",
            "resume_scope": "step_visit",
            "semantic_role": "lexical_checkpoint_record",
        },
    }
    common_checkpoint_ids = set(retained_points) & set(proposed_points)
    assert len(common_checkpoint_ids) == 10
    for checkpoint_id in common_checkpoint_ids:
        retained_point = deepcopy(retained_points[checkpoint_id])
        proposed_point = deepcopy(proposed_points[checkpoint_id])
        retained_restore = retained_point["details"].pop("restore")
        proposed_restore = proposed_point["details"].pop("restore")
        assert retained_point == proposed_point
        assert retained_restore != proposed_restore

    retained_nodes = retained_bundle.runtime_plan.nodes
    proposed_nodes = proposed_bundle.runtime_plan.nodes
    assert (len(retained_nodes), len(proposed_nodes)) == (111, 110)
    assert set(retained_nodes) - set(proposed_nodes) == {call_node}
    assert set(proposed_nodes) - set(retained_nodes) == set()
    retained_projection = _json_value(retained_bundle.projection)
    proposed_projection = _json_value(proposed_bundle.projection)
    assert set(retained_projection["call_boundaries"]) - set(
        proposed_projection["call_boundaries"]
    ) == {call_node}
    for key, expected_removed in (
        ("entries_by_node_id", call_node),
        ("compatibility_index_by_node_id", call_node),
    ):
        retained_rows = retained_projection[key]
        proposed_rows = proposed_projection[key]
        assert set(retained_rows) - set(proposed_rows) == {expected_removed}
        assert set(proposed_rows) - set(retained_rows) == set()
        assert sum(
            retained_rows[row_id] != proposed_rows[row_id]
            for row_id in set(retained_rows) & set(proposed_rows)
        ) == 71
    retained_by_index = retained_projection["node_id_by_compatibility_index"]
    proposed_by_index = proposed_projection["node_id_by_compatibility_index"]
    assert set(retained_by_index) - set(proposed_by_index) == {"71"}
    assert sum(
        retained_by_index[index] != proposed_by_index[index]
        for index in set(retained_by_index) & set(proposed_by_index)
    ) == 71

    retained_state = _json_value(retained_bundle.semantic_ir.state_layout)
    proposed_state = _json_value(proposed_bundle.semantic_ir.state_layout)
    assert set(retained_state) - set(proposed_state) == {
        f"state:{DESIGN_DELTA_PUBLIC_ENTRY}:presentation:{call_node}",
        f"state:{DESIGN_DELTA_PUBLIC_ENTRY}:checkpoint:top_level_node::{call_node}::static",
        f"state:{DESIGN_DELTA_PUBLIC_ENTRY}:checkpoint:call_boundary::{call_node}::static",
        f"state:{DESIGN_DELTA_PUBLIC_ENTRY}:lexical_checkpoint_point:{removed_checkpoint_id}",
        (
            f"state:{DESIGN_DELTA_PUBLIC_ENTRY}:lexical_checkpoint_index:"
            "alloc:lisp_frontend_design_delta_drain_drain:"
            "lexical_checkpoint_index:dcc1dd7f13771347"
        ),
        (
            f"state:{DESIGN_DELTA_PUBLIC_ENTRY}:lexical_checkpoint_record:"
            "alloc:lisp_frontend_design_delta_drain_drain:"
            "lexical_checkpoint_record:e7b8bf747452186a"
        ),
    }
    assert set(proposed_state) - set(retained_state) == set()

    retained_effects = _json_value(retained_bundle.semantic_ir.effects)
    proposed_effects = _json_value(proposed_bundle.semantic_ir.effects)
    builder_effect = f"effect:{DESIGN_DELTA_PUBLIC_ENTRY}:{call_node}:workflow_call"
    assert set(retained_effects) - set(proposed_effects) == {builder_effect}
    assert set(proposed_effects) - set(retained_effects) == set()
    assert all(
        retained_effects[key] == proposed_effects[key]
        for key in set(retained_effects) & set(proposed_effects)
    )

    assert workflow_public_input_contracts(retained_bundle) == (
        workflow_public_input_contracts(proposed_bundle)
    )
    assert workflow_output_contracts(retained_bundle) == workflow_output_contracts(
        proposed_bundle
    )
    assert _json_value(retained_bundle.surface.artifacts) == _json_value(
        proposed_bundle.surface.artifacts
    )
    assert _json_value(retained_bundle.surface.finalization) == _json_value(
        proposed_bundle.surface.finalization
    )
    retained_workflow = _json_value(retained_bundle.semantic_ir.workflows)[
        DESIGN_DELTA_PUBLIC_ENTRY
    ]
    proposed_workflow = _json_value(proposed_bundle.semantic_ir.workflows)[
        DESIGN_DELTA_PUBLIC_ENTRY
    ]
    assert retained_workflow["publication_ref_ids"] == proposed_workflow[
        "publication_ref_ids"
    ]

    retained_runtime_inputs = _json_value(
        workflow_runtime_input_contracts(retained_bundle)
    )
    proposed_runtime_inputs = _json_value(
        workflow_runtime_input_contracts(proposed_bundle)
    )
    changed_runtime_inputs = {
        name
        for name in retained_runtime_inputs
        if retained_runtime_inputs[name] != proposed_runtime_inputs[name]
    }
    assert changed_runtime_inputs == {"run__state-root", "run__artifact-root"}
    assert retained_runtime_inputs["run__state-root"]["default"] == "state/run"
    assert retained_runtime_inputs["run__artifact-root"]["default"] == (
        "artifacts/run"
    )
    assert "default" not in proposed_runtime_inputs["run__state-root"]
    assert "default" not in proposed_runtime_inputs["run__artifact-root"]


def _design_delta_default_state_value(type_payload: Mapping[str, object]) -> object:
    kind = type_payload.get("kind")
    if kind == "primitive":
        return {"String": "", "Bool": False, "Int": 0}[type_payload["name"]]
    if kind == "record":
        return {
            str(field["name"]): _design_delta_default_state_value(field["type"])
            for field in type_payload.get("fields", ())
        }
    if kind == "list":
        return []
    if kind == "path":
        return ""
    if kind == "enum":
        allowed = tuple(type_payload.get("allowed", ()))
        assert allowed
        return allowed[0]
    raise AssertionError(f"unsupported native state seed type: {type_payload!r}")


def _iter_design_delta_surface_steps(steps):
    if hasattr(steps, "steps"):
        steps = steps.steps
    for step in steps or ():
        yield step
        yield from _iter_design_delta_surface_steps(step.then_branch)
        yield from _iter_design_delta_surface_steps(step.else_branch)
        yield from _iter_design_delta_surface_steps(step.for_each_steps)
        for case in step.match_cases.values():
            yield from _iter_design_delta_surface_steps(case.steps)


def _seed_design_delta_native_resources(bundles, workspace: Path) -> None:
    for bundle in bundles:
        for step in _iter_design_delta_surface_steps(bundle.surface.steps):
            declaration = step.resource_transition.get("declaration")
            resource = step.resource_transition.get("resource")
            if declaration is None or resource is None:
                continue
            if declaration.resource.backing.kind != "native":
                continue
            state_path = workspace / str(resource["state_path"])
            if state_path.exists():
                continue
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(
                    {
                        "transition_schema_version": 1,
                        "resource_id": resource["resource_id"],
                        "resource_kind": resource["resource_kind"],
                        "state_version": "native:0:seed",
                        "state": _design_delta_default_state_value(
                            declaration.resource.state_type
                        ),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )


def _write_design_delta_runtime_inputs(workspace: Path) -> dict[str, object]:
    existing = {
        "docs/steering.md": "steering\n",
        "docs/design/target.md": "target\n",
        "docs/design/baseline.md": "baseline\n",
        "state/manifest.json": "{}\n",
        "state/progress.json": "{}\n",
        "artifacts/work/architecture-index.md": "index\n",
    }
    for relative_path, content in existing.items():
        target = workspace / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return {
        "steering_path": "docs/steering.md",
        "target_design_path": "docs/design/target.md",
        "baseline_design_path": "docs/design/baseline.md",
        "manifest_path": "state/manifest.json",
        "progress_ledger_path": "state/progress.json",
        "architecture_bundle_path": "state/architecture-bundle.json",
        "architecture_targets__design_gap_id": "task-1-contract-gap",
        "architecture_targets__architecture_path": "docs/plans/task-1-architecture.md",
        "architecture_targets__work_item_context_path": "artifacts/work/task-1-context.md",
        "architecture_targets__check_commands_path": "state/task-1-checks.json",
        "architecture_targets__plan_target_path": "docs/plans/task-1-plan.md",
        "existing_architecture_index_path": "artifacts/work/architecture-index.md",
    }


def _write_json_bundle(workspace: Path, relative_path: str, payload: object) -> None:
    target = Path(relative_path)
    if not target.is_absolute():
        target = workspace / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _design_delta_command_success(step_name: str, mode: CaptureMode) -> ExecutionResult:
    return ExecutionResult(
        step_name, 0, CaptureResult(mode=mode, output="ok", exit_code=0), 1
    )


def _selector_bundle(workspace: Path, *, done: bool) -> dict[str, object]:
    selection_path = "state/selector-done.json" if done else "state/selector-gap.json"
    _write_json_bundle(workspace, selection_path, {"selected": not done})
    return {
        "selection_status": "DONE" if done else "DRAFT_DESIGN_GAP",
        "selection_bundle_path": selection_path,
        "work_item_bootstrap": {
            "work_item_source": "DESIGN_GAP",
            "work_item_id": "task-1-contract-gap",
            "plan_target_path": "docs/plans/task-1-plan.md",
            "check_commands": {"commands": []},
            "architecture_path": "docs/plans/task-1-architecture.md",
        },
        "is_selected": False,
        "is_design_gap": not done,
        "is_done": done,
        "is_blocked": False,
        "blocked_reason": "",
    }


def _design_delta_artifact_projection(workspace: Path) -> dict[str, str]:
    artifacts = workspace / "artifacts"
    return {
        path.relative_to(workspace).as_posix(): _sha256_path(path)
        for path in sorted(artifacts.rglob("*"))
        if path.is_file()
    }


def _design_delta_runtime_effect_projection(state) -> dict[str, object]:
    publications = {}
    transitions = []
    for result in state["steps"].values():
        debug = result.get("debug") or {}
        if materialized := debug.get("materialize_view"):
            target = materialized["target_path"]
            if target.startswith("artifacts/"):
                publications[target] = materialized["view_digest"]
        if transition := debug.get("resource_transition"):
            transitions.append(
                {
                    "step_id": result["step_id"],
                    "resource_id": transition["resource_id"],
                    "replayed": transition["replayed"],
                }
            )
    return {"publications": publications, "resource_transitions": transitions}


def _design_delta_compile_projection(linked_result) -> dict[str, object]:
    document = build_source_map_document(
        linked_result,
        selected_name=DESIGN_DELTA_PUBLIC_ENTRY,
        display_name_resolver=lambda name: name.rsplit("::", 1)[-1],
    )
    relevant = {
        DESIGN_DELTA_PUBLIC_ENTRY,
        "lisp_frontend_design_delta/selector::select-next-work",
        "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture-stdlib",
        "lisp_frontend_design_delta/design_gap_architect::validate-design-gap-architecture-stdlib",
    }
    source_owners = {}
    for name, workflow in document.workflows.items():
        if name not in relevant:
            continue
        owner_path = Path(workflow.workflow_origin.path)
        source_owners[name] = owner_path.relative_to(REPO_ROOT).as_posix()
    workflow_source_owners = {
        name: Path(workflow.workflow_origin.path).relative_to(REPO_ROOT).as_posix()
        for name, workflow in document.workflows.items()
    }
    checkpoint_rows = {
        point.checkpoint_id: f"{point.workflow_name}::{point.presentation_key}"
        for bundle in linked_result.validated_bundles_by_name.values()
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
    }
    return {
        "source_owners": source_owners,
        "workflow_source_owners": workflow_source_owners,
        "checkpoint_ids": sorted(checkpoint_rows),
        "checkpoint_names": checkpoint_rows,
    }


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


def _design_delta_completed_finalization_proposed_inline_source(
    old_source: bytes,
) -> bytes:
    source = old_source.decode("utf-8")
    replacements = (
        (
            "  (defworkflow finalize-selected-item-from-completed-implementation\n",
            "  (defproc finalize-selected-item-from-completed-implementation\n",
            1,
        ),
        (
            "  (defproc finalize-selected-item-from-completed-implementation\n"
            "    ((implementation_phase_result ImplementationPhaseResult))\n"
            "    -> SelectedItemResult\n"
            "    (let* ((plan\n"
            "             (call project-selected-item-finalizer-approved-plan\n",
            "  (defproc finalize-selected-item-from-completed-implementation\n"
            "    ((implementation_phase_result ImplementationPhaseResult))\n"
            "    -> SelectedItemResult\n"
            "    :effects ((calls-workflow lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-approved-plan)\n"
            "              (calls-workflow lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-completed-implementation)\n"
            "              (uses-command apply_resource_transition))\n"
            "    :lowering inline\n"
            "    (let* ((plan\n"
            "             (call project-selected-item-finalizer-approved-plan\n",
            1,
        ),
        (
            "              (call finalize-selected-item-from-completed-implementation\n"
            "                :implementation_phase_result implementation)",
            "              (finalize-selected-item-from-completed-implementation\n"
            "                implementation)",
            1,
        ),
        (
            "                              (call "
            "finalize-selected-item-from-completed-implementation\n"
            "                                :implementation_phase_result implementation)",
            "                              (finalize-selected-item-from-completed-implementation\n"
            "                                implementation)",
            1,
        ),
        (
            "              (calls-workflow lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-completed-implementation)\n",
            "",
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


@contextmanager
def _design_delta_same_path_drain_io(drain_source: bytes):
    with _design_delta_same_path_source_io(
        DESIGN_DELTA_DRAIN,
        drain_source,
    ) as evidence:
        yield evidence


def _compile_design_delta_same_path_work_item_variant(
    workspace: Path,
    work_item_source: bytes,
):
    with _design_delta_same_path_work_item_io(work_item_source) as evidence:
        result, _ = _compile_design_delta_parent_drain_entrypoint(workspace)
    return result, evidence


class _DesignDeltaProcessInterruption(BaseException):
    """Test-only abrupt stop after a public-wrapper effect checkpoint commits."""


def _design_delta_first_public_resource_transition(bundle) -> object:
    candidates = [
        point
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
        and point.details["effect_boundary"]["effect_kind"]
        == "resource_transition"
    ]
    assert candidates
    return candidates[0]


def _design_delta_interrupt_after_checkpoint(
    production_hook,
    *,
    target_point: object,
    state_manager: StateManager,
    control: dict[str, object],
):
    from orchestrator.workflow_lisp.lexical_checkpoints import (
        resolve_checkpoint_index_path,
    )

    def interrupt(state, step_name, step, finalized) -> None:
        production_hook(state, step_name, step, finalized)
        if finalized.get("step_id") != target_point.node_id:
            return
        persisted = state_manager.load().steps
        matches = [
            value
            for value in persisted.values()
            if value.get("step_id") == target_point.node_id
            and value.get("status") == "completed"
        ]
        assert len(matches) == 1
        index = state_manager.read_runtime_sidecar_json(
            resolve_checkpoint_index_path(
                state_manager=state_manager,
                workflow_name=target_point.workflow_name,
                checkpoint_id=target_point.checkpoint_id,
            )
        )
        record_path = index["records"][-1]["record_path"]
        record = state_manager.read_runtime_sidecar_json(
            state_manager.workspace / record_path
        )
        assert record["completed_effect_refs"]
        control["interrupted_step_id"] = target_point.node_id
        raise _DesignDeltaProcessInterruption

    return interrupt


def _execute_design_delta_public_wrapper(
    workspace: Path,
    *,
    run_id: str,
    provider_roles: list[str],
    command_roles: list[str],
    resume: bool = False,
    interrupt_after_committed_effect: bool = False,
    work_item_source: bytes | None = None,
) -> dict[str, object]:
    workflow_relative_path = DESIGN_DELTA_DRAIN.relative_to(REPO_ROOT)
    workflow_path = workspace / workflow_relative_path
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_bytes(DESIGN_DELTA_DRAIN.read_bytes())
    if work_item_source is None:
        linked_result, _ = _compile_design_delta_parent_drain_entrypoint(workspace)
        compile_source_reads = None
    else:
        variant_compile = _compile_design_delta_same_path_work_item_variant(
            workspace,
            work_item_source,
        )
        linked_result, compile_source_reads = variant_compile
    bundle = linked_result.entry_result.validated_bundles[DESIGN_DELTA_PUBLIC_ENTRY]
    bundles = tuple(linked_result.validated_bundles_by_name.values())
    _seed_design_delta_native_resources(bundles, workspace)
    public_inputs = _write_design_delta_runtime_inputs(workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    if not resume:
        state_manager.initialize(
            workflow_relative_path.as_posix(),
            context=bundle_context_dict(bundle),
            bound_inputs=bind_workflow_inputs(
                {
                    name: workflow_runtime_input_contracts(bundle)[name]
                    for name in public_inputs
                },
                public_inputs,
                workspace,
            ),
        )

    control = {
        "provider_queue": list(provider_roles),
        "command_queue": list(command_roles),
        "provider_attempts": [],
        "provider_successes": [],
        "command_attempts": [],
    }

    def prepare_provider(_self, provider_name=None, prompt_content=None, env=None, **_kwargs):
        assert control["provider_queue"], "unexpected provider effect"
        role = control["provider_queue"].pop(0)
        bundle_path = (env or {}).get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
        assert isinstance(bundle_path, str) and bundle_path
        invocation = SimpleNamespace(
            input_mode="stdin",
            prompt=prompt_content or "",
            provider_name=provider_name,
            evidence_role=role,
            output_bundle_path=bundle_path,
        )
        return invocation, None

    def execute_provider(_self, invocation, **_kwargs):
        role = invocation.evidence_role
        control["provider_attempts"].append(role)
        payload = {
            "selector-gap": _selector_bundle(workspace, done=False),
            "selector-done": _selector_bundle(workspace, done=True),
            "architect": {"draft_status": "DRAFTED"},
        }[role]
        if role == "architect":
            _write_json_bundle(
                workspace,
                "artifacts/work/draft_architecture_bundle.json",
                {"status": "drafted"},
            )
        _write_json_bundle(workspace, invocation.output_bundle_path, payload)
        control["provider_successes"].append(role)
        return ProviderExecutionResult(0, b"ok", b"", 1)

    def execute_command(
        _self,
        step_name,
        command,
        env=None,
        output_capture=CaptureMode.TEXT,
        **_kwargs,
    ):
        bundle_path = (env or {}).get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
        assert isinstance(bundle_path, str) and bundle_path
        if str(step_name).endswith("__managed_write_roots"):
            args = list(command[4:]) if isinstance(command, list) else []
            _write_json_bundle(
                workspace,
                bundle_path,
                {
                    str(args[index]): str(args[index + 1])
                    for index in range(0, len(args), 2)
                },
            )
            return _design_delta_command_success(step_name, output_capture)
        assert control["command_queue"], "unexpected command effect"
        role = control["command_queue"].pop(0)
        assert role == "validate-architecture"
        control["command_attempts"].append(role)
        report_path = "artifacts/work/task-1-validation.md"
        report = workspace / report_path
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("validated\n", encoding="utf-8")
        _write_json_bundle(
            workspace,
            bundle_path,
            {
                "architecture_validation_status": "VALID",
                "work_item_bundle_path": report_path,
            },
        )
        return _design_delta_command_success(step_name, output_capture)

    with patch.object(
        ProviderExecutor, "prepare_invocation", prepare_provider
    ), patch.object(ProviderExecutor, "execute", execute_provider), patch.object(
        StepExecutor, "execute_command", execute_command
    ):
        executor = WorkflowExecutor(
            bundle,
            workspace,
            state_manager,
            max_retries=0,
            retry_delay_ms=0,
        )
        interruption_control: dict[str, object] = {}
        if interrupt_after_committed_effect:
            target_point = _design_delta_first_public_resource_transition(bundle)
            production_hook = executor.outcome_recorder.post_persist_hook
            assert production_hook is not None
            executor.outcome_recorder.post_persist_hook = (
                _design_delta_interrupt_after_checkpoint(
                    production_hook,
                    target_point=target_point,
                    state_manager=state_manager,
                    control=interruption_control,
                )
            )
        try:
            state = executor.execute(
                run_id=run_id if resume else None,
                resume=resume,
                on_error="stop",
            )
        except _DesignDeltaProcessInterruption:
            assert not resume
            state = state_manager.load().to_dict()

    failed_steps = {
        name: json.dumps(result.get("error"), sort_keys=True)
        for name, result in state.get("steps", {}).items()
        if isinstance(result, Mapping) and result.get("status") == "failed"
    }
    assert not control["provider_queue"], failed_steps
    assert not control["command_queue"], failed_steps
    resume_report_path = (
        state_manager.run_root
        / "workflow_lisp"
        / "checkpoints"
        / "default_resume_report.json"
    )
    projections = _design_delta_runtime_effect_projection(state)
    compile_projection = _design_delta_compile_projection(linked_result)
    return {
        "state": state,
        "provider_attempts": control["provider_attempts"],
        "provider_successes": control["provider_successes"],
        "command_attempts": control["command_attempts"],
        "interruption": interruption_control,
        "artifacts": _design_delta_artifact_projection(workspace),
        **projections,
        **compile_projection,
        "resume_report": (
            json.loads(resume_report_path.read_text(encoding="utf-8"))
            if resume_report_path.exists()
            else None
        ),
        "compile_source_reads": compile_source_reads,
    }


def test_procedure_first_design_delta_public_wrapper_runtime_contract(
    tmp_path: Path,
) -> None:
    runtime = _execute_design_delta_public_wrapper(
        tmp_path,
        run_id="procedure-first-design-delta-clean",
        provider_roles=["selector-gap", "architect", "selector-done"],
        command_roles=["validate-architecture"],
    )

    assert runtime["state"]["status"] == "completed"
    assert runtime["provider_attempts"] == [
        "selector-gap",
        "architect",
        "selector-done",
    ]
    assert runtime["provider_successes"] == runtime["provider_attempts"]
    assert runtime["command_attempts"] == ["validate-architecture"]
    assert runtime["state"]["workflow_outputs"] == {
        "return__variant": "DONE",
        "return__drain-summary__drain_status": "DONE",
        "return__drain-summary__drain_status_reason": "",
        "return__drain-summary__state_version": (
            "lisp_frontend_autonomous_drain_run_state/v1"
        ),
    }
    assert runtime["artifacts"]
    assert set(runtime["publications"]) == {
        "artifacts/work/drain-progress-report.md",
        "artifacts/work/drain_summary.json",
    }
    assert len(runtime["resource_transitions"]) == 2
    assert all(
        transition["resource_id"] == "drain-run-state"
        and transition["replayed"] is False
        for transition in runtime["resource_transitions"]
    )
    assert set(runtime["source_owners"]) == {
        DESIGN_DELTA_PUBLIC_ENTRY,
        "lisp_frontend_design_delta/selector::select-next-work",
        "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture-stdlib",
        "lisp_frontend_design_delta/design_gap_architect::validate-design-gap-architecture-stdlib",
    }
    assert runtime["checkpoint_ids"]
    assert {
        name: _projection_sha256(runtime[name])
        for name in _DESIGN_DELTA_RUNTIME_PROJECTION_DIGESTS
    } == _DESIGN_DELTA_RUNTIME_PROJECTION_DIGESTS


def test_procedure_first_design_delta_public_wrapper_resume_contract(
    tmp_path: Path,
) -> None:
    clean_workspace = tmp_path / "clean"
    interrupted_workspace = tmp_path / "interrupted"
    clean_workspace.mkdir()
    interrupted_workspace.mkdir()
    clean = _execute_design_delta_public_wrapper(
        clean_workspace,
        run_id="procedure-first-design-delta-clean",
        provider_roles=["selector-gap", "architect", "selector-done"],
        command_roles=["validate-architecture"],
    )
    first = _execute_design_delta_public_wrapper(
        interrupted_workspace,
        run_id="procedure-first-design-delta-resume",
        provider_roles=["selector-gap", "architect", "selector-done"],
        command_roles=["validate-architecture"],
        interrupt_after_committed_effect=True,
    )
    assert first["state"]["status"] == "running"
    interrupted_step_id = first["interruption"]["interrupted_step_id"]
    assert first["provider_successes"] == [
        "selector-gap",
        "architect",
        "selector-done",
    ]

    resumed = _execute_design_delta_public_wrapper(
        interrupted_workspace,
        run_id="procedure-first-design-delta-resume",
        provider_roles=[],
        command_roles=[],
        resume=True,
    )

    assert resumed["state"]["status"] == "completed"
    assert resumed["provider_attempts"] == []
    assert resumed["provider_successes"] == resumed["provider_attempts"]
    assert resumed["command_attempts"] == []
    interrupted_visits = [
        value["visit_count"]
        for value in resumed["state"]["steps"].values()
        if value.get("step_id") == interrupted_step_id
    ]
    assert interrupted_visits == [1]
    assert resumed["state"]["workflow_outputs"] == clean["state"]["workflow_outputs"]
    assert resumed["artifacts"] == clean["artifacts"]
    assert resumed["publications"] == clean["publications"]
    assert resumed["resource_transitions"] == clean["resource_transitions"]
    assert resumed["source_owners"] == clean["source_owners"]
    assert resumed["checkpoint_ids"] == clean["checkpoint_ids"]
    assert resumed["resume_report"]["status"] == "pass"
    assert resumed["resume_report"]["restore_decision"] == "RESTORED"


def test_design_delta_finalizer_hypothetical_removes_four_public_wrapper_checkpoints(
    tmp_path: Path,
) -> None:
    retained_source = DESIGN_DELTA_WORK_ITEM.read_bytes()
    proposed_source = _design_delta_finalizer_proposed_inline_source(retained_source)
    current = _execute_design_delta_public_wrapper(
        tmp_path / "current",
        run_id="finalizer-retained-current",
        provider_roles=["selector-gap", "architect", "selector-done"],
        command_roles=["validate-architecture"],
        work_item_source=retained_source,
    )
    proposed = _execute_design_delta_public_wrapper(
        tmp_path / "proposed",
        run_id="finalizer-proposed-inline",
        provider_roles=["selector-gap", "architect", "selector-done"],
        command_roles=["validate-architecture"],
        work_item_source=proposed_source,
    )

    retained_source_sha256 = "sha256:" + hashlib.sha256(retained_source).hexdigest()
    proposed_source_sha256 = "sha256:" + hashlib.sha256(proposed_source).hexdigest()
    assert retained_source_sha256 != proposed_source_sha256
    for runtime, expected_sha256 in (
        (current, retained_source_sha256),
        (proposed, proposed_source_sha256),
    ):
        reads = runtime["compile_source_reads"]
        assert reads["path"] == str(DESIGN_DELTA_WORK_ITEM.resolve())
        assert reads["selected_sha256"] == expected_sha256
        assert set(reads["counts"]) == {"read_bytes", "read_text", "open"}
        assert reads["counts"]["read_bytes"] > 0
        assert reads["counts"]["read_text"] > 0
        assert reads["total"] == sum(reads["counts"].values())
        assert set(reads["served_sha256"]) == {expected_sha256}
        assert reads["disk_before_sha256"] == retained_source_sha256
        assert reads["disk_after_sha256"] == retained_source_sha256
    assert retained_source_sha256 not in proposed["compile_source_reads"][
        "served_sha256"
    ]
    assert DESIGN_DELTA_WORK_ITEM.read_bytes() == retained_source

    assert _projection_sha256(current["checkpoint_ids"]) == (
        "sha256:d0c2ef05da988b3fb6bd93a30f426ee6dec55ed4f905b72ae6efeaa63c12e8a8"
    )
    assert _projection_sha256(proposed["checkpoint_ids"]) == (
        "sha256:275f8563b6fd7c3909f13cdf4554b570fe2fcded94c7e4fdb46385b9844a0c0d"
    )
    removed_ids = set(current["checkpoint_ids"]) - set(proposed["checkpoint_ids"])
    added_ids = set(proposed["checkpoint_ids"]) - set(current["checkpoint_ids"])
    removed = {
        checkpoint_id: current["checkpoint_names"][checkpoint_id]
        for checkpoint_id in sorted(removed_ids)
    }
    assert added_ids == set()
    assert removed == {
        "ckpt:719e087e3f3fd34effef1df2": (
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-completed-implementation::"
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-completed-implementation__"
            "implementation__call_lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-completed-implementation"
        ),
        "ckpt:a50e5dd2106381d32be8aed9": (
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-completed-implementation::"
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-completed-implementation__"
            "plan__call_lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-approved-plan"
        ),
        "ckpt:bad73d47b2fb350f033b5621": (
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-blocked-implementation::"
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-blocked-implementation__"
            "implementation__call_lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-blocked-implementation"
        ),
        "ckpt:e915cc6153281198cd61b3e7": (
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-blocked-implementation::"
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-blocked-implementation__"
            "plan__call_lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-approved-plan"
        ),
    }

    current_owners = current["workflow_source_owners"]
    proposed_owners = proposed["workflow_source_owners"]
    common_owner_keys = set(current_owners) & set(proposed_owners)
    assert {
        key: current_owners[key] for key in sorted(common_owner_keys)
    } == {
        key: proposed_owners[key] for key in sorted(common_owner_keys)
    }
    assert set(current_owners) - set(proposed_owners) == {
        (
            "lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-approved-plan"
        ),
        (
            "lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-completed-implementation"
        ),
        (
            "lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-blocked-implementation"
        ),
    }
    assert set(proposed_owners) - set(current_owners) == set()

    affected_names = {
        "project-selected-item-finalizer-approved-plan",
        "project-selected-item-finalizer-completed-implementation",
        "project-selected-item-finalizer-blocked-implementation",
    }
    for runtime in (current, proposed):
        executed_step_ids = {
            result.get("step_id", "")
            for result in runtime["state"]["steps"].values()
            if isinstance(result, Mapping)
        }
        assert all(
            affected_name not in step_id
            for affected_name in affected_names
            for step_id in executed_step_ids
        )

    # This run exercises only the unaffected selector/architect route. These
    # equalities characterize that route; they do not establish finalizer parity.
    assert current["state"]["status"] == proposed["state"]["status"] == "completed"
    for effect_projection in (
        "provider_attempts",
        "provider_successes",
        "command_attempts",
    ):
        assert proposed[effect_projection] == current[effect_projection]
    for projection in (
        "workflow_outputs",
        "artifacts",
        "publications",
        "resource_transitions",
    ):
        current_value = (
            current["state"][projection]
            if projection == "workflow_outputs"
            else current[projection]
        )
        proposed_value = (
            proposed["state"][projection]
            if projection == "workflow_outputs"
            else proposed[projection]
        )
        assert proposed_value == current_value


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
    retained_result, retained_reads = _compile_design_delta_same_path_work_item_variant(
        tmp_path / "retained",
        retained_source,
    )
    assert retained_result.entry_result.validated_bundles[DESIGN_DELTA_PUBLIC_ENTRY]
    assert retained_reads["selected_sha256"] == retained_sha256
    assert set(retained_reads["served_sha256"]) == {retained_sha256}
    assert retained_reads["disk_before_sha256"] == retained_sha256
    assert retained_reads["disk_after_sha256"] == retained_sha256

    (tmp_path / "proposed").mkdir()
    with _design_delta_same_path_work_item_io(proposed_source) as proposed_reads:
        with pytest.raises(LispFrontendCompileError) as excinfo:
            _compile_design_delta_parent_drain_entrypoint(tmp_path / "proposed")

    assert [diagnostic.code for diagnostic in excinfo.value.diagnostics] == [
        "pure_expr_operand_type_mismatch"
    ]
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.message == (
        "pure projection result type did not match the lowered contract"
    )
    diagnostic_line = proposed_text.splitlines()[diagnostic.span.start.line - 1]
    assert "BlockerClass.roadmap_conflict" in diagnostic_line
    assert "(blocker-class std/resource/BlockerClass)" in proposed_text

    assert proposed_reads["selected_sha256"] == proposed_sha256
    assert set(proposed_reads["served_sha256"]) == {proposed_sha256}
    assert proposed_reads["disk_before_sha256"] == retained_sha256
    assert proposed_reads["disk_after_sha256"] == retained_sha256
    assert DESIGN_DELTA_WORK_ITEM.read_bytes() == retained_source


def test_design_delta_completed_finalization_hypothetical_fails_shared_validation(
    tmp_path: Path,
) -> None:
    retained_source = DESIGN_DELTA_WORK_ITEM.read_bytes()
    proposed_source = _design_delta_completed_finalization_proposed_inline_source(
        retained_source
    )
    retained_sha256 = "sha256:" + hashlib.sha256(retained_source).hexdigest()
    proposed_sha256 = "sha256:" + hashlib.sha256(proposed_source).hexdigest()
    assert retained_sha256 != proposed_sha256
    proposed_text = proposed_source.decode("utf-8")
    callee = "finalize-selected-item-from-completed-implementation"
    assert len(re.findall(rf"\(defproc\s+{callee}\b", proposed_text)) == 1
    assert not re.search(rf"\(defworkflow\s+{callee}\b", proposed_text)
    assert not re.search(rf"\(call\s+{callee}\b", proposed_text)
    assert len(re.findall(rf"\({callee}\b", proposed_text)) == 2
    assert (
        f"(calls-workflow lisp_frontend_design_delta/work_item::{callee})"
        not in proposed_text
    )
    proposed_definition = proposed_text.split(
        f"  (defproc {callee}", 1
    )[1].split("\n  (defworkflow finalize-selected-item-from-blocked", 1)[0]
    assert proposed_definition.count("(calls-workflow ") == 2
    assert proposed_definition.count("(uses-command apply_resource_transition)") == 1
    assert set(
        re.findall(
            r"\((?:calls-workflow|uses-command)\s+[^)]+\)",
            proposed_definition,
        )
    ) == {
        "(calls-workflow lisp_frontend_design_delta/work_item::"
        "project-selected-item-finalizer-approved-plan)",
        "(calls-workflow lisp_frontend_design_delta/work_item::"
        "project-selected-item-finalizer-completed-implementation)",
        "(uses-command apply_resource_transition)",
    }
    assert ":lowering inline" in proposed_definition

    (tmp_path / "retained").mkdir()
    retained_result, retained_reads = _compile_design_delta_same_path_work_item_variant(
        tmp_path / "retained",
        retained_source,
    )
    assert retained_result.entry_result.validated_bundles[DESIGN_DELTA_PUBLIC_ENTRY]
    assert retained_reads["selected_sha256"] == retained_sha256
    assert set(retained_reads["served_sha256"]) == {retained_sha256}
    assert retained_reads["disk_before_sha256"] == retained_sha256
    assert retained_reads["disk_after_sha256"] == retained_sha256

    (tmp_path / "proposed").mkdir()
    with _design_delta_same_path_work_item_io(proposed_source) as proposed_reads:
        with pytest.raises(LispFrontendCompileError) as excinfo:
            _compile_design_delta_parent_drain_entrypoint(tmp_path / "proposed")

    diagnostics = excinfo.value.diagnostics
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "workflow_boundary_type_invalid",
        "workflow_boundary_type_invalid",
    ]
    expected_by_projection = {
        "project-selected-item-finalizer-completed-implementation": {
            "start": (159, 14),
            "end": (160, 73),
            "path_symbol": "__implementation__call_lisp_frontend_design_delta/"
            "work_item::project-selected-item-finalizer-completed-implementation",
            "variant_symbol": "__match_implementation__blocked",
        },
        "project-selected-item-finalizer-approved-plan": {
            "start": (156, 14),
            "end": (157, 73),
            "path_symbol": "__plan__call_lisp_frontend_design_delta/work_item::"
            "project-selected-item-finalizer-approved-plan",
            "variant_symbol": "__match_plan__blocked",
        },
    }
    observed_projections = set()
    proposed_lines = proposed_text.splitlines()
    for diagnostic in diagnostics:
        assert diagnostic.phase == "shared_validation"
        assert diagnostic.validation_pass == "shared_validation"
        assert diagnostic.authority_layer == "shared_validation"
        assert diagnostic.diagnostic_kind == "validation"
        assert diagnostic.form_path == (
            "workflow-lisp",
            "defproc",
            callee,
        )
        assert Path(diagnostic.span.start.path).resolve() == (
            DESIGN_DELTA_WORK_ITEM.resolve()
        )
        source_line = proposed_lines[diagnostic.span.start.line - 1]
        projection = next(
            name for name in expected_by_projection if name in source_line
        )
        observed_projections.add(projection)
        expected = expected_by_projection[projection]
        assert (
            diagnostic.span.start.line,
            diagnostic.span.start.column,
        ) == expected["start"]
        assert (
            diagnostic.span.end.line,
            diagnostic.span.end.column,
        ) == expected["end"]
        assert expected["path_symbol"] in diagnostic.message
        assert expected["variant_symbol"] in diagnostic.message
        assert ".artifacts.return__blocker-class" in diagnostic.message
        assert diagnostic.message.count("return__blocker-class") == 2
    assert observed_projections == set(expected_by_projection)

    assert proposed_reads["selected_sha256"] == proposed_sha256
    assert set(proposed_reads["served_sha256"]) == {proposed_sha256}
    assert proposed_reads["disk_before_sha256"] == retained_sha256
    assert proposed_reads["disk_after_sha256"] == retained_sha256
    assert proposed_reads["rejected_writes"] == []
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
    retained_result, retained_reads = _compile_design_delta_same_path_work_item_variant(
        tmp_path / "retained",
        retained_source,
    )
    (tmp_path / "proposed").mkdir()
    proposed_result, proposed_reads = _compile_design_delta_same_path_work_item_variant(
        tmp_path / "proposed",
        proposed_source,
    )
    for reads, expected_sha256 in (
        (retained_reads, retained_sha256),
        (proposed_reads, proposed_sha256),
    ):
        assert reads["selected_sha256"] == expected_sha256
        assert set(reads["served_sha256"]) == {expected_sha256}
        assert reads["disk_before_sha256"] == retained_sha256
        assert reads["disk_after_sha256"] == retained_sha256
        assert reads["rejected_writes"] == []
    assert DESIGN_DELTA_WORK_ITEM.read_bytes() == retained_source

    proposed_compile = proposed_result.compiled_results_by_name[
        "lisp_frontend_design_delta/work_item"
    ]
    pending = next(
        procedure
        for procedure in proposed_compile.typed_procedures
        if procedure.definition.name.rsplit("::", 1)[-1] == "run-work-item-pending"
    )
    assert pending.signature.requested_lowering_mode.value == "inline"
    assert pending.resolved_lowering_mode.value == "inline"
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
    assert {
        (row["kind"], row["subject"])
        for row in _effect_rows(pending.transitive_effect_summary)
    } == expected_effects
    caller = next(
        workflow
        for workflow in proposed_compile.typed_workflows
        if workflow.definition.name.rsplit("::", 1)[-1] == "run-work-item"
    )
    assert expected_effects <= {
        (row["kind"], row["subject"])
        for row in _effect_rows(caller.effect_summary)
    }
    caller_nodes = tuple(walk_expr(caller.typed_body.expr))
    assert "lisp_frontend_design_delta/work_item::run-work-item-pending" in {
        node.callee_name
        for node in caller_nodes
        if isinstance(node, ProcedureCallExpr)
    }
    assert "lisp_frontend_design_delta/work_item::run-work-item-pending" not in {
        node.callee_name for node in caller_nodes if isinstance(node, CallExpr)
    }

    retained_projection = _design_delta_compile_projection(retained_result)
    proposed_projection = _design_delta_compile_projection(proposed_result)
    removed_ids = set(retained_projection["checkpoint_ids"]) - set(
        proposed_projection["checkpoint_ids"]
    )
    added_ids = set(proposed_projection["checkpoint_ids"]) - set(
        retained_projection["checkpoint_ids"]
    )
    caller_owner = "lisp_frontend_design_delta/work_item::run-work-item"
    removed = {
        checkpoint_id: retained_projection["checkpoint_names"][checkpoint_id]
        for checkpoint_id in sorted(removed_ids)
    }
    assert removed == {
        "ckpt:086b77522a63d90a481896c2": (
            f"{caller_owner}::"
            "lisp_frontend_design_delta/work_item::run-work-item__pending__"
            "call_lisp_frontend_design_delta/work_item::run-work-item-pending"
        )
    }
    added = {
        checkpoint_id: proposed_projection["checkpoint_names"][checkpoint_id]
        for checkpoint_id in sorted(added_ids)
    }
    new_presentation_prefix = (
        "lisp_frontend_design_delta/work_item::run-work-item__pending__"
        "lisp_frontend_design_delta/work_item::run-work-item-pending_1__"
    )
    caller_namespace = f"{caller_owner}::{new_presentation_prefix}"
    assert all(
        checkpoint_name.startswith(f"{caller_owner}::{new_presentation_prefix}")
        for checkpoint_name in added.values()
    )
    assert added == {
        "ckpt:00dc7237d9abde23fb40b69b": (
            caller_namespace
            + "match_plan__approved__terminal__call_"
            "lisp_frontend_design_delta/projections::classify-work-item-terminal"
        ),
        "ckpt:09ce859d00f0962b793dfebf": (
            caller_namespace
            + "match_plan__approved__pending__match_terminal__implementation_blocked__"
            "lisp_frontend_design_delta/work_item::route-blocked-implementation_1__"
            "classification__call_lisp_frontend_design_delta/work_item::"
            "classify-blocked-implementation-recovery"
        ),
        "ckpt:1b3c82661af3b2feaa35f42b": (
            caller_namespace
            + "match_plan__approved__pending__match_terminal__plan_review_exhausted__"
            "finalized__call_lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-blocked-implementation"
        ),
        "ckpt:233ecfb0b10c3da348dc56a2": (
            caller_namespace
            + "match_plan__approved__pending__match_terminal__implementation_blocked__"
            "lisp_frontend_design_delta/work_item::route-blocked-implementation_1__"
            "match_decision__gap_design_revision_required__durability-recorded__"
            "lisp_frontend_design_delta/transitions::"
            "record-work-item-blocked-recovery-summary_1__transition-result"
        ),
        "ckpt:294b5ca0e981a654fe3bd2b0": (
            caller_namespace
            + "match_plan__approved__pending__match_terminal__implementation_blocked__"
            "lisp_frontend_design_delta/work_item::route-blocked-implementation_1__"
            "match_decision__terminal_blocked__finalized__call_"
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-blocked-implementation"
        ),
        "ckpt:30bafb11d2737afb8b1cf688": (
            caller_namespace
            + "match_plan__approved__pending__match_terminal__implementation_blocked__"
            "lisp_frontend_design_delta/work_item::route-blocked-implementation_1__"
            "match_decision__target_design_revision_required__durability-recorded__"
            "lisp_frontend_design_delta/transitions::"
            "record-work-item-blocked-recovery-summary_2__transition-result"
        ),
        "ckpt:59af01e48a3e10414e79c371": (
            caller_namespace
            + "plan__call_lisp_frontend_design_delta/plan_phase::run-plan-phase"
        ),
        "ckpt:905debcfe48342339d32bdf7": (
            caller_namespace
            + "match_plan__approved__pending__match_terminal__"
            "implementation_review_exhausted__finalized__call_"
            "lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-blocked-implementation"
        ),
        "ckpt:b629ae4c8beb869a841e46f0": (
            caller_namespace
            + "match_plan__approved__pending__match_terminal__complete__finalized__"
            "call_lisp_frontend_design_delta/work_item::"
            "finalize-selected-item-from-completed-implementation"
        ),
        "ckpt:bf70f41dfed8714340562b03": (
            caller_namespace
            + "resolved__call_lisp_frontend_design_delta/bootstrap::"
            "project-work-item-inputs"
        ),
        "ckpt:cce0b07caefb09af76cf8154": (
            caller_namespace
            + "match_plan__approved__pending__match_terminal__implementation_blocked__"
            "lisp_frontend_design_delta/work_item::route-blocked-implementation_1__"
            "match_decision__prerequisite_gap_required__durability-recorded__"
            "lisp_frontend_design_delta/transitions::"
            "record-work-item-blocked-recovery-summary_3__transition-result"
        ),
        "ckpt:e737e9259c7ab5d6d3278eb8": (
            caller_namespace
            + "match_plan__approved__implementation__call_"
            "lisp_frontend_design_delta/implementation_phase::implementation-phase"
        ),
    }


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


def _pilot_source_bytes(side: str) -> dict[str, object]:
    assert side in {"old", "new"}
    evidence_index = _load_json(PILOT_EVIDENCE / "evidence_index.json")
    manifest_binding = (
        evidence_index["artifacts"]["old_build_manifest"]
        if side == "old"
        else evidence_index["artifacts"]["new_build"]["build_manifest"]
    )
    expected_manifest_sha256 = {
        "old": "sha256:97c78179655c48cb2ac24e599c17bfb0d1d1e0960a7e31836ce0727a5777d783",
        "new": "sha256:dc21dcdc7fb5748b2442c5e9b615672c4915cd9b9fba6f69f894991c8ae0f00f",
    }[side]
    manifest_path = PILOT_EVIDENCE / side / "build_manifest.json"
    assert manifest_binding == {
        "path": manifest_path.relative_to(REPO_ROOT).as_posix(),
        "sha256": expected_manifest_sha256,
    }
    assert _sha256_path(manifest_path) == expected_manifest_sha256

    manifest = _load_json(manifest_path)
    expected_input_paths = {
        "source": f"{side}/source.orc",
        "provider_externs": "inputs/provider_externs.json",
        "prompt_externs": "inputs/prompt_externs.json",
        "command_boundaries": "inputs/command_boundaries.json",
    }
    assert set(manifest["inputs"]) == set(expected_input_paths)
    frozen_inputs: dict[str, object] = {}
    for input_name, expected_relative_path in expected_input_paths.items():
        input_binding = manifest["inputs"][input_name]
        assert input_binding["path"] == expected_relative_path
        input_path = PILOT_EVIDENCE / expected_relative_path
        assert _sha256_path(input_path) == input_binding["sha256"]
        frozen_inputs[input_name] = (
            input_path.read_bytes()
            if input_name == "source"
            else _load_json(input_path)
        )
    return {
        "build_manifest_sha256": expected_manifest_sha256,
        "source_sha256": manifest["inputs"]["source"]["sha256"],
        **frozen_inputs,
    }


def _run_tree_facts(root: Path) -> dict[str, object]:
    rows: list[tuple[str, str, str | None]] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        directories.sort()
        filenames.sort()
        current_path = Path(current)
        for name in (*directories, *filenames):
            path = current_path / name
            assert not path.is_symlink()
            relative = path.relative_to(root).as_posix()
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


def _short_name(name: str) -> str:
    return name.rsplit("::", 1)[-1]


def _json_value(value):
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _portable_contract_value(value):
    if isinstance(value, str):
        return value.replace(MODULE_NAME, MODULE_TOKEN).replace(MODULE_SLUG, "$module_slug")
    if isinstance(value, Mapping):
        return {
            _portable_contract_value(key): _portable_contract_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_portable_contract_value(item) for item in value]
    return value


def _type_contract(type_ref) -> dict[str, object]:
    contract: dict[str, object] = {"type_name": type_ref.name}
    definition = getattr(type_ref, "definition", None)
    if definition is not None:
        for field_name in ("kind", "under", "must_exist"):
            if hasattr(definition, field_name):
                contract[field_name] = _json_value(getattr(definition, field_name))
    allowed_values = getattr(type_ref, "allowed_values", ())
    if allowed_values:
        contract["allowed_values"] = list(allowed_values)
    return contract


def _public_signature_contract(compile_result) -> dict[str, object]:
    workflow = next(
        workflow
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == PUBLIC_ENTRY
    )
    signature = workflow.signature
    return_type = signature.return_type_ref
    return {
        "inputs": [
            {
                "name": name,
                "default": _json_value(signature.param_defaults.get(name)),
                **_type_contract(type_ref),
            }
            for name, type_ref in signature.params
        ],
        "outputs": [
            {
                "name": field.name,
                **_type_contract(return_type.field_types[field.name]),
            }
            for field in return_type.definition.fields
        ],
        "return_type": return_type.name,
    }


def _effect_rows(effect_summary) -> list[dict[str, str]]:
    return sorted(
        (
            {
                "kind": type(effect).__name__,
                "subject": ".".join(effect.subject),
            }
            for effect in effect_summary.transitive_effects
        ),
        key=lambda row: (row["kind"], row["subject"]),
    )


def _artifact_contracts(compile_result) -> list[dict[str, object]]:
    def contract_field(field: Mapping[str, object]) -> dict[str, object]:
        return {
            key: _json_value(field[key])
            for key in (
                "name",
                "json_pointer",
                "type",
                "under",
                "must_exist_target",
                "allowed",
            )
            if key in field
        }

    def bundle_contract(bundle: Mapping[str, object] | None):
        if bundle is None:
            return None
        return {
            "fields": [contract_field(field) for field in bundle.get("fields", ())],
        }

    def variant_contract(variant: Mapping[str, object] | None):
        if variant is None:
            return None
        return {
            "discriminant": contract_field(variant["discriminant"]),
            "shared_fields": [
                contract_field(field) for field in variant.get("shared_fields", ())
            ],
            "variants": {
                name: {
                    "fields": [
                        contract_field(field)
                        for field in definition.get("fields", ())
                    ]
                }
                for name, definition in variant.get("variants", {}).items()
            },
        }

    rows: list[dict[str, object]] = []
    for workflow_name, bundle in sorted(compile_result.validated_bundles.items()):
        for step in bundle.surface.steps:
            output_bundle = step.common.output_bundle
            variant_output = step.common.variant_output
            publishes = step.common.publishes
            if output_bundle is None and variant_output is None and not publishes:
                continue
            is_tracked_plan_step = "tracked-plan-phase" in step.name
            step_role = (
                "draft"
                if "__draft" in step.name
                else "review"
                if "__review" in step.name
                else step.name
            )
            rows.append(
                {
                    "workflow": "tracked-plan-phase"
                    if is_tracked_plan_step
                    else workflow_name,
                    "step": step_role if is_tracked_plan_step else step.name,
                    "kind": step.kind.value,
                    "output_bundle_contract": bundle_contract(output_bundle),
                    "variant_output_contract": variant_contract(variant_output),
                    "publishes": _json_value(publishes),
                }
            )
    return sorted(rows, key=lambda row: (str(row["workflow"]), str(row["step"])))


def _source_map_rows(linked_result) -> dict[str, object]:
    document = build_source_map_document(
        linked_result,
        selected_name=PUBLIC_ENTRY,
        display_name_resolver=_short_name,
    )
    rows: dict[str, object] = {}
    for workflow_name in (PUBLIC_ENTRY, TRACKED_PLAN):
        workflow = document.workflows.get(workflow_name)
        if workflow is None:
            continue
        entries = (workflow.workflow_origin, *workflow.step_ids.values())
        lineage_by_origin: dict[str, object] = {}
        expansion_by_origin: dict[str, object] = {}
        form_path_overrides: dict[str, object] = {}
        workflow_form_path = list(workflow.workflow_origin.form_path)
        for entry in entries:
            expansion = [
                    {
                        key: _json_value(getattr(frame, key))
                        for key in (
                            "macro_name",
                            "expansion_id",
                            "template_path",
                            "function_name",
                        )
                        if hasattr(frame, key)
                    }
                    for frame in entry.expansion_stack
                ]
            lineage = sorted(
                {
                        "procedure_call_site"
                        if note.startswith("procedure call site at")
                        else "procedure_definition"
                        if note.startswith("procedure definition at")
                        else note
                        for note in entry.notes
                }
            )
            if expansion:
                expansion_by_origin[entry.origin_key] = expansion
            if lineage:
                lineage_by_origin[entry.origin_key] = lineage
            if list(entry.form_path) != workflow_form_path:
                form_path_overrides[entry.origin_key] = list(entry.form_path)
        rows[workflow_name] = {
            "workflow_origin": {
                "origin_key": workflow.workflow_origin.origin_key,
                "form_path": list(workflow.workflow_origin.form_path),
            },
            "step_origin_keys": sorted(entry.origin_key for entry in workflow.step_ids.values()),
            "expansion_by_origin": expansion_by_origin,
            "lineage_by_origin": lineage_by_origin,
            "form_path_overrides": form_path_overrides,
        }
    return rows


def _runtime_contract(compile_result) -> dict[str, object]:
    state_write_roots: list[dict[str, object]] = []
    resume_checkpoints: list[dict[str, object]] = []
    lexical_checkpoints: list[dict[str, object]] = []
    for workflow_name in (PUBLIC_ENTRY, TRACKED_PLAN):
        bundle = compile_result.validated_bundles.get(workflow_name)
        if bundle is None:
            continue
        state_write_roots.extend(
            {
                "workflow": workflow_name,
                "semantic_role": allocation.semantic_role.value,
                "stable_identity": allocation.stable_identity,
            }
            for allocation in bundle.provenance.generated_path_allocations
            if "write_root" in allocation.semantic_role.value
        )
        resume_checkpoints.extend(
            {
                "checkpoint_kind": checkpoint.checkpoint_kind,
                "node_id": checkpoint.node_id,
                "presentation_key": checkpoint.presentation_key,
                "runtime_step_id_mode": checkpoint.runtime_step_id_mode,
            }
            for checkpoint in bundle.runtime_plan.resume_checkpoints
        )
        lexical_checkpoints.extend(
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "program_point_id": checkpoint.program_point_id,
                "point_kind": checkpoint.point_kind,
                "origin_key": checkpoint.origin_key,
                "presentation_key": checkpoint.presentation_key,
                "step_kind": checkpoint.details.get("step_kind"),
                "resume_policy_kind": (
                    checkpoint.details.get("effect_boundary", {})
                    .get("policy", {})
                    .get("policy_kind")
                ),
            }
            for checkpoint in bundle.runtime_plan.lexical_checkpoint_points
        )
    return {
        "state_write_roots": sorted(
            state_write_roots,
            key=lambda row: (row["workflow"], row["semantic_role"], row["stable_identity"]),
        ),
        "resume_checkpoints": resume_checkpoints,
        "lexical_checkpoints": lexical_checkpoints,
    }


def _tracked_plan_projection(linked_result) -> dict[str, object]:
    compile_result = linked_result.entry_result
    public_bundle = compile_result.validated_bundles[PUBLIC_ENTRY]
    public_workflow = next(
        workflow
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == PUBLIC_ENTRY
    )
    public_plan_steps = [
        step
        for step in public_bundle.surface.steps
        if "tracked-plan-phase" in step.name
    ]
    lowered_step_order = {
        workflow_name: [
            (
                f"{step.kind.value}:tracked-plan-phase:"
                + (
                    "draft"
                    if "__draft" in step.name
                    else "review"
                    if "__review" in step.name
                    else "match"
                    if step.kind.value == "match"
                    else "call"
                )
                if "tracked-plan-phase" in step.name
                else f"{step.kind.value}:{step.name}"
            )
            for step in bundle.surface.steps
        ]
        for workflow_name, bundle in sorted(compile_result.validated_bundles.items())
    }
    projection = {
        "schema_version": "procedure_first.tracked_plan_phase_contract.v1",
        "public_contract": {
            "module": compile_result.module.module_name,
            "entry_workflow": PUBLIC_ENTRY,
            "exported_workflows": sorted(compile_result.module.exports),
            **_public_signature_contract(compile_result),
            "terminal_outcome": {
                "terminal_node_id": public_bundle.runtime_plan.ordered_node_ids[-1],
                "terminal_node_kind": public_bundle.runtime_plan.nodes[
                    public_bundle.runtime_plan.ordered_node_ids[-1]
                ].kind,
                "finalization_entry_node_id": public_bundle.ir.finalization_entry_node_id,
            },
        },
        "artifact_contracts": _artifact_contracts(compile_result),
        "caller_visible_effects": [
            row
            for row in _effect_rows(public_workflow.effect_summary)
            if not (
                row["kind"] == "CallsWorkflowEffect"
                and row["subject"] == TRACKED_PLAN
            )
        ],
        "runtime_contract": _runtime_contract(compile_result),
        "internal_route": {
            "lowered_step_order": lowered_step_order,
            "registered_workflows": sorted(
                workflow.typed_workflow.definition.name
                for workflow in compile_result.lowered_workflows
            ),
            "public_plan_nodes": [
                {
                    "kind": step.kind.value,
                    "name": step.name,
                    "step_id": step.step_id,
                    "call_alias": step.call_alias,
                }
                for step in public_plan_steps
            ],
            "source_map": _source_map_rows(linked_result),
        },
    }
    return _portable_contract_value(projection)


def _assert_reviewed_structural_delta(
    expected_route: dict[str, object],
    actual_route: dict[str, object],
) -> None:
    if actual_route == expected_route:
        return

    assert actual_route["registered_workflows"] == [
        name
        for name in expected_route["registered_workflows"]
        if name != TRACKED_PLAN_TOKEN
    ]
    expected_orders = expected_route["lowered_step_order"]
    actual_orders = actual_route["lowered_step_order"]
    expected_public_order = expected_orders[PUBLIC_ENTRY_TOKEN]
    tracked_order = expected_orders[TRACKED_PLAN_TOKEN]
    expected_inline_public_order: list[str] = []
    for step in expected_public_order:
        if step == "call:tracked-plan-phase:call":
            expected_inline_public_order.extend(tracked_order)
        else:
            expected_inline_public_order.append(step)
    assert actual_orders[PUBLIC_ENTRY_TOKEN] == expected_inline_public_order
    assert {
        name: order
        for name, order in actual_orders.items()
        if name != PUBLIC_ENTRY_TOKEN
    } == {
        name: order
        for name, order in expected_orders.items()
        if name not in {PUBLIC_ENTRY_TOKEN, TRACKED_PLAN_TOKEN}
    }
    old_call_node = expected_route["public_plan_nodes"]
    assert len(old_call_node) == 1
    old_call_node = old_call_node[0]
    assert old_call_node["kind"] == "call"
    assert old_call_node["call_alias"] == TRACKED_PLAN_TOKEN
    inline_name_prefix = old_call_node["name"].replace(
        f"__call_{TRACKED_PLAN_TOKEN}",
        f"__{TRACKED_PLAN_TOKEN}_1",
    )
    inline_step_id_prefix = old_call_node["step_id"].replace(
        "__call_$module_slug_tracked_plan_phase",
        "__$module_slug_tracked_plan_phase_1",
    )
    inline_roles = [step.rsplit(":", 1)[-1] for step in tracked_order]
    assert inline_roles == ["draft", "review", "match"]
    expected_inline_nodes = [
        {
            "kind": "provider",
            "name": f"{inline_name_prefix}__draft",
            "step_id": f"{inline_step_id_prefix}__draft",
            "call_alias": None,
        },
        {
            "kind": "provider",
            "name": f"{inline_name_prefix}__review",
            "step_id": f"{inline_step_id_prefix}__review",
            "call_alias": None,
        },
        {
            "kind": "match",
            "name": f"{inline_name_prefix}__match_review",
            "step_id": f"{inline_step_id_prefix}__match_review",
            "call_alias": None,
        },
    ]
    assert actual_route["public_plan_nodes"] == expected_inline_nodes

    expected_source_map = expected_route["source_map"]
    actual_source_map = actual_route["source_map"]
    assert TRACKED_PLAN_TOKEN not in actual_source_map
    assert set(actual_source_map) == {PUBLIC_ENTRY_TOKEN}
    expected_public_source = expected_source_map[PUBLIC_ENTRY_TOKEN]
    actual_public_source = actual_source_map[PUBLIC_ENTRY_TOKEN]
    assert actual_public_source["workflow_origin"] == expected_public_source["workflow_origin"]

    def without_tracked_plan_origins(values):
        def is_inline_route_origin(origin_key: str) -> bool:
            return (
                "tracked-plan-phase" in origin_key
                or "tracked_plan_phase" in origin_key
            )

        if isinstance(values, list):
            return [value for value in values if not is_inline_route_origin(value)]
        return {
            origin_key: value
            for origin_key, value in values.items()
            if not is_inline_route_origin(origin_key)
        }

    for field_name in (
        "step_origin_keys",
        "expansion_by_origin",
        "lineage_by_origin",
        "form_path_overrides",
    ):
        assert without_tracked_plan_origins(actual_public_source[field_name]) == (
            without_tracked_plan_origins(expected_public_source[field_name])
        )
    inline_origin_keys = {
        origin_key
        for origin_key in actual_public_source["step_origin_keys"]
        if "tracked-plan-phase" in origin_key or "tracked_plan_phase" in origin_key
    }
    for node in expected_inline_nodes:
        assert any(node["name"] in origin_key for origin_key in inline_origin_keys)
        assert any(
            node["step_id"].removeprefix("root.") in origin_key
            for origin_key in inline_origin_keys
        )
    inline_form_paths = actual_public_source["form_path_overrides"]
    assert {
        tuple(form_path)
        for origin_key, form_path in inline_form_paths.items()
        if origin_key in inline_origin_keys
    } == {("workflow-lisp", "defproc", "tracked-plan-phase")}
    assert inline_origin_keys - set(inline_form_paths)
    inline_lineage_labels = {
        lineage
        for origin_key, lineages in actual_public_source["lineage_by_origin"].items()
        if origin_key in inline_origin_keys
        for lineage in lineages
    }
    assert inline_lineage_labels >= {
        "procedure_call_site",
        "procedure_definition",
    }


def _assert_provisional_runtime_delta(
    expected_runtime: dict[str, object],
    actual_runtime: dict[str, object],
) -> None:
    frozen_runtime = _load_json(BASELINE)["runtime_contract"]
    assert expected_runtime == frozen_runtime

    def partition_rows(rows, *, key, candidate_keys):
        candidate_key_set = set(candidate_keys)
        candidates = [row for row in rows if key(row) in candidate_key_set]
        preserved = [row for row in rows if key(row) not in candidate_key_set]
        assert tuple(key(row) for row in candidates) == candidate_keys
        assert len({key(row) for row in rows}) == len(rows)
        return candidates, preserved

    expected_write_roots = expected_runtime["state_write_roots"]
    actual_write_roots = actual_runtime["state_write_roots"]
    expected_resume = expected_runtime["resume_checkpoints"]
    actual_resume = actual_runtime["resume_checkpoints"]
    expected_lexical = expected_runtime["lexical_checkpoints"]
    actual_lexical = actual_runtime["lexical_checkpoints"]
    for rows in (
        expected_write_roots,
        actual_write_roots,
        expected_resume,
        actual_resume,
        expected_lexical,
        actual_lexical,
    ):
        assert isinstance(rows, list)

    old_write_roots, preserved_write_roots = partition_rows(
        expected_write_roots,
        key=lambda row: row["stable_identity"],
        candidate_keys=_RETIRED_OLD_WRITE_ROOT_KEYS,
    )
    old_resume, preserved_resume = partition_rows(
        expected_resume,
        key=lambda row: (row["checkpoint_kind"], row["node_id"]),
        candidate_keys=_RETIRED_OLD_RESUME_KEYS,
    )
    old_lexical, preserved_lexical = partition_rows(
        expected_lexical,
        key=lambda row: row["checkpoint_id"],
        candidate_keys=_RETIRED_OLD_LEXICAL_KEYS,
    )

    new_write_root_keys = tuple(
        row["stable_identity"] for row in _NEW_INLINE_WRITE_ROOT_ROWS
    )
    new_resume_keys = tuple(
        (row["checkpoint_kind"], row["node_id"])
        for row in _NEW_INLINE_RESUME_ROWS
    )
    new_lexical_keys = tuple(row["checkpoint_id"] for row in _NEW_INLINE_LEXICAL_ROWS)
    new_write_roots, actual_preserved_write_roots = partition_rows(
        actual_write_roots,
        key=lambda row: row["stable_identity"],
        candidate_keys=new_write_root_keys,
    )
    new_resume, actual_preserved_resume = partition_rows(
        actual_resume,
        key=lambda row: (row["checkpoint_kind"], row["node_id"]),
        candidate_keys=new_resume_keys,
    )
    new_lexical, actual_preserved_lexical = partition_rows(
        actual_lexical,
        key=lambda row: row["checkpoint_id"],
        candidate_keys=new_lexical_keys,
    )

    assert old_write_roots == [
        row
        for row in frozen_runtime["state_write_roots"]
        if row["stable_identity"] in set(_RETIRED_OLD_WRITE_ROOT_KEYS)
    ]
    assert old_resume == [
        row
        for row in frozen_runtime["resume_checkpoints"]
        if (row["checkpoint_kind"], row["node_id"])
        in set(_RETIRED_OLD_RESUME_KEYS)
    ]
    assert old_lexical == [
        row
        for row in frozen_runtime["lexical_checkpoints"]
        if row["checkpoint_id"] in set(_RETIRED_OLD_LEXICAL_KEYS)
    ]
    assert new_write_roots == list(_NEW_INLINE_WRITE_ROOT_ROWS)
    assert new_resume == list(_NEW_INLINE_RESUME_ROWS)
    assert new_lexical == list(_NEW_INLINE_LEXICAL_ROWS)

    assert actual_preserved_write_roots == preserved_write_roots
    assert actual_preserved_resume == preserved_resume
    assert actual_preserved_lexical == preserved_lexical
    assert len(preserved_write_roots) == 4
    assert len(preserved_resume) == 4
    assert len(preserved_lexical) == 2

    assert actual_write_roots == [*new_write_roots, *preserved_write_roots]
    assert actual_resume == [
        preserved_resume[0],
        *new_resume,
        *preserved_resume[1:],
    ]
    assert actual_lexical == [
        preserved_lexical[0],
        *new_lexical,
        preserved_lexical[1],
    ]


@pytest.mark.parametrize(
    "corruption",
    ("preserved_public", "retired_old_candidate", "inline_candidate"),
)
def test_provisional_runtime_delta_rejects_identity_corruption(
    tracked_plan_compile,
    corruption: str,
) -> None:
    expected_runtime = deepcopy(_load_json(BASELINE)["runtime_contract"])
    actual_runtime = deepcopy(
        _tracked_plan_projection(tracked_plan_compile)["runtime_contract"]
    )

    if corruption == "preserved_public":
        row = next(
            row
            for row in actual_runtime["resume_checkpoints"]
            if row["presentation_key"]
            == f"{PUBLIC_ENTRY_TOKEN}__design__call_$module::tracked-design-phase"
            and row["checkpoint_kind"] == "call_boundary"
        )
        row["runtime_step_id_mode"] = "corrupt"
    elif corruption == "retired_old_candidate":
        row = next(
            row
            for row in expected_runtime["lexical_checkpoints"]
            if row["presentation_key"] == "$module::tracked-plan-phase__draft"
        )
        row["checkpoint_id"] = f"{row['checkpoint_id']}:corrupt"
    else:
        row = next(
            row
            for row in actual_runtime["state_write_roots"]
            if "tracked-plan-phase_1__draft" in row["stable_identity"]
        )
        row["stable_identity"] = f"{row['stable_identity']}:corrupt"

    with pytest.raises(AssertionError):
        _assert_provisional_runtime_delta(expected_runtime, actual_runtime)


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
    assert TRACKED_PLAN not in {
        workflow.typed_workflow.definition.name
        for workflow in compile_result.lowered_workflows
    }
    public_bundle = compile_result.validated_bundles[PUBLIC_ENTRY]
    assert [
        step.kind.value
        for step in public_bundle.surface.steps
        if "tracked-plan-phase" in step.name
    ] == ["provider", "provider", "match"]


def test_post_edit_tracked_plan_phase_does_not_use_schema1_iteration_override_across_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_predicate = procedure_lowering._schema1_iteration_private_override_applies
    active_route: list[str | None] = [None]
    predicate_call_counts = {"legacy": 0, "wcc_m4": 0}
    tracked_plan_decisions = {"legacy": [], "wcc_m4": []}

    def spy_on_override_predicate(procedure, *, context):
        route = active_route[0]
        assert route is not None
        predicate_call_counts[route] += 1
        decision = original_predicate(procedure, context=context)
        if procedure.definition.name == TRACKED_PLAN:
            tracked_plan_decisions[route].append(decision)
        return decision

    monkeypatch.setattr(
        procedure_lowering,
        "_schema1_iteration_private_override_applies",
        spy_on_override_predicate,
    )

    compile_results = {}
    for route in ("legacy", "wcc_m4"):
        active_route[0] = route
        compile_results[route] = compile_stage3_entrypoint(
            EXAMPLE,
            source_roots=(WORKFLOWS,),
            entry_workflow="design-plan-impl-review-stack",
            provider_externs=_load_json(
                MIGRATION_INPUTS / "design_plan_impl_stack.providers.json"
            ),
            prompt_externs=_load_json(
                MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json"
            ),
            command_boundaries=_load_json(
                MIGRATION_INPUTS / "design_plan_impl_stack.commands.json"
            ),
            validate_shared=True,
            workspace_root=REPO_ROOT,
            lowering_route=route,
        )
    active_route[0] = None

    assert tracked_plan_decisions["legacy"]
    assert not any(tracked_plan_decisions["legacy"])
    assert predicate_call_counts["wcc_m4"] == 0
    assert tracked_plan_decisions["wcc_m4"] == []
    for linked_result in compile_results.values():
        compile_result = linked_result.entry_result
        procedure = next(
            procedure
            for procedure in compile_result.typed_procedures
            if procedure.definition.name == TRACKED_PLAN
        )
        assert procedure.signature.requested_lowering_mode.value == "inline"
        assert procedure.resolved_lowering_mode.value == "inline"
        assert procedure.generated_workflow_name is None
        assert not any(
            workflow.typed_workflow.definition.name == TRACKED_PLAN
            or workflow.typed_workflow.definition.name.startswith(f"{TRACKED_PLAN}.")
            for workflow in compile_result.lowered_workflows
        )


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
    actual = _tracked_plan_projection(tracked_plan_compile)

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
    actual_route = actual.pop("internal_route")
    expected_runtime = expected.pop("runtime_contract")
    actual_runtime = actual.pop("runtime_contract")
    assert expected == actual
    _assert_reviewed_structural_delta(expected_route, actual_route)
    _assert_provisional_runtime_delta(expected_runtime, actual_runtime)


def test_tracked_plan_phase_root_checksum_negative_is_pre_executor_and_byte_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.cli.commands import resume as resume_command
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor

    old_frozen = _pilot_source_bytes("old")
    new_frozen = _pilot_source_bytes("new")
    old_source = old_frozen["source"]
    new_source = new_frozen["source"]
    old_checksum = old_frozen["source_sha256"]
    new_checksum = new_frozen["source_sha256"]
    assert isinstance(old_source, bytes)
    assert isinstance(new_source, bytes)
    assert isinstance(old_checksum, str)
    assert isinstance(new_checksum, str)
    assert old_frozen["build_manifest_sha256"] == (
        "sha256:97c78179655c48cb2ac24e599c17bfb0d1d1e0960a7e31836ce0727a5777d783"
    )
    assert new_frozen["build_manifest_sha256"] == (
        "sha256:dc21dcdc7fb5748b2442c5e9b615672c4915cd9b9fba6f69f894991c8ae0f00f"
    )
    assert old_checksum != new_checksum
    assert new_source == EXAMPLE.read_bytes()

    workspace = tmp_path / "workspace"
    workflow_path = workspace / "workflows" / "examples" / EXAMPLE.name
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_bytes(old_source)

    run_id = "tracked-plan-root-checksum-negative"
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state = state_manager.initialize(str(workflow_path))
    assert state.workflow_checksum == old_checksum
    state.status = "failed"
    state.steps = {
        "synthetic-old-boundary": {
            "status": "completed",
            "step_id": _OLD_CALL_NODE_ID,
            "exit_code": 0,
        }
    }
    state_manager._write_state()
    retained_checkpoint = (
        state_manager.run_root
        / "workflow_lisp"
        / "checkpoints"
        / "records"
        / "ckpt:synthetic-old"
        / "record:synthetic-old.json"
    )
    retained_checkpoint.parent.mkdir(parents=True)
    retained_checkpoint.write_bytes(b'{"status":"completed"}\n')

    workflow_path.write_bytes(new_source)
    assert state_manager.calculate_checksum(workflow_path) == new_checksum

    current_compile = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(workspace / "workflows",),
        provider_externs=new_frozen["provider_externs"],
        prompt_externs=new_frozen["prompt_externs"],
        command_boundaries=new_frozen["command_boundaries"],
        validate_shared=True,
        workspace_root=workspace,
    )
    current_bundle = current_compile.validated_bundles_by_name[PUBLIC_ENTRY]
    before_state_bytes = state_manager.state_file.read_bytes()
    before_tree = _run_tree_facts(state_manager.run_root)
    loader_calls: list[Path] = []

    def load_current_pilot_bundle(**kwargs):
        loader_calls.append(Path(kwargs["workflow_path"]).resolve())
        return current_bundle

    def unexpected_runtime_call(*_args, **_kwargs):
        raise AssertionError(
            "actual pilot root checksum mismatch reached executor/provider/command execution"
        )

    monkeypatch.setattr(
        resume_command,
        "_load_resume_workflow_bundle",
        load_current_pilot_bundle,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_execute_provider_with_context",
        unexpected_runtime_call,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_execute_command_with_context",
        unexpected_runtime_call,
    )
    monkeypatch.setattr(resume_command, "WorkflowExecutor", unexpected_runtime_call)
    monkeypatch.chdir(workspace)

    result = resume_command.resume_workflow(
        run_id=run_id,
        repair=False,
        force_restart=False,
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "checksum" in captured.err.lower()
    assert loader_calls == [workflow_path.resolve()]
    assert state_manager.state_file.read_bytes() == before_state_bytes
    assert _run_tree_facts(state_manager.run_root) == before_tree


def test_tracked_plan_phase_callee_checksum_negative_is_pre_child_and_no_remap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow.executable_ir import CallBoundaryNode
    from orchestrator.workflow.executor import WorkflowExecutor
    from tests.workflow_bundle_helpers import bundle_context_dict

    old_frozen = _pilot_source_bytes("old")
    new_frozen = _pilot_source_bytes("new")
    old_source = old_frozen["source"]
    new_source = new_frozen["source"]
    old_checksum = old_frozen["source_sha256"]
    new_checksum = new_frozen["source_sha256"]
    assert isinstance(old_source, bytes)
    assert isinstance(new_source, bytes)
    assert isinstance(old_checksum, str)
    assert isinstance(new_checksum, str)
    assert old_frozen["build_manifest_sha256"] == (
        "sha256:97c78179655c48cb2ac24e599c17bfb0d1d1e0960a7e31836ce0727a5777d783"
    )
    assert new_frozen["build_manifest_sha256"] == (
        "sha256:dc21dcdc7fb5748b2442c5e9b615672c4915cd9b9fba6f69f894991c8ae0f00f"
    )
    assert old_checksum != new_checksum
    assert new_source == EXAMPLE.read_bytes()

    workspace = tmp_path / "workspace"
    workflow_path = workspace / "workflows" / "examples" / EXAMPLE.name
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_bytes(old_source)
    compiled_old = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(workspace / "workflows",),
        provider_externs=old_frozen["provider_externs"],
        prompt_externs=old_frozen["prompt_externs"],
        command_boundaries=old_frozen["command_boundaries"],
        validate_shared=True,
        workspace_root=workspace,
    )
    parent_bundle = compiled_old.validated_bundles_by_name[PUBLIC_ENTRY]
    callee_bundle = compiled_old.validated_bundles_by_name[TRACKED_PLAN]
    assert callee_bundle.provenance.workflow_path == workflow_path

    plan_call = next(
        node
        for node in parent_bundle.ir.nodes.values()
        if isinstance(node, CallBoundaryNode) and node.call_alias == TRACKED_PLAN
    )
    design_call = next(
        node
        for node in parent_bundle.ir.nodes.values()
        if isinstance(node, CallBoundaryNode)
        and node.call_alias.endswith("::tracked-design-phase")
    )
    plan_step = {
        "name": plan_call.presentation_name,
        "step_id": plan_call.step_id,
        "call": plan_call.call_alias,
    }

    design_path = workspace / "docs" / "plans" / "synthetic-design.md"
    design_path.parent.mkdir(parents=True)
    design_path.write_text("# Synthetic design\n", encoding="utf-8")
    state_manager = StateManager(
        workspace=workspace,
        run_id="tracked-plan-callee-checksum-negative",
    )
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(parent_bundle),
    )
    assert state_manager.state is not None
    state = state_manager.state.to_dict()
    state["bound_inputs"] = {
        "plan_target_path": "docs/plans/synthetic-plan.md",
        "plan_review_report_target_path": "artifacts/review/synthetic-plan-review.md",
    }
    state["steps"] = {
        design_call.presentation_name: {
            "status": "completed",
            "step_id": design_call.step_id,
            "artifacts": {"return__design_path": "docs/plans/synthetic-design.md"},
        }
    }
    state["step_visits"] = {plan_call.presentation_name: 1}

    parent_executor = WorkflowExecutor(parent_bundle, workspace, state_manager)
    parent_executor.resume_mode = True
    plan_projection = parent_bundle.projection.entries_by_node_id[plan_call.node_id]
    assert isinstance(plan_projection.compatibility_index, int)
    parent_executor.current_step = plan_projection.compatibility_index
    assert plan_call.step_id == _OLD_CALL_NODE_ID.replace("$module_slug", MODULE_SLUG)
    frame_id = parent_executor.call_executor.frame_id(plan_step, state)
    assert frame_id == f"{plan_call.step_id}::visit::1"
    old_frame = {
        "call_frame_id": frame_id,
        "call_step_name": plan_call.presentation_name,
        "call_step_id": plan_call.step_id,
        "import_alias": TRACKED_PLAN,
        "workflow_file": workflow_path.relative_to(workspace).as_posix(),
        "status": "running",
        "state": {
            "workflow_file": workflow_path.relative_to(workspace).as_posix(),
            "workflow_checksum": old_checksum,
            "status": "running",
            "steps": {
                "synthetic-old-provider": {
                    "status": "completed",
                    "step_id": _OLD_PRIVATE_NODE_BASE,
                }
            },
        },
    }
    state["call_frames"] = {frame_id: deepcopy(old_frame)}
    state_manager.state.bound_inputs = deepcopy(state["bound_inputs"])
    state_manager.state.steps = deepcopy(state["steps"])
    state_manager.state.step_visits = deepcopy(state["step_visits"])
    state_manager.state.call_frames = deepcopy(state["call_frames"])
    state_manager._write_state()
    state = state_manager.state.to_dict()
    before_frames = deepcopy(state["call_frames"])
    before_frame_ids = tuple(sorted(before_frames))
    before_state_bytes = state_manager.state_file.read_bytes()
    before_tree = _run_tree_facts(state_manager.run_root)
    assert _load_json(state_manager.state_file)["call_frames"] == before_frames

    workflow_path.write_bytes(new_source)
    assert state_manager.calculate_checksum(workflow_path) == new_checksum

    def unexpected_runtime_call(*_args, **_kwargs):
        raise AssertionError(
            "actual pilot callee checksum mismatch reached child/provider/command execution"
        )

    monkeypatch.setattr(
        WorkflowExecutor,
        "_execute_provider_with_context",
        unexpected_runtime_call,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_execute_command_with_context",
        unexpected_runtime_call,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.WorkflowExecutor",
        unexpected_runtime_call,
    )

    result = parent_executor.call_executor.execute_call(plan_step, state)

    assert result["status"] == "failed"
    assert result["error"]["type"] == "call_resume_checksum_mismatch"
    assert result["error"]["context"] == {
        "step": plan_call.presentation_name,
        "call": TRACKED_PLAN,
        "call_frame_id": frame_id,
        "workflow_file": workflow_path.relative_to(workspace).as_posix(),
        "persisted_checksum": old_checksum,
        "current_checksum": new_checksum,
        "reason": "workflow_modified",
    }
    assert state["call_frames"] == before_frames
    assert tuple(sorted(state["call_frames"])) == before_frame_ids == (frame_id,)
    assert not any("::retry::" in candidate for candidate in state["call_frames"])
    assert state_manager.state_file.read_bytes() == before_state_bytes
    assert _load_json(state_manager.state_file)["call_frames"] == before_frames
    assert _run_tree_facts(state_manager.run_root) == before_tree


def test_tracked_plan_phase_checksum_evidence_projection_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.cli.commands import resume as resume_command
    from orchestrator.cli.commands import run as run_command
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor

    def forbidden_runtime(*_args, **_kwargs):
        raise AssertionError("checksum evidence replay reached runtime authority")

    monkeypatch.setattr(StateManager, "initialize", forbidden_runtime)
    monkeypatch.setattr(WorkflowExecutor, "__init__", forbidden_runtime)
    monkeypatch.setattr(run_command, "run_workflow", forbidden_runtime)
    monkeypatch.setattr(resume_command, "resume_workflow", forbidden_runtime)
    run_roots = (
        REPO_ROOT / ".orchestrate" / "runs",
        REPO_ROOT
        / ".orchestrate"
        / "procedure-first-pilot-evidence"
        / "tracked-plan-phase"
        / "workspace"
        / ".orchestrate"
        / "runs",
    )
    before_run_directories = {
        root: tuple(sorted(path.name for path in root.iterdir())) for root in run_roots
    }

    old_manifest = _load_json(PILOT_EVIDENCE / "old" / "build_manifest.json")
    new_manifest = _load_json(PILOT_EVIDENCE / "new" / "build_manifest.json")
    record = _load_json(PILOT_EVIDENCE / "retirement_record.json")
    _assert_callee_characterization(record)
    root_path = PILOT_EVIDENCE / "evidence" / "root_checksum_characterization.json"
    root_characterization = _load_json(root_path)
    root_projection = root_characterization["projection"]
    expected_root_details = {
        "command": (
            "7e4b3428 tests/test_resume_command.py::"
            "test_default_resume_root_checksum_mismatch_is_pre_executor_and_byte_immutable"
        ),
        "default_resume": True,
        "observability_overrides": False,
        "cli_overrides": False,
        "exit_status": 1,
        "tree_immutability": "before_equals_after",
        "executor_constructed": False,
        "provider_executed": False,
        "command_executed": False,
    }
    expected_claim_boundary = {
        "actual_subject_rejection": "not_asserted",
        "cross_source_compatibility": "not_asserted",
        "runtime_authority": "none",
    }
    assert set(root_characterization) == {"schema", "projection", "projection_sha256"}
    assert root_characterization["schema"] == "workflow_lisp_root_checksum_characterization.v1"
    assert set(root_projection) == {"details", "claim_boundary"}
    assert root_projection["details"] == expected_root_details
    assert root_projection["claim_boundary"] == expected_claim_boundary
    assert root_characterization["projection_sha256"] == _projection_sha256(
        root_projection
    )
    root_record = record["checksum_evidence"]["root"]
    assert root_record == {
        "evidence_mode": "generic_characterization",
        **expected_root_details,
        "characterization_path": root_path.relative_to(REPO_ROOT).as_posix(),
        "characterization_sha256": (
            "sha256:" + hashlib.sha256(root_path.read_bytes()).hexdigest()
        ),
        "projection_sha256": root_characterization["projection_sha256"],
    }
    assert "before_tree_digest" not in root_record
    assert "after_tree_digest" not in root_record
    assert "before_tree_digest" not in root_projection["details"]
    assert "after_tree_digest" not in root_projection["details"]
    assert (
        "checksum_provenance.root=evidence/root_checksum_characterization.json#"
        + root_record["characterization_sha256"]
    ) in record["supporting_labels"]

    callee = _load_json(
        PILOT_EVIDENCE / "evidence" / "callee_checksum_characterization.json"
    )
    assert callee["schema"] == "procedure_first_pilot_checksum_characterization.v1"
    assert callee["scope"] == {
        "classification": (
            "accepted generic guard characterization bound to actual pilot checksum delta"
        ),
        "not_live_old_run_resume": True,
        "not_actual_pilot_rejection_negative": True,
        "not_cross_source_compatibility": True,
    }
    assert callee["projection"]["guard_provenance"] == {
        "commit": "e4f2ecbeb6203554aa1b70b54156ca469bbf3687",
        "nodeid": (
            "tests/test_resume_command.py::"
            "test_call_subworkflow_resume_rejects_imported_workflow_checksum_mismatch"
        ),
        "mismatch_identity": (
            "examples/design_plan_impl_review_stack_v2_call::tracked-plan-phase"
        ),
        "guard_result": "rejected_before_child_execution_without_identity_remap",
    }
    assert callee["projection"]["pilot_checksum_delta"] == {
        "old": {
            "source_sha256": old_manifest["inputs"]["source"]["sha256"],
            "build_manifest_sha256": (
                "sha256:97c78179655c48cb2ac24e599c17bfb0d1d1e0960a7e31836ce0727a5777d783"
            ),
        },
        "new": {
            "source_sha256": new_manifest["inputs"]["source"]["sha256"],
            "build_manifest_sha256": (
                "sha256:dc21dcdc7fb5748b2442c5e9b615672c4915cd9b9fba6f69f894991c8ae0f00f"
            ),
        },
        "source_checksum_changed": True,
        "build_manifest_checksum_changed": True,
    }
    assert callee["projection_sha256"] == _projection_sha256(callee["projection"])

    after_run_directories = {
        root: tuple(sorted(path.name for path in root.iterdir())) for root in run_roots
    }
    assert after_run_directories == before_run_directories


def test_tracked_plan_phase_retirement_record_replays_final_scan_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.cli.commands import resume as resume_command
    from orchestrator.cli.commands import run as run_command
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor
    from orchestrator.workflow_lisp import procedure_identity_retirement as retirement

    def forbidden_runtime(*_args, **_kwargs):
        raise AssertionError("retirement record replay reached runtime authority")

    monkeypatch.setattr(StateManager, "initialize", forbidden_runtime)
    monkeypatch.setattr(WorkflowExecutor, "__init__", forbidden_runtime)
    monkeypatch.setattr(run_command, "run_workflow", forbidden_runtime)
    monkeypatch.setattr(resume_command, "resume_workflow", forbidden_runtime)
    scan_evidence = _load_json(PILOT_EVIDENCE / "final_known_store_scans.json")
    retained_scans = {
        Path(scan["scanner_result"]["root"]).resolve(): scan["scanner_result"]
        for scan in scan_evidence["scans"].values()
    }
    expected_identities = frozenset(scan_evidence["old_identity_query"]["identities"])
    observed_queries: list[Path] = []

    def retained_scan_only(root, *, retired_identities, query_version):
        canonical = Path(root).resolve()
        assert canonical in retained_scans
        assert query_version == "procedure-identity-store-query.v1"
        assert frozenset(retired_identities) == expected_identities
        observed_queries.append(canonical)
        return deepcopy(retained_scans[canonical])

    monkeypatch.setattr(retirement, "scan_known_state_store", retained_scan_only)
    run_roots = tuple(retained_scans)
    before_run_directories = {
        root: tuple(sorted(path.name for path in root.iterdir())) for root in run_roots
    }
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
    record = retirement.load_retirement_record(record_path)
    result = retirement.validate_retirement_record(record, repo_root=REPO_ROOT)

    assert result.valid is True
    assert result.issues == ()
    assert set(observed_queries) == set(retained_scans)
    after_run_directories = {
        root: tuple(sorted(path.name for path in root.iterdir())) for root in run_roots
    }
    assert after_run_directories == before_run_directories


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


@pytest.mark.skipif(
    os.environ.get("ORCHESTRATOR_RUN_LIVE_PROCEDURE_RETIREMENT_VALIDATION") != "1",
    reason="live procedure-retirement scan validation is opt-in",
)
def test_tracked_plan_phase_retirement_record_validates_live() -> None:
    from orchestrator.workflow_lisp.procedure_identity_retirement import (
        load_retirement_record,
        validate_retirement_record,
    )

    record = load_retirement_record(PILOT_EVIDENCE / "retirement_record.json")
    result = validate_retirement_record(record, repo_root=REPO_ROOT)

    assert result.valid is True
    assert result.issues == ()
