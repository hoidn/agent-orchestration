"""Lowering provenance ownership and shared-validation remapping helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from orchestrator.exceptions import ValidationSubjectRef

from ..diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    with_diagnostic_metadata,
)
from ..expressions import ProcedureCallExpr
from ..procedures import ProcedureLoweringMode, TypedProcedureDef
from ..spans import SourceSpan

if TYPE_CHECKING:
    from ..contracts import GeneratedContractFieldOrigin
    from .core import LoweredWorkflow


_SHARED_VALIDATION_CODE_RE = re.compile(
    r"\b("
    r"workflow_call_version_mismatch|"
    r"contract_refinement_weakened|"
    r"contract_refinement_type_conflict|"
    r"materialized_view_used_as_semantic_authority|"
    r"pointer_authority_conflict|"
    r"snapshot_ref_unknown_step|"
    r"snapshot_ref_unknown_name|"
    r"snapshot_candidate_unchanged|"
    r"snapshot_candidate_ambiguous|"
    r"invalid_variant_bundle|"
    r"variant_required_field_missing|"
    r"variant_forbidden_field_present|"
    r"variant_ref_unproved|"
    r"variant_ref_wrong_variant|"
    r"variant_unavailable|"
    r"atomic_commit_failed|"
    r"bundle_commit_aborted_invalid_candidate|"
    r"executable_ir_invalid|"
    r"semantic_ir_invalid"
    r")\b"
)
_MESSAGE_FALLBACK_NOTE = (
    "shared validation provenance matched by message text fallback; "
    "structured subject refs were unavailable"
)


@dataclass(frozen=True)
class LoweringOrigin:
    """Frontend source location for generated workflow dictionary entries."""

    span: SourceSpan
    form_path: tuple[str, ...]
    origin_key: str = ""
    expansion_stack: tuple[object, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationSubjectBinding:
    """Structured validation subject mapped to one lowering origin."""

    subject_ref: ValidationSubjectRef
    origin: LoweringOrigin


@dataclass(frozen=True)
class GeneratedSemanticEffectBinding:
    """Frontend-owned lineage for promoted semantic effects introduced by lowering."""

    effect_key: str
    step_id: str
    effect_kind: str
    origin: LoweringOrigin
    details: Mapping[str, Any]


@dataclass(frozen=True)
class LoweringOriginMap:
    """Complete source-map index for one lowered workflow."""

    workflow_name: str
    workflow_origin: LoweringOrigin
    step_spans: Mapping[str, LoweringOrigin]
    authored_input_spans: Mapping[str, LoweringOrigin]
    internal_input_spans: Mapping[str, LoweringOrigin]
    generated_output_spans: Mapping[str, LoweringOrigin]
    generated_path_spans: Mapping[str, LoweringOrigin]
    validation_subject_bindings: tuple[ValidationSubjectBinding, ...] = ()
    generated_semantic_effects: tuple[GeneratedSemanticEffectBinding, ...] = ()

    @property
    def workflow_span(self) -> SourceSpan:
        return self.workflow_origin.span

    @property
    def generated_input_spans(self) -> Mapping[str, LoweringOrigin]:
        return MappingProxyType({**dict(self.authored_input_spans), **dict(self.internal_input_spans)})


def _origin_from_source(source: object, *, span: SourceSpan | None = None) -> LoweringOrigin:
    """Build a source-map origin from any typed frontend node-like object."""

    origin_span = span or getattr(source, "span")
    return LoweringOrigin(
        span=origin_span,
        form_path=getattr(source, "form_path", ()),
        expansion_stack=getattr(source, "expansion_stack", ()),
    )


def _origin_from_context_source(context: Any, source: object, *, span: SourceSpan | None = None) -> LoweringOrigin:
    """Build an origin and attach active procedure/lowering provenance notes."""

    base = _origin_from_source(source, span=span)
    if not context.origin_notes:
        return base
    return LoweringOrigin(
        span=base.span,
        form_path=base.form_path,
        origin_key=base.origin_key,
        expansion_stack=base.expansion_stack,
        notes=context.origin_notes,
    )


def _with_origin_key(
    origin: LoweringOrigin,
    *,
    workflow_name: str,
    entity_kind: str,
    subject_name: str,
) -> LoweringOrigin:
    return replace(
        origin,
        origin_key=_lowering_origin_key(
            workflow_name=workflow_name,
            entity_kind=entity_kind,
            subject_name=subject_name,
        ),
    )


def _origins_with_keys(
    origins: Mapping[str, LoweringOrigin],
    *,
    workflow_name: str,
    entity_kind: str,
) -> dict[str, LoweringOrigin]:
    return {
        name: _with_origin_key(
            origin,
            workflow_name=workflow_name,
            entity_kind=entity_kind,
            subject_name=name,
        )
        for name, origin in origins.items()
    }


def _register_generated_contract_field_bindings(
    context: Any,
    field_origins: tuple[GeneratedContractFieldOrigin, ...],
) -> None:
    """Register authored field origins for one runtime-attached contract."""

    bindings_by_subject = {
        (
            binding.subject_ref.subject_kind,
            binding.subject_ref.subject_name,
            binding.subject_ref.workflow_name,
        ): binding
        for binding in context.generated_contract_field_bindings
    }
    for field_origin in field_origins:
        subject_ref = field_origin.subject_ref
        subject_identity = (
            subject_ref.subject_kind,
            subject_ref.subject_name,
            subject_ref.workflow_name,
        )
        binding = ValidationSubjectBinding(
            subject_ref=subject_ref,
            origin=_with_origin_key(
                _origin_from_context_source(context, field_origin),
                workflow_name=context.workflow_name,
                entity_kind="variant_output_field",
                subject_name=subject_ref.subject_name,
            ),
        )
        existing = bindings_by_subject.get(subject_identity)
        if existing is not None and existing.origin == binding.origin:
            continue
        if existing is not None:
            raise LispFrontendCompileError(
                (
                    with_diagnostic_metadata(
                        LispFrontendDiagnostic(
                            code="source_map_duplicate_key",
                            message=(
                                "variant-output field subject "
                                f"`{subject_ref.subject_name}` has conflicting authored origins"
                            ),
                            span=binding.origin.span,
                            form_path=binding.origin.form_path,
                            expansion_stack=binding.origin.expansion_stack,
                            phase="lowering",
                        ),
                        validation_pass="source_map",
                    ),
                ),
            )
        context.generated_contract_field_bindings.append(binding)
        bindings_by_subject[subject_identity] = binding


def _lowering_origin_key(
    *,
    workflow_name: str,
    entity_kind: str,
    subject_name: str,
) -> str:
    return f"{workflow_name}::{entity_kind}::{subject_name}"


def _build_validation_subject_bindings(
    *,
    workflow_name: str,
    workflow_origin: LoweringOrigin,
    step_spans: Mapping[str, LoweringOrigin],
    generated_inputs: Mapping[str, LoweringOrigin],
    generated_outputs: Mapping[str, LoweringOrigin],
    generated_paths: Mapping[str, LoweringOrigin],
    extra_bindings: Iterable[ValidationSubjectBinding] = (),
) -> tuple[ValidationSubjectBinding, ...]:
    bindings: list[ValidationSubjectBinding] = [
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="workflow",
                subject_name=workflow_name,
                workflow_name=workflow_name,
            ),
            origin=workflow_origin,
        )
    ]
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="step_id",
                subject_name=name,
                workflow_name=workflow_name,
            ),
            origin=origin,
        )
        for name, origin in step_spans.items()
    )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="step_id",
                subject_name=f"root.{name}",
                workflow_name=workflow_name,
            ),
            origin=origin,
        )
        for name, origin in step_spans.items()
        if not str(name).startswith("root.")
    )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="generated_input",
                subject_name=name,
                workflow_name=workflow_name,
            ),
            origin=origin,
        )
        for name, origin in generated_inputs.items()
    )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="generated_output",
                subject_name=name,
                workflow_name=workflow_name,
            ),
            origin=origin,
        )
        for name, origin in generated_outputs.items()
    )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="generated_path",
                subject_name=name,
                workflow_name=workflow_name,
            ),
            origin=origin,
        )
        for name, origin in generated_paths.items()
    )
    bindings.extend(extra_bindings)
    bindings.sort(
        key=lambda binding: (
            binding.subject_ref.subject_kind,
            binding.subject_ref.subject_name,
            binding.origin.origin_key,
        )
    )
    return tuple(bindings)


def _derive_generated_semantic_effects(
    raw_steps: object,
    *,
    context: Any,
    workflow_origin: LoweringOrigin,
) -> tuple[GeneratedSemanticEffectBinding, ...]:
    effects: list[GeneratedSemanticEffectBinding] = list(
        getattr(context, "generated_semantic_effects", ()) or ()
    )
    for step in _walk_generated_steps(raw_steps):
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            continue
        step_origin = context.step_spans.get(step_id)
        if step_origin is None:
            step_name = step.get("name")
            step_origin = context.step_spans.get(step_name) if isinstance(step_name, str) else None
        if step_origin is None:
            step_origin = workflow_origin

        pre_snapshot = step.get("pre_snapshot")
        if isinstance(pre_snapshot, Mapping):
            snapshot_name = pre_snapshot.get("name")
            candidates = pre_snapshot.get("candidates")
            if isinstance(snapshot_name, str) and isinstance(candidates, Mapping):
                effects.append(
                    GeneratedSemanticEffectBinding(
                        effect_key=f"snapshot:{step_id}:{snapshot_name}",
                        step_id=step_id,
                        effect_kind="snapshot_capture",
                        origin=step_origin,
                        details=MappingProxyType(
                            {
                                "snapshot_kind": snapshot_name,
                                "candidate_names": tuple(name for name in candidates if isinstance(name, str)),
                            }
                        ),
                    )
                )

        materialize = step.get("materialize_artifacts")
        values = materialize.get("values") if isinstance(materialize, Mapping) else None
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, Mapping):
                continue
            value_name = value.get("name")
            pointer = value.get("pointer")
            pointer_path = pointer.get("path") if isinstance(pointer, Mapping) else None
            if not isinstance(value_name, str) or not isinstance(pointer_path, str):
                continue
            effects.append(
                GeneratedSemanticEffectBinding(
                    effect_key=f"pointer:{step_id}:{value_name}",
                    step_id=step_id,
                    effect_kind="pointer_materialization",
                    origin=context.generated_path_spans.get(pointer_path, step_origin),
                    details=MappingProxyType(
                        {
                            "pointer_path": pointer_path,
                            "representation_role": "artifact_pointer",
                            "value_name": value_name,
                        }
                    ),
                )
            )
    for output_name, projection in sorted(context.output_projection_metadata.items()):
        if not isinstance(projection, Mapping):
            continue
        projection_class = projection.get("projection_class")
        source_step_id = projection.get("source_step_id")
        if projection_class != "provider_bundle_path_projection":
            continue
        if not isinstance(source_step_id, str) or not source_step_id:
            continue
        effect_key = projection.get("projection_id")
        if not isinstance(effect_key, str) or not effect_key:
            effect_key = f"{projection_class}:{source_step_id}:{output_name}"
        effect_origin = context.generated_output_spans.get(output_name, workflow_origin)
        effects.append(
            GeneratedSemanticEffectBinding(
                effect_key=effect_key,
                step_id=source_step_id,
                effect_kind=projection_class,
                origin=effect_origin,
                details=MappingProxyType(
                    {
                        **dict(projection),
                        "projected_output_name": output_name,
                    }
                ),
            )
        )
    effects.sort(key=lambda effect: (effect.effect_kind, effect.step_id, effect.effect_key))
    return tuple(effects)


def _walk_generated_steps(raw_steps: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(raw_steps, list):
        return ()
    steps: list[Mapping[str, Any]] = []
    for step in raw_steps:
        if not isinstance(step, Mapping):
            continue
        steps.append(step)
        match = step.get("match")
        if isinstance(match, Mapping):
            for case in (match.get("cases") or {}).values():
                if isinstance(case, Mapping):
                    steps.extend(_walk_generated_steps(case.get("steps")))
        repeat = step.get("repeat_until")
        if isinstance(repeat, Mapping):
            steps.extend(_walk_generated_steps(repeat.get("steps")))
        branch = step.get("if")
        if isinstance(branch, Mapping):
            steps.extend(_walk_generated_steps(branch.get("then")))
            steps.extend(_walk_generated_steps(branch.get("else")))
        for_each = step.get("for_each")
        if isinstance(for_each, Mapping):
            steps.extend(_walk_generated_steps(for_each.get("steps")))
    return tuple(steps)


def _record_step_origin(context: Any, *, step_name: str, step_id: str, source: object) -> None:
    """Record both human step name and stable id as aliases to one origin."""

    origin = _origin_from_context_source(context, source)
    context.step_spans[step_name] = origin
    context.step_spans[step_id] = origin


def _record_missing_step_origins(context: Any, raw_steps: object, *, source: object) -> None:
    """Backfill origin-map entries for generated nested steps that lack one."""

    for step in _walk_generated_steps(raw_steps):
        step_name = step.get("name")
        step_id = step.get("id")
        if not isinstance(step_name, str) or not isinstance(step_id, str):
            continue
        if step_name in context.step_spans or step_id in context.step_spans:
            continue
        _record_step_origin(context, step_name=step_name, step_id=step_id, source=source)


def _helper_provenance_notes(expansion_stack: tuple[object, ...]) -> tuple[str, ...]:
    notes: list[str] = []
    for helper in expansion_stack:
        function_name = getattr(helper, "function_name", None)
        call_span = getattr(helper, "call_span", None)
        definition_span = getattr(helper, "definition_span", None)
        if function_name is None or call_span is None or definition_span is None:
            continue
        call = call_span.start
        definition = definition_span.start
        notes.append(f"helper call site at {call.path}:{call.line}:{call.column} (`{function_name}`)")
        notes.append(f"helper definition at {definition.path}:{definition.line}:{definition.column}")
    return tuple(notes)


def _origin_for_workflow(
    typed_workflow: Any,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> LoweringOrigin:
    """Choose workflow-level provenance for authored and generated workflows."""

    notes: tuple[str, ...] = ()
    body_expr = typed_workflow.typed_body.expr
    if isinstance(body_expr, ProcedureCallExpr):
        procedure = typed_procedures.get(body_expr.callee_name)
        if procedure is not None and procedure.resolved_lowering_mode == ProcedureLoweringMode.INLINE:
            from .procedures import _procedure_provenance_notes

            notes = _procedure_provenance_notes(body_expr, procedure)
    elif helper_notes := _helper_provenance_notes(getattr(body_expr, "expansion_stack", ())):
        return LoweringOrigin(
            span=body_expr.span,
            form_path=body_expr.form_path,
            expansion_stack=body_expr.expansion_stack,
            notes=helper_notes,
        )
    elif typed_workflow.definition.name.startswith("%") and ".v1" in typed_workflow.definition.name:
        procedure_name = typed_workflow.definition.name.removeprefix("%").split(".")[-2]
        procedure = typed_procedures.get(procedure_name)
        if procedure is not None:
            notes = (
                f"procedure definition at {procedure.definition.span.start.path}:{procedure.definition.span.start.line}:{procedure.definition.span.start.column}",
            )
    return LoweringOrigin(
        span=typed_workflow.definition.span,
        form_path=typed_workflow.definition.form_path,
        expansion_stack=typed_workflow.definition.expansion_stack,
        notes=notes,
    )


def _rekey_origin_map(origin_map: LoweringOriginMap, *, workflow_name: str) -> LoweringOriginMap:
    """Rebuild one origin map for a renamed lowered workflow clone."""

    workflow_origin = _with_origin_key(
        origin_map.workflow_origin,
        workflow_name=workflow_name,
        entity_kind="workflow",
        subject_name=workflow_name,
    )
    step_spans = _origins_with_keys(
        origin_map.step_spans,
        workflow_name=workflow_name,
        entity_kind="step_id",
    )
    authored_input_spans = _origins_with_keys(
        origin_map.authored_input_spans,
        workflow_name=workflow_name,
        entity_kind="generated_input",
    )
    internal_input_spans = _origins_with_keys(
        origin_map.internal_input_spans,
        workflow_name=workflow_name,
        entity_kind="generated_internal_input",
    )
    generated_output_spans = _origins_with_keys(
        origin_map.generated_output_spans,
        workflow_name=workflow_name,
        entity_kind="generated_output",
    )
    generated_path_spans = _origins_with_keys(
        origin_map.generated_path_spans,
        workflow_name=workflow_name,
        entity_kind="generated_path",
    )
    generated_semantic_effects = tuple(
        replace(
            effect,
            origin=_with_origin_key(
                effect.origin,
                workflow_name=workflow_name,
                entity_kind="generated_path"
                if effect.effect_kind == "pointer_materialization"
                else "step_id",
                subject_name=effect.details.get("pointer_path", effect.step_id),
            ),
        )
        for effect in origin_map.generated_semantic_effects
    )
    contract_field_bindings = tuple(
        replace(
            binding,
            subject_ref=replace(
                binding.subject_ref,
                workflow_name=workflow_name,
            ),
            origin=_with_origin_key(
                binding.origin,
                workflow_name=workflow_name,
                entity_kind="variant_output_field",
                subject_name=binding.subject_ref.subject_name,
            ),
        )
        for binding in origin_map.validation_subject_bindings
        if binding.subject_ref.subject_kind == "variant_output_field"
    )
    return LoweringOriginMap(
        workflow_name=workflow_name,
        workflow_origin=workflow_origin,
        step_spans=MappingProxyType(step_spans),
        authored_input_spans=MappingProxyType(authored_input_spans),
        internal_input_spans=MappingProxyType(internal_input_spans),
        generated_output_spans=MappingProxyType(generated_output_spans),
        generated_path_spans=MappingProxyType(generated_path_spans),
        validation_subject_bindings=_build_validation_subject_bindings(
            workflow_name=workflow_name,
            workflow_origin=workflow_origin,
            step_spans=step_spans,
            generated_inputs={**authored_input_spans, **internal_input_spans},
            generated_outputs=generated_output_spans,
            generated_paths=generated_path_spans,
            extra_bindings=contract_field_bindings,
        ),
        generated_semantic_effects=generated_semantic_effects,
    )


def _raise_remapped_validation_error(
    lowered_workflow: LoweredWorkflow,
    errors: list[Any],
) -> None:
    """Convert shared validation errors into frontend diagnostics when possible."""

    diagnostics: list[LispFrontendDiagnostic] = []
    for error in errors:
        message = str(error.message)
        subject_refs = tuple(getattr(error, "subject_refs", ()) or ())
        origin = None
        notes: tuple[str, ...] = ()
        if subject_refs:
            origin = _origin_for_validation_subject_refs(lowered_workflow.origin_map, subject_refs)
            if origin is None:
                diagnostics.append(
                    with_diagnostic_metadata(
                        LispFrontendDiagnostic(
                            code="source_map_validation_ref_missing",
                            message=_missing_validation_subject_message(subject_refs),
                            span=lowered_workflow.origin_map.workflow_span,
                            form_path=lowered_workflow.typed_workflow.definition.form_path,
                            expansion_stack=lowered_workflow.origin_map.workflow_origin.expansion_stack,
                        ),
                        validation_pass="source_map",
                    )
                )
                continue
        else:
            origin = _remap_validation_message(lowered_workflow.origin_map, message)
            notes = (_MESSAGE_FALLBACK_NOTE,)
        if origin is None:
            diagnostics.append(
                with_diagnostic_metadata(
                    LispFrontendDiagnostic(
                        code="source_map_missing",
                        message=message,
                        span=lowered_workflow.origin_map.workflow_span,
                        form_path=lowered_workflow.typed_workflow.definition.form_path,
                        expansion_stack=lowered_workflow.origin_map.workflow_origin.expansion_stack,
                    ),
                    validation_pass="source_map",
                )
            )
            continue
        diagnostics.append(
            _remapped_shared_validation_diagnostic(
                lowered_workflow,
                message=message,
                origin=origin,
                notes=notes,
            )
        )
    raise LispFrontendCompileError(tuple(diagnostics))


def _remapped_shared_validation_diagnostic(
    lowered_workflow: LoweredWorkflow,
    *,
    message: str,
    origin: LoweringOrigin,
    notes: tuple[str, ...],
) -> LispFrontendDiagnostic:
    code = _shared_validation_diagnostic_code(message)
    validation_pass = "semantic_ir" if code == "semantic_ir_invalid" else "shared_validation"
    authority_layer = "shared" if validation_pass == "semantic_ir" else "shared_validation"
    return with_diagnostic_metadata(
        LispFrontendDiagnostic(
            code=code,
            message=message,
            span=origin.span,
            form_path=origin.form_path or lowered_workflow.typed_workflow.definition.form_path,
            expansion_stack=origin.expansion_stack,
            notes=origin.notes + notes,
        ),
        validation_pass=validation_pass,
        authority_layer=authority_layer,
    )


def _origin_for_validation_subject_refs(
    origin_map: LoweringOriginMap,
    subject_refs: tuple[ValidationSubjectRef, ...],
) -> LoweringOrigin | None:
    bindings_by_ref = {
        (
            binding.subject_ref.subject_kind,
            binding.subject_ref.subject_name,
            binding.subject_ref.workflow_name or origin_map.workflow_name,
        ): binding.origin
        for binding in origin_map.validation_subject_bindings
    }
    for subject_ref in subject_refs:
        origin = bindings_by_ref.get(
            (
                subject_ref.subject_kind,
                subject_ref.subject_name,
                subject_ref.workflow_name or origin_map.workflow_name,
            )
        )
        if origin is not None:
            return origin
    return None


def _missing_validation_subject_message(
    subject_refs: tuple[ValidationSubjectRef, ...],
) -> str:
    refs = ", ".join(f"{subject_ref.subject_kind}:{subject_ref.subject_name}" for subject_ref in subject_refs)
    return f"validation subject refs missing from origin map: {refs}"


def _remap_validation_message(origin_map: LoweringOriginMap, message: str) -> LoweringOrigin | None:
    """Best-effort map a shared validation message back to frontend origin."""

    for key, origin in origin_map.step_spans.items():
        if key in message:
            return origin
    for key, origin in origin_map.generated_input_spans.items():
        if key in message:
            return origin
    for key, origin in origin_map.generated_output_spans.items():
        if key in message:
            return origin
    for key, origin in origin_map.generated_path_spans.items():
        if key in message:
            return origin
    if "output" in message or "input" in message or "workflow" in message:
        return origin_map.workflow_origin
    return None


def _shared_validation_diagnostic_code(message: str) -> str:
    """Classify a shared validation message as a frontend diagnostic code."""

    match = _SHARED_VALIDATION_CODE_RE.search(message)
    if match is not None:
        return match.group(1)
    if "parent directory traversal" in message or "absolute paths not allowed" in message:
        return "path_definition_invalid"
    return "workflow_boundary_type_invalid"
