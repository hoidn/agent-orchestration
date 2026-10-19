"""Mode 2 of the structural search driver: archive, parent and site selection, feedback, per-generation judging and
validation, with scripted providers, a scripted mutator and a scripted judge (no provider is called)."""

import json
import os
import random
import shutil
import subprocess
import sys
import threading
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import pytest

from experiments.compare.repos import sha256_file

from experiments.compare import pool as pooling, prepare
from experiments.orc_structural_search import judging
from experiments.orc_structural_search.adaptive import (
    feedback, incumbent, initial_archive, retain, run_mode2, select_parent, validate_finalists)
from experiments.orc_structural_search.config import load_config
from experiments.orc_structural_search.judging import judge_generation
from experiments.orc_structural_search.ledger import CallCapExceeded
from experiments.orc_structural_search.records import append_record, read_records
from experiments.orc_structural_search.scoring import read_pool
from experiments.orc_structural_search.scoring_phase2 import phase2_readout
from tests.experiments.compare_harness_support import skip_without_sandbox, write_memo
from tests.experiments.orc_structural_search_support import REPO, SEEDS, script, world  # noqa: F401 (world: fixture)

PHASE2 = REPO / "experiments" / "orc_structural_search" / "criteria" / "phase2.json"
CONFIG = {"mutable_files": ["direct.orc"], "mutable_definitions": ["run"], "condition": "topology-only",
          "interface": "I1", "entry_workflow": "direct::run", "source_root": ".", "providers_file": "providers.json",
          "command_boundaries_file": "commands.json", "episode_wall_clock_sec": 120, "criterion_sha256": None}
JUDGES = ["judge-a", "judge-b"]
UPSTREAM = "--- a/pkg/__init__.py\n+++ b/pkg/__init__.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n"
# The scripted mode 2 mutator: wraps the form at the I2 site (or, for I1, the mutable file's first provider call)
# in `(if true <form> <form>)` (the form's own type, a new skeleton) and appends a comment naming the episode, so
# every child is a distinct candidate; it copies its brief to briefs.txt beside itself.
MUTATOR = f"""#!{sys.executable} -I
import re, sys
from pathlib import Path
brief = Path("EPISODE.md").read_text()
with open(Path(sys.argv[0]).parent / "briefs.txt", "a") as out:
    out.write(brief)
index = int(re.match(r"# Episode (\\d+)", brief).group(1))
site = re.search(r"^Site: .*@(.+):(\\d+):(\\d+)$", brief, re.M)
name = site.group(1) if site else re.search(r"^Mutable scope: files ([^;,]+)", brief, re.M).group(1)
source = Path(name).read_text()
if site:
    start = sum(len(t) for t in source.splitlines(keepends=True)[:int(site.group(2)) - 1]) + int(site.group(3)) - 1
else:
    start = source.index("(provider-result")
depth = 0
for end in range(start, len(source)):  # the seeds' forms hold no parenthesis inside a string
    depth += {{"(": 1, ")": -1}}.get(source[end], 0)
    if depth == 0:
        break
form = source[start:end + 1]
Path(name).write_text(source[:start] + f"(if true {{form}} {{form}})" + source[end + 1:] + f";; episode {{index}}\\n")
"""


def entry(cid, mean_value, mean_calls, seed=None):
    return {"candidate_id": cid, "candidate_root": f"/e/candidates/{cid}", "seed": seed, "module": "direct",
            "values": {"t": [mean_value]}, "calls": [mean_calls], "mean_value": mean_value, "mean_calls": mean_calls,
            "evidence": "adaptive", "generation": 1}


def joined(policy, task, value, calls=1, mode="catalog", outcome="completed"):
    return {"evaluation_id": f"{policy}-{task}", "candidate_id": f"sha256:{policy}", "mode": mode, "policy": policy,
            "task": task, "replicate": 1, "outcome": outcome, "value": value, "hidden": 0.5, "calls": calls,
            "wall_clock_sec": 10.0}


def test_initial_archive_from_phase1_rows_names_the_best_seed_incumbent():
    rows = [joined("direct", "t1", 4), joined("direct", "t2", 6), joined("best_of_n", "t1", 7, calls=3),
            joined("best_of_n", "t2", 7, calls=3), joined("unguided:sha256:x", "t1", 8, mode="unguided")]
    entries = initial_archive(rows, {"direct": "/e/candidates/sha256:d", "best_of_n": "/e/candidates/sha256:b"},
                              tasks=["t1", "t2"])
    assert ([(e["candidate_id"], e["seed"], e["mean_value"], e["mean_calls"], e["evidence"]) for e in entries],
            incumbent(entries)["seed"]) == (
        [("sha256:b", "best_of_n", 7, 3, "phase1-prior"), ("sha256:d", "direct", 5, 1, "phase1-prior")], "best_of_n")


