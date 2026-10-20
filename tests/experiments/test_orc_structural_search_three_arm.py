from tests.experiments.qualification_support import measure_free, qualified, write
from tests.experiments.orc_structural_search_support import launch_config
"""The three-arm run (three_arm.py): I1, I2 and I3 episodes against the rebound direct parents, the stratified subset,
its evaluations, judging through the ledger and the per-arm readout, with a scripted `codex` (the mutator command's
CLI and the parents' coder) and a scripted judge (no provider is called)."""

import hashlib
import json
import os
import random
import shutil
import shlex
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from experiments.compare.repos import sha256_file
from experiments.orc_structural_search import three_arm, three_arm_readout
from experiments.orc_structural_search.driver import Unit, archive, launch_units
from experiments.orc_structural_search.ledger import CallCapExceeded
from experiments.orc_structural_search.quota import MAX_QUOTA_RETRIES, QuotaGuard
from experiments.orc_structural_search.records import append_record, read_records
from experiments.orc_structural_search.scoring import contaminated_children, pool_evaluations
from experiments.orc_structural_search.sites import eligible_sites, select_site, site_manifest
from tests.experiments.orc_structural_search_support import (  # noqa: F401 (pyright, world: fixtures)
    I3_CONFIG, MUTATOR, MUTATOR_I2, REPO, SCRIPTED, capped_copy, pyright, script, world)
from tests.experiments.test_orc_structural_search_adaptive import JUDGES, add_anchors, scripted_judge
from tests.experiments.test_orc_structural_search_driver import sandboxed  # noqa: F401 (fixture)
from tests.experiments.test_orc_structural_search_i3 import CODEX_EDIT, CODEX_MUTATOR

CRITERION = REPO / "experiments" / "orc_structural_search" / "criteria" / "three_arm.json"
PARENTS = REPO / "experiments" / "orc_structural_search" / "three_arm"
CONFIG = {"mutable_files": ["direct.orc"], "mutable_definitions": ["run"], "condition": "topology-only",
          "interface": "I1", "entry_workflow": "direct::run", "source_root": ".", "providers_file": "providers.json",
          "command_boundaries_file": "commands.json", "episode_wall_clock_sec": 3600, "criterion_sha256": None}
CHANGE = {"summary": "set VALUE", "account": "edited pkg"}
QUOTA = "You've hit your usage limit · resets 5:30pm (America/Los_Angeles)"
QUOTA_PLAIN = "You've hit your usage limit."  # no reset time the guard parses: it pauses quota.UNPARSED_PAUSE
# the I3 edit of test_orc_structural_search_i3, plus a comment naming the episode: every I3 child is another
# candidate with the same program digest
I3_EDIT = CODEX_EDIT + """import re
index = int(re.match(r"# Episode (\\d+)", Path("EPISODE.md").read_text()).group(1))
Path("direct.py").write_text(Path("direct.py").read_text() + f"# episode {index}\\n")
"""
# The scripted `codex`: in an episode's workspace (EPISODE.md present) the mutator for its arm (I2: the brief names a
# site; I3: direct.py; else I1), the I1 and I2 edits cycling over the global episode index; with quota-once beside
# it, the next I2 episode prints a quota line and exits 1 instead (once), with quota-always every episode prints one
# without a reset time; with print-once beside it, the next episode prints that file's text first (once). Elsewhere
# the scripted provider.
CODEX = """#!{python} -I
import re, runpy, sys
from pathlib import Path
here = Path({here!r})
if not Path("EPISODE.md").exists():
    runpy.run_path(str(here / "provider.py"))
    sys.exit(0)
brief = Path("EPISODE.md").read_text()
site = re.search(r"^Site: ", brief, re.M)
if (here / "print-once").exists():
    print((here / "print-once").read_text(), flush=True)
    (here / "print-once").unlink()
if (here / "quota-always").exists():
    print({plain!r}, flush=True)
    sys.exit(1)
if site and (here / "quota-once").exists():
    (here / "quota-once").unlink()
    print({quota!r}, flush=True)
    sys.exit(1)
runpy.run_path(str(here / ("i2.py" if site else "i3.py" if Path("direct.py").exists() else "i1.py")))
"""


