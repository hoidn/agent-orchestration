from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.family_profiles import (
    load_workflow_family_profile_catalog,
)

from orchestrator.workflow_lisp.workflows import ExternalToolBinding


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
WORKFLOW_LISP_INVALID_FIXTURES = (
    REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "invalid"
)
LET_PROC_WITHOUT_CONTEXT_SOURCE_INVALID_FIXTURE = (
    WORKFLOW_LISP_INVALID_FIXTURES
    / "derived_phase_context_let_proc_without_context_source_invalid.orc"
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
DESIGN_DELTA_PRODUCTION_MODULES = frozenset(
    {
        "lisp_frontend_design_delta/bootstrap",
        "lisp_frontend_design_delta/design_gap_architect",
        "lisp_frontend_design_delta/drain",
        "lisp_frontend_design_delta/implementation_phase",
        "lisp_frontend_design_delta/plan_phase",
        "lisp_frontend_design_delta/projections",
        "lisp_frontend_design_delta/selector",
        "lisp_frontend_design_delta/stdlib_adapters",
        "lisp_frontend_design_delta/transitions",
        "lisp_frontend_design_delta/types",
        "lisp_frontend_design_delta/work_item",
    }
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




def _design_delta_direct_fixture_command_boundaries(
    fixture_name: str,
) -> dict[str, object]:
    command_boundaries = dict(
        _parse_command_boundaries_manifest(
            json.loads(DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8")),
            manifest_path=DESIGN_DELTA_PARENT_DRAIN_COMMANDS,
        )
    )
    if fixture_name == "design_delta_loop_promoted_hook_phase_ctx.orc":
        command_boundaries.update(
            {
                "drain_select": ExternalToolBinding(
                    name="drain_select",
                    stable_command=("python", "scripts/select_next_item.py"),
                ),
                "drain_draft_gap": ExternalToolBinding(
                    name="drain_draft_gap",
                    stable_command=("python", "scripts/draft_gap_item.py"),
                ),
                "mk_fallback_report": ExternalToolBinding(
                    name="mk_fallback_report",
                    stable_command=("python", "scripts/make_fallback_report.py"),
                ),
            }
        )
    return command_boundaries


def test_let_proc_without_context_source_rejects_at_typecheck_like_authored_twin(tmp_path: Path) -> None:
    source = REPO_ROOT / "tests/fixtures/workflow_lisp/current_evaluated/let_proc_missing_context.orc"
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_entrypoint(source, source_roots=(source.parent,),
            command_boundaries={}, workspace_root=tmp_path, validate_shared=True)
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "workflow_signature_mismatch"
    assert diagnostic.phase == "typecheck"
    assert "phase-ctx" in diagnostic.message


