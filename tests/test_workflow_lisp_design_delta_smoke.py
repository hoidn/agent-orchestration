from __future__ import annotations

import json
from pathlib import Path

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.family_profiles import (
    load_workflow_family_profile_catalog,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_INPUTS = (
    REPO_ROOT / "workflows" / "examples" / "inputs" / "workflow_lisp_migrations"
)
DESIGN_DELTA_PARENT_DRAIN_COMMANDS = (
    MIGRATION_INPUTS / "design_delta_parent_drain.commands.json"
)
DESIGN_DELTA_PARENT_DRAIN_PROVIDERS = (
    MIGRATION_INPUTS / "design_delta_parent_drain.providers.json"
)
DESIGN_DELTA_PARENT_DRAIN_PROMPTS = (
    MIGRATION_INPUTS / "design_delta_parent_drain.prompts.json"
)

DESIGN_DELTA_TARGET_WORKFLOWS = (
    "%implementation_phase.lisp_frontend_design_delta/implementation_phase::fix-implementation.v1",
    "%implementation_phase.lisp_frontend_design_delta/implementation_phase::review-implementation.v1",
    "%plan_phase.lisp_frontend_design_delta/plan_phase::review-plan.v1",
    "%plan_phase.lisp_frontend_design_delta/plan_phase::revise-plan.v1",
    "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture",
    "lisp_frontend_design_delta/design_gap_architect::validate-design-gap-architecture",
    "lisp_frontend_design_delta/drain::drain",
    "lisp_frontend_design_delta/implementation_phase::implementation-phase",
    "lisp_frontend_design_delta/plan_phase::run-plan-phase",
    "lisp_frontend_design_delta/selector::select-next-work",
    "lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery",
    "lisp_frontend_design_delta/work_item::route-blocked-implementation",
    "lisp_frontend_design_delta/work_item::run-selected-item-stdlib",
    "lisp_frontend_design_delta/work_item::run-work-item",
)


def _write_smoke_family_profile(tmp_path: Path) -> Path:
    registry_path = tmp_path / "boundary_authority.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_design_delta_boundary_authority.v1",
                "rows": [
                    {
                        "workflow_name": workflow_name,
                        "field_name": "fixture-authority",
                        "authority_class": "public_authored",
                        "surface_kind": "public_input",
                        "path_like": False,
                        "parity_constrained": False,
                        "owner": "test",
                        "justification": "Preserve the production smoke compile contract.",
                        "replacement_tranche": "none",
                    }
                    for workflow_name in DESIGN_DELTA_TARGET_WORKFLOWS
                ],
            }
        ),
        encoding="utf-8",
    )
    profile_path = tmp_path / "family_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_family_profile.v1",
                "family_id": "design_delta_parent_drain_smoke",
                "workflow_name_prefixes": [
                    "%implementation_phase.lisp_frontend_design_delta/",
                    "%plan_phase.lisp_frontend_design_delta/",
                    "lisp_frontend_design_delta/",
                ],
                "target_workflows": DESIGN_DELTA_TARGET_WORKFLOWS,
                "boundary_authority_registry": registry_path.name,
                "checked_public_inputs": {},
                "entry_phase_identities": {},
                "hidden_context_rules": [],
                "typed_prompt_input_rows": [],
            }
        ),
        encoding="utf-8",
    )
    return profile_path


def _compile_design_delta_parent_drain_entrypoint(tmp_path: Path):
    result = compile_stage3_entrypoint(
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "drain.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs=json.loads(
            DESIGN_DELTA_PARENT_DRAIN_PROVIDERS.read_text(encoding="utf-8")
        ),
        prompt_externs=json.loads(
            DESIGN_DELTA_PARENT_DRAIN_PROMPTS.read_text(encoding="utf-8")
        ),
        command_boundaries=_parse_command_boundaries_manifest(
            json.loads(DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8")),
            manifest_path=DESIGN_DELTA_PARENT_DRAIN_COMMANDS,
        ),
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (_write_smoke_family_profile(tmp_path),)
        ),
    )
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    return result, lowered_by_name


HISTORICAL_PARITY_REPORT_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "review-parity-check"
    / "design_delta_parent_drain.json"
)
FOCUSED_SMOKE_MODULE = "tests/test_workflow_lisp_design_delta_smoke.py"
PARENT_DRAIN_EVIDENCE_ROLES = (
    "smoke_or_integration",
    "terminal_state_parity",
)


def test_design_delta_parent_drain_smoke_compiles_production_entry(
    tmp_path: Path,
) -> None:
    result, lowered_by_name = _compile_design_delta_parent_drain_entrypoint(tmp_path)

    assert not result.diagnostics
    assert result.entry_result.lowering_schema_version == 2
    assert "lisp_frontend_design_delta/drain::drain" in (
        result.entry_result.validated_bundles
    )
    assert "lisp_frontend_design_delta/drain::drain" in lowered_by_name


def test_design_delta_parent_drain_historical_parity_records_focused_smoke() -> None:
    report = json.loads(HISTORICAL_PARITY_REPORT_PATH.read_text(encoding="utf-8"))
    expected_command = [
        "python",
        "-m",
        "pytest",
        FOCUSED_SMOKE_MODULE,
        "-q",
    ]

    for role in PARENT_DRAIN_EVIDENCE_ROLES:
        evidence = report["evidence"][role]
        command = evidence["argv"]
        assert command == expected_command
        assert evidence["exit_code"] == 0
        assert evidence["status"] == "pass"
