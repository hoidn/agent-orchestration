"""MLE-bench family plan, Task 2: the verifier path (experiments/mle_bench_tasks/verifier/) and the agent-side format
check (experiments/mle_bench_tasks/agent/validate_submission.py).

The verifier runs as the harness runs it: `bash test.sh` against a directory tree standing in for the verifier
container's file system, its in-image paths moved into the tree by environment variables. The benchmark's grader is
replaced there by a stand-in `mlebench` package (STAND_IN below) that grades with the fixture's own grade.py and the
benchmark's medal rule; one test, skipped where the benchmark's environment is absent, runs the same submissions
through the benchmark's own `grade_csv` and shows that the two give the same reward file.
"""

import csv
import importlib.util
import json
import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "experiments" / "mle_bench_tasks"
TEST_SH = KIT / "verifier" / "test.sh"
VALIDATOR = KIT / "agent" / "validate_submission.py"
FIXTURES = ROOT / "tests" / "experiments" / "fixtures" / "mle_bench"  # the data directory: tiny-tabular/prepared/...
TINY = FIXTURES / "tiny-tabular"
ANSWERS = TINY / "prepared" / "private" / "answers.csv"
SAMPLE = TINY / "prepared" / "public" / "sample_submission.csv"
CID = "tiny-tabular"
MLE_VENV = Path.home() / "lh-cache" / "mle" / "venv"  # the benchmark's grader and its dependencies (read only)
MLE_SRC = Path.home() / "lh-cache" / "mle" / "src" / "mlebench"
TESTS = ["valid", "above_median", "bronze", "silver", "gold"]  # the five-line test report (plan M4)

STAND_IN_GRADE = '''
"""Stands in for mlebench.grade: grade_csv with the fixture's grade function and the benchmark's rule for fewer than
100 teams (mlebench/grade.py, grade_helpers.Grader). Only what the verifier reads is reported."""
from types import SimpleNamespace

import pandas as pd


def _score(path, competition):
    try:
        submission = pd.read_csv(path, float_precision="round_trip")
    except pd.errors.EmptyDataError:
        submission = pd.DataFrame()
    try:
        return round(competition.grade(submission, pd.read_csv(competition.answers)), 5)
    except Exception:  # as Grader.__call__: any error of the grade function is an invalid submission
        return None


def grade_csv(path, competition):
    if not competition.answers.is_file():
        raise ValueError(f"Dataset for competition `{competition.id}` is not prepared!")
    exists = path.is_file() and path.suffix.lower() == ".csv"
    score = _score(path, competition) if exists else None
    board = pd.read_csv(competition.leaderboard)["score"]
    lower, n = bool(board.iloc[0] < board.iloc[-1]), len(board)
    assert 1 <= n < 100
    gold, silver, bronze = (float(board.iloc[max(1, int(n * f)) - 1]) for f in (0.1, 0.2, 0.4))
    at = lambda t: score is not None and (score <= t if lower else score >= t)
    g = at(gold)
    s = not g and at(silver)
    b = not g and not s and at(bronze)
    above = score is not None and bool(score < board.median() if lower else score > board.median())
    report = {"score": score, "gold_medal": g, "silver_medal": s, "bronze_medal": b, "any_medal": g or s or b,
              "above_median": above, "submission_exists": exists, "valid_submission": score is not None,
              "is_lower_better": lower}
    return SimpleNamespace(to_dict=lambda: report)
'''

