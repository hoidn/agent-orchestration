"""MLE-bench family plan, Task 2: the verifier path (experiments/mle_bench_tasks/verifier/) and the agent-side format
check (experiments/mle_bench_tasks/agent/validate_submission.py).

The verifier runs as the harness runs it: `bash test.sh` against a directory tree standing in for the verifier
container's file system, its in-image paths moved into the tree by environment variables. The benchmark's grader is
replaced there by a stand-in `mlebench` package (STAND_IN below) that grades with the competition's grade.py, logs as
the benchmark's Grader does, and applies the benchmark's medal rule; one test, skipped where the benchmark's
environment is absent, runs the same submissions through the benchmark's own `grade_csv` and shows that the two give
the same reward file.
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

STAND_IN_HELPERS = '''
"""Stands in for mlebench.grade_helpers: Grader.__call__'s handling of the grade function, and its logging."""
import logging

logger = logging.getLogger(__name__)


class InvalidSubmissionError(Exception):
    pass


def call(grade_fn, submission, answers):
    try:
        score = grade_fn(submission, answers)
    except InvalidSubmissionError as e:
        logger.warning(f"Invalid submission: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during grading: {e}")
        return None
    return round(score, 5)
'''

STAND_IN_GRADE = '''
"""Stands in for mlebench.grade: grade_csv with the competition's grade function and the benchmark's rule for fewer
than 100 teams (mlebench/grade.py, grade_helpers.Grader). Only what the verifier reads is reported."""
from types import SimpleNamespace

import pandas as pd

from mlebench.grade_helpers import call


def _score(path, competition):
    try:
        submission = pd.read_csv(path, float_precision="round_trip")
    except pd.errors.EmptyDataError:
        submission = pd.DataFrame()
    return call(competition.grade, submission, pd.read_csv(competition.answers))


def grade_csv(path, competition):
    if not competition.answers.is_file():
        raise ValueError(f"Dataset for competition `{competition.id}` is not prepared!")
    exists = path.is_file() and path.suffix.lower() == ".csv"
    score = _score(path, competition) if exists else None
    board = pd.read_csv(competition.leaderboard)["score"]
    lower, n = bool(board.iloc[0] < board.iloc[-1]), len(board)
    assert 1 <= n < 100
    gold, silver, bronze = (float(board.iloc[max(1, int(n * f)) - 1]) for f in (0.1, 0.2, 0.4))
    at = lambda t: score is not None and bool(score <= t if lower else score >= t)
    g = at(gold)
    s = not g and at(silver)
    b = not g and not s and at(bronze)
    above = score is not None and bool(score < board.median() if lower else score > board.median())
    report = {"score": score, "gold_medal": g, "silver_medal": s, "bronze_medal": b, "any_medal": g or s or b,
              "above_median": above, "submission_exists": exists, "valid_submission": score is not None,
              "is_lower_better": lower, "gold_threshold": gold, "silver_threshold": silver,
              "bronze_threshold": bronze, "median_threshold": float(board.median())}
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

STAND_IN = {"__init__.py": "", "grade_helpers.py": STAND_IN_HELPERS, "grade.py": STAND_IN_GRADE,
            "registry.py": STAND_IN_REGISTRY}

# Grade functions put in place of the fixture's, in the tree's copy of the competition (never in the fixture).
FIXTURE_GRADE = (TINY / "competition" / "grade.py").read_text()
RETURNS = "def grade(submission, answers):\n    return {}\n".format
RAISES_INVALID = ("from mlebench.grade_helpers import InvalidSubmissionError\n\n\n"
                  "def grade(submission, answers):\n    raise InvalidSubmissionError('a submission fault')\n")
RAISES_OTHER = "def grade(submission, answers):\n    raise KeyError('a grader-side fault')\n"
LOSS = (FIXTURE_GRADE.replace("def grade(", "def auc(")
        + "\n\ndef grade(submission, answers):\n    return 1 - auc(submission, answers)\n")
