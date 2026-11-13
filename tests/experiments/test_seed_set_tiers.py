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
from tests.experiments.seed_set_offline_support import manifest_rows
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
    done = {"T3-00": {"sha256": b.package_hash(tmp_path / "tasks" / "T3-00"), "stable": True}}
    (tmp_path / anchors.FILE).write_text(json.dumps(done))
    checked = []
    monkeypatch.setattr(anchors, "check", lambda package, work: checked.append(package.name) or {"stable": True,
                        "sha256": "x", "reference_failing": [], "runs": []})
    anchors.run(tmp_path / "work", out=tmp_path)
    assert sorted(checked) == ["T3-01", "T3w-00", "T3w-01"]
