"""Public evaluated E1 consumers retain pinned child and settlement evidence."""

import base64
import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.machine import site_nodes
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.run_ref.source import canonical_source_request
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from tests.e2e.test_e2e_workflow_lisp_run_ref import (
    _assert_complete_evidence_manifest,
    _git,
)
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
from tests.workflow_evaluated_run_ref_helpers import _json_lines, _run_to_exit
from tests.test_workflow_evaluated_run_ref import (
    _authority,
    _public_fixture,
    _repeated_fixture,
)


def _assert_pinned_evidence(attempt_root, *, settlement, static, candidate):
    request = json.loads((attempt_root / "child-request.json").read_bytes())
    child = json.loads((attempt_root / "child-result.json").read_bytes())
    manifest = _assert_complete_evidence_manifest(
        attempt_root, settlement=settlement, mode="path"
    )
    _assert_materialized_revision(request, manifest, static, candidate)
    _assert_source_tree_bytes(request, candidate)
    compilation = _assert_child_contract(child, request)
    return request, compilation["program_identity"], manifest


def _assert_materialized_revision(request, manifest, static, candidate):
    materialized = request["materialized_source"]
    revision = materialized["repository_revision"]
    git_tree = "git-tree:" + _git(candidate, "rev-parse", "HEAD^{tree}")
    assert materialized["normalized_locator"] == candidate.resolve().as_uri()
    assert materialized["resolved_commit_sha"] == _git(candidate, "rev-parse", "HEAD")
    assert revision["resolved_commit_sha"] == materialized["resolved_commit_sha"]
    assert materialized["verified_git_tree"] == git_tree
    assert manifest["verified_git_tree_id"] == git_tree
    assert manifest["source_digest"] == canonical_sha256(canonical_source_request(static.source))
    assert manifest["result_contract_digest"] == static.result_digest
    assert manifest["repository_revision_digest"] == revision["digest"]


def _assert_source_tree_bytes(request, candidate):
    materialized = request["materialized_source"]
    source_tree = materialized["source_tree_manifest"]
    assert materialized["post_setup_tree_manifest"] == source_tree
    (entry,) = source_tree["entries"]
    assert entry["path"] == "candidate.orc"
    assert entry["sha256"] == "sha256:" + hashlib.sha256((candidate / "candidate.orc").read_bytes()).hexdigest()
    assert (Path(request["clone_root"]) / entry["path"]).read_bytes() == (candidate / entry["path"]).read_bytes()


def _assert_child_contract(child, request):
    compilation = child["path_compile"]
    expected_facts = {"direct": [], "transitive": []}
    if child["schema_version"] == "run_ref_path_child_result.v1":
        expected_facts["procedure_edges"] = []
    assert compilation["effect_facts"] == expected_facts
    assert compilation["signature"]["return"] == {"kind": "primitive", "name": "Bool"}
    assert compilation["evidence"]["repository_revision_digest"] == request["materialized_source"]["repository_revision"]["digest"]
    assert compilation["evidence"]["verified_git_tree"] == request["materialized_source"]["verified_git_tree"]
    assert child["status"] == "completed"
    assert child["workflow_outputs"] == {"__result__": True}
    return compilation


def _assert_bounded_delta(attempt_root, *, envelope, manifest, request, child_target):
    delta_bytes = (attempt_root / "workspace-delta.json").read_bytes()
    delta = json.loads(delta_bytes)
    assert set(delta) == {
        "base", "changed_files", "deleted_files", "untracked_files",
        "normalized_diff", "declared_artifacts",
    }
    revision = dict(request["materialized_source"]["repository_revision"])
    revision.pop("schema_version")
    assert delta["base"] == revision
    untracked = _expected_untracked_delta(attempt_root, child_target)
    assert delta["changed_files"] == delta["deleted_files"] == []
    assert delta["untracked_files"] == untracked
    assert delta["declared_artifacts"] == []
    assert delta["normalized_diff"] == {
        "entries": [], "catalog_digest": canonical_sha256({
            "changed_files": [], "deleted_files": [], "untracked_files": untracked,
        }),
        "truncated": False, "omitted_bytes": 0, "omitted_entries": 0,
    }
    assert canonical_sha256(delta) == manifest["workspace_delta_digest"]
    assert envelope["workspace_delta"] == delta
    _assert_accounting(attempt_root, envelope, manifest, request)
    return delta_bytes


def _expected_untracked_delta(attempt_root, child_target):
    logs = attempt_root / "workspace" / "logs"
    if child_target == "2.35":
        assert not logs.exists()
        return []
    assert logs.is_dir() and not list(logs.iterdir())
    return [{"path": "logs", "kind": "directory",
             "mode": logs.stat().st_mode & 0o777, "size": 0,
             "old_sha256": None, "new_sha256": None, "link_target": None}]


def _assert_accounting(attempt_root, envelope, manifest, request):
    accounting = json.loads((attempt_root / "accounting.json").read_bytes())
    assert envelope["accounting"] == accounting
    assert accounting["child_run_id"] == request["child_run_id"]
    assert accounting["terminal_status"] == "completed"
    assert accounting["provider_attempts"] == accounting["token_usage"] == accounting["cost"] == "UNKNOWN"
    assert canonical_sha256(accounting) == manifest["accounting_digest"]


