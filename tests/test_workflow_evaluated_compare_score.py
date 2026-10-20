"""`experiments/compare/score.orc` with a scripted judge on the evaluated route.

The judge is the consumer shim installed as `claude` (`claude_unrestricted_workspace`): it answers one
`List[Rating]` per batch from its plan and logs each request. Public compile, a run stopped after a batch's
commit, CLI resume to completion and a completed resume that changes nothing; an out-of-range `Score`
token fails the effect before anything after it runs.
"""

from __future__ import annotations

import json

import pytest

from tests.test_workflow_evaluated_invalidate import _cli
from tests.workflow_evaluated_consumer_sources import (
    Program, assert_request_lineage, current_route, install, install_shims, requests,
)
from tests.workflow_evaluated_totality_helpers import checked_run


SCORE = Program("experiments/compare/score.orc", "score::score", "experiments/compare",
                {"providers": "experiments/compare/score.providers.json"})
SCORE_REF = Program("experiments/compare/score_ref.orc", "score_ref::score", "experiments/compare",
                    {"providers": "experiments/compare/score.providers.json"})


@pytest.fixture(params=[SCORE, SCORE_REF], ids=["historical", "reference"])
def program(request):
    return request.param


JUDGE = "claude-opus-5-5"
CRITERION = "sha256:" + "c" * 64


def _inputs(tmp_path, program, *batches: tuple[str, ...]) -> dict:
    """Score inputs as `prepare.py pool` writes them: absolute clone paths per batch."""
    return {"batches": [{"clones": [str(tmp_path / "pool" / clone) for clone in batch],
                         **({"reference": str(tmp_path / "pool" / "ref1")} if program == SCORE_REF else {})}
                        for batch in batches],
            "intent": "add returns a + b for every pair of numbers", "criterion_sha256": CRITERION,
            "judge_model": JUDGE}


def _ratings(batch: dict, *scores: str) -> list[dict]:
    """One deterministic `Rating` per clone of `batch`, in its order; `scores` cycle over the criteria."""
    rows = [{"clone": clone, "root_cause": scores[index % len(scores)], "scope": "S2",
             "generality": scores[(index + 1) % len(scores)], "layering": "S1", "reason": f"reason {index}"}
            for index, clone in enumerate(batch["clones"])]
    if "reference" in batch:
        for row in rows:
            row["completeness"] = row.pop("root_cause")
            row["correctness"] = row.pop("generality")
    return rows


def _plan(inputs: dict, *answers: list[dict]) -> dict:
    return {"repos": [clone for batch in inputs["batches"] for clone in batch["clones"]],
            "claude": [{"result": answer} for answer in answers]}


@pytest.mark.parametrize("marker,paused", [("loop:#1[1]", 1), ("loop:#1[2]", 2)],
                         ids=["after-first-batch", "after-second-batch"])
def test_score_returns_one_rating_per_clone_per_batch_in_order(tmp_path, monkeypatch, marker, paused, program):
    inputs = _inputs(tmp_path, program, ("k7q2", "m3x9", "p0d4"), ("r8n1", "t5w6"))
    answers = [_ratings(inputs["batches"][0], "S0", "S1", "S2"), _ratings(inputs["batches"][1], "S2")]
    install_shims(tmp_path / "bin", monkeypatch, _plan(inputs, *answers))
    root = tmp_path / "workspace"

    route = current_route(root, install(root, program, inputs), marker)

    run_header = json.loads((route.authority.run_root / "run.json").read_text(encoding="utf-8"))
    assert route.value == answers  # memo terminal value: Score tokens are the JSON strings "S0", "S1", "S2"
    assert [(request["tool"], request["repos"]) for request in route.requests] == [
        ("claude", batch["clones"]) for batch in inputs["batches"]]
    assert all(inputs["intent"] in request["prompt"] for request in route.requests)
    assert {tuple(request["argv"]) for request in route.requests} == {
        ("-p", "--model", JUDGE, "--effort", "high", "--permission-mode", "bypassPermissions")}
    assert run_header["bound_inputs"]["criterion_sha256"] == CRITERION
    assert (len(route.paused), set(route.started().values())) == (paused, {1})
    if program == SCORE_REF:
        reference = inputs["batches"][0]["reference"]
        assert all(reference not in request["repos"] and reference in request["prompt"] for request in route.requests)
        assert all(row["clone"] != reference for batch in route.value for row in batch)
    assert_request_lineage(route)


def test_out_of_range_score_fails_the_effect(tmp_path, monkeypatch, program):
    inputs = _inputs(tmp_path, program, ("k7q2", "m3x9"), ("r8n1",))
    bad = _ratings(inputs["batches"][0], "S2")
    bad[1]["scope"] = "S3"
    install_shims(tmp_path / "bin", monkeypatch, _plan(inputs, bad, _ratings(inputs["batches"][1], "S2")))
    root = tmp_path / "workspace"
    frontend = install(root, program, inputs)

    ran = _cli(root, "run", *frontend, "--input-file", "inputs.json")

    _, snapshot = checked_run(root)
    failed = [entry.data for entry in snapshot.entries if entry.data["record"] == "failed"]
    assert (ran.returncode != 0, len(requests(root)), snapshot.active_commits) == (True, 1, {})
    assert (snapshot.terminal.data["outcome"], snapshot.terminal.data["code"]) == ("failed", "provider_result_invalid")
    assert [(violation["type"], violation["context"]["error"].split()[0])
            for record in failed for violation in record["violations"]] == [
        ("invalid_transportable_value", "$/1/scope")]
