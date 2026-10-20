"""Generic calibration pools and complete-denominator verdicts; no provider calls."""

import json
from pathlib import Path

import pytest

from experiments.compare import pool as pooling, prepare, repos, summarize
from tests.experiments.compare_harness_support import UPSTREAM, world, write_memo  # noqa: F401

REFERENCE_RUBRIC = {"workflow": "score_ref.orc", "entry": "score_ref::score",
                    "criteria": ["completeness", "correctness", "scope", "layering"], "reference": "upstream"}


@pytest.fixture
def package(world):
    anchors = world.task / "anchors"
    (anchors / "upstream.diff").rename(anchors / "task-upstream.diff")
    (anchors / "symptom.diff").rename(anchors / "task-stub.diff")
    for role in ("partial", "mutant"):
        (anchors / f"task-{role}.diff").write_bytes((anchors / "task-stub.diff").read_bytes())
    rule = repos.load(world.criterion) | {
        "purpose": "calibration", "rubric": REFERENCE_RUBRIC,
        "anchors": {"task": {role: f"task-{role}" for role in ("upstream", "stub", "partial", "mutant")}},
        "calibration": {"margin": 4, "mutant_margin": 2, "error_rate": 0}, "anchor_spread_limit": 2}
    repos.dump(world.criterion, rule)
    diffs = []
    for index in range(11):
        path = world.tmp / f"filler-{index}.diff"
        path.write_text(UPSTREAM.replace("+    return a + b", f"+    return a + b + {index}"))
        diffs.append(path)
    bad = world.tmp / "bad.diff"
    bad.write_text(UPSTREAM.replace("-    return a - b", "-    return wrong"))
    return rule, diffs, bad


def make_pool(world, diffs, out="calibration", **kwargs):
    return pooling.pool_from_diffs(world.task, world.criterion, world.outside / out, ["judge-a", "judge-b"],
                                   world.runtime, diffs, **({"batches": 2, "per_batch": 5,
                                   "min_per_batch": 4, "filler_seed": 27} | kwargs))


def test_applicable_keeps_only_diffs_that_apply_on_the_seeded_base(world, package):
    _, diffs, bad = package
    assert pooling.applicable(world.runtime, world.base, world.task / "seed", [diffs[0], bad, diffs[1]]) == diffs[:2]


def test_pool_from_diffs_deals_disjoint_fillers_and_every_anchor_into_each_batch(world, package):
    _, diffs, _ = package
    mapping = make_pool(world, diffs)
    def labels(mapping):
        return [[mapping["clones"][cid]["labels"] for cid in batch if mapping["clones"][cid]["arm"] == "filler"]
                for batch in mapping["batches"]]
    assert labels(mapping) == labels(make_pool(world, diffs, out="same-seed"))
    assert len({tuple(label) for batch in labels(mapping) for label in batch}) == 10
    assert mapping["runs"] == {}
    for ids in mapping["batches"]:
        assert len(ids) + 1 == 10
        assert sum(mapping["clones"][cid]["arm"] == "anchor" for cid in ids) == 4
        assert all(mapping["clones"][cid]["run"] is None for cid in ids)


@pytest.mark.parametrize("options,minimum", [({"per_batch": 6}, False), ({"min_per_batch": 6}, False),
                                               ({"batches": 0}, False), ({}, True)])
def test_pool_from_diffs_refuses_invalid_capacity_before_writing(world, package, options, minimum):
    _, diffs, _ = package
    with pytest.raises(SystemExit, match="batch|filler|capacity"):
        make_pool(world, diffs[:7] if minimum else diffs, **options)
    assert not (world.outside / "calibration").exists()


def test_pool_from_diffs_refuses_duplicate_fillers(world, package):
    _, diffs, _ = package
    with pytest.raises(SystemExit, match="duplicate|distinct|filler"):
        make_pool(world, [diffs[0]] * 10)
    assert not (world.outside / "calibration").exists()


def test_calibrate_cli_filters_and_reports_nonapplicable_fillers(world, package, capsys):
    _, diffs, bad = package
    prepare.main(["calibrate", "--task", str(world.task), "--criterion", str(world.criterion),
                  "--out", str(world.outside / "cli"), "--runtime", str(world.runtime),
                  "--judge", "judge-a", "--judge", "judge-b", "--batches", "2", "--per-batch", "5",
                  "--min-per-batch", "4", "--filler-seed", "27",
                  *[arg for path in [*diffs, bad] for arg in ("--filler", str(path))]])
    output = capsys.readouterr().out
    assert str(bad) in output and all(str(path) in output for path in diffs)
    assert len(repos.load(world.outside / "cli/records/mapping.json")["batches"]) == 2


