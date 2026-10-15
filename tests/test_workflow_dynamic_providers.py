"""Public direct provider execution for the dynamic Workflow Lisp profile."""

from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import shutil
import sys

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow.dynamic.state import load_dynamic_view
from orchestrator.workflow.dynamic.runtime import execute_dynamic_run
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.dynamic.build import prepare_dynamic_program_bundle
from orchestrator.workflow_lisp.dynamic.program import DynamicProgram
from tests.test_workflow_dynamic_source import write_source


COMMAND_PROBE = "tests/fixtures/workflow_lisp/dynamic/command_probe.py"


def _source(
    tmp_path, *, raw_note=False, raw_message=False, bool_model=False,
    bad_effort=False, budget=1000,
):
    write_source(tmp_path, "old/prompts", '''
      (export Decision NotePath ReportPath review)
      (defpath NotePath :kind relpath :under "notes" :must-exist true)
      (defpath ReportPath :kind relpath :under "reports" :must-exist false)
      (defunion Decision (APPROVE (ok Bool) (score Int)) (REJECT (reason String)))
      (defprompt review
        (:fills (note :doc NotePath) (message :text) (report :path :out ReportPath))
        -> Decision "Review {message}; report: {report}")
    ''', budget=None, target="2.35")
    note_type = "Value" if raw_note else "NotePath"
    message_type = "Value" if raw_message else "String"
    model_type = "Value" if bool_model else "String"
    effort_type = "Value" if bad_effort else "String"
    return write_source(tmp_path, "demo/main", f'''
      (import old/prompts :only (Decision NotePath ReportPath review))
      (export main)
      (defrecord CommandResult (literal String) (computed String) (opaque String) (first Int) (second Int))
      (define (accept answer)
        (command-result probe
          :argv ("python" "{COMMAND_PROBE}" "finish" "approved"
            (field answer "score") "selected" 11 12)
          :returns CommandResult))
      (define (reject answer)
        (command-result probe
          :argv ("python" "{COMMAND_PROBE}" "finish" "rejected"
            (field answer "reason") "selected" 0 0)
          :returns CommandResult))
      (defworkflow main ((note {note_type}) (message {message_type})
                         (report ReportPath) (model {model_type}) (effort {effort_type}))
        -> CommandResult
        (let* ((answer (provider-result providers.review
                         :prompt (review :note note :message message :report report)
                         :model model :effort effort))
               (continuation (if (= (field answer "variant") "APPROVE") accept reject)))
          (continuation answer)))
    ''', budget=budget)


def _provider_node(tree):
    if isinstance(tree, dict):
        if tree.get("k") == "perform" and tree.get("class") == "provider":
            return tree
        for value in tree.values():
            found = _provider_node(value)
            if found is not None:
                return found
    elif isinstance(tree, list):
        for value in tree:
            found = _provider_node(value)
            if found is not None:
                return found
    return None


def _args(path, providers, commands, values):
    inputs = path.parent.parent / "inputs.json"
    inputs.write_text(json.dumps(values), encoding="utf-8")
    return create_parser().parse_args([
        "run", str(path), "--source-root", str(path.parent.parent),
        "--provider-externs-file", str(providers),
        "--command-boundaries-file", str(commands),
        "--input-file", str(inputs),
    ])


def _manifests(tmp_path):
    providers = tmp_path / "providers.json"
    providers.write_text(json.dumps({"providers.review": "codex"}), encoding="utf-8")
    commands = tmp_path / "commands.json"
    commands.write_text(json.dumps({"probe": {
        "kind": "external_tool",
        "stable_command": ["python", COMMAND_PROBE],
        "closure": [],
    }}), encoding="utf-8")
    return providers, commands


