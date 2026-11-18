"""The verifier of an MLE-bench attempt (family plan, Task 2; decisions M1, M2 and M4): grade the one submission the
agent left with the benchmark's grader and write the reward file and the five-line test report the harness reads.

Usage (from test.sh, in the verifier image): python3 -I grade_submission.py      no arguments; paths from IN_IMAGE

Reads (in-image paths; each can be moved by the environment variable of the same name, which the tests do):
  MLE_COMPETITION_ID   the competition id (no default; the image sets it)
  MLE_SUBMISSION       the submission, the task's one artifact
  MLE_DATA_DIR         the grader's data directory: <id>/prepared/private/ holds the held-out answers
  MLE_BENCHMARK_DIR    the benchmark's source at the pinned commit; it is put first on sys.path, and the competition's
                       grading code, config.yaml and leaderboard.csv sit in mlebench/competitions/<id>/, where the
                       benchmark's registry looks for them
  MLE_GRADER_WORK      the working directory: the benchmark opens a cache in the current directory when it is imported
Writes, in MLE_LOGS_DIR, each by a temporary file and a rename, reward.json first:
  reward.json          reward is 1 for any medal, else 0. Beside it: valid_submission, above_median (0 or 1), medal
                       (0 none, 1 bronze, 2 silver, 3 gold) and grader_exception (see below); score and percentile
                       only when the
                       grader gives a finite score; gold_, silver_, bronze_ and median_threshold as the grader reports
                       them, each left out when not finite. Never a null: Harbor accepts finite numbers only
  ctrf.json            five tests (valid, above_median, bronze, silver, gold), each passed or failed; the launcher
                       exports results.summary.passed and .tests as the graded outcome

Outcomes, all with a written reward of 0 unless a medal is earned:
  - a submission that is a symbolic link, is larger than the size cap, or cannot be read as CSV by pandas (malformed,
    empty, not UTF-8) is never given to the grader: the grader grades an absent file instead, which yields its
    thresholds and no score (not valid), and the reason goes to standard error;
  - a score that is not finite (NaN, as pearsonr gives for a constant column, or infinite) counts as no score;
    valid_submission stays what the grader reports;
  - the benchmark catches every exception of a competition's grade function and reports no score, so a fault on the
    grader's side there cannot be told from a bad submission: reward 0. grader_exception is 1 when the benchmark
    logged an unexpected exception (anything but its InvalidSubmissionError) inside the competition's grade
    function in this run, else 0. For several competitions a faulty submission causes exactly that (a grade
    function that checks with assert, or the fixture's plain ValueError), so the flag marks an attempt for a person
    to look at; it is not evidence of a grader fault.
A failure outside the grade function (the registry cannot find the competition, the answers are missing or
unreadable, the leaderboard is missing, an import fails) escapes: exit non-zero, the error on standard error, and
neither file written, which the launcher classifies as an infrastructure failure, never as a failed attempt.
"""

import csv
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

IN_IMAGE = {
    "MLE_SUBMISSION": "/home/submission/submission.csv",
    "MLE_DATA_DIR": "/private/data",
    "MLE_BENCHMARK_DIR": "/opt/mle-bench",
    "MLE_GRADER_WORK": "/grader-work",
    "MLE_LOGS_DIR": "/logs/verifier",
}
TESTS = ("valid", "above_median", "bronze", "silver", "gold")
THRESHOLDS = ("gold_threshold", "silver_threshold", "bronze_threshold", "median_threshold")
GRADER_LOGGER = "mlebench.grade_helpers"  # Grader.__call__ logs an ERROR for an unexpected error of the grade function
CAP_FLOOR, CAP_MULTIPLE = 64 * 2**20, 5  # the size cap: the larger of 64 MiB and 5 times the largest private file
ABSENT = "refused-submission.csv"  # what the grader is given, in the work directory, for a refused submission


