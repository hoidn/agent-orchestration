"""Mode 2 of the structural search driver: archive, parent and site selection, feedback, per-generation judging and
validation, with scripted providers, a scripted mutator and a scripted judge (no provider is called)."""

import json
import os
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest

from experiments.orc_structural_search.adaptive import (
    feedback, incumbent, initial_archive, retain, run_mode2, select_parent, validate_finalists)
from experiments.orc_structural_search.config import load_config
from experiments.orc_structural_search.ledger import CallCapExceeded
from experiments.orc_structural_search.records import read_records
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


def joined(policy, task, value, calls=1, mode="catalog"):
    return {"evaluation_id": f"{policy}-{task}", "candidate_id": f"sha256:{policy}", "mode": mode, "policy": policy,
            "task": task, "replicate": 1, "value": value, "hidden": 0.5, "calls": calls, "wall_clock_sec": 10.0}


def test_initial_archive_from_phase1_rows_names_the_best_seed_incumbent():
    rows = [joined("direct", "t1", 4), joined("direct", "t2", 6), joined("best_of_n", "t1", 7, calls=3),
            joined("best_of_n", "t2", 7, calls=3), joined("unguided:sha256:x", "t1", 8, mode="unguided")]
    entries = initial_archive(rows, {"direct": "/e/candidates/sha256:d", "best_of_n": "/e/candidates/sha256:b"})
    assert ([(e["candidate_id"], e["seed"], e["mean_value"], e["mean_calls"], e["evidence"]) for e in entries],
            incumbent(entries)["seed"]) == (
        [("sha256:b", "best_of_n", 7, 3, "phase1-prior"), ("sha256:d", "direct", 5, 1, "phase1-prior")], "best_of_n")


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


def scripted_judge(log):
    """A judge that rates an `if`-wrapped candidate 6, any other evaluation 4, the upstream anchor 8 and the stub 0,
    as a completed scoring run under the judge's state directory (no provider call)."""
    def scorer(pool, judge):
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
        (state / "r1").mkdir(parents=True)
        (state / "r1" / "run.json").write_text(json.dumps({"bound_inputs": inputs}))
        write_memo({"state_root": state}, [], value)
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
    (world.tmp / "config.json").write_text(json.dumps(CONFIG))
    mutator = world.outside / "mutator.py"
    mutator.write_text(MUTATOR)
    script(world, [{"match": "Implement this change", "result": {"summary": "set VALUE", "account": "edited pkg"}}])
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}
    return world, {"validation": validation, "criterion": criterion, "mutator": mutator, "env": env}


def mode2(m2, tag="a", *, generations=1, episodes=4, run_seed=7, call_cap=200):
    world, m = m2
    evidence = world.outside / f"evidence-{tag}"
    result = run_mode2(world.tmp / "config.json", phase1_joined=world.tmp / "joined.json", seeds=[SEEDS / "direct.orc"],
                       adaptive_tasks=[world.task], validation_task=m["validation"], generations=generations,
                       episodes_per_generation=episodes, run_seed=run_seed, work_root=world.outside / f"work-{tag}",
                       evidence_root=evidence, agent_cmd=[sys.executable, "-I", str(m["mutator"])],
                       runtime=world.runtime, env=m["env"], timeout_sec=600,
                       solutions={t: world.solution for t in (world.task.name, m["validation"].name)},
                       call_cap=call_cap, concurrency=4, criterion=m["criterion"], judges=JUDGES,
                       scorer=scripted_judge(evidence / "log.jsonl"))
    return result, read_records(evidence / "log.jsonl"), evidence


def kind(rows, name):
    return [row for row in rows if row["kind"] == name]


def test_generation_judges_each_task_once_with_both_anchors_and_updates_the_archive(m2):
    world, _ = m2
    _, rows, evidence = mode2(m2)
    pools = [Path(row["pool"]) for row in kind(rows, "judging")]
    batches = [json.loads((p / "records" / "mapping.json").read_text()) for p in pools]
    anchors = [sorted(mapping["clones"][c]["labels"][0] for c in batch if mapping["clones"][c]["arm"] == "anchor")
               for mapping in batches for batch in mapping["batches"]]
    children = {row["candidate_id"] for row in kind(rows, "episode") if row["outcome"] == "accepted"}
    gen1 = json.loads((evidence / "archive" / "gen-1.json").read_text())
    assert ([(row["generation"], row["task"]) for row in kind(rows, "judging")], anchors,
            {e["candidate_id"] for e in gen1} == children, {e["mean_value"] for e in gen1}) == (
        [(0, world.task.name), (1, world.task.name)], [[f"{world.task.name}-stub", f"{world.task.name}-upstream"]] * 2,
        True, {6.0})