def _stage_tools(tmp_path, monkeypatch):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    provider = binary_dir / "codex"
    shutil.copyfile(Path(__file__).parent / "fixtures/workflow_lisp/dynamic/provider_probe.py", provider)
    provider.chmod(0o700)
    (tmp_path / "tests/fixtures/workflow_lisp/dynamic").mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent / "fixtures/workflow_lisp/dynamic/command_probe.py",
                    tmp_path / COMMAND_PROBE)
    monkeypatch.setenv("PATH", str(binary_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(tmp_path)


def _forbid_workflow_executor(monkeypatch):
    from orchestrator.workflow.executor import WorkflowExecutor

    def fail(*_args, **_kwargs):
        raise AssertionError("dynamic provider execution constructed WorkflowExecutor")

    monkeypatch.setattr(WorkflowExecutor, "__init__", fail)


def _values(**overrides):
    return {
        "note": "notes/input.md",
        "message": "inspect candidate",
        "report": "reports/review.md",
        "model": "local-model",
        "effort": "low",
        **overrides,
    }


def test_public_provider_selects_closure_and_runs_later_command(tmp_path, monkeypatch):
    path = _source(tmp_path, budget=37)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("IMPORTED PROMPT DOCUMENT", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)

    from orchestrator.workflow.dynamic import runtime as runtime_module
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    original_resolve = runtime_module._resolve_provider_input_values
    prepared = []

    def capture(*args, **kwargs):
        resolved = original_resolve(*args, **kwargs)
        prepared.append(resolved)
        return resolved

    monkeypatch.setattr(runtime_module, "_resolve_provider_input_values", capture)
    result = run_workflow(_args(path, providers, commands, _values()))

    assert prepared[0].input_parts["delivery"] == canonical_sha256("file/2")
    assert result.exit_code == 0
    assert result.workflow_outputs == {
        "literal": "approved", "computed": "7", "opaque": "selected",
        "first": 11, "second": 12,
    }
    event = json.loads((tmp_path / "provider_events.jsonl").read_text().splitlines()[0])
    assert "IMPORTED PROMPT DOCUMENT" in event["prompt"]
    assert "inspect candidate" in event["prompt"]
    assert event["argv"] == [
        "exec", "--model", "local-model", "--config",
        "model_reasoning_effort=low", "--dangerously-bypass-approvals-and-sandbox",
    ]
    view = load_dynamic_view(result.run_root)
    assert view["steps_used"] == 37
    assert [(row["effect_class"], row["status"]) for row in view["effects"]] == [
        ("provider", "completed"), ("command", "completed"),
    ]
    provider_attempt = result.run_root / view["effects"][0]["result_path"].rsplit("/", 1)[0]
    assert event["result_path"] == str(result.run_root / view["effects"][0]["result_path"])
    assert (provider_attempt / "prompt.txt").read_text(encoding="utf-8") == event["prompt"]
    assert (tmp_path / "reports/review.md").read_text(encoding="utf-8") == "provider report"
    commands_seen = [json.loads(line) for line in (tmp_path / "command_events.jsonl").read_text().splitlines()]
    assert [row["action"] for row in commands_seen] == ["finish"]


def test_public_provider_result_path_survives_provider_chdir(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("captured document", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    probe = tmp_path / "bin/codex"
    text = probe.read_text(encoding="utf-8")
    assert 'Path(event["result_path"]).write_text' in text
    probe.write_text(text.replace(
        'Path(event["result_path"]).write_text',
        'os.chdir("provider-subdir")\nPath(event["result_path"]).write_text',
    ), encoding="utf-8")
    (tmp_path / "provider-subdir").mkdir()
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, providers, commands, _values()))

    view = load_dynamic_view(result.run_root)
    event, = [json.loads(line) for line in (tmp_path / "provider_events.jsonl").read_text().splitlines()]
    expected = result.run_root / view["effects"][0]["result_path"]
    assert result.exit_code == 0, view["error"]
    assert event["result_path"] == str(expected)
    assert json.loads(expected.read_text(encoding="utf-8")) == {
        "variant": "APPROVE", "ok": True, "score": 7,
    }


def test_public_provider_resnapshots_imported_document_on_fresh_run(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    note = tmp_path / "notes/input.md"
    note.write_text("FIRST DOCUMENT SNAPSHOT", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)

    first = run_workflow(_args(path, providers, commands, _values()))
    note.write_text("SECOND DOCUMENT SNAPSHOT", encoding="utf-8")
    second = run_workflow(_args(path, providers, commands, _values()))

    assert first.exit_code == second.exit_code == 0
    assert first.run_id != second.run_id
    events = [
        json.loads(line)
        for line in (tmp_path / "provider_events.jsonl").read_text().splitlines()
    ]
    assert len(events) == 2
    assert "FIRST DOCUMENT SNAPSHOT" in events[0]["prompt"]
    assert "SECOND DOCUMENT SNAPSHOT" in events[1]["prompt"]
    assert events[0]["result_path"] != events[1]["result_path"]
    for result, event in ((first, events[0]), (second, events[1])):
        view = load_dynamic_view(result.run_root)
        assert [row['ordinal'] for row in view['effects']] == [1, 2]
        provider_path = tmp_path / event['result_path']
        assert provider_path == result.run_root / view['effects'][0]['result_path']
        assert json.loads(provider_path.read_text()) == {"variant": "APPROVE", "ok": True, "score": 7}


def test_provider_snapshot_can_be_stored_captured_and_shadowed_before_command(tmp_path, monkeypatch):
    path = _source(tmp_path)
    text = path.read_text().replace('(defworkflow main',
        '(define (apply callback) (callback))\n(defworkflow main')
    text = text.replace('(continuation answer)', f'''(let* ((saved answer)
      (reader (fn () (continuation saved))) (box (record (read reader)))
      (answer (record (variant "REJECT") (reason "shadow")))
      (later (command-result probe :argv ("python" "{COMMAND_PROBE}" "first") :returns Int)))
      (apply (field box "read")))''')
    path.write_text(text)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('SNAPSHOT')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    probe = tmp_path / COMMAND_PROBE
    probe.write_text(probe.read_text().replace('    result = 11', '    output = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n    (output.parents[2] / "1/attempt-1/result.json").write_text(\'{"replaced":true}\')\n    result = 11'))
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, providers, commands, _values()))
    assert result.exit_code == 0 and result.workflow_outputs['computed'] == '7'
    view = load_dynamic_view(result.run_root)
    assert [(row['effect_class'], row['status']) for row in view['effects']] == [
        ('provider', 'completed'), ('command', 'completed'), ('command', 'completed')]
    assert json.loads((result.run_root / view['effects'][0]['result_path']).read_text()) == {
        'replaced': True}
    assert [json.loads(line)['action'] for line in (tmp_path / 'command_events.jsonl').read_text().splitlines()] == ['first', 'finish']


def test_provider_prefix_repeats_after_later_command_failure_without_overwriting_old_run(tmp_path, monkeypatch):
    path = _source(tmp_path)
    path.write_text(path.read_text().replace('"finish" "approved"', '"leak" "approved"'))
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('PRIVATE DOCUMENT')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    probe = tmp_path / COMMAND_PROBE
    probe.write_text(probe.read_text().replace('    raise SystemExit(7)',
        '    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("11")\n    raise SystemExit(7)'))
    _forbid_workflow_executor(monkeypatch)
    first = run_workflow(_args(path, providers, commands, _values()))
    old = {p.relative_to(first.run_root).as_posix(): p.read_bytes() for p in first.run_root.rglob('*') if p.is_file()}
    second = run_workflow(_args(path, providers, commands, _values()))
    assert first.exit_code == second.exit_code == 1 and first.run_id != second.run_id
    assert old == {p.relative_to(first.run_root).as_posix(): p.read_bytes() for p in first.run_root.rglob('*') if p.is_file()}
    assert len((tmp_path / 'provider_events.jsonl').read_text().splitlines()) == 2
    assert [json.loads(line)['action'] for line in (tmp_path / 'command_events.jsonl').read_text().splitlines()] == ['leak', 'leak']
    for result in (first, second):
        view = load_dynamic_view(result.run_root)
        assert view['workflow_outputs'] is None
        assert [(row['ordinal'], row['effect_class'], row['status']) for row in view['effects']] == [
            (1, 'provider', 'completed'), (2, 'command', 'failed')]
        assert json.loads((result.run_root / view['effects'][0]['result_path']).read_text())['score'] == 7
        assert json.loads((result.run_root / view['effects'][1]['result_path']).read_text()) == 11
        assert 'PRIVATE DOCUMENT' not in json.dumps(view['error'])


def test_provider_input_and_document_are_fresh_while_attempt_keeps_captured_document(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / 'notes').mkdir()
    note = tmp_path / 'notes/input.md'
    note.write_text('DOC_A')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    probe = tmp_path / 'bin/codex'
    probe.write_text(probe.read_text().replace('report_match =', '''result['score'] = 9 if 'SECOND_GOAL' in prompt else 7
Path('notes/input.md').write_text('DOC_B')
report_match ='''))
    _forbid_workflow_executor(monkeypatch)
    first = run_workflow(_args(path, providers, commands, _values(message='FIRST_GOAL')))
    second = run_workflow(_args(path, providers, commands, _values(message='SECOND_GOAL')))
    assert first.exit_code == second.exit_code == 0 and first.run_id != second.run_id
    assert [first.workflow_outputs['computed'], second.workflow_outputs['computed']] == ['7', '9']
    events = [json.loads(line) for line in (tmp_path / 'provider_events.jsonl').read_text().splitlines()]
    for result, event, goal, document in ((first, events[0], 'FIRST_GOAL', 'DOC_A'), (second, events[1], 'SECOND_GOAL', 'DOC_B')):
        assert goal in event['prompt'] and document in event['prompt']
        view = load_dynamic_view(result.run_root)
        attempt = result.run_root / view['effects'][0]['result_path'].rsplit('/', 1)[0]
        assert (attempt / 'prompt.txt').read_text() == event['prompt']
    assert 'DOC_B' not in events[0]['prompt'] and 'FIRST_GOAL' not in events[1]['prompt']


@pytest.mark.parametrize('budget,expected_effects', [(1, 0), (30, 1)])
def test_provider_and_later_command_share_budget_with_fresh_prefix_repetition(tmp_path, monkeypatch, budget, expected_effects):
    path = _source(tmp_path, budget=budget)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('budget document')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    results = [run_workflow(_args(path, providers, commands, _values())) for _ in range(2)]
    assert results[0].run_id != results[1].run_id
    for result in results:
        assert result.exit_code == 1
        view = load_dynamic_view(result.run_root)
        assert view['steps_used'] == budget and view['error']['code'] == 'dynamic_budget_exhausted'
        assert len(view['effects']) == expected_effects
        assert all(row['status'] == 'completed' for row in view['effects'])
    assert not (tmp_path / 'command_events.jsonl').exists()
    log = tmp_path / 'provider_events.jsonl'
    assert (len(log.read_text().splitlines()) if log.exists() else 0) == expected_effects * 2


def test_provider_missing_result_on_fresh_run_never_adopts_prior_native_success(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('document')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    first = run_workflow(_args(path, providers, commands, _values()))
    first_view = load_dynamic_view(first.run_root)
    prior = (first.run_root / first_view['effects'][0]['result_path']).read_bytes()
    monkeypatch.setenv('DYNAMIC_PROVIDER_MODE', 'missing-bundle')
    second = run_workflow(_args(path, providers, commands, _values()))
    assert first.exit_code == 0 and second.exit_code == 1 and first.run_id != second.run_id
    second_view = load_dynamic_view(second.run_root)
    assert second_view['workflow_outputs'] is None and second_view['effects'][0]['status'] == 'failed'
    assert second_view['error']['code'] == 'provider_result_missing'
    assert not (second.run_root / second_view['effects'][0]['result_path']).exists()
    assert (first.run_root / first_view['effects'][0]['result_path']).read_bytes() == prior


def test_provider_predispatch_refusal_then_fresh_corrected_entry_dispatches(tmp_path, monkeypatch):
    path = _source(tmp_path, raw_message=True)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('document')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    refused = run_workflow(_args(path, providers, commands, _values(message=17)))
    assert refused.exit_code == 1 and load_dynamic_view(refused.run_root)['effects'] == []
    assert not (tmp_path / 'provider_events.jsonl').exists()
    corrected = run_workflow(_args(path, providers, commands, _values(message='corrected goal')))
    assert corrected.exit_code == 0 and corrected.run_id != refused.run_id
    event, = [json.loads(line) for line in (tmp_path / 'provider_events.jsonl').read_text().splitlines()]
    assert 'corrected goal' in event['prompt']


def test_provider_required_record_input_refuses_bool_int_missing_and_extra_before_allocation(tmp_path, monkeypatch):
    path = _source(tmp_path)
    text = path.read_text().replace('(export main)', '(export main) (defrecord Answer (ok Bool) (count Int))')
    text = text.replace('(defworkflow main ((note ', '(defworkflow main ((answer Answer) (note ')
    path.write_text(text)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('document')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    for answer in ({}, {'ok': 'true', 'count': 1}, {'ok': True, 'count': False},
                   {'ok': True, 'count': 1, 'extra': 2}):
        result = run_workflow(_args(path, providers, commands, _values(answer=answer)))
        assert result.exit_code == 2 and result.run_root is None
    assert not (tmp_path / 'provider_events.jsonl').exists()
    assert not (tmp_path / '.orchestrate/runs').exists()
    assert run_workflow(_args(path, providers, commands, _values(answer={'ok': True, 'count': 1}))).exit_code == 0


def test_missing_provider_binding_is_refused_even_in_an_unselected_body(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('document')
    providers, commands = _manifests(tmp_path)
    providers.write_text('{}')
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    for hidden in (False, True):
        if hidden:
            text = path.read_text().replace('(provider-result providers.review', '(if true (record (variant "REJECT") (reason "unused")) (provider-result providers.review')
            text = text.replace(':model model :effort effort))', ':model model :effort effort)))')
            path.write_text(text)
        result = run_workflow(_args(path, providers, commands, _values()))
        assert result.exit_code == 2 and result.run_root is None
        assert not (tmp_path / 'provider_events.jsonl').exists()
        assert not (tmp_path / '.orchestrate/runs').exists()


@pytest.mark.parametrize('raw', ['{', '{"variant":"APPROVE","ok":true,"ok":false,"score":7}',
                                  '{"variant":"APPROVE","ok":true,"score":NaN}'])
def test_E12b_malformed_duplicate_and_nonfinite_json_never_publish(tmp_path, monkeypatch, raw):
    path = _source(tmp_path)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('PRIVATE DOCUMENT')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    probe = tmp_path / 'bin/codex'
    probe.write_text(probe.read_text().replace('write_text(json.dumps(result), encoding="utf-8")',
        f'write_text({raw!r}, encoding="utf-8")'))
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, providers, commands, _values()))
    view = load_dynamic_view(result.run_root)
    assert result.exit_code == 1 and view['workflow_outputs'] is None
    assert [(row['effect_class'], row['status']) for row in view['effects']] == [('provider', 'failed')]
    assert view['error']['code'] == 'provider_result_invalid'
    assert 'PRIVATE DOCUMENT' not in json.dumps(view['error'])
    assert (result.run_root / view['effects'][0]['result_path']).read_text() == raw
    assert not (tmp_path / 'command_events.jsonl').exists()


@pytest.mark.parametrize('wrong', ['result-path', 'report-directory'])
def test_provider_wrong_result_channel_and_required_report_kind_never_publish(tmp_path, monkeypatch, wrong):
    path = _source(tmp_path)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('document')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    probe = tmp_path / 'bin/codex'
    text = probe.read_text()
    if wrong == 'result-path':
        text = text.replace('Path(event["result_path"]).write_text', 'Path("other-result.json").write_text')
    else:
        text = text.replace('report.write_text("provider report", encoding="utf-8")', 'report.mkdir()')
    probe.write_text(text)
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, providers, commands, _values()))
    view = load_dynamic_view(result.run_root)
    assert result.exit_code == 1 and view['workflow_outputs'] is None
    assert view['error']['code'] == ('provider_result_missing' if wrong == 'result-path' else 'provider_result_invalid')
    assert view['effects'][0]['status'] == 'failed'
    assert not (tmp_path / 'command_events.jsonl').exists()


