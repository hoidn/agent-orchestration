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
G0_RETIREMENT_REQUIRED_FIELDS = frozenset(
    {
        "retirement_class",
        "retirement_label",
        "replacement_surface",
        "bridge_owner",
        "expiry_condition",
        "evidence_refs",
    }
)
G0_RETIREMENT_ALLOWED_CLASSES = frozenset(
    {
        "typed_projection",
        "outcome_classification",
        "resource_transition",
        "view_writer",
        "manifest_assembly",
        "path_materialization",
        "validation",
        "genuine_system",
        "legacy_bridge",
    }
)
G0_RETIREMENT_ALLOWED_LABELS = frozenset(
    {
        "retire_to_projection",
        "retire_to_view",
        "retire_to_transition",
        "keep_certified_system",
        "keep_bridge",
        "unknown_requires_design",
    }
)
DESIGN_DELTA_G0_HELPER_NAMES = frozenset(
    {
        "run_neurips_backlog_checks",
        "validate_review_findings_v1",
        "project_lisp_frontend_selector_action",
        "validate_lisp_frontend_design_gap_architecture",
        "materialize_lisp_frontend_work_item_inputs",
        "classify_lisp_frontend_work_item_terminal",
        "select_lisp_frontend_blocked_recovery_route",
        "record_terminal_work_item",
        "record_blocked_recovery_outcome",
        "write_lisp_frontend_drain_status",
        "finalize_lisp_frontend_drain_summary",
    }
)
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
    retirement_class: str | None = None
    retirement_label: str | None = None
    replacement_surface: str | None = None
    bridge_owner: str | None = None
    expiry_condition: str | None = None
    evidence_refs: tuple[str, ...] = ()


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
    retirement_class: str | None = None
    retirement_label: str | None = None
    replacement_surface: str | None = None
    bridge_owner: str | None = None
    expiry_condition: str | None = None
    evidence_refs: tuple[str, ...] = ()


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
        _validate_g0_retirement_metadata(name, binding, diagnostics)
        bindings[name] = binding

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return CommandBoundaryEnvironment(bindings_by_name=bindings)


def _environment_span() -> SourceSpan:
    position = SourcePosition(path="<stage3-environment>", line=1, column=1, offset=0)
    return SourceSpan(start=position, end=position)


def _validate_g0_retirement_metadata(
    name: str,
    binding: ExternalToolBinding | CertifiedAdapterBinding,
    diagnostics: list[LispFrontendDiagnostic],
) -> None:
    if name not in DESIGN_DELTA_G0_HELPER_NAMES:
        return

    values = {
        "retirement_class": getattr(binding, "retirement_class", None),
        "retirement_label": getattr(binding, "retirement_label", None),
        "replacement_surface": getattr(binding, "replacement_surface", None),
        "bridge_owner": getattr(binding, "bridge_owner", None),
        "expiry_condition": getattr(binding, "expiry_condition", None),
        "evidence_refs": getattr(binding, "evidence_refs", ()),
    }
    missing = [
        field_name
        for field_name in sorted(G0_RETIREMENT_REQUIRED_FIELDS)
        if (
            not values[field_name]
            if field_name != "evidence_refs"
            else not isinstance(values[field_name], tuple) or not values[field_name]
        )
    ]
    if missing:
        diagnostics.append(
            LispFrontendDiagnostic(
                code="command_adapter_missing_contract",
                message=(
                    f"design-delta command boundary `{name}` is missing required G0 retirement metadata: "
                    + ", ".join(missing)
                ),
                span=_environment_span(),
                phase="typecheck",
            )
        )
        return
    retirement_class = values["retirement_class"]
    if retirement_class not in G0_RETIREMENT_ALLOWED_CLASSES:
        diagnostics.append(
            LispFrontendDiagnostic(
                code="command_adapter_missing_contract",
                message=f"design-delta command boundary `{name}` uses unknown retirement_class `{retirement_class}`",
                span=_environment_span(),
                phase="typecheck",
            )
        )
    retirement_label = values["retirement_label"]
    if retirement_label not in G0_RETIREMENT_ALLOWED_LABELS:
        diagnostics.append(
            LispFrontendDiagnostic(
                code="command_adapter_missing_contract",
                message=f"design-delta command boundary `{name}` uses unknown retirement_label `{retirement_label}`",
                span=_environment_span(),
                phase="typecheck",
            )
        )
    for field_name in ("replacement_surface", "bridge_owner", "expiry_condition"):
        value = values[field_name]
        if not isinstance(value, str) or not value.strip():
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="command_adapter_missing_contract",
                    message=f"design-delta command boundary `{name}` requires non-empty `{field_name}`",
                    span=_environment_span(),
                    phase="typecheck",
                )
            )
    evidence_refs = values["evidence_refs"]
    if not isinstance(evidence_refs, tuple) or any(not isinstance(item, str) or not item for item in evidence_refs):
        diagnostics.append(
            LispFrontendDiagnostic(
                code="command_adapter_missing_contract",
                message=f"design-delta command boundary `{name}` requires non-empty string `evidence_refs`",
                span=_environment_span(),
                phase="typecheck",
            )
        )