def test_archive_mean_value_counts_a_failed_evaluation_as_zero_and_leaves_out_an_incident():
    rows = [joined("direct", "t1", 4), joined("direct", "t1", None, outcome="failed"), joined("direct", "t2", 6),
            joined("direct", "t2", None, outcome="incident")]
    (entry,) = initial_archive(rows, {"direct": "/e/candidates/sha256:d"}, tasks=["t1", "t2"])
    assert entry["mean_value"] == 4  # t1 mean(4, 0) = 2, t2 6


def test_judge_generation_returns_a_tasks_failed_evaluations_without_a_pool(tmp_path):
    evidence = tmp_path / "e"
    evidence.mkdir()
    for eid, generation in (("f1", 1), ("f0", 0)):
        append_record(evidence / "log.jsonl", {
            "kind": "evaluation", "mode": "adaptive", "evaluation_id": eid, "candidate_id": "c", "task_id": "t1",
            "replicate": 1, "outcome": "failed", "split": "adaptive", "generation": generation,
            "records_dir": str(tmp_path / eid), "provider_calls": 2, "wall_clock_sec": 5.0})
    rows = judge_generation(evidence, 1, [tmp_path / "t1"], criterion=tmp_path / "c.json", judges=JUDGES,
                            solutions={}, call_cap=1, pool_root=tmp_path / "pools")
    assert [(r["evaluation_id"], r["outcome"], r["calls"]) for r in rows] == [("f1", "failed", 2)]


def test_initial_archive_refuses_rows_of_a_task_that_is_not_adaptive():
    rows = [joined("direct", "t1", 4), joined("direct", "t-validation", 6)]
    with pytest.raises(ValueError, match="t-validation"):
        initial_archive(rows, {"direct": "/e/candidates/sha256:d"}, tasks=["t1"])


def refused_mode2(tmp_path, *, adaptive=("t1",), validation="tv", criterion=("t1",), pools="pools", work="w"):
    """run_mode2 with nothing to run: only its argument checks can refuse it."""
    (tmp_path / "config.json").write_text(json.dumps(CONFIG))
    (tmp_path / "criterion.json").write_text(json.dumps({"adaptive_tasks": [f"tasks/{t}" for t in criterion],
                                                         "validation_task": "tasks/tv"}))
    run_mode2(tmp_path / "config.json", phase1_joined=tmp_path / "joined.json", seeds=[],
              adaptive_tasks=[tmp_path / t for t in adaptive], validation_task=tmp_path / validation, generations=0,
              episodes_per_generation=0, run_seed=1, work_root=tmp_path / work, evidence_root=tmp_path / "e",
              agent_cmd=[], runtime=tmp_path / "runtime", env={}, timeout_sec=1, solutions={}, call_cap=1,
              concurrency=1, criterion=tmp_path / "criterion.json", judges=JUDGES, pools_root=tmp_path / pools)


def test_mode2_refuses_a_validation_task_among_the_adaptive_tasks(tmp_path):
    with pytest.raises(ValueError, match="validation task tv is among the adaptive tasks"):
        refused_mode2(tmp_path, adaptive=("t1", "tv"))


def test_mode2_refuses_tasks_other_than_the_criterions(tmp_path):
    with pytest.raises(ValueError, match="not the criterion's"):
        refused_mode2(tmp_path, criterion=("t2",))


@pytest.mark.parametrize("pools, work", [("e/pools", "w"), ("w/episodes/pools", "w"), (".", "w"), ("p", "p/w")])
def test_mode2_refuses_a_pools_root_inside_the_evidence_or_work_root_or_holding_either(tmp_path, pools, work):
    with pytest.raises(ValueError, match="pools root"):
        refused_mode2(tmp_path, pools=pools, work=work)
    assert not (tmp_path / "e").exists()


def test_retain_keeps_incumbent_and_at_most_six_frontier_members():
    frontier = [entry(f"c{k}", float(k), float(k)) for k in range(8)]  # each trades value for calls: none dominated
    kept = retain(frontier, entry("c8", 8.0, 8.0))
    assert ([e["candidate_id"] for e in kept], incumbent(kept)["candidate_id"]) == (
        ["c8", "c7", "c6", "c5", "c4", "c3", "c2"], "c8")


