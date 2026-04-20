import json
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from tests.workflow_bundle_helpers import bundle_context_dict


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


def test_ledger_mirror_conflict_returns_normalized_step_failure(tmp_path: Path) -> None:
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

    state = _run(tmp_path, _workflow())

    result = state["steps"]["Draft"]
    assert result["status"] == "failed"
    assert result["exit_code"] == 2
    assert result["error"]["type"] == "ledger_conflict"
    assert result["outcome"]["class"] == "ledger_conflict"
    assert "result_path" not in state.get("artifact_versions", {})


def test_output_bundle_relpath_target_ledger_collision_fails_before_promotion(tmp_path: Path) -> None:
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