def install(world, quota_once=False, print_once=None, quota_always=False):
    """The scripted codex and its parts in the world's fakebin; the parents copied outside the repository."""
    for name, source in {"provider.py": SCRIPTED, "i1.py": MUTATOR.replace("][index]", "][index % 3]"),
                         "i2.py": MUTATOR_I2.replace("][index]", "][index % 4]"), "i3.py": I3_EDIT,
                         "codex": CODEX.format(python=sys.executable, here=str(world.fakebin), quota=QUOTA,
                                              plain=QUOTA_PLAIN)}.items():
        (world.fakebin / name).write_text(source)
    (world.fakebin / "codex").chmod(0o755)
    if quota_once:
        (world.fakebin / "quota-once").write_text("")
    if quota_always:
        (world.fakebin / "quota-always").write_text("")
    if print_once:
        (world.fakebin / "print-once").write_text(print_once)
    script(world, [{"match": "Implement this change", "result": CHANGE}])
    for name in ("orc", "python"):
        if not (world.tmp / "parents" / name).exists():
            capped_copy(PARENTS / name, world.tmp / "parents" / name)
    configure(world, CRITERION)


def capped_criterion(path):
    """Amend only temporary launch criteria to match the capped fixture mutator/parents."""
    assert path.resolve() != CRITERION.resolve()
    value = json.loads(path.read_text())
    value["envelope"]["mutator"] = shlex.join(CODEX_MUTATOR)
    if "models" in value:
        aliases = {"gpt-6.1-sol": "gpt-5.6-terra", "claude-opus-5-5": "claude-sonnet-5-5"}
        value["models"] = {aliases.get(model, model): efforts for model, efforts in value["models"].items()}
    return write(path, value)


def configure(world, criterion):
    """The run configuration naming `criterion`'s sha256."""
    (world.tmp / "config.json").write_text(json.dumps(CONFIG | {"criterion_sha256": sha256_file(criterion)}))


def env_of(world):
    return {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}


def criterion_for(world, tasks):
    """The frozen criterion with the scripted judges and the test tasks' anchors."""
    q = qualified(world.tmp / 'qualified-three-arm', runtime=world.runtime, tasks=tasks, judges=JUDGES)
    data = json.loads(CRITERION.read_text()) | json.loads(q.criterion.read_text())
    data['anchors'] = {t.name: {'upstream': f'{t.name}-upstream', 'stub': f'{t.name}-stub'} for t in tasks}
    write(q.criterion, data)
    return capped_criterion(q.criterion)


def run(world, *, episodes=1, tasks=None, call_cap=200, continue_run=False, run_seed=7, criterion=CRITERION,
        guard=None):
    """(result, log rows, evidence root) of one scripted three-arm run (installed with `install`)."""
    evidence = world.tmp / "evidence"
    if criterion == CRITERION:
        criterion = measure_free(world.tmp / 'three-arm-mechanics', template=criterion, tasks=tasks or [world.task])
    criterion = capped_criterion(criterion)
    configure(world, criterion)
    result = three_arm.run_three_arm(
        world.tmp / "config.json", parents={name: world.tmp / "parents" / name for name in ("orc", "python")},
        tasks=tasks or [world.task], work_root=world.outside / "work", evidence_root=evidence,
        episodes_per_arm=episodes, agent_cmd=CODEX_MUTATOR, runtime=world.runtime, env=env_of(world),
        timeout_sec=14400, solutions={t.name: world.solution for t in tasks or [world.task]}, call_cap=call_cap,
        concurrency=4,
        run_seed=run_seed, subset_seed=3, criterion=criterion, continue_run=continue_run,
        guard=guard or QuotaGuard(retries=0))
    return result, read_records(evidence / "log.jsonl"), evidence


