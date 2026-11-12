"""Generated Python binder names follow the callee, so effect sites survive insertions."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys

import pytest

from orchestrator.py.diagnostics import PythonFrontendError
from tests.test_workflow_python_cli import _cli, _env
from tests.test_workflow_python_declarations import compile_source


REPO = Path(__file__).parents[1]


_HEADER = '''
plan = Prompt(text="{task}", fills={"task": Text}, returns=str)
review = Prompt(text="{task}", fills={"task": Text}, returns=str)
agent = Provider("review")
@workflow
def run(task: str) -> str:
'''


def _sites(root: Path, body: str) -> list[tuple[str, str]]:
    _, _, built = compile_source(root, _HEADER + body, providers={"providers.review": "codex"})
    return [path for _owner, path in built.program.sites]


def test_inserting_a_step_of_another_callee_keeps_later_names(tmp_path):
    body = '''
    first = agent(review(task=task))
    return agent(review(task=first))
    '''
    inserted = '''
    agent(plan(task=task))
    first = agent(review(task=task))
    return agent(review(task=first))
    '''
    assert _sites(tmp_path / "inserted", inserted) == ["_plan", *_sites(tmp_path / "base", body)]


def test_inserting_a_step_of_the_same_callee_moves_only_that_callee(tmp_path):
    inserted = '''
    agent(review(task=task))
    first = agent(review(task=task))
    return agent(plan(task=first))
    '''
    assert _sites(tmp_path, inserted) == ["_review", "_review_2", "_plan"]


def test_explicit_name_survives_any_insertion(tmp_path):
    body = '''
    return agent(review(task=task), name="verdict")
    '''
    inserted = '''
    agent(review(task=task))
    agent(plan(task=task))
    return agent(review(task=task), name="verdict")
    '''
    assert "verdict" in _sites(tmp_path / "base", body)
    assert "verdict" in _sites(tmp_path / "inserted", inserted)


def test_reused_explicit_name_is_refused_at_its_python_line(tmp_path):
    body = '''
    first = agent(review(task=task), name="verdict")
    return agent(plan(task=first), name="verdict")
    '''
    with pytest.raises(PythonFrontendError) as refused:
        _sites(tmp_path, body)
    lines = (tmp_path / "sample.py").read_text(encoding="utf-8").splitlines()
    assert (refused.value.code, lines[refused.value.site.line - 1].strip()) == (
        "python_binder_name_taken", 'return agent(plan(task=first), name="verdict")',
    )


def test_run_built_before_the_rule_resumes_from_its_snapshot(tmp_path):
    # The pre-rule emitter bound these two commands as `_e0` and `_e1`; the
    # explicit names reproduce that snapshot byte for byte.
    before_rule = (
        "from orchestrator.py import Command, workflow\n"
        "counted = Command('counted', returns=int)\n"
        "@workflow\n"
        "def run(start: int) -> int:\n"
        "    first = counted('python', 'count_tool.py', start, name='_e0')\n"
        "    return counted('python', 'count_tool.py', first, name='_e1')\n"
    )
    source = tmp_path / "workflow.py"
    source.write_text(before_rule, encoding="utf-8")
    (tmp_path / "count_tool.py").write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        "value = int(sys.argv[1])\n"
        "with Path('calls.jsonl').open('a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps(value) + '\\n')\n"
        "Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text(str(value + 1), encoding='utf-8')\n",
        encoding="utf-8",
    )
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"counted": {
        "stable_command": ["python", "count_tool.py"], "closure": ["count_tool.py"],
    }}), encoding="utf-8")
    from tests.test_workflow_evaluated_resume_kills import (
        _kill_after_first_commit, _rows, _run_root, _snapshot,
    )
    arguments = ["py", "run", str(source), "--entry-workflow", "run",
                 "--command-boundaries-file", str(boundaries), "--input", "start=5"]
    _kill_after_first_commit(tmp_path, arguments, _env(tmp_path))
    run_root = _run_root(tmp_path)
    before = _snapshot(run_root)
    from orchestrator.workflow.evaluated.authority import load_run_authority
    assert [path for _owner, path in load_run_authority(run_root).program.sites] == ["_e0", "_e1"]

    # The same source under the rule builds a different program; resume must not use it.
    source.write_text(before_rule.replace(", name='_e0'", "").replace(", name='_e1'", ""), encoding="utf-8")
    resumed = _cli(tmp_path, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    after = _snapshot(run_root)
    assert _rows(after, "committed")[0] == _rows(before, "committed")[0]
    assert after.terminal is not None and after.terminal.data["value"] == 7
    assert (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines() == ["5", "6"]


def test_a_callee_parameter_called_name_keeps_its_argument(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @proc
    def greet(name: str) -> str: return name
    @workflow
    def run(task: str) -> str:
        return greet(name=task)
    ''')
    assert built.program.tree["body"]["name"] == "_greet"


def test_a_form_nested_in_one_arm_keeps_the_sibling_arm_sites(tmp_path):
    base = '''
    return when(task == "x", then=lambda: agent(review(task=task)), else_=lambda: agent(plan(task=task)))
    '''
    nested = '''
    return when(task == "x",
        then=lambda: concat(when(task == "y", then=lambda: "a", else_=lambda: "b"), agent(review(task=task))),
        else_=lambda: agent(plan(task=task)))
    '''
    else_site = "_when / body / else / _plan"
    assert else_site in _sites(tmp_path / "base", base)
    assert else_site in _sites(tmp_path / "nested", nested)


def _refusal(root: Path, body: str) -> tuple[str, str]:
    with pytest.raises(PythonFrontendError) as refused:
        _sites(root, body)
    lines = (root / "sample.py").read_text(encoding="utf-8").splitlines()
    return refused.value.code, lines[refused.value.site.line - 1].strip()


def test_a_name_on_a_loop_tail_branch_is_refused_at_its_python_line(tmp_path):
    body = '''
    return loop(state=0, max=3,
        body=lambda n: when(n == 2, then=lambda: done(task), else_=lambda: cont(n + 1), name="decide"),
        on_exhausted=lambda n: task)
    '''
    assert _refusal(tmp_path, body) == (
        "python_binder_name_unbound",
        'body=lambda n: when(n == 2, then=lambda: done(task), else_=lambda: cont(n + 1), name="decide"),',
    )


@pytest.mark.parametrize("reserved", ["true", "if", "match"])
def test_an_orc_literal_or_form_name_is_refused_as_a_binder(tmp_path, reserved):
    body = f'''
    return agent(review(task=task), name="{reserved}")
    '''
    assert _refusal(tmp_path, body) == (
        "python_binder_name_reserved", f'return agent(review(task=task), name="{reserved}")',
    )


def test_all_of_refuses_a_name_at_its_python_line(tmp_path):
    body = '''
    return when(all_of(lambda: task == "x", name="both"), then=lambda: task, else_=lambda: task)
    '''
    assert _refusal(tmp_path, body)[0] == "python_binder_name_unsupported"


_MATCH = '''
@variant
class Good:
    text: str
@variant
class Bad:
    reason: str
@variant
class Odd:
    note: str
Outcome = Good | Bad
review = Prompt(text="{task}", fills={"task": Text}, returns=str)
agent = Provider("review")
@workflow
def run(value: Outcome) -> str:
    return match(value, Good=lambda good: agent(review(task=good.text)),
                 Bad=lambda bad: agent(review(task=bad.reason))NAME)
'''


def _match_sites(root: Path, *, name: str = "", union: str = "Good | Bad", odd: str = "") -> list[str]:
    source = _MATCH.replace("NAME", name).replace("Good | Bad", union).replace("bad.reason))", "bad.reason))" + odd)
    _, _, built = compile_source(root, source, providers={"providers.review": "codex"})
    return [path for _owner, path in built.program.sites]


def test_a_match_binds_its_callee_name(tmp_path):
    assert _match_sites(tmp_path) == ["_match / body / Good / _review", "_match / body / Bad / _review_2"]


def test_a_named_match_binds_its_name(tmp_path):
    assert {path.split(" / ")[0] for path in _match_sites(tmp_path, name=', name="verdict"')} == {"verdict"}


def test_adding_a_union_variant_keeps_the_sites_of_untouched_arms(tmp_path):
    base = _match_sites(tmp_path / "base")
    widened = _match_sites(tmp_path / "widened", union="Good | Bad | Odd",
                           odd=", Odd=lambda odd: agent(review(task=odd.note))")
    assert widened[:2] == base


_BINDERS = re.compile(r"(?:\(let\* \(|\n {11})\((\S+) |\(\(\w+ (_\w+)\) |\(fn \((\S+)\)")


def _python_examples():
    return sorted((REPO / "workflows" / "examples").rglob("*.py"))


def _generated_definitions(example: Path, out: Path) -> list[str]:
    from orchestrator.py.emit import generate_graph
    name = f"names_probe_{example.stem}"
    spec = importlib.util.spec_from_file_location(name, example)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        graph = generate_graph(module, out, module_name=f"py/{example.stem}")
        return graph.source_path.read_text(encoding="utf-8").split("\n  (def")
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize("example", [p for p in _python_examples() if "orchestrator.py" in p.read_text()],
                         ids=lambda path: path.name)
def test_no_binder_is_emitted_twice_in_one_workflow_function(tmp_path, example):
    for definition in _generated_definitions(example, tmp_path):
        binders = [next(group for group in match if group) for match in _BINDERS.findall(definition)]
        assert len(binders) == len(set(binders)), definition.split("\n", 1)[0]


def test_the_durable_approval_example_keeps_its_binder_names(tmp_path):
    example = REPO / "workflows/examples/durable_host_input/approval.py"
    recover = next(d for d in _generated_definitions(example, tmp_path) if d.startswith("workflow recover"))
    assert [next(group for group in match if group) for match in _BINDERS.findall(recover)] == [
        "_diagnose_prompt", "_verify", "_approval", "_match", "_case0", "_when", "_action", "_action_2",
        "_case1", "_action_3", "_case2", "_action_4",
    ]
