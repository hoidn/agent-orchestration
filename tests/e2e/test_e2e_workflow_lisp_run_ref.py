"""End-to-end acceptance for target-2.24 ``run-ref`` execution."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.run_ref.runtime import (
    RunRefRuntimeDependencies,
)
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.compiler import LoweringRoute
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.workflow_bundle_helpers import bundle_context_dict


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", repository.as_posix(), *args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _commit_candidate(repository: Path, source: str) -> str:
    repository.mkdir()
    _git(repository, "init", "--quiet")
    (repository / "candidate.orc").write_text(source, encoding="utf-8")
    _git(repository, "add", "candidate.orc")
    _git(
        repository,
        "-c",
        "user.name=Run Ref E2E",
        "-c",
        "user.email=run-ref-e2e@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "candidate",
    )
    return _git(repository, "rev-parse", "HEAD")


def _build_controller(workspace: Path, source: str):
    source_path = workspace / "controller.orc"
    source_path.write_text(source, encoding="utf-8")
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(workspace,),
            entry_workflow="orchestrate",
            workspace_root=workspace,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    return source_path, result.validated_bundle


def _execute_controller(
    workspace: Path,
    *,
    source_path: Path,
    bundle,
    run_id: str,
    run_ref_root: Path,
):
    manager = StateManager(workspace=workspace, run_id=run_id)
    manager.initialize(
        source_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={},
    )
    manager.bind_run_ref_root(run_ref_root)
    state = WorkflowExecutor(
        bundle,
        workspace,
        manager,
        max_retries=0,
        retry_delay_ms=0,
    ).execute(on_error="stop")
    return state, manager


def _assert_complete_evidence_manifest(
    attempt_root: Path,
    *,
    settlement: dict,
    mode: str,
) -> dict:
    manifest = json.loads(
        (attempt_root / "evidence-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == "run_ref_evidence_manifest.v1"
    assert manifest["mode"] == mode
    assert manifest["attempt_ordinal"] == settlement["attempt_ordinal"]
    assert manifest["child_run_id"] == settlement["child_run_id"]
    assert manifest["step_config_digest"] == settlement["step_config_digest"]
    assert manifest["child_terminal_state_digest"] == settlement[
        "child_terminal_state_digest"
    ]
    assert manifest["result_contract_digest"] == settlement[
        "result_contract_digest"
    ]
    assert manifest["result_payload_digest"] == settlement[
        "result_payload_digest"
    ]
    assert manifest["workspace_delta_digest"] == settlement[
        "workspace_delta_digest"
    ]
    assert manifest["accounting_digest"] == settlement["accounting_digest"]
    assert canonical_sha256(manifest) == settlement["evidence_manifest_digest"]
    assert set(manifest["paths"]) == {
        "accounting",
        "baseline",
        "child_request",
        "child_result",
        "child_state",
        "setup_evidence",
        "workspace",
        "workspace_delta",
    }
    assert all(Path(value).exists() for value in manifest["paths"].values())
    return manifest


def test_mode2_pinned_bool_executes_through_real_parent_and_child(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    commit = _commit_candidate(
        candidate,
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defworkflow run () -> Bool
    true))
""",
    )
    parent = tmp_path / "parent"
    parent.mkdir()
    source_path, bundle = _build_controller(
        parent,
        f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule controller)
  (export orchestrate)
  (defworkflow orchestrate () -> Bool
    (let* ((attempt
             (run-ref
               :source (:repo "{candidate.resolve().as_uri()}"
                        :commit "{commit}")
               :program (:path "candidate.orc" :entry run)
               :inputs ()
               :returns Bool
               :policy (:environment :deterministic-effect-free :setup ()))))
      attempt.value)))