STAND_IN_REGISTRY = '''
from pathlib import Path
from types import SimpleNamespace

COMPETITIONS = Path(__file__).parent / "competitions"


class Registry:
    def __init__(self, data_dir=Path("/nonexistent")):
        self.data_dir = data_dir

    def set_data_dir(self, data_dir):
        return Registry(data_dir)

    def get_competition(self, cid):
        namespace = {}
        exec((COMPETITIONS / cid / "grade.py").read_text(), namespace)
        return SimpleNamespace(id=cid, grade=namespace["grade"], leaderboard=COMPETITIONS / cid / "leaderboard.csv",
                               answers=self.data_dir / cid / "prepared" / "private" / "answers.csv")


registry = Registry()
'''


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bench(root, package):
    """A benchmark directory: <root>/mlebench/ from `package` (a dict of stand-in modules, or the benchmark's source
    directory), with the fixture's competition at mlebench/competitions/tiny-tabular/, where the benchmark keeps it."""
    target = root / "mlebench"
    if isinstance(package, dict):
        target.mkdir(parents=True)
        for name, text in package.items():
            (target / name).write_text(text)
    else:
        target.mkdir(parents=True)
        for path in package.glob("*.py"):
            shutil.copyfile(path, target / path.name)
        (target / "competitions").mkdir()
        shutil.copyfile(package / "competitions" / "__init__.py", target / "competitions" / "__init__.py")
    shutil.copytree(TINY / "competition", target / "competitions" / CID)
    return root


STAND_IN = {"__init__.py": "", "grade.py": STAND_IN_GRADE, "registry.py": STAND_IN_REGISTRY}


def _tree(tmp_path, submission=None, data_dir=FIXTURES, package=STAND_IN):
    """A directory tree standing in for the verifier container, and the environment that points the verifier at it."""
    tree = tmp_path / "tree"
    (tree / "home" / "submission").mkdir(parents=True)
    if submission is not None:
        (tree / "home" / "submission" / "submission.csv").write_bytes(submission)
    bench = _bench(tree / "opt" / "mle-bench", package)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "MLE_COMPETITION_ID": CID, "MLE_DATA_DIR": str(data_dir),
           "MLE_BENCHMARK_DIR": str(bench), "MLE_SUBMISSION": str(tree / "home" / "submission" / "submission.csv"),
           "MLE_LOGS_DIR": str(tree / "logs" / "verifier"), "MLE_GRADER_WORK": str(tree / "grader-work")}
    return tree, env


def _verify(tmp_path, submission=None, **kwargs):
    """Run test.sh in a stand-in tree; return (process, reward or None, ctrf or None)."""
    tree, env = _tree(tmp_path, submission, **kwargs)
    done = subprocess.run(["bash", str(TEST_SH)], env=env, capture_output=True, text=True, timeout=120)
    logs = tree / "logs" / "verifier"
    read = lambda name: json.loads((logs / name).read_text()) if (logs / name).is_file() else None
    return done, read("reward.json"), read("ctrf.json")


def _passed(ctrf):
    summary = ctrf["results"]["summary"]
    statuses = {t["name"]: t["status"] for t in ctrf["results"]["tests"]}
    return summary["passed"], summary["tests"], [name for name in TESTS if statuses[name] == "passed"]


def _auc_submission(k):
    """A submission whose ROC AUC against the fixture's answers is exactly k / (positives x negatives): negative i
    gets (i + 1) / (N + 1); a positive that is to beat c negatives gets (c + 0.5) / (N + 1)."""
    rows = list(csv.DictReader(ANSWERS.open()))
    positives = [r["id"] for r in rows if r["probability"] == "1"]
    negatives = [r["id"] for r in rows if r["probability"] == "0"]
    n = len(negatives)
    full, rest = divmod(k, n)
    beats = [n] * full + [rest] + [0] * (len(positives) - full - 1)
    value = {i: (j + 1) / (n + 1) for j, i in enumerate(negatives)}
    value |= {i: (c + 0.5) / (n + 1) for i, c in zip(positives, beats)}
    return ("id,probability\n" + "".join(f"{r['id']},{value[r['id']]!r}\n" for r in rows)).encode()


PAIRS = 22 * 18  # the fixture's positives times negatives: AUC moves in steps of 1/396


