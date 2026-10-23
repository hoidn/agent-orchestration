from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import orchestrator
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = "derived_pure_replay.v1"
OUTCOME = {
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


def _workflow_text(evidence: Path) -> str:
    effect = evidence / "effect.py"
    counts = evidence / "counts.json"
    marker = evidence / "marker"
    return f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule settled_failed_command_fixture)
  (export run)
  (defrecord PriorValue (count Int) (value String))
  (defrecord Completion (count Int) (value String))
  (defrecord Output (count Int) (value String) (derived Int))
  (defworkflow run
    ((seed Int))
    -> Output
    (let* ((prior
             (command-result commit-prior
               :argv ("{sys.executable}" "{effect}" "first" seed "{counts}")
               :returns PriorValue))
           (derived (+ prior.count 7))
           (done
             (if (= derived 8)
               (command-result retry-work
                 :argv ("{sys.executable}" "{effect}" "retry" seed
                       "{marker}" "{counts}")
                 :returns Completion)
               (record Completion :count 0 :value "not-reached"))))
      (record Output :count done.count :value done.value :derived derived))))
'''


def _effect_script() -> str:
    return '''import json
import os
import sys
from pathlib import Path

mode = sys.argv[1]
if mode == "first":
    seed, counts_path = sys.argv[2:]
elif mode == "retry":
    seed, marker_path, counts_path = sys.argv[2:]
else:
    raise SystemExit(f"unknown effect mode: {mode}")

counts_file = Path(counts_path)
counts = json.loads(counts_file.read_text()) if counts_file.exists() else {}
counts[mode] = counts.get(mode, 0) + 1
counts_file.write_text(json.dumps(counts, sort_keys=True) + "\\n")

if mode == "retry" and not Path(marker_path).exists():
    print("external marker unavailable", file=sys.stderr)
    raise SystemExit(29)

if mode == "first":
    result = {"count": counts[mode], "value": f"durable-{seed}"}
