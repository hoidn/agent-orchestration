"""Public direct command execution for the dynamic Workflow Lisp profile."""

import json
import os
from pathlib import Path
import shutil

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow.dynamic.state import load_dynamic_view
from tests.test_workflow_dynamic_source import write_source


PROBE = "tests/fixtures/workflow_lisp/dynamic/command_probe.py"


def _args(path, manifest, *inputs):
    return create_parser().parse_args([
        "run", str(path), "--command-boundaries-file", str(manifest), *inputs,
    ])


def _external_manifest(path, *names, closure=()):
    path.write_text(json.dumps({
        name: {
            "kind": "external_tool",
            "stable_command": ["python", PROBE],
            "closure": list(closure),
        }
        for name in names
    }))
    return path


def _certified_manifest(path):
    path.write_text(json.dumps({"adapter": {
        "kind": "certified_adapter",
        "stable_command": ["python", PROBE, "adapter"],
        "input_contract": {"type": "object"},
        "output_type_name": "Echo",
        "effects": ["structured_result"],
        "path_safety": {"kind": "workspace_relpath"},
        "source_map_behavior": "step",
        "fixture_ids": ["dynamic_command"],
        "negative_fixture_ids": ["dynamic_command_invalid"],
        "behavior_class": "structured_result",
        "input_signature": [
            {"name": "text", "type_name": "String", "required": True, "transport_key": "text"},
            {"name": "count", "type_name": "Int", "required": True, "transport_key": "count"},
        ],
        "artifact_contracts": ["dynamic_command"],
        "state_writes": [],
        "error_codes": ["dynamic_command_invalid"],
        "owner_module": "demo/main",
        "replacement_path": None,
        "invocation_protocol": "json_object_positional_arg",
        "closure": [],
    }}))
    return path


def _stage_probe(workspace):
    destination = workspace / PROBE
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).parent / "fixtures/workflow_lisp/dynamic/command_probe.py", destination)


def _forbid_workflow_executor(monkeypatch):
    from orchestrator.workflow.executor import WorkflowExecutor

    def fail(*_args, **_kwargs):
        raise AssertionError("dynamic command execution constructed WorkflowExecutor")

    monkeypatch.setattr(WorkflowExecutor, "__init__", fail)


def test_public_command_runs_once_in_operand_order_with_native_values(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", '''
      (export main)
      (defrecord Echo (literal String) (computed String) (opaque String) (first Int) (second Int))
      (defworkflow main ((flag Bool) (opaque String)) -> Echo
        (command-result probe
          :argv ("python" "tests/fixtures/workflow_lisp/dynamic/command_probe.py"
            "finish" true flag opaque
            (command-result probe :argv ("python" "tests/fixtures/workflow_lisp/dynamic/command_probe.py" "first") :returns Int)
            (command-result probe :argv ("python" "tests/fixtures/workflow_lisp/dynamic/command_probe.py" "second") :returns Int))
          :returns Echo))
    ''', budget=20)
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest, "--input", "flag=false", "--input", "opaque=${inputs.hidden}"))

    assert result.exit_code == 0
    assert result.workflow_outputs == {
        "literal": "True",
        "computed": "false",
        "opaque": "${inputs.hidden}",
        "first": 11,
        "second": 12,
    }
    calls = [json.loads(line) for line in (tmp_path / "command_events.jsonl").read_text().splitlines()]
    assert [row["action"] for row in calls] == ["first", "second", "finish"]
    assert calls[-1]["args"] == ["True", "false", "${inputs.hidden}", "11", "12"]

    view = load_dynamic_view(result.run_root)
    assert view["status"] == "completed"
    assert [row["ordinal"] for row in view["effects"]] == [1, 2, 3]
    assert [row["status"] for row in view["effects"]] == ["completed"] * 3
    assert view["steps_used"] == view["budget"] == 20
    first_attempt = result.run_root / "effects/1/attempt-1"
    assert not (first_attempt / "inputs.json").exists()
    header = json.loads((result.run_root / "run.json").read_text())
    assert Path(calls[0]["executable"]).resolve() == Path(header["interpreters"]["python"]["path"]).resolve()


def test_public_command_operand_budget_exhaustion_prevents_dispatch(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "{PROBE}" "first") :returns Int))
    ''', budget=1)
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"] == []
    assert view["error"]["code"] == "dynamic_budget_exhausted"
    assert not (tmp_path / "command_events.jsonl").exists()


