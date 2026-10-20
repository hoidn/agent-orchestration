"""Mode 2 of the structural search driver: archive, parent and site selection, feedback, per-generation judging and
validation, with scripted providers, a scripted mutator and a scripted judge (no provider is called)."""

import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest


from experiments.orc_structural_search.adaptive import feedback, incumbent, initial_archive, retain, run_mode2, select_parent
from experiments.orc_structural_search.judging import judge_generation
from experiments.orc_structural_search.records import append_record, read_records
from tests.experiments.compare_harness_support import write_memo
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



@pytest.mark.parametrize('purpose', ['quality-unqualified', 'measure-free', 'quality-qualified'])
def test_mode2_refuses_fresh_adaptive_launch_without_provider_work(tmp_path, purpose):
    from tests.experiments.qualification_support import qualified, write, sha
    q = qualified(tmp_path / 'first')
    validation = tmp_path / 'validation'
    shutil.copytree(q.tasks[0], validation)
    q = qualified(tmp_path / 'qualification', runtime=q.runtime, tasks=[q.tasks[0], validation], judges=JUDGES)
    frozen = json.loads(PHASE2.read_text()) | json.loads(q.criterion.read_text())
    frozen.update(adaptive_tasks=[str(q.tasks[0])], validation_task=str(validation))
    if purpose == 'measure-free':
        frozen['purpose'] = 'measure-free'
    elif purpose == 'quality-unqualified':
        del frozen['qualification']
    write(q.criterion, frozen)
    config = write(tmp_path / 'config.json', CONFIG | {'criterion_sha256': sha(q.criterion)})
    expected = 'unsupported' if purpose != 'quality-unqualified' else 'qualification'
    with pytest.raises(ValueError, match=expected):
        run_mode2(config, phase1_joined=tmp_path / 'joined.json', seeds=[], adaptive_tasks=[q.tasks[0]],
            validation_task=validation, generations=1, episodes_per_generation=1, run_seed=1,
            work_root=tmp_path / 'work', evidence_root=tmp_path / 'evidence', agent_cmd=[], runtime=q.runtime,
            env={}, timeout_sec=1, solutions={}, call_cap=1, concurrency=1, criterion=q.criterion,
            judges=JUDGES, pools_root=tmp_path / 'pools')
    assert not (tmp_path / 'evidence').exists()