PEARSON = ("import scipy.stats\n\n\ndef grade(submission, answers):\n"
           "    merged = answers.merge(submission, on='id', suffixes=('_true', ''))\n"
           "    return scipy.stats.pearsonr(merged['probability'], merged['probability_true'])[0]\n")


def _lower_board():
    """The fixture's leaderboard as a loss: each score s becomes 1 - s, best (lowest) first."""
    rows = list(csv.DictReader((TINY / "competition" / "leaderboard.csv").open()))
    for row in rows:
        row["score"] = row["scoreNullable"] = repr(round(1 - float(row["score"]), 5))
    return "\n".join([",".join(rows[0])] + [",".join(r.values()) for r in rows]) + "\n"


LOWER_IS_BETTER = {"grade.py": LOSS, "leaderboard.csv": _lower_board()}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bench(root, package, competition):
    """A benchmark directory: <root>/mlebench/ from `package` (a dict of stand-in modules, or the benchmark's source
    directory), with the fixture's competition at mlebench/competitions/tiny-tabular/, where the benchmark keeps it,
    and the files of `competition` replacing (or, for None, removing) the copy's."""
    target = root / "mlebench"
    target.mkdir(parents=True)
    if isinstance(package, dict):
        for name, text in package.items():
            (target / name).write_text(text)
    else:
        for path in package.glob("*.py"):
            shutil.copyfile(path, target / path.name)
        (target / "competitions").mkdir()
        shutil.copyfile(package / "competitions" / "__init__.py", target / "competitions" / "__init__.py")
    copy = target / "competitions" / CID
    shutil.copytree(TINY / "competition", copy)
    for name, text in competition.items():
        (copy / name).unlink()
        if text is not None:
            (copy / name).write_text(text)
    return root


def _tree(tmp_path, submission=None, data_dir=FIXTURES, package=STAND_IN, competition={}, cid=CID):
    """A directory tree standing in for the verifier container, and the environment that points the verifier at it."""
    tree = tmp_path / "tree"
    (tree / "home" / "submission").mkdir(parents=True)
    if submission is not None:
        (tree / "home" / "submission" / "submission.csv").write_bytes(submission)
    bench = _bench(tree / "opt" / "mle-bench", package, competition)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python3").symlink_to(sys.executable)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "MLE_COMPETITION_ID": cid, "MLE_DATA_DIR": str(data_dir),
           "MLE_BENCHMARK_DIR": str(bench), "MLE_SUBMISSION": str(tree / "home" / "submission" / "submission.csv"),
           "MLE_LOGS_DIR": str(tree / "logs" / "verifier"), "MLE_GRADER_WORK": str(tree / "grader-work")}
    return tree, env


def _logs(tree):
    """(reward or None, ctrf or None, the names in the logs directory)."""
    logs = tree / "logs" / "verifier"
    read = lambda name: json.loads((logs / name).read_text()) if (logs / name).is_file() else None
    return read("reward.json"), read("ctrf.json"), sorted(p.name for p in logs.iterdir()) if logs.is_dir() else []


def _run(tree, env):
    done = subprocess.run(["bash", str(TEST_SH)], env=env, capture_output=True, text=True, timeout=120)
    return (done, *_logs(tree)[:2])


def _verify(tmp_path, submission=None, **kwargs):
    """Run test.sh in a stand-in tree; return (process, reward or None, ctrf or None)."""
    return _run(*_tree(tmp_path, submission, **kwargs))


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
# The fixture's thresholds: positions 2, 4 and 8 of 20 teams, and the median of the twenty scores.
THRESHOLD_FIELDS = {"gold_threshold": 0.96218, "silver_threshold": 0.91742, "bronze_threshold": 0.83113,
                    "median_threshold": 0.806165}
NO_SCORE = {"reward": 0, "valid_submission": 0, "above_median": 0, "medal": 0, "grader_exception": 0,
            **THRESHOLD_FIELDS}


