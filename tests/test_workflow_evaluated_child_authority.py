"""Closed child settlement binds the exact captured authority bytes."""

from dataclasses import replace
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path

from orchestrator.workflow.evaluated.memo import reduce_memo
from orchestrator.workflow.run_ref import ledger, runtime
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
import pytest
from tests import test_workflow_evaluated_run_ref_caller as caller
from tests.test_workflow_run_ref_child import _build_path_fixture
from tests.test_workflow_evaluated_child_values import _checked_child_fixture, _commit_prepared
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from orchestrator.workflow.run_ref import evaluated_child
from orchestrator.workflow.workspace_files import WorkspaceFiles


def _terminal_digest(root):
    header = (root / "run.json").read_bytes()
    program = (root / "closed_program.json").read_bytes()
    memo = (root / "memo.jsonl").read_bytes()
    complete = reduce_memo(memo, {}).complete_bytes
    hashed = lambda value: "sha256:" + sha256(value).hexdigest()
    return canonical_sha256({"domain": "run_ref_evaluated_child_terminal.v1",
        "header_sha256": hashed(header), "program_sha256": hashed(program),
        "memo_sha256": hashed(memo[:complete])})


def test_child_terminal_proof_binds_exact_authority_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    launched = []

    def launch_real(launch):
        process = runtime._default_child_launcher(launch)
        assert process.returncode == 0, process.stderr.decode()
        assert json.loads(process.stdout)["schema_version"] == "run_ref_path_child_result.v2"
        launched.append(launch)
        return process

    with caller._checked_launch_fixture(tmp_path, allocate=False) as (request, _fixture, document, owner):
        request = replace(request, parent_identity=document["parent_authority"]["identity"], parent_attempt=2)
        prepared = runtime.prepare_run_ref_settlement(request,
            dependencies=runtime.RunRefRuntimeDependencies(launch_child=launch_real))
        root = prepared.settled_result.workspace_path / ".orchestrate" / "runs" / prepared.settled_result.child_run_id
        assert len(launched) == 1
        assert launched[0].parent_root_fd == owner.root_fd
        assert prepared.envelope["value"] == "mode2-child-input"
        assert prepared.settled_result.child_terminal_state_digest == _terminal_digest(root)
        evidence = json.loads(prepared.evidence_manifest_path.read_bytes())
        assert evidence["paths"]["child_state"] == (root / "run.json").as_posix()
        row = ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        assert (row.stage, row.attempt_ordinal, request.parent_attempt) == ("completed_pending_parent_commit", 1, 2)
        assert json.loads((root / "state.json").read_bytes())["status"] == "completed"


@pytest.mark.parametrize("field,value", [("program_identity", 17), ("schema_version", []), ("schema_version", {})])
def test_legacy_result_malformed_identity_has_controlled_refusal(tmp_path, field, value):
    def launch_invalid(launch):
        process = runtime._default_child_launcher(launch)
        assert process.returncode == 0
        result = json.loads(process.stdout)
        destination = result["path_compile"] if field == "program_identity" else result
        destination[field] = value
        return replace(process, stdout=canonical_json_bytes(result) + b"\n")

    with caller._checked_launch_fixture(tmp_path, allocate=False) as (request, _fixture, document, _owner):
        request = replace(request, parent_identity=document["parent_authority"]["identity"], parent_attempt=2)
        with pytest.raises(runtime.RunRefRuntimeError, match="child_result_binding_invalid"):
            runtime.prepare_run_ref_settlement(request,
                dependencies=runtime.RunRefRuntimeDependencies(launch_child=launch_invalid))


