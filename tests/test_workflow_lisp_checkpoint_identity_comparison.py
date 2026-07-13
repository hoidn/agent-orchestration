from __future__ import annotations

import json
from pathlib import Path

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.family_profiles import load_workflow_family_profile_catalog
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_shadow_points.orc")

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINES = REPO_ROOT / "tests" / "baselines" / "drain_checkpoint_identity"
DESIGN_DELTA_DRAIN_SOURCE = (
    REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
)
DESIGN_DELTA_PARENT_DRAIN_COMMANDS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)
DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.family_profile.json"
)


def _executor_for_fixture(tmp_path: Path) -> WorkflowExecutor:
    tmp_path.mkdir(parents=True, exist_ok=True)
    local_fixture = tmp_path / FIXTURE.name
    local_fixture.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )
    state_manager = StateManager(tmp_path, run_id="checkpoint-identity-comparison")
    return WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)


def checkpoint_identity_map(executor: WorkflowExecutor) -> dict[tuple[str, str], str]:
    """Map (workflow_name, origin_key) to checkpoint_id for every lexical point."""
    return {
        (point.workflow_name, point.origin_key): point.checkpoint_id
        for point in executor.runtime_plan.lexical_checkpoint_points
    }


def test_checkpoint_identity_stable_across_recompiles(tmp_path: Path) -> None:
    first = _executor_for_fixture(tmp_path / "a")
    second = _executor_for_fixture(tmp_path / "b")

    assert checkpoint_identity_map(first) == checkpoint_identity_map(second)


# --- Drain checkpoint-identity baselines ------------------------------------
#
# Snapshots recorded before the macro was re-targeted onto the generic proc
# (drain-migration plan
# docs/plans/2026-07-07-drain-migration-g8-retirement.md Task 1.3; component
# plan 2026-07-06-backlog-drain-generic-migration-plan.md Task 3). Task 1.5's
# gate diffed the generic-route compile against these baselines. The standalone
# intrinsic exemplar is now retired and retained only as historical JSON;
# resume runs of the production family still depend on the recorded ids.
#
# The map spans every validated bundle the compile produces (entry workflow,
# helper workflows, and the macro-generated `std/drain::backlog-drain` child)
# because the generated child's checkpoints are exactly the identities the
# migration puts at risk. Keys append the point's `step_kind` to the plan's
# `workflow::origin` form: the production module has one lexical step that
# carries two effect-boundary checkpoints (a `call` and a `resource_transition`)
# with identical origin keys but distinct checkpoint ids, so the two-part key
# would silently drop a row.


def _design_delta_parent_drain_provider_externs() -> dict[str, str]:
    # Copied from tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py
    # (parent-drain loader); inlined so this module survives that suite's
    # planned retirement.
    return {
        "providers.plan.draft": "fake-plan-draft",
        "providers.plan.review": "fake-plan-review",
        "providers.plan.fix": "fake-plan-fix",
        "providers.architect.draft": "fake-architect-draft",
        "providers.implementation.execute": "fake-implementation-execute",
        "providers.implementation.review": "fake-implementation-review",
        "providers.implementation.fix": "fake-implementation-fix",
        "providers.selector": "fake-selector",
        "providers.work-item.recovery-classifier": "fake-work-item-recovery",
    }


def _design_delta_parent_drain_prompt_externs() -> dict[str, object]:
    return {
        "prompts.plan.draft": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md"
        },
        "prompts.plan.review": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md"
        },
        "prompts.plan.fix": {
            "input_file": "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md"
        },
        "prompts.implementation.execute": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_implementation_phase/implement_plan.md"
            )
        },
        "prompts.implementation.review": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_implementation_phase/review_implementation.md"
            )
        },
        "prompts.implementation.fix": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_implementation_phase/fix_implementation.md"
            )
        },
        "prompts.work-item.classify-blocked-recovery": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_design_delta_work_item/"
                "classify_blocked_implementation_recovery.md"
            )
        },
        "prompts.selector.select-next-work": {
            "input_file": (
                "workflows/library/prompts/lisp_frontend_selector/"
                "select_next_design_delta_work.md"
            )
        },
        "prompts.architect.draft": {
            "input_file": (
                "workflows/library/prompts/"
                "lisp_frontend_design_delta_design_gap_architect/"
                "draft_implementation_architecture.md"
            )
        },
    }


def _design_delta_drain_validated_bundles(tmp_path: Path):
    commands_payload = json.loads(DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8"))
    result = compile_stage3_entrypoint(
        DESIGN_DELTA_DRAIN_SOURCE,
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs=_design_delta_parent_drain_provider_externs(),
        prompt_externs=_design_delta_parent_drain_prompt_externs(),
        command_boundaries=_parse_command_boundaries_manifest(
            commands_payload,
            manifest_path=DESIGN_DELTA_PARENT_DRAIN_COMMANDS,
        ),
        validate_shared=True,
        workspace_root=tmp_path,
        family_profile_catalog=load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE,)
        ),
    )
    return result.validated_bundles_by_name


def _identity_map_for(source_path: Path, tmp_path: Path) -> dict[str, str]:
    """`{workflow}::{origin}::{step_kind}` -> checkpoint_id across all bundles."""
    if source_path == DESIGN_DELTA_DRAIN_SOURCE:
        bundles = _design_delta_drain_validated_bundles(tmp_path)
    else:
        raise ValueError(f"no generic-route compile recipe for {source_path}")
    state_manager = StateManager(tmp_path, run_id="drain-identity-baseline")
    rows: dict[str, str] = {}
    for _name, bundle in sorted(bundles.items()):
        executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
        for point in executor.runtime_plan.lexical_checkpoint_points:
            step_kind = point.details.get("step_kind", point.point_kind)
            key = f"{point.workflow_name}::{point.origin_key}::{step_kind}"
            if key in rows:
                raise AssertionError(
                    f"duplicate checkpoint identity key {key!r}: "
                    f"{rows[key]} vs {point.checkpoint_id}"
                )
            rows[key] = point.checkpoint_id
    return rows


def test_retired_intrinsic_exemplar_baseline_remains_historical_evidence() -> None:
    recorded = json.loads((BASELINES / "exemplar.json").read_text(encoding="utf-8"))
    assert recorded
    assert all(isinstance(key, str) and isinstance(value, str) for key, value in recorded.items())


def test_design_delta_drain_generic_route_matches_baseline(tmp_path: Path) -> None:
    live = _identity_map_for(DESIGN_DELTA_DRAIN_SOURCE, tmp_path)
    recorded = json.loads((BASELINES / "design_delta_drain.json").read_text(encoding="utf-8"))
    assert live == recorded
