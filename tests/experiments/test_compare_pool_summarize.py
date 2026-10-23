"""Comparison harness, scoring side (experiments/compare): blind pool, verify-pool, summarize.

Behaviour on temporary git repositories with a stand-in agent CLI and synthetic scoring runs written
where each judge's state directory holds them; see compare_harness_support.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from experiments.compare import pool as pooling, prepare, repos, summarize
from tests.experiments.compare_harness_support import (  # noqa: F401 (world and pooled are fixtures)
    REPO, call, drive, edit, pooled, skip_without_sandbox, start, world, write_memo, write_task,
)

skip_without_sandbox()

TOKENS = {  # (arm, last label) -> four Score tokens; judge-b rates the control's root cause one higher
    ("best_of_n", "cand-1"): ("S1",) * 4, ("best_of_n", "cand-2"): ("S2",) * 4,
    ("reviewed_change", "first"): ("S0",) * 4, ("reviewed_change", "final"): ("S2",) * 4,
    ("direct_task", "final"): ("S1",) * 4, ("anchor", "upstream"): ("S2",) * 4, ("anchor", "symptom"): ("S0",) * 4,
}


def rating(path, clone, judge):
    tokens = TOKENS[(clone["arm"], "upstream" if clone["labels"][-1].endswith("upstream") else clone["labels"][-1])]
    if judge == "judge-b" and clone["arm"] == "direct_task":
        tokens = ("S2",) + tokens[1:]
    return dict(zip(("root_cause", "scope", "generality", "layering"), tokens), clone=path, reason="r")


def score(out, judge, mapping, *, tamper=None, sha=None, run_id="r1", scanned=True, prompts=()):
    """Write a completed scoring run, with a provider start per prompt, where the judge's own --state-dir
    puts it, then scan the judge."""
    inputs = json.loads((out / "records" / f"score-inputs-{judge}.json").read_text())
    value = [[rating(path, mapping["clones"][Path(path).name], judge) for path in batch["clones"]]
             for batch in inputs["batches"]]
    if tamper:
        tamper(value)
    inputs["criterion_sha256"] = sha or inputs["criterion_sha256"]
    state = out / "judges" / mapping["judges"][judge]["dir"] / "state"
    (state / run_id).mkdir(parents=True)
    (state / run_id / "run.json").write_text(json.dumps({"bound_inputs": inputs}))
    write_memo({"state_root": state}, prompts, value, run_id=run_id)
    if scanned:
        pooling.scan_judge(out, judge, "f" * 40)


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


def test_pool_records_the_runtime_commit(pooled, world):
    assert pooled.mapping["runtime_commit"] == world.solution


def test_pool_refuses_a_runtime_with_uncommitted_changes_to_tracked_files(world):
    records, _ = drive(world, "direct_task", ["true"], True)
    (world.runtime / "README.md").write_text("edited\n")
    with pytest.raises(SystemExit, match="uncommitted changes to tracked files"):
        pooling.pool(world.task, world.criterion, world.outside / "pool", ["j"], [records])


def test_pool_refuses_a_run_resumed_after_its_scan(world):
    records, record = drive(world, "direct_task", ["true"], True)
    call(world, record, "true")
    write_memo(record, ["true", "true"], True)
    prepare.collect(records)
    with pytest.raises(SystemExit, match="the scan covers 1 calls but 2 were made"):
        pooling.pool(world.task, world.criterion, world.outside / "pool", ["j"], [records])


def test_pool_refuses_an_unscanned_run(world):
    records, record = start(world, "direct_task")
    call(world, record, "true")
    write_memo(record, ["true"], True)
    prepare.collect(records)
    with pytest.raises(SystemExit, match="scanned"):
        pooling.pool(world.task, world.criterion, world.outside / "pool", ["j"], [records])


def test_pool_refuses_a_run_with_hits_and_no_verdict(world):
    records, _ = drive(world, "direct_task", ["echo github.com"], True)
    with pytest.raises(SystemExit, match="1 scan hits and no verdict"):
        pooling.pool(world.task, world.criterion, world.outside / "pool", ["j"], [records])


def test_pool_excludes_contaminated_runs_and_includes_cleared_ones(world):
    dirty, _ = drive(world, "direct_task", ["echo github.com"], True, verdict=("contaminated", "read the fix"))
    cleared, _ = drive(world, "direct_task", ["echo github.com"], True, verdict=("cleared", "printed a URL"))
    clean, _ = drive(world, "direct_task", ["true"], True)
    mapping = pooling.pool(world.task, world.criterion, world.outside / "pool", ["j"], [dirty, cleared, clean])
    assert (mapping["runs"][str(dirty)]["excluded"],
            sorted({c["run"] for c in mapping["clones"].values() if c["run"]})) == (
        "contaminated: read the fix", sorted([str(cleared), str(clean)]))


def fable_session(home, directory):
    slug = "".join(c if c.isalnum() else "-" for c in str(directory))
    (home / ".claude/projects" / slug).mkdir(parents=True)
    (home / ".claude/projects" / slug / "s.jsonl").write_text(json.dumps(
        {"type": "assistant", "message": {"model": "claude-fable-5-1", "content": []}}) + "\n")


def test_pool_excludes_a_run_whose_sessions_answered_with_fable(world):
    records, record = start(world, "direct_task")
    call(world, record, "true")
    write_memo(record, ["true"], True)
    prepare.collect(records)
    fable_session(Path(record["sandbox"]["home"]), record["tree"])
    prepare.scan(records, world.solution)
    clean, _ = drive(world, "direct_task", ["true"], True)
    mapping = pooling.pool(world.task, world.criterion, world.outside / "pool", ["j"], [records, clean])
    assert (mapping["runs"][str(records)]["excluded"].startswith("Fable model"),
            {c["run"] for c in mapping["clones"].values() if c["run"]}) == (True, {str(clean)})


def run_judge_script(pooled, judge, script, *args):
    command = f"bash {pooled.out / 'records' / f'{script}-{judge}.sh'} {' '.join(args)}"
    return json.loads(subprocess.run(["bash", "-c", command], capture_output=True, text=True, check=True).stdout)


def test_judges_run_behind_the_shims_from_their_own_directory_and_state(pooled, world):
    home = str(pooled.out / "judges" / pooled.mapping["judges"]["judge-a"]["dir"])
    seen, resumed = run_judge_script(pooled, "judge-a", "score"), run_judge_script(pooled, "judge-a", "resume", "R1")
    assert (seen["cwd"], seen["path0"], seen["env"]["COMPARE_ROOT"], seen["env"]["COMPARE_TREE"],
            seen["argv"][-2:], resumed["argv"]) == (
        home, str(world.runtime / "experiments/compare/shim"), str(pooled.out / "records" / "judges" / "judge-a"),
        home, ["--state-dir", home + "/state"], ["resume", "R1", "--state-dir", home + "/state"])


def judge_session(pooled, world, judge, command):
    """A Claude CLI session file of the judge's working directory holding one shell action."""
    home = str(pooled.out / "judges" / pooled.mapping["judges"][judge]["dir"])
    session_home = Path(pooled.mapping["judges"][judge]["sandbox"]["home"])
    project = session_home / ".claude" / "projects" / "".join(c if c.isalnum() else "-" for c in home)
    project.mkdir(parents=True)
    (project / "s.jsonl").write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "input": {"command": command}}]}}) + "\n")