def test_the_constructed_submissions_have_the_auc_they_are_built_for():
    """The threshold controls' construction, checked with the fixture's grader in-process."""
    import pandas as pd
    namespace = {}
    exec((TINY / "competition" / "grade.py").read_text(), namespace)
    answers = pd.read_csv(ANSWERS)
    rows = list(csv.DictReader(ANSWERS.open()))
    assert (sum(r["probability"] == "1" for r in rows), sum(r["probability"] == "0" for r in rows)) == (22, 18)
    for k in (319, 320, 329, 330):
        assert namespace["grade"](pd.read_csv(BytesIO(_auc_submission(k))), answers) == pytest.approx(k / PAIRS)


# --- the verifier -------------------------------------------------------------------------------------------------

def test_the_answers_earn_reward_1_with_gold_and_five_tests_passed(tmp_path):
    done, reward, ctrf = _verify(tmp_path, ANSWERS.read_bytes())
    assert done.returncode == 0, done.stderr
    assert reward == {"reward": 1, "score": 1.0, "percentile": 100.0, "valid_submission": 1, "above_median": 1,
                      "medal": 3}
    assert _passed(ctrf) == (5, 5, TESTS)


def test_the_sample_submission_earns_reward_0_and_is_valid(tmp_path):
    done, reward, ctrf = _verify(tmp_path, SAMPLE.read_bytes())
    assert done.returncode == 0, done.stderr
    assert reward == {"reward": 0, "score": 0.5, "percentile": 0.0, "valid_submission": 1, "above_median": 0,
                      "medal": 0}
    assert _passed(ctrf) == (1, 5, ["valid"])


UNUSABLE = {
    "missing": None,
    "empty": b"",
    "malformed": b"id,probability\n1289,0.5\n1378,0.5,7,8\n\"unclosed\n",
    "not-utf8": b"id,probability\n\xff\xfe\xfa,0.5\n",
    "wrong-columns": SAMPLE.read_bytes().replace(b"probability", b"p", 1),
}


@pytest.mark.parametrize("case", list(UNUSABLE))
def test_an_unusable_submission_gets_a_written_reward_0_not_valid_with_no_score_or_percentile(tmp_path, case):
    """Missing, empty, malformed, unreadable or wrong: reward 0, not valid; the score and the percentile, which the
    grader does not give, are left out of the file (never written as 0 or null)."""
    done, reward, ctrf = _verify(tmp_path, UNUSABLE[case])
    assert done.returncode == 0, done.stderr
    assert reward == {"reward": 0, "valid_submission": 0, "above_median": 0, "medal": 0}
    assert _passed(ctrf) == (0, 5, [])


def test_an_error_inside_the_grader_writes_no_reward_and_exits_non_zero_with_the_error_on_stderr(tmp_path):
    """A data directory without the answers: the grader raises, so the launcher sees no reward (an infrastructure
    failure), never a failed attempt."""
    empty = tmp_path / "no-answers"
    empty.mkdir()
    done, reward, ctrf = _verify(tmp_path, ANSWERS.read_bytes(), data_dir=empty)
    assert (done.returncode != 0, reward, ctrf) == (True, None, None)
    assert "not prepared" in done.stderr


# Just above and just below the bronze line (0.83113, position 8 of 20) and the median line (0.806165).
THRESHOLDS = {
    "above-bronze": (330, {"reward": 1, "above_median": 1, "medal": 1}, ["valid", "above_median", "bronze"]),
    "below-bronze": (329, {"reward": 0, "above_median": 1, "medal": 0}, ["valid", "above_median"]),
    "above-median": (320, {"reward": 0, "above_median": 1, "medal": 0}, ["valid", "above_median"]),
    "below-median": (319, {"reward": 0, "above_median": 0, "medal": 0}, ["valid"]),
}


