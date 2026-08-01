"""Explicit mutable state owned by one Workflow Lisp compile."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from .expressions import ExprNode
    from .functions import FunctionCatalog
    from .loop_state import LoopStateCarrierMetadata
    from .parametric_constraints import SharedUnionFieldCapability
    from .procedure_refs import ResolvedProcRefValue
    from .procedure_typecheck import PendingParametricProcedureSpecialization
    from .procedures import ProcedureSignature, TypedProcedureDef
    from .prompts import PromptCatalog
    from .typecheck_run_ref import RunRefSiteMetadata
    from .spans import SourceSpan
    from .typecheck_context import LoopTypecheckContext
    from .workflows import WorkflowSignature


NameResolver: TypeAlias = Callable[
    [str, "SourceSpan", tuple[str, ...]],
    str,
]
LoopCarrierExprKey: TypeAlias = tuple[str, int, int, tuple[str, ...]]
LoopCarrierFieldSignature: TypeAlias = tuple[tuple[str, str], ...]
RunRefExprKey: TypeAlias = str
RunRefTypeSignature: TypeAlias = str


@dataclass
class ElaborationSessionState:
    """Lexically scoped expression-elaboration inputs."""

    procedure_name_resolver: NameResolver | None = None
    function_name_resolver: NameResolver | None = None
    workflow_name_resolver: NameResolver | None = None
    function_names: frozenset[str] = frozenset()
    local_proc_names: frozenset[str] = frozenset()
    loop_body_depth: int = 0
    let_proc_depth: int = 0
    guidance_example: bool = False
    target_dsl_version: str | None = None
    prompt_catalog: PromptCatalog | None = None


@dataclass
class TypecheckSessionState:
    """Mutable typing and generated-carrier state for one compile."""

    function_catalog: FunctionCatalog | None = None
    proc_ref_value_env: Mapping[str, ResolvedProcRefValue] = field(
        default_factory=dict
    )
    value_expr_env: Mapping[str, ExprNode] = field(default_factory=dict)
    loop_context: list[LoopTypecheckContext] = field(default_factory=list)
    generated_local_procedures: dict[str, TypedProcedureDef] = field(
        default_factory=dict
    )
    let_proc_rewrite_results: dict[int, ExprNode] = field(default_factory=dict)
    workflow_signature: WorkflowSignature | None = None
    procedure_hidden_context_signature: ProcedureSignature | None = None
    reusable_state_producer_context: Mapping[str, object] | None = None
    shared_union_field_capabilities: tuple[
        SharedUnionFieldCapability, ...
    ] = ()
    loop_carrier_metadata_by_name: dict[
        str, LoopStateCarrierMetadata
    ] = field(default_factory=dict)
    loop_carrier_metadata_by_expr_key: dict[
        LoopCarrierExprKey,
        dict[LoopCarrierFieldSignature, LoopStateCarrierMetadata],
    ] = field(
        default_factory=dict
    )
    run_ref_metadata_by_name: dict[str, RunRefSiteMetadata] = field(
        default_factory=dict
    )
    run_ref_metadata_by_expr_key: dict[
        RunRefExprKey,
        dict[RunRefTypeSignature, RunRefSiteMetadata],
    ] = field(default_factory=dict)
    parametric_specialization_requests: dict[
        str, PendingParametricProcedureSpecialization
    ] = field(default_factory=dict)


@dataclass
class LoweringSessionState:
    """Mutable lowering evidence owned by one compile."""

    intrinsic_form_lowering_counts: dict[str, int] = field(
        default_factory=dict
    )


@dataclass
class CompilerSession:
    """All mutable state for exactly one public compile attempt."""

    elaboration: ElaborationSessionState = field(
        default_factory=ElaborationSessionState
    )
    typecheck: TypecheckSessionState = field(default_factory=TypecheckSessionState)
    lowering: LoweringSessionState = field(default_factory=LoweringSessionState)