def test_judge_scan_finds_the_pool_records_and_other_judges(pooled, world):
    other = pooled.mapping["judges"]["judge-b"]["dir"]
    judge_session(pooled, world, "judge-a", f"cat {pooled.out}/records/mapping.json ../{other}/state")
    hits = pooling.scan_judge(pooled.out, "judge-a", "f" * 40)
    assert sorted(h["pattern"] for h in hits) == ["other tree or judge", "pool record files", "this pool's records"]


def test_judge_scan_finds_the_agents_trees(pooled, world):
    agents = Path(next(iter(pooled.mapping["runs"]))).parents[2] / "agents"
    judge_session(pooled, world, "judge-a", f"ls {agents}")
    hits = pooling.scan_judge(pooled.out, "judge-a", "f" * 40)
    assert [h["pattern"] for h in hits] == ["agents' trees"]


def test_summarize_refuses_judge_hits_without_a_verdict_and_leaves_out_a_contaminated_judge(pooled, world):
    judge_session(pooled, world, "judge-a", f"cat {pooled.out}/records/mapping.json")
    for judge in ("judge-a", "judge-b"):
        score(pooled.out, judge, pooled.mapping)
    with pytest.raises(SystemExit, match="judge judge-a has 2 scan hits and no verdict: prepare.py scan --pool"):
        summarize.summarize(pooled.out, world.criterion)
    pooling.adjudicate_judge(pooled.out, "judge-a", "contaminated", "read the mapping")
    results = summarize.summarize(pooled.out, world.criterion)
    assert (results["judges"], results["excluded_judges"]) == (
        ["judge-b"], {"judge-a": "contaminated: read the mapping"})


