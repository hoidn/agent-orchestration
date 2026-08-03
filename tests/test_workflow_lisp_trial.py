import pytest
from dataclasses import replace

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.definitions import (
    PathDef,
    RecordDef,
    RecordField,
    UnionDef,
    UnionVariant,
)
from orchestrator.workflow_lisp.expressions import (
    DoneExpr,
    IfExpr,
    ListExpr,
    ListMapEffectExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    ProcedureCallExpr,
    TrialExpr,
    elaborate_expression,
    parse_trial_expression,
)
from orchestrator.workflow_lisp.form_registry import get_form_spec
from orchestrator.workflow_lisp import expressions
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode, syntax_node_datum
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    UnionTypeRef,
)
from orchestrator.workflow_lisp.typecheck_dispatch import typecheck_expression
from orchestrator.workflow_lisp.typecheck_context import (
    TypecheckSessionStateCollisionError,
)
from orchestrator.workflow_lisp.effects import (
    RunsRefEffect,
    RunsTrialEffect,
    effect_summary,
    parse_effect_clause,
    render_effect_atom,
)
from orchestrator.workflow_lisp.procedure_typecheck import (
    typecheck_procedure_definitions,
)
from orchestrator.workflow_lisp.procedures import (
    ProcedureCatalog,
    ProcedureDef,
    ProcedureLoweringMode,
    ProcedureSignature,
    validate_procedure_effects,
)
from orchestrator.workflow_lisp.result_guidance import ReturnSpec
from orchestrator.workflow_lisp.workflows import (
    ExternEnvironment,
    PromptExtern,
    ProviderExtern,
    WorkflowCatalog,
    WorkflowSignature,
)
from orchestrator.workflow_lisp.trial_result_contract import (
    TRIAL_FIXED_TYPE_NAMES,
    TRIAL_RESULT_CONTRACT_SCHEMA,
    derive_trial_result_contract,
)


FORM_PATH = ("workflow-lisp", "trial-test")
COMMIT_A = "0123456789abcdef0123456789abcdef01234567"
COMMIT_B = "89abcdef0123456789abcdef0123456789abcdef"


def _expression(source: str) -> SyntaxNode:
    parsed = read_sexpr_text(source, source_path="trial_expression.orc")
    assert len(parsed.items) == 1
    datum = parsed.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="trial_expression.orc",
        form_path=FORM_PATH,
    )


def _run_ref(*, child: str, commit: str, returns: str | None = None) -> str:
    returns_clause = "" if returns is None else f" :returns {returns}"
    return (
        "(run-ref "
        f':source (:repo "file:///workspace" :commit "{commit}") '
        f":program (:bundle {child}) :inputs (){returns_clause} "
        ":policy (:setup ()))"
    )


def _trial_source(*, arm_a: str | None = None, arm_b: str | None = None) -> str:
    arm_a = arm_a or _run_ref(child="first", commit=COMMIT_A)
    arm_b = arm_b or _run_ref(child="second", commit=COMMIT_B)
    return f"""
(trial
  :arms ((:id "direct" :run-ref {arm_a})
         (:id "orc" :run-ref {arm_b}))
  :reps 3
  :max-concurrency 4
  :evaluation
  (record
    :checks (list
      (record :id "correctness"
              :command (list "python" "-m" "pytest" "-q")
              :authority "correctness"
              :required true
              :timeout-ms 600000))
    :judgment
    (record :provider "scorer"
            :rubric-asset "rubrics/trial.md"
            :evidence-confidentiality "same_trust_boundary"
            :evidence-limits
            (record :max-item-bytes 65536
                    :max-packet-bytes 262144))
    :observation
    (record :include
            (list "task_spec" "validated_result" "workspace_delta"
                  "check_results" "declared_artifacts" "failure_evidence")
            :diff-cap-bytes 262144
            :reveal-provider-identity false)
    :aggregation
    (record :mode "independent_rubric"
            :rep-combine "median"
            :tie "authored_order")
    :success-rule
    (record :superior
            (record :min-abs-improvement 0.10 :max-cost-ratio 1.5)
            :non-inferior
            (record :min-cost-reduction 0.20)
            :count-failures-as-outcomes true))
  :budget
  (record :arm-timeout-ms 900000
          :trial-timeout-ms 3600000
          :max-evaluator-attempts 6
          :max-evaluator-concurrency 2))
"""


def _replace_evaluation(source: str, replacement: str) -> str:
    start = source.index("  :evaluation\n")
    end = source.index("  :budget\n", start)
    return source[:start] + f"  :evaluation\n  {replacement}\n" + source[end:]


def _type_env(*extra_types) -> FrontendTypeEnvironment:
    refs = {
        name: PrimitiveTypeRef(name=name)
        for name in (
            "String",
            "Int",
            "Float",
            "Bool",
            "Value",
            "RunId",
            "Provider",
            "Prompt",
        )
    }
    refs.update({type_ref.name: type_ref for type_ref in extra_types})
    return FrontendTypeEnvironment(
        refs,
        target_dsl_version="2.25",
        nominal_descriptor_names_by_definition_id={
            id(type_ref.definition): type_ref.name
            for type_ref in extra_types
            if isinstance(type_ref, (RecordTypeRef, UnionTypeRef))
        },
    )


def _catalog(expr: TrialExpr, first_type, second_type=None) -> WorkflowCatalog:
    second_type = second_type or first_type
    signatures = {}
    for name, type_ref in (("first", first_type), ("second", second_type)):
        signatures[name] = WorkflowSignature(
            name=name,
            params=(),
            return_type_ref=type_ref,
            span=expr.span,
            form_path=("workflow-lisp", "defworkflow", name),
        )
    return WorkflowCatalog(
        signatures_by_name=signatures,
        definitions_by_name={},
        imported_bundles_by_name={},
    )


def _externs() -> ExternEnvironment:
    return ExternEnvironment(
        bindings_by_name={
            "scorer": ProviderExtern(name="scorer", provider_id="codex"),
            "trial-rubric": PromptExtern(
                name="trial-rubric",
                asset_file="rubrics/trial.md",
            ),
        }
    )