def _compile_public(parent, source):
    result = _cli(parent, "compile", str(source))
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    artifact = Path(summary["build_root"]) / "closed_program.json"
    program = ClosedProgram.from_artifact(artifact.read_text())
    assert program.digest == summary["program_digest"]
    return program


def _assert_public_readonly_reuse(parent, refs, authority, identity, control):
    before = _tree_bytes(parent), _tree_bytes(refs)
    counts = _observer_counts(control)
    for _ in range(2):
        _run_to_exit(parent, control, ["resume", authority.run_root.name])
        assert _observer_counts(control) == counts
        assert (_tree_bytes(parent), _tree_bytes(refs)) == before
    refused = _cli(parent, "invalidate", authority.run_root.name, identity)
    assert refused.returncode == 2
    assert "invalidate_coordinator_committed" in refused.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before


@pytest.mark.parametrize("child_target", ["2.24", "2.35"], ids=["legacy", "evaluated"])
def test_public_compile_run_resume_preserves_e1_pinned_evidence(tmp_path, child_target):
    first_root = tmp_path / "first"
    first_root.mkdir()
    parent, source, refs = _repeated_fixture(
        first_root, child_target=child_target, structure="nested"
    )
    candidate = first_root / "candidate"
    second_parent = tmp_path / "second" / "parent"
    second_parent.mkdir(parents=True)
    second_source = second_parent / "controller.orc"
    second_source.write_bytes(source.read_bytes())
    executions = [(parent, source, refs), (second_parent, second_source, tmp_path / "second" / "refs")]
    child_identities, deltas = [], []
    for parent, source, refs in executions:
        compiled = _compile_public(parent, source)
        control = tmp_path / "observers" / parent.parent.name
        _run_to_exit(parent, control, ["run", str(source), "--run-ref-root", str(refs)])
        authority, memo = _assert_completed_parent(parent, compiled, control)
        (node,) = site_nodes(authority.program).values()
        static = decode_run_ref_static_config(base64.b64decode(node["config"]))
        ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
        for commit in memo.active_commits.values():
            settlement = commit.data["proof"]["settled_result"]
            workspace = Path(settlement["workspace_path"])
            attempt_root = workspace.parent
            request, child_identity, manifest = _assert_pinned_evidence(
                attempt_root, settlement=settlement, static=static, candidate=candidate
            )
            _assert_settled_visit_request(authority, memo, commit, refs, parent, request)
            (row,) = [row for row in ledger.rows if row.visit.record == settlement["visit"] and row.stage == "committed"]
            assert row.bindings.evidence_manifest_digest == canonical_sha256(manifest)
            child_identities.append(child_identity)
            deltas.append(_assert_bounded_delta(
                attempt_root, envelope=commit.data["value"], manifest=manifest, request=request,
                child_target=child_target
            ))
        _assert_public_readonly_reuse(parent, refs, authority, commit.data["identity"], control)
    assert child_identities == [child_identities[0]] * 4
    assert deltas == [deltas[0]] * 4


def _observer_counts(control):
    return tuple(len(_json_lines(control / name)) for name in
                 ("launches.jsonl", "finalize.jsonl", "reconcile.jsonl"))


def _assert_completed_parent(parent, compiled, control):
    authority, memo = _authority(parent)
    assert authority.program.digest == compiled.digest
    assert memo.terminal.data == {"record": "terminal", "outcome": "completed", "value": True}
    assert len(memo.active_commits) == len(memo.settlements) == 2
    assert _observer_counts(control) == (2, 2, 0)
    return authority, memo


def _assert_settled_visit_request(authority, memo, commit, refs, parent, request):
    assert commit.data["value"]["value"] is True
    assert (commit.data["identity"], commit.data["attempt"]) in memo.settlements
    settlement = commit.data["proof"]["settled_result"]
    workspace = Path(settlement["workspace_path"])
    assert workspace.is_relative_to(refs) and not workspace.is_relative_to(parent)
    assert not authority.run_root.is_relative_to(refs)
    assert settlement["attempt_ordinal"] == settlement["visit"]["visit_count"] == 1
    assert request["parent_authority"] == {
        "run_root": str(authority.run_root), "identity": commit.data["identity"],
        "attempt": commit.data["attempt"],
    }
    assert request["inputs"] == {"flag": True}
    assert Path(request["child_state_dir"]).is_relative_to(workspace)


@pytest.mark.parametrize("child_body", [
    '(command-result missing_adapter :adapter missing_adapter :inputs () :returns Bool)',
    '(provider-result providers.worker :prompt prompts.worker :inputs () :returns Bool)',
], ids=["tool", "provider"])
def test_public_e1_child_refuses_unconfigured_environment(tmp_path, child_body):
    parent, source, refs = _public_fixture(tmp_path, child_target="2.35", child_body=child_body)
    _compile_public(parent, source)
    result = _cli(parent, "run", str(source), "--run-ref-root", str(refs))
    assert result.returncode == 1, result.stderr
    authority, memo = _authority(parent)
    assert memo.terminal.data["outcome"] == "failed"
    assert memo.terminal.data["code"] == "trial_candidate_environment_not_admissible"
    assert not memo.active_commits and not memo.settlements
    (request_path,) = refs.rglob("child-request.json")
    request = json.loads(request_path.read_bytes())
    assert not (Path(request["child_state_dir"]) / request["child_run_id"]).exists()
    assert not list(refs.rglob("child-result.json"))
    assert not list(refs.rglob("evidence-manifest.json"))
