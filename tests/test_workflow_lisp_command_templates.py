"""Materialization decisions retain the independent legacy command oracle."""

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.expressions import FieldAccessExpr, IfExpr, LiteralExpr, NameExpr
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


SPAN = SourceSpan(
    start=SourcePosition(path="transport.orc", line=1, column=1, offset=0),
    end=SourcePosition(path="transport.orc", line=1, column=2, offset=1),
)


def _literal(value):
    return LiteralExpr(value=value, literal_kind="bool", span=SPAN, form_path=())


def _selection():
    return IfExpr(
        condition_expr=_literal(True), then_expr=_literal(True),
        else_expr=_literal(False), span=SPAN, form_path=(),
    )


@pytest.mark.parametrize(
    "expansion,existing,run_ref,provider,request_input,expected",
    [
        (False, None, False, False, False, "if_projection"),
        (False, None, True, False, False, "if_projection"),
        (False, None, False, True, True, "whole_value"),
        (False, None, False, False, True, "alias"),
        (False, None, True, False, True, "request_projection"),
        (True, None, True, True, True, "expansion_projection"),
    ],
)
def test_wcc_materialization_precedence(expansion, existing, run_ref, provider, request_input, expected):
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import (
        wcc_binding_materialization,
    )

    expr = _selection()
    kind, value = wcc_binding_materialization(
        expr, expansion_owned=expansion, existing_ref=existing,
        resolved_binding=expr.then_expr, run_ref_demand=run_ref,
        provider_context_demand=provider, request_input_demand=request_input,
    )
    assert kind == expected
    assert value is (expr if expansion or run_ref or provider else expr.then_expr)


@pytest.mark.parametrize("existing,expected", [
    ("inputs.actual", "alias"), (_literal(True), "expansion_projection"),
    ({"field": "inputs.actual"}, "expansion_projection"), (None, "expansion_projection"),
])
def test_expansion_alias_requires_an_existing_direct_reference(existing, expected):
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import (
        wcc_binding_materialization,
    )

    expr = NameExpr(name="actual", span=SPAN, form_path=())
    kind, value = wcc_binding_materialization(
        expr, expansion_owned=True, existing_ref=existing, resolved_binding=None,
        run_ref_demand=True, provider_context_demand=True, request_input_demand=True,
    )
    assert kind == expected
    assert value is (existing if expected == "alias" else expr)


@pytest.mark.parametrize("literal", [True, False])
def test_legacy_command_binding_emission_retains_literal_and_runtime_bool(tmp_path: Path, literal):
    source = tmp_path / "entry.orc"
    bool_text = "true" if literal else "false"
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.34") '
        '(defrecord Result (seen String)) '
        '(defworkflow run ((n Int :default 7)) -> Result '
        '(command-result echo :argv ("python" "probe.py" '
        f'{bool_text} (let* ((x {bool_text})) x) '
        f'(if true {bool_text} {bool_text}) '
        '(let* ((s "${inputs.n}")) s)) :returns Result)))'
    )
    result = compile_stage3_module(
        source, entry_workflow="run", workspace_root=tmp_path,
        command_boundaries={"echo": ExternalToolBinding(name="echo", stable_command=("python", "probe.py"))},
        validate_shared=False,
    )
    steps = result.lowered_workflows[0].authored_mapping["steps"]
    assert len(steps) == 2
    assert "pure_projection" in steps[0]
    assert steps[1]["command"] == [
        "python", "probe.py", str(literal), str(literal),
        "${root.steps.run____wcc_anf_ecf7564cf1.artifacts.__result__}", "${inputs.n}",
    ]


def test_surface_binding_inline_and_projection_are_distinct_owners():
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import (
        is_inline_let_binding_expr, surface_binding_materialization,
    )

    literal = _literal(True)
    selection = _selection()
    assert is_inline_let_binding_expr(literal)
    assert not is_inline_let_binding_expr(selection)
    assert surface_binding_materialization(selection, resolved_binding=literal) == ("projection", literal)