def test_the_constructed_submissions_have_the_auc_they_are_built_for():
    """The threshold controls' construction, checked with the fixture's grader in-process."""
    import pandas as pd
    namespace = {}
    exec(FIXTURE_GRADE, namespace)
    answers = pd.read_csv(ANSWERS)
    rows = list(csv.DictReader(ANSWERS.open()))
    assert (sum(r["probability"] == "1" for r in rows), sum(r["probability"] == "0" for r in rows)) == (22, 18)
    for k in (319, 320, 329, 330):
        assert namespace["grade"](pd.read_csv(BytesIO(_auc_submission(k))), answers) == pytest.approx(k / PAIRS)


# --- the verifier -------------------------------------------------------------------------------------------------

def test_the_answers_earn_reward_1_with_gold_and_five_tests_passed(tmp_path):
    tree, env = _tree(tmp_path, ANSWERS.read_bytes())
    done, reward, ctrf = _run(tree, env)
    assert done.returncode == 0, done.stderr
    assert reward == {"reward": 1, "score": 1.0, "percentile": 100.0, "valid_submission": 1, "above_median": 1,
                      "medal": 3, "grader_exception": 0, **THRESHOLD_FIELDS}
    assert _passed(ctrf) == (5, 5, TESTS)
    assert _logs(tree)[2] == ["ctrf.json", "reward.json"]  # no temporary file left behind


def test_the_sample_submission_earns_reward_0_and_is_valid(tmp_path):
    done, reward, ctrf = _verify(tmp_path, SAMPLE.read_bytes())
    assert done.returncode == 0, done.stderr
    assert reward == {"reward": 0, "score": 0.5, "percentile": 0.0, "valid_submission": 1, "above_median": 0,
                      "medal": 0, "grader_exception": 0, **THRESHOLD_FIELDS}
    assert _passed(ctrf) == (1, 5, ["valid"])


UNUSABLE = {  # the submission, and whether the benchmark logs an unexpected grading error for it
    "missing": (None, 0),
    "empty": (b"", 0),
    "malformed": (b"id,probability\n1289,0.5\n1378,0.5,7,8\n\"unclosed\n", 0),
    "not-utf8": (b"id,probability\n\xff\xfe\xfa,0.5\n", 0),
    # The fixture's grade function raises a plain ValueError, which the benchmark logs as an unexpected error.
    "wrong-columns": (SAMPLE.read_bytes().replace(b"probability", b"p", 1), 1),
}


@pytest.mark.parametrize("case", list(UNUSABLE))
def test_an_unusable_submission_gets_a_written_reward_0_not_valid_with_no_score_or_percentile(tmp_path, case):
    """Missing, empty, malformed, unreadable or wrong: reward 0, not valid; the score and the percentile, which the
    grader does not give, are left out of the file (never written as 0 or null)."""
    submission, flagged = UNUSABLE[case]
    done, reward, ctrf = _verify(tmp_path, submission)
    assert done.returncode == 0, done.stderr
    assert reward == NO_SCORE | {"grader_exception": flagged}
    assert _passed(ctrf) == (0, 5, [])


def test_a_submission_that_is_a_symbolic_link_is_not_followed(tmp_path):
    tree, env = _tree(tmp_path)
    (tree / "home" / "submission" / "submission.csv").symlink_to(ANSWERS)
    done, reward, ctrf = _run(tree, env)
    assert (done.returncode, reward, _passed(ctrf)) == (0, NO_SCORE, (0, 5, []))
    assert done.stderr.startswith("symlink")


def _mlebench_state():
    """The loaded mlebench modules and the sys.path entries that hold an mlebench package."""
    return (sorted(m for m in sys.modules if m.split(".")[0] == "mlebench"),
            [p for p in sys.path if (Path(p) / "mlebench").is_dir()])