def test_summarize_leaves_out_a_judge_whose_sessions_answered_with_fable(pooled, world):
    fable_session(Path(pooled.mapping["judges"]["judge-a"]["sandbox"]["home"]),
                  pooled.out / "judges" / pooled.mapping["judges"]["judge-a"]["dir"])
    for judge in ("judge-a", "judge-b"):
        score(pooled.out, judge, pooled.mapping)
    with pytest.raises(SystemExit, match="Fable model"):
        pooling.adjudicate_judge(pooled.out, "judge-a", "cleared", "a probe")
    results = summarize.summarize(pooled.out, world.criterion)
    assert (results["judges"], results["excluded_judges"]["judge-a"].startswith("Fable model")) == (["judge-b"], True)


def judge_call(pooled, world, judge, script):
    """One call of the judge's CLI through the shims, recorded where its scoring command records them."""
    home = str(pooled.out / "judges" / pooled.mapping["judges"][judge]["dir"])
    record = {"records": str(pooled.out / "records" / "judges" / judge), "tree": home,
              "compare_base": pooled.mapping["compare_base"], "cwd": home,
              "sandbox": pooled.mapping["judges"][judge]["sandbox"]}
    assert call(world, record, script).returncode == 0


def test_summarize_pairs_a_judges_provider_starts_with_its_shim_call_records(pooled, world):
    judge_call(pooled, world, "judge-a", "true")
    score(pooled.out, "judge-a", pooled.mapping, prompts=["true"])
    score(pooled.out, "judge-b", pooled.mapping)
    assert summarize.summarize(pooled.out, world.criterion)["judges"] == ["judge-a", "judge-b"]


