"""Shared Workflow Lisp bridge from lowering sites to generated path allocations."""

from __future__ import annotations

import hashlib
from typing import Any

from orchestrator.workflow.state_layout import (
    GeneratedPathAllocation,
    GeneratedPathAllocationRequest,
    GeneratedPathPrivacy,
    GeneratedPathResumeScope,
    GeneratedPathSemanticRole,
    StateLayout,
)

from .origins import _origin_from_context_source

PATH_SEGMENT_FILENAME_LIMIT = 255


def _stable_identity(*parts: str | None) -> str:
    return "/".join(part for part in parts if isinstance(part, str) and part)


def _slug_token(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-") or "generated"


def _path_digest(*parts: str | None) -> str:
    payload = "|".join(part for part in parts if isinstance(part, str) and part)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _bounded_path_segment(
    value: str,
    *,
    digest_source: str,
    limit: int = PATH_SEGMENT_FILENAME_LIMIT,
) -> str:
    if len(value) <= limit:
        return value
    token = _slug_token(value)
    suffix = f"__{_path_digest(digest_source, value)}"
    prefix_limit = max(1, limit - len(suffix))
    prefix = token[:prefix_limit].rstrip("._-") or "generated"
    return f"{prefix}{suffix}"


def _bounded_json_filename(
    value: str,
    *,
    digest_source: str,
    limit: int = PATH_SEGMENT_FILENAME_LIMIT,
) -> str:
    filename = f"{value}.json"
    if len(filename) <= limit:
        return filename
    token = _slug_token(value)
    suffix = f"__{_path_digest(digest_source, value)}.json"
    prefix_limit = max(1, limit - len(suffix))
    prefix = token[:prefix_limit].rstrip("._-") or "generated"
    return f"{prefix}{suffix}"


def _schema_identity_part(context: Any) -> str | None:
    schema = getattr(context, "lowering_schema_version", None)
    return f"schema:{schema}" if isinstance(schema, int) else None


def _record_allocation(
    *,
    context: Any,
    source_expr: Any,
    allocation: GeneratedPathAllocation,
) -> GeneratedPathAllocation:
    context.generated_path_allocations.append(allocation)
    context.generated_path_spans[allocation.concrete_path_template] = _origin_from_context_source(context, source_expr)
    return allocation


def _allocate(
    *,
    context: Any,
    source_expr: Any,
    semantic_role: GeneratedPathSemanticRole,
    privacy: GeneratedPathPrivacy,
    resume_scope: GeneratedPathResumeScope,
    stable_identity: str,
    generated_input_name: str | None = None,
    path_template: str | None = None,
    projection_hints: dict[str, object] | None = None,
) -> GeneratedPathAllocation:
    hints = dict(projection_hints or {})
    if path_template is not None:
        hints.setdefault("path_template", path_template)
    allocation = StateLayout.allocate(
        GeneratedPathAllocationRequest(
            owner="workflow_lisp",
            workflow_name=context.workflow_name,
            semantic_role=semantic_role,
            privacy=privacy,
            resume_scope=resume_scope,
            stable_identity=stable_identity,
            generated_input_name=generated_input_name,
            projection_hints=hints,
        )
    )
    return _record_allocation(context=context, source_expr=source_expr, allocation=allocation)


def allocate_generated_result_bundle(
    *,
    context: Any,
    source_expr: Any,
    step_name: str,
    step_id: str,
    semantic_role: GeneratedPathSemanticRole,
    path_template: str | None = None,
    privacy: GeneratedPathPrivacy = GeneratedPathPrivacy.PRIVATE_GENERATED,
    resume_scope: GeneratedPathResumeScope = GeneratedPathResumeScope.STEP_VISIT,
    stable_target: str = "result_bundle",
) -> GeneratedPathAllocation:
    generated_input_name = None if path_template is not None else f"__write_root__{step_id}__result_bundle"
    return _allocate(
        context=context,
        source_expr=source_expr,
        semantic_role=semantic_role,
        privacy=privacy,
        resume_scope=resume_scope,
        stable_identity=_stable_identity(
            _schema_identity_part(context),
            context.workflow_name,
            step_name,
            stable_target,
        ),
        generated_input_name=generated_input_name,
        path_template=path_template,
    )


def allocate_reusable_call_write_root(
    *,
    context: Any,
    source_expr: Any,
    call_step_name: str,
    callee_name: str,
    managed_input_name: str,
) -> GeneratedPathAllocation:
    path_identity = _stable_identity(
        _schema_identity_part(context),
        context.workflow_name,
        call_step_name,
        context.iteration_scope,
        callee_name,
        managed_input_name,
    )
    base_segments = [
        ".orchestrate/workflow_lisp/calls",
        _bounded_path_segment(context.workflow_name, digest_source=f"{path_identity}/workflow"),
        _bounded_path_segment(call_step_name, digest_source=f"{path_identity}/call"),
    ]
    if context.iteration_scope is not None:
        base_segments.append(context.iteration_scope)
    base_segments.append(
        _bounded_path_segment(callee_name, digest_source=f"{path_identity}/callee")
    )
    relative_path = "/".join(
        (*base_segments, _bounded_json_filename(managed_input_name, digest_source=path_identity))
    )
    return _allocate(
        context=context,
        source_expr=source_expr,
        semantic_role=GeneratedPathSemanticRole.REUSABLE_CALL_WRITE_ROOT,
        privacy=GeneratedPathPrivacy.COMPATIBILITY_VIEW,
        resume_scope=(
            GeneratedPathResumeScope.LOOP_ITERATION
            if context.iteration_scope is not None
            else GeneratedPathResumeScope.CALL_FRAME
        ),
        stable_identity=path_identity,
        generated_input_name=managed_input_name,
        path_template=relative_path,
    )


def allocate_compatibility_binding_bundle(
    *,
    context: Any,
    source_expr: Any,
    call_step_name: str,
    callee_name: str,
) -> GeneratedPathAllocation:
    path_identity = _stable_identity(
        _schema_identity_part(context),
        context.workflow_name,
        call_step_name,
        context.iteration_scope,
        callee_name,
        "managed_write_roots_bundle",
    )
    relative_path = "/".join(
        (
            ".orchestrate/workflow_lisp/call_bindings",
            _bounded_path_segment(context.workflow_name, digest_source=f"{path_identity}/workflow"),
            _bounded_path_segment(call_step_name, digest_source=f"{path_identity}/call"),
            context.iteration_scope or "root",
            _bounded_path_segment(callee_name, digest_source=f"{path_identity}/callee"),
            "__managed_write_roots.json",
        )
    )
    return _allocate(
        context=context,
        source_expr=source_expr,
        semantic_role=GeneratedPathSemanticRole.COMPATIBILITY_POINTER_VIEW,
        privacy=GeneratedPathPrivacy.COMPATIBILITY_VIEW,
        resume_scope=GeneratedPathResumeScope.LOOP_ITERATION,
        stable_identity=path_identity,
        path_template=relative_path,
        projection_hints={"compatibility_class": "loop_binding_bundle"},
    )


def allocate_materialized_value_view(
    *,
    context: Any,
    source_expr: Any,
    path_template: str,
    stable_target: str,
    privacy: GeneratedPathPrivacy = GeneratedPathPrivacy.COMPATIBILITY_VIEW,
) -> GeneratedPathAllocation:
    schema_identity = _schema_identity_part(context)
    return _allocate(
        context=context,
        source_expr=source_expr,
        semantic_role=GeneratedPathSemanticRole.MATERIALIZED_VALUE_VIEW,
        privacy=privacy,
        resume_scope=GeneratedPathResumeScope.NONE,
        stable_identity=_stable_identity(
            schema_identity,
            context.workflow_name,
            context.step_name_prefix if schema_identity is not None else None,
            stable_target,
        ),
        path_template=path_template,
    )


def allocate_private_generated_path(
    *,
    context: Any,
    source_expr: Any,
    semantic_role: GeneratedPathSemanticRole,
    stable_target: str,
    path_template: str | None = None,
    resume_scope: GeneratedPathResumeScope = GeneratedPathResumeScope.RUN,
    privacy: GeneratedPathPrivacy = GeneratedPathPrivacy.PRIVATE_GENERATED,
) -> GeneratedPathAllocation:
    resolved_path_template = path_template
    if resolved_path_template is None:
        suffix = ".jsonl" if semantic_role == GeneratedPathSemanticRole.TRANSITION_AUDIT else ".json"
        resolved_path_template = "/".join(
            (
                "state",
                "workflow_lisp",
                _slug_token(context.workflow_name),
                f"{_slug_token(stable_target)}{suffix}",
            )
        )
    return _allocate(
        context=context,
        source_expr=source_expr,
        semantic_role=semantic_role,
        privacy=privacy,
        resume_scope=resume_scope,
        stable_identity=_stable_identity(
            _schema_identity_part(context),
            context.workflow_name,
            context.step_name_prefix if _schema_identity_part(context) is not None else None,
            stable_target,
        ),
        path_template=resolved_path_template,
    )


def allocation_reason(allocation: GeneratedPathAllocation) -> str | None:
    if allocation.semantic_role in {
        GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
        GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
        GeneratedPathSemanticRole.VARIANT_PROJECTION_BUNDLE,
        GeneratedPathSemanticRole.PURE_PROJECTION_BUNDLE,
        GeneratedPathSemanticRole.GENERATED_INTERNAL_INPUT_BINDING,
    } and allocation.generated_input_name:
        return "managed_write_root"
    return None