@contextmanager
def _prepared_child(root):
    with _checked_child_fixture(root) as (request, owner):
        prepared = runtime.prepare_run_ref_settlement(request)
        evidence = json.loads(prepared.evidence_manifest_path.read_bytes())
        row = ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        arguments = {"workspace": row.bindings.workspace_path, "child_run_id": row.bindings.child_run_id,
            "child_request": json.loads(Path(evidence["paths"]["child_request"]).read_bytes()),
            "child_result": json.loads(Path(evidence["paths"]["child_result"]).read_bytes()),
            "step_config": request.step_config, "repository_revision_digest": runtime._repository_revision(request).digest,
            "verified_git_tree": row.bindings.verified_git_tree_id}
        child_root = row.bindings.workspace_path / ".orchestrate" / "runs" / row.bindings.child_run_id
        yield request, owner, prepared, child_root, arguments


def test_initial_finalize_recovery_reuse_share_terminal_validator(tmp_path, monkeypatch):
    calls = []
    real_validate = evaluated_child.validate_evaluated_child_terminal
    def observe(**kwargs):
        calls.append(kwargs)
        return real_validate(**kwargs)
    monkeypatch.setattr(evaluated_child, "validate_evaluated_child_terminal", observe)
    with _prepared_child(tmp_path) as (request, owner, prepared, _root, _arguments):
        assert len(calls) == 1
        _commit_prepared(request, prepared, owner)
        from orchestrator.workflow.run_ref import path_compile
        monkeypatch.setattr(path_compile, "_require_path_compiler_identity", lambda *_args, **_kwargs: pytest.fail("durable installed compiler check"))
        finalized = runtime.finalize_run_ref_parent_commit(request, prepared, persisted_settled_result=prepared.settled_result.record)
        assert len(calls) == 3
        before = _tree_bytes(tmp_path)
        recovered = runtime.recover_run_ref_settlement(request, settled_result=prepared.settled_result.record, reconcile_pending=False)
        reused = runtime.validate_completed_run_ref_authority(request, settled_result=prepared.settled_result.record,
            artifacts=prepared.artifacts, reconcile_pending=False)
        assert len(calls) == 5
        assert finalized.envelope == recovered.envelope == reused.envelope == prepared.envelope
        assert _tree_bytes(tmp_path) == before


def test_completed_child_proof_does_not_need_published_view(tmp_path):
    with _prepared_child(tmp_path) as (_request, _owner, prepared, root, arguments):
        (root / "state.json").unlink()
        before = _tree_bytes(tmp_path)
        value, path, digest = evaluated_child.validate_evaluated_child_terminal(**arguments)
        assert (value, path, digest) == ("direct", root / "run.json", prepared.settled_result.child_terminal_state_digest)
        assert not (root / "state.json").exists()
        assert _tree_bytes(tmp_path) == before


