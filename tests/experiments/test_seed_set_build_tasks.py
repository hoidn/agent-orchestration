"""Seed-set task builder: mining rules, split, function stripping, hashing and one package end to end."""

import ast
import os
import subprocess
import tempfile

import pytest

from experiments.seed_set import build_tasks as b

MESSAGE = ("fix(calc): return the true sum and difference\n\n"
           "add and sub returned the wrong value for every pair of operands; both now follow the arithmetic.\n\n"
           "Co-Authored-By: Someone <someone@example.invalid>\n")
BUGGY = "def add(a, b):\n    return a - b\n\n\ndef sub(a, b):\n    return a + b\n"
FIXED = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
OLD_TEST = "from orchestrator.calc import add, sub\n\n\ndef test_import():\n    assert add and sub\n"
NEW_TEST = OLD_TEST + ("\n\ndef test_add_is_sum():\n    assert add(2, 3) == 5\n"
                       "\n\ndef test_sub_is_difference():\n    assert sub(5, 3) == 2\n")


def commit(repo, files, message, date):
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
def history(tmp_path_factory):
    repo = tmp_path_factory.mktemp("repo")
    subprocess.run(["git", "init", "-q", repo], check=True)
    commit(repo, {".gitignore": ".orchestrate/\n", "orchestrator/__init__.py": "", "orchestrator/calc.py": BUGGY,
                  "tests/test_calc.py": OLD_TEST}, "init", "2026-06-01T00:00:00+0000")
    shas = {
        "fix": commit(repo, {"orchestrator/calc.py": FIXED, "tests/test_calc.py": NEW_TEST}, MESSAGE,
                      "2026-08-01T00:00:00+0000"),
        "docs": commit(repo, {"README.md": "notes\n", "tests/test_calc.py": NEW_TEST + "\n"},
                       "fix: typo in the notes", "2026-08-02T00:00:00+0000"),
        "feature": commit(repo, {"orchestrator/calc.py": FIXED + "\n\ndef mul(a, b):\n    return a * b\n",
                                 "tests/test_mul.py": "def test_mul():\n    pass\n"},
                          "feat: add mul", "2026-08-03T00:00:00+0000"),
        "reverted": commit(repo, {"orchestrator/calc.py": FIXED + "\n\ndef mul(a, b):\n    return a * b + 0\n",
                                  "tests/test_mul.py": "def test_mul():\n    pass\n\n"},
                           "fix: wrong mul rounding", "2026-08-04T00:00:00+0000"),
    }
    shas["revert"] = commit(repo, {"orchestrator/calc.py": FIXED + "\n\ndef mul(a, b):\n    return a * b\n",
                                   "tests/test_mul.py": "def test_mul():\n    pass\n"},
                            f"Revert \"fix: wrong mul rounding\"\n\nThis reverts commit {shas['reverted']}.",
                            "2026-08-05T00:00:00+0000")
    return repo, shas


def test_mine_admits_only_the_fix_commit(history):
    repo, shas = history
    candidates, _ = b.mine(repo, "HEAD")
    assert [c["commit"] for c in candidates] == [shas["fix"]]


def test_mine_records_a_reason_for_every_rejected_commit(history):
    repo, shas = history
    _, rejects = b.mine(repo, "HEAD")
    reasons = {r["commit"]: r["reason"] for r in rejects}
    assert reasons == {shas["docs"]: "no change under orchestrator/", shas["feature"]: "not fix-worded",
                       shas["reverted"]: "revert or reverted", shas["revert"]: "revert or reverted"}


def test_mine_without_fix_wording_admits_the_unworded_commit(history):
    repo, shas = history
    candidates, _ = b.mine(repo, "HEAD", fix_wording=False)
    assert sorted(c["commit"] for c in candidates) == sorted([shas["fix"], shas["feature"]])


def test_split_does_not_depend_on_input_order():
    groups = [f"tests/test_x.py::test_{i}" for i in range(6)]
    assert b.split(groups) == b.split(list(reversed(groups)))


def test_split_puts_every_group_on_exactly_one_side():
    groups = [f"tests/test_x.py::test_{i}" for i in range(6)]
    visible, hidden = b.split(groups)
    assert sorted([visible, *hidden]) == sorted(groups)


def test_strip_functions_removes_named_functions_and_their_decorators():
    source = ("import pytest\n\n\n@pytest.mark.parametrize('x', [1])\ndef test_gone(x):\n    pass\n\n\n"
              "class TestBox:\n    def test_kept(self):\n        pass\n\n    def test_gone_too(self):\n        pass\n")
    stripped = b.strip_functions(source, {"test_gone", "TestBox::test_gone_too"})
    assert sorted(b.test_functions(stripped)) == ["TestBox::test_kept"] and "parametrize" not in stripped


