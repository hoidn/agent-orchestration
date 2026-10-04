"""Checked child values remain direct, typed and reusable after parent commit."""

import base64
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from dataclasses import replace

import pytest

from orchestrator.cli.commands.evaluated import bind_program_inputs
from orchestrator.workflow.evaluated.authority import publish_run_authority
from orchestrator.workflow.evaluated.machine import site_classes, site_nodes
from orchestrator.workflow.evaluated.memo import append_record, read_memo
from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig
from orchestrator.workflow.run_ref import ledger, runtime
from orchestrator.workflow.run_ref import evaluated_child
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_memo import _committed, _started
from tests.test_workflow_evaluated_path_compile import _closed_source, _closed_source_fixture
from tests import test_workflow_evaluated_run_ref_caller as caller
from orchestrator.workflow.workspace_files import WorkspaceFiles


@contextmanager
def _checked_child_fixture(root, *, source=None, type_name="String", value="direct", definitions="", imports=None, returns=None, parent_files=None):
    returns = returns or type_name
    source = source or _closed_source(parameters=f"(payload {type_name})", returns=returns, import_form=definitions)
    fixture = _closed_source_fixture(root, source, imports)
    workspace = root / "parent-workspace"
    workspace.mkdir()
    for name, content in {**(imports or {}), **(parent_files or {})}.items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    revision = fixture.materialized_source.repository_revision_id
    parent_source = workspace / "parent.orc"
    parent_source.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule parent) {definitions} (export run)
      (defworkflow run ((payload {type_name})) -> String
        (let* ((child (run-ref :source (:repo {json.dumps(revision.normalized_locator)} :commit "{revision.resolved_commit_sha}")
          :program (:path "candidate.orc" :entry run) :inputs (:payload payload) :returns {returns}
          :policy (:environment :deterministic-effect-free :setup ())))) "parent")))''')
    program = build_closed_program_bundle(FrontendBuildRequest(source_path=parent_source, workspace_root=workspace)).program
    node = next(iter(site_nodes(program).values()))
    config = RunRefStepConfig(common=StepCommonConfig(), run_ref=decode_run_ref_static_config(base64.b64decode(node["config"])))
    bound = bind_program_inputs(program, {"payload": value}, workspace=workspace)
    parent_root = workspace / ".orchestrate" / "runs" / "parent-run"
    recipe = {"source_roots": [], "entry_workflow": None, "provider_externs_path": None,
        "prompt_externs_path": None, "imported_workflow_bundles_path": None, "command_boundaries_path": None,
        "input_file": None, "input_overrides": {"payload": value}}
    run_ref_root = fixture.materialized_source.workspace_path.parents[4]
    with publish_run_authority(parent_root, program, run_id=parent_root.name, workflow_file="parent.orc",
        workflow_checksum="sha256:" + sha256(parent_source.read_bytes()).hexdigest(), bound_inputs=bound,
        resume_request=recipe, run_ref_root=run_ref_root.as_posix()) as authority:
        owner = authority.run_files
        identity = next(iter(site_classes(program)))
        append_record(authority.memo_path, _started(identity), run_files=owner)
        append_record(authority.memo_path, {"record": "failed", "identity": identity, "attempt": 1,
            "code": "fixture_retry", "exit_info": {}}, run_files=owner)
        append_record(authority.memo_path, _started(identity, 2), run_files=owner)
        visit = ledger.RunRefVisitKey(parent_run_id=parent_root.name, execution_frame_id="root", call_frame_id=None,
            step_id="root." + canonical_sha256(identity).removeprefix("sha256:"), visit_count=1)
        request = runtime.RunRefRuntimeRequest(step_config=config, visit=visit, parent_state={"bound_inputs": bound},
            parent_workspace=workspace, parent_run_root=parent_root, run_ref_root=run_ref_root, run_files=owner,
            parent_identity=identity, parent_attempt=2)
        yield request, owner


def _commit_prepared(request, prepared, owner):
    append_record(request.parent_run_root / "memo.jsonl", _committed(request.parent_identity, 2,
        effect_class="run_ref", value=dict(prepared.envelope),
        proof={"settled_result": prepared.settled_result.record, "artifacts": dict(prepared.artifacts)}), run_files=owner)
    assert request.parent_identity not in read_memo(request.parent_run_root / "memo.jsonl",
        {request.parent_identity: "run_ref"}, run_files=owner).pending_starts


@pytest.mark.parametrize("optional", [None, "present"])
def test_direct_nested_child_value_survives_envelope_and_reuse(tmp_path, optional):
    common = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common)
      (export Packet Choice) (defunion Choice (KEEP (text String)) (DROP))
      (defrecord Packet (choices List[Choice]) (scores Map[String,Int]) (note Optional[String])))'''
    definition = "(import common :only (Packet Choice))"
    source = _closed_source(parameters='(payload Packet) (label String :default "omitted")',
        import_form=definition, returns="Packet")
    value = {"choices": [{"variant": "KEEP", "text": "nested"}, {"variant": "DROP"}],
        "scores": {"one": 1, "two": 2}, "note": optional}
    with _checked_child_fixture(tmp_path, source=source, type_name="Packet", value=value,
        definitions=definition, imports={"common.orc": common}) as (request, owner):
        launched = []
        def launch_real(launch):
            launched.append(launch)
            return runtime._default_child_launcher(launch)
        prepared = runtime.prepare_run_ref_settlement(request, dependencies=runtime.RunRefRuntimeDependencies(launch_child=launch_real))
        assert prepared.envelope["value"] == value
        _commit_prepared(request, prepared, owner)
        recovered = runtime.validate_completed_run_ref_authority(request, settled_result=prepared.settled_result.record,
            artifacts=prepared.artifacts, reconcile_pending=True)
        before = _tree_bytes(tmp_path)
        reused = runtime.recover_run_ref_settlement(request, settled_result=prepared.settled_result.record, reconcile_pending=False)
        assert recovered.envelope["value"] == reused.envelope["value"] == value
        assert recovered.artifacts == reused.artifacts == prepared.artifacts
        assert ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1].stage == "committed"
        assert _tree_bytes(tmp_path) == before
        assert len(launched) == 1


