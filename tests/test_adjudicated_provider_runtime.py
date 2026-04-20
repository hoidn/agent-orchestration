import json
from pathlib import Path

import pytest
import yaml

import orchestrator.workflow.executor as executor_module
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.adjudication import (
    PromotionConflictError,
    adjudication_visit_paths,
    candidate_paths,
)
from orchestrator.workflow.executor import WorkflowExecutor
from tests.workflow_bundle_helpers import bundle_context_dict


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _install_fake_clock(monkeypatch: pytest.MonkeyPatch, fake_clock: _FakeClock) -> None:
    monkeypatch.setattr(executor_module.time, "monotonic", fake_clock.monotonic)
    monkeypatch.setattr("orchestrator.workflow.adjudication.time.monotonic", fake_clock.monotonic)
    monkeypatch.setattr(executor_module.time, "sleep", lambda seconds: fake_clock.advance(float(seconds)))


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _candidate_command(label: str, body: str, pointer_dir: str = "state") -> list[str]:
    return [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"Path({pointer_dir!r}).mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            f"Path({str(Path(pointer_dir) / 'result_path.txt')!r}).write_text('docs/plans/{label}.md\\n', encoding='utf-8')\n"
            f"Path('docs/plans/{label}.md').write_text({body!r}, encoding='utf-8')\n"
        ),
    ]


def _evaluator_command(scores: dict[str, float]) -> list[str]:
    return [
        "python",
        "-c",
        (
            "import json, sys\n"
            "text = sys.stdin.read()\n"
            "packet = json.loads(text.split('Evaluator Packet:', 1)[1])\n"
            "candidate_id = packet['candidate_id']\n"
            f"scores = {scores!r}\n"
            "print(json.dumps({'candidate_id': candidate_id, 'score': scores[candidate_id], 'summary': 'scored'}))\n"
        ),
    ]


def _workflow(scores: dict[str, float] | None = None, **step_overrides: object) -> dict:
    scores = {"a": 0.4, "b": 0.9} if scores is None else scores
    step = {
        "name": "Draft",
        "id": "draft",
        "adjudicated_provider": {
            "candidates": [
                {"id": "a", "provider": "candidate_a"},
                {"id": "b", "provider": "candidate_b"},
            ],
            "evaluator": {
                "provider": "evaluator",
                "input_file": "evaluator.md",
                "evidence_confidentiality": "same_trust_boundary",
            },
            "selection": {
                "tie_break": "candidate_order",
            },
            "score_ledger_path": "artifacts/evaluations/draft_scores.jsonl",
        },
        "input_file": "prompt.md",
        "expected_outputs": [
            {
                "name": "result_path",
                "path": "state/result_path.txt",
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }
        ],
        "publishes": [
            {"artifact": "result_path", "from": "result_path"},
        ],
    }
    step.update(step_overrides)
    return {
        "version": "2.11",
        "name": "adjudicated-runtime",
        "artifacts": {
            "result_path": {
                "kind": "relpath",
                "type": "relpath",
                "pointer": "state/result_path.txt",
                "under": "docs/plans",
                "must_exist_target": True,
            },
        },
        "providers": {
            "candidate_a": {"command": _candidate_command("a", "weaker"), "input_mode": "stdin"},
            "candidate_b": {"command": _candidate_command("b", "better"), "input_mode": "stdin"},
            "evaluator": {"command": _evaluator_command(scores), "input_mode": "stdin"},
        },
        "steps": [step],
    }


def _run(workspace: Path, workflow: dict, *, mutate_executor: object = None) -> dict:
    (workspace / "prompt.md").write_text("Draft the best possible artifact.", encoding="utf-8")
    (workspace / "evaluator.md").write_text("Return strict JSON.", encoding="utf-8")
    workflow_file = _write_yaml(workspace / "workflow.yaml", workflow)
    loaded = WorkflowLoader(workspace).load(workflow_file)
    state_manager = StateManager(workspace=workspace, run_id="run-1")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, workspace, state_manager, retry_delay_ms=0)
    if callable(mutate_executor):
        mutate_executor(executor)
    return executor.execute()


def test_adjudicated_provider_selects_highest_scored_candidate_and_publishes(tmp_path: Path) -> None:
    state = _run(tmp_path, _workflow())

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["artifacts"]["result_path"] == "docs/plans/b.md"
    assert (tmp_path / "docs/plans/b.md").read_text(encoding="utf-8") == "better"
    assert result["adjudication"]["selected_candidate_id"] == "b"
    assert result["adjudication"]["selected_score"] == 0.9
    assert result["adjudication"]["promotion_status"] == "committed"
    selected_state = result["adjudication"]["candidates"]["b"]
    assert selected_state["candidate_run_key"].startswith("sha256:")
    assert selected_state["score_run_key"].startswith("sha256:")
    assert "output" not in result
    assert "json" not in result
    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert [row["candidate_id"] for row in rows] == ["a", "b"]
    assert [row["selected"] for row in rows] == [False, True]
    assert state["artifact_versions"]["result_path"][-1]["value"] == "docs/plans/b.md"


