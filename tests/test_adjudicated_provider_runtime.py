import json
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _candidate_command(label: str, body: str) -> list[str]:
    return [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            f"Path('state/result_path.txt').write_text('docs/plans/{label}.md\\n', encoding='utf-8')\n"
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


def _run(workspace: Path, workflow: dict) -> dict:
    (workspace / "prompt.md").write_text("Draft the best possible artifact.", encoding="utf-8")
    (workspace / "evaluator.md").write_text("Return strict JSON.", encoding="utf-8")
    workflow_file = _write_yaml(workspace / "workflow.yaml", workflow)
    loaded = WorkflowLoader(workspace).load(workflow_file)
    state_manager = StateManager(workspace=workspace, run_id="run-1")
    state_manager.initialize("workflow.yaml")
    return WorkflowExecutor(loaded, workspace, state_manager, retry_delay_ms=0).execute()


def test_adjudicated_provider_selects_highest_scored_candidate_and_publishes(tmp_path: Path) -> None:
    state = _run(tmp_path, _workflow())

    result = state["steps"]["Draft"]
    assert result["status"] == "completed"
    assert result["artifacts"]["result_path"] == "docs/plans/b.md"
    assert (tmp_path / "docs/plans/b.md").read_text(encoding="utf-8") == "better"
    assert result["adjudication"]["selected_candidate_id"] == "b"
    assert result["adjudication"]["selected_score"] == 0.9
    assert result["adjudication"]["promotion_status"] == "committed"
    assert "output" not in result
    assert "json" not in result
    ledger = tmp_path / "artifacts/evaluations/draft_scores.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert [row["candidate_id"] for row in rows] == ["a", "b"]
    assert [row["selected"] for row in rows] == [False, True]
    assert state["artifact_versions"]["result_path"][-1]["value"] == "docs/plans/b.md"


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
