"""Attempt-owned input documents at the evaluated command boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated import runtime
from tests.test_workflow_evaluated_command_lifecycle import _program, _publish, _started_snapshot


@pytest.mark.parametrize("inputs,payload", [(None, None), ("()", {}), ('((text "é"))', {"text": "é"})])
def test_attempt_publishes_document_exclusively_before_dispatch(tmp_path, inputs, payload):
    script = tmp_path / "consumer.py"
    script.write_text(
        'import json, os, sys\nfrom pathlib import Path\n'
        'value = None if len(sys.argv) == 1 else json.loads(Path(sys.argv[-1]).read_bytes())\n'
        'Path("observed.json").write_text(json.dumps({"argv": sys.argv[1:], "value": value}))\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5")\n', encoding="utf-8")
    section = "" if inputs is None else " :inputs " + inputs
    _, program = _program(tmp_path,
        '(command-result consume :argv ("python" "consumer.py")' + section + ' :returns Int)',
        bindings={"consume": "consumer.py"})
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        observed = json.loads((tmp_path / "observed.json").read_text())
        assert observed["value"] == payload
        snapshot = _started_snapshot(authority, program)
        commit = next(iter(snapshot.active_commits.values()))
        input_path = authority.run_root / Path(commit.data["result_path"]).parent / "inputs.json"
        if payload is None:
            assert observed["argv"] == []
            assert not input_path.exists()
        else:
            assert tmp_path / observed["argv"][-1] == input_path
            assert input_path.read_bytes() == json.dumps(payload, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode()
            assert input_path.stat().st_mode & 0o777 == 0o600


def test_external_bytes_and_contract_digest_ignore_attempt_path(tmp_path, monkeypatch):
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    from tests.test_workflow_evaluated_invalidate import _tree_bytes

    _write_retry_consumer(tmp_path)
    _, program = _program(tmp_path,
        '(command-result consume :argv ("python" "consumer.py" "--named=ok") :inputs ((text "é")) :returns Int)',
        bindings={"consume": "consumer.py"})
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (1, None)
        assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        rows = [entry.data for entry in _started_snapshot(authority, program).entries if entry.data["record"] == "started"]
        _assert_retry_inputs(tmp_path, authority, rows)
        old_input = authority.run_root / Path(rows[-1]["result_path"]).parent / "inputs.json"
        old_input.unlink()
        before = _tree_bytes(authority.run_root)
        real_read, real_create = WorkspaceFiles.read, WorkspaceFiles.create

        def read(owner, path, *args, **kwargs):
            if str(path).endswith("inputs.json"):
                pytest.fail("memo reuse read the generated input file")
            return real_read(owner, path, *args, **kwargs)

        def create(owner, path, *args, **kwargs):
            if str(path).endswith("inputs.json"):
                pytest.fail("memo reuse regenerated the input file")
            return real_create(owner, path, *args, **kwargs)

        monkeypatch.setattr(WorkspaceFiles, "read", read)
        monkeypatch.setattr(WorkspaceFiles, "create", create)
        for _ in range(2):
            assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        assert _tree_bytes(authority.run_root) == before
        assert len(json.loads((tmp_path / "requests.json").read_text())) == 2


def _write_retry_consumer(root):
    (root / "consumer.py").write_text('import json, os, sys\nfrom pathlib import Path\n'
        'p=Path("requests.json");rows=json.loads(p.read_text()) if p.exists() else []\n'
        'rows.append({"argv":sys.argv[1:],"bytes":Path(sys.argv[-1]).read_text()});p.write_text(json.dumps(rows))\n'
        'if len(rows)==1: raise SystemExit(1)\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5")\n')


def _assert_retry_inputs(root, authority, rows):
    from hashlib import sha256
    from orchestrator.workflow.run_ref.contracts import canonical_sha256

    requests = json.loads((root / "requests.json").read_text())
    assert [row["attempt"] for row in rows] == [1, 2]
    assert rows[0]["input_parts"] == rows[1]["input_parts"]
    assert rows[0]["input_digest"] == rows[1]["input_digest"]
    assert requests[0]["argv"][-1] != requests[1]["argv"][-1]
    assert requests[0]["argv"][:-1] == requests[1]["argv"][:-1] == ["--named=ok"]
    assert requests[0]["bytes"] == requests[1]["bytes"] == '{"text":"é"}'
    assert rows[0]["input_parts"]["document"] == "sha256:" + sha256('{"text":"é"}'.encode()).hexdigest()
    assert rows[0]["input_parts"]["input_contract"] == canonical_sha256([["text", {"kind": "primitive", "name": "String"}]])
    assert (authority.run_root / Path(rows[0]["result_path"]).parent / "inputs.json").read_bytes() == '{"text":"é"}'.encode()


@pytest.mark.parametrize("failure", ["existing", "symlink", "io"])
def test_document_publication_failure_preserves_reserved_attempt_without_dispatch(tmp_path, monkeypatch, failure):
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    (tmp_path / "consumer.py").write_text('import os\nfrom pathlib import Path\n'
        'Path("dispatched").touch()\nPath(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5")\n')
    _, program = _program(tmp_path,
        '(command-result consume :argv ("python" "consumer.py") :inputs () :returns Int)',
        bindings={"consume": "consumer.py"})
    create = WorkspaceFiles.create
    owners = []

    def obstruct(owner, path, data, **kwargs):
        if str(path) == "inputs.json":
            owners.append(owner)
            _obstruct_document(owner, failure, create, tmp_path)
        return create(owner, path, data, **kwargs)

    monkeypatch.setattr(WorkspaceFiles, "create", obstruct)
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (1, None)
        snapshot = _started_snapshot(authority, program)
        assert [entry.data["record"] for entry in snapshot.entries] == ["started", "failed", "terminal"]
        assert not snapshot.active_commits
        assert not (tmp_path / "dispatched").exists()
        assert owners[0].closed
        if failure == "existing":
            assert (owners[0].workspace / "inputs.json").read_bytes() == b"preserved"
        if failure == "symlink":
            assert (tmp_path / "untouched.txt").read_bytes() == b"preserved"


def _obstruct_document(owner, failure, create, root):
    if failure == "existing":
        create(owner, "inputs.json", b"preserved", exclusive=True)
    elif failure == "symlink":
        target = root / "untouched.txt"
        target.write_bytes(b"preserved")
        (owner.workspace / "inputs.json").symlink_to(target)
    else:
        raise OSError("injected publication failure")


def test_external_run_root_uses_workspace_relative_document_token(tmp_path):
    from orchestrator.workflow.evaluated.authority import publish_run_authority

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "consumer.py").write_text('import json, os, sys\nfrom pathlib import Path\n'
        'Path("token.txt").write_text(sys.argv[-1])\n'
        'assert json.loads(Path(sys.argv[-1]).read_bytes())=={"text":"é"}\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5")\n')
    _, program = _program(workspace,
        '(command-result consume :argv ("python" "consumer.py") :inputs ((text "é")) :returns Int)',
        bindings={"consume": "consumer.py"})
    run_root = tmp_path / "external-runs/run-1"
    with publish_run_authority(run_root, program, run_id="run-1", workflow_file="lifecycle.orc",
        workflow_checksum="sha256:" + "0" * 64, resume_request={"source_roots": [], "entry_workflow": None, "provider_externs_path": None,
            "prompt_externs_path": None, "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}}, bound_inputs={}) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=workspace) == (0, 5)
        token = (workspace / "token.txt").read_text()
        assert token.startswith("../external-runs/run-1/")
        assert (workspace / token).resolve().read_bytes() == '{"text":"é"}'.encode()
        assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=workspace) == (0, 5)


def test_document_fd_write_uses_retained_attempt_after_root_swap(tmp_path, monkeypatch):
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    (tmp_path / "consumer.py").write_text('from pathlib import Path\nPath("dispatched").touch()\n')
    _, program = _program(tmp_path,
        '(command-result consume :argv ("python" "consumer.py") :inputs () :returns Int)',
        bindings={"consume": "consumer.py"})
    create = WorkspaceFiles.create
    displaced = []

    def swap(owner, path, data, **kwargs):
        if str(path) != "inputs.json":
            return create(owner, path, data, **kwargs)
        original = owner.workspace.with_name("held-attempt")
        owner.workspace.rename(original)
        owner.workspace.mkdir()
        displaced.append((owner, original))
        create(owner, path, data, **kwargs)
        raise OSError("stop after writing by retained FD")

    monkeypatch.setattr(WorkspaceFiles, "create", swap)
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (1, None)
        owner, original = displaced[0]
        assert (original / "inputs.json").read_bytes() == b"{}"
        assert not (owner.workspace / "inputs.json").exists()
        assert owner.closed
        assert not (tmp_path / "dispatched").exists()
        assert [row.data["record"] for row in _started_snapshot(authority, program).entries] == ["started", "failed", "terminal"]


def test_imported_same_label_uses_exact_owner_protocol_after_source_deletion(tmp_path):
    from dataclasses import replace
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from tests.test_workflow_lisp_command_input_documents import _adapter_commands, _commands
    from tests.workflow_lisp_closed_program_helpers import install

    (tmp_path / "emit.py").write_text('import json, os, sys\nfrom pathlib import Path\n'
        'last=sys.argv[-1]; mode="file" if last.endswith("inputs.json") else "inline"\n'
        'payload=json.loads(Path(last).read_bytes()) if mode=="file" else json.loads(last)\n'
        'Path("protocols.jsonl").open("a").write(json.dumps({"mode":mode,"payload":payload,"argv":sys.argv[1:]})+"\\n")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("seen"))\n')
    certified = {name: replace(binding, closure=("emit.py",), stable_command=("python", "emit.py"))
        for name, binding in _adapter_commands(tmp_path, "Int").items()}
    external = {name: replace(binding, closure=("emit.py",)) for name, binding in _commands(tmp_path).items()}
    producer_path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule producer) (export run) (defworkflow run ((n Int)) -> String
        (command-result emit :adapter emit :inputs ((payload n)) :returns String)))''')
    producer = compile_typed_program(producer_path, entry_workflow="run", source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries=certified)
    consumer_path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule consumer) (export run) (defworkflow run () -> Int
        (let* ((ignored (command-result emit :argv ("python" "emit.py" "--extra")
          :inputs ((payload (call producer :n 7))) :returns String))) 5)))''')
    consumer = compile_typed_program(consumer_path, entry_workflow="run", source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries=external, imported_programs={"producer": producer})
    program = build_closed_program(consumer)
    producer_path.unlink()
    consumer_path.unlink()
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        rows = [json.loads(line) for line in (tmp_path / "protocols.jsonl").read_text().splitlines()]
        assert [(row["mode"], row["payload"]) for row in rows] == [("inline", {"body": 7}), ("file", {"payload": "seen"})]
        assert rows[1]["argv"][0] == "--extra"
        assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        assert len((tmp_path / "protocols.jsonl").read_text().splitlines()) == 2


def test_certified_nested_document_preserves_inline_signature_order(tmp_path):
    from dataclasses import replace
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from tests.test_workflow_lisp_command_input_documents import _adapter_commands, _source

    (tmp_path / "consume.py").write_text('import json, os, sys\nfrom pathlib import Path\n'
        'Path("inline.bin").write_bytes(sys.argv[-1].encode())\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("seen"))\n')
    commands = {name: replace(binding, stable_command=("python", "consume.py"), closure=("consume.py",))
        for name, binding in _adapter_commands(tmp_path, "Box").items()}
    source = tmp_path / "nested.orc"
    source.write_text(_source('''(let* ((ignored (command-result emit :adapter emit
        :inputs ((payload (record Box :z (list 2 1) :a "é"))) :returns String))) 5)''', returns="Int",
        declarations='(defrecord Box (z List[Int]) (a String))').replace('(defmodule cp/closed_elaboration)', '(defmodule nested)'))
    typed = compile_typed_program(source, entry_workflow="run", source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries=commands)
    program = build_closed_program(typed)
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        assert (tmp_path / "inline.bin").read_bytes() == '{"body":{"z":[2,1],"a":"é"}}'.encode()
        commit = next(iter(_started_snapshot(authority, program).active_commits.values()))
        assert not (authority.run_root / Path(commit.data["result_path"]).parent / "inputs.json").exists()
        assert "input_contract" not in commit.data["input_parts"]
        assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)


def _closure_program(root, body):
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.closed.build import build_closed_program

    (root / "consumer.py").write_text('import os\nfrom pathlib import Path\n'
        'Path("dispatched").touch()\nPath(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5")\n')
    (root / "danger.py").write_text('raise AssertionError("unreachable command dispatched")\n')
    source, _ = _program(root, body, bindings={"consume": "consumer.py", "danger": "danger.py"})
    typed = compile_typed_program(source, entry_workflow="run", source_roots=(root,), workspace_root=root,
        command_boundaries={"consume": ExternalToolBinding(name="consume", stable_command=("python", "consumer.py"), closure=("consumer.py",)),
            "danger": ExternalToolBinding(name="danger", stable_command=("python", "danger.py"), closure=(".",))})
    return build_closed_program(typed)


def test_document_closure_guard_is_local_to_reached_command(tmp_path):
    program = _closure_program(tmp_path, '''(if true
        (command-result consume :argv ("python" "consumer.py") :inputs () :returns Int)
        (command-result danger :argv ("python" "danger.py") :inputs () :returns Int))''')
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        snapshot = _started_snapshot(authority, program)
        assert len(snapshot.active_commits) == 1
        commit = next(iter(snapshot.active_commits.values()))
        assert {tuple(json.loads(key)[:2]) for key in commit.data["implementation_files"]} == {("workspace", "consumer.py")}
        assert (tmp_path / "dispatched").exists()


def test_document_command_rejects_closure_overlap_before_started(tmp_path, caplog):
    program = _closure_program(tmp_path,
        '(command-result danger :argv ("python" "danger.py") :inputs () :returns Int)')
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (1, None)
        snapshot = _started_snapshot(authority, program)
        assert not snapshot.latest_starts
        assert not (authority.run_root / "effects").exists()
        assert "runtime destination overlaps command closure" in caplog.text


@pytest.mark.parametrize("explicit_null", [False, True])
def test_checked_local_definition_null_configuration_uses_root_document_binding(tmp_path, explicit_null):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, canonical_digest

    (tmp_path / "consumer.py").write_text('import json, os, sys\nfrom pathlib import Path\n'
        'value=json.loads(Path(sys.argv[-1]).read_bytes())\nPath("observed.json").write_text(json.dumps(value))\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("5")\n')
    source, original = _program(tmp_path, '(emit 7)',
        declarations='''(defproc emit ((n Int)) -> Int :effects ((uses-command consume)) :lowering private-workflow
          (command-result consume :argv ("python" "consumer.py") :inputs ((n n)) :returns Int))''',
        bindings={"consume": "consumer.py"})
    tree = deepcopy(original.tree)
    owner, = [name for name, definition in tree["definitions"].items() if definition["key"][:3] == ["lifecycle", "procedure", "emit"]]
    assert "configuration" not in tree["definitions"][owner]
    if explicit_null:
        tree["definitions"][owner]["configuration"] = None
    resealed = ClosedProgram(tree=tree, sites=original.sites, digest=canonical_digest(tree))
    program = ClosedProgram.from_artifact(resealed.artifact())
    source.unlink()
    assert ("configuration" in program.tree["definitions"][owner]) is explicit_null
    with _publish(tmp_path, program) as authority:
        assert runtime.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        assert json.loads((tmp_path / "observed.json").read_text()) == {"n": 7}
        before = authority.memo_path.read_bytes()
        assert runtime.execute_pure_resume(authority, {}, run_id="run-1", workspace=tmp_path) == (0, 5)
        assert authority.memo_path.read_bytes() == before