def test_public_external_document_preserves_empty_record_presence(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defrecord Empty)
      (defworkflow main () -> Int
        (command-result probe
          :argv ("python" "{PROBE}" "document")
          :inputs () :input-type Empty :returns Int))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 0
    assert result.workflow_outputs == 0
    view = load_dynamic_view(result.run_root)
    attempt = result.run_root / view["effects"][0]["result_path"].rsplit("/", 1)[0]
    assert (attempt / "inputs.json").read_bytes() == b"{}"
    calls = [json.loads(line) for line in (tmp_path / "command_events.jsonl").read_text().splitlines()]
    assert len(calls) == 1
    assert calls[0]["action"] == "document" and calls[0]["document"] == {}
    assert calls[0]["args"] == [(attempt / "inputs.json").relative_to(tmp_path).as_posix()]


def test_public_external_document_uses_declared_record_and_native_output(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defrecord Input (text String) (count Int))
      (defworkflow main ((text String) (count Int)) -> Int
        (command-result probe :argv ("python" "{PROBE}" "document")
          :inputs ((text text) (count count)) :input-type Input :returns Int))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest, "--input", "text=hello", "--input", "count=4"))

    assert result.exit_code == 0 and result.workflow_outputs == 4
    view = load_dynamic_view(result.run_root)
    attempt = result.run_root / view["effects"][0]["result_path"].rsplit("/", 1)[0]
    assert (attempt / "inputs.json").read_bytes() == b'{"count":4,"text":"hello"}'
    calls = [json.loads(line) for line in (tmp_path / "command_events.jsonl").read_text().splitlines()]
    assert calls[0]["document"] == {"count": 4, "text": "hello"}
    assert calls[0]["args"][-1] == (attempt / "inputs.json").relative_to(tmp_path).as_posix()