@pytest.fixture(scope="module", autouse=True)
def no_stand_in_left_loaded():
    """After this module's tests in a worker, in whatever order they ran: no mlebench module loaded and no path to
    one added, so no stand-in shadows the benchmark's package for a later test."""
    before = _mlebench_state()
    yield
    assert _mlebench_state() == before


@pytest.fixture
def in_process(monkeypatch):
    """For a test that runs main() in this process: its cwd and sys.path are put back, and the mlebench it imported
    (the stand-in) is unloaded."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    for name in [m for m in sys.modules if m.split(".")[0] == "mlebench"]:
        del sys.modules[name]


@pytest.fixture(scope="module")
def grading():
    return _load(KIT / "verifier" / "grade_submission.py", "mle_grade_submission")


def test_an_oversized_submission_gets_reward_0_and_is_not_valid(grading, in_process, tmp_path, monkeypatch, capsys):
    """Above the size cap (passed lowered here), the attempt's fault: the answers themselves get reward 0, not valid,
    with the thresholds, and the reason on stderr."""
    tree, env = _tree(tmp_path, ANSWERS.read_bytes())
    monkeypatch.chdir(tmp_path)  # main() enters MLE_GRADER_WORK; the test's own directory is put back afterwards
    grading.main(env, cap=ANSWERS.stat().st_size - 1)
    reward, ctrf, _ = _logs(tree)
    assert (reward, _passed(ctrf)) == (NO_SCORE, (0, 5, []))
    assert capsys.readouterr().err.startswith("oversized")


def test_the_size_cap_is_the_larger_of_64_mib_and_five_times_the_largest_private_file(grading):
    private = TINY / "prepared" / "private"
    assert (grading.size_cap(private), grading.size_cap(private, floor=0)) == (64 * 2**20, 5 * ANSWERS.stat().st_size)


@pytest.mark.parametrize("value", ['float("nan")', 'float("inf")', '-float("inf")'])
def test_a_score_that_is_not_finite_is_treated_as_no_score_and_still_writes_a_reward(tmp_path, value):
    """reward 0, medal 0, not above the median, no score or percentile; valid as the grader reports it (valid)."""
    done, reward, ctrf = _verify(tmp_path, SAMPLE.read_bytes(), competition={"grade.py": RETURNS(value)})
    assert done.returncode == 0, done.stderr
    assert reward == NO_SCORE | {"valid_submission": 1}
    assert _passed(ctrf) == (1, 5, ["valid"])


@pytest.mark.parametrize("grade, flagged", [(RAISES_OTHER, 1), (RAISES_INVALID, 0)])
def test_an_error_inside_the_grade_function_gives_reward_0_and_flags_only_an_unexpected_one(tmp_path, grade, flagged):
    """The benchmark turns any error of a grade function into no score. Its InvalidSubmissionError is a submission
    fault; any other is logged as unexpected, and the verifier records it as grader_exception 1 for a person to
    rule on."""
    done, reward, ctrf = _verify(tmp_path, ANSWERS.read_bytes(), competition={"grade.py": grade})
    assert done.returncode == 0, done.stderr
    assert reward == NO_SCORE | {"grader_exception": flagged}


GRADER_FAULTS = {
    "no-answers": {"data_dir": Path("/nonexistent-data-dir")},
    "unknown-competition": {"cid": "no-such-competition"},
    "no-leaderboard": {"competition": {"leaderboard.csv": None}},
    "no-benchmark": {"package": {"__init__.py": ""}},
}


@pytest.mark.parametrize("case", list(GRADER_FAULTS))
def test_a_fault_outside_the_grade_function_writes_neither_file_and_exits_non_zero(tmp_path, case):
    """The launcher then sees no reward (an infrastructure failure), never a failed attempt."""
    done, reward, ctrf = _verify(tmp_path, ANSWERS.read_bytes(), **GRADER_FAULTS[case])
    assert (done.returncode != 0, reward, ctrf, done.stderr != "") == (True, None, None, True)


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


@pytest.mark.parametrize("k, medal, percentile", [(330, 1, 65.0), (329, 0, 60.0)])
def test_on_a_lower_is_better_leaderboard_the_percentile_and_the_medal_follow_the_direction(tmp_path, k, medal,
                                                                                            percentile):
    """1 - AUC against the fixture's leaderboard as a loss (bronze line 0.16887): 0.16667 is a bronze and beats or
    ties 13 of 20; 0.16919 is not and beats or ties 12. Read the wrong way, they would beat 7 and 8."""
    done, reward, _ = _verify(tmp_path, _auc_submission(k), competition=LOWER_IS_BETTER)
    assert done.returncode == 0, done.stderr
    assert (reward["score"], reward["medal"], reward["percentile"]) == (round(1 - k / PAIRS, 5), medal, percentile)


CONTROLS = {case: (submission, {}) for case, (submission, _) in UNUSABLE.items()}
CONTROLS |= {"answers": (ANSWERS.read_bytes(), {}), "sample": (SAMPLE.read_bytes(), {})}
CONTROLS |= {case: (_auc_submission(k), {}) for case, (k, _, _) in THRESHOLDS.items()}
CONTROLS |= {
    "lower-is-better": (_auc_submission(330), LOWER_IS_BETTER),
    "constant-on-correlation": (SAMPLE.read_bytes(), {"grade.py": PEARSON}),  # pearsonr of a constant column: NaN
    "infinite": (SAMPLE.read_bytes(), {"grade.py": RETURNS('float("inf")')}),
    "raises-invalid": (ANSWERS.read_bytes(), {"grade.py": RAISES_INVALID}),
    "raises-other": (ANSWERS.read_bytes(), {"grade.py": RAISES_OTHER}),
}


@pytest.mark.skipif(not (MLE_VENV / "bin" / "python").is_file() or not MLE_SRC.is_dir(),
                    reason="the benchmark's environment (~/lh-cache/mle/venv and src) is absent on this machine")
@pytest.mark.parametrize("case", list(CONTROLS))
def test_the_benchmarks_own_grade_csv_gives_the_same_reward_file_as_the_stand_in(tmp_path, case):
    """The verifier script run by the benchmark's interpreter (-I) on a copy of the benchmark's package with the
    fixture's competition added (its grade function or leaderboard replaced in the copy where the case says); its
    reward file and test report equal the stand-in's."""
    submission, competition = CONTROLS[case]
    stand_in = _verify(tmp_path / "stand-in", submission, competition=competition)
    tree, env = _tree(tmp_path / "real", submission, package=MLE_SRC, competition=competition)
    real = subprocess.run([str(MLE_VENV / "bin" / "python"), "-I", str(KIT / "verifier" / "grade_submission.py")],
                          env=env, capture_output=True, text=True, timeout=300)
    assert real.returncode == 0, real.stderr
    graded = any((tree / "opt" / "mle-bench" / "mlebench" / "__pycache__").glob("grade.*.pyc"))
    assert graded  # the grader runs in every case: a refused file is replaced by an absent one
    reward, ctrf, _ = _logs(tree)
    assert (reward, _passed(ctrf)) == (stand_in[1], _passed(stand_in[2]))
    if case == "constant-on-correlation":
        assert reward == NO_SCORE | {"valid_submission": 1}