def _transportable_types(span):
    string_type = PrimitiveTypeRef("String")
    int_type = PrimitiveTypeRef("Int")
    record_def = RecordDef(
        name="Measurement",
        fields=(RecordField(name="label", type_name="String", span=span),),
        span=span,
    )
    record_type = RecordTypeRef(
        name="Measurement",
        definition=record_def,
        field_types={"label": string_type},
    )
    union_def = UnionDef(
        name="Outcome",
        variants=(
            UnionVariant(name="Completed", fields=(), span=span),
            UnionVariant(name="Failed", fields=(), span=span),
        ),
        span=span,
    )
    union_type = UnionTypeRef(
        name="Outcome",
        definition=union_def,
        variant_field_types={"Completed": {}, "Failed": {}},
    )
    path_type = PathTypeRef(
        name="ArtifactPath",
        definition=PathDef(
            name="ArtifactPath",
            kind="relpath",
            under="artifacts/work",
            must_exist=False,
            span=span,
        ),
    )
    return (
        PrimitiveTypeRef("Bool"),
        PrimitiveTypeRef("Status", allowed_values=("OK", "BAD")),
        record_type,
        union_type,
        OptionalTypeRef("Optional[String]", string_type),
        ListTypeRef("List[String]", string_type),
        MapTypeRef("Map[String,Int]", string_type, int_type),
        path_type,
        PrimitiveTypeRef("Value"),
    )


def test_trial_form_is_registered_only_for_target_225() -> None:
    assert get_form_spec("trial", target_dsl_version="2.24") is None
    spec = get_form_spec("trial", target_dsl_version="2.25")
    assert spec is not None
    assert spec.kind.value == "core_effect"
    assert spec.elaboration_route == "trial"


def test_trial_parser_surface_is_public() -> None:
    assert hasattr(expressions, "TrialExpr")
    assert hasattr(expressions, "parse_trial_expression")


def test_trial_target_225_parses_exact_closed_static_form() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )

    assert isinstance(expr, TrialExpr)
    assert tuple(arm.arm_id for arm in expr.arms) == ("direct", "orc")
    assert tuple(arm.run_ref.program.workflow_name for arm in expr.arms) == (
        "first",
        "second",
    )
    assert expr.reps == 3
    assert expr.max_concurrency == 4
    assert expr.evaluation.provider == "scorer"
    assert expr.evaluation.rubric_asset == "rubrics/trial.md"
    assert expr.evaluation.checks[0].command == (
        "python",
        "-m",
        "pytest",
        "-q",
    )
    assert expr.evaluation.min_abs_improvement == 0.10
    assert expr.evaluation.max_cost_ratio == 1.5
    assert expr.evaluation.min_cost_reduction == 0.20
    assert expr.budget.max_evaluator_concurrency == 2