def test_public_certified_adapter_keeps_signature_order_and_inline_document(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defrecord Echo (text String) (count Int))
      (define (consume answer) (record (text (field answer "text")) (count (field answer "count"))))
      (defworkflow main ((text String) (count Int)) -> Echo
        (consume (command-result adapter :adapter adapter
          :inputs ((count count) (text text)) :returns Echo)))
    ''')
    manifest = _certified_manifest(tmp_path / "commands.json")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    dry = _args(path, manifest, "--input", "text=é", "--input", "count=4")
    dry.dry_run = True
    assert run_workflow(dry).exit_code == 0
    assert not (tmp_path / "command_events.jsonl").exists()
    assert not (tmp_path / ".orchestrate/runs").exists()

    result = run_workflow(_args(path, manifest, "--input", "text=é", "--input", "count=4"))

    assert result.exit_code == 0
    assert result.workflow_outputs == {"text": "é", "count": 4}
    calls = [json.loads(line) for line in (tmp_path / "command_events.jsonl").read_text().splitlines()]
    assert len(calls) == 1
    assert calls[0]["action"] == "adapter"
    assert calls[0]["args"] == ['{"text":"é","count":4}']
    assert calls[0]["document"] == {"text": "é", "count": 4}
    assert Path(calls[0]["executable"]).resolve() == Path(json.loads((result.run_root / "run.json").read_text())["interpreters"]["python"]["path"]).resolve()


def test_UC08_effect_operands_run_once_in_order_and_share_one_budget(tmp_path, monkeypatch):
    prefix = '''(export main) (defrecord Echo (text String) (count Int))
      (define (emit text count) (command-result adapter :adapter adapter
        :inputs ((count count) (text text)) :returns Echo))'''
    append = '(list/append (list (emit "first" 1)) (emit "second" 2))'
    update = '''(let* ((base (record (first 0) (second 0) (keep "same")))
      (updated (record-update base (first (field (emit "third" 10) "count"))
        (second (field (emit "fourth" 20) "count")))))
      (list (field updated "first") (field updated "second") (field updated "keep")
        (field base "first") (field base "second")))'''
    manifest = _certified_manifest(tmp_path / 'commands.json')
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)
    for body, expected in ((append, [{'text': 'first', 'count': 1}, {'text': 'second', 'count': 2}]),
                           (update, [10, 20, 'same', 0, 0])):
        path = write_source(tmp_path, 'demo/main', prefix + f'(defworkflow main () -> Value {body})')
        result = run_workflow(_args(path, manifest))
        assert result.exit_code == 0
        view = load_dynamic_view(result.run_root)
        assert view['workflow_outputs'] == expected
        assert [(row['ordinal'], row['status']) for row in view['effects']] == [(1, 'completed'), (2, 'completed')]
    calls = [json.loads(line) for line in (tmp_path / 'command_events.jsonl').read_text().splitlines()]
    assert [row['document']['count'] for row in calls] == [1, 2, 10, 20]
    assert [row['args'] for row in calls] == [[f'{{"text":"{text}","count":{count}}}'] for text, count in (
        ('first', 1), ('second', 2), ('third', 10), ('fourth', 20))]
    (tmp_path / 'command_events.jsonl').unlink()
    path = write_source(tmp_path, 'demo/main', prefix + f'(defworkflow main () -> Value {append})', budget=12)
    result = run_workflow(_args(path, manifest))
    view = load_dynamic_view(result.run_root)
    assert result.exit_code == 1 and view['error']['code'] == 'dynamic_budget_exhausted'
    assert view['steps_used'] == 12 and len(view['effects']) == 1
    assert view['effects'][0]['status'] == 'completed'
    assert len((tmp_path / 'command_events.jsonl').read_text().splitlines()) == 1


def test_UC09_fail_keeps_reason_context_and_skips_unselected_work(tmp_path, monkeypatch):
    path = write_source(tmp_path, 'demo/main', f'''(export main)
      (define (chosen) (fail "chosen_reason"))
      (defworkflow main () -> Int (if true (chosen)
        (command-result probe :argv ("python" "{PROBE}" "first") :returns Int)))''')
    manifest = _external_manifest(tmp_path / 'commands.json', 'probe')
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, manifest))
    view = load_dynamic_view(result.run_root)
    assert result.exit_code == 1 and view['effects'] == []
    assert view['error']['code'] == 'dynamic_explicit_failure'
    assert view['error']['metadata']['reason'] == 'chosen_reason'
    assert view['error']['metadata']['call_context'] and view['steps_used'] > 0
    assert not (tmp_path / 'command_events.jsonl').exists()


def test_certified_binding_absence_mismatch_and_runtime_inputs_refuse_before_dispatch(tmp_path, monkeypatch):
    path = write_source(tmp_path, 'demo/main', '''(export main)
      (defrecord Echo (text String) (count Int))
      (defworkflow main ((raw Value)) -> Echo (command-result adapter :adapter adapter
        :inputs ((text "native") (count raw)) :returns Echo))''')
    manifest = _certified_manifest(tmp_path / 'commands.json')
    valid = manifest.read_text()
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)
    for contents in ('{}', valid.replace('"output_type_name": "Echo"', '"output_type_name": "String"')):
        manifest.write_text(contents)
        result = run_workflow(_args(path, manifest, '--input', 'raw=1'))
        assert result.exit_code == 2 and result.run_root is None
        assert not (tmp_path / '.orchestrate/runs').exists()
    manifest.write_text(valid)
    result = run_workflow(_args(path, manifest, '--input-file', _write_input(tmp_path, {'raw': 'SECRET'})))
    view = load_dynamic_view(result.run_root)
    assert result.exit_code == 1 and view['effects'] == []
    assert 'SECRET' not in json.dumps(view['error'])
    assert not (tmp_path / 'command_events.jsonl').exists()


def test_E01b_command_result_uses_the_same_closure_boundary(tmp_path, monkeypatch):
    path = write_source(tmp_path, 'demo/main', f'''(export main)
      (define (more) (command-result probe :argv ("python" "{PROBE}" "second") :returns Int))
      (defworkflow main () -> Int (let* ((value (command-result probe
        :argv ("python" "{PROBE}" "first") :returns Int))
        (selected (if (= value 11) more (fn () (fail "wrong_branch"))))) (selected)))''')
    manifest = _external_manifest(tmp_path / 'commands.json', 'probe')
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)
    result = run_workflow(_args(path, manifest))
    assert result.exit_code == 0 and result.workflow_outputs == 12
    assert [json.loads(line)['action'] for line in (tmp_path / 'command_events.jsonl').read_text().splitlines()] == ['first', 'second']


def test_E08b_failed_leaf_keeps_its_output_without_rollback_or_no_repeat_claim(tmp_path, monkeypatch):
    path = write_source(tmp_path, 'demo/main', f'''(export main) (defworkflow main () -> Int
      (command-result probe :argv ("python" "{PROBE}" "leak") :returns Int))''')
    manifest = _external_manifest(tmp_path / 'commands.json', 'probe')
    _stage_probe(tmp_path)
    probe = tmp_path / PROBE
    probe.write_text(probe.read_text().replace('raise SystemExit(7)',
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("11")\n    raise SystemExit(7)'))
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)
    results = [run_workflow(_args(path, manifest)) for _ in range(2)]
    assert results[0].run_root != results[1].run_root
    for result in results:
        view = load_dynamic_view(result.run_root)
        assert result.exit_code == 1 and view['workflow_outputs'] is None
        assert [row['status'] for row in view['effects']] == ['failed']
        assert (result.run_root / view['effects'][0]['result_path']).read_text() == '11'
    assert len((tmp_path / 'command_events.jsonl').read_text().splitlines()) == 2


def test_E09a_leaf_input_contracts_refuse_bad_values_before_launch(tmp_path, monkeypatch):
    from copy import deepcopy

    path = write_source(tmp_path, 'demo/main', f'''(export main)
      (defrecord Item (count Int))
      (defunion Decision (ACCEPTED (confidence Int)) (REJECTED (reason String)))
      (defrecord Input (flag Bool) (number Int) (ratio Float)
        (items List[Item]) (decisions List[Decision]))
      (defrecord Envelope (payload Input))
      (defworkflow main ((raw Value)) -> Float (command-result probe
        :argv ("python" "{PROBE}" "document")
        :inputs ((payload raw)) :input-type Envelope :returns Float))''')
    manifest = _external_manifest(tmp_path / 'commands.json', 'probe')
    _stage_probe(tmp_path)
    probe = tmp_path / PROBE
    probe.write_text(probe.read_text().replace('row["document"].get("count", 0)', 'row["document"]["payload"]["ratio"]'))
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)
    valid = {'flag': True, 'number': 3, 'ratio': 3, 'items': [{'count': 7}],
             'decisions': [{'variant': 'ACCEPTED', 'confidence': 2}]}
    cases = []
    missing = deepcopy(valid)
    missing.pop('number')
    cases.extend((missing, {**valid, 'extra': 'unexpected'}, {**valid, 'number': True},
                  {**valid, 'number': '3'}, {**valid, 'ratio': '3.0'},
                  {**valid, 'items': [{'count': '7'}]},
                  {**valid, 'decisions': [{'variant': 'ACCEPTED', 'confidence': 2, 'reason': 'inactive'}]}))
    for value in cases:
        result = run_workflow(_args(path, manifest, '--input-file', _write_input(tmp_path, {'raw': value})))
        view = load_dynamic_view(result.run_root)
        assert result.exit_code == 1 and view['effects'] == []
        assert view['error']['code'] == 'effect_input_invalid'
        assert 'unexpected' not in json.dumps(view['error'])
    source = path.read_text()
    path.write_text(source.replace(':inputs ((payload raw))',
        ':inputs ((payload (record-update raw ("ratio" (fn () 3.0)))))'))
    refused = run_workflow(_args(path, manifest, '--input-file', _write_input(tmp_path, {'raw': valid})))
    assert refused.exit_code == 1
    assert load_dynamic_view(refused.run_root)['effects'] == []
    assert load_dynamic_view(refused.run_root)['error']['code'] == 'effect_input_invalid'
    path.write_text(source)
    assert not (tmp_path / 'command_events.jsonl').exists()
    result = run_workflow(_args(path, manifest, '--input-file', _write_input(tmp_path, {'raw': valid})))
    assert result.exit_code == 0 and result.workflow_outputs == 3.0
    event, = [json.loads(line) for line in (tmp_path / 'command_events.jsonl').read_text().splitlines()]
    assert event['document']['payload']['ratio'] == 3.0


def test_public_document_schema_failure_settles_no_effect_and_hides_values(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defrecord Input (text String))
      (defworkflow main ((raw Value)) -> Int
        (command-result probe :argv ("python" "{PROBE}" "document")
          :inputs ((text raw)) :input-type Input :returns Int))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest, "--input-file", _write_input(tmp_path, {"raw": {"secret": "private-value"}})))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"] == []
    assert view["error"]["code"] == "effect_input_invalid"
    assert "private-value" not in json.dumps(view["error"])
    assert not (tmp_path / "command_events.jsonl").exists()


def test_public_document_path_failure_settles_no_effect_and_never_dispatches(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defpath Note :kind relpath :under "notes" :must-exist true)
      (defrecord Input (note Note))
      (defworkflow main ((raw Value)) -> Int
        (command-result probe :argv ("python" "{PROBE}" "document")
          :inputs ((note (field raw "note"))) :input-type Input :returns Int))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest, "--input-file", _write_input(tmp_path, {"raw": {"note": "../secret.txt"}})))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"] == []
    assert view["error"]["code"] == "effect_input_invalid"
    assert "secret.txt" not in json.dumps(view["error"])
    assert not (tmp_path / "command_events.jsonl").exists()


def test_public_document_type_error_redacts_runtime_map_keys(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defrecord Input (payload Map[String,List[Int]]))
      (defworkflow main ((raw Value)) -> Int
        (command-result probe :argv ("python" "{PROBE}" "document")
          :inputs ((payload raw)) :input-type Input :returns Int))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest, "--input-file", _write_input(
        tmp_path, {"raw": {"TOPSECRET-RUNTIME-KEY": ["private-value"]}},
    )))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"] == []
    assert view["error"]["code"] == "effect_input_invalid"
    assert view["error"]["metadata"]["violation_kinds"] == ["invalid_transportable_value"]
    assert view["error"]["metadata"]["expected_contract"] == {
        "kind": "map",
        "key": {"kind": "primitive", "name": "String"},
        "value": {
            "kind": "list",
            "item": {"kind": "primitive", "name": "Int"},
        },
    }
    assert view["error"]["metadata"]["field_path"] == "/payload/*/0"
    assert "TOPSECRET-RUNTIME-KEY" not in json.dumps(view["error"])
    assert "private-value" not in json.dumps(view["error"])
    assert not (tmp_path / "command_events.jsonl").exists()


def test_public_command_rechecks_closure_before_success_publication(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "{PROBE}" "mutate") :returns Int))
    ''')
    (tmp_path / "mutable.txt").write_text("pinned", encoding="utf-8")
    manifest = _external_manifest(tmp_path / "commands.json", "probe", closure=("mutable.txt",))
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"][0]["status"] == "failed"
    assert view["error"]["code"] == "command_closure_written"
    assert view["workflow_outputs"] is None
    assert (tmp_path / "mutable.txt").read_text(encoding="utf-8") == "changed"
    assert len((tmp_path / "command_events.jsonl").read_text().splitlines()) == 1


