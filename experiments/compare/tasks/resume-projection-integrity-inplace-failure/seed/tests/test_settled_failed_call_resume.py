from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import orchestrator
import pytest
from orchestrator.workflow_lisp import lexical_checkpoint_restore, lexical_checkpoints
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.state import StateManager


REPO_ROOT = Path(__file__).resolve().parents[1]
PURE_RESULT_REPLAY = False
_OUTCOME = {
    "status": "completed",
    "phase": "execution",
    "class": "completed",
    "retryable": False,
}


def _module_is_from_candidate(module: Any, candidate: Path) -> bool:
    try:
        Path(module.__file__).resolve().relative_to(candidate.resolve())
    except (AttributeError, ValueError):
        return False
    return True


def _assert_historical_imports(candidate: Path) -> None:
    assert _module_is_from_candidate(orchestrator, candidate)
    assert _module_is_from_candidate(lexical_checkpoints, candidate)
    assert _module_is_from_candidate(lexical_checkpoint_restore, candidate)


def _workflow_text(evidence: Path) -> str:
    effect = evidence / "effect.py"
    counts = evidence / "counts.json"
    marker = evidence / "marker"
    gate = evidence / "gate"
    entered = evidence / "entered"
    child_pid = evidence / "child.pid"
    callee_body = (
        """
           (derived (if (= prior.count 1) (+ prior.count 7) 0))
           (done
             (if (= prior.count 1)
               (command-result retry-work
                 :argv ("python" "{effect}" "second" prior.count prior.value "{marker}" "{counts}" "{gate}" "{entered}" "{child_pid}")
                 :returns Completion)
               (record Completion :count prior.count :value prior.value)))"""
        if PURE_RESULT_REPLAY
        else """
           (done
             (command-result retry-work
               :argv ("python" "{effect}" "second" prior.count prior.value "{marker}" "{counts}" "{gate}" "{entered}" "{child_pid}")
               :returns Completion))"""
    )
    callee_result = (
        "(record Completion :count (+ derived done.count) :value prior.value)"
        if PURE_RESULT_REPLAY
        else "(record Completion :count done.count :value prior.value)"
    )
    caller_body = (
        """
           (result
             (if (= seed 4)
               (call callee :seed seed)
               (record Completion :count 0 :value "fallback")))"""
        if PURE_RESULT_REPLAY
        else """
           (result (call callee :seed seed))"""
    )
    callee_body = callee_body.format(
        effect=effect,
        marker=marker,
        counts=counts,
        gate=gate,
        entered=entered,
        child_pid=child_pid,
    )
    return f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule settled_failed_call_fixture)
  (export caller callee)
  (defrecord PriorValue (count Int) (value String))
  (defrecord CallerPrior (value String))
  (defrecord Completion (count Int) (value String))
  (defrecord CallerOutput (count Int) (value String) (caller_value String))
  (defworkflow callee
    ((seed Int))
    -> Completion
    (let* ((prior
             (command-result commit-prior
               :argv ("python" "{effect}" "first" seed "{counts}")
               :returns PriorValue)){callee_body})
      {callee_result}))
  (defworkflow caller
    ((seed Int))
    -> CallerOutput
    (let* ((caller_prior
             (command-result commit-caller-prior
               :argv ("python" "{effect}" "caller" seed "{counts}")
               :returns CallerPrior)){caller_body})
      (record CallerOutput :count result.count :value result.value :caller_value caller_prior.value))))
"""


def _effect_script() -> str:
    return """import json
import os
import sys
import time
from pathlib import Path

mode = sys.argv[1]
if mode == "caller":
    value, counts_path = sys.argv[2:]
elif mode == "first":
    value, counts_path = sys.argv[2:]
elif mode == "second":
    value, durable_value, marker_path, counts_path, gate_path, entered_path, pid_path = sys.argv[2:]
    if Path(gate_path).exists():
        Path(pid_path).write_text(f"{os.getpid()}\\n")
        Path(entered_path).write_text("entered\\n")
        time.sleep(60)
    if not Path(marker_path).exists():
        print("external marker unavailable", file=sys.stderr)
        raise SystemExit(29)
else:
    raise SystemExit(f"unknown effect mode: {mode}")

counts_file = Path(counts_path)
counts = json.loads(counts_file.read_text()) if counts_file.exists() else {}
key = {"caller": "caller", "first": "first", "second": "second"}[mode]
counts[key] = counts.get(key, 0) + 1
counts_file.write_text(json.dumps(counts, sort_keys=True) + "\\n")
if mode == "caller":
    result = {"value": f"caller-{value}"}
elif mode == "first":
    result = {"count": counts[key], "value": f"durable-{value}"}