def test_terminal_helper_captures_three_files_once_without_source_or_preparation(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated import authority
    from orchestrator.workflow.run_ref import child, path_compile, source
    from orchestrator.workflow_lisp.closed import artifact
    from orchestrator.cli.commands import evaluated

    with _prepared_child(tmp_path) as (_request, _owner, prepared, root, arguments):
        (arguments["workspace"] / "candidate.orc").unlink()
        (tmp_path / "repository").rename(tmp_path / "unavailable-source")
        before = _tree_bytes(tmp_path)
        reads = []
        real_read = WorkspaceFiles.read
        def observe(files, path):
            reads.append(Path(path).name)
            return real_read(files, path)
        forbidden = lambda *_args, **_kwargs: pytest.fail("proof recaptured source or opened captured authority again")
        with monkeypatch.context() as guards:
            guards.setattr(WorkspaceFiles, "read", observe)
            guards.setattr(authority, "_read_header_json", forbidden)
            guards.setattr(authority, "_read_file", forbidden)
            guards.setattr(source, "materialize_source", forbidden)
            guards.setattr(artifact, "prepare_closed_program_bundle", forbidden)
            guards.setattr(evaluated, "bind_program_inputs", forbidden)
            guards.setattr(path_compile, "_require_path_compiler_identity", forbidden)
            guards.setattr(child, "_materialized_source_from_payload", forbidden)
            guards.setattr(runtime, "_copy_path_value", forbidden)
            value, path, digest = evaluated_child.validate_evaluated_child_terminal(**arguments)
        assert (value, path, digest) == ("direct", root / "run.json", prepared.settled_result.child_terminal_state_digest)
        assert reads == ["run.json", "closed_program.json", "memo.jsonl"]
        assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("sibling", ["run.json", "closed_program.json", "memo.jsonl"])
def test_child_root_swap_refuses_after_retained_three_file_capture(tmp_path, monkeypatch, sibling):
    with _prepared_child(tmp_path) as (_request, _owner, _prepared, root, arguments):
        original = _tree_bytes(root)
        payloads = {name: (root / name).read_bytes() for name in ("run.json", "closed_program.json", "memo.jsonl")}
        retained = root.with_name("retained-child")
        reads = []
        real_read = WorkspaceFiles.read
        substitute = None
        def swap(files, path):
            nonlocal substitute
            data = real_read(files, path)
            reads.append((Path(path).name, data))
            if Path(path).name == sibling:
                root.rename(retained)
                root.mkdir()
                for name in payloads:
                    (root / name).write_bytes(b"substitute bytes\n")
                substitute = _tree_bytes(root)
            return data
        monkeypatch.setattr(WorkspaceFiles, "read", swap)
        with pytest.raises(ValueError, match="child root changed"):
            evaluated_child.validate_evaluated_child_terminal(**arguments)
        assert reads == list(payloads.items())
        assert _tree_bytes(retained) == original
        assert _tree_bytes(root) == substitute


@pytest.mark.parametrize("sibling", ["run.json", "closed_program.json", "memo.jsonl"])
@pytest.mark.parametrize("kind", ["symlink", "directory", "missing"])
def test_terminal_siblings_must_be_regular_retained_files(tmp_path, sibling, kind):
    with _prepared_child(tmp_path) as (_request, _owner, _prepared, root, arguments):
        path = root / sibling
        held = root / (sibling + ".held")
        path.rename(held)
        if kind == "symlink":
            path.symlink_to(held.name)
        elif kind == "directory":
            path.mkdir()
        before = _tree_bytes(tmp_path)
        with pytest.raises(OSError):
            evaluated_child.validate_evaluated_child_terminal(**arguments)
        assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("sibling", ["run.json", "closed_program.json", "memo.jsonl"])
def test_terminal_digest_binds_full_raw_authority_and_complete_memo_prefix(tmp_path, sibling):
    with _prepared_child(tmp_path) as (_request, _owner, prepared, root, arguments):
        path = root / sibling
        document = json.loads(path.read_bytes())
        path.write_bytes(json.dumps(document, indent=None if sibling == "memo.jsonl" else 2).encode() + b"\n")
        _value, _path, digest = evaluated_child.validate_evaluated_child_terminal(**arguments)
        assert digest == _terminal_digest(root) != prepared.settled_result.child_terminal_state_digest
        (root / "state.json").write_text('{"status":"stale"}')
        memo = root / "memo.jsonl"
        memo.write_bytes(memo.read_bytes() + b'{"record":"incomplete')
        before = _tree_bytes(tmp_path)
        assert evaluated_child.validate_evaluated_child_terminal(**arguments)[2] == digest
        assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("change", ["complete_corrupt", "extra_terminal", "failed", "halt", "wrapper"])
def test_terminal_corruption_is_readonly(tmp_path, change):
    with _prepared_child(tmp_path) as (_request, _owner, _prepared, root, arguments):
        memo = root / "memo.jsonl"
        record = json.loads(memo.read_bytes())
        if change == "complete_corrupt":
            memo.write_bytes(memo.read_bytes() + b"broken\n")
        elif change == "extra_terminal":
            memo.write_bytes(memo.read_bytes() * 2)
        elif change == "failed":
            record = {"record": "terminal", "outcome": "failed", "code": "fixture_failed", "message": "fixture"}
            memo.write_bytes(canonical_json_bytes(record) + b"\n")
            assert reduce_memo(memo.read_bytes(), {}).terminal.data["outcome"] == "failed"
        elif change == "halt":
            record["value"] = "changed terminal"
            arguments["child_result"]["workflow_outputs"]["__result__"] = record["value"]
            memo.write_bytes(canonical_json_bytes(record) + b"\n")
        else:
            arguments["child_result"]["workflow_outputs"] = {"payload": "direct"}
        before = _tree_bytes(tmp_path)
        with pytest.raises(ValueError):
            evaluated_child.validate_evaluated_child_terminal(**arguments)
        assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("change", ["terminal", "wrapper", "static_type", "facts"])
def test_late_child_corruption_refuses_before_child_completed_or_result_write(tmp_path, change):
    with _checked_child_fixture(tmp_path, type_name="Int", value=1) as (request, owner):
        hooks = []
        launched = []
        def launch_invalid(launch):
            process = runtime._default_child_launcher(launch)
            assert process.returncode == 0, process.stderr.decode()
            launched.append(launch)
            result = json.loads(process.stdout)
            root = launch.workspace / ".orchestrate" / "runs" / launch.child_run_id
            if change in {"terminal", "static_type"}:
                memo = root / "memo.jsonl"
                record = json.loads(memo.read_bytes())
                record["value"] = 2 if change == "terminal" else True
                result["workflow_outputs"]["__result__"] = record["value"]
                memo.write_bytes(canonical_json_bytes(record) + b"\n")
            elif change == "wrapper":
                result["workflow_outputs"] = {"unexpected": 1}
            else:
                result["path_compile"]["signature"]["inputs"][0]["required"] = 1
            return replace(process, stdout=canonical_json_bytes(result) + b"\n")
        with pytest.raises(runtime.RunRefRuntimeError, match="evaluated_child_authority_invalid"):
            runtime.prepare_run_ref_settlement(request, dependencies=runtime.RunRefRuntimeDependencies(
                launch_child=launch_invalid, crash_hook=hooks.append))
        row = ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        assert row.stage == "launched"
        assert "child_completion" not in hooks
        assert not (launched[0].request_path.parent / runtime._CHILD_RESULT_FILENAME).exists()


@pytest.mark.parametrize("authority_change", ["intact", "tamper_memo", "missing_header", "corrupt_header", "artifact_only", "memo_only"])
def test_closed_child_cannot_downgrade_to_legacy_result_and_state_view(tmp_path, authority_change):
    with _checked_child_fixture(tmp_path) as (request, owner):
        hooks = []
        launched = []
        def downgrade(launch):
            process = runtime._default_child_launcher(launch)
            assert process.returncode == 0, process.stderr.decode()
            result = json.loads(process.stdout)
            assert result["schema_version"] == evaluated_child.RESULT_SCHEMA
            root = launch.workspace / ".orchestrate" / "runs" / launch.child_run_id
            assert json.loads((root / "run.json").read_bytes())["result_persistence_profile"] == "evaluated_execution.v1"
            result["schema_version"] = "run_ref_path_child_result.v1"
            result["path_compile"]["program_identity"] = {}
            if authority_change == "tamper_memo":
                memo = root / "memo.jsonl"
                record = json.loads(memo.read_bytes())
                record["value"] = "adulterated completed child"
                memo.write_bytes(canonical_json_bytes(record) + b"\n")
                assert reduce_memo(memo.read_bytes(), {}).terminal.data["value"] == record["value"]
            _change_evaluated_siblings(root, authority_change)
            (root / "state.json").write_bytes(canonical_json_bytes({"run_id": launch.child_run_id,
                "status": "completed", "workflow_outputs": result["workflow_outputs"]}) + b"\n")
            launched.append(launch)
            return replace(process, stdout=canonical_json_bytes(result) + b"\n")
        with pytest.raises(runtime.RunRefRuntimeError):
            runtime.prepare_run_ref_settlement(request, dependencies=runtime.RunRefRuntimeDependencies(
                launch_child=downgrade, crash_hook=hooks.append))
        assert ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1].stage == "launched"
        assert "child_completion" not in hooks
        assert not (launched[0].request_path.parent / runtime._CHILD_RESULT_FILENAME).exists()