def test_evaluator_packet_includes_consumed_relpath_target_content(tmp_path: Path) -> None:
    workflow = _workflow(
        {"a": 1.0},
        adjudicated_provider={
            "candidates": [
                {"id": "a", "provider": "candidate_a"},
            ],
            "evaluator": {
                "provider": "evaluator",
                "input_file": "evaluator.md",
                "evidence_confidentiality": "same_trust_boundary",
            },
            "selection": {
                "tie_break": "candidate_order",
                "require_score_for_single_candidate": True,
            },
            "score_ledger_path": "artifacts/evaluations/draft_scores.jsonl",
        },
        consumes=[
            {
                "artifact": "source_doc",
                "producers": ["Seed"],
                "policy": "latest_successful",
                "freshness": "any",
            },
        ],
        prompt_consumes=["source_doc"],
    )
    workflow["artifacts"]["source_doc"] = {
        "kind": "relpath",
        "type": "relpath",
        "pointer": "state/source_doc_path.txt",
        "under": "docs",
        "must_exist_target": True,
    }
    workflow["providers"]["evaluator"] = {
        "command": [
            "python",
            "-c",
            (
                "import json, sys\n"
                "packet = json.loads(sys.stdin.read().split('Evaluator Packet:', 1)[1])\n"
                "items = {item['name']: item['content'] for item in packet['evidence_items']}\n"
                "assert packet['consumed_artifacts'] == {'source_doc': 'docs/source.md'}\n"
                "assert items['consume.source_doc.value'] == 'docs/source.md'\n"
                "assert items['consume.source_doc.target'] == 'source evidence\\n'\n"
                "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': 1.0, 'summary': 'has source'}))\n"
            ),
        ],
        "input_mode": "stdin",
    }
    workflow["steps"].insert(
        0,
        {
            "name": "Seed",
            "command": [
                "python",
                "-c",
                (
                    "from pathlib import Path\n"
                    "Path('state').mkdir(exist_ok=True)\n"
                    "Path('docs').mkdir(exist_ok=True)\n"
                    "Path('state/source_doc_path.txt').write_text('docs/source.md\\n', encoding='utf-8')\n"
                    "Path('docs/source.md').write_text('source evidence\\n', encoding='utf-8')\n"
                ),
            ],
            "expected_outputs": [
                {
                    "name": "source_doc_path",
                    "path": "state/source_doc_path.txt",
                    "type": "relpath",
                    "under": "docs",
                    "must_exist_target": True,
                }
            ],
            "publishes": [{"artifact": "source_doc", "from": "source_doc_path"}],
        },
    )

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["adjudication"]["selected_score"] == 1.0


def test_score_ledger_path_is_substituted_before_mirror_materialization(tmp_path: Path) -> None:
    workflow = _workflow()
    workflow["steps"][0]["adjudicated_provider"]["score_ledger_path"] = (
        "artifacts/evaluations/${run.id}/draft_scores.jsonl"
    )

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["adjudication"]["score_ledger_path"] == "artifacts/evaluations/run-1/draft_scores.jsonl"
    assert (tmp_path / "artifacts/evaluations/run-1/draft_scores.jsonl").exists()
    assert not (tmp_path / "artifacts/evaluations/${run.id}/draft_scores.jsonl").exists()


def test_score_ledger_path_rejects_artifacts_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "artifacts").symlink_to(outside, target_is_directory=True)

    state = _run(tmp_path, _workflow())

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "ledger_path_collision"
    assert not (outside / "evaluations/draft_scores.jsonl").exists()


def test_adjudicated_provider_tie_breaks_by_candidate_order(tmp_path: Path) -> None:
    state = _run(tmp_path, _workflow(scores={"a": 0.8, "b": 0.8}))

    result = state["steps"]["Draft"]
    assert result["artifacts"]["result_path"] == "docs/plans/a.md"
    assert result["adjudication"]["selection_reason"] == "candidate_order_tie_break"


def test_single_candidate_promotes_when_evaluation_fails_and_score_optional(tmp_path: Path) -> None:
    workflow = _workflow()
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        "print('not json')",
    ]
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["artifacts"]["result_path"] == "docs/plans/a.md"
    assert result["adjudication"]["selected_score"] is None
    assert result["adjudication"]["candidates"]["a"]["score_status"] == "evaluation_failed"


def test_single_candidate_scorer_unavailable_promotes_when_score_optional(tmp_path: Path) -> None:
    workflow = _workflow()
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["steps"][0]["adjudicated_provider"]["evaluator"]["input_file"] = "missing-evaluator.md"

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["artifacts"]["result_path"] == "docs/plans/a.md"
    candidate_state = result["adjudication"]["candidates"]["a"]
    assert candidate_state["score_status"] == "scorer_unavailable"
    assert candidate_state["scorer_resolution_failure_key"].startswith("sha256:")
    paths = candidate_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1, "a")
    assert not paths.evaluation_packet_path.exists()

    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["score_status"] == "scorer_unavailable"
    assert rows[0]["scorer_identity_hash"] is None
    assert rows[0]["scorer_resolution_failure_key"].startswith("sha256:")