def test_the_thresholds_are_left_out_when_the_grader_gives_none_or_a_value_that_is_not_finite(grading):
    report = {"score": 0.5, "gold_medal": False, "silver_medal": False, "bronze_medal": False, "above_median": False,
              "valid_submission": True, "is_lower_better": False, "gold_threshold": float("nan"),
              "silver_threshold": float("inf"), "bronze_threshold": 0.4}  # no median_threshold
    fields = grading.outcome(report, False, TINY / "competition" / "leaderboard.csv")
    assert [name for name in fields if name.endswith("_threshold")] == ["bronze_threshold"]


@pytest.mark.parametrize("case", ["answers", "sample", "missing", "constant-on-correlation"])
def test_the_launchers_readers_accept_the_reward_file_and_the_test_report(tmp_path, case):
    """Harbor's rule (finite numbers only), the slot record's strict reader, ladder.py's reward and graded outcome as
    it reads them from a trial directory, and slot_record.load on an export holding that start."""
    from tests.experiments.long_horizon_record_support import EFFORTS, GRADED_TASK, export, filled, load_kit
    submission, competition = CONTROLS[case]
    tree, env = _tree(tmp_path, submission, competition=competition)
    assert _run(tree, env)[0].returncode == 0
    slot_record, ladder = load_kit("slot_record"), load_kit("ladder")
    rewards = slot_record.read(tree / "logs" / "verifier" / "reward.json")
    assert all(type(v) in (int, float) for v in rewards.values())
    trial = tmp_path / "trial"
    (trial / "verifier").mkdir(parents=True)
    (trial / "result.json").write_text(json.dumps({"verifier_result": {"rewards": rewards}}))
    shutil.copyfile(tree / "logs" / "verifier" / "ctrf.json", trial / "verifier" / "ctrf.json")
    criterion = filled()
    start = {"reward": ladder._reward(trial), "graded": ladder.graded(trial, criterion, GRADED_TASK)}
    slot_record.load(export({GRADED_TASK: {EFFORTS[0]: [start]}}), criterion)
    assert start == {"reward": int(case == "answers"), "graded": {"passed": _passed(json.loads(
        (trial / "verifier" / "ctrf.json").read_text()))[0], "total": 5}}