def test_trial_rejects_target_224_with_closed_diagnostic() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_trial_expression(
            _expression(_trial_source()),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == "trial_target_dsl_unsupported"


@pytest.mark.parametrize(
    ("source", "expected_code"),
    (
        (
            _trial_source().replace(
                ":reps 3", ":reps 3 :reps 4", 1
            ),
            "trial_arms_invalid",
        ),
        (
            _trial_source().replace(
                ':id "orc"', ':id "direct"', 1
            ),
            "trial_arms_invalid",
        ),
        (_trial_source().replace(":reps 3", ":reps 0", 1), "trial_reps_invalid"),
        (
            _trial_source().replace(
                ":max-concurrency 4", ":max-concurrency 33", 1
            ),
            "trial_concurrency_invalid",
        ),
        (
            _replace_evaluation(_trial_source(), "runtime-evaluation"),
            "trial_evaluation_contract_not_pure",
        ),
        (
            _replace_evaluation(_trial_source(), '"literal-but-not-a-record"'),
            "trial_evaluation_contract_invalid",
        ),
        (
            _trial_source().replace(
                ":max-packet-bytes 262144", ":max-packet-bytes 1", 1
            ),
            "trial_packet_limit_invalid",
        ),
        (
            _trial_source().replace(
                ':authority "correctness"', ':authority "preference"', 1
            ),
            "trial_evaluation_contract_invalid",
        ),
        (
            _trial_source().replace(
                '"task_spec" "validated_result"',
                '"unknown_evidence" "validated_result"',
                1,
            ),
            "trial_packet_policy_invalid",
        ),
        (
            _trial_source().replace(
                ":max-evaluator-concurrency 2",
                ":max-evaluator-concurrency 7",
                1,
            ),
            "trial_budget_invalid",
        ),
        (
            _trial_source().replace(
                ":reveal-provider-identity false",
                ":reveal-provider-identity true",
                1,
            ),
            "trial_blinding_policy_invalid",
        ),
    ),
)
def test_trial_closed_shape_and_bounds_use_owned_refusals(
    source: str,
    expected_code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_trial_expression(
            _expression(source),
            target_dsl_version="2.25",
        )

    assert excinfo.value.diagnostics[0].code == expected_code


@pytest.mark.parametrize(
    "source",
    (
        pytest.param(
            _trial_source().replace(
                ':id "correctness"', ':id runtime-check-id', 1
            ),
            id="check-id-symbol",
        ),
        pytest.param(
            _trial_source().replace(
                ':command (list "python" "-m" "pytest" "-q")',
                ':command (list "python" (runtime-argument))',
                1,
            ),
            id="check-command-call",
        ),
        pytest.param(
            _trial_source().replace(
                ":timeout-ms 600000", ":timeout-ms runtime-timeout", 1
            ),
            id="check-timeout-symbol",
        ),
        pytest.param(
            _trial_source().replace(
                ':provider "scorer"', ':provider (runtime-provider)', 1
            ),
            id="judgment-provider-call",
        ),
        pytest.param(
            _trial_source().replace(
                ":max-item-bytes 65536",
                ":max-item-bytes (runtime-limit)",
                1,
            ),
            id="judgment-limit-call",
        ),
        pytest.param(
            _trial_source().replace(
                '(list "task_spec" "validated_result"',
                '(list runtime-include "validated_result"',
                1,
            ),
            id="observation-include-symbol",
        ),
        pytest.param(
            _trial_source().replace(
                ":diff-cap-bytes 262144",
                ":diff-cap-bytes (runtime-diff-cap)",
                1,
            ),
            id="observation-diff-cap-call",
        ),
        pytest.param(
            _trial_source().replace(
                ':mode "independent_rubric"', ':mode runtime-mode', 1
            ),
            id="aggregation-symbol",
        ),
        pytest.param(
            _trial_source().replace(
                ":min-abs-improvement 0.10",
                ":min-abs-improvement (runtime-threshold)",
                1,
            ),
            id="success-rule-call",
        ),
        pytest.param(
            _trial_source().replace(
                ":arm-timeout-ms 900000",
                ":arm-timeout-ms runtime-budget",
                1,
            ),
            id="budget-symbol",
        ),
    ),
)
def test_trial_nested_runtime_contract_values_are_not_pure(source: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_trial_expression(
            _expression(source),
            target_dsl_version="2.25",
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "trial_evaluation_contract_not_pure"
    )


def test_trial_enormous_numeric_threshold_uses_closed_diagnostic() -> None:
    threshold = replace(
        syntax_node_datum(_expression("1")),
        value=10**10000,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        expressions._trial_number(
            threshold,
            positive=False,
            label="minimum absolute improvement",
            form_path=FORM_PATH,
        )

    assert (
        excinfo.value.diagnostics[0].code
        == "trial_evaluation_contract_invalid"
    )


def test_trial_typechecks_homogeneous_arms_to_generated_result_and_effect() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )

    assert isinstance(typed.type_ref, RecordTypeRef)
    assert typed.type_ref.name.startswith("TrialResult$")
    assert expr.evaluation.provider == "scorer"
    assert isinstance(typed.expr, TrialExpr)
    assert typed.expr.evaluation.provider == "codex"
    assert typed.expr.span == expr.span
    assert typed.expr.form_path == expr.form_path
    assert {type(effect).__name__ for effect in typed.effect_summary.direct_effects} == {
        "RunsTrialEffect"
    }


def test_trial_failed_enclosing_placement_rolls_back_type_environment() -> None:
    trial = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    literal = LiteralExpr("unused", "string", trial.span, FORM_PATH)
    candidate = IfExpr(trial, literal, literal, trial.span, FORM_PATH)
    type_env = _type_env()
    type_refs_object = type_env._type_refs
    owned_names_object = type_env._compiler_owned_type_names
    original_types = dict(type_refs_object)
    original_owned_names = set(owned_names_object)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            candidate,
            type_env=type_env,
            value_env={},
            workflow_catalog=_catalog(trial, PrimitiveTypeRef("String")),
            extern_environment=_externs(),
        )

    assert excinfo.value.diagnostics[0].code == "trial_nested_unsupported"
    assert type_env._type_refs is type_refs_object
    assert type_env._compiler_owned_type_names is owned_names_object
    assert type_env._type_refs == original_types
    assert type_env._compiler_owned_type_names == original_owned_names


def test_trial_success_commits_generated_types_to_type_environment() -> None:
    trial = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    type_env = _type_env()
    original_types = dict(type_env._type_refs)
    original_owned_names = set(type_env._compiler_owned_type_names)

    typed = typecheck_expression(
        trial,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(trial, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )

    assert type_env._type_refs != original_types
    assert type_env._compiler_owned_type_names > original_owned_names
    assert typed.type_ref.name in type_env._compiler_owned_type_names
    assert type_env._type_refs[typed.type_ref.name] is typed.type_ref


def test_trial_later_failure_restores_post_success_type_environment() -> None:
    first = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    second = parse_trial_expression(
        _expression(f"\n{_trial_source()}"),
        target_dsl_version="2.25",
    )
    literal = LiteralExpr("unused", "string", second.span, FORM_PATH)
    failing_candidate = IfExpr(
        second,
        literal,
        literal,
        second.span,
        FORM_PATH,
    )
    type_env = _type_env()

    first_typed = typecheck_expression(
        first,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(first, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    post_success_types = dict(type_env._type_refs)
    post_success_owned_names = set(type_env._compiler_owned_type_names)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            failing_candidate,
            type_env=type_env,
            value_env={},
            workflow_catalog=_catalog(second, PrimitiveTypeRef("String")),
            extern_environment=_externs(),
        )

    assert excinfo.value.diagnostics[0].code == "trial_nested_unsupported"
    assert first_typed.type_ref.name in type_env._compiler_owned_type_names
    assert type_env._type_refs == post_success_types
    assert type_env._compiler_owned_type_names == post_success_owned_names


def test_trial_fixed_verdict_types_reuse_across_distinct_sites() -> None:
    first = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    second = parse_trial_expression(
        _expression(f"\n{_trial_source()}"),
        target_dsl_version="2.25",
    )
    assert first.span != second.span
    type_env = _type_env()
    catalog = _catalog(first, PrimitiveTypeRef("String"))

    first_typed = typecheck_expression(
        first,
        type_env=type_env,
        value_env={},
        workflow_catalog=catalog,
        extern_environment=_externs(),
    )
    second_typed = typecheck_expression(
        second,
        type_env=type_env,
        value_env={},
        workflow_catalog=catalog,
        extern_environment=_externs(),
    )

    assert first_typed.type_ref.name != second_typed.type_ref.name
    assert {
        "TrialRepetitionVerdict",
        "TrialAggregateScore",
    } <= set(TRIAL_FIXED_TYPE_NAMES)
    assert type_env._type_refs["TrialVerdict"].field_types[
        "per_repetition"
    ].item_type_ref.name == "TrialRepetitionVerdict"
    assert type_env._type_refs["TrialVerdict"].field_types[
        "aggregate_scores"
    ].item_type_ref.name == "TrialAggregateScore"


def test_trial_fixed_type_collision_still_fails_closed() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    type_env = _type_env()
    catalog = _catalog(expr, PrimitiveTypeRef("String"))
    typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=catalog,
        extern_environment=_externs(),
    )
    aggregate = type_env._type_refs["TrialAggregateScore"]
    type_env._type_refs["TrialAggregateScore"] = replace(
        aggregate,
        field_types={
            **aggregate.field_types,
            "failed_count": PrimitiveTypeRef("String"),
        },
    )

    with pytest.raises(
        TypecheckSessionStateCollisionError,
        match="trial compiler type collision for 'TrialAggregateScore'",
    ):
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={},
            workflow_catalog=catalog,
            extern_environment=_externs(),
        )


def test_trial_rejects_mismatched_arm_value_descriptors() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(
                expr,
                PrimitiveTypeRef("String"),
                PrimitiveTypeRef("Int"),
            ),
            extern_environment=_externs(),
        )

    assert excinfo.value.diagnostics[0].code == "trial_arm_result_mismatch"


@pytest.mark.parametrize(
    "value_index",
    range(9),
)
def test_trial_accepts_every_transportable_value_root(value_index: int) -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    value_types = _transportable_types(expr.span)
    value_type = value_types[value_index]
    type_env = _type_env(*value_types[1:4], value_types[7])
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, value_type),
        extern_environment=_externs(),
    )

    outcome = typed.type_ref.field_types["outcomes"].item_type_ref
    assert outcome.variant_field_types["Completed"]["value"] == value_type
    assert derive_trial_result_contract(
        typed.type_ref,
        type_env=type_env,
    ).type_ref is typed.type_ref


