"""Seed-set ladder builder: tier assignment, statements, squashed topic runs, carried rejections, T0 hints, and
the check-withheld form on a real task package."""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from experiments.compare import repos
from experiments.seed_set import build_tasks as b, forms, tiers
from tests.experiments.seed_set_offline_support import manifest_rows, stable_anchors
from experiments.seed_set.programs import dev_check

REAL = b.HERE / "tasks" / "1f424cc9ae"  # a T3 package whose visible check runs in about a second


@pytest.mark.parametrize("files, lines, added, subject, run, tier", [
    (1, 20, 5, "fix: x", False, "T1"), (1, 21, 5, "fix: x", False, "T2"), (2, 60, 30, "fix: x", False, "T2"),
    (3, 61, 30, "fix: x", False, "T3"), (6, 50, 30, "fix: x", False, "T4"), (5, 200, 100, "fix: x", False, "T4"),
    (16, 100, 50, "fix: x", False, None), (5, 601, 300, "fix: x", False, None),
    (3, 400, 350, "feat(a): x", False, "T5"), (9, 1100, 1000, "feat(a): x", False, None),
    (9, 1300, 1200, "feat(a): x", True, "T6"), (4, 320, 299, "feat(a): x", True, None),
])
def test_tier_of_assigns_each_size_to_one_tier(files, lines, added, subject, run, tier):
    assert tiers.tier_of(files, lines, added, subject, run=run) == tier


def test_t1_statement_names_the_changed_file():
    cand = {"message": "fix: x\n\nbody", "source_files": ["orchestrator/a.py"]}
    assert tiers.tier_statement("T1", cand).endswith("The change is in orchestrator/a.py.\n")


def test_t2_bodyless_short_statement_adds_the_file_names():  # the recorded M8 deviation keeps this
    cand = {"message": "fix: x", "source_files": ["orchestrator/a.py", "orchestrator/b.py"]}
    assert tiers.tier_statement("T2", cand) == "fix: x\n\nThe change is in orchestrator/a.py and orchestrator/b.py.\n"


def test_t2_statement_with_a_body_is_the_message():
    cand = {"message": "fix: x\n\nshort body", "source_files": ["orchestrator/a.py"]}
    assert tiers.tier_statement("T2", cand) == "fix: x\n\nshort body\n"


def test_t4_statement_is_the_message_even_when_short():
    cand = {"message": "fix: x", "source_files": ["orchestrator/a.py"]}
    assert tiers.tier_statement("T4", cand) == "fix: x\n"


def test_carried_keeps_only_statement_independent_rejections():
    rows = [{"reason": "1 fail-to-pass function(s), need 2"}, {"reason": "statement under 80 characters"},
            {"reason": None}, {"reason": "admitted"}]
    assert [tiers.carried(r) for r in rows] == ["1 fail-to-pass function(s), need 2", None, None, None]


@pytest.mark.parametrize("reason", ["beyond the tier's cap", "not evaluated: tier full"])
def test_a_ladder_builds_unreached_or_capped_candidate_is_not_a_rejection(reason):  # a ladder screening as prior
    assert tiers.carried({"reason": reason}) is None


def commit(repo, files, message, date="2026-08-01T00:00:00+0000"):
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                    "--no-gpg-sign", "-m", message], check=True, env=env)
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture(scope="module")
def topic(tmp_path_factory):
    repo = tmp_path_factory.mktemp("topic")
    subprocess.run(["git", "init", "-q", repo], check=True)
    root = commit(repo, {".gitignore": ".orchestrate/\n", "orchestrator/__init__.py": ""}, "init",
                  "2026-06-01T00:00:00+0000")
    big = "".join(f"def f{i}():\n    return {i}\n" for i in range(160))
    shas = [commit(repo, {"orchestrator/big.py": big, "tests/test_big.py": "def test_a():\n    pass\n"},
                   "feat(big): add the big module"),
            commit(repo, {"orchestrator/big.py": big + "X = 1\n", "tests/test_big.py": "def test_b():\n    pass\n"},
                   "fix(big): set X"),
            commit(repo, {"README.md": "notes\n"}, "docs: notes")]
    return repo, root, shas