def test_scorer_unavailable_leaves_invalid_candidates_not_evaluated(tmp_path: Path) -> None:
    workflow = _workflow(scores={"b": 0.9})
    workflow["providers"]["candidate_a"]["command"] = ["python", "-c", "pass"]
    workflow["steps"][0]["adjudicated_provider"]["evaluator"]["input_file"] = "missing-evaluator.md"

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["adjudication"]["selected_candidate_id"] == "b"
    assert result["adjudication"]["candidates"]["a"]["candidate_status"] == "contract_failed"
    assert result["adjudication"]["candidates"]["a"]["score_status"] == "not_evaluated"
    assert result["adjudication"]["candidates"]["b"]["score_status"] == "scorer_unavailable"


def test_single_candidate_required_score_blocks_when_evaluator_provider_unavailable(tmp_path: Path) -> None:
    workflow = _workflow()
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["steps"][0]["adjudicated_provider"]["selection"]["require_score_for_single_candidate"] = True

    def unregister_evaluator(executor: WorkflowExecutor) -> None:
        executor.provider_registry._providers.pop("evaluator")

    state = _run(tmp_path, workflow, mutate_executor=unregister_evaluator)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "adjudication_scorer_unavailable"
    candidate_state = result["adjudication"]["candidates"]["a"]
    assert candidate_state["score_status"] == "scorer_unavailable"
    assert candidate_state["scorer_resolution_failure_key"].startswith("sha256:")
    paths = candidate_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1, "a")
    assert not paths.evaluation_packet_path.exists()


def test_single_candidate_required_score_blocks_when_evaluator_params_do_not_resolve(tmp_path: Path) -> None:
    workflow = _workflow()
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["steps"][0]["adjudicated_provider"]["selection"]["require_score_for_single_candidate"] = True
    workflow["steps"][0]["adjudicated_provider"]["evaluator"]["provider_params"] = {
        "model": "${context.missing_model}",
    }

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "adjudication_scorer_unavailable"
    candidate_state = result["adjudication"]["candidates"]["a"]
    assert candidate_state["score_status"] == "scorer_unavailable"
    assert candidate_state["failure_type"] == "evaluator_params_substitution_failed"
    paths = candidate_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1, "a")
    assert not paths.evaluation_packet_path.exists()


def test_unreadable_rubric_records_scorer_unavailable_without_packet(tmp_path: Path) -> None:
    (tmp_path / "rubric.md").mkdir()
    workflow = _workflow()
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["steps"][0]["adjudicated_provider"]["evaluator"]["rubric_input_file"] = "rubric.md"

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["adjudication"]["selected_candidate_id"] == "a"
    candidate_state = result["adjudication"]["candidates"]["a"]
    assert candidate_state["score_status"] == "scorer_unavailable"
    assert candidate_state["failure_type"] == "rubric_read_failed"
    assert candidate_state["scorer_resolution_failure_key"].startswith("sha256:")
    resolution_failure = tmp_path / ".orchestrate/runs/run-1/adjudication/root/root.draft/1/scorer/resolution_failure.json"
    assert resolution_failure.exists()
    paths = candidate_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1, "a")
    assert not paths.evaluation_packet_path.exists()


def test_single_candidate_required_score_blocks_on_evaluation_failure(tmp_path: Path) -> None:
    workflow = _workflow()
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        "print('not json')",
    ]
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["steps"][0]["adjudicated_provider"]["selection"]["require_score_for_single_candidate"] = True

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "adjudication_partial_scoring_failed"
    assert not (tmp_path / "state/result_path.txt").exists()
    assert "result_path" not in state.get("artifact_versions", {})


