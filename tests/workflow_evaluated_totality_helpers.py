"""Real public compile, committed pause and CLI recovery for totality fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun
from tests.test_workflow_evaluated_resume import _resume_cli, _snapshot
from tests.test_workflow_lisp_closed_program_compile_cli import _compile
from tests.test_workflow_lisp_generic_unions_runtime import _write_sources, _write_probe, _public_run_files, _log
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv
from tests.workflow_lisp_closed_program_corpus import entry_with_target
from tests.workflow_lisp_totality_matrix_sources import COMMANDS, FORMS, PROBE, program
from tests.workflow_lisp_totality_matrix_locality import axes, form_value
from tests.test_workflow_lisp_closed_program_corpus import _CONTROL_COMMANDS, _control_sources
from tests.test_workflow_lisp_closed_run_ref_placement import _path_form, _placement_source, _restricted_source
from tests.test_workflow_evaluated_run_ref import _assert_readonly_resumes
from tests.e2e.test_e2e_workflow_lisp_run_ref import _assert_complete_evidence_manifest
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module, syntax_head_name, syntax_node_datum


CONTROL_PROBE = '''import json, os, sys
from pathlib import Path
command, raw = sys.argv[1:3]
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(f"{command} {raw}\\n")
n = int(raw)
value = bool(n) if command == "check" else n + (command == "next-val")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(value))
'''

UNION_PROBE = '''import json, os, sys
from pathlib import Path
document = json.loads(Path(sys.argv[-1]).read_text())
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write("reflect " + document["choice"]["variant"] + "\\n")
Path(__file__).with_suffix(".document.json").write_text(json.dumps(document))
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(document["choice"]))
'''


REPRO_VALUES = {
    "repro:if-record-loop": {"n": 4},
    "repro:if-list-loop": {"n": 2, "parents": [{"n": 2}]},
    "repro:nested-effectful-argument": {"n": 27},
    "repro:pure-helper-exhaustion": {"turn": 1, "status": "loop_bound_exhausted"},
    "repro:pure-helper-exhaustion-top-level": {"turn": 1, "status": "loop_bound_exhausted"},
    "repro:call-result-in-if": {"flag": True, "note": "same"},
    "repro:scalar-call-loop-state": 1,
}


def cell_refusal(form, position):
    _, locality, base = axes(form)
    if base.startswith("repro:"):
        return None
    value = form_value(form, FORMS, "probe.py")
    if position == "match-subject" and value.type in ("Int", "Float", "Box"):
        return "match_subject_not_union"
    if position in ("record-field", "variant-field") and value.calls:
        return "effect_not_permitted"
    if position == "on-exhausted-value" and value.calls:
        return "loop_recur_contract_invalid"
    if position == "on-exhausted-value" and base == "pure-proc-call" and locality != "inline":
        return "loop_recur_contract_invalid"
    return None


def native_cell_value(form, position):
    _, _, base = axes(form)
    if base.startswith("repro:"):
        return REPRO_VALUES[base]
    value = form_value(form, FORMS, "probe.py")
    if position in ("match-subject", "variant-field") and value.type != "Float":
        return 7
    return value.value


def prepare_cell(root, form, position):
    probe = _write_probe(root, "probe", PROBE)
    sources = program(form, position, probe.as_posix())
    source = _write_sources(root, sources)
    source.write_text(entry_with_target(source, "2.35"))
    if cell_refusal(form, position) == "match_subject_not_union":
        source.write_text(source.read_text().replace(" None)", " ((HIT item) 7))"))
    return public_files(root, probe), probe


def prepare_control(root, case, route, *, replacement=None):
    probe = _write_probe(root, "probe", CONTROL_PROBE)
    sources, entry = _control_sources(case, route)
    if replacement is not None:
        before, after = replacement
        sources = {path: text.replace(before, after) for path, text in sources.items()}
    for name in _CONTROL_COMMANDS:
        before = f'(command-result {name} :argv ("python" "probe.py" n)'
        after = f'(command-result {name} :argv ("python" "probe.py" "{name}" n)'
        sources = {path: text.replace(before, after) for path, text in sources.items()}
    sources = {name: text.replace('"probe.py"', json.dumps(probe.as_posix()))
               for name, text in sources.items()}
    _write_sources(root, sources)
    files = public_files(root, probe, _CONTROL_COMMANDS)
    files["source"] = root / (entry.split("::")[0] + ".orc")
    return files, probe


def prepare_union(root, imported, inputs, *, generic=False):
    probe = _write_probe(root, "probe", UNION_PROBE)
    declarations = '''(defrecord Payload (n Int) (label String))
      (defunion Choice (LEFT (payload Payload)) (RIGHT (count Int)))'''
    if generic:
        declarations = declarations.replace('(defunion Choice (LEFT (payload Payload))',
                                             '(defunion Choice :forall (T) (LEFT (payload T))')
    helper = '(defworkflow echo ((value Choice)) -> Choice value)'
    if generic:
        helper = helper.replace('Choice', 'Choice[Payload]')
    body = f'''(let* ((native (call echo :value choice)))
      (command-result reflect :argv ("python" {json.dumps(probe.as_posix())})
        :inputs ((choice native) (nested nested)) :returns Choice))'''
    sources = {}
    type_name = "Choice[Payload]" if generic else "Choice"
    imports = ""
    if imported:
        sources["grt/helper.orc"] = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule grt/helper) (export Choice Payload echo) {declarations} {helper})'''
        imports = '(import grt/helper :as old)'
        helper = ''
        type_name = "old.Choice[old.Payload]" if generic else "old.Choice"
        body = body.replace('(call echo ', '(call old.echo ')
    sources["grt/entry.orc"] = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule grt/entry) {imports} (export run) {declarations} {helper}
      (defworkflow run ((choice {type_name}) (nested List[{type_name}])) -> {type_name} {body}))'''
    sources["grt/entry.orc"] = sources["grt/entry.orc"].replace(":returns Choice", ":returns " + type_name)
    _write_sources(root, sources)
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps(inputs, ensure_ascii=False))
    return public_files(root, probe, ("reflect",)), probe, input_file


def assert_source_refusal(files, result, code):
    (files["workspace"] / "compile.stdout").write_text(result.stdout)
    (files["workspace"] / "compile.stderr").write_text(result.stderr)
    (files["workspace"] / "compile.argv.json").write_text(json.dumps(result.args))
    assert result.returncode == 2
    assert f"[{code}]" in result.stderr, result.stderr
    location = re.search(r"^(.+\.orc):[0-9]+:[0-9]+:", result.stderr, re.MULTILINE)
    assert location is not None
    source = Path(location[1])
    assert source.is_relative_to(files["source_root"])
    assert source.is_file()


def public_files(root, probe, commands=COMMANDS):
    files = _public_run_files(root, {name: probe for name in commands})
    files["workspace"] = root
    rows = json.loads(files["commands"].read_text())
    for row in rows.values():
        row["closure"] = [probe.name]
    files["commands"].write_text(json.dumps(rows))
    return files


def public_run(files, input_file=None):
    args = _run_args(files, input_file=input_file)
    args.command_boundaries_file = str(files["commands"])
    args.emit_debug_yaml = False
    argv = [value for value in _run_argv(files) if value != "--emit-debug-yaml"]
    argv.extend(["--command-boundaries-file", str(files["commands"])])
    if input_file is not None:
        argv.extend(["--input-file", str(input_file)])
    if "refs" in files:
        args.run_ref_root = str(files["refs"])
        argv.extend(["--run-ref-root", str(files["refs"])])
    with patch.object(sys, "argv", argv):
        return run_workflow(args)


def prepare_placement(root, position, locality):
    parent = root / "parent"
    parent.mkdir()
    basic = position if position in ("body", "budget", "seed", "match", "map") else "body"
    source, revision = _placement_source(parent, basic, locality)
    if position != basic:
        replace_placement_body(source, revision, position, locality)
    probe = _write_probe(parent, "unused", "")
    files = public_files(parent, probe, ())
    files.update(source=source, refs=root / "refs")
    input_file = parent / "inputs.json"
    input_file.write_text(json.dumps({"payload": "placement"}))
    return files, input_file


def prepare_restricted_placement(root, position, locality):
    parent = root / "parent"
    parent.mkdir()
    source = _restricted_source(parent, position, locality)
    probe = _write_probe(parent, "unused", "")
    files = public_files(parent, probe, ())
    files.update(source=source, refs=root / "refs")
    return files


def replace_placement_body(source, revision, position, locality):
    perform = _path_form(revision)
    value = f'(let* ((child {perform})) child.value)' if locality == "direct" else '(invoke payload)'
    bodies = {
        "branch": f'(if true {value} "unselected")',
        "loop": f'''(loop/recur :max 1 :state (loop-state (n Int 0)) :on-exhausted "exhausted"
          (fn (outer) (done (loop/recur :max 1 :state (loop-state (n Int 0))
            :on-exhausted "exhausted" (fn (inner) (done {value}))))))''',
        "serial-map": f'''(let* ((first (list/map-effect ((item (list payload "second"))) :max 2
          {perform.replace(":payload payload", ":payload item") if locality == "direct" else "(invoke item)"})))
          (list/map ((item first)) {"item.value" if locality == "direct" else "item"}))''',
    }
    module = build_syntax_module(read_sexpr_file(source))
    workflow = next(form for form in module.forms if syntax_head_name(syntax_node_datum(form)) == "defworkflow")
    body = syntax_node_datum(workflow).items[-1]
    text = source.read_text()
    text = text[:body.span.start.offset] + bodies[position] + text[body.span.end.offset:]
    if position == "serial-map":
        result_type = syntax_node_datum(workflow).items[-2]
        text = text[:result_type.span.start.offset] + "List[String]" + text[result_type.span.end.offset:]
    source.write_text(text)


def assert_run_ref_commit(authority, entry):
    row = entry.data
    assert row["effect_class"] == "run_ref"
    assert row["input_digest"] == canonical_sha256(row["input_parts"])
    assert row["result_digest"] == canonical_sha256(row["value"])
    settled = row["proof"]["settled_result"]
    _assert_complete_evidence_manifest(Path(settled["workspace_path"]).parent, settlement=settled, mode="path")
    assert settled["visit"]["parent_run_id"] == authority.run_root.name
    assert row["attempt"] == 1
    assert json.loads(authority.memo_path.read_bytes()[entry.offset:].splitlines()[0]) == row


def exercise_placement(files, input_file, expected_value, count, monkeypatch):
    compile_public(files)
    monkeypatch.chdir(files["workspace"])
    pause = pause_public(files, monkeypatch, input_file)
    authority, before = checked_run(files["workspace"])
    assert before.terminal is None
    assert list(before.active_commits.values()) == [pause]
    assert_run_ref_commit(authority, pause)
    prefix = authority.memo_path.read_bytes()
    result = _resume_cli(files["workspace"], authority.run_root.name)
    assert result.returncode == 0, result.stderr
    authority, after = checked_run(files["workspace"])
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert_placement_final(authority, after, files["refs"], expected_value, count)
    _assert_readonly_resumes(files["workspace"], authority, files["refs"])


def assert_placement_final(authority, snapshot, refs, expected_value, count):
    assert snapshot.terminal.data == {"record": "terminal", "outcome": "completed", "value": expected_value}
    assert len(snapshot.active_commits) == len(snapshot.latest_starts) == len(snapshot.settlements) == count
    assert len(list(refs.rglob("child-request.json"))) == count
    ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    assert len([row for row in ledger.rows if row.stage == "committed"]) == count
    for entry in snapshot.active_commits.values():
        assert_run_ref_commit(authority, entry)


def checked_run(root):
    run_root, = (root / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    return authority, read_memo(authority.memo_path, site_classes(authority.program))


def compile_public(files):
    result = _compile(files)
    (files["workspace"] / "compile.stdout").write_text(result.stdout)
    (files["workspace"] / "compile.stderr").write_text(result.stderr)
    (files["workspace"] / "compile.argv.json").write_text(json.dumps(result.args))
    assert result.returncode == 0, result.stderr


def pause_public(files, monkeypatch, input_file=None):
    appended = []
    real_append = runtime.append_record

    def after_commit(path, record, **kwargs):
        entry = real_append(path, record, **kwargs)
        if record.get("record") == "committed":
            appended.append(entry)
            raise _InterruptedRun()
        return entry

    with monkeypatch.context() as patched:
        patched.setattr(runtime, "append_record", after_commit)
        with pytest.raises(_InterruptedRun):
            public_run(files, input_file)
    assert len(appended) == 1
    return appended[0]


def assert_commit_bytes(authority, entry):
    row = entry.data
    assert entry.offset >= 0
    memo_line = authority.memo_path.read_bytes()[entry.offset:].splitlines()[0]
    assert json.loads(memo_line) == row
    assert row["input_digest"] == canonical_sha256(row["input_parts"])
    result = (authority.run_root / row["result_path"]).read_bytes()
    assert row["result_digest"] == "sha256:" + hashlib.sha256(result).hexdigest()
    assert row["value"] == json.loads(result)
    assert row["attempt"] == 1


def assert_final(root, probe, expected_value, expected_calls):
    authority, snapshot = checked_run(root)
    assert snapshot.terminal.data == {"record": "terminal", "outcome": "completed", "value": expected_value}
    assert _log(probe) == expected_calls
    commits = list(snapshot.active_commits.values())
    assert len(commits) == len(expected_calls)
    assert len({entry.data["identity"] for entry in commits}) == len(commits)
    assert len(snapshot.latest_starts) == len(commits)
    for entry in commits:
        assert_commit_bytes(authority, entry)
    return authority, snapshot


def completed_resume(root, probe, authority):
    before = _snapshot(root / ".orchestrate")
    before_calls = _log(probe)
    resumed = _resume_cli(root, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert _snapshot(root / ".orchestrate") == before
    assert _log(probe) == before_calls


def exercise(root, files, probe, expected_value, expected_calls, monkeypatch, input_file=None):
    compile_public(files)
    monkeypatch.chdir(root)
    if expected_calls:
        pause = pause_public(files, monkeypatch, input_file)
        authority, snapshot = checked_run(root)
        assert snapshot.terminal is None
        assert len(snapshot.active_commits) == 1
        assert _log(probe) == expected_calls[:1]
        first, = snapshot.active_commits.values()
        assert first == pause
        assert_commit_bytes(authority, first)
        prefix = authority.memo_path.read_bytes()
        resumed = _resume_cli(root, authority.run_root.name)
        assert resumed.returncode == 0, resumed.stderr
        assert authority.memo_path.read_bytes().startswith(prefix)
    else:
        result = public_run(files, input_file)
        assert result.exit_code == 0
    authority, snapshot = assert_final(root, probe, expected_value, expected_calls)
    completed_resume(root, probe, authority)
    return authority, snapshot