def test_topic_runs_group_consecutive_commits_of_one_scope(topic):
    repo, _, shas = topic
    assert [[c[0] for c in run] for run in tiers.topic_runs(repo, "HEAD")] == [shas[:2]]


def test_run_candidate_squashes_from_the_first_parent_to_the_last_commit(topic):
    repo, root, shas = topic
    cand, _ = tiers.run_candidate(repo, tiers.topic_runs(repo, "HEAD")[0])
    assert (cand["parent"], cand["commit"], cand["statement"], cand["tier"]) == (
        root, shas[1], "feat(big): add the big module\nfix(big): set X\n", "T5")


def test_failure_lines_keep_the_assertion_without_the_clone_path():
    output = "/w/clone/tests/test_x.py:3: in test_y\n    assert f() == 2\nE   assert 1 == 2\nE    +  where 1 = f()\n"
    assert forms.failure_lines(output, "/w/clone") == ["E   assert 1 == 2", "E    +  where 1 = f()"]


def test_t0_hint_extends_both_statements_and_renames_the_anchors(tmp_path):
    pkg = tmp_path / "abc"
    (pkg / "anchors").mkdir(parents=True)
    (pkg / "anchors/abc-upstream.diff").write_text("")
    (pkg / "intent.txt").write_text("fix: x\n")
    (pkg / "task.txt").write_text("fix: x\nVisible check: run it.\n")
    forms.hinted(pkg, tmp_path / "abc-t0", ["E   assert 1 == 2"])
    out = tmp_path / "abc-t0"
    assert ((out / "task.txt").read_text(), sorted(p.name for p in (out / "anchors").iterdir())) == (
        "fix: x\n\nThe check currently fails with:\n    E   assert 1 == 2\nVisible check: run it.\n",
        ["abc-t0-upstream.diff"])


@pytest.fixture(scope="module")
def withheld_clone(tmp_path_factory):
    if not REAL.is_dir():
        pytest.skip("the real T3 package is not built")
    work = tmp_path_factory.mktemp("withheld")
    pkg = work / "1f424cc9ae-withheld"
    forms.withhold(REAL, pkg)
    clone = work / "clone"
    repos.build_candidate(b.ROOT, (pkg / "base_commit").read_text().strip(), pkg / "seed", clone)
    return pkg, clone


def defined(clone, names):
    found = subprocess.run(["grep", "-rlE", "--include=*.py", "--exclude-dir=.git",
                            rf"def ({'|'.join(map(re.escape, names))})\b", str(clone / "tests")],
                           capture_output=True, text=True).stdout
    return found.split()


def test_withheld_tree_defines_no_visible_or_hidden_test_function(withheld_clone):
    pkg, clone = withheld_clone
    names = [n.split("::")[-1] for n in (pkg / "hidden_tests.txt").read_text().split() if "::" in n]
    visible = json.loads((pkg / "seed/dev-check.json").read_text())["argv"][-1].split("::")[-1]
    assert defined(clone, [*names, visible]) == []


def test_withheld_check_fails_on_the_base_and_leaves_the_tree_as_it_was(withheld_clone):
    pkg, clone = withheld_clone
    before = forms.tree_digest(clone)
    assert (dev_check.check(clone, pkg / "withheld")["passed"], forms.tree_digest(clone)) == (False, before)


def test_withheld_check_restores_the_tree_after_a_timeout(withheld_clone):
    pkg, clone = withheld_clone
    config = clone / "dev-check.json"
    original = config.read_text()
    config.write_text(json.dumps({**json.loads(original), "timeout_sec": 0.5}))
    before = forms.tree_digest(clone)
    try:
        report = dev_check.check(clone, pkg / "withheld")
        assert (report["failing"], forms.tree_digest(clone)) == (["timeout after 0.5s"], before)
    finally:
        config.write_text(original)


def test_withheld_check_without_its_source_fails_closed(withheld_clone):
    _, clone = withheld_clone
    assert dev_check.check(clone, Path("/nonexistent"))["failing"] == ["withheld check source unavailable"]


