"""End-to-end acceptance for target-2.25 ``trial`` execution."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier, Lock

import pytest

from orchestrator.providers.executor import ProviderExecutionResult
from orchestrator.runtime_observability import (
    record_compiled_frontend_provenance,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.pure_result_replay import (
    DERIVED_PURE_REPLAY_PROFILE,
    PureReplayVisitWitness,
    classify_pure_replay_progress,
)
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.run_ref.runtime import RunRefRuntimeDependencies
from orchestrator.workflow.trial.ledger import load_trial_event_ledger
from orchestrator.workflow.trial.packets import TRIAL_EVALUATION_PACKET_SCHEMA
from orchestrator.workflow.trial.runtime import TrialRuntimeDependencies
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.compiler import LoweringRoute
from orchestrator.workflow_lisp.wcc.route import (
    workflow_lisp_context_with_lowering_schema,
)
from tests.test_workflow_trial_adjudication import _Executor, _dependencies
from tests.workflow_bundle_helpers import bundle_context_dict


_CHECK_CODE = (
    "from pathlib import Path; "
    "assert Path('assets/task.txt').read_text().strip() == 'fixed trial task'"
)


class _InjectedCrash(RuntimeError):
    pass


_FIXED_TASK = "fixed trial task"
_FIXED_STUDY_RESULT = "fixed trial result"


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", repository.as_posix(), *args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _commit_candidate(repository: Path) -> str:
    repository.mkdir()
    _git(repository, "init", "--quiet")
    (repository / "candidate.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule candidate)
  (export direct orc)
  (defworkflow direct () -> String "alpha-output")
  (defworkflow orc () -> String "beta-output"))
""",
        encoding="utf-8",
    )
    assets = repository / "assets"
    assets.mkdir()
    (assets / "task.txt").write_text("fixed trial task\n", encoding="utf-8")
    _git(repository, "add", "candidate.orc", "assets/task.txt")
    _git(
        repository,
        "-c",
        "user.name=Trial E2E",
        "-c",
        "user.email=trial-e2e@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "candidate",
    )
    return _git(repository, "rev-parse", "HEAD")


def _commit_mode1_coordinator_candidate(repository: Path) -> str:
    repository.mkdir()
    _git(repository, "init", "--quiet")
    script_path = repository / "scripts" / "typed_coordinator.py"
    script_path.parent.mkdir()
    script_path.write_text(
        """\
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from orchestrator.providers import ProviderExecutor, ProviderParams, ProviderRegistry
from orchestrator.workflow.prompting import PromptComposer


task = Path("assets/task.txt").read_text(encoding="utf-8").strip()
if len(sys.argv) != 2 or sys.argv[1] != task or task != "fixed trial task":
    raise SystemExit("unexpected task")


def provider_phase(value: str, ordinal: int) -> str:
    result_path = f".orchestrate/fixed-study/coordinator-{ordinal}.json"
    contract = {
        "path": result_path,
        "fields": [
            {"name": "__result__", "json_pointer": "", "type": "string"}
        ],
    }
    prompt = PromptComposer(
        workspace=Path.cwd(),
        asset_resolver=None,
    ).apply_output_contract_prompt_suffix({"output_bundle": contract}, value)
    executor = ProviderExecutor(
        Path.cwd(),
        ProviderRegistry(),
        provider_observation_enabled=False,
    )
    invocation, error = executor.prepare_invocation(
        "gemini",
        ProviderParams(),
        {},
        prompt_content=prompt,
        env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": result_path},
    )
    if error is not None or invocation is None:
        raise SystemExit(f"provider preparation failed: {error}")
    execution = executor.execute(invocation, cwd=Path.cwd())
    if not execution.is_promotable:
        raise SystemExit("provider execution failed")
    value = json.loads(Path(result_path).read_text(encoding="utf-8"))
    if type(value) is not str:
        raise SystemExit("provider result was not a String")
    return value


first = provider_phase(task, 1)
result = provider_phase(first, 2)
output = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result) + "\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    provider_path = repository / "bin" / "gemini"
    provider_path.parent.mkdir()
    provider_path.write_text(
        """\
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


if len(sys.argv) != 3 or sys.argv[1] != "-p":
    raise SystemExit("unexpected provider argv")
log = Path(".orchestrate/fixed-study/provider-calls.jsonl")
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"input_mode": "argv", "prompt_present": True}))
    stream.write("\\n")
output = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
if not output.is_absolute():
    output = Path.cwd() / output
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps("fixed trial result") + "\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    provider_path.chmod(0o755)
    (repository / "candidate.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule candidate)
  (export direct orc)
  (defprompt action-prompt
    (:fills (task :text))
    -> String
    "{task}")
  (defworkflow direct ((task String)) -> String
    (provider-result providers.study
      :prompt (action-prompt :task task)
      :delivery :composed))
  (defworkflow phase-one ((task String)) -> String
    (provider-result providers.study
      :prompt (action-prompt :task task)
      :delivery :composed))
  (defworkflow phase-two ((prior String)) -> String
    (provider-result providers.study
      :prompt (action-prompt :task prior)
      :delivery :composed))
  (defworkflow orc ((task String)) -> String
    (let* ((first (call phase-one :task task))
           (result (call phase-two :prior first)))
      result)))