def test_invalid_candidate_is_not_evaluated_or_selected(tmp_path: Path) -> None:
    workflow = _workflow(scores={"b": 0.9})
    workflow["providers"]["candidate_a"]["command"] = ["python", "-c", "pass"]
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        (
            "import json, sys\n"
            "packet = json.loads(sys.stdin.read().split('Evaluator Packet:', 1)[1])\n"
            "if packet['candidate_id'] == 'a':\n"
            "    raise SystemExit(7)\n"
            "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': 0.9, 'summary': 'valid'}))\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["adjudication"]["selected_candidate_id"] == "b"
    assert result["adjudication"]["candidates"]["a"]["candidate_status"] == "contract_failed"
    assert result["adjudication"]["candidates"]["a"]["score_status"] == "not_evaluated"


def test_multi_candidate_partial_scoring_fails_without_promotion(tmp_path: Path) -> None:
    workflow = _workflow()
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        (
            "import json, sys\n"
            "packet = json.loads(sys.stdin.read().split('Evaluator Packet:', 1)[1])\n"
            "candidate_id = packet['candidate_id']\n"
            "print('not json' if candidate_id == 'b' else json.dumps({'candidate_id': candidate_id, 'score': 0.8, 'summary': 'ok'}))\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["exit_code"] == 2
    assert result["error"]["type"] == "adjudication_partial_scoring_failed"
    assert not (tmp_path / "docs/plans/b.md").exists()


def test_ledger_mirror_conflict_returns_normalized_step_failure(tmp_path: Path) -> None:
    attempt_file = tmp_path / "candidate_attempts.txt"
    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            {
                "row_schema": "adjudicated_provider.score.v1",
                "run_id": "other-run",
                "execution_frame_id": "root",
                "step_id": "root.draft",
                "visit_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({attempt_file.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('selected once', encoding='utf-8')\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["exit_code"] == 2
    assert result["error"]["type"] == "ledger_conflict"
    assert result["outcome"]["class"] == "ledger_conflict"
    assert attempt_file.read_text(encoding="utf-8") == "1"
    assert "result_path" not in state.get("artifact_versions", {})


def test_ledger_mirror_rejects_invalid_jsonl(tmp_path: Path) -> None:
    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("{not json}\n", encoding="utf-8")

    state = _run(tmp_path, _workflow())

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "ledger_conflict"
    assert "result_path" not in state.get("artifact_versions", {})


def test_two_adjudicated_steps_cannot_share_one_score_ledger_mirror(tmp_path: Path) -> None:
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    second_step = {
        **workflow["steps"][0],
        "name": "DraftAgain",
        "id": "draft_again",
    }
    workflow["steps"] = [workflow["steps"][0], second_step]

    state = _run(tmp_path, workflow)

    assert state["steps"]["Draft"]["status"] == "completed"
    result = state["steps"]["DraftAgain"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "ledger_conflict"
    assert state["artifact_versions"]["result_path"][-1]["producer"] == "root.draft"


def test_output_bundle_relpath_target_ledger_collision_fails_before_promotion(tmp_path: Path) -> None:
    attempt_file = tmp_path / "candidate_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["artifacts"] = {
        "doc": {
            "kind": "relpath",
            "type": "relpath",
            "pointer": "state/bundle.json",
            "under": "artifacts/evaluations",
            "must_exist_target": True,
        },
    }
    step = workflow["steps"][0]
    step["retries"] = {"max": 1, "delay_ms": 0}
    step["adjudicated_provider"]["candidates"] = [{"id": "a", "provider": "candidate_a"}]
    step["adjudicated_provider"]["score_ledger_path"] = "artifacts/evaluations/draft_scores.jsonl"
    step.pop("expected_outputs")
    step["output_bundle"] = {
        "path": "state/bundle.json",
        "fields": [
            {
                "name": "doc",
                "json_pointer": "/doc",
                "type": "relpath",
                "under": "artifacts/evaluations",
                "must_exist_target": True,
            }
        ],
    }
    step["publishes"] = [{"artifact": "doc", "from": "doc"}]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "import json\n"
            "from pathlib import Path\n"
            f"attempt_file = Path({attempt_file.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('artifacts/evaluations').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/bundle.json').write_text(json.dumps({'doc': 'artifacts/evaluations/draft_scores.jsonl'}), encoding='utf-8')\n"
            "Path('artifacts/evaluations/draft_scores.jsonl').write_text('selected artifact\\n', encoding='utf-8')\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "ledger_path_collision"
    assert attempt_file.read_text(encoding="utf-8") == "1"
    assert not (tmp_path / "state/bundle.json").exists()
    assert not (tmp_path / "artifacts/evaluations/draft_scores.jsonl").exists()
    assert "doc" not in state.get("artifact_versions", {})


def test_candidate_timeout_returns_logical_step_timeout(tmp_path: Path) -> None:
    workflow = _workflow()
    workflow["steps"][0]["timeout_sec"] = 0.1
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        "import time; time.sleep(1)",
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["exit_code"] == 124
    assert result["error"]["type"] == "timeout"
    assert result["outcome"]["class"] == "timeout"
    assert result["outcome"]["retryable"] is True
    assert result["adjudication"]["candidates"]["a"]["candidate_status"] == "timeout"


def test_candidate_exit_124_does_not_mask_later_valid_candidate_when_deadline_remains(tmp_path: Path) -> None:
    workflow = _workflow(scores={"b": 0.9})
    workflow["steps"][0]["timeout_sec"] = 60
    workflow["providers"]["candidate_a"]["command"] = ["python", "-c", "raise SystemExit(124)"]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["adjudication"]["selected_candidate_id"] == "b"
    candidate_a = result["adjudication"]["candidates"]["a"]
    assert candidate_a["candidate_status"] == "timeout"
    assert candidate_a["score_status"] == "not_evaluated"
    assert result["artifacts"]["result_path"] == "docs/plans/b.md"


def test_logical_deadline_remaining_budget_is_passed_to_candidate_and_evaluator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock = _FakeClock()
    _install_fake_clock(monkeypatch, fake_clock)
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 10
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    observed_timeouts: list[float | None] = []

    def mutate_executor(executor: WorkflowExecutor) -> None:
        original_prepare = executor.provider_executor.prepare_invocation
        original_execute = executor._execute_provider_invocation

        def prepare_with_timeout_capture(*args, **kwargs):
            observed_timeouts.append(kwargs.get("timeout_sec"))
            return original_prepare(*args, **kwargs)

        def execute_and_advance(invocation, **kwargs):
            result = original_execute(invocation, **kwargs)
            fake_clock.advance(2.0)
            return result

        executor.provider_executor.prepare_invocation = prepare_with_timeout_capture
        executor._execute_provider_invocation = execute_and_advance

    state = _run(tmp_path, workflow, mutate_executor=mutate_executor)

    assert state["steps"]["Draft"]["status"] == "completed"
    assert observed_timeouts[:2] == [10.0, 8.0]


def test_deadline_expiring_after_baseline_starts_no_candidate_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock = _FakeClock()
    _install_fake_clock(monkeypatch, fake_clock)
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 1
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    copy_calls = 0
    original_create_baseline = executor_module.create_baseline_snapshot
    original_prepare_workspace = executor_module.prepare_candidate_workspace_from_baseline

    def slow_baseline(**kwargs):
        result = original_create_baseline(**kwargs)
        fake_clock.advance(2.0)
        return result

    def count_candidate_copy(**kwargs):
        nonlocal copy_calls
        copy_calls += 1
        return original_prepare_workspace(**kwargs)

    monkeypatch.setattr(executor_module, "create_baseline_snapshot", slow_baseline)
    monkeypatch.setattr(executor_module, "prepare_candidate_workspace_from_baseline", count_candidate_copy)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "timeout"
    assert copy_calls == 0


def test_deadline_expiring_after_candidate_copy_starts_no_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock = _FakeClock()
    _install_fake_clock(monkeypatch, fake_clock)
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 1
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    provider_launches = 0
    original_prepare_workspace = executor_module.prepare_candidate_workspace_from_baseline

    def slow_candidate_copy(**kwargs):
        result = original_prepare_workspace(**kwargs)
        fake_clock.advance(2.0)
        return result

    def mutate_executor(executor: WorkflowExecutor) -> None:
        original_prepare = executor.provider_executor.prepare_invocation

        def count_provider_launch(*args, **kwargs):
            nonlocal provider_launches
            provider_launches += 1
            return original_prepare(*args, **kwargs)

        executor.provider_executor.prepare_invocation = count_provider_launch

    monkeypatch.setattr(executor_module, "prepare_candidate_workspace_from_baseline", slow_candidate_copy)

    state = _run(tmp_path, workflow, mutate_executor=mutate_executor)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "timeout"
    assert provider_launches == 0


def test_deadline_expiring_during_selection_starts_no_ledger_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock = _FakeClock()
    _install_fake_clock(monkeypatch, fake_clock)
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 1
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    ledger_calls = 0
    original_select = executor_module.select_candidate
    original_materialize = executor_module.materialize_run_score_ledger

    def slow_selection(*args, **kwargs):
        result = original_select(*args, **kwargs)
        fake_clock.advance(2.0)
        return result

    def count_ledger(*args, **kwargs):
        nonlocal ledger_calls
        ledger_calls += 1
        return original_materialize(*args, **kwargs)

    monkeypatch.setattr(executor_module, "select_candidate", slow_selection)
    monkeypatch.setattr(executor_module, "materialize_run_score_ledger", count_ledger)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "timeout"
    assert ledger_calls == 0


def test_deadline_expiring_during_pending_ledger_starts_no_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock = _FakeClock()
    _install_fake_clock(monkeypatch, fake_clock)
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 1
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    promotion_calls = 0
    original_materialize = executor_module.materialize_run_score_ledger
    original_promote = executor_module.promote_candidate_outputs

    def slow_ledger(*args, **kwargs):
        result = original_materialize(*args, **kwargs)
        fake_clock.advance(2.0)
        return result

    def count_promotion(**kwargs):
        nonlocal promotion_calls
        promotion_calls += 1
        return original_promote(**kwargs)

    monkeypatch.setattr(executor_module, "materialize_run_score_ledger", slow_ledger)
    monkeypatch.setattr(executor_module, "promote_candidate_outputs", count_promotion)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "timeout"
    assert promotion_calls == 0


def test_deadline_expiring_during_promotion_starts_no_terminal_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock = _FakeClock()
    _install_fake_clock(monkeypatch, fake_clock)
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 1
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    ledger_calls = 0
    original_promote = executor_module.promote_candidate_outputs
    original_materialize = executor_module.materialize_run_score_ledger

    def slow_promotion(**kwargs):
        result = original_promote(**kwargs)
        fake_clock.advance(2.0)
        return result

    def count_ledger(*args, **kwargs):
        nonlocal ledger_calls
        ledger_calls += 1
        return original_materialize(*args, **kwargs)

    monkeypatch.setattr(executor_module, "promote_candidate_outputs", slow_promotion)
    monkeypatch.setattr(executor_module, "materialize_run_score_ledger", count_ledger)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "timeout"
    assert ledger_calls == 1


def test_deadline_expiring_during_parent_validation_fails_before_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_clock = _FakeClock()
    _install_fake_clock(monkeypatch, fake_clock)
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 1
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    original_validate = executor_module.validate_expected_outputs

    def slow_parent_validation(expected_outputs, *, workspace):
        result = original_validate(expected_outputs, workspace=workspace)
        if Path(workspace).resolve() == tmp_path.resolve():
            fake_clock.advance(2.0)
        return result

    monkeypatch.setattr(executor_module, "validate_expected_outputs", slow_parent_validation)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "timeout"


def test_candidate_and_evaluator_stdout_stderr_are_sidecars_only(tmp_path: Path) -> None:
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "import sys\n"
            "from pathlib import Path\n"
            "print('candidate stdout sidecar')\n"
            "print('candidate stderr sidecar', file=sys.stderr)\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('selected', encoding='utf-8')\n"
        ),
    ]
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        (
            "import json, sys\n"
            "packet = json.loads(sys.stdin.read().split('Evaluator Packet:', 1)[1])\n"
            "print('evaluator stderr sidecar', file=sys.stderr)\n"
            "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': 0.9, 'summary': 'selected'}))\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert "output" not in result
    assert "lines" not in result
    assert "json" not in result
    assert "truncated" not in result
    assert "debug" not in result

    paths = candidate_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1, "a")
    assert paths.stdout_log.read_text(encoding="utf-8") == "candidate stdout sidecar\n"
    assert paths.stderr_log.read_text(encoding="utf-8") == "candidate stderr sidecar\n"
    assert "candidate_id" in paths.evaluation_output_path.read_text(encoding="utf-8")
    assert paths.evaluation_stderr_log.read_text(encoding="utf-8") == "evaluator stderr sidecar\n"


def test_candidate_retry_starts_from_fresh_baseline_and_records_attempt_count(tmp_path: Path) -> None:
    attempt_file = tmp_path / "candidate_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({attempt_file.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "if attempt == 1:\n"
            "    Path('partial.txt').write_text('stale failed attempt', encoding='utf-8')\n"
            "    raise SystemExit(1)\n"
            "if Path('partial.txt').exists():\n"
            "    raise SystemExit(8)\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('fresh success', encoding='utf-8')\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert attempt_file.read_text(encoding="utf-8") == "2"
    assert result["artifacts"]["result_path"] == "docs/plans/a.md"
    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["candidate_status"] == "output_valid"
    assert rows[0]["provider_exit_code"] == 0
    assert rows[0]["attempt_count"] == 2


def test_candidate_retry_does_not_restart_other_candidates_or_step_visit(tmp_path: Path) -> None:
    candidate_a_attempts = tmp_path / "candidate_a_attempts.txt"
    candidate_b_attempts = tmp_path / "candidate_b_attempts.txt"
    workflow = _workflow(scores={"a": 0.9, "b": 0.4})
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_a_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "if attempt == 1:\n"
            "    raise SystemExit(1)\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('retry winner', encoding='utf-8')\n"
        ),
    ]
    workflow["providers"]["candidate_b"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_b_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/b.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/b.md').write_text('other candidate once', encoding='utf-8')\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert candidate_a_attempts.read_text(encoding="utf-8") == "2"
    assert candidate_b_attempts.read_text(encoding="utf-8") == "1"
    assert state["step_visits"]["Draft"] == 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "artifacts/evaluations/draft_scores.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {row["candidate_id"]: row["attempt_count"] for row in rows} == {"a": 2, "b": 1}


def test_candidate_exit_124_can_retry_when_deadline_remains(tmp_path: Path) -> None:
    attempt_file = tmp_path / "candidate_timeout_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 60
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({attempt_file.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "if attempt == 1:\n"
            "    raise SystemExit(124)\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('retry success', encoding='utf-8')\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert attempt_file.read_text(encoding="utf-8") == "2"
    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["attempt_count"] == 2


def test_retry_delay_that_would_cross_logical_deadline_fails_timeout(tmp_path: Path) -> None:
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["timeout_sec"] = 0.1
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 1000}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = ["python", "-c", "raise SystemExit(1)"]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["exit_code"] == 124
    assert result["error"]["type"] == "timeout"
    assert result["adjudication"]["candidates"]["a"]["attempt_count"] == 1


def test_evaluator_retry_reuses_packet_without_rerunning_candidate(tmp_path: Path) -> None:
    candidate_attempt_file = tmp_path / "candidate_attempts.txt"
    evaluator_attempt_file = tmp_path / "evaluator_attempts.txt"
    packet_hash_file = tmp_path / "packet_hash.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_attempt_file.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('candidate once', encoding='utf-8')\n"
        ),
    ]
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        (
            "import json, sys\n"
            "from pathlib import Path\n"
            "packet = json.loads(sys.stdin.read().split('Evaluator Packet:', 1)[1])\n"
            f"attempt_file = Path({evaluator_attempt_file.as_posix()!r})\n"
            f"packet_hash_file = Path({packet_hash_file.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "packet_hash = packet['evaluation_packet_hash']\n"
            "if attempt == 1:\n"
            "    packet_hash_file.write_text(packet_hash, encoding='utf-8')\n"
            "    raise SystemExit(1)\n"
            "if packet_hash_file.read_text(encoding='utf-8') != packet_hash:\n"
            "    raise SystemExit(9)\n"
            "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': 0.9, 'summary': 'scored'}))\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert candidate_attempt_file.read_text(encoding="utf-8") == "1"
    assert evaluator_attempt_file.read_text(encoding="utf-8") == "2"
    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["score_status"] == "scored"
    assert rows[0]["attempt_count"] == 1


@pytest.mark.parametrize(
    ("candidate_ids", "require_score", "expected_status", "expected_error"),
    [
        (["a"], False, "completed", None),
        (["a"], True, "failed", "adjudication_partial_scoring_failed"),
        (["a", "b"], False, "failed", "adjudication_partial_scoring_failed"),
    ],
)
def test_exhausted_evaluator_retries_follow_selection_rules(
    tmp_path: Path,
    candidate_ids: list[str],
    require_score: bool,
    expected_status: str,
    expected_error: str | None,
) -> None:
    workflow = _workflow(scores={"a": 0.9, "b": 0.4})
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": candidate_id, "provider": f"candidate_{candidate_id}"}
        for candidate_id in candidate_ids
    ]
    if require_score:
        workflow["steps"][0]["adjudicated_provider"]["selection"]["require_score_for_single_candidate"] = True
    workflow["providers"]["evaluator"]["command"] = ["python", "-c", "raise SystemExit(1)"]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == expected_status
    if expected_error is None:
        assert result["adjudication"]["selected_candidate_id"] == "a"
        assert result["adjudication"]["selected_score"] is None
        assert result["adjudication"]["candidates"]["a"]["score_status"] == "evaluation_failed"
        assert result["adjudication"]["candidates"]["a"]["evaluator_attempt_count"] == 2
    else:
        assert result["error"]["type"] == expected_error
        for candidate_id in candidate_ids:
            candidate_state = result["adjudication"]["candidates"][candidate_id]
            assert candidate_state["score_status"] == "evaluation_failed"
            assert candidate_state["evaluator_attempt_count"] == 2
        assert "result_path" not in state.get("artifact_versions", {})