@pytest.mark.parametrize('approved', [True, False])
def test_provider_decision_selects_lazy_pure_or_command_callable(tmp_path, monkeypatch, approved):
    _source(tmp_path)
    path = write_source(tmp_path, 'demo/main', f'''(import old/prompts :only (Decision NotePath ReportPath review))
      (export main)
      (defrecord CommandResult (literal String) (computed String) (opaque String) (first Int) (second Int))
      (define (accepted answer) (record (title "draft")))
      (define (rejected answer) (command-result probe :argv ("python" "{COMMAND_PROBE}"
        "finish" "rejected" (field answer "reason") "selected" 0 0) :returns CommandResult))
      (defworkflow main ((note NotePath) (message String) (report ReportPath) (model String) (effort String)) -> Value
        (let* ((answer (provider-result providers.review :prompt (review :note note :message message :report report)
          :model model :effort effort))
          (selected (if (= (field answer "variant") "APPROVE") accepted rejected))) (selected answer)))''')
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('DOC_A')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    if not approved:
        probe = tmp_path / 'bin/codex'
        probe.write_text(probe.read_text().replace('{"variant": "APPROVE", "ok": True, "score": 7}',
            '{"variant": "REJECT", "reason": "reject draft | clarity | DOC_A"}'))
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, providers, commands, _values(message='reject draft | clarity')))
    assert result.exit_code == 0
    view = load_dynamic_view(result.run_root)
    assert [row['effect_class'] for row in view['effects']] == (['provider'] if approved else ['provider', 'command'])
    if approved:
        assert result.workflow_outputs == {'title': 'draft'}
        assert not (tmp_path / 'command_events.jsonl').exists()
    else:
        assert result.workflow_outputs['computed'] == 'reject draft | clarity | DOC_A'
        event, = [json.loads(line) for line in (tmp_path / 'command_events.jsonl').read_text().splitlines()]
        assert event['args'][1] == 'reject draft | clarity | DOC_A'