def observations(rule, *, batches=2, upstream=8, partial=5, mutant=5, stub=1):
    roles = rule["anchors"]["task"]
    mapping = {"task": "/tasks/task", "batches": [list(roles.values()) for _ in range(batches)]}
    results = {"judges": rule["judges"], "excluded_judges": {}, "anchors": [
        {"judge": judge, "batch": batch, "anchor": roles[role], "total": total}
        for judge in rule["judges"] for batch in range(batches)
        for role, total in {"upstream": upstream, "stub": stub, "partial": partial, "mutant": mutant}.items()]}
    return results, mapping


def test_calibration_verdict_passes_when_every_rule_holds_in_every_pair(world, package):
    rule, _, _ = package
    results, mapping = observations(rule)
    verdict = summarize.calibration(results, mapping, rule)
    assert verdict["passed"] is True
    assert len(verdict["pairs"]) == 4
    assert (verdict["p1_failing"], verdict["p2_failing"], verdict["p3_failing"]) == (0, 0, 0)
    assert verdict["anchor_spread"] == {judge: {anchor: 0 for anchor in rule["anchors"]["task"].values()}
                                           for judge in rule["judges"]}


def test_calibration_verdict_requires_the_partial_ordering(world, package):
    rule, _, _ = package
    results, mapping = observations(rule)
    next(row for row in results["anchors"] if row["anchor"] == "task-partial")["total"] = 0
    verdict = summarize.calibration(results, mapping, rule)
    assert verdict["p2_failing"] == .25
    assert verdict["passed"] is False


@pytest.mark.parametrize("mutant", [7, 8])
def test_calibration_verdict_fails_a_similarity_judge_on_the_mutant(world, package, mutant):
    rule, _, _ = package
    results, mapping = observations(rule, mutant=mutant)
    verdict = summarize.calibration(results, mapping, rule)
    assert verdict["p1_failing"] == verdict["p2_failing"] == 0
    assert verdict["p3_failing"] == 1
    assert verdict["passed"] is False


def test_calibration_verdict_fails_on_anchor_spread_above_the_limit(world, package):
    rule, _, _ = package
    results, mapping = observations(rule, partial=3, mutant=3)
    results["anchors"][0]["total"] = 5
    verdict = summarize.calibration(results, mapping, rule)
    assert verdict["p1_failing"] == verdict["p2_failing"] == verdict["p3_failing"] == 0
    assert verdict["anchor_spread"]["judge-a"]["task-upstream"] == 3
    assert verdict["passed"] is False


@pytest.mark.parametrize("missing", ["judge", "excluded", "control", "incomplete", "all"])
def test_calibration_missing_judges_and_controls_fail_the_declared_denominator(world, package, missing):
    rule, _, _ = package
    results, mapping = observations(rule)
    if missing in ("judge", "all"):
        results["judges"] = [] if missing == "all" else ["judge-a"]
        results["anchors"] = [row for row in results["anchors"] if row["judge"] in results["judges"]]
    elif missing == "excluded":
        results["excluded_judges"] = {"judge-b": "contaminated"}
    elif missing == "control":
        results["anchors"].pop()
    else:
        results["anchors"][-1]["total"] = None
    verdict = summarize.calibration(results, mapping, rule)
    assert len(verdict["pairs"]) == 4
    assert verdict["passed"] is False
    assert verdict["p3_failing"] >= .25


def saved_results(world, rule, out, **kwargs):
    results, mapping = observations(rule, **kwargs)
    results |= {"criterion_sha256": repos.sha256_file(world.criterion), "task": mapping["task"],
                "calibration": summarize.calibration(results, mapping, rule)}
    path = world.tmp / f"{out}.json"
    repos.dump(path, results)
    return path


