"""Generic calibration pools and complete-denominator verdicts; no provider calls."""

import json
from itertools import product
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
    results = {"judges": list(rule["judges"]), "excluded_judges": {}, "anchors": [
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
    session_home = Path(mapping["judges"]["judge-a"]["sandbox"]["home"])
    slug = "".join(char if char.isalnum() else "-" for char in str(home))
    project = session_home / ".claude/projects" / slug
    project.mkdir(parents=True)
    (project / "s.jsonl").write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "input": {"command": "python -m pytest tests/ && python dev_check.py"}}]}}) + "\n")
    hits = pooling.scan_judge(out, "judge-a", world.solution)
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
        pooling.scan_judge(out, judge, world.solution)

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


def test_absolute_calibration_pools_only_blind_clones_and_preserves_the_full_denominator(world, package):
    rule, diffs, _ = package
    rule["rubric"] = {**REFERENCE_RUBRIC, "workflow": "score_absolute.orc", "entry": "score_absolute::score",
                      "reference": None}
    repos.dump(world.criterion, rule)
    mapping = make_pool(world, diffs, out="absolute-calibration")
    out = world.outside / "absolute-calibration"
    assert not mapping.get("references")
    assert all(clone["arm"] != "reference" for clone in mapping["clones"].values())
    for batch in mapping["batches"]:
        assert len(batch) == 9
        assert sum(mapping["clones"][cid]["arm"] == "anchor" for cid in batch) == 4
    expected = {"task-upstream": 8, "task-stub": 1, "task-partial": 5, "task-mutant": 5}
    for judge, info in mapping["judges"].items():
        inputs = repos.load(out / "records" / f"score-inputs-{judge}.json")
        assert all(set(batch) == {"clones"} for batch in inputs["batches"])
        command = (out / "records" / f"score-{judge}.sh").read_text()
        assert "score_absolute.orc" in command and "--entry-workflow score_absolute::score" in command
        value = []
        for batch in inputs["batches"]:
            ratings = []
            for path in batch["clones"]:
                clone = mapping["clones"][Path(path).name]
                total = expected.get(clone["labels"][0], 3)
                scores = [f"S{min(2, max(0, total - index * 2))}" for index in range(4)]
                ratings.append(dict(zip(rule["rubric"]["criteria"], scores), clone=path, reason="control"))
            value.append(ratings)
        state = out / "judges" / info["dir"] / "state/r1"
        state.mkdir(parents=True)
        repos.dump(state / "run.json", {"bound_inputs": inputs})
        write_memo({"state_root": state.parent}, [], value)
        pooling.scan_judge(out, judge, world.solution)
    result = summarize.summarize(out, world.criterion)
    assert result["calibration"]["passed"] is True
    assert {(pair["judge"], pair["batch"]) for pair in result["calibration"]["pairs"]} == set(
        product(rule["judges"], range(len(mapping["batches"]))))
    for cid, clone in result["clones"].items():
        assert clone["score"] == expected.get(clone["labels"][0], 3)
        assert set(clone["ratings"]) == set(rule["judges"])
    result["judges"] = [rule["judges"][0]]
    incomplete = summarize.calibration(result, mapping, rule)
    assert len(incomplete["pairs"]) == len(rule["judges"]) * len(mapping["batches"])
    assert incomplete["passed"] is False


def control_means_rule(rule):
    return rule | {
        "rubric": {**REFERENCE_RUBRIC, "workflow": "score_absolute.orc", "entry": "score_absolute::score",
                   "reference": None},
        "calibration": {"rule": "control-means-v1", "margin": 1, "error_rate": 0},
        "anchors": {task: {role: label for role, label in roles.items() if role != "partial"}
                    for task, roles in rule["anchors"].items()}}


def control_means_observations(rule):
    mapping = {"task": "/tasks/task", "batches": [[], []]}
    results = {"judges": list(rule["judges"]), "excluded_judges": {}, "anchors": [
        {"judge": judge, "batch": batch, "anchor": label,
         "total": {"upstream": (4, 8), "stub": (4, 0), "mutant": (4, 0)}[role][batch]}
        for judge in rule["judges"] for batch in range(2)
        for role, label in rule["anchors"]["task"].items()]}
    return results, mapping


def test_control_means_accepts_aggregate_separation_despite_ties_and_spread(world, package):
    rule = control_means_rule(package[0])
    rule.pop("anchor_spread_limit")
    results, mapping = control_means_observations(rule)
    verdict = summarize.calibration(results, mapping, rule)
    assert verdict["passed"] is True
    assert verdict["rule"] == "control-means-v1"
    assert verdict["anchor_spread"]["judge-a"]["task-upstream"] == 4
    assert len(verdict["pairs"]) == len(rule["judges"]) * 2


@pytest.mark.parametrize("negative", ["stub", "mutant"])
def test_control_means_requires_separation_from_each_negative_for_every_judge(world, package, negative):
    rule = control_means_rule(package[0])
    results, mapping = control_means_observations(rule)
    for row in results["anchors"]:
        if row["judge"] == "judge-b" and row["anchor"] == f"task-{negative}":
            row["total"] = 6
    assert summarize.calibration(results, mapping, rule)["passed"] is False


