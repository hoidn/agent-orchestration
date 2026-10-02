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
