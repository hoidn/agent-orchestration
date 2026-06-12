"""Shared generated-path allocation contracts and runtime path rendering helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping


STATE_LAYOUT_SCHEMA_VERSION = "workflow_state_layout.v1"
WORKSPACE_RELATIVE_PATH_SAFETY = "workspace_relative"
RUNTIME_RUN_ID_TOKEN = "${runtime.run_id}"
ENTRYPOINT_MANAGED_WRITE_ROOT_FILENAME_LIMIT = 128


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


def freeze_projection_hints(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return MappingProxyType({})
    return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})


class GeneratedPathSemanticRole(str, Enum):
    COMMAND_RESULT_BUNDLE = "command_result_bundle"
    PROVIDER_RESULT_BUNDLE = "provider_result_bundle"
    VARIANT_PROJECTION_BUNDLE = "variant_projection_bundle"
    PURE_PROJECTION_BUNDLE = "pure_projection_bundle"
    RESOURCE_STATE = "resource_state"
    TRANSITION_AUDIT = "transition_audit"
    MATERIALIZED_VALUE_VIEW = "materialized_value_view"
    REUSABLE_CALL_WRITE_ROOT = "reusable_call_write_root"
    ENTRYPOINT_MANAGED_WRITE_ROOT = "entrypoint_managed_write_root"
    GENERATED_INTERNAL_INPUT_BINDING = "generated_internal_input_binding"
    COMPATIBILITY_POINTER_VIEW = "compatibility_pointer_view"


class GeneratedPathPrivacy(str, Enum):
    PUBLIC_AUTHORED = "public_authored"
    PUBLIC_ARTIFACT = "public_artifact"
    PRIVATE_GENERATED = "private_generated"
    COMPATIBILITY_VIEW = "compatibility_view"
    RUNTIME_SIDECAR = "runtime_sidecar"


class GeneratedPathResumeScope(str, Enum):
    NONE = "none"
    RUN = "run"
    CALL_FRAME = "call_frame"
    LOOP_FRAME = "loop_frame"
    LOOP_ITERATION = "loop_iteration"
    STEP_VISIT = "step_visit"


@dataclass(frozen=True)
class GeneratedPathAllocationRequest:
    owner: str
    workflow_name: str
    semantic_role: GeneratedPathSemanticRole
    privacy: GeneratedPathPrivacy
    resume_scope: GeneratedPathResumeScope
    stable_identity: str
    generated_input_name: str | None = None
    path_safety_policy: str = WORKSPACE_RELATIVE_PATH_SAFETY
    projection_hints: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_hints", freeze_projection_hints(self.projection_hints))


@dataclass(frozen=True)
class GeneratedPathAllocation:
    allocation_id: str
    workflow_name: str
    semantic_role: GeneratedPathSemanticRole
    privacy: GeneratedPathPrivacy
    resume_scope: GeneratedPathResumeScope
    stable_identity: str
    concrete_path_template: str
    generated_input_name: str | None = None
    path_safety_policy: str = WORKSPACE_RELATIVE_PATH_SAFETY
    projection_hints: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_hints", freeze_projection_hints(self.projection_hints))


def _slug_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "workflow"


def _entrypoint_managed_write_root_filename(request: GeneratedPathAllocationRequest) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", request.generated_input_name or "write_root") or "write_root"
    filename = f"{token}.json"
    if len(filename) <= ENTRYPOINT_MANAGED_WRITE_ROOT_FILENAME_LIMIT:
        return filename
    digest = hashlib.sha256(
        "|".join(
            (
                STATE_LAYOUT_SCHEMA_VERSION,
                request.workflow_name,
                request.stable_identity,
                request.generated_input_name or "",
            )
        ).encode("utf-8")
    ).hexdigest()[:16]
    suffix = f"__{digest}.json"
    prefix_limit = ENTRYPOINT_MANAGED_WRITE_ROOT_FILENAME_LIMIT - len(suffix)
    prefix = token[:prefix_limit].rstrip("._-") or "write_root"
    return f"{prefix}{suffix}"


def _validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Generated path allocation requires a non-empty relative path")
    if value.startswith("/"):
        raise ValueError(f"Generated path allocation must be workspace-relative, got `{value}`")
    parts = PurePosixPath(value).parts
    if any(part == ".." for part in parts):
        raise ValueError(f"Generated path allocation may not escape the workspace, got `{value}`")
    return value


def _allocation_id(request: GeneratedPathAllocationRequest) -> str:
    digest = hashlib.sha256(
        "|".join(
            (
                STATE_LAYOUT_SCHEMA_VERSION,
                request.owner,
                request.workflow_name,
                request.semantic_role.value,
                request.privacy.value,
                request.resume_scope.value,
                request.stable_identity,
                request.generated_input_name or "",
            )
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"alloc:{_slug_token(request.workflow_name)}:{request.semantic_role.value}:{digest}"


def _template_from_request(request: GeneratedPathAllocationRequest) -> str:
    if request.semantic_role == GeneratedPathSemanticRole.ENTRYPOINT_MANAGED_WRITE_ROOT:
        if not request.generated_input_name:
            raise ValueError("entrypoint managed write-root allocations require a generated_input_name")
        return _validate_relative_path(
            "/".join(
                (
                    ".orchestrate",
                    "workflow_lisp",
                    "entry",
                    RUNTIME_RUN_ID_TOKEN,
                    _slug_token(request.workflow_name),
                    _entrypoint_managed_write_root_filename(request),
                )
            )
        )
    for hint_key in ("path_template", "relative_path"):
        hint_value = request.projection_hints.get(hint_key)
        if isinstance(hint_value, str) and hint_value:
            return _validate_relative_path(hint_value)
    if request.generated_input_name:
        return f"${{inputs.{request.generated_input_name}}}"
    raise ValueError(
        "Generated path allocation requires either a generated_input_name or one path_template/relative_path hint"
    )


def allocate_generated_path(request: GeneratedPathAllocationRequest) -> GeneratedPathAllocation:
    if not request.owner:
        raise ValueError("Generated path allocation request requires an owner")
    if not request.workflow_name:
        raise ValueError("Generated path allocation request requires a workflow_name")
    if not request.stable_identity:
        raise ValueError("Generated path allocation request requires a stable_identity")
    return GeneratedPathAllocation(
        allocation_id=_allocation_id(request),
        workflow_name=request.workflow_name,
        semantic_role=request.semantic_role,
        privacy=request.privacy,
        resume_scope=request.resume_scope,
        stable_identity=request.stable_identity,
        concrete_path_template=_template_from_request(request),
        generated_input_name=request.generated_input_name,
        path_safety_policy=request.path_safety_policy,
        projection_hints=request.projection_hints,
    )


def render_generated_path_template(
    allocation: GeneratedPathAllocation,
    *,
    run_id: str | None = None,
) -> str:
    rendered = allocation.concrete_path_template
    if run_id is not None:
        rendered = rendered.replace(RUNTIME_RUN_ID_TOKEN, run_id)
    return rendered


class StateLayout:
    """Semantic allocation facade for generated compiler/runtime paths."""

    @staticmethod
    def allocate(request: GeneratedPathAllocationRequest) -> GeneratedPathAllocation:
        return allocate_generated_path(request)


class PathAllocator:
    """Concrete path allocator facade used by runtime and lowering bridges."""

    @staticmethod
    def allocate(request: GeneratedPathAllocationRequest) -> GeneratedPathAllocation:
        return allocate_generated_path(request)


def derive_entrypoint_managed_write_root_allocations(
    allocations: tuple[GeneratedPathAllocation, ...],
) -> tuple[GeneratedPathAllocation, ...]:
    """Derive runtime entrypoint write-root allocations from structured bundle producers.

    Older bundles may only record the command/provider/variant producer
    allocations for managed write-root inputs. This helper derives the
    entrypoint-managed binding metadata without changing the hidden input names
    or bundle-authority rules.
    """

    recorded_entry_inputs = {
        allocation.generated_input_name
        for allocation in allocations
        if allocation.semantic_role == GeneratedPathSemanticRole.ENTRYPOINT_MANAGED_WRITE_ROOT
        and isinstance(allocation.generated_input_name, str)
    }
    derived: list[GeneratedPathAllocation] = []
    for allocation in allocations:
        if (
            allocation.semantic_role
            not in {
                GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
                GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
                GeneratedPathSemanticRole.VARIANT_PROJECTION_BUNDLE,
                GeneratedPathSemanticRole.PURE_PROJECTION_BUNDLE,
            }
            or not isinstance(allocation.generated_input_name, str)
            or allocation.generated_input_name in recorded_entry_inputs
        ):
            continue
        derived.append(
            StateLayout.allocate(
                GeneratedPathAllocationRequest(
                    owner="workflow_runtime",
                    workflow_name=allocation.workflow_name,
                    semantic_role=GeneratedPathSemanticRole.ENTRYPOINT_MANAGED_WRITE_ROOT,
                    privacy=GeneratedPathPrivacy.PRIVATE_GENERATED,
                    resume_scope=GeneratedPathResumeScope.RUN,
                    stable_identity=f"{allocation.stable_identity}/entry",
                    generated_input_name=allocation.generated_input_name,
                    projection_hints={"source_allocation_id": allocation.allocation_id},
                )
            )
        )
        recorded_entry_inputs.add(allocation.generated_input_name)
    return tuple(derived)
