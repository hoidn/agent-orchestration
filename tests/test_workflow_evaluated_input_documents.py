"""Public compile/run/resume of attempt-owned typed command documents."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_command_template_scopes import (
    _assert_two_public_resumes, _write_entry, _write_inputs,
)
from tests.test_workflow_evaluated_command_templates import _write_boundaries


def _entry_args(root, source, boundaries):
    return (str(source), "--source-root", str(root / "src"),
            "--entry-workflow", "r12/entry::run", "--command-boundaries-file", str(boundaries))


def _compile(root, arguments):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-m", "orchestrator", "compile", *arguments],
                          cwd=root, env=env, capture_output=True, text=True)


def _read_run(root):
    run_root, = (root / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    return authority, read_memo(authority.memo_path, site_classes(authority.program))


def _write_consumer(root, *, inline=False):
    read = 'sys.argv[-1].encode()' if inline else 'Path(sys.argv[-1]).read_bytes()'
    (root / "consumer.py").write_text(
        'import json, os, sys\nfrom pathlib import Path\n'
        'data=' + read + '\n'
        'with Path("dispatches.jsonl").open("a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
        'Path("document.bin").write_bytes(data)\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(data)\n', encoding="utf-8")


def _rich_fixture(root):
    _write_consumer(root)
    source = _write_entry(root, '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) (export run)
      (defpath Asset :kind relpath :under "assets" :must-exist false)
      (defunion Choice (YES (asset Asset)) (NO))
      (defrecord Candidate (choices List[Choice]) (note Optional[String]))
      (defrecord Trial (candidate Candidate) (metadata Map[String,List[Int]]) (report Optional[Asset]))
      (defworkflow run ((candidate Candidate) (trials List[Trial]) (label String :default "défaut")) -> Value
        (command-result emit :argv ("python" "consumer.py" "extra" "--mode=report" "${inputs.label}")
          :inputs ((trials trials) (label label) (candidate candidate)) :returns Value)))''')
    candidate = {"choices": [{"variant": "YES", "asset": "assets/é.txt"}, {"variant": "NO"}], "note": None}
    trials = [{"candidate": candidate, "metadata": {"z": [2, 1], "a/b~c": []}, "report": None},
              {"candidate": {"choices": [], "note": "雪"}, "metadata": {}, "report": "assets/result.txt"}]
    inputs = _write_inputs(root, {"candidate": candidate, "trials": trials})
    boundaries = _write_boundaries(root, {"emit": {
        "stable_command": ["python", "consumer.py"], "closure": ["consumer.py"]}})
    return _entry_args(root, source, boundaries), inputs, {"trials": trials, "label": "défaut", "candidate": candidate}


def _assert_rich_document(root, payload):
    authority, snapshot = _read_run(root)
    assert snapshot.terminal.data == {"record": "terminal", "outcome": "completed", "value": payload}
    commit, = snapshot.active_commits.values()
    expected = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert (root / "document.bin").read_bytes() == expected
    requests = [json.loads(line) for line in (root / "dispatches.jsonl").read_text().splitlines()]
    argv, = requests
    assert argv[:-1] == ["extra", "--mode=report", "défaut"]
    input_path = authority.run_root / Path(commit.data["result_path"]).parent / "inputs.json"
    assert root / argv[-1] == input_path
    assert input_path.read_bytes() == expected
    assert input_path.stat().st_mode & 0o777 == 0o600
    return authority, commit, expected


def _assert_rich_parts(authority, commit, expected):
    parts = commit.data["input_parts"]
    assert parts["document"] == "sha256:" + hashlib.sha256(expected).hexdigest()
    assert parts["argv"] == canonical_sha256(["python", "consumer.py", "extra", "--mode=report", "défaut"])
    descriptors = dict(authority.program.tree["params"])
    contract = [[name, descriptors[name]] for name in ("trials", "label", "candidate")]
    assert parts["input_contract"] == canonical_sha256(contract)
    assert commit.data["input_digest"] == canonical_sha256(parts)
    assert commit.data["depends_on"] == []
    assert json.loads((authority.run_root / "run.json").read_text())["bound_inputs"]["label"] == "défaut"


def test_public_typed_document_round_trips(tmp_path):
    arguments, inputs, payload = _rich_fixture(tmp_path)
    compiled = _compile(tmp_path, arguments)
    assert compiled.returncode == 0, compiled.stderr
    result = _run_cli(tmp_path, *arguments, "--input-file", str(inputs))
    assert result.returncode == 0, result.stderr
    authority, commit, expected = _assert_rich_document(tmp_path, payload)
    _assert_rich_parts(authority, commit, expected)
    _assert_two_public_resumes(tmp_path, tmp_path / "dispatches.jsonl", tmp_path / "document.bin")


def _source(body, *, declarations="", params="", imports=""):
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/entry) {imports} (export run) {declarations}
      (defworkflow run ({params}) -> Value {body}))'''


def _bindings(root, names=("emit",)):
    return _write_boundaries(root, {name: {
        "stable_command": ["python", "consumer.py" if name == "emit" else name + ".py"],
        "closure": ["consumer.py" if name == "emit" else name + ".py"]} for name in names})


def _write_producer(root, name, value):
    (root / (name + ".py")).write_text(
        'import json, os\nfrom pathlib import Path\n'
        f'Path("order.txt").open("a").write("{name}\\n")\n'
        f'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({value!r}))\n')


def _run_body(root, body, *, declarations="", params="", inputs=None, imports="", names=("emit",)):
    source = _write_entry(root, _source(body, declarations=declarations, params=params, imports=imports))
    arguments = _entry_args(root, source, _bindings(root, names))
    extra = () if inputs is None else ("--input-file", str(_write_inputs(root, inputs)))
    return _run_cli(root, *arguments, *extra)


@pytest.mark.parametrize("present,certified", [(False, False), (True, False), (False, True)])
def test_public_empty_and_absent_documents_differ(tmp_path, present, certified):
    (tmp_path / "consumer.py").write_text('import json, os, sys\nfrom pathlib import Path\n'
        'value=None if len(sys.argv)==1 else json.loads(Path(sys.argv[-1]).read_bytes())\n'
        'Path("observed.json").write_text(json.dumps({"argv":sys.argv[1:],"value":value}))\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(value))\n')
    section = " :inputs ()" if present else ""
    source = _write_entry(tmp_path, _source('(command-result emit :argv ("python" "consumer.py")' + section + ' :returns Value)'))
    boundaries = _certified_bindings(tmp_path, ("a-b", "a_b"), names=("emit",)) if certified else _bindings(tmp_path)
    result = _run_cli(tmp_path, *_entry_args(tmp_path, source, boundaries))
    assert result.returncode == 0, result.stderr
    authority, snapshot = _read_run(tmp_path)
    commit, = snapshot.active_commits.values()
    observed = json.loads((tmp_path / "observed.json").read_text())
    assert snapshot.terminal.data["value"] == observed["value"] == ({} if present else None)
    documents = list(authority.run_root.rglob("inputs.json"))
    assert len(documents) == int(present)
    assert len(observed["argv"]) == int(present)
    assert ("document" in commit.data["input_parts"]) == present
    if present:
        assert documents[0].read_bytes() == b"{}"
        assert tmp_path / observed["argv"][0] == documents[0]
    _assert_two_public_resumes(tmp_path, tmp_path / "observed.json")


def _certified_bindings(root, fields, *, names=("emit", "one", "two")):
    from tests.test_workflow_lisp_command_adapters import _typed_adapter_manifest_payload

    row = _typed_adapter_manifest_payload()["normalize_result"]
    row.update(stable_command=["python", "consumer.py"], closure=["consumer.py"], output_type_name="Value",
        input_signature=[{"name": name, "type_name": "Int", "required": True, "transport_key": name} for name in fields])
    path = _bindings(root, names)
    rows = json.loads(path.read_text())
    rows["emit"] = row
    path.write_text(json.dumps(rows))
    return path


@pytest.mark.parametrize("certified", [False, True])
@pytest.mark.parametrize("fields", [("a-b", "a_b"), ("a_b", "a-b")])
@pytest.mark.parametrize("effects", [False, True])
def test_public_colliding_inputs_keep_distinct_values_and_each_effect_once(tmp_path, certified, fields, effects):
    _write_consumer(tmp_path, inline=certified)
    _write_producer(tmp_path, "one", 11)
    _write_producer(tmp_path, "two", 12)
    declarations = '''(defproc one () -> Int :effects ((uses-command one)) :lowering inline
      (command-result one :argv ("python" "one.py") :returns Int))
      (defproc two () -> Int :effects ((uses-command two)) :lowering inline
      (command-result two :argv ("python" "two.py") :returns Int))'''
    expressions = {"a-b": "(one)" if effects else "(+ n 1)", "a_b": "(two)" if effects else "(+ n 2)"}
    document = " ".join(f"({name} {expressions[name]})" for name in fields)
    mode = ":adapter emit" if certified else ':argv ("python" "consumer.py")'
    source = _write_entry(tmp_path, _source(f'(command-result emit {mode} :inputs ({document}) :returns Value)',
        declarations=declarations, params="(n Int)"))
    boundaries = _certified_bindings(tmp_path, fields) if certified else _bindings(tmp_path, ("emit", "one", "two"))
    result = _run_cli(tmp_path, *_entry_args(tmp_path, source, boundaries), "--input", "n=10")
    assert result.returncode == 0, result.stderr
    _assert_collision_run(tmp_path, certified, fields, effects)
    markers = [tmp_path / "dispatches.jsonl", tmp_path / "document.bin"]
    if effects:
        markers.append(tmp_path / "order.txt")
    _assert_two_public_resumes(tmp_path, *markers)


def _assert_collision_run(tmp_path, certified, fields, effects):
    authority, snapshot = _read_run(tmp_path)
    assert snapshot.terminal.data["value"] == {"a-b": 11, "a_b": 12}
    expected = [{"a-b": "one", "a_b": "two"}[name] for name in fields] if effects else []
    actual = (tmp_path / "order.txt").read_text().splitlines() if effects else []
    assert actual == expected
    assert len(snapshot.active_commits) == (3 if effects else 1)
    assert len((tmp_path / "dispatches.jsonl").read_text().splitlines()) == 1
    assert len(list(authority.run_root.rglob("inputs.json"))) == int(not certified)
    _assert_selected_dependencies(snapshot, 2 if effects else 0)
    _assert_document_bytes(tmp_path, {name: {"a-b": 11, "a_b": 12}[name] for name in fields}, sorted_keys=not certified)


def _assert_document_bytes(root, expected, *, sorted_keys=False):
    raw = json.dumps(expected, ensure_ascii=False, sort_keys=sorted_keys, separators=(",", ":")).encode()
    assert (root / "document.bin").read_bytes() == raw
    return raw


@pytest.mark.parametrize("first", ["argv", "inputs"])
@pytest.mark.parametrize("fields", [("text", "more"), ("more", "text")])
@pytest.mark.parametrize("flag", [False, True])
def test_public_operand_order_and_dependencies(tmp_path, first, fields, flag):
    _write_consumer(tmp_path)
    for name, value in (("number", 7), ("text", "é"), ("more", 9)):
        _write_producer(tmp_path, name, value)
    library = tmp_path / "src" / "r12" / "library.orc"
    library.parent.mkdir(parents=True)
    library.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule r12/library) (export text)
      (defproc text () -> String :effects ((uses-command text)) :lowering inline
        (command-result text :argv ("python" "text.py") :returns String)))''')
    declarations = '''(defproc number () -> Int :effects ((uses-command number)) :lowering inline
      (command-result number :argv ("python" "number.py") :returns Int))
      (defproc more () -> Int :effects ((uses-command more)) :lowering inline
      (command-result more :argv ("python" "more.py") :returns Int))'''
    argv = ':argv ("python" "consumer.py" (let* ((n (number))) n))'
    expressions = {"text": '(if flag (text) "unused")', "more": '(more)'}
    document = ':inputs (' + ' '.join(f'({name} {expressions[name]})' for name in fields) + ')'
    sections = f'{argv} {document}' if first == "argv" else f'{document} {argv}'
    result = _run_body(tmp_path, f'(command-result emit {sections} :returns Value)', declarations=declarations,
        params="(flag Bool)", inputs={"flag": flag}, imports="(import r12/library :only (text))",
        names=("emit", "number", "text", "more"))
    assert result.returncode == 0, result.stderr
    _, snapshot = _read_run(tmp_path)
    expected = [name for name in fields if name != "text" or flag]
    expected = ["number", *expected] if first == "argv" else [*expected, "number"]
    assert (tmp_path / "order.txt").read_text().splitlines() == expected
    assert snapshot.terminal.data["value"] == {"text": "é" if flag else "unused", "more": 9}
    _assert_selected_dependencies(snapshot, len(expected))
    _assert_two_public_resumes(tmp_path, tmp_path / "order.txt", tmp_path / "dispatches.jsonl")


def _assert_selected_dependencies(snapshot, producer_count):
    commits = list(snapshot.active_commits.values())
    assert len(commits) == producer_count + 1
    assert commits[-1].data["depends_on"] == sorted(row.data["identity"] for row in commits[:-1])
    assert all(row.data["depends_on"] == [] for row in commits[:-1])


def test_public_pure_division_precedes_later_operand_effect(tmp_path):
    _write_consumer(tmp_path)
    _write_producer(tmp_path, "number", 7)
    declarations = '''(defproc number () -> Int :effects ((uses-command number)) :lowering inline
      (command-result number :argv ("python" "number.py") :returns Int))'''
    result = _run_body(tmp_path,
        '(command-result emit :inputs ((quotient (/ 7.0 divisor))) :argv ("python" "consumer.py" (number)) :returns Value)',
        declarations=declarations, params="(divisor Float)", inputs={"divisor": 0}, names=("emit", "number"))
    assert result.returncode == 1, result.stderr
    assert not (tmp_path / "order.txt").exists()
    assert not (tmp_path / "dispatches.jsonl").exists()
    authority, snapshot = _read_run(tmp_path)
    assert not snapshot.active_commits
    assert not any(row.data["record"] == "started" for row in snapshot.entries)
    assert not list(authority.run_root.rglob("attempt-*"))


@pytest.mark.parametrize("capture", [False, True])
def test_public_document_only_import_and_capture_keep_dependency_and_r12(tmp_path, capture):
    _write_consumer(tmp_path)
    (tmp_path / "inc.py").write_text('import json, os, sys\nfrom pathlib import Path\n'
        'Path("producer-argv.json").write_text(json.dumps(sys.argv[1:]))\n'
        'Path("order.txt").open("a").write("inc\\n")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(int(sys.argv[1])+int(sys.argv[2])))\n')
    params = '(n Int) (state_root String :default "ROOT")'
    if capture:
        body = '''(let-proc (saved ((x Int)) -> Int :captures (n)
          (command-result inc :argv ("python" "inc.py" n x "${inputs.state_root}") :returns Int))
          (let* ((n 100))
            (command-result emit :argv ("python" "consumer.py")
              :inputs ((payload (invoke (proc-ref saved) 1))) :returns Value)))'''
        declarations = '(defproc invoke ((hook ProcRef[Int -> Int]) (x Int)) -> Int :effects () :lowering inline (hook x))'
        imports = ""
    else:
        helper = tmp_path / "src" / "r12" / "helper.orc"
        helper.parent.mkdir(parents=True)
        helper.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule r12/helper) (export produce)
          (defproc produce ((x Int)) -> Int :effects ((uses-command inc)) :lowering private-workflow
            (command-result inc :argv ("python" "inc.py" x 1 "${inputs.x}") :returns Int)))''')
        body = '(command-result emit :argv ("python" "consumer.py") :inputs ((payload (h.produce n))) :returns Value)'
        declarations, imports = "", '(import r12/helper :as h :only (produce))'
    result = _run_body(tmp_path, body, declarations=declarations, imports=imports,
        params=params, inputs={"n": 10}, names=("emit", "inc"))
    assert result.returncode == 0, result.stderr
    _, snapshot = _read_run(tmp_path)
    assert snapshot.terminal.data["value"] == {"payload": 11}
    assert json.loads((tmp_path / "producer-argv.json").read_text()) == ["10", "1", "ROOT" if capture else "10"]
    assert (tmp_path / "order.txt").read_text() == "inc\n"
    _assert_selected_dependencies(snapshot, 1)
    _assert_two_public_resumes(tmp_path, tmp_path / "order.txt", tmp_path / "producer-argv.json", tmp_path / "dispatches.jsonl")


@pytest.mark.parametrize("optional", [False, True])
def test_public_nested_certified_document_keeps_selected_signature_order(tmp_path, optional):
    _write_consumer(tmp_path, inline=True)
    source = _write_entry(tmp_path, _source('(command-result emit :adapter emit :inputs (' +
        ('(optional 7) ' if optional else '') + '(payload box)) :returns Value)',
        declarations='(defrecord Box (z List[Int]) (a String))', params='(box Box)'))
    boundaries = _certified_bindings(tmp_path, ("payload", "optional"), names=("emit",))
    rows = json.loads(boundaries.read_text())
    rows["emit"]["input_signature"][0]["type_name"] = "Box"
    rows["emit"]["input_signature"][1]["required"] = False
    boundaries.write_text(json.dumps(rows))
    box = {"z": [2, 1], "a": "é"}
    result = _run_cli(tmp_path, *_entry_args(tmp_path, source, boundaries),
        "--input-file", str(_write_inputs(tmp_path, {"box": box})))
    assert result.returncode == 0, result.stderr
    expected = {"payload": box} | ({"optional": 7} if optional else {})
    _assert_nested_inline(tmp_path, expected)
    _assert_two_public_resumes(tmp_path, tmp_path / "dispatches.jsonl", tmp_path / "document.bin")


def _assert_nested_inline(root, expected):
    authority, snapshot = _read_run(root)
    assert snapshot.terminal.data["value"] == expected
    raw = _assert_document_bytes(root, expected)
    commit, = snapshot.active_commits.values()
    assert commit.data["input_parts"]["document"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert "input_contract" not in commit.data["input_parts"]
    assert not list(authority.run_root.rglob("inputs.json"))
