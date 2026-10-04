"""Private path children require checked live parent launch authority."""

import base64
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import json
import os

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority, publish_run_authority
from orchestrator.workflow.evaluated.machine import site_classes, site_nodes
from orchestrator.workflow.evaluated.memo import append_record, read_memo
from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig
from orchestrator.workflow.run_ref import child, ledger, runtime
from orchestrator.workflow.run_ref import launch_authority
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.source import materialize_source
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_memo import _committed, _started
from tests.test_workflow_run_ref_child import _build_path_fixture, _path_request


def _checked_parent_program(root, fixture, structure="direct", returns="String"):
    source = root / "parent.orc"
    revision = fixture.materialized_source.repository_revision_id
    perform = f'''(run-ref
          :source (:repo {json.dumps(revision.normalized_locator)} :commit "{revision.resolved_commit_sha}")
          :program (:path "candidate.orc" :entry run)
          :inputs (:payload payload) :returns {returns}
          :policy (:environment :deterministic-effect-free :setup ()))'''
    body = f'(let* ((child {perform})) "parent")'
    definitions = ""
    if structure in {"call", "nested"}:
        if structure == "nested":
            definitions = f'(defworkflow leaf ((payload String)) -> String {body})'
            body = '(call leaf :payload payload)'
        definitions += f'(defworkflow helper ((payload String)) -> String {body})'
        body = '(call helper :payload payload)'
    elif structure == "loop":
        body = f'''(loop/recur :max 2 :state (loop-state (current String payload))
          :on-exhausted "exhausted" (fn (state) (done {body})))'''
    source.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule parent) (export run) {definitions}
      (defworkflow run ((payload String)) -> String {body}))''')
    build = FrontendBuildRequest(source_path=source, workspace_root=root)
    program = build_closed_program_bundle(build).program
    node = next(iter(site_nodes(program).values()))
    config = RunRefStepConfig(common=StepCommonConfig(),
                             run_ref=decode_run_ref_static_config(base64.b64decode(node["config"])))
    return source, program, config


def _allocate_launched(request, fixture, document, owner):
    bindings = runtime._attempt_bindings(
        request, attempt_ordinal=1, workspace=fixture.materialized_source.workspace_path,
        parent_values={"payload": "mode2-child-input"},
    )
    document["child_run_id"] = bindings.child_run_id
    # The reused fixture materializes eagerly; allocation requires absence.
    workspace = fixture.materialized_source.workspace_path
    held = workspace.with_name("fixture-materialized")
    workspace.rename(held)
    try:
        ledger.allocate_attempt(request.ledger_path, visit=request.visit,
                                bindings=bindings, run_files=owner)
    finally:
        held.rename(workspace)
    materialized = fixture.materialized_source
    transitions = (
        ("materialized", {"verified_git_tree_id": materialized.verified_git_tree.value}),
        ("setup_completed", {"setup_evidence_digest": materialized.setup_evidence_digest,
                             "post_setup_baseline_digest": materialized.post_setup_baseline_identity.digest}),
        ("program_prepared", {"program_preparation_digest": "sha256:" + "1" * 64}),
        ("launched", {"child_launch_digest": canonical_sha256(document)}),
    )
    for stage, updates in transitions:
        ledger.advance_attempt(request.ledger_path, visit=request.visit, attempt_ordinal=1,
                               stage=stage, binding_updates=updates, run_files=owner)


@contextmanager
def _checked_launch_fixture(tmp_path, *, allocate=True, structure="direct", dynamic_index=0):
    fixture = _build_path_fixture(tmp_path)
    parent_workspace = tmp_path / "parent-workspace"
    parent_workspace.mkdir()
    source, program, config = _checked_parent_program(parent_workspace, fixture, structure)
    fixture = replace(fixture, step_config=config)
    parent_root = parent_workspace / ".orchestrate" / "runs" / "parent-run"
    recipe = {"source_roots": [], "entry_workflow": None,
              "provider_externs_path": None, "prompt_externs_path": None,
              "imported_workflow_bundles_path": None, "command_boundaries_path": None,
              "input_file": None, "input_overrides": {"payload": "mode2-child-input"}}
    with publish_run_authority(
        parent_root, program, run_id=parent_root.name, workflow_file="parent.orc",
        workflow_checksum="sha256:" + sha256(source.read_bytes()).hexdigest(),
        bound_inputs=recipe["input_overrides"], resume_request=recipe,
        run_ref_root=fixture.materialized_source.workspace_path.parents[4].as_posix(),
    ) as authority:
        owner = authority.run_files
        identity = next(iter(site_classes(program))).replace("[*]", f"[{dynamic_index}]")
        append_record(authority.memo_path, _started(identity), run_files=owner)
        append_record(authority.memo_path, {"record": "failed", "identity": identity,
                      "attempt": 1, "code": "fixture_retry", "exit_info": {}}, run_files=owner)
        append_record(authority.memo_path, _started(identity, 2), run_files=owner)
        assert read_memo(authority.memo_path, site_classes(program), run_files=owner).pending_starts[identity].data["attempt"] == 2
        visit = ledger.RunRefVisitKey(parent_run_id=parent_root.name, execution_frame_id="root",
                                     call_frame_id=None, step_id="root." + canonical_sha256(identity).removeprefix("sha256:"),
                                     visit_count=1)
        request = runtime.RunRefRuntimeRequest(
            step_config=config, visit=visit, parent_state={"bound_inputs": recipe["input_overrides"]},
            parent_workspace=parent_workspace, parent_run_root=parent_root,
            run_ref_root=fixture.materialized_source.workspace_path.parents[4], run_files=owner,
        )
        document = _path_request(fixture)
        document.update(schema_version="run_ref_path_child_request.v2",
                        parent_authority={"run_root": parent_root.as_posix(), "identity": identity, "attempt": 2})
        if allocate:
            _allocate_launched(request, fixture, document, owner)
        fixture.request_path.write_bytes(canonical_json_bytes(document))
        yield request, fixture, document, owner


@pytest.mark.parametrize("structure", ["direct", "call", "nested", "loop"])
def test_private_v2_requires_current_parent_launch_authority(tmp_path, monkeypatch, capsys, structure):
    compiled = []
    real_compile = child.compile_and_admit_path_program

    def observe_compile(**kwargs):
        compiled.append(kwargs)
        return real_compile(**kwargs)

    monkeypatch.setattr(child, "compile_and_admit_path_program", observe_compile)
    with _checked_launch_fixture(tmp_path, structure=structure) as (_request, fixture, document, owner):
        result = child.main(["--path-request", fixture.request_path.as_posix(),
                             "--parent-root-fd", str(owner.root_fd)])
        output = capsys.readouterr()
        assert result == 0, output.err
        assert len(compiled) == 1
        returned = json.loads(output.out)
        assert returned["schema_version"] == "run_ref_path_child_result.v1"
        assert returned["workflow_outputs"] == {"__result__": "mode2-child-input"}
        assert document["parent_authority"]["attempt"] == 2
        assert ledger.load_attempt_ledger(_request.ledger_path, run_files=owner).rows[-1].attempt_ordinal == 1


@pytest.mark.parametrize("issued_index", [0, 1])
def test_private_loop_activation_cannot_use_other_iterations_launch(
    tmp_path, monkeypatch, capsys, issued_index
):
    with _checked_launch_fixture(tmp_path, allocate=False, structure="loop", dynamic_index=issued_index) as (
        request, fixture, document, owner
    ):
        issued_identity = document["parent_authority"]["identity"]
        wrong_identity = issued_identity.replace(f"[{issued_index}]", f"[{1 - issued_index}]")
        assert wrong_identity != issued_identity
        memo_path = request.parent_run_root / "memo.jsonl"
        append_record(memo_path, _started(wrong_identity), run_files=owner)
        append_record(memo_path, {"record": "failed", "identity": wrong_identity,
                      "attempt": 1, "code": "fixture_retry", "exit_info": {}}, run_files=owner)
        append_record(memo_path, _started(wrong_identity, 2), run_files=owner)
        authority = load_run_authority(request.parent_run_root, run_files=owner)
        memo = read_memo(memo_path, site_classes(authority.program), run_files=owner)
        assert set(memo.pending_starts) == {issued_identity, wrong_identity}
        _allocate_other_loop_launch(request, fixture, wrong_identity, owner)
        _allocate_launched(request, fixture, document, owner)
        launch_authority.validate_parent_launch(document, parent_root_fd=owner.root_fd,
            step_config=request.step_config, materialized_source=fixture.materialized_source)
        assert ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1].attempt_ordinal == 1
        document["parent_authority"]["identity"] = wrong_identity
        fixture.request_path.write_bytes(canonical_json_bytes(document))
        before = _tree_bytes(request.parent_run_root)
        observed = []
        real_validate = launch_authority.validate_parent_launch

        def observe_authority(*args, **kwargs):
            try:
                return real_validate(*args, **kwargs)
            except ValueError as error:
                observed.append(str(error))
                raise

        monkeypatch.setattr(launch_authority, "validate_parent_launch", observe_authority)
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        assert child.main(["--path-request", fixture.request_path.as_posix(),
                           "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "request_invalid"
        assert observed == ["parent current head is not this launched visit"]
        assert _tree_bytes(request.parent_run_root) == before


def _allocate_other_loop_launch(request, fixture, identity, owner):
    workspace = fixture.materialized_source.workspace_path.with_name("other-iteration")
    materialized = materialize_source(request.step_config.run_ref.source,
        run_ref_root=request.run_ref_root, workspace=workspace)
    other = replace(fixture, materialized_source=materialized,
        state_dir=workspace / ".orchestrate" / "runs")
    visit = replace(request.visit,
        step_id="root." + canonical_sha256(identity).removeprefix("sha256:"))
    other_request = replace(request, visit=visit)
    document = _path_request(other)
    document.update(schema_version="run_ref_path_child_request.v2", parent_authority={
        "run_root": request.parent_run_root.as_posix(), "identity": identity, "attempt": 2})
    _allocate_launched(other_request, other, document, owner)
    launch_authority.validate_parent_launch(document, parent_root_fd=owner.root_fd,
        step_config=request.step_config, materialized_source=materialized)


@pytest.mark.parametrize("field", ["inputs", "child_run_id", "clone_root", "child_state_dir", "test_control"])
def test_direct_v2_execution_rejects_fields_changed_after_decode(tmp_path, field, monkeypatch):
    with _checked_launch_fixture(tmp_path) as (_request, fixture, _document, owner):
        decoded = child.load_path_request(fixture.request_path, parent_root_fd=owner.root_fd)
        mutations = {"inputs": {"payload": "unauthorized-input"}, "child_run_id": "foreign-run",
                     "clone_root": tmp_path, "child_state_dir": tmp_path,
                     "test_control": child.RunRefChildTestControl("mode_2_compile", tmp_path / "progress")}
        changed = replace(decoded, **{field: mutations[field]})
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        with pytest.raises(child._ChildCommandError, match="request_invalid"):
            child.execute_path_request(changed)


def test_parent_lifecycle_transfers_retained_descriptor(tmp_path, monkeypatch):
    with _checked_launch_fixture(tmp_path, allocate=False) as (request, _fixture, document, owner):
        request = replace(request, parent_identity=document["parent_authority"]["identity"], parent_attempt=2)
        observed = []
        real_validate = launch_authority.validate_parent_launch

        def observe_ack(*args, **kwargs):
            observed.append(kwargs["expected_row_digest"])
            assert kwargs["expected_row_digest"] == ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1].row_digest
            return real_validate(*args, **kwargs)

        monkeypatch.setattr(launch_authority, "validate_parent_launch", observe_ack)

        def launch_checked(launch):
            assert getattr(launch, "parent_root_fd", None) == owner.root_fd
            return runtime._default_child_launcher(launch)

        runtime.prepare_run_ref_settlement(
            request, dependencies=runtime.RunRefRuntimeDependencies(launch_child=launch_checked))
        assert len(observed) == 1


def test_durable_v2_recovery_and_reuse_after_memo_commit(tmp_path):
    with _checked_launch_fixture(tmp_path, allocate=False) as (request, _fixture, document, owner):
        identity = document["parent_authority"]["identity"]
        request = replace(request, parent_identity=identity, parent_attempt=2)
        prepared = runtime.prepare_run_ref_settlement(request)
        append_record(request.parent_run_root / "memo.jsonl", _committed(
            identity, 2, effect_class="run_ref", value=dict(prepared.envelope),
            proof={"settled_result": prepared.settled_result.record, "artifacts": dict(prepared.artifacts)}),
            run_files=owner)
        assert identity not in read_memo(request.parent_run_root / "memo.jsonl", {identity: "run_ref"}, run_files=owner).pending_starts
        recovered = runtime.validate_completed_run_ref_authority(
            request, settled_result=prepared.settled_result.record, artifacts=prepared.artifacts, reconcile_pending=True)
        reused = runtime.validate_completed_run_ref_authority(
            request, settled_result=prepared.settled_result.record, artifacts=prepared.artifacts, reconcile_pending=False)
        assert recovered.envelope == reused.envelope == prepared.envelope
        assert ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1].stage == "committed"


@pytest.mark.parametrize("header_change", [{"result_persistence_profile": "legacy"}, {"run_id": "foreign"},
                                          {"schema_version": "foreign"}, {"run_ref_root": None}])
def test_child_refuses_invalid_parent_header_without_compile(tmp_path, monkeypatch, capsys, header_change):
    with _checked_launch_fixture(tmp_path) as (request, fixture, _document, owner):
        path = request.parent_run_root / "run.json"
        header = json.loads(path.read_bytes())
        if header_change == {"run_ref_root": None}:
            header.pop("run_ref_root")
        else:
            header.update(header_change)
        path.write_bytes(canonical_json_bytes(header))
        before = _tree_bytes(request.parent_run_root)
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "request_invalid"
        assert _tree_bytes(request.parent_run_root) == before


@pytest.mark.parametrize("descriptor_kind", ["missing", "closed", "file", "foreign", "v1", "mode1"])
def test_child_requires_exact_v2_descriptor_transport(tmp_path, monkeypatch, capsys, descriptor_kind):
    with _checked_launch_fixture(tmp_path) as (request, fixture, document, owner):
        descriptor = os.dup(owner.root_fd)
        if descriptor_kind == "closed":
            os.close(descriptor)
        elif descriptor_kind in {"file", "foreign"}:
            os.close(descriptor)
            descriptor = os.open(fixture.request_path if descriptor_kind == "file" else tmp_path, os.O_RDONLY)
        if descriptor_kind == "v1":
            document.pop("parent_authority")
            document["schema_version"] = child.RUN_REF_PATH_CHILD_REQUEST_SCHEMA
            fixture.request_path.write_bytes(canonical_json_bytes(document))
        arguments = ["--request" if descriptor_kind == "mode1" else "--path-request", fixture.request_path.as_posix()]
        if descriptor_kind != "missing":
            arguments += ["--parent-root-fd", str(descriptor)]
        before = _tree_bytes(request.parent_run_root)
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        try:
            assert child.main(arguments) == 2
            assert json.loads(capsys.readouterr().err)["reason"] == "request_invalid"
            assert _tree_bytes(request.parent_run_root) == before
        finally:
            if descriptor_kind != "closed":
                os.close(descriptor)


@pytest.mark.parametrize("mutation", ["identity", "attempt", "bool_attempt", "root", "inputs", "child_id", "config", "extra"])
def test_child_refuses_changed_full_request(tmp_path, monkeypatch, capsys, mutation):
    with _checked_launch_fixture(tmp_path) as (request, fixture, document, owner):
        authority_changes = {"identity": {"identity": "foreign"}, "attempt": {"attempt": 1},
                             "bool_attempt": {"attempt": True}, "root": {"run_root": tmp_path.as_posix()}}
        changes = {"inputs": {"inputs": {"payload": "changed"}}, "child_id": {"child_run_id": "foreign"},
                   "config": {"expected_step_config_digest": "sha256:" + "f" * 64}, "extra": {"parent_root_fd": owner.root_fd}}
        document["parent_authority"].update(authority_changes.get(mutation, {}))
        document.update(changes.get(mutation, {}))
        fixture.request_path.write_bytes(canonical_json_bytes(document))
        before = _tree_bytes(request.parent_run_root)
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "request_invalid"
        assert _tree_bytes(request.parent_run_root) == before


@pytest.mark.parametrize("artifact", ["run.json", "closed_program.json", "memo.jsonl", "run-ref-attempts.jsonl"])
def test_child_refuses_corrupt_parent_artifact_without_writes(tmp_path, monkeypatch, capsys, artifact):
    with _checked_launch_fixture(tmp_path) as (request, fixture, _document, owner):
        (request.parent_run_root / artifact).write_bytes(b"corrupt\n")
        before = _tree_bytes(request.parent_run_root)
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "request_invalid"
        assert _tree_bytes(request.parent_run_root) == before


def test_child_refuses_historical_launched_row(tmp_path, monkeypatch, capsys):
    with _checked_launch_fixture(tmp_path) as (request, fixture, _document, owner):
        ledger.advance_attempt(request.ledger_path, visit=request.visit, attempt_ordinal=1,
                               stage="child_completed", binding_updates={
                                   "child_terminal_state_digest": "sha256:" + "e" * 64,
                                   "result_payload_digest": "sha256:" + "e" * 64}, run_files=owner)
        before = _tree_bytes(request.parent_run_root)
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "request_invalid"
        assert _tree_bytes(request.parent_run_root) == before


@pytest.mark.parametrize("boundary", ["write_sync", "ack", "crash_hook"])
def test_parent_refuses_root_swap_before_child_launch(tmp_path, monkeypatch, boundary):
    with _checked_launch_fixture(tmp_path, allocate=False) as (request, _fixture, document, owner):
        request = replace(request, parent_identity=document["parent_authority"]["identity"], parent_attempt=2)
        root = request.parent_run_root
        substitute = None

        def swap():
            nonlocal substitute
            root.rename(root.with_name("retained-parent"))
            root.mkdir()
            (root / "run-ref-attempts.jsonl").write_bytes(b"untouched substitute")
            substitute = _tree_bytes(root)

        real_write = owner.write_atomic
        real_ack = runtime.acknowledge_persisted_run_ref_lifecycle_event

        def write_atomic(path, payload):
            real_write(path, payload)
            if boundary == "write_sync" and str(path).endswith("run-ref-attempts.jsonl") and json.loads(payload.splitlines()[-1])["stage"] == "launched":
                swap()

        def acknowledge(event, **kwargs):
            acknowledgement = real_ack(event, **kwargs)
            if boundary == "ack" and event.stage == "launched":
                swap()
            return acknowledgement

        monkeypatch.setattr(owner, "write_atomic", write_atomic)
        monkeypatch.setattr(runtime, "acknowledge_persisted_run_ref_lifecycle_event", acknowledge)
        effects = runtime.RunRefRuntimeDependencies(
            launch_child=lambda _launch: pytest.fail("launched"),
            crash_hook=lambda stage: swap() if boundary == "crash_hook" and stage == "launch" else None)
        with pytest.raises(runtime.RunRefRuntimeError, match="parent_launch_authority_invalid"):
            runtime.prepare_run_ref_settlement(request, dependencies=effects)
        assert substitute is not None and _tree_bytes(root) == substitute
        assert ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1].stage == "launched"


def test_child_refuses_root_swap_during_authority_read(tmp_path, monkeypatch, capsys):
    with _checked_launch_fixture(tmp_path) as (request, fixture, _document, owner):
        real_load = launch_authority.load_attempt_ledger
        root = request.parent_run_root

        def load_then_swap(*args, **kwargs):
            result = real_load(*args, **kwargs)
            root.rename(root.with_name("retained-parent"))
            root.mkdir()
            return result

        monkeypatch.setattr(launch_authority, "load_attempt_ledger", load_then_swap)
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "request_invalid"
        assert _tree_bytes(root) == {"<root>": ("directory", None)}


def test_child_binds_exact_other_checked_config_before_ledger_hash(tmp_path, monkeypatch, capsys):
    with _checked_launch_fixture(tmp_path) as (request, fixture, document, owner):
        source, other_program, _other_config = _checked_parent_program(request.parent_workspace, fixture, returns="Int")
        root = request.parent_run_root
        header = json.loads((root / "run.json").read_bytes())
        header.update(program_digest=other_program.digest,
                      workflow_checksum="sha256:" + sha256(source.read_bytes()).hexdigest())
        (root / "run.json").write_bytes(canonical_json_bytes(header))
        (root / "closed_program.json").write_text(other_program.artifact())
        checked = load_run_authority(root, run_files=owner)
        assert site_classes(checked.program) == {document["parent_authority"]["identity"]: "run_ref"}
        before = _tree_bytes(root)
        monkeypatch.setattr(launch_authority, "load_attempt_ledger", lambda *_args, **_kwargs: pytest.fail("passed checked config"))
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "request_invalid"
        assert _tree_bytes(root) == before


@pytest.mark.parametrize("supersession", ["discard", "new_ordinal", "failed_start"])
def test_direct_child_refuses_superseded_live_permission(tmp_path, monkeypatch, supersession):
    with _checked_launch_fixture(tmp_path) as (request, fixture, document, owner):
        decoded = child.load_path_request(fixture.request_path, parent_root_fd=owner.root_fd)
        if supersession == "failed_start":
            append_record(request.parent_run_root / "memo.jsonl", {"record": "failed",
                          "identity": document["parent_authority"]["identity"], "attempt": 2,
                          "code": "fixture_failure", "exit_info": {}}, run_files=owner)
        else:
            workspace = fixture.materialized_source.workspace_path
            runtime._default_discard_workspace(workspace)
            ledger.record_discarded_attempt(request.ledger_path, visit=request.visit, attempt_ordinal=1,
                                            workspace_path=workspace, disposition_digest="sha256:" + "c" * 64, run_files=owner)
            if supersession == "new_ordinal":
                bindings = runtime._attempt_bindings(request, attempt_ordinal=2,
                           workspace=workspace, parent_values={"payload": "mode2-child-input"})
                ledger.allocate_attempt(request.ledger_path, visit=request.visit, bindings=bindings, run_files=owner)
        before = _tree_bytes(request.parent_run_root)
        monkeypatch.setattr(child, "compile_and_admit_path_program", lambda **_kwargs: pytest.fail("compiled"))
        with pytest.raises(child._ChildCommandError, match="request_invalid"):
            child.execute_path_request(decoded)
        assert _tree_bytes(request.parent_run_root) == before


def test_live_parent_requires_exact_acknowledged_digest(tmp_path):
    with _checked_launch_fixture(tmp_path) as (request, fixture, document, owner):
        before = _tree_bytes(request.parent_run_root)
        with pytest.raises(ValueError, match="acknowledged row"):
            launch_authority.validate_parent_launch(document, parent_root_fd=owner.root_fd,
                step_config=request.step_config, materialized_source=fixture.materialized_source,
                expected_row_digest="sha256:" + "f" * 64)
        assert _tree_bytes(request.parent_run_root) == before


def test_default_v2_launcher_transports_fd_only_in_memory(tmp_path, monkeypatch):
    with _checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        observed = {}

        def run_process(argv, **kwargs):
            observed.update(argv=argv, **kwargs)
            return type("Completed", (), {"returncode": 0, "stdout": b"{}", "stderr": b""})()

        monkeypatch.setattr(runtime.subprocess, "run", run_process)
        launch = runtime.RunRefChildLaunch("path", fixture.request_path, document,
                    fixture.materialized_source.workspace_path, document["child_run_id"], owner.root_fd)
        before = fixture.request_path.read_bytes()
        runtime._default_child_launcher(launch)
        assert observed["argv"][1:3] == ("-I", "-c")
        assert observed["argv"][5:] == ("--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd))
        assert (observed["pass_fds"], observed["cwd"], observed["shell"]) == ((owner.root_fd,), launch.workspace, False)
        assert "PYTHONPATH" not in observed["env"]
        assert fixture.request_path.read_bytes() == before == canonical_json_bytes(document)
        assert set(document["parent_authority"]) == {"run_root", "identity", "attempt"}
