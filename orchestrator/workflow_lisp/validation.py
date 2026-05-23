"""Validation pipeline orchestration for the Workflow Lisp frontend."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    diagnostic_effective_severity,
    validation_pass_order_key,
    with_diagnostic_metadata,
)
from .lints import LINT_PROFILE_DEFAULT


VALIDATION_PASS_CATALOG: tuple[str, ...] = (
    "parse",
    "module",
    "macro",
    "type",
    "effect",
    "reference",
    "contract",
    "proof",
    "authority",
    "lowering_surface",
    "source_map",
    "shared_validation",
    "executable",
)


@dataclass(frozen=True)
class ValidationPipelineState:
    """Aggregate state that pass runners can enrich as compilation advances."""

    parse_tree: object | None = None
    syntax_module: object | None = None
    expanded_syntax_module: object | None = None
    module: object | None = None
    type_env: object | None = None
    workflow_defs: tuple[object, ...] = ()
    procedure_defs: tuple[object, ...] = ()
    workflow_catalog: object | None = None
    procedure_catalog: object | None = None
    extern_environment: object | None = None
    command_boundary_environment: object | None = None
    typed_procedures: tuple[object, ...] = ()
    typed_workflows: tuple[object, ...] = ()
    lowered_workflows: tuple[object, ...] = ()
    validated_bundles: Mapping[str, object] = field(default_factory=dict)
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationPipelinePass:
    """One ordered validation pass in the frontend pipeline."""

    pass_id: str
    runner: Callable[[ValidationPipelineState], ValidationPipelineState | None]
    covers_passes: tuple[str, ...] = ()
    authority_layer: str = "frontend"
    blocking: bool = True
    artifact_ready: bool | Callable[[ValidationPipelineState], bool] = False
    attach_metadata: bool = True


@dataclass(frozen=True)
class ValidationPassResult:
    """Observed outcome for one validation pass execution."""

    pass_id: str
    authority_layer: str
    blocking: bool
    diagnostics: tuple[LispFrontendDiagnostic, ...]
    artifact_ready: bool


def run_validation_pipeline(
    initial_state: ValidationPipelineState,
    passes: Sequence[ValidationPipelinePass],
    *,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> tuple[ValidationPipelineState, tuple[ValidationPassResult, ...]]:
    """Run pass runners in order and stop after the first blocking failure."""

    state = initial_state
    results: list[ValidationPassResult] = []
    for pipeline_pass in passes:
        covered_passes = pipeline_pass.covers_passes or (pipeline_pass.pass_id,)
        try:
            next_state = pipeline_pass.runner(state)
        except LispFrontendCompileError as exc:
            diagnostics = tuple(
                with_diagnostic_metadata(
                    diagnostic,
                    validation_pass=(
                        pipeline_pass.pass_id
                        if pipeline_pass.attach_metadata
                        and diagnostic.validation_pass is None
                        else None
                    ),
                    authority_layer=(
                        pipeline_pass.authority_layer
                        if pipeline_pass.attach_metadata
                        and diagnostic.authority_layer is None
                        else None
                    ),
                    lint_profile=lint_profile,
                )
                for diagnostic in exc.diagnostics
            )
            failing_pass = _failing_pass_id(
                pipeline_pass,
                diagnostics,
                covered_passes,
            )
            completed_passes = ()
            if failing_pass in covered_passes:
                completed_passes = covered_passes[:covered_passes.index(failing_pass)]
            for completed_pass_id in completed_passes:
                results.append(
                    ValidationPassResult(
                        pass_id=completed_pass_id,
                        authority_layer=pipeline_pass.authority_layer,
                        blocking=False,
                        diagnostics=(),
                        artifact_ready=False,
                    )
                )
            results.append(
                ValidationPassResult(
                    pass_id=failing_pass,
                    authority_layer=_authority_layer_for_diagnostics(
                        diagnostics,
                        default=pipeline_pass.authority_layer,
                    ),
                    blocking=(
                        pipeline_pass.blocking
                        and any(
                            diagnostic_effective_severity(
                                diagnostic,
                                lint_profile=lint_profile,
                            )
                            == "error"
                            for diagnostic in diagnostics
                        )
                    ),
                    diagnostics=diagnostics,
                    artifact_ready=False,
                )
            )
            if results[-1].blocking:
                break
        else:
            state = next_state or state
            artifact_ready = _artifact_ready(pipeline_pass.artifact_ready, state)
            for completed_pass_id in covered_passes:
                results.append(
                    ValidationPassResult(
                        pass_id=completed_pass_id,
                        authority_layer=pipeline_pass.authority_layer,
                        blocking=False,
                        diagnostics=(),
                        artifact_ready=artifact_ready,
                    )
                )
    return state, tuple(results)


def collect_pipeline_diagnostics(
    results: Sequence[ValidationPassResult],
) -> tuple[LispFrontendDiagnostic, ...]:
    """Return the flattened diagnostics emitted by pipeline execution."""

    return tuple(
        diagnostic
        for result in results
        for diagnostic in result.diagnostics
    )


def raise_pipeline_diagnostics(
    results: Sequence[ValidationPassResult],
    *,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> None:
    """Raise one aggregate compile error if any pipeline pass emitted diagnostics."""

    diagnostics = collect_pipeline_diagnostics(results)
    if any(
        diagnostic_effective_severity(
            diagnostic,
            lint_profile=lint_profile,
        )
        == "error"
        for diagnostic in diagnostics
    ):
        raise LispFrontendCompileError(diagnostics)


def _artifact_ready(
    artifact_ready: bool | Callable[[ValidationPipelineState], bool],
    state: ValidationPipelineState,
) -> bool:
    if callable(artifact_ready):
        return bool(artifact_ready(state))
    return artifact_ready


def _authority_layer_for_diagnostics(
    diagnostics: Sequence[LispFrontendDiagnostic],
    *,
    default: str,
) -> str:
    if not diagnostics:
        return default
    layers = {
        diagnostic.authority_layer
        for diagnostic in diagnostics
        if diagnostic.authority_layer is not None
    }
    if len(layers) == 1:
        return next(iter(layers))
    return default


def _failing_pass_id(
    pipeline_pass: ValidationPipelinePass,
    diagnostics: Sequence[LispFrontendDiagnostic],
    covered_passes: tuple[str, ...],
) -> str:
    if not diagnostics:
        return pipeline_pass.pass_id
    candidate_passes = {
        diagnostic.validation_pass
        for diagnostic in diagnostics
        if diagnostic.validation_pass is not None
    }
    if not candidate_passes:
        return pipeline_pass.pass_id
    covered_candidates = [
        pass_id for pass_id in covered_passes if pass_id in candidate_passes
    ]
    if covered_candidates:
        return covered_candidates[0]
    return min(candidate_passes, key=validation_pass_order_key)