def test_public_command_ignores_generated_bytecode_in_declared_closure_directory(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''(export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "{PROBE}" "mutate") :returns Int))''')
    closure = tmp_path / "closure"
    closure.mkdir()
    (closure / "cache_module.py").write_text("value = 42\n", encoding="utf-8")
    manifest = _external_manifest(tmp_path / "commands.json", "probe", closure=("closure",))
    _stage_probe(tmp_path)
    probe = tmp_path / PROBE
    text = probe.read_text(encoding="utf-8")
    assert 'elif action == "mutate":' in text
    probe.write_text(text.replace(
        "import os\n", "import os\nimport py_compile\n",
    ).replace(
        'elif action == "mutate":',
        'elif action == "mutate":\n    py_compile.compile("closure/cache_module.py", doraise=True)',
    ), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 0 and result.workflow_outputs == 42
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "completed" and view["effects"][0]["status"] == "completed"
    bytecode = list((closure / "__pycache__").glob("*.pyc"))
    assert len(bytecode) == 1 and bytecode[0].is_file()
    event, = [json.loads(line) for line in (tmp_path / "command_events.jsonl").read_text().splitlines()]
    assert event["action"] == "mutate"


def test_public_command_closure_disjointness_precedes_effect_allocation(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "{PROBE}" "document") :returns Int))
    ''')
    (tmp_path / ".orchestrate").mkdir()
    manifest = _external_manifest(tmp_path / "commands.json", "probe", closure=(".orchestrate",))
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"] == []
    assert view["error"]["code"] == "command_closure_unreadable"
    assert not (tmp_path / "command_events.jsonl").exists()