def test_a_dominated_child_does_not_enter_the_archive():
    archive = [entry("a", 6.0, 2.0), entry("b", 4.0, 1.0)]
    assert [e["candidate_id"] for e in retain(archive, entry("c", 5.0, 3.0))] == ["a", "b"]


def test_select_parent_is_uniform_and_reproducible_for_a_seed():
    archive = [entry(c, 5.0, 1.0) for c in "abc"]
    draws = [select_parent(archive, rng)["candidate_id"] for rng in [random.Random(3)] for _ in range(3000)]
    again = [select_parent(archive, rng)["candidate_id"] for rng in [random.Random(3)] for _ in range(3000)]
    assert (draws == again, all(900 < n < 1100 for n in Counter(draws).values())) == (True, True)


def test_feedback_carries_the_parents_scores_and_run_facts_but_no_hidden_or_other_candidates():
    parent = entry("sha256:p", 6.0, 2.0) | {"values": {"t1": [5.0, 7.0]}}
    row = {"kind": "evaluation", "candidate_id": "sha256:p", "task_id": "t1", "outcome": "completed", "split": "adaptive",
           "value": {"variant": "DONE", "summary": "s"}, "provider_calls": 2, "wall_clock_sec": 30.5, "hidden": 0.9}
    others = [row | {"candidate_id": "sha256:other", "wall_clock_sec": 99.0},
              row | {"split": "validation", "task_id": "t-validation"}]
    assert feedback(parent, [row, *others]) == {
        "mean_value": {"t1": {"mean": 6.0, "n": 2}},
        "runs": [{"task": "t1", "outcome": "completed", "terminal": "DONE", "provider_calls": 2, "wall_clock_sec": 30.5}]}


def add_anchors(task):
    (task / "anchors").mkdir()
    (task / "anchors" / f"{task.name}-upstream.diff").write_text(UPSTREAM)
    (task / "anchors" / f"{task.name}-stub.diff").write_text("")


def scripted_judge(log, hit=None):
    """A judge that rates an `if`-wrapped candidate 6, any other evaluation 4, the upstream anchor 8 and the stub 0,
    as a completed scoring run under the judge's state directory (no provider call). With `hit` (text), a pool of
    generation 1 records one call for judge-a whose output is that text (a scan hit when it names the solution)."""
    def scorer(pool, judge, script="score"):
        mapping = json.loads((pool / "records" / "mapping.json").read_text())
        roots = {str(Path(r["records_dir"]).resolve()): r["candidate_root"]
                 for r in read_records(log) if r["kind"] == "evaluation"}
        def tokens(clone):
            if clone["arm"] == "anchor":
                return ("S2",) * 4 if clone["labels"][0].endswith("upstream") else ("S0",) * 4
            source = "".join(p.read_text() for p in Path(roots[clone["run"]]).glob("*.orc"))
            return ("S2", "S2", "S1", "S1") if "(if true" in source else ("S1",) * 4
        inputs = json.loads((pool / "records" / f"score-inputs-{judge}.json").read_text())
        value = [[dict(zip(("root_cause", "scope", "generality", "layering"), tokens(mapping["clones"][Path(p).name])),
                       clone=p, reason="r") for p in batch["clones"]] for batch in inputs["batches"]]
        state = pool / "judges" / mapping["judges"][judge]["dir"] / "state"
        (state / "r1").mkdir(parents=True, exist_ok=True)
        (state / "r1" / "run.json").write_text(json.dumps({"bound_inputs": inputs}))
        prompts = ["judge prompt"] if hit and judge == "judge-a" and pool.parent.name == "gen-1" else []
        for n, prompt in enumerate(prompts, 1):
            call = pool / "records" / "judges" / judge / "calls" / str(n)
            call.mkdir(parents=True)
            (call / "prompt.txt").write_text(prompt)
            (call / "stdout.txt").write_text(f"{hit}\n")
        write_memo({"state_root": state}, prompts, value)
    return scorer