def test_durable_v2_inputs_do_not_check_path_existence_or_copy(tmp_path, monkeypatch):
    common = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common)
      (export WorkPath) (defpath WorkPath :kind relpath :under "artifacts" :must-exist true))'''
    definition = "(import common :only (WorkPath))"
    source = _closed_source(parameters="(payload WorkPath)", body='"copied"', import_form=definition)
    with _checked_child_fixture(tmp_path, source=source, type_name="WorkPath", value="artifacts/seed.txt", returns="String",
        definitions=definition, imports={"common.orc": common}, parent_files={"artifacts/seed.txt": "source bytes"}) as (request, owner):
        prepared = runtime.prepare_run_ref_settlement(request)
        evidence = json.loads(prepared.evidence_manifest_path.read_bytes())
        document = json.loads(Path(evidence["paths"]["child_request"]).read_bytes())
        row = ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        copied = row.bindings.workspace_path / document["inputs"]["payload"]
        copied.unlink()
        monkeypatch.setattr(runtime, "_copy_path_value", lambda *_args, **_kwargs: pytest.fail("durable path copy"))
        before = _tree_bytes(tmp_path)
        assert runtime._validate_child_request_document(request, row=row, document=document) == ("path", document)
        assert _tree_bytes(tmp_path) == before


def test_float_integer_override_preserves_recipe_and_normalizes_durable_value(tmp_path, monkeypatch):
    real_request = runtime._build_child_request
    def integer_override(*args, **kwargs):
        mode, document = real_request(*args, **kwargs)
        document["inputs"]["payload"] = 1
        return mode, document
    monkeypatch.setattr(runtime, "_build_child_request", integer_override)
    with _checked_child_fixture(tmp_path, type_name="Float", value=1) as (request, owner):
        prepared = runtime.prepare_run_ref_settlement(request)
        root = prepared.settled_result.workspace_path / ".orchestrate" / "runs" / prepared.settled_result.child_run_id
        header = json.loads((root / "run.json").read_bytes())
        assert type(header["resume_request"]["input_overrides"]["payload"]) is int
        assert type(header["bound_inputs"]["payload"]) is float
        assert type(prepared.envelope["value"]) is float
        _commit_prepared(request, prepared, owner)
        finalized = runtime.finalize_run_ref_parent_commit(request, prepared, persisted_settled_result=prepared.settled_result.record)
        before = _tree_bytes(tmp_path)
        reused = runtime.reuse_run_ref_settlement(request, settled_result=prepared.settled_result.record,
            artifacts=prepared.artifacts, reconcile_pending=False)
        assert finalized.envelope == reused.envelope == prepared.envelope
        assert type(reused.envelope["value"]) is float
        assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("type_name,value", [("Bool", True), ("Int", 1), ("Float", 1.5), ("Optional[String]", None),
    ("List[Int]", [1, 2]), ("Map[String,Int]", {"one": 1}), ("Value", {"nested": [None, True, 1, 1.5, "text"]})])
def test_direct_scalar_and_container_values_keep_json_shape(tmp_path, type_name, value):
    with _checked_child_fixture(tmp_path, type_name=type_name, value=value) as (request, owner):
        prepared = runtime.prepare_run_ref_settlement(request)
        assert prepared.envelope["value"] == value
        assert type(prepared.envelope["value"]) is type(value)
        _commit_prepared(request, prepared, owner)
        finalized = runtime.finalize_run_ref_parent_commit(request, prepared, persisted_settled_result=prepared.settled_result.record)
        before = _tree_bytes(tmp_path)
        reused = runtime.reuse_run_ref_settlement(request, settled_result=prepared.settled_result.record,
            artifacts=prepared.artifacts, reconcile_pending=False)
        assert finalized.envelope == reused.envelope == prepared.envelope
        assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("type_name,value,wrong", [("Int", 1, True), ("Bool", True, 1), ("Float", 1.5, True)])
def test_durable_typed_inputs_do_not_equate_bool_and_numeric_values(tmp_path, type_name, value, wrong):
    with _checked_child_fixture(tmp_path, type_name=type_name, value=value) as (request, owner):
        prepared = runtime.prepare_run_ref_settlement(request)
        evidence = json.loads(prepared.evidence_manifest_path.read_bytes())
        document = json.loads(Path(evidence["paths"]["child_request"]).read_bytes())
        document["inputs"]["payload"] = wrong
        row = ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        before = _tree_bytes(tmp_path)
        with pytest.raises(runtime.RunRefRuntimeError, match="child_request_inputs_invalid"):
            runtime._validate_child_request_document(request, row=row, document=document)
        assert _tree_bytes(tmp_path) == before


def test_committed_path_result_is_pure_in_terminal_helper_but_e1_still_checks_artifact(tmp_path):
    common = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common)
      (export WorkPath) (defpath WorkPath :kind relpath :under "artifacts" :must-exist true))'''
    definition = "(import common :only (WorkPath))"
    with _checked_child_fixture(tmp_path, type_name="WorkPath", value="artifacts/seed.txt", definitions=definition,
        imports={"common.orc": common}, parent_files={"artifacts/seed.txt": "source bytes"}) as (request, owner):
        prepared = runtime.prepare_run_ref_settlement(request)
        _commit_prepared(request, prepared, owner)
        runtime.finalize_run_ref_parent_commit(request, prepared, persisted_settled_result=prepared.settled_result.record)
        evidence = json.loads(prepared.evidence_manifest_path.read_bytes())
        document = json.loads(Path(evidence["paths"]["child_request"]).read_bytes())
        result = json.loads(Path(evidence["paths"]["child_result"]).read_bytes())
        row = ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        value = prepared.envelope["value"]
        assert value == document["inputs"]["payload"] != "artifacts/seed.txt"
        (row.bindings.workspace_path / value).unlink()
        before = _tree_bytes(tmp_path)
        assert evaluated_child.validate_evaluated_child_terminal(workspace=row.bindings.workspace_path,
            child_run_id=row.bindings.child_run_id, child_request=document, child_result=result, step_config=request.step_config,
            repository_revision_digest=runtime._repository_revision(request).digest,
            verified_git_tree=row.bindings.verified_git_tree_id)[0] == value
        with pytest.raises(runtime.RunRefRuntimeError, match="run_ref_delta_capture_failed|run_ref_evidence_invalid"):
            runtime.reuse_run_ref_settlement(request, settled_result=prepared.settled_result.record,
                artifacts=prepared.artifacts, reconcile_pending=False)
        assert _tree_bytes(tmp_path) == before


