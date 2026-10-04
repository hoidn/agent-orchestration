"""Public retry and read-only replay of command input documents."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_input_documents import (
    _bindings, _entry_args, _read_run, _run_body, _source, _write_consumer,
)
from tests.test_workflow_evaluated_command_template_scopes import _write_entry, _assert_two_public_resumes
from tests.test_workflow_evaluated_resume import _resume_cli, _snapshot
from tests.test_workflow_evaluated_input_document_contracts import _assert_committed_violation


def _retry_run(root):
    (root / "consumer.py").write_text('import json, os, sys\nfrom pathlib import Path\n'
        'p=Path("requests.json");rows=json.loads(p.read_text()) if p.exists() else []\n'
        'data=Path(sys.argv[-1]).read_bytes()\n'
        'rows.append({"argv":sys.argv[1:],"bytes":data.decode()});p.write_text(json.dumps(rows))\n'
        'print("attempt-document:"+sys.argv[-1],flush=True)\n'
        'if len(rows)==1: raise SystemExit(1)\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_bytes(data)\n')
    source = _write_entry(root, _source('(command-result emit :argv ("python" "consumer.py" "--named=ok")'
        ' :inputs ((text "é")) :returns Value)'))
    result = _run_cli(root, *_entry_args(root, source, _bindings(root)))
    assert result.returncode == 1, result.stderr
    authority, _ = _read_run(root)
    before = _snapshot(authority.run_root)
    resumed = _resume_cli(root, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    authority, snapshot = _read_run(root)
    _assert_retry_rows(root, authority, snapshot, before)
    return authority


def _assert_retry_rows(root, authority, snapshot, before):
    starts = [row.data for row in snapshot.entries if row.data["record"] == "started"]
    requests = json.loads((root / "requests.json").read_text())
    assert [row["attempt"] for row in starts] == [1, 2]
    assert starts[0]["input_parts"] == starts[1]["input_parts"]
    assert starts[0]["input_digest"] == starts[1]["input_digest"]
    assert requests[0]["argv"][:-1] == requests[1]["argv"][:-1] == ["--named=ok"]
    assert requests[0]["argv"][-1] != requests[1]["argv"][-1]
    assert requests[0]["bytes"] == requests[1]["bytes"] == '{"text":"é"}'
    _assert_preserved_attempt(authority, starts[0], before)
    assert snapshot.terminal.data["value"] == {"text": "é"}


def _assert_preserved_attempt(authority, first, before):
    old_root = Path(first["result_path"]).parent.as_posix() + "/"
    old_bytes = {key: value for key, value in before.items() if key.startswith(old_root)}
    after = _snapshot(authority.run_root)
    assert {key: value for key, value in after.items() if key.startswith(old_root)} == old_bytes
    assert old_bytes[old_root + "inputs.json"] == '{"text":"é"}'.encode()
    assert b"attempt-document:" in old_bytes[old_root + "stdout.txt"]
    assert old_root + "stderr.txt" in old_bytes


@pytest.mark.parametrize("delete", [False, True])
def test_public_retry_and_reuse_ignore_old_generated_document(tmp_path, monkeypatch, delete):
    authority = _retry_run(tmp_path)
    _, snapshot = _read_run(tmp_path)
    commit, = snapshot.active_commits.values()
    generated = authority.run_root / Path(commit.data["result_path"]).parent / "inputs.json"
    if delete:
        generated.unlink()
    else:
        generated.write_bytes(b"deliberately-corrupt-generated-input")
    _assert_two_public_resumes(tmp_path, tmp_path / "requests.json")
    before = _snapshot(tmp_path / ".orchestrate")
    calls = _observe_document_io(monkeypatch, tmp_path, _generated_input_tokens(tmp_path, authority, snapshot))
    monkeypatch.chdir(tmp_path)
    for _ in range(2):
        assert resume_workflow(authority.run_root.name) == 0
    assert calls == []
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert len(json.loads((tmp_path / "requests.json").read_text())) == 2


def _generated_input_tokens(workspace, authority, snapshot):
    return {(authority.run_root / Path(row.data["result_path"]).parent / "inputs.json").relative_to(workspace)
            for row in snapshot.entries if row.data["record"] == "started" and "document" in row.data["input_parts"]}


def _observe_document_io(monkeypatch, workspace, generated_tokens):
    calls = []
    generated_paths = {workspace / token for token in generated_tokens}

    def wrap(method, label, *, selected=False):
        def observed(*args, **kwargs):
            if not selected or args[0].workspace / Path(args[1]) in generated_paths:
                calls.append(label)
            return method(*args, **kwargs)
        return observed

    for name in ("read", "open_read", "create"):
        monkeypatch.setattr(WorkspaceFiles, name, wrap(getattr(WorkspaceFiles, name), name, selected=True))
    monkeypatch.setattr(runtime, "perform_command", wrap(runtime.perform_command, "dispatch"))
    monkeypatch.setattr(runtime, "repair_torn_tail", wrap(runtime.repair_torn_tail, "repair"))
    return calls


def _path_run(root, *, remove=False):
    _write_consumer(root)
    (root / "make.py").write_text('import json, os\nfrom pathlib import Path\n'
        'p=Path("artifacts/work/report.md");p.parent.mkdir(parents=True,exist_ok=True);p.write_text("report")\n'
        'Path("order.txt").open("a").write("make\\n")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(str(p)))\n')
    action = 'Path("artifacts/work/report.md").unlink()\n' if remove else ''
    (root / "later.py").write_text('import os\nfrom pathlib import Path\n' + action +
        'Path("order.txt").open("a").write("later\\n")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("0")\n')
    return _run_body(root, '''(let* ((report (command-result make :argv ("python" "make.py") :returns Report)))
      (command-result emit :argv ("python" "consumer.py"
        (command-result later :argv ("python" "later.py") :returns Int))
        :inputs ((trials (list (record Trial :report report)))) :returns Value))''',
        declarations='(defpath Report :kind relpath :under "artifacts/work" :must-exist true) (defrecord Trial (report Report))',
        names=("emit", "make", "later"))


def test_public_reached_document_failure_preserves_prior_operand_commits(tmp_path):
    result = _path_run(tmp_path, remove=True)
    assert result.returncode == 1, result.stderr
    assert "effect_input_invalid" in result.stderr
    assert not (tmp_path / "dispatches.jsonl").exists()
    _, snapshot = _read_run(tmp_path)
    assert len(snapshot.active_commits) == 2
    assert len([row for row in snapshot.entries if row.data["record"] == "started"]) == 2
    assert (tmp_path / "order.txt").read_text() == "make\nlater\n"


def _capture_refusal(monkeypatch):
    errors = []
    real = runtime._resume_refusal

    def refuse(error):
        errors.append(error)
        return real(error)

    monkeypatch.setattr(runtime, "_resume_refusal", refuse)
    return errors


def test_public_committed_document_input_violation_is_readonly(tmp_path, monkeypatch):
    result = _path_run(tmp_path)
    assert result.returncode == 0, result.stderr
    authority, snapshot = _read_run(tmp_path)
    report = tmp_path / "artifacts/work/report.md"
    report.unlink()
    with authority.memo_path.open("ab") as stream:
        stream.write(b'{"record":"unfinished"')
    (authority.run_root / "state.json").write_text('{"stale":true}')
    before = _snapshot(tmp_path / ".orchestrate")
    markers = [(tmp_path / name).read_bytes() for name in ("order.txt", "dispatches.jsonl")]
    cli = _resume_cli(tmp_path, authority.run_root.name)
    assert cli.returncode == 2, cli.stderr
    assert "effect_input_diverged" in cli.stderr
    _assert_refusal_evidence(tmp_path, before, markers)
    calls = _observe_document_io(monkeypatch, tmp_path, _generated_input_tokens(tmp_path, authority, snapshot))
    errors = _capture_refusal(monkeypatch)
    monkeypatch.chdir(tmp_path)
    assert resume_workflow(authority.run_root.name) == 2
    _assert_committed_violation(errors[0])
    _assert_refusal_evidence(tmp_path, before, markers)
    assert calls == []
    report.write_text("restored different bytes; referent is not C6 content identity")
    assert resume_workflow(authority.run_root.name) == 0
    assert calls == []
    _assert_refusal_evidence(tmp_path, before, markers)
    _assert_two_public_resumes(tmp_path, tmp_path / "order.txt", tmp_path / "dispatches.jsonl")


def _assert_refusal_evidence(root, before, markers):
    assert _snapshot(root / ".orchestrate") == before
    assert [(root / name).read_bytes() for name in ("order.txt", "dispatches.jsonl")] == markers
