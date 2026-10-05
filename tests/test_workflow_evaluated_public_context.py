"""Public context and committed provider-path semantics, with real performers."""

import json
import os
from pathlib import Path

import pytest

from tests.test_workflow_evaluated_providers import (
    _assert_attempt_evidence, _assert_cli_resumes_unchanged,
    _assert_public_request_contract, _fixture, _orchestrate_snapshot, _requests,
)
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.workflow_evaluated_totality_helpers import (
    checked_run, compile_public, pause_public, public_run,
)
from tests.workflow_evaluated_context_helpers import (
    assert_pure_public, pure_files, public_entry_cli, legacy_carried_context,
    prepare_public_producers, pause_context, assert_public_producer_commits,
    assert_public_producer_requests,
    prepare_library_producers, assert_library_configuration, pause_library_fourth,
    assert_library_requests, assert_library_replays,
    prepare_phase_provider, legacy_phase_provider, public_context_run, assert_completed_resumes,
    assert_library_command_inventory,
)
from tests.test_workflow_lisp_closed_program_elaboration import _BIND_PROC_CAPTURE_SOURCE
from tests.test_workflow_evaluated_call_routes import _legacy_context_output
from tests.test_workflow_evaluated_cli import _run_cli


PROVIDER_PATH_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
  (defrecord Result (ok Bool))
  (defrecord Projection (bundle ResultBundle))
  (defworkflow run ((message String)) -> Projection
    (let* ((r (provider-result providers.review :prompt prompts.base
               :inputs (message) :model "chosen-model" :effort "low" :returns Result)))
      (record Projection :bundle (provider-bundle-path r :as ResultBundle)))))'''


def _provider_files(root, source=PROVIDER_PATH_SOURCE):
    fixture = _fixture(root, source)
    commands = root / "commands.json"
    commands.write_text("{}")
    files = {"workspace": root, "source": fixture[0], "source_root": root,
             "providers": fixture[1], "prompts": fixture[2], "commands": commands}
    inputs = root / "inputs.json"
    inputs.write_text(json.dumps({"message": "typed input"}))
    return files, inputs


def _assert_provider_commit(root, authority, entry):
    (request,) = _requests(root)
    row = entry.data
    assert row["effect_class"] == "provider"
    assert row["value"] == {"ok": True}
    assert row["attempt"] == 1
    assert json.loads(authority.memo_path.read_bytes()[entry.offset:].splitlines()[0]) == row
    _assert_public_request_contract(root, authority.run_root, row, request)
    _assert_attempt_evidence(authority.run_root, row, request)
    return (authority.run_root / row["result_path"]).relative_to(root).as_posix()


def test_public_provider_bundle_path_matches_committed_workspace_path(tmp_path, monkeypatch):
    files, inputs = _provider_files(tmp_path)
    compile_public(files)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(tmp_path)
    pause = pause_public(files, monkeypatch, inputs)
    authority, before = checked_run(tmp_path)
    assert before.terminal is None
    (commit,) = before.active_commits.values()
    assert commit == pause
    expected_path = _assert_provider_commit(tmp_path, authority, commit)
    prefix = authority.memo_path.read_bytes()
    request_bytes = (tmp_path / "requests.jsonl").read_bytes()
    resumed = _resume_cli(tmp_path, authority.run_root.name)
    (tmp_path / "resume.stdout").write_text(resumed.stdout)
    (tmp_path / "resume.stderr").write_text(resumed.stderr)
    assert resumed.returncode == 0, resumed.stderr
    _, completed = checked_run(tmp_path)
    assert completed.terminal.data["value"] == {"bundle": expected_path}
    assert completed.terminal.data["value"]["bundle"] == _requests(tmp_path)[0]["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert (tmp_path / "requests.jsonl").read_bytes() == request_bytes
    _assert_cli_resumes_unchanged(tmp_path, authority.run_root.name,
                                _orchestrate_snapshot(tmp_path), request_bytes)


def test_public_provider_bundle_path_fresh_execution(tmp_path, monkeypatch):
    files, inputs = _provider_files(tmp_path)
    compile_public(files)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(tmp_path)
    assert public_run(files, inputs).exit_code == 0
    authority, snapshot = checked_run(tmp_path)
    (commit,) = snapshot.active_commits.values()
    expected_path = _assert_provider_commit(tmp_path, authority, commit)
    assert snapshot.terminal.data["value"] == {"bundle": expected_path}
    assert snapshot.terminal.data["value"]["bundle"] == _requests(tmp_path)[0]["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
    request_bytes = (tmp_path / "requests.jsonl").read_bytes()
    _assert_cli_resumes_unchanged(tmp_path, authority.run_root.name,
                                _orchestrate_snapshot(tmp_path), request_bytes)


@pytest.mark.parametrize("nested", (False, True))
def test_public_runtime_captures_keep_nested_reference_values(tmp_path, monkeypatch, nested):
    call = (
        "(invoke-three (bind-proc (proc-ref helper) :fixed x) "
        "(bind-proc (proc-ref helper) :fixed x) "
        "(bind-proc (proc-ref apply-one) :callback "
        "(bind-proc (proc-ref helper) :fixed x)) x)"
        if nested else "(invoke (bind-proc (proc-ref helper) :fixed x) x)"
    )
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule cp/captures) (export run)
      (defproc helper ((fixed Int) (x Int)) -> Int :effects () :lowering inline (+ fixed x))
      (defproc apply-one ((callback ProcRef[Int -> Int]) (x Int)) -> Int
        :effects () :lowering inline (callback x))
      (defproc invoke ((runner ProcRef[Int -> Int]) (x Int)) -> Int
        :effects () :lowering inline (runner x))
      (defproc invoke-three ((a ProcRef[Int -> Int]) (b ProcRef[Int -> Int])
                             (runner ProcRef[Int -> Int]) (x Int)) -> Int
        :effects () :lowering inline (runner x))
      (defworkflow run ((x Int)) -> Int {call}))'''
    files, inputs = pure_files(tmp_path, source, {"x": 4})
    _, result = assert_pure_public(files, inputs, 8, monkeypatch)
    assert result.descriptor == {"kind": "primitive", "name": "Int"}