def kind(rows, name):
    return [row for row in rows if row["kind"] == name]


def test_three_arm_runs_six_episodes_per_arm_against_the_two_parents_and_writes_per_arm_figures(sandboxed, world,
                                                                                               pyright):
    install(world)
    result, rows, evidence = run(world, episodes=6)
    (parents,) = kind(rows, "parents")
    episodes = kind(rows, "episode")
    i1 = [row["candidate_id"] for row in episodes if row["arm"] == "I1" and row["outcome"] == "accepted"]
    arms = result["arms"]
    assert ({arm: figures["completed"] for arm, figures in arms.items()}, sorted(result),
            [row["episode_index"] for row in episodes], {row["mode"] for row in episodes},
            all(row["parent_candidate_id"] == parents["python" if row["arm"] == "I3" else "orc"] for row in episodes),
            {(row["arm"], row["site_id"] is not None, row["run_seed"]) for row in episodes},
            (arms["I1"]["accepted"], arms["I1"]["refused"]), (arms["I3"]["accepted"], arms["I3"]["exact_repeats"]),
            arms["I1"]["subset"], len(arms["I3"]["subset"]),
            json.loads((evidence / "readout.json").read_text()) == result) == (
        dict.fromkeys(("I1", "I2", "I3"), 6), ["arms", "collapse_threshold", "criterion_sha256"], list(range(18)), {"three_arm"}, True,
        {("I1", False, None), ("I2", True, 7), ("I3", False, None)}, (4, {"frozen_surface_changed": 2}), (6, 5),
        i1[:2], 1, True)  # I3: one child, the others repeat its program (comments only)


def episode_row(arm, index, cid, skeleton, outcome="accepted", parent="p", mode="three_arm", program=None):
    return {"kind": "episode", "mode": mode, "arm": arm, "interface": arm, "episode_index": index,
            "episode_id": f"e{index}", "candidate_id": cid, "parent_candidate_id": parent, "skeleton": skeleton,
            "outcome": outcome, "provider_calls": 1, "program_digest": program or f"program-{cid}"}


def tie(seed, cid):
    return hashlib.sha256(f"{seed}:{cid}".encode()).hexdigest()


def test_subset_prefers_distinct_skeletons_and_is_reproducible():
    rows = [episode_row("I1", 0, "a", "s1"), episode_row("I1", 1, "b", "s1"), episode_row("I1", 2, "c", "s2"),
            episode_row("I1", 3, "p", "s3"), episode_row("I1", 4, "a", "s1"),
            episode_row("I1", 5, "x", "s4", mode="unguided"),
            episode_row("I2", 6, "d", "s1"), episode_row("I2", 7, "e", "s1"), episode_row("I2", 8, "f", "s1"),
            episode_row("I2", 9, "g", "s9", outcome="rejected"), episode_row("I3", 10, "a", "s5"),
            episode_row("I3", 11, "h", "s5")]
    criterion = json.loads(CRITERION.read_text())
    chosen = {seed: {arm: [row["candidate_id"] for row in picked]
                     for arm, picked in three_arm.subset(rows, criterion, seed).items()} for seed in (5, 6)}
    assert (chosen[5] == {arm: [r["candidate_id"] for r in picked]
                          for arm, picked in three_arm.subset(rows, criterion, 5).items()},
            [chosen[seed] for seed in (5, 6)]) == (True, [
                {"I1": ["a", "c"], "I2": ["d", min("ef", key=lambda cid: tie(seed, cid))], "I3": ["h"]}
                for seed in (5, 6)])


def scanned(evidence, episode_id, hits, verdict):
    records = evidence / "episodes" / episode_id
    records.mkdir(parents=True, exist_ok=True)
    (records / "record.json").write_text(json.dumps({"scan": {"calls": 1, "hits": hits, "verdict": verdict}}))