def test_trial_accepts_target_225_nested_structural_transport() -> None:
    probe = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    record_def = RecordDef(
        name="Measurement",
        fields=(
            RecordField(name="label", type_name="String", span=probe.span),
        ),
        span=probe.span,
    )
    record_type = RecordTypeRef(
        name="Measurement",
        definition=record_def,
        field_types={"label": PrimitiveTypeRef("String")},
    )
    value_type = ListTypeRef("List[Measurement]", record_type)
    typed = typecheck_expression(
        probe,
        type_env=_type_env(record_type),
        value_env={},
        workflow_catalog=_catalog(probe, value_type),
        extern_environment=_externs(),
    )

    outcome = typed.type_ref.field_types["outcomes"].item_type_ref
    assert outcome.variant_field_types["Completed"]["value"] == value_type


def test_trial_generated_contract_has_exact_union_and_load_bearing_path() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()),
        target_dsl_version="2.25",
    )
    type_env = _type_env()
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    contract = derive_trial_result_contract(typed.type_ref, type_env=type_env)

    assert contract.descriptor["schema"] == TRIAL_RESULT_CONTRACT_SCHEMA
    envelope = contract.descriptor["envelope"]
    assert [field["name"] for field in envelope["fields"]] == [
        "outcomes",
        "verdict",
        "verdict_artifact",
    ]
    outcome = typed.type_ref.field_types["outcomes"].item_type_ref
    assert tuple(outcome.variant_field_types) == ("Completed", "Failed")
    assert tuple(outcome.variant_field_types["Completed"]) == (
        "arm_id",
        "rep",
        "value",
        "evidence",
    )
    verdict_path = typed.type_ref.field_types["verdict_artifact"]
    assert isinstance(verdict_path, PathTypeRef)
    assert verdict_path.definition.under == "artifacts/trials"
    assert verdict_path.definition.must_exist is True


def test_trial_completed_evidence_descriptor_closes_check_results() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    type_env = _type_env()
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    envelope = derive_trial_result_contract(
        typed.type_ref, type_env=type_env
    ).descriptor["envelope"]
    suffix = typed.type_ref.name.removeprefix("TrialResult$")

    result_fields = {field["name"]: field["type"] for field in envelope["fields"]}
    outcome = result_fields["outcomes"]["item"]
    completed = next(
        variant for variant in outcome["variants"] if variant["name"] == "Completed"
    )
    completed_fields = {
        field["name"]: field["type"] for field in completed["fields"]
    }
    evidence = completed_fields["evidence"]
    assert evidence["name"] == f"CompletedTrialEvidence${suffix}"
    assert [field["name"] for field in evidence["fields"]] == [
        "workspace_delta",
        "accounting",
        "check_results",
        "evaluation_label",
        "packet_identity",
        "scorer_identity",
        "score",
        "child_run_id",
        "attempt_ordinal",
    ]
    evidence_fields = {
        field["name"]: field["type"] for field in evidence["fields"]
    }
    assert evidence_fields["check_results"] == {
        "kind": "list",
        "item": {
            "kind": "record",
            "name": f"TrialCheckResult${suffix}",
            "fields": [
                {
                    "name": "check_id",
                    "type": {"kind": "primitive", "name": "String"},
                },
                {
                    "name": "authority",
                    "type": {
                        "kind": "enum",
                        "name": "TrialCheckAuthority",
                        "allowed": ["correctness", "invariant"],
                    },
                },
                {
                    "name": "required",
                    "type": {"kind": "primitive", "name": "Bool"},
                },
                {
                    "name": "status",
                    "type": {
                        "kind": "enum",
                        "name": "TrialCheckStatus",
                        "allowed": ["COMPLETED", "TIMED_OUT", "LAUNCH_FAILED"],
                    },
                },
                {
                    "name": "exit_code",
                    "type": {
                        "kind": "optional",
                        "item": {"kind": "primitive", "name": "Int"},
                    },
                },
                {
                    "name": "duration_ms",
                    "type": {"kind": "primitive", "name": "Int"},
                },
                {
                    "name": "output_digest",
                    "type": {"kind": "primitive", "name": "String"},
                },
                {
                    "name": "output_bytes",
                    "type": {"kind": "primitive", "name": "String"},
                },
            ],
        },
    }


def test_trial_partial_evidence_descriptor_lists_only_present_closed_facts() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    type_env = _type_env()
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    envelope = derive_trial_result_contract(
        typed.type_ref, type_env=type_env
    ).descriptor["envelope"]
    suffix = typed.type_ref.name.removeprefix("TrialResult$")

    result_fields = {field["name"]: field["type"] for field in envelope["fields"]}
    outcome = result_fields["outcomes"]["item"]
    variants = {variant["name"]: variant for variant in outcome["variants"]}
    completed_fields = {
        field["name"]: field["type"] for field in variants["Completed"]["fields"]
    }
    completed_evidence_fields = {
        field["name"]: field["type"]
        for field in completed_fields["evidence"]["fields"]
    }
    failed_fields = {
        field["name"]: field["type"] for field in variants["Failed"]["fields"]
    }
    partial_evidence = failed_fields["evidence"]
    assert partial_evidence["name"] == f"PartialTrialEvidence${suffix}"
    assert [field["name"] for field in partial_evidence["fields"]] == ["facts"]
    facts = partial_evidence["fields"][0]["type"]
    assert facts["kind"] == "list"
    assert facts["item"] == {
        "kind": "union",
        "name": f"PartialTrialFact${suffix}",
        "variants": [
            {
                "name": "WorkspaceDelta",
                "fields": [
                    {
                        "name": "workspace_delta",
                        "type": completed_evidence_fields["workspace_delta"],
                    }
                ],
            },
            {
                "name": "RunAccounting",
                "fields": [
                    {
                        "name": "accounting",
                        "type": completed_evidence_fields["accounting"],
                    }
                ],
            },
            {
                "name": "CheckResults",
                "fields": [
                    {
                        "name": "check_results",
                        "type": completed_evidence_fields["check_results"],
                    }
                ],
            },
            {
                "name": "EvaluationLabel",
                "fields": [
                    {
                        "name": "evaluation_label",
                        "type": {"kind": "primitive", "name": "String"},
                    }
                ],
            },
            {
                "name": "PacketIdentity",
                "fields": [
                    {
                        "name": "packet_identity",
                        "type": {"kind": "primitive", "name": "String"},
                    }
                ],
            },
            {
                "name": "ScorerIdentity",
                "fields": [
                    {
                        "name": "scorer_identity",
                        "type": {"kind": "primitive", "name": "String"},
                    }
                ],
            },
            {
                "name": "Score",
                "fields": [
                    {
                        "name": "score",
                        "type": {"kind": "primitive", "name": "Float"},
                    }
                ],
            },
            {
                "name": "ChildRunId",
                "fields": [
                    {
                        "name": "child_run_id",
                        "type": {"kind": "primitive", "name": "RunId"},
                    }
                ],
            },
            {
                "name": "AttemptOrdinal",
                "fields": [
                    {
                        "name": "attempt_ordinal",
                        "type": {"kind": "primitive", "name": "Int"},
                    }
                ],
            },
        ],
    }