# --- the percentile -----------------------------------------------------------------------------------------------

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
    (0.85, HIGHER, True, 25.0),  # the same numbers read the other way: beats or ties only 0.9
])
def test_the_percentile_is_the_share_of_the_leaderboard_beaten_or_tied_in_the_metrics_direction(
        grading, score, scores, lower, expected):
    assert grading.percentile(score, scores, lower) == expected


def test_the_percentile_of_an_empty_leaderboard_is_refused(grading):
    with pytest.raises(ValueError):
        grading.percentile(0.5, [], False)


# --- the agent-side format check ----------------------------------------------------------------------------------

AUDIT = """
import json, os, runpy, sys
script, log = sys.argv[1], sys.argv[2]
interpreter = tuple(os.path.realpath(p) + os.sep for p in {sys.prefix, sys.base_prefix, sys.exec_prefix})
opened = []

def hook(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.realpath(os.fsdecode(args[0]))
        if not path.startswith(interpreter) and path not in (os.path.realpath(log), os.path.realpath(script)):
            opened.append(path)

sys.addaudithook(hook)
sys.argv = sys.argv[2:]
sys.argv[0] = script
try:
    runpy.run_path(script, run_name="__main__")
finally:
    with open(log, "w") as f:
        json.dump(opened, f)
"""
PUBLIC_ONLY = {"home/data/sample_submission.csv", "home/submission/submission.csv"}


def _validate(tmp_path, submission):
    """Run the format check in a tree holding only the agent's public files (no private directory anywhere), as
    the instruction tells the agent to; return (process, every file it opened outside the interpreter's own, by its
    path in the tree, or absolute when outside it)."""
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
    opened = {Path(p) for p in json.loads(log.read_text())}
    root = tree.resolve()
    return done, {p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p) for p in opened}


def _codes(done):
    """(the problems' codes, the notes' codes), each sorted: a problem line is "<code>: ...", a note "note: <code>:
    ...", and the accepted verdict "ok: ..."."""
    lines = done.stdout.splitlines()
    problems = [line.split(":", 1)[0] for line in lines if not line.startswith(("note:", "ok:"))]
    notes = [line.split(":")[1].strip() for line in lines if line.startswith("note:")]
    return sorted(problems), sorted(notes)


