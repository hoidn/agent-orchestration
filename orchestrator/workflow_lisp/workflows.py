"""Elaborate `defworkflow` forms and register callable workflow boundaries.

This module turns syntax-layer workflow definitions into typed call signatures,
checks that frontend record/union boundaries can be represented by current
workflow contracts, imports signatures from validated workflow bundles, and
typechecks workflow bodies against local procedures, externs, and command
boundaries.

See `../../docs/design/workflow_lisp_frontend_mvp_specification.md` for the supported
`defworkflow` scope and `../../docs/design/workflow_lisp_core_workflow_ast.md` for
the planned syntax-neutral workflow representation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from orchestrator.workflow.loaded_bundle import (
    workflow_boundary_projection,
    workflow_input_contracts,
    workflow_output_contracts,
    workflow_public_input_contracts,
)

from .command_boundaries import (
    CertifiedAdapterBinding,
    CommandBoundaryEnvironment,
    ExternalToolBinding,
    build_command_boundary_environment,
)
from .context_classification import classify_structural_private_exec_context
from .definitions import WorkflowLispModule
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from .entry_publication import EntryPublicationPolicy, parse_entry_publication_policy, validate_entry_publication_policy
from .expression_traversal import walk_expr
from .expressions import CallExpr, elaborate_expression
from .family_profiles import WorkflowFamilyProfileCatalog
from .lints import required_lint_diagnostic
from .macros import collect_macro_catalog, expand_module_forms
from .phase import (
    PHASE_CONTEXT_NAME,
    derived_private_child_context_eligibility,
    derive_promoted_entry_hidden_context_metadata,
    eligible_private_context_source_param_names,
    private_exec_context_kind,
    PromotedEntryHiddenContextRequirement,
)
from .procedure_refs import ProcRefResolutionContext
from .procedures import ProcedureCatalog
from .spans import SourceSpan
from .spans import SourcePosition
from .syntax import (
    ExpansionStack,
    SyntaxIdentifier,
    SyntaxFloat,
    SyntaxInt,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    SyntaxBool,
    WorkflowLispSyntaxModule,
    syntax_head,
    syntax_head_name,
    syntax_identifier,
    syntax_node_datum,
    syntax_resolved_name,
)
from .type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
    type_refs_compatible,
)
from .typecheck import (
    TypedExpr,
    clear_active_reusable_state_producer_context,
    clear_active_workflow_signature,
    set_active_reusable_state_producer_context,
    set_active_workflow_signature,
    typecheck_expression,
)

if TYPE_CHECKING:
    from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
    from .functions import FunctionCatalog
    from .lowering import LoweredWorkflow
    from .procedures import TypedProcedureDef


@dataclass(frozen=True)
class ProviderExtern:
    """Provider alias supplied from the build environment."""

    name: str
    provider_id: str


PromptExternSourceKind = Literal["asset_file", "input_file"]
PromptExternBindingValue = "PromptExtern | str | Mapping[str, object]"


@dataclass(frozen=True, init=False)
class PromptExtern:
    """Prompt binding supplied from the build environment.

    The canonical shape records the prompt source surface explicitly while
    keeping the legacy ``asset_file=...`` constructor/property surface for
    current direct callers.
    """

    name: str
    source_kind: PromptExternSourceKind
    path: str

    def __init__(
        self,
        *,
        name: str,
        source_kind: PromptExternSourceKind | None = None,
        path: str | None = None,
        asset_file: str | None = None,
        input_file: str | None = None,
    ) -> None:
        raw_value: dict[str, object] = {}
        if source_kind is not None:
            raw_value["source_kind"] = source_kind
        if path is not None:
            raw_value["path"] = path
        if asset_file is not None:
            raw_value["asset_file"] = asset_file
        if input_file is not None:
            raw_value["input_file"] = input_file
        resolved_source_kind, resolved_path = _coerce_prompt_extern_source(
            name=name,
            raw_value=raw_value,
            allow_prompt_extern_instance=False,
        )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "source_kind", resolved_source_kind)
        object.__setattr__(self, "path", resolved_path)

    @property
    def asset_file(self) -> str | None:
        return self.path if self.source_kind == "asset_file" else None

    @property
    def input_file(self) -> str | None:
        return self.path if self.source_kind == "input_file" else None


@dataclass(frozen=True)
class ExternEnvironment:
    """Provider and prompt bindings supplied by the build caller.

    `.orc` source refers to providers and prompt assets by name. The build
    environment resolves those names to provider ids and prompt file paths
    before typechecking and lowering.
    """

    bindings_by_name: Mapping[str, ProviderExtern | PromptExtern]


def prompt_extern_source_payload(binding: PromptExtern) -> dict[str, str]:
    """Serialize one prompt extern to its canonical source-aware payload."""

    return {binding.source_kind: binding.path}


def prompt_extern_legacy_binding_value(binding: PromptExtern) -> str | None:
    """Return the legacy string-valued binding view for asset-backed prompts."""

    return binding.asset_file


def normalize_prompt_extern_binding(
    name: str,
    raw_value: PromptExtern | str | Mapping[str, object],
) -> PromptExtern:
    """Validate and normalize one prompt extern binding."""

    source_kind, path = _coerce_prompt_extern_source(name=name, raw_value=raw_value)
    return PromptExtern(name=name, source_kind=source_kind, path=path)


def normalize_public_prompt_extern_binding(
    name: str,
    raw_value: str | Mapping[str, object],
) -> PromptExtern:
    """Validate one authored manifest binding without exposing internal shapes."""

    source_kind, path = _coerce_prompt_extern_source(
        name=name,
        raw_value=raw_value,
        allow_prompt_extern_instance=False,
        allow_canonical_source_payload=False,
    )
    return PromptExtern(name=name, source_kind=source_kind, path=path)


def normalize_prompt_extern_bindings(
    prompt_externs: Mapping[str, PromptExtern | str | Mapping[str, object]] | None,
) -> dict[str, PromptExtern]:
    """Validate and normalize prompt extern bindings keyed by authored name."""

    return {
        name: normalize_prompt_extern_binding(name, raw_value)
        for name, raw_value in (prompt_externs or {}).items()
    }


def prompt_extern_source_bindings_payload(
    prompt_externs: Mapping[str, PromptExtern | str | Mapping[str, object]] | None,
) -> dict[str, dict[str, str]]:
    """Return canonical source-aware payloads keyed by authored prompt name."""

    bindings = normalize_prompt_extern_bindings(prompt_externs)
    return {
        name: prompt_extern_source_payload(binding)
        for name, binding in sorted(bindings.items())
    }


def prompt_extern_legacy_bindings(
    prompt_externs: Mapping[str, PromptExtern | str | Mapping[str, object]] | None,
) -> dict[str, str]:
    """Return the legacy string-valued asset-backed prompt binding view."""

    bindings = normalize_prompt_extern_bindings(prompt_externs)
    return {
        name: binding.path
        for name, binding in sorted(bindings.items())
        if binding.source_kind == "asset_file"
    }


def _coerce_prompt_extern_source(
    *,
    name: str,
    raw_value: PromptExtern | str | Mapping[str, object],
    allow_prompt_extern_instance: bool = True,
    allow_canonical_source_payload: bool = True,
) -> tuple[PromptExternSourceKind, str]:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("require non-empty authored names")
    if allow_prompt_extern_instance and isinstance(raw_value, PromptExtern):
        return raw_value.source_kind, raw_value.path
    if isinstance(raw_value, str):
        if not raw_value.strip():
            raise ValueError("require non-empty string shorthand values")
        return "asset_file", raw_value
    if not isinstance(raw_value, Mapping):
        raise ValueError("must map names to string values or source objects")

    if "source_kind" in raw_value or "path" in raw_value:
        if not allow_canonical_source_payload:
            raise ValueError("canonical source payloads are not a public manifest shape")
        source_kind = raw_value.get("source_kind")
        path = raw_value.get("path")
        if source_kind not in ("asset_file", "input_file"):
            raise ValueError("canonical bindings require `source_kind` of `asset_file` or `input_file`")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("canonical bindings require non-empty string `path` values")
        return source_kind, path

    allowed_keys = ("asset_file", "input_file")
    present_keys = tuple(key for key in allowed_keys if key in raw_value)
    unknown_keys = tuple(key for key in raw_value if key not in allowed_keys)
    if unknown_keys or len(present_keys) != 1:
        raise ValueError("source objects must contain exactly one of `asset_file` or `input_file`")
    source_kind = present_keys[0]
    path = raw_value[source_kind]
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"`{source_kind}` values must be non-empty strings")
    return source_kind, path

@dataclass(frozen=True)
class WorkflowParam:
    """Authored `defworkflow` parameter before type resolution."""

    name: str
    type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    default_value: "WorkflowParamDefault | None" = None


@dataclass(frozen=True)
class WorkflowParamDefault:
    """Authored workflow-boundary default with source provenance."""

    syntax: SyntaxNode
    normalized_value: object | None = None

    @property
    def datum(self) -> object:
        datum = self.syntax.datum
        if isinstance(datum, (SyntaxString, SyntaxInt, SyntaxBool)):
            return datum.value
        if isinstance(datum, SyntaxIdentifier):
            return datum.resolved_name
        if isinstance(datum, SyntaxKeyword):
            return datum.value
        return datum

    @property
    def span(self) -> SourceSpan:
        return self.syntax.span

    @property
    def form_path(self) -> tuple[str, ...]:
        return self.syntax.form_path

    @property
    def expansion_stack(self) -> ExpansionStack:
        return self.syntax.expansion_stack


@dataclass(frozen=True)
class WorkflowDef:
    """Parsed workflow definition with signature text and body syntax."""

    name: str
    params: tuple[WorkflowParam, ...]
    return_type_name: str
    body: SyntaxNode
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    publication_policy: EntryPublicationPolicy | None = None



@dataclass(frozen=True)
class WorkflowSignature:
    """Type-resolved workflow call boundary."""

    name: str
    params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: TypeRef
    span: SourceSpan
    form_path: tuple[str, ...]
    param_defaults: Mapping[str, WorkflowParamDefault] = field(default_factory=dict)
    hidden_context_requirements: Mapping[str, PromotedEntryHiddenContextRequirement] = field(default_factory=dict)
    hidden_context_ambiguities: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    private_compatibility_bridge_types: Mapping[str, TypeRef] = field(default_factory=dict)
    allow_hidden_context_binding: bool = False
    allow_private_compatibility_bridge_omission: bool = False
    allowed_hidden_context_callees: frozenset[str] = frozenset()
    derived_hidden_context_callees: frozenset[str] = frozenset()
    entry_hidden_context_callees: frozenset[str] = frozenset()
    allowed_private_compatibility_bridge_callees: frozenset[str] = frozenset()


@dataclass(frozen=True)
class TypedWorkflowDef:
    """Workflow definition after body typechecking and effect analysis."""

    definition: WorkflowDef
    signature: WorkflowSignature
    typed_body: TypedExpr
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY
    specialization: object | None = None


@dataclass(frozen=True)
class WorkflowCatalog:
    """Lookup table for local and imported workflow call signatures."""

    signatures_by_name: Mapping[str, WorkflowSignature]
    definitions_by_name: Mapping[str, WorkflowDef]
    imported_bundles_by_name: Mapping[str, "LoadedWorkflowBundle"]
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None


@dataclass(frozen=True)
class Stage3CompileResult:
    """Compiled module result after typecheck, lowering, and shared validation."""

    module: WorkflowLispModule
    workflow_catalog: WorkflowCatalog
    procedure_catalog: ProcedureCatalog
    extern_environment: ExternEnvironment
    command_boundary_environment: CommandBoundaryEnvironment
    typed_procedures: tuple["TypedProcedureDef", ...]
    typed_workflows: tuple[TypedWorkflowDef, ...]
    lowered_workflows: tuple["LoweredWorkflow", ...]
    validated_bundles: Mapping[str, "LoadedWorkflowBundle"]
    diagnostics: tuple[LispFrontendDiagnostic, ...] = ()
    validation_profile: object | None = None
    retained_non_promotable_diagnostics: tuple[LispFrontendDiagnostic, ...] = ()
    lowering_schema_version: int = 1


@dataclass(frozen=True)
class WorkflowBoundaryAnalysis:
    """Whether a frontend type can be represented by current workflow contracts."""

    lowerable: bool
    contains_json: bool
    contains_provider_or_prompt: bool
    contains_workflow_ref: bool
    contains_proc_ref: bool
    contains_union: bool
    contains_collection: bool
    offending_path: tuple[str, ...] = ()
    offending_type_name: str | None = None


def _phase_family_hidden_context_requirements(
    signature: WorkflowSignature,
    requirements: Mapping[str, PromotedEntryHiddenContextRequirement],
    *,
    workflow_catalog: WorkflowCatalog,
) -> Mapping[str, PromotedEntryHiddenContextRequirement]:
    family_profile_catalog = workflow_catalog.family_profile_catalog
    if family_profile_catalog is None:
        return requirements
    hidden_context_rule = family_profile_catalog.hidden_context_rule(signature.name)
    if hidden_context_rule is None:
        return requirements

    updated = dict(requirements)
    params_by_name = dict(signature.params)
    named_type_ref = params_by_name.get(hidden_context_rule.parameter_name)
    if (
        named_type_ref is not None
        and private_exec_context_kind(named_type_ref) != PHASE_CONTEXT_NAME
    ):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_family_profile_hidden_context_invalid",
                    message=(
                        "workflow family profile hidden-context rule must bind a "
                        f"structural `{PHASE_CONTEXT_NAME}` parameter on "
                        f"`{signature.name}`, but `{hidden_context_rule.parameter_name}` "
                        "does not"
                    ),
                    span=signature.span,
                    form_path=signature.form_path,
                    phase="workflow_family_profile",
                ),
            )
        )

    structural_phase_context_params = [
        param_name
        for param_name, type_ref in signature.params
        if private_exec_context_kind(type_ref) == PHASE_CONTEXT_NAME
    ]
    if named_type_ref is not None:
        selected_param_names = [hidden_context_rule.parameter_name]
    elif len(structural_phase_context_params) == 1:
        selected_param_names = structural_phase_context_params
    else:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_family_profile_hidden_context_invalid",
                    message=(
                        "workflow family profile hidden-context rule must resolve to "
                        f"exactly one structural `{PHASE_CONTEXT_NAME}` parameter on "
                        f"`{signature.name}`"
                    ),
                    span=signature.span,
                    form_path=signature.form_path,
                    phase="workflow_family_profile",
                ),
            )
        )

    for param_name in selected_param_names:
        existing = updated.get(param_name)
        if existing is not None and existing.context_kind != PHASE_CONTEXT_NAME:
            continue
        updated[param_name] = PromotedEntryHiddenContextRequirement(
            param_name=param_name,
            context_kind=PHASE_CONTEXT_NAME,
            phase_name=hidden_context_rule.phase_identity,
            binding_kind="derived_private_child_context",
            allows_entry_bootstrap=(
                existing is not None
                and (
                    existing.binding_kind != "derived_private_child_context"
                    or existing.allows_entry_bootstrap
                )
            ),
        )
    return updated


def analyze_workflow_boundary_type(
    type_ref: TypeRef,
    *,
    source_path: tuple[str, ...] = (),
    allow_union: bool = False,
    allow_top_level_workflow_ref: bool = False,
) -> WorkflowBoundaryAnalysis:
    """Return whether one workflow-boundary type can lower to shared contracts."""

    if isinstance(type_ref, PathTypeRef):
        return WorkflowBoundaryAnalysis(
            lowerable=True,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=False,
            contains_proc_ref=False,
            contains_union=False,
            contains_collection=False,
        )
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.name == "Json":
            return WorkflowBoundaryAnalysis(
                lowerable=False,
                contains_json=True,
                contains_provider_or_prompt=False,
                contains_workflow_ref=False,
                contains_proc_ref=False,
                contains_union=False,
                contains_collection=False,
                offending_path=source_path,
                offending_type_name=type_ref.name,
            )
        if type_ref.name in {"Provider", "Prompt"}:
            return WorkflowBoundaryAnalysis(
                lowerable=False,
                contains_json=False,
                contains_provider_or_prompt=True,
                contains_workflow_ref=False,
                contains_proc_ref=False,
                contains_union=False,
                contains_collection=False,
                offending_path=source_path,
                offending_type_name=type_ref.name,
            )
        return WorkflowBoundaryAnalysis(
            lowerable=True,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=False,
            contains_proc_ref=False,
            contains_union=False,
            contains_collection=False,
        )
    if isinstance(type_ref, WorkflowRefTypeRef):
        for index, param_type_ref in enumerate(type_ref.param_type_refs):
            analysis = analyze_workflow_boundary_type(
                param_type_ref,
                source_path=source_path + (f"param_{index}",),
                allow_union=False,
                allow_top_level_workflow_ref=False,
            )
            if analysis.contains_collection:
                return WorkflowBoundaryAnalysis(
                    lowerable=False,
                    contains_json=analysis.contains_json,
                    contains_provider_or_prompt=analysis.contains_provider_or_prompt,
                    contains_workflow_ref=True,
                    contains_proc_ref=analysis.contains_proc_ref,
                    contains_union=analysis.contains_union,
                    contains_collection=True,
                    offending_path=analysis.offending_path or source_path,
                    offending_type_name=analysis.offending_type_name or type_ref.name,
                )
            if not analysis.lowerable:
                return analysis
        return_analysis = analyze_workflow_boundary_type(
            type_ref.return_type_ref,
            source_path=source_path + ("return",),
            allow_union=True,
            allow_top_level_workflow_ref=False,
        )
        if return_analysis.contains_collection:
            return WorkflowBoundaryAnalysis(
                lowerable=False,
                contains_json=return_analysis.contains_json,
                contains_provider_or_prompt=return_analysis.contains_provider_or_prompt,
                contains_workflow_ref=True,
                contains_proc_ref=return_analysis.contains_proc_ref,
                contains_union=return_analysis.contains_union,
                contains_collection=True,
                offending_path=return_analysis.offending_path or source_path,
                offending_type_name=return_analysis.offending_type_name or type_ref.name,
            )
        if not return_analysis.lowerable:
            return return_analysis
        if allow_top_level_workflow_ref:
            return WorkflowBoundaryAnalysis(
                lowerable=True,
                contains_json=False,
                contains_provider_or_prompt=False,
                contains_workflow_ref=False,
                contains_proc_ref=False,
                contains_union=False,
                contains_collection=False,
            )
        return WorkflowBoundaryAnalysis(
            lowerable=False,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=True,
            contains_proc_ref=False,
            contains_union=False,
            contains_collection=False,
            offending_path=source_path,
            offending_type_name=type_ref.name,
        )
    if isinstance(type_ref, ProcRefTypeRef):
        return WorkflowBoundaryAnalysis(
            lowerable=False,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=False,
            contains_proc_ref=True,
            contains_union=False,
            contains_collection=False,
            offending_path=source_path,
            offending_type_name=type_ref.name,
        )
    if isinstance(type_ref, ListTypeRef):
        analysis = analyze_workflow_boundary_type(
            type_ref.item_type_ref,
            source_path=source_path + ("item",),
            allow_union=False,
            allow_top_level_workflow_ref=False,
        )
        if not analysis.lowerable:
            return analysis
        return WorkflowBoundaryAnalysis(
            lowerable=True,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=False,
            contains_proc_ref=False,
            contains_union=False,
            contains_collection=True,
        )
    if isinstance(type_ref, OptionalTypeRef):
        analysis = analyze_workflow_boundary_type(
            type_ref.item_type_ref,
            source_path=source_path + ("item",),
            allow_union=False,
            allow_top_level_workflow_ref=False,
        )
        if not analysis.lowerable:
            return analysis
        return WorkflowBoundaryAnalysis(
            lowerable=False,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=False,
            contains_proc_ref=False,
            contains_union=False,
            contains_collection=True,
            offending_path=source_path,
            offending_type_name=type_ref.name,
        )
    if isinstance(type_ref, MapTypeRef):
        key_analysis = analyze_workflow_boundary_type(
            type_ref.key_type_ref,
            source_path=source_path + ("key",),
            allow_union=False,
            allow_top_level_workflow_ref=False,
        )
        if not key_analysis.lowerable:
            return key_analysis
        value_analysis = analyze_workflow_boundary_type(
            type_ref.value_type_ref,
            source_path=source_path + ("value",),
            allow_union=False,
            allow_top_level_workflow_ref=False,
        )
        if not value_analysis.lowerable:
            return value_analysis
        return WorkflowBoundaryAnalysis(
            lowerable=False,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=False,
            contains_proc_ref=False,
            contains_union=False,
            contains_collection=True,
            offending_path=source_path,
            offending_type_name=type_ref.name,
        )
    if isinstance(type_ref, RecordTypeRef):
        for field in type_ref.definition.fields:
            field_type = type_ref.field_types.get(field.name)
            if field_type is None:
                raise TypeError(f"missing resolved field type for `{type_ref.name}.{field.name}`")
            analysis = analyze_workflow_boundary_type(
                field_type,
                source_path=source_path + (field.name,),
                allow_union=allow_union,
                allow_top_level_workflow_ref=False,
            )
            if not analysis.lowerable or analysis.contains_collection:
                return analysis
        return WorkflowBoundaryAnalysis(
            lowerable=True,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=False,
            contains_proc_ref=False,
            contains_union=False,
            contains_collection=False,
        )
    if isinstance(type_ref, UnionTypeRef):
        if allow_union:
            for variant in type_ref.definition.variants:
                for field in variant.fields:
                    field_type = type_ref.variant_field_types[variant.name][field.name]
                    analysis = analyze_workflow_boundary_type(
                        field_type,
                        source_path=source_path + (variant.name, field.name),
                        allow_union=False,
                        allow_top_level_workflow_ref=False,
                    )
                    if not analysis.lowerable or analysis.contains_collection:
                        return analysis
            return WorkflowBoundaryAnalysis(
                lowerable=True,
                contains_json=False,
                contains_provider_or_prompt=False,
                contains_workflow_ref=False,
                contains_proc_ref=False,
                contains_union=False,
                contains_collection=False,
            )
        return WorkflowBoundaryAnalysis(
            lowerable=False,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_workflow_ref=False,
            contains_proc_ref=False,
            contains_union=True,
            contains_collection=False,
            offending_path=source_path,
            offending_type_name=type_ref.name,
        )
    raise TypeError(f"unsupported workflow-boundary type reference: {type(type_ref)!r}")


def elaborate_workflow_definitions(module_syntax: WorkflowLispSyntaxModule) -> tuple[WorkflowDef, ...]:
    """Elaborate all top-level `defworkflow` forms from one syntax module."""

    expanded_module = expand_module_forms(
        module_syntax,
        catalog=collect_macro_catalog(module_syntax),
    )
    definitions: list[WorkflowDef] = []
    for form in expanded_module.forms:
        if syntax_resolved_name(syntax_head(form)) == "defworkflow":
            definitions.append(_elaborate_workflow_definition(form))
    return tuple(definitions)


def build_workflow_catalog(
    module: WorkflowLispModule,
    workflow_defs: tuple[WorkflowDef, ...],
    type_env: FrontendTypeEnvironment,
    *,
    imported_signatures: Mapping[str, WorkflowSignature] | None = None,
    lookup_aliases: Mapping[str, str] | None = None,
    imported_workflow_bundles: Mapping[str, "LoadedWorkflowBundle"] | None = None,
    allow_hidden_context_callers: bool = False,
    selected_entry_workflow_name: str | None = None,
    allow_collection_input_boundaries: bool = False,
    allow_collection_return_boundaries: bool = False,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
) -> WorkflowCatalog:
    """Build same-file workflow signatures before any body is typechecked."""
    from .contracts import is_transportable_result_type
    from .phase_family_boundary import (
        is_compatibility_bridge_param,
        is_selected_phase_family_workflow,
    )

    signatures_by_name: dict[str, WorkflowSignature] = dict(imported_signatures or {})
    for imported_name, imported_bundle in (imported_workflow_bundles or {}).items():
        imported_signature = signatures_by_name.get(imported_name)
        if imported_signature is None:
            continue
        signatures_by_name[imported_name] = _merge_signature_compatibility_bridge_types(
            imported_signature,
            bundle=imported_bundle,
            type_env=type_env,
        )
    definitions_by_name: dict[str, WorkflowDef] = {}
    diagnostics: list[LispFrontendDiagnostic] = []
    for workflow_def in workflow_defs:
        if workflow_def.name in definitions_by_name:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="workflow_definition_duplicate",
                    message=f"duplicate workflow definition `{workflow_def.name}`",
                    span=workflow_def.span,
                    form_path=workflow_def.form_path,
                    expansion_stack=workflow_def.expansion_stack,
                )
            )
            continue
        return_type_ref = type_env.resolve_type(
            workflow_def.return_type_name,
            span=workflow_def.span,
            form_path=workflow_def.form_path,
            expansion_stack=workflow_def.expansion_stack,
        )
        if not is_transportable_result_type(return_type_ref):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="workflow_return_type_invalid",
                    message=(
                        f"workflow `{workflow_def.name}` must return a transportable result type, "
                        f"got `{workflow_def.return_type_name}`"
                    ),
                    span=workflow_def.span,
                    form_path=workflow_def.form_path,
                    expansion_stack=workflow_def.expansion_stack,
                )
            )
            continue
        if not isinstance(return_type_ref, (RecordTypeRef, UnionTypeRef)):
            # Root-valued public returns are a DSL v2.15 contract; transportability
            # (checked above) is the only additional gate for them, so the Stage 3
            # record/union boundary-flattening analysis below does not apply.
            if not _target_dsl_supports_root_workflow_returns(module.target_dsl_version):
                diagnostics.append(
                    LispFrontendDiagnostic(
                        code="workflow_root_return_target_dsl_unsupported",
                        message=(
                            f"workflow `{workflow_def.name}` returns "
                            f"`{workflow_def.return_type_name}` directly, which requires "
                            'DSL 2.15; declare `(:target-dsl "2.15")` in the module header'
                        ),
                        span=workflow_def.span,
                        form_path=workflow_def.form_path,
                        expansion_stack=workflow_def.expansion_stack,
                    )
                )
                continue
        else:
            return_analysis = analyze_workflow_boundary_type(
                return_type_ref,
                source_path=("return",),
                allow_union=True,
            )
            return_diagnostic = _boundary_diagnostic(
                workflow_name=workflow_def.name,
                analysis=return_analysis,
                span=workflow_def.span,
                form_path=workflow_def.form_path,
                expansion_stack=workflow_def.expansion_stack,
                allow_collection_boundaries=allow_collection_return_boundaries,
            )
            if return_diagnostic is not None:
                diagnostics.append(return_diagnostic)
                continue
        params: list[tuple[str, TypeRef]] = []
        private_compatibility_bridge_types: dict[str, TypeRef] = {}
        param_defaults: dict[str, WorkflowParamDefault] = {}
        workflow_invalid = False
        for param in workflow_def.params:
            param_type = type_env.resolve_type(
                param.type_name,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
            )
            param_analysis = analyze_workflow_boundary_type(
                param_type,
                source_path=(param.name,),
                allow_top_level_workflow_ref=True,
            )
            param_diagnostic = _boundary_diagnostic(
                workflow_name=workflow_def.name,
                analysis=param_analysis,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
                allow_collection_boundaries=allow_collection_input_boundaries,
            )
            if param_diagnostic is not None:
                diagnostics.append(param_diagnostic)
                workflow_invalid = True
                continue
            params.append((param.name, param_type))
            if is_compatibility_bridge_param(param.name, param_type):
                private_compatibility_bridge_types[param.name] = param_type
            if param.default_value is not None:
                try:
                    param_defaults[param.name] = _resolve_workflow_param_default(
                        param=param,
                        param_type=param_type,
                    )
                except LispFrontendCompileError as exc:
                    diagnostics.extend(exc.diagnostics)
                    workflow_invalid = True
        if workflow_invalid:
            continue
        signature = WorkflowSignature(
            name=workflow_def.name,
            params=tuple(params),
            return_type_ref=return_type_ref,
            span=workflow_def.span,
            form_path=workflow_def.form_path,
            param_defaults=param_defaults,
            private_compatibility_bridge_types=private_compatibility_bridge_types,
            allow_private_compatibility_bridge_omission=False,
        )
        definitions_by_name[workflow_def.name] = workflow_def
        signatures_by_name[workflow_def.name] = signature

    derived_hidden_context_callees_by_workflow: Mapping[str, frozenset[str]] = {}
    entry_hidden_context_callees_by_workflow: Mapping[str, frozenset[str]] = {}
    if allow_hidden_context_callers:
        derived_hidden_context_callees_by_workflow = _shared_proof_hidden_context_omission_callees(
            module=module,
            selected_entry_workflow_name=selected_entry_workflow_name,
            workflow_defs=workflow_defs,
            signatures_by_name=signatures_by_name,
        )
    selected_entry_hidden_context_callees_by_workflow = (
        _selected_entry_hidden_context_omission_callees(
            module=module,
            selected_entry_workflow_name=selected_entry_workflow_name,
            workflow_defs=workflow_defs,
            signatures_by_name=signatures_by_name,
            filter_entry_bootstrap_callees=False,
        )
    )
    entry_hidden_context_callees_by_workflow = _selected_entry_hidden_context_omission_callees(
        module=module,
        selected_entry_workflow_name=selected_entry_workflow_name,
        workflow_defs=workflow_defs,
        signatures_by_name=signatures_by_name,
        filter_entry_bootstrap_callees=True,
    )
    hidden_context_callees_by_workflow: Mapping[str, frozenset[str]] = {
        workflow_name: frozenset(
            set(derived_hidden_context_callees_by_workflow.get(workflow_name, frozenset()))
            | set(selected_entry_hidden_context_callees_by_workflow.get(workflow_name, frozenset()))
        )
        for workflow_name in set(derived_hidden_context_callees_by_workflow).union(
            selected_entry_hidden_context_callees_by_workflow
        )
    }
    compatibility_bridge_callees_by_workflow = (
        _shared_proof_compatibility_bridge_omission_callees(
            module=module,
            workflow_defs=workflow_defs,
            signatures_by_name=signatures_by_name,
        )
        )
    workflow_ref_bridge_omission_workflows = {
        workflow_def.name
        for workflow_def in workflow_defs
        if _workflow_omits_private_compatibility_bridge_via_workflow_ref(
            workflow_def,
            signatures_by_name=signatures_by_name,
        )
    }
    merged_compatibility_bridge_types_by_workflow = (
        _merged_private_compatibility_bridge_types_by_workflow(
            workflow_defs=workflow_defs,
            signatures_by_name=signatures_by_name,
        )
    )
    for workflow_name in set(hidden_context_callees_by_workflow).union(
        compatibility_bridge_callees_by_workflow
    ).union(merged_compatibility_bridge_types_by_workflow).union(
        workflow_ref_bridge_omission_workflows
    ):
        signature = signatures_by_name[workflow_name]
        hidden_context_callees = hidden_context_callees_by_workflow.get(workflow_name, frozenset())
        compatibility_bridge_callees = compatibility_bridge_callees_by_workflow.get(
            workflow_name,
            frozenset(),
        )
        compatibility_bridge_types = merged_compatibility_bridge_types_by_workflow.get(
            workflow_name,
            signature.private_compatibility_bridge_types,
        )
        signatures_by_name[workflow_name] = WorkflowSignature(
            name=signature.name,
            params=signature.params,
            return_type_ref=signature.return_type_ref,
            span=signature.span,
            form_path=signature.form_path,
            param_defaults=signature.param_defaults,
            hidden_context_requirements=signature.hidden_context_requirements,
            hidden_context_ambiguities=signature.hidden_context_ambiguities,
            private_compatibility_bridge_types=compatibility_bridge_types,
            allow_hidden_context_binding=bool(hidden_context_callees),
            allow_private_compatibility_bridge_omission=bool(
                compatibility_bridge_callees
            )
            or workflow_name in workflow_ref_bridge_omission_workflows,
            allowed_hidden_context_callees=hidden_context_callees,
            derived_hidden_context_callees=derived_hidden_context_callees_by_workflow.get(
                workflow_name,
                frozenset(),
            ),
            entry_hidden_context_callees=entry_hidden_context_callees_by_workflow.get(
                workflow_name,
                frozenset(),
            ),
            allowed_private_compatibility_bridge_callees=compatibility_bridge_callees,
        )

    for imported_name, imported_bundle in (imported_workflow_bundles or {}).items():
        if imported_name in signatures_by_name:
            if imported_signatures is not None and imported_name in imported_signatures:
                continue
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="workflow_definition_duplicate",
                    message=f"duplicate workflow definition `{imported_name}`",
                    span=_bundle_source_span(imported_bundle),
                    form_path=("workflow-lisp", imported_name),
                )
            )
            continue
        signatures_by_name[imported_name] = _signature_from_imported_bundle(
            imported_name,
            imported_bundle,
            type_env=type_env,
        )
    for alias_name, canonical_name in (lookup_aliases or {}).items():
        signature = signatures_by_name.get(canonical_name)
        if signature is not None:
            signatures_by_name[alias_name] = signature

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return WorkflowCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        imported_bundles_by_name=dict(imported_workflow_bundles or {}),
        family_profile_catalog=family_profile_catalog,
    )


def _shared_proof_hidden_context_omission_callees(
    *,
    module: WorkflowLispModule,
    selected_entry_workflow_name: str | None,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> Mapping[str, frozenset[str]]:
    """Return the approved proof-route callees for hidden context omission."""

    proof_worker_names = _shared_proof_hidden_context_seed_workflow_names(
        module=module,
        selected_entry_workflow_name=selected_entry_workflow_name,
        workflow_defs=workflow_defs,
        signatures_by_name=signatures_by_name,
    )
    allowed_workflow_names = set(
        _shared_proof_hidden_context_workflow_names(
            module=module,
            selected_entry_workflow_name=selected_entry_workflow_name,
            workflow_defs=workflow_defs,
            signatures_by_name=signatures_by_name,
        )
    )
    allowed_workflow_names.update(proof_worker_names)
    if not allowed_workflow_names:
        return {}
    proof_route_names = set(proof_worker_names)
    proof_route_names.update(
        _transitive_local_callers(
            workflow_defs=workflow_defs,
            target_names=proof_worker_names,
        )
    )
    omitted_callees_by_workflow = _omitted_private_exec_context_callees_by_workflow(
        workflow_defs=workflow_defs,
        signatures_by_name=signatures_by_name,
    )
    allowed: dict[str, frozenset[str]] = {}
    for workflow_name in allowed_workflow_names:
        omitted_callees = omitted_callees_by_workflow.get(workflow_name, frozenset())
        if workflow_name in proof_worker_names:
            approved_callees = omitted_callees
        else:
            approved_callees = frozenset(
                callee_name for callee_name in omitted_callees if callee_name in proof_route_names
            )
        if approved_callees:
            allowed[workflow_name] = approved_callees
    return allowed


def _selected_entry_hidden_context_omission_callees(
    *,
    module: WorkflowLispModule,
    selected_entry_workflow_name: str | None,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
    filter_entry_bootstrap_callees: bool,
) -> Mapping[str, frozenset[str]]:
    """Return omitted hidden-context callees for promoted-entry wrappers."""

    omitted_callees_by_workflow = _omitted_private_exec_context_callees_by_workflow(
        workflow_defs=workflow_defs,
        signatures_by_name=signatures_by_name,
    )
    if not omitted_callees_by_workflow:
        return {}

    workflow_name_by_local_name = {
        workflow_def.name.rsplit("::", 1)[-1]: workflow_def.name for workflow_def in workflow_defs
    }
    local_workflow_names = frozenset(workflow_name_by_local_name.values())
    exported_workflow_names = frozenset(
        workflow_name_by_local_name.get(exported_name, exported_name)
        for exported_name in module.exports
        if isinstance(exported_name, str)
        and workflow_name_by_local_name.get(exported_name, exported_name) in signatures_by_name
    )

    def _callee_allows_entry_bootstrap(callee_name: str) -> bool:
        callee_signature = signatures_by_name.get(callee_name)
        if callee_signature is None:
            return False
        return any(
            getattr(requirement, "allows_entry_bootstrap", False)
            for requirement in callee_signature.hidden_context_requirements.values()
        )

    def _entry_bootstrap_callees(callees: frozenset[str] | None) -> frozenset[str]:
        if not callees:
            return frozenset()
        if not filter_entry_bootstrap_callees:
            return callees
        return frozenset(
            callee_name
            for callee_name in callees
            if callee_name not in local_workflow_names
            or callee_name in exported_workflow_names
            or _callee_allows_entry_bootstrap(callee_name)
        )

    candidate_workflow_names: set[str] = set()
    if selected_entry_workflow_name is not None:
        selected_workflow_name = workflow_name_by_local_name.get(
            selected_entry_workflow_name,
            selected_entry_workflow_name,
        )
        selected_local_name = selected_workflow_name.rsplit("::", 1)[-1]
        if not (
            selected_local_name in {"entry", "drain", "promoted-entry-resume-plan-gate-wrapper"}
        ):
            return {}
        candidate_workflow_names.add(selected_workflow_name)
    else:
        for exported_name in module.exports:
            if not isinstance(exported_name, str):
                continue
            candidate_workflow_names.add(
                workflow_name_by_local_name.get(exported_name, exported_name)
            )

    allowed: dict[str, frozenset[str]] = {}
    for workflow_name in candidate_workflow_names:
        selected_callees = _entry_bootstrap_callees(
            omitted_callees_by_workflow.get(workflow_name)
        )
        if selected_callees:
            allowed[workflow_name] = selected_callees
    return allowed


def _shared_proof_hidden_context_workflow_names(
    *,
    module: WorkflowLispModule,
    selected_entry_workflow_name: str | None,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> set[str]:
    """Return exported entry wrappers eligible for the shared item-ctx proof lane."""

    exported_names = {name for name in module.exports if isinstance(name, str)}
    proof_worker_names = _shared_proof_hidden_context_seed_workflow_names(
        module=module,
        selected_entry_workflow_name=selected_entry_workflow_name,
        workflow_defs=workflow_defs,
        signatures_by_name=signatures_by_name,
    )
    if not proof_worker_names:
        return set()
    proof_callers = _transitive_local_callers(
        workflow_defs=workflow_defs,
        target_names=proof_worker_names,
    )
    allowed: set[str] = set()
    for workflow_def in workflow_defs:
        local_name = workflow_def.name.rsplit("::", 1)[-1]
        if workflow_def.name not in exported_names and local_name not in exported_names:
            continue
        if workflow_def.name not in proof_callers:
            continue
        signature = signatures_by_name.get(workflow_def.name)
        if signature is None:
            continue
        if any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in signature.params):
            continue
        if any(private_exec_context_kind(type_ref) is not None for _, type_ref in signature.params):
            continue
        allowed.add(workflow_def.name)
    return allowed


def _shared_proof_hidden_context_seed_workflow_names(
    *,
    module: WorkflowLispModule,
    selected_entry_workflow_name: str | None,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> set[str]:
    """Return worker lanes that legitimately seed promoted hidden-context routing."""

    workflow_defs_by_name = {workflow_def.name: workflow_def for workflow_def in workflow_defs}
    item_ctx_workers = {
        workflow_name
        for workflow_name in _shared_proof_item_ctx_worker_workflow_names(
            workflow_defs=workflow_defs,
            signatures_by_name=signatures_by_name,
        )
        if _workflow_omits_private_exec_context_binding(
            workflow_defs_by_name[workflow_name],
            signatures_by_name=signatures_by_name,
        )
    }
    return item_ctx_workers


def _shared_proof_item_ctx_worker_workflow_names(
    *,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> set[str]:
    """Return worker lanes that qualify for the shared `ItemCtx + payload` proof."""

    allowed: set[str] = set()
    for workflow_def in workflow_defs:
        signature = signatures_by_name.get(workflow_def.name)
        if signature is None:
            continue
        if any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in signature.params):
            continue
        if derived_private_child_context_eligibility(
            signature,
            param_name="phase-ctx",
        ).allowed:
            allowed.add(workflow_def.name)
    return allowed


def _transitive_local_callers(
    *,
    workflow_defs: tuple[WorkflowDef, ...],
    target_names: set[str],
) -> set[str]:
    """Return local workflows that transitively call any target workflow."""

    if not target_names:
        return set()

    workflow_names = {workflow_def.name for workflow_def in workflow_defs}
    workflow_name_by_local_name = {
        workflow_def.name.rsplit("::", 1)[-1]: workflow_def.name for workflow_def in workflow_defs
    }
    reverse_call_graph: dict[str, set[str]] = {name: set() for name in workflow_names}
    for workflow_def in workflow_defs:
        for callee_name, _bound_names in _iter_workflow_call_sites(workflow_def):
            callee_name = workflow_name_by_local_name.get(callee_name, callee_name)
            if callee_name not in workflow_names:
                continue
            reverse_call_graph.setdefault(callee_name, set()).add(workflow_def.name)

    callers: set[str] = set()
    pending = list(target_names)
    while pending:
        callee_name = pending.pop()
        for caller_name in reverse_call_graph.get(callee_name, ()):
            if caller_name in callers:
                continue
            callers.add(caller_name)
            pending.append(caller_name)
    return callers


def _is_private_exec_context_type(type_ref) -> bool:
    return (
        private_exec_context_kind(type_ref) is not None
        or classify_structural_private_exec_context(type_ref) is not None
    )


def _workflow_omits_private_compatibility_bridge(
    workflow_def: WorkflowDef,
    *,
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> bool:
    """Return whether one workflow omits a known private bridge binding on a call."""

    workflow_name_by_local_name = {
        name.rsplit("::", 1)[-1]: name for name in signatures_by_name if "::" in name
    }
    for callee_name, bound_names in _iter_workflow_call_sites(workflow_def):
        callee_name = workflow_name_by_local_name.get(callee_name, callee_name)
        callee_signature = signatures_by_name.get(callee_name)
        if callee_signature is None:
            continue
        for binding_name in callee_signature.private_compatibility_bridge_types:
            if binding_name not in bound_names:
                return True
    return False


def _workflow_omits_private_exec_context_binding(
    workflow_def: WorkflowDef,
    *,
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> bool:
    """Return whether one workflow omits a private exec-context binding on a call."""

    workflow_name_by_local_name = {
        name.rsplit("::", 1)[-1]: name for name in signatures_by_name if "::" in name
    }
    for callee_name, bound_names in _iter_workflow_call_sites(workflow_def):
        callee_name = _resolve_call_site_workflow_name(
            callee_name,
            workflow_name_by_local_name=workflow_name_by_local_name,
        )
        callee_signature = signatures_by_name.get(callee_name)
        if callee_signature is None:
            continue
        for binding_name, binding_type in callee_signature.params:
            if binding_name in bound_names or binding_name in callee_signature.param_defaults:
                continue
            if _is_private_exec_context_type(binding_type):
                return True
    return False


def _omitted_private_exec_context_callees_by_workflow(
    *,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> Mapping[str, frozenset[str]]:
    """Return omitted private-context call targets for each workflow."""

    workflow_name_by_local_name = {
        name.rsplit("::", 1)[-1]: name for name in signatures_by_name if "::" in name
    }
    omitted: dict[str, frozenset[str]] = {}
    for workflow_def in workflow_defs:
        omitted_callees: set[str] = set()
        for callee_name, bound_names in _iter_workflow_call_sites(workflow_def):
            callee_name = _resolve_call_site_workflow_name(
                callee_name,
                workflow_name_by_local_name=workflow_name_by_local_name,
            )
            callee_signature = signatures_by_name.get(callee_name)
            if callee_signature is None:
                continue
            for binding_name, binding_type in callee_signature.params:
                if binding_name in bound_names or binding_name in callee_signature.param_defaults:
                    continue
                if _is_private_exec_context_type(binding_type):
                    omitted_callees.add(callee_signature.name)
                    break
        if omitted_callees:
            omitted[workflow_def.name] = frozenset(omitted_callees)
    return omitted


def _resolve_call_site_workflow_name(
    callee_name: str,
    *,
    workflow_name_by_local_name: Mapping[str, str],
) -> str:
    resolved = workflow_name_by_local_name.get(callee_name)
    if resolved is not None:
        return resolved
    if "." in callee_name:
        resolved = workflow_name_by_local_name.get(callee_name.rsplit(".", 1)[-1])
        if resolved is not None:
            return resolved
    return callee_name


def _omitted_private_compatibility_bridge_callees_by_workflow(
    *,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> Mapping[str, frozenset[str]]:
    """Return omitted bridge-call targets for each workflow."""

    workflow_name_by_local_name = {
        name.rsplit("::", 1)[-1]: name for name in signatures_by_name if "::" in name
    }
    omitted: dict[str, frozenset[str]] = {}
    for workflow_def in workflow_defs:
        omitted_callees: set[str] = set()
        for callee_name, bound_names in _iter_workflow_call_sites(workflow_def):
            callee_name = workflow_name_by_local_name.get(callee_name, callee_name)
            callee_signature = signatures_by_name.get(callee_name)
            if callee_signature is None:
                continue
            for binding_name in callee_signature.private_compatibility_bridge_types:
                if binding_name not in bound_names:
                    omitted_callees.add(callee_signature.name)
                    break
        if omitted_callees:
            omitted[workflow_def.name] = frozenset(omitted_callees)
    return omitted


def _workflow_omits_private_compatibility_bridge_via_workflow_ref(
    workflow_def: WorkflowDef,
    *,
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> bool:
    """Return whether a workflow-ref call site omits a compatibility bridge."""

    from .phase_family_boundary import COMPATIBILITY_BRIDGE_PARAM_NAMES

    signature = signatures_by_name.get(workflow_def.name)
    if signature is None:
        return False
    workflow_ref_params = {
        name for name, type_ref in signature.params if isinstance(type_ref, WorkflowRefTypeRef)
    }
    if not workflow_ref_params:
        return False
    for callee_name, bound_names in _iter_workflow_call_sites(workflow_def):
        if callee_name not in workflow_ref_params:
            continue
        if any(binding_name not in bound_names for binding_name in COMPATIBILITY_BRIDGE_PARAM_NAMES):
            return True
    return False


def _merged_private_compatibility_bridge_types_by_workflow(
    *,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> Mapping[str, Mapping[str, TypeRef]]:
    """Propagate bridge types through workers that omit bridge bindings locally."""

    omitted_callees_by_workflow = _omitted_private_compatibility_bridge_callees_by_workflow(
        workflow_defs=workflow_defs,
        signatures_by_name=signatures_by_name,
    )
    merged: dict[str, Mapping[str, TypeRef]] = {}
    for workflow_def in workflow_defs:
        signature = signatures_by_name.get(workflow_def.name)
        if signature is None:
            continue
        combined = dict(signature.private_compatibility_bridge_types)
        for callee_name in omitted_callees_by_workflow.get(workflow_def.name, frozenset()):
            callee_signature = signatures_by_name.get(callee_name)
            if callee_signature is None:
                continue
            combined.update(callee_signature.private_compatibility_bridge_types)
        if combined != dict(signature.private_compatibility_bridge_types):
            merged[workflow_def.name] = combined
    return merged


def _iter_workflow_call_sites(
    workflow_def: WorkflowDef,
) -> tuple[tuple[str, frozenset[str]], ...]:
    """Return workflow call sites as `(callee_name, bound_names)` tuples."""

    body_expr = workflow_def.body
    if isinstance(body_expr, SyntaxNode):
        return tuple(_iter_syntax_workflow_call_sites(syntax_node_datum(body_expr)))
    return tuple(
        (node.callee_name, frozenset(binding_name for binding_name, _ in node.bindings))
        for node in walk_expr(body_expr)
        if isinstance(node, CallExpr)
    )


def _iter_syntax_workflow_call_sites(
    datum: SyntaxNode | SyntaxList | SyntaxIdentifier | SyntaxKeyword | SyntaxString | SyntaxInt | SyntaxFloat | SyntaxBool,
) -> tuple[tuple[str, frozenset[str]], ...]:
    """Return workflow call sites from raw syntax before expression elaboration."""

    if isinstance(datum, SyntaxNode):
        return _iter_syntax_workflow_call_sites(syntax_node_datum(datum))
    if not isinstance(datum, SyntaxList):
        return ()

    call_sites: list[tuple[str, frozenset[str]]] = []
    head_name = syntax_head_name(datum)
    if head_name == "call" and len(datum.items) >= 2:
        callee_name = syntax_resolved_name(datum.items[1])
        if callee_name is not None:
            bound_names = frozenset(
                item.value.lstrip(":")
                for item in datum.items[2:]
                if isinstance(item, SyntaxKeyword)
            )
            call_sites.append((callee_name, bound_names))
    for item in datum.items:
        call_sites.extend(_iter_syntax_workflow_call_sites(item))
    return tuple(call_sites)


def _shared_proof_compatibility_bridge_omission_callees(
    *,
    module: WorkflowLispModule,
    workflow_defs: tuple[WorkflowDef, ...],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> Mapping[str, frozenset[str]]:
    """Return the approved proof-route callees for bridge omission."""

    _ = module
    bridge_worker_names = {
        workflow_def.name
        for workflow_def in workflow_defs
        if (
            (signature := signatures_by_name.get(workflow_def.name)) is not None
            and not any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in signature.params)
            and len(eligible_private_context_source_param_names(signature)) == 1
        )
        if _workflow_omits_private_compatibility_bridge(
            workflow_def,
            signatures_by_name=signatures_by_name,
        )
    }
    if not bridge_worker_names:
        return {}
    bridge_route_names = set(bridge_worker_names)
    bridge_route_names.update(
        _transitive_local_callers(
            workflow_defs=workflow_defs,
            target_names=bridge_worker_names,
        )
    )
    omitted_callees_by_workflow = _omitted_private_compatibility_bridge_callees_by_workflow(
        workflow_defs=workflow_defs,
        signatures_by_name=signatures_by_name,
    )
    allowed: dict[str, frozenset[str]] = {}
    for workflow_name in bridge_route_names:
        if workflow_name not in signatures_by_name:
            continue
        if any(
            isinstance(type_ref, WorkflowRefTypeRef)
            for _, type_ref in signatures_by_name[workflow_name].params
        ):
            continue
        if workflow_name in bridge_worker_names:
            approved_callees = omitted_callees_by_workflow.get(workflow_name, frozenset())
        else:
            approved_callees = frozenset(bridge_route_names)
        if approved_callees:
            allowed[workflow_name] = approved_callees
    return allowed


def specialized_private_compatibility_bridge_callees(
    workflow_def: WorkflowDef,
    *,
    base_signature: WorkflowSignature,
    workflow_ref_bindings: Mapping[str, object],
    signatures_by_name: Mapping[str, WorkflowSignature],
) -> frozenset[str]:
    """Resolve exact bridge-omission callees after workflow-ref specialization."""

    allowed = set(base_signature.allowed_private_compatibility_bridge_callees)
    if not workflow_ref_bindings:
        return frozenset(allowed)
    for callee_name, bound_names in _iter_workflow_call_sites(workflow_def):
        resolved = workflow_ref_bindings.get(callee_name)
        if resolved is None:
            continue
        target_name = getattr(resolved, "workflow_name", None)
        if not isinstance(target_name, str):
            continue
        target_signature = signatures_by_name.get(target_name)
        if target_signature is None:
            continue
        if any(
            binding_name not in bound_names
            for binding_name in target_signature.private_compatibility_bridge_types
        ):
            allowed.add(target_name)
    return frozenset(allowed)


def _signature_from_imported_bundle(
    alias: str,
    bundle: "LoadedWorkflowBundle",
    *,
    type_env: FrontendTypeEnvironment,
) -> WorkflowSignature:
    """Reconstruct a frontend workflow signature from a validated bundle."""

    from .contracts import is_transportable_result_type

    input_contracts = workflow_input_contracts(bundle)
    public_input_contracts = workflow_public_input_contracts(bundle)
    boundary_projection = workflow_boundary_projection(bundle)
    grouped_inputs: dict[str, dict[str, Mapping[str, object]]] = {}
    param_order: list[str] = []
    for input_name, input_spec in public_input_contracts.items():
        if not isinstance(input_name, str) or not isinstance(input_spec, Mapping):
            continue
        param_name = input_name.split("__", 1)[0]
        if param_name not in grouped_inputs:
            grouped_inputs[param_name] = {}
            param_order.append(param_name)
        grouped_inputs[param_name][input_name] = dict(input_spec)
    for input_name in boundary_projection.private_compatibility_bridge_inputs:
        input_spec = input_contracts.get(input_name)
        if not isinstance(input_name, str) or not isinstance(input_spec, Mapping):
            continue
        param_name = input_name.split("__", 1)[0]
        if param_name not in grouped_inputs:
            grouped_inputs[param_name] = {}
            param_order.append(param_name)
        grouped_inputs[param_name][input_name] = dict(input_spec)
    for binding in boundary_projection.private_runtime_context_bindings:
        param_name = binding.source_param_name or binding.binding_id
        if not isinstance(param_name, str):
            continue
        binding_inputs = {
            input_name: dict(input_spec)
            for input_name in binding.generated_input_names
            if isinstance(input_name, str)
            and isinstance((input_spec := input_contracts.get(input_name)), Mapping)
        }
        if not binding_inputs:
            continue
        if param_name not in grouped_inputs:
            grouped_inputs[param_name] = {}
            param_order.append(param_name)
        grouped_inputs[param_name].update(binding_inputs)

    span = _bundle_source_span(bundle)
    form_path = ("workflow-lisp", alias)
    params_list: list[tuple[str, TypeRef]] = []
    param_defaults: dict[str, WorkflowParamDefault] = {}
    for param_name in param_order:
        param_type = _match_boundary_type_from_contracts(
            grouped_inputs[param_name],
            type_env=type_env,
            generated_name=param_name,
            allow_union=False,
            span=span,
            form_path=form_path,
        )
        params_list.append((param_name, param_type))
        imported_default = _workflow_param_default_from_imported_contracts(
            contracts=grouped_inputs[param_name],
            param_name=param_name,
            param_type=param_type,
            span=span,
            form_path=form_path,
        )
        if imported_default is not None:
            param_defaults[param_name] = imported_default
    params = tuple(params_list)
    return_type_ref = _match_boundary_type_from_contracts(
        {
            output_name: dict(output_spec)
            for output_name, output_spec in workflow_output_contracts(bundle).items()
            if isinstance(output_name, str) and isinstance(output_spec, Mapping)
        },
        type_env=type_env,
        generated_name="return",
        allow_union=True,
        span=span,
        form_path=form_path,
    )
    if not is_transportable_result_type(return_type_ref):
        raise LispFrontendCompileError(
            (
                required_lint_diagnostic(
                    "workflow_call_signature_erased",
                    message=f"imported workflow `{alias}` must resolve to a transportable return type",
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    hidden_context_requirements = _hidden_context_requirements_from_bundle(
        bundle,
        params=params,
    )
    return WorkflowSignature(
        name=alias,
        params=params,
        return_type_ref=return_type_ref,
        span=span,
        form_path=form_path,
        param_defaults=param_defaults,
        hidden_context_requirements=hidden_context_requirements,
        private_compatibility_bridge_types=_compatibility_bridge_types_from_bundle(
            bundle,
            type_env=type_env,
            span=span,
            form_path=form_path,
            existing_param_names=frozenset(name for name, _ in params),
        ),
        allow_private_compatibility_bridge_omission=False,
    )


def _hidden_context_requirements_from_bundle(
    bundle: "LoadedWorkflowBundle",
    *,
    params: tuple[tuple[str, TypeRef], ...],
) -> Mapping[str, PromotedEntryHiddenContextRequirement]:
    """Recover callee-owned hidden-context requirements from imported boundary metadata."""

    params_by_name = dict(params)
    requirements: dict[str, PromotedEntryHiddenContextRequirement] = {}
    for binding in workflow_boundary_projection(bundle).private_runtime_context_bindings:
        param_name = None
        if binding.source_param_name in params_by_name:
            param_name = binding.source_param_name
        elif binding.binding_id in params_by_name:
            param_name = binding.binding_id
        if param_name is None:
            continue
        binding_kind = "runtime_owned_entry_context"
        allows_entry_bootstrap = False
        if (
            binding.context_family == PHASE_CONTEXT_NAME
            and binding.derived_phase_identity is not None
        ):
            binding_kind = "derived_private_child_context"
            allows_entry_bootstrap = True
        elif binding.bridge_class == "derived_private_child_context":
            binding_kind = "derived_private_child_context"
        requirements[param_name] = PromotedEntryHiddenContextRequirement(
            param_name=param_name,
            context_kind=binding.context_family,
            phase_name=binding.derived_phase_identity,
            binding_kind=binding_kind,
            allows_entry_bootstrap=allows_entry_bootstrap,
        )
    return requirements


def _compatibility_bridge_types_from_bundle(
    bundle: "LoadedWorkflowBundle",
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
    existing_param_names: frozenset[str],
) -> Mapping[str, TypeRef]:
    from .phase_family_boundary import is_compatibility_bridge_param

    preferred_type_candidates_by_input = {
        "run_state_path": ("RunStatePath", "StateFileExisting", "StateExisting", "StateFile"),
        "progress_ledger_path": ("ProgressLedger",),
        "selection_bundle_path": ("SelectionBundlePath",),
    }
    input_contracts = workflow_input_contracts(bundle)
    boundary_projection = workflow_boundary_projection(bundle)
    compatibility_types: dict[str, TypeRef] = {}
    for input_name in boundary_projection.private_compatibility_bridge_inputs:
        if input_name in existing_param_names:
            continue
        input_spec = input_contracts.get(input_name)
        if not isinstance(input_spec, Mapping):
            continue
        preferred_type = None
        for candidate_name in preferred_type_candidates_by_input.get(input_name, ()):
            try:
                candidate_type = type_env.resolve_type(
                    candidate_name,
                    span=span,
                    form_path=form_path,
                )
            except LispFrontendCompileError:
                continue
            if is_compatibility_bridge_param(input_name, candidate_type):
                preferred_type = candidate_type
                break
        compatibility_types[input_name] = preferred_type or _match_boundary_type_from_contracts(
            {input_name: dict(input_spec)},
            type_env=type_env,
            generated_name=input_name,
            allow_union=False,
            span=span,
            form_path=form_path,
        )
    return compatibility_types


def _merge_signature_compatibility_bridge_types(
    signature: WorkflowSignature,
    *,
    bundle: "LoadedWorkflowBundle",
    type_env: FrontendTypeEnvironment,
) -> WorkflowSignature:
    compatibility_types = _compatibility_bridge_types_from_bundle(
        bundle,
        type_env=type_env,
        span=signature.span,
        form_path=signature.form_path,
        existing_param_names=frozenset(name for name, _ in signature.params).union(
            signature.private_compatibility_bridge_types
        ),
    )
    if not compatibility_types:
        return signature
    merged_compatibility_types = dict(signature.private_compatibility_bridge_types)
    merged_compatibility_types.update(compatibility_types)
    return WorkflowSignature(
        name=signature.name,
        params=signature.params,
        return_type_ref=signature.return_type_ref,
        span=signature.span,
        form_path=signature.form_path,
        param_defaults=signature.param_defaults,
        hidden_context_requirements=signature.hidden_context_requirements,
        hidden_context_ambiguities=signature.hidden_context_ambiguities,
        private_compatibility_bridge_types=merged_compatibility_types,
        allow_hidden_context_binding=signature.allow_hidden_context_binding,
        allow_private_compatibility_bridge_omission=signature.allow_private_compatibility_bridge_omission,
        allowed_hidden_context_callees=signature.allowed_hidden_context_callees,
        derived_hidden_context_callees=signature.derived_hidden_context_callees,
        entry_hidden_context_callees=signature.entry_hidden_context_callees,
        allowed_private_compatibility_bridge_callees=(
            signature.allowed_private_compatibility_bridge_callees
        ),
    )


def _workflow_param_default_from_imported_contracts(
    *,
    contracts: Mapping[str, Mapping[str, object]],
    param_name: str,
    param_type: TypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> WorkflowParamDefault | None:
    if len(contracts) != 1:
        return None
    field_spec = next(iter(contracts.values()))
    if not isinstance(field_spec, Mapping) or "default" not in field_spec:
        return None
    normalized_value = field_spec["default"]
    return WorkflowParamDefault(
        syntax=_synthetic_workflow_param_default_syntax(
            normalized_value=normalized_value,
            param_type=param_type,
            span=span,
            form_path=form_path,
        ),
        normalized_value=normalized_value,
    )


def _synthetic_workflow_param_default_syntax(
    *,
    normalized_value: object,
    param_type: TypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> SyntaxNode:
    module_path = span.start.path
    if isinstance(normalized_value, bool):
        datum = SyntaxBool(
            value=normalized_value,
            span=span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=(),
        )
    elif isinstance(normalized_value, int):
        datum = SyntaxInt(
            value=normalized_value,
            span=span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=(),
        )
    elif isinstance(normalized_value, float):
        datum = SyntaxFloat(
            value=normalized_value,
            span=span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=(),
        )
    elif isinstance(param_type, PrimitiveTypeRef) and param_type.allowed_values and isinstance(normalized_value, str):
        datum = SyntaxIdentifier(
            display_name=normalized_value,
            resolved_name=normalized_value,
            span=span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=(),
        )
    else:
        datum = SyntaxString(
            value=str(normalized_value),
            span=span,
            module_path=module_path,
            form_path=form_path,
            expansion_stack=(),
        )
    return SyntaxNode(
        datum=datum,
        span=span,
        module_path=module_path,
        form_path=form_path,
    )


def _target_dsl_supports_root_workflow_returns(target_dsl_version: str) -> bool:
    """Return whether a module's target DSL accepts root-valued public returns."""

    try:
        parsed = tuple(int(part) for part in str(target_dsl_version).split("."))
    except ValueError:
        return False
    return parsed >= (2, 15)


