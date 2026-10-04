"""Public evaluated parents use the existing path child and settlement authority."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from tests.e2e.test_e2e_workflow_lisp_run_ref import (
    _assert_complete_evidence_manifest,
    _commit_candidate,
    _git,
)
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_resume import _resume_cli


def _public_fixture(root: Path, *, child_target="2.24", parent_target="2.35", body=None,
    definitions="", inputs="", call_inputs="", child_body="true", child_definitions="", returns="Bool", parameters="", imports="", child_imports=""):
    candidate = root / "candidate"
    commit = _commit_candidate(candidate, f'''(workflow-lisp
      (:language "0.1") (:target-dsl "{child_target}")
      (defmodule candidate) {child_imports} (export run)
      {child_definitions} (defworkflow run ({inputs}) -> {returns} {child_body}))''')
    parent = root / "parent"
    parent.mkdir()
    call = f'''(run-ref :source (:repo "{candidate.resolve().as_uri()}" :commit "{commit}")
      :program (:path "candidate.orc" :entry run) :inputs ({call_inputs}) :returns {returns}
      :policy (:environment :deterministic-effect-free :setup ()))'''
    source = parent / "controller.orc"
    source.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "{parent_target}")
      (defmodule controller) {imports} (export run) {definitions(call) if callable(definitions) else definitions}
      (defworkflow run ({parameters}) -> Bool {body(call) if body else f'(let* ((attempt {call})) attempt.value)'}))''')
    return parent, source, root / "refs"


def _authority(root):
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    return authority, read_memo(authority.memo_path, site_classes(authority.program))


def _assert_readonly_resumes(parent, authority, refs):
    before = _tree_bytes(parent), _tree_bytes(refs)
    for _ in range(2):
        result = _resume_cli(parent, authority.run_root.name)
        assert result.returncode == 0, result.stderr
        assert (_tree_bytes(parent), _tree_bytes(refs)) == before


@pytest.mark.parametrize("child_target", ["2.24", "2.35"], ids=["legacy-child", "evaluated-child"])
def test_public_parent_child_matrix_and_k7(tmp_path, child_target):
    parent, source, refs = _public_fixture(tmp_path, child_target=child_target)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    assert memo.terminal.data == {"record": "terminal", "outcome": "completed", "value": True}
    (commit,) = memo.active_commits.values()
    assert commit.data["effect_class"] == "run_ref"
    assert (commit.data["identity"], commit.data["attempt"]) in memo.settlements
    settled = commit.data["proof"]["settled_result"]
    assert settled["visit"] == {
        "parent_run_id": authority.run_root.name,
        "execution_frame_id": "root", "call_frame_id": None,
        "step_id": "root." + canonical_sha256(commit.data["identity"]).removeprefix("sha256:"),
        "visit_count": 1,
    }
    ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    assert [row.stage for row in ledger.rows][-2:] == ["completed_pending_parent_commit", "committed"]
    workspace = Path(settled["workspace_path"])
    assert workspace.is_relative_to(refs) and (workspace / ".git").exists()
    attempt_root = workspace.parent
    request = json.loads((attempt_root / "child-request.json").read_text())
    child_result = json.loads((attempt_root / "child-result.json").read_text())
    assert request["schema_version"] == "run_ref_path_child_request.v2"
    assert child_result["schema_version"] == ("run_ref_path_child_result.v1" if child_target == "2.24" else "run_ref_path_child_result.v2")
    assert request["parent_authority"] == {"run_root": str(authority.run_root),
        "identity": commit.data["identity"], "attempt": commit.data["attempt"]}
    _assert_complete_evidence_manifest(attempt_root, settlement=settled, mode="path")
    _assert_readonly_resumes(parent, authority, refs)


@pytest.mark.parametrize("child_target", ["2.24", "2.35"])
def test_public_legacy_parent_retains_child_target_boundary(tmp_path, child_target):
    parent, source, refs = _public_fixture(tmp_path, child_target=child_target, parent_target="2.24")
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == (0 if child_target == "2.24" else 2), result.stderr
    (run_root,) = (parent / ".orchestrate" / "runs").iterdir()
    state = json.loads((run_root / "state.json").read_text())
    assert state["status"] == ("completed" if child_target == "2.24" else "failed")
    if child_target == "2.24":
        assert state["workflow_outputs"] == {"__result__": True}
        assert _resume_cli(parent, run_root.name).returncode == 0
    else:
        assert "evaluated_execution_unavailable" in json.dumps(state)
        assert not list(refs.rglob("closed_program.json"))
        (request_path,) = refs.rglob("child-request.json")
        request = json.loads(request_path.read_text())
        assert not (Path(request["child_state_dir"]) / request["child_run_id"]).exists()


def _repeated_fixture(root, *, child_target="2.24", structure="direct", forwarding=False):
    definitions = ""
    if structure != "direct":
        leaf = lambda call: f'''(defproc invoke ((flag Bool)) -> Bool
          :effects ((runs-ref run)) :lowering inline (let* ((child {call})) child.value))'''
        definitions = leaf
        if structure == "nested":
            definitions = lambda call: leaf(call) + '''(defproc outer ((flag Bool)) -> Bool
              :effects ((runs-ref run)) :lowering inline
              (loop/recur :max 1 :state (loop-state (current Bool flag))
                :on-exhausted false (fn (state) (done (invoke state.current)))))'''
    def body(call):
        value = f'(let* ((child {call})) child.value)' if structure == "direct" else (
            '(outer state.current)' if structure == "nested" else '(invoke state.current)')
        return f'''(loop/recur :max 2
          :state (loop-state (current Bool {"false" if forwarding else "true"}) (round Int 0))
          :on-exhausted false (fn (state) (let* ((value {value}))
            (if (= state.round 0) (continue (record-update state :current true :round 1)) (done value)))))'''
    return _public_fixture(root, child_target=child_target, body=body, definitions=definitions,
        inputs="(flag Bool)", call_inputs=":flag " + ("state.current" if structure == "direct" else "flag"), child_body="flag")


def _assert_distinct_repeated_visits(proofs):
    assert len({proof["visit"]["step_id"] for proof in proofs}) == 2
    for field in ("workspace_path", "child_run_id"):
        assert len({proof[field] for proof in proofs}) == 2
    assert all(proof["visit"]["visit_count"] == proof["attempt_ordinal"] == 1 for proof in proofs)


@pytest.mark.parametrize("child_target", ["2.24", "2.35"])
@pytest.mark.parametrize("structure", ["direct", "helper", "nested"])
@pytest.mark.parametrize("forwarding", [False, True], ids=["same-inputs", "state-input"])
def test_public_same_site_continue_done_keeps_distinct_k7(tmp_path, child_target, structure, forwarding):
    parent, source, refs = _repeated_fixture(tmp_path, child_target=child_target,
        structure=structure, forwarding=forwarding)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    assert len(site_classes(authority.program)) == 1
    commits = list(memo.active_commits.values())
    assert len(commits) == len(memo.settlements) == 2 and memo.terminal.data["value"] is True
    proofs = [commit.data["proof"]["settled_result"] for commit in commits]
    _assert_distinct_repeated_visits(proofs)
    requests = [json.loads((Path(proof["workspace_path"]).parent / "child-request.json").read_text()) for proof in proofs]
    assert [request["inputs"]["flag"] for request in requests] == ([False, True] if forwarding else [True, True])
    assert proofs[0]["step_config_digest"] == proofs[1]["step_config_digest"]
    assert [request["parent_authority"]["identity"] for request in requests] == [commit.data["identity"] for commit in commits]
    _assert_readonly_resumes(parent, authority, refs)


def test_run_ref_request_refuses_workspace_overlap_before_started(tmp_path):
    parent, source, _refs = _public_fixture(tmp_path)
    result = _run_cli(parent, str(source), "--run-ref-root", str(parent / "refs"))
    assert result.returncode == 1, result.stderr
    authority, memo = _authority(parent)
    assert not memo.latest_starts
    assert not (authority.run_root / "effects").exists()
    assert not (authority.run_root / "run-ref-attempts.jsonl").exists()


@pytest.mark.parametrize("edge", ["private", "native"])
def test_public_private_and_native_calls_keep_resolved_child_inputs(tmp_path, edge):
    def definitions(call):
        header = '(defworkflow invoke ((flag Bool)) -> Bool' if edge == "native" else (
            '(defproc invoke ((flag Bool)) -> Bool :effects ((runs-ref run)) :lowering private-workflow')
        return f'{header} (let* ((child {call})) child.value))'
    invoke = '(call invoke :flag true)' if edge == "native" else '(invoke true)'
    parent, source, refs = _public_fixture(tmp_path, definitions=definitions, body=lambda call: invoke,
        inputs="(flag-name Bool)", call_inputs=":flag-name flag", child_body="flag-name")
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    (commit,) = memo.active_commits.values()
    proof = commit.data["proof"]["settled_result"]
    request = json.loads((Path(proof["workspace_path"]).parent / "child-request.json").read_text())
    assert request["inputs"] == {"flag-name": True}
    assert memo.terminal.data["value"] is True
    _assert_readonly_resumes(parent, authority, refs)


@pytest.mark.parametrize("note", [None, "present"])
def test_public_nested_values_keep_child_default_omissions(tmp_path, note):
    common = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common)
      (export Packet Choice) (defunion Choice (KEEP (text String)) (DROP))
      (defrecord Packet (flag Bool) (choices List[Choice]) (scores Map[String,Int]) (note Optional[String])))'''
    imported = '(import common :only (Packet Choice))'
    parent, source, refs = _public_fixture(tmp_path, child_target="2.35", imports=imported,
        child_imports=imported, parameters="(payload Packet)",
        inputs='(payload Packet) (label String :default "omitted")', call_inputs=":payload payload",
        child_body="payload", returns="Packet", body=lambda call: f'(let* ((child {call})) child.value.flag)')
    _add_common_source(parent, source, tmp_path / "candidate", common)
    payload = {"flag": True, "choices": [{"variant": "KEEP", "text": "nested"}, {"variant": "DROP"}],
        "scores": {"one": 1, "two": 2}, "note": note}
    inputs = parent / "inputs.json"
    inputs.write_text(json.dumps({"payload": payload}))
    result = _run_cli(parent, str(source), "--input-file", str(inputs), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    (commit,) = memo.active_commits.values()
    assert commit.data["value"]["value"] == payload
    workspace = Path(commit.data["proof"]["settled_result"]["workspace_path"])
    request = json.loads((workspace.parent / "child-request.json").read_text())
    assert request["inputs"] == {"payload": payload}
    (child_header,) = workspace.glob(".orchestrate/runs/*/run.json")
    header = json.loads(child_header.read_text())
    assert header["resume_request"]["input_overrides"] == {"payload": payload}
    assert header["bound_inputs"] == {"payload": payload, "label": "omitted"}
    _assert_readonly_resumes(parent, authority, refs)


def _add_common_source(parent, source, candidate, common):
    old_commit = _git(candidate, "rev-parse", "HEAD")
    (candidate / "common.orc").write_text(common)
    (parent / "common.orc").write_text(common)
    _git(candidate, "add", "common.orc")
    _git(candidate, "-c", "user.name=Run Ref E2E", "-c", "user.email=run-ref-e2e@example.invalid", "commit", "--quiet", "-m", "common")
    source.write_text(source.read_text().replace(old_commit, _git(candidate, "rev-parse", "HEAD")))


def test_public_path_copy_is_confined_to_prepare_and_preserves_child_recipe(tmp_path, monkeypatch):
    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.workflow.run_ref import runtime
    common = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common)
      (export WorkPath) (defpath WorkPath :kind relpath :under "artifacts" :must-exist true))'''
    imported = '(import common :only (WorkPath))'
    parent, source, refs = _public_fixture(tmp_path, child_target="2.35", imports=imported, child_imports=imported,
        parameters="(payload WorkPath)", inputs="(payload WorkPath)", call_inputs=":payload payload",
        child_body="payload", returns="WorkPath", body=lambda call: f'(let* ((child {call})) true)')
    _add_common_source(parent, source, tmp_path / "candidate", common)
    (parent / "artifacts").mkdir()
    (parent / "artifacts" / "seed.txt").write_text("parent source bytes")
    result = _run_cli(parent, str(source), "--input", "payload=artifacts/seed.txt", "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    (commit,) = memo.active_commits.values()
    workspace = Path(commit.data["proof"]["settled_result"]["workspace_path"])
    request = json.loads((workspace.parent / "child-request.json").read_text())
    copied = request["inputs"]["payload"]
    assert copied == commit.data["value"]["value"] != authority.header["bound_inputs"]["payload"]
    assert (workspace / copied).read_text() == "parent source bytes"
    (child_header,) = workspace.glob(".orchestrate/runs/*/run.json")
    assert json.loads(child_header.read_text())["resume_request"]["input_overrides"] == {"payload": copied}
    def forbidden(*args, **kwargs):
        pytest.fail("memo hit repeated path copy")
    monkeypatch.setattr(runtime, "_copy_path_value", forbidden)
    monkeypatch.chdir(parent)
    before = _tree_bytes(parent), _tree_bytes(refs)
    for _ in range(2):
        assert resume_workflow(authority.run_root.name) == 0
        assert (_tree_bytes(parent), _tree_bytes(refs)) == before


def test_public_child_input_tracks_prior_command_dependency(tmp_path):
    from tests.test_workflow_evaluated_command_template_scopes import _write_probe, _write_boundaries
    body = lambda call: f'''(let* ((seed (command-result emit :argv ("python" "probe.py") :returns Int))
      (child {call})) child.value)'''
    parent, source, refs = _public_fixture(tmp_path, body=body,
        inputs="(flag Bool)", call_inputs=":flag (> seed -1)", child_body="flag")
    _write_probe(parent)
    boundaries = _write_boundaries(parent)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    command, child = memo.active_commits.values()
    assert child.data["depends_on"] == [command.data["identity"]]
    workspace = Path(child.data["proof"]["settled_result"]["workspace_path"])
    assert json.loads((workspace.parent / "child-request.json").read_text())["inputs"] == {"flag": True}
    _assert_readonly_resumes(parent, authority, refs)
