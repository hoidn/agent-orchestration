"""Comparison scoring workflows with a scripted judge on the evaluated route.

The judge is the consumer shim installed as `claude` (`claude_unrestricted_workspace`): it answers one
`List[Rating]` per batch from its plan and logs each request. Public compile, a run stopped after a batch's
commit, CLI resume to completion and a completed resume that changes nothing; an out-of-range `Score`
token fails the effect before anything after it runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

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

SCORE_ABSOLUTE = Program("experiments/compare/score_absolute.orc", "score_absolute::score", "experiments/compare",
                         {"providers": "experiments/compare/score.providers.json"})


@pytest.fixture(params=[SCORE, SCORE_REF, SCORE_ABSOLUTE], ids=["historical", "reference", "absolute"])
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


def _ratings(program: Program, batch: dict, *scores: str) -> list[dict]:
    """One deterministic `Rating` per clone of `batch`, in its order; `scores` cycle over the criteria."""
    rows = [{"clone": clone, "root_cause": scores[index % len(scores)], "scope": "S2",
             "generality": scores[(index + 1) % len(scores)], "layering": "S1", "reason": f"reason {index}"}
            for index, clone in enumerate(batch["clones"])]
    if program != SCORE:
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
    answers = [_ratings(program, inputs["batches"][0], "S0", "S1", "S2"), _ratings(program, inputs["batches"][1], "S2")]
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
    if program == SCORE_ABSOLUTE:
        assert all(set(batch) == {"clones"} for batch in run_header["bound_inputs"]["batches"])
    assert_request_lineage(route)


def test_out_of_range_score_fails_the_effect(tmp_path, monkeypatch, program):
    inputs = _inputs(tmp_path, program, ("k7q2", "m3x9"), ("r8n1",))
    bad = _ratings(program, inputs["batches"][0], "S2")
    bad[1]["scope"] = "S3"
    install_shims(tmp_path / "bin", monkeypatch, _plan(inputs, bad, _ratings(program, inputs["batches"][1], "S2")))
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


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def _patch(repo: Path, body: str) -> str:
    source = repo / "pkg/calc.py"
    source.write_text(f"def add(a, b):\n{body}\n", encoding="utf-8")
    patch = _git(repo, "diff", "--binary", "--", "pkg/calc.py")
    _git(repo, "checkout", "--", "pkg/calc.py")
    return patch + "\n"


def _new_file_patch(name: str) -> str:
    return (f"diff --git a/pkg/{name}.py b/pkg/{name}.py\nnew file mode 100644\n"
            f"--- /dev/null\n+++ b/pkg/{name}.py\n@@ -0,0 +1 @@\n+VALUE = 1\n")


def _local_rating_provider(fakebin: Path) -> Path:
    fakebin.mkdir(parents=True)
    codex = fakebin / "codex"
    codex.write_text(f"#!{sys.executable}\n" + '''
import json, os, re, sys
from pathlib import Path
prompt = sys.stdin.read()
plan = json.loads(Path(os.environ["COMPARE_TEST_PLAN"]).read_text())
repos = sorted((path for path in plan["ratings"] if path in prompt), key=prompt.index)
match = re.search(r"(?m)^- path: ([^\\n]+)$", prompt)
if not repos or match is None:
    raise SystemExit("unrecognized scripted score request")
result = Path(match.group(1))
result.parent.mkdir(parents=True, exist_ok=True)
result.write_text(json.dumps([plan["ratings"][path] for path in repos]), encoding="utf-8")
with Path(os.environ["COMPARE_TEST_CALLS"]).open("a", encoding="utf-8") as output:
    output.write(json.dumps({"argv": sys.argv[1:], "repos": repos}) + chr(10))
''', encoding="utf-8")
    codex.chmod(0o755)
    return codex


def test_control_means_runs_through_prepare_orchestrator_summary_and_c1(tmp_path, monkeypatch):
    """Three declared controls survive the public offline score path into C1's raw-rating join."""
    from experiments.orc_structural_search.qualification_io import package_digest
    from experiments.orc_structural_search.qualification_measure_v2 import pool_observation
    from tests.experiments.compare_harness_support import OUTSIDE_SANDBOX_MOUNTS, skip_without_sandbox
    from tests.experiments.qualification_support import qualified_v2, ref
    from tests.test_workflow_evaluated_invalidate import _cli

    skip_without_sandbox()
    controls = {"rule": "control-means-v1", "margin": 1, "error_rate": 0}
    evidence = tmp_path / "evidence"
    runtime = tmp_path / "runtime"
    task = evidence / "tasks" / "adaptive"
    (runtime / "pkg").mkdir(parents=True)
    (runtime / "pkg/calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    _git(runtime, "init", "-q")
    _git(runtime, "add", "pkg/calc.py")
    subprocess.run(["git", "-C", str(runtime), "-c", "user.name=fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "-qm", "toy base"], check=True)
    base = _git(runtime, "rev-parse", "HEAD")
    (task / "anchors").mkdir(parents=True)
    (task / "seed").mkdir()
    (task / "task.txt").write_text("Make add return the sum.\n", encoding="utf-8")
    (task / "intent.txt").write_text("add returns a + b for every pair of numbers.\n", encoding="utf-8")
    (task / "base_commit").write_text(base + "\n", encoding="utf-8")
    for role, body in (
        ("upstream", "    return a + b"),
        ("stub", "    if (a, b) == (2, 3):\n        return 5\n    return a - b"),
        ("mutant", "    return a + b + 1"),
        ("partial", "    return a + b if a == b else a - b"),
    ):
        (task / "anchors" / f"adaptive-{role}.diff").write_text(_patch(runtime, body), encoding="utf-8")

    q = qualified_v2(evidence, runtime=runtime, tasks=[task], calibration=controls)
    judge = q.judges[0]
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    outside = Path(tempfile.mkdtemp(dir=OUTSIDE_SANDBOX_MOUNTS))
    try:
        pool = outside / "pool"
        fillers = [outside / "filler-1.diff", outside / "filler-2.diff"]
        for index, path in enumerate(fillers, 1):
            path.write_text(_new_file_patch(f"filler{index}"), encoding="utf-8")
        prepared = subprocess.run(
            [sys.executable, str(Path(__file__).parents[1] / "experiments/compare/prepare.py"), "calibrate",
             "--task", str(task), "--criterion", str(q.calibration), "--out", str(pool),
             "--runtime", str(runtime), "--judge", f"{judge}={q.bindings}",
             "--filler", str(fillers[0]), "--filler", str(fillers[1]),
             "--batches", "2", "--per-batch", "1", "--min-per-batch", "1", "--filler-seed", "1"],
            cwd=Path(__file__).parents[1], capture_output=True, text=True)
        assert prepared.returncode == 0, prepared.stderr
        mapping = json.loads((pool / "records/mapping.json").read_text(encoding="utf-8"))
        assert len(mapping["batches"]) == 2
        roles = json.loads(q.calibration.read_text(encoding="utf-8"))["anchors"][task.name]
        assert set(roles) == {"upstream", "stub", "mutant"}
        assert all({mapping["clones"][cid]["labels"][0] for cid in batch
                    if mapping["clones"][cid]["arm"] == "anchor"} == set(roles.values())
                   for batch in mapping["batches"])
        assert all("adaptive-partial" not in mapping["clones"][cid]["labels"]
                   for batch in mapping["batches"] for cid in batch)

        role_for_label = {label: role for role, label in roles.items()}
        total_by_role = ({"upstream": (4, 8), "stub": (4, 2), "mutant": (2, 4)})
        rating_by_path = {}
        for batch_index, batch in enumerate(mapping["batches"]):
            for cid in batch:
                clone = mapping["clones"][cid]
                label = clone["labels"][0]
                total = total_by_role[role_for_label[label]][batch_index] if clone["arm"] == "anchor" else 4
                scores = ["S2"] * (total // 2) + ["S1"] * (total % 2) + ["S0"] * (4 - (total + 1) // 2)
                rating_by_path[str(pool / "clones" / cid)] = {
                    "clone": str(pool / "clones" / cid), "completeness": scores[0], "correctness": scores[1],
                    "scope": scores[2], "layering": scores[3], "reason": "scripted fixture rating"}
        plan, calls = pool / "records/local-rating-plan.json", pool / "records/local-provider-calls.jsonl"
        (pool / "records").mkdir(exist_ok=True)
        plan.write_text(json.dumps({"ratings": rating_by_path}), encoding="utf-8")
        fakebin = outside / "fakebin"
        _local_rating_provider(fakebin)

        judge_home = pool / "judges" / mapping["judges"][judge]["dir"]
        inputs = json.loads((pool / f"records/score-inputs-{judge}.json").read_text(encoding="utf-8"))
        (judge_home / "inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
        monkeypatch.setenv("PATH", f"{Path(__file__).parents[1] / 'experiments/compare/shim'}:{fakebin}:{os.environ['PATH']}")
        monkeypatch.setenv("COMPARE_TEST_PLAN", str(plan))
        monkeypatch.setenv("COMPARE_TEST_CALLS", str(calls))
        monkeypatch.setenv("COMPARE_ROOT", str(pool / "records/judges" / judge))
        monkeypatch.setenv("COMPARE_TREE", str(judge_home))
        monkeypatch.setenv("COMPARE_BASE", mapping["compare_base"])
        source = runtime / "experiments/compare/score_absolute.orc"
        provider_args = ["--entry-workflow", "score_absolute::score", "--source-root",
                         str(runtime / "experiments/compare"), "--provider-externs-file",
                         str(q.bindings)]
        compiled = _cli(judge_home, "compile", str(source), *provider_args)
        assert compiled.returncode == 0, compiled.stderr
        scored = _cli(judge_home, "run", str(source), *provider_args, "--input-file", "inputs.json",
                      "--state-dir", str(judge_home / "state"))
        assert scored.returncode == 0, scored.stderr
        assert len(calls.read_text(encoding="utf-8").splitlines()) == 2
        assert len(list((pool / "records/judges" / judge / "calls").glob("*"))) == 2

        state = judge_home / "state"
        run_root = next(path for path in state.iterdir() if path.is_dir())
        terminal = json.loads((run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines()[-1])["value"]
        assert len(terminal) == len(mapping["batches"]) and all(
            row[component] in {"S0", "S1", "S2"}
            for batch in terminal for row in batch
            for component in ("completeness", "correctness", "scope", "layering"))
        scanned = subprocess.run(
            [sys.executable, str(Path(__file__).parents[1] / "experiments/compare/prepare.py"), "scan",
             "--pool", str(pool), "--judge", judge, "--hash", mapping["compare_base"]],
            cwd=Path(__file__).parents[1], capture_output=True, text=True)
        assert scanned.returncode == 0, scanned.stderr
        summarized = subprocess.run(
            [sys.executable, str(Path(__file__).parents[1] / "experiments/compare/summarize.py"),
             "--pool", str(pool), "--criterion", str(q.calibration)],
            cwd=Path(__file__).parents[1], capture_output=True, text=True)
        assert summarized.returncode == 0, summarized.stderr
        results = json.loads((pool / "records/results.json").read_text(encoding="utf-8"))
        assert results["calibration"]["passed"] is True
        entry = {"task_id": task.name, "stage": "A_prime", "criterion": ref(q.calibration),
                 "mapping": ref(pool / "records/mapping.json"), "results": ref(pool / "records/results.json"),
                 "patches": {cid: ref(pool / "records/patches" / f"{cid}.diff") for cid in mapping["clones"]}}
        study = json.loads(q.criterion.read_text(encoding="utf-8"))
        observation = pool_observation(entry, q.receipt.parent, study, q.criterion,
                                       {task.name: task}, {task.name: package_digest(task)})
        assert observation[1]["passed"] is True
        assert observation[2] == results["anchors"]
    finally:
        clones = outside / "pool/clones"
        if clones.exists():
            clones.chmod(0o755)
        shutil.rmtree(outside)