@pytest.mark.parametrize("second_consumer", [False, True])
def test_request_input_second_consumer_changes_the_command_binding(tmp_path: Path, second_consumer):
    # Frozen from the independent pre-extraction legacy owner, not the helper.
    source = tmp_path / "entry.orc"
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.34") '
        '(defrecord Result (seen String)) '
        '(defworkflow run () -> ' + ('HumanReply' if second_consumer else 'String') +
        ' (let* ((question (if true "chosen" "other")) '
        '(seen (command-result echo :argv ("python" "probe.py" question) :returns Result))) '
        + ('(request-input question)' if second_consumer else 'question') + ')))'
    )
    result = compile_stage3_module(
        source, entry_workflow="run", workspace_root=tmp_path,
        command_boundaries={"echo": ExternalToolBinding(name="echo", stable_command=("python", "probe.py"))},
        validate_shared=False,
    )
    steps = result.lowered_workflows[0].authored_mapping["steps"]
    assert len(steps) == 2
    command = next(step["command"] for step in steps if "command" in step)
    assert command == ["python", "probe.py", (
        "chosen" if second_consumer else "${root.steps.run__question.artifacts.__result__}"
    )]
    if second_consumer:
        assert steps[1]["request_input"] == {"question": {"literal": "chosen"}}
    else:
        assert steps[0]["pure_projection"]["payload"]["expr"]["value"] == "chosen"


@pytest.mark.parametrize("resolved,run_ref,expected", [
    ("inputs.record.field", False, "alias"),
    ({"leaf": "inputs.record.field"}, False, "whole_value"),
    ("inputs.record.field", True, "alias"),
])
def test_provider_context_field_availability_precedes_request_projection(resolved, run_ref, expected):
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import (
        wcc_binding_materialization,
    )

    expr = FieldAccessExpr(
        base=NameExpr(name="record", span=SPAN, form_path=()),
        fields=("field",), span=SPAN, form_path=(),
    )
    kind, value = wcc_binding_materialization(
        expr, expansion_owned=False, existing_ref=None, resolved_binding=resolved,
        run_ref_demand=run_ref, provider_context_demand=True,
        request_input_demand=False,
    )
    assert kind == expected
    assert value is (expr if run_ref or expected == "whole_value" else resolved)


def test_run_ref_resolver_override_alone_does_not_emit_a_projection():
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import (
        wcc_binding_materialization,
    )

    expr = NameExpr(name="value", span=SPAN, form_path=())
    assert wcc_binding_materialization(
        expr, expansion_owned=False, existing_ref=None, resolved_binding=_literal(True),
        run_ref_demand=True, provider_context_demand=False, request_input_demand=False,
    ) == ("alias", expr)


@pytest.mark.parametrize("available_root", [False, True])
def test_provider_field_fact_selects_real_whole_value_emission(tmp_path: Path, monkeypatch, available_root):
    import orchestrator.workflow_lisp.wcc.defunctionalize as owner

    original = owner._resolve_wcc_inline_expr_value
    original_demands = owner._wcc_continuation_binding_demands

    def resolve(expr, **kwargs):
        # Exercise the owner with an explicit already-materialized Context root.
        # Ordinary authored Context inputs supply a structural Mapping instead.
        if available_root and isinstance(expr, FieldAccessExpr) and expr.base.name == "holder":
            return "inputs.pre_materialized_context"
        return original(expr, **kwargs)

    monkeypatch.setattr(owner, "_resolve_wcc_inline_expr_value", resolve)

    def direct_field_demands(body):
        # Public provider prebinding normally demands its generated Name alias.
        # Supply direct FieldAccess ownership to discriminate the existing rule.
        return {
            key: (run_ref, frozenset({"copied"}), request_input)
            for key, (run_ref, _provider, request_input) in original_demands(body).items()
        }

    monkeypatch.setattr(owner, "_wcc_continuation_binding_demands", direct_field_demands)
    source = tmp_path / "entry.orc"
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.34") '
        '(defrecord Holder (context Context)) '
        '(defworkflow run ((seed Contextual[Int])) -> Int '
        '(let* ((holder (record Holder :context seed.context)) (copied holder.context)) '
        '(provider-result providers.ask :prompt prompts.ask :inputs () :context copied :returns Int))))'
    )
    result = compile_stage3_module(
        source, entry_workflow="run", workspace_root=tmp_path, validate_shared=False,
        provider_externs={"providers.ask": "ask-provider"},
        prompt_externs={"prompts.ask": "prompts/ask.md"},
    )
    steps = result.lowered_workflows[0].authored_mapping["steps"]
    if available_root:
        assert len(steps) == 1
        assert steps[0]["provider_context"] == {"input": {"ref": "inputs.pre_materialized_context"}}
    else:
        assert len(steps) == 2
        assert steps[0]["output_bundle"]["fields"][0]["json_pointer"] == ""
        assert "pure_projection" in steps[0]
        assert steps[1]["provider_context"] == {
            "input": {"ref": f"root.steps.{steps[0]['name']}.artifacts.__result__"}
        }