def test_run_local_ledger_records_pending_selection_before_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    run_ledger = adjudication_visit_paths(
        tmp_path / ".orchestrate/runs/run-1",
        "root",
        "root.draft",
        1,
    ).run_score_ledger_path

    def fail_after_pending_ledger(**_: object) -> object:
        rows = [json.loads(line) for line in run_ledger.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["selected"] is True
        assert rows[0]["promotion_status"] == "pending"
        assert rows[0]["promoted_paths"] == {}
        raise PromotionConflictError("stop after pending ledger")

    monkeypatch.setattr("orchestrator.workflow.executor.promote_candidate_outputs", fail_after_pending_ledger)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "promotion_conflict"


def test_promotion_conflict_is_not_retried_by_step_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_attempts = tmp_path / "candidate_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('selected once', encoding='utf-8')\n"
        ),
    ]

    def fail_promotion(**_: object) -> object:
        raise PromotionConflictError("terminal promotion conflict")

    monkeypatch.setattr("orchestrator.workflow.executor.promote_candidate_outputs", fail_promotion)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "promotion_conflict"
    assert candidate_attempts.read_text(encoding="utf-8") == "1"


def test_ledger_mirror_failure_is_not_retried_by_step_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_attempts = tmp_path / "candidate_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('selected once', encoding='utf-8')\n"
        ),
    ]

    def fail_mirror(*args, **kwargs) -> None:
        del args, kwargs
        raise OSError("mirror write failed")

    monkeypatch.setattr(executor_module, "materialize_score_ledger_mirror", fail_mirror)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "ledger_mirror_failed"
    assert candidate_attempts.read_text(encoding="utf-8") == "1"
    assert "result_path" not in state.get("artifact_versions", {})


