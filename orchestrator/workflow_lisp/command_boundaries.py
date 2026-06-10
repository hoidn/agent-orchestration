"""Frontend-owned command-boundary metadata and validation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourcePosition, SourceSpan


CertifiedAdapterBehaviorClass = Literal[
    "external_tool",
    "structured_result",
    "resource_transition",
    "resume_state_reuse",
]
CertifiedAdapterInvocationProtocol = Literal["json_object_positional_arg"]
PROMOTED_CALL_REQUIRED_METADATA_FIELDS = frozenset(
    {
        "behavior_class",
        "input_signature",
        "artifact_contracts",
        "state_writes",
        "error_codes",
        "owner_module",
        "replacement_path",
        "invocation_protocol",
    }
)


@dataclass(frozen=True)
class ExternalToolBinding:
    """Named command that can be invoked from Workflow Lisp."""

    name: str
    stable_command: tuple[str, ...]


@dataclass(frozen=True)
class CertifiedAdapterInputField:
    """One declared promoted adapter input."""

    name: str
    type_name: str
    required: bool
    transport_key: str


@dataclass(frozen=True)
class CertifiedAdapterBinding:
    """Command boundary with explicit typed workflow semantics."""

    name: str
    stable_command: tuple[str, ...]
    input_contract: Mapping[str, object]
    output_type_name: str
    effects: tuple[str, ...]
    path_safety: Mapping[str, object]
    source_map_behavior: str
    fixture_ids: tuple[str, ...]
    negative_fixture_ids: tuple[str, ...]
    behavior_class: CertifiedAdapterBehaviorClass | str | None = None
    input_signature: tuple[CertifiedAdapterInputField, ...] = ()
    artifact_contracts: tuple[str, ...] = ()
    state_writes: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()
    owner_module: str | None = None
    replacement_path: str | None = None
    invocation_protocol: CertifiedAdapterInvocationProtocol | str | None = None
    declared_promoted_fields: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CommandBoundaryEnvironment:
    """Named commands available to `command-result` forms."""

    bindings_by_name: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]


def certified_adapter_supports_promoted_calls(binding: CertifiedAdapterBinding) -> bool:
    """Return whether one certified adapter carries the promoted call metadata."""

    return bool(
        PROMOTED_CALL_REQUIRED_METADATA_FIELDS.issubset(binding.declared_promoted_fields)
        and
        binding.behavior_class
        and binding.input_signature
        and binding.owner_module
        and binding.invocation_protocol == "json_object_positional_arg"
    )


def build_command_boundary_environment(
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
) -> CommandBoundaryEnvironment:
    """Validate named command bindings supplied by the build caller."""

    diagnostics: list[LispFrontendDiagnostic] = []
    bindings: dict[str, ExternalToolBinding | CertifiedAdapterBinding] = {}

    for name, binding in (command_boundaries or {}).items():
        if not isinstance(name, str) or not name.strip():
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="command_adapter_missing_contract",
                    message="command boundary bindings require non-empty names",
                    span=_environment_span(),
                    phase="typecheck",
                )
            )
            continue
        if not binding.stable_command or not all(isinstance(token, str) and token for token in binding.stable_command):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="command_adapter_missing_contract",
                    message=f"command boundary `{name}` must declare a non-empty stable command",
                    span=_environment_span(),
                    phase="typecheck",
                )
            )
            continue
        if isinstance(binding, CertifiedAdapterBinding):
            if (
                not binding.input_contract
                or not binding.output_type_name
                or not binding.effects
                or not binding.path_safety
                or not binding.source_map_behavior
            ):
                diagnostics.append(
                    LispFrontendDiagnostic(
                        code="command_adapter_missing_contract",
                        message=f"certified adapter `{name}` is missing required contract metadata",
                        span=_environment_span(),
                        phase="typecheck",
                    )
                )
                continue
            if not binding.fixture_ids or not binding.negative_fixture_ids:
                diagnostics.append(
                    LispFrontendDiagnostic(
                        code="command_adapter_missing_contract",
                        message=f"certified adapter `{name}` requires positive and negative fixtures",
                        span=_environment_span(),
                        phase="typecheck",
                    )
                )
                continue
        bindings[name] = binding

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return CommandBoundaryEnvironment(bindings_by_name=bindings)


def _environment_span() -> SourceSpan:
    position = SourcePosition(path="<stage3-environment>", line=1, column=1, offset=0)
    return SourceSpan(start=position, end=position)