def test_trial_verdict_descriptor_closes_rows_usage_and_cost() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    type_env = _type_env()
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    envelope = derive_trial_result_contract(
        typed.type_ref, type_env=type_env
    ).descriptor["envelope"]
    result_fields = {field["name"]: field["type"] for field in envelope["fields"]}

    assert result_fields["verdict"] == {
        "kind": "record",
        "name": "TrialVerdict",
        "fields": [
            {
                "name": "authored_arm_order",
                "type": {
                    "kind": "list",
                    "item": {"kind": "primitive", "name": "String"},
                },
            },
            {
                "name": "per_repetition",
                "type": {
                    "kind": "list",
                    "item": {
                        "kind": "record",
                        "name": "TrialRepetitionVerdict",
                        "fields": [
                            {
                                "name": "arm_id",
                                "type": {"kind": "primitive", "name": "String"},
                            },
                            {
                                "name": "rep",
                                "type": {"kind": "primitive", "name": "Int"},
                            },
                            {
                                "name": "outcome",
                                "type": {
                                    "kind": "enum",
                                    "name": "TrialRepetitionOutcome",
                                    "allowed": ["COMPLETED", "FAILED"],
                                },
                            },
                            {
                                "name": "score",
                                "type": {
                                    "kind": "optional",
                                    "item": {
                                        "kind": "primitive",
                                        "name": "Float",
                                    },
                                },
                            },
                        ],
                    },
                },
            },
            {
                "name": "aggregate_scores",
                "type": {
                    "kind": "list",
                    "item": {
                        "kind": "record",
                        "name": "TrialAggregateScore",
                        "fields": [
                            {
                                "name": "arm_id",
                                "type": {"kind": "primitive", "name": "String"},
                            },
                            {
                                "name": "score",
                                "type": {
                                    "kind": "optional",
                                    "item": {
                                        "kind": "primitive",
                                        "name": "Float",
                                    },
                                },
                            },
                            {
                                "name": "completed_count",
                                "type": {"kind": "primitive", "name": "Int"},
                            },
                            {
                                "name": "failed_count",
                                "type": {"kind": "primitive", "name": "Int"},
                            },
                        ],
                    },
                },
            },
            {
                "name": "ranking",
                "type": {
                    "kind": "list",
                    "item": {"kind": "primitive", "name": "String"},
                },
            },
            {
                "name": "selected_arm",
                "type": {
                    "kind": "optional",
                    "item": {"kind": "primitive", "name": "String"},
                },
            },
            {
                "name": "success_rule_disposition",
                "type": {"kind": "primitive", "name": "String"},
            },
            {
                "name": "budget_accounting",
                "type": {
                    "kind": "record",
                    "name": "TrialBudgetAccounting",
                    "fields": [
                        {
                            "name": "cell_count",
                            "type": {"kind": "primitive", "name": "Int"},
                        },
                        {
                            "name": "completed_count",
                            "type": {"kind": "primitive", "name": "Int"},
                        },
                        {
                            "name": "failed_count",
                            "type": {"kind": "primitive", "name": "Int"},
                        },
                        {
                            "name": "child_attempts",
                            "type": {"kind": "primitive", "name": "Int"},
                        },
                        {
                            "name": "evaluator_attempts",
                            "type": {"kind": "primitive", "name": "Int"},
                        },
                        {
                            "name": "elapsed_ms",
                            "type": {"kind": "primitive", "name": "Int"},
                        },
                        {
                            "name": "token_usage",
                            "type": {
                                "kind": "union",
                                "name": "TrialTokenUsage",
                                "variants": [
                                    {
                                        "name": "KNOWN",
                                        "fields": [
                                            {
                                                "name": "prompt_tokens",
                                                "type": {
                                                    "kind": "primitive",
                                                    "name": "Int",
                                                },
                                            },
                                            {
                                                "name": "completion_tokens",
                                                "type": {
                                                    "kind": "primitive",
                                                    "name": "Int",
                                                },
                                            },
                                            {
                                                "name": "total_tokens",
                                                "type": {
                                                    "kind": "primitive",
                                                    "name": "Int",
                                                },
                                            },
                                        ],
                                    },
                                    {"name": "UNKNOWN", "fields": []},
                                ],
                            },
                        },
                        {
                            "name": "cost",
                            "type": {
                                "kind": "union",
                                "name": "TrialCost",
                                "variants": [
                                    {
                                        "name": "KNOWN",
                                        "fields": [
                                            {
                                                "name": "amount",
                                                "type": {
                                                    "kind": "primitive",
                                                    "name": "Float",
                                                },
                                            },
                                            {
                                                "name": "currency",
                                                "type": {
                                                    "kind": "primitive",
                                                    "name": "String",
                                                },
                                            },
                                        ],
                                    },
                                    {"name": "UNKNOWN", "fields": []},
                                ],
                            },
                        },
                    ],
                },
            },
        ],
    }


