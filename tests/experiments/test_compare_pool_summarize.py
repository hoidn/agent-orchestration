"""Comparison harness, scoring side (experiments/compare): blind pool, verify-pool, summarize.

Behaviour on temporary git repositories with a stand-in agent CLI and synthetic scoring runs written
where each judge's state directory holds them; see compare_harness_support.
"""

import json
import os
from pathlib import Path

import pytest

from experiments.compare import pool as pooling, prepare, repos, summarize
from tests.experiments.compare_harness_support import (  # noqa: F401 (world and pooled are fixtures)
    REPO, call, drive, edit, pooled, start, world, write_memo, write_task,
)

TOKENS = {  # (arm, last label) -> four Score tokens; judge-b rates the control's root cause one higher
    ("best_of_n", "cand-1"): ("S1",) * 4, ("best_of_n", "cand-2"): ("S2",) * 4,
    ("reviewed_change", "first"): ("S0",) * 4, ("reviewed_change", "final"): ("S2",) * 4,
    ("direct_task", "final"): ("S1",) * 4, ("anchor", "upstream"): ("S2",) * 4, ("anchor", "symptom"): ("S0",) * 4,
}


def rating(path, clone, judge):
    tokens = TOKENS[(clone["arm"], clone["labels"][-1])]
    if judge == "judge-b" and clone["arm"] == "direct_task":
        tokens = ("S2",) + tokens[1:]
    return dict(zip(("root_cause", "scope", "generality", "layering"), tokens), clone=path, reason="r")


def score(out, judge, mapping, *, tamper=None, sha=None, run_id="r1"):
    """Write a completed scoring run where the judge's own --state-dir puts it."""
    inputs = json.loads((out / "records" / f"score-inputs-{judge}.json").read_text())
    value = [[rating(path, mapping["clones"][Path(path).name], judge) for path in batch["clones"]]
             for batch in inputs["batches"]]
    if tamper:
        tamper(value)
    inputs["criterion_sha256"] = sha or inputs["criterion_sha256"]
    run = out / "judges" / mapping["judges"][judge]["dir"] / "state" / run_id
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"bound_inputs": inputs}))
    (run / "memo.jsonl").write_text(json.dumps({"outcome": "completed", "record": "terminal", "value": value}) + "\n")


def test_pool_composes_batches_per_d4(pooled):  # each reviewed_change stage is drawn at random: two valid shapes
    clones, anchors = pooled.mapping["clones"], [("anchor", "symptom"), ("anchor", "upstream")]
    bon = [("best_of_n", "cand-1"), ("best_of_n", "cand-2"), ("direct_task", "final")]
    rc = "reviewed_change"
    same, first, final = (rc, "first", "final"), (rc, "first"), (rc, "final")
    shapes = sorted(sorted((clones[c]["arm"], *clones[c]["labels"]) for c in b) for b in pooled.mapping["batches"])
    assert shapes in [sorted(sorted(b + anchors) for b in (bon, [same, x], [y]))
                      for x, y in ((first, final), (final, first))]


def test_pool_strips_design_artifacts_and_records_the_removal(pooled):
    cid = next(cid for cid, c in pooled.mapping["clones"].items() if c["labels"] == ["cand-2"])
    clone = pooled.out / "clones" / cid
    assert (pooled.mapping["clones"][cid]["stripped"], (clone / "docs/design/plan.md").exists(),
            "pkg/extra.py" in repos.git(clone, "diff", "--name-only")) == (["docs/design/plan.md"], False, True)


def test_pool_keeps_arms_and_stages_out_of_what_judges_see(pooled):
    inputs = (pooled.out / "records" / "score-inputs-judge-a.json").read_text().replace(str(pooled.out), "")
    words = ("best_of_n", "reviewed_change", "direct_task", "first", "final", "cand-", "anchor", "run-")
    assert [w for w in words if w in inputs or any(w in cid for cid in pooled.mapping["clones"])] == []