def test_run_ref_demand_precedes_real_request_input_alias_emission(tmp_path: Path, monkeypatch):
    import orchestrator.workflow_lisp.wcc.defunctionalize as owner

    original = owner._wcc_continuation_binding_demands

    def demands(body):
        # The existing scan separately covers run-ref keyword operand selection.
        # Supply that fact alongside a real request-input second consumer here.
        return {
            key: (run_ref | {"question"}, provider, request_input)
            for key, (run_ref, provider, request_input) in original(body).items()
        }

    monkeypatch.setattr(owner, "_wcc_continuation_binding_demands", demands)
    source = tmp_path / "entry.orc"
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.34") '
        '(defrecord Result (seen String)) '
        '(defworkflow run () -> HumanReply '
        '(let* ((question (if true "chosen" "other")) '
        '(seen (command-result echo :argv ("python" "probe.py" question) :returns Result))) '
        '(request-input question))))'
    )
    result = compile_stage3_module(
        source, entry_workflow="run", workspace_root=tmp_path, validate_shared=False,
        command_boundaries={"echo": ExternalToolBinding(name="echo", stable_command=("python", "probe.py"))},
    )
    steps = result.lowered_workflows[0].authored_mapping["steps"]
    assert len(steps) == 3
    assert "pure_projection" in steps[0]
    assert steps[1]["command"] == [
        "python", "probe.py", "${root.steps.run__question.artifacts.__result__}",
    ]
    assert steps[2]["request_input"] == {
        "question": {"ref": "root.steps.run__question.artifacts.__result__"}
    }


@pytest.mark.parametrize("leaves", [
    ("inputs.left", "inputs.right"), ("inputs.left", None),
    ("inputs.left", _literal(True)),
])
def test_all_direct_output_leaves_required_by_legacy_shortcut(monkeypatch, leaves):
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.lowering import core
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import (
        direct_output_leaves_available,
    )
    from orchestrator.workflow_lisp.type_env import RecordTypeRef

    fields = tuple(
        SimpleNamespace(generated_name=name, source_path=("return", name))
        for name in ("left", "right")
    )
    monkeypatch.setattr("orchestrator.workflow_lisp.contracts.derive_workflow_boundary_fields", lambda *a, **k: fields)
    monkeypatch.setattr(
        core, "_inline_expr_field_value",
        lambda expr, field_path, **k: leaves[("left", "right").index(field_path[0])],
    )
    result_type = RecordTypeRef(name="Pair", definition=None, field_types={})
    context = SimpleNamespace(
        signature=SimpleNamespace(return_type_ref=result_type),
        type_env=SimpleNamespace(target_dsl_version="2.32"),
    )
    refs = core._inline_output_refs_for_expr(
        NameExpr(name="pair", span=SPAN, form_path=()), type_ref=result_type,
        local_values={}, context=context,
    )
    assert (refs is not None) == direct_output_leaves_available(isinstance(leaf, str) for leaf in leaves)
    assert refs == (
        {"left": "inputs.left", "right": "inputs.right"}
        if all(isinstance(leaf, str) for leaf in leaves) else None
    )


