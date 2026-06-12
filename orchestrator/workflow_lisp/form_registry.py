"""Frontend-owned inventory of compiler-known Workflow Lisp heads."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from orchestrator.workflow.pure_expr import PURE_EXPR_OPERATOR_CATALOG


class FormKind(Enum):
    """Classification for compiler-known authored heads."""

    TOP_LEVEL_DEFINITION = "top_level_definition"
    CORE_SPECIAL = "core_special"
    CORE_EFFECT = "core_effect"
    STDLIB_EXTENSION = "stdlib_extension"
    TEMP_COMPILER_INTRINSIC = "temp_compiler_intrinsic"


@dataclass(frozen=True)
class FormSpec:
    """One compiler-known form with ownership and routing metadata."""

    name: str
    kind: FormKind
    owner_module: str
    introduced_in: str
    remove_by: str | None
    macro_bindable: bool
    admitted_top_level: bool
    elaboration_route: str | None
    feature_tags: frozenset[str]
    rationale: str


def _spec(
    name: str,
    *,
    kind: FormKind,
    owner_module: str,
    introduced_in: str,
    remove_by: str | None,
    macro_bindable: bool,
    admitted_top_level: bool,
    elaboration_route: str | None,
    feature_tags: tuple[str, ...] = (),
    rationale: str,
) -> FormSpec:
    return FormSpec(
        name=name,
        kind=kind,
        owner_module=owner_module,
        introduced_in=introduced_in,
        remove_by=remove_by,
        macro_bindable=macro_bindable,
        admitted_top_level=admitted_top_level,
        elaboration_route=elaboration_route,
        feature_tags=frozenset(feature_tags),
        rationale=rationale,
    )


_FORM_SPECS = (
    _spec(
        "workflow-lisp",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="syntax",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route=None,
        rationale="Module header stays reserved and never elaborates as an expression.",
    ),
    _spec(
        "defenum",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="definitions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Enum definitions are admitted only at top level.",
    ),
    _spec(
        "defpath",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="definitions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Path definitions are admitted only at top level.",
    ),
    _spec(
        "defschema",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="definitions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Schema definitions are admitted only at top level.",
    ),
    _spec(
        "defrecord",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="definitions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Record definitions are admitted only at top level.",
    ),
    _spec(
        "defunion",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="definitions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Union definitions are admitted only at top level.",
    ),
    _spec(
        "defresource",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="definitions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Resource declarations are admitted only at top level.",
    ),
    _spec(
        "deftransition",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="definitions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Transition declarations are admitted only at top level.",
    ),
    _spec(
        "defworkflow",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="workflows",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Workflow definitions are admitted only at top level.",
    ),
    _spec(
        "defun",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="functions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Helper functions remain top-level-only compiler definitions.",
    ),
    _spec(
        "defproc",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="procedures",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=True,
        elaboration_route=None,
        rationale="Procedure definitions remain top-level-only compiler definitions.",
    ),
    _spec(
        "defmodule",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="modules",
        introduced_in="workflow_lisp_frontend_future_surface",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route=None,
        rationale="Module declarations stay reserved while the authored module surface is partial.",
    ),
    _spec(
        "import",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="modules",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route=None,
        rationale="Import forms remain compiler-owned top-level entries.",
    ),
    _spec(
        "export",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="modules",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route=None,
        rationale="Export forms remain compiler-owned top-level entries.",
    ),
    _spec(
        "defmacro",
        kind=FormKind.TOP_LEVEL_DEFINITION,
        owner_module="macros",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route=None,
        rationale="Macro definitions remain reserved compiler-owned top-level entries.",
    ),
    _spec(
        "record",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="record",
        rationale="Record construction elaborates through the core expression elaborator.",
    ),
    *(
        _spec(
            operator_name,
            kind=FormKind.CORE_SPECIAL,
            owner_module="expressions",
            introduced_in="workflow_lisp_generic_core_expression_surface",
            remove_by=None,
            macro_bindable=False,
            admitted_top_level=False,
            elaboration_route="record_update" if operator_name == "record-update" else "pure_op",
            feature_tags=("pure_expression_core",),
            rationale=(
                "Closed pure operator heads elaborate through the shared pure-expression route."
            ),
        )
        for operator_name in PURE_EXPR_OPERATOR_CATALOG
    ),
    _spec(
        "loop-state",
        kind=FormKind.CORE_SPECIAL,
        owner_module="loop_state",
        introduced_in="workflow_lisp_frontend_parametric_loop_state",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="loop_state",
        rationale="Loop-frame carrier authoring elaborates through the dedicated loop-state route.",
    ),
    _spec(
        "variant",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="variant",
        rationale="Variant construction remains macro-bindable while elaborating through the core expression path.",
    ),
    _spec(
        "let*",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="let_star",
        rationale="Sequential lexical bindings elaborate through the core expression path.",
    ),
    _spec(
        "if",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="if",
        rationale="Conditionals remain macro-bindable while elaborating through the core expression path.",
    ),
    _spec(
        "match",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="match",
        rationale="Variant-proof matching elaborates through the core expression path.",
    ),
    _spec(
        "loop/recur",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="loop_recur",
        rationale="Loop/recur stays macro-bindable while elaborating through the guarded expression path.",
    ),
    _spec(
        "fn",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="loop_fn_guard",
        rationale="Loop body functions stay macro-bindable but preserve the loop-only guard.",
    ),
    _spec(
        "continue",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="continue_guard",
        rationale="Loop continue stays macro-bindable but preserves the loop-only guard.",
    ),
    _spec(
        "done",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="done_guard",
        rationale="Loop termination stays macro-bindable but preserves the loop-only guard.",
    ),
    _spec(
        "call",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="call",
        rationale="Workflow calls elaborate through the core expression path.",
    ),
    _spec(
        "workflow-ref",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="workflow_ref",
        rationale="Workflow refs stay macro-bindable while elaborating through the core expression path.",
    ),
    _spec(
        "proc-ref",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_proc_refs_partial_application",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="proc_ref",
        rationale="Proc refs stay macro-bindable while elaborating through the core expression path.",
    ),
    _spec(
        "bind-proc",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_proc_refs_partial_application",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="bind_proc",
        rationale="Partial application stays macro-bindable while elaborating through the core expression path.",
    ),
    _spec(
        "let-proc",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_let_proc_local_proc_refs",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route="let_proc_guard",
        rationale="Local ProcRef bindings stay macro-bindable while preserving the V1 nesting guard.",
    ),
    _spec(
        "provider-result",
        kind=FormKind.CORE_EFFECT,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="provider_result",
        rationale="Provider effects elaborate through a fixed compiler path.",
    ),
    _spec(
        "provider-bundle-path",
        kind=FormKind.CORE_SPECIAL,
        owner_module="expressions",
        introduced_in="workflow_lisp_post_foundation_typed_projection",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="provider_bundle_path",
        rationale="Provider bundle-path projection stays a narrow compiler-owned expression surface.",
    ),
    _spec(
        "command-result",
        kind=FormKind.CORE_EFFECT,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="command_result",
        rationale="Command effects elaborate through a fixed compiler path.",
    ),
    _spec(
        "review-revise-loop",
        kind=FormKind.STDLIB_EXTENSION,
        owner_module="stdlib_modules/std/phase.orc",
        introduced_in="workflow_lisp_review_revise_stdlib_parametric_integration",
        remove_by=None,
        macro_bindable=True,
        admitted_top_level=False,
        elaboration_route=None,
        feature_tags=("review_loop_public_surface",),
        rationale="The public stdlib review loop stays macro-bindable and must reach the compiler via imported stdlib expansion.",
    ),
    _spec(
        "with-phase",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by="ordinary stdlib/runtime phase composition",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="with_phase",
        rationale="Phase scoping remains a temporary compiler intrinsic pending broader composition work.",
    ),
    _spec(
        "phase-target",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by="ordinary stdlib/runtime phase composition",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="phase_target",
        rationale="Phase target lookup remains a temporary compiler intrinsic pending broader composition work.",
    ),
    _spec(
        "__generated-relpath-seed__",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_review_revise_stdlib_parametric_integration",
        remove_by="ordinary imported stdlib seed ownership",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="generated_relpath_seed",
        rationale="Compiler-private relpath seeds remain hidden while ordinary stdlib code still needs typed placeholder paths.",
    ),
    _spec(
        "run-provider-phase",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_mvp",
        remove_by="ordinary imported stdlib expansion",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="run_provider_phase",
        rationale="Provider phase lowering remains a temporary compiler intrinsic pending ordinary stdlib ownership.",
    ),
    _spec(
        "produce-one-of",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by="ordinary imported stdlib expansion",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="produce_one_of",
        rationale="Candidate production remains a temporary compiler intrinsic pending ordinary stdlib ownership.",
    ),
    _spec(
        "provider",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by="ordinary imported stdlib expansion",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route=None,
        feature_tags=("nested_producer_only",),
        rationale="The producer helper stays reserved for nested stdlib producer sections rather than general expression elaboration.",
    ),
    _spec(
        "resume-or-start",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by="ordinary imported stdlib expansion",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="resume_or_start",
        rationale="Resume/state-reuse remains a temporary compiler intrinsic pending ordinary stdlib ownership.",
    ),
    _spec(
        "resource-transition",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by="runtime-native resource transitions",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="resource_transition",
        rationale="Resource transitions stay compiler-owned until the runtime-native surface is promoted.",
    ),
    _spec(
        "finalize-selected-item",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by="ordinary imported stdlib expansion",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="finalize_selected_item",
        rationale="Selection finalization remains compiler-owned pending ordinary stdlib ownership.",
    ),
    _spec(
        "backlog-drain",
        kind=FormKind.TEMP_COMPILER_INTRINSIC,
        owner_module="expressions",
        introduced_in="workflow_lisp_frontend_refactor",
        remove_by="ordinary imported stdlib expansion",
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="backlog_drain",
        rationale="Backlog drain remains compiler-owned pending ordinary stdlib ownership.",
    ),
)


def _requires_elaboration_route(spec: FormSpec) -> bool:
    if spec.kind in {FormKind.TOP_LEVEL_DEFINITION, FormKind.STDLIB_EXTENSION}:
        return False
    if "nested_producer_only" in spec.feature_tags:
        return False
    return True


def _validate_form_specs(specs: tuple[FormSpec, ...]) -> None:
    seen: set[str] = set()
    for spec in specs:
        if spec.name in seen:
            raise ValueError(f"duplicate form registry entry for `{spec.name}`")
        seen.add(spec.name)
        if spec.admitted_top_level and spec.kind is not FormKind.TOP_LEVEL_DEFINITION:
            raise ValueError(
                f"non-definition form `{spec.name}` cannot be admitted at top level"
            )
        if _requires_elaboration_route(spec) and not spec.elaboration_route:
            raise ValueError(f"form `{spec.name}` requires an elaboration route")
    review_loop = next(spec for spec in specs if spec.name == "review-revise-loop")
    if not review_loop.macro_bindable:
        raise ValueError("`review-revise-loop` must remain macro-bindable")


def _build_registry(specs: tuple[FormSpec, ...]) -> dict[str, FormSpec]:
    _validate_form_specs(specs)
    return {spec.name: spec for spec in specs}


_FORM_REGISTRY = _build_registry(_FORM_SPECS)
_RESERVED_MACRO_NAMES = frozenset(
    spec.name for spec in _FORM_REGISTRY.values() if not spec.macro_bindable
)
_ADMITTED_TOP_LEVEL_HEADS = frozenset(
    spec.name for spec in _FORM_REGISTRY.values() if spec.admitted_top_level
)


def get_form_spec(name: str) -> FormSpec | None:
    """Return one compiler-known form spec by authored head name."""

    return _FORM_REGISTRY.get(name)


def reserved_macro_names() -> frozenset[str]:
    """Return the exact set of macro-reserved authored heads."""

    return _RESERVED_MACRO_NAMES


def admitted_top_level_heads() -> frozenset[str]:
    """Return the exact set of compiler-admitted top-level definition heads."""

    return _ADMITTED_TOP_LEVEL_HEADS


def head_has_feature_tag(name: str, tag: str) -> bool:
    """Return whether one compiler-known head advertises a feature tag."""

    spec = get_form_spec(name)
    return spec is not None and tag in spec.feature_tags