@pytest.fixture
def m2(world):
    """The world with anchors, a validation task package, a Phase 2 criterion over them, Phase 1 prior rows for
    the direct seed, the configuration and the scripted mutator, providers and judge."""
    skip_without_sandbox()
    validation = world.tmp / "task-v"
    shutil.copytree(world.task, validation)
    for task in (world.task, validation):
        add_anchors(task)
    criterion = world.tmp / "criterion.json"
    criterion.write_text(json.dumps(json.loads(PHASE2.read_text()) | {
        "adaptive_tasks": [str(world.task)], "validation_task": str(validation), "judges": JUDGES,
        "anchors": {t.name: {"upstream": f"{t.name}-upstream", "stub": f"{t.name}-stub"} for t in (world.task, validation)}}))
    (world.tmp / "joined.json").write_text(json.dumps([joined("direct", world.task.name, 4.0)]))
    (world.tmp / "config.json").write_text(json.dumps(CONFIG | {"criterion_sha256": sha256_file(criterion)}))
    mutator = world.outside / "mutator.py"
    mutator.write_text(MUTATOR)
    script(world, [{"match": "Implement this change", "result": {"summary": "set VALUE", "account": "edited pkg"}}])
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}
    return world, {"validation": validation, "criterion": criterion, "mutator": mutator, "env": env}


def mode2(m2, tag="a", *, generations=1, episodes=4, run_seed=7, call_cap=200, scorer=None, mutator=None):
    """(readout, log rows, evidence root, launch) of one scripted mode 2 run."""
    world, m = m2
    evidence = world.outside / f"evidence-{tag}"
    result, launch = run_mode2(world.tmp / "config.json", phase1_joined=world.tmp / "joined.json", seeds=[SEEDS / "direct.orc"],
                       adaptive_tasks=[world.task], validation_task=m["validation"], generations=generations,
                       episodes_per_generation=episodes, run_seed=run_seed, work_root=world.outside / f"work-{tag}",
                       evidence_root=evidence, agent_cmd=[sys.executable, "-I", str(mutator or m["mutator"])],
                       runtime=world.runtime, env=m["env"], timeout_sec=600,
                       solutions={t: world.solution for t in (world.task.name, m["validation"].name)},
                       call_cap=call_cap, concurrency=4, criterion=m["criterion"], judges=JUDGES,
                       pools_root=world.outside / f"pools-{tag}",
                       scorer=scorer or scripted_judge(evidence / "log.jsonl"))
    return result, read_records(evidence / "log.jsonl"), evidence, launch


def kind(rows, name):
    return [row for row in rows if row["kind"] == name]


def test_generation_judges_each_task_once_with_both_anchors_and_updates_the_archive(m2):
    world, _ = m2
    _, rows, evidence, _ = mode2(m2)
    pools = [Path(row["pool"]) for row in kind(rows, "judging")]
    batches = [json.loads((p / "records" / "mapping.json").read_text()) for p in pools]
    anchors = [sorted(mapping["clones"][c]["labels"][0] for c in batch if mapping["clones"][c]["arm"] == "anchor")
               for mapping in batches for batch in mapping["batches"]]
    children = {row["candidate_id"] for row in kind(rows, "episode") if row["outcome"] == "accepted"}
    gen1 = json.loads((evidence / "archive" / "gen-1.json").read_text())
    assert ([(row["generation"], row["task"]) for row in kind(rows, "judging")], anchors,
            {e["candidate_id"] for e in gen1} == children, {e["mean_value"] for e in gen1},
            {p.parent.parent for p in pools}, (evidence / "pools").exists()) == (
        [(0, world.task.name), (1, world.task.name)], [[f"{world.task.name}-stub", f"{world.task.name}-upstream"]] * 2,
        True, {6.0}, {(world.outside / "pools-a").resolve()}, False)


def test_generation_splits_more_than_eight_children_into_anchored_batches(m2):
    _, rows, _, _ = mode2(m2, episodes=9)
    (gen1,) = [row for row in kind(rows, "judging") if row["generation"] == 1]
    mapping = json.loads((Path(gen1["pool"]) / "records" / "mapping.json").read_text())
    arms = [Counter(mapping["clones"][c]["arm"] == "anchor" for c in batch) for batch in mapping["batches"]]
    assert (len([r for r in kind(rows, "episode") if r["outcome"] == "accepted"]), sorted(a[False] for a in arms),
            [a[True] for a in arms], len(json.loads(Path(gen1["results"]).read_text())["runs"])) == (9, [4, 5], [2, 2], 9)