@pytest.mark.parametrize("failure_type", ["promotion_validation_failed", "promotion_rollback_conflict"])
def test_promotion_terminal_failures_are_not_retried_by_step_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_type: str,
) -> None:
    candidate_attempts = tmp_path / "candidate_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["retries"] = {"max": 1, "delay_ms": 0}
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('selected once', encoding='utf-8')\n"
        ),
    ]

    def fail_promotion(**_: object) -> object:
        raise PromotionConflictError(f"terminal {failure_type}", failure_type=failure_type)

    monkeypatch.setattr(executor_module, "promote_candidate_outputs", fail_promotion)

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == failure_type
    assert candidate_attempts.read_text(encoding="utf-8") == "1"


def test_mirror_conflict_does_not_mask_no_valid_candidates_failure(tmp_path: Path) -> None:
    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            {
                "row_schema": "adjudicated_provider.score.v1",
                "run_id": "other-run",
                "execution_frame_id": "root",
                "step_id": "root.draft",
                "visit_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    workflow = _workflow()
    workflow["providers"]["candidate_a"]["command"] = ["python", "-c", "pass"]
    workflow["providers"]["candidate_b"]["command"] = ["python", "-c", "pass"]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "adjudication_no_valid_candidates"
    assert result["outcome"]["class"] == "adjudication_no_valid_candidates"
    assert "result_path" not in state.get("artifact_versions", {})


def test_scorer_snapshot_is_persisted_and_rubric_is_score_evidence(tmp_path: Path) -> None:
    (tmp_path / "rubric.md").write_text("Prefer complete and specific artifacts.", encoding="utf-8")
    workflow = _workflow()
    workflow["steps"][0]["adjudicated_provider"]["evaluator"]["rubric_input_file"] = "rubric.md"
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        (
            "import json, sys\n"
            "packet = json.loads(sys.stdin.read().split('Evaluator Packet:', 1)[1])\n"
            "assert any(item['name'] == 'rubric' and 'Prefer complete' in item['content'] for item in packet['evidence_items'])\n"
            "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': 0.7, 'summary': 'rubric scored'}))\n"
        ),
    ]

    state = _run(tmp_path, workflow)

    result = state["steps"]["Draft"]
    scorer_snapshot = tmp_path / result["adjudication"]["scorer_snapshot_path"]
    assert scorer_snapshot.exists()
    snapshot = json.loads(scorer_snapshot.read_text(encoding="utf-8"))
    assert snapshot["evaluator_prompt_content"] == "Return strict JSON."
    assert snapshot["rubric_content"] == "Prefer complete and specific artifacts."
    assert snapshot["rubric_hash"].startswith("sha256:")
    assert result["adjudication"]["candidates"]["a"]["score_status"] == "scored"