@pytest.mark.parametrize("choice", (False, True))
def test_public_sibling_local_captures_survive_source_free_readback(tmp_path, monkeypatch, choice):
    source_path = (Path(__file__).parent / "fixtures" /
                   "workflow_lisp" / "closed_program" / "local_proc_specializations.orc")
    source = source_path.read_text().replace('"TARGET"', '"2.35"')
    files, inputs = pure_files(tmp_path, source, {"choice": choice, "input": 4})
    _, result = assert_pure_public(files, inputs, 11, monkeypatch)
    assert result.descriptor == {"kind": "primitive", "name": "Int"}


def test_public_bound_proc_captures_once_before_sibling_shadow(tmp_path, monkeypatch):
    files, inputs = pure_files(tmp_path, _BIND_PROC_CAPTURE_SOURCE.replace("TARGET", "2.35"), {})
    script = tmp_path / "add.py"
    script.write_text('''import json, os, sys
from pathlib import Path
values = [int(value) for value in sys.argv[1:]]
with open("add.log", "a") as log:
    log.write(json.dumps(values) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(sum(values)))
''')
    files["commands"].write_text(json.dumps({"add": {"kind": "external_tool",
        "stable_command": ["python", "add.py"], "closure": ["add.py"]}}))
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    pause = pause_public(files, monkeypatch, inputs)
    authority, snapshot = checked_run(tmp_path)
    assert list(snapshot.active_commits.values()) == [pause]
    assert pause.data["value"] == 7
    assert (tmp_path / "add.log").read_bytes() == b"[2, 5]\n"
    resumed = _resume_cli(tmp_path, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _, snapshot = checked_run(tmp_path)
    assert snapshot.terminal.data["value"] == 7
    before = _orchestrate_snapshot(tmp_path)
    for _ in range(2):
        resumed = _resume_cli(tmp_path, authority.run_root.name)
        assert resumed.returncode == 0, resumed.stderr
        assert _orchestrate_snapshot(tmp_path) == before
        assert (tmp_path / "add.log").read_bytes() == b"[2, 5]\n"


@pytest.mark.parametrize("explicit", (False, True))
def test_public_run_and_phase_context_match_existing_route(tmp_path, monkeypatch, explicit):
    entry = (
        "(defworkflow entry ((phase-ctx PhaseCtx) (payload Int)) -> Observed "
        "(call leaf :phase-ctx phase-ctx :payload payload))"
        if explicit else
        "(defworkflow entry ((payload Int)) -> Observed (call leaf :payload payload))"
    )
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule context_probe)
      (import std/context :only (RunCtx PhaseCtx))
      (import std/phase :only (with-phase)) (export entry)
      (defrecord Observed (run-id RunId) (run-state Path.state-root)
        (run-artifacts Path.artifact-root) (phase Symbol)
        (state Path.state-root) (artifacts Path.artifact-root) (payload Int))
      {entry}
      (defworkflow leaf ((phase-ctx PhaseCtx) (payload Int)) -> Observed
        (with-phase phase-ctx plan-gate-wrapper
          (record Observed :run-id phase-ctx.run.run-id
            :run-state phase-ctx.run.state-root :run-artifacts phase-ctx.run.artifact-root
            :phase phase-ctx.phase-name :state phase-ctx.state-root
            :artifacts phase-ctx.artifact-root :payload payload))))'''
    inputs = {"payload": 5}
    context = {"run": {"run-id": "explicit-run", "state-root": "state/explicit-run",
                        "artifact-root": "artifacts/explicit-run"},
               "phase-name": "caller-phase", "state-root": "state/caller-phase",
               "artifact-root": "artifacts/caller-phase"}
    if explicit:
        inputs["phase-ctx"] = context
    files, input_file = pure_files(tmp_path, source, inputs)
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    run = _run_cli(tmp_path, str(files["source"]), "--source-root", str(tmp_path),
                   "--entry-workflow", "entry", "--input-file", str(input_file),
                   "--command-boundaries-file", str(files["commands"]))
    (tmp_path / "run.stdout").write_text(run.stdout)
    (tmp_path / "run.stderr").write_text(run.stderr)
    assert run.returncode == 0, run.stderr
    authority, snapshot = checked_run(tmp_path)
    run_id = authority.run_root.name
    expected = ({"run-id": "explicit-run", "run-state": "state/explicit-run",
                 "run-artifacts": "artifacts/explicit-run", "phase": "caller-phase",
                 "state": "state/caller-phase", "artifacts": "artifacts/caller-phase", "payload": 5}
                if explicit else
                {"run-id": run_id, "run-state": "state/run", "run-artifacts": "artifacts/run",
                 "phase": "plan-gate-wrapper", "state": "state/plan-gate-wrapper",
                 "artifacts": "artifacts/plan-gate-wrapper", "payload": 5})
    assert snapshot.terminal.data["value"] == expected
    before = _orchestrate_snapshot(tmp_path)
    for _ in range(2):
        resumed = _resume_cli(tmp_path, run_id)
        assert resumed.returncode == 0, resumed.stderr
        assert _orchestrate_snapshot(tmp_path) == before
    assert _legacy_context_output(tmp_path / "legacy", entry, inputs, run_id=run_id) == expected


def test_public_generic_private_calls_keep_distinct_native_types(tmp_path, monkeypatch):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule local_generic) (export run)
      (defrecord Payload (count Int) (flag Bool))
      (defrecord Result (number Int) (payload Payload))
      (defproc identity :forall (T) ((value T)) -> T
        :effects () :lowering private-workflow value)
      (defworkflow run ((number Int) (payload Payload)) -> Result
        (let* ((kept-number (identity number)) (kept-payload (identity payload)))
          (record Result :number kept-number :payload kept-payload))))'''
    expected = {"number": 6, "payload": {"count": 4, "flag": True}}
    files, inputs = pure_files(tmp_path, source, expected)
    program, result = assert_pure_public(files, inputs, expected, monkeypatch)
    identities = [definition for definition in program.tree["definitions"].values()
                  if definition["key"][:3] == ["local_generic", "procedure", "identity"]]
    assert len(identities) == 2
    assert {row["key"][8]["params"][0]["name"] for row in identities} == {"Int", "local_generic::Payload"}
    assert result.descriptor["name"] == "local_generic::Result"