def test_public_command_failure_settles_row_without_exit_output_metadata(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "{PROBE}" "leak") :returns Int))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"][0]["status"] == "failed"
    assert view["error"]["code"] == "command_exit_nonzero"
    assert "private-stdout-value" not in json.dumps(view["error"])
    assert "private-stderr-value" not in json.dumps(view["error"])
    assert view["workflow_outputs"] is None


def test_public_command_failure_keeps_completed_prefix_and_stops_later_dispatch(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defworkflow main () -> Int
        (let* ((prefix (command-result probe
                        :argv ("python" "{PROBE}" "first") :returns Int)))
          (let* ((failed (command-result probe
                               :argv ("python" "{PROBE}" "leak") :returns Int)))
            (command-result probe :argv ("python" "{PROBE}" "second") :returns Int))))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    results = [run_workflow(_args(path, manifest)) for _ in range(2)]

    assert all(result.exit_code == 1 and result.run_root is not None for result in results)
    assert results[0].run_root != results[1].run_root
    views = [load_dynamic_view(result.run_root) for result in results]
    assert all(view["status"] == "failed" and view["workflow_outputs"] is None for view in views)
    assert all([row["status"] for row in view["effects"]] == ["completed", "failed"] for view in views)
    actions = [json.loads(line)["action"] for line in (tmp_path / "command_events.jsonl").read_text().splitlines()]
    assert actions == ["first", "leak", "first", "leak"]
    assert all("second" not in json.dumps(view) for view in views)