def _edit(drop_rows=(), add=(), header=None, blank=None):
    """The sample submission with rows dropped, rows added, another header, or one value blanked."""
    lines = SAMPLE.read_text().splitlines()
    head, rows = lines[0], lines[1:]
    if blank is not None:
        rows[blank] = rows[blank].split(",")[0] + ","
    rows = [r for i, r in enumerate(rows) if i not in drop_rows] + list(add)
    return ("\n".join([header or head, *rows]) + "\n").encode()


def _swapped():
    """The sample with its two columns in the other order."""
    rows = [line.split(",") for line in SAMPLE.read_text().splitlines()]
    return ("\n".join(f"{b},{a}" for a, b in rows) + "\n").encode()


ACCEPTED = {
    "sample": (SAMPLE.read_bytes(), []),
    "byte-order-mark": (b"\xef\xbb\xbf" + SAMPLE.read_bytes(), []),
    "trailing-blank-line": (SAMPLE.read_bytes() + b"\n", []),
    "columns-reordered": (_swapped(), []),
    "empty-value": (_edit(blank=3), ["empty-value"]),
}


@pytest.mark.parametrize("case", list(ACCEPTED))
def test_the_format_check_accepts_what_graders_accept_and_opens_only_the_sample_and_the_submission(tmp_path, case):
    """Exit 0 is a pass; an empty value is a note, not a problem (one competition's own sample is all empty)."""
    submission, notes = ACCEPTED[case]
    done, opened = _validate(tmp_path, submission)
    assert (done.returncode, _codes(done)) == (0, ([], notes)), done.stdout + done.stderr
    assert opened == PUBLIC_ONLY
    assert not (tmp_path / "agent" / "private").exists()


SECOND_ID = SAMPLE.read_text().splitlines()[2].split(",")[0]
REFUSED = {
    "missing-column": (b"id\n" + b"".join(r.split(b",")[0] + b"\n" for r in SAMPLE.read_bytes().splitlines()[1:]),
                       (["missing-column"], [])),
    "renamed-column": (_edit(header="id,prob"), (["extra-column", "missing-column"], [])),
    "duplicated-column": (("\n".join(f"{line},{line.split(',')[1]}" for line in SAMPLE.read_text().splitlines())
                           + "\n").encode(), (["duplicate-column"], [])),
    "missing-id": (_edit(drop_rows=[0]), (["missing-id"], [])),
    "extra-id": (_edit(add=["99999999,0.5"]), (["extra-id"], [])),
    "duplicated-id": (_edit(drop_rows=[0], add=[f"{SECOND_ID},0.5"]), (["duplicate-id", "missing-id"], [])),
    "ragged-row": (_edit(add=[f"{SECOND_ID},0.5,7"], drop_rows=[1]), (["ragged-row"], [])),
    "problem-and-note": (_edit(drop_rows=[0], blank=3), (["missing-id"], ["empty-value"])),
    "no-file": (None, (["no-file"], [])),
    "empty-file": (b"", (["empty-file"], [])),
    "not-utf8": (b"id,probability\n\xff,0.5\n", (["unreadable"], [])),
}


@pytest.mark.parametrize("case", list(REFUSED))
def test_the_format_check_refuses_a_structural_problem_with_one_line_per_problem(tmp_path, case):
    submission, codes = REFUSED[case]
    done, opened = _validate(tmp_path, submission)
    assert (done.returncode, _codes(done)) == (1, codes), done.stdout + done.stderr
    assert opened <= PUBLIC_ONLY


def test_the_format_check_needs_its_sample(tmp_path):
    """No public sample: a usage error (exit 2, on stderr), not a verdict on the submission."""
    done = subprocess.run([sys.executable, "-I", str(VALIDATOR), str(SAMPLE), str(tmp_path / "absent.csv")],
                          capture_output=True, text=True, timeout=60)
    assert (done.returncode, done.stdout, done.stderr != "") == (2, "", True)