def test_adjudicated_provider_inside_call_frame_uses_frame_scoped_sidecars(tmp_path: Path) -> None:
    library = _workflow(scores={"a": 0.9, "b": 0.2})
    library["name"] = "adjudicated-child"
    library["inputs"] = {
        "write_root": {
            "type": "relpath",
        }
    }
    library["artifacts"] = {
        "result_path": {
            "kind": "relpath",
            "type": "relpath",
            "pointer": "${inputs.write_root}/result_path.txt",
            "under": "docs/plans",
            "must_exist_target": True,
        },
    }
    library["outputs"] = {
        "result_path": {
            "kind": "relpath",
            "type": "relpath",
            "from": {"ref": "root.steps.Draft.artifacts.result_path"},
        }
    }
    library["providers"]["candidate_a"]["command"] = _candidate_command("a", "weaker", "state/adjudicated-call")
    library["providers"]["candidate_b"]["command"] = _candidate_command("b", "better", "state/adjudicated-call")
    library["steps"][0]["expected_outputs"][0]["path"] = "${inputs.write_root}/result_path.txt"
    _write_yaml(tmp_path / "workflows/library/adjudicated_child.yaml", library)
    caller = {
        "version": "2.11",
        "name": "call-adjudicated",
        "imports": {"child": "workflows/library/adjudicated_child.yaml"},
        "steps": [
            {
                "name": "RunChild",
                "id": "run_child",
                "call": "child",
                "with": {
                    "write_root": "state/adjudicated-call",
                },
            }
        ],
    }
    (tmp_path / "prompt.md").write_text("Draft the best possible artifact.", encoding="utf-8")
    (tmp_path / "evaluator.md").write_text("Return strict JSON.", encoding="utf-8")
    workflow_file = _write_yaml(tmp_path / "workflow.yaml", caller)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="run-1")
    state_manager.initialize("workflow.yaml", bundle_context_dict(loaded))
    state = WorkflowExecutor(loaded, tmp_path, state_manager, retry_delay_ms=0).execute()

    frame_id, frame = next(iter(state["call_frames"].items()))
    child_result = frame["state"]["steps"]["Draft"]
    adjudication = child_result["adjudication"]
    ledger = tmp_path / adjudication["run_score_ledger_path"]
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]

    assert state["status"] == "completed"
    assert adjudication["execution_frame_id"] == frame_id
    assert adjudication["call_frame_id"] == frame_id
    assert "/adjudication/root/" not in adjudication["run_score_ledger_path"]
    assert "/call_frames/" not in adjudication["run_score_ledger_path"]
    assert {row["execution_frame_id"] for row in rows} == {frame_id}
    assert {row["call_frame_id"] for row in rows} == {frame_id}