@pytest.mark.parametrize(
    ("verdict_field", "budget_field"),
    (
        ("per_repetition", None),
        ("aggregate_scores", None),
        (None, "token_usage"),
        (None, "cost"),
    ),
)
def test_trial_generated_contract_rejects_loose_value_verdict_leaves(
    verdict_field: str | None,
    budget_field: str | None,
) -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    type_env = _type_env()
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    verdict = typed.type_ref.field_types["verdict"]
    loose_value = PrimitiveTypeRef("Value")
    if verdict_field is not None:
        loose_verdict = replace(
            verdict,
            field_types={**verdict.field_types, verdict_field: loose_value},
        )
    else:
        budget = verdict.field_types["budget_accounting"]
        loose_budget = replace(
            budget,
            field_types={**budget.field_types, budget_field: loose_value},
        )
        loose_verdict = replace(
            verdict,
            field_types={**verdict.field_types, "budget_accounting": loose_budget},
        )
    tampered = replace(
        typed.type_ref,
        field_types={**typed.type_ref.field_types, "verdict": loose_verdict},
    )

    with pytest.raises(ValueError, match="generated result schema"):
        derive_trial_result_contract(tampered, type_env=type_env)


@pytest.mark.parametrize("variant_name", ("Completed", "Failed"))
def test_trial_generated_contract_rejects_loose_value_evidence(
    variant_name: str,
) -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    type_env = _type_env()
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    outcomes = typed.type_ref.field_types["outcomes"]
    outcome = outcomes.item_type_ref
    variant_fields = outcome.variant_field_types[variant_name]
    evidence = variant_fields["evidence"]
    value_type = PrimitiveTypeRef("Value")
    loose_fact_type = (
        ListTypeRef("List[Value]", value_type)
        if variant_name == "Completed"
        else MapTypeRef(
            "Map[String,Value]",
            PrimitiveTypeRef("String"),
            value_type,
        )
    )
    evidence_field = "check_results" if variant_name == "Completed" else "facts"
    loose_evidence = replace(
        evidence,
        field_types={**evidence.field_types, evidence_field: loose_fact_type},
    )
    loose_outcome = replace(
        outcome,
        variant_field_types={
            **outcome.variant_field_types,
            variant_name: {**variant_fields, "evidence": loose_evidence},
        },
    )
    tampered = replace(
        typed.type_ref,
        field_types={
            **typed.type_ref.field_types,
            "outcomes": replace(outcomes, item_type_ref=loose_outcome),
        },
    )

    with pytest.raises(ValueError, match="generated result schema"):
        derive_trial_result_contract(tampered, type_env=type_env)


def test_trial_generated_contract_rejects_tampered_verdict_path() -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    type_env = _type_env()
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    bad_path = PathTypeRef(
        name="TrialVerdictPath",
        definition=replace(
            typed.type_ref.field_types["verdict_artifact"].definition,
            under="artifacts/elsewhere",
        ),
    )
    tampered = replace(
        typed.type_ref,
        field_types={
            **typed.type_ref.field_types,
            "verdict_artifact": bad_path,
        },
    )

    with pytest.raises(ValueError, match="verdict artifact"):
        derive_trial_result_contract(tampered, type_env=type_env)


@pytest.mark.parametrize(
    ("externs", "expected_code"),
    (
        (
            ExternEnvironment(
                bindings_by_name={
                    "trial-rubric": PromptExtern(
                        name="trial-rubric", asset_file="rubrics/trial.md"
                    )
                }
            ),
            "trial_evaluation_provider_unresolved",
        ),
        (
            ExternEnvironment(
                bindings_by_name={
                    "scorer": ProviderExtern(name="scorer", provider_id="codex")
                }
            ),
            "trial_evaluation_rubric_unresolved",
        ),
    ),
)
def test_trial_resolves_provider_and_rubric_at_the_consuming_site(
    externs: ExternEnvironment,
    expected_code: str,
) -> None:
    expr = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
            extern_environment=externs,
        )

    assert excinfo.value.diagnostics[0].code == expected_code


def test_pre_225_same_named_procedure_remains_backward_compatible() -> None:
    expr = elaborate_expression(
        _expression('(trial "legacy")'),
        bound_names=frozenset(),
        procedure_names=frozenset({"trial"}),
        target_dsl_version="2.24",
    )

    assert isinstance(expr, ProcedureCallExpr)
    assert expr.callee_name == "trial"


@pytest.mark.parametrize("placement", ("if", "loop", "list-map", "pure"))
def test_trial_rejects_pure_loop_and_generated_effect_placements(
    placement: str,
) -> None:
    from orchestrator.workflow_lisp.functions import (
        FunctionDef,
        _validate_pure_function_expr,
    )

    trial = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    literal = LiteralExpr("done", "string", trial.span, FORM_PATH)
    if placement == "if":
        candidate = IfExpr(trial, literal, literal, trial.span, FORM_PATH)
    elif placement == "loop":
        candidate = LoopRecurExpr(
            LiteralExpr(1, "int", trial.span, FORM_PATH),
            LiteralExpr(0, "int", trial.span, FORM_PATH),
            "state",
            trial,
            trial.span,
            FORM_PATH,
        )
    elif placement == "list-map":
        candidate = ListMapEffectExpr(
            "item",
            ListExpr((literal,), None, trial.span, FORM_PATH),
            1,
            trial,
            None,
            None,
            trial.span,
            FORM_PATH,
        )
    else:
        function = FunctionDef(
            name="pure-helper",
            params=(),
            body=_expression('"unused"'),
            span=trial.span,
            form_path=FORM_PATH,
            return_type_name="String",
        )
        with pytest.raises(LispFrontendCompileError) as excinfo:
            _validate_pure_function_expr(trial, function_def=function)
        assert excinfo.value.diagnostics[0].code == "trial_nested_unsupported"
        return

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            candidate,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(trial, PrimitiveTypeRef("String")),
            extern_environment=_externs(),
        )
    assert excinfo.value.diagnostics[0].code == "trial_nested_unsupported"


def test_runs_trial_effect_parses_and_renders_as_a_marker() -> None:
    syntax = syntax_node_datum(_expression("((runs-trial))"))
    effects = parse_effect_clause(
        syntax,
        span=syntax.span,
        form_path=FORM_PATH,
    )

    assert effects == frozenset({RunsTrialEffect()})
    assert render_effect_atom(next(iter(effects))) == "runs-trial"