else:
    result = {"count": int(seed) + 1, "value": f"completed-{seed}"}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    json.dumps(result, sort_keys=True) + "\\n", encoding="utf-8"
)
'''


def _write_fixture(evidence: Path) -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "counts.json").write_text("{}\n", encoding="utf-8")
    (evidence / "effect.py").write_text(_effect_script(), encoding="utf-8")
    (evidence / "settled_failed_command_fixture.orc").write_text(
        _workflow_text(evidence), encoding="utf-8"
    )
    command = [sys.executable, str(evidence / "effect.py")]
    (evidence / "command-boundaries.json").write_text(
        json.dumps(
            {
                name: {"kind": "external_tool", "stable_command": command}
                for name in ("commit-prior", "retry-work")
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _run_cli(candidate: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", *args],
        cwd=candidate,
        capture_output=True,
        text=True,
        check=False,
    )


def _compile_and_run(candidate: Path, evidence: Path) -> tuple[str, dict[str, Any]]:
    _write_fixture(evidence)
    source = evidence / "settled_failed_command_fixture.orc"
    boundaries = evidence / "command-boundaries.json"
    compiled = _run_cli(
        candidate,
        "compile",
        str(source),
        "--entry-workflow",
        "run",
        "--source-root",
        str(evidence),
        "--command-boundaries-file",
        str(boundaries),
    )
    assert compiled.returncode == 0, (compiled.stdout, compiled.stderr)
    run = _run_cli(
        candidate,
        "run",
        str(source),
        "--entry-workflow",
        "run",
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
    state = _state_after(candidate, run_id)
    counts = json.loads((evidence / "counts.json").read_text(encoding="utf-8"))
    assert counts == {"first": 1, "retry": 1}, counts
    assert not (evidence / "marker").exists()
    return run_id, state


def _record_paths(candidate: Path, run_id: str) -> list[Path]:
    root = candidate / ".orchestrate" / "runs" / run_id / "workflow_lisp" / "checkpoints" / "records"
    return sorted(root.glob("*/*.json"))


def _compile_fixture(candidate: Path, evidence: Path) -> Any:
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from orchestrator.workflow_lisp.workflows import ExternalToolBinding

    source = evidence / "settled_failed_command_fixture.orc"
    command = (sys.executable, str(evidence / "effect.py"))
    return compile_stage3_entrypoint(
        source,
        source_roots=(evidence,),
        entry_workflow="run",
        command_boundaries={
            name: ExternalToolBinding(name=name, stable_command=command)
            for name in ("commit-prior", "retry-work")
        },
        validate_shared=True,
        workspace_root=candidate,
    )


def _failed_command(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    failed = [
        (name, row)
        for name, row in state.get("steps", {}).items()
        if row.get("status") == "failed"
    ]
    assert len(failed) == 1, failed
    name, row = failed[0]
    assert row.get("exit_code") == 29, row
    assert row.get("outcome", {}).get("class") == "command_failed", row
    assert state.get("step_visits", {}).get(name) == row.get("visit_count") == 1
    return name, row


def _validate_checkpoint_authority(
    candidate: Path,
    evidence: Path,
    run_id: str,
    state: dict[str, Any],
    step_name: str,
    failed_row: dict[str, Any],
) -> tuple[Path, dict[str, Any], Any, Any]:
    from orchestrator.state import StateManager
    from orchestrator.workflow_lisp import lexical_checkpoint_restore, lexical_checkpoints

    compiled = _compile_fixture(candidate, evidence)
    bundle = compiled.validated_bundles_by_name["settled_failed_command_fixture::run"]
    matches = []
    for path in _record_paths(candidate, run_id):
        record = json.loads(path.read_text(encoding="utf-8"))
        resume_after = record.get("restore_payload", {}).get("resume_after", {})
        if resume_after.get("step_id") == failed_row.get("step_id"):
            matches.append((path, record))
    assert len(matches) == 1, matches
    record_path, record = matches[0]
    points = [
        point
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.checkpoint_id == record.get("checkpoint_id")
    ]
    assert len(points) == 1, points
    point = points[0]
    assert point.step_id == failed_row["step_id"]
    expected_point = lexical_checkpoints._point_payload(point)
    assert expected_point["effect_boundary"]["policy"]["policy_kind"] == (
        "reuse_validated_structured_output"
    )
    manager = StateManager(workspace=candidate, run_id=run_id)
    expected_identity = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=manager,
        runtime_plan=bundle.runtime_plan,
        workflow_path=evidence / "settled_failed_command_fixture.orc",
    )
    lexical_checkpoints.validate_checkpoint_record(
        record,
        expected_point=expected_point,
        expected_program_identity=expected_identity,
    )
    restore_payload = record["restore_payload"]
    lexical_checkpoint_restore.validate_restore_payload(
        restore_payload,
        expected_origin_key=record["origin_key"],
    )
    expected_index = bundle.runtime_plan.nodes[point.node_id].execution_index
    assert record["run_id"] == run_id
    assert record["frame_identity"] == {
        "execution_index": expected_index,
        "visit_count": failed_row["visit_count"],
        "loop_iteration": None,
        "call_frame_id": None,
    }
    assert restore_payload.get("restorable") is True
    assert restore_payload["resume_after"]["step_id"] == failed_row["step_id"]
    assert restore_payload["resume_after"]["execution_index"] == expected_index
    assert state["step_visits"][step_name] == record["frame_identity"]["visit_count"]
    return record_path, record, compiled, bundle


def _pure_rows_are_shells(
    candidate: Path,
    run_id: str,
    state: dict[str, Any],
    compiled: Any,
    bundle: Any,
    *,
    completed: bool,
) -> bool:
    pure_nodes = [
        node for node in bundle.runtime_plan.nodes.values() if node.kind == "pure_projection"
    ]
    if not pure_nodes:
        return False
    lowered = {
        workflow.typed_workflow.signature.name: workflow
        for workflow in compiled.entry_result.lowered_workflows
    }
    workflow = lowered.get(bundle.runtime_plan.workflow_name)
    if workflow is None:
        return False
    pure_effects = [
        effect
        for effect in workflow.origin_map.generated_semantic_effects
        if effect.effect_kind == "pure_projection"
    ]
    if len(pure_effects) != len(pure_nodes):
        return False
    nodes_by_step_id = {node.step_id: node for node in pure_nodes}
    pure_step_ids = {node.step_id for node in pure_nodes}
    reached_pure_ids = {
        node.step_id
        for node in pure_nodes
        if node.presentation_key in state.get("steps", {})
    }
    shell_rows = [
        row
        for row in state.get("steps", {}).values()
        if row.get("step_id") in pure_step_ids
    ]
    if not reached_pure_ids or {row.get("step_id") for row in shell_rows} != reached_pure_ids:
        return False
    for row in shell_rows:
        node = nodes_by_step_id[row["step_id"]]
        expected = {
            "name": node.presentation_key,
            "step_id": node.step_id,
            "visit_count": 1,
            "status": "completed",
            "exit_code": 0,
            "outcome": OUTCOME,
            "result_storage": PROFILE,
        }
        if row != expected or state.get("step_visits", {}).get(node.presentation_key) != 1:
            return False
    if completed:
        if state.get("status") != "completed":
            return False
    versions = state.get("private_artifact_versions", {})
    if not isinstance(versions, dict) or any(
        version.get("producer") in pure_step_ids
        for entries in versions.values()
        for version in entries
    ):
        return False
    for effect in pure_effects:
        output_ref = effect.details.get("output_bundle_path")
        if not isinstance(output_ref, str) or not output_ref.startswith("${inputs.") or not output_ref.endswith("}"):
            return False
        input_name = output_ref[len("${inputs.") : -1]
        output_path = state.get("bound_inputs", {}).get(input_name)
        if isinstance(output_path, str) and (candidate / output_path).is_file():
            return False
    for path in _record_paths(candidate, run_id):
        record = json.loads(path.read_text(encoding="utf-8"))
        resume_after = record.get("restore_payload", {}).get("resume_after", {})
        if resume_after.get("step_id") in pure_step_ids or any(
            binding.get("source_step_id") in pure_step_ids
            for binding in record.get("restore_payload", {}).get("bindings", [])
        ):
            return False
    return True


def _state_after(candidate: Path, run_id: str) -> dict[str, Any]:
    path = candidate / ".orchestrate" / "runs" / run_id / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["run_id"] = run_id
    return state


def test_settled_failed_root_command_resumes_from_its_checkpoint(tmp_path: Path) -> None:
    candidate = REPO_ROOT
    assert _module_is_from_candidate(orchestrator, candidate)
    evidence = tmp_path / "positive"
    run_id, failed_state = _compile_and_run(candidate, evidence)
    step_name, failed_row = _failed_command(failed_state)
    record_path, record, _compiled, bundle = _validate_checkpoint_authority(
        candidate, evidence, run_id, failed_state, step_name, failed_row
    )
    assert record_path.is_file()
    reached_pure_nodes = [
        node
        for node in bundle.runtime_plan.nodes.values()
        if node.kind == "pure_projection" and node.presentation_key in failed_state["steps"]
    ]
    assert reached_pure_nodes
    assert all(
        failed_state["steps"][node.presentation_key].get("status") == "completed"
        and failed_state["step_visits"].get(node.presentation_key) == 1
        for node in reached_pure_nodes
    ), reached_pure_nodes

    profile_before = failed_state.get("result_persistence_profile")
    initial_shells = [
        row
        for row in failed_state.get("steps", {}).values()
        if row.get("result_storage") == PROFILE
    ]
    pure_before = _pure_rows_are_shells(
        candidate, run_id, failed_state, _compiled, bundle, completed=False
    )
    (evidence / "marker").write_text("enabled\n", encoding="utf-8")
    resumed = _run_cli(candidate, "resume", run_id)
    final_state = _state_after(candidate, run_id)
    counts = json.loads((evidence / "counts.json").read_text(encoding="utf-8"))
    expected_output = {
        "return__count": 5,
        "return__value": "completed-4",
        "return__derived": 8,
    }
    final_shells = [
        row
        for row in final_state.get("steps", {}).values()
        if row.get("result_storage") == PROFILE
    ]
    observations = {
        "profile_before_resume": profile_before,
        "initial_pure_shells": initial_shells,
        "resume_exit_code": resumed.returncode,
        "resume_stderr": resumed.stderr,
        "status_after_resume": final_state.get("status"),
        "counts_after_resume": counts,
        "workflow_outputs": final_state.get("workflow_outputs"),
        "final_pure_shells": final_shells,
    }
    target = {
        "profile_persisted_before_resume": profile_before == PROFILE,
        "derived_values_are_shells_before_resume": pure_before,
        "resume_completed": resumed.returncode == 0 and final_state.get("status") == "completed",
        "prior_effect_not_repeated_and_failed_command_retried": counts == {"first": 1, "retry": 2},
        "output_correct": final_state.get("workflow_outputs") == expected_output,
        "derived_values_remain_shells": _pure_rows_are_shells(
            candidate, run_id, final_state, _compiled, bundle, completed=True
        ),
    }
    assert all(target.values()), {"target": target, "observations": observations}


@pytest.mark.parametrize("mutation", ["missing", "invalid", "non_restorable"])
def test_bad_checkpoint_authority_keeps_settled_command_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow_lisp import lexical_checkpoints

    candidate = REPO_ROOT
    evidence = tmp_path / mutation
    run_id, state = _compile_and_run(candidate, evidence)
    step_name, failed_row = _failed_command(state)
    record_path, record, _compiled, _bundle = _validate_checkpoint_authority(
        candidate, evidence, run_id, state, step_name, failed_row
    )
    assert state.get("result_persistence_profile") == PROFILE, state
    if mutation == "missing":
        index_path = lexical_checkpoints.resolve_checkpoint_index_path(
            state_manager=StateManager(workspace=candidate, run_id=run_id),
            workflow_name=record["program_identity"]["workflow_name"],
            checkpoint_id=record["checkpoint_id"],
        )
        index = json.loads(index_path.read_text(encoding="utf-8"))
        entries = [
            entry
            for entry in index["records"]
            if entry.get("record_id") == record["record_id"]
            and entry.get("frame_identity") == record["frame_identity"]
        ]
        assert len(entries) == 1, entries
        index["records"].remove(entries[0])
        record_path.unlink()
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    elif mutation == "invalid":
        assert record["restore_payload"]["bindings"], record
        record["restore_payload"]["bindings"][0]["value_digest"] = "sha256:" + "0" * 64
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    else:
        record["restore_payload"]["restorable"] = False
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    (evidence / "marker").write_text("enabled\n", encoding="utf-8")
    resumed = _run_cli(candidate, "resume", run_id)
    counts = json.loads((evidence / "counts.json").read_text(encoding="utf-8"))
    assert resumed.returncode != 0, (mutation, resumed.stdout, resumed.stderr)
    assert counts == {"first": 1, "retry": 1}, (mutation, counts)
