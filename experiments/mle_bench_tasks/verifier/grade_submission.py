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
Writes, in MLE_LOGS_DIR:
  ctrf.json            five tests (valid, above_median, bronze, silver, gold), each passed or failed; the launcher
                       exports results.summary.passed and .tests as the graded outcome
  reward.json          written last. reward is 1 for any medal, else 0. Beside it: valid_submission, above_median
                       (0 or 1) and medal (0 none, 1 bronze, 2 silver, 3 gold); score and percentile only when the
                       grader gives a score, never as 0 or null (Harbor accepts finite numbers only)

Outcomes: a missing, empty, unreadable or malformed submission is graded as one with no score (reward 0, not valid);
an error inside the grader (the answers absent, the benchmark not importable, a bad leaderboard) escapes, so the
script exits non-zero with the error on standard error and writes no reward file, which the launcher classifies as
an infrastructure failure, never as a failed attempt.
"""

import csv
import json
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
# The report the benchmark's grade_csv gives a submission it cannot score (rank_score of a null score).
NO_SCORE = {"score": None, "valid_submission": False, "above_median": False, "gold_medal": False,
            "silver_medal": False, "bronze_medal": False, "is_lower_better": False}


def benchmark_report(submission, competition_id, data_dir, benchmark_dir):
    """The one call into the benchmark's grader: mlebench.grade.grade_csv on the registry pointed at data_dir.
    Returns CompetitionReport.to_dict(). In the suite a stand-in mlebench package sits at benchmark_dir."""
    sys.path.insert(0, str(benchmark_dir))
    from mlebench.grade import grade_csv
    from mlebench.registry import registry
    return grade_csv(submission, registry.set_data_dir(data_dir).get_competition(competition_id)).to_dict()


def unreadable(submission):
    """True for a file pandas cannot read as CSV (malformed, not UTF-8, empty, unreadable). The benchmark's grade_csv
    lets that error escape, which would make the agent's bad file look like a grader failure (ruling 2); an absent
    file is left to the grader, which reports it itself."""
    if not submission.is_file():
        return False
    import pandas as pd
    try:  # the benchmark's own reader (mlebench.utils.read_csv)
        pd.read_csv(submission, float_precision="round_trip")
    except (OSError, ValueError):  # pandas' ParserError and EmptyDataError, and UnicodeDecodeError, are ValueErrors
        return True
    return False


def percentile(score, scores, lower_is_better):
    """The share of the leaderboard's scores, in percent, that score beats or ties in the metric's direction (plan M1).
    A score past the best gives 100, one short of the worst 0."""
    if not scores:
        raise ValueError("the leaderboard has no scores")
    beaten = sum(s >= score if lower_is_better else s <= score for s in scores)
    return 100.0 * beaten / len(scores)


def leaderboard_scores(path):
    with open(path, newline="") as f:
        return [float(row["score"]) for row in csv.DictReader(f)]


def outcome(report, leaderboard):
    """The reward file's fields from a grader report; leaderboard is read only when there is a score."""
    medal = 3 if report["gold_medal"] else 2 if report["silver_medal"] else 1 if report["bronze_medal"] else 0
    fields = {"reward": int(medal > 0), "valid_submission": int(report["valid_submission"]),
              "above_median": int(report["above_median"]), "medal": medal}
    if report["score"] is not None:
        fields["score"] = report["score"]
        fields["percentile"] = percentile(report["score"], leaderboard_scores(leaderboard), report["is_lower_better"])
    return fields


def test_report(fields, start_ms):
    """The five-line test report in the CTRF form the launcher reads (results.summary.passed and .tests)."""
    passed = {"valid": fields["valid_submission"] == 1, "above_median": fields["above_median"] == 1,
              "bronze": fields["medal"] >= 1, "silver": fields["medal"] >= 2, "gold": fields["medal"] == 3}
    tests = [{"name": name, "status": "passed" if passed[name] else "failed", "duration": 0} for name in TESTS]
    n = sum(passed.values())
    return {"results": {"tool": {"name": "mle-bench-verifier"}, "tests": tests, "summary": {
        "tests": len(TESTS), "passed": n, "failed": len(TESTS) - n, "pending": 0, "skipped": 0, "other": 0,
        "start": start_ms, "stop": int(time.time() * 1000)}}}


def main(env=os.environ):
    start_ms = int(time.time() * 1000)
    paths = {name: Path(env.get(name, default)) for name, default in IN_IMAGE.items()}
    competition_id = env["MLE_COMPETITION_ID"]
    submission, bench = paths["MLE_SUBMISSION"], paths["MLE_BENCHMARK_DIR"]
    paths["MLE_GRADER_WORK"].mkdir(parents=True, exist_ok=True)
    os.chdir(paths["MLE_GRADER_WORK"])
    report = NO_SCORE if unreadable(submission) else benchmark_report(
        submission, competition_id, paths["MLE_DATA_DIR"], bench)
    fields = outcome(report, bench / "mlebench" / "competitions" / competition_id / "leaderboard.csv")
    logs = paths["MLE_LOGS_DIR"]
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "ctrf.json").write_text(json.dumps(test_report(fields, start_ms), indent=2) + "\n")
    (logs / "reward.json").write_text(json.dumps(fields, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
