"""Typed target-2.25 trial form ownership."""

from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json

from .effects import (
    RunsTrialEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expression_traversal import walk_expr
from .expressions import (
    RunRefBundleProgram,
    RunRefExpr,
    TrialArm,
    TrialExpr,
)
from .normalized_type_descriptor import compiler_normalized_type_descriptor
from .trial_result_contract import (
    build_trial_generated_types,
    derive_trial_result_contract,
)
from .typecheck_context import TypecheckSessionStateCollisionError, raise_error
from .typecheck_run_ref import _typecheck_run_ref_expr_with_details


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _install_compiler_type(type_env, type_ref) -> None:
    owned = getattr(type_env, "_compiler_owned_type_names", None)
    if owned is None:
        owned = set()
        type_env._compiler_owned_type_names = owned
    existing = type_env._type_refs.get(type_ref.name)
    if existing is None:
        type_env._type_refs[type_ref.name] = type_ref
        owned.add(type_ref.name)
        return
    from .typecheck_run_ref import _type_identity

    if type_ref.name not in owned or _type_identity(existing) != _type_identity(type_ref):
        raise TypecheckSessionStateCollisionError(
            f"trial compiler type collision for {type_ref.name!r}"
        )


def _raise_nested(expr, *, message: str) -> None:
    raise_error(
        message,
        code="trial_nested_unsupported",
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _validate_evaluation_bindings(expr: TrialExpr, *, context) -> str:
    from .workflows import PromptExtern, ProviderExtern

    externs = context.extern_environment
    provider = (
        externs.bindings_by_name.get(expr.evaluation.provider)
        if externs is not None
        else None
    )
    if not isinstance(provider, ProviderExtern):
        raise_error(
            f"trial evaluator provider {expr.evaluation.provider!r} is unresolved",
            code="trial_evaluation_provider_unresolved",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    assert isinstance(provider, ProviderExtern)
    rubric_matches = tuple(
        binding
        for binding in externs.bindings_by_name.values()
        if isinstance(binding, PromptExtern)
        and binding.asset_file == expr.evaluation.rubric_asset
    )
    if len(rubric_matches) != 1:
        raise_error(
            f"trial rubric asset {expr.evaluation.rubric_asset!r} is unresolved or ambiguous",
            code="trial_evaluation_rubric_unresolved",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    return provider.provider_id


def typecheck_trial_expr(expr, *, context, recurse, typed_factory):
    """Type one bounded static trial and derive its monomorphic result."""

    evaluator_provider_id = _validate_evaluation_bindings(expr, context=context)
    typed_arms: list[TrialArm] = []
    value_types = []
    value_descriptors = []
    arm_summaries = []
    arm_type_payloads = []
    for arm in expr.arms:
        arm_graph = tuple(walk_expr(arm.run_ref))
        nested = next(
            (
                candidate
                for candidate in arm_graph
                if isinstance(candidate, TrialExpr)
            ),
            None,
        )
        if nested is not None:
            _raise_nested(nested, message="nested trials are unsupported")
        run_ref_details = _typecheck_run_ref_expr_with_details(
            arm.run_ref,
            context=context,
            recurse=recurse,
            typed_factory=typed_factory,
        )
        typed_run_ref = run_ref_details.typed_expr
        if any(
            isinstance(effect, RunsTrialEffect)
            for summary in run_ref_details.input_effect_summaries
            for effect in (*summary.direct_effects, *summary.transitive_effects)
        ):
            _raise_nested(
                arm.run_ref,
                message="a trial arm input or reachable graph contains another trial",
            )
        for run_ref in arm_graph:
            if not isinstance(run_ref, RunRefExpr) or not isinstance(
                run_ref.program,
                RunRefBundleProgram,
            ):
                continue
            reachable = context.workflow_effects_by_name.get(
                run_ref.program.workflow_name
            )
            if reachable is not None and any(
                isinstance(effect, RunsTrialEffect)
                for effect in (
                    *reachable.direct_effects,
                    *reachable.transitive_effects,
                )
            ):
                _raise_nested(
                    run_ref,
                    message="a trial arm's reachable workflow graph contains another trial",
                )
        value_type = typed_run_ref.type_ref.field_types["value"]
        descriptor = compiler_normalized_type_descriptor(
            value_type,
            type_env=context.type_env,
        )
        value_types.append(value_type)
        value_descriptors.append(descriptor)
        arm_summaries.extend(run_ref_details.input_effect_summaries)
        typed_arms.append(
            TrialArm(arm_id=arm.arm_id, run_ref=typed_run_ref.expr)
        )
        arm_type_payloads.append(
            {
                "arm_id": arm.arm_id,
                "value": descriptor,
                "result": compiler_normalized_type_descriptor(
                    typed_run_ref.type_ref,
                    type_env=context.type_env,
                ),
            }
        )
    if any(descriptor != value_descriptors[0] for descriptor in value_descriptors[1:]):
        raise_error(
            "all trial arms must return the same normalized value descriptor",
            code="trial_arm_result_mismatch",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )

    caller = getattr(context.session_state.workflow_signature, "name", None)
    site_digest = _canonical_digest(
        {
            "caller": caller or "::".join(expr.form_path),
            "position": [
                expr.span.start.line,
                expr.span.start.column,
                expr.span.end.line,
                expr.span.end.column,
            ],
            "value_contract": value_descriptors[0],
        }
    )
    generated = build_trial_generated_types(
        value_type=value_types[0],
        site_digest=site_digest,
        type_env=context.type_env,
    )
    for _, type_ref in generated.compiler_owned_types:
        _install_compiler_type(context.type_env, type_ref)
    derive_trial_result_contract(
        generated.result_type,
        type_env=context.type_env,
    )
    trial_effect = effect_summary_from_direct(
        direct_effects=(RunsTrialEffect(),)
    )
    return typed_factory(
        expr=replace(
            expr,
            arms=tuple(typed_arms),
            evaluation=replace(
                expr.evaluation,
                provider=evaluator_provider_id,
            ),
            site_digest=site_digest,
        ),
        type_ref=generated.result_type,
        effect=merge_effect_summaries(*arm_summaries, trial_effect),
    )
