"""Seed-set leak audit on a tiny synthetic history: a clean package passes; a clone holding the fix's commit, a
seed file repeating a line the fix adds, and the scan's hash-only coverage are detected or recorded."""

import os
import shutil
import subprocess

import pytest

from experiments.compare import repos
from experiments.seed_set import build_tasks as b, leak_audit

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    total_of_both_operands = a + b\n    return total_of_both_operands\n"
OLD_TEST = "from orchestrator.calc import add\n\n\ndef test_import():\n    assert add\n"
NEW_TEST = OLD_TEST + "\n\ndef test_add_one():\n    assert add(2, 3) == 5\n\n\ndef test_add_two():\n    assert add(1, 1) == 2\n"
MESSAGE = "fix(calc): return the true sum\n\nadd returned the difference of its operands for every pair; it now sums.\n"


def commit(repo, files, message, date):
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                    "--no-gpg-sign", "-m", message], check=True, env=env)
    return repos.git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    repo = tmp_path_factory.mktemp("repo")
    subprocess.run(["git", "init", "-q", repo], check=True)
    commit(repo, {".gitignore": ".orchestrate/\n", "orchestrator/__init__.py": "", "orchestrator/calc.py": BUGGY,
                  "tests/test_calc.py": OLD_TEST}, "init", "2026-06-01T00:00:00+0000")
    fix = commit(repo, {"orchestrator/calc.py": FIXED, "tests/test_calc.py": NEW_TEST}, MESSAGE,
                 "2026-08-01T00:00:00+0000")
    work = tmp_path_factory.mktemp("work")
    row = b.evaluate(b.mine(repo, "HEAD")[0][0], work, runs=1)
    assert row["reason"] is None
    return repo, fix, work / "pkgs" / fix[:10]


def test_clean_package_passes_the_audit(package, tmp_path):
    repo, fix, pkg = package
    assert leak_audit.audit(pkg, tmp_path, [fix], repo) == []


def test_clone_holding_the_fix_commit_fails_the_object_check(package, tmp_path):
    repo, fix, pkg = package
    base = (pkg / "base_commit").read_text().strip()
    clone = tmp_path / "clone"
    seeded = repos.build_candidate(repo, base, pkg / "seed", clone)
    repos.git(clone, "fetch", "-q", "--upload-pack", "git -c uploadpack.allowAnySHA1InWant=true upload-pack",
              str(repo), fix)
    (clone / ".git/FETCH_HEAD").unlink()
    assert leak_audit.objects_reason(clone, base, seeded, pkg / "seed", [fix]) is not None


def test_seed_file_repeating_a_line_the_fix_adds_fails_the_line_check(package, tmp_path):
    repo, fix, pkg = package
    planted = tmp_path / pkg.name
    shutil.copytree(pkg, planted)
    test_file = planted / "seed/tests/test_calc.py"
    test_file.write_text(test_file.read_text() + "\n# total_of_both_operands = a + b\n")
    assert [check for check, _ in leak_audit.audit(planted, tmp_path / "w", [fix], repo)] == ["lines"]


def test_scan_reports_the_fix_hash_planted_in_a_call_output(package, tmp_path):
    repo, fix, _ = package
    shown = repos.git(repo, "show", fix)
    assert "solution hash" in leak_audit.scan_check(fix, tmp_path, shown)


def test_scan_does_not_see_a_copy_of_the_fix_without_its_hash(package, tmp_path):
    repo, fix, pkg = package
    diff = (pkg / "anchors" / f"{pkg.name}-upstream.diff").read_text()
    assert leak_audit.scan_check(fix, tmp_path, diff) == []