def test_withheld_check_passes_with_the_reference_fix_and_leaves_the_tree_as_it_was(withheld_clone):
    pkg, clone = withheld_clone
    repos.git(clone, "apply", "--binary", str(pkg / "anchors" / f"{pkg.name}-upstream.diff"))
    try:
        before = forms.tree_digest(clone)
        assert (dev_check.check(clone, pkg / "withheld")["passed"], forms.tree_digest(clone)) == (True, before)
    finally:
        repos.git(clone, "apply", "-R", "--binary", str(pkg / "anchors" / f"{pkg.name}-upstream.diff"))


def test_an_unstable_package_rejects_its_row_and_its_probe_flag_moves_to_the_next_usable_task():
    rows = manifest_rows({"T2": 7, "T3": 6})
    stability = {"T3-01": {"stable": False, "reference_failing": [], "runs": [
                     {"T3-01-base": ["tests/test_x.py", "tests/test_y.py"], "T3-01-upstream": []},
                     {"T3-01-base": ["tests/test_y.py"], "T3-01-upstream": []}]},  # test_x varies on the base
                 "T2w-02": {"stable": False, "reference_failing": ["tests/test_y.py::t"]}}
    out = tiers.reject_unstable(rows, stability)
    by = {r["id"]: r for r in out}
    assert ([r["id"] for r in out if r.get("probe") and r["tier"] == "T3"],
            [r["id"] for r in out if r.get("probe") and r["tier"] == "T2"],
            by["T3-01"]["rejected"], by["T2-02"]["rejected"]) == (
        ["T3-00", "T3-02", "T3-03", "T3-04"], ["T2-00", "T2-01", "T2-03", "T2-04"],
        "anchor not stable under study conditions: tests/test_x.py",
        "anchor not stable under study conditions: T2w-02: tests/test_y.py::t")


def test_an_unstable_smoke_moves_the_smoke_to_the_first_usable_t2_task_that_is_not_a_probe_task():
    rows = manifest_rows({"T2": 7})
    out = tiers.reject_unstable(rows, {"smoke": {"stable": False, "reference_failing": []}})
    assert [r["id"] for r in out if r["set"] == "smoke"] == ["T2-04"]


def test_the_anchor_check_resumes_past_packages_recorded_at_their_current_hash(tmp_path, monkeypatch):
    from experiments.seed_set import anchors
    rows = manifest_rows({"T3": 2}, smoke=False)
    (tmp_path / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    done = {"T3-00": {"sha256": b.package_hash(tmp_path / "tasks" / "T3-00"), "stable": True,
                      "scoring_path": anchors.scoring_path_hash()},
            "T3-01": {"sha256": b.package_hash(tmp_path / "tasks" / "T3-01"), "stable": True,
                      "scoring_path": "0" * 64}}  # measured under another scoring path: checked again
    (tmp_path / anchors.FILE).write_text(json.dumps(done))
    checked = []
    monkeypatch.setattr(anchors, "check", lambda package, work: checked.append(package.name) or {"stable": True,
                        "sha256": "x", "reference_failing": [], "runs": []})
    anchors.run(tmp_path / "work", out=tmp_path)
    assert sorted(checked) == ["T3-01", "T3w-00", "T3w-01"]


def test_the_anchor_check_records_the_scoring_path_on_every_entry_it_writes(tmp_path, monkeypatch):
    from experiments.seed_set import anchors
    (tmp_path / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in manifest_rows({"T3": 1}, smoke=False)))
    monkeypatch.setattr(anchors, "check", lambda package, work: {"stable": True, "sha256": "x",
                                                                 "reference_failing": [], "runs": []})
    anchors.run(tmp_path / "work", out=tmp_path)
    written = json.loads((tmp_path / anchors.FILE).read_text())
    assert {pid: e.get("scoring_path") for pid, e in written.items()} == dict.fromkeys(
        ["T3-00", "T3w-00"], anchors.scoring_path_hash())