def test_public_command_failure_keeps_call_context_without_argument_values(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (define (invoke secret)
        (command-result probe :argv ("python" "{PROBE}" "leak" secret) :returns Int))
      (defworkflow main ((secret String)) -> Int (invoke secret))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest, "--input", "secret=TOPSECRET"))

    assert result.exit_code == 1 and result.run_root is not None
    error = load_dynamic_view(result.run_root)["error"]
    assert error["metadata"]["call_stack"]
    assert error["metadata"]["call_context"]
    assert "TOPSECRET" not in json.dumps(error)


def test_public_command_rejects_raw_wrong_root_without_disclosing_value(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "{PROBE}" "wrong-root") :returns Int))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"][0]["status"] == "failed"
    assert view["workflow_outputs"] is None
    assert "private-result-value" not in json.dumps(view["error"])
    attempt = result.run_root / "effects/1/attempt-1"
    assert json.loads((attempt / "result.json").read_text()) == "private-result-value"


def test_public_record_result_error_keeps_safe_violation_and_expected_schema(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defrecord Output (count Int))
      (defworkflow main () -> Output
        (command-result probe :argv ("python" "{PROBE}" "wrong-record") :returns Output))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"][0]["status"] == "failed"
    assert view["workflow_outputs"] is None
    error = view["error"]
    assert error["code"] == "dynamic_command_result_invalid"
    assert error["metadata"]["violation_kinds"] == ["invalid_transportable_value"]
    assert error["metadata"]["expected_contract"] == {
        "kind": "record",
        "name": "Output",
        "fields": [{"name": "count", "type": {"kind": "primitive", "name": "Int"}}],
    }
    assert "private-result-value" not in json.dumps(error)