def test_judge_calls_enter_the_ledger_and_the_cap_refuses_a_generation_before_its_episodes(m2):
    world, _ = m2
    evidence = world.outside / "evidence-a"
    with pytest.raises(CallCapExceeded, match="generation 1's episodes"):
        mode2(m2, call_cap=3)  # generation 0: one evaluation and two judges; 4 episodes, children and judges exceed
    rows = read_records(evidence / "log.jsonl")
    ledger = json.loads((evidence / "calls.json").read_text())
    trajectory = json.loads((evidence / "readout.json").read_text())["trajectory"]
    assert ([(e["key"], e["planned"], e["calls"]) for e in ledger if e["kind"] == "judge"], kind(rows, "episode"),
            [r["generation"] for r in kind(rows, "evaluation")], (evidence / "archive" / "gen-1.json").exists(),
            [t["generation"] for t in trajectory]) == (
        [(f"gen 0 {world.task.name} {j}", 1, 0) for j in JUDGES], [], [0], False, [0])


def read_json(path):
    try:
        return json.loads(path.read_text())
    except ValueError:  # being written
        return {}


WAITING = "waiting for a scan verdict on "


class Waits:
    """sys.stdout passed through, keeping the scan file of every line announcing that the driver waits for it."""

    def __init__(self, out):
        self.out, self.paths = out, []

    def write(self, text):
        self.paths += [Path(line[len(WAITING):].split(": ")[0]) for line in text.splitlines()
                       if line.startswith(WAITING)]
        return self.out.write(text)

    def flush(self):
        self.out.flush()