def kit_tree(root):
    """A copy of the scoring path's shape: kit modules, a task package's module and a data file."""
    for relative in ("experiments/seed_set/anchors.py", "experiments/seed_set/tasks/p/fix.py",
                     "experiments/seed_set/tasks.jsonl", "experiments/compare/pool.py"):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(f"# {relative}\n")
    return root


@pytest.mark.parametrize("edited, changes", [("experiments/seed_set/anchors.py", True),
                                             ("experiments/compare/pool.py", True),
                                             ("experiments/seed_set/tasks/p/fix.py", False),
                                             ("experiments/seed_set/tasks.jsonl", False)])
def test_the_scoring_path_hash_follows_the_kit_modules_only(tmp_path, edited, changes):
    from experiments.seed_set import anchors
    root = kit_tree(tmp_path)
    before = anchors.scoring_path_hash(root)
    (root / edited).write_text((root / edited).read_text() + " ")
    assert (anchors.scoring_path_hash(root) != before) is changes


def verified_kit(out, scoring_path):
    """A kit directory of one T3 task (both forms) whose packages hash as listed, with stable anchors measured under
    `scoring_path` (see `stable_anchors`)."""
    rows = manifest_rows({"T3": 1}, smoke=False)
    for row in rows:
        for pid, key in ((row["id"], "package_sha256"), (row["withheld_id"], "withheld_sha256")):
            (out / "tasks" / pid).mkdir(parents=True)
            (out / "tasks" / pid / "f").write_text(pid)
            row[key] = b.package_hash(out / "tasks" / pid)
    (out / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    stable_anchors(out / "tasks.jsonl", scoring_path=scoring_path)
    return out


def test_verify_accepts_anchors_measured_under_the_current_scoring_path(tmp_path):
    assert tiers.verify(verified_kit(tmp_path, "current")) is None


@pytest.mark.parametrize("scoring_path", ["0" * 64, None])
def test_verify_refuses_anchors_measured_under_another_or_no_scoring_path(tmp_path, scoring_path):
    with pytest.raises(SystemExit, match=r"T3-00 \(other scoring path\)"):
        tiers.verify(verified_kit(tmp_path, scoring_path))


@pytest.mark.parametrize("entry, reason", [  # "now": the current package hash or scoring path
    ({"sha256": "now", "stable": True, "scoring_path": "0" * 64}, "other scoring path"),
    ({"sha256": "now", "stable": True}, "other scoring path"),
    ({"sha256": "now", "stable": False, "scoring_path": "now"}, "unstable"),
    ({"sha256": "0" * 64, "stable": True, "scoring_path": "now"}, "not measured"),
    (None, "not measured")])
def test_unstable_names_each_package_without_a_stable_anchor_and_why(tmp_path, entry, reason):
    from experiments.seed_set import anchors
    now = {"sha256": b.package_hash(tmp_path / "T3-00"), "scoring_path": anchors.scoring_path_hash()}
    stability = {"T3w-00": now | {"stable": True}}
    if entry:
        stability["T3-00"] = {k: now[k] if v == "now" else v for k, v in entry.items()}
    assert anchors.unstable(manifest_rows({"T3": 1}, smoke=False), stability, tmp_path) == [f"T3-00 ({reason})"]


def build_world(tmp_path, monkeypatch):
    """A first build of six drawn T3 rows, a smoke T3 row and an old T1 row, and a ladder pool of one T1 fix and one
    T1 non-fix, two T2 fixes, one T4 and one T5, every collaborator of `tiers.build` that runs git, the oracle or
    the leak audit replaced by its recorded answer (t3-1 fails the leak audit, b has no T0 variant)."""
    out, work = tmp_path / "out", tmp_path / "work"
    old = [{"id": f"t3-{k}", "commit": f"c{k}", "tier": "T3", "set": "drawn", "source_files": ["orchestrator/a.py"],
            "source_lines": 10, "subject": "fix: a"} for k in range(6)]
    old += [{"id": "sm", "commit": "cs", "set": "smoke", "source_files": ["x", "y", "z"], "source_lines": 100,
             "subject": "fix: s"},
            {"id": "old-t1", "commit": "co", "tier": "T1", "set": "ladder", "source_files": ["x"], "source_lines": 3,
             "subject": "fix: o"}]
    out.mkdir()
    (out / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in old))
    for r in old:
        (out / "tasks" / r["id"]).mkdir(parents=True)
        (out / "tasks" / r["id"] / "f").write_text(r["id"])
    pool = [{"id": i, "tier": t, "message": m, "commit": f"k{i}", "rank": n, "subject": m, "parent": f"p{i}",
             "source_files": [f"orchestrator/{i}.py"], "source_lines": 5, "source_added": 3, "nontest_lines": 5,
             "tests": [f"tests/test_{i}.py"], "repo": str(tmp_path)}
            for n, (i, t, m) in enumerate([("a", "T1", "fix: a"), ("b", "T1", "feat: b"), ("c", "T2", "fix: c"),
                                           ("d", "T2", "fix: d"), ("e", "T4", "feat: e"), ("f", "T5", "feat: f")])]
    for name in [f"{r['id']}-withheld" for r in old] + [i for c in pool for i in (c["id"], f"{c['id']}-withheld")]:
        (work / "pkgs" / name).mkdir(parents=True)
        (work / "pkgs" / name / "f").write_text(name)
    evaluated, verified = [], []

    def fake_candidates(repo, tip, t3_ids, record):
        record.append({"id": "mined", "stage": "mine", "reason": f"t3 ids {sorted(t3_ids)}"})
        return [dict(c) for c in pool]

    def fake_evaluate(cands, rows, prior, work_, workers, runs):
        evaluated.append([c["id"] for c in cands])
        for c in cands:
            rows[c["id"]] = {"id": c["id"], "commit": c["commit"], "stage": "evaluate", "reason": "admitted",
                             "visible": ["v"], "hidden": ["h"], "package_sha256": f"p-{c['id']}",
                             "withheld_sha256": f"w-{c['id']}", "clone": "/x", "base_outputs": []}
        return list(cands), {}

    def fake_t0(cand, row, staged):
        if cand["id"] != "a":
            return None, "the base runs' failure lines differ or are empty"
        (staged / "a-t0").mkdir()
        (staged / "a-t0" / "f").write_text("hint")
        return "a-t0", None

    monkeypatch.setenv("PATH", f"{b.GUARD}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(tiers, "CAP", 2)
    monkeypatch.setattr(tiers, "candidates", fake_candidates)
    monkeypatch.setattr(tiers, "evaluate_tier", fake_evaluate)
    monkeypatch.setattr(tiers, "t0_variant", fake_t0)
    monkeypatch.setattr(tiers, "t3_withheld_checks", lambda t3, *_: [
        {"id": r["id"], "stage": "withheld", "withheld_sha256": f"w-{r['id']}"} for r in t3])
    monkeypatch.setattr(tiers.leak_audit, "audit", lambda package, *_: [("leak", "names the fix")]
                        if package.name.startswith("t3-1") else [])
    monkeypatch.setattr(tiers, "verify", verified.append)
    return out, work, evaluated, verified


def test_build_writes_each_tiers_manifest_rows_packages_and_screening_records(tmp_path, monkeypatch):
    """Characterization of `tiers.build`, pinned before its split (re-review of fix round 1, minor 9)."""
    out, work, evaluated, verified = build_world(tmp_path, monkeypatch)
    tiers.build(work, 1, 5, out=out, repo=tmp_path, tip="TIP")
    lines = [json.loads(line) for line in (out / "tasks.jsonl").read_text().splitlines()]
    records = [json.loads(line) for line in (out / "ladder_screening.jsonl").read_text().splitlines()]
    assert ([(r["id"], r["tier"], r["form"], r["probe"], r.get("widened"), r.get("rejected"), r["withheld_id"],
              r["withheld_sha256"], r.get("variant_of")) for r in lines],
            sorted(p.name for p in (out / "tasks").iterdir()),
            [(r["id"], r["stage"], r.get("tier"), r.get("reason"), r["tip"]) for r in records if r["id"] != "mined"],
            [r["reason"] for r in records if r["id"] == "mined"], evaluated, verified,
            (out / "tasks" / "a-t0" / "f").read_text(), (out / "tasks_new").exists()) == (
        [("t3-0", "T3", "in_tree", True, None, None, "t3-0-withheld", "w-t3-0", None),
         ("t3-1", "T3", "in_tree", False, None, "leak audit: t3-1: leak: names the fix", "t3-1-withheld", "w-t3-1",
          None),
         ("t3-2", "T3", "in_tree", True, None, None, "t3-2-withheld", "w-t3-2", None),
         ("t3-3", "T3", "in_tree", True, None, None, "t3-3-withheld", "w-t3-3", None),
         ("t3-4", "T3", "in_tree", True, None, None, "t3-4-withheld", "w-t3-4", None),
         ("t3-5", "T3", "in_tree", False, None, None, "t3-5-withheld", "w-t3-5", None),
         ("sm", "T3", "in_tree", False, None, None, "sm-withheld", "w-sm", None),
         ("a", "T1", "in_tree", True, True, None, "a-withheld", "w-a", None),
         ("a-t0", "T0", "in_tree", True, True, None, None, None, "a"),
         ("b", "T1", "in_tree", True, True, None, "b-withheld", "w-b", None),
         ("c", "T2", "in_tree", True, False, None, "c-withheld", "w-c", None),
         ("d", "T2", "in_tree", True, False, None, "d-withheld", "w-d", None),
         ("e", "T4", "in_tree", True, False, None, "e-withheld", "w-e", None),
         ("f-withheld", "T5", "withheld", True, False, None, None, None, None)],
        sorted(["a", "a-t0", "a-withheld", "b", "b-withheld", "c", "c-withheld", "d", "d-withheld", "e", "e-withheld",
                "f-withheld"] + [n for k in range(6) for n in (f"t3-{k}", f"t3-{k}-withheld")] + ["sm", "sm-withheld"]),
        [(i, s, "T3", reason, "TIP") for t in [f"t3-{k}" for k in range(6)] + ["sm"]
         for i, s, reason in ((t, "withheld", None), (t, "t3-audit", "leak audit: t3-1: leak: names the fix"
                                                     if t == "t3-1" else "clean"))]
        + [("a-t0", "t0", "T0", "admitted", "TIP"),
           ("b-t0", "t0", "T0", "the base runs' failure lines differ or are empty", "TIP"),
           ("a", "evaluate", "T1", "admitted", "TIP"), ("b", "evaluate", "T1", "admitted", "TIP"),
           ("c", "evaluate", "T2", "admitted", "TIP"), ("d", "evaluate", "T2", "admitted", "TIP"),
           ("e", "evaluate", "T4", "admitted", "TIP"), ("f", "evaluate", "T5", "admitted", "TIP")],
        ["t3 ids ['sm', 't3-0', 't3-1', 't3-2', 't3-3', 't3-4', 't3-5']"],
        [["a"], ["a", "b"], ["c", "d"], ["e"], ["f"], []], [out], "hint", False)


def test_build_refuses_a_first_build_row_whose_withheld_form_failed(tmp_path, monkeypatch):
    out, work, _, verified = build_world(tmp_path, monkeypatch)
    monkeypatch.setattr(tiers, "t3_withheld_checks", lambda t3, *_: [
        {"id": r["id"], "reason": "no fail-to-pass" if r["id"] == "t3-2" else None, "withheld_sha256": "w"} for r in t3])
    with pytest.raises(SystemExit, match="t3-2: the check-withheld form failed: no fail-to-pass"):
        tiers.build(work, 1, 5, out=out, repo=tmp_path, tip="TIP")
    assert (verified, (out / "tasks.jsonl").read_text().count("\n")) == ([], 8)


def test_build_refuses_without_the_no_provider_stubs_first_on_path(tmp_path, monkeypatch):
    out, work, _, _ = build_world(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    with pytest.raises(SystemExit, match="first on PATH"):
        tiers.build(work, 1, 5, out=out, repo=tmp_path, tip="TIP")
