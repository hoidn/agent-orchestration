"""Python control thunks lower to ordinary checked Workflow Lisp regions."""
from __future__ import annotations

import pytest

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.py.diagnostics import PythonFrontendError
from orchestrator.py import concat
from orchestrator.py.trace import Expr, TraceScope
from tests.test_workflow_python_declarations import compile_source


def _provider_run(program, inputs, events):
    def perform(node, _operands, identity, _owner, _reader):
        label = node["prompt"]["fills"][0]["value"]["v"]
        events.append(label)
        if node["result"] == {"kind": "primitive", "name": "Bool"}:
            value = label in {"all-second", "any-first"}
        else:
            value = f"reply:{label}"
        return coerce_evaluated_value(value, node["result"], dependencies={identity})

    return evaluate_closed_program(program, inputs, effect_handler=perform)


def test_when_traces_effects_in_selected_region(tmp_path):
    source = '''
    p = Prompt(text="Evaluate {task}", fills={"task": Text}, returns=str)
    agent = Provider("trace")

    def then_arm():
        agent(p(task="then-ignored"))
        return agent(p(task="then-result"))

    def else_arm():
        agent(p(task="else-ignored"))
        return agent(p(task="else-result"))

    @workflow
    def run(flag: bool) -> str:
        outer = agent(p(task="outer"))
        return when(flag,
            then=lambda: concat(outer, then_arm()),
            else_=lambda: concat(outer, else_arm()))
    '''
    _, _, built = compile_source(
        tmp_path, source, providers={"providers.trace": "stub"}
    )

    events = []
    selected = _provider_run(built.program, {"flag": True}, events)
    assert selected.value == "reply:outerreply:then-result"
    assert events == ["outer", "then-ignored", "then-result"]

    events.clear()
    selected = _provider_run(built.program, {"flag": False}, events)
    assert selected.value == "reply:outerreply:else-result"
    assert events == ["outer", "else-ignored", "else-result"]


def test_match_requires_exact_cases_and_scopes_binders(tmp_path):
    source = '''
    @variant
    class Good:
        text: str
    @variant
    class Bad:
        reason: str
    Outcome = Good | Bad

    @workflow
    def run(_case0: str, _e0: str, value: Outcome) -> str:
        return match(value,
            Good=lambda good: good.text,
            Bad=lambda bad: bad.reason)
    '''
    _, _, built = compile_source(tmp_path / "valid", source)
    assert evaluate_closed_program(
        built.program,
        {"_case0": "authored-case", "_e0": "authored-effect",
         "value": {"variant": "Good", "text": "done"}},
    ).value == "done"
    assert evaluate_closed_program(
        built.program,
        {"_case0": "authored-case", "_e0": "authored-effect",
         "value": {"variant": "Bad", "reason": "blocked"}},
    ).value == "blocked"

    with pytest.raises(PythonFrontendError, match="python_match_cases"):
        compile_source(tmp_path / "missing", source.replace(",\n            Bad=lambda bad: bad.reason", ""))
    with pytest.raises(PythonFrontendError, match="python_match_cases"):
        compile_source(tmp_path / "extra", source.replace(
            "Bad=lambda bad: bad.reason)",
            "Bad=lambda bad: bad.reason, Other=lambda other: \"other\")"))

    wrong_arm_field = source.replace("good.text", "good.reason")
    with pytest.raises(PythonFrontendError, match="python_symbolic_attribute"):
        compile_source(tmp_path / "wrong-arm-field", wrong_arm_field)

    unproved_constructor_field = '''
    @variant
    class Good:
        text: str
    @variant
    class Bad:
        reason: str
    Outcome = Good | Bad
    @workflow
    def run() -> str:
        return Good(text="done").text
    '''
    with pytest.raises(PythonFrontendError, match="python_symbolic_attribute"):
        compile_source(tmp_path / "unproved", unproved_constructor_field)

    wrong_join = '''
    @workflow
    def run(flag: bool) -> int:
        return when(flag, then=lambda: 1, else_=lambda: "wrong")
    '''
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path / "wrong-join", wrong_join)


def test_nested_when_and_match_regions_compile_and_evaluate(tmp_path):
    source = '''
    @variant
    class Good:
        text: str
    @variant
    class Bad:
        reason: str
    Outcome = Good | Bad
    @workflow
    def run(flag: bool) -> str:
        candidate = when(flag,
            then=lambda: Good(text="done"),
            else_=lambda: Bad(reason="blocked"))
        return match(candidate,
            Good=lambda good: when(flag, then=lambda: good.text, else_=lambda: "unused"),
            Bad=lambda bad: when(flag, then=lambda: "unused", else_=lambda: bad.reason))
    '''
    _, _, built = compile_source(tmp_path, source)
    assert evaluate_closed_program(
        built.program, {"flag": True}
    ).value == "done"
    assert evaluate_closed_program(
        built.program, {"flag": False}
    ).value == "blocked"