def test_provider_document_symlink_refuses_before_launch(tmp_path, monkeypatch):
    path = _source(tmp_path, raw_note=True)
    (tmp_path / 'notes').mkdir()
    outside = tmp_path.parent / 'outside.md'
    outside.write_text('PRIVATE DOCUMENT')
    (tmp_path / 'notes/link.md').symlink_to(outside)
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, providers, commands, _values(note='notes/link.md')))
    view = load_dynamic_view(result.run_root)
    assert result.exit_code == 1 and view['effects'] == []
    assert 'PRIVATE DOCUMENT' not in json.dumps(view['error'])
    assert not (tmp_path / 'provider_events.jsonl').exists()


def test_admitted_provider_extern_alias_uses_definition_owner_binding(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("captured document", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    built = prepare_dynamic_program_bundle(FrontendBuildRequest(
        source_path=path,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        provider_externs_path=providers,
        command_boundaries_path=commands,
    ))
    tree = json.loads(built.program.artifact())
    node = _provider_node(tree["definitions"])
    assert node["provider"] == "codex"
    node["provider"] = "providers.review"
    admitted = DynamicProgram.from_artifact(json.dumps(tree))
    built = replace(built, program=admitted)

    exit_code, _run_id, run_root, outputs = execute_dynamic_run(
        built, _values(), workspace=tmp_path, workflow_path=path,
    )
    view = load_dynamic_view(run_root)

    assert exit_code == 0, view["error"]
    assert outputs == view["workflow_outputs"]
    assert [row["effect_class"] for row in view["effects"]] == ["provider", "command"]
    assert [row["status"] for row in view["effects"]] == ["completed", "completed"]
    assert (tmp_path / "provider_events.jsonl").is_file()


def test_admitted_provider_without_policy_uses_shared_empty_policy(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("captured document", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    built = prepare_dynamic_program_bundle(FrontendBuildRequest(
        source_path=path,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        provider_externs_path=providers,
        command_boundaries_path=commands,
    ))
    tree = json.loads(built.program.artifact())
    node = _provider_node(tree["definitions"])
    node["policy"] = None
    entries = tree["source_map"]["entries"]
    for pointer in list(entries):
        if "/policy/" in pointer:
            del entries[pointer]
    built = replace(built, program=DynamicProgram.from_artifact(json.dumps(tree)))

    exit_code, _run_id, run_root, outputs = execute_dynamic_run(
        built, _values(), workspace=tmp_path, workflow_path=path,
    )
    view = load_dynamic_view(run_root)

    assert exit_code == 0, view["error"]
    assert outputs == view["workflow_outputs"]
    assert [row["status"] for row in view["effects"]] == ["completed", "completed"]
    event = json.loads((tmp_path / "provider_events.jsonl").read_text().splitlines()[0])
    argv = event["argv"]
    assert argv[argv.index("--model") + 1] == "gpt-5.5"
    assert argv[argv.index("--config") + 1] == "model_reasoning_effort=high"
    assert "--dangerously-bypass-approvals-and-sandbox" in argv


def test_sourcefree_imported_provider_asset_uses_library_owner(tmp_path, monkeypatch):
    library = write_source(tmp_path, "lib/provider", '''
      (export invoke)
      (defunion Answer (APPROVE (ok Bool) (score Int)) (REJECT (reason String)))
      (define (invoke)
        (provider-result providers.review :prompt prompts.base :returns Answer))
    ''', budget=None)
    path = write_source(tmp_path, "demo/main", '''
      (import lib/provider :only (invoke))
      (export main)
      (defworkflow main () -> Value (invoke))
    ''')
    (library.parent / "prompt.md").write_text("LIBRARY ASSET SNAPSHOT", encoding="utf-8")
    (path.parent / "prompt.md").write_text("CALLER DECOY", encoding="utf-8")
    providers, _commands = _manifests(tmp_path)
    prompts = tmp_path / "prompts.json"
    prompts.write_text(json.dumps({"prompts.base": {"asset_file": "prompt.md"}}), encoding="utf-8")
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    built = prepare_dynamic_program_bundle(FrontendBuildRequest(
        source_path=path,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        provider_externs_path=providers,
        prompt_externs_path=prompts,
    ))
    node = _provider_node(json.loads(built.program.artifact())["definitions"])
    assert node["prompt_owner"] == {"asset_base": "lib", "module": "lib/provider"}
    library.unlink()
    path.unlink()

    exit_code, _run_id, run_root, outputs = execute_dynamic_run(
        built, {}, workspace=tmp_path, workflow_path=path,
    )
    view = load_dynamic_view(run_root)
    event = json.loads((tmp_path / "provider_events.jsonl").read_text().splitlines()[0])

    assert exit_code == 0, view["error"]
    assert "LIBRARY ASSET SNAPSHOT" in event["prompt"]
    assert "CALLER DECOY" not in event["prompt"]
    assert outputs == view["workflow_outputs"] == {
        "variant": "APPROVE", "ok": True, "score": 7,
    }


def test_public_provider_dryrun_never_launches_or_allocates(tmp_path, monkeypatch):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("document", encoding="utf-8")
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)

    args = _args(path, providers, commands, _values())
    args.dry_run = True
    result = run_workflow(args)

    assert result.exit_code == 0
    assert not (tmp_path / "provider_events.jsonl").exists()
    assert not (tmp_path / "command_events.jsonl").exists()
    assert not (tmp_path / ".orchestrate/runs").exists()


@pytest.mark.parametrize("dry_run", [False, True])
def test_provider_without_execute_permission_refuses_before_dispatch(
    tmp_path, monkeypatch, caplog, dry_run,
):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("document", encoding="utf-8")
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    binary_dir = tmp_path / "bin"
    (binary_dir / "codex").chmod(0o600)
    for name in ("python", "python3"):
        (binary_dir / name).symlink_to(sys.executable)
    monkeypatch.setenv("PATH", str(binary_dir))
    args = _args(path, providers, commands, _values())
    args.dry_run = dry_run

    with caplog.at_level(logging.ERROR):
        result = run_workflow(args)

    assert result.exit_code == 2 and result.run_root is None
    assert "command_interpreter_missing" in caplog.text
    assert "document" not in caplog.text
    assert not (tmp_path / "provider_events.jsonl").exists()
    assert not (tmp_path / "command_events.jsonl").exists()
    assert not (tmp_path / ".orchestrate/runs").exists()


@pytest.mark.parametrize(
    ("options", "values", "expected_code"),
    [
        ({"raw_message": True}, _values(message=17), "dynamic_boundary_invalid"),
        ({"bool_model": True}, _values(model=False), "dynamic_boundary_invalid"),
        ({"bad_effort": True}, _values(effort=False), "dynamic_boundary_invalid"),
        ({"raw_note": True}, _values(note="../private.md"), "dynamic_boundary_invalid"),
    ],
    ids=("fill-type", "model-type", "effort-type", "document-path"),
)
def test_provider_fill_policy_and_path_refusals_precede_dispatch(
    tmp_path, monkeypatch, options, values, expected_code,
):
    path = _source(tmp_path, **options)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("source note", encoding="utf-8")
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, providers, commands, values))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"] == []
    assert view["error"]["code"] == expected_code
    assert not (tmp_path / "provider_events.jsonl").exists()
    assert not (tmp_path / "command_events.jsonl").exists()
    assert "PRIVATE" not in json.dumps(view["error"])


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("wrong-bool", "provider_result_invalid"),
        ("inactive-field", "provider_result_invalid"),
        ("int64-overflow", "provider_result_invalid"),
        ("missing-report", "provider_result_invalid"),
        ("missing-bundle", "provider_result_missing"),
        ("stdout-bundle", "provider_result_missing"),
    ],
)
def test_provider_failure_never_publishes_success_or_runs_next_command(
    tmp_path, monkeypatch, mode, expected_code,
):
    path = _source(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/input.md").write_text("PRIVATE DOCUMENT", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    monkeypatch.setenv("DYNAMIC_PROVIDER_MODE", mode)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, providers, commands, _values()))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["workflow_outputs"] is None
    assert len(view["effects"]) == 1
    assert view["effects"][0]["effect_class"] == "provider"
    assert view["effects"][0]["status"] == "failed"
    assert view["error"]["code"] == expected_code
    assert view["error"]["metadata"]["call_stack"] == []
    assert view["error"]["metadata"]["call_context"] == []
    assert view["error"]["metadata"]["module"] == "demo/main"
    assert view["error"]["metadata"]["span"]
    if expected_code == "provider_result_invalid":
        assert view["error"]["metadata"]["violation_kinds"]
        assert view["error"]["metadata"]["expected_contract"]["kind"] == "union"
    assert "PRIVATE DOCUMENT" not in json.dumps(view["error"])
    assert "private-provider-stdout" not in json.dumps(view)
    assert not (tmp_path / "command_events.jsonl").exists()


def test_E04b_failed_provider_in_helper_keeps_safe_caller_context(tmp_path, monkeypatch):
    path = _source(tmp_path)
    expression = """(provider-result providers.review
                         :prompt (review :note note :message message :report report)
                         :model model :effort effort)"""
    source = path.read_text()
    assert expression in source
    source = source.replace(expression, '(dispatch note message report model effort)')
    source = source.replace('(defworkflow main',
        '(define (dispatch note message report model effort) (let* ((invoke (fn () ' + expression + '))) (invoke)))\n(defworkflow main')
    path.write_text(source)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('TOPSECRET DOCUMENT')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    monkeypatch.setenv('DYNAMIC_PROVIDER_MODE', 'wrong-bool')
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, providers, commands, _values(message='TOPSECRET MESSAGE')))
    assert result.exit_code == 1
    view = load_dynamic_view(result.run_root)
    assert view['error']['code'] == 'provider_result_invalid'
    metadata = view['error']['metadata']
    assert len(metadata['call_context']) == 2
    assert metadata['call_context'][0][2] == 'demo/main::dispatch'
    assert metadata['call_stack'] and metadata['span']
    assert metadata['effect_ordinal'] == 1
    assert 'TOPSECRET' not in json.dumps(view['error'])
    assert not (tmp_path / 'command_events.jsonl').exists()