def test_public_command_cannot_publish_from_a_replaced_attempt_directory(tmp_path, monkeypatch):
    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "{PROBE}" "replace") :returns Int))
    ''')
    (tmp_path / "mutable.txt").write_text("pinned")
    manifest = _external_manifest(tmp_path / "commands.json", "probe", closure=("mutable.txt",))
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)

    result = run_workflow(_args(path, manifest))

    assert result.exit_code == 1 and result.run_root is not None
    view = load_dynamic_view(result.run_root)
    assert view["status"] == "failed" and view["effects"][0]["status"] == "failed"
    assert view["error"]["code"] == "command_result_missing"
    assert view["workflow_outputs"] is None
    attempt = result.run_root / "effects/1/attempt-1"
    assert json.loads((attempt / "result.json").read_text()) == 99
    assert (attempt.parent / "moved-attempt/result.json").exists() is False


def test_interrupted_command_closes_attempt_descriptor_without_settling_row(tmp_path, monkeypatch):
    import pytest
    import orchestrator.workflow.dynamic.runtime as runtime

    path = write_source(tmp_path, "demo/main", f'''
      (export main)
      (defworkflow main () -> Int
        (command-result probe :argv ("python" "{PROBE}" "first") :returns Int))
    ''')
    manifest = _external_manifest(tmp_path / "commands.json", "probe")
    _stage_probe(tmp_path)
    monkeypatch.chdir(tmp_path)
    _forbid_workflow_executor(monkeypatch)
    captured = {}

    def interrupt(*_args, attempt_files, **_kwargs):
        captured["fd"] = attempt_files.root_fd
        raise KeyboardInterrupt("interrupted performer")

    monkeypatch.setattr(runtime, "perform_command", interrupt)

    with pytest.raises(KeyboardInterrupt, match="interrupted performer") as caught:
        run_workflow(_args(path, manifest))

    assert caught.value.__traceback__ is not None
    with pytest.raises(OSError):
        os.fstat(captured["fd"])
    run_root, = (tmp_path / ".orchestrate/runs").iterdir()
    state = json.loads((run_root / "state.json").read_text())
    assert state["status"] == "running" and state["current_effect"] == 1
    assert state["effects"][0]["status"] == "running"


def _write_input(workspace, value):
    path = workspace / "input.json"
    path.write_text(json.dumps(value))
    return str(path)