def _change_evaluated_siblings(root, change):
    if change == "corrupt_header":
        (root / "run.json").write_bytes(b"broken\n")
    elif change == "missing_header":
        (root / "run.json").unlink()
    elif change in {"artifact_only", "memo_only"}:
        keep = "closed_program.json" if change == "artifact_only" else "memo.jsonl"
        for name in ("run.json", "closed_program.json", "memo.jsonl"):
            if name != keep:
                (root / name).unlink()


@pytest.mark.parametrize("authority_change", ["intact", "missing_header", "corrupt_header", "artifact_only", "memo_only"])
def test_durable_downgrade_refuses_checked_child_profile_before_mutation(tmp_path, authority_change):
    with _prepared_child(tmp_path) as (request, owner, prepared, root, arguments):
        result = arguments["child_result"]
        result["schema_version"] = "run_ref_path_child_result.v1"
        result["path_compile"]["program_identity"] = {}
        evidence = json.loads(prepared.evidence_manifest_path.read_bytes())
        Path(evidence["paths"]["child_result"]).write_bytes(canonical_json_bytes(result) + b"\n")
        (root / "state.json").write_bytes(canonical_json_bytes({"run_id": arguments["child_run_id"],
            "status": "completed", "workflow_outputs": result["workflow_outputs"]}) + b"\n")
        _change_evaluated_siblings(root, authority_change)
        row = ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        row = replace(row, bindings=replace(row.bindings, result_payload_digest=canonical_sha256(result)))
        before = _tree_bytes(tmp_path)
        with pytest.raises(runtime.RunRefRuntimeError, match="child_result_profile_invalid"):
            runtime._validate_bound_authority(request, row)
        assert _tree_bytes(tmp_path) == before