def test_a_contaminated_child_is_never_chosen_and_an_unadjudicated_hit_is_refused(tmp_path):
    hit = [{"file": "calls/1/stdout.txt", "line": 1, "pattern": "archive", "text": "E/log.jsonl"}]
    for row in (episode_row("I1", 0, "a", "s1"), episode_row("I1", 1, "b", "s2")):
        append_record(tmp_path / "log.jsonl", row)
    scanned(tmp_path, "e0", hit, {"verdict": "contaminated", "reason": "read the log"})
    scanned(tmp_path, "e1", [], None)
    rows, criterion = read_records(tmp_path / "log.jsonl"), json.loads(CRITERION.read_text())
    chosen = three_arm.subset(rows, criterion, 1, contaminated_children(tmp_path / "log.jsonl"))
    scanned(tmp_path, "e1", hit, None)
    with pytest.raises(ValueError, match="no verdict"):
        contaminated_children(tmp_path / "log.jsonl")
    assert [row["candidate_id"] for row in chosen["I1"]] == ["b"]


def test_subset_children_are_evaluated_once_per_task_and_logged_with_their_arm(sandboxed, world, pyright):
    install(world)
    second = world.tmp / "task-2"
    shutil.copytree(world.task, second)
    result, rows, _ = run(world, tasks=[world.task, second])
    chosen = {cid: arm for arm, figures in result["arms"].items() for cid in figures["subset"]}
    baselines = [row for row in kind(rows, "evaluation") if row.get("parent_for_arms")]
    assert len(baselines) == 4
    evaluations = [row for row in kind(rows, "evaluation") if not row.get("parent_for_arms")]
    assert (Counter((row["candidate_id"], row["task_id"]) for row in evaluations),
            {row["candidate_id"]: row["arm"] for row in evaluations}, {row["mode"] for row in evaluations},
            all(row["episode_id"] and row["parent_candidate_id"] and row["candidate_root"] for row in evaluations),
            sorted(set(chosen.values()))) == (
        Counter({(cid, task.name): 1 for cid in chosen for task in (world.task, second)}), chosen, {"three_arm"}, True,
        ["I1", "I3"])


def test_three_arm_cap_refuses_a_launch_and_judges_enter_the_ledger(sandboxed, world, pyright):
    install(world)
    add_anchors(world.task)
    criterion = criterion_for(world, [world.task])
    with pytest.raises(CallCapExceeded):  # three episodes of one recorded call each: no evaluation fits
        run(world, call_cap=3, criterion=criterion)
    refused = read_records(world.tmp / "evidence" / "log.jsonl")
    trees = [path for name in ("agents", "records") for path in (world.outside / "work" / name).glob("*")]
    _, rows, evidence = run(world, continue_run=True, criterion=criterion)
    pool = pool_evaluations(evidence, world.task, out=world.outside / "pools" / world.task.name, judges=JUDGES,
                            criterion=criterion)
    judging = three_arm.judge(evidence, pool, world.task, criterion=criterion, judges=JUDGES, solution=world.solution,
                              call_cap=200, scorer=scripted_judge(evidence / "log.jsonl"))
    entries = json.loads((evidence / "calls.json").read_text())
    result = three_arm_readout.readout(evidence / "log.jsonl", evidence / "readout.json", criterion,
                                       [Path(judging["results"])])
    assert ([row["arm"] for row in kind(refused, "episode")], kind(refused, "evaluation"), trees,
            [(e["key"], e["planned"], e["calls"]) for e in entries if e["kind"] == "judge"],
            kind(read_records(evidence / "log.jsonl"), "judging") == [judging], judging["generation"],
            sorted(result["tasks"][world.task.name]["arms"]), result["decision"]) == (
        ["I1", "I2", "I3"], [], [], [(f"three-arm {world.task.name} {judge}", 1, 0) for judge in JUDGES], True, -2,
        ["I1", "I2", "I3"], three_arm_readout.DECISION)