""",
        encoding="utf-8",
    )
    assets = repository / "assets"
    assets.mkdir()
    (assets / "task.txt").write_text("fixed trial task\n", encoding="utf-8")
    _git(
        repository,
        "add",
        "candidate.orc",
        "bin/gemini",
        "scripts/typed_coordinator.py",
        "assets/task.txt",
    )
    _git(
        repository,
        "-c",
        "user.name=Trial E2E",
        "-c",
        "user.email=trial-e2e@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "typed coordinator candidate",
    )
    return _git(repository, "rev-parse", "HEAD")


def test_mode1_bundle_command_wrapper_executes_typed_python_in_child_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    commit = _commit_mode1_coordinator_candidate(candidate)
    workspace = (tmp_path / "parent").resolve()
    workspace.mkdir()
    source_path = workspace / "controller.orc"
    source_path.write_text(
        f'''\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule controller)
  (export orchestrate)
  (defworkflow conventional-coordinator ((task String)) -> String
    (command-result typed_coordinator
      :argv ("{sys.executable}" "scripts/typed_coordinator.py" task)
      :returns String))
  (defworkflow orchestrate () -> String
    (let* ((attempt
             (run-ref
               :source (:repo "{candidate.resolve().as_uri()}"
                        :commit "{commit}")
               :program (:bundle conventional-coordinator)
               :inputs (:task "fixed trial task")
               :policy (:setup ()))))
      attempt.value)))
''',
        encoding="utf-8",
    )
    command_boundaries = workspace / "commands.json"
    command_boundaries.write_text(
        json.dumps(
            {
                "typed_coordinator": {
                    "kind": "external_tool",
                    "stable_command": [
                        sys.executable,
                        "scripts/typed_coordinator.py",
                    ],
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (workspace / "providers.json").write_text(
        json.dumps({"providers.study": "gemini"}),
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(workspace, candidate),
            entry_workflow="orchestrate",
            provider_externs_path=workspace / "providers.json",
            command_boundaries_path=command_boundaries,
            workspace_root=workspace,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    manager = StateManager(
        workspace=workspace,
        run_id="mode1-python-coordinator",
    )
    manager.initialize(
        source_path.relative_to(workspace).as_posix(),
        context=bundle_context_dict(built.validated_bundle),
        bound_inputs={},
    )
    run_ref_root = (tmp_path / "external-run-ref-root").resolve()
    manager.bind_run_ref_root(run_ref_root)
    monkeypatch.setenv("PATH", "./bin" + os.pathsep + os.environ["PATH"])

    state = WorkflowExecutor(
        built.validated_bundle,
        workspace,
        manager,
        max_retries=0,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert state["status"] == "completed", state
    assert state["workflow_outputs"] == {"__result__": _FIXED_STUDY_RESULT}
    [child_request] = tuple(run_ref_root.rglob("child-request.json"))
    request = json.loads(child_request.read_text(encoding="utf-8"))
    assert request["target_workflow_name"] == "controller::conventional-coordinator"
    [provider_log] = tuple(
        run_ref_root.rglob("workspace/.orchestrate/fixed-study/provider-calls.jsonl")
    )
    assert len(provider_log.read_text(encoding="utf-8").splitlines()) == 2


def _write_fixed_study_parent(
    workspace: Path,
    *,
    repository: Path,
    commit: str,
    max_concurrency: int,
) -> Path:
    source_path = workspace / "controller.orc"
    source_path.write_text(
        f'''\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule controller)
  (import candidate :as candidate :only (direct orc))
  (export compare)
  (defworkflow direct-treatment ((task String)) -> String
    (call candidate.direct :task task))
  (defworkflow conventional-coordinator ((task String)) -> String
    (command-result typed_coordinator
      :argv ("{sys.executable}" "scripts/typed_coordinator.py" task)
      :returns String))
  (defworkflow orc-treatment ((task String)) -> String
    (call candidate.orc :task task))
  (defworkflow compare ((task String)) -> String
    (let* ((trial-result
             (trial
      :arms ((:id "DIRECT"
              :run-ref
              (run-ref
                :source (:repo "{repository.resolve().as_uri()}"
                         :commit "{commit}")
                :program (:bundle direct-treatment)
                :inputs (:task task)
                :policy (:setup ())))
             (:id "COORDINATOR"
              :run-ref
              (run-ref
                :source (:repo "{repository.resolve().as_uri()}"
                         :commit "{commit}")
                :program (:bundle conventional-coordinator)
                :inputs (:task task)
                :policy (:setup ())))
             (:id "ORC"
              :run-ref
              (run-ref
                :source (:repo "{repository.resolve().as_uri()}"
                         :commit "{commit}")
                :program (:bundle orc-treatment)
                :inputs (:task task)
                :policy (:setup ()))))
      :reps 1
      :max-concurrency {max_concurrency}
      :evaluation
      (record
        :checks (list
          (record :id "committed-asset"
                  :command (list "{sys.executable}" "-c" "{_CHECK_CODE}")
                  :authority "correctness"
                  :required true
                  :timeout-ms 5000))
        :judgment
        (record :provider "scorer"
                :rubric-asset "rubrics/trial.md"
                :evidence-confidentiality "same_trust_boundary"
                :evidence-limits
                (record :max-item-bytes 65536 :max-packet-bytes 262144))
        :observation
        (record :include
                (list "task_spec" "validated_result" "workspace_delta"
                      "check_results" "failure_evidence")
                :diff-cap-bytes 65536
                :reveal-provider-identity false)
        :aggregation
        (record :mode "independent_rubric"
                :rep-combine "median"
                :tie "authored_order")
        :success-rule
        (record :superior
                (record :min-abs-improvement 0.10 :max-cost-ratio 1.5)
                :non-inferior
                (record :min-cost-reduction 0.20)
                :count-failures-as-outcomes true))
      :budget
      (record :arm-timeout-ms 900000
              :trial-timeout-ms 3600000
              :max-evaluator-attempts 3
              :max-evaluator-concurrency 3))))
      "done")))
''',
        encoding="utf-8",
    )
    (workspace / "providers.json").write_text(
        json.dumps(
            {
                "providers.study": "gemini",
                "scorer": "test-provider",
            }
        ),
        encoding="utf-8",
    )
    (workspace / "prompts.json").write_text(
        json.dumps({"trial-rubric": "rubrics/trial.md"}),
        encoding="utf-8",
    )
    (workspace / "commands.json").write_text(
        json.dumps(
            {
                "typed_coordinator": {
                    "kind": "external_tool",
                    "stable_command": [
                        sys.executable,
                        "scripts/typed_coordinator.py",
                    ],
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rubric_path = workspace / "rubrics" / "trial.md"
    rubric_path.parent.mkdir()
    rubric_path.write_text("Score the supplied evidence.\n", encoding="utf-8")
    return source_path


def _build_fixed_study_fixture(
    tmp_path: Path,
    *,
    run_id: str,
) -> dict[str, object]:
    candidate = tmp_path / "candidate"
    commit = _commit_mode1_coordinator_candidate(candidate)
    workspace = (tmp_path / "parent").resolve()
    workspace.mkdir()
    source_path = _write_fixed_study_parent(
        workspace,
        repository=candidate,
        commit=commit,
        max_concurrency=3,
    )
    built = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(workspace, candidate),
            entry_workflow="compare",
            provider_externs_path=workspace / "providers.json",
            prompt_externs_path=workspace / "prompts.json",
            command_boundaries_path=workspace / "commands.json",
            workspace_root=workspace,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    bundle = built.validated_bundle
    run_ref_root = (tmp_path / "external-run-ref-root").resolve()
    run_ref_root.mkdir()
    manager = StateManager(
        workspace=workspace,
        run_id=run_id,
        state_dir=(workspace / "state").resolve(),
    )
    context = workflow_lisp_context_with_lowering_schema(
        bundle_context_dict(bundle),
        built.manifest.lowering_schema_version,
    )
    run_state = manager.initialize(
        source_path.relative_to(workspace).as_posix(),
        context=context,
        bound_inputs={"task": _FIXED_TASK},
        result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
    )
    manager.bind_run_ref_root(run_ref_root)
    with manager.state_transaction() as transaction_state:
        record_compiled_frontend_provenance(
            transaction_state,
            bundle.provenance,
        )
    return {
        "commit": commit,
        "workspace": workspace,
        "source_path": source_path,
        "bundle": bundle,
        "run_ref_root": run_ref_root,
        "manager": manager,
        "run_state": run_state,
        "run_id": run_id,
    }


def _decode_trailing_trial_packet(prompt: str) -> tuple[dict[str, object], bytes]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[dict[str, object], bytes]] = []
    for offset, character in enumerate(prompt):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(prompt, offset)
        except json.JSONDecodeError:
            continue
        if (
            prompt[end:].strip()
            or not isinstance(value, dict)
            or value.get("schema") != TRIAL_EVALUATION_PACKET_SCHEMA
        ):
            continue
        candidates.append((value, prompt[offset:end].encode("utf-8")))
    assert len(candidates) == 1
    packet, packet_bytes = candidates[0]
    assert canonical_json_bytes(packet) == packet_bytes
    return packet, packet_bytes


class _PacketCapturingExecutor:
    def __init__(self) -> None:
        self.prepared: list[dict[str, object]] = []
        self.packet_bytes: list[bytes] = []
        self.executed: list[tuple[str, str]] = []

    def prepare_invocation(self, provider, params, context, **kwargs):
        assert provider == "scorer"
        assert context == {}
        packet, packet_bytes = _decode_trailing_trial_packet(
            kwargs["prompt_content"]
        )
        citable = packet["citable_item_ids"]
        assert isinstance(citable, list)
        citation = (
            "failure_evidence"
            if "failure_evidence" in citable
            else "validated_result"
        )
        assert citation in citable
        self.prepared.append(packet)
        self.packet_bytes.append(packet_bytes)
        return (packet["evaluation_id"], citation), None

    def execute(self, invocation, *, cwd):
        label, citation = invocation
        self.executed.append((label, citation))
        return ProviderExecutionResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "candidate_id": label,
                    "score": 0.5,
                    "summary": "the frozen evidence satisfies the rubric",
                    "citations": [citation],
                }
            ).encode("utf-8"),
            stderr=b"",
            duration_ms=3,
        )


def _write_parent(
    workspace: Path,
    *,
    repository: Path,
    commit: str,
    max_concurrency: int,
) -> Path:
    source_path = workspace / "controller.orc"
    source_path.write_text(
        f'''\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule controller)
  (export compare)
  (defworkflow build-prelude ((seed String)) -> String
    (string/concat seed "-ready"))
  (defworkflow compare ((seed String)) -> String
    (let* ((prelude (call build-prelude :seed seed))
           (trial-result
             (trial
      :arms ((:id "direct"
              :run-ref
              (run-ref
                :source (:repo "{repository.resolve().as_uri()}"
                         :commit "{commit}")
                :program (:path "candidate.orc" :entry direct)
                :inputs ()
                :returns String
                :policy (:environment :deterministic-effect-free :setup ())))
             (:id "orc"
              :run-ref
              (run-ref
                :source (:repo "{repository.resolve().as_uri()}"
                         :commit "{commit}")
                :program (:path "candidate.orc" :entry orc)
                :inputs ()
                :returns String
                :policy (:environment :deterministic-effect-free :setup ()))))
      :reps 1
      :max-concurrency {max_concurrency}
      :evaluation
      (record
        :checks (list
          (record :id "committed-asset"
                  :command (list "{sys.executable}" "-c" "{_CHECK_CODE}")
                  :authority "correctness"
                  :required true
                  :timeout-ms 5000))
        :judgment
        (record :provider "scorer"
                :rubric-asset "rubrics/trial.md"
                :evidence-confidentiality "same_trust_boundary"
                :evidence-limits
                (record :max-item-bytes 65536 :max-packet-bytes 262144))
        :observation
        (record :include
                (list "validated_result" "workspace_delta" "check_results")
                :diff-cap-bytes 65536
                :reveal-provider-identity false)
        :aggregation
        (record :mode "independent_rubric"
                :rep-combine "median"
                :tie "authored_order")
        :success-rule
        (record :superior
                (record :min-abs-improvement 0.10 :max-cost-ratio 1.5)
                :non-inferior
                (record :min-cost-reduction 0.20)
                :count-failures-as-outcomes true))
      :budget
      (record :arm-timeout-ms 900000
              :trial-timeout-ms 3600000
              :max-evaluator-attempts 2
              :max-evaluator-concurrency 2))))
      "done")))
''',
        encoding="utf-8",
    )
    (workspace / "providers.json").write_text(
        json.dumps({"scorer": "test-provider"}),
        encoding="utf-8",
    )
    (workspace / "prompts.json").write_text(
        json.dumps({"trial-rubric": "rubrics/trial.md"}),
        encoding="utf-8",
    )
    rubric_path = workspace / "rubrics" / "trial.md"
    rubric_path.parent.mkdir()
    rubric_path.write_text("Score the supplied evidence.\n", encoding="utf-8")
    return source_path


def _build_trial_fixture(
    tmp_path: Path,
    *,
    max_concurrency: int,
    run_id: str,
) -> dict[str, object]:
    candidate = tmp_path / "candidate"
    commit = _commit_candidate(candidate)
    workspace = (tmp_path / "parent").resolve()
    workspace.mkdir()
    source_path = _write_parent(
        workspace,
        repository=candidate,
        commit=commit,
        max_concurrency=max_concurrency,
    )
    built = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(workspace,),
            entry_workflow="compare",
            provider_externs_path=workspace / "providers.json",
            prompt_externs_path=workspace / "prompts.json",
            workspace_root=workspace,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    bundle = built.validated_bundle
    run_ref_root = (tmp_path / "external-run-ref-root").resolve()
    run_ref_root.mkdir()
    manager = StateManager(
        workspace=workspace,
        run_id=run_id,
        state_dir=(workspace / "state").resolve(),
    )
    context = workflow_lisp_context_with_lowering_schema(
        bundle_context_dict(bundle),
        built.manifest.lowering_schema_version,
    )
    run_state = manager.initialize(
        source_path.relative_to(workspace).as_posix(),
        context=context,
        bound_inputs={"seed": "fixture"},
        result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
    )
    manager.bind_run_ref_root(run_ref_root)
    with manager.state_transaction() as transaction_state:
        record_compiled_frontend_provenance(
            transaction_state,
            bundle.provenance,
        )
    return {
        "commit": commit,
        "workspace": workspace,
        "source_path": source_path,
        "bundle": bundle,
        "run_ref_root": run_ref_root,
        "manager": manager,
        "run_state": run_state,
        "run_id": run_id,
    }


class _RealLaunchHarness:
    def __init__(
        self,
        *,
        barrier: Barrier | None = None,
        fail_arm_id: str | None = None,
    ) -> None:
        self.barrier = barrier
        self.fail_arm_id = fail_arm_id
        self.launches = []
        self.active = 0
        self.max_active = 0
        self._lock = Lock()

    def factory(self, cell, _request):
        base = RunRefRuntimeDependencies()

        def counted_launch(launch):
            with self._lock:
                self.launches.append((cell, launch))
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                if cell.arm_id == self.fail_arm_id:
                    raise RuntimeError("deterministic fixed-study launch failure")
                if self.barrier is not None:
                    self.barrier.wait(timeout=30)
                return base.launch_child(launch)
            finally:
                with self._lock:
                    self.active -= 1

        return replace(base, launch_child=counted_launch)


def _new_executor(
    fixture: dict[str, object],
    *,
    manager: StateManager,
    runtime_dependencies: TrialRuntimeDependencies,
    evaluation_dependencies,
) -> WorkflowExecutor:
    executor = WorkflowExecutor(
        fixture["bundle"],
        fixture["workspace"],
        manager,
        logs_dir=manager.logs_dir,
        max_retries=0,
        retry_delay_ms=0,
        provider_observation_enabled=False,
    )
    executor._trial_runtime_dependencies = runtime_dependencies
    executor._trial_evaluation_dependencies = evaluation_dependencies
    return executor


def _fresh_manager(fixture: dict[str, object]) -> StateManager:
    workspace = fixture["workspace"]
    run_id = fixture["run_id"]
    assert isinstance(workspace, Path)
    assert isinstance(run_id, str)
    manager = StateManager(
        workspace=workspace,
        run_id=run_id,
        state_dir=(workspace / "state").resolve(),
    )
    manager.load()
    return manager


def _ledger_bytes(manager: StateManager) -> dict[str, bytes]:
    paths = tuple(manager.run_root.rglob("trial-events.jsonl")) + tuple(
        manager.run_root.rglob("run-ref-attempts.jsonl")
    )
    return {
        path.relative_to(manager.run_root).as_posix(): path.read_bytes()
        for path in paths
    }


def _e1_ledger_paths_by_cell(
    trial_ledger_path: Path,
) -> dict[tuple[str, int], Path]:
    paths: dict[tuple[str, int], Path] = {}
    for row in load_trial_event_ledger(trial_ledger_path).rows:
        if row.kind != "cell_allocated":
            continue
        payload = row.payload
        cell = payload["cell"]
        key = (cell["arm_id"], cell["rep"])
        path = Path(payload["e1_ledger_path"])
        prior = paths.get(key)
        assert prior is None or prior == path
        paths[key] = path
    return paths


def _completed_trial_payload(state: dict[str, object]) -> dict[str, object]:
    [trial_step] = [
        step
        for step in state["steps"].values()
        if isinstance(step, dict) and isinstance(step.get("trial"), dict)
    ]
    assert trial_step["status"] == "completed"
    return trial_step["trial"]


def _assert_captured_packets_match_freeze(
    manager: StateManager,
    scorer: _PacketCapturingExecutor,
) -> None:
    [trial_ledger_path] = tuple(manager.run_root.rglob("trial-events.jsonl"))
    ledger = load_trial_event_ledger(trial_ledger_path)
    [freeze] = [row for row in ledger.rows if row.kind == "packets_frozen"]
    frozen_digests = {
        row["opaque_label"]: row["packet_digest"]
        for row in freeze.payload["cell_packets"]
    }
    assert len(scorer.prepared) == len(frozen_digests)
    for packet, packet_bytes in zip(
        scorer.prepared,
        scorer.packet_bytes,
        strict=True,
    ):
        label = packet["evaluation_id"]
        assert frozen_digests[label] == canonical_sha256(packet)
        assert canonical_json_bytes(packet) == packet_bytes


def _provider_call_count(launch) -> int:
    path = launch.workspace / ".orchestrate/fixed-study/provider-calls.jsonl"
    assert path.is_file()
    return len(path.read_text(encoding="utf-8").splitlines())


def test_fixed_study_executes_three_truthful_mechanisms_with_zero_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixed_study_fixture(
        tmp_path,
        run_id="trial-fixed-study-success",
    )
    manager = fixture["manager"]
    run_state = fixture["run_state"]
    run_ref_root = fixture["run_ref_root"]
    assert isinstance(manager, StateManager)
    assert isinstance(run_ref_root, Path)
    monkeypatch.setenv("PATH", "./bin" + os.pathsep + os.environ["PATH"])

    def fixed_label_salt(size: int) -> bytes:
        assert size == 32
        return b"a" * 32

    monkeypatch.setattr(
        "orchestrator.workflow.executor.os.urandom",
        fixed_label_salt,
    )

    launches = _RealLaunchHarness(barrier=Barrier(3))
    check_calls = []

    def counted_check(argv, **kwargs):
        check_calls.append((tuple(argv), Path(kwargs["cwd"]), kwargs["shell"]))
        assert Path(kwargs["cwd"], "assets/task.txt").read_text(
            encoding="utf-8"
        ).strip() == _FIXED_TASK
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    scorer = _PacketCapturingExecutor()
    evaluation_dependencies, _unused = _dependencies(
        scorer,
        check_runner=counted_check,
    )
    executor = _new_executor(
        fixture,
        manager=manager,
        runtime_dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=launches.factory,
        ),
        evaluation_dependencies=evaluation_dependencies,
    )

    result = executor.execute(
        run_id=run_state.run_id,
        on_error="stop",
        max_retries=0,
        retry_delay_ms=0,
    )

    assert result["status"] == "completed", result
    authored = _completed_trial_payload(result)
    assert [row["arm_id"] for row in authored["outcomes"]] == [
        "DIRECT",
        "COORDINATOR",
        "ORC",
    ]
    assert [row["variant"] for row in authored["outcomes"]] == [
        "Completed",
        "Completed",
        "Completed",
    ]
    assert [row["value"] for row in authored["outcomes"]] == [
        _FIXED_STUDY_RESULT,
        _FIXED_STUDY_RESULT,
        _FIXED_STUDY_RESULT,
    ]
    failure_counts = {
        row["arm_id"]: int(row["variant"] == "Failed")
        for row in authored["outcomes"]
    }
    assert failure_counts == {"DIRECT": 0, "COORDINATOR": 0, "ORC": 0}
    assert authored["verdict"]["ranking"] == ["DIRECT", "COORDINATOR", "ORC"]
    budget_accounting = authored["verdict"]["budget_accounting"]
    assert budget_accounting["child_attempts"] == 3
    assert budget_accounting["evaluator_attempts"] == 3

    assert len(launches.launches) == 3
    assert launches.max_active == 3
    assert {
        cell.arm_id: launch.mode for cell, launch in launches.launches
    } == {"DIRECT": "bundle", "COORDINATOR": "bundle", "ORC": "bundle"}
    assert {
        cell.arm_id: _provider_call_count(launch)
        for cell, launch in launches.launches
    } == {"DIRECT": 1, "COORDINATOR": 2, "ORC": 2}
    assert len(check_calls) == 3
    assert all(
        call[0] == (sys.executable, "-c", _CHECK_CODE)
        and call[2] is False
        for call in check_calls
    )
    assert len(scorer.executed) == 3
    assert all(citation == "validated_result" for _label, citation in scorer.executed)
    _assert_captured_packets_match_freeze(manager, scorer)

    normalized_packets = []
    for packet in scorer.prepared:
        normalized = dict(packet)
        normalized["evaluation_id"] = "normalized-evaluation-id"
        normalized_packets.append(canonical_json_bytes(normalized))
        payload = canonical_json_bytes(packet)
        assert b"DIRECT" not in payload
        assert b"COORDINATOR" not in payload
        assert b"ORC" not in payload
    assert len(set(normalized_packets)) == 1

    [trial_ledger_path] = tuple(manager.run_root.rglob("trial-events.jsonl"))
    trial_ledger = load_trial_event_ledger(trial_ledger_path)
    sealed_bindings = trial_ledger.rows[0].payload[
        "sealed_opaque_label_map"
    ]["bindings"]
    label_to_arm = {
        row["opaque_label"]: row["cell"]["arm_id"]
        for row in sealed_bindings
    }
    evaluator_labels = [packet["evaluation_id"] for packet in scorer.prepared]
    assert set(evaluator_labels) == set(label_to_arm)
    assert all(label.startswith("opaque-") for label in evaluator_labels)
    randomized_opaque_order = sorted(evaluator_labels)
    assert [label_to_arm[label] for label in randomized_opaque_order] == [
        "ORC",
        "DIRECT",
        "COORDINATOR",
    ]

    treatment_domain = ("DIRECT", "COORDINATOR", "ORC")
    blinded_guesses = []
    for packet_bytes in scorer.packet_bytes:
        evaluator_visible = json.loads(packet_bytes)
        evaluator_visible["evaluation_id"] = "normalized-evaluation-id"
        bucket = hashlib.sha256(
            canonical_json_bytes(evaluator_visible)
        ).digest()[0] % len(treatment_domain)
        blinded_guesses.append(treatment_domain[bucket])
    assert len(set(blinded_guesses)) == 1
    correct_labels = sum(
        guess == label_to_arm[label]
        for guess, label in zip(blinded_guesses, evaluator_labels, strict=True)
    )
    assert correct_labels == 1
    assert correct_labels / len(evaluator_labels) <= 1 / 3

    # Treatment identity and authored order re-enter only through the sealed
    # join used by the public result, after each evaluator saw one opaque packet.
    assert [row["arm_id"] for row in authored["outcomes"]] == list(
        treatment_domain
    )
    assert authored["verdict"]["ranking"] == list(treatment_domain)

    child_requests = {
        cell.arm_id: json.loads(
            launch.request_path.read_text(encoding="utf-8")
        )
        for cell, launch in launches.launches
    }
    assert {
        cell.arm_id: _git(launch.workspace, "rev-parse", "HEAD")
        for cell, launch in launches.launches
    } == {
        "DIRECT": fixture["commit"],
        "COORDINATOR": fixture["commit"],
        "ORC": fixture["commit"],
    }
    assert len(
        {
            request["expected_capsule_digest"]
            for request in child_requests.values()
        }
    ) == 1
    coordinator_request = child_requests["COORDINATOR"]
    assert coordinator_request["target_workflow_name"] == (
        "controller::conventional-coordinator"
    )
    assert coordinator_request["inputs"] == {"task": _FIXED_TASK}
    assert child_requests["DIRECT"]["inputs"] == {"task": _FIXED_TASK}
    assert child_requests["ORC"]["inputs"] == {"task": _FIXED_TASK}
    assert child_requests["DIRECT"]["target_workflow_name"] == (
        "controller::direct-treatment"
    )
    assert child_requests["ORC"]["target_workflow_name"] == (
        "controller::orc-treatment"
    )


def test_fixed_study_retains_one_treatment_failure_without_cancelling_siblings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixed_study_fixture(
        tmp_path,
        run_id="trial-fixed-study-failure-control",
    )
    manager = fixture["manager"]
    run_ref_root = fixture["run_ref_root"]
    assert isinstance(manager, StateManager)
    assert isinstance(run_ref_root, Path)
    monkeypatch.setenv("PATH", "./bin" + os.pathsep + os.environ["PATH"])
    launches = _RealLaunchHarness(fail_arm_id="COORDINATOR")
    scorer = _PacketCapturingExecutor()
    evaluation_dependencies, _unused = _dependencies(
        scorer,
        check_runner=subprocess.run,
    )
    executor = _new_executor(
        fixture,
        manager=manager,
        runtime_dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=launches.factory,
        ),
        evaluation_dependencies=evaluation_dependencies,
    )

    result = executor.execute(on_error="stop")

    assert result["status"] == "completed", result
    authored = _completed_trial_payload(result)
    outcomes = {row["arm_id"]: row for row in authored["outcomes"]}
    assert outcomes["DIRECT"]["variant"] == "Completed"
    assert outcomes["DIRECT"]["value"] == _FIXED_STUDY_RESULT
    assert outcomes["ORC"]["variant"] == "Completed"
    assert outcomes["ORC"]["value"] == _FIXED_STUDY_RESULT
    assert outcomes["COORDINATOR"]["variant"] == "Failed"
    assert outcomes["COORDINATOR"]["failure"] == {
        "code": "run_ref_child_launch_failed",
        "phase": "launched",
        "retryable": False,
        "secondary_causes": [],
    }
    failure_table = [
        {
            "arm_id": row["arm_id"],
            "failure_count": int(row["variant"] == "Failed"),
            "failure_code": (
                row["failure"]["code"]
                if row["variant"] == "Failed"
                else None
            ),
        }
        for row in authored["outcomes"]
    ]
    assert failure_table == [
        {"arm_id": "DIRECT", "failure_count": 0, "failure_code": None},
        {
            "arm_id": "COORDINATOR",
            "failure_count": 1,
            "failure_code": "run_ref_child_launch_failed",
        },
        {"arm_id": "ORC", "failure_count": 0, "failure_code": None},
    ]
    assert len(launches.launches) == 3
    assert [cell.arm_id for cell, _launch in launches.launches] == [
        "DIRECT",
        "COORDINATOR",
        "ORC",
    ]
    assert {
        cell.arm_id: _provider_call_count(launch)
        for cell, launch in launches.launches
        if cell.arm_id != "COORDINATOR"
    } == {"DIRECT": 1, "ORC": 2}
    child_states = tuple(run_ref_root.rglob(".orchestrate/runs/*/state.json"))
    assert len(child_states) == 2
    assert all(
        json.loads(path.read_text(encoding="utf-8"))["status"] == "completed"
        for path in child_states
    )
    budget_accounting = authored["verdict"]["budget_accounting"]
    assert budget_accounting["child_attempts"] == 3
    assert budget_accounting["evaluator_attempts"] == 3
    assert len(scorer.executed) == 3
    assert sum(
        citation == "failure_evidence" for _label, citation in scorer.executed
    ) == 1
    _assert_captured_packets_match_freeze(manager, scorer)


def test_real_two_arm_trial_executes_concurrently_and_commits_one_parent(
    tmp_path: Path,
) -> None:
    fixture = _build_trial_fixture(
        tmp_path,
        max_concurrency=2,
        run_id="trial-e2e-parent",
    )
    workspace = fixture["workspace"]
    run_ref_root = fixture["run_ref_root"]
    manager = fixture["manager"]
    run_state = fixture["run_state"]
    assert isinstance(workspace, Path)
    assert isinstance(run_ref_root, Path)
    assert isinstance(manager, StateManager)

    launch_harness = _RealLaunchHarness(barrier=Barrier(2))

    check_calls = []

    def counted_check(argv, **kwargs):
        check_calls.append((tuple(argv), Path(kwargs["cwd"]), kwargs["shell"]))
        return subprocess.run(argv, **kwargs)

    scorer = _Executor()
    evaluation_dependencies, _unused_check_calls = _dependencies(
        scorer,
        check_runner=counted_check,
    )
    executor = _new_executor(
        fixture,
        manager=manager,
        runtime_dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=launch_harness.factory,
        ),
        evaluation_dependencies=evaluation_dependencies,
    )

    result = executor.execute(
        run_id=run_state.run_id,
        on_error="stop",
        max_retries=0,
        retry_delay_ms=0,
    )

    assert result["status"] == "completed", result
    [trial_step] = [
        step
        for step in result["steps"].values()
        if isinstance(step, dict) and isinstance(step.get("trial"), dict)
    ]
    assert trial_step["status"] == "completed"
    authored = trial_step["trial"]
    assert [row["variant"] for row in authored["outcomes"]] == [
        "Completed",
        "Completed",
    ]
    assert [row["arm_id"] for row in authored["outcomes"]] == [
        "direct",
        "orc",
    ]
    assert [row["value"] for row in authored["outcomes"]] == [
        "alpha-output",
        "beta-output",
    ]
    assert authored["verdict"]["ranking"] == ["direct", "orc"]
    assert authored["verdict"]["selected_arm"] is None
    verdict_artifact = workspace / authored["verdict_artifact"]
    assert verdict_artifact.is_file()

    trial_ledgers = tuple(manager.run_root.rglob("trial-events.jsonl"))
    assert len(trial_ledgers) == 1
    trial_ledger = load_trial_event_ledger(trial_ledgers[0])
    assert tuple(
        row for row in trial_ledger.rows if row.kind == "trial_parent_committed"
    ) == (trial_ledger.rows[-1],)
    assert len(launch_harness.launches) == 2
    assert launch_harness.max_active == 2
    assert len(check_calls) == 2
    assert all(
        call[0] == (sys.executable, "-c", _CHECK_CODE)
        for call in check_calls
    )
    assert all(call[2] is False for call in check_calls)
    assert len(scorer.prepared) == 2
    assert len(scorer.executed) == 2

    e1_ledgers = tuple(manager.run_root.rglob("run-ref-attempts.jsonl"))
    assert len(e1_ledgers) == 2
    assert all(load_attempt_ledger(path).rows[-1].stage == "committed" for path in e1_ledgers)
    child_states = tuple(run_ref_root.rglob(".orchestrate/runs/*/state.json"))
    assert len(child_states) == 2
    assert all(
        json.loads(path.read_text(encoding="utf-8"))["status"] == "completed"
        for path in child_states
    )
    child_requests = tuple(run_ref_root.rglob("child-request.json"))
    assert len(child_requests) == 2
    assert all(
        json.loads(path.read_text(encoding="utf-8"))["materialized_source"][
            "resolved_commit_sha"
        ]
        == fixture["commit"]
        for path in child_requests
    )


def test_completed_trial_visit_is_reused_after_downstream_parent_failure(
    tmp_path: Path,
) -> None:
    fixture = _build_trial_fixture(
        tmp_path,
        max_concurrency=2,
        run_id="trial-e2e-reuse",
    )
    manager = fixture["manager"]
    assert isinstance(manager, StateManager)
    launches = _RealLaunchHarness(barrier=Barrier(2))
    check_calls = []

    def counted_check(argv, **kwargs):
        check_calls.append(tuple(argv))
        return subprocess.run(argv, **kwargs)

    scorer = _Executor()
    evaluation_dependencies, _unused = _dependencies(
        scorer,
        check_runner=counted_check,
    )
    executor = _new_executor(
        fixture,
        manager=manager,
        runtime_dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=launches.factory,
        ),
        evaluation_dependencies=evaluation_dependencies,
    )
    first = executor.execute(on_error="stop")
    assert first["status"] == "completed", first
    before = _ledger_bytes(manager)
    trial_step_name, trial_step_before = next(
        (name, step)
        for name, step in first["steps"].items()
        if isinstance(step, dict) and isinstance(step.get("trial"), dict)
    )
    assert len(launches.launches) == 2
    assert len(check_calls) == 2
    assert len(scorer.executed) == 2

    # Resuming a fully completed run intentionally starts a new workflow visit.
    # Model a downstream interruption after the trial visit committed by
    # reopening only the terminal pure projection through the public witness
    # lifecycle. The trial and its E1 authority remain terminal.
    with manager.state_transaction() as state:
        terminal_step_name, terminal_step = next(
            (name, step)
            for name, step in state.steps.items()
            if isinstance(step, dict)
            and str(step.get("step_id", "")).endswith("__terminal_projection")
        )
        terminal_step = state.steps.pop(terminal_step_name)
        terminal_step_id = terminal_step["step_id"]
        terminal_visit = terminal_step["visit_count"]
        assert state.step_visits.pop(terminal_step_name) == terminal_visit
        bundle = fixture["bundle"]
        terminal_index = tuple(bundle.ir.body_region).index(terminal_step_id)
    assert terminal_visit == 1
    assert (
        manager.begin_eligible_pure_visit(
            step_name=terminal_step_name,
            step_index=terminal_index,
            step_id=terminal_step_id,
        )
        == terminal_visit
    )
    terminal_witness = PureReplayVisitWitness(
        presentation_key=terminal_step_name,
        step_index=terminal_index,
        step_id=terminal_step_id,
        visit_count=terminal_visit,
    )
    with manager.state_transaction() as state:
        state.status = "failed"
        state.error = {
            "type": "downstream_fixture_failure",
            "message": "fixture failure after completed trial",
        }
    assert manager.state is not None
    assert (
        classify_pure_replay_progress(
            manager.state,
            witness=terminal_witness,
        )
        == "interrupted"
    )

    def forbidden_run_ref_dependencies(_cell, _request):
        raise AssertionError("completed resume launched a child")

    forbidden_scorer = _Executor(forbidden=True)
    forbidden_evaluation, forbidden_check_calls = _dependencies(
        forbidden_scorer,
    )
    resume_manager = _fresh_manager(fixture)
    resume_executor = _new_executor(
        fixture,
        manager=resume_manager,
        runtime_dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=forbidden_run_ref_dependencies,
        ),
        evaluation_dependencies=forbidden_evaluation,
    )

    resumed = resume_executor.execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed", resumed
    assert resumed["workflow_outputs"] == {"__result__": "done"}
    assert resumed["steps"][trial_step_name] == trial_step_before
    assert forbidden_check_calls == []
    assert forbidden_scorer.prepared == []
    assert forbidden_scorer.executed == []
    assert _ledger_bytes(resume_manager) == before


def test_interrupted_second_cell_resumes_with_one_fresh_e1_attempt(
    tmp_path: Path,
) -> None:
    fixture = _build_trial_fixture(
        tmp_path,
        max_concurrency=1,
        run_id="trial-e2e-recovery",
    )
    manager = fixture["manager"]
    assert isinstance(manager, StateManager)
    launches = _RealLaunchHarness()
    prepared_boundaries = 0

    def crash_second_prepared(boundary: str) -> None:
        nonlocal prepared_boundaries
        if boundary != "after_e1_prepared_before_trial_prepared":
            return
        prepared_boundaries += 1
        if prepared_boundaries == 2:
            raise _InjectedCrash(boundary)

    check_calls = []

    def counted_check(argv, **kwargs):
        check_calls.append(tuple(argv))
        return subprocess.run(argv, **kwargs)

    scorer = _Executor()
    evaluation_dependencies, _unused = _dependencies(
        scorer,
        check_runner=counted_check,
    )
    executor = _new_executor(
        fixture,
        manager=manager,
        runtime_dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=launches.factory,
            crash_hook=crash_second_prepared,
        ),
        evaluation_dependencies=evaluation_dependencies,
    )

    with pytest.raises(
        _InjectedCrash,
        match="after_e1_prepared_before_trial_prepared",
    ):
        executor.execute(on_error="stop")

    assert len(launches.launches) == 2
    assert check_calls == []
    assert scorer.executed == []
    [trial_ledger_path] = tuple(manager.run_root.rglob("trial-events.jsonl"))
    trial_ledger_before = load_trial_event_ledger(trial_ledger_path)
    assert not any(
        row.kind == "trial_parent_committed" for row in trial_ledger_before.rows
    )
    e1_paths = _e1_ledger_paths_by_cell(trial_ledger_path)
    assert set(e1_paths) == {("direct", 1), ("orc", 1)}
    direct_e1_path = e1_paths[("direct", 1)]
    orc_e1_path = e1_paths[("orc", 1)]
    direct_before = load_attempt_ledger(direct_e1_path)
    orc_before = load_attempt_ledger(orc_e1_path)
    assert (direct_before.rows[-1].attempt_ordinal, direct_before.rows[-1].stage) == (
        1,
        "committed",
    )
    assert (
        orc_before.rows[-1].attempt_ordinal,
        orc_before.rows[-1].stage,
        orc_before.rows[-1].status,
    ) == (1, "completed_pending_parent_commit", "pending_parent_commit")
    direct_ledger_bytes = direct_e1_path.read_bytes()
    interrupted_child_id = orc_before.rows[-1].bindings.child_run_id
    interrupted_workspace = orc_before.rows[-1].bindings.workspace_path
    assert interrupted_child_id is not None
    assert interrupted_workspace is not None and interrupted_workspace.is_dir()

    resume_manager = _fresh_manager(fixture)
    resume_executor = _new_executor(
        fixture,
        manager=resume_manager,
        runtime_dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=launches.factory,
        ),
        evaluation_dependencies=evaluation_dependencies,
    )
    resumed = resume_executor.execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed", resumed
    assert len(launches.launches) == 3
    assert [cell.arm_id for cell, _launch in launches.launches] == [
        "direct",
        "orc",
        "orc",
    ]
    assert direct_e1_path.read_bytes() == direct_ledger_bytes
    orc_after = load_attempt_ledger(orc_e1_path)
    assert any(
        row.attempt_ordinal == 1 and row.status == "discarded"
        for row in orc_after.rows
    )
    assert (
        orc_after.rows[-1].attempt_ordinal,
        orc_after.rows[-1].stage,
        orc_after.rows[-1].status,
    ) == (2, "committed", "committed")
    assert orc_after.rows[-1].bindings.child_run_id != interrupted_child_id
    assert orc_after.rows[-1].bindings.workspace_path != interrupted_workspace
    assert not interrupted_workspace.exists()
    assert len(check_calls) == 2
    assert len(scorer.prepared) == 2
    assert len(scorer.executed) == 2
    trial_ledger = load_trial_event_ledger(trial_ledger_path)
    assert tuple(
        row for row in trial_ledger.rows if row.kind == "trial_parent_committed"
    ) == (trial_ledger.rows[-1],)
    assert len([row for row in trial_ledger.rows if row.kind == "check_settled"]) == 2
    assert len([row for row in trial_ledger.rows if row.kind == "score_settled"]) == 2