@pytest.mark.parametrize("damage", ["missing_judge", "excluded", "missing_control", "duplicate", "none",
                                    "boolean", "nan", "infinity", "range", "missing_batch"])
def test_control_means_fails_incomplete_or_invalid_observations(world, package, damage):
    rule = control_means_rule(package[0])
    results, mapping = control_means_observations(rule)
    if damage == "missing_judge":
        results["judges"].remove("judge-b")
    elif damage == "excluded":
        results["excluded_judges"]["judge-b"] = "contaminated"
    elif damage == "missing_control":
        results["anchors"].pop()
    elif damage == "duplicate":
        results["anchors"].append(dict(results["anchors"][0]))
    elif damage == "missing_batch":
        mapping["batches"].append([])
    else:
        results["anchors"][0]["total"] = {
            "none": None, "boolean": True, "nan": float("nan"), "infinity": float("inf"), "range": 9}[damage]
    verdict = summarize.calibration(results, mapping, rule)
    assert verdict["passed"] is False
    assert len(verdict["pairs"]) == len(rule["judges"]) * len(mapping["batches"])


@pytest.mark.parametrize("change", [{"rule": "unknown"}, {"margin": 2}, {"error_rate": .1},
                                     {"mutant_margin": 2}, {"margin": True}])
def test_control_means_refuses_unknown_rules_and_configurable_parameters(world, package, change):
    rule = control_means_rule(package[0])
    results, mapping = control_means_observations(rule)
    rule["calibration"].update(change)
    with pytest.raises(SystemExit, match="calibration|control-means"):
        summarize.calibration(results, mapping, rule)


def test_control_means_pool_and_capacity_select_only_declared_controls(world, package):
    from experiments.orc_structural_search.scoring import fillers_per_batch
    rule = control_means_rule(package[0])
    repos.dump(world.criterion, rule)
    capacity = fillers_per_batch(world.task, rule["rubric"], world.criterion)
    assert capacity == 7
    mapping = make_pool(world, package[1], batches=1, per_batch=7, min_per_batch=7)
    assert len(mapping["batches"][0]) == 10
    assert {clone["labels"][0] for clone in mapping["clones"].values() if clone["arm"] == "anchor"} == {
        "task-upstream", "task-stub", "task-mutant"}
    assert (world.task / "anchors/task-partial.diff").is_file()


def test_control_means_calibration_over_ignores_spread_but_requires_every_pool(world, package):
    rule = control_means_rule(package[0])
    rule.pop("anchor_spread_limit")
    repos.dump(world.criterion, rule)
    paths = []
    for name, shift in (("A", 0), ("B2", -1)):
        results, mapping = control_means_observations(rule)
        for row in results["anchors"]:
            if row["anchor"] == "task-upstream":
                row["total"] += shift
        results.update(task=mapping["task"], criterion_sha256=repos.sha256_file(world.criterion),
                       calibration=summarize.calibration(results, mapping, rule))
        path = world.tmp / f"means-{name}.json"
        repos.dump(path, results)
        paths.append(path)
    assert summarize.calibration_over(paths, world.criterion)["passed"] is True
    results["calibration"]["passed"] = False
    repos.dump(paths[-1], results)
    assert summarize.calibration_over(paths, world.criterion)["passed"] is False


@pytest.mark.parametrize('totals,passed', [([(6, 0, 0, 4), (5, 0, 2, 3)], False),
                                         ([(8, 0, 5, 4), (6, 0, 5, 2)], True)], ids=['AT-PRR', 'AT-RPI'])
def test_historical_at_observations_keep_the_original_partial_order_gate(totals, passed):
    roles = ('upstream', 'stub', 'partial', 'mutant')
    criterion = {'purpose': 'calibration', 'judges': ['judge'],
                 'anchors': {'task': {role: role for role in roles}},
                 'calibration': {'margin': 4, 'mutant_margin': 2, 'error_rate': 0}, 'anchor_spread_limit': 2}
    mapping = {'task': '/tasks/task', 'batches': [[], []]}
    results = {'judges': ['judge'], 'anchors': [
        {'judge': 'judge', 'batch': batch, 'anchor': role, 'total': total}
        for batch, values in enumerate(totals) for role, total in zip(roles, values)]}
    verdict = summarize.calibration(results, mapping, criterion)
    assert verdict['passed'] is passed
    assert verdict['p2_failing'] == (0 if passed else .5)


@pytest.mark.parametrize('change', ['partial', 'duplicate', 'missing_file'])
def test_control_means_pool_refuses_invalid_declared_roles_before_creation(world, package, change):
    rule = control_means_rule(package[0])
    if change == 'partial':
        rule['anchors']['task']['partial'] = 'task-partial'
    elif change == 'duplicate':
        rule['anchors']['task']['mutant'] = 'task-stub'
    else:
        rule['anchors']['task']['mutant'] = 'absent-mutant'
    repos.dump(world.criterion, rule)
    with pytest.raises(SystemExit, match='anchor|role'):
        make_pool(world, package[1])
    assert not (world.outside / 'calibration').exists()