def test_a_launch_beyond_the_cap_waits_for_an_evaluation_in_flight_to_settle(sandboxed, world):
    """Three I3 evaluations (eight planned calls each) under a cap that fits two in flight but not three: without
    the gate the third is refused, with it the third waits for one to settle (one recorded call) and runs."""
    script(world, [{"match": "Implement this change", "sleep": 6, "result": CHANGE}])
    capped_copy(PARENTS / "python", world.tmp / "python")
    tasks = [world.task] + [shutil.copytree(world.task, world.tmp / f"task-{n}") for n in (2, 3)]

    def launch(tag, gate):
        evidence = world.tmp / f"evidence-{tag}"
        _, root = archive(world.tmp / "python", evidence, world.runtime)
        return launch_units([Unit(root, launch_config(world, I3_CONFIG), {}, task, 1) for task in tasks], concurrency=3, gate=gate,
                            work_root=world.outside / f"work-{tag}", evidence_root=evidence, runtime=world.runtime,
                            env=env_of(world), timeout_sec=600, solutions={t.name: world.solution for t in tasks},
                            holdouts=(), call_cap=20, criterion=world.criterion)

    with pytest.raises(CallCapExceeded):
        launch("plain", None)
    rows = launch("gated", three_arm.CapGate(QuotaGuard()).run)
    assert [row["outcome"] for row in rows] == ["completed"] * 3


def test_three_arm_readout_reports_per_arm_and_per_child_descriptively_without_a_decision(tmp_path):
    criterion = tmp_path / "criterion.json"
    criterion.write_text(json.dumps(json.loads(CRITERION.read_text()) | {
        "tasks": ["tasks/t1"], "anchors": {"t1": {"upstream": "t1-upstream", "stub": "t1-stub"}}}))
    from tests.experiments.readout_support import report_qualification, report_pool
    q = report_qualification(tmp_path / 'quality', criterion, ['t1'])
    criterion = q.criterion
    evaluations = [("e1", "I1", "c1", "completed"), ("e2", "I3", "c3", "completed"), ("e3", "I3", "c4", "failed"),
                   ("e4", "I2", "c2", "completed"), ("e5", "I1", "c9", "failed")]  # c9: no longer in the subset
    for eid, arm, cid, outcome in evaluations:
        append_record(tmp_path / "log.jsonl", {
            "kind": "evaluation", "mode": "three_arm", "arm": arm, "evaluation_id": eid, "candidate_id": cid,
            "criterion_sha256": hashlib.sha256(criterion.read_bytes()).hexdigest(), "task_id": "t1", "replicate": 1, "outcome": outcome, "split": "unavailable",
            "records_dir": str(tmp_path / eid), "provider_calls": 1, "wall_clock_sec": 5.0, "incidents": []})
    runs = [{"run": str(tmp_path / eid), "arm": eid, "value": value, "hidden_value": None, "calls": 1,
             "wall_clock_sec": 5.0} for eid, value in (("e1", 6.0), ("e2", 4.0), ("e4", None))]
    anchors = [{"batch": 0, "judge": "judge-a", "anchor": "t1-upstream", "total": 8},
               {"batch": 0, "judge": "judge-a", "anchor": "t1-stub", "total": 0}]
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"criterion_sha256": hashlib.sha256(criterion.read_bytes()).hexdigest(),
                                   "runs": runs, "anchors": anchors, "agreement": {}, "excluded_judges": {}}))
    report_pool(results, q, 't1')
    driver = {"criterion_sha256": hashlib.sha256(criterion.read_bytes()).hexdigest(),
              "arms": {"I1": {"completed": 6, "subset": ["c1"]}, "I2": {"subset": ["c2", "c5"]},
                       "I3": {"subset": ["c3", "c4"]}}}
    (tmp_path / "readout.json").write_text(json.dumps(driver))
    result = three_arm_readout.readout(tmp_path / "log.jsonl", tmp_path / "readout.json", criterion, [results])
    task = result["tasks"]["t1"]
    arms = task["arms"]
    assert ((arms["I1"]["mean"], arms["I1"]["failed"], arms["I3"]["mean"], arms["I3"]["failed"], arms["I2"]["mean"],
             arms["I2"]["excluded"]),
            {arm: sorted(figures["children"]) for arm, figures in arms.items()},
            arms["I3"]["children"]["c4"]["values"], task["anchor_checks"]["anchors_ok"],
            arms["I2"]["children"]["c5"]["mean"],
            result["compile_only"], result["decision"]) == (
        (3.0, 1, 2.0, 1, "unavailable", 1), {"I1": ["c1", "c9"], "I2": ["c2", "c5"], "I3": ["c3", "c4"]}, [0.0], True,
        "unavailable", driver,
        "descriptive; no separation rule applied (Phase 1 decision stands)")