@pytest.mark.parametrize("case", list(THRESHOLDS))
def test_a_submission_on_either_side_of_a_threshold_is_graded_to_its_class(tmp_path, case):
    k, expected, passed = THRESHOLDS[case]
    done, reward, ctrf = _verify(tmp_path, _auc_submission(k))
    assert done.returncode == 0, done.stderr
    assert {key: reward[key] for key in expected} == expected
    assert (reward["valid_submission"], reward["score"]) == (1, round(k / PAIRS, 5))
    assert _passed(ctrf)[2] == passed


CONTROLS = {"answers": ANSWERS.read_bytes(), "sample": SAMPLE.read_bytes(), "missing": None,
            "malformed": UNUSABLE["malformed"], "wrong-columns": UNUSABLE["wrong-columns"]}
CONTROLS |= {case: _auc_submission(k) for case, (k, _, _) in THRESHOLDS.items()}


@pytest.mark.skipif(not (MLE_VENV / "bin" / "python").is_file() or not MLE_SRC.is_dir(),
                    reason="the benchmark's environment (~/lh-cache/mle/venv and src) is absent on this machine")
@pytest.mark.parametrize("case", list(CONTROLS))
def test_the_benchmarks_own_grade_csv_gives_the_same_reward_file_as_the_stand_in(tmp_path, case):
    """The verifier script run by the benchmark's interpreter (-I) on a copy of the benchmark's package with the
    fixture's competition added; its reward file and test report equal the stand-in's."""
    stand_in = _verify(tmp_path / "stand-in", CONTROLS[case])
    tree, env = _tree(tmp_path / "real", CONTROLS[case], package=MLE_SRC)
    real = subprocess.run([str(MLE_VENV / "bin" / "python"), "-I", str(KIT / "verifier" / "grade_submission.py")],
                          env=env, capture_output=True, text=True, timeout=300)
    assert real.returncode == 0, real.stderr
    logs = tree / "logs" / "verifier"
    assert json.loads((logs / "reward.json").read_text()) == stand_in[1]
    assert _passed(json.loads((logs / "ctrf.json").read_text())) == _passed(stand_in[2])


# --- the percentile -----------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def grading():
    return _load(KIT / "verifier" / "grade_submission.py", "mle_grade_submission")


HIGHER = [0.9, 0.8, 0.8, 0.7]  # best first, higher is better
LOWER = [0.1, 0.2, 0.2, 0.3]  # best first, lower is better


@pytest.mark.parametrize("score, scores, lower, expected", [
    (0.85, HIGHER, False, 75.0),  # beats three of four
    (0.8, HIGHER, False, 75.0),  # a tie counts as beaten: 0.8, 0.8, 0.7
    (0.95, HIGHER, False, 100.0),  # above the leaderboard's range
    (0.6, HIGHER, False, 0.0),  # below it
    (0.9, HIGHER, False, 100.0),  # ties the best
    (0.15, LOWER, True, 75.0),
    (0.2, LOWER, True, 75.0),
    (0.05, LOWER, True, 100.0),
    (0.4, LOWER, True, 0.0),
    (0.8, HIGHER, True, 25.0),  # the same numbers read the other way: beats or ties only 0.9
])
def test_the_percentile_is_the_share_of_the_leaderboard_beaten_or_tied_in_the_metrics_direction(
        grading, score, scores, lower, expected):
    assert grading.percentile(score, scores, lower) == expected


def test_the_percentile_of_an_empty_leaderboard_is_refused(grading):
    with pytest.raises(ValueError):
        grading.percentile(0.5, [], False)


# --- the agent-side format check ----------------------------------------------------------------------------------

AUDIT = """
import json, runpy, sys
opened = []
sys.addaudithook(lambda event, args: event == "open" and isinstance(args[0], str) and opened.append(args[0]))
script, log = sys.argv[1], sys.argv[2]
sys.argv = sys.argv[2:]
sys.argv[0] = script
try:
    runpy.run_path(script, run_name="__main__")
finally:
    with open(log, "w") as f:
        json.dump(opened, f)
"""