def test_summarize_refuses_a_judge_whose_provider_starts_have_no_shim_call_records(pooled, world):
    score(pooled.out, "judge-a", pooled.mapping, prompts=["true"])
    score(pooled.out, "judge-b", pooled.mapping)
    with pytest.raises(SystemExit, match="1 provider starts in the memo but 0 call directories"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_refuses_an_unscanned_judge(pooled, world):
    score(pooled.out, "judge-a", pooled.mapping)
    score(pooled.out, "judge-b", pooled.mapping, scanned=False)
    with pytest.raises(SystemExit, match="judge judge-b has not been scanned"):
        summarize.summarize(pooled.out, world.criterion)


def test_verify_pool_restores_a_clone_holding_an_ignored_file(pooled, capsys):
    clone = pooled.out / "clones" / next(iter(pooled.mapping["clones"]))
    (clone / "artifacts").mkdir()
    (clone / "artifacts/x.md").write_text("judge notes\n")
    with pytest.raises(SystemExit, match="restored"):
        pooling.verify_pool(pooled.out)
    assert ((clone / "artifacts").exists(), "artifacts/ (ignored)" in capsys.readouterr().out) == (False, True)


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


@pytest.mark.parametrize(("token", "expected"), [("S0", 0), ("S3", 3), ("S8", 8)])
def test_quality_rubric_joins_its_single_functional_score(token, expected, tmp_path):
    clone = str(tmp_path / "pool/clones/a1b2c3d4")
    mapping = {"rubric": {"criteria": ["quality"]}}
    ratings = [[{"clone": clone, "quality": token, "reason": "functional behavior"}]]

    joined = summarize.join(tmp_path, [{"clones": [clone]}], ratings, [["a1b2c3d4"]],
                            criteria=summarize.criteria_of(mapping))

    assert joined["a1b2c3d4"]["quality"] == expected


@pytest.mark.parametrize("token", ["S9", "unknown", 8])
def test_quality_rubric_rejects_unknown_or_out_of_range_tokens(token, tmp_path):
    clone = str(tmp_path / "pool/clones/a1b2c3d4")
    ratings = [[{"clone": clone, "quality": token, "reason": "invalid"}]]

    with pytest.raises(SystemExit, match="quality"):
        summarize.join(tmp_path, [{"clones": [clone]}], ratings, [["a1b2c3d4"]], criteria=("quality",))


def test_quality_rubric_must_not_mix_with_component_criteria():
    with pytest.raises(SystemExit, match="quality.*only"):
        summarize.criteria_of({"rubric": {"criteria": ["quality", "scope"]}})


def test_historical_component_rubric_still_rejects_s3(tmp_path):
    clone = str(tmp_path / "pool/clones/a1b2c3d4")
    ratings = [[{"clone": clone, "completeness": "S3", "reason": "invalid"}]]

    with pytest.raises(SystemExit, match="completeness.*S3"):
        summarize.join(tmp_path, [{"clones": [clone]}], ratings, [["a1b2c3d4"]], criteria=("completeness",))


def test_quality_rubric_keeps_the_clone_id_position_check(tmp_path):
    clone = str(tmp_path / "pool/clones/a1b2c3d4")
    ratings = [[{"clone": "other-clone", "quality": "S8", "reason": "complete"}]]

    with pytest.raises(SystemExit, match="batch 0 position 0"):
        summarize.join(tmp_path, [{"clones": [clone]}], ratings, [["a1b2c3d4"]], criteria=("quality",))


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


def test_summarize_refuses_a_criterion_naming_other_judges(pooled, world):
    other = world.tmp / "other-judges.json"
    other.write_text(json.dumps({**json.loads(world.criterion.read_text()), "judges": ["judge-a"]}))
    with pytest.raises(SystemExit, match=r"criterion names judges \['judge-a'\] but the pool has"):
        summarize.summarize(pooled.out, other)


def test_summarize_refuses_unless_every_judge_has_exactly_one_scoring_run(pooled, world):
    score(pooled.out, "judge-a", pooled.mapping)
    pooling.scan_judge(pooled.out, "judge-b", "f" * 40)
    with pytest.raises(SystemExit, match="judge judge-b: expected one scoring run.*found 0"):
        summarize.summarize(pooled.out, world.criterion)
    score(pooled.out, "judge-b", pooled.mapping)
    score(pooled.out, "judge-b", pooled.mapping, run_id="r2")
    with pytest.raises(SystemExit, match="judge judge-b: expected one scoring run.*found 2"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_runs_hidden_acceptance_in_an_untouched_copy_without_git_and_lists_failing_nodes(world):
    task = world.tmp / "task-hidden"
    write_task(task, world.base, anchors=False, hidden=True)
    own_test = "mkdir -p tests && printf 'def test_missing():\\n    pass\\n' > tests/test_hidden.py"
    records, _ = drive(world, "direct_task", [edit("$PWD", "a + b") + own_test], True, task=task)
    out, criterion = world.outside / "pool-hidden", world.tmp / "criterion-one-judge.json"
    criterion.write_text(json.dumps({**json.loads(world.criterion.read_text()), "judges": ["judge-a"]}))
    mapping = pooling.pool(task, criterion, out, ["judge-a"], [records])
    score(out, "judge-a", mapping)
    results = summarize.summarize(out, criterion)
    pooling.verify_pool(out)
    failed = [clone["hidden_failed"] for clone in results["clones"].values()]
    assert (results["measures"]["direct_task.hidden_mean"], failed) == (
        pytest.approx(3 / 4), [["tests/test_hidden.py::test_missing"]])


def test_reviewed_change_hidden_paired_gain_is_the_final_minus_the_first_hidden_fraction():
    values = summarize.run_values("reviewed_change", None, {"first": 3, "final": 5}, {"first": 0.25, "final": 0.75})
    rows = [{"arm": "reviewed_change", "calls": 4, "wall_clock_sec": 60, **values}]
    assert summarize.measures(rows)["reviewed_change.hidden_paired_gain_mean"] == 0.5


REFERENCE_RUBRIC = {"workflow": "score_ref.orc", "entry": "score_ref::score",
                    "criteria": ["completeness", "correctness", "scope", "layering"], "reference": "upstream"}


@pytest.fixture
def reference_pool(world):
    frozen = json.loads(world.criterion.read_text()) | {"rubric": REFERENCE_RUBRIC}
    world.criterion.write_text(json.dumps(frozen))
    upstream = world.task / "anchors/upstream.diff"
    upstream.rename(world.task / "anchors/task-upstream.diff")
    run, _ = drive(world, "direct_task", [edit("$PWD", "a + b")], True)
    out = world.outside / "reference-pool"
    mapping = pooling.pool(world.task, world.criterion, out, ["judge-a", "judge-b"], [run])
    return out, mapping


def reference_scores(out, mapping, world):
    def rename(value):
        for batch in value:
            for row in batch:
                row["completeness"] = row.pop("root_cause")
                row["correctness"] = row.pop("generality")
    for judge in mapping["judges"]:
        score(out, judge, mapping, tamper=rename)


def test_pool_with_a_reference_rubric_adds_one_reference_clone_per_batch_outside_the_blind_list(reference_pool):
    out, mapping = reference_pool
    assert len(mapping["references"]) == len(mapping["batches"]) == 1
    for judge in mapping["judges"]:
        inputs = repos.load(out / "records" / f"score-inputs-{judge}.json")
        for batch, ids, cid in zip(inputs["batches"], mapping["batches"], mapping["references"]):
            assert mapping["clones"][cid]["arm"] == "reference"
            assert cid not in ids
            assert batch["reference"] == str(out / "clones" / cid)
            assert batch["reference"] not in batch["clones"]
        command = (out / "records" / f"score-{judge}.sh").read_text()
        assert "score_ref.orc" in command and "--entry-workflow score_ref::score" in command


def test_summarize_joins_the_pools_criteria_names_and_reports_them(reference_pool, world):
    out, mapping = reference_pool
    reference_scores(out, mapping, world)
    results = summarize.summarize(out, world.criterion)
    assert set(results["agreement"]) == set(REFERENCE_RUBRIC["criteria"])
    assert all(0 <= row["score"] <= 8 for row in results["clones"].values() if row["arm"] != "reference")
    assert any(row["total"] == 8 for row in results["anchors"])


def test_summarize_skips_reference_clones_everywhere(reference_pool, world, monkeypatch):
    out, mapping = reference_pool
    (world.task / "hidden").mkdir()
    (world.task / "hidden_tests.txt").write_text("tests/hidden.py::test_add\n")
    checked = []
    monkeypatch.setattr(summarize, "hidden_failures", lambda clone, *args: checked.append(clone.name) or [])
    reference_scores(out, mapping, world)
    results = summarize.summarize(out, world.criterion)
    for cid in mapping["references"]:
        row = results["clones"][cid]
        assert (row["score"], row["hidden"], row["ratings"]) == (None, None, {})
        assert cid not in checked
        assert all(cid not in run["scores"] for run in results["runs"])
        assert all(anchor["anchor"] != "reference" for anchor in results["anchors"])


def test_summarize_refuses_a_criterion_whose_rubric_differs_from_the_pools(pooled, world):
    world.criterion.write_text(json.dumps(repos.load(world.criterion) | {"rubric": REFERENCE_RUBRIC}))
    with pytest.raises(SystemExit, match="rubric"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_reads_a_mapping_without_rubric_as_the_historical_rubric(pooled, world):
    pooled.mapping.pop("rubric", None)
    repos.dump(pooled.out / "records/mapping.json", pooled.mapping)
    for judge in pooled.mapping["judges"]:
        score(pooled.out, judge, pooled.mapping)
    assert set(summarize.summarize(pooled.out, world.criterion)["agreement"]) == set(summarize.CRITERIA)


def test_pool_batches_carry_every_package_anchor_and_stay_within_ten(world):
    from experiments.orc_structural_search import scoring
    (world.task / "anchors/upstream.diff").rename(world.task / "anchors/task-upstream.diff")
    patch = (world.task / "anchors/symptom.diff").read_bytes()
    for name in ("partial", "mutant"):
        (world.task / f"anchors/{name}.diff").write_bytes(patch)
    world.criterion.write_text(json.dumps(repos.load(world.criterion) | {"rubric": REFERENCE_RUBRIC}))
    records, record = drive(world, "direct_task", [edit("$PWD", "a + b")], True)
    ref = repos.load(records / "record.json")
    finals = [(str(records), ref, ["final"])] * 11
    capacity = scoring.fillers_per_batch(world.task, REFERENCE_RUBRIC)
    assert capacity == 5
    batches = scoring.split_batches(finals, key=lambda row: row[0], size=capacity)
    mapping = pooling.write_pool(world.task, world.criterion, world.outside / "four-anchors", ["judge-a"],
                                 ref, {}, batches)
    assert len(mapping["batches"]) == 3
    for batch in mapping["batches"]:
        assert sum(mapping["clones"][cid]["arm"] == "anchor" for cid in batch) == 4
        assert len(batch) + 1 <= 10
    with pytest.raises(SystemExit, match="ten|10"):
        pooling.write_pool(world.task, world.criterion, world.outside / "overflow", ["judge-a"], ref, {}, [finals[:6]])
    assert not (world.outside / "overflow").exists()


def test_summarize_refuses_a_reference_bound_to_another_clone(reference_pool, world):
    out, mapping = reference_pool
    reference_scores(out, mapping, world)
    run = out / "judges" / mapping["judges"]["judge-a"]["dir"] / "state/r1/run.json"
    header = repos.load(run)
    header["bound_inputs"]["batches"][0]["reference"] = str(out / "clones" / mapping["batches"][0][0])
    repos.dump(run, header)
    with pytest.raises(SystemExit, match="reference"):
        summarize.summarize(out, world.criterion)