def test_i2_site_draw_is_reproducible_for_a_run_seed(sandboxed, world, pyright):
    install(world)
    _, rows, evidence = run(world, episodes=2, run_seed=11)
    config = three_arm.arm_config(world.tmp / "config.json", "I2")
    parent = evidence / "candidates" / kind(rows, "parents")[0]["orc"]
    sites = eligible_sites(site_manifest(parent, config, runtime=world.runtime), config)
    drawn = [(row["site_id"], row["run_seed"]) for row in kind(rows, "episode") if row["arm"] == "I2"]
    assert drawn == [(select_site(sites, random.Random(f"11 {row['episode_index']}"))["site_id"], 11)
                     for row in kind(rows, "episode") if row["arm"] == "I2"]


def test_a_slot_whose_quota_relaunches_are_used_up_stops_the_run_and_continue_completes_it(sandboxed, world,
                                                                                         pyright):
    install(world, quota_once=True)
    with pytest.raises(three_arm.QuotaExhausted, match="rerun with --continue"):
        run(world)
    stopped = read_records(world.tmp / "evidence" / "log.jsonl")
    readout_written = (world.tmp / "evidence" / "readout.json").exists()
    result, rows, _ = run(world, continue_run=True)
    episodes = kind(rows, "episode")
    assert ([(row["arm"], row["episode_index"]) for row in kind(stopped, "episode")], kind(stopped, "evaluation"),
            readout_written, [(row["arm"], row["episode_index"]) for row in episodes], episodes[1]["incidents"],
            result["arms"]["I2"]["completed"], sum(result["arms"]["I2"]["episodes"].values()),
            max(Counter(row["evaluation_id"] for row in kind(rows, "evaluation")).values()),
            len(kind(rows, "parents"))) == (
        [("I1", 0), ("I2", 1)], [], False, [("I1", 0), ("I2", 1), ("I2", 2), ("I3", 3)],
        [f"quota: {QUOTA}"], 1, 2, 1, 1)


def unparsed_quota_guard():
    """A quota guard with every relaunch (MAX_QUOTA_RETRIES) and a fake clock its pauses advance."""
    now = [datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)]

    def sleep(seconds):
        now[0] += timedelta(seconds=seconds)

    return QuotaGuard(retries=MAX_QUOTA_RETRIES, clock=lambda: now[0], sleep=sleep, say=lambda line: None)


def test_an_episode_slot_that_keeps_hitting_an_unparsed_quota_stops_the_run_after_its_relaunches(sandboxed, world,
                                                                                               pyright):
    install(world, quota_always=True)
    with pytest.raises(three_arm.QuotaExhausted, match="rerun with --continue"):
        run(world, episodes=6, guard=unparsed_quota_guard())
    rows = read_records(world.tmp / "evidence" / "log.jsonl")
    assert ([(row["arm"], row["incidents"]) for row in kind(rows, "episode")], kind(rows, "evaluation"),
            (world.tmp / "evidence" / "readout.json").exists()) == (
        [("I1", [f"quota: {QUOTA_PLAIN}"])] * (1 + MAX_QUOTA_RETRIES), [], False)


