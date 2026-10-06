"""Committed provider paths and path run-reference envelopes through public 2.35 runs."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.evaluated.views import load_evaluated_view
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.e2e.test_e2e_workflow_evaluated_run_ref import _compile_public
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
from tests.test_workflow_evaluated_run_ref import _assert_readonly_resumes, _authority
from tests.test_workflow_evaluated_run_ref_settlement import _service_run
from tests.workflow_evaluated_path_envelope_helpers import (
    CASES, HOMONYM, _path_names, assert_nested_path_envelope, interrupt_after, local_parent_fixture,
    path_envelope_fixture, recorded_signature_return, settled_evidence, static_config, tamper_child_evidence,
)
from tests.workflow_evaluated_run_ref_helpers import _json_lines, _run_to_exit
from tests.test_workflow_evaluated_providers import (
    _assert_cli_resumes_unchanged, _orchestrate_snapshot, _requests, workspace_relative,
)
from tests.test_workflow_evaluated_public_context import _provider_files
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.workflow_evaluated_context_helpers import public_context_run
from tests.workflow_evaluated_totality_helpers import checked_run, compile_public


PROVIDER = ('(provider-result providers.review :prompt prompts.base :inputs ({operand}) '
            ':model "chosen-model" :effort "low" :returns Result)')

PATHS_SOURCE = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
  (defpath ReportPath :kind relpath :under "artifacts" :must-exist true)
  (defrecord Result (ok Bool) (report ReportPath))
  (defunion Located (FOUND (bundle ResultBundle)) (MISSING))
  (defrecord Paths (direct ResultBundle) (called ResultBundle) (carried ResultBundle)
    (looped ResultBundle) (arm Located) (report ReportPath))
  (defworkflow locate ((message String)) -> ResultBundle
    (let* ((r {PROVIDER.format(operand="message")})) (provider-bundle-path r :as ResultBundle)))
  (defworkflow keep ((bundle ResultBundle)) -> ResultBundle bundle)
  (defworkflow run ((message String)) -> Paths
    (let* ((first {PROVIDER.format(operand="message")})
           (direct (provider-bundle-path first :as ResultBundle))
           (called (call locate :message message))
           (carried (call keep :bundle direct))
           (looped (loop/recur :max 2 :state (loop-state (round Int 0)) :on-exhausted direct
             (fn (state) (let* ((r {PROVIDER.format(operand="first.report")})
                                (p (provider-bundle-path r :as ResultBundle)))
               (if (= state.round 0) (continue (record-update state :round 1)) (done p)))))))
      (record Paths :direct direct :called called :carried carried :looped looped
        :arm (variant Located FOUND :bundle looped) :report first.report))))'''

REPORT = "artifacts/report.md"
REPORT_SENTINEL = "declared-report-bytes-7f3c"
RAW_RESULT = {"ok": True, "extra": 7, "report": REPORT}


def _provider_path_workspace(root, monkeypatch):
    files, inputs = _provider_files(root, PATHS_SOURCE)
    (root / "artifacts").mkdir()
    (root / REPORT).write_text(REPORT_SENTINEL + "\n")
    compile_public(files)
    monkeypatch.setenv("PATH", str(root / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(root)
    return files, inputs


def _resume_paused_after(monkeypatch, run_id, count):
    commits = []
    real_append = runtime.append_record

    def after_commit(path, record, **kwargs):
        entry = real_append(path, record, **kwargs)
        if record.get("record") == "committed":
            commits.append(entry)
            if len(commits) == count:
                raise _InterruptedRun()
        return entry

    with monkeypatch.context() as patched:
        patched.setattr(runtime, "append_record", after_commit)
        with pytest.raises(_InterruptedRun):
            resume_workflow(run_id)
    return commits


def _assert_attempt_locators(root, authority, commits, requests):
    located = []
    for commit, request in zip(commits, requests, strict=True):
        path = f'{authority.header["result_root"]}/{commit["result_path"]}'
        assert path == os.path.relpath(authority.run_root / commit["result_path"], root)
        env = request["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        assert os.path.isabs(env) and workspace_relative(env, root) == path
        assert commit["result_path"].endswith(f'/attempt-{commit["attempt"]}/result.json')
        raw = (root / path).read_bytes()
        assert json.loads(raw) == RAW_RESULT
        assert commit["result_digest"] == "sha256:" + sha256(raw).hexdigest()
        assert commit["value"] == {"ok": True, "report": REPORT}
        assert commit["result_digest"] != canonical_sha256(commit["value"])
        located.append(path)
    return located


def _assert_declared_field_is_not_a_read(commits, requests):
    for commit, request in zip(commits, requests, strict=True):
        assert not [part for part in commit["input_parts"] if part.startswith("dependency:")]
        assert commit["implementation_files"] == {}
        assert REPORT_SENTINEL not in request["prompt"]


def _fail_first_attempt_then_pause(root, files, inputs, monkeypatch):
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "nonzero")
    assert public_context_run(files, inputs).exit_code == 1
    authority, failed = checked_run(root)
    (failed_start,) = failed.latest_starts.values()
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "success")
    monkeypatch.setenv("PROVIDER_SHIM_RESULT", json.dumps(RAW_RESULT))
    paused = _resume_paused_after(monkeypatch, authority.run_root.name, 2)
    assert len(_requests(root)) == 3
    return authority, failed_start, [entry.data for entry in paused]


def _assert_projected_paths(authority, snapshot, located):
    expected = {"direct": located[0], "called": located[1], "carried": located[0],
                "looped": located[3], "arm": {"variant": "FOUND", "bundle": located[3]}, "report": REPORT}
    assert snapshot.terminal.data["value"] == expected
    assert load_evaluated_view(authority.run_root)["workflow_outputs"] == expected


def test_public_provider_bundle_paths_name_committed_attempts_through_call_loop_and_union(tmp_path, monkeypatch):
    files, inputs = _provider_path_workspace(tmp_path, monkeypatch)
    authority, failed_start, paused = _fail_first_attempt_then_pause(tmp_path, files, inputs, monkeypatch)
    prefix = authority.memo_path.read_bytes()
    resumed = _resume_cli(tmp_path, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _, snapshot = checked_run(tmp_path)
    assert authority.memo_path.read_bytes().startswith(prefix)
    commits = [entry.data for entry in snapshot.active_commits.values()]
    assert commits[:2] == paused and [commit["attempt"] for commit in commits] == [2, 1, 1, 1]
    requests = _requests(tmp_path)
    assert len(requests) == 5
    failed_path = f'{authority.header["result_root"]}/{failed_start.data["result_path"]}'
    env = requests[0]["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
    assert os.path.isabs(env) and workspace_relative(env, tmp_path) == failed_path
    located = _assert_attempt_locators(tmp_path, authority, commits, requests[1:])
    assert failed_path not in located
    _assert_declared_field_is_not_a_read(commits[2:], requests[3:])
    _assert_projected_paths(authority, snapshot, located)
    (tmp_path / REPORT).write_text("changed declared bytes\n")
    _assert_cli_resumes_unchanged(tmp_path, authority.run_root.name, _orchestrate_snapshot(tmp_path),
                                  (tmp_path / "requests.jsonl").read_bytes(), count=2)


@pytest.mark.parametrize("case", list(CASES))
def test_public_path_child_envelope_keeps_nested_child_relative_paths(tmp_path, case):
    parent, source, refs, inputs = path_envelope_fixture(tmp_path, case)
    result = _run_cli(parent, str(source), *inputs, "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, commit = assert_nested_path_envelope(case, parent, refs)
    before = _tree_bytes(parent), _tree_bytes(refs)
    refused = _cli(parent, "invalidate", authority.run_root.name, commit.data["identity"])
    assert refused.returncode == 2 and "invalidate_coordinator_committed" in refused.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before
    assert len(list(refs.rglob("child-request.json"))) == 1
    _assert_readonly_resumes(parent, authority, refs)


@pytest.mark.parametrize("form,child_target,expected", [
    ("imported-path", "2.35", "common::WorkPath"), ("local-parent", "2.35", "controller::LocalPath"),
    ("legacy-local", "2.24", "controller::LocalPath")])
def test_public_path_refinement_uses_closed_nominal_names(tmp_path, form, child_target, expected):
    if form == "imported-path":
        parent, source, refs, inputs = path_envelope_fixture(tmp_path, "evaluated-nested")
    else:
        parent, source, refs, inputs = local_parent_fixture(tmp_path, child_target)
    static = static_config(_compile_public(parent, source))
    refinement = static.program.return_refinement
    assert refinement == static.result_descriptor["envelope"]["fields"][0]["type"]
    assert _path_names(refinement) == {expected}
    result = _run_cli(parent, str(source), *inputs, "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    _, memo, _, _, documents = settled_evidence(parent)
    assert memo.terminal.data["value"] is True
    assert documents["child-result"]["path_compile"]["signature"]["return"] == recorded_signature_return(
        child_target, refinement, bare_paths=form != "imported-path")


def test_public_legacy_child_homonymous_path_type_is_refused_at_admission(tmp_path, monkeypatch):
    parent, source, refs, inputs = path_envelope_fixture(tmp_path, "legacy-homonym", HOMONYM)
    child_diagnostics = []
    real_run = subprocess.run

    def capture(command, *args, **kwargs):
        completed = real_run(command, *args, **kwargs)
        if "--path-request" in command:
            child_diagnostics.append(json.loads(completed.stderr))
        return completed

    monkeypatch.setattr(subprocess, "run", capture)
    assert _service_run(monkeypatch, parent, source, refs, *inputs).exit_code == 1
    (diagnostic,) = child_diagnostics
    assert (diagnostic["code"], diagnostic["secondary_causes"]) == (
        "trial_program_signature_mismatch", ["return_type_mismatch"])
    _, memo = _authority(parent)
    assert memo.terminal.data["code"] == "trial_program_signature_mismatch" and not memo.active_commits
    (request_path,) = refs.rglob("child-request.json")
    request = json.loads(request_path.read_bytes())
    assert not (Path(request["child_state_dir"]) / request["child_run_id"]).exists()


@pytest.mark.parametrize("gap", ["pending", "committed", "settled"])
@pytest.mark.parametrize("case", ["legacy-union", "evaluated-nested"])
def test_public_resume_after_commit_or_settlement_keeps_envelope_without_child(tmp_path, monkeypatch, case, gap):
    parent, source, refs, inputs = path_envelope_fixture(tmp_path / "w", case)
    authority, before = interrupt_after(monkeypatch, parent, source, refs, inputs, gap)
    (commit,) = before.active_commits.values()
    identity = commit.data["identity"]
    attempt_root = Path(commit.data["proof"]["settled_result"]["workspace_path"]).parent
    evidence = _tree_bytes(attempt_root)
    control = tmp_path / "observer"
    _run_to_exit(parent, control, ["resume", authority.run_root.name])
    observed = [len(_json_lines(control / name)) for name in ("launches.jsonl", "reconcile.jsonl")]
    assert observed == [0, 0 if gap == "settled" else 1]
    _, after = _authority(parent)
    assert after.active_commits[identity] == commit
    assert after.latest_starts[identity] == before.latest_starts[identity]
    assert _tree_bytes(attempt_root) == evidence
    assert len(list(refs.rglob("child-request.json"))) == 1
    assert_nested_path_envelope(case, parent, refs)
    _assert_readonly_resumes(parent, authority, refs)


OWNERS = {"artifact": "run_ref_delta_capture_failed: delta_record_mismatch",
          "missing-artifact": "run_ref_delta_capture_failed: declared_artifact_missing",
          "delta": "run_ref_delta_capture_failed: delta_digest_mismatch",
          "terminal": "run_ref_child_result_invalid: evaluated_child_authority_invalid",
          "proof": "run_ref_evidence_invalid: persisted_artifacts_binding_invalid",
          "missing-delta": "run_ref_evidence_invalid: workspace_delta_unreadable",
          "missing-terminal": "run_ref_child_result_invalid: evaluated_child_authority_invalid",
          "missing-proof": "[memo_inconsistent]",
          "legacy-terminal": "run_ref_child_result_invalid: child_terminal_state_invalid"}
TAMPERS = [("evaluated-nested", kind, gap) for kind in ("artifact", "missing-artifact", "delta", "missing-delta",
           "terminal", "missing-terminal", "proof", "missing-proof") for gap in ("committed", "settled")] + [("legacy-union", "artifact", "committed"),
                                                   ("legacy-union", "terminal", "committed")]


@pytest.mark.parametrize("case,kind,gap", TAMPERS)
def test_public_resume_refuses_tampered_path_evidence_before_reconcile_or_launch(tmp_path, monkeypatch, case, kind, gap):
    parent, source, refs, inputs = path_envelope_fixture(tmp_path, case)
    interrupt_after(monkeypatch, parent, source, refs, inputs, gap)
    authority, _memo, _commit, attempt_root, documents = settled_evidence(parent)
    child_root = attempt_root / "workspace" / ".orchestrate" / "runs" / documents["child-request"]["child_run_id"]
    tamper_child_evidence(kind, authority, attempt_root, child_root)
    before = _tree_bytes(parent), _tree_bytes(refs)
    resumed = _resume_cli(parent, authority.run_root.name)
    owner = OWNERS[("legacy-" if case.startswith("legacy") and kind == "terminal" else "") + kind]
    assert resumed.returncode == 2 and owner in resumed.stderr, resumed.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before
    assert len(list(refs.rglob("child-request.json"))) == 1