def _validate(tmp_path, submission):
    """Run the format check in a tree holding only the agent's public files (no private directory anywhere), as
    the instruction tells the agent to; return (process, every path under the tree it opened)."""
    tree = tmp_path / "agent"
    (tree / "home" / "data").mkdir(parents=True)
    (tree / "home" / "submission").mkdir()
    shutil.copyfile(SAMPLE, tree / "home" / "data" / "sample_submission.csv")
    target = tree / "home" / "submission" / "submission.csv"
    if submission is not None:
        target.write_bytes(submission)
    log = tmp_path / "opened.json"
    done = subprocess.run(
        [sys.executable, "-I", "-c", AUDIT, str(VALIDATOR), str(log), str(target),
         str(tree / "home" / "data" / "sample_submission.csv")],
        capture_output=True, text=True, timeout=60)
    opened = {Path(p).resolve() for p in json.loads(log.read_text())} if log.is_file() else set()
    return done, {p.relative_to(tree.resolve()).as_posix() for p in opened if p.is_relative_to(tree.resolve())}


def _codes(done):
    return sorted(line.split(":", 1)[0] for line in done.stdout.splitlines())


def test_the_format_check_accepts_the_sample_and_opens_only_the_sample_and_the_submission(tmp_path):
    done, opened = _validate(tmp_path, SAMPLE.read_bytes())
    assert done.returncode == 0, done.stdout + done.stderr
    assert opened == {"home/data/sample_submission.csv", "home/submission/submission.csv"}
    assert not (tmp_path / "agent" / "private").exists()


def _edit(drop_rows=(), add=(), column=None, blank=None):
    """The sample submission with rows dropped, rows added, the second column renamed, or one value blanked."""
    lines = SAMPLE.read_text().splitlines()
    header, rows = lines[0], lines[1:]
    if column is not None:
        header = f"id,{column}"
    if blank is not None:
        rows[blank] = rows[blank].split(",")[0] + ","
    rows = [r for i, r in enumerate(rows) if i not in drop_rows] + list(add)
    return ("\n".join([header, *rows]) + "\n").encode()


FIRST_ID = SAMPLE.read_text().splitlines()[1].split(",")[0]
REFUSED = {
    "missing-column": (b"id\n" + b"".join(r.split(b",")[0] + b"\n" for r in SAMPLE.read_bytes().splitlines()[1:]),
                       ["missing-column"]),
    "renamed-column": (_edit(column="prob"), ["extra-column", "missing-column"]),
    "missing-id": (_edit(drop_rows=[0]), ["missing-id"]),
    "extra-id": (_edit(add=["99999999,0.5"]), ["extra-id"]),
    "duplicated-id": (_edit(drop_rows=[0], add=[f"{SAMPLE.read_text().splitlines()[2].split(',')[0]},0.5"]),
                      ["duplicate-id", "missing-id"]),
    "empty-value": (_edit(blank=3), ["empty-value"]),
    "two-problems": (_edit(drop_rows=[0], blank=3), ["empty-value", "missing-id"]),
    "no-file": (None, ["no-file"]),
    "empty-file": (b"", ["empty-file"]),
}


@pytest.mark.parametrize("case", list(REFUSED))
def test_the_format_check_refuses_with_one_line_per_problem(tmp_path, case):
    submission, codes = REFUSED[case]
    done, opened = _validate(tmp_path, submission)
    assert (done.returncode, _codes(done)) == (1, codes), done.stdout + done.stderr
    assert opened <= {"home/data/sample_submission.csv", "home/submission/submission.csv"}


def test_the_format_check_needs_its_sample(tmp_path):
    """No public sample: a usage error (exit 2, on stderr), not a verdict on the submission."""
    done = subprocess.run([sys.executable, "-I", str(VALIDATOR), str(SAMPLE), str(tmp_path / "absent.csv")],
                          capture_output=True, text=True, timeout=60)
    assert (done.returncode, done.stdout, "absent.csv" in done.stderr) == (2, "", True)