def test_a_run_refuses_a_hide_path_that_does_not_exist_before_anything_exists(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps(CONFIG | {"criterion_sha256": sha256_file(CRITERION)}))
    with pytest.raises(ValueError, match="not an existing directory"):
        three_arm.run_three_arm(tmp_path / "config.json", parents={}, tasks=[], work_root=tmp_path / "w",
                                evidence_root=tmp_path / "e", episodes_per_arm=6, agent_cmd=shlex.split(json.loads(CRITERION.read_text())["envelope"]["mutator"]),
                                runtime=tmp_path, env={}, timeout_sec=14400, solutions={}, call_cap=1, concurrency=1,
                                run_seed=1, subset_seed=1, criterion=CRITERION, hide=[tmp_path / "ss-evidnce2"])
    assert [path.name for path in tmp_path.iterdir()] == ["config.json"]


def test_the_subset_skips_a_child_whose_program_repeats_the_parents_or_a_chosen_childs():
    rows = [{"kind": "parents", "subset_seed": 1, "program_digests": {"orc": "parent-orc", "python": "parent-py"}},
            episode_row("I1", 0, "a", "s1", program="pa"), episode_row("I1", 1, "b", "s2", program="parent-orc"),
            episode_row("I1", 2, "c", "s2", program="pa"), episode_row("I1", 3, "d", "s2", program="pd"),
            episode_row("I3", 4, "e", "s5", program="pa"), episode_row("I3", 5, "f", "s5", program="pf")]
    chosen = three_arm.subset(rows, json.loads(CRITERION.read_text()), 1)
    assert {arm: [row["candidate_id"] for row in picked] for arm, picked in chosen.items()} == {
        "I1": ["a", "d"], "I2": [], "I3": ["f"]}


def test_a_run_refuses_an_orc_parent_that_does_not_compile_before_any_spend(world):
    install(world)
    entry = world.tmp / "parents" / "orc" / "direct.orc"
    entry.write_text(entry.read_text().replace("(export run)", "(export run missing)"))
    with pytest.raises(RuntimeError, match="does not compile"):
        run(world)
    evidence = world.tmp / "evidence"
    assert ((evidence / "log.jsonl").exists(), (evidence / "calls.json").exists()) == (False, False)


def test_the_readout_command_reads_the_log_alone_without_results(tmp_path, capsys):
    criterion = tmp_path / "criterion.json"
    criterion.write_text(json.dumps(json.loads(CRITERION.read_text()) | {"tasks": ["tasks/t1"]}))
    append_record(tmp_path / "log.jsonl", {
        "kind": "evaluation", "mode": "three_arm", "arm": "I1", "evaluation_id": "e1", "candidate_id": "c1",
        "criterion_sha256": sha256_file(criterion), "task_id": "t1", "replicate": 1, "outcome": "failed", "split": "unavailable", "records_dir": str(tmp_path),
        "provider_calls": 1, "wall_clock_sec": 5.0, "incidents": []})
    (tmp_path / "readout.json").write_text(json.dumps({"criterion_sha256": sha256_file(criterion),
                                                       "arms": {"I1": {"subset": ["c1"]}, "I2": {"subset": []},
                                                                "I3": {"subset": []}}}))
    three_arm.main(["readout", "--log", str(tmp_path / "log.jsonl"), "--driver-readout",
                    str(tmp_path / "readout.json"), "--criterion", str(criterion), "--measure-free"])
    result = json.loads(capsys.readouterr().out)
    assert result['mode'] == 'measure-free'
    assert result['executions'][0]['outcome'] == 'failed'
    assert 'tasks' not in result and 'anchors' not in result