def test_existing_adjudication_sidecars_fail_fast_without_rebaseline(tmp_path: Path) -> None:
    (tmp_path / "prompt.md").write_text("Draft the best possible artifact.", encoding="utf-8")
    (tmp_path / "evaluator.md").write_text("Return strict JSON.", encoding="utf-8")
    workflow_file = _write_yaml(tmp_path / "workflow.yaml", _workflow())
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="run-1")
    state_manager.initialize("workflow.yaml")

    run_root = tmp_path / ".orchestrate/runs/run-1"
    visit = adjudication_visit_paths(run_root, "root", "root.draft", 1)
    visit.baseline_workspace.mkdir(parents=True)
    stale_baseline = visit.baseline_workspace / "stale.txt"
    stale_baseline.write_text("original baseline sidecar", encoding="utf-8")
    stale_packet = candidate_paths(run_root, "root", "root.draft", 1, "a").evaluation_packet_path
    stale_packet.parent.mkdir(parents=True)
    stale_packet.write_text('{"packet": "stale"}', encoding="utf-8")

    state = WorkflowExecutor(loaded, tmp_path, state_manager, retry_delay_ms=0).execute()

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "adjudication_resume_mismatch"
    assert stale_baseline.read_text(encoding="utf-8") == "original baseline sidecar"
    assert stale_packet.read_text(encoding="utf-8") == '{"packet": "stale"}'
