"""Python declarations generate ordinary sources checked by the existing compiler."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


def module_source(root, source, *, name="sample"):
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.py"
    path.write_text("from __future__ import annotations\nfrom orchestrator.py import *\n" + textwrap.dedent(source))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    return module


def generate(root, source, *, providers=None, prompts=None, name="sample"):
    from orchestrator.py.emit import generate_module
    module = module_source(root, source, name=name)
    generated = generate_module(module, root / "generated")
    paths = {}
    for key, content in (("providers", providers), ("prompts", prompts)):
        if content is not None:
            paths[key] = root / f"{key}.json"
            paths[key].write_text(json.dumps(content))
    request = FrontendBuildRequest(source_path=generated.source_path,
        source_roots=(generated.source_root,), workspace_root=root,
        entry_workflow="run", provider_externs_path=paths.get("providers"),
        prompt_externs_path=paths.get("prompts"))
    return module, generated, request


def compile_source(root, source, **kwargs):
    module, generated, request = generate(root, source, **kwargs)
    return module, generated, build_closed_program_bundle(request)


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from nodes(child)


def test_forward_declarations_compile(tmp_path):
    source = '''
    calls = []
    @workflow
    def run(value: Later, count: int = 2) -> Later:
        calls.append("run")
        return again(value)
    @workflow
    def again(value: Later) -> Later:
        calls.append("again")
        return Later(text=value.text, number=value.number + 1)
    @record
    class Later:
        text: str
        number: int
    '''
    from orchestrator.py.emit import generate_module
    module = module_source(tmp_path, source)
    assert module.calls == []
    generated = generate_module(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=generated.source_path,
        source_roots=(generated.source_root,), workspace_root=tmp_path, entry_workflow="run"))
    assert module.calls == ["run", "again"]
    assert built.entry_workflow == "py/sample::run"
    assert built.typed_program.entry.signature.return_type_ref.name.endswith("Later")
    assert generated.source_map.entries
    assert all(row.python.path == str(tmp_path / "sample.py") for row in generated.source_map.entries)
    assert len([n for n in nodes(built.program.tree) if n.get("k") == "call"]) >= 1


def test_enum_values_are_wire_tokens(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    from enum import Enum
    class Verdict(Enum):
        ACCEPT = "accept"
        REVISE = "revise"
    @workflow
    def run() -> Verdict:
        return Verdict.ACCEPT
    ''')
    enum = built.program.tree["types"]["py/sample::Verdict"]
    assert enum["allowed"] == ["accept", "revise"]
    assert any(n.get("v") == "accept" for n in nodes(built.program.tree))


@pytest.mark.parametrize("members", ['A = 1', 'A = "bad token"', 'A = "same"\nB = "same"'])
def test_invalid_enums_refuse(tmp_path, members):
    from orchestrator.py.diagnostics import PythonFrontendError
    with pytest.raises(PythonFrontendError, match="python_enum_invalid"):
        compile_source(tmp_path, 'from enum import Enum\nclass Choice(Enum):\n' + textwrap.indent(members, '    ') + '\n@workflow\ndef run() -> Choice:\n    return Choice.A\n')


def test_prompt_kinds_and_externs_compile(tmp_path):
    (tmp_path / "template.md").write_text("Inspect {task} {path} {value} {out}")
    (tmp_path / "external.md").write_text("Review the input")
    _, _, built = compile_source(tmp_path, '''
    class Report(RelPath, under="reports", must_exist=True): pass
    class Output(RelPath, under="output", must_exist=False): pass
    @record
    class Result:
        ok: bool
    local = Prompt(file="template.md", fills={"task": Text, "doc": Doc[Report],
        "path": PathOf[Report], "value": Value[list[str]], "out": Out[Output]}, returns=Result)
    @prompt(returns=Result)
    def inline(task: Text) -> str:
        return "Inspect {task}"
    external = Prompt.extern("prompts.review", returns=Result)
    agent = Provider("review", model="chosen-model", effort="low", timeout_sec=10)
    @workflow
    def run(task: str, report: Report, target: Output, notes: list[str]) -> Result:
        agent(local(task=task, doc=report, path=report, value=notes, out=target))
        agent(inline(task=task))
        return agent(external(task), timeout_sec=20)
    ''', providers={"providers.review": "codex"}, prompts={"prompts.review": {"asset_file": "external.md"}})
    assert len(built.program.sites) == 3
    assert built.typed_program.entry.signature.return_type_ref.name.endswith("Result")


def test_provider_order_reuse_and_ignored_call(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    prompt1 = Prompt(text="First {task}", fills={"task": Text}, returns=str)
    prompt2 = Prompt(text="Second {task}", fills={"task": Text}, returns=str)
    agent = Provider("review")
    @record
    class Pair:
        left: str
        right: str
    @workflow
    def run(task: str) -> Pair:
        agent(prompt1(task=task))
        result = agent(prompt2(task=task))
        return Pair(left=result, right=result)
    ''', providers={"providers.review": "codex"})
    assert len(built.program.sites) == 2
    performs = [n for n in nodes(built.program.tree["body"]) if n.get("k") == "perform"]
    assert len(performs) == 2
    fields = [n for n in nodes(built.program.tree["body"]) if n.get("k") == "record"][-1]
    values = dict(fields["fields"])
    assert values["left"]["k"] == values["right"]["k"] == "name"
    assert values["left"]["n"] == values["right"]["n"]


@pytest.mark.parametrize("annotation", ["Any", "object", "dict[str, int]", "tuple[int, int]", "Missing"])
def test_bad_annotations_and_symbolic_coercions_refuse(tmp_path, annotation):
    from orchestrator.py.diagnostics import PythonFrontendError
    with pytest.raises(PythonFrontendError, match="python_annotation_unsupported"):
        compile_source(tmp_path, f'from typing import Any\n@workflow\ndef run(x: {annotation}) -> int:\n    return 1\n')


@pytest.mark.parametrize("operation", ["bool(x)", "len(x)", "str(x)", 'f"{x}"', "list(x)", '"a" in x', 'x.append("a")', 'setattr(x, "field", 1)', 'x.__setitem__(0, "a")', 'x[0]'])
def test_symbolic_coercions_refuse(tmp_path, operation):
    from orchestrator.py.diagnostics import PythonFrontendError
    with pytest.raises(PythonFrontendError, match="python_symbolic") as error:
        compile_source(tmp_path, f'@workflow\ndef run(x: list[str]) -> int:\n    {operation}\n    return 1\n')
    assert error.value.site.path == str(tmp_path / "sample.py")
    assert error.value.site.line >= 4


def test_recursive_annotations_and_conflicting_returns_refuse(tmp_path):
    from orchestrator.py.diagnostics import PythonFrontendError
    for name, source, code in [
        ("recursive", '@record\nclass Node:\n    next: Node | None\n@workflow\ndef run(x: Node) -> Node:\n    return x\n', "python_recursive_type"),
        ("conflict", '@workflow(returns=str)\ndef run() -> int:\n    return 1\n', "python_return_annotation_conflict"),
        ("barecase", '@variant\nclass Done:\n    text: str\n@variant\nclass Failed:\n    reason: str\nOutcome = Done | Failed\n@workflow\ndef run(x: Done) -> str:\n    return x.text\n', "python_variant_signature_unsupported"),
    ]:
        with pytest.raises(PythonFrontendError, match=code):
            compile_source(tmp_path / name, source)


def test_union_list_optional_constructors_compile(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @variant
    class Ready:
        message: str
    @variant
    class Empty: pass
    Outcome = Ready | Empty
    @record
    class Envelope:
        items: list[Outcome]
        note: str | None
    @workflow
    def run(note: str | None) -> Envelope:
        return Envelope(items=[Ready(message="ok"), Empty()], note=note)
    ''')
    assert built.typed_program.entry.signature.return_type_ref.name.endswith("Envelope")


def test_compiler_owns_type_errors_prompt_checks_and_missing_externs(tmp_path):
    invalid = [
        ('@workflow\ndef run() -> int:\n    return "wrong"\n', None),
        ('p = Prompt(text="{missing}", fills={"task": Text}, returns=str)\n@workflow\ndef run(task: str) -> str:\n    return Provider("review")(p(task=task))\n', {"providers.review": "codex"}),
        ('p = Prompt(text="{task}", fills={"task": Text}, returns=str)\n@workflow\ndef run(task: str) -> str:\n    return Provider("review")(p(task=task))\n', None),
        ('p = Prompt.extern("prompts.absent", returns=str)\n@workflow\ndef run(task: str) -> str:\n    return Provider("review")(p(task))\n', {"providers.review": "codex"}),
    ]
    for index, (source, providers) in enumerate(invalid):
        with pytest.raises(LispFrontendCompileError):
            compile_source(tmp_path / str(index), source, providers=providers)


def test_helpers_and_supported_operators_compile(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @record
    class Result:
        count: int
        text: str
        positive: bool
        number: float
    @workflow
    def run(items: list[str], text: str, value: int, number: float) -> Result:
        return Result(count=length(items) + value * 2 - 1,
            text=concat("prefix", text), positive=not_(value < 0), number=number / 2.0)
    ''')
    assert built.typed_program.entry.signature.return_type_ref.name.endswith("Result")


def test_provider_calls_outside_trace_refuse(tmp_path):
    from orchestrator.py import Prompt, Provider
    from orchestrator.py.diagnostics import PythonFrontendError
    with pytest.raises(PythonFrontendError, match="python_effect_outside_trace"):
        Provider("review")(Prompt(text="ok", fills={}, returns=str)())


FOUR_SITES = '''
class DraftDocPath(RelPath, under="artifacts/design", must_exist=True): pass
class DesignDocPath(RelPath, under="docs/design", must_exist=True): pass
@record
class Draft:
    doc: DraftDocPath
@record
class Design:
    doc: DesignDocPath
@record
class Feedback:
    blocking: list[str]
    notes: list[str]
@record
class Execution:
    summary: str
    commits: list[str]
    checks_run: list[str]
    left_undone: list[str]
draft = Prompt(text="Draft {task}", fills={"task": Text}, returns=Draft)
review = Prompt(text="Review {task}", fills={"task": Text, "design": Doc[DraftDocPath]}, returns=Feedback)
revise = Prompt(text="Revise {task} {draft_path} {blocking} {notes}", fills={
    "task": Text, "design": Doc[DraftDocPath], "draft_path": PathOf[DraftDocPath],
    "blocking": Value[list[str]], "notes": Value[list[str]]}, returns=Design)
execute = Prompt(text="Execute {task}", fills={"task": Text, "design": Doc[DesignDocPath]}, returns=Execution)
planner = Provider("claude", effort="high", timeout_sec=3600)
reviewer = Provider("codex", effort="high", timeout_sec=3600)
@workflow
def run(task: str, planner_model: str = "claude-opus-5-5", reviewer_model: str = "gpt-6.1-sol") -> Execution:
    draft_result = planner(draft(task=task), model=planner_model)
    feedback = reviewer(review(task=task, design=draft_result.doc), model=reviewer_model)
    revised = planner(revise(task=task, design=draft_result.doc, draft_path=draft_result.doc,
        blocking=feedback.blocking, notes=feedback.notes), model=planner_model)
    return reviewer(execute(task=task, design=revised.doc), model=reviewer_model, timeout_sec=14400)
'''


def test_four_site_provider_flow_matches_existing_example(tmp_path):
    _, _, built = compile_source(tmp_path, FOUR_SITES, providers={"providers.claude": "claude_unrestricted_workspace", "providers.codex": "codex"})
    repo = Path(__file__).parents[1]
    existing = build_closed_program_bundle(FrontendBuildRequest(
        source_path=repo / "workflows/examples/design_review_execute.orc", workspace_root=repo,
        provider_externs_path=repo / "workflows/examples/inputs/design_review_execute/providers.json"))
    assert len(built.program.sites) == len(existing.program.sites) == 4
    first_sig = built.typed_program.entry.signature
    second_sig = existing.typed_program.entry.signature
    assert [(name, ref.name) for name, ref in first_sig.params] == [(name, ref.name) for name, ref in second_sig.params]
    assert [(name, ref.name) for name, ref in first_sig.return_type_ref.field_types.items()] == [(name, ref.name) for name, ref in second_sig.return_type_ref.field_types.items()]
    def lineage(program):
        effects = []
        labels = {}
        body = program.tree["body"]
        def reference(value):
            if value["k"] == "field":
                return (*reference(value["base"]), tuple(value["path"]))
            if value["k"] == "name":
                return ("effect", labels[value["n"]]) if value["n"] in labels else ("parameter", value["n"])
            if value["k"] == "lit":
                return ("literal", value["v"])
            raise AssertionError(value)
        while body["k"] == "let":
            effect = body["value"]
            assert effect["k"] == "perform" and effect["class"] == "provider"
            effects.append((effect["provider"],
                [(fill["name"], fill["kind"], reference(fill["value"])) for fill in effect["prompt"]["fills"]],
                {key: reference(value) for key, value in effect["policy"].items()}))
            labels[body["name"]] = len(effects) - 1
            body = body["body"]
        if body["k"] == "perform":
            effects.append((body["provider"],
                [(fill["name"], fill["kind"], reference(fill["value"])) for fill in body["prompt"]["fills"]],
                {key: reference(value) for key, value in body["policy"].items()}))
        return effects
    assert lineage(built.program) == lineage(existing.program)
    assert lineage(built.program)[2][1][1:] == [
        ("design", "doc", ("effect", 0, ("doc",))),
        ("draft_path", "path", ("effect", 0, ("doc",))),
        ("blocking", "value", ("effect", 1, ("blocking",))),
        ("notes", "value", ("effect", 1, ("notes",))),
    ]



@pytest.mark.parametrize("payload, expected", [('{"ok":true,"extra":7}', 0), ('{"ok":"bad"}', 1)])
def test_provider_stub_validates_typed_result(tmp_path, payload, expected):
    from tests.test_workflow_evaluated_providers import SHIM
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo
    _, generated, request = generate(tmp_path, '''
    @record
    class Result:
        ok: bool
    p = Prompt(text="Inspect {task}", fills={"task": Text}, returns=Result)
    agent = Provider("review", model="chosen-model", effort="low")
    @workflow
    def run(task: str) -> Result:
        return agent(p(task=task))
    ''', providers={"providers.review": "codex"})
    binary = tmp_path / "bin/codex"
    binary.parent.mkdir()
    binary.write_text(f"#!{sys.executable}\n" + SHIM)
    binary.chmod(0o700)
    repo = Path(__file__).parents[1]
    result = subprocess.run([sys.executable, "-m", "orchestrator", "run", str(generated.source_path),
        "--source-root", str(generated.source_root), "--provider-externs-file", str(request.provider_externs_path),
        "--entry-workflow", "run", "--input", "task=inspect"], cwd=tmp_path,
        env={**os.environ, "PATH": str(binary.parent) + os.pathsep + os.environ["PATH"], "PYTHONPATH": str(repo),
             "PROVIDER_SHIM_RESULT": payload}, capture_output=True, text=True)
    assert result.returncode == expected, result.stderr
    (run_root,) = (tmp_path / ".orchestrate/runs").iterdir()
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    if expected == 0:
        assert snapshot.terminal.data["value"] == {"ok": True}
    else:
        assert any(row.data.get("code") == "provider_result_invalid" for row in snapshot.entries)
    assert len((tmp_path / "requests.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("target", ["2.35", "2.36", "2.37", "2.38", "2.39"])
def test_module_target_is_admitted_by_existing_compiler(tmp_path, target):
    _, generated, built = compile_source(tmp_path, f'TARGET = "{target}"\n@workflow(returns=int)\ndef run():\n    return 1\n')
    assert generated.module_name == "py/sample"
    assert built.program.tree["target"] == target


@pytest.mark.parametrize("target", ["2.34", "2.41"])
def test_module_target_outside_admission_refuses(tmp_path, target):
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path, f'TARGET = "{target}"\n@workflow\ndef run() -> int:\n    return 1\n')


def test_none_literal_refuses_without_synthesized_semantics(tmp_path):
    from orchestrator.py.diagnostics import PythonFrontendError
    with pytest.raises(PythonFrontendError, match="python_none_literal_unsupported"):
        compile_source(tmp_path, '@workflow\ndef run() -> str | None:\n    return None\n')


def test_record_fields_named_like_trace_metadata_compile(tmp_path):
    _, _, built = compile_source(tmp_path, """
    @record
    class Item:
        kind: str
        annotation: str
        args: int
        site: int
    @workflow
    def run(item: Item) -> Item:
        return Item(kind=item.kind, annotation=item.annotation, args=item.args, site=item.site)
    """)
    assert built.typed_program.entry.signature.return_type_ref.name.endswith("Item")
    fields = dict(built.program.tree["body"]["value"]["fields"])
    assert set(fields) == {"kind", "annotation", "args", "site"}
    for name, value in fields.items():
        assert value["k"] == "field"
        assert value["path"] == [name]
        assert value["base"]["n"] == "item"


def test_projection_of_constructed_base_gets_a_binding(tmp_path):
    _, _, built = compile_source(tmp_path, """
    @record
    class Item:
        value: int
    @workflow
    def run(number: int) -> int:
        return Item(value=number + 1).value
    """)
    assert built.program.tree["body"]["k"] == "let"


def test_union_requires_unambiguous_alias_and_expected_constructor_owner(tmp_path):
    from orchestrator.py.diagnostics import PythonFrontendError
    with pytest.raises(PythonFrontendError, match="python_union_owner_ambiguous"):
        compile_source(tmp_path, """
        @variant
        class Yes: pass
        @variant
        class No: pass
        One = Yes | No
        Two = Yes | No
        @workflow
        def run() -> One:
            return Yes()
        """)


def test_prompt_registration_defers_template_and_call_sites_map_to_python(tmp_path):
    source = """
    calls = []
    @prompt(returns=str)
    def template(task: Text) -> str:
        calls.append("template")
        return "Inspect {task}"
    agent = Provider("review")
    @workflow
    def run(task: str) -> str:
        return agent(template(task=task))
    """
    from orchestrator.py.emit import generate_module
    module = module_source(tmp_path, source)
    assert module.calls == []
    generated = generate_module(module, tmp_path / "generated")
    assert module.calls == ["template"]
    call_maps = [row for row in generated.source_map.entries if row.kind == "call"]
    assert call_maps
    for row in call_maps:
        line = (tmp_path / "sample.py").read_text().splitlines()[row.python.line - 1]
        assert "agent(" in line
        assert row.generated.end_line >= row.generated.line


def test_generated_bindings_do_not_shadow_python_parameters(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    p = Prompt(text="{task}", fills={"task": Text}, returns=str)
    agent = Provider("review")
    @record
    class Pair:
        effect: str
        parameter: str
    @workflow
    def run(_e0: str) -> Pair:
        value = agent(p(task=_e0))
        return Pair(effect=value, parameter=_e0)
    ''', providers={"providers.review": "codex"})
    body = built.program.tree["body"]
    assert body["name"] != "_e0"
    assert body["value"]["prompt"]["fills"][0]["value"]["n"] == "_e0"
    fields = dict(body["body"]["value"]["fields"])
    assert fields["parameter"]["n"] == "_e0"
    assert fields["effect"]["n"] == body["name"]


def test_reserved_symbolic_internals_refuse_at_declaration(tmp_path):
    from orchestrator.py.diagnostics import PythonFrontendError
    with pytest.raises(PythonFrontendError, match="python_record_field_reserved"):
        compile_source(tmp_path, '@record\nclass Item:\n    _kind: str\n@workflow\ndef run(item: Item) -> Item:\n    return item\n')


@pytest.mark.parametrize("exports", [None, ["run"]])
def test_only_selected_definition_roots_and_called_private_helpers_trace(tmp_path, exports):
    selection = f"__all__ = {exports!r}\n" if exports is not None else ""
    module, _, built = compile_source(tmp_path, selection + textwrap.dedent('''
    calls = []
    @workflow
    def run() -> int:
        calls.append("run")
        _helper()
        return _helper()
    @workflow
    def _helper() -> int:
        calls.append("helper")
        return 1
    @workflow
    def _unused(value: Undefined) -> Undefined:
        raise RuntimeError("Unreachable private definition must not execute")
    '''))
    assert module.calls == ["run", "helper"]
    assert built.typed_program.entry.signature.return_type_ref.name == "Int"


def test_explicit_exports_do_not_trace_unselected_public_definitions(tmp_path):
    module, _, _ = compile_source(tmp_path, '''
    __all__ = ["run"]
    calls = []
    @workflow
    def run() -> int:
        calls.append("run")
        return 1
    @workflow
    def unused() -> int:
        raise RuntimeError("Unselected definition must not execute")
    ''')
    assert module.calls == ["run"]


@pytest.mark.parametrize("value", ['"false"', '0', '1', 'None'])
def test_path_must_exist_requires_a_real_boolean(tmp_path, value):
    from orchestrator.py.diagnostics import PythonFrontendError
    with pytest.raises(PythonFrontendError, match="python_path_must_exist_invalid") as error:
        compile_source(tmp_path, f'class Report(RelPath, under="reports", must_exist={value}): pass\n@workflow\ndef run(path: Report) -> Report:\n    return path\n')
    assert error.value.site.path == str(tmp_path / "sample.py")


def test_path_under_validation_remains_compiler_owned(tmp_path):
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path, 'class Report(RelPath, under=123): pass\n@workflow\ndef run(path: Report) -> Report:\n    return path\n')


def test_cross_module_call_preserves_definition_owner(tmp_path):
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    module_source(tmp_path / "foreign", '@workflow\ndef helper() -> int:\n    return 1\n', name="foreign_definition")
    _module, generated, built = compile_source(tmp_path, 'from foreign_definition import helper\n@workflow\ndef run() -> int:\n    return helper()\n')
    assert evaluate_closed_program(built.program, {}).value == 1
    assert (generated.source_root / "py/foreign_definition.orc").exists()