def test_capture_order_preserves_sequential_shadowing_and_match_binders():
    from orchestrator.workflow_lisp.expressions import LetStarExpr, MatchArm, MatchExpr
    from orchestrator.workflow_lisp.lowering.command_control_decisions import helper_capture_names

    def name(value):
        return NameExpr(name=value, span=SPAN, form_path=())

    arm = MatchArm(
        variant_name="A", binding_name="c", body=IfExpr(
            condition_expr=name("flag"), then_expr=name("c"),
            else_expr=FieldAccessExpr(
                base=name("holder"), fields=("value",), span=SPAN, form_path=(),
            ),
            span=SPAN, form_path=(),
        ), span=SPAN, form_path=(),
    )
    expr = LetStarExpr(
        bindings=(("a", name("b")), ("b", name("a"))),
        body=MatchExpr(subject=name("choice"), arms=(arm,), span=SPAN, form_path=()),
        span=SPAN, form_path=(),
    )
    assert helper_capture_names(
        expr, local_type_bindings=dict.fromkeys(("flag", "a", "c", "b", "choice", "holder")),
    ) == ("flag", "b", "choice", "holder")


def test_variant_capture_exposes_payload_fields_and_types_without_nominal_record():
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.definitions import RecordField, UnionVariant
    from orchestrator.workflow_lisp.lowering.command_control_decisions import helper_capture_payload
    from orchestrator.workflow_lisp.lowering.control_match import _helper_capture_boundary_type
    from orchestrator.workflow_lisp.type_env import (
        PrimitiveTypeRef, RecordTypeRef, UnionTypeRef, VariantCaseTypeRef,
    )

    field = RecordField(name="value", type_name="Int", span=SPAN)
    definition = UnionVariant(name="A", fields=(field,), span=SPAN)
    payload_type = PrimitiveTypeRef(name="Int")
    union = UnionTypeRef(
        name="Choice", definition=None, variant_field_types={"A": {"value": payload_type}},
    )
    variant = VariantCaseTypeRef(union_name="Choice", variant_name="A", definition=definition)
    type_env = SimpleNamespace(resolve_type=lambda *a, **k: union)
    fields, types = helper_capture_payload(variant, type_env=type_env, span=SPAN, form_path=())
    assert fields == (field,)
    assert types == {"value": payload_type}
    legacy = _helper_capture_boundary_type(
        "arm", variant, context=SimpleNamespace(type_env=type_env), span=SPAN, form_path=(),
    )
    assert isinstance(legacy, RecordTypeRef)
    assert legacy.name == "%match-arm.Choice.a.arm"
    assert legacy.definition.fields == (field,)
    assert legacy.field_types == {"value": payload_type}
    assert helper_capture_payload(payload_type, type_env=None, span=SPAN, form_path=()) is None


@pytest.mark.parametrize("workflow,iteration,boundary,body,expected", [
    ("run", True, True, True, True), ("%composition.arm.v1", True, True, True, False),
    ("run", False, True, True, False), ("run", True, False, True, False),
    ("run", True, True, False, False),
])
def test_schema1_private_override_requires_both_private_checks(
    monkeypatch, workflow, iteration, boundary, body, expected,
):
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import (
        schema1_iteration_private_override_applies,
    )
    from orchestrator.workflow_lisp.procedures import ProcedureLoweringMode
    import orchestrator.workflow_lisp.procedure_specialization as owner
    import orchestrator.workflow_lisp.procedures as procedure_owner

    monkeypatch.setattr(procedure_owner, "procedure_type_env_for", lambda *a, **k: k["default"])
    checks = []
    monkeypatch.setattr(
        owner, "_procedure_private_boundary_valid",
        lambda *a, **k: checks.append("boundary") or boundary,
    )
    monkeypatch.setattr(
        owner, "_procedure_private_body_valid",
        lambda *a, **k: checks.append("body") or body,
    )
    procedure = SimpleNamespace(
        resolved_lowering_mode=ProcedureLoweringMode.INLINE,
        typed_body=SimpleNamespace(expr=_literal(True)),
    )
    assert schema1_iteration_private_override_applies(
        procedure, iteration_scope=object() if iteration else None,
        workflow_name=workflow, default_type_env=object(), typed_procedures={},
        procedure_type_envs={}, workflow_signatures={},
    ) is expected
    expected_checks = []
    if iteration and not workflow.startswith("%composition."):
        expected_checks.append("boundary")
        if boundary:
            expected_checks.append("body")
    assert checks == expected_checks


