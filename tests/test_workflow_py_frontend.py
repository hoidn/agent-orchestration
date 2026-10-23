"""Native Python declarations compile through the ordinary evaluated owner."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


def load(root, source, name='author'):
    path = root / f'{name}.py'
    path.write_text(source, encoding='utf-8')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


APPROVAL = '''from enum import Enum
from orchestrator.py import workflow, proc, record, Prompt, Text, Provider, Command, ask, match, HostReply
class Approval(Enum):
    YES = "approved"
    NO = "denied"
@record
class Diagnosis:
    summary: str
@record
class Outcome:
    status: str
prompt = Prompt(text="{problem}", fills={"problem": Text}, returns=Diagnosis)
question = Prompt(text="{summary}", fills={"summary": Text}, returns=Approval)
diagnoser = Provider("providers.diagnose")
verify = Command("verify", returns=Diagnosis)
action = Command("action", returns=Outcome)
@workflow(returns=Outcome)
def recovery(problem: str):
    diagnosis = diagnoser(prompt(problem=problem))
    checked = verify("python", "command.py", "verify", diagnosis.summary)
    reply = approval(checked)
    return match(reply,
        ANSWERED=lambda answer: match(answer.value,
            YES=lambda _: action("python", "command.py", "repair"),
            NO=lambda _: action("python", "command.py", "denied")),
        CANCELLED=lambda _: action("python", "command.py", "cancelled"),
        EXPIRED=lambda _: action("python", "command.py", "expired"))
@proc(returns=HostReply[Approval])
def approval(diagnosis: Diagnosis):
    return ask(question(summary=diagnosis.summary), returns=Approval)
'''


def manifests(root):
    providers = root / 'providers.json'
    providers.write_text(json.dumps({'providers.diagnose': 'codex'}))
    commands = root / 'commands.json'
    commands.write_text(json.dumps({name: {'stable_command': ['python', 'command.py'],
        'closure': ['command.py']} for name in ['verify', 'action']}))
    (root / 'command.py').write_text('''import json, os, sys
from pathlib import Path
with Path("commands.log").open("a") as target: target.write(sys.argv[1] + "\\n")
value = {"summary": sys.argv[2]} if sys.argv[1] == "verify" else {"status": sys.argv[1]}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(value))
''')
    binary = root / 'bin' / 'codex'
    binary.parent.mkdir()
    binary.write_text(f'#!{sys.executable}\n' + '''import os, sys
from pathlib import Path
sys.stdin.buffer.read()
with Path("providers.log").open("a") as target: target.write("diagnose\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"summary":"checked"}')
''')
    binary.chmod(0o700)
    return providers, commands


def test_native_approval_feasibility(tmp_path, monkeypatch):
    from orchestrator.py import build
    from orchestrator.cli.main import create_parser
    from orchestrator.cli.commands.run import run_workflow
    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.host_input import pending, answer
    from tests.workflow_evaluated_host_input_helpers import rows
    monkeypatch.chdir(tmp_path)
    providers, commands = manifests(tmp_path)
    monkeypatch.setenv('PATH', str(tmp_path / 'bin') + os.pathsep + os.environ['PATH'])
    module = load(tmp_path, APPROVAL)
    built = build(module.recovery, workspace=tmp_path, provider_externs_file=providers,
                  command_boundaries_file=commands)
    assert not (tmp_path / 'providers.log').exists()
    assert not (tmp_path / 'commands.log').exists()
    from orchestrator.contracts.closed_program.node_walk import _ast_nodes
    program = built.closed_result.program
    nodes = [node for body in [program.tree['body'], *[d['body'] for d in program.tree['definitions'].values()]]
             for node in _ast_nodes(body) if node.get('k') == 'perform']
    assert {'provider', 'command', 'request_input'} <= {node['class'] for node in nodes}
    request, = [node for node in nodes if node['class'] == 'request_input']
    assert request['result']['name'].startswith('std/host::HostReply[')
    args = create_parser().parse_args(['run', str(built.source_path), '--source-root', str(built.source_path.parent),
        '--provider-externs-file', str(providers), '--command-boundaries-file', str(commands), '--input', 'problem=broken', '--quiet'])
    result = run_workflow(args)
    assert result.exit_code == 0
    request = pending(result.run_root)
    assert request is not None
    assert (tmp_path / 'commands.log').read_text().splitlines() == ['verify']
    answer(result.run_root, request['request_id'], 'approved', by='tester', workspace=tmp_path)
    assert resume_workflow(result.run_id) == 0
    assert resume_workflow(result.run_id) == 0
    assert (tmp_path / 'providers.log').read_text().splitlines() == ['diagnose']
    assert (tmp_path / 'commands.log').read_text().splitlines() == ['verify', 'repair']
    assert rows(result.run_root)[-1]['value'] == {'status': 'repair'}


def compile_source(root, source, name='author', **kwargs):
    from orchestrator.py import build
    module = load(root, source, name)
    return module, build(module.run, workspace=root, **kwargs)


PREFIX = 'from orchestrator.py import *\nfrom enum import Enum\n'


def test_declarations_and_typed_constructors_are_closed(tmp_path):
    source = PREFIX + '''from typing import Union
@variant
class ACCEPT:
    reason: str
@variant
class REJECT:
    reason: str
Decision = Union[ACCEPT, REJECT]
@record
class Result:
    decision: Decision
    counts: list[int]
class Evidence(RelPath, under="artifacts", must_exist=False): pass
@workflow(returns=Result)
def run():
    choice = ACCEPT(reason="ok")
    record = Result(decision=choice, counts=[1, 2])
    return Result(decision=record.decision, counts=record.counts)
'''
    _, built = compile_source(tmp_path, source)
    result = built.closed_result.program.tree['result']
    assert result['kind'] == 'record'
    assert result['fields'][0]['type']['kind'] == 'union'
    assert result['fields'][1]['type']['kind'] == 'list'


def test_path_constructor_uses_declared_root_and_when_is_lazy(tmp_path):
    source = PREFIX + '''class Evidence(RelPath, under="artifacts", must_exist=False): pass
@record
class Result:
    evidence: Evidence
    label: str
command = Command("action", returns=str)
@workflow(returns=Result)
def run(flag: bool):
    evidence = Evidence("note.md")
    label = when(flag, then=lambda: command("python", "tool.py", "yes"), otherwise=lambda: "no")
    return Result(evidence=evidence, label=label)
'''
    (tmp_path / 'tool.py').write_text('print("unused")')
    commands = tmp_path / 'commands.json'
    commands.write_text(json.dumps({'action': {'stable_command': ['python', 'tool.py'], 'closure': ['tool.py']}}))
    _, built = compile_source(tmp_path, source, command_boundaries_file=commands)
    tree = built.closed_result.program.tree
    assert tree['result']['fields'][0]['type']['under'] == 'artifacts'
    from orchestrator.contracts.closed_program.node_walk import _ast_nodes
    assert any(node.get('payload', {}).get('expr', {}).get('kind') == 'path_join_under'
               for node in _ast_nodes(tree['body']))


@pytest.mark.parametrize('expression', ['bool(value)', 'iter(value)', 'len(value)', 'str(value)',
    'f"{value}"', 'value == value', 'value != value', 'value < value', 'value <= value',
    'value > value', 'value >= value', 'value + 1', '1 + value', 'value - 1', 'value * 2',
    'value / 2', 'value // 2', 'value % 2', 'value ** 2', '-value'])
def test_symbolic_python_operations_refuse_with_source(tmp_path, expression):
    from orchestrator.py.trace import AuthoringError
    source = PREFIX + f'''@workflow(returns=int)
def run(value: int):
    ignored = {expression}
    return value
'''
    with pytest.raises(AuthoringError, match=r'author.py:5.*symbolic'):
        compile_source(tmp_path, source)


@pytest.mark.parametrize('body', [
    'return when(flag, then="eager", otherwise=lambda: "lazy")',
    'return when(flag, then=lambda arg: "bad", otherwise=lambda: "good")',
    'return when(flag, then=lambda: 1, otherwise=lambda: "bad")',
])
def test_invalid_lazy_branches_refuse(tmp_path, body):
    with pytest.raises(ValueError):
        compile_source(tmp_path, PREFIX + '@workflow(returns=str)\ndef run(flag: bool):\n    ' + body + '\n')


@pytest.mark.parametrize('declarations,body', [
    ('class Choice(Enum):\n    YES="yes"\n    ALIAS="yes"', 'return Choice.YES'),
    ('class Choice(Enum):\n    YES=1', 'return Choice.YES'),
    ('class Choice(Enum):\n    YES="yes"\n    NO="no"', 'return match(choice, YES=lambda _: "yes")'),
    ('class Choice(Enum):\n    YES="yes"', 'return match(choice, YES="eager")'),
])
def test_enum_aliases_values_and_coverage_refuse(tmp_path, declarations, body):
    source = PREFIX + declarations + '\n@workflow(returns=str)\ndef run(choice: Choice):\n    ' + body + '\n'
    with pytest.raises((ValueError, TypeError)):
        compile_source(tmp_path, source)


@pytest.mark.parametrize('declarations', [
    '@record\nclass Bad:\n    value: dict[str, int]',
    '@record\nclass Bad:\n    value: object',
    '@record\nclass Parent:\n    value: int\n@record\nclass Bad(Parent): pass',
])
def test_unsupported_types_refuse(tmp_path, declarations):
    with pytest.raises((ValueError, TypeError)):
        compile_source(tmp_path, PREFIX + declarations + '\n@workflow(returns=Bad)\ndef run(value: Bad): return value\n')


def test_ambiguous_variant_membership_refuses(tmp_path):
    source = PREFIX + '''@variant
class A: pass
@variant
class B: pass
@variant
class C: pass
First = A | B
Second = A | C
@workflow(returns=First)
def run(): return A()
'''
    with pytest.raises((ValueError, TypeError), match='ambiguous'):
        compile_source(tmp_path, source)


@pytest.mark.parametrize('effect', ['[]', '[uses_command("other")]'])
def test_effect_ceilings_restrict_subjects_and_host_input(tmp_path, effect):
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
    source = PREFIX + f'''@proc(returns=HostReply[str], effects={effect})
def approval(): return ask("question", returns=str)
@workflow(returns=HostReply[str])
def run(): return approval()
'''
    with pytest.raises(LispFrontendCompileError) as error:
        compile_source(tmp_path, source)
    assert any('Python author.py:' in note for d in error.value.diagnostics for note in d.notes)


def test_explicit_host_effect_and_return_annotation_shorthand(tmp_path):
    source = PREFIX + '''@proc(effects=[host_input])
def approval() -> HostReply[str]: return ask("question", returns=str)
@workflow()
def run() -> HostReply[str]: return approval()
'''
    _, built = compile_source(tmp_path, source)
    assert built.closed_result.program.tree['result']['name'] == 'std/host::HostReply[String]'


def test_return_conflicts_and_recursion_refuse(tmp_path):
    for source in [PREFIX + '@workflow(returns=str)\ndef run() -> int: return 1\n',
                   PREFIX + '@proc(returns=str)\ndef again(): return again()\n@workflow(returns=str)\ndef run(): return again()\n']:
        with pytest.raises(ValueError): compile_source(tmp_path, source)


def test_all_prompt_fill_kinds_use_existing_contracts(tmp_path):
    source = PREFIX + '''class Input(RelPath, under="inputs", must_exist=True): pass
class Output(RelPath, under="outputs", must_exist=False): pass
class Choice(Enum): YES="yes"
prompt = Prompt(text="{text} {choice} {path} {out}", fills={"text": Text, "doc": Doc[Input], "choice": Value[Choice], "path": PathOf[Input], "out": Out[Output]}, returns=str)
provider = Provider("providers.work")
@workflow(returns=str)
def run(text: str, doc: Input, out: Output):
    return provider(prompt(text=text, doc=doc, choice=Choice.YES, path=doc, out=out), model="chosen", effort="low", timeout_sec=30)
'''
    providers = tmp_path / 'providers.json'
    providers.write_text('{"providers.work":"codex"}')
    _, built = compile_source(tmp_path, source, provider_externs_file=providers)
    from orchestrator.contracts.closed_program.node_walk import _ast_nodes
    provider, = [node for node in _ast_nodes(built.closed_result.program.tree['body']) if node.get('class') == 'provider']
    assert [fill['kind'] for fill in provider['prompt']['fills']] == ['text', 'doc', 'value', 'path', 'path']
    assert provider['prompt']['fills'][-1]['output_role'] == 'required_string_file'


@pytest.mark.parametrize('application', ['prompt()', 'prompt(text=1)', 'prompt(text="x", other="bad")'])
def test_prompt_fill_application_refuses_missing_wrong_and_extra(tmp_path, application):
    source = PREFIX + f'''prompt = Prompt(text="{{text}}", fills={{"text": Text}}, returns=str)
@workflow(returns=HostReply[str])
def run(): return ask({application}, returns=str)
'''
    with pytest.raises(ValueError): compile_source(tmp_path, source)


def test_build_does_not_export_unselected_placeholders():
    import orchestrator.py as py
    assert not {'Agent', 'parallel', 'run_ref', 'import_orc', 'pure', 'loop'} & set(vars(py))


def test_plain_helpers_are_inlined_and_forward_procs_trace_once(tmp_path):
    source = PREFIX + '''events = []
@workflow(returns=str)
def run(value: str):
    return later(later(helper(value)))
@proc(returns=str)
def later(value: str):
    events.append("later")
    return value
def helper(value):
    events.append("helper")
    return value
'''
    module = load(tmp_path, source)
    assert module.events == []
    from orchestrator.py import build
    built = build(module.run, workspace=tmp_path)
    assert module.events == ['helper', 'later']
    assert any(name.endswith('::later') for name in built.closed_result.typed_program.procedures)


@pytest.mark.parametrize('conversion', ['repr(value)', 'f"{value!r}"', 'f"{value!a}"'])
def test_symbolic_repr_conversion_refuses(tmp_path, conversion):
    source = PREFIX + f'@workflow(returns=int)\ndef run(value: int):\n    ignored = {conversion}\n    return value\n'
    with pytest.raises(ValueError, match='symbolic'): compile_source(tmp_path, source)


def test_enum_member_names_lower_to_wire_tokens_on_every_branch(tmp_path, monkeypatch):
    from orchestrator.cli.main import create_parser
    from orchestrator.cli.commands.run import run_workflow
    source = PREFIX + '''class Choice(Enum):
    YES = "approved"
    NO = "denied"
@workflow(returns=str)
def run(choice: Choice):
    return match(choice, YES=lambda _: "repair", NO=lambda _: "escalate")
'''
    _, built = compile_source(tmp_path, source)
    monkeypatch.chdir(tmp_path)
    for wire, outcome in [('approved', 'repair'), ('denied', 'escalate')]:
        args = create_parser().parse_args(['run', str(built.source_path), '--input', 'choice=' + wire, '--quiet'])
        result = run_workflow(args)
        assert result.exit_code == 0
        from tests.workflow_evaluated_host_input_helpers import rows
        assert rows(result.run_root)[-1]['value'] == outcome


def test_generated_bindings_do_not_shadow_author_parameters(tmp_path, monkeypatch):
    from orchestrator.cli.main import create_parser
    from orchestrator.cli.commands.run import run_workflow
    from tests.workflow_evaluated_host_input_helpers import rows
    source = PREFIX + '''@workflow(returns=str)
def run(v1: str):
    ignored = when(True, then=lambda: "effect-result", otherwise=lambda: "other")
    return v1
'''
    _, built = compile_source(tmp_path, source)
    monkeypatch.chdir(tmp_path)
    result = run_workflow(create_parser().parse_args(['run', str(built.source_path), '--input', 'v1=original', '--quiet']))
    assert result.exit_code == 0
    assert rows(result.run_root)[-1]['value'] == 'original'


def test_distinct_types_with_identical_names_are_not_merged(tmp_path):
    source = PREFIX + '''@record
class First:
    text: str
@record
class Second:
    count: int
First.__name__ = "Same"
Second.__name__ = "Same"
@record
class Result:
    first: First
    second: Second
@workflow(returns=Result)
def run(first: First, second: Second): return Result(first=first, second=second)
'''
    with pytest.raises(ValueError, match='type.*name|name.*type'):
        compile_source(tmp_path, source)


def test_generated_prompt_name_does_not_shadow_author_proc(tmp_path, monkeypatch):
    from orchestrator.cli.main import create_parser
    from orchestrator.cli.commands.run import run_workflow
    from tests.workflow_evaluated_host_input_helpers import rows
    source = PREFIX + '''question = Prompt(text="{text}", fills={"text":Text}, returns=str)
@proc(returns=str)
def prompt1(value: str): return value
@workflow(returns=str)
def run(value: str):
    ignored = ask(question(text=value), returns=str)
    return prompt1(value)
'''
    _, built = compile_source(tmp_path, source)
    monkeypatch.chdir(tmp_path)
    result = run_workflow(create_parser().parse_args(['run', str(built.source_path), '--input', 'value=original', '--quiet']))
    from orchestrator.host_input import answer, pending
    request = pending(result.run_root)
    answer(result.run_root, request['request_id'], 'different', by='tester', workspace=tmp_path)
    from orchestrator.cli.commands.resume import resume_workflow
    assert resume_workflow(result.run_id) == 0
    assert rows(result.run_root)[-1]['value'] == 'original'


@pytest.mark.parametrize('name', ['String', 'Int', 'HostReply', 'Provider', 'List'])
def test_author_types_cannot_shadow_builtin_or_imported_types(tmp_path, name):
    source = PREFIX + f'''@record
class {name}:
    value: str
@workflow(returns={name})
def run(value: {name}): return value
'''
    with pytest.raises(ValueError, match='reserved.*type|type.*reserved'):
        compile_source(tmp_path, source)
