from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.family_profiles import (
    load_workflow_family_profile_catalog,
)
from orchestrator.workflow_lisp.wcc.route import DEFAULT_LOWERING_ROUTE
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
WORKFLOW_LISP_VALID_FIXTURES = (
    REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
)
DESIGN_DELTA_LIBRARY_ROOT = (
    REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta"
)
DESIGN_DELTA_WORK_ITEM_RUNTIME_MIRROR_ROOT = (
    WORKFLOW_LISP_VALID_FIXTURES
    / "design_delta_work_item_runtime"
    / "lisp_frontend_design_delta"
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
DESIGN_DELTA_DIRECT_FIXTURE_CASES = (
    (
        "design_delta_loop_promoted_hook_phase_ctx.orc",
        "design_delta_loop_promoted_hook_phase_ctx::drain-entry",
    ),
    (
        "design_delta_parent_calls_implementation_phase.orc",
        "design_delta_parent_calls_implementation_phase::run-implementation-phase",
    ),
    (
        "design_delta_parent_calls_work_item.orc",
        "design_delta_parent_calls_work_item::run-parent-work-item",
    ),
    (
        "design_delta_item_ctx_child_phase_reuse_proc.orc",
        "design_delta_item_ctx_child_phase_reuse_proc::run-entry",
    ),
    (
        "design_delta_item_ctx_child_phase_reuse_proc_ref.orc",
        "design_delta_item_ctx_child_phase_reuse_proc_ref::run-entry",
    ),
)
DESIGN_DELTA_DIRECT_FIXTURE_IDS = (
    "loop-promoted-hook",
    "parent-implementation-phase",
    "parent-work-item",
    "item-ctx-proc",
    "item-ctx-proc-ref",
)
DESIGN_DELTA_MIRROR_MODULES = (
    "bootstrap.orc",
    "design_gap_architect.orc",
    "implementation_phase.orc",
    "plan_phase.orc",
    "projections.orc",
    "selector.orc",
    "stdlib_adapters.orc",
    "transitions.orc",
    "types.orc",
    "work_item.orc",
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
    assert DESIGN_DELTA_PRODUCTION_MODULES.issubset(
        result.compiled_results_by_name
    )


@pytest.mark.parametrize(
    ("fixture_name", "expected_workflow"),
    DESIGN_DELTA_DIRECT_FIXTURE_CASES,
    ids=DESIGN_DELTA_DIRECT_FIXTURE_IDS,
)
def test_registered_design_delta_fixture_compiles_directly(
    tmp_path: Path,
    fixture_name: str,
    expected_workflow: str,
) -> None:
    result = compile_stage3_entrypoint(
        WORKFLOW_LISP_VALID_FIXTURES / fixture_name,
        source_roots=(
            WORKFLOW_LISP_VALID_FIXTURES,
            REPO_ROOT / "workflows" / "library",
        ),
        provider_externs=json.loads(
            DESIGN_DELTA_PARENT_DRAIN_PROVIDERS.read_text(encoding="utf-8")
        ),
        prompt_externs=json.loads(
            DESIGN_DELTA_PARENT_DRAIN_PROMPTS.read_text(encoding="utf-8")
        ),
        command_boundaries=_design_delta_direct_fixture_command_boundaries(
            fixture_name
        ),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=DEFAULT_LOWERING_ROUTE,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (_write_smoke_family_profile(tmp_path),)
        ),
    )

    assert result.entry_result.lowering_schema_version == 2
    assert expected_workflow in result.validated_bundles_by_name


@pytest.mark.parametrize("module_name", DESIGN_DELTA_MIRROR_MODULES)
def test_design_delta_work_item_runtime_mirror_matches_production_owner(
    module_name: str,
) -> None:
    mirror_path = DESIGN_DELTA_WORK_ITEM_RUNTIME_MIRROR_ROOT / module_name
    production_path = DESIGN_DELTA_LIBRARY_ROOT / module_name

    assert mirror_path.read_bytes() == production_path.read_bytes()


def test_design_delta_stdlib_payloads_compiles_directly(tmp_path: Path) -> None:
    result = compile_stage3_entrypoint(
        DESIGN_DELTA_LIBRARY_ROOT / "stdlib_payloads.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs=json.loads(
            DESIGN_DELTA_PARENT_DRAIN_PROVIDERS.read_text(encoding="utf-8")
        ),
        prompt_externs=json.loads(
            DESIGN_DELTA_PARENT_DRAIN_PROMPTS.read_text(encoding="utf-8")
        ),
        command_boundaries=_design_delta_direct_fixture_command_boundaries(
            "stdlib_payloads.orc"
        ),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=DEFAULT_LOWERING_ROUTE,
    )

    assert result.entry_result.lowering_schema_version == 2
    assert (
        "lisp_frontend_design_delta/stdlib_payloads::project-selected-item-payload"
        in result.validated_bundles_by_name
    )


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