@pytest.mark.parametrize("control", ["when", "match"])
def test_contextual_union_flows_from_nested_region_to_ancestor_binding(tmp_path, control):
    if control == "when":
        body = '''
        return when(flag,
            then=lambda: when(flag, then=lambda: choice,
                              else_=lambda: A(value=2)),
            else_=lambda: B(value=3))
        '''
        signature = "flag: bool"
    else:
        body = '''
        return match(value,
            A=lambda a: when(flag, then=lambda: choice,
                             else_=lambda: A(value=2)),
            B=lambda b: B(value=3))
        '''
        signature = "value: First, flag: bool"
    source = f'''
    @variant
    class A:
        value: int
    @variant
    class B:
        value: int
    @variant
    class C:
        value: int
    First = A | B
    Second = A | C
    @workflow
    def run({signature}) -> First:
        choice = when(True, then=lambda: A(value=1), else_=lambda: A(value=2))
        {body}
    '''
    _, _, built = compile_source(tmp_path, source)
    inputs = {"flag": True, **({} if control == "when" else {
        "value": {"variant": "A", "value": 0}
    })}
    assert evaluate_closed_program(built.program, inputs).value == {
        "variant": "A", "value": 1
    }


@pytest.mark.parametrize("control", ["when", "match"])
def test_float_literal_branch_hint_survives_unary_negation(tmp_path, control):
    if control == "when":
        body = "when(flag, then=lambda: 1.0, else_=lambda: 2.0)"
        signature = "flag: bool"
        inputs = {"flag": True}
    else:
        body = "match(value, A=lambda a: 1.0, B=lambda b: 2.0)"
        signature = "value: Outcome"
        inputs = {"value": {"variant": "A", "value": 0}}
    source = f'''
    @variant
    class A:
        value: int
    @variant
    class B:
        value: int
    Outcome = A | B
    @workflow
    def run({signature}) -> float:
        return -{body}
    '''
    _, _, built = compile_source(tmp_path, source)
    assert evaluate_closed_program(built.program, inputs).value == -1.0


def test_module_level_record_constant_remains_usable(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @record
    class Counter:
        count: int
    initial = Counter(count=3)
    class Report(RelPath, under="reports", must_exist=True): pass
    initial_path = Report("fixed.md")
    @workflow
    def run() -> int:
        return initial.count + 2
    @workflow
    def path() -> Report:
        return initial_path
    ''')
    assert evaluate_closed_program(built.program, {}).value == 5


def test_module_level_pure_expressions_remain_usable(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    joined = concat("a", "b")
    combined = concat(joined, "!")
    size = length(["a", "b"])
    doubled_size = size + length(["c", "d"])
    enabled = not_(False)
    negative = -size
    @record
    class Values:
        joined: str
        combined: str
        size: int
        doubled_size: int
        enabled: bool
        negative: int
    initial = Values(joined=joined, combined=combined, size=size,
                     doubled_size=doubled_size, enabled=enabled, negative=negative)
    @workflow
    def run() -> Values:
        return initial
    ''')
    assert evaluate_closed_program(built.program, {}).value == {
        "joined": "ab", "combined": "ab!", "size": 2,
        "doubled_size": 4, "enabled": True, "negative": -2,
    }


def test_module_level_pure_helper_refuses_scoped_operands():
    escaped = Expr("ref", ("_case0",), str, _scope=TraceScope())
    with pytest.raises(PythonFrontendError, match="python_scope_escape"):
        concat([escaped])


def test_boolean_thunks_short_circuit(tmp_path):
    source = '''
    p = Prompt(text="Check {task}", fills={"task": Text}, returns=bool)
    agent = Provider("trace")
    @workflow
    def run(use_all: bool) -> bool:
        return when(use_all,
            then=lambda: all_of(
                lambda: agent(p(task="all-first")),
                lambda: agent(p(task="all-second"))),
            else_=lambda: any_of(
                lambda: agent(p(task="any-first")),
                lambda: agent(p(task="any-second"))))
    '''
    _, _, built = compile_source(
        tmp_path, source, providers={"providers.trace": "stub"}
    )

    events = []
    result = _provider_run(built.program, {"use_all": True}, events)
    assert result.value is False
    assert events == ["all-first"]

    events.clear()
    result = _provider_run(built.program, {"use_all": False}, events)
    assert result.value is True
    assert events == ["any-first"]


def test_eager_branches_and_escaped_binders_refuse(tmp_path):
    eager = '''
    p = Prompt(text="Evaluate {task}", fills={"task": Text}, returns=str)
    agent = Provider("trace")
    @workflow
    def run(flag: bool) -> str:
        result = agent(p(task="already-recorded"))
        return when(flag, then=result, else_=lambda: "else")
    '''
    with pytest.raises(PythonFrontendError, match="python_when_thunk_required"):
        compile_source(tmp_path / "eager", eager,
            providers={"providers.trace": "stub"})

    wrong_thunk_arity = '''
    @workflow
    def run(flag: bool) -> int:
        return when(flag, then=lambda value: value, else_=lambda: 0)
    '''
    with pytest.raises(PythonFrontendError, match="python_when_thunk_required"):
        compile_source(tmp_path / "wrong-arity", wrong_thunk_arity)

    escaped = '''
    captured = []
    @variant
    class Good:
        text: str
    @variant
    class Bad:
        reason: str
    Outcome = Good | Bad

    def keep(value):
        captured.append(value)
        return "kept"

    @workflow
    def run(value: Outcome) -> str:
        match(value,
            Good=lambda good: keep(good),
            Bad=lambda bad: "bad")
        return captured[0].text
    '''
    with pytest.raises(PythonFrontendError, match="python_scope_escape"):
        compile_source(tmp_path / "escaped", escaped)


