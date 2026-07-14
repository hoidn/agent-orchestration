from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.contracts import structured_contract_semantic_digest
from orchestrator.workflow_lisp.source_map import (
    WorkflowLispSourceMap,
    build_source_map_document,
)
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
REVIEWED_INLINE_CALL_RETIREMENT_COUNT = 30
REVIEWED_INLINE_CALL_RETIREMENT_DIGEST = (
    "sha256:2df99fdd82327c87285e7053bcdaf3e909c4078a4d56dcc16d8caf894360cfca"
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


def test_result_guidance_is_excluded_from_reusable_contract_identity() -> None:
    contract = {
        "fields": [
            {
                "name": "__result__",
                "json_pointer": "",
                "type": "bool",
            }
        ]
    }
    guided = {
        **contract,
        "result_guidance": {
            "description": "True only when no blockers remain.",
            "example": True,
        },
    }

    assert structured_contract_semantic_digest(guided) == structured_contract_semantic_digest(contract)


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
    # Kept local so checkpoint-identity coverage owns its compile inputs.
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


def _design_delta_drain_compile_result(tmp_path: Path):
    commands_payload = json.loads(DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8"))
    return compile_stage3_entrypoint(
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
    )


def _design_delta_drain_source_map(compile_result) -> WorkflowLispSourceMap:
    return build_source_map_document(
        compile_result,
        selected_name="lisp_frontend_design_delta/drain::drain",
        display_name_resolver=lambda name: name.rsplit("::", 1)[-1],
    )


def _identity_map_from_bundles(bundles, tmp_path: Path) -> dict[str, str]:
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


def _reviewed_inline_call_retirement_digest(rows: Mapping[str, str]) -> str:
    payload = json.dumps(
        sorted(rows.items()),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _normalize_reviewed_inline_call_retirement(
    *,
    recorded: Mapping[str, str],
    live: Mapping[str, str],
    source_map: WorkflowLispSourceMap,
) -> tuple[dict[str, str], dict[str, str]]:
    retired = {
        key: recorded[key]
        for key in sorted(set(recorded) - set(live))
    }
    if len(retired) != REVIEWED_INLINE_CALL_RETIREMENT_COUNT:
        raise AssertionError(
            "reviewed inline-call retirement count changed: "
            f"expected {REVIEWED_INLINE_CALL_RETIREMENT_COUNT}, got {len(retired)}"
        )
    digest = _reviewed_inline_call_retirement_digest(retired)
    if digest != REVIEWED_INLINE_CALL_RETIREMENT_DIGEST:
        raise AssertionError(
            "reviewed inline-call retirement identity set changed: "
            f"expected {REVIEWED_INLINE_CALL_RETIREMENT_DIGEST}, got {digest}"
        )

    lineage_by_call_key = {}
    for workflow_name, workflow in source_map.workflows.items():
        for entry in workflow.step_ids.values():
            key = f"{workflow_name}::{entry.origin_key}::call"
            if key in lineage_by_call_key:
                raise AssertionError(
                    f"ambiguous current source-map lineage for retired call key {key!r}"
                )
            lineage_by_call_key[key] = entry

    for key, checkpoint_id in retired.items():
        if not key.endswith("::call") or not checkpoint_id.startswith("ckpt:"):
            raise AssertionError(
                f"reviewed retirement row is not a lexical call checkpoint: {key!r}"
            )
        entry = lineage_by_call_key.get(key)
        if entry is None:
            raise AssertionError(
                f"reviewed retired call has no unique current step lineage: {key!r}"
            )
        if entry.entity_kind != "step_id":
            raise AssertionError(
                f"reviewed retired call lineage is not a step identity: {key!r}"
            )
        if not any(
            note.startswith("procedure definition at") for note in entry.notes
        ) or not any(
            note.startswith("procedure call site at") for note in entry.notes
        ):
            raise AssertionError(
                "reviewed retired call lacks inline procedure definition/call-site "
                f"lineage: {key!r}"
            )

    normalized = dict(recorded)
    for key in retired:
        del normalized[key]
    return normalized, retired


def test_retired_intrinsic_exemplar_baseline_remains_historical_evidence() -> None:
    recorded = json.loads((BASELINES / "exemplar.json").read_text(encoding="utf-8"))
    assert recorded
    assert all(isinstance(key, str) and isinstance(value, str) for key, value in recorded.items())


def test_design_delta_drain_generic_route_matches_baseline(tmp_path: Path) -> None:
    compile_result = _design_delta_drain_compile_result(tmp_path)
    live = _identity_map_from_bundles(
        compile_result.validated_bundles_by_name,
        tmp_path,
    )
    recorded = json.loads((BASELINES / "design_delta_drain.json").read_text(encoding="utf-8"))
    source_map = _design_delta_drain_source_map(compile_result)
    normalized_recorded, retired = _normalize_reviewed_inline_call_retirement(
        recorded=recorded,
        live=live,
        source_map=source_map,
    )

    assert len(retired) == REVIEWED_INLINE_CALL_RETIREMENT_COUNT
    assert (
        _reviewed_inline_call_retirement_digest(retired)
        == REVIEWED_INLINE_CALL_RETIREMENT_DIGEST
    )
    assert live == normalized_recorded


def test_reviewed_inline_call_retirement_rejects_identity_or_lineage_drift(
    tmp_path: Path,
) -> None:
    compile_result = _design_delta_drain_compile_result(tmp_path)
    live = _identity_map_from_bundles(
        compile_result.validated_bundles_by_name,
        tmp_path,
    )
    recorded = json.loads((BASELINES / "design_delta_drain.json").read_text(encoding="utf-8"))
    source_map = _design_delta_drain_source_map(compile_result)
    retired_keys = set(recorded) - set(live)

    drifted_recorded = dict(recorded)
    drifted_recorded[min(retired_keys)] = "ckpt:unreviewed-drift"
    with pytest.raises(
        AssertionError,
        match="reviewed inline-call retirement identity set changed",
    ):
        _normalize_reviewed_inline_call_retirement(
            recorded=drifted_recorded,
            live=live,
            source_map=source_map,
        )

    broken_workflows = dict(source_map.workflows)
    broken = False
    for workflow_name, workflow in source_map.workflows.items():
        broken_steps = dict(workflow.step_ids)
        for step_id, entry in workflow.step_ids.items():
            call_key = f"{workflow_name}::{entry.origin_key}::call"
            if call_key not in retired_keys:
                continue
            broken_steps[step_id] = replace(
                entry,
                notes=tuple(
                    note
                    for note in entry.notes
                    if not note.startswith("procedure call site at")
                ),
            )
            broken_workflows[workflow_name] = replace(
                workflow,
                step_ids=broken_steps,
            )
            broken = True
            break
        if broken:
            break
    assert broken
    broken_source_map = replace(source_map, workflows=broken_workflows)

    with pytest.raises(
        AssertionError,
        match="lacks inline procedure definition/call-site lineage",
    ):
        _normalize_reviewed_inline_call_retirement(
            recorded=recorded,
            live=live,
            source_map=broken_source_map,
        )
