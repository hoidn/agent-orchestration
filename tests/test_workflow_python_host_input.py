"""Native Python host questions use the compiler and ordinary durable lifecycle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.py import build, run
from orchestrator.py.diagnostics import PythonFrontendError
from orchestrator.py.emit import generate_graph
from orchestrator.host_input import answer, pending
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_python_declarations import module_source, nodes
from tests.test_workflow_python_cli import _cli
from tests.workflow_evaluated_host_input_helpers import rows, resume


def compile_source(root, source, **options):
    module = module_source(root, source)
    graph = generate_graph(module, root / "generated", **options)
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=graph.source_path, source_roots=graph.source_roots,
        entry_workflow="run", workspace_root=root,
    ))
    return graph, built


def requests(program):
    return [node for node in nodes(program.tree) if node.get("k") == "perform"
            and node.get("class") == "request_input"]


def test_default_target_star_import_keeps_239_without_host_dependency(tmp_path):
    graph, built = compile_source(tmp_path, '''
    @proc
    def identity(value: int) -> int: return value
    @workflow
    def run() -> int: return identity(7)
    ''')
    assert built.program.tree["result"]["name"] == "Int"
    assert not any(path.name == "host.orc" for path in graph.source_reads)


def test_body_only_ask_is_retained_even_when_result_is_ignored(tmp_path):
    graph, built = compile_source(tmp_path, '''
    TARGET = "2.40"
    @workflow
    def run() -> int:
        ask("Review?", returns=str)
        return 7
    ''')
    assert len(requests(built.program)) == 1
    assert requests(built.program)[0]["result"]["name"] == "std/host::HostReply[String]"
    assert any(path.name == "host.orc" for path in graph.source_reads)
    assert any(entry.kind == "call" and entry.python.line == 7 for entry in graph.source_map.entries)


@pytest.mark.parametrize("target", ["2.35", "2.38", "2.39"])
def test_body_only_ask_refuses_old_target_before_run_publication(tmp_path, target):
    source = module_source(tmp_path, f'''
    TARGET = "{target}"
    @workflow
    def run() -> int:
        ask("Review?", returns=str)
        return 7
    ''')
    with pytest.raises(PythonFrontendError) as error:
        build(source.__file__, workspace_root=tmp_path)
    assert error.value.code == "python_host_input_target"
    assert error.value.site.path == source.__file__
    assert error.value.site.line == 7
    assert not (tmp_path / ".orchestrate/runs").exists()


def test_explicit_host_reply_annotation_refuses_old_target(tmp_path):
    with pytest.raises(PythonFrontendError, match="python_host_input_target"):
        compile_source(tmp_path, '''
        @workflow
        def run(reply: HostReply[str]) -> HostReply[str]: return reply
        ''')


@pytest.mark.parametrize("effect", ["", "effects=(host_input,)"])
def test_proc_host_effect_is_inferred_or_restricted(tmp_path, effect):
    _, built = compile_source(tmp_path, f'''
    TARGET = "2.40"
    @proc({effect})
    def approval() -> HostReply[str]: return ask("Review?", returns=str)
    @workflow
    def run() -> HostReply[str]: return approval()
    ''')
    assert len(requests(built.program)) == 1


@pytest.mark.parametrize("decorator", ["proc(effects=())", "pure"])
def test_pure_and_empty_effect_contract_refuse_host_input(tmp_path, decorator):
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path, f'''
        TARGET = "2.40"
        @{decorator}
        def approval() -> HostReply[str]: return ask("Review?", returns=str)
        @workflow
        def run() -> HostReply[str]: return approval()
        ''')


@pytest.mark.parametrize("declarations,annotation,reply,consume,expected", [
    ("", "str", "accepted", "answered.value", "accepted"),
    ('from enum import Enum\nclass Approval(Enum): YES="approved"; NO="denied"', "Approval", "approved",
     'when(answered.value == Approval.YES, then=lambda: "approved", else_=lambda: "denied")', "approved"),
    ('@variant\nclass ACCEPT:\n    reason: str\n@variant\nclass REJECT: pass\nDecision=ACCEPT | REJECT',
     "Decision", {"variant": "ACCEPT", "reason": "checked"},
     'match(answered.value, ACCEPT=lambda accepted: accepted.reason, REJECT=lambda _: "rejected")', "checked"),
])
def test_typed_reply_uses_existing_generic_and_match(tmp_path, monkeypatch, declarations, annotation, reply, consume, expected):
    monkeypatch.chdir(tmp_path)
    source = module_source(tmp_path, f'''
TARGET = "2.40"
{declarations}
@proc
def approval() -> HostReply[{annotation}]: return ask("Review?", returns={annotation})
@workflow
def run() -> str:
    result = approval()
    return match(result, ANSWERED=lambda answered: {consume},
                 CANCELLED=lambda cancelled: cancelled.by, EXPIRED=lambda _: "expired")
''')
    started = run(source.__file__, quiet=True)
    request = pending(started.run_root)
    assert request is not None
    answer(started.run_root, request["request_id"], reply, by="operator", workspace=tmp_path)
    assert resume(started.run_root) == 0
    assert resume(started.run_root) == 0
    committed = [row for row in rows(started.run_root) if row.get("effect_class") == "request_input"]
    assert len(committed) == 1
    assert committed[0]["value"] == {"variant": "ANSWERED", "value": reply, "by": "operator"}
    assert rows(started.run_root)[-1]["value"] == expected


@pytest.mark.parametrize("style", ["local", "decorator", "imported", "python"])
def test_prompt_questions_preserve_doc_value_and_show_operands(tmp_path, monkeypatch, style):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "inputs").mkdir()
    document = tmp_path / "inputs/report.md"
    document.write_text("runtime policy evidence")
    prelude = '''from enum import Enum
class Choice(Enum): YES="approved"
class Report(RelPath, under="inputs", must_exist=True): pass
'''
    if style == "local":
        prompt = 'question=Prompt(text="{text} {choice}", fills={"text":Text,"choice":Value[Choice],"doc":Doc[Report]}, returns=str)\n'
        application = 'question(text=text, choice=choice, doc=report)'
    elif style == "decorator":
        prompt = '''@prompt(returns=str)
def question(text: Text, choice: Value[Choice], doc: Doc[Report]) -> str:
    return "{text} {choice}"
'''
        application = 'question(text=text, choice=choice, doc=report)'
    elif style == "python":
        (tmp_path / "host_question.py").write_text("from orchestrator.py import *\n" + prelude +
            'question=Prompt(text="{text} {choice}", fills={"text":Text,"choice":Value[Choice],"doc":Doc[Report]}, returns=str)\n')
        monkeypatch.syspath_prepend(str(tmp_path))
        prelude = "from host_question import Choice, Report, question\n"
        prompt = ""
        application = 'question(text=text, choice=choice, doc=report)'
    else:
        library = tmp_path / "libs/library/question.orc"
        library.parent.mkdir(parents=True)
        library.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
          (defmodule library/question) (export Choice Report question)
          (defenum Choice approved)
          (defpath Report :kind relpath :under "inputs" :must-exist true)
          (defprompt question (:fills (text :text) (choice :value Choice) (doc :doc Report)) -> String
            "{text} {choice}"))''')
        prelude = 'library=import_orc("library/question", source_root="libs")\nReport=library.Report\nChoice=library.Choice\n'
        prompt = ""
        application = 'library.question(text=text, choice=choice, doc=report)'
    source = module_source(tmp_path, 'TARGET="2.40"\n' + prelude + prompt + f'''
@workflow
def run(text: str, report: Report, choice: Choice) -> HostReply[str]:
    return ask({application}, returns=str, timeout_sec=60, show=(report,))
''')
    started = run(source.__file__, inputs={"text": "review", "report": "inputs/report.md", "choice": "approved"}, quiet=True)
    request = pending(started.run_root)
    assert request is not None
    assert request["show"][0]["path"] == "inputs/report.md"
    assert request["show"][0]["sha256"] == "sha256:" + hashlib.sha256(document.read_bytes()).hexdigest()
    assert any(part.get("kind") == "doc" for part in requests_from_authority(started.run_root)["prompt"]["fills"])
    assert request["deadline"] - request["created_at"] == 60
    answer(started.run_root, request["request_id"], "accepted", by="operator", workspace=tmp_path)
    assert resume(started.run_root) == 0
    assert rows(started.run_root)[-1]["value"]["value"] == "accepted"


def requests_from_authority(run_root):
    from orchestrator.workflow.evaluated.authority import load_run_authority
    request, = requests(load_run_authority(run_root).program)
    return request


def test_prompt_extern_is_explicitly_refused_as_host_question(tmp_path):
    with pytest.raises(PythonFrontendError) as error:
        compile_source(tmp_path, '''
        TARGET="2.40"
        question=Prompt.extern("prompts.question", returns=str)
        @workflow
        def run() -> HostReply[str]: return ask(question("review"), returns=str)
        ''')
    assert error.value.code == "python_host_prompt_extern"


@pytest.mark.parametrize("question,options", [
    ('"Review?"', 'timeout_sec=False'),
    ('"Review?"', 'show=("inputs/report.md",)'),
    ('question(text=7)', ''),
    ('question(text="review")', 'returns=int'),
])
def test_question_operands_keep_existing_compiler_validation(tmp_path, question, options):
    returns = "" if "returns=" in options else "returns=str, "
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path, f'''
        TARGET="2.40"
        question=Prompt(text="{{text}}", fills={{"text":Text}}, returns=str)
        @workflow
        def run() -> HostReply[str]: return ask({question}, {returns}{options})
        ''')


def test_ask_binding_does_not_shadow_author_parameter_or_prompt_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = module_source(tmp_path, '''
    TARGET="2.40"
    question=Prompt(text="{text}", fills={"text":Text}, returns=str)
    @proc
    def prompt1(value: str) -> str: return value
    @workflow
    def run(_e0: str) -> str:
        ask(question(text=_e0), returns=str)
        return prompt1(_e0)
    ''')
    started = run(source.__file__, inputs={"_e0": "original"}, quiet=True)
    request = pending(started.run_root)
    answer(started.run_root, request["request_id"], "different", by="operator", workspace=tmp_path)
    assert resume(started.run_root) == 0
    assert rows(started.run_root)[-1]["value"] == "original"


def test_serial_python_loop_asks_once_per_visit_and_reuses_bound_reply(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = module_source(tmp_path, '''
    TARGET="2.40"
    def step(count):
        reply = ask("Review?", returns=str)
        return match(reply,
            ANSWERED=lambda answer: when(answer.value == answer.value,
                then=lambda: cont(count + 1), else_=lambda: done(count)),
            CANCELLED=lambda _: done(count), EXPIRED=lambda _: done(count))
    @workflow
    def run() -> int:
        return loop(state=0, max=2, body=step, on_exhausted=lambda count: count)
    ''')
    started = run(source.__file__, quiet=True)
    identifiers = []
    for value in ("first", "second"):
        request = pending(started.run_root)
        assert request is not None
        identifiers.append(request["request_id"])
        assert resume(started.run_root) == 0
        assert pending(started.run_root)["request_id"] == request["request_id"]
        answer(started.run_root, request["request_id"], value, by="operator", workspace=tmp_path)
        assert resume(started.run_root) == 0
    assert len(set(identifiers)) == 2
    assert pending(started.run_root) is None
    assert rows(started.run_root)[-1]["value"] == 2
    assert len([row for row in rows(started.run_root) if row.get("effect_class") == "request_input"]) == 2


@pytest.mark.parametrize("source_kind", ["orc", "python"])
def test_imported_asking_procedure_uses_same_memo(tmp_path, monkeypatch, source_kind):
    monkeypatch.chdir(tmp_path)
    if source_kind == "orc":
        library = tmp_path / "libs/library/approval.orc"
        library.parent.mkdir(parents=True)
        library.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
          (defmodule library/approval) (import std/host :only (HostReply)) (export approval)
          (defproc approval ((text String)) -> HostReply[String]
            (request-input text :returns String)))''')
        imports = 'library=import_orc("library/approval", source_root="libs")'
    else:
        (tmp_path / "host_approval.py").write_text('''from orchestrator.py import *
TARGET="2.40"
@proc
def approval(text: str) -> HostReply[str]: return ask(text, returns=str)
''')
        monkeypatch.syspath_prepend(str(tmp_path))
        imports = "import host_approval as library"
    source = module_source(tmp_path, 'TARGET="2.40"\n' + imports + '''
@workflow
def run() -> str:
    return match(library.approval("Review?"), ANSWERED=lambda a: a.value,
                 CANCELLED=lambda _: "cancelled", EXPIRED=lambda _: "expired")
''')
    started = run(source.__file__, quiet=True)
    request = pending(started.run_root)
    answer(started.run_root, request["request_id"], "accepted", by="operator", workspace=tmp_path)
    assert resume(started.run_root) == 0
    assert rows(started.run_root)[-1]["value"] == "accepted"


def _started_cli(root, body):
    source = module_source(root, 'TARGET="2.40"\n' + body)
    result = _cli(root, "py", "run", source.__file__, "--quiet")
    assert result.returncode == 0, result.stderr
    run_root, = (root / ".orchestrate/runs").iterdir()
    header = json.loads((run_root / "run.json").read_text())
    return source, run_root, root / header["workflow_file"]


@pytest.mark.parametrize("mutation", ["changed", "missing"])
def test_generated_source_mutation_refuses_settlement_and_resume(tmp_path, mutation):
    _, run_root, generated = _started_cli(tmp_path, '''
@workflow
def run() -> HostReply[str]: return ask("Review?", returns=str)
''')
    request = pending(run_root)
    before = (run_root / "memo.jsonl").read_bytes()
    if mutation == "changed":
        generated.write_text(generated.read_text().replace("request-input", "unknown-input"))
    else:
        generated.unlink()
    settled = _cli(tmp_path, "input", "answer", run_root.name, request["request_id"],
                   "--by", "operator", "--value", '"accepted"')
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert settled.returncode == resumed.returncode == 2
    assert "Traceback" not in settled.stderr + resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == before


def test_original_source_prompt_and_map_are_not_resume_authority(tmp_path):
    template = tmp_path / "question.md"
    template.write_text("{text}")
    source, run_root, generated = _started_cli(tmp_path, '''
question=Prompt(file="question.md", fills={"text":Text}, returns=str)
@workflow
def run() -> HostReply[str]: return ask(question(text="review"), returns=str)
''')
    original = generated.read_bytes()
    source_map = generated.parents[2] / "source-map.json"
    source_hashes = json.loads(source_map.read_text())["source_hashes"]
    assert source_hashes[source.__file__] == "sha256:" + hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest()
    template.write_text("changed template")
    Path(source.__file__).unlink()
    template.unlink()
    source_map.unlink()
    assert generated.read_bytes() == original
    request = pending(run_root)
    settled = _cli(tmp_path, "input", "answer", run_root.name, request["request_id"],
                   "--by", "operator", "--value", '"accepted"')
    assert settled.returncode == 0, settled.stderr
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0


def test_runtime_doc_divergence_cannot_be_waived_by_show_override(tmp_path):
    (tmp_path / "inputs").mkdir()
    document = tmp_path / "inputs/report.md"
    document.write_text("initial")
    source = module_source(tmp_path, '''
    TARGET="2.40"
    class Report(RelPath, under="inputs", must_exist=True): pass
    question=Prompt(text="{text}", fills={"text":Text,"doc":Doc[Report]}, returns=str)
    @workflow
    def run(report: Report) -> HostReply[str]:
        return ask(question(text="review",doc=report), returns=str, show=(report,))
    ''')
    result = _cli(tmp_path, "py", "run", source.__file__, "--input", "report=inputs/report.md", "--quiet")
    assert result.returncode == 0, result.stderr
    run_root, = (tmp_path / ".orchestrate/runs").iterdir()
    request = pending(run_root)
    document.write_text("changed")
    before = (run_root / "memo.jsonl").read_bytes()
    settled = _cli(tmp_path, "input", "answer", run_root.name, request["request_id"],
                   "--by", "operator", "--value", '"accepted"', "--accept-changed-evidence")
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert settled.returncode == resumed.returncode == 2
    assert "effect_input_diverged" in settled.stderr and "effect_input_diverged" in resumed.stderr
    assert "Traceback" not in settled.stderr + resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == before