else:
    result = {"count": int(value), "value": durable_value}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(result, sort_keys=True) + "\\n")
"""


def _write_fixture(evidence: Path) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "counts.json").write_text("{}\n", encoding="utf-8")
    (evidence / "effect.py").write_text(_effect_script(), encoding="utf-8")
    (evidence / "settled_failed_call_fixture.orc").write_text(_workflow_text(evidence), encoding="utf-8")
    commands = {
        name: {
            "kind": "external_tool",
            "stable_command": ["python", str(evidence / "effect.py")],
        }
        for name in ("commit-caller-prior", "commit-prior", "retry-work")
    }
    (evidence / "command-boundaries.json").write_text(
        json.dumps(commands, indent=2) + "\n",
        encoding="utf-8",
    )


def _record_command(evidence: Path, row: dict[str, Any]) -> None:
    with (evidence / "commands.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _run_cli(candidate: Path, evidence: Path, *args: str) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, "-m", "orchestrator", *args]
    result = subprocess.run(argv, cwd=candidate, capture_output=True, text=True, check=False)
    _record_command(
        evidence,
        {
            "argv": argv,
            "cwd": str(candidate.resolve()),
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    return result


def _compile_and_run(candidate: Path, evidence: Path) -> tuple[str, dict[str, Any]]:
    _write_fixture(evidence)
    source = evidence / "settled_failed_call_fixture.orc"
    boundaries = evidence / "command-boundaries.json"
    for entry in ("caller", "callee"):
        compiled = _run_cli(
            candidate,
            evidence,
            "compile",
            str(source),
            "--entry-workflow",
            entry,
            "--source-root",
            str(evidence),
            "--command-boundaries-file",
            str(boundaries),
        )
        assert compiled.returncode == 0, (entry, compiled.stdout, compiled.stderr)

    run = _run_cli(
        candidate,
        evidence,
        "run",
        str(source),
        "--entry-workflow",
        "caller",
        "--source-root",
        str(evidence),
        "--command-boundaries-file",
        str(boundaries),
        "--input",
        "seed=4",
    )
    assert run.returncode == 1, (run.returncode, run.stdout, run.stderr)
    assert "exit code 29" in run.stderr, run.stderr
    match = re.search(r"Created new run: ([A-Za-z0-9-]+)", run.stderr)
    assert match is not None, run.stderr
    run_id = match.group(1)
    state_path = candidate / ".orchestrate" / "runs" / run_id / "state.json"
    assert state_path.is_file()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    counts = json.loads((evidence / "counts.json").read_text(encoding="utf-8"))
    assert counts == {"caller": 1, "first": 1}, counts
    assert not (evidence / "marker").exists()
    return run_id, state


def _failed_scope_rows(state: dict[str, Any]) -> tuple[str, dict[str, Any], str, dict[str, Any], str, dict[str, Any]]:
    frame_items = [
        (frame_id, frame)
        for frame_id, frame in state.get("call_frames", {}).items()
        if frame.get("status") == "failed"
    ]
    assert len(frame_items) == 1, frame_items
    frame_id, frame = frame_items[0]
    caller_rows = [
        (name, row)
        for name, row in state["steps"].items()
        if row.get("status") == "failed" and row.get("step_id") == frame.get("call_step_id")
    ]
    assert len(caller_rows) == 1, caller_rows
    caller_name, caller_row = caller_rows[0]
    child_state = frame["state"]
    child_rows = [
        (name, row)
        for name, row in child_state["steps"].items()
        if row.get("status") == "failed"
    ]
    assert len(child_rows) == 1, child_rows
    child_name, child_row = child_rows[0]
    assert child_row.get("exit_code") == 29
    return frame_id, frame, caller_name, caller_row, child_name, child_row


def _record_paths(candidate: Path, run_id: str) -> list[Path]:
    root = candidate / ".orchestrate" / "runs" / run_id / "workflow_lisp" / "checkpoints" / "records"
    return sorted(root.glob("*/*.json"))


def _find_record(
    candidate: Path,
    run_id: str,
    workflow_name: str,
    failed_step_id: str,
) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in _record_paths(candidate, run_id):
        record = json.loads(path.read_text(encoding="utf-8"))
        resume_after = record.get("restore_payload", {}).get("resume_after", {})
        if (
            record.get("program_identity", {}).get("workflow_name") == workflow_name
            and resume_after.get("step_id") == failed_step_id
        ):
            matches.append((path, record))
    assert len(matches) == 1, (workflow_name, failed_step_id, matches)
    return matches[0]


def _compile_fixture(candidate: Path, evidence: Path) -> Any:
    commands = {
        name: ExternalToolBinding(
            name=name,
            stable_command=("python", str(evidence / "effect.py")),
        )
        for name in ("commit-caller-prior", "commit-prior", "retry-work")
    }
    source = evidence / "settled_failed_call_fixture.orc"
    return compile_stage3_entrypoint(
        source,
        source_roots=(evidence,),
        entry_workflow="caller",
        command_boundaries=commands,
        validate_shared=True,
        workspace_root=candidate,
    )


def _validate_checkpoint_authority(
    candidate: Path,
    evidence: Path,
    run_id: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    _assert_historical_imports(candidate)
    frame_id, frame, caller_name, caller_row, child_name, child_row = _failed_scope_rows(state)
    child_state = frame["state"]
    assert state["step_visits"][caller_name] == caller_row["visit_count"] == 1
    assert child_state["step_visits"][child_name] == child_row["visit_count"] == 1
    assert caller_row["outcome"]["status"] == "failed"
    assert child_row["outcome"]["class"] == "command_failed"

    caller_path, caller_record = _find_record(
        candidate,
        run_id,
        "settled_failed_call_fixture::caller",
        caller_row["step_id"],
    )
    callee_path, callee_record = _find_record(
        candidate,
        run_id,
        "settled_failed_call_fixture::callee",
        child_row["step_id"],
    )
    source = evidence / "settled_failed_call_fixture.orc"
    caller_compiled = _compile_fixture(candidate, evidence)
    caller_bundle = caller_compiled.validated_bundles_by_name[
        "settled_failed_call_fixture::caller"
    ]
    callee_bundle = caller_compiled.validated_bundles_by_name[
        "settled_failed_call_fixture::callee"
    ]
    caller_point = next(
        point
        for point in caller_bundle.runtime_plan.lexical_checkpoint_points
        if point.checkpoint_id == caller_record["checkpoint_id"]
    )
    callee_point = next(
        point
        for point in callee_bundle.runtime_plan.lexical_checkpoint_points
        if point.checkpoint_id == callee_record["checkpoint_id"]
    )
    assert caller_point.step_id == caller_row["step_id"]
    assert callee_point.step_id == child_row["step_id"]
    caller_expected = lexical_checkpoints._point_payload(caller_point)
    callee_expected = lexical_checkpoints._point_payload(callee_point)
    state_manager = StateManager(workspace=candidate, run_id=run_id)
    caller_identity = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=state_manager,
        runtime_plan=caller_bundle.runtime_plan,
        workflow_path=source,
    )
    callee_identity = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=state_manager,
        runtime_plan=callee_bundle.runtime_plan,
        workflow_path=source,
    )
    lexical_checkpoints.validate_checkpoint_record(
        caller_record,
        expected_point=caller_expected,
        expected_program_identity=caller_identity,
    )
    lexical_checkpoints.validate_checkpoint_record(
        callee_record,
        expected_point=callee_expected,
        expected_program_identity=callee_identity,
    )
    lexical_checkpoint_restore.validate_restore_payload(
        caller_record["restore_payload"],
        expected_origin_key=caller_record["origin_key"],
    )
    lexical_checkpoint_restore.validate_restore_payload(
        callee_record["restore_payload"],
        expected_origin_key=callee_record["origin_key"],
    )
    assert caller_record["restore_payload"].get("restorable") is True
    assert callee_record["restore_payload"].get("restorable") is True

    for record, point, bundle in ((caller_record, caller_point, caller_bundle),
                                  (callee_record, callee_point, callee_bundle)):
        expected_index = bundle.runtime_plan.nodes[point.node_id].execution_index
        assert record["run_id"] == run_id
        assert record["frame_identity"]["execution_index"] == expected_index
        assert record["restore_payload"]["resume_after"]["execution_index"] == expected_index
        assert record["restore_payload"]["resume_after"]["program_point_id"] == point.program_point_id

    assert caller_record["frame_identity"]["call_frame_id"] == frame_id
    assert caller_record["frame_identity"]["visit_count"] == caller_row["visit_count"]
    assert caller_record["restore_payload"]["resume_after"]["step_id"] == caller_row["step_id"]
    assert caller_expected["effect_boundary"]["policy"]["policy_kind"] == "reuse_validated_workflow_call"
    assert (
        caller_record["validity_envelope"]["effect_policy_digest"]
        == caller_expected["effect_boundary"]["policy"]["policy_digest"]
    )
    assert callee_record["frame_identity"]["call_frame_id"] == frame_id
    assert callee_record["frame_identity"]["visit_count"] == child_row["visit_count"]
    assert callee_record["restore_payload"]["resume_after"]["step_id"] == child_row["step_id"]
    assert (
        callee_expected["effect_boundary"]["policy"]["policy_kind"]
        == "reuse_validated_structured_output"
    )
    assert (
        callee_record["validity_envelope"]["effect_policy_digest"]
        == callee_expected["effect_boundary"]["policy"]["policy_digest"]
    )
    caller_binding = next(
        binding
        for binding in caller_record["restore_payload"]["bindings"]
        if binding["binding_name"] == "caller_prior"
    )
    callee_binding = next(
        binding
        for binding in callee_record["restore_payload"]["bindings"]
        if binding["binding_name"] == "prior"
    )
    assert caller_binding["value"] == {"value": "caller-4"}
    assert callee_binding["value"] == {"count": 1, "value": "durable-4"}
    for binding, bundle in (
        (caller_binding, caller_bundle),
        (callee_binding, callee_bundle),
    ):
        producer = next(node for node in bundle.runtime_plan.nodes.values()
                        if node.presentation_key == binding["source_step_name"])
        assert producer.kind == "command"
        assert binding["source_step_id"] == producer.lexical_scope[-1]
        assert binding["source_step_name"] == producer.presentation_key

    proof = {
        "candidate_root": str(candidate.resolve()),
        "run_id": run_id,
        "module_origins": {
            "orchestrator": orchestrator.__file__,
            "lexical_checkpoints": lexical_checkpoints.__file__,
            "lexical_checkpoint_restore": lexical_checkpoint_restore.__file__,
        },
        "counts_before_resume": json.loads((evidence / "counts.json").read_text(encoding="utf-8")),
        "call_frame_id": frame_id,
        "failed_call_row": {
            "name": caller_name,
            "step_id": caller_row["step_id"],
            "visit_count": caller_row["visit_count"],
            "step_visits": state["step_visits"][caller_name],
        },
        "failed_callee_command_row": {
            "name": child_name,
            "step_id": child_row["step_id"],
            "visit_count": child_row["visit_count"],
            "step_visits": child_state["step_visits"][child_name],
            "exit_code": child_row["exit_code"],
        },
        "caller_checkpoint": {
            "path": str(caller_path),
            "checkpoint_id": caller_record["checkpoint_id"],
            "record_id": caller_record["record_id"],
            "policy_kind": caller_expected["effect_boundary"]["policy"]["policy_kind"],
            "policy_digest_match": True,
            "checkpoint_validation": "passed",
            "expected_program_identity": caller_identity,
            "expected_point": caller_expected,
            "restore_payload_validation": "passed",
            "restore_payload": caller_record["restore_payload"],
            "legacy_provisional_policy": caller_record.get("provisional_policy"),
        },
        "callee_checkpoint": {
            "path": str(callee_path),
            "checkpoint_id": callee_record["checkpoint_id"],
            "record_id": callee_record["record_id"],
            "policy_kind": callee_expected["effect_boundary"]["policy"]["policy_kind"],
            "policy_digest_match": True,
            "checkpoint_validation": "passed",
            "expected_program_identity": callee_identity,
            "expected_point": callee_expected,
            "restore_payload_validation": "passed",
            "restore_payload": callee_record["restore_payload"],
            "legacy_provisional_policy": callee_record.get("provisional_policy"),
        },
        "target_profile_and_shell_observations": (
            _pure_result_observations(
                candidate, run_id, state, frame["state"], caller_compiled, caller_bundle, callee_bundle
            )
            if PURE_RESULT_REPLAY
            else None
        ),
    }
    (evidence / "checkpoint-proof-before-resume.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "frame_id": frame_id,
        "caller_step_id": caller_row["step_id"],
        "caller_record": caller_record,
        "callee_record": callee_record,
        "child_state": child_state,
        "profiles_before_resume": {
            "caller": state.get("result_persistence_profile"),
            "callee": child_state.get("result_persistence_profile"),
        },
        "compiled": caller_compiled,
        "caller_bundle": caller_bundle,
        "callee_bundle": callee_bundle,
    }


def _pure_result_observations(
    candidate: Path,
    run_id: str,
    root_state: dict[str, Any],
    child_state: dict[str, Any],
    compiled: Any,
    caller_bundle: Any,
    callee_bundle: Any,
) -> dict[str, Any]:
    scopes = (
        ("caller", root_state, caller_bundle.runtime_plan),
        ("callee", child_state, callee_bundle.runtime_plan),
    )
    # Fixed seed=4 takes the caller's then branch; its fallback projection never runs.
    expected_local = {
        "caller": {"settled_failed_call_fixture_caller__result__condition"},
        "callee": {
            "settled_failed_call_fixture_callee__derived",
            "settled_failed_call_fixture_callee__done__condition",
            "settled_failed_call_fixture_callee__terminal_projection",
        },
    }
    lowered = {
        workflow.typed_workflow.signature.name: workflow
        for workflow in compiled.entry_result.lowered_workflows
    }
    all_pure_ids = {}
    expected_identities = set()
    observed_shell_identities = []
    shell_rows = []
    pure_identity_mappings = []
    pure_bundles = []
    private_lineage_refs = []
    for scope, scoped_state, plan in scopes:
        effects = {
            effect.step_id: effect
            for effect in lowered[plan.workflow_name].origin_map.generated_semantic_effects
            if effect.effect_kind == "pure_projection"
        }
        nodes = {
            node.lexical_scope[-1]: node
            for node in plan.nodes.values()
            if node.kind == "pure_projection"
        }
        assert set(effects) == set(nodes), (scope, effects.keys(), nodes.keys())
        assert expected_local[scope] <= effects.keys()
        all_pure_ids[plan.workflow_name] = set(effects) | {node.step_id for node in nodes.values()}
        for local_id, node in nodes.items():
            pure_identity_mappings.append({"scope": scope, "node_id": node.node_id,
                "runtime_step_id": node.step_id, "compiler_step_id": local_id,
                "expected_reached": local_id in expected_local[scope]})
            output_ref = effects[local_id].details["output_bundle_path"]
            assert output_ref.startswith("${inputs.") and output_ref.endswith("}")
            input_name = output_ref[len("${inputs."):-1]
            bound_path = scoped_state.get("bound_inputs", {}).get(input_name)
            if isinstance(bound_path, str) and (candidate / bound_path).is_file():
                pure_bundles.append({"scope": scope, "runtime_step_id": node.step_id,
                    "output_ref": output_ref, "bound_input": input_name,
                    "path": str(candidate / bound_path)})
            if local_id not in expected_local[scope]:
                continue
            expected_identities.add((scope, node.step_id))
            name = node.presentation_key
            row = scoped_state.get("steps", {}).get(name)
            expected = {"name": name, "step_id": node.step_id, "visit_count": 1,
                "status": "completed", "exit_code": 0, "outcome": _OUTCOME,
                "result_storage": "derived_pure_replay.v1"}
            shell_rows.append({"scope": scope, "step_id": node.step_id, "row": row,
                "exact": row == expected and scoped_state.get("step_visits", {}).get(name) == 1})
        observed_shell_identities.extend(
            (scope, row.get("step_id"))
            for row in scoped_state.get("steps", {}).values()
            if row.get("result_storage") == "derived_pure_replay.v1"
        )
        versions = scoped_state.get("private_artifact_versions", {})
        assert isinstance(versions, dict)
        runtime_ids = {node.step_id for node in nodes.values()}
        for artifact, entries in versions.items():
            assert isinstance(entries, list)
            for version in entries:
                assert isinstance(version, dict)
                if version.get("producer") in runtime_ids:
                    private_lineage_refs.append({"scope": scope, "artifact": artifact,
                        "producer": version["producer"], "version": version.get("version")})
    assert len(expected_identities) == 4
    assert len(pure_identity_mappings) == 5
    records = [json.loads(path.read_text(encoding="utf-8")) for path in _record_paths(candidate, run_id)]
    pure_checkpoint_ids = []
    pure_restore_bindings = []
    for record in records:
        ids = all_pure_ids[record["program_identity"]["workflow_name"]]
        resume_after = record.get("restore_payload", {}).get("resume_after", {})
        if (record.get("pending_effect_policy", {}).get("effect_kind") == "pure_projection"
                or resume_after.get("step_id") in ids):
            pure_checkpoint_ids.append(record["checkpoint_id"])
        for binding in record.get("restore_payload", {}).get("bindings", []):
            if binding.get("source_step_id") in ids:
                pure_restore_bindings.append({"checkpoint_id": record["checkpoint_id"],
                    "source_step_id": binding["source_step_id"]})
    return {
        "profiles": {"caller": root_state.get("result_persistence_profile"),
                     "callee": child_state.get("result_persistence_profile")},
        "pure_shell_count": len(observed_shell_identities),
        "pure_compiler_node_count": len(expected_identities),
        "all_compiled_pure_node_count": len(pure_identity_mappings),
        "expected_reached_pure_identities": sorted(expected_identities),
        "observed_shell_identities": sorted(observed_shell_identities),
        "pure_shell_rows": shell_rows,
        "pure_shells_exact": (set(observed_shell_identities) == expected_identities
                              and len(observed_shell_identities) == len(expected_identities)
                              and all(row["exact"] for row in shell_rows)),
        "pure_identity_mappings": pure_identity_mappings,
        "pure_checkpoint_ids": pure_checkpoint_ids,
        "pure_restore_bindings": pure_restore_bindings,
        "pure_result_bundles": pure_bundles,
        "pure_private_lineage_refs": private_lineage_refs,
    }


def _contains_result(value: Any) -> bool:
    expected_count = 9 if PURE_RESULT_REPLAY else 1
    if isinstance(value, dict):
        if value.get("count") == expected_count and value.get("value") == "durable-4" and value.get("caller_value") == "caller-4":
            return True
        return any(_contains_result(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_result(item) for item in value)
    return False


def _state_after(candidate: Path, run_id: str) -> dict[str, Any]:
    return json.loads(
        (candidate / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8")
    )


def _raw_authority(
    candidate: Path,
    run_id: str,
    state: dict[str, Any],
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    _, frame, _, caller_row, _, child_row = _failed_scope_rows(state)
    caller_path, caller_record = _find_record(
        candidate,
        run_id,
        "settled_failed_call_fixture::caller",
        caller_row["step_id"],
    )
    callee_path, callee_record = _find_record(
        candidate,
        run_id,
        "settled_failed_call_fixture::callee",
        child_row["step_id"],
    )
    assert caller_record["restore_payload"]["restorable"] is True
    assert callee_record["restore_payload"]["restorable"] is True
    return caller_path, caller_record, callee_path, callee_record


def test_settled_failed_call_resumes_in_the_same_frame(tmp_path: Path) -> None:
    candidate = REPO_ROOT
    _assert_historical_imports(candidate)
    evidence = tmp_path / "positive"
    run_id, initial_state = _compile_and_run(candidate, evidence)
    authority = _validate_checkpoint_authority(candidate, evidence, run_id, initial_state)

    (evidence / "marker").write_text("enabled\n", encoding="utf-8")
    resumed = _run_cli(candidate, evidence, "resume", run_id)
    final_state = _state_after(candidate, run_id)
    final_frames = [
        (frame_id, frame)
        for frame_id, frame in final_state.get("call_frames", {}).items()
        if frame.get("call_step_id") == authority["caller_step_id"]
    ]
    final_counts = json.loads((evidence / "counts.json").read_text(encoding="utf-8"))
    output = final_state.get("workflow_outputs", {})
    observations: dict[str, Any] = {
        "resume_exit_code": resumed.returncode,
        "resume_stdout": resumed.stdout,
        "resume_stderr": resumed.stderr,
        "counts_after_resume": final_counts,
        "same_original_frame": len(final_frames) == 1 and final_frames[0][0] == authority["frame_id"],
        "frame_completed": (
            len(final_frames) == 1
            and final_frames[0][1].get("status") == "completed"
            and final_frames[0][1].get("state", {}).get("status") == "completed"
        ),
        "root_completed": final_state.get("status") == "completed",
        "final_output_matches_expected_result": _contains_result(output),
    }
    if PURE_RESULT_REPLAY:
        observations["profiles_before_resume"] = authority["profiles_before_resume"]
        observations["profile_and_derived_persistence"] = _pure_result_observations(
            candidate,
            run_id,
            final_state,
            final_frames[0][1].get("state", {}) if final_frames else {},
            authority["compiled"],
            authority["caller_bundle"],
            authority["callee_bundle"],
        )
    (evidence / "target-observations.json").write_text(
        json.dumps(observations, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    target_passed = (
        observations["resume_exit_code"] == 0
        and observations["counts_after_resume"] == {"caller": 1, "first": 1, "second": 1}
        and observations["same_original_frame"]
        and observations["frame_completed"]
        and observations["root_completed"]
        and observations["final_output_matches_expected_result"]
    )
    if PURE_RESULT_REPLAY:
        profile_observations = observations["profile_and_derived_persistence"]
        target_passed = target_passed and (
            observations["profiles_before_resume"]
            == {"caller": "derived_pure_replay.v1", "callee": "derived_pure_replay.v1"}
            and profile_observations["profiles"]
            == {"caller": "derived_pure_replay.v1", "callee": "derived_pure_replay.v1"}
            and profile_observations["pure_shell_count"]
            == profile_observations["pure_compiler_node_count"]
            and profile_observations["pure_shells_exact"]
            and not profile_observations["pure_checkpoint_ids"]
            and not profile_observations["pure_restore_bindings"]
            and not profile_observations["pure_result_bundles"]
            and not profile_observations["pure_private_lineage_refs"]
        )
    assert target_passed, (
        "target recovery assertions failed after both actual caller and callee checkpoint "
        "preconditions passed; see retained checkpoint-proof-before-resume.json and "
        "target-observations.json: "
        + json.dumps(
            {
                "preconditions": {
                    "caller_checkpoint": authority["caller_record"]["checkpoint_id"],
                    "caller_restore_payload_restorable": authority["caller_record"]["restore_payload"]["restorable"],
                    "callee_checkpoint": authority["callee_record"]["checkpoint_id"],
                    "callee_restore_payload_restorable": authority["callee_record"]["restore_payload"]["restorable"],
                    "frame_id": authority["frame_id"],
                },
                "observations": observations,
            },
            sort_keys=True,
        )
    )


def test_bad_checkpoint_authority_stays_fail_closed(tmp_path: Path) -> None:
    candidate = REPO_ROOT
    observations = {}
    for mutation in ("missing", "invalid", "non_restorable"):
        evidence = tmp_path / mutation
        run_id, state = _compile_and_run(candidate, evidence)
        caller_path, caller_record, callee_path, callee_record = _raw_authority(
            candidate,
            run_id,
            state,
        )
        snapshot = evidence / "before-mutation"
        snapshot.mkdir()
        run_dir = candidate / ".orchestrate" / "runs" / run_id
        shutil.copy2(run_dir / "state.json", snapshot / "state.json")
        shutil.copytree(
            run_dir / "workflow_lisp" / "checkpoints",
            snapshot / "checkpoints",
        )
        if mutation == "missing":
            index_path = lexical_checkpoints.resolve_checkpoint_index_path(
                state_manager=StateManager(workspace=candidate, run_id=run_id),
                workflow_name=callee_record["program_identity"]["workflow_name"],
                checkpoint_id=callee_record["checkpoint_id"],
            )
            index = json.loads(index_path.read_text(encoding="utf-8"))
            matches = [entry for entry in index["records"]
                       if entry["record_id"] == callee_record["record_id"]
                       and entry["frame_identity"] == callee_record["frame_identity"]]
            assert len(matches) == 1
            assert candidate / matches[0]["record_path"] == callee_path
            index["records"].remove(matches[0])
            callee_path.unlink()
            index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
            compiled = _compile_fixture(candidate, evidence)
            bundle = compiled.validated_bundles_by_name["settled_failed_call_fixture::callee"]
            decision = lexical_checkpoint_restore.select_restore_candidate(
                state_manager=StateManager(workspace=candidate, run_id=run_id),
                runtime_plan=bundle.runtime_plan,
                state=state["call_frames"][callee_record["frame_identity"]["call_frame_id"]]["state"],
                checkpoint_id=callee_record["checkpoint_id"],
                executable_workflow=bundle.ir,
                loaded_workflow=bundle,
            )
            absence = {"kind": decision.kind, "selection_observation": decision.selection_observation,
                       "checkpoint_id": decision.checkpoint_id, "diagnostics": list(decision.diagnostics)}
            (evidence / "record-absence-decision.json").write_text(
                json.dumps(absence, indent=2) + "\n", encoding="utf-8")
            assert decision.kind != lexical_checkpoint_restore.RESTORE_DECISION_RESTORED, absence
            assert decision.selection_observation == lexical_checkpoint_restore.RESTORE_SELECTION_RECORD_ABSENT, absence
        elif mutation == "invalid":
            caller_record["restore_payload"]["bindings"][0]["value_digest"] = "sha256:" + "0" * 64
            caller_path.write_text(json.dumps(caller_record, indent=2) + "\n", encoding="utf-8")
        else:
            callee_record["restore_payload"]["restorable"] = False
            callee_path.write_text(json.dumps(callee_record, indent=2) + "\n", encoding="utf-8")

        (evidence / "marker").write_text("enabled\n", encoding="utf-8")
        resumed = _run_cli(candidate, evidence, "resume", run_id)
        counts = json.loads((evidence / "counts.json").read_text(encoding="utf-8"))
        observations[mutation] = {
            "exit_code": resumed.returncode,
            "stdout": resumed.stdout,
            "stderr": resumed.stderr,
            "counts": counts,
            "mutated_authority": str(callee_path if mutation != "invalid" else caller_path),
        }
    (tmp_path / "bad-checkpoint-observations.json").write_text(
        json.dumps(observations, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failures = {
        mutation: observation
        for mutation, observation in observations.items()
        if observation["exit_code"] == 0
        or observation["counts"] != {"caller": 1, "first": 1}
    }
    assert not failures, json.dumps(failures, sort_keys=True)


def test_unknown_interruption_has_no_settled_failure_restore_eligibility(tmp_path: Path) -> None:
    candidate = REPO_ROOT
    evidence = tmp_path / "interrupted"
    _write_fixture(evidence)
    source = evidence / "settled_failed_call_fixture.orc"
    boundaries = evidence / "command-boundaries.json"
    for entry in ("caller", "callee"):
        compiled = _run_cli(
            candidate,
            evidence,
            "compile",
            str(source),
            "--entry-workflow",
            entry,
            "--source-root",
            str(evidence),
            "--command-boundaries-file",
            str(boundaries),
        )
        assert compiled.returncode == 0, (entry, compiled.stdout, compiled.stderr)

    (evidence / "gate").write_text("block\n", encoding="utf-8")
    argv = [
        sys.executable,
        "-m",
        "orchestrator",
        "run",
        str(source),
        "--entry-workflow",
        "caller",
        "--source-root",
        str(evidence),
        "--command-boundaries-file",
        str(boundaries),
        "--input",
        "seed=4",
    ]
    log_path = evidence / "interrupted-run.log"
    process = None
    child_pid = None
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            argv,
            cwd=candidate,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            _record_command(
                evidence,
                {"argv": argv, "cwd": str(candidate.resolve()), "started": True, "interrupted": True},
            )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not (evidence / "entered").exists():
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            assert (evidence / "entered").exists(), log_path.read_text(encoding="utf-8")
            child_pid = int((evidence / "child.pid").read_text(encoding="utf-8").strip())
        finally:
            if child_pid is None and (evidence / "child.pid").is_file():
                child_pid = int((evidence / "child.pid").read_text(encoding="utf-8").strip())
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

    log_text = log_path.read_text(encoding="utf-8")
    match = re.search(r"Created new run: ([A-Za-z0-9-]+)", log_text)
    assert match is not None, log_text
    run_id = match.group(1)
    (evidence / "gate").unlink()
    (evidence / "marker").write_text("enabled\n", encoding="utf-8")
    interrupted_state = _state_after(candidate, run_id)
    frame_items = list(interrupted_state.get("call_frames", {}).items())
    assert len(frame_items) == 1, frame_items
    frame_id, frame = frame_items[0]
    child_state = frame["state"]
    child_cursor = child_state.get("current_step")
    assert isinstance(child_cursor, dict)
    assert child_cursor["status"] == "running" and child_cursor["type"] == "command"
    child_name = child_cursor["name"]
    assert child_state["step_visits"][child_name] == child_cursor["visit_count"] == 1
    child_row = child_state.get("steps", {}).get(child_name)
    assert child_row is None or (child_row.get("status") == "running" and not child_row.get("outcome"))
    assert frame["status"] == "running"
    assert interrupted_state["current_step"]["step_id"] == frame["call_step_id"]
    counts_before = json.loads((evidence / "counts.json").read_text(encoding="utf-8"))
    assert counts_before == {"caller": 1, "first": 1}
    (evidence / "state-before-resume.json").write_bytes(
        (candidate / ".orchestrate" / "runs" / run_id / "state.json").read_bytes())
    compiled = _compile_fixture(candidate, evidence)
    callee_bundle = compiled.validated_bundles_by_name["settled_failed_call_fixture::callee"]
    points = [point for point in callee_bundle.runtime_plan.lexical_checkpoint_points
              if point.step_id == child_cursor["step_id"]]
    assert len(points) == 1
    point = points[0]
    decision = lexical_checkpoint_restore.select_restore_candidate(
        state_manager=StateManager(workspace=candidate, run_id=run_id),
        runtime_plan=callee_bundle.runtime_plan,
        state=child_state,
        checkpoint_id=point.checkpoint_id,
        executable_workflow=callee_bundle.ir,
        loaded_workflow=callee_bundle,
    )
    eligibility = {
        "kind": decision.kind,
        "selection_observation": decision.selection_observation,
        "checkpoint_id": decision.checkpoint_id,
        "diagnostics": list(decision.diagnostics),
        "current_step_id": child_cursor["step_id"],
        "compiled_point_step_id": point.step_id,
    }
    assert decision.kind != lexical_checkpoint_restore.RESTORE_DECISION_RESTORED, eligibility
    assert json.loads((evidence / "counts.json").read_text(encoding="utf-8")) == counts_before
    (evidence / "unknown-interruption-before-resume.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "call_frame_id": frame_id,
                "child_row_name": child_name,
                "child_row": child_row,
                "child_current_step": child_cursor,
                "settled_failure_eligibility": eligibility,
                "counts_before_resume": json.loads((evidence / "counts.json").read_text(encoding="utf-8")),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    resumed = _run_cli(candidate, evidence, "resume", run_id)
    counts = json.loads((evidence / "counts.json").read_text(encoding="utf-8"))
    observation = {
        "resume_exit_code": resumed.returncode,
        "stdout": resumed.stdout,
        "stderr": resumed.stderr,
        "counts_after_resume": counts,
        "call_frame_id": frame_id,
        "child_row_status_after_interruption": child_row.get("status") if child_row else None,
        "child_row_outcome_after_interruption": child_row.get("outcome") if child_row else None,
        "child_current_step_after_interruption": child_cursor,
        "settled_failure_eligibility": eligibility,
        "compatibility_observation_only": True,
    }
    (evidence / "unknown-interruption-observations.json").write_text(
        json.dumps(observation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