def test_calibration_over_combines_pools_and_their_cross_pool_spread(world, package):
    rule, _, _ = package
    a = saved_results(world, rule, "A", partial=3, mutant=3)
    b = saved_results(world, rule, "B2", upstream=5, partial=3, mutant=3)
    verdict = summarize.calibration_over([a, b], world.criterion)
    assert all(verdict["pools"].values())
    assert verdict["anchor_spread"]["judge-a"]["task-upstream"] == 3
    assert verdict["passed"] is False


def test_calibration_over_uses_the_actual_accepted_a_or_a2_baseline(world, package, capsys):
    rule, _, _ = package
    failed_a = saved_results(world, rule, "A", mutant=8)
    accepted_a2 = saved_results(world, rule, "A2")
    b2 = saved_results(world, rule, "B2")
    assert summarize.calibration_over([failed_a, b2], world.criterion)["passed"] is False
    summarize.main(["--calibration-over", str(accepted_a2), str(b2), "--criterion", str(world.criterion)])
    assert json.loads(capsys.readouterr().out)["passed"] is True


def test_calibration_over_refuses_another_criterion(world, package):
    rule, _, _ = package
    path = saved_results(world, rule, "A")
    result = repos.load(path) | {"criterion_sha256": "0" * 64}
    repos.dump(path, result)
    with pytest.raises(SystemExit, match="criterion"):
        summarize.calibration_over([path], world.criterion)


def test_judge_scan_reports_test_runs_and_requires_existing_adjudication(world, package):
    _, diffs, _ = package
    mapping = make_pool(world, diffs)
    out = world.outside / "calibration"
    home = out / "judges" / mapping["judges"]["judge-a"]["dir"]
    slug = "".join(char if char.isalnum() else "-" for char in str(home))
    project = world.tmp / "home/.claude/projects" / slug
    project.mkdir(parents=True)
    (project / "s.jsonl").write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "input": {"command": "python -m pytest tests/ && python dev_check.py"}}]}}) + "\n")
    hits = pooling.scan_judge(out, "judge-a", world.solution, home=world.tmp / "home")
    assert any(hit["pattern"] == "judge ran tests" for hit in hits)
    with pytest.raises(SystemExit, match="no verdict"):
        summarize.judge_exclusion(out, "judge-a")
    pooling.adjudicate_judge(out, "judge-a", "cleared", "reported test run inspected")
    assert summarize.judge_exclusion(out, "judge-a") is None


def test_summarize_writes_calibration_without_rerunning_hidden_acceptance(world, package, monkeypatch):
    rule, diffs, _ = package
    mapping = make_pool(world, diffs)
    out = world.outside / "calibration"
    for judge, info in mapping["judges"].items():
        inputs = repos.load(out / "records" / f"score-inputs-{judge}.json")
        value = []
        for batch in inputs["batches"]:
            ratings = []
            for path in batch["clones"]:
                label = mapping["clones"][Path(path).name]["labels"][0]
                total = {"task-upstream": 8, "task-stub": 1, "task-partial": 5, "task-mutant": 5}.get(label, 3)
                scores = [f"S{min(2, max(0, total - index * 2))}" for index in range(4)]
                ratings.append(dict(zip(REFERENCE_RUBRIC["criteria"], scores), clone=path, reason="control"))
            value.append(ratings)
        state = out / "judges" / info["dir"] / "state/r1"
        state.mkdir(parents=True)
        repos.dump(state / "run.json", {"bound_inputs": inputs})
        write_memo({"state_root": state.parent}, [], value)
        pooling.scan_judge(out, judge, world.solution, home=world.tmp / "home")

    def reject_hidden_run(*args, **kwargs):
        raise AssertionError("calibration summaries must use retained hidden diagnostics")

    monkeypatch.setattr(summarize, "hidden_acceptance", reject_hidden_run)
    result = summarize.summarize(out, world.criterion)
    assert result["calibration"]["passed"] is True
    assert all(clone["hidden"] is None and clone["hidden_failed"] is None
               for clone in result["clones"].values())
    assert repos.load(out / "records/results.json")["calibration"] == result["calibration"]
    assert "Calibration:" in (out / "records/results.md").read_text()
    assert summarize.calibration_over([out / "records/results.json"], world.criterion)["passed"] is True


def test_calibration_does_not_reinterpret_structural_v1_quality_rules():
    criterion = {"purpose": "quality", "calibration": {"margin": 4, "error_rate": 0}}
    assert summarize.calibration({}, {"task": "/tasks/task"}, criterion) is None