@pytest.mark.parametrize(("expression", "result_type", "providers"), [
    ("Box(value=captured[0])", "Box", None),
    ("[captured[0]]", "list[Outcome]", None),
    ("concat(captured[0])", "str", None),
    ("captured[0] + \"suffix\"", "str", None),
    ("agent(p(task=captured[0]))", "str", {"providers.trace": "stub"}),
    ("agent(p(task=\"ok\"), model=captured[0])", "str", {"providers.trace": "stub"}),
    ("helper(captured[0])", "Outcome", None),
])
def test_escaped_binders_refuse_inside_nested_runtime_values(
    tmp_path, expression, result_type, providers
):
    source = f'''
    captured = []
    p = Prompt(text="Evaluate {{task}}", fills={{"task": Text}}, returns=str)
    agent = Provider("trace")
    @record
    class Box:
        value: str
    @variant
    class Good:
        text: str
    @variant
    class Bad:
        reason: str
    Outcome = Good | Bad
    @workflow
    def helper(value: Outcome) -> Outcome:
        return value
    def keep(value):
        captured.append(value)
        return "kept"
    @workflow
    def run(value: Outcome) -> {result_type}:
        match(value, Good=lambda good: keep(good), Bad=lambda bad: "bad")
        return {expression}
    '''
    with pytest.raises(PythonFrontendError, match="python_scope_escape") as error:
        compile_source(tmp_path, source, providers=providers)
    assert error.value.site.path == str(tmp_path / "sample.py")


def test_match_binder_captured_by_sibling_arm_refuses(tmp_path):
    source = '''
    captured = []
    @variant
    class Good:
        text: str
    @variant
    class Bad:
        reason: str
    Outcome = Good | Bad
    def keep(value):
        captured.append(value)
        return "kept"
    @workflow
    def run(value: Outcome) -> str:
        return match(value,
            Good=lambda good: keep(good),
            Bad=lambda bad: captured[0].reason)
    '''
    with pytest.raises(PythonFrontendError, match="python_scope_escape"):
        compile_source(tmp_path, source)


@pytest.mark.parametrize("nested", [False, True])
def test_discarded_workflow_calls_propagate_declared_argument_context(tmp_path, nested):
    invocation = "consume(choice)"
    if nested:
        invocation = f"when(enabled, then=lambda: {invocation}, else_=lambda: 0)"
    source = f'''
    @variant
    class A:
        value: int
    @variant
    class B:
        value: int
    @variant
    class C:
        value: int
    First = A | B
    Second = A | C
    @workflow
    def consume(value: First) -> int:
        return match(value, A=lambda a: a.value, B=lambda b: b.value)
    @workflow
    def run(flag: bool, enabled: bool) -> int:
        choice = when(flag, then=lambda: A(value=1), else_=lambda: A(value=2))
        {invocation}
        return 1
    '''
    _, _, built = compile_source(tmp_path, source)
    for flag in (False, True):
        for enabled in (False, True):
            assert evaluate_closed_program(built.program,
                {"flag": flag, "enabled": enabled}).value == 1


@pytest.mark.parametrize("nested", [False, True])
def test_discarded_provider_calls_propagate_declared_fill_context(tmp_path, nested):
    invocation = "agent(p(choice=choice))"
    if nested:
        invocation = f"when(enabled, then=lambda: {invocation}, else_=lambda: 0)"
    source = f'''
    @variant
    class A:
        value: int
    @variant
    class B:
        value: int
    @variant
    class C:
        value: int
    First = A | B
    Second = A | C
    p = Prompt(text="Inspect {{choice}}", fills={{"choice": Value[First]}}, returns=int)
    agent = Provider("trace")
    @workflow
    def run(flag: bool, enabled: bool) -> int:
        choice = when(flag, then=lambda: A(value=1), else_=lambda: A(value=2))
        {invocation}
        return 1
    '''
    _, _, built = compile_source(tmp_path, source, providers={"providers.trace": "stub"})
    events = []
    def perform(node, operands, identity, _owner, _reader):
        events.append([value.value for value in operands])
        return coerce_evaluated_value(7, node["result"], dependencies={identity})
    for flag in (False, True):
        for enabled in (False, True):
            events.clear()
            assert evaluate_closed_program(built.program,
                {"flag": flag, "enabled": enabled}, effect_handler=perform).value == 1
            expected = [[{"variant": "A", "value": 1 if flag else 2}]] if not nested or enabled else []
            assert events == expected
