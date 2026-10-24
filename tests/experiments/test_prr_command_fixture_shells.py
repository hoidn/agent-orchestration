"""The public fixture requires shells only for successful pure rows."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.state import StepResult


FIXTURE = Path(__file__).parents[2] / "experiments/compare/tasks/pure-result-replay-command-recovery/seed/tests/test_settled_failed_command_resume.py"
spec = importlib.util.spec_from_file_location("public_command_fixture", FIXTURE)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


@pytest.fixture
def state_case(tmp_path):
    nodes = [SimpleNamespace(kind="pure_projection", step_id=f"pure-{name}", presentation_key=name)
             for name in ("completed", "skipped")]
    effects = [SimpleNamespace(effect_kind="pure_projection", details={"output_bundle_path": f"${{inputs.{name}_bundle}}"})
               for name in ("completed", "skipped")]
    lowered = SimpleNamespace(typed_workflow=SimpleNamespace(signature=SimpleNamespace(name="fixture")),
                              origin_map=SimpleNamespace(generated_semantic_effects=effects))
    compiled = SimpleNamespace(entry_result=SimpleNamespace(lowered_workflows=[lowered]))
    bundle = SimpleNamespace(runtime_plan=SimpleNamespace(workflow_name="fixture", nodes={n.step_id: n for n in nodes}))
    skipped = StepResult(status="skipped", name="skipped", step_id="pure-skipped", exit_code=0, duration_ms=0,
                         skipped=True, outcome={"status": "skipped", "phase": "pre_execution", "class": "skipped", "retryable": False}).to_dict()
    state = {"status": "completed", "steps": {
        "completed": {"name": "completed", "step_id": "pure-completed", "visit_count": 1, "status": "completed",
                      "exit_code": 0, "outcome": fixture.OUTCOME, "result_storage": fixture.PROFILE},
        "skipped": skipped}, "step_visits": {"completed": 1}, "private_artifact_versions": {},
        "bound_inputs": {name + "_bundle": name + ".json" for name in ("completed", "skipped")}}
    def check():
        return fixture._pure_rows_are_shells(tmp_path, "run", state, compiled, bundle, completed=True)
    return tmp_path, state, check


def test_valid_full_unvisited_skip_alongside_exact_completion_shell(state_case):
    _, _, check = state_case
    assert check()


@pytest.mark.parametrize("status", ["failed", "skipped"])
def test_visited_failure_or_skip_remains_full_step_result(state_case, status):
    _, state, check = state_case
    state["steps"]["skipped"] = StepResult(status=status, name="skipped", step_id="pure-skipped", visit_count=1,
        skipped=status == "skipped", exit_code=1 if status == "failed" else 0,
        outcome={"status": status, "phase": "execution", "class": status, "retryable": False}).to_dict()
    state["step_visits"]["skipped"] = 1
    assert check()


@pytest.mark.parametrize("status,contradiction", [("failed", "completed"), ("failed", "skipped"),
                                                  ("skipped", "completed"), ("skipped", "failed")])
def test_full_durable_row_rejects_contradictory_outcome_status(state_case, status, contradiction):
    _, state, check = state_case
    state["steps"]["skipped"] = StepResult(status=status, name="skipped", step_id="pure-skipped", visit_count=1,
        skipped=status == "skipped", outcome={"status": contradiction}).to_dict()
    state["step_visits"]["skipped"] = 1
    assert not check()


@pytest.mark.parametrize("change", [{"value": 8}, {"output": 8}, {"visit_count": 2}, {"exit_code": 1},
                                     {"outcome": {"status": "completed"}}, {"unexpected": "field"}])
def test_completion_shell_remains_exact(state_case, change):
    _, state, check = state_case
    state["steps"]["completed"].update(change)
    assert not check()


@pytest.mark.parametrize("change", [{"name": "wrong"}, {"step_id": "wrong"}, {"status": "running"},
                                     {"skipped": False}, {"visit_count": 2}, {"value": 8}])
def test_malformed_full_skip_is_not_ignored(state_case, change):
    _, state, check = state_case
    state["steps"]["skipped"].update(change)
    assert not check()


@pytest.mark.parametrize("artifact", ["bundle", "private-version", "checkpoint", "binding"])
def test_forbidden_pure_artifacts_still_refuse(state_case, artifact):
    root, state, check = state_case
    if artifact == "bundle":
        (root / "completed.json").write_text("8")
    elif artifact == "private-version":
        state["private_artifact_versions"] = {"value": [{"producer": "pure-completed"}]}
    else:
        record = root / ".orchestrate/runs/run/workflow_lisp/checkpoints/records/checkpoint/record.json"
        record.parent.mkdir(parents=True)
        payload = {"resume_after": {"step_id": "pure-completed"}} if artifact == "checkpoint" else {
            "bindings": [{"source_step_id": "pure-completed"}]}
        record.write_text(json.dumps({"restore_payload": payload}))
    assert not check()