def test_E09b_shared_provider_validation_consumes_one_captured_result(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated import commands as shared_commands

    path = _source(tmp_path)
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('document')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    _forbid_workflow_executor(monkeypatch)
    validate = shared_commands._validate_result_bytes
    replaced = []

    def replace_after_validation(node, captured, result_path, workspace_files, **kwargs):
        value = validate(node, captured, result_path, workspace_files, **kwargs)
        if node['class'] == 'provider':
            target = tmp_path / result_path
            target.write_text('{"broken":true}')
            replaced.append(target)
        return value

    monkeypatch.setattr(shared_commands, '_validate_result_bytes', replace_after_validation)
    result = run_workflow(_args(path, providers, commands, _values()))
    assert result.exit_code == 0 and result.workflow_outputs['computed'] == '7'
    assert len(replaced) == 1
    assert json.loads(replaced[0].read_text()) == {'broken': True}
    assert len((tmp_path / 'provider_events.jsonl').read_text().splitlines()) == 1
    assert [json.loads(line)['action'] for line in (tmp_path / 'command_events.jsonl').read_text().splitlines()] == ['finish']


@pytest.mark.parametrize('raw', [
    '{"variant":"APPROVE","ok":true,"score":"7","rows":[]}',
    '{"variant":"APPROVE","ok":true,"rows":[]}',
    '{"variant":"APPROVE","ok":true,"score":7,"rows":[],"extra":"PRIVATE"}',
    '{"variant":"APPROVE","ok":true,"score":7,"rows":[{"count":"PRIVATE"}]}',
])
def test_E09b_public_provider_rejects_missing_extra_integer_and_nested_fields(tmp_path, monkeypatch, raw):
    path = _source(tmp_path)
    prompt = tmp_path / 'old/prompts.orc'
    prompt.write_text(prompt.read_text().replace(
        '(defunion Decision (APPROVE (ok Bool) (score Int)) (REJECT (reason String)))',
        '(defrecord Row (count Int))\n(defunion Decision (APPROVE (ok Bool) (score Int) (rows List[Row])) (REJECT (reason String)))'))
    (tmp_path / 'notes').mkdir()
    (tmp_path / 'notes/input.md').write_text('PRIVATE DOCUMENT')
    (tmp_path / 'reports').mkdir()
    providers, commands = _manifests(tmp_path)
    _stage_tools(tmp_path, monkeypatch)
    probe = tmp_path / 'bin/codex'
    probe.write_text(probe.read_text().replace('json.dumps(result), encoding="utf-8"',
        repr(raw) + ', encoding="utf-8"'))
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, providers, commands, _values()))
    assert result.exit_code == 1
    view = load_dynamic_view(result.run_root)
    assert view['workflow_outputs'] is None
    assert [(row['effect_class'], row['status']) for row in view['effects']] == [('provider', 'failed')]
    assert view['error']['code'] == 'provider_result_invalid'
    assert 'PRIVATE' not in json.dumps(view['error'])
    assert (result.run_root / view['effects'][0]['result_path']).read_text() == raw
    assert not (tmp_path / 'command_events.jsonl').exists()