""",
    )
    external_root = (tmp_path / "run-ref-root").resolve()

    state, manager = _execute_controller(
        parent,
        source_path=source_path,
        bundle=bundle,
        run_id="mode2-parent",
        run_ref_root=external_root,
    )

    assert state["status"] == "completed", state.get("error")
    assert state["workflow_outputs"] == {"__result__": True}
    run_ref_step = next(
        step
        for step in state["steps"].values()
        if isinstance(step.get("run_ref"), dict)
    )
    assert run_ref_step["artifacts"]["value"] is True
    settlement = run_ref_step["run_ref"]
    workspace = Path(settlement["workspace_path"])
    assert workspace.is_relative_to(external_root)
    assert not workspace.is_relative_to(parent)
    assert not manager.run_root.is_relative_to(external_root)
    child_state = (
        workspace
        / ".orchestrate"
        / "runs"
        / settlement["child_run_id"]
        / "state.json"
    )
    assert json.loads(child_state.read_text(encoding="utf-8"))["status"] == (
        "completed"
    )
    attempt_root = workspace.parent
    child_result = json.loads(
        (attempt_root / "child-result.json").read_text(encoding="utf-8")
    )
    assert child_result["schema_version"] == "run_ref_path_child_result.v1"
    assert child_result["workflow_outputs"] == {"__result__": True}
    assert child_result["path_compile"]["diagnostics"]["status"] == "accepted"
    child_request = json.loads(
        (attempt_root / "child-request.json").read_text(encoding="utf-8")
    )
    assert child_request["materialized_source"]["resolved_commit_sha"] == commit
    assert child_result["path_compile"]["evidence"][
        "repository_revision_digest"
    ] == child_request["materialized_source"]["repository_revision"]["digest"]
    delta = json.loads(
        (attempt_root / "workspace-delta.json").read_text(encoding="utf-8")
    )
    delta_bytes = (attempt_root / "workspace-delta.json").read_bytes()
    accounting = json.loads(
        (attempt_root / "accounting.json").read_text(encoding="utf-8")
    )
    evidence_manifest = _assert_complete_evidence_manifest(
        attempt_root,
        settlement=settlement,
        mode="path",
    )
    assert set(delta) == {
        "base",
        "changed_files",
        "deleted_files",
        "untracked_files",
        "normalized_diff",
        "declared_artifacts",
    }
    assert delta["base"]["resolved_commit_sha"] == commit
    assert accounting["provider_attempts"] == "UNKNOWN"
    assert accounting["token_usage"] == "UNKNOWN"
    assert accounting["cost"] == "UNKNOWN"
    assert evidence_manifest["repository_revision_digest"] == delta["base"][
        "digest"
    ]
    ledger = load_attempt_ledger(manager.run_root / "run-ref-attempts.jsonl")
    assert ledger.rows[-1].stage == "committed"
    assert ledger.rows[-1].bindings.workspace_delta_digest == settlement[
        "workspace_delta_digest"
    ]

    repeat_state, repeat_manager = _execute_controller(
        parent,
        source_path=source_path,
        bundle=bundle,
        run_id="mode2-parent-repeat",
        run_ref_root=external_root,
    )
    assert repeat_state["status"] == "completed", repeat_state.get("error")
    repeat_step = next(
        step
        for step in repeat_state["steps"].values()
        if isinstance(step.get("run_ref"), dict)
    )
    repeat_attempt_root = Path(repeat_step["run_ref"]["workspace_path"]).parent
    repeat_child_result = json.loads(
        (repeat_attempt_root / "child-result.json").read_text(encoding="utf-8")
    )
    assert repeat_child_result["path_compile"]["program_identity"] == (
        child_result["path_compile"]["program_identity"]
    )
    assert (
        repeat_attempt_root / "workspace-delta.json"
    ).read_bytes() == delta_bytes
    assert load_attempt_ledger(
        repeat_manager.run_root / "run-ref-attempts.jsonl"
    ).rows[-1].stage == "committed"


def test_mode1_imported_asset_child_executes_from_procedure_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    commit = _commit_candidate(
        candidate,
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defworkflow run () -> String
    "candidate-workspace"))
""",
    )
    parent = tmp_path / "parent"
    child_module = parent / "child_command"
    child_module.mkdir(parents=True)
    (child_module / "asset_child.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule child_command/asset_child)
  (export render)
  (defworkflow render ((value String)) -> String
    (provider-result providers.render
      :prompt prompts.render
      :inputs (value)
      :returns String)))