def test_trial_is_valid_in_branches_and_effectful_procedures() -> None:
    trial = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    condition = LiteralExpr(True, "bool", trial.span, FORM_PATH)
    branch = typecheck_expression(
        IfExpr(condition, trial, trial, trial.span, FORM_PATH),
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(trial, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )
    assert RunsTrialEffect() in branch.effect_summary.direct_effects

    body = LetStarExpr(
        bindings=(("trial-result", trial),),
        body=LiteralExpr("done", "string", trial.span, FORM_PATH),
        span=trial.span,
        form_path=FORM_PATH,
    )
    procedure = ProcedureDef(
        name="run-trial",
        params=(),
        declared_effects=frozenset({RunsTrialEffect()}),
        requested_lowering_mode=ProcedureLoweringMode.INLINE,
        body=body,
        span=trial.span,
        form_path=FORM_PATH,
        return_spec=ReturnSpec(type_name="String", guidance=None, span=trial.span),
    )
    signature = ProcedureSignature(
        name="run-trial",
        params=(),
        return_type_ref=PrimitiveTypeRef("String"),
        declared_effects=frozenset({RunsTrialEffect()}),
        requested_lowering_mode=ProcedureLoweringMode.INLINE,
        span=trial.span,
        form_path=FORM_PATH,
    )
    catalog = ProcedureCatalog(
        signatures_by_name={"run-trial": signature},
        definitions_by_name={"run-trial": procedure},
        call_graph={},
    )
    typed = typecheck_procedure_definitions(
        (procedure,),
        type_env=_type_env(),
        workflow_catalog=_catalog(trial, PrimitiveTypeRef("String")),
        procedure_catalog=catalog,
        extern_environment=_externs(),
        command_boundary_environment=None,
    )[0]
    validate_procedure_effects(
        procedure_def=procedure,
        declared_effects=procedure.declared_effects,
        inferred_effects=typed.direct_effect_summary.direct_effects,
    )
    assert typed.typed_body.type_ref == PrimitiveTypeRef("String")


def test_trial_effect_flows_through_reusable_calls() -> None:
    trial = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    signature = ProcedureSignature(
        name="run-trial",
        params=(),
        return_type_ref=PrimitiveTypeRef("String"),
        declared_effects=frozenset({RunsTrialEffect()}),
        requested_lowering_mode=ProcedureLoweringMode.INLINE,
        span=trial.span,
        form_path=FORM_PATH,
    )
    catalog = ProcedureCatalog(
        signatures_by_name={"run-trial": signature},
        definitions_by_name={},
        call_graph={},
    )
    typed = typecheck_expression(
        ProcedureCallExpr("run-trial", (), trial.span, FORM_PATH),
        type_env=_type_env(),
        value_env={},
        procedure_catalog=catalog,
        procedure_effects_by_name={
            "run-trial": effect_summary(
                direct_effects=(RunsTrialEffect(),)
            )
        },
    )

    assert typed.effect_summary.direct_effects == frozenset()
    assert typed.effect_summary.transitive_effects == frozenset(
        {RunsTrialEffect()}
    )


def test_trial_preserves_nested_run_ref_input_effect_after_outer_boundary() -> None:
    nested = _run_ref(child="first", commit=COMMIT_A)
    outer = (
        "(run-ref "
        f':source (:repo "file:///workspace" :commit "{COMMIT_B}") '
        ':program (:path "candidate.orc" :entry candidate) '
        f":inputs (:seed {nested}) :returns String "
        ":policy (:environment :deterministic-effect-free :setup ()))"
    )
    expr = parse_trial_expression(
        _expression(_trial_source(arm_a=outer)),
        target_dsl_version="2.25",
    )

    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )

    assert typed.effect_summary.direct_effects == frozenset(
        {
            RunsRefEffect(subject=("first",)),
            RunsTrialEffect(),
        }
    )
    assert RunsRefEffect(subject=("candidate",)) not in (
        typed.effect_summary.direct_effects
    )


def test_trial_preserves_same_subject_nested_run_ref_input_effect() -> None:
    nested = (
        "(run-ref "
        f':source (:repo "file:///workspace" :commit "{COMMIT_A}") '
        ':program (:path "nested.orc" :entry candidate) '
        ":inputs () :returns String "
        ":policy (:environment :deterministic-effect-free :setup ()))"
    )
    outer = (
        "(run-ref "
        f':source (:repo "file:///workspace" :commit "{COMMIT_B}") '
        ':program (:path "candidate.orc" :entry candidate) '
        f":inputs (:seed {nested}) :returns String "
        ":policy (:environment :deterministic-effect-free :setup ()))"
    )
    expr = parse_trial_expression(
        _expression(_trial_source(arm_a=outer)),
        target_dsl_version="2.25",
    )

    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        extern_environment=_externs(),
    )

    assert typed.effect_summary.direct_effects == frozenset(
        {
            RunsRefEffect(subject=("candidate",)),
            RunsTrialEffect(),
        }
    )


def test_trial_allows_nested_bundle_with_non_trial_reachable_graph() -> None:
    nested = _run_ref(child="first", commit=COMMIT_A)
    outer = (
        "(run-ref "
        f':source (:repo "file:///workspace" :commit "{COMMIT_B}") '
        ':program (:path "candidate.orc" :entry candidate) '
        f":inputs (:seed {nested}) :returns String "
        ":policy (:environment :deterministic-effect-free :setup ()))"
    )
    expr = parse_trial_expression(
        _expression(_trial_source(arm_a=outer)),
        target_dsl_version="2.25",
    )

    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
        workflow_effects_by_name={"first": effect_summary()},
        extern_environment=_externs(),
    )

    assert typed.effect_summary.direct_effects == frozenset(
        {
            RunsRefEffect(subject=("first",)),
            RunsTrialEffect(),
        }
    )


def test_trial_rejects_nested_bundle_with_reachable_trial_effect() -> None:
    nested = _run_ref(child="first", commit=COMMIT_A)
    outer = (
        "(run-ref "
        f':source (:repo "file:///workspace" :commit "{COMMIT_B}") '
        ':program (:path "candidate.orc" :entry candidate) '
        f":inputs (:seed {nested}) :returns String "
        ":policy (:environment :deterministic-effect-free :setup ()))"
    )
    expr = parse_trial_expression(
        _expression(_trial_source(arm_a=outer)),
        target_dsl_version="2.25",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(expr, PrimitiveTypeRef("String")),
            workflow_effects_by_name={
                "first": effect_summary(
                    direct_effects=(),
                    transitive_effects=(RunsTrialEffect(),),
                )
            },
            extern_environment=_externs(),
        )

    assert excinfo.value.diagnostics[0].code == "trial_nested_unsupported"