@pytest.mark.parametrize("explicit", (False, True))
def test_public_item_carried_run_and_explicit_phase_keep_all_fields(tmp_path, explicit):
    override = (''' :phase-ctx (record PhaseCtx :run item-ctx.run :phase-name payload.phase
                  :state-root item-ctx.state-root :artifact-root item-ctx.artifact-root)'''
                if explicit else "")
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule context_probe) (import std/context :only (RunCtx PhaseCtx ItemCtx))
      (import std/phase :only (with-phase)) (export entry)
      (defrecord Observed (run-id RunId) (run-state Path.state-root)
        (run-artifacts Path.artifact-root) (phase Symbol) (state Path.state-root)
        (artifacts Path.artifact-root) (payload Int))
      (defrecord Payload (n Int) (phase Symbol))
      (defworkflow entry ((run_id RunId) (run_state Path.state-root)
          (run_artifacts Path.artifact-root) (item_state Path.state-root)
          (item_artifacts Path.artifact-root) (ledger Path.state-root) (phase_name Symbol)
          (item_id String) (payload_n Int)) -> Observed
        (call parent :item-ctx (record ItemCtx
          :run (record RunCtx :run-id run_id :state-root run_state :artifact-root run_artifacts)
          :item-id item_id :state-root item_state :artifact-root item_artifacts :ledger ledger)
          :payload (record Payload :n payload_n :phase phase_name)))
      (defworkflow parent ((item-ctx ItemCtx) (payload Payload)) -> Observed
        (call child :payload payload{override}))
      (defworkflow child ((phase-ctx PhaseCtx) (payload Payload)) -> Observed
        (with-phase phase-ctx child-phase
          (record Observed :run-id phase-ctx.run.run-id
            :run-state phase-ctx.run.state-root :run-artifacts phase-ctx.run.artifact-root
            :phase phase-ctx.phase-name :state phase-ctx.state-root
            :artifacts phase-ctx.artifact-root :payload payload.n))))'''
    values = {"run_id": "carried-run", "run_state": "state/carried", "run_artifacts": "artifacts/carried",
              "item_state": "state/items/one", "item_artifacts": "artifacts/items/one",
              "ledger": "state/items/one/ledger.json", "phase_name": "chosen-phase", "item_id": "one", "payload_n": 7}
    files, inputs = pure_files(tmp_path, source, values)
    authority, snapshot = public_entry_cli(files, inputs)
    expected = {"run-id": "carried-run", "run-state": "state/carried", "run-artifacts": "artifacts/carried",
                "phase": "chosen-phase" if explicit else "child-phase",
                "state": "state/items/one" if explicit else "state/child-phase",
                "artifacts": "artifacts/items/one" if explicit else "artifacts/child-phase", "payload": 7}
    assert snapshot.terminal.data["value"] == expected
    assert authority.header["run_id"] != expected["run-id"]
    assert legacy_carried_context(tmp_path / "legacy", source, values, authority.header["run_id"]) == expected


def test_public_imports_select_producer_assets_policies_and_argv(tmp_path, monkeypatch):
    files, inputs = prepare_public_producers(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_RESULTS", json.dumps(["11", "13"]))
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    pause = pause_context(files, monkeypatch, inputs)
    authority, prefix = checked_run(tmp_path)
    assert list(prefix.active_commits.values()) == [pause]
    assert pause.data["value"] == 6
    resumed = _resume_cli(tmp_path, authority.header["run_id"])
    assert resumed.returncode == 0, resumed.stderr
    _, snapshot = checked_run(tmp_path)
    assert snapshot.terminal.data["value"] == {"left": 17, "right": 22}
    assert (tmp_path / "commands.log").read_bytes() == b'["left", 5]\n["right", 7]\n'
    assert_public_producer_commits(tmp_path, authority, snapshot)
    assert_public_producer_requests(tmp_path, authority, snapshot)
    log = (tmp_path / "commands.log").read_bytes()
    _assert_cli_resumes_unchanged(tmp_path, authority.header["run_id"], _orchestrate_snapshot(tmp_path),
                                (tmp_path / "requests.jsonl").read_bytes(), count=2)
    assert (tmp_path / "commands.log").read_bytes() == log


def test_independent_library_import_maps_execute_and_replay_real_producers(tmp_path, monkeypatch):
    from hashlib import sha256
    from orchestrator.workflow.evaluated.authority import publish_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo

    source, program, io = prepare_library_producers(tmp_path)
    assert_library_configuration(program)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_RESULTS", json.dumps(["11", "13"]))
    # Truthful publication plumbing only: these independent in-memory maps
    # cannot be reconstructed by a CLI recipe with the current manifest API.
    recipe = {"source_roots": ["."], "entry_workflow": "run", "provider_externs_path": None,
              "prompt_externs_path": None, "command_boundaries_path": None,
              "imported_workflow_bundles_path": None, "input_file": None, "input_overrides": {}}
    run_root = tmp_path / ".orchestrate" / "runs" / "library-config"
    with publish_run_authority(run_root, program, run_id=run_root.name, workflow_file="main.orc",
            workflow_checksum="sha256:" + sha256(source.read_bytes()).hexdigest(), bound_inputs={},
            resume_request=recipe) as authority:
        commits = pause_library_fourth(tmp_path, authority, io, monkeypatch)
        snapshot = read_memo(authority.memo_path, site_classes(program))
        assert list(snapshot.active_commits.values()) == commits
        assert snapshot.terminal is None
        assert_public_producer_commits(tmp_path, authority, snapshot)
        assert_library_command_inventory(tmp_path, snapshot)
        assert_library_requests(tmp_path, authority, snapshot)
        assert_library_replays(tmp_path, authority, io, authority.memo_path.read_bytes())


def _paused_phase_provider_value(root, files, input_file, monkeypatch):
    compile_public(files)
    pause = pause_context(files, monkeypatch, input_file)
    authority, paused = checked_run(root)
    assert list(paused.active_commits.values()) == [pause] and paused.terminal is None
    assert len(_requests(root)) == 1
    resumed = _resume_cli(root, authority.header["run_id"])
    assert resumed.returncode == 0, resumed.stderr
    authority, snapshot = checked_run(root)
    assert list(snapshot.active_commits.values()) == [pause]
    _assert_attempt_evidence(authority.run_root, pause.data, _requests(root)[0])
    assert_completed_resumes(root, authority.header["run_id"])
    return snapshot.terminal.data["value"]


def _source_free_result(root, authority):
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow_lisp.closed.program import ClosedProgram

    for source in root.rglob("*.orc"):
        source.unlink()
    program = ClosedProgram.from_artifact(authority.program_path.read_text())
    return evaluate_closed_program(program, authority.header["bound_inputs"], run_id=authority.header["run_id"])


def test_public_named_phase_targets_match_real_legacy_provider(tmp_path, monkeypatch):
    from tests.test_workflow_evaluated_phase_context import _FIXED_PHASE_TARGET_SOURCE

    source = _FIXED_PHASE_TARGET_SOURCE.replace("(defmodule phase_targets_swapped)", "(defmodule main)")
    source = source.replace("(import std/phase :only (with-phase))", "(import std/phase :only (with-phase)) (export run)")
    source = source.replace("defworkflow run-implementation-attempt", "defworkflow run")
    source = source.replace(":returns ImplementationAttempt)", ':model "chosen-model" :effort "low" :returns ImplementationAttempt)')
    context = {"implementation_state_bundle_path": "artifacts/work/state.json",
        "execution_report_target": "artifacts/work/runtime-execution-report.md",
        "progress_report_target": "artifacts/work/runtime-progress-report.md"}
    inputs = {"phase-ctx": context, "inputs": {"design": "docs/design/design.md", "plan": "docs/plans/plan.md"}}
    payload = {"variant": "COMPLETED", "implementation_state": "COMPLETED",
               "execution_report_path": context["execution_report_target"]}
    monkeypatch.setenv("PROVIDER_SHIM_RESULT", json.dumps(payload))
    outputs = []
    for target in ("2.34", "2.35"):
        root = tmp_path / target
        files, input_file = prepare_phase_provider(root, source.replace("TARGET", target), inputs)
        monkeypatch.setenv("PATH", str(root / "bin") + os.pathsep + os.environ["PATH"])
        monkeypatch.chdir(root)
        if target == "2.34":
            outputs.append(legacy_phase_provider(files, inputs))
        else:
            outputs.append(_paused_phase_provider_value(root, files, input_file, monkeypatch))
        (request,) = _requests(root)
        assert json.loads(request["prompt"].split("\n\n")[0]) == {"phase": "implementation"}
        assert request["prompt"].index(context["progress_report_target"]) < request["prompt"].index(context["execution_report_target"])
    assert outputs == [{"implementation_state": "COMPLETED", "implementation_state_bundle_path": context["implementation_state_bundle_path"]}] * 2


@pytest.mark.parametrize("phase", ("work", "implementation"))
def test_public_hidden_generic_phase_target_preserves_refinement(tmp_path, monkeypatch, phase):
    from tests.test_workflow_lisp_closed_program_elaboration import _GENERIC_PHASE_TARGET_SOURCE

    source = _GENERIC_PHASE_TARGET_SOURCE.replace("TARGET", "2.35").replace("with-phase ctx implementation", "with-phase ctx " + phase)
    files, inputs = pure_files(tmp_path, source, {})
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    run = public_context_run(files, inputs)
    authority, snapshot = checked_run(tmp_path)
    assert not snapshot.latest_starts
    assert not _requests(tmp_path)
    if phase == "work":
        assert run.exit_code == 0
        assert snapshot.terminal.data["value"] == "artifacts/work/work/execution-report.md"
        assert_completed_resumes(tmp_path, run.run_id)
        result = _source_free_result(tmp_path, authority)
        assert (result.json_value(), result.descriptor["under"]) == (snapshot.terminal.data["value"], "artifacts/work")
    else:
        assert run.exit_code == 1
        assert snapshot.terminal.data["outcome"] == "failed"
        assert "path_join_under_escape" in json.dumps(snapshot.terminal.data)