def test_package_hash_changes_when_a_file_changes(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("one")
    before = b.package_hash(tmp_path)
    (tmp_path / "a" / "f.txt").write_text("two")
    assert b.package_hash(tmp_path) != before


def test_leak_check_rejects_a_statement_naming_a_hidden_test(tmp_path):
    text = "Fix the sum so that test_add_is_sum passes again, and keep every other operand pair working too."
    assert b.leak_reason(text, ["test_add_is_sum"], tmp_path) == "statement names a hidden test"


@pytest.fixture(scope="module")
def built(history, tmp_path_factory):
    repo, _ = history
    candidate = b.mine(repo, "HEAD")[0][0]
    work = tmp_path_factory.mktemp("work")
    return b.evaluate(candidate, work, runs=1), work / "pkgs" / candidate["commit"][:10]


def test_evaluated_package_passes_the_oracle(built):
    row, _ = built
    assert row["reason"] is None


def test_package_seed_holds_no_hidden_function(built):
    row, pkg = built
    names = {n.split("::")[-1] for n in row["hidden"]}
    assert names and names.isdisjoint(b.test_functions((pkg / "seed/tests/test_calc.py").read_text()))


def test_package_hides_every_function_but_the_visible_one(built):
    row, pkg = built
    hidden = (pkg / "hidden_tests.txt").read_text().split()
    assert hidden == [*row["hidden"], "tests/test_calc.py"] and row["visible"] not in hidden


def test_package_statement_drops_trailers(built):
    _, pkg = built
    assert "Co-Authored-By" not in (pkg / "intent.txt").read_text()


def test_package_base_anchor_is_empty_and_upstream_has_no_tests(built):
    _, pkg = built
    upstream = (pkg / "anchors" / f"{pkg.name}-upstream.diff").read_text()
    assert (pkg / "anchors" / f"{pkg.name}-base.diff").read_bytes() == b"" and "tests/" not in upstream


def test_package_hash_is_reproducible_from_the_same_commit(built, history, tmp_path):
    row, _ = built
    repo, _ = history
    again = b.evaluate(b.mine(repo, "HEAD")[0][0], tmp_path, runs=1)
    assert again["package_sha256"] == row["package_sha256"]


def test_seed_file_parses(built):
    _, pkg = built
    ast.parse((pkg / "seed/tests/test_calc.py").read_text())


def test_candidate_whose_tests_call_a_provider_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", repo], check=True)
    commit(repo, {".gitignore": ".orchestrate/\n", "orchestrator/__init__.py": "", "orchestrator/calc.py": BUGGY,
                  "tests/test_calc.py": OLD_TEST}, "init", "2026-06-01T00:00:00+0000")
    calls = "import subprocess\n" + NEW_TEST + (
        "\n\ndef test_reaches_a_provider():\n    subprocess.run(['claude', '-p', '--model', 'x'])\n")
    commit(repo, {"orchestrator/calc.py": FIXED, "tests/test_calc.py": calls}, MESSAGE, "2026-08-01T00:00:00+0000")
    row = b.evaluate(b.mine(repo, "HEAD")[0][0], tmp_path / "work", runs=1)
    assert (row["reason"], row["note"]) == ("tests attempt a provider call", ["claude -p --model x"])


def test_evaluate_leaves_the_callers_temporary_directory_and_path_unchanged(history, tmp_path):
    repo, _ = history
    before = (os.environ.get("TMPDIR"), os.environ["PATH"], tempfile.gettempdir())
    b.evaluate(b.mine(repo, "HEAD")[0][0], tmp_path / "work", runs=1)
    assert (os.environ.get("TMPDIR"), os.environ["PATH"], tempfile.gettempdir()) == before


def test_statement_repeating_an_added_line_is_rejected():
    text = "Fix the sum: the function now reads return a + b and returns the true sum of both operands."
    assert b.statement_reason(text, ["return a + b and returns"]) == "statement repeats a line the fix adds"


def test_withheld_form_of_the_package_passes_the_oracle(history, tmp_path):
    from experiments.seed_set import forms
    repo, _ = history
    row = b.evaluate(b.mine(repo, "HEAD")[0][0], tmp_path, runs=1, withheld=forms.withhold)
    assert (row["reason"], bool(row["withheld_sha256"])) == (None, True)
