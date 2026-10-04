"""Checked private callers use ordinary closed child compilation."""

import json
import base64
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority, publish_run_authority
from orchestrator.workflow.evaluated.memo import append_record, read_memo
from orchestrator.workflow.evaluated.machine import site_classes, site_nodes
from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig
from orchestrator.workflow.run_ref import child, ledger, runtime
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed import artifact
from tests import test_workflow_evaluated_run_ref_caller as caller
from tests.test_workflow_run_ref_child import _PathFixture, _build_path_fixture, _git, _path_request
from tests.test_workflow_evaluated_memo import _started


def _closed_source_fixture(root, source, imports=None):
    from orchestrator.workflow.run_ref.source import SourceRequest, materialize_source

    repository = root / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    for name, content in {"candidate.orc": source, **(imports or {})}.items():
        (repository / name).write_text(content)
    _git(repository, "add", ".")
    _git(repository, "-c", "user.name=Child Test", "-c", "user.email=child@example.invalid",
         "commit", "--quiet", "-m", "closed fixture")
    source_request = SourceRequest(locator=repository.resolve().as_uri(), commit=_git(repository, "rev-parse", "HEAD"))
    root_ref = (root / "run-ref").resolve()
    workspace = root_ref / "runs" / "parent" / "step" / "1" / "workspace"
    materialized = materialize_source(source_request, run_ref_root=root_ref, workspace=workspace)
    return _PathFixture(materialized, None, "closed-child", workspace / ".orchestrate" / "runs", root / "request.json")