def test_supplied_header_loader_normalizes_wrong_descriptor_root(tmp_path):
    from orchestrator.workflow.evaluated.authority import RunAuthorityError, load_run_authority

    with _prepared_child(tmp_path) as (_request, _owner, _prepared, root, _arguments):
        header = json.loads((root / "run.json").read_bytes())
        other = tmp_path / "wrong-root"
        other.mkdir()
        files = WorkspaceFiles(other)
        try:
            before = _tree_bytes(tmp_path)
            with pytest.raises(RunAuthorityError, match="invalid evaluated authority"):
                load_run_authority(root, header=header, run_files=files)
            assert _tree_bytes(tmp_path) == before
        finally:
            files.close()


def test_header_capture_normalizes_wrong_descriptor_root(tmp_path):
    from orchestrator.workflow.evaluated import authority

    with _prepared_child(tmp_path) as (_request, _owner, _prepared, root, _arguments):
        other = tmp_path / "wrong-root"
        other.mkdir()
        files = WorkspaceFiles(other)
        try:
            before = _tree_bytes(tmp_path)
            with pytest.raises(authority.RunAuthorityError):
                authority._read_header_json(root / "run.json", run_files=files)
            assert _tree_bytes(tmp_path) == before
        finally:
            files.close()


@pytest.mark.parametrize("field", ["source_roots", "entry_workflow", "provider_externs_path", "prompt_externs_path",
    "imported_workflow_bundles_path", "command_boundaries_path", "input_file", "input_overrides", "missing_recipe", "missing_root"])
