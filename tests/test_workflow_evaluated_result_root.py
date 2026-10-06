"""Immutable header `result_root`: publication, resume and view dispositions for X4."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

import pytest

from orchestrator.cli.commands.invalidate import invalidate_run
from orchestrator.cli.commands.report import report_workflow
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.state import StateManager
from orchestrator.workflow.evaluated.authority import (
    RunAuthorityError, load_run_authority, load_run_header, publish_run_authority,
)
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import MemoError, read_memo
from orchestrator.workflow.evaluated.views import load_evaluated_view
from orchestrator.workflow.run_ref import child
from tests import test_workflow_evaluated_run_ref_caller as caller
from tests import workflow_evaluated_totality_helpers as totality
from tests.test_workflow_evaluated_cli import _build, _run_cli
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_providers import _orchestrate_snapshot, _requests, workspace_relative
from tests.test_workflow_evaluated_public_context import (
    PROVIDER_PATH_SOURCE, _assert_provider_commit, _provider_files,
)
from tests.test_workflow_evaluated_run_ref_root import _completed_run
from tests.test_workflow_run_ref_child import _build_path_fixture
from tests.workflow_evaluated_context_helpers import public_context_run
from tests.workflow_evaluated_totality_helpers import (
    checked_run, compile_public, pause_public, public_run,
)


NESTED = ".orchestrate/runs/custom"
_SENTINEL = "x4-result-root-sentinel"
_MANIFESTS =("providers.json", "prompts.json", "commands.json", "inputs.json", "requests.jsonl")

TWO_PROVIDER_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
  (defrecord Result (ok Bool))
  (defrecord Projection (bundle ResultBundle))
  (defworkflow run ((message String)) -> Projection
    (let* ((a (provider-result providers.review :prompt prompts.base
               :inputs (message) :model "chosen-model" :effort "low" :returns Result))
           (b (provider-result providers.review :prompt prompts.base
               :inputs (a) :model "chosen-model" :effort "low" :returns Result)))
      (record Projection :bundle (provider-bundle-path b :as ResultBundle)))))'''

ECHO_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
  (defrecord Result (ok Bool))
  (defrecord Projection (bundle ResultBundle) (echoed String))
  (defworkflow run ((message String)) -> Projection
    (let* ((r (provider-result providers.review :prompt prompts.base
               :inputs (message) :model "chosen-model" :effort "low" :returns Result))
           (p (provider-bundle-path r :as ResultBundle))
           (c (command-result echo :argv ("python" "echo.py" message) :returns String)))
      (record Projection :bundle p :echoed c))))'''

ECHO = '''import json, os, sys
from pathlib import Path
with open("echo.log", "a") as log:
    log.write(sys.argv[1] + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(sys.argv[1]))
'''


def _x4_workspace(root, monkeypatch, source=PROVIDER_PATH_SOURCE, commands=None):
    files, inputs = _provider_files(root, source)
    if commands is not None:
        files["commands"].write_text(json.dumps(commands))
    compile_public(files)
    monkeypatch.setenv("PATH", str(root / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(root)
    return files, inputs


def _x4_cli(files, inputs, *extra):
    root = files["workspace"]
    return _run_cli(root, str(files["source"]), "--source-root", str(root),
                    "--provider-externs-file", str(files["providers"]),
                    "--prompt-externs-file", str(files["prompts"]),
                    "--command-boundaries-file", str(files["commands"]),
                    "--input-file", str(inputs), *extra)


def _checked(run_root):
    authority = load_run_authority(run_root)
    return authority, read_memo(authority.memo_path, site_classes(authority.program))


def _only_run(runs_root):
    (run_root,) = runs_root.iterdir()
    return run_root


def _pop_result_root(run_root):
    header = json.loads((run_root / "run.json").read_text())
    header.pop("result_root")
    (run_root / "run.json").write_text(json.dumps(header))


def _guard_path_io(monkeypatch, forbidden):
    originals = {name: getattr(os, name) for name in ("open", "stat", "lstat")}
    resolve = Path.resolve

    def check(path):
        if not isinstance(path, int) and forbidden(os.fsdecode(os.fspath(path))):
            pytest.fail(f"forbidden path IO: {path!r}")

    def guarded(name):
        def call(path, *args, **kwargs):
            check(path)
            return originals[name](path, *args, **kwargs)
        return call

    def guarded_resolve(path, *args, **kwargs):
        check(path)
        return resolve(path, *args, **kwargs)

    for name in originals:
        monkeypatch.setattr(os, name, guarded(name))
    monkeypatch.setattr(Path, "resolve", guarded_resolve)


def _forbidden_memo_read(*args, **kwargs):
    pytest.fail("memo was read before header preflight finished")


def _x4_evidence(root):
    return _orchestrate_snapshot(root), (root / "requests.jsonl").read_bytes()


def _assert_resumes_readonly(observe, run_id, count=2, **options):
    before = observe()
    for _ in range(count):
        assert resume_workflow(run_id, **options) == 0
        assert observe() == before


def _assert_refused(caplog, run_root, code, **options):
    before = _tree_bytes(run_root)
    caplog.clear()
    assert resume_workflow(run_root.name, **options) == 2
    assert f"[{code}]" in caplog.text
    assert _tree_bytes(run_root) == before


def _assert_nested_bundle(root, run_root):
    authority, snapshot = _checked(run_root)
    (commit,) = snapshot.active_commits.values()
    bundle = f"{NESTED}/{run_root.name}/{commit.data['result_path']}"
    assert authority.header["result_root"] == f"{NESTED}/{run_root.name}"
    assert snapshot.terminal.data["value"] == {"bundle": bundle}
    assert bundle == _assert_provider_commit(root, authority, commit)
    assert bundle == os.path.relpath(run_root / commit.data["result_path"], root)
    env = _requests(root)[0]["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
    assert os.path.isabs(env) and bundle == workspace_relative(env, root)
    assert "sha256:" + sha256((root / bundle).read_bytes()).hexdigest() == commit.data["result_digest"]


@pytest.mark.parametrize("paused", (False, True))
def test_nested_state_dir_returns_actual_workspace_path(tmp_path, monkeypatch, paused):
    files, inputs = _x4_workspace(tmp_path, monkeypatch)
    if paused:
        with monkeypatch.context() as adapted:
            adapted.setattr(totality, "public_run", lambda f, i=None: public_context_run(f, i, NESTED))
            totality.pause_public(files, adapted, inputs)
        assert resume_workflow(_only_run(tmp_path / NESTED).name, state_dir=NESTED) == 0
    else:
        result = _x4_cli(files, inputs, "--state-dir", NESTED)
        assert result.returncode == 0, result.stderr
    run_root = _only_run(tmp_path / NESTED)
    _assert_nested_bundle(tmp_path, run_root)
    _assert_resumes_readonly(lambda: _x4_evidence(tmp_path), run_root.name, state_dir=NESTED)


def test_source_free_view_load_reads_no_recipe_or_result(tmp_path, monkeypatch, capsys):
    files, inputs = _x4_workspace(tmp_path, monkeypatch)
    assert public_run(files, inputs).exit_code == 0
    authority, snapshot = checked_run(tmp_path)
    expected = snapshot.terminal.data["value"]
    for path in [*tmp_path.rglob("*.orc"), *(tmp_path / name for name in _MANIFESTS)]:
        path.unlink()
    (authority.run_root / "effects").rename(tmp_path / "effects-aside")
    capsys.readouterr()
    _guard_path_io(monkeypatch, lambda spelling: spelling.endswith((".orc", "result.json", *_MANIFESTS))
                   or "effects/" in spelling)
    assert load_evaluated_view(authority.run_root)["workflow_outputs"] == expected
    assert report_workflow(authority.run_root.name, runs_root=str(authority.run_root.parent), format="json") == 0
    assert json.loads(capsys.readouterr().out)["run"]["workflow_outputs"] == expected


def test_whole_workspace_relocation_keeps_result_root(tmp_path, monkeypatch):
    files, inputs = _x4_workspace(tmp_path / "ws", monkeypatch)
    assert public_run(files, inputs).exit_code == 0
    authority, snapshot = checked_run(tmp_path / "ws")
    run_id, header = authority.run_root.name, authority.header_path.read_bytes()
    bundle = snapshot.terminal.data["value"]["bundle"]
    moved = tmp_path / "moved"
    shutil.move(tmp_path / "ws", moved)
    monkeypatch.chdir(moved)
    moved_root = moved / ".orchestrate" / "runs" / run_id
    before = _orchestrate_snapshot(moved)
    assert (moved_root / "run.json").read_bytes() == header
    assert resume_workflow(run_id) == 0
    assert _orchestrate_snapshot(moved) == before
    assert load_evaluated_view(moved_root)["workflow_outputs"]["bundle"] == bundle


def test_paused_workspace_relocation_dispatches_under_the_moved_root(tmp_path, monkeypatch):
    files, inputs = _x4_workspace(tmp_path / "ws", monkeypatch, source=TWO_PROVIDER_SOURCE)
    pause_public(files, monkeypatch, inputs)
    run_id = checked_run(tmp_path / "ws")[0].run_root.name
    moved = tmp_path / "moved"
    shutil.move(tmp_path / "ws", moved)
    monkeypatch.chdir(moved)
    monkeypatch.setenv("PATH", str(moved / "bin") + os.pathsep + os.environ["PATH"])
    assert resume_workflow(run_id) == 0
    _, snapshot = checked_run(moved)
    second = max(snapshot.active_commits.values(), key=lambda entry: entry.offset).data
    requests = _requests(moved)
    assert len(requests) == 2
    env, prompt = requests[1]["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], requests[1]["prompt"]
    relative = f".orchestrate/runs/{run_id}/{second['result_path']}"
    assert env == os.path.join(moved, relative)
    assert relative in prompt and env not in prompt


def _assert_failed_at_form(run_root, snapshot, joined):
    terminal = snapshot.terminal.data
    assert (terminal["outcome"], terminal["code"]) == ("failed", "pure_expr_operand_type_mismatch")
    state = json.loads((run_root / "state.json").read_text())
    assert (state["status"], state["memo_offset"]) == ("failed", len((run_root / "memo.jsonl").read_bytes()))
    view = load_evaluated_view(run_root)
    assert (view["status"], view["error"]["code"], view["workflow_outputs"]) == (
        "failed", "pure_expr_operand_type_mismatch", None)
    for message in (terminal["message"], view["error"]["message"]):
        assert joined in message and '"ok"' not in message


def _assert_provider_invalidation_reruns(run_root, workspace, state_dir, commit):
    record = invalidate_run(run_root.name, commit.data["identity"], state_dir=state_dir)
    assert (record["record"], record["from_commit"]) == ("invalidated", commit.offset)
    view = json.loads((run_root / "state.json").read_text())
    assert (view["status"] != "failed", view["error"], view["next_effect"]) == (True, None, commit.data["identity"])
    assert resume_workflow(run_root.name, state_dir=state_dir) == 1
    _, after = _checked(run_root)
    terminals = [entry.data["outcome"] for entry in after.entries if entry.data["record"] == "terminal"]
    (rerun,) = after.active_commits.values()
    assert (terminals, rerun.data["attempt"], len(_requests(workspace))) == (["failed"] * 2, 2, 2)
    return after, rerun


@pytest.mark.parametrize("state_dir", ("../state", "state"))
def test_run_root_outside_orchestrate_runs_fails_at_form(tmp_path, monkeypatch, caplog, state_dir):
    workspace = tmp_path / "ws"
    files, inputs = _x4_workspace(workspace, monkeypatch)
    result = _x4_cli(files, inputs, "--state-dir", state_dir)
    assert result.returncode == 1, result.stderr
    run_root = _only_run((workspace / state_dir).resolve())
    result_root = f"{state_dir}/{run_root.name}"
    assert load_run_header(run_root)["result_root"] == result_root
    _, snapshot = _checked(run_root)
    (commit,) = snapshot.active_commits.values()
    assert commit.data["result_path"].startswith("effects/")
    assert (run_root / commit.data["result_path"]).is_file() and len(_requests(workspace)) == 1
    _assert_failed_at_form(run_root, snapshot, f"{result_root}/{commit.data['result_path']}")
    _assert_refused(caplog, run_root, "pure_expr_operand_type_mismatch", state_dir=state_dir)
    after, rerun = _assert_provider_invalidation_reruns(run_root, workspace, state_dir, commit)
    _assert_failed_at_form(run_root, after, f"{result_root}/{rerun.data['result_path']}")


@pytest.mark.parametrize("state_dir", ("../state", "state"))
def test_programs_without_x4_run_under_any_state_dir(tmp_path, monkeypatch, state_dir):
    workspace = tmp_path / "ws"
    source, _program = _build(workspace)
    result = _run_cli(workspace, str(source), "--input", "score=0.75", "--state-dir", state_dir)
    assert result.returncode == 0, result.stderr
    run_root = _only_run((workspace / state_dir).resolve())
    assert load_run_header(run_root)["result_root"] == f"{state_dir}/{run_root.name}"
    monkeypatch.chdir(workspace)
    before = _tree_bytes(run_root)
    for _ in range(2):
        assert resume_workflow(run_root.name, state_dir=state_dir) == 0
        assert _tree_bytes(run_root) == before


@pytest.mark.parametrize("state_dir", ("../state", None))
def test_changed_result_root_relationship_refuses_before_memo(tmp_path, monkeypatch, caplog, state_dir):
    workspace = tmp_path / "ws"
    source, _program = _build(workspace)
    extra = ("--state-dir", state_dir) if state_dir else ()
    assert _run_cli(workspace, str(source), "--input", "score=0.75", *extra).returncode == 0
    runs_root = (workspace / state_dir).resolve() if state_dir else workspace / ".orchestrate" / "runs"
    run_root = _only_run(runs_root)
    monkeypatch.chdir(workspace)
    _assert_resumes_readonly(lambda: _tree_bytes(run_root), run_root.name, count=1, state_dir=str(runs_root))
    elsewhere = tmp_path / "other" / "sub"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr("orchestrator.workflow.evaluated.runtime.read_memo", _forbidden_memo_read)
    _assert_refused(caplog, run_root, "resume_result_root_changed", state_dir=str(runs_root))
    _assert_refused(caplog, run_root, "resume_run_ref_root_changed", state_dir=str(runs_root),
                    run_ref_root=str(tmp_path / "other-refs"))
    assert "resume_result_root_changed" not in caplog.text


def _assert_malformed_refusals(run_root):
    loaders = (lambda: load_run_header(run_root), lambda: invalidate_run(run_root.name, "unused"),
               lambda: load_evaluated_view(run_root))
    for load in loaders:
        with pytest.raises(RunAuthorityError) as refused:
            load()
        assert refused.value.code == "memo_inconsistent"
    assert resume_workflow(run_root.name) == 2


def test_malformed_result_root_refuses_every_loader_without_path_io(tmp_path, monkeypatch, caplog):
    run_root = _completed_run(tmp_path)
    run_id, sentinel = run_root.name, _SENTINEL
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text())
    exact = ("", f"/proc/self/fd/7/{run_id}", "\x00")
    malformed = (*exact, f"/{sentinel}/{run_id}", f".orchestrate/runs/{sentinel}//{run_id}",
                 f".orchestrate/runs/{sentinel}/{run_id}/", f"./.orchestrate/runs/{sentinel}/{run_id}",
                 f".orchestrate/runs/{sentinel}/../{run_id}", f".orchestrate/runs/{sentinel}/other-run", None, 17)
    _guard_path_io(monkeypatch, lambda spelling: sentinel in spelling or spelling in exact)
    for target in ("runtime.read_memo", "memo.read_memo", "views.reduce_memo"):
        monkeypatch.setattr(f"orchestrator.workflow.evaluated.{target}", _forbidden_memo_read)
    monkeypatch.chdir(tmp_path)
    for value in malformed:
        header["result_root"] = value
        header_path.write_text(json.dumps(header))
        before = _tree_bytes(run_root)
        _assert_malformed_refusals(run_root)
        assert _tree_bytes(run_root) == before
    assert "memo_inconsistent" in caplog.text


def test_publication_validates_result_root_before_creating_run_root(tmp_path):
    _source, program = _build(tmp_path)
    run_root = tmp_path / ".orchestrate" / "runs" / "r"
    recipe = {"source_roots": ["."], "entry_workflow": None, "provider_externs_path": None,
              "prompt_externs_path": None, "imported_workflow_bundles_path": None,
              "command_boundaries_path": None, "input_file": None, "input_overrides": {"score": 0.75}}

    def publish(result_root):
        return publish_run_authority(run_root, program, run_id="r", workflow_file="evaluated/inputs.orc",
            workflow_checksum="sha256:" + "0" * 64, bound_inputs={"score": 0.75, "threshold": 0.5},
            resume_request=recipe, result_root=result_root)

    for malformed in ("/abs/r", ".orchestrate/runs/x/../r", ".orchestrate/runs/other"):
        with pytest.raises(RunAuthorityError), publish(malformed):
            pass
        assert not run_root.exists()
    with publish(".orchestrate/runs/r") as authority:
        assert authority.header["result_root"] == ".orchestrate/runs/r"


def test_absent_result_root_without_x4_resumes_and_loads(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    _pop_result_root(run_root)
    monkeypatch.chdir(tmp_path)
    before = _tree_bytes(run_root)
    assert resume_workflow(run_root.name) == 0
    assert _tree_bytes(run_root) == before
    assert StateManager(tmp_path, run_root.name).load().status == "completed"
    assert load_evaluated_view(run_root)["status"] == "completed"


def test_absent_result_root_refuses_x4_reached_in_replay(tmp_path, monkeypatch, caplog):
    files, inputs = _x4_workspace(tmp_path, monkeypatch)
    pause = pause_public(files, monkeypatch, inputs)
    authority, _ = checked_run(tmp_path)
    _pop_result_root(authority.run_root)
    requests = (tmp_path / "requests.jsonl").read_bytes()
    _assert_refused(caplog, authority.run_root, "result_root_missing")
    assert (tmp_path / "requests.jsonl").read_bytes() == requests
    view = load_evaluated_view(authority.run_root)
    assert (view["status"], view["workflow_outputs"], view["error"]) == ("interrupted", None, None)
    record = invalidate_run(authority.run_root.name, pause.data["identity"])
    assert (record["record"], record["from_commit"]) == ("invalidated", pause.offset)
    view = load_evaluated_view(authority.run_root)
    assert (view["error"], view["next_effect"]) == (None, pause.data["identity"])


def test_absent_result_root_at_completed_x4_terminal_refuses(tmp_path, monkeypatch, caplog):
    files, inputs = _x4_workspace(tmp_path, monkeypatch)
    assert public_run(files, inputs).exit_code == 0
    authority, _ = checked_run(tmp_path)
    _pop_result_root(authority.run_root)
    _assert_refused(caplog, authority.run_root, "result_root_missing")
    with pytest.raises(MemoError) as refused:
        load_evaluated_view(authority.run_root)
    assert refused.value.code == "memo_inconsistent"


def test_absent_result_root_fails_x4_reached_after_continuation(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_SHIM_RESULTS", json.dumps(['{"ok":true}'] * 2))
    files, inputs = _x4_workspace(tmp_path, monkeypatch, TWO_PROVIDER_SOURCE)
    pause_public(files, monkeypatch, inputs)
    authority, _ = checked_run(tmp_path)
    _pop_result_root(authority.run_root)
    assert resume_workflow(authority.run_root.name) == 1
    _, snapshot = checked_run(tmp_path)
    assert len(snapshot.active_commits) == 2 and len(_requests(tmp_path)) == 2
    assert (snapshot.terminal.data["outcome"], snapshot.terminal.data["code"]) == ("failed", "result_root_missing")
    before, requests = _orchestrate_snapshot(tmp_path), (tmp_path / "requests.jsonl").read_bytes()
    assert resume_workflow(authority.run_root.name) == 2
    assert _orchestrate_snapshot(tmp_path) == before
    assert (tmp_path / "requests.jsonl").read_bytes() == requests


def test_path_mode_child_publishes_result_root(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(
        root, target_dsl_version="2.35"))
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(),
                           "--parent-root-fd", str(owner.root_fd)]) == 0, capsys.readouterr().err
        workspace = fixture.materialized_source.workspace_path
        header = load_run_authority(workspace / ".orchestrate" / "runs" / document["child_run_id"]).header
        assert header["result_root"] == f".orchestrate/runs/{document['child_run_id']}"


def _assert_reopened_view(run_root, provider, command):
    view = json.loads((run_root / "state.json").read_text())
    assert view["status"] != "failed" and view["error"] is None and view["workflow_outputs"] is None
    assert view["next_effect"] == command.data["identity"]
    assert view["steps"][provider.data["identity"]]["status"] == "completed"
    assert view["steps"][command.data["identity"]]["status"] == "invalidated"


def test_invalidation_keeping_provider_commit_republishes_through_x4(tmp_path, monkeypatch):
    (tmp_path / "echo.py").write_text(ECHO)
    files, inputs = _x4_workspace(tmp_path, monkeypatch, ECHO_SOURCE, {"echo": {
        "kind": "external_tool", "stable_command": ["python", "echo.py"], "closure": ["echo.py"]}})
    assert public_run(files, inputs).exit_code == 0
    authority, snapshot = checked_run(tmp_path)
    provider, command = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    assert (provider.data["effect_class"], command.data["effect_class"]) == ("provider", "command")
    completed = snapshot.terminal.data["value"]
    assert completed["bundle"] == f".orchestrate/runs/{authority.run_root.name}/{provider.data['result_path']}"
    requests, log = (tmp_path / "requests.jsonl").read_bytes(), (tmp_path / "echo.log").read_text()

    record = invalidate_run(authority.run_root.name, command.data["identity"])
    assert (record["record"], record["from_commit"]) == ("invalidated", command.offset)
    _assert_reopened_view(authority.run_root, provider, command)
    assert resume_workflow(authority.run_root.name) == 0
    _, after = checked_run(tmp_path)
    assert after.terminal.data["value"] == completed
    assert (tmp_path / "requests.jsonl").read_bytes() == requests
    assert (tmp_path / "echo.log").read_text() == log * 2