def _match_boundary_type_from_contracts(
    contracts: Mapping[str, Mapping[str, object]],
    *,
    type_env: FrontendTypeEnvironment,
    generated_name: str,
    allow_union: bool,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    """Find the authored type whose flattened contracts match a bundle boundary."""

    normalized_contracts = {
        name: _normalize_boundary_contract_definition(definition)
        for name, definition in contracts.items()
        if isinstance(name, str) and isinstance(definition, Mapping)
    }
    if generated_name == "return" and set(normalized_contracts) == {"__result__"}:
        return _root_boundary_type_from_contract(
            normalized_contracts["__result__"],
            type_env=type_env,
            span=span,
            form_path=form_path,
        )
    candidates: list[TypeRef] = []
    for candidate in type_env._type_refs.values():  # noqa: SLF001 - internal compiler matching
        if isinstance(candidate, UnionTypeRef) and not allow_union:
            continue
        if not isinstance(candidate, (PrimitiveTypeRef, PathTypeRef, RecordTypeRef, UnionTypeRef)):
            continue
        analysis = analyze_workflow_boundary_type(
            candidate,
            source_path=(generated_name,),
            allow_union=allow_union,
        )
        if not analysis.lowerable:
            continue
        if _flattened_boundary_contracts(candidate, generated_name=generated_name, span=span, form_path=form_path) == normalized_contracts:
            if any(type_refs_compatible(existing, candidate) for existing in candidates):
                continue
            candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        candidate_names = ", ".join(sorted(candidate.name for candidate in candidates))
        raise LispFrontendCompileError(
            (
                required_lint_diagnostic(
                    "workflow_call_signature_erased",
                    message=(
                        f"imported workflow boundary for `{generated_name}` is ambiguous across authored types: "
                        f"{candidate_names}"
                    ),
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    raise LispFrontendCompileError(
        (
            required_lint_diagnostic(
                "workflow_call_signature_erased",
                message=f"imported workflow boundary for `{generated_name}` does not match any authored type in scope",
                span=span,
                form_path=form_path,
            ),
        )
    )


def _flattened_boundary_contracts(
    type_ref: TypeRef,
    *,
    generated_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> Mapping[str, Mapping[str, object]]:
    """Flatten a frontend boundary type into shared workflow contract fields."""

    from .contracts import (
        _relax_variant_only_relpath_outputs,
        derive_workflow_boundary_fields,
    )

    fields = derive_workflow_boundary_fields(
        type_ref,
        generated_name=generated_name,
        source_path=(generated_name,),
        span=span,
        form_path=form_path,
    )
    if generated_name == "return" and isinstance(type_ref, UnionTypeRef):
        fields = _relax_variant_only_relpath_outputs(
            type_ref,
            fields,
            span=span,
            form_path=form_path,
        )

    return {
        field.generated_name: _normalize_boundary_contract_definition(field.contract_definition)
        for field in fields
    }


def _root_boundary_type_from_contract(
    definition: Mapping[str, object],
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    """Reconstruct an imported root `__result__` return type from its contract.

    Root boundary contracts fully describe scalar and collection structure, so
    they are rebuilt structurally; enum and path leaves resolve to the caller's
    authored types by matching their declared constraints, mirroring the
    record/union candidate matching in `_match_boundary_type_from_contracts`.
    """

    reconstructed = _reconstruct_root_contract_type(
        definition,
        type_env=type_env,
        span=span,
        form_path=form_path,
    )
    from .contracts import root_workflow_boundary_field

    round_trip = _normalize_boundary_contract_definition(
        root_workflow_boundary_field(
            reconstructed,
            span=span,
            form_path=form_path,
        ).contract_definition
    )
    if round_trip != _normalize_boundary_contract_definition(definition):
        raise LispFrontendCompileError(
            (
                required_lint_diagnostic(
                    "workflow_call_signature_erased",
                    message=(
                        "imported workflow root `__result__` boundary does not match the "
                        f"reconstructed `{reconstructed.name}` contract"
                    ),
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    return reconstructed


def _reconstruct_root_contract_type(
    definition: Mapping[str, object],
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    value_type = definition.get("type")
    if value_type == "bool":
        return PrimitiveTypeRef(name="Bool")
    if value_type == "integer":
        return PrimitiveTypeRef(name="Int")
    if value_type == "float":
        return PrimitiveTypeRef(name="Float")
    if value_type == "string":
        return PrimitiveTypeRef(name="String")
    if value_type == "enum":
        allowed = tuple(str(value) for value in definition.get("allowed", ()))
        return _match_root_leaf_candidate(
            type_env,
            matches=lambda candidate: isinstance(candidate, PrimitiveTypeRef)
            and candidate.allowed_values == allowed,
            leaf_label=f"enum values {list(allowed)}",
            span=span,
            form_path=form_path,
        )
    if value_type == "relpath":
        under = definition.get("under")
        must_exist = definition.get("must_exist_target")
        return _match_root_leaf_candidate(
            type_env,
            matches=lambda candidate: isinstance(candidate, PathTypeRef)
            and candidate.definition.under == under
            and candidate.definition.must_exist == must_exist,
            leaf_label=f"relpath under `{under}`",
            span=span,
            form_path=form_path,
        )
    if value_type == "optional":
        item = _reconstruct_root_contract_type(
            _mapping_or_erased(definition.get("item"), span=span, form_path=form_path),
            type_env=type_env,
            span=span,
            form_path=form_path,
        )
        return OptionalTypeRef(name=f"Optional[{item.name}]", item_type_ref=item)
    if value_type == "list":
        item = _reconstruct_root_contract_type(
            _mapping_or_erased(definition.get("items"), span=span, form_path=form_path),
            type_env=type_env,
            span=span,
            form_path=form_path,
        )
        return ListTypeRef(name=f"List[{item.name}]", item_type_ref=item)
    if value_type == "map":
        value = _reconstruct_root_contract_type(
            _mapping_or_erased(definition.get("values"), span=span, form_path=form_path),
            type_env=type_env,
            span=span,
            form_path=form_path,
        )
        return MapTypeRef(
            name=f"Map[String, {value.name}]",
            key_type_ref=PrimitiveTypeRef(name="String"),
            value_type_ref=value,
        )
    raise LispFrontendCompileError(
        (
            required_lint_diagnostic(
                "workflow_call_signature_erased",
                message=(
                    "imported workflow root `__result__` boundary uses unsupported "
                    f"contract type `{value_type}`"
                ),
                span=span,
                form_path=form_path,
            ),
        )
    )


def _mapping_or_erased(
    value: object,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    raise LispFrontendCompileError(
        (
            required_lint_diagnostic(
                "workflow_call_signature_erased",
                message="imported workflow root `__result__` boundary is missing an element schema",
                span=span,
                form_path=form_path,
            ),
        )
    )


def _match_root_leaf_candidate(
    type_env: FrontendTypeEnvironment,
    *,
    matches,
    leaf_label: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    candidates: list[TypeRef] = []
    for candidate in type_env._type_refs.values():  # noqa: SLF001 - internal compiler matching
        if not matches(candidate):
            continue
        if any(type_refs_compatible(existing, candidate) for existing in candidates):
            continue
        candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        candidate_names = ", ".join(sorted(candidate.name for candidate in candidates))
        raise LispFrontendCompileError(
            (
                required_lint_diagnostic(
                    "workflow_call_signature_erased",
                    message=(
                        "imported workflow root `__result__` boundary is ambiguous across "
                        f"authored types: {candidate_names}"
                    ),
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    raise LispFrontendCompileError(
        (
            required_lint_diagnostic(
                "workflow_call_signature_erased",
                message=(
                    "imported workflow root `__result__` boundary does not match any "
                    f"authored type in scope ({leaf_label})"
                ),
                span=span,
                form_path=form_path,
            ),
        )
    )


def _workflow_boundary_fields_for_param(
    param: WorkflowParam,
    param_type: TypeRef,
) -> tuple[object, ...]:
    from .contracts import derive_workflow_boundary_fields

    return derive_workflow_boundary_fields(
        param_type,
        generated_name=param.name,
        source_path=(param.name,),
        span=param.span,
        form_path=param.form_path,
    )


def _resolve_workflow_param_default(
    *,
    param: WorkflowParam,
    param_type: TypeRef,
) -> WorkflowParamDefault:
    default_value = param.default_value
    if default_value is None:
        raise ValueError("workflow param default resolution requires an authored default")

    flattened_fields = _workflow_boundary_fields_for_param(param, param_type)
    if len(flattened_fields) != 1:
        _raise_workflow_param_default_error(
            code="workflow_param_default_unsupported",
            message=(
                f"default for workflow param `{param.name}` is supported only for "
                "boundary types that flatten to exactly one workflow input contract"
            ),
            param=param,
        )

    normalized_value = _normalize_workflow_param_default_literal(
        param=param,
        param_type=param_type,
        default_value=default_value,
    )
    return WorkflowParamDefault(
        syntax=default_value.syntax,
        normalized_value=normalized_value,
    )


def _normalize_workflow_param_default_literal(
    *,
    param: WorkflowParam,
    param_type: TypeRef,
    default_value: WorkflowParamDefault,
) -> object:
    datum = default_value.syntax.datum
    if isinstance(param_type, PathTypeRef):
        if isinstance(datum, SyntaxString):
            return datum.value
        _raise_workflow_param_default_type_error(param=param)
    if isinstance(param_type, PrimitiveTypeRef):
        if param_type.allowed_values:
            if isinstance(datum, SyntaxIdentifier) and datum.resolved_name in param_type.allowed_values:
                return datum.resolved_name
            _raise_workflow_param_default_type_error(param=param)
        if param_type.name == "String":
            if isinstance(datum, SyntaxString):
                return datum.value
            _raise_workflow_param_default_type_error(param=param)
        if param_type.name == "Int":
            if isinstance(datum, SyntaxInt):
                return datum.value
            _raise_workflow_param_default_type_error(param=param)
        if param_type.name == "Float":
            if isinstance(datum, SyntaxFloat):
                return datum.value
            _raise_workflow_param_default_type_error(param=param)
        if param_type.name == "Bool":
            if isinstance(datum, SyntaxBool):
                return datum.value
            _raise_workflow_param_default_type_error(param=param)
    _raise_workflow_param_default_error(
        code="workflow_param_default_unsupported",
        message=(
            f"default for workflow param `{param.name}` is not supported for boundary type `{param.type_name}`"
        ),
        param=param,
    )


def _raise_workflow_param_default_type_error(*, param: WorkflowParam) -> None:
    _raise_workflow_param_default_error(
        code="workflow_param_default_type_invalid",
        message=f"default for workflow param `{param.name}` must match boundary type `{param.type_name}`",
        param=param,
    )


def _raise_workflow_param_default_error(
    *,
    code: str,
    message: str,
    param: WorkflowParam,
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
            ),
        )
    )


def _normalize_boundary_contract_definition(definition: Mapping[str, object]) -> Mapping[str, object]:
    """Normalize a contract shape for structural boundary comparison."""

    return {
        str(key): value
        for key, value in dict(definition).items()
        if key not in {"default", "from", "projection", "__allow_unresolved_source"}
    }


def _bundle_source_span(bundle: "LoadedWorkflowBundle") -> SourceSpan:
    """Create a diagnostic span for an imported workflow bundle."""

    workflow_path = bundle.provenance.workflow_path
    return SourceSpan(
        start=SourcePosition(path=str(workflow_path), line=1, column=1, offset=0),
        end=SourcePosition(path=str(workflow_path), line=1, column=1, offset=0),
    )


def typecheck_workflow_definitions(
    workflow_defs: tuple[WorkflowDef, ...],
    *,
    module: WorkflowLispModule | None = None,
    type_env: FrontendTypeEnvironment,
    workflow_catalog: WorkflowCatalog,
    procedure_catalog: ProcedureCatalog | None = None,
    function_catalog: "FunctionCatalog | None" = None,
    extern_environment: ExternEnvironment | None = None,
    command_boundary_environment: CommandBoundaryEnvironment | None = None,
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    proc_ref_resolution_context: ProcRefResolutionContext | None = None,
    reusable_state_producer_context: Mapping[str, object] | None = None,
    selected_entry_workflow_name: str | None = None,
) -> tuple[TypedWorkflowDef, ...]:
    """Typecheck workflow parameters and bodies against the registered signatures."""

    externs = extern_environment or ExternEnvironment(bindings_by_name={})
    command_boundaries = command_boundary_environment
    procedure_names = frozenset() if procedure_catalog is None else frozenset(procedure_catalog.signatures_by_name)
    function_names = (
        frozenset()
        if function_catalog is None
        else frozenset(function_catalog.signatures_by_name)
    )
    elaborated_bodies: dict[str, object] = {}
    for workflow_def in workflow_defs:
        signature = workflow_catalog.signatures_by_name[workflow_def.name]
        if workflow_def.publication_policy is not None:
            validate_entry_publication_policy(
                workflow_def.publication_policy,
                workflow_name=workflow_def.name,
                return_union_variants=(
                    tuple(variant.name for variant in signature.return_type_ref.definition.variants)
                    if isinstance(signature.return_type_ref, UnionTypeRef)
                    else None
                ),
                selected_entry_workflow_name=selected_entry_workflow_name,
                exported_workflow_names=() if module is None else module.exports,
            )
        value_env: dict[str, TypeRef] = {
            param_name: type_ref for param_name, type_ref in signature.params
        }
        for extern_name, binding in externs.bindings_by_name.items():
            if isinstance(binding, ProviderExtern):
                value_env[extern_name] = PrimitiveTypeRef(name="Provider")
            else:
                value_env[extern_name] = PrimitiveTypeRef(name="Prompt")

        if isinstance(workflow_def.body, SyntaxNode):
            body_expr = elaborate_expression(
                workflow_def.body,
                bound_names=frozenset(value_env),
                procedure_names=procedure_names,
                function_names=function_names,
                function_name_resolver=function_name_resolver,
                procedure_name_resolver=procedure_name_resolver,
                workflow_name_resolver=workflow_name_resolver,
            )
        else:
            body_expr = workflow_def.body
        elaborated_bodies[workflow_def.name] = body_expr
        hidden_context_requirements, hidden_context_ambiguities = (
            derive_promoted_entry_hidden_context_metadata(signature, body_expr)
        )
        hidden_context_requirements = _phase_family_hidden_context_requirements(
            signature,
            hidden_context_requirements,
            workflow_catalog=workflow_catalog,
        )
        workflow_catalog.signatures_by_name[workflow_def.name] = WorkflowSignature(
            name=signature.name,
            params=signature.params,
            return_type_ref=signature.return_type_ref,
            span=signature.span,
            form_path=signature.form_path,
            param_defaults=signature.param_defaults,
            hidden_context_requirements=hidden_context_requirements,
            hidden_context_ambiguities=hidden_context_ambiguities,
            private_compatibility_bridge_types=signature.private_compatibility_bridge_types,
            allow_hidden_context_binding=signature.allow_hidden_context_binding,
            allow_private_compatibility_bridge_omission=(
                signature.allow_private_compatibility_bridge_omission
            ),
            allowed_hidden_context_callees=signature.allowed_hidden_context_callees,
            derived_hidden_context_callees=signature.derived_hidden_context_callees,
            entry_hidden_context_callees=signature.entry_hidden_context_callees,
            allowed_private_compatibility_bridge_callees=(
                signature.allowed_private_compatibility_bridge_callees
            ),
        )

    typed_workflows: list[TypedWorkflowDef] = []
    for workflow_def in workflow_defs:
        seen_names: set[str] = set()
        value_env: dict[str, TypeRef] = {}
        for param_name, type_ref in workflow_catalog.signatures_by_name[workflow_def.name].params:
            if param_name in seen_names:
                duplicate = next(param for param in workflow_def.params if param.name == param_name)
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="workflow_param_duplicate",
                            message=f"duplicate workflow parameter `{param_name}`",
                            span=duplicate.span,
                            form_path=duplicate.form_path,
                            expansion_stack=duplicate.expansion_stack,
                        ),
                    )
                )
            seen_names.add(param_name)
            value_env[param_name] = type_ref
        for extern_name, binding in externs.bindings_by_name.items():
            if isinstance(binding, ProviderExtern):
                value_env[extern_name] = PrimitiveTypeRef(name="Provider")
            else:
                value_env[extern_name] = PrimitiveTypeRef(name="Prompt")

        signature = workflow_catalog.signatures_by_name[workflow_def.name]
        body_expr = elaborated_bodies[workflow_def.name]
        set_active_workflow_signature(signature)
        set_active_reusable_state_producer_context(reusable_state_producer_context)
        try:
            typed_body = typecheck_expression(
                body_expr,
                type_env=type_env,
                value_env=value_env,
                workflow_catalog=workflow_catalog,
                procedure_catalog=procedure_catalog,
                function_catalog=function_catalog,
                extern_environment=externs,
                command_boundary_environment=command_boundaries,
                procedure_effects_by_name=procedure_effects_by_name,
                workflow_effects_by_name=workflow_effects_by_name,
                proc_ref_resolution_context=proc_ref_resolution_context,
            )
        finally:
            clear_active_reusable_state_producer_context()
            clear_active_workflow_signature()
        if not type_refs_compatible(signature.return_type_ref, typed_body.type_ref):
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="return_type_mismatch",
                        message=(
                            f"workflow `{workflow_def.name}` declared return type "
                            f"`{workflow_def.return_type_name}` but body returned a different type"
                        ),
                        span=workflow_def.body.span,
                        form_path=workflow_def.body.form_path,
                        expansion_stack=workflow_def.body.expansion_stack,
                    ),
                )
            )
        typed_workflows.append(
            TypedWorkflowDef(
                definition=workflow_def,
                signature=signature,
                typed_body=typed_body,
                effect_summary=typed_body.effect_summary,
            )
        )
    return tuple(typed_workflows)


def _boundary_diagnostic(
    *,
    workflow_name: str,
    analysis: WorkflowBoundaryAnalysis,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack = (),
    allow_collection_boundaries: bool = False,
) -> LispFrontendDiagnostic | None:
    """Translate workflow-boundary analysis into a frontend diagnostic."""

    if (
        allow_collection_boundaries
        and analysis.lowerable
        and analysis.contains_collection
        and not analysis.contains_json
        and not analysis.contains_provider_or_prompt
        and not analysis.contains_workflow_ref
        and not analysis.contains_proc_ref
        and not analysis.contains_union
    ):
        return None

    if analysis.lowerable and not (
        analysis.contains_json
        or analysis.contains_provider_or_prompt
        or analysis.contains_workflow_ref
        or analysis.contains_proc_ref
        or analysis.contains_collection
        or analysis.contains_union
    ):
        return None

    path_label = ".".join(analysis.offending_path) if analysis.offending_path else workflow_name
    if analysis.contains_json:
        return LispFrontendDiagnostic(
            code="json_surface_unsupported",
            message=f"`Json` is not supported on workflow boundaries in Stage 3 (`{path_label}`)",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if analysis.contains_provider_or_prompt:
        return LispFrontendDiagnostic(
            code="workflow_boundary_type_invalid",
            message=(
                f"`{analysis.offending_type_name}` cannot cross a Stage 3 workflow boundary "
                f"(`{path_label}`)"
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if analysis.contains_workflow_ref:
        return LispFrontendDiagnostic(
            code="workflow_ref_runtime_transport_forbidden",
            message=(
                f"`{analysis.offending_type_name}` cannot cross a runtime workflow boundary "
                f"(`{path_label}`)"
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if analysis.contains_proc_ref:
        return LispFrontendDiagnostic(
            code="proc_ref_runtime_transport_forbidden",
            message=(
                f"`{analysis.offending_type_name}` cannot cross a runtime workflow boundary "
                f"(`{path_label}`)"
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if analysis.contains_collection:
        return LispFrontendDiagnostic(
            code="workflow_boundary_collection_unsupported",
            message=(
                f"workflow boundary `{path_label}` cannot transport collection type "
                f"`{analysis.offending_type_name}` in Stage 3"
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if analysis.contains_union:
        return LispFrontendDiagnostic(
            code="workflow_boundary_type_invalid",
            message=(
                f"workflow boundary `{path_label}` must lower to scalars, relpaths, or records; "
                "unions are not supported in Stage 3"
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    return LispFrontendDiagnostic(
        code="workflow_boundary_type_invalid",
        message=f"workflow boundary `{path_label}` is not lowerable in Stage 3",
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def _elaborate_workflow_definition(form: SyntaxNode) -> WorkflowDef:
    """Parse one `defworkflow` form into a workflow definition object."""

    datum = syntax_node_datum(form)
    if not isinstance(datum, SyntaxList) or len(datum.items) < 6:
        _raise_error(
            "`defworkflow` requires a name, params, return arrow, return type, and one body",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    name_node = syntax_identifier(datum.items[1])
    if name_node is None:
        _raise_error(
            "workflow name must be a symbol",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    params_node = datum.items[2]
    if not isinstance(params_node, SyntaxList):
        _raise_error(
            "workflow params must be a list",
            span=params_node.span,
            form_path=form.form_path,
            expansion_stack=params_node.expansion_stack,
        )
    arrow_node = syntax_identifier(datum.items[3])
    if arrow_node is None or arrow_node.resolved_name != "->":
        _raise_error(
            "workflow return separator must be `->`",
            span=datum.items[3].span,
            form_path=form.form_path,
            expansion_stack=datum.items[3].expansion_stack,
        )
    return_type_node = datum.items[4]
    return_type_identifier = syntax_identifier(return_type_node)
    if return_type_identifier is None:
        _raise_error(
            "workflow return type must be a symbol",
            span=return_type_node.span,
            form_path=form.form_path,
            expansion_stack=return_type_node.expansion_stack,
        )
    publication_policy = None
    if len(datum.items) not in {6, 7}:
        _raise_error(
            "`defworkflow` requires exactly one body expression",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    if len(datum.items) == 7:
        policy_datum = datum.items[5]
        publication_policy = parse_entry_publication_policy(
            SyntaxNode(
                datum=policy_datum,
                span=policy_datum.span,
                module_path=form.module_path,
                form_path=form.form_path,
            ),
            workflow_name=name_node.resolved_name,
        )

    params = tuple(_elaborate_param(param, form.form_path) for param in params_node.items)
    body_datum = datum.items[6] if len(datum.items) == 7 else datum.items[5]
    body = SyntaxNode(
        datum=body_datum,
        span=body_datum.span,
        module_path=form.module_path,
        form_path=form.form_path,
    )
    return WorkflowDef(
        name=name_node.resolved_name,
        params=params,
        return_type_name=return_type_identifier.resolved_name,
        body=body,
        span=form.span,
        form_path=form.form_path,
        expansion_stack=datum.expansion_stack,
        publication_policy=publication_policy,
    )


def _elaborate_param(raw_param: object, form_path: tuple[str, ...]) -> WorkflowParam:
    """Parse one `(name Type)` or `(name Type :default <literal>)` workflow parameter."""

    if not isinstance(raw_param, SyntaxList):
        span = raw_param.span if hasattr(raw_param, "span") else None
        if span is None:
            raise TypeError("workflow params must carry spans")
        _raise_error(
            "workflow params must be lists of `(name Type)` or `(name Type :default <literal>)`",
            span=span,
            form_path=form_path,
            expansion_stack=getattr(raw_param, "expansion_stack", ()),
        )
    if len(raw_param.items) not in {2, 4}:
        message = "workflow params must be lists of `(name Type)` or `(name Type :default <literal>)`"
        if len(raw_param.items) >= 3:
            keyword = raw_param.items[2]
            if isinstance(keyword, SyntaxKeyword):
                if keyword.value != ":default":
                    message = f"unknown workflow param keyword `{keyword.value}`"
                else:
                    message = "workflow param `:default` requires a value"
        _raise_error(
            message,
            span=raw_param.span,
            form_path=form_path,
            expansion_stack=raw_param.expansion_stack,
        )
    name_node = raw_param.items[0]
    type_node = raw_param.items[1]
    name_identifier = syntax_identifier(name_node)
    type_identifier = syntax_identifier(type_node)
    if name_identifier is None:
        _raise_error(
            "workflow param names must be symbols",
            span=name_node.span,
            form_path=form_path,
            expansion_stack=name_node.expansion_stack,
        )
    if type_identifier is None:
        _raise_error(
            "workflow param types must be symbols",
            span=type_node.span,
            form_path=form_path,
            expansion_stack=type_node.expansion_stack,
        )
    default_value = None
    if len(raw_param.items) == 4:
        keyword_node = raw_param.items[2]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "workflow params must be lists of `(name Type)` or `(name Type :default <literal>)`",
                span=raw_param.span,
                form_path=form_path,
                expansion_stack=raw_param.expansion_stack,
            )
        if keyword_node.value != ":default":
            _raise_error(
                f"unknown workflow param keyword `{keyword_node.value}`",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        default_syntax = SyntaxNode(
            datum=raw_param.items[3],
            span=raw_param.items[3].span,
            module_path=raw_param.module_path,
            form_path=raw_param.form_path,
        )
        default_value = WorkflowParamDefault(syntax=default_syntax)
    return WorkflowParam(
        name=name_identifier.resolved_name,
        type_name=type_identifier.resolved_name,
        span=raw_param.span,
        form_path=form_path,
        expansion_stack=raw_param.expansion_stack,
        default_value=default_value,
    )


def _raise_error(
    message: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack = (),
) -> None:
    """Raise one workflow-elaboration diagnostic."""

    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="frontend_parse_error",
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


def build_extern_environment(
    *,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, PromptExtern | str | Mapping[str, object]] | None = None,
) -> ExternEnvironment:
    """Validate build-supplied provider and prompt bindings."""

    diagnostics: list[LispFrontendDiagnostic] = []
    bindings: dict[str, ProviderExtern | PromptExtern] = {}

    for name, provider_id in (provider_externs or {}).items():
        if not isinstance(name, str) or not name.strip() or not isinstance(provider_id, str) or not provider_id.strip():
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="provider_result_provider_invalid",
                    message="provider extern bindings require non-empty authored names and provider ids",
                    span=_environment_span(),
                )
            )
            continue
        bindings[name] = ProviderExtern(name=name, provider_id=provider_id)

    for name, raw_binding in (prompt_externs or {}).items():
        try:
            bindings[name] = normalize_prompt_extern_binding(name, raw_binding)
        except ValueError as exc:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="provider_result_prompt_invalid",
                    message=f"prompt extern bindings {exc}",
                    span=_environment_span(),
                )
            )

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return ExternEnvironment(bindings_by_name=bindings)
