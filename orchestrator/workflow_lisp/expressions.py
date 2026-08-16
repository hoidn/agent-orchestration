"""Elaborate supported Workflow Lisp expression forms into typed AST nodes.

See `../../docs/design/workflow_lisp_frontend_mvp_specification.md` for the current
expression scope and `../../docs/design/workflow_lisp_frontend_specification.md` for
the full intended language surface.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
import math
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Callable

from orchestrator.workflow.run_ref.contracts import (
    RunRefSourceRefusal,
    SetupCommand,
    SetupPolicy,
)
from orchestrator.workflow.run_ref.source import (
    normalize_repository_locator,
    validate_commit_sha,
)
from orchestrator.workflow.pure_expr import PURE_EXPR_OPERATOR_CATALOG
from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    PhasedDeliveryDiagnostic,
)

from .compiler_session import CompilerSession, ElaborationSessionState
from .diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    build_authored_phased_delivery_diagnostic,
)
from .form_registry import (
    FormKind,
    get_form_spec,
    list_traversal_authored_heads,
)
from .phase_stdlib import (
    ProduceOneOfCandidateFieldSpec,
    ProduceOneOfCandidateSpec,
    ProduceOneOfProducerSpec,
)
from .procedures import ProcedureParam
from .prompts import (
    PromptApplicationExpr,
    PromptCatalog,
    elaborate_prompt_application,
)
from .resource_stdlib import FinalizeSelectedItemSpec, ResourceTransitionSpec
from .result_guidance import ReturnSpec, parse_return_spec
from .spans import SourceSpan
from .syntax import (
    ExpansionStack,
    LIST_TRAVERSAL_MIN_TARGET_DSL_VERSION,
    MAX_STATIC_LIVE_PROVIDER_PEERS,
    RUN_REF_MIN_TARGET_DSL_VERSION,
    TRIAL_MIN_TARGET_DSL_VERSION,
    SyntaxBool,
    SyntaxFloat,
    SyntaxIdentifier,
    SyntaxInt,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    syntax_head,
    syntax_identifier,
    syntax_node_datum,
    target_dsl_supports_list_traversal,
    target_dsl_supports_prompt_calculus,
    target_dsl_supports_phased_contract_delivery,
    target_dsl_supports_provider_peer_messaging,
    target_dsl_supports_run_ref,
    target_dsl_supports_trial,
)

if TYPE_CHECKING:
    from .type_env import TypeRef


@dataclass(frozen=True)
class NameExpr:
    """One lexical name reference."""

    name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LiteralExpr:
    """One primitive literal."""

    value: str | int | float | bool
    literal_kind: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class EnumMemberExpr:
    """One qualified enum-member literal reference."""

    enum_name: str
    member_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()

    @property
    def name(self) -> str:
        return f"{self.enum_name}.{self.member_name}"



@dataclass(frozen=True)
class UnionVariantTagExpr:
    """Compiler-owned literal for one contextual union-variant tag.

    Produced when equality typing resolves an otherwise-unbound identifier
    against a union discriminant (``(= attempt.variant COMPLETED)``). It is not
    source-nameable: the identifier is rewritten to this node only inside a
    discriminant comparison. ``union_name`` preserves the owning union identity
    and ``variant_names`` the full declared variant set so proof analysis can
    infer a remaining singleton after exclusion.
    """

    union_name: str
    variant_name: str
    variant_names: tuple[str, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()

@dataclass(frozen=True)
class FieldAccessExpr:
    """One dotted field-access chain rooted at a lexical name."""

    base: NameExpr
    fields: tuple[str, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class RecordExpr:
    """One record-construction form."""

    type_name: str
    fields: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PureOpExpr:
    """One closed pure operator application."""

    operator: str
    args: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ListExpr:
    """One target-2.18 ordered list constructor."""

    items: tuple["ExprNode", ...]
    element_type_ref: "TypeRef | None"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ListMapExpr:
    """One target-2.18 pure lexical list-mapping binder."""

    binder_name: str
    source_expr: "ExprNode"
    body_expr: "ExprNode"
    source_item_type_ref: "TypeRef | None"
    result_item_type_ref: "TypeRef | None"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ListMapEffectExpr:
    """One target-2.18 bounded effectful lexical list-mapping binder."""

    binder_name: str
    source_expr: "ExprNode"
    max_iterations: int
    body_expr: "ExprNode"
    source_item_type_ref: "TypeRef | None"
    result_item_type_ref: "TypeRef | None"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class CompilerListNonemptyHeadExpr:
    """One compiler-owned, statically nonempty list-head projection."""

    source_expr: "ExprNode"
    element_type_ref: "TypeRef"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PathJoinUnderExpr:
    """One target-2.18 pure rooted-path construction form."""

    path_type_name: str
    child_expr: "ExprNode"
    path_type_ref: "TypeRef | None"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class RecordUpdateExpr:
    """One record-update expression over an existing record value."""

    base_expr: "ExprNode"
    overrides: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LoopStateField:
    """One authored loop-state seed field."""

    name: str
    type_name: str
    value_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LoopStateSeedExpr:
    """One loop-state seed form with explicit typed fields."""

    fields: tuple[LoopStateField, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LoopStateUpdateExpr:
    """One loop-state update form based on an existing carrier."""

    base_expr: "ExprNode"
    overrides: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class UnionVariantExpr:
    """One union-variant constructor."""

    type_name: str
    variant_name: str
    fields: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LetStarExpr:
    """One sequential lexical binding form."""

    bindings: tuple[tuple[str, "ExprNode"], ...]
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class IfExpr:
    """One ternary conditional expression."""

    condition_expr: "ExprNode"
    then_expr: "ExprNode"
    else_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    # Private branch proof facts keyed by binding identity, carried to WCC for
    # runtime `requires_variant` guards. Excluded from source-level equality:
    # two structurally identical `if` forms remain equal regardless of proof.
    true_proof_context: object = field(default=None, compare=False, repr=False)
    false_proof_context: object = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class CondClause:
    """One `cond` clause: an optional condition paired with one result."""

    condition_expr: "ExprNode" | None
    result_expr: "ExprNode"
    is_else: bool
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class CondExpr:
    """One target-2.26 `cond` form, erased into nested `if` before WCC."""

    clauses: tuple["CondClause", ...]
    has_else: bool
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()

@dataclass(frozen=True)
class MatchArm:
    """One `match` variant arm."""

    variant_name: str
    binding_name: str
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class MatchExpr:
    """One exhaustive variant match form."""

    subject: "ExprNode"
    arms: tuple[MatchArm, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class CallExpr:
    """One same-file workflow call."""

    callee_name: str
    bindings: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    authored_callee_span: SourceSpan | None = field(default=None, compare=False)


@dataclass(frozen=True)
class RunRefSource:
    """One exact source repository and commit requested by `run-ref`."""

    repo: str
    commit: str


@dataclass(frozen=True)
class RunRefBundleProgram:
    """One statically named workflow from the caller's compiled bundle."""

    workflow_name: str


@dataclass(frozen=True)
class RunRefPathProgram:
    """One clone-relative Workflow Lisp program and static entrypoint."""

    path: str
    entry_name: str


@dataclass(frozen=True)
class RunRefExpr:
    """One target-2.24 pinned mode-1 child-run expression."""

    source: RunRefSource
    program: RunRefBundleProgram | RunRefPathProgram
    inputs: tuple[tuple[str, "ExprNode"], ...]
    setup: SetupPolicy
    span: SourceSpan
    form_path: tuple[str, ...]
    returns_type_name: str | None = None
    environment: str | None = None
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class TrialArm:
    """One statically authored trial arm and its nested E1 form."""

    arm_id: str
    run_ref: RunRefExpr


@dataclass(frozen=True)
class TrialCheck:
    """One compile-time deterministic trial check."""

    check_id: str
    command: tuple[str, ...]
    authority: str
    required: bool
    timeout_ms: int


@dataclass(frozen=True)
class TrialEvaluation:
    """Closed compile-time evaluation contract for one trial site."""

    checks: tuple[TrialCheck, ...]
    provider: str
    rubric_asset: str
    evidence_confidentiality: str
    max_item_bytes: int
    max_packet_bytes: int
    observation_include: tuple[str, ...]
    diff_cap_bytes: int
    reveal_provider_identity: bool
    aggregation_mode: str
    rep_combine: str
    tie: str
    min_abs_improvement: float
    max_cost_ratio: float
    min_cost_reduction: float
    count_failures_as_outcomes: bool


@dataclass(frozen=True)
class TrialBudget:
    """Closed compile-time trial budget contract."""

    arm_timeout_ms: int
    trial_timeout_ms: int
    max_evaluator_attempts: int
    max_evaluator_concurrency: int


@dataclass(frozen=True)
class TrialExpr:
    """One target-2.25 bounded static trial expression."""

    arms: tuple[TrialArm, ...]
    reps: int
    max_concurrency: int
    evaluation: TrialEvaluation
    budget: TrialBudget
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    site_digest: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class ProcedureCallExpr:
    """One same-file procedure call."""

    callee_name: str
    args: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    authored_callee_span: SourceSpan | None = field(default=None, compare=False)


@dataclass(frozen=True)
class FunctionCallExpr:
    """One frontend-local pure helper call."""

    callee_name: str
    args: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WithPhaseExpr:
    """One compile-time phase-scope wrapper."""

    ctx_expr: "ExprNode"
    phase_name: str
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PhaseTargetExpr:
    """One named phase-target reference."""

    target_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class GeneratedRelpathSeedExpr:
    """One compiler-private relpath seed placeholder."""

    target_type_ref: "TypeRef | Any"
    literal_path: str
    seed_role: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WorkflowRefLiteralExpr:
    """One compile-time workflow reference literal."""

    target_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcRefLiteralExpr:
    """One compile-time procedure reference literal."""

    target_name: str
    authored_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class BindProcBinding:
    """One authored `bind-proc` keyword/value pair."""

    name: str
    value_expr: "ExprNode"
    keyword_span: SourceSpan
    keyword_form_path: tuple[str, ...]
    keyword_expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class BindProcExpr:
    """One compile-time proc-ref partial application."""

    base_expr: "ExprNode"
    bindings: tuple[BindProcBinding, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LetProcBinding:
    """One authored V1 `let-proc` local procedure binding."""

    local_name: str
    params: tuple[ProcedureParam, ...]
    return_type_name: str
    capture_names: tuple[str, ...]
    local_body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LetProcExpr:
    """One lexical local procedure plus the body that can reference it."""

    binding: LetProcBinding
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LiveProviderBinding:
    """One named member of a bounded live-provider supervision group."""

    name: str
    value_expr: "ExprNode"
    observes: str | None
    name_span: SourceSpan
    observes_span: SourceSpan | None
    observed_name_span: SourceSpan | None
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WithLiveProvidersExpr:
    """Exactly two live providers plus their pure settlement body."""

    bindings: tuple[LiveProviderBinding, ...]
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LiveProviderPeerBinding:
    """One named member of a static provider peer group."""

    name: str
    value_expr: "ExprNode"
    name_span: SourceSpan
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WithLiveProviderPeersExpr:
    """Two through eight provider peers plus a pure settlement body."""

    bindings: tuple[LiveProviderPeerBinding, ...]
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PromptDependencySpec:
    """Typed authored exact-path inputs for one provider prompt."""

    required: tuple["ExprNode", ...]
    optional: tuple["ExprNode", ...]
    position: str
    instruction: str | None
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProviderResultExpr:
    """One provider result with a typed structured return contract."""

    provider: "ExprNode"
    prompt: "ExprNode | PromptApplicationExpr"
    inputs: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    model: "ExprNode | None" = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    effort: "ExprNode | None" = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    timeout_sec: "ExprNode | None" = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    delivery: "LiteralExpr | None" = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    materialization_attempts: "LiteralExpr | None" = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    prompt_dependencies: PromptDependencySpec | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    return_spec: ReturnSpec | None = field(
        default=None,
        repr=False,
        metadata={"json_name": "returns_type_name", "json_value_attr": "type_name"},
    )
    returns_type_name: InitVar[str | None] = None

    def __post_init__(self, returns_type_name: str | None) -> None:
        if self.return_spec is None:
            if returns_type_name is None:
                raise TypeError("provider results require a return spec")
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=returns_type_name, guidance=None, span=self.span),
            )
        elif returns_type_name is not None and self.return_spec.type_name != returns_type_name:
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=returns_type_name, guidance=None, span=self.return_spec.span),
            )


ProviderResultExpr.returns_type_name = property(lambda self: self.return_spec.type_name)


@dataclass(frozen=True)
class ProviderBundlePathExpr:
    """One typed projection of canonical provider bundle identity to a relpath."""

    source_expr: "ExprNode"
    target_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class CommandResultExpr:
    """One command result with a typed structured return contract."""

    step_name: str
    argv: tuple["ExprNode", ...]
    adapter_name: str | None
    adapter_inputs: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    return_spec: ReturnSpec | None = field(
        default=None,
        repr=False,
        metadata={"json_name": "returns_type_name", "json_value_attr": "type_name"},
    )
    returns_type_name: InitVar[str | None] = None

    def __post_init__(self, returns_type_name: str | None) -> None:
        if self.return_spec is None:
            if returns_type_name is None:
                raise TypeError("command results require a return spec")
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=returns_type_name, guidance=None, span=self.span),
            )
        elif returns_type_name is not None and self.return_spec.type_name != returns_type_name:
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=returns_type_name, guidance=None, span=self.return_spec.span),
            )


CommandResultExpr.returns_type_name = property(lambda self: self.return_spec.type_name)


@dataclass(frozen=True)
class LoopBodyFnExpr:
    """One compiler-owned `loop/recur` body binder."""

    binding_name: str
    body_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ContinueExpr:
    """One loop-local `continue` control transfer."""

    state_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class DoneExpr:
    """One loop-local `done` control transfer."""

    result_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    terminal_state_expr: "ExprNode | None" = None


@dataclass(frozen=True)
class LoopRecurExpr:
    """One public bounded `loop/recur` form."""

    max_iterations_expr: "ExprNode"
    initial_state_expr: "ExprNode"
    binding_name: str
    body_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    on_exhausted_result_expr: "ExprNode | None" = None
    exhaustion_diagnostic_code: str | None = None
    single_iteration_effect_kinds: tuple[str, ...] | None = None
    effect_cardinality_diagnostic_code: str | None = None


