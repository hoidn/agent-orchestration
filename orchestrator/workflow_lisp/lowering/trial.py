"""Inert shared lowering leaf for one typed target-2.25 ``trial`` effect."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from orchestrator.workflow.state_layout import GeneratedPathSemanticRole
from orchestrator.workflow.trial.config import (
    TrialArmStaticConfig,
    build_trial_static_config,
)

from ..trial_result_contract import (
    derive_trial_output_bundle_fields,
    derive_trial_result_contract,
)
from ..type_env import RecordTypeRef, TypeRef
from ..wcc.model import WccTrialPayload
from .context import _LoweringContext, _TerminalResult
from .generated_paths import allocate_generated_result_bundle
from .origins import (
    GeneratedSemanticEffectBinding,
    _origin_from_context_source,
    _record_step_origin,
)
from .run_ref import (
    LowerableRunRef,
    LowerableRunRefInput,
    _lower_run_ref_static_config,
)
from .values import _record_output_refs


@dataclass(frozen=True)
class LowerableTrialInput:
    """One flattened dynamic input owned by a nested trial arm."""

    keyword: str
    value_expr: object
    type_ref: TypeRef


@dataclass(frozen=True)
class LowerableTrial:
    """Closed static trial payload plus its flattened dynamic inputs."""

    payload: WccTrialPayload
    inputs: tuple[LowerableTrialInput, ...]
    span: object
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...]


def _lower_trial_operation(
    trial: LowerableTrial,
    *,
    result_type: RecordTypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, object],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower one trial into exactly one effect plus pure input projections."""

    if not isinstance(trial, LowerableTrial):
        raise TypeError("trial lowering requires LowerableTrial")
    if not isinstance(result_type, RecordTypeRef):
        raise TypeError("trial lowering requires its generated record result")
    payload = trial.payload
    contract = derive_trial_result_contract(result_type, type_env=context.type_env)
    if (
        result_type.name != payload.generated_result_type
        or contract.descriptor != payload.result_descriptor
        or contract.digest != payload.result_digest
    ):
        raise ValueError("trial result metadata changed before lowering")

    inputs_by_keyword = {row.keyword: row for row in trial.inputs}
    if len(inputs_by_keyword) != len(trial.inputs):
        raise ValueError("trial dynamic input keyword is repeated")
    expected_keywords = {
        keyword
        for arm in payload.arms
        for _, keyword in arm.input_keywords
    }
    if set(inputs_by_keyword) != expected_keywords:
        raise ValueError("trial dynamic inputs disagree with the typed payload")

    prefix_steps: list[dict[str, Any]] = []
    arms: list[TrialArmStaticConfig] = []
    for arm_index, arm in enumerate(payload.arms):
        descriptor_by_name = dict(arm.run_ref.input_type_descriptors)
        lowerable_inputs: list[LowerableRunRefInput] = []
        for source_name, keyword in arm.input_keywords:
            row = inputs_by_keyword[keyword]
            descriptor = descriptor_by_name.get(source_name)
            if not isinstance(descriptor, dict):
                raise ValueError("trial arm input descriptor is unavailable")
            lowerable_inputs.append(
                LowerableRunRefInput(
                    name=source_name,
                    value_expr=row.value_expr,
                    type_ref=row.type_ref,
                    type_descriptor=descriptor,
                )
            )
        nested = LowerableRunRef(
            payload=arm.run_ref,
            inputs=tuple(lowerable_inputs),
            span=trial.span,
            form_path=(*trial.form_path, "arms", str(arm_index), "run-ref"),
            expansion_stack=trial.expansion_stack,
        )
        arm_prefix, run_ref_config, _ = _lower_run_ref_static_config(
            nested,
            result_type=None,
            context=context,
            local_values=local_values,
            projection_step_role=f"trial_arm_{arm_index}_input",
        )
        prefix_steps.extend(arm_prefix)
        arms.append(
            TrialArmStaticConfig(
                arm_id=arm.arm_id,
                run_ref=run_ref_config,
            )
        )

    compiler_identity = tuple(
        {arm.run_ref.compiler_runtime_identity_digest for arm in arms}
    )
    if len(compiler_identity) != 1:
        raise ValueError("trial arm compiler/runtime identities disagree")
    config = build_trial_static_config(
        compiler_runtime_identity_digest=compiler_identity[0],
        site_digest=payload.site_digest,
        arms=tuple(arms),
        reps=payload.reps,
        max_concurrency=payload.max_concurrency,
        evaluation=payload.evaluation,
        budget=payload.budget,
        result_descriptor=contract.descriptor,
        result_digest=contract.digest,
        target_dsl_version=context.type_env.target_dsl_version,
    )
    step_name = context.step_name_prefix
    step_id = context.normalize_generated_step_id(step_name)
    allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=trial,
        step_name=step_name,
        step_id=step_id,
        semantic_role=GeneratedPathSemanticRole.TRIAL_RESULT_BUNDLE,
        stable_target="trial_result",
    )
    _record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=trial,
    )
    context.generated_semantic_effects.append(
        GeneratedSemanticEffectBinding(
            effect_key=f"trial:{step_id}",
            step_id=step_id,
            effect_kind="trial",
            origin=context.step_spans[step_id],
            details={
                "trial_static_config_schema_version": config.record[
                    "schema_version"
                ],
                "trial_static_config_digest": config.digest,
                "compiler_runtime_identity_digest": (
                    config.compiler_runtime_identity_digest
                ),
                "site_digest": config.site_digest,
                "generated_result_type": config.generated_result_type,
                "result_digest": config.result_digest,
                "arms_digest": config.arms_digest,
                "evaluation_digest": config.evaluation_digest,
                "budget_digest": config.budget_digest,
                "result_allocation_id": allocation.allocation_id,
                "output_bundle_path": allocation.concrete_path_template,
            },
        )
    )
    step = {
        "name": step_name,
        "id": step_id,
        "output_bundle": {
            "path": allocation.concrete_path_template,
            "fields": derive_trial_output_bundle_fields(contract),
        },
        "trial": config,
    }
    return [*prefix_steps, step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_record_output_refs(step_name, result_type),
        output_kind="step",
        hidden_inputs={
            allocation.generated_input_name: _origin_from_context_source(
                context,
                trial,
            )
        },
        checkpoint_identity_component_digest=config.digest,
        checkpoint_result_contract_digest=config.result_digest,
    )