def test_legacy_profile_check_and_state_capture_share_retained_root(tmp_path, monkeypatch):
    with caller._checked_launch_fixture(tmp_path, allocate=False) as (request, _fixture, document, owner):
        request = replace(request, parent_identity=document["parent_authority"]["identity"], parent_attempt=2)
        observed = {}
        real_path_read, real_fd_read = Path.read_bytes, WorkspaceFiles.read
        def swap(path):
            if path != observed.get("state") or observed.get("swapped"):
                return
            root = path.parent
            retained = root.with_name("retained-legacy-child")
            root.rename(retained)
            root.mkdir()
            state = json.loads(observed["payload"])
            state["substitute_marker"] = True
            (root / "state.json").write_text(json.dumps(state))
            (root / "run.json").write_bytes(real_path_read(request.parent_run_root / "run.json"))
            observed.update(swapped=True, retained=retained)
            observed["substitute"] = _tree_bytes(root)
        def path_read(path):
            swap(path)
            return real_path_read(path)
        def fd_read(files, path):
            swap(Path(path))
            return real_fd_read(files, path)
        monkeypatch.setattr(Path, "read_bytes", path_read)
        monkeypatch.setattr(WorkspaceFiles, "read", fd_read)
        def launch_real(launch):
            process = runtime._default_child_launcher(launch)
            assert process.returncode == 0, process.stderr.decode()
            root = launch.workspace / ".orchestrate" / "runs" / launch.child_run_id
            observed.update(payload=real_path_read(root / "state.json"), original=_tree_bytes(root))
            observed["state"] = root / "state.json"
            return process
        with pytest.raises(runtime.RunRefRuntimeError):
            runtime.prepare_run_ref_settlement(request, dependencies=runtime.RunRefRuntimeDependencies(launch_child=launch_real))
        assert observed["swapped"]
        assert ledger.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1].stage == "launched"
        assert _tree_bytes(observed["retained"]) == observed["original"]
        assert _tree_bytes(observed["state"].parent) == observed["substitute"]