def test_judges_cannot_list_the_clones_directory(pooled):
    with pytest.raises(PermissionError):
        os.listdir(pooled.out / "clones")


def test_each_judge_gets_its_own_inputs_working_and_state_directory(pooled, world):
    judges = pooled.mapping["judges"]
    commands = {j: (pooled.out / "records" / f"score-{j}.sh").read_text().split() for j in judges}
    inputs = {j: json.loads((pooled.out / "records" / f"score-inputs-{j}.json").read_text()) for j in judges}
    homes = {j: str(pooled.out / "judges" / info["dir"]) for j, info in judges.items()}
    providers = {"judge-a": str(world.runtime / "experiments/compare/score.providers.json"),
                 "judge-b": str(REPO / "experiments/compare/providers/score_codex.json")}
    assert ({j: (c[1], c[c.index("--state-dir") + 1], c[c.index("--provider-externs-file") + 1])
             for j, c in commands.items()},
            {j: (i["judge_model"], i["criterion_sha256"]) for j, i in inputs.items()}, len(set(homes.values()))) == (
        {j: (homes[j], homes[j] + "/state", providers[j]) for j in judges},
        {j: (j, repos.sha256_file(world.criterion)) for j in judges}, 2)


def test_pool_refuses_an_unscanned_run(world):
    records, record = start(world, "direct_task")
    call(world, record, "true")
    write_memo(record, ["true"], True)
    prepare.collect(records)
    with pytest.raises(SystemExit, match="scanned"):
        pooling.pool(world.task, world.criterion, world.tmp / "pool", ["j"], [records])


def test_pool_refuses_a_run_with_hits_and_no_verdict(world):
    records, _ = drive(world, "direct_task", ["echo github.com"], True)
    with pytest.raises(SystemExit, match="1 scan hits and no verdict"):
        pooling.pool(world.task, world.criterion, world.tmp / "pool", ["j"], [records])


def test_pool_excludes_contaminated_runs_and_includes_cleared_ones(world):
    dirty, _ = drive(world, "direct_task", ["echo github.com"], True, verdict=("contaminated", "read the fix"))
    cleared, _ = drive(world, "direct_task", ["echo github.com"], True, verdict=("cleared", "printed a URL"))
    clean, _ = drive(world, "direct_task", ["true"], True)
    mapping = pooling.pool(world.task, world.criterion, world.tmp / "pool", ["j"], [dirty, cleared, clean])
    assert (mapping["runs"][str(dirty)]["excluded"],
            sorted({c["run"] for c in mapping["clones"].values() if c["run"]})) == (
        "contaminated: read the fix", sorted([str(cleared), str(clean)]))


def test_verify_pool_restores_a_clone_a_judge_changed(pooled, capsys):
    cid = next(iter(pooled.mapping["clones"]))
    clone, base = pooled.out / "clones" / cid, pooled.mapping["compare_base"]
    recorded = repos.patch_of(clone, base)
    (clone / "pkg/calc.py").write_text("broken\n")
    (clone / "notes.txt").write_text("judge notes\n")
    with pytest.raises(SystemExit):
        pooling.verify_pool(pooled.out)
    printed = capsys.readouterr().out
    assert (cid in printed, "notes.txt" in printed, repos.patch_of(clone, base) == recorded) == (True, True, True)
    pooling.verify_pool(pooled.out)


@pytest.fixture
def results(pooled, world):
    for judge in ("judge-a", "judge-b"):
        score(pooled.out, judge, pooled.mapping)
    return summarize.summarize(pooled.out, world.criterion)


def test_summarize_joins_ratings_by_position_and_computes_measures(results):
    m = results["measures"]
    assert (m["best_of_n.mean"], m["best_of_n.paired_gain_mean"], m["best_of_n.group_gain_mean"],
            m["best_of_n.minus_control"], m["reviewed_change.paired_gain_mean"],
            m["reviewed_change.paired_gain_runs_negative"], results["verdict"]["primary"][0]["met"]) == (
        8, 4, 2, 3.5, 4, 0, True)