def test_trial_rejects_direct_and_reachable_nested_trials() -> None:
    inner = _trial_source().strip()
    nested_source = _trial_source().replace(
        ":inputs ()",
        f":inputs (:nested {inner})",
        1,
    )
    nested = parse_trial_expression(
        _expression(nested_source), target_dsl_version="2.25"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            nested,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(nested, PrimitiveTypeRef("String")),
            extern_environment=_externs(),
        )
    assert excinfo.value.diagnostics[0].code == "trial_nested_unsupported"

    direct = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            direct,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(direct, PrimitiveTypeRef("String")),
            workflow_effects_by_name={
                "first": effect_summary(
                    direct_effects=(RunsTrialEffect(),)
                )
            },
            extern_environment=_externs(),
        )
    assert excinfo.value.diagnostics[0].code == "trial_nested_unsupported"


@pytest.mark.parametrize("placement", ("pure", "loop", "generated"))
def test_transitive_trial_effect_is_rejected_from_containing_contexts(
    placement: str,
) -> None:
    from orchestrator.workflow_lisp.functions import (
        FunctionDef,
        _validate_pure_function_expr,
    )

    trial = parse_trial_expression(
        _expression(_trial_source()), target_dsl_version="2.25"
    )
    signature = ProcedureSignature(
        name="run-trial",
        params=(),
        return_type_ref=PrimitiveTypeRef("String"),
        declared_effects=frozenset({RunsTrialEffect()}),
        requested_lowering_mode=ProcedureLoweringMode.INLINE,
        span=trial.span,
        form_path=FORM_PATH,
    )
    catalog = ProcedureCatalog(
        signatures_by_name={"run-trial": signature},
        definitions_by_name={},
        call_graph={},
    )
    call = ProcedureCallExpr("run-trial", (), trial.span, FORM_PATH)
    effects = {"run-trial": effect_summary(direct_effects=(RunsTrialEffect(),))}
    if placement == "pure":
        function = FunctionDef(
            name="pure-helper",
            params=(),
            body=_expression('"unused"'),
            span=trial.span,
            form_path=FORM_PATH,
            return_type_name="String",
        )
        with pytest.raises(LispFrontendCompileError) as excinfo:
            _validate_pure_function_expr(
                call,
                function_def=function,
                procedure_catalog=catalog,
            )
    elif placement == "loop":
        candidate = LoopRecurExpr(
            LiteralExpr(1, "int", trial.span, FORM_PATH),
            LiteralExpr(0, "int", trial.span, FORM_PATH),
            "state",
            call,
            trial.span,
            FORM_PATH,
        )
        with pytest.raises(LispFrontendCompileError) as excinfo:
            typecheck_expression(
                candidate,
                type_env=_type_env(),
                value_env={},
                procedure_catalog=catalog,
                procedure_effects_by_name=effects,
            )
    else:
        literal = LiteralExpr("item", "string", trial.span, FORM_PATH)
        candidate = ListMapEffectExpr(
            "item",
            ListExpr((literal,), None, trial.span, FORM_PATH),
            1,
            call,
            None,
            None,
            trial.span,
            FORM_PATH,
        )
        with pytest.raises(LispFrontendCompileError) as excinfo:
            typecheck_expression(
                candidate,
                type_env=_type_env(),
                value_env={},
                procedure_catalog=catalog,
                procedure_effects_by_name=effects,
            )
    assert excinfo.value.diagnostics[0].code == "trial_nested_unsupported"


def test_full_compiler_types_trial_in_exported_workflow_before_lowering(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import compiler as workflow_lisp_compiler

    source_path = tmp_path / "trial_frontend.orc"
    source_path.write_text(
        f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule trial_frontend)
  (export compare first second)
  (defworkflow first () -> String
    "first")
  (defworkflow second () -> String
    "second")
  (defworkflow compare () -> Value
    {_trial_source().strip()}))
""",
        encoding="utf-8",
    )

    class TypedFrontendReached(Exception):
        pass

    def capture_typed_frontend(**kwargs):
        typed_entry = next(
            workflow
            for workflow in kwargs["typed_workflows"]
            if workflow.definition.name == "compare"
        )
        assert isinstance(typed_entry.typed_body.expr, TrialExpr)
        assert isinstance(typed_entry.typed_body.type_ref, RecordTypeRef)
        assert typed_entry.typed_body.type_ref.name.startswith("TrialResult$")
        assert typed_entry.signature.return_type_ref == typed_entry.typed_body.type_ref
        assert (
            kwargs["workflow_catalog"]
            .signatures_by_name["compare"]
            .return_type_ref
            == typed_entry.typed_body.type_ref
        )
        assert RunsTrialEffect() in typed_entry.effect_summary.direct_effects
        raise TypedFrontendReached

    monkeypatch.setattr(
        workflow_lisp_compiler,
        "_lower_workflows_for_route",
        capture_typed_frontend,
    )
    with pytest.raises(TypedFrontendReached):
        workflow_lisp_compiler.compile_stage3_module(
            source_path,
            entry_workflow="compare",
            provider_externs={"scorer": "test-provider"},
            prompt_externs={"trial-rubric": "rubrics/trial.md"},
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="legacy",
        )


@pytest.mark.parametrize("target_dsl_version", ("2.24", "2.25"))
def test_full_compiler_keeps_non_trial_value_return_signature(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    target_dsl_version: str,
) -> None:
    from orchestrator.workflow_lisp import compiler as workflow_lisp_compiler

    source_path = tmp_path / "value_frontend.orc"
    source_path.write_text(
        f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target_dsl_version}")
  (defmodule value_frontend)
  (export passthrough)
  (defworkflow passthrough ((payload Value)) -> Value
    payload))
""",
        encoding="utf-8",
    )

    class TypedFrontendReached(Exception):
        pass

    def capture_typed_frontend(**kwargs):
        typed_entry = next(
            workflow
            for workflow in kwargs["typed_workflows"]
            if workflow.definition.name == "passthrough"
        )
        assert typed_entry.signature.return_type_ref == PrimitiveTypeRef("Value")
        assert (
            kwargs["workflow_catalog"]
            .signatures_by_name["passthrough"]
            .return_type_ref
            == PrimitiveTypeRef("Value")
        )
        raise TypedFrontendReached

    monkeypatch.setattr(
        workflow_lisp_compiler,
        "_lower_workflows_for_route",
        capture_typed_frontend,
    )
    with pytest.raises(TypedFrontendReached):
        workflow_lisp_compiler.compile_stage3_module(
            source_path,
            entry_workflow="passthrough",
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="legacy",
        )