@dataclass(frozen=True)
class RunProviderPhaseExpr:
    """One high-level typed phase provider execution form."""

    phase_name: str
    ctx_expr: "ExprNode"
    inputs_expr: "ExprNode"
    provider: "ExprNode"
    prompt: "ExprNode"
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProduceOneOfExpr:
    """One high-level produced-outcome selection form."""

    returns_type_name: str
    ctx_expr: "ExprNode"
    producer: ProduceOneOfProducerSpec
    candidates: tuple[ProduceOneOfCandidateSpec, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ResumeOrStartExpr:
    """One typed reusable-state gate around resume or fresh start."""

    resume_name: str
    ctx_expr: "ExprNode"
    resume_from_expr: "ExprNode"
    valid_when: tuple[str, ...]
    start_expr: "ExprNode"
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    validation_spec: object | None = None


@dataclass(frozen=True)
class ResourceTransitionExpr:
    """One supported resource movement form."""

    spec: ResourceTransitionSpec
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class MaterializeViewExpr:
    """One generated value-view materialization form."""

    view_name: str
    value_expr: "ExprNode"
    renderer_id: str
    renderer_version: int
    target_expr: "ExprNode" | None
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class FinalizeSelectedItemExpr:
    """One selected-item final result routing form."""

    spec: FinalizeSelectedItemSpec
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


ExprNode = (
    NameExpr
    | LiteralExpr
    | EnumMemberExpr
    | UnionVariantTagExpr
    | RecordExpr
    | PureOpExpr
    | ListExpr
    | ListMapExpr
    | ListMapEffectExpr
    | CompilerListNonemptyHeadExpr
    | PathJoinUnderExpr
    | RecordUpdateExpr
    | LoopStateSeedExpr
    | LoopStateUpdateExpr
    | UnionVariantExpr
    | LetStarExpr
    | IfExpr
    | CondExpr
    | MatchExpr
    | CallExpr
    | RunRefExpr
    | TrialExpr
    | FunctionCallExpr
    | ProcedureCallExpr
    | WithPhaseExpr
    | PhaseTargetExpr
    | GeneratedRelpathSeedExpr
    | WorkflowRefLiteralExpr
    | ProcRefLiteralExpr
    | BindProcExpr
    | LetProcExpr
    | WithLiveProvidersExpr
    | WithLiveProviderPeersExpr
    | ProviderResultExpr
    | ProviderBundlePathExpr
    | CommandResultExpr
    | ContinueExpr
    | DoneExpr
    | LoopRecurExpr
    | RunProviderPhaseExpr
    | ProduceOneOfExpr
    | ResumeOrStartExpr
    | ResourceTransitionExpr
    | MaterializeViewExpr
    | FinalizeSelectedItemExpr
)



_ElaborationRouteHandler = Callable[
    [SyntaxList, tuple[str, ...], frozenset[str], frozenset[str], ElaborationSessionState],
    "ExprNode",
]


def parse_run_ref_expression(
    node: SyntaxNode,
    *,
    target_dsl_version: str,
    bound_names: frozenset[str] = frozenset(),
    procedure_names: frozenset[str] = frozenset(),
    function_names: frozenset[str] = frozenset(),
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    guidance_example: bool = False,
    prompt_catalog: PromptCatalog | None = None,
    session_state: ElaborationSessionState | None = None,
) -> RunRefExpr:
    """Parse the isolated E1 mode-1 surface before compiler integration."""

    datum = syntax_node_datum(node)
    head = syntax_head(datum) if isinstance(datum, SyntaxList) else None
    if head is None or head.resolved_name != "run-ref":
        _raise_error(
            "the run-ref parser requires one `run-ref` form",
            code="run_ref_shape_invalid",
            span=node.span,
            form_path=node.form_path,
            expansion_stack=datum.expansion_stack,
        )
    return _parse_run_ref_syntax_list(
        datum,
        form_path=node.form_path,
        target_dsl_version=target_dsl_version,
        bound_names=bound_names,
        procedure_names=procedure_names,
        function_names=function_names,
        function_name_resolver=function_name_resolver,
        procedure_name_resolver=procedure_name_resolver,
        workflow_name_resolver=workflow_name_resolver,
        guidance_example=guidance_example,
        prompt_catalog=prompt_catalog,
        session_state=session_state,
    )


def parse_trial_expression(
    node: SyntaxNode,
    *,
    target_dsl_version: str,
    bound_names: frozenset[str] = frozenset(),
    procedure_names: frozenset[str] = frozenset(),
    function_names: frozenset[str] = frozenset(),
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    guidance_example: bool = False,
    prompt_catalog: PromptCatalog | None = None,
    session_state: ElaborationSessionState | None = None,
) -> TrialExpr:
    """Parse one closed target-2.25 trial form."""

    datum = syntax_node_datum(node)
    head = syntax_head(datum) if isinstance(datum, SyntaxList) else None
    if head is None or head.resolved_name != "trial":
        _raise_error(
            "the trial parser requires one `trial` form",
            code="trial_arms_invalid",
            span=node.span,
            form_path=node.form_path,
            expansion_stack=datum.expansion_stack,
        )
    return _parse_trial_syntax_list(
        datum,
        form_path=node.form_path,
        target_dsl_version=target_dsl_version,
        bound_names=bound_names,
        procedure_names=procedure_names,
        function_names=function_names,
        function_name_resolver=function_name_resolver,
        procedure_name_resolver=procedure_name_resolver,
        workflow_name_resolver=workflow_name_resolver,
        guidance_example=guidance_example,
        prompt_catalog=prompt_catalog,
        session_state=session_state,
    )


def elaborate_expression(
    node: SyntaxNode,
    *,
    bound_names: frozenset[str],
    procedure_names: frozenset[str] = frozenset(),
    function_names: frozenset[str] = frozenset(),
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    guidance_example: bool = False,
    target_dsl_version: str | None = None,
    prompt_catalog: PromptCatalog | None = None,
    session_state: ElaborationSessionState | None = None,
) -> ExprNode:
    """Elaborate one syntax node into a supported Workflow Lisp expression."""

    session_state = session_state or CompilerSession().elaboration
    previous_state = ElaborationSessionState(
        procedure_name_resolver=session_state.procedure_name_resolver,
        function_name_resolver=session_state.function_name_resolver,
        workflow_name_resolver=session_state.workflow_name_resolver,
        function_names=session_state.function_names,
        local_proc_names=session_state.local_proc_names,
        loop_body_depth=session_state.loop_body_depth,
        let_proc_depth=session_state.let_proc_depth,
        guidance_example=session_state.guidance_example,
        target_dsl_version=session_state.target_dsl_version,
        prompt_catalog=session_state.prompt_catalog,
    )
    session_state.function_name_resolver = function_name_resolver
    session_state.function_names = function_names
    session_state.procedure_name_resolver = procedure_name_resolver
    session_state.workflow_name_resolver = workflow_name_resolver
    session_state.local_proc_names = frozenset()
    session_state.let_proc_depth = 0
    session_state.guidance_example = guidance_example
    session_state.target_dsl_version = target_dsl_version
    session_state.prompt_catalog = prompt_catalog
    try:
        return _elaborate(
            syntax_node_datum(node),
            form_path=node.form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
    finally:
        session_state.procedure_name_resolver = previous_state.procedure_name_resolver
        session_state.function_name_resolver = previous_state.function_name_resolver
        session_state.workflow_name_resolver = previous_state.workflow_name_resolver
        session_state.function_names = previous_state.function_names
        session_state.local_proc_names = previous_state.local_proc_names
        session_state.loop_body_depth = previous_state.loop_body_depth
        session_state.let_proc_depth = previous_state.let_proc_depth
        session_state.guidance_example = previous_state.guidance_example
        session_state.target_dsl_version = previous_state.target_dsl_version
        session_state.prompt_catalog = previous_state.prompt_catalog


def _elaborate(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    if isinstance(datum, SyntaxString):
        return LiteralExpr(
            value=datum.value,
            literal_kind="string",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxInt):
        return LiteralExpr(
            value=datum.value,
            literal_kind="int",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxBool):
        return LiteralExpr(
            value=datum.value,
            literal_kind="bool",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxFloat):
        if session_state.guidance_example:
            return LiteralExpr(
                value=datum.value,
                literal_kind="float",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        _raise_error(
            "float literals are only supported in `defworkflow` parameter defaults",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxIdentifier):
        return _elaborate_symbol(datum, form_path=form_path, bound_names=bound_names)
    if isinstance(datum, SyntaxList):
        return _elaborate_list(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
    raise TypeError(f"unsupported expression datum: {type(datum)!r}")


def _elaborate_symbol(
    datum: SyntaxIdentifier,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> ExprNode:
    if datum.resolved_name in bound_names:
        return NameExpr(
            name=datum.resolved_name,
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    segments = datum.resolved_name.split(".")
    if len(segments) > 1 and segments[0] in bound_names:
        return FieldAccessExpr(
            base=NameExpr(
                name=segments[0],
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            ),
            fields=tuple(segments[1:]),
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if len(segments) == 2:
        return EnumMemberExpr(
            enum_name=segments[0],
            member_name=segments[1],
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return NameExpr(
        name=datum.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_list(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    if not datum.items:
        _raise_error(
            "expression forms must be non-empty lists",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    head = syntax_head(datum)
    if head is None:
        _raise_error(
            "expression forms must start with a symbol",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    form_spec = get_form_spec(
        head.resolved_name,
        target_dsl_version=session_state.target_dsl_version,
    )
    if (
        form_spec is not None
        and head.resolved_name in list_traversal_authored_heads()
        and not target_dsl_supports_list_traversal(
            session_state.target_dsl_version or ""
        )
        and (
            head.resolved_name in session_state.function_names
            or head.resolved_name in procedure_names
            or head.resolved_name in bound_names
        )
    ):
        form_spec = None
    if (
        head.resolved_name == "with-live-provider-peers"
        and session_state.target_dsl_version is not None
        and not target_dsl_supports_provider_peer_messaging(
            session_state.target_dsl_version
        )
        and (
            head.resolved_name in session_state.function_names
            or head.resolved_name in procedure_names
            or head.resolved_name in bound_names
        )
    ):
        form_spec = None
    if (
        form_spec is None
        and head.resolved_name in {"run-ref", "trial"}
        and head.resolved_name not in session_state.function_names
        and head.resolved_name not in procedure_names
        and head.resolved_name not in bound_names
    ):
        route = _route_run_ref if head.resolved_name == "run-ref" else _route_trial
        return route(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
    if form_spec is not None:
        if form_spec.kind is FormKind.TOP_LEVEL_DEFINITION:
            _raise_error(
                f"`{head.display_name}` is a top-level definition form and cannot appear in expression position",
                code="top_level_definition_in_expression_position",
                span=head.span,
                form_path=form_path,
                expansion_stack=head.expansion_stack,
            )
        if form_spec.kind is FormKind.STDLIB_EXTENSION:
            _raise_error(
                f"`{head.display_name}` requires imported stdlib expansion before expression elaboration",
                code="stdlib_extension_missing_import_route",
                span=head.span,
                form_path=form_path,
                expansion_stack=head.expansion_stack,
            )
        if form_spec.elaboration_route is not None:
            return _dispatch_elaboration_route(
                form_spec.elaboration_route,
                datum,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
    if head.resolved_name in session_state.function_names:
        return _elaborate_function_call(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
    if head.resolved_name in procedure_names:
        return _elaborate_procedure_call(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
    if head.resolved_name in session_state.local_proc_names:
        _raise_error(
            f"`{head.display_name}` is a local `let-proc` binding and must be referenced with `proc-ref`",
            code="let_proc_bare_name_invalid",
            span=head.span,
            form_path=form_path,
            expansion_stack=head.expansion_stack,
        )
    if head.resolved_name in bound_names:
        return _elaborate_procedure_call(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
    if _looks_like_pure_operator_head(head.resolved_name):
        _raise_error(
            f"unsupported pure operator `{head.display_name}`",
            code="pure_expr_operator_unsupported",
            span=head.span,
            form_path=form_path,
            expansion_stack=head.expansion_stack,
        )
    _raise_error(
        f"unknown same-file procedure callee `{head.display_name}`",
        code="procedure_call_unknown",
        span=head.span,
        form_path=form_path,
        expansion_stack=head.expansion_stack,
    )


def _dispatch_elaboration_route(
    route_key: str,
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    handler = _elaboration_route_handlers().get(route_key)
    if handler is None:
        raise AssertionError(f"unknown Workflow Lisp elaboration route `{route_key}`")
    return handler(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )


def _guard_loop_fn_route(
    datum: SyntaxList,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    _raise_error(
        "`fn` is valid only as the body form of `loop/recur`",
        code="loop_recur_fn_outside_loop",
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _guard_continue_route(
    datum: SyntaxList,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    if session_state.loop_body_depth <= 0:
        _raise_error(
            "`continue` is valid only inside `loop/recur`",
            code="loop_recur_continue_outside_loop",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return _elaborate_continue(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )


def _guard_done_route(
    datum: SyntaxList,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    if session_state.loop_body_depth <= 0:
        _raise_error(
            "`done` is valid only inside `loop/recur`",
            code="loop_recur_done_outside_loop",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return _elaborate_done(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )


def _guard_let_proc_route(
    datum: SyntaxList,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    if session_state.let_proc_depth > 0:
        _raise_error(
            "`let-proc` cannot be nested in V1",
            code="let_proc_nested_unsupported",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return _elaborate_let_proc(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )


def _route_phase_target(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    del bound_names, procedure_names
    return _elaborate_phase_target(datum, form_path=form_path)


def _route_generated_relpath_seed(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    del bound_names, procedure_names
    return _elaborate_generated_relpath_seed(datum, form_path=form_path)


def _route_workflow_ref(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    del bound_names, procedure_names
    return _elaborate_workflow_ref_literal(datum, form_path=form_path, session_state=session_state)


def _route_proc_ref(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    del bound_names, procedure_names
    return _elaborate_proc_ref_literal(datum, form_path=form_path, session_state=session_state)


def _route_run_ref(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    return _parse_run_ref_syntax_list(
        datum,
        form_path=form_path,
        target_dsl_version=session_state.target_dsl_version or "",
        bound_names=bound_names,
        procedure_names=procedure_names,
        function_names=session_state.function_names,
        function_name_resolver=session_state.function_name_resolver,
        procedure_name_resolver=session_state.procedure_name_resolver,
        workflow_name_resolver=session_state.workflow_name_resolver,
        guidance_example=session_state.guidance_example,
        prompt_catalog=session_state.prompt_catalog,
        session_state=session_state,
    )


def _route_trial(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ExprNode:
    return _parse_trial_syntax_list(
        datum,
        form_path=form_path,
        target_dsl_version=session_state.target_dsl_version or "",
        bound_names=bound_names,
        procedure_names=procedure_names,
        function_names=session_state.function_names,
        function_name_resolver=session_state.function_name_resolver,
        procedure_name_resolver=session_state.procedure_name_resolver,
        workflow_name_resolver=session_state.workflow_name_resolver,
        guidance_example=session_state.guidance_example,
        prompt_catalog=session_state.prompt_catalog,
        session_state=session_state,
    )


def _elaboration_route_handlers() -> dict[str, _ElaborationRouteHandler]:
    return {
        "record": _elaborate_record,
        "pure_op": _elaborate_pure_op,
        "list": _elaborate_list_constructor,
        "list_map": _elaborate_list_map,
        "list_map_effect": _elaborate_list_map_effect,
        "path_join_under": _elaborate_path_join_under,
        "record_update": _elaborate_record_update,
        "loop_state": _elaborate_loop_state,
        "variant": _elaborate_variant,
        "let_star": _elaborate_letstar,
        "if": _elaborate_if,
        "cond": _elaborate_cond,
        "match": _elaborate_match,
        "loop_recur": _elaborate_loop_recur,
        "loop_fn_guard": _guard_loop_fn_route,
        "continue_guard": _guard_continue_route,
        "done_guard": _guard_done_route,
        "call": _elaborate_call,
        "with_phase": _elaborate_with_phase,
        "phase_target": _route_phase_target,
        "generated_relpath_seed": _route_generated_relpath_seed,
        "workflow_ref": _route_workflow_ref,
        "proc_ref": _route_proc_ref,
        "bind_proc": _elaborate_bind_proc,
        "let_proc_guard": _guard_let_proc_route,
        "with_live_providers": _elaborate_with_live_providers,
        "with_live_provider_peers": _elaborate_with_live_provider_peers,
        "provider_result": _elaborate_provider_result,
        "provider_bundle_path": _elaborate_provider_bundle_path,
        "command_result": _elaborate_command_result,
        "run_ref": _route_run_ref,
        "trial": _route_trial,
        "run_provider_phase": _elaborate_run_provider_phase,
        "produce_one_of": _elaborate_produce_one_of,
        "resume_or_start": _elaborate_resume_or_start,
        "resource_transition": _elaborate_resource_transition,
        "materialize_view": _elaborate_materialize_view,
        "finalize_selected_item": _elaborate_finalize_selected_item,
    }


def _run_ref_sections(
    items: list[object],
    *,
    label: str,
    form_path: tuple[str, ...],
) -> dict[str, object]:
    if len(items) % 2 != 0:
        node = items[-1]
        _raise_error(
            f"{label} requires keyword/value pairs",
            code="run_ref_shape_invalid",
            span=node.span,
            form_path=form_path,
            expansion_stack=node.expansion_stack,
        )
    sections: dict[str, object] = {}
    for index in range(0, len(items), 2):
        keyword_node = items[index]
        value_node = items[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                f"{label} entries must start with keywords",
                code="run_ref_shape_invalid",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        if keyword_node.value in sections:
            _raise_error(
                f"{label} duplicated keyword `{keyword_node.value}`",
                code="run_ref_shape_invalid",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        sections[keyword_node.value] = value_node
    return sections


def _normalize_run_ref_program_path(path: str) -> str:
    if (
        not path
        or "\\" in path
        or path.startswith("/")
        or not path.endswith(".orc")
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError(
            "program path must be a canonical relative POSIX .orc path"
        )
    return PurePosixPath(path).as_posix()


def _parse_run_ref_setup(
    setup_node: object,
    *,
    form_path: tuple[str, ...],
) -> SetupPolicy:
    if not isinstance(setup_node, SyntaxList):
        _raise_error(
            "`run-ref :setup` requires a static setup list",
            code="run_ref_literal_required",
            span=setup_node.span,
            form_path=form_path,
            expansion_stack=setup_node.expansion_stack,
        )
    commands: list[SetupCommand] = []
    for raw_command in setup_node.items:
        if not isinstance(raw_command, SyntaxList):
            _raise_error(
                "`run-ref :setup` commands must be literal keyword forms",
                code="run_ref_literal_required",
                span=raw_command.span,
                form_path=form_path,
                expansion_stack=raw_command.expansion_stack,
            )
        command_sections = _run_ref_sections(
            raw_command.items,
            label="`run-ref :setup` command",
            form_path=form_path,
        )
        if ":argv" not in command_sections or not set(
            command_sections
        ).issubset({":argv", ":env"}):
            _raise_error(
                "`run-ref :setup` commands require :argv and optional :env",
                code="run_ref_shape_invalid",
                span=raw_command.span,
                form_path=form_path,
                expansion_stack=raw_command.expansion_stack,
            )
        argv_node = command_sections[":argv"]
        if (
            not isinstance(argv_node, SyntaxList)
            or not argv_node.items
            or any(not isinstance(item, SyntaxString) for item in argv_node.items)
        ):
            _raise_error(
                "`run-ref :setup :argv` requires nonempty literal strings",
                code="run_ref_literal_required",
                span=argv_node.span,
                form_path=form_path,
                expansion_stack=argv_node.expansion_stack,
            )
        env: tuple[tuple[str, str], ...] = ()
        env_node = command_sections.get(":env")
        if env_node is not None:
            if not isinstance(env_node, SyntaxList):
                _raise_error(
                    "`run-ref :setup :env` requires literal keyword/string pairs",
                    code="run_ref_literal_required",
                    span=env_node.span,
                    form_path=form_path,
                    expansion_stack=env_node.expansion_stack,
                )
            env_sections = _run_ref_sections(
                env_node.items,
                label="`run-ref :setup :env`",
                form_path=form_path,
            )
            if any(not isinstance(value, SyntaxString) for value in env_sections.values()):
                _raise_error(
                    "`run-ref :setup :env` values must be literal strings",
                    code="run_ref_literal_required",
                    span=env_node.span,
                    form_path=form_path,
                    expansion_stack=env_node.expansion_stack,
                )
            env = tuple(
                (name[1:], value.value)
                for name, value in env_sections.items()
            )
        try:
            commands.append(
                SetupCommand(
                    argv=tuple(item.value for item in argv_node.items),
                    env=env,
                )
            )
        except ValueError as exc:
            _raise_error(
                f"`run-ref :setup` literal policy is invalid: {exc}",
                code="run_ref_literal_required",
                span=raw_command.span,
                form_path=form_path,
                expansion_stack=raw_command.expansion_stack,
            )
    return SetupPolicy(commands=tuple(commands))


def _parse_run_ref_syntax_list(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    target_dsl_version: str,
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    function_names: frozenset[str],
    function_name_resolver,
    procedure_name_resolver,
    workflow_name_resolver,
    guidance_example: bool,
    prompt_catalog: PromptCatalog | None,
    session_state: ElaborationSessionState | None,
) -> RunRefExpr:
    if not target_dsl_supports_run_ref(target_dsl_version):
        _raise_error(
            f"`run-ref` requires target DSL {RUN_REF_MIN_TARGET_DSL_VERSION} or newer",
            code="run_ref_target_dsl_unsupported",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    sections = _run_ref_sections(
        datum.items[1:],
        label="`run-ref`",
        form_path=form_path,
    )
    required_sections = {":source", ":program", ":inputs", ":policy"}
    allowed_sections = required_sections | {":returns"}
    if not required_sections.issubset(sections) or not set(sections).issubset(
        allowed_sections
    ):
        _raise_error(
            "`run-ref` requires :source, :program, :inputs, and :policy with only approved keys",
            code="run_ref_shape_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    source_node = sections[":source"]
    if not isinstance(source_node, SyntaxList):
        _raise_error(
            "`run-ref :source` must contain :repo and :commit",
            code="run_ref_literal_required",
            span=source_node.span,
            form_path=form_path,
            expansion_stack=source_node.expansion_stack,
        )
    source_sections = _run_ref_sections(
        source_node.items,
        label="`run-ref :source`",
        form_path=form_path,
    )
    repo_node = source_sections.get(":repo")
    commit_node = source_sections.get(":commit")
    if set(source_sections) != {":repo", ":commit"}:
        _raise_error(
            "`run-ref :source` requires exactly :repo and :commit",
            code="run_ref_shape_invalid",
            span=source_node.span,
            form_path=form_path,
            expansion_stack=source_node.expansion_stack,
        )
    if not isinstance(repo_node, SyntaxString) or not isinstance(
        commit_node, SyntaxString
    ):
        selected = (
            repo_node
            if not isinstance(repo_node, SyntaxString)
            else commit_node
        )
        _raise_error(
            "`run-ref :repo` and `:commit` require static string literals",
            code="run_ref_literal_required",
            span=selected.span,
            form_path=form_path,
            expansion_stack=selected.expansion_stack,
        )
    try:
        normalized_repo = normalize_repository_locator(repo_node.value)
    except RunRefSourceRefusal as exc:
        _raise_error(
            f"`run-ref :repo` repository locator is invalid: {exc}",
            code="run_ref_literal_required",
            span=repo_node.span,
            form_path=form_path,
            expansion_stack=repo_node.expansion_stack,
        )
    try:
        commit_sha = validate_commit_sha(commit_node.value)
    except RunRefSourceRefusal as exc:
        _raise_error(
            f"`run-ref :commit` revision is invalid: {exc}",
            code="run_ref_literal_required",
            span=commit_node.span,
            form_path=form_path,
            expansion_stack=commit_node.expansion_stack,
        )

    program_node = sections[":program"]
    if not isinstance(program_node, SyntaxList):
        _raise_error(
            "`run-ref :program` must select a bundle workflow",
            code="run_ref_program_mode_invalid",
            span=program_node.span,
            form_path=form_path,
            expansion_stack=program_node.expansion_stack,
        )
    program_sections = _run_ref_sections(
        program_node.items,
        label="`run-ref :program`",
        form_path=form_path,
    )
    program_keys = set(program_sections)
    if not program_keys.issubset({":bundle", ":path", ":entry"}):
        _raise_error(
            "`run-ref :program` contains an unknown key",
            code="run_ref_shape_invalid",
            span=program_node.span,
            form_path=form_path,
            expansion_stack=program_node.expansion_stack,
        )
    if program_keys == {":bundle"}:
        bundle_node = program_sections[":bundle"]
        bundle_identifier = syntax_identifier(bundle_node)
        if bundle_identifier is None:
            _raise_error(
                "`run-ref :bundle` requires a static workflow-name symbol",
                code="run_ref_literal_required",
                span=bundle_node.span,
                form_path=form_path,
                expansion_stack=bundle_node.expansion_stack,
            )
        bundle_resolver = workflow_name_resolver
        if bundle_resolver is None and session_state is not None:
            bundle_resolver = session_state.workflow_name_resolver
        bundle_name = (
            bundle_resolver(
                bundle_identifier.resolved_name,
                bundle_identifier.span,
                form_path,
            )
            if bundle_resolver is not None
            else bundle_identifier.resolved_name
        )
        program: RunRefBundleProgram | RunRefPathProgram = RunRefBundleProgram(
            workflow_name=bundle_name
        )
        mode = "bundle"
    elif program_keys == {":path", ":entry"}:
        path_node = program_sections[":path"]
        entry_node = program_sections[":entry"]
        entry_identifier = syntax_identifier(entry_node)
        if not isinstance(path_node, SyntaxString):
            _raise_error(
                "`run-ref :path` requires a static string literal",
                code="run_ref_literal_required",
                span=path_node.span,
                form_path=form_path,
                expansion_stack=path_node.expansion_stack,
            )
        if entry_identifier is None:
            _raise_error(
                "`run-ref :entry` requires a static workflow-name symbol",
                code="run_ref_literal_required",
                span=entry_node.span,
                form_path=form_path,
                expansion_stack=entry_node.expansion_stack,
            )
        try:
            normalized_path = _normalize_run_ref_program_path(path_node.value)
        except ValueError as exc:
            _raise_error(
                f"`run-ref :path` is invalid: {exc}",
                code="run_ref_literal_required",
                span=path_node.span,
                form_path=form_path,
                expansion_stack=path_node.expansion_stack,
            )
        program = RunRefPathProgram(
            path=normalized_path,
            entry_name=entry_identifier.resolved_name,
        )
        mode = "path"
    else:
        _raise_error(
            "`run-ref :program` must select exactly :bundle or :path with :entry",
            code="run_ref_program_mode_invalid",
            span=program_node.span,
            form_path=form_path,
            expansion_stack=program_node.expansion_stack,
        )

    inputs_node = sections[":inputs"]
    if not isinstance(inputs_node, SyntaxList):
        _raise_error(
            "`run-ref :inputs` requires keyword/value pairs",
            code="run_ref_literal_required",
            span=inputs_node.span,
            form_path=form_path,
            expansion_stack=inputs_node.expansion_stack,
        )
    input_sections = _run_ref_sections(
        inputs_node.items,
        label="`run-ref :inputs`",
        form_path=form_path,
    )
    if any(not name[1:] for name in input_sections):
        _raise_error(
            "`run-ref :inputs` names must be nonempty keywords",
            code="run_ref_shape_invalid",
            span=inputs_node.span,
            form_path=form_path,
            expansion_stack=inputs_node.expansion_stack,
        )
    inputs = tuple(
        (
            name[1:],
            elaborate_expression(
                SyntaxNode(
                    datum=value,
                    span=value.span,
                    module_path=value.module_path,
                    form_path=form_path + ("inputs", name[1:]),
                ),
                bound_names=bound_names,
                procedure_names=procedure_names,
                function_names=function_names,
                function_name_resolver=function_name_resolver,
                procedure_name_resolver=procedure_name_resolver,
                workflow_name_resolver=workflow_name_resolver,
                guidance_example=guidance_example,
                target_dsl_version=target_dsl_version,
                prompt_catalog=prompt_catalog,
                session_state=session_state,
            ),
        )
        for name, value in input_sections.items()
    )

    returns_node = sections.get(":returns")
    returns_identifier = (
        syntax_identifier(returns_node) if returns_node is not None else None
    )
    if mode == "bundle" and returns_node is not None:
        _raise_error(
            "bundle-mode `run-ref` forbids :returns",
            code="run_ref_program_mode_invalid",
            span=returns_node.span,
            form_path=form_path,
            expansion_stack=returns_node.expansion_stack,
        )
    if mode == "path" and returns_node is not None and returns_identifier is None:
        _raise_error(
            "`run-ref :returns` requires a static type-name symbol",
            code="run_ref_literal_required",
            span=returns_node.span,
            form_path=form_path,
            expansion_stack=returns_node.expansion_stack,
        )
    returns_type_name = (
        returns_identifier.resolved_name
        if returns_identifier is not None
        else None
    )

    policy_node = sections[":policy"]
    if not isinstance(policy_node, SyntaxList):
        _raise_error(
            "`run-ref :policy` must contain an empty :setup",
            code="run_ref_literal_required",
            span=policy_node.span,
            form_path=form_path,
            expansion_stack=policy_node.expansion_stack,
        )
    policy_sections = _run_ref_sections(
        policy_node.items,
        label="`run-ref :policy`",
        form_path=form_path,
    )
    policy_keys = set(policy_sections)
    if not policy_keys.issubset({":environment", ":setup"}):
        _raise_error(
            "`run-ref :policy` contains an unknown key",
            code="run_ref_shape_invalid",
            span=policy_node.span,
            form_path=form_path,
            expansion_stack=policy_node.expansion_stack,
        )
    if mode == "bundle" and ":environment" in policy_sections:
        environment_node = policy_sections[":environment"]
        _raise_error(
            "bundle-mode `run-ref` forbids :environment",
            code="run_ref_program_mode_invalid",
            span=environment_node.span,
            form_path=form_path,
            expansion_stack=environment_node.expansion_stack,
        )
    if mode == "path" and policy_keys != {":environment", ":setup"}:
        _raise_error(
            "path-mode `run-ref` requires :environment and :setup",
            code="run_ref_program_mode_invalid",
            span=policy_node.span,
            form_path=form_path,
            expansion_stack=policy_node.expansion_stack,
        )
    setup_node = policy_sections.get(":setup")
    if mode == "bundle" and policy_keys != {":setup"}:
        _raise_error(
            "`run-ref :policy` requires exactly :setup",
            code="run_ref_shape_invalid",
            span=policy_node.span,
            form_path=form_path,
            expansion_stack=policy_node.expansion_stack,
        )
    environment: str | None = None
    if mode == "path":
        environment_node = policy_sections[":environment"]
        if not isinstance(environment_node, SyntaxKeyword):
            _raise_error(
                "`run-ref :environment` requires a static policy keyword",
                code="run_ref_literal_required",
                span=environment_node.span,
                form_path=form_path,
                expansion_stack=environment_node.expansion_stack,
            )
        if environment_node.value != ":deterministic-effect-free":
            _raise_error(
                "path-mode `run-ref` requires :deterministic-effect-free",
                code="run_ref_program_mode_invalid",
                span=environment_node.span,
                form_path=form_path,
                expansion_stack=environment_node.expansion_stack,
            )
        environment = environment_node.value[1:]
    setup = _parse_run_ref_setup(setup_node, form_path=form_path)

    return RunRefExpr(
        source=RunRefSource(repo=normalized_repo, commit=commit_sha),
        program=program,
        inputs=inputs,
        setup=setup,
        span=datum.span,
        form_path=form_path,
        returns_type_name=returns_type_name,
        environment=environment,
        expansion_stack=datum.expansion_stack,
    )


def _trial_fail(
    node: SyntaxNode | SyntaxList | object,
    *,
    code: str,
    message: str,
    form_path: tuple[str, ...],
) -> None:
    _raise_error(
        message,
        code=code,
        span=node.span,
        form_path=form_path,
        expansion_stack=node.expansion_stack,
    )


def _trial_is_compile_time_structural_data(node: object) -> bool:
    if isinstance(node, SyntaxNode):
        return _trial_is_compile_time_structural_data(syntax_node_datum(node))
    if isinstance(
        node,
        (SyntaxString, SyntaxInt, SyntaxFloat, SyntaxBool, SyntaxKeyword),
    ):
        return True
    if not isinstance(node, SyntaxList):
        return False
    head = syntax_head(node)
    return (
        head is not None
        and head.resolved_name in {"record", "list"}
        and all(
            _trial_is_compile_time_structural_data(item)
            for item in node.items[1:]
        )
    )


def _trial_record_sections(
    node: object,
    *,
    label: str,
    code: str,
    form_path: tuple[str, ...],
) -> dict[str, object]:
    if not isinstance(node, SyntaxList):
        _trial_fail(
            node,
            code=code,
            message=f"{label} must be a compile-time structural record",
            form_path=form_path,
        )
    head = syntax_head(node)
    if head is None or head.resolved_name != "record":
        _trial_fail(
            node,
            code=code,
            message=f"{label} must be a compile-time pure `(record ...)` value",
            form_path=form_path,
        )
    return _trial_sections(
        node.items[1:],
        label=label,
        code=code,
        form_path=form_path,
    )


def _trial_sections(
    items: tuple[object, ...] | list[object],
    *,
    label: str,
    code: str,
    form_path: tuple[str, ...],
) -> dict[str, object]:
    if len(items) % 2 != 0:
        _trial_fail(
            items[-1],
            code=code,
            message=f"{label} requires keyword/value pairs",
            form_path=form_path,
        )
    sections: dict[str, object] = {}
    for index in range(0, len(items), 2):
        key = items[index]
        value = items[index + 1]
        if not isinstance(key, SyntaxKeyword):
            _trial_fail(
                key,
                code=code,
                message=f"{label} keys must be keywords",
                form_path=form_path,
            )
        if key.value in sections:
            _trial_fail(
                key,
                code=code,
                message=f"{label} contains duplicate key {key.value}",
                form_path=form_path,
            )
        sections[key.value] = value
    return sections


def _trial_require_exact_keys(
    sections: dict[str, object],
    expected: frozenset[str],
    *,
    node: object,
    code: str,
    label: str,
    form_path: tuple[str, ...],
) -> None:
    if set(sections) != expected:
        _trial_fail(
            node,
            code=code,
            message=f"{label} has missing, duplicate, or unknown keys",
            form_path=form_path,
        )


def _trial_list_items(
    node: object,
    *,
    code: str,
    label: str,
    form_path: tuple[str, ...],
) -> tuple[object, ...]:
    if not isinstance(node, SyntaxList):
        _trial_fail(
            node,
            code=code,
            message=f"{label} must be a compile-time `(list ...)` value",
            form_path=form_path,
        )
    head = syntax_head(node)
    if head is None or head.resolved_name != "list":
        _trial_fail(
            node,
            code=code,
            message=f"{label} must be a compile-time `(list ...)` value",
            form_path=form_path,
        )
    return tuple(node.items[1:])


def _trial_positive_int(
    node: object,
    *,
    code: str,
    label: str,
    form_path: tuple[str, ...],
) -> int:
    if (
        not isinstance(node, SyntaxInt)
        or isinstance(node.value, bool)
        or node.value <= 0
    ):
        _trial_fail(
            node,
            code=code,
            message=f"{label} must be a positive integer literal",
            form_path=form_path,
        )
    return node.value


def _trial_number(
    node: object,
    *,
    positive: bool,
    label: str,
    form_path: tuple[str, ...],
) -> float:
    if not isinstance(node, (SyntaxInt, SyntaxFloat)) or isinstance(
        node.value, bool
    ):
        _trial_fail(
            node,
            code="trial_evaluation_contract_invalid",
            message=f"{label} must be a finite numeric literal",
            form_path=form_path,
        )
    try:
        value = float(node.value)
    except OverflowError:
        _trial_fail(
            node,
            code="trial_evaluation_contract_invalid",
            message=f"{label} is outside its accepted numeric range",
            form_path=form_path,
        )
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        _trial_fail(
            node,
            code="trial_evaluation_contract_invalid",
            message=f"{label} is outside its accepted numeric range",
            form_path=form_path,
        )
    return value


def _parse_trial_evaluation(
    node: object,
    *,
    form_path: tuple[str, ...],
) -> TrialEvaluation:
    if not _trial_is_compile_time_structural_data(node):
        _trial_fail(
            node,
            code="trial_evaluation_contract_not_pure",
            message="`trial :evaluation` must be compile-time structural data",
            form_path=form_path,
        )
    sections = _trial_record_sections(
        node,
        label="`trial :evaluation`",
        code="trial_evaluation_contract_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        sections,
        frozenset(
            {
                ":checks",
                ":judgment",
                ":observation",
                ":aggregation",
                ":success-rule",
            }
        ),
        node=node,
        code="trial_evaluation_contract_invalid",
        label="`trial :evaluation`",
        form_path=form_path,
    )

    checks: list[TrialCheck] = []
    seen_check_ids: set[str] = set()
    for check_node in _trial_list_items(
        sections[":checks"],
        code="trial_evaluation_contract_invalid",
        label="`trial :evaluation :checks`",
        form_path=form_path,
    ):
        check = _trial_record_sections(
            check_node,
            label="trial check",
            code="trial_evaluation_contract_invalid",
            form_path=form_path,
        )
        _trial_require_exact_keys(
            check,
            frozenset(
                {":id", ":command", ":authority", ":required", ":timeout-ms"}
            ),
            node=check_node,
            code="trial_evaluation_contract_invalid",
            label="trial check",
            form_path=form_path,
        )
        check_id_node = check[":id"]
        authority_node = check[":authority"]
        required_node = check[":required"]
        if not isinstance(check_id_node, SyntaxString) or not check_id_node.value:
            _trial_fail(
                check_id_node,
                code="trial_evaluation_contract_invalid",
                message="trial check IDs must be non-empty string literals",
                form_path=form_path,
            )
        if check_id_node.value in seen_check_ids:
            _trial_fail(
                check_id_node,
                code="trial_evaluation_contract_invalid",
                message="trial check IDs must be unique",
                form_path=form_path,
            )
        seen_check_ids.add(check_id_node.value)
        command_nodes = _trial_list_items(
            check[":command"],
            code="trial_evaluation_contract_invalid",
            label="trial check command",
            form_path=form_path,
        )
        if not command_nodes or any(
            not isinstance(item, SyntaxString) or not item.value
            for item in command_nodes
        ):
            _trial_fail(
                check[":command"],
                code="trial_evaluation_contract_invalid",
                message="trial check commands require non-empty literal argv",
                form_path=form_path,
            )
        if (
            not isinstance(authority_node, SyntaxString)
            or authority_node.value not in {"correctness", "invariant"}
        ):
            _trial_fail(
                authority_node,
                code="trial_evaluation_contract_invalid",
                message="trial check authority must be correctness or invariant",
                form_path=form_path,
            )
        if not isinstance(required_node, SyntaxBool):
            _trial_fail(
                required_node,
                code="trial_evaluation_contract_invalid",
                message="trial check required must be a Boolean literal",
                form_path=form_path,
            )
        checks.append(
            TrialCheck(
                check_id=check_id_node.value,
                command=tuple(item.value for item in command_nodes),
                authority=authority_node.value,
                required=required_node.value,
                timeout_ms=_trial_positive_int(
                    check[":timeout-ms"],
                    code="trial_evaluation_contract_invalid",
                    label="trial check timeout",
                    form_path=form_path,
                ),
            )
        )

    judgment_node = sections[":judgment"]
    judgment = _trial_record_sections(
        judgment_node,
        label="`trial :evaluation :judgment`",
        code="trial_evaluation_contract_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        judgment,
        frozenset(
            {
                ":provider",
                ":rubric-asset",
                ":evidence-confidentiality",
                ":evidence-limits",
            }
        ),
        node=judgment_node,
        code="trial_evaluation_contract_invalid",
        label="trial judgment",
        form_path=form_path,
    )
    provider_node = judgment[":provider"]
    rubric_node = judgment[":rubric-asset"]
    confidentiality_node = judgment[":evidence-confidentiality"]
    if not isinstance(provider_node, SyntaxString) or not provider_node.value:
        _trial_fail(
            provider_node,
            code="trial_evaluation_contract_invalid",
            message="trial judgment provider must be a non-empty string literal",
            form_path=form_path,
        )
    if not isinstance(rubric_node, SyntaxString) or not rubric_node.value:
        _trial_fail(
            rubric_node,
            code="trial_evaluation_contract_invalid",
            message="trial judgment rubric asset must be a non-empty string literal",
            form_path=form_path,
        )
    rubric_path = PurePosixPath(rubric_node.value)
    if (
        rubric_path.is_absolute()
        or rubric_node.value != rubric_path.as_posix()
        or any(part in {"", ".", ".."} for part in rubric_path.parts)
    ):
        _trial_fail(
            rubric_node,
            code="trial_evaluation_rubric_unresolved",
            message="trial rubric asset must be one normalized relative path",
            form_path=form_path,
        )
    if (
        not isinstance(confidentiality_node, SyntaxString)
        or confidentiality_node.value != "same_trust_boundary"
    ):
        _trial_fail(
            confidentiality_node,
            code="trial_blinding_policy_invalid",
            message="trial evidence confidentiality must be same_trust_boundary",
            form_path=form_path,
        )
    limits_node = judgment[":evidence-limits"]
    limits = _trial_record_sections(
        limits_node,
        label="trial evidence limits",
        code="trial_packet_limit_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        limits,
        frozenset({":max-item-bytes", ":max-packet-bytes"}),
        node=limits_node,
        code="trial_packet_limit_invalid",
        label="trial evidence limits",
        form_path=form_path,
    )
    max_item_bytes = _trial_positive_int(
        limits[":max-item-bytes"],
        code="trial_packet_limit_invalid",
        label="max item bytes",
        form_path=form_path,
    )
    max_packet_bytes = _trial_positive_int(
        limits[":max-packet-bytes"],
        code="trial_packet_limit_invalid",
        label="max packet bytes",
        form_path=form_path,
    )
    if max_packet_bytes < max_item_bytes:
        _trial_fail(
            limits_node,
            code="trial_packet_limit_invalid",
            message="max packet bytes must be at least max item bytes",
            form_path=form_path,
        )

    observation_node = sections[":observation"]
    observation = _trial_record_sections(
        observation_node,
        label="trial observation",
        code="trial_packet_policy_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        observation,
        frozenset(
            {":include", ":diff-cap-bytes", ":reveal-provider-identity"}
        ),
        node=observation_node,
        code="trial_packet_policy_invalid",
        label="trial observation",
        form_path=form_path,
    )
    include_nodes = _trial_list_items(
        observation[":include"],
        code="trial_packet_policy_invalid",
        label="trial observation include",
        form_path=form_path,
    )
    allowed_includes = {
        "task_spec",
        "validated_result",
        "workspace_delta",
        "check_results",
        "declared_artifacts",
        "failure_evidence",
    }
    if (
        any(
            not isinstance(item, SyntaxString)
            or item.value not in allowed_includes
            for item in include_nodes
        )
        or len({item.value for item in include_nodes}) != len(include_nodes)
    ):
        _trial_fail(
            observation[":include"],
            code="trial_packet_policy_invalid",
            message="trial observation include names must be unique and closed",
            form_path=form_path,
        )
    reveal_node = observation[":reveal-provider-identity"]
    if not isinstance(reveal_node, SyntaxBool) or reveal_node.value:
        _trial_fail(
            reveal_node,
            code="trial_blinding_policy_invalid",
            message="trial provider identity reveal must be false",
            form_path=form_path,
        )

    aggregation_node = sections[":aggregation"]
    aggregation = _trial_record_sections(
        aggregation_node,
        label="trial aggregation",
        code="trial_evaluation_contract_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        aggregation,
        frozenset({":mode", ":rep-combine", ":tie"}),
        node=aggregation_node,
        code="trial_evaluation_contract_invalid",
        label="trial aggregation",
        form_path=form_path,
    )
    aggregation_expected = {
        ":mode": "independent_rubric",
        ":rep-combine": "median",
        ":tie": "authored_order",
    }
    for key, expected in aggregation_expected.items():
        value = aggregation[key]
        if not isinstance(value, SyntaxString) or value.value != expected:
            _trial_fail(
                value,
                code="trial_evaluation_contract_invalid",
                message=f"trial aggregation {key} must be {expected}",
                form_path=form_path,
            )

    success_node = sections[":success-rule"]
    success = _trial_record_sections(
        success_node,
        label="trial success rule",
        code="trial_evaluation_contract_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        success,
        frozenset(
            {":superior", ":non-inferior", ":count-failures-as-outcomes"}
        ),
        node=success_node,
        code="trial_evaluation_contract_invalid",
        label="trial success rule",
        form_path=form_path,
    )
    superior_node = success[":superior"]
    superior = _trial_record_sections(
        superior_node,
        label="trial superior rule",
        code="trial_evaluation_contract_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        superior,
        frozenset({":min-abs-improvement", ":max-cost-ratio"}),
        node=superior_node,
        code="trial_evaluation_contract_invalid",
        label="trial superior rule",
        form_path=form_path,
    )
    noninferior_node = success[":non-inferior"]
    noninferior = _trial_record_sections(
        noninferior_node,
        label="trial non-inferior rule",
        code="trial_evaluation_contract_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        noninferior,
        frozenset({":min-cost-reduction"}),
        node=noninferior_node,
        code="trial_evaluation_contract_invalid",
        label="trial non-inferior rule",
        form_path=form_path,
    )
    failures_node = success[":count-failures-as-outcomes"]
    if not isinstance(failures_node, SyntaxBool) or not failures_node.value:
        _trial_fail(
            failures_node,
            code="trial_evaluation_contract_invalid",
            message="trial failures must count as outcomes",
            form_path=form_path,
        )

    return TrialEvaluation(
        checks=tuple(checks),
        provider=provider_node.value,
        rubric_asset=rubric_node.value,
        evidence_confidentiality=confidentiality_node.value,
        max_item_bytes=max_item_bytes,
        max_packet_bytes=max_packet_bytes,
        observation_include=tuple(item.value for item in include_nodes),
        diff_cap_bytes=_trial_positive_int(
            observation[":diff-cap-bytes"],
            code="trial_packet_limit_invalid",
            label="trial diff cap",
            form_path=form_path,
        ),
        reveal_provider_identity=False,
        aggregation_mode="independent_rubric",
        rep_combine="median",
        tie="authored_order",
        min_abs_improvement=_trial_number(
            superior[":min-abs-improvement"],
            positive=False,
            label="minimum absolute improvement",
            form_path=form_path,
        ),
        max_cost_ratio=_trial_number(
            superior[":max-cost-ratio"],
            positive=True,
            label="maximum cost ratio",
            form_path=form_path,
        ),
        min_cost_reduction=_trial_number(
            noninferior[":min-cost-reduction"],
            positive=False,
            label="minimum cost reduction",
            form_path=form_path,
        ),
        count_failures_as_outcomes=True,
    )


def _parse_trial_budget(
    node: object,
    *,
    form_path: tuple[str, ...],
) -> TrialBudget:
    if not _trial_is_compile_time_structural_data(node):
        _trial_fail(
            node,
            code="trial_evaluation_contract_not_pure",
            message="`trial :budget` must be compile-time structural data",
            form_path=form_path,
        )
    sections = _trial_record_sections(
        node,
        label="`trial :budget`",
        code="trial_budget_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        sections,
        frozenset(
            {
                ":arm-timeout-ms",
                ":trial-timeout-ms",
                ":max-evaluator-attempts",
                ":max-evaluator-concurrency",
            }
        ),
        node=node,
        code="trial_budget_invalid",
        label="trial budget",
        form_path=form_path,
    )
    values = {
        key: _trial_positive_int(
            sections[key],
            code="trial_budget_invalid",
            label=key,
            form_path=form_path,
        )
        for key in sections
    }
    if values[":max-evaluator-concurrency"] > values[":max-evaluator-attempts"]:
        _trial_fail(
            node,
            code="trial_budget_invalid",
            message="evaluator concurrency cannot exceed evaluator attempts",
            form_path=form_path,
        )
    return TrialBudget(
        arm_timeout_ms=values[":arm-timeout-ms"],
        trial_timeout_ms=values[":trial-timeout-ms"],
        max_evaluator_attempts=values[":max-evaluator-attempts"],
        max_evaluator_concurrency=values[":max-evaluator-concurrency"],
    )


def _parse_trial_syntax_list(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    target_dsl_version: str,
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    function_names: frozenset[str],
    function_name_resolver,
    procedure_name_resolver,
    workflow_name_resolver,
    guidance_example: bool,
    prompt_catalog: PromptCatalog | None,
    session_state: ElaborationSessionState | None,
) -> TrialExpr:
    if not target_dsl_supports_trial(target_dsl_version):
        _raise_error(
            f"`trial` requires target DSL {TRIAL_MIN_TARGET_DSL_VERSION} or newer",
            code="trial_target_dsl_unsupported",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    sections = _trial_sections(
        datum.items[1:],
        label="`trial`",
        code="trial_arms_invalid",
        form_path=form_path,
    )
    _trial_require_exact_keys(
        sections,
        frozenset(
            {":arms", ":reps", ":max-concurrency", ":evaluation", ":budget"}
        ),
        node=datum,
        code="trial_arms_invalid",
        label="`trial`",
        form_path=form_path,
    )
    arms_node = sections[":arms"]
    if not isinstance(arms_node, SyntaxList):
        _trial_fail(
            arms_node,
            code="trial_arms_invalid",
            message="trial arms must be one static list",
            form_path=form_path,
        )
    arms: list[TrialArm] = []
    seen_ids: set[str] = set()
    for index, arm_node in enumerate(arms_node.items):
        if not isinstance(arm_node, SyntaxList):
            _trial_fail(
                arm_node,
                code="trial_arms_invalid",
                message="each trial arm must contain :id and :run-ref",
                form_path=form_path,
            )
        arm_sections = _trial_sections(
            arm_node.items,
            label="trial arm",
            code="trial_arms_invalid",
            form_path=form_path,
        )
        _trial_require_exact_keys(
            arm_sections,
            frozenset({":id", ":run-ref"}),
            node=arm_node,
            code="trial_arms_invalid",
            label="trial arm",
            form_path=form_path,
        )
        arm_id_node = arm_sections[":id"]
        if not isinstance(arm_id_node, SyntaxString) or not arm_id_node.value:
            _trial_fail(
                arm_id_node,
                code="trial_arms_invalid",
                message="trial arm IDs must be non-empty string literals",
                form_path=form_path,
            )
        if arm_id_node.value in seen_ids:
            _trial_fail(
                arm_id_node,
                code="trial_arms_invalid",
                message="trial arm IDs must be unique",
                form_path=form_path,
            )
        seen_ids.add(arm_id_node.value)
        run_ref_node = arm_sections[":run-ref"]
        run_ref_head = (
            syntax_head(run_ref_node)
            if isinstance(run_ref_node, SyntaxList)
            else None
        )
        if run_ref_head is None or run_ref_head.resolved_name != "run-ref":
            _trial_fail(
                run_ref_node,
                code="trial_arms_invalid",
                message="trial arms require nested `run-ref` syntax",
                form_path=form_path,
            )
        arms.append(
            TrialArm(
                arm_id=arm_id_node.value,
                run_ref=_parse_run_ref_syntax_list(
                    run_ref_node,
                    form_path=(*form_path, "arms", str(index), "run-ref"),
                    target_dsl_version=target_dsl_version,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    function_names=function_names,
                    function_name_resolver=function_name_resolver,
                    procedure_name_resolver=procedure_name_resolver,
                    workflow_name_resolver=workflow_name_resolver,
                    guidance_example=guidance_example,
                    prompt_catalog=prompt_catalog,
                    session_state=session_state,
                ),
            )
        )
    if not 2 <= len(arms) <= 16:
        _trial_fail(
            arms_node,
            code="trial_arms_invalid",
            message="trial requires between 2 and 16 static arms",
            form_path=form_path,
        )
    reps = _trial_positive_int(
        sections[":reps"],
        code="trial_reps_invalid",
        label="trial repetitions",
        form_path=form_path,
    )
    if reps > 64 or len(arms) * reps > 256:
        _trial_fail(
            sections[":reps"],
            code="trial_reps_invalid",
            message="trial repetitions or total cells exceed their bounds",
            form_path=form_path,
        )
    max_concurrency = _trial_positive_int(
        sections[":max-concurrency"],
        code="trial_concurrency_invalid",
        label="trial arm concurrency",
        form_path=form_path,
    )
    if max_concurrency > 32 or max_concurrency > len(arms) * reps:
        _trial_fail(
            sections[":max-concurrency"],
            code="trial_concurrency_invalid",
            message="trial arm concurrency exceeds its bound or cell count",
            form_path=form_path,
        )
    return TrialExpr(
        arms=tuple(arms),
        reps=reps,
        max_concurrency=max_concurrency,
        evaluation=_parse_trial_evaluation(
            sections[":evaluation"], form_path=form_path
        ),
        budget=_parse_trial_budget(sections[":budget"], form_path=form_path),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _looks_like_pure_operator_head(name: str) -> bool:
    if name in PURE_EXPR_OPERATOR_CATALOG:
        return True
    if "/" in name:
        return True
    return name in {"and", "or", "not", "min", "max", "some?", "or-else", "record-update"}


def _require_list_traversal_target(
    datum: SyntaxList,
    *,
    session_state: ElaborationSessionState,
) -> None:
    if target_dsl_supports_list_traversal(
        session_state.target_dsl_version or ""
    ):
        return
    _raise_error(
        (
            "list traversal and rooted path construction require target DSL "
            f"{LIST_TRAVERSAL_MIN_TARGET_DSL_VERSION} or newer"
        ),
        code="list_traversal_target_dsl_unsupported",
        span=datum.span,
        form_path=datum.form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_record(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> RecordExpr:
    if len(datum.items) < 2:
        _raise_error("`record` requires a type name", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    type_node = datum.items[1]
    type_identifier = syntax_identifier(type_node)
    if type_identifier is None:
        _raise_error(
            "`record` type name must be a symbol",
            span=type_node.span,
            form_path=form_path,
            expansion_stack=type_node.expansion_stack,
        )
    raw_fields = datum.items[2:]
    if len(raw_fields) % 2 != 0:
        _raise_error(
            "`record` requires keyword/value field pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    fields: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_fields), 2):
        keyword_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`record` fields must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        fields.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
            )
        )
    return RecordExpr(
        type_name=type_identifier.resolved_name,
        fields=tuple(fields),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_pure_op(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> PureOpExpr:
    head = syntax_head(datum)
    assert head is not None
    spec = PURE_EXPR_OPERATOR_CATALOG[head.resolved_name]
    if spec.min_schema_version >= 2:
        _require_list_traversal_target(datum, session_state=session_state)
    return PureOpExpr(
        operator=head.resolved_name,
        args=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            for item in datum.items[1:]
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_list_constructor(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ListExpr:
    _require_list_traversal_target(datum, session_state=session_state)
    return ListExpr(
        items=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            for item in datum.items[1:]
        ),
        element_type_ref=None,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_list_map(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ListMapExpr:
    _require_list_traversal_target(datum, session_state=session_state)
    if len(datum.items) != 3:
        _raise_error(
            "`list/map` requires one binder list and one pure body",
            code="list_map_binder_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_binders = datum.items[1]
    if (
        not isinstance(raw_binders, SyntaxList)
        or len(raw_binders.items) != 1
        or not isinstance(raw_binders.items[0], SyntaxList)
        or len(raw_binders.items[0].items) != 2
    ):
        _raise_error(
            "`list/map` binder must be exactly `((name list-expr))`",
            code="list_map_binder_invalid",
            span=raw_binders.span,
            form_path=form_path,
            expansion_stack=raw_binders.expansion_stack,
        )
    raw_binding = raw_binders.items[0]
    binder = syntax_identifier(raw_binding.items[0])
    if (
        binder is None
        or binder.resolved_name.startswith("__")
        or binder.resolved_name in bound_names
    ):
        _raise_error(
            "`list/map` binder name is invalid, reserved, or already bound",
            code="list_map_binder_invalid",
            span=raw_binding.items[0].span,
            form_path=form_path,
            expansion_stack=raw_binding.items[0].expansion_stack,
        )
    source_expr = _elaborate(
        raw_binding.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )
    body_expr = _elaborate(
        datum.items[2],
        form_path=form_path,
        bound_names=frozenset((*bound_names, binder.resolved_name)),
        procedure_names=procedure_names,
        session_state=session_state,
    )
    return ListMapExpr(
        binder_name=binder.resolved_name,
        source_expr=source_expr,
        body_expr=body_expr,
        source_item_type_ref=None,
        result_item_type_ref=None,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_list_map_effect(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ListMapEffectExpr:
    _require_list_traversal_target(datum, session_state=session_state)
    if (
        len(datum.items) != 5
        or not isinstance(datum.items[2], SyntaxKeyword)
        or datum.items[2].value != ":max"
        or not isinstance(datum.items[3], SyntaxInt)
        or isinstance(datum.items[3].value, bool)
        or datum.items[3].value <= 0
    ):
        _raise_error(
            "`list/map-effect` requires `:max` followed by a positive integer literal",
            code="list_map_effect_max_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_binders = datum.items[1]
    if (
        not isinstance(raw_binders, SyntaxList)
        or len(raw_binders.items) != 1
        or not isinstance(raw_binders.items[0], SyntaxList)
        or len(raw_binders.items[0].items) != 2
    ):
        _raise_error(
            "`list/map-effect` binder must be exactly `((name list-expr))`",
            code="list_map_binder_invalid",
            span=raw_binders.span,
            form_path=form_path,
            expansion_stack=raw_binders.expansion_stack,
        )
    raw_binding = raw_binders.items[0]
    binder = syntax_identifier(raw_binding.items[0])
    if (
        binder is None
        or binder.resolved_name.startswith("__")
        or binder.resolved_name in bound_names
    ):
        _raise_error(
            "`list/map-effect` binder name is invalid, reserved, or already bound",
            code="list_map_binder_invalid",
            span=raw_binding.items[0].span,
            form_path=form_path,
            expansion_stack=raw_binding.items[0].expansion_stack,
        )
    source_expr = _elaborate(
        raw_binding.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )
    body_expr = _elaborate(
        datum.items[4],
        form_path=form_path,
        bound_names=frozenset((*bound_names, binder.resolved_name)),
        procedure_names=procedure_names,
        session_state=session_state,
    )
    return ListMapEffectExpr(
        binder_name=binder.resolved_name,
        source_expr=source_expr,
        max_iterations=datum.items[3].value,
        body_expr=body_expr,
        source_item_type_ref=None,
        result_item_type_ref=None,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_path_join_under(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> PathJoinUnderExpr:
    _require_list_traversal_target(datum, session_state=session_state)
    if len(datum.items) != 3:
        _raise_error(
            "`path/join-under` requires a path type and one child expression",
            code="path_join_under_type_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    path_type = syntax_identifier(datum.items[1])
    if path_type is None:
        _raise_error(
            "`path/join-under` first operand must be a resolved path type",
            code="path_join_under_type_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    return PathJoinUnderExpr(
        path_type_name=path_type.resolved_name,
        child_expr=_elaborate(
            datum.items[2],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        path_type_ref=None,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_record_update(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> RecordUpdateExpr:
    if len(datum.items) < 4:
        _raise_error(
            "`record-update` requires a base expression and at least one keyword/value override",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_fields = datum.items[2:]
    if len(raw_fields) % 2 != 0:
        _raise_error(
            "`record-update` requires keyword/value override pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    overrides: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_fields), 2):
        keyword_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`record-update` overrides must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        overrides.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
            )
        )
    return RecordUpdateExpr(
        base_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        overrides=tuple(overrides),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_loop_state(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> LoopStateSeedExpr | LoopStateUpdateExpr:
    if len(datum.items) < 2:
        _raise_error(
            "`loop-state` requires typed field entries or `:like` plus overrides",
            code="loop_state_requires_typed_fields",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    first_item = datum.items[1]
    if isinstance(first_item, SyntaxKeyword):
        return _elaborate_loop_state_update(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
    return _elaborate_loop_state_seed(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )


def _elaborate_loop_state_seed(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> LoopStateSeedExpr:
    fields: list[LoopStateField] = []
    seen_fields: set[str] = set()
    for field_node in datum.items[1:]:
        if not isinstance(field_node, SyntaxList) or len(field_node.items) != 3:
            _raise_error(
                "`loop-state` seed fields must use `(field Type value)` entries",
                code="loop_state_requires_typed_fields",
                span=field_node.span,
                form_path=form_path,
                expansion_stack=field_node.expansion_stack,
            )
        name_node = syntax_identifier(field_node.items[0])
        type_node = syntax_identifier(field_node.items[1])
        value_node = field_node.items[2]
        if name_node is None or type_node is None:
            _raise_error(
                "`loop-state` seed fields must use `(field Type value)` entries",
                code="loop_state_requires_typed_fields",
                span=field_node.span,
                form_path=form_path,
                expansion_stack=field_node.expansion_stack,
            )
        if name_node.resolved_name in seen_fields:
            _raise_error(
                f"duplicate loop-state field `{name_node.display_name}`",
                code="loop_state_duplicate_field",
                span=name_node.span,
                form_path=form_path,
                expansion_stack=name_node.expansion_stack,
            )
        seen_fields.add(name_node.resolved_name)
        fields.append(
            LoopStateField(
                name=name_node.resolved_name,
                type_name=type_node.resolved_name,
                value_expr=_elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
                span=field_node.span,
                form_path=form_path,
                expansion_stack=field_node.expansion_stack,
            )
        )
    return LoopStateSeedExpr(
        fields=tuple(fields),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_loop_state_update(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> LoopStateUpdateExpr:
    if len(datum.items) < 4 or not isinstance(datum.items[1], SyntaxKeyword) or datum.items[1].value != ":like":
        _raise_error(
            "`loop-state` updates must start with `:like` and a base expression",
            code="loop_state_requires_typed_fields",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    base_node = datum.items[2]
    if isinstance(base_node, SyntaxKeyword):
        _raise_error(
            "`loop-state :like` requires a base expression before overrides",
            code="loop_state_requires_typed_fields",
            span=base_node.span,
            form_path=form_path,
            expansion_stack=base_node.expansion_stack,
        )
    override_nodes = datum.items[3:]
    if len(override_nodes) % 2 != 0:
        _raise_error(
            "`loop-state :like` requires keyword/value override pairs",
            code="loop_state_requires_typed_fields",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    seen_fields: set[str] = set()
    overrides: list[tuple[str, ExprNode]] = []
    for index in range(0, len(override_nodes), 2):
        keyword_node = override_nodes[index]
        value_node = override_nodes[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`loop-state :like` overrides must use keyword/value pairs",
                code="loop_state_requires_typed_fields",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        field_name = keyword_node.value[1:]
        if field_name in seen_fields:
            _raise_error(
                f"duplicate loop-state field `{field_name}`",
                code="loop_state_duplicate_field",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        seen_fields.add(field_name)
        overrides.append(
            (
                field_name,
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
            )
        )
    return LoopStateUpdateExpr(
        base_expr=_elaborate(
            base_node,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        overrides=tuple(overrides),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_variant(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> UnionVariantExpr:
    if len(datum.items) < 3:
        _raise_error(
            "`variant` requires a union type and variant name",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    type_node = datum.items[1]
    type_identifier = syntax_identifier(type_node)
    if type_identifier is None:
        _raise_error(
            "`variant` union type must be a symbol",
            span=type_node.span,
            form_path=form_path,
            expansion_stack=type_node.expansion_stack,
        )
    variant_node = datum.items[2]
    variant_identifier = syntax_identifier(variant_node)
    if variant_identifier is None:
        _raise_error(
            "`variant` name must be a symbol",
            span=variant_node.span,
            form_path=form_path,
            expansion_stack=variant_node.expansion_stack,
        )
    raw_fields = datum.items[3:]
    if len(raw_fields) % 2 != 0:
        _raise_error(
            "`variant` requires keyword/value field pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    fields: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_fields), 2):
        keyword_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`variant` fields must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        fields.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
            )
        )
    return UnionVariantExpr(
        type_name=type_identifier.resolved_name,
        variant_name=variant_identifier.resolved_name,
        fields=tuple(fields),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_letstar(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> LetStarExpr:
    if len(datum.items) != 3:
        _raise_error(
            "`let*` requires a binding list and one body",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_bindings = datum.items[1]
    if not isinstance(raw_bindings, SyntaxList):
        _raise_error(
            "`let*` bindings must be a list",
            span=raw_bindings.span,
            form_path=form_path,
            expansion_stack=raw_bindings.expansion_stack,
        )
    current_names = set(bound_names)
    bindings: list[tuple[str, ExprNode]] = []
    for raw_binding in raw_bindings.items:
        if not isinstance(raw_binding, SyntaxList) or len(raw_binding.items) != 2:
            _raise_error(
                "`let*` bindings must be two-item lists of `(name expr)`",
                span=raw_binding.span,
                form_path=form_path,
                expansion_stack=raw_binding.expansion_stack,
            )
        name_node = syntax_identifier(raw_binding.items[0])
        if name_node is None:
            _raise_error(
                "`let*` binding names must be symbols",
                span=raw_binding.items[0].span,
                form_path=form_path,
                expansion_stack=raw_binding.items[0].expansion_stack,
            )
        value_expr = _elaborate(
            raw_binding.items[1],
            form_path=form_path,
            bound_names=frozenset(current_names),
            procedure_names=procedure_names,
            session_state=session_state,
        )
        bindings.append((name_node.resolved_name, value_expr))
        current_names.add(name_node.resolved_name)
    body = _elaborate(
        datum.items[2],
        form_path=form_path,
        bound_names=frozenset(current_names),
        procedure_names=procedure_names,
        session_state=session_state,
    )
    return LetStarExpr(
        bindings=tuple(bindings),
        body=body,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_match(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> MatchExpr:
    if len(datum.items) < 2:
        _raise_error("`match` requires a subject", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    subject = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )
    arms: list[MatchArm] = []
    for raw_arm in datum.items[2:]:
        if not isinstance(raw_arm, SyntaxList) or len(raw_arm.items) != 2:
            _raise_error(
                "`match` arms must be `((VARIANT binding) body)`",
                span=raw_arm.span,
                form_path=form_path,
                expansion_stack=raw_arm.expansion_stack,
            )
        pattern = raw_arm.items[0]
        if not isinstance(pattern, SyntaxList) or len(pattern.items) != 2:
            _raise_error(
                "`match` arm patterns must be `(VARIANT binding)`",
                span=pattern.span,
                form_path=form_path,
                expansion_stack=pattern.expansion_stack,
            )
        variant_node = syntax_identifier(pattern.items[0])
        binding_node = syntax_identifier(pattern.items[1])
        if variant_node is None:
            _raise_error(
                "`match` variant names must be symbols",
                span=pattern.items[0].span,
                form_path=form_path,
                expansion_stack=pattern.items[0].expansion_stack,
            )
        if binding_node is None:
            _raise_error(
                "`match` binding names must be symbols",
                span=pattern.items[1].span,
                form_path=form_path,
                expansion_stack=pattern.items[1].expansion_stack,
            )
        body = _elaborate(
            raw_arm.items[1],
            form_path=form_path,
            bound_names=frozenset(set(bound_names) | {binding_node.resolved_name}),
            procedure_names=procedure_names,
            session_state=session_state,
        )
        arms.append(
            MatchArm(
                variant_name=variant_node.resolved_name,
                binding_name=binding_node.resolved_name,
                body=body,
                span=raw_arm.span,
                form_path=form_path,
                expansion_stack=raw_arm.expansion_stack,
            )
        )
    return MatchExpr(
        subject=subject,
        arms=tuple(arms),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_if(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> IfExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`if` requires exactly a condition, then branch, and else branch",
            code="if_form_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return IfExpr(
        condition_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        then_expr=_elaborate(
            datum.items[2],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        else_expr=_elaborate(
            datum.items[3],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_cond(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> CondExpr:
    if len(datum.items) < 2:
        _raise_error(
            "`cond` requires at least one clause",
            code="cond_clause_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_clauses = datum.items[1:]

    # First pass: validate clause shape and `else` placement before elaborating
    # any child, so a non-final `else` is reported at the else clause even when
    # its own result contains invalid nested syntax.
    else_clause: SyntaxList | None = None
    for raw_clause in raw_clauses:
        if not isinstance(raw_clause, SyntaxList) or len(raw_clause.items) != 2:
            _raise_error(
                "`cond` clauses must be two-element lists of `(condition result)`",
                code="cond_clause_invalid",
                span=raw_clause.span,
                form_path=form_path,
                expansion_stack=raw_clause.expansion_stack,
            )
        head = syntax_head(raw_clause)
        is_else = head is not None and head.resolved_name == "else"
        if is_else:
            if else_clause is not None:
                _raise_error(
                    "`cond` may contain at most one `else` clause",
                    code="cond_else_invalid",
                    span=raw_clause.span,
                    form_path=form_path,
                    expansion_stack=raw_clause.expansion_stack,
                )
            else_clause = raw_clause
        elif else_clause is not None:
            _raise_error(
                "`cond` `else` must be the final clause",
                code="cond_else_invalid",
                span=else_clause.span,
                form_path=form_path,
                expansion_stack=else_clause.expansion_stack,
            )

    # Second pass: elaborate each clause's condition and result.
    clauses: list[CondClause] = []
    for raw_clause in raw_clauses:
        head = syntax_head(raw_clause)
        is_else = head is not None and head.resolved_name == "else"
        condition_expr = None
        if not is_else:
            condition_expr = _elaborate(
                raw_clause.items[0],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
        result_expr = _elaborate(
            raw_clause.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
        clauses.append(
            CondClause(
                condition_expr=condition_expr,
                result_expr=result_expr,
                is_else=is_else,
                span=raw_clause.span,
                form_path=form_path,
                expansion_stack=raw_clause.expansion_stack,
            )
        )
    return CondExpr(
        clauses=tuple(clauses),
        has_else=else_clause is not None,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_loop_recur(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> LoopRecurExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`loop/recur` requires :max, :state, and one loop-body `fn`",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    keyword_items = datum.items[1:-1]
    if len(keyword_items) < 4 or len(keyword_items) % 2 != 0:
        _raise_error(
            "`loop/recur` requires :max, :state, and one loop-body `fn`",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    sections: dict[str, object] = {}
    for index in range(0, len(keyword_items), 2):
        keyword_node = keyword_items[index]
        value_node = keyword_items[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`loop/recur` entries before the body must be keyword/value pairs",
                code="loop_recur_contract_invalid",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        if keyword_node.value in sections:
            _raise_error(
                f"`loop/recur` duplicated keyword `{keyword_node.value}`",
                code="loop_recur_contract_invalid",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        sections[keyword_node.value] = value_node
    unexpected_keywords = set(sections) - {":max", ":state", ":on-exhausted"}
    if unexpected_keywords:
        first_unexpected = min(unexpected_keywords)
        keyword_index = next(
            index
            for index in range(0, len(keyword_items), 2)
            if isinstance(keyword_items[index], SyntaxKeyword)
            and keyword_items[index].value == first_unexpected
        )
        keyword_node = keyword_items[keyword_index]
        _raise_error(
            f"`loop/recur` does not support keyword `{first_unexpected}`",
            code="loop_recur_contract_invalid",
            span=keyword_node.span,
            form_path=form_path,
            expansion_stack=keyword_node.expansion_stack,
        )
    max_node = sections.get(":max")
    state_node = sections.get(":state")
    if max_node is None or state_node is None:
        _raise_error(
            "`loop/recur` requires :max and :state",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    body_fn = _elaborate_loop_body_fn(
        datum.items[-1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )
    loop_bound_names = frozenset(set(bound_names) | {body_fn.binding_name})
    on_exhausted_node = sections.get(":on-exhausted")
    return LoopRecurExpr(
        max_iterations_expr=_elaborate(
            max_node,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        initial_state_expr=_elaborate(
            state_node,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        binding_name=body_fn.binding_name,
        body_expr=body_fn.body_expr,
        on_exhausted_result_expr=(
            _elaborate(
                on_exhausted_node,
                form_path=form_path,
                bound_names=loop_bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            if on_exhausted_node is not None
            else None
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_loop_body_fn(
    node: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> LoopBodyFnExpr:

    if not isinstance(node, SyntaxList) or len(node.items) != 3:
        _raise_error(
            "`loop/recur` body must be `(fn (state) body)`",
            code="loop_recur_fn_invalid",
            span=getattr(node, "span"),
            form_path=form_path,
            expansion_stack=getattr(node, "expansion_stack", ()),
        )
    head = syntax_identifier(node.items[0])
    binding_list = node.items[1]
    if head is None or head.resolved_name != "fn" or not isinstance(binding_list, SyntaxList) or len(binding_list.items) != 1:
        _raise_error(
            "`loop/recur` body must be `(fn (state) body)`",
            code="loop_recur_fn_invalid",
            span=node.span,
            form_path=form_path,
            expansion_stack=node.expansion_stack,
        )
    binding_node = syntax_identifier(binding_list.items[0])
    if binding_node is None:
        _raise_error(
            "`loop/recur` body binding must be one symbol",
            code="loop_recur_fn_invalid",
            span=binding_list.span,
            form_path=form_path,
            expansion_stack=binding_list.expansion_stack,
        )
    session_state.loop_body_depth += 1
    try:
        body_expr = _elaborate(
            node.items[2],
            form_path=form_path,
            bound_names=frozenset(set(bound_names) | {binding_node.resolved_name}),
            procedure_names=procedure_names,
            session_state=session_state,
        )
    finally:
        session_state.loop_body_depth -= 1
    return LoopBodyFnExpr(
        binding_name=binding_node.resolved_name,
        body_expr=body_expr,
        span=node.span,
        form_path=form_path,
        expansion_stack=node.expansion_stack,
    )


def _elaborate_continue(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ContinueExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`continue` requires exactly one state payload",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ContinueExpr(
        state_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_done(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> DoneExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`done` requires exactly one result payload",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return DoneExpr(
        result_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_call(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> CallExpr:
    if len(datum.items) < 2:
        _raise_error("`call` requires a callee name", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    callee_node = datum.items[1]
    callee_identifier = syntax_identifier(callee_node)
    if callee_identifier is None:
        _raise_error(
            "`call` callee name must be a symbol",
            span=callee_node.span,
            form_path=form_path,
            expansion_stack=callee_node.expansion_stack,
        )
    raw_bindings = datum.items[2:]
    if len(raw_bindings) % 2 != 0:
        _raise_error(
            "`call` requires keyword/value binding pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    bindings: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_bindings), 2):
        keyword_node = raw_bindings[index]
        value_node = raw_bindings[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`call` bindings must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        bindings.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
            )
        )
    return CallExpr(
        callee_name=(
            callee_identifier.resolved_name
            if callee_identifier.resolved_name in bound_names
            else callee_identifier.resolved_name
            if session_state.workflow_name_resolver is None
            else session_state.workflow_name_resolver(
                callee_identifier.resolved_name,
                callee_identifier.span,
                form_path,
            )
        ),
        bindings=tuple(bindings),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
        authored_callee_span=_direct_authored_callee_span(
            datum,
            callee_identifier,
        ),
    )


def _elaborate_function_call(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> FunctionCallExpr:
    callee_identifier = syntax_identifier(datum.items[0])
    assert callee_identifier is not None
    return FunctionCallExpr(
        callee_name=(
            session_state.function_name_resolver(
                callee_identifier.resolved_name,
                callee_identifier.span,
                form_path,
            )
            if session_state.function_name_resolver is not None
            else callee_identifier.resolved_name
        ),
        args=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            for item in datum.items[1:]
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_procedure_call(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ProcedureCallExpr:
    callee_identifier = syntax_identifier(datum.items[0])
    assert callee_identifier is not None
    callee_name = callee_identifier.resolved_name
    if callee_name not in bound_names:
        callee_name = (
            session_state.procedure_name_resolver(
                callee_name,
                callee_identifier.span,
                form_path,
            )
            if session_state.procedure_name_resolver is not None
            else callee_name
        )
    return ProcedureCallExpr(
        callee_name=callee_name,
        args=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            for item in datum.items[1:]
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
        authored_callee_span=_direct_authored_callee_span(
            datum,
            callee_identifier,
        ),
    )


def _direct_authored_callee_span(
    call_datum: SyntaxList,
    callee_datum: SyntaxIdentifier,
) -> SourceSpan | None:
    """Return exact callee provenance only for a direct authored call."""

    if (
        call_datum.expansion_stack
        or callee_datum.expansion_stack
        or callee_datum.introduced_by_expansion_id is not None
    ):
        return None
    return callee_datum.span


def _elaborate_with_phase(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> WithPhaseExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`with-phase` requires a context, phase name, and one body",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    phase_name_node = datum.items[2]
    phase_identifier = syntax_identifier(phase_name_node)
    if phase_identifier is None:
        _raise_error(
            "`with-phase` phase name must be a symbol",
            span=phase_name_node.span,
            form_path=form_path,
            expansion_stack=phase_name_node.expansion_stack,
        )
    return WithPhaseExpr(
        ctx_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        phase_name=phase_identifier.resolved_name,
        body=_elaborate(
            datum.items[3],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_with_live_providers(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> WithLiveProvidersExpr:
    if len(datum.items) != 3:
        _raise_error(
            "`with-live-providers` requires one binding list and one settlement body",
            code="with_live_providers_arity_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_bindings = datum.items[1]
    if not isinstance(raw_bindings, SyntaxList) or len(raw_bindings.items) != 2:
        _raise_error(
            "`with-live-providers` requires exactly two bindings",
            code="with_live_providers_bindings_invalid",
            span=raw_bindings.span,
            form_path=form_path,
            expansion_stack=raw_bindings.expansion_stack,
        )

    parsed: list[
        tuple[
            SyntaxList,
            SyntaxIdentifier,
            SyntaxNode | Any,
            SyntaxKeyword | None,
            SyntaxIdentifier | None,
        ]
    ] = []
    names: set[str] = set()
    for raw_binding in raw_bindings.items:
        if not isinstance(raw_binding, SyntaxList) or len(raw_binding.items) not in (2, 4):
            _raise_error(
                "live-provider bindings must be `(name expr)` or `(name expr :observes peer)`",
                code="with_live_providers_binding_invalid",
                span=raw_binding.span,
                form_path=form_path,
                expansion_stack=raw_binding.expansion_stack,
            )
        name_node = syntax_identifier(raw_binding.items[0])
        if name_node is None:
            _raise_error(
                "live-provider binding names must be symbols",
                code="with_live_providers_binding_invalid",
                span=raw_binding.items[0].span,
                form_path=form_path,
                expansion_stack=raw_binding.items[0].expansion_stack,
            )
        if name_node.resolved_name in names:
            _raise_error(
                f"duplicate live-provider binding `{name_node.display_name}`",
                code="with_live_providers_binding_duplicate",
                span=name_node.span,
                form_path=form_path,
                expansion_stack=name_node.expansion_stack,
            )
        names.add(name_node.resolved_name)

        observes_keyword: SyntaxKeyword | None = None
        observed_name: SyntaxIdentifier | None = None
        if len(raw_binding.items) == 4:
            keyword_node = raw_binding.items[2]
            observed_node = raw_binding.items[3]
            observed_name = syntax_identifier(observed_node)
            if (
                not isinstance(keyword_node, SyntaxKeyword)
                or keyword_node.value != ":observes"
                or observed_name is None
            ):
                invalid_clause_node = (
                    observed_node
                    if (
                        isinstance(keyword_node, SyntaxKeyword)
                        and keyword_node.value == ":observes"
                    )
                    else keyword_node
                )
                _raise_error(
                    "live-provider observation clauses must be `:observes peer`",
                    code="with_live_providers_binding_invalid",
                    span=invalid_clause_node.span,
                    form_path=form_path,
                    expansion_stack=invalid_clause_node.expansion_stack,
                )
            observes_keyword = keyword_node
        parsed.append(
            (
                raw_binding,
                name_node,
                raw_binding.items[1],
                observes_keyword,
                observed_name,
            )
        )

    observed = [item for item in parsed if item[3] is not None]
    if not observed:
        _raise_error(
            "`with-live-providers` requires exactly one `:observes` edge",
            code="with_live_providers_observation_missing",
            span=raw_bindings.span,
            form_path=form_path,
            expansion_stack=raw_bindings.expansion_stack,
        )
    if len(observed) != 1:
        duplicate_keyword = observed[1][3]
        assert duplicate_keyword is not None
        _raise_error(
            "`with-live-providers` permits exactly one `:observes` edge",
            code="with_live_providers_observation_duplicate",
            span=duplicate_keyword.span,
            form_path=form_path,
            expansion_stack=duplicate_keyword.expansion_stack,
        )
    observer_name = observed[0][1].resolved_name
    observed_name = observed[0][4]
    assert observed_name is not None
    if observed_name.resolved_name not in names or observed_name.resolved_name == observer_name:
        _raise_error(
            "`:observes` must name the sibling live-provider binding",
            code="with_live_providers_observed_peer_invalid",
            span=observed_name.span,
            form_path=form_path,
            expansion_stack=observed_name.expansion_stack,
        )

    bindings = tuple(
        LiveProviderBinding(
            name=name_node.resolved_name,
            value_expr=_elaborate(
                value_node,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            ),
            observes=(
                observed_name_node.resolved_name
                if observed_name_node is not None
                else None
            ),
            name_span=name_node.span,
            observes_span=(
                observes_keyword.span if observes_keyword is not None else None
            ),
            observed_name_span=(
                observed_name_node.span if observed_name_node is not None else None
            ),
            span=raw_binding.span,
            form_path=form_path,
            expansion_stack=raw_binding.expansion_stack,
        )
        for (
            raw_binding,
            name_node,
            value_node,
            observes_keyword,
            observed_name_node,
        ) in parsed
    )
    return WithLiveProvidersExpr(
        bindings=bindings,
        body=_elaborate(
            datum.items[2],
            form_path=form_path,
            bound_names=frozenset(set(bound_names) | names),
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_with_live_provider_peers(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> WithLiveProviderPeersExpr:
    if len(datum.items) != 3:
        _raise_error(
            (
                "`with-live-provider-peers` requires one binding list "
                "and one settlement body"
            ),
            code="with_live_provider_peers_arity_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_bindings = datum.items[1]
    if (
        not isinstance(raw_bindings, SyntaxList)
        or not 2
        <= len(raw_bindings.items)
        <= MAX_STATIC_LIVE_PROVIDER_PEERS
    ):
        _raise_error(
            (
                "`with-live-provider-peers` requires between two and "
                f"{MAX_STATIC_LIVE_PROVIDER_PEERS} bindings"
            ),
            code="with_live_provider_peers_bindings_invalid",
            span=raw_bindings.span,
            form_path=form_path,
            expansion_stack=raw_bindings.expansion_stack,
        )

    parsed: list[
        tuple[SyntaxList, SyntaxIdentifier, SyntaxNode | Any]
    ] = []
    names: set[str] = set()
    for raw_binding in raw_bindings.items:
        if (
            not isinstance(raw_binding, SyntaxList)
            or len(raw_binding.items) != 2
        ):
            _raise_error(
                "provider-peer bindings must be `(name expr)`",
                code="with_live_provider_peers_binding_invalid",
                span=raw_binding.span,
                form_path=form_path,
                expansion_stack=raw_binding.expansion_stack,
            )
        name_node = syntax_identifier(raw_binding.items[0])
        if name_node is None:
            _raise_error(
                "provider-peer binding names must be symbols",
                code="with_live_provider_peers_binding_invalid",
                span=raw_binding.items[0].span,
                form_path=form_path,
                expansion_stack=raw_binding.items[0].expansion_stack,
            )
        if name_node.resolved_name in names:
            _raise_error(
                f"duplicate provider-peer binding `{name_node.display_name}`",
                code="with_live_provider_peers_binding_duplicate",
                span=name_node.span,
                form_path=form_path,
                expansion_stack=name_node.expansion_stack,
            )
        names.add(name_node.resolved_name)
        parsed.append((raw_binding, name_node, raw_binding.items[1]))

    bindings = tuple(
        LiveProviderPeerBinding(
            name=name_node.resolved_name,
            value_expr=_elaborate(
                value_node,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            ),
            name_span=name_node.span,
            span=raw_binding.span,
            form_path=form_path,
            expansion_stack=raw_binding.expansion_stack,
        )
        for raw_binding, name_node, value_node in parsed
    )
    return WithLiveProviderPeersExpr(
        bindings=bindings,
        body=_elaborate(
            datum.items[2],
            form_path=form_path,
            bound_names=frozenset(set(bound_names) | names),
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_workflow_ref_literal(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    session_state: ElaborationSessionState,
) -> WorkflowRefLiteralExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`workflow-ref` requires exactly one workflow symbol",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    target_identifier = syntax_identifier(datum.items[1])
    if target_identifier is None:
        _raise_error(
            "`workflow-ref` target must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    target_name = (
        session_state.workflow_name_resolver(
            target_identifier.resolved_name,
            target_identifier.span,
            form_path,
        )
        if session_state.workflow_name_resolver is not None
        else target_identifier.resolved_name
    )
    return WorkflowRefLiteralExpr(
        target_name=target_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_proc_ref_literal(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    session_state: ElaborationSessionState,
) -> ProcRefLiteralExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`proc-ref` requires exactly one procedure symbol",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    target_identifier = syntax_identifier(datum.items[1])
    if target_identifier is None:
        _raise_error(
            "`proc-ref` target must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    authored_name = target_identifier.resolved_name
    if authored_name in session_state.local_proc_names:
        target_name = authored_name
    else:
        target_name = (
            session_state.procedure_name_resolver(
                authored_name,
                target_identifier.span,
                form_path,
            )
            if session_state.procedure_name_resolver is not None
            else authored_name
        )
    return ProcRefLiteralExpr(
        target_name=target_name,
        authored_name=authored_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_bind_proc(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> BindProcExpr:
    if len(datum.items) < 4 or len(datum.items[2:]) % 2 != 0:
        _raise_error(
            "`bind-proc` requires a proc-ref expression followed by keyword/value pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    base_expr = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )
    bindings: list[BindProcBinding] = []
    raw_bindings = datum.items[2:]
    for index in range(0, len(raw_bindings), 2):
        keyword_node = raw_bindings[index]
        value_node = raw_bindings[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`bind-proc` bindings must use keyword/value pairs",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        bindings.append(
            BindProcBinding(
                name=keyword_node.value[1:],
                value_expr=_elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
                keyword_span=keyword_node.span,
                keyword_form_path=form_path,
                keyword_expansion_stack=keyword_node.expansion_stack,
            )
        )
    return BindProcExpr(
        base_expr=base_expr,
        bindings=tuple(bindings),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_let_proc(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> LetProcExpr:

    if len(datum.items) != 3:
        _raise_error(
            "`let-proc` requires exactly one binding and one body",
            code="let_proc_syntax_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    binding_node = datum.items[1]
    if not isinstance(binding_node, SyntaxList):
        _raise_error(
            "`let-proc` binding must be a list",
            code="let_proc_syntax_invalid",
            span=binding_node.span,
            form_path=form_path,
            expansion_stack=binding_node.expansion_stack,
        )
    if binding_node.items and isinstance(binding_node.items[0], SyntaxList):
        _raise_error(
            "`let-proc` supports exactly one local binding in V1",
            code="let_proc_multiple_bindings_unsupported",
            span=binding_node.span,
            form_path=form_path,
            expansion_stack=binding_node.expansion_stack,
        )
    if len(binding_node.items) != 7:
        _raise_error(
            "`let-proc` binding must provide name, params, `->`, return type, `:captures`, and one body",
            code="let_proc_syntax_invalid",
            span=binding_node.span,
            form_path=form_path,
            expansion_stack=binding_node.expansion_stack,
        )
    name_identifier = syntax_identifier(binding_node.items[0])
    if name_identifier is None:
        _raise_error(
            "`let-proc` local name must be a symbol",
            code="let_proc_syntax_invalid",
            span=binding_node.items[0].span,
            form_path=form_path,
            expansion_stack=binding_node.items[0].expansion_stack,
        )
    if (
        name_identifier.resolved_name in bound_names
        or name_identifier.resolved_name in procedure_names
    ):
        _raise_error(
            (
                f"`let-proc` local procedure `{name_identifier.resolved_name}` collides "
                "with an existing value or procedure binding"
            ),
            code="let_proc_name_collision",
            span=binding_node.items[0].span,
            form_path=form_path,
            expansion_stack=binding_node.items[0].expansion_stack,
        )
    params_node = binding_node.items[1]
    if not isinstance(params_node, SyntaxList):
        _raise_error(
            "`let-proc` params must be a list",
            code="let_proc_syntax_invalid",
            span=params_node.span,
            form_path=form_path,
            expansion_stack=params_node.expansion_stack,
        )
    arrow_identifier = syntax_identifier(binding_node.items[2])
    if arrow_identifier is None or arrow_identifier.resolved_name != "->":
        _raise_error(
            "`let-proc` requires `->` before the return type",
            code="let_proc_syntax_invalid",
            span=binding_node.items[2].span,
            form_path=form_path,
            expansion_stack=binding_node.items[2].expansion_stack,
        )
    return_type_identifier = syntax_identifier(binding_node.items[3])
    if return_type_identifier is None:
        _raise_error(
            "`let-proc` return type must be a symbol",
            code="let_proc_syntax_invalid",
            span=binding_node.items[3].span,
            form_path=form_path,
            expansion_stack=binding_node.items[3].expansion_stack,
        )
    captures_keyword = binding_node.items[4]
    if not isinstance(captures_keyword, SyntaxKeyword) or captures_keyword.value != ":captures":
        _raise_error(
            "`let-proc` requires a `:captures` clause",
            code="let_proc_syntax_invalid",
            span=getattr(captures_keyword, "span", binding_node.span),
            form_path=form_path,
            expansion_stack=getattr(captures_keyword, "expansion_stack", datum.expansion_stack),
        )
    captures_node = binding_node.items[5]
    if not isinstance(captures_node, SyntaxList):
        _raise_error(
            "`let-proc` captures must be a list of identifiers",
            code="let_proc_syntax_invalid",
            span=captures_node.span,
            form_path=form_path,
            expansion_stack=captures_node.expansion_stack,
        )

    params = tuple(_elaborate_let_proc_param(param, form_path) for param in params_node.items)
    capture_names: list[str] = []
    seen_captures: set[str] = set()
    for capture_node in captures_node.items:
        capture_identifier = syntax_identifier(capture_node)
        if capture_identifier is None or "." in capture_identifier.resolved_name:
            _raise_error(
                "`let-proc` captures must be plain identifiers",
                code="let_proc_capture_not_identifier",
                span=capture_node.span,
                form_path=form_path,
                expansion_stack=capture_node.expansion_stack,
            )
        capture_name = capture_identifier.resolved_name
        if capture_name not in bound_names:
            _raise_error(
                f"unknown `let-proc` capture `{capture_name}`",
                code="let_proc_capture_unknown",
                span=capture_node.span,
                form_path=form_path,
                expansion_stack=capture_node.expansion_stack,
            )
        if capture_name in seen_captures:
            _raise_error(
                f"duplicate `let-proc` capture `{capture_name}`",
                code="let_proc_capture_duplicate",
                span=capture_node.span,
                form_path=form_path,
                expansion_stack=capture_node.expansion_stack,
            )
        seen_captures.add(capture_name)
        capture_names.append(capture_name)

    previous_local_proc_names = session_state.local_proc_names
    previous_let_proc_depth = session_state.let_proc_depth
    session_state.local_proc_names = session_state.local_proc_names | frozenset({name_identifier.resolved_name})
    session_state.let_proc_depth += 1
    try:
        local_body = _elaborate(
            binding_node.items[6],
            form_path=form_path,
            bound_names=frozenset(capture_names) | frozenset(param.name for param in params),
            procedure_names=procedure_names,
            session_state=session_state,
        )
        body = _elaborate(
            datum.items[2],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
    finally:
        session_state.local_proc_names = previous_local_proc_names
        session_state.let_proc_depth = previous_let_proc_depth

    return LetProcExpr(
        binding=LetProcBinding(
            local_name=name_identifier.resolved_name,
            params=params,
            return_type_name=return_type_identifier.resolved_name,
            capture_names=tuple(capture_names),
            local_body=local_body,
            span=binding_node.span,
            form_path=form_path,
            expansion_stack=binding_node.expansion_stack,
        ),
        body=body,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_let_proc_param(raw_param: object, form_path: tuple[str, ...]) -> ProcedureParam:
    if not isinstance(raw_param, SyntaxList) or len(raw_param.items) != 2:
        _raise_error(
            "`let-proc` params must be two-item lists of `(name Type)`",
            code="let_proc_syntax_invalid",
            span=getattr(raw_param, "span"),
            form_path=form_path,
            expansion_stack=getattr(raw_param, "expansion_stack", ()),
        )
    name_identifier = syntax_identifier(raw_param.items[0])
    type_identifier = syntax_identifier(raw_param.items[1])
    if name_identifier is None:
        _raise_error(
            "`let-proc` param names must be symbols",
            code="let_proc_syntax_invalid",
            span=raw_param.items[0].span,
            form_path=form_path,
            expansion_stack=raw_param.items[0].expansion_stack,
        )
    if type_identifier is None:
        _raise_error(
            "`let-proc` param types must be symbols",
            code="let_proc_syntax_invalid",
            span=raw_param.items[1].span,
            form_path=form_path,
            expansion_stack=raw_param.items[1].expansion_stack,
        )
    return ProcedureParam(
        name=name_identifier.resolved_name,
        type_name=type_identifier.resolved_name,
        span=raw_param.span,
        form_path=form_path,
        expansion_stack=raw_param.expansion_stack,
    )


def _elaborate_phase_target(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
) -> PhaseTargetExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`phase-target` requires exactly one target symbol",
            code="phase_target_name_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    target_node = datum.items[1]
    target_identifier = syntax_identifier(target_node)
    if target_identifier is None:
        _raise_error(
            "`phase-target` target name must be a symbol",
            code="phase_target_name_invalid",
            span=target_node.span,
            form_path=form_path,
            expansion_stack=target_node.expansion_stack,
        )
    return PhaseTargetExpr(
        target_name=target_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_generated_relpath_seed(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
) -> GeneratedRelpathSeedExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`__generated-relpath-seed__` requires a type name, literal path, and seed role",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    type_identifier = syntax_identifier(datum.items[1])
    if type_identifier is None:
        _raise_error(
            "`__generated-relpath-seed__` type name must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    path_node = datum.items[2]
    if not isinstance(path_node, SyntaxString):
        _raise_error(
            "`__generated-relpath-seed__` literal path must be a string",
            span=datum.items[2].span,
            form_path=form_path,
            expansion_stack=datum.items[2].expansion_stack,
        )
    seed_role_node = datum.items[3]
    if not isinstance(seed_role_node, SyntaxString):
        _raise_error(
            "`__generated-relpath-seed__` seed role must be a string",
            span=datum.items[3].span,
            form_path=form_path,
            expansion_stack=datum.items[3].expansion_stack,
        )
    return GeneratedRelpathSeedExpr(
        target_type_ref=type_identifier.resolved_name,
        literal_path=path_node.value,
        seed_role=seed_role_node.value,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_provider_result(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ProviderResultExpr:
    if len(datum.items) < 4:
        _raise_error(
            "`provider-result` requires provider and :prompt",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    provider = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`provider-result`")
    allowed_sections = {
        ":prompt",
        ":inputs",
        ":returns",
        ":model",
        ":effort",
        ":timeout-sec",
        ":delivery",
        ":materialization-attempts",
        ":prompt-dependencies",
    }
    invalid_section = next((name for name in sections if name not in allowed_sections), None)
    if invalid_section is not None:
        keyword_node = next(
            item
            for item in datum.items[2::2]
            if isinstance(item, SyntaxKeyword) and item.value == invalid_section
        )
        _raise_error(
            f"`provider-result` does not accept keyword `{invalid_section}`",
            code="provider_result_keyword_invalid",
            span=keyword_node.span,
            form_path=form_path,
            expansion_stack=keyword_node.expansion_stack,
        )
    prompt_node = sections.get(":prompt")
    inputs_node = sections.get(":inputs")
    returns_node = sections.get(":returns")
    if prompt_node is None:
        _raise_error(
            "`provider-result` requires :prompt",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    prompt_identifier = syntax_identifier(prompt_node)
    if (
        prompt_identifier is not None
        and prompt_identifier.resolved_name not in bound_names
        and session_state.prompt_catalog is not None
        and session_state.prompt_catalog.resolve(
            prompt_identifier.resolved_name
        )
        is not None
    ):
        _require_prompt_calculus_target(
            prompt_identifier,
            form_path=form_path,
            session_state=session_state,
        )
        _raise_error(
            "a prompt declaration must be fully applied in `provider-result :prompt`",
            code="prompt_partial_application_unsupported",
            span=prompt_identifier.span,
            form_path=form_path,
            expansion_stack=prompt_identifier.expansion_stack,
        )
    prompt_proc_ref_target = (
        syntax_identifier(prompt_node.items[1])
        if (
            isinstance(prompt_node, SyntaxList)
            and len(prompt_node.items) == 2
            and syntax_head(prompt_node) is not None
            and syntax_head(prompt_node).resolved_name == "proc-ref"
        )
        else None
    )
    if (
        prompt_proc_ref_target is not None
        and session_state.prompt_catalog is not None
        and session_state.prompt_catalog.resolve(
            prompt_proc_ref_target.resolved_name
        )
        is not None
    ):
        _require_prompt_calculus_target(
            prompt_proc_ref_target,
            form_path=form_path,
            session_state=session_state,
        )
        _raise_error(
            "a prompt declaration cannot be used through `proc-ref`",
            code="prompt_partial_application_unsupported",
            span=prompt_proc_ref_target.span,
            form_path=form_path,
            expansion_stack=prompt_proc_ref_target.expansion_stack,
        )
    prompt_head = (
        syntax_head(prompt_node)
        if isinstance(prompt_node, SyntaxList)
        else None
    )
    resolved_prompt = (
        session_state.prompt_catalog.resolve(prompt_head.resolved_name)
        if session_state.prompt_catalog is not None and prompt_head is not None
        else None
    )
    delivery_node = sections.get(":delivery")
    attempts_node = sections.get(":materialization-attempts")
    if delivery_node is not None or attempts_node is not None:
        if not target_dsl_supports_phased_contract_delivery(
            session_state.target_dsl_version or ""
        ):
            selected = (
                delivery_node
                if delivery_node is not None
                else attempts_node
            )
            _raise_error(
                "phased provider delivery requires target DSL 2.23",
                code="provider_phased_delivery_requires_dsl_2_23",
                span=selected.span,
                form_path=form_path,
                expansion_stack=selected.expansion_stack,
                phased_delivery_diagnostic=(
                    build_authored_phased_delivery_diagnostic(
                        "target_below_2_23",
                        canonical_value=session_state.target_dsl_version,
                        source_spans_by_owner={
                            "delivery_keyword": selected.span,
                            "provider_application": datum.span,
                        },
                    )
                ),
            )
    delivery_value: str | None = None
    if delivery_node is not None:
        if not isinstance(delivery_node, SyntaxKeyword):
            _raise_error(
                "`provider-result :delivery` must be `:composed` or `:phased`",
                code="provider_phased_delivery_policy_invalid",
                span=delivery_node.span,
                form_path=form_path,
                expansion_stack=delivery_node.expansion_stack,
                phased_delivery_diagnostic=(
                    build_authored_phased_delivery_diagnostic(
                        "delivery_type_invalid",
                        canonical_value=None,
                        source_spans_by_owner={
                            "delivery_keyword": delivery_node.span,
                            "provider_application": datum.span,
                        },
                    )
                ),
            )
        if delivery_node.value not in {":composed", ":phased"}:
            _raise_error(
                "`provider-result :delivery` must be `:composed` or `:phased`",
                code="provider_phased_delivery_policy_invalid",
                span=delivery_node.span,
                form_path=form_path,
                expansion_stack=delivery_node.expansion_stack,
                phased_delivery_diagnostic=(
                    build_authored_phased_delivery_diagnostic(
                        "delivery_enum_invalid",
                        canonical_value=None,
                        source_spans_by_owner={
                            "delivery_keyword": delivery_node.span,
                            "provider_application": datum.span,
                        },
                    )
                ),
            )
        delivery_value = delivery_node.value[1:]
    attempts_value: int | None = None
    if attempts_node is not None:
        if isinstance(attempts_node, SyntaxBool):
            _raise_error(
                "`provider-result :materialization-attempts` must be a literal integer in 1..3",
                code="provider_phased_delivery_policy_invalid",
                span=attempts_node.span,
                form_path=form_path,
                expansion_stack=attempts_node.expansion_stack,
                phased_delivery_diagnostic=(
                    build_authored_phased_delivery_diagnostic(
                        "attempts_type_invalid",
                        canonical_value=None,
                        source_spans_by_owner={
                            "materialization_attempts_keyword": attempts_node.span,
                            "provider_application": datum.span,
                        },
                    )
                ),
            )
        if not isinstance(attempts_node, SyntaxInt):
            _raise_error(
                "`provider-result :materialization-attempts` must be a literal integer in 1..3",
                code="provider_phased_delivery_policy_invalid",
                span=attempts_node.span,
                form_path=form_path,
                expansion_stack=attempts_node.expansion_stack,
                phased_delivery_diagnostic=(
                    build_authored_phased_delivery_diagnostic(
                        "attempts_literal_required",
                        canonical_value=None,
                        source_spans_by_owner={
                            "materialization_attempts_keyword": attempts_node.span,
                            "provider_application": datum.span,
                        },
                    )
                ),
            )
        if attempts_node.value not in {1, 2, 3}:
            canonical_attempts = (
                attempts_node.value
                if -(2**63) <= attempts_node.value <= 2**63 - 1
                else None
            )
            _raise_error(
                "`provider-result :materialization-attempts` must be a literal integer in 1..3",
                code="provider_phased_delivery_policy_invalid",
                span=attempts_node.span,
                form_path=form_path,
                expansion_stack=attempts_node.expansion_stack,
                phased_delivery_diagnostic=(
                    build_authored_phased_delivery_diagnostic(
                        "attempts_out_of_range",
                        canonical_value=canonical_attempts,
                        source_spans_by_owner={
                            "materialization_attempts_keyword": attempts_node.span,
                            "provider_application": datum.span,
                        },
                    )
                ),
            )
        attempts_value = attempts_node.value
    if attempts_node is not None and delivery_value != "phased":
        _raise_error(
            "`provider-result :materialization-attempts` requires explicit phased delivery",
            code="provider_phased_delivery_policy_invalid",
            span=attempts_node.span,
            form_path=form_path,
            expansion_stack=attempts_node.expansion_stack,
            phased_delivery_diagnostic=(
                build_authored_phased_delivery_diagnostic(
                    "attempts_pairing_invalid",
                    canonical_value=None,
                    source_spans_by_owner={
                        "materialization_attempts_keyword": attempts_node.span,
                        "provider_application": datum.span,
                    },
                )
            ),
        )
    if delivery_value == "phased":
        if resolved_prompt is None:
            _raise_error(
                "phased provider delivery requires a fragment-backed prompt",
                code="provider_phased_delivery_policy_invalid",
                span=delivery_node.span,
                form_path=form_path,
                expansion_stack=delivery_node.expansion_stack,
                phased_delivery_diagnostic=(
                    build_authored_phased_delivery_diagnostic(
                        "fragment_application_required",
                        canonical_value=None,
                        source_spans_by_owner={
                            "fragment_contract": prompt_node.span,
                            "provider_application": datum.span,
                        },
                    )
                ),
            )
        if attempts_value is None:
            attempts_value = 2
    prompt_application: PromptApplicationExpr | None = None
    if resolved_prompt is not None:
        _require_prompt_calculus_target(
            prompt_node,
            form_path=form_path,
            session_state=session_state,
        )
        prompt_application = elaborate_prompt_application(
            prompt_node,
            catalog=session_state.prompt_catalog,
            elaborate_fill=lambda item: _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            ),
            form_path=form_path,
            return_redeclaration_node=returns_node,
        )
        if inputs_node is not None:
            _raise_error(
                "fragment-backed provider calls cannot redeclare `:inputs`",
                code="prompt_inputs_redeclaration_forbidden",
                span=inputs_node.span,
                form_path=form_path,
                expansion_stack=inputs_node.expansion_stack,
            )
        if ":prompt-dependencies" in sections:
            dependency_node = sections[":prompt-dependencies"]
            _raise_error(
                "fragment-backed provider calls cannot redeclare `:prompt-dependencies`",
                code="prompt_dependency_redeclaration_forbidden",
                span=dependency_node.span,
                form_path=form_path,
                expansion_stack=dependency_node.expansion_stack,
            )
        return_spec = resolved_prompt.declaration.return_spec
        inputs: tuple[ExprNode, ...] = ()
    else:
        if inputs_node is None or returns_node is None:
            _raise_error(
                "`provider-result` requires :inputs and :returns for an extern prompt",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        if not isinstance(inputs_node, SyntaxList):
            _raise_error(
                "`provider-result :inputs` must be a list",
                span=inputs_node.span,
                form_path=form_path,
                expansion_stack=inputs_node.expansion_stack,
            )
        return_spec = parse_return_spec(
            returns_node,
            form_path=form_path,
            label="`provider-result :returns`",
        )
        inputs = tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            for item in inputs_node.items
        )
    return ProviderResultExpr(
        provider=provider,
        prompt=(
            prompt_application
            if prompt_application is not None
            else _elaborate(
                prompt_node,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
        ),
        inputs=inputs,
        returns_type_name=return_spec.type_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
        model=(
            _elaborate(
                sections[":model"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            if ":model" in sections
            else None
        ),
        effort=(
            _elaborate(
                sections[":effort"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            if ":effort" in sections
            else None
        ),
        timeout_sec=(
            LiteralExpr(
                value=sections[":timeout-sec"].value,
                literal_kind="float",
                span=sections[":timeout-sec"].span,
                form_path=form_path,
                expansion_stack=sections[":timeout-sec"].expansion_stack,
            )
            if isinstance(sections.get(":timeout-sec"), SyntaxFloat)
            else _elaborate(
                sections[":timeout-sec"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            if ":timeout-sec" in sections
            else None
        ),
        delivery=(
            LiteralExpr(
                value=delivery_value,
                literal_kind="string",
                span=delivery_node.span,
                form_path=form_path,
                expansion_stack=delivery_node.expansion_stack,
            )
            if delivery_node is not None
            else None
        ),
        materialization_attempts=(
            LiteralExpr(
                value=attempts_value,
                literal_kind="int",
                span=(
                    attempts_node.span
                    if attempts_node is not None
                    else delivery_node.span
                ),
                form_path=form_path,
                expansion_stack=(
                    attempts_node.expansion_stack
                    if attempts_node is not None
                    else delivery_node.expansion_stack
                ),
            )
            if attempts_value is not None
            else None
        ),
        prompt_dependencies=(
            _elaborate_prompt_dependencies(
                sections[":prompt-dependencies"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            if ":prompt-dependencies" in sections
            and prompt_application is None
            else None
        ),
        return_spec=return_spec,
    )


def _elaborate_prompt_dependencies(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> PromptDependencySpec:
    if not isinstance(datum, SyntaxList) or not datum.items:
        _raise_error(
            "`provider-result :prompt-dependencies` requires a non-empty keyword list",
            code="prompt_dependencies_clause_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if len(datum.items) % 2:
        _raise_error(
            "`provider-result :prompt-dependencies` requires keyword/value pairs",
            code="prompt_dependencies_clause_invalid",
            span=datum.items[-1].span,
            form_path=form_path,
            expansion_stack=datum.items[-1].expansion_stack,
        )

    sections: dict[str, object] = {}
    for index in range(0, len(datum.items), 2):
        keyword = datum.items[index]
        value = datum.items[index + 1]
        if not isinstance(keyword, SyntaxKeyword):
            _raise_error(
                "`provider-result :prompt-dependencies` entries must start with keywords",
                code="prompt_dependencies_clause_invalid",
                span=keyword.span,
                form_path=form_path,
                expansion_stack=keyword.expansion_stack,
            )
        if keyword.value in sections:
            _raise_error(
                f"`provider-result :prompt-dependencies` duplicated keyword `{keyword.value}`",
                code="prompt_dependencies_keyword_duplicate",
                span=keyword.span,
                form_path=form_path,
                expansion_stack=keyword.expansion_stack,
            )
        if keyword.value not in {":required", ":optional", ":position", ":instruction"}:
            _raise_error(
                f"`provider-result :prompt-dependencies` does not accept `{keyword.value}`",
                code="prompt_dependencies_keyword_invalid",
                span=keyword.span,
                form_path=form_path,
                expansion_stack=keyword.expansion_stack,
            )
        sections[keyword.value] = value

    def operands(section: str) -> tuple[ExprNode, ...]:
        value = sections.get(section)
        if value is None:
            return ()
        if not isinstance(value, SyntaxList) or not value.items:
            _raise_error(
                f"`provider-result :prompt-dependencies {section}` requires a non-empty list",
                code="prompt_dependencies_clause_invalid",
                span=value.span,
                form_path=form_path,
                expansion_stack=value.expansion_stack,
            )
        elaborated = tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            for item in value.items
        )
        generated = next(
            (item for item in elaborated if isinstance(item, GeneratedRelpathSeedExpr)),
            None,
        )
        if generated is not None:
            _raise_error(
                "compiler-generated relpath seeds are not prompt-dependency operands",
                code="prompt_dependency_generated_relpath_invalid",
                span=generated.span,
                form_path=generated.form_path,
                expansion_stack=generated.expansion_stack,
            )
        return elaborated

    required = operands(":required")
    optional = operands(":optional")
    if not required and not optional:
        _raise_error(
            "`provider-result :prompt-dependencies` requires required or optional operands",
            code="prompt_dependencies_clause_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    position = "prepend"
    position_node = sections.get(":position")
    if position_node is not None:
        identifier = syntax_identifier(position_node)
        if identifier is None or identifier.resolved_name not in {"prepend", "append"}:
            _raise_error(
                "prompt dependency position must be `prepend` or `append`",
                code="prompt_dependency_position_invalid",
                span=position_node.span,
                form_path=form_path,
                expansion_stack=position_node.expansion_stack,
            )
        position = identifier.resolved_name

    instruction = None
    instruction_node = sections.get(":instruction")
    if instruction_node is not None:
        if not isinstance(instruction_node, SyntaxString):
            _raise_error(
                "prompt dependency instruction must be a literal string",
                code="prompt_dependency_instruction_literal_required",
                span=instruction_node.span,
                form_path=form_path,
                expansion_stack=instruction_node.expansion_stack,
            )
        instruction = instruction_node.value
        if len(instruction.encode("utf-8", errors="strict")) > 261630:
            _raise_error(
                "prompt dependency instruction exceeds its UTF-8 byte limit",
                code="prompt_dependency_instruction_exceeds_byte_limit",
                span=instruction_node.span,
                form_path=form_path,
                expansion_stack=instruction_node.expansion_stack,
            )

    return PromptDependencySpec(
        required=required,
        optional=optional,
        position=position,
        instruction=instruction,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_provider_bundle_path(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ProviderBundlePathExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`provider-bundle-path` requires source and :as target type",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    source_expr = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )
    keyword = datum.items[2]
    if not isinstance(keyword, SyntaxKeyword) or keyword.value != ":as":
        _raise_error(
            "`provider-bundle-path` requires :as target type",
            span=keyword.span,
            form_path=form_path,
            expansion_stack=keyword.expansion_stack,
        )
    target_identifier = syntax_identifier(datum.items[3])
    if target_identifier is None:
        _raise_error(
            "`provider-bundle-path :as` must name a path type",
            span=datum.items[3].span,
            form_path=form_path,
            expansion_stack=datum.items[3].expansion_stack,
        )
    return ProviderBundlePathExpr(
        source_expr=source_expr,
        target_type_name=target_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_command_result(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> CommandResultExpr:
    if len(datum.items) < 5:
        _raise_error(
            "`command-result` requires a step name plus either :argv or :adapter/:inputs and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    step_name_node = datum.items[1]
    step_identifier = syntax_identifier(step_name_node)
    if step_identifier is None:
        _raise_error(
            "`command-result` step name must be a symbol",
            span=step_name_node.span,
            form_path=form_path,
            expansion_stack=step_name_node.expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`command-result`")
    argv_node = sections.get(":argv")
    adapter_node = sections.get(":adapter")
    inputs_node = sections.get(":inputs")
    returns_node = sections.get(":returns")
    uses_raw_argv = argv_node is not None
    uses_adapter = adapter_node is not None or inputs_node is not None
    if returns_node is None:
        _raise_error(
            "`command-result` requires :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return_spec = parse_return_spec(
        returns_node,
        form_path=form_path,
        label="`command-result :returns`",
    )
    if uses_raw_argv and uses_adapter:
        _raise_error(
            "`command-result` must use exactly one of :argv or :adapter/:inputs",
            code="command_result_adapter_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if uses_raw_argv:
        if not isinstance(argv_node, SyntaxList):
            _raise_error(
                "`command-result :argv` must be a list",
                span=argv_node.span,
                form_path=form_path,
                expansion_stack=argv_node.expansion_stack,
            )
        return CommandResultExpr(
            step_name=step_identifier.resolved_name,
            argv=tuple(
                _elaborate(
                    item,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                )
                for item in argv_node.items
            ),
            adapter_name=None,
            adapter_inputs=(),
            returns_type_name=return_spec.type_name,
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
            return_spec=return_spec,
        )
    if adapter_node is None or inputs_node is None:
        _raise_error(
            "`command-result` adapter mode requires both :adapter and :inputs",
            code="command_result_adapter_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    adapter_identifier = syntax_identifier(adapter_node)
    if adapter_identifier is None:
        _raise_error(
            "`command-result :adapter` must be a symbol",
            code="command_result_adapter_invalid",
            span=adapter_node.span,
            form_path=form_path,
            expansion_stack=adapter_node.expansion_stack,
        )
    if not isinstance(inputs_node, SyntaxList):
        _raise_error(
            "`command-result :inputs` must be a list of (field expr) pairs",
            code="command_result_adapter_invalid",
            span=inputs_node.span,
            form_path=form_path,
            expansion_stack=inputs_node.expansion_stack,
        )
    seen_input_names: set[str] = set()
    adapter_inputs: list[tuple[str, ExprNode]] = []
    for item in inputs_node.items:
        if not isinstance(item, SyntaxList) or len(item.items) != 2:
            _raise_error(
                "`command-result :inputs` entries must be (field expr) pairs",
                code="command_result_adapter_invalid",
                span=item.span if isinstance(item, SyntaxList) else inputs_node.span,
                form_path=form_path,
                expansion_stack=getattr(item, "expansion_stack", inputs_node.expansion_stack),
            )
        field_identifier = syntax_identifier(item.items[0])
        if field_identifier is None:
            _raise_error(
                "`command-result :inputs` field names must be symbols",
                code="command_result_adapter_invalid",
                span=item.items[0].span,
                form_path=form_path,
                expansion_stack=item.items[0].expansion_stack,
            )
        field_name = field_identifier.resolved_name
        if field_name in seen_input_names:
            _raise_error(
                f"`command-result :inputs` duplicates field `{field_name}`",
                code="command_result_adapter_invalid",
                span=item.items[0].span,
                form_path=form_path,
                expansion_stack=item.items[0].expansion_stack,
            )
        seen_input_names.add(field_name)
        adapter_inputs.append(
            (
                field_name,
                _elaborate(
                    item.items[1],
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
            )
        )
    return CommandResultExpr(
        step_name=step_identifier.resolved_name,
        argv=(),
        adapter_name=adapter_identifier.resolved_name,
        adapter_inputs=tuple(adapter_inputs),
        returns_type_name=return_spec.type_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
        return_spec=return_spec,
    )


def _elaborate_run_provider_phase(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> RunProviderPhaseExpr:
    if len(datum.items) < 7:
        _raise_error(
            "`run-provider-phase` requires a phase name plus :ctx, :inputs, :provider, :prompt, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    phase_identifier = syntax_identifier(datum.items[1])
    if phase_identifier is None:
        _raise_error(
            "`run-provider-phase` phase name must be a symbol",
            code="run_provider_phase_return_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`run-provider-phase`")
    ctx_node = sections.get(":ctx")
    inputs_node = sections.get(":inputs")
    provider_node = sections.get(":provider")
    prompt_node = sections.get(":prompt")
    returns_node = sections.get(":returns")
    if any(node is None for node in (ctx_node, inputs_node, provider_node, prompt_node, returns_node)):
        _raise_error(
            "`run-provider-phase` requires :ctx, :inputs, :provider, :prompt, and :returns",
            code="run_provider_phase_return_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    returns_identifier = syntax_identifier(returns_node)
    if returns_identifier is None:
        _raise_error(
            "`run-provider-phase :returns` must be a symbol",
            code="run_provider_phase_return_invalid",
            span=returns_node.span,
            form_path=form_path,
            expansion_stack=returns_node.expansion_stack,
        )
    return RunProviderPhaseExpr(
        phase_name=phase_identifier.resolved_name,
        ctx_expr=_elaborate(ctx_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        inputs_expr=_elaborate(inputs_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        provider=_elaborate(provider_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        prompt=_elaborate(prompt_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_produce_one_of(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ProduceOneOfExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`produce-one-of` requires a return type plus :ctx, :producer, and :candidates",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    returns_identifier = syntax_identifier(datum.items[1])
    if returns_identifier is None:
        _raise_error(
            "`produce-one-of` return type must be a symbol",
            code="produce_one_of_candidate_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of`")
    ctx_node = sections.get(":ctx")
    producer_node = sections.get(":producer")
    candidates_node = sections.get(":candidates")
    if ctx_node is None or producer_node is None or candidates_node is None:
        _raise_error(
            "`produce-one-of` requires :ctx, :producer, and :candidates",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if not isinstance(producer_node, SyntaxList):
        _raise_error(
            "`produce-one-of :producer` must be a list",
            code="produce_one_of_candidate_invalid",
            span=producer_node.span,
            form_path=form_path,
            expansion_stack=producer_node.expansion_stack,
        )
    producer = _elaborate_produce_one_of_producer(
        producer_node,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
        session_state=session_state,
    )
    if not isinstance(candidates_node, SyntaxList):
        _raise_error(
            "`produce-one-of :candidates` must be a list",
            code="produce_one_of_candidate_invalid",
            span=candidates_node.span,
            form_path=form_path,
            expansion_stack=candidates_node.expansion_stack,
        )
    return ProduceOneOfExpr(
        returns_type_name=returns_identifier.resolved_name,
        ctx_expr=_elaborate(ctx_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        producer=producer,
        candidates=tuple(
            _elaborate_produce_one_of_candidate(
                candidate_node,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            for candidate_node in candidates_node.items
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_resume_or_start(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ResumeOrStartExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`resume-or-start` requires a name plus :ctx, :resume-from, :start, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    resume_identifier = syntax_identifier(datum.items[1])
    if resume_identifier is None:
        _raise_error(
            "`resume-or-start` name must be a symbol",
            code="resume_or_start_contract_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`resume-or-start`")
    required = (":ctx", ":resume-from", ":start", ":returns")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`resume-or-start` requires :ctx, :resume-from, :start, and :returns",
            code="resume_or_start_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    valid_when_node = sections.get(":valid-when")
    valid_variants: tuple[str, ...] = ()
    if valid_when_node is not None:
        if not isinstance(valid_when_node, SyntaxList):
            _raise_error(
                "`resume-or-start :valid-when` must be a list of variants",
                code="resume_or_start_contract_invalid",
                span=valid_when_node.span,
                form_path=form_path,
                expansion_stack=valid_when_node.expansion_stack,
            )
        variants: list[str] = []
        for item in valid_when_node.items:
            variant_identifier = syntax_identifier(item)
            if variant_identifier is None:
                _raise_error(
                    "`resume-or-start :valid-when` entries must be symbols",
                    code="resume_or_start_contract_invalid",
                    span=item.span,
                    form_path=form_path,
                    expansion_stack=item.expansion_stack,
                )
            variants.append(variant_identifier.resolved_name)
        valid_variants = tuple(variants)
    returns_identifier = syntax_identifier(sections[":returns"])
    if returns_identifier is None:
        _raise_error(
            "`resume-or-start :returns` must be a symbol",
            code="resume_or_start_contract_invalid",
            span=sections[":returns"].span,
            form_path=form_path,
            expansion_stack=sections[":returns"].expansion_stack,
    )
    return ResumeOrStartExpr(
        resume_name=resume_identifier.resolved_name,
        ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        resume_from_expr=_elaborate(sections[":resume-from"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        valid_when=valid_variants,
        start_expr=_elaborate(sections[":start"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_resource_transition(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ResourceTransitionExpr:
    if len(datum.items) < 2:
        _raise_error(
            "`resource-transition` requires either the legacy queue-move shape or the declared-transition keyword shape",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    if isinstance(datum.items[1], SyntaxKeyword):
        sections = _keyword_sections(datum.items[1:], form_path=form_path, label="`resource-transition`")
        required = (":transition", ":resource", ":request")
        if any(sections.get(keyword) is None for keyword in required):
            _raise_error(
                "`resource-transition` requires :transition, :resource, and :request for declared transitions",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        transition_identifier = syntax_identifier(sections[":transition"])
        resource_identifier = syntax_identifier(sections[":resource"])
        if transition_identifier is None or resource_identifier is None:
            _raise_error(
                "`resource-transition :transition` and `:resource` must be symbols",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        return ResourceTransitionExpr(
            spec=ResourceTransitionSpec(
                mode="declared_transition",
                transition_ref_name=transition_identifier.resolved_name,
                resource_ref_name=resource_identifier.resolved_name,
                expected_version_expr=(
                    _elaborate(
                        sections[":expect-version"],
                        form_path=form_path,
                        bound_names=bound_names,
                        procedure_names=procedure_names,
                        session_state=session_state,
                    )
                    if sections.get(":expect-version") is not None
                    else None
                ),
                request_expr=_elaborate(
                    sections[":request"],
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                    session_state=session_state,
                ),
            ),
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    if len(datum.items) < 8:
        _raise_error(
            "`resource-transition` requires a transition name plus :ctx, :resource, :from, :to, :ledger, and :event",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    transition_identifier = syntax_identifier(datum.items[1])
    if transition_identifier is None:
        _raise_error(
            "`resource-transition` transition name must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`resource-transition`")
    required = (":ctx", ":resource", ":from", ":to", ":ledger", ":event")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`resource-transition` requires :ctx, :resource, :from, :to, :ledger, and :event",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    from_identifier = syntax_identifier(sections[":from"])
    to_identifier = syntax_identifier(sections[":to"])
    event_identifier = syntax_identifier(sections[":event"])
    if from_identifier is None or to_identifier is None or event_identifier is None:
        _raise_error(
            "`resource-transition` queue and event operands must be symbols",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ResourceTransitionExpr(
        spec=ResourceTransitionSpec(
            mode="legacy_queue_move",
            transition_name=transition_identifier.resolved_name,
            ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
            when_expr=(
                _elaborate(sections[":when"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state)
                if sections.get(":when") is not None
                else None
            ),
            resource_expr=_elaborate(
                sections[":resource"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            ),
            from_queue_name=from_identifier.resolved_name,
            to_queue_name=to_identifier.resolved_name,
            ledger_expr=_elaborate(sections[":ledger"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
            event_name=event_identifier.resolved_name,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_materialize_view(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> MaterializeViewExpr:
    if len(datum.items) < 2:
        _raise_error(
            "`materialize-view` requires a view name plus keyword arguments",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    view_identifier = syntax_identifier(datum.items[1])
    if view_identifier is None:
        _raise_error(
            "`materialize-view` view name must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`materialize-view`")
    required = (":value", ":renderer", ":renderer-version", ":returns")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`materialize-view` requires :value, :renderer, :renderer-version, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    renderer_identifier = syntax_identifier(sections[":renderer"])
    if renderer_identifier is None:
        _raise_error(
            "`materialize-view :renderer` must be a symbol",
            code="materialize_view_renderer_unknown",
            span=sections[":renderer"].span,
            form_path=form_path,
            expansion_stack=sections[":renderer"].expansion_stack,
        )
    renderer_version = sections[":renderer-version"]
    if not isinstance(renderer_version, SyntaxInt):
        _raise_error(
            "`materialize-view :renderer-version` must be an integer literal",
            code="materialize_view_renderer_unknown",
            span=sections[":renderer-version"].span,
            form_path=form_path,
            expansion_stack=sections[":renderer-version"].expansion_stack,
        )
    returns_identifier = syntax_identifier(sections[":returns"])
    if returns_identifier is None:
        _raise_error(
            "`materialize-view :returns` must be a symbol",
            code="materialize_view_target_contract_invalid",
            span=sections[":returns"].span,
            form_path=form_path,
            expansion_stack=sections[":returns"].expansion_stack,
        )
    return MaterializeViewExpr(
        view_name=view_identifier.resolved_name,
        value_expr=_elaborate(
            sections[":value"],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        ),
        renderer_id=renderer_identifier.resolved_name,
        renderer_version=renderer_version.value,
        target_expr=(
            _elaborate(
                sections[":target"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            )
            if sections.get(":target") is not None
            else None
        ),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_finalize_selected_item(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> FinalizeSelectedItemExpr:
    sections = _keyword_sections(datum.items[1:], form_path=form_path, label="`finalize-selected-item`")
    required = (":ctx", ":selected", ":queue-transition", ":roadmap", ":plan", ":implementation")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`finalize-selected-item` requires :ctx, :selected, :queue-transition, :roadmap, :plan, and :implementation",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return FinalizeSelectedItemExpr(
        spec=FinalizeSelectedItemSpec(
            ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
            selected_expr=_elaborate(
                sections[":selected"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            ),
            queue_transition_expr=_elaborate(
                sections[":queue-transition"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            ),
            roadmap_expr=_elaborate(sections[":roadmap"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
            plan_expr=_elaborate(sections[":plan"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
            implementation_expr=_elaborate(
                sections[":implementation"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
                session_state=session_state,
            ),
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_produce_one_of_producer(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ProduceOneOfProducerSpec:
    head = syntax_head(datum)
    if head is None or head.resolved_name != "provider" or len(datum.items) < 5:
        _raise_error(
            "`produce-one-of :producer` must be a `(provider ...)` form",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of :producer`")
    prompt_node = sections.get(":prompt")
    inputs_node = sections.get(":inputs")
    if prompt_node is None or inputs_node is None or not isinstance(inputs_node, SyntaxList):
        _raise_error(
            "`produce-one-of :producer` requires :prompt and list-valued :inputs",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfProducerSpec(
        kind="provider",
        provider_expr=_elaborate(datum.items[1], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        prompt_expr=_elaborate(prompt_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
        inputs=tuple(
            _elaborate(item, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state)
            for item in inputs_node.items
        ),
    )


def _elaborate_produce_one_of_candidate(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ProduceOneOfCandidateSpec:
    if not isinstance(datum, SyntaxList) or not datum.items:
        _raise_error(
            "`produce-one-of` candidates must be non-empty lists",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    variant_identifier = syntax_identifier(datum.items[0])
    if variant_identifier is None:
        _raise_error(
            "`produce-one-of` candidate variants must be symbols",
            code="produce_one_of_candidate_invalid",
            span=datum.items[0].span,
            form_path=form_path,
            expansion_stack=datum.items[0].expansion_stack,
        )
    fields = tuple(
        _elaborate_produce_one_of_candidate_field(
            item,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
            session_state=session_state,
        )
        for item in datum.items[1:]
    )
    if not fields:
        _raise_error(
            "`produce-one-of` candidates must describe at least one field",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfCandidateSpec(variant_name=variant_identifier.resolved_name, fields=fields)


def _elaborate_produce_one_of_candidate_field(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
    session_state: ElaborationSessionState,
) -> ProduceOneOfCandidateFieldSpec:
    if not isinstance(datum, SyntaxList) or len(datum.items) < 3:
        _raise_error(
            "`produce-one-of` candidate fields must be structured lists",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    field_identifier = syntax_identifier(datum.items[0])
    if field_identifier is None:
        _raise_error(
            "`produce-one-of` candidate field names must be symbols",
            code="produce_one_of_candidate_invalid",
            span=datum.items[0].span,
            form_path=form_path,
            expansion_stack=datum.items[0].expansion_stack,
        )
    if len(datum.items) >= 4 and isinstance(datum.items[1], SyntaxIdentifier) and isinstance(datum.items[2], SyntaxKeyword):
        source_type_identifier = syntax_identifier(datum.items[1])
        sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of` candidate field")
        source_node = sections.get(":source")
        source_identifier = syntax_identifier(source_node) if source_node is not None else None
        if source_type_identifier is None or source_identifier is None:
            _raise_error(
                "`produce-one-of` candidate source fields require a type name and `:source` symbol",
                code="produce_one_of_candidate_invalid",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        return ProduceOneOfCandidateFieldSpec(
            field_name=field_identifier.resolved_name,
            source_type_name=source_type_identifier.resolved_name,
            source_kind=source_identifier.resolved_name,
        )
    sections = _keyword_sections(datum.items[1:], form_path=form_path, label="`produce-one-of` candidate field")
    target_node = sections.get(":target")
    schema_node = sections.get(":schema")
    schema_identifier = syntax_identifier(schema_node) if schema_node is not None else None
    if target_node is None or schema_identifier is None:
        _raise_error(
            "`produce-one-of` candidate path fields require `:target` and `:schema`",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfCandidateFieldSpec(
        field_name=field_identifier.resolved_name,
        schema_type_name=schema_identifier.resolved_name,
        target_expr=_elaborate(target_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names, session_state=session_state),
    )


def _keyword_sections(
    items: list[object],
    *,
    form_path: tuple[str, ...],
    label: str,
) -> dict[str, object]:
    if len(items) % 2 != 0:
        _raise_error(
            f"{label} requires keyword/value pairs",
            span=items[-1].span,
            form_path=form_path,
            expansion_stack=items[-1].expansion_stack,
        )
    sections: dict[str, object] = {}
    for index in range(0, len(items), 2):
        keyword_node = items[index]
        value_node = items[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                f"{label} entries must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        if keyword_node.value in sections:
            _raise_error(
                f"{label} duplicated keyword `{keyword_node.value}`",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        sections[keyword_node.value] = value_node
    return sections


def _require_prompt_calculus_target(
    node: object,
    *,
    form_path: tuple[str, ...],
    session_state: ElaborationSessionState,
) -> None:
    if (
        isinstance(session_state.target_dsl_version, str)
        and target_dsl_supports_prompt_calculus(
            session_state.target_dsl_version
        )
    ):
        return
    _raise_error(
        "prompt calculus forms require target DSL 2.20 or later",
        code="prompt_calculus_requires_dsl_2_20",
        span=node.span,
        form_path=form_path,
        expansion_stack=node.expansion_stack,
    )


def _raise_error(
    message: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    code: str = "frontend_parse_error",
    expansion_stack: ExpansionStack = (),
    phased_delivery_diagnostic: PhasedDeliveryDiagnostic | None = None,
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
                phased_delivery_diagnostic=phased_delivery_diagnostic,
            ),
        )
    )