def test_summarize_counts_exact_agreement_per_criterion(results, pooled):
    n = len(pooled.mapping["clones"])
    assert results["agreement"] == {"root_cause": {"agree": n - 1, "of": n}, "scope": {"agree": n, "of": n},
                                    "generality": {"agree": n, "of": n}, "layering": {"agree": n, "of": n}}


def test_summarize_reports_anchor_scores_per_batch_and_judge(results):
    assert sorted((a["batch"], a["anchor"], a["judge"], a["total"]) for a in results["anchors"]) == sorted(
        (i, name, judge, total) for i in range(3) for judge in ("judge-a", "judge-b")
        for name, total in (("upstream", 8), ("symptom", 0)))


def test_failed_runs_are_listed_with_their_reason_and_never_pooled(results, pooled):
    row = next(row for row in results["runs"] if row["run"] == str(pooled.failed))
    assert (row["outcome"], row["failure"]["code"], row["value"], row["scores"]) == (
        "failed", "provider_timeout", None, {})


def test_results_md_holds_what_results_json_reports(results, pooled):
    text = (pooled.out / "records" / "results.md").read_text()
    expected = ["root_cause: 11/12", "batch 2, symptom, judge-b: 0", "primary: best_of_n.group_gain_mean >= 0.75",
                "best_of_n.minus_control: 3.50", "provider_timeout"]
    assert [line for line in expected if line not in text] == []


def test_summarize_refuses_a_batch_with_a_missing_rating(pooled, world):
    score(pooled.out, "judge-a", pooled.mapping, tamper=lambda value: value[1].pop())
    score(pooled.out, "judge-b", pooled.mapping)
    with pytest.raises(SystemExit, match="batch 1"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_refuses_a_copied_back_id_that_disagrees_with_its_position(pooled, world):
    def swap(value):
        value[0][0]["clone"], value[0][1]["clone"] = value[0][1]["clone"], value[0][0]["clone"]
    score(pooled.out, "judge-a", pooled.mapping, tamper=swap)
    score(pooled.out, "judge-b", pooled.mapping)
    with pytest.raises(SystemExit, match="batch 0 position 0"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_refuses_a_scoring_run_bound_to_another_criterion(pooled, world):
    score(pooled.out, "judge-a", pooled.mapping, sha="0" * 64)
    score(pooled.out, "judge-b", pooled.mapping)
    with pytest.raises(SystemExit, match=f"{'0' * 64}.*{repos.sha256_file(world.criterion)}"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_refuses_unless_every_judge_has_exactly_one_scoring_run(pooled, world):
    score(pooled.out, "judge-a", pooled.mapping)
    with pytest.raises(SystemExit, match="judge judge-b: expected one scoring run.*found 0"):
        summarize.summarize(pooled.out, world.criterion)
    score(pooled.out, "judge-b", pooled.mapping)
    score(pooled.out, "judge-b", pooled.mapping, run_id="r2")
    with pytest.raises(SystemExit, match="judge judge-b: expected one scoring run.*found 2"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_runs_hidden_acceptance_in_an_untouched_copy_without_git(world):
    task = world.tmp / "task-hidden"
    write_task(task, world.base, anchors=False, hidden=True)
    own_test = "mkdir -p tests && printf 'def test_missing():\\n    pass\\n' > tests/test_hidden.py"
    records, _ = drive(world, "direct_task", [edit("$PWD", "a + b") + own_test], True, task=task)
    out = world.tmp / "pool-hidden"
    mapping = pooling.pool(task, world.criterion, out, ["judge-a"], [records])
    score(out, "judge-a", mapping)
    results = summarize.summarize(out, world.criterion)
    pooling.verify_pool(out)
    assert results["measures"]["direct_task.hidden_mean"] == pytest.approx(3 / 4)