def _closed_source(*, parameters="(payload String)", body="payload", definitions="", returns="String", import_form=""):
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule candidate) {import_form} (export run) {definitions}
      (defworkflow run ({parameters}) -> {returns} {body}))'''


@contextmanager
def _typed_closed_launch(root, monkeypatch, source, *, type_name="String", value="mode2-child-input", definitions="", imports=None, returns="String", parent_files=None):
    from orchestrator.cli.commands.evaluated import bind_program_inputs

    fixture = _closed_source_fixture(root, source, imports)
    workspace = root / "parent-workspace"
    workspace.mkdir()
    for name, content in (imports or {}).items():
        (workspace / name).write_text(content)
    for name, content in (parent_files or {}).items():
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
    program = artifact.build_closed_program_bundle(FrontendBuildRequest(source_path=parent_source, workspace_root=workspace)).program
    node = next(iter(site_nodes(program).values()))
    config = RunRefStepConfig(common=StepCommonConfig(), run_ref=decode_run_ref_static_config(base64.b64decode(node["config"])))
    fixture = replace(fixture, step_config=config)
    bound = bind_program_inputs(program, {"payload": value}, workspace=workspace)
    parent_root = workspace / ".orchestrate" / "runs" / "parent-run"
    recipe = {"source_roots": [], "entry_workflow": None, "provider_externs_path": None,
              "prompt_externs_path": None, "imported_workflow_bundles_path": None,
              "command_boundaries_path": None, "input_file": None, "input_overrides": {"payload": value}}
    with publish_run_authority(parent_root, program, run_id=parent_root.name, workflow_file="parent.orc",
        workflow_checksum="sha256:" + sha256(parent_source.read_bytes()).hexdigest(), bound_inputs=bound,
        resume_request=recipe, run_ref_root=fixture.materialized_source.workspace_path.parents[4].as_posix()) as authority:
        owner = authority.run_files
        identity = next(iter(site_classes(program)))
        append_record(authority.memo_path, _started(identity), run_files=owner)
        visit = ledger.RunRefVisitKey(parent_run_id=parent_root.name, execution_frame_id="root", call_frame_id=None,
            step_id="root." + canonical_sha256(identity).removeprefix("sha256:"), visit_count=1)
        request = runtime.RunRefRuntimeRequest(step_config=config, visit=visit, parent_state={"bound_inputs": bound},
            parent_workspace=workspace, parent_run_root=parent_root, run_ref_root=fixture.materialized_source.workspace_path.parents[4], run_files=owner)
        values = runtime.resolve_run_ref_inputs(config.run_ref.inputs, parent_state={"bound_inputs": bound}, parent_workspace=workspace,
                                               child_workspace=fixture.materialized_source.workspace_path)
        materialized, _baseline, _manifest = runtime._snapshot_post_input_baseline(fixture.materialized_source)
        fixture = replace(fixture, materialized_source=materialized)
        document = _path_request(fixture)
        document.update(schema_version="run_ref_path_child_request.v2", inputs=values,
            parent_authority={"run_root": parent_root.as_posix(), "identity": identity, "attempt": 1})
        real_bindings = runtime._attempt_bindings
        with monkeypatch.context() as allocation_patch:
            allocation_patch.setattr(runtime, "_attempt_bindings", lambda *args, **kwargs:
                real_bindings(*args, **{**kwargs, "parent_values": bound}))
            caller._allocate_launched(request, fixture, document, owner)
        fixture.request_path.write_bytes(canonical_json_bytes(document))
        yield request, fixture, document, owner


def test_authorized_path_child_uses_ordinary_closed_build(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(
        root, target_dsl_version="2.35"))
    prepared = []
    real_prepare = artifact.prepare_closed_program_bundle

    def observe_prepare(request, **kwargs):
        prepared.append(request)
        return real_prepare(request, **kwargs)

    monkeypatch.setattr(artifact, "prepare_closed_program_bundle", observe_prepare)
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(),
                           "--parent-root-fd", str(owner.root_fd)]) == 0, capsys.readouterr().err
        returned = json.loads(capsys.readouterr().out)
        assert returned["schema_version"] == "run_ref_path_child_result.v2"
        assert returned["workflow_outputs"] == {"__result__": "mode2-child-input"}
        assert len(prepared) == 1
        build = prepared[0]
        workspace = fixture.materialized_source.workspace_path
        assert (build.source_roots, build.entry_workflow, build.boundary_admission_profile,
                build.lowering_route, build.emit_debug_yaml) == ((workspace,), "run", None, None, False)
        assert (build.provider_externs_path, build.prompt_externs_path,
                build.imported_workflow_bundles_path, build.command_boundaries_path) == (None,) * 4
        root = workspace / ".orchestrate" / "runs" / document["child_run_id"]
        authority = load_run_authority(root)
        assert authority.header["workflow_file"] == "candidate.orc"
        assert authority.header["resume_request"] == {
            "source_roots": ["."], "entry_workflow": "run", "provider_externs_path": None,
            "prompt_externs_path": None, "imported_workflow_bundles_path": None,
            "command_boundaries_path": None, "input_file": None,
            "input_overrides": {"payload": "mode2-child-input"},
        }
        memo = read_memo(authority.memo_path, {})
        assert memo.terminal.data["value"] == "mode2-child-input"
        assert authority.program.digest == returned["path_compile"]["program_identity"]["program_digest"]


@pytest.mark.parametrize("case", ["required", "input_type", "return_type", "unknown_name", "symlink", "directory"])
def test_closed_child_refuses_source_and_signature_before_publication(tmp_path, monkeypatch, capsys, case):
    choices = {
        "required": _closed_source(parameters="(payload String) (extra String)"),
        "input_type": _closed_source(parameters="(payload Int)", body='"value"'),
        "return_type": _closed_source(returns="Int", body="1"),
        "unknown_name": _closed_source(body="missing_name"),
    }
    source = choices.get(case, _closed_source())
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _closed_source_fixture(root, source))
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        path = fixture.materialized_source.workspace_path / "candidate.orc"
        if case == "symlink":
            target = path.with_suffix(".held")
            path.rename(target)
            path.symlink_to(target.name)
        elif case == "directory":
            path.unlink()
            path.mkdir()
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        diagnostic = json.loads(capsys.readouterr().err)
        assert diagnostic["status"] == "rejected"
        assert not (fixture.state_dir / document["child_run_id"]).exists()
        if case == "unknown_name":
            assert diagnostic["compile_diagnostics"]["status"] == "rejected"
        elif case in {"required", "input_type", "return_type"}:
            assert diagnostic["code"] == "trial_program_signature_mismatch"
            assert "compile_diagnostics" not in diagnostic


def test_closed_signature_retains_nominal_identity(tmp_path, monkeypatch, capsys):
    common = '(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule common) (export Packet) (defrecord Packet (text String)))'
    source = _closed_source(parameters="(payload Packet)", definitions="(defrecord Packet (text String))", body="payload.text")
    with _typed_closed_launch(tmp_path, monkeypatch, source, type_name="Packet", value={"text": "nominal"},
        definitions="(import common :only (Packet))", imports={"common.orc": common}) as (_request, fixture, document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        diagnostic = json.loads(capsys.readouterr().err)
        assert diagnostic["code"] == "trial_program_signature_mismatch"
        assert not (fixture.state_dir / document["child_run_id"]).exists()


def test_closed_facts_validator_uses_recorded_authority_without_source_io(tmp_path, monkeypatch, capsys):
    from pathlib import Path
    from orchestrator.workflow.run_ref import path_compile
    from orchestrator.workflow.run_ref.closed_path import validate_closed_path_facts

    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 0
        facts = json.loads(capsys.readouterr().out)["path_compile"]
        program = load_run_authority(fixture.state_dir / document["child_run_id"]).program
        (fixture.materialized_source.workspace_path / "candidate.orc").unlink()
        with monkeypatch.context() as validation_patch:
            forbidden = lambda *_args, **_kwargs: pytest.fail("durable facts recaptured filesystem or installed compiler")
            validation_patch.setattr(Path, "read_bytes", forbidden)
            validation_patch.setattr(Path, "read_text", forbidden)
            validation_patch.setattr(path_compile, "_require_path_compiler_identity", forbidden)
            validate_closed_path_facts(facts, program=program, materialized_source=fixture.materialized_source,
                                       step_config=fixture.step_config)


def test_closed_facts_do_not_equate_bool_and_int(tmp_path, monkeypatch, capsys):
    from orchestrator.workflow.run_ref.closed_path import validate_closed_path_facts
    from orchestrator.workflow.run_ref.path_compile import RunRefPathCompileRefusal

    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 0
        facts = json.loads(capsys.readouterr().out)["path_compile"]
        program = load_run_authority(fixture.state_dir / document["child_run_id"]).program
        facts["signature"]["inputs"][0]["required"] = 1
        with pytest.raises(RunRefPathCompileRefusal):
            validate_closed_path_facts(facts, program=program, materialized_source=fixture.materialized_source,
                                       step_config=fixture.step_config)


@pytest.mark.parametrize("field", ["signature", "effect_facts", "program_identity", "evidence", "diagnostics", "extra"])
def test_closed_facts_are_checked_before_publication(tmp_path, monkeypatch, capsys, field):
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    real_admit = child._admit_path_request

    def change_facts(request):
        admitted = real_admit(request)
        facts = admitted.path_compile
        changes = {"signature": {"inputs": [], "return": {"kind": "primitive", "name": "Int"}},
                   "effect_facts": {"direct": [], "transitive": [], "procedure_edges": []},
                   "program_identity": {"schema_version": "workflow_lisp_program_identity.v2"},
                   "evidence": {}, "diagnostics": [{}], "extra": True}
        facts[field] = changes[field]
        return replace(admitted, _facts_json=canonical_json_bytes(facts))

    monkeypatch.setattr(child, "_admit_path_request", change_facts)
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "path_compile_rejected"
        root = fixture.materialized_source.workspace_path / ".orchestrate" / "runs" / document["child_run_id"]
        assert not root.exists()


def test_closed_child_invalid_input_retains_binding_refusal(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    with caller._checked_launch_fixture(tmp_path, allocate=False) as (request, fixture, document, owner):
        document["inputs"] = {"payload": 17}
        caller._allocate_launched(request, fixture, document, owner)
        fixture.request_path.write_bytes(canonical_json_bytes(document))
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        assert json.loads(capsys.readouterr().err)["reason"] == "input_binding_rejected"
        assert not (fixture.state_dir / document["child_run_id"]).exists()


@pytest.mark.parametrize("metadata", ["missing_diagnostics", "malformed_effects", "nonempty_effects", "nonempty_sites"])
def test_closed_child_requires_actual_compile_metadata(tmp_path, monkeypatch, capsys, metadata):
    from orchestrator.workflow_lisp.effects import EffectSummary, UsesCommandEffect

    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    real_prepare = artifact.prepare_closed_program_bundle
    parent_program = []

    def change_metadata(*args, **kwargs):
        built = real_prepare(*args, **kwargs)
        if args[0].source_path.name != "candidate.orc":
            return built
        effects = frozenset({UsesCommandEffect(("fixture",))})
        changes = {"missing_diagnostics": {"compile_diagnostics": None},
                   "malformed_effects": {"entry_effect_summary": None},
                   "nonempty_effects": {"entry_effect_summary": EffectSummary(effects, effects, frozenset())},
                   "nonempty_sites": {"program": parent_program[0]}}
        return replace(built, **changes[metadata])

    monkeypatch.setattr(artifact, "prepare_closed_program_bundle", change_metadata)
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        parent_program.append(load_run_authority(_request.parent_run_root, run_files=owner).program)
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        diagnostic = json.loads(capsys.readouterr().err)
        expected = "trial_program_compile_rejected" if metadata == "missing_diagnostics" else "trial_candidate_environment_not_admissible"
        assert (diagnostic["reason"], diagnostic["code"]) == ("path_compile_rejected", expected)
        assert "compile_diagnostics" not in diagnostic
        assert not (fixture.state_dir / document["child_run_id"]).exists()


def test_closed_child_retains_linked_diagnostics(tmp_path, monkeypatch, capsys):
    from orchestrator.workflow_lisp import compiler
    from orchestrator.workflow_lisp.diagnostics import serialize_diagnostics
    from orchestrator.workflow_lisp.lints import required_lint_diagnostic
    from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan

    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    real_compile = compiler.compile_stage3_entrypoint
    linked = []

    def retain_warning(*args, **kwargs):
        result = real_compile(*args, **kwargs)
        if args[0].name == "candidate.orc":
            position = SourcePosition(path=args[0].as_posix(), line=1, column=1, offset=0)
            warning = required_lint_diagnostic("low_level_state_path_in_high_level_module",
                message="linked-result capture fixture", span=SourceSpan(start=position, end=position))
            result = replace(result, diagnostics=(*result.diagnostics, warning))
            linked.append(result.diagnostics)
        return result

    monkeypatch.setattr(compiler, "compile_stage3_entrypoint", retain_warning)
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, _document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 0
        facts = json.loads(capsys.readouterr().out)["path_compile"]
        assert len(linked) == 1
        assert facts["diagnostics"] == serialize_diagnostics(linked[0])


def test_closed_child_allows_pure_procedure(tmp_path, monkeypatch, capsys):
    from orchestrator.workflow.run_ref.closed_path import _require_closed_effects
    from orchestrator.workflow_lisp.effects import EffectSummary, ProcedureCallEdge

    definition = '(defproc carry ((value String)) -> String :effects () :lowering inline value)'
    source = _closed_source(definitions=definition, body="(carry payload)")
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _closed_source_fixture(root, source))
    captured = []
    real_prepare = artifact.prepare_closed_program_bundle

    def observe_prepare(*args, **kwargs):
        result = real_prepare(*args, **kwargs)
        captured.append(result)
        return result

    monkeypatch.setattr(artifact, "prepare_closed_program_bundle", observe_prepare)
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, _document, owner):
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 0
        returned = json.loads(capsys.readouterr().out)
        # The actual inline compiler erases pure edges; independently retain a
        # well-typed edge to prove that E1 does not forbid this metadata.
        summary = EffectSummary(frozenset(), frozenset(), frozenset({ProcedureCallEdge("candidate/carry")}))
        with_edge = replace(captured[-1], entry_effect_summary=summary)
        assert _require_closed_effects(with_edge, fixture.step_config) == {"direct": [], "transitive": []}
        assert returned["path_compile"]["effect_facts"] == {"direct": [], "transitive": []}
        assert returned["workflow_outputs"] == {"__result__": "mode2-child-input"}


def test_old_import_graph_matches_public_closed_admission(tmp_path, monkeypatch, capsys):
    from orchestrator.cli.commands.compile import compile_workflow
    from orchestrator.cli.main import create_parser

    old = '''(workflow-lisp (:language "0.1") (:target-dsl "2.24")
      (defmodule old) (export choose Choice)
      (defunion Choice (KEEP (value String)) (DROP))
      (defworkflow choose ((payload Choice)) -> String
        (match payload (KEEP (value) value) (DROP () "drop"))))'''
    source = _closed_source(import_form="(import old :only (choose Choice))",
                            body="(call choose :payload (variant Choice KEEP :value payload))")
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root:
        _closed_source_fixture(root, source, {"old.orc": old}))
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        workspace = fixture.materialized_source.workspace_path
        monkeypatch.chdir(workspace)
        args = create_parser().parse_args(["compile", "candidate.orc", "--source-root", ".",
                                          "--entry-workflow", "run", "--diagnostics-json"])
        assert compile_workflow(args) == 2
        public = json.loads(capsys.readouterr().out)
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        private = json.loads(capsys.readouterr().err)["compile_diagnostics"]
        assert public["status"] == private["status"] == "rejected"
        assert [row["code"] for row in public["diagnostics"]] == [row["code"] for row in private["diagnostics"]] == ["workflow_boundary_type_invalid"]
        assert not (fixture.state_dir / document["child_run_id"]).exists()


def test_closed_child_checks_compiler_before_build(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import path_compile

    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, document, owner):
        monkeypatch.setattr(path_compile, "compute_compiler_runtime_identity", lambda:
                            SimpleNamespace(digest="sha256:" + "f" * 64))
        monkeypatch.setattr(artifact, "prepare_closed_program_bundle", lambda *_args, **_kwargs: pytest.fail("compiled foreign identity"))
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 2
        diagnostic = json.loads(capsys.readouterr().err)
        assert diagnostic["code"] == "trial_program_compile_rejected"
        assert diagnostic["secondary_causes"] == ["compiler_runtime_identity_mismatch"]
        assert not (fixture.state_dir / document["child_run_id"]).exists()


def test_closed_child_never_uses_flat_execution_or_build_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(caller, "_build_path_fixture", lambda root: _build_path_fixture(root, target_dsl_version="2.35"))
    with caller._checked_launch_fixture(tmp_path) as (_request, fixture, _document, owner):
        forbidden = lambda *_args, **_kwargs: pytest.fail("legacy dispatch or second cache publication")
        monkeypatch.setattr(child, "compile_and_admit_path_program", forbidden)
        monkeypatch.setattr(child, "_execute_bundle", forbidden)
        monkeypatch.setattr(artifact, "build_closed_program_bundle", forbidden)
        assert child.main(["--path-request", fixture.request_path.as_posix(), "--parent-root-fd", str(owner.root_fd)]) == 0
        assert json.loads(capsys.readouterr().out)["schema_version"] == "run_ref_path_child_result.v2"