""",
        encoding="utf-8",
    )
    (child_module / "entry.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule child_command/entry)
  (import child_command/asset_child :only (render))
  (export run)
  (defworkflow run ((value String)) -> String
    (call render :value value)))
""",
        encoding="utf-8",
    )
    asset_marker = "RUN-REF-MODE1-ASSET-CLOSURE"
    (child_module / "render.md").write_text(
        f"Return the typed input. {asset_marker}\n",
        encoding="utf-8",
    )
    providers_path = parent / "providers.json"
    providers_path.write_text(
        json.dumps({"providers.render": "gemini"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prompts_path = parent / "prompts.json"
    prompts_path.write_text(
        json.dumps(
            {"prompts.render": {"asset_file": "render.md"}},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    controller = f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule controller)
  (import child_command/entry :as child :only (run))
  (export orchestrate)
  (defworkflow bundled-child ((value String)) -> String
    (call child.run :value value))
  (defproc launch-child () -> String
    :effects ((runs-ref controller::bundled-child))
    :lowering inline
    (let* ((attempt
             (run-ref
               :source (:repo "{candidate.resolve().as_uri()}"
                        :commit "{commit}")
               :program (:bundle bundled-child)
               :inputs (:value "typed-child-input")
               :policy (:setup ()))))
      attempt.value))
  (defworkflow orchestrate () -> String
    (if true
        (launch-child)
        "unreached")))
"""
    source_path = parent / "controller.orc"
    source_path.write_text(controller, encoding="utf-8")
    built = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(parent,),
            entry_workflow="orchestrate",
            provider_externs_path=providers_path,
            prompt_externs_path=prompts_path,
            workspace_root=parent,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )

    executable_dir = tmp_path / "bin"
    executable_dir.mkdir()
    provider = executable_dir / "gemini"
    provider.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

prompt = " ".join(sys.argv[1:])
if "RUN-REF-MODE1-ASSET-CLOSURE" not in prompt:
    raise SystemExit("prompt asset was not staged")
if "typed-child-input" not in prompt:
    raise SystemExit("typed input was not rendered")
target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps("staged-import-and-asset-ok") + "\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    provider.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        executable_dir.as_posix() + os.pathsep + os.environ["PATH"],
    )
    external_root = (tmp_path / "run-ref-root-mode1").resolve()

    state, manager = _execute_controller(
        parent,
        source_path=source_path,
        bundle=built.validated_bundle,
        run_id="mode1-parent",
        run_ref_root=external_root,
    )

    assert state["status"] == "completed", state.get("error")
    assert state["workflow_outputs"] == {
        "__result__": "staged-import-and-asset-ok"
    }
    run_ref_step = next(
        step
        for step in state["steps"].values()
        if isinstance(step.get("run_ref"), dict)
    )
    assert run_ref_step["artifacts"]["value"] == (
        "staged-import-and-asset-ok"
    )
    settlement = run_ref_step["run_ref"]
    workspace = Path(settlement["workspace_path"])
    assert workspace.is_relative_to(external_root)
    assert not workspace.is_relative_to(parent)
    assert not manager.run_root.is_relative_to(external_root)
    attempt_root = workspace.parent
    child_request = json.loads(
        (attempt_root / "child-request.json").read_text(encoding="utf-8")
    )
    child_result = json.loads(
        (attempt_root / "child-result.json").read_text(encoding="utf-8")
    )
    assert child_request["schema_version"] == "run_ref_child_request.v1"
    assert child_request["target_workflow_name"] == "controller::bundled-child"
    assert child_result["workflow_outputs"] == {
        "__result__": "staged-import-and-asset-ok"
    }
    assert child_result["capsule_digest"] == child_request[
        "expected_capsule_digest"
    ]
    assert "path_compile" not in child_result
    child_state = json.loads(
        (
            workspace
            / ".orchestrate"
            / "runs"
            / settlement["child_run_id"]
            / "state.json"
        ).read_text(encoding="utf-8")
    )
    [imported_call] = child_state["steps"].values()
    assert imported_call["debug"]["call"]["import_alias"] == (
        "child_command/entry::run"
    )
    staged_capsule = (
        workspace / ".orchestrate" / "run-ref-capsule" / "closure" / "source"
    )
    assert (staged_capsule / "controller.orc").is_file()
    assert (staged_capsule / "entry.orc").is_file()
    assert (staged_capsule / "asset_child.orc").is_file()
    assert (
        staged_capsule / "render.md"
    ).read_text(encoding="utf-8") == f"Return the typed input. {asset_marker}\n"
    delta = json.loads(
        (attempt_root / "workspace-delta.json").read_text(encoding="utf-8")
    )
    accounting = json.loads(
        (attempt_root / "accounting.json").read_text(encoding="utf-8")
    )
    evidence_manifest = _assert_complete_evidence_manifest(
        attempt_root,
        settlement=settlement,
        mode="bundle",
    )
    assert delta["base"]["resolved_commit_sha"] == commit
    assert delta["changed_files"] == []
    assert delta["deleted_files"] == []
    assert len(delta["untracked_files"]) == 1
    assert delta["untracked_files"][0]["path"] == "logs"
    assert delta["untracked_files"][0]["kind"] == "directory"
    assert delta["declared_artifacts"] == []
    assert accounting["provider_attempts"] == "UNKNOWN"
    assert accounting["token_usage"] == "UNKNOWN"
    assert accounting["cost"] == "UNKNOWN"
    assert evidence_manifest["repository_revision_digest"] == delta["base"][
        "digest"
    ]
    ledger = load_attempt_ledger(manager.run_root / "run-ref-attempts.jsonl")
    assert ledger.rows[-1].stage == "committed"
    assert ledger.rows[-1].bindings.workspace_delta_digest == settlement[
        "workspace_delta_digest"
    ]


def test_committed_site_reuses_and_incomplete_site_reruns_fresh_on_resume(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    commit = _commit_candidate(
        candidate,
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defworkflow run () -> Bool
    true))
""",
    )
    parent = tmp_path / "parent"
    parent.mkdir()
    source_path, bundle = _build_controller(
        parent,
        f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule controller)
  (export orchestrate)
  (defworkflow orchestrate () -> Bool
    (let* ((first
             (run-ref
               :source (:repo "{candidate.resolve().as_uri()}"
                        :commit "{commit}")
               :program (:path "candidate.orc" :entry run)
               :inputs ()
               :returns Bool
               :policy (:environment :deterministic-effect-free :setup ())))
           (second
             (run-ref
               :source (:repo "{candidate.resolve().as_uri()}"
                        :commit "{commit}")
               :program (:path "candidate.orc" :entry run)
               :inputs ()
               :returns Bool
               :policy (:environment :deterministic-effect-free :setup ()))))
      (if first.value second.value false))))
""",
    )
    external_root = (tmp_path / "run-ref-root-recovery").resolve()
    run_id = "recovery-parent"
    manager = StateManager(workspace=parent, run_id=run_id)
    manager.initialize(
        source_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={},
    )
    manager.bind_run_ref_root(external_root)
    base_dependencies = RunRefRuntimeDependencies()
    launches = []

    def counted_launch(launch):
        launches.append(launch)
        return base_dependencies.launch_child(launch)

    def crash_second_site(boundary: str) -> None:
        if boundary == "launch" and len(launches) == 1:
            raise RuntimeError("injected-second-site-launch-crash")

    executor = WorkflowExecutor(
        bundle,
        parent,
        manager,
        max_retries=0,
        retry_delay_ms=0,
        provider_observation_enabled=False,
    )
    executor._run_ref_runtime_dependencies = replace(
        base_dependencies,
        launch_child=counted_launch,
        crash_hook=crash_second_site,
    )

    with pytest.raises(
        RuntimeError,
        match="injected-second-site-launch-crash",
    ):
        executor.execute(on_error="stop")

    assert manager.load().status == "failed"
    ledger_path = manager.run_root / "run-ref-attempts.jsonl"
    before = load_attempt_ledger(ledger_path)
    committed = [
        row
        for row in before.rows
        if row.stage == "committed" and row.status == "committed"
    ]
    assert len(committed) == 1
    committed_visit = committed[0].visit
    committed_rows_before = tuple(
        row for row in before.rows if row.visit == committed_visit
    )
    incomplete = before.rows[-1]
    assert incomplete.visit != committed_visit
    assert incomplete.attempt_ordinal == 1
    assert (incomplete.stage, incomplete.status) == ("launched", "in_progress")
    assert incomplete.bindings.workspace_path.is_dir()
    interrupted_workspace = incomplete.bindings.workspace_path
    interrupted_child_id = incomplete.bindings.child_run_id

    resume_manager = StateManager(workspace=parent, run_id=run_id)
    resume_manager.load()
    resume_executor = WorkflowExecutor(
        bundle,
        parent,
        resume_manager,
        max_retries=0,
        retry_delay_ms=0,
        provider_observation_enabled=False,
    )
    resume_executor._run_ref_runtime_dependencies = replace(
        base_dependencies,
        launch_child=counted_launch,
    )
    resumed = resume_executor.execute(on_error="stop", resume=True)

    assert resumed["status"] == "completed", resumed.get("error")
    assert resumed["workflow_outputs"] == {"__result__": True}
    after = load_attempt_ledger(ledger_path)
    assert tuple(
        row for row in after.rows if row.visit == committed_visit
    ) == committed_rows_before
    assert len(launches) == 2
    assert launches[0].child_run_id == committed[0].bindings.child_run_id
    assert sum(
        launch.child_run_id == committed[0].bindings.child_run_id
        for launch in launches
    ) == 1
    assert all(
        launch.child_run_id != interrupted_child_id for launch in launches
    )
    interrupted_rows = [
        row for row in after.rows if row.visit == incomplete.visit
    ]
    discarded = [
        row
        for row in interrupted_rows
        if row.attempt_ordinal == 1 and row.status == "discarded"
    ]
    assert len(discarded) == 1
    assert not interrupted_workspace.exists()
    disposition_path = interrupted_workspace.parent / "disposition.json"
    disposition = json.loads(disposition_path.read_text(encoding="utf-8"))
    assert disposition["disposition"] == (
        "discard_incomplete_attempt_and_rerun_fresh"
    )
    assert disposition["workspace_deletion"] == {
        "status": "deleted_or_confirmed_absent",
        "workspace_absent": True,
    }
    recovered = [
        row
        for row in interrupted_rows
        if row.attempt_ordinal == 2
        and row.stage == "committed"
        and row.status == "committed"
    ]
    assert len(recovered) == 1
    assert recovered[0].bindings.workspace_path != interrupted_workspace
    assert recovered[0].bindings.child_run_id != interrupted_child_id
    assert recovered[0].visit.visit_count == incomplete.visit.visit_count == 1


def test_target_224_rejects_run_ref_inside_loop_recur(tmp_path: Path) -> None:
    workspace = tmp_path / "loop-refusal"
    workspace.mkdir()
    source_path = workspace / "controller.orc"
    source_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule controller)
  (export orchestrate)
  (defworkflow child () -> Bool
    true)
  (defworkflow orchestrate () -> Bool
    (loop/recur :max 1 :state false
      (fn (state)
        (let* ((attempt
                 (run-ref
                   :source (:repo "file:///candidate"
                            :commit "0000000000000000000000000000000000000000")
                   :program (:bundle child)
                   :inputs ()
                   :policy (:setup ()))))
          (done attempt.value))))))
""",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(
            FrontendBuildRequest(
                source_path=source_path,
                source_roots=(workspace,),
                entry_workflow="orchestrate",
                workspace_root=workspace,
                lowering_route=LoweringRoute.WCC_M4,
            )
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_placement_invalid"