def test_closed_child_requires_its_complete_exact_new_recipe_and_root(tmp_path, field):
    with _prepared_child(tmp_path) as (_request, _owner, _prepared, root, arguments):
        path = root / "run.json"
        header = json.loads(path.read_bytes())
        if field == "missing_root":
            del header["run_ref_root"]
        elif field == "missing_recipe":
            del header["resume_request"]
        else:
            choices = {"source_roots": [], "entry_workflow": "candidate::run", "input_overrides": {"payload": "changed"}}
            header["resume_request"][field] = choices.get(field, "manifest.json")
        path.write_bytes(canonical_json_bytes(header) + b"\n")
        before = _tree_bytes(tmp_path)
        with pytest.raises(ValueError):
            evaluated_child.validate_evaluated_child_terminal(**arguments)
        assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("change", ["header_profile", "header_run_id", "header_program_digest", "header_inputs", "header_pins",
    "artifact", "identity_digest", "semantic_digest", "signature", "effects", "evidence", "diagnostics", "result_v1", "result_unknown", "request_v1"])
def test_closed_child_header_artifact_facts_and_schema_corruption_refuse(tmp_path, change):
    with _prepared_child(tmp_path) as (_request, _owner, _prepared, root, arguments):
        header_path = root / "run.json"
        header = json.loads(header_path.read_bytes())
        facts = arguments["child_result"]["path_compile"]
        if change.startswith("header_"):
            _corrupt_header(header, change)
            header_path.write_bytes(canonical_json_bytes(header) + b"\n")
        elif change == "artifact":
            (root / "closed_program.json").write_bytes(b"{}\n")
        elif change == "request_v1":
            arguments["child_request"]["schema_version"] = "run_ref_path_child_request.v1"
        elif change.startswith("result_"):
            arguments["child_result"]["schema_version"] = "run_ref_path_child_result.v1" if change == "result_v1" else "unknown"
        else:
            _corrupt_closed_facts(facts, change)
        before = _tree_bytes(tmp_path)
        with pytest.raises(ValueError):
            evaluated_child.validate_evaluated_child_terminal(**arguments)
        assert _tree_bytes(tmp_path) == before


def _corrupt_header(header, change):
    alterations = {"header_profile": ("result_persistence_profile", "legacy"), "header_run_id": ("run_id", "foreign"),
        "header_program_digest": ("program_digest", "sha256:" + "f" * 64), "header_inputs": ("bound_inputs", {"payload": "changed"}),
        "header_pins": ("interpreters", {"foreign": {}})}
    key, value = alterations[change]
    header[key] = value
    if change == "header_inputs":
        header["input_digest"] = canonical_sha256(value)


def _corrupt_closed_facts(facts, change):
    if change in {"identity_digest", "semantic_digest"}:
        identity = facts["program_identity"]
        key = "digest" if change == "identity_digest" else "program_digest"
        identity[key] = "sha256:" + "f" * 64
        if change == "semantic_digest":
            identity["digest"] = canonical_sha256({key: value for key, value in identity.items() if key != "digest"})
    elif change == "signature":
        facts["signature"]["inputs"][0]["required"] = 1
    elif change == "effects":
        facts["effect_facts"]["direct"] = ["command"]
    elif change == "evidence":
        facts["evidence"]["digest"] = "sha256:" + "f" * 64
    else:
        facts["diagnostics"] = {}


def test_durable_evidence_rejects_foreign_child_state_path_even_with_resealed_digest(tmp_path):
    with _prepared_child(tmp_path) as (request, owner, prepared, root, _arguments):
        evidence = json.loads(prepared.evidence_manifest_path.read_bytes())
        evidence["paths"]["child_state"] = (root / "state.json").as_posix()
        prepared.evidence_manifest_path.write_bytes(canonical_json_bytes(evidence) + b"\n")
        row = ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        row = replace(row, bindings=replace(row.bindings, evidence_manifest_digest=canonical_sha256(evidence)))
        before = _tree_bytes(tmp_path)
        with pytest.raises(runtime.RunRefRuntimeError, match="evidence_manifest_binding_invalid"):
            runtime._validate_bound_authority(request, row)
        assert _tree_bytes(tmp_path) == before