@pytest.mark.parametrize("control_body", [False, True])
def test_selected_proc_ref_rows_match_independent_legacy_emission(tmp_path, monkeypatch, control_body):
    from orchestrator.workflow_lisp.lowering import procedures
    from orchestrator.workflow_lisp.lowering.command_control_decisions import select_surface_procedure_call
    from orchestrator.workflow_lisp.lowering.command_control_summary import (
        expression_control_summary, control_facts_for_context,
    )
    from orchestrator.workflow_lisp.lowering.composition_graph import (
        CompositionScope, build_fragment, fragment_requires_helper_boundary,
    )

    fixture = Path(__file__).parent / "fixtures/workflow_lisp/valid/proc_ref_bind_proc_forwarding.orc"
    source_text = fixture.read_text().replace('(:target-dsl "2.14")', '(:target-dsl "2.32")')
    if control_body:
        start = source_text.index("    (command-result run_checks")
        end = source_text.index("\n  (defproc invoke-runner", start)
        command = source_text[start:end].strip()[:-1]
        source_text = source_text[:start] + f"    (if true {command} {command}))" + source_text[end:]
    source = tmp_path / "entry.orc"
    source.write_text(source_text)
    original_call = procedures._lower_procedure_call
    original_erasure = procedures._runtime_erasure_checked
    expected_rows = {}
    actual_rows = {}
    observations = []
    commands = []

    def command_rows(steps):
        for step in steps:
            if "command" in step:
                commands.append(step["command"])
            if "if" in step:
                command_rows(step["then"]["steps"])
                command_rows(step["else"]["steps"])

    def erase(steps, terminal, *, plan):
        actual_rows[id(plan.provenance_source)] = (plan.selected_procedure, plan.resolved_args)
        return original_erasure(steps, terminal, plan=plan)

    def call(expr, *, result_type, context, local_values):
        selected_control = expression_control_summary(
            expr, result_type=result_type, facts=control_facts_for_context(context), local_values=local_values,
        )
        expected_rows[id(expr)] = select_surface_procedure_call(
            expr, local_values=local_values, typed_procedures=context.typed_procedures,
            procedure_catalog=getattr(context, "procedure_catalog", None),
            workflow_catalog=context.workflow_catalog, typed_workflows=context.workflows_by_name,
        )
        steps, terminal = original_call(expr, result_type=result_type, context=context, local_values=local_values)
        fragment = build_fragment(
            emitted_steps=steps, scope=CompositionScope("probe", None, "inline", None),
            output_refs=terminal.output_refs, hidden_inputs=terminal.hidden_inputs,
        )
        actual_control = fragment_requires_helper_boundary(fragment)
        assert selected_control == actual_control
        observations.append(actual_control)
        command_rows(steps)
        return steps, terminal

    monkeypatch.setattr(procedures, "_lower_procedure_call", call)
    monkeypatch.setattr(procedures, "_runtime_erasure_checked", erase)
    compile_stage3_module(
        source, entry_workflow="entry", workspace_root=tmp_path,
        lowering_route="legacy", validate_shared=False,
        command_boundaries={"run_checks": ExternalToolBinding(
            name="run_checks", stable_command=("python", "scripts/run_checks.py"),
        )},
    )
    assert len(expected_rows) == len(actual_rows) == 3
    for key, (selected, args) in expected_rows.items():
        assert selected is actual_rows[key][0]
        assert args == actual_rows[key][1]
    assert observations == [control_body] * 3
    assert len(commands) == (6 if control_body else 3)
    assert all(command == [
        "python", "scripts/run_checks.py", "${inputs.input__report}", "${inputs.input__label}",
    ] for command in commands)


def test_inline_binding_merge_keeps_caller_specialization_actual_precedence():
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.lowering.command_control_decisions import inline_procedure_bindings

    procedure = SimpleNamespace(
        signature=SimpleNamespace(params=(("actual", object()),)),
        specialization=SimpleNamespace(
            workflow_ref_bindings={"same": "workflow", "workflow": "forwarded"},
            proc_ref_bindings={"same": "proc"}, value_bindings={"same": "value", "actual": "bound"},
        ),
    )
    caller = {"same": "caller", "actual": "caller-actual", "untouched": "kept"}
    assert inline_procedure_bindings(procedure, caller_values=caller, actual_values=("resolved",)) == {
        "same": "value", "actual": "resolved", "untouched": "kept", "workflow": "forwarded",
    }
    assert caller == {"same": "caller", "actual": "caller-actual", "untouched": "kept"}
