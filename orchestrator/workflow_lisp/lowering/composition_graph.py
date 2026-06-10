"""Intermediate fragment metadata for nested structured-control lowering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.state_layout import GeneratedPathAllocation

from .origins import GeneratedSemanticEffectBinding, LoweringOrigin

STRUCTURED_CONTROL_STEP_KEYS = frozenset({"if", "match", "repeat_until"})


@dataclass(frozen=True)
class ScopeProjection:
    """Values intentionally projected across one composition scope boundary."""

    output_refs: Mapping[str, str]
    hidden_inputs: Mapping[str, LoweringOrigin]


@dataclass(frozen=True)
class CompositionScope:
    """One lowering-time composition scope used before shared rendering."""

    scope_id: str
    parent_scope_id: str | None
    kind: str
    owner_step_name: str | None
    resume_identity_hint: str | None = None


@dataclass(frozen=True)
class GeneratedHelperPlan:
    """Generated helper-boundary metadata for one hoisted fragment."""

    workflow_name: str
    call_step_name: str
    captured_params: tuple[str, ...]


@dataclass(frozen=True)
class CompositionFragment:
    """Intermediate lowered fragment before final shared-structure emission."""

    emitted_steps: tuple[dict[str, Any], ...]
    entry_scope_id: str
    exit_projection: ScopeProjection
    leaf_terminal: object | None
    generated_helper_plans: tuple[GeneratedHelperPlan, ...]
    hidden_inputs: Mapping[str, LoweringOrigin]
    generated_path_allocations: tuple[GeneratedPathAllocation, ...]
    generated_semantic_effects: tuple[GeneratedSemanticEffectBinding, ...]
    effect_summary: object | None
    resume_identity_hint: str | None = None


def fragment_requires_helper_boundary(fragment: CompositionFragment) -> bool:
    """Return whether one fragment must cross a helper call boundary."""

    return any(
        isinstance(step, Mapping)
        and any(key in step for key in STRUCTURED_CONTROL_STEP_KEYS)
        for step in fragment.emitted_steps
    )


def build_fragment(
    *,
    emitted_steps: Sequence[dict[str, Any]],
    scope: CompositionScope,
    output_refs: Mapping[str, str],
    hidden_inputs: Mapping[str, LoweringOrigin],
    leaf_terminal: object | None = None,
    generated_helper_plans: Sequence[GeneratedHelperPlan] = (),
    generated_path_allocations: Sequence[GeneratedPathAllocation] = (),
    generated_semantic_effects: Sequence[GeneratedSemanticEffectBinding] = (),
    effect_summary: object | None = None,
) -> CompositionFragment:
    """Create one fragment from the current lowering owner data."""

    projection = ScopeProjection(
        output_refs=dict(output_refs),
        hidden_inputs=dict(hidden_inputs),
    )
    return CompositionFragment(
        emitted_steps=tuple(emitted_steps),
        entry_scope_id=scope.scope_id,
        exit_projection=projection,
        leaf_terminal=leaf_terminal,
        generated_helper_plans=tuple(generated_helper_plans),
        hidden_inputs=dict(hidden_inputs),
        generated_path_allocations=tuple(generated_path_allocations),
        generated_semantic_effects=tuple(generated_semantic_effects),
        effect_summary=effect_summary,
        resume_identity_hint=scope.resume_identity_hint,
    )