class _Flag(logging.Handler):
    """Set by any ERROR record the benchmark's Grader logs while it is attached."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.raised = False

    def emit(self, record):
        self.raised = True


def benchmark_report(submission, competition_id, data_dir, benchmark_dir):
    """The one call into the benchmark's grader: mlebench.grade.grade_csv on the registry pointed at data_dir.
    Returns (CompetitionReport.to_dict(), whether the Grader logged an unexpected error). In the suite a stand-in
    mlebench package sits at benchmark_dir."""
    sys.path.insert(0, str(benchmark_dir))
    from mlebench.grade import grade_csv
    from mlebench.registry import registry
    competition = registry.set_data_dir(data_dir).get_competition(competition_id)
    flag = _Flag()
    logging.getLogger(GRADER_LOGGER).addHandler(flag)
    return grade_csv(submission, competition).to_dict(), flag.raised


def size_cap(private_dir, floor=CAP_FLOOR, multiple=CAP_MULTIPLE):
    """The larger of floor and multiple times the largest file of the private directory (the answers, or a gold
    submission beside them)."""
    sizes = [p.stat().st_size for p in private_dir.rglob("*") if p.is_file()] if private_dir.is_dir() else []
    return max([floor] + [multiple * s for s in sizes])


def refusal(submission, cap):
    """Why the submission is not given to the grader, as "<code>: <detail>", or None. The benchmark's grade_csv lets
    a read error escape, which would make the agent's bad file look like a grader failure (ruling 2), and it follows
    links and reads any size; an absent file is left to the grader, which reports it itself."""
    if submission.is_symlink():
        return "symlink: the submission is a symbolic link; it is not followed"
    if not submission.is_file():
        return None
    if submission.stat().st_size > cap:
        return f"oversized: {submission.stat().st_size} bytes, above the cap of {cap}"
    import pandas as pd
    try:  # the benchmark's own reader (mlebench.utils.read_csv)
        pd.read_csv(submission, float_precision="round_trip")
    except (OSError, ValueError) as e:  # ValueError: pandas' ParserError, EmptyDataError; UnicodeDecodeError
        return f"unreadable: {type(e).__name__}: {e}"
    return None


def percentile(score, scores, lower_is_better):
    """The share of the leaderboard's scores, in percent, that score beats or ties in the metric's direction (plan M1).
    A score past the best gives 100, one short of the worst 0."""
    if not scores:
        raise ValueError("the leaderboard has no scores")
    beaten = sum(s >= score if lower_is_better else s <= score for s in scores)
    return 100.0 * beaten / len(scores)


def leaderboard_scores(path):
    """The leaderboard's score column, best first as the snapshot lists it."""
    with open(path, newline="") as f:
        return [float(row["score"]) for row in csv.DictReader(f)]


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def outcome(report, grader_exception, leaderboard):
    """The reward file's fields from a grader report; leaderboard is read only when there is a finite score."""
    score = report["score"]
    scored = _finite(score)
    medal = (3 if report["gold_medal"] else 2 if report["silver_medal"] else 1 if report["bronze_medal"] else 0
             ) if scored else 0
    fields = {"reward": int(medal > 0), "valid_submission": int(report["valid_submission"]),
              "above_median": int(scored and report["above_median"]), "medal": medal,
              "grader_exception": int(grader_exception)}
    if scored:
        fields["score"] = score
        fields["percentile"] = percentile(score, leaderboard_scores(leaderboard), report["is_lower_better"])
    return fields | {name: report[name] for name in THRESHOLDS if _finite(report.get(name))}


def test_report(fields, start_ms):
    """The five-line test report in the CTRF form the launcher reads (results.summary.passed and .tests)."""
    passed = {"valid": fields["valid_submission"] == 1, "above_median": fields["above_median"] == 1,
              "bronze": fields["medal"] >= 1, "silver": fields["medal"] >= 2, "gold": fields["medal"] == 3}
    tests = [{"name": name, "status": "passed" if passed[name] else "failed", "duration": 0} for name in TESTS]
    n = sum(passed.values())
    return {"results": {"tool": {"name": "mle-bench-verifier"}, "tests": tests, "summary": {
        "tests": len(TESTS), "passed": n, "failed": len(TESTS) - n, "pending": 0, "skipped": 0, "other": 0,
        "start": start_ms, "stop": int(time.time() * 1000)}}}


def _write(path, text):
    """Write by a temporary file in the same directory and a rename, so a reader never sees a partial file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def main(env=os.environ, cap=None):
    """Grade and write both files; cap overrides the size cap (the tests lower it)."""
    start_ms = int(time.time() * 1000)
    paths = {name: Path(env.get(name, default)) for name, default in IN_IMAGE.items()}
    competition_id = env["MLE_COMPETITION_ID"]
    submission, bench, work = paths["MLE_SUBMISSION"], paths["MLE_BENCHMARK_DIR"], paths["MLE_GRADER_WORK"]
    work.mkdir(parents=True, exist_ok=True)
    os.chdir(work)
    private = paths["MLE_DATA_DIR"] / competition_id / "prepared" / "private"
    reason = refusal(submission, size_cap(private) if cap is None else cap)
    if reason:
        print(reason, file=sys.stderr)
    graded = work / ABSENT if reason else submission
    report, raised = benchmark_report(graded, competition_id, paths["MLE_DATA_DIR"], bench)
    fields = outcome(report, raised, bench / "mlebench" / "competitions" / competition_id / "leaderboard.csv")
    texts = {"reward.json": json.dumps(fields, allow_nan=False) + "\n",
             "ctrf.json": json.dumps(test_report(fields, start_ms), indent=2) + "\n"}
    paths["MLE_LOGS_DIR"].mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():  # reward.json first
        _write(paths["MLE_LOGS_DIR"] / name, text)


if __name__ == "__main__":
    main()
