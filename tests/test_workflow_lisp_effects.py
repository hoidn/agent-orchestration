from __future__ import annotations

import importlib
from pathlib import Path
from textwrap import dedent

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_RESOURCE_TRANSITION_EFFECTS_FIXTURE = FIXTURES / "valid" / "resource_transition_effects.orc"


def _compile(path: Path, *, tmp_path: Path):
    return compile_stage3_module(
        path,
        validate_shared=False,
        workspace_root=tmp_path,
    )


def _write_effect_module(path: Path, *, effect_kind: str) -> Path:
    path.write_text(
        dedent(
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.14")
              (defrecord Result
                (ok Bool))
              (defproc sample
                ()
                -> Result
                :effects
                  (({effect_kind} backlog.item))
                :lowering inline
                (record Result
                  :ok true))
              (defworkflow orchestrate
                ()
                -> Result
                (sample)))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def test_internal_promoted_effect_atoms_render_deterministically() -> None:
    effects_module = importlib.import_module("orchestrator.workflow_lisp.effects")

    moves_resource = getattr(effects_module, "MovesResourceEffect")(
        subject=("queue", "item"),
        from_queue=("Queue", "active"),
        to_queue=("Queue", "in_progress"),
    )
    updates_ledger = getattr(effects_module, "UpdatesLedgerEffect")(
        subject=("queue", "item"),
        event_name=("LedgerEvent", "SELECTED"),
    )
    captures_snapshot = getattr(effects_module, "CapturesSnapshotEffect")(
        subject=("phase", "implementation"),
        snapshot_kind=("before",),
        candidate_names=("summary", "run_state"),
    )
    materializes_pointer = getattr(effects_module, "MaterializesPointerEffect")(
        subject=("artifact", "selected_item_summary"),
        pointer_path=("state", "selected-item-summary.json"),
        representation_role=("artifact_pointer",),
    )

    assert effects_module.render_effect_atom(moves_resource) == (
        "moves-resource(queue.item, from=Queue.active, to=Queue.in_progress)"
    )
    assert effects_module.render_effect_atom(updates_ledger) == (
        "updates-ledger(queue.item, event=LedgerEvent.SELECTED)"
    )
    assert effects_module.render_effect_atom(captures_snapshot) == (
        "captures-snapshot(phase.implementation, kind=before, candidates=summary|run_state)"
    )
    assert effects_module.render_effect_atom(materializes_pointer) == (
        "materializes-pointer("
        "artifact.selected_item_summary, path=state.selected-item-summary.json, role=artifact_pointer)"
    )


@pytest.mark.parametrize(
    "effect_kind",
    (
        "moves-resource",
        "updates-ledger",
        "captures-snapshot",
        "materializes-pointer",
    ),
)
def test_authored_promoted_effect_spellings_remain_invalid(tmp_path: Path, effect_kind: str) -> None:
    path = _write_effect_module(tmp_path / f"{effect_kind}.orc", effect_kind=effect_kind)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "procedure_effect_invalid"
    assert f"unsupported procedure effect kind `{effect_kind}`" in excinfo.value.diagnostics[0].message


def test_effect_summary_merge_preserves_promoted_atoms() -> None:
    effects_module = importlib.import_module("orchestrator.workflow_lisp.effects")
    summary = effects_module.merge_effect_summaries(
        effects_module.effect_summary_from_direct(
            direct_effects=(
                getattr(effects_module, "MovesResourceEffect")(
                    subject=("queue", "item"),
                    from_queue=("Queue", "active"),
                    to_queue=("Queue", "in_progress"),
                ),
                getattr(effects_module, "UpdatesLedgerEffect")(
                    subject=("queue", "item"),
                    event_name=("LedgerEvent", "SELECTED"),
                ),
            )
        ),
        effects_module.effect_summary_from_direct(
            direct_effects=(
                getattr(effects_module, "CapturesSnapshotEffect")(
                    subject=("phase", "implementation"),
                    snapshot_kind=("before",),
                    candidate_names=("summary",),
                ),
                getattr(effects_module, "MaterializesPointerEffect")(
                    subject=("artifact", "selected_item_summary"),
                    pointer_path=("state", "selected-item-summary.json"),
                    representation_role=("artifact_pointer",),
                ),
            )
        ),
    )

    assert len(summary.direct_effects) == 4
    assert summary.transitive_effects == summary.direct_effects
    assert effects_module.render_effect_set(summary.direct_effects) == (
        "("
        "captures-snapshot(phase.implementation, kind=before, candidates=summary), "
        "materializes-pointer(artifact.selected_item_summary, path=state.selected-item-summary.json, role=artifact_pointer), "
        "moves-resource(queue.item, from=Queue.active, to=Queue.in_progress), "
        "updates-ledger(queue.item, event=LedgerEvent.SELECTED)"
        ")"
    )


def test_resource_transition_infers_promoted_effects(tmp_path: Path) -> None:
    effects_module = importlib.import_module("orchestrator.workflow_lisp.effects")
    result = _compile(VALID_RESOURCE_TRANSITION_EFFECTS_FIXTURE, tmp_path=tmp_path)
    workflow = next(
        typed_workflow
        for typed_workflow in result.typed_workflows
        if typed_workflow.definition.name == "move-selected-item"
    )

    assert workflow.effect_summary.transitive_effects == frozenset(
        {
            effects_module.UsesCommandEffect(subject=("apply_resource_transition",)),
            getattr(effects_module, "MovesResourceEffect")(
                subject=("backlog-item",),
                from_queue=("Queue", "active"),
                to_queue=("Queue", "in_progress"),
            ),
            getattr(effects_module, "UpdatesLedgerEffect")(
                subject=("backlog-item",),
                event_name=("SELECTED",),
            ),
        }
    )