def test_generation_splits_more_than_eight_children_into_anchored_batches(m2):
    _, rows, _ = mode2(m2, episodes=9)
    (gen1,) = [row for row in kind(rows, "judging") if row["generation"] == 1]
    mapping = json.loads((Path(gen1["pool"]) / "records" / "mapping.json").read_text())
    arms = [Counter(mapping["clones"][c]["arm"] == "anchor" for c in batch) for batch in mapping["batches"]]
    assert (len([r for r in kind(rows, "episode") if r["outcome"] == "accepted"]), sorted(a[False] for a in arms),
            [a[True] for a in arms], len(json.loads(Path(gen1["results"]).read_text())["runs"])) == (9, [4, 5], [2, 2], 9)


def test_judge_calls_enter_the_ledger_and_the_cap_refuses_a_generation(m2):
    world, _ = m2
    evidence = world.outside / "evidence-a"
    with pytest.raises(CallCapExceeded):
        mode2(m2, call_cap=3)  # generation 0: one evaluation call and two judge reservations; then 4 episodes
    rows = read_records(evidence / "log.jsonl")
    ledger = json.loads((evidence / "calls.json").read_text())
    assert ([(e["key"], e["planned"], e["calls"]) for e in ledger if e["kind"] == "judge"],
            len([r for r in kind(rows, "episode") if r["generation"] == 1]),
            [r["generation"] for r in kind(rows, "evaluation")], (evidence / "archive" / "gen-1.json").exists()) == (
        [(f"gen 0 {world.task.name} {j}", 1, 0) for j in JUDGES], 4, [0], False)


def test_mode2_interleaves_i1_and_i2_and_reports_per_interface_figures(m2):
    result, rows, _ = mode2(m2)
    assert ([row["interface"] for row in kind(rows, "episode")], [row["site_id"] is None for row in kind(rows, "episode")],
            {name: (r["episodes"], r["distinct_skeletons"]) for name, r in result["interfaces"].items()}) == (
        ["I1", "I2", "I1", "I2"], [True, False, True, False], {"I1": ({"accepted": 2}, 1), "I2": ({"accepted": 2}, 2)})


def test_mode2_is_reproducible_for_a_run_seed(m2):
    draws = []
    for tag in ("a", "b"):
        _, rows, _ = mode2(m2, tag, generations=2, episodes=2, run_seed=11)
        draws.append([(r["generation"], r["parent_candidate_id"], r["site_id"]) for r in kind(rows, "episode")])
    assert (draws[0] == draws[1], len({d[1] for d in draws[0]}) > 1) == (True, True)


def test_validation_task_never_reaches_an_episode_or_adaptive_evaluation(m2):
    world, m = m2
    _, rows, _ = mode2(m2)
    briefs = (m["mutator"].parent / "briefs.txt").read_text()
    assert ([r for r in rows if r.get("task_id") == m["validation"].name and r.get("split") != "validation"],
            str(m["validation"]) in briefs, m["validation"].name in briefs,
            {r["split"] for r in kind(rows, "evaluation")}, briefs.count("# Episode")) == ([], False, False, {"adaptive"}, 4)


def test_validate_finalists_replicates_the_reference_and_direct_beside_the_finalists(m2):
    world, m = m2
    result, _, evidence = mode2(m2)
    launch = {"work_root": world.outside / "work-a", "evidence_root": evidence, "runtime": world.runtime,
              "env": m["env"], "timeout_sec": 600, "solutions": {m["validation"].name: world.solution},
              "call_cap": 200, "concurrency": 4}
    judge = {"criterion": m["criterion"], "judges": JUDGES, "scorer": scripted_judge(evidence / "log.jsonl")}
    rows = validate_finalists(evidence, evidence / "archive" / "gen-1.json", config=load_config(world.tmp / "config.json"),
                              reference_seed="direct",
                              validation_task=m["validation"], launch=launch, judge=judge)
    log = read_records(evidence / "log.jsonl")
    (validation,) = [r for r in kind(log, "judging") if r["task"] == m["validation"].name]
    readout = phase2_readout([evidence / "log.jsonl"], [evidence / "archive"],
                             read_pool(Path(validation["results"]), evidence / "log.jsonl", m["criterion"]),
                             m["criterion"])
    direct = next(r["candidate_id"] for r in kind(log, "reference"))
    assert (sorted(Counter(r["candidate_id"] for r in rows).values()), direct in {r["candidate_id"] for r in rows},
            {r["split"] for r in kind(log, "evaluation") if r["task_id"] == m["validation"].name},
            readout["rule"], readout["final_choice"] != direct) == ([2, 2, 2], True, {"validation"}, "chosen", True)