@contextmanager
def adjudicator(waits, delay=0.3):
    """Records a `cleared` verdict on each scan the driver announces it waits for, `delay` seconds after."""
    stop, done = threading.Event(), set()

    def clear():
        while not stop.wait(delay):
            for path in [p for p in waits.paths if p not in done]:
                if path.name == "record.json":
                    prepare.adjudicate(path.parent, "cleared", "test")
                else:  # <pool>/records/judges/<judge>/scan.json
                    pooling.adjudicate_judge(path.parents[3], path.parent.name, "cleared", "test")
                done.add(path)

    thread = threading.Thread(target=clear, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


PROBE = """
import subprocess
subprocess.run(["claude", "-p"], input="holdout probe\\n- path: /dev/null\\n", text=True, check=True)
"""


def mode2_with_hits(m2, monkeypatch):
    """A mode 2 run (one generation, two episodes) whose evaluations' coder and episodes' mutator (through one claude
    call) print the validation task's path, and whose judge-a output in generation 1 names the solution; every scan
    is cleared by the test after the driver announces it waits for it. (readout, rows, evidence, launch, the scan
    files waited for, in order)."""
    world, m = m2
    monkeypatch.setattr(judging, "POLL_SEC", 0.05)
    script(world, [{"match": "Implement this change", "print": str(m["validation"]),
                    "result": {"summary": "set VALUE", "account": "edited pkg"}},
                   {"match": "holdout probe", "print": str(m["validation"]), "result": {}}])
    probe = world.outside / "probe.py"
    probe.write_text(MUTATOR + PROBE)
    log, waits = world.outside / "evidence-a" / "log.jsonl", Waits(sys.stdout)
    monkeypatch.setattr(sys, "stdout", waits)
    with adjudicator(waits):
        return (*mode2(m2, episodes=2, scorer=scripted_judge(log, hit=world.solution), mutator=probe), waits.paths)


def test_mode2_waits_for_verdicts_on_run_and_judge_scan_hits_then_continues(m2, monkeypatch):
    _, rows, evidence, _, waits = mode2_with_hits(m2, monkeypatch)
    runs = {Path(r["records_dir"]) / "record.json" for r in kind(rows, "evaluation")}
    (judged,) = [Path(r["pool"]) for r in kind(rows, "judging") if r["generation"] == 1]
    assert (len(waits) == len(set(waits)), set(waits) == runs | {judged / "records/judges/judge-a/scan.json"},
            [r["generation"] for r in kind(rows, "judging")], (evidence / "archive" / "gen-1.json").exists()) == (
        True, True, [0, 1], True)


def test_the_validation_task_is_a_holdout_root_of_episode_and_adaptive_evaluation_scans(m2, monkeypatch):
    _, rows, evidence, _, _ = mode2_with_hits(m2, monkeypatch)
    def patterns(record):
        return {hit["pattern"] for hit in read_json(record)["scan"]["hits"]}
    episodes = [patterns(evidence / "episodes" / r["episode_id"] / "record.json") for r in kind(rows, "episode")]
    evaluations = [patterns(Path(r["records_dir"]) / "record.json") for r in kind(rows, "evaluation")]
    assert (len(episodes), len(evaluations) > 1, all("holdout" in p for p in episodes + evaluations)) == (2, True, True)


def test_a_judge_that_fails_twice_is_a_judge_incident_and_the_loop_continues(m2):
    world, _ = m2
    judged, attempts = scripted_judge(world.outside / "evidence-a" / "log.jsonl"), []

    def failing(pool, judge, script="score"):
        attempts.append((pool.parent.name, judge, script))
        if (pool.parent.name, judge) == ("gen-1", "judge-a"):
            raise subprocess.CalledProcessError(1, f"{script}-{judge}.sh")
        judged(pool, judge, script)

    _, rows, evidence, _ = mode2(m2, generations=2, episodes=2, scorer=failing)
    ledger = json.loads((evidence / "calls.json").read_text())
    assert ([r["generation"] for r in kind(rows, "judge_incident")], [a for a in attempts if a[0] == "gen-1"],
            sorted(p.name for p in (evidence / "archive").glob("gen-*.json")),
            [e["key"] for e in ledger if e["calls"] is None]) == (
        [1], [("gen-1", "judge-a", "score"), ("gen-1", "judge-a", "resume")], ["gen-0.json", "gen-2.json"], [])


def test_mode2_interleaves_i1_and_i2_and_reports_per_interface_figures(m2):
    result, rows, _, _ = mode2(m2)
    assert ([row["interface"] for row in kind(rows, "episode")], [row["site_id"] is None for row in kind(rows, "episode")],
            {name: (r["episodes"], r["distinct_skeletons"]) for name, r in result["interfaces"].items()}) == (
        ["I1", "I2", "I1", "I2"], [True, False, True, False], {"I1": ({"accepted": 2}, 1), "I2": ({"accepted": 2}, 2)})


def test_mode2_is_reproducible_for_a_run_seed(m2):
    draws = []
    for tag in ("a", "b"):
        _, rows, _, _ = mode2(m2, tag, generations=2, episodes=2, run_seed=11)
        draws.append([(r["generation"], r["parent_candidate_id"], r["site_id"]) for r in kind(rows, "episode")])
    assert (draws[0] == draws[1], len({d[1] for d in draws[0]}) > 1) == (True, True)


def test_validation_task_never_reaches_an_episode_or_adaptive_evaluation(m2):
    world, m = m2
    _, rows, _, _ = mode2(m2)
    briefs = (m["mutator"].parent / "briefs.txt").read_text()
    assert ([r for r in rows if r.get("task_id") == m["validation"].name and r.get("split") != "validation"],
            str(m["validation"]) in briefs, m["validation"].name in briefs,
            {r["split"] for r in kind(rows, "evaluation")}, briefs.count("# Episode")) == ([], False, False, {"adaptive"}, 4)


def test_validate_finalists_replicates_the_reference_and_direct_beside_the_finalists(m2):
    world, m = m2
    _, _, evidence, launch = mode2(m2)
    judge = {"criterion": m["criterion"], "judges": JUDGES, "scorer": scripted_judge(evidence / "log.jsonl")}
    config, gen1 = load_config(world.tmp / "config.json"), evidence / "archive" / "gen-1.json"
    with pytest.raises(ValueError, match="pools root"):
        validate_finalists(gen1, config=config, validation_task=m["validation"], judge=judge,
                           launch=launch | {"pools_root": evidence / "pools"})
    rows = validate_finalists(gen1, config=config, validation_task=m["validation"], launch=launch, judge=judge)
    log = read_records(evidence / "log.jsonl")
    (validation,) = [r for r in kind(log, "judging") if r["task"] == m["validation"].name]
    readout = phase2_readout([evidence / "log.jsonl"], [evidence / "archive"],
                             read_pool(Path(validation["results"]), evidence / "log.jsonl", m["criterion"]),
                             m["criterion"])
    direct = next(r["candidate_id"] for r in kind(log, "reference"))
    assert (sorted(Counter(r["candidate_id"] for r in rows).values()), direct in {r["candidate_id"] for r in rows},
            {r["split"] for r in kind(log, "evaluation") if r["task_id"] == m["validation"].name},
            readout["rule"], readout["final_choice"] != direct) == ([2, 2, 2], True, {"validation"}, "chosen", True)