def test_an_accepted_episode_with_unadjudicated_scan_hits_stops_the_run_before_the_subset(sandboxed, world, pyright):
    install(world, print_once=str(world.tmp / "evidence" / "log.jsonl"))  # the I1 episode names the evidence root
    with pytest.raises(ValueError, match="no verdict"):
        run(world)
    rows = read_records(world.tmp / "evidence" / "log.jsonl")
    assert ([(row["arm"], row["outcome"], row["scan_pending"]) for row in kind(rows, "episode")][0],
            kind(rows, "evaluation"), (world.tmp / "evidence" / "readout.json").exists()) == (
        ("I1", "accepted", True), [], False)


def test_a_run_refuses_another_mutator_criterion_hash_or_envelope_before_anything_exists(tmp_path):
    historical_mutator = shlex.split(json.loads(CRITERION.read_text())["envelope"]["mutator"])
    hashed = CONFIG | {"criterion_sha256": sha256_file(CRITERION)}
    cases = [(hashed, ["claude", "-p"], 14400, "--agent-cmd"), (CONFIG | {"criterion_sha256": "0" * 64},
                                                                 historical_mutator, 14400, "criterion_sha256"),
             (hashed | {"episode_wall_clock_sec": 600}, historical_mutator, 14400, "episode_wall_clock_sec"),
             (hashed, historical_mutator, 600, "--eval-timeout-sec")]
    named = []
    for config, agent_cmd, timeout, field in cases:
        (tmp_path / "config.json").write_text(json.dumps(config))
        with pytest.raises(ValueError) as error:
            three_arm.run_three_arm(tmp_path / "config.json", parents={}, tasks=[], work_root=tmp_path / "w",
                                    evidence_root=tmp_path / "e", episodes_per_arm=6, agent_cmd=agent_cmd,
                                    runtime=tmp_path, env={}, timeout_sec=timeout, solutions={}, call_cap=1,
                                    concurrency=1, run_seed=1, subset_seed=1, criterion=CRITERION)
        named.append(str(error.value).split(": ", 1)[1].split(" ")[0] == field)
    assert (named, (tmp_path / "e").exists()) == ([True] * 4, False)


def test_a_smoke_evaluates_the_two_parents_once_per_task_through_the_command_line(sandboxed, world, pyright,
                                                                                  monkeypatch):
    install(world)
    for name, value in env_of(world).items():
        monkeypatch.setenv(name, value)
    evidence, parents = world.tmp / "evidence", world.tmp / "parents"
    criterion = capped_criterion(measure_free(world.tmp / "cli-mechanics", template=CRITERION, tasks=[world.task]))
    configure(world, criterion)
    three_arm.main(["run", "--smoke", "--episodes-per-arm", "0", "--config", str(world.tmp / "config.json"),
                    "--parents", f"orc={parents / 'orc'}", f"python={parents / 'python'}",
                    "--criterion", str(criterion), "--tasks", str(world.task),
                    "--work-root", str(world.outside / "work"), "--evidence", str(evidence),
                    "--agent-cmd", " ".join(CODEX_MUTATOR), "--runtime", str(world.runtime),
                    "--eval-timeout-sec", "14400",
                    "--solution", f"{world.task.name}={world.solution}", "--call-cap", "9", "--run-seed", "1",
                    "--subset-seed", "1"])
    rows = read_records(evidence / "log.jsonl")
    (parents_row,) = kind(rows, "parents")
    assert (sorted((row["mode"], row["parent"], row["candidate_id"], row["outcome"])
                   for row in kind(rows, "evaluation")), kind(rows, "episode"),
            (evidence / "readout.json").exists()) == (
        [("smoke", "orc", parents_row["orc"], "completed"), ("smoke", "python", parents_row["python"], "completed")],
        [], False)
