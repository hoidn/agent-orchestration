"""MLE-bench family plan, Task 7: the qualification check's logic (experiments/mle_bench_tasks/qualify.py) and the
refusals of qualify.sh that come before any container.

The containers themselves (the images, Harbor, the verifier's grader) run only in qualify.sh on this machine; what is
tested here is what decides its ten lines: the controls' construction around the two lines, the verdict on each leg
and control from recorded rewards, and the reading of Harbor's trial record. The grader is a stand-in that scores
with the fixture's grade.py and reports the fixture's thresholds.
"""

import copy
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "experiments" / "mle_bench_tasks"
QUALIFY_SH = KIT / "qualify.sh"
TINY = ROOT / "tests" / "experiments" / "fixtures" / "mle_bench" / "tiny-tabular"
ANSWERS = TINY / "prepared" / "private" / "answers.csv"
SAMPLE = TINY / "prepared" / "public" / "sample_submission.csv"
LINES = {"gold_threshold": 0.96218, "silver_threshold": 0.91742, "bronze_threshold": 0.83113,
         "median_threshold": 0.806165}  # the fixture's leaderboard, as the benchmark's rule gives them

spec = importlib.util.spec_from_file_location("mle_qualify", KIT / "qualify.py")
qualify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualify)

namespace = {}
exec((TINY / "competition" / "grade.py").read_text(), namespace)
FIXTURE_GRADE = namespace["grade"]


def grader(lower=False):
    """A stand-in for the benchmark's grade_csv: the fixture's AUC (or 1 - AUC as a loss), rounded as the benchmark
    rounds, with the fixture's lines (mirrored for a loss)."""
    answers = pd.read_csv(ANSWERS)

    def grade(path):
        auc = round(FIXTURE_GRADE(pd.read_csv(path), answers), 5)
        lines = {k: round(1 - v, 6) for k, v in LINES.items()} if lower else LINES
        return {"score": round(1 - auc, 5) if lower else auc, "is_lower_better": lower, **lines}
    return grade


def build(tmp_path, lower=False):
    work = tmp_path / "work"
    work.mkdir()
    return qualify.build_controls(ANSWERS, SAMPLE, grader(lower), work), work


# --- the controls (plan M2) ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("lower", [False, True])
def test_each_pair_of_controls_sits_one_row_either_side_of_its_line(tmp_path, lower):
    built, _ = build(tmp_path, lower)
    for line, strict in (("bronze", False), ("median", True)):
        past, short = built["controls"][f"{line}-past"], built["controls"][f"{line}-short"]
        at = built["lines"][line]
        assert short["rows_replaced"] - past["rows_replaced"] == 1
        assert qualify.past(past["score"], at, lower, strict)
        assert not qualify.past(short["score"], at, lower, strict)


def test_each_controls_file_is_graded_to_the_score_recorded_for_it(tmp_path):
    built, work = build(tmp_path)
    grade = grader()
    assert {label: grade(work / f"{label}.csv")["score"] for label in qualify.CONTROLS} == {
        label: c["score"] for label, c in built["controls"].items()}


def test_the_expected_classes_follow_the_scores_and_the_two_lines(tmp_path):
    built, _ = build(tmp_path)
    assert {label: c["expected"] for label, c in built["controls"].items()} == {
        "bronze-past": {"reward": 1, "above_median": 1}, "bronze-short": {"reward": 0, "above_median": 1},
        "median-past": {"reward": 0, "above_median": 1}, "median-short": {"reward": 0, "above_median": 0}}


def test_the_margin_of_a_pair_is_the_distance_between_its_two_scores(tmp_path):
    built, _ = build(tmp_path)
    c = built["controls"]
    assert built["margins"] == {line: pytest.approx(abs(c[f"{line}-past"]["score"] - c[f"{line}-short"]["score"]))
                                for line in ("bronze", "median")}


def test_replaced_rows_take_the_samples_values_by_id_and_the_rest_keep_the_answers():
    answers, sample = pd.read_csv(ANSWERS), pd.read_csv(SAMPLE).iloc[::-1].reset_index(drop=True)
    sample["probability"] = sample["id"] / 10000
    out = qualify.replaced(answers, sample, [3, 0, 7, 1], 2)
    by_id = dict(zip(sample["id"], sample["probability"]))
    assert [out.iloc[i, 1] for i in (3, 0)] == [by_id[answers.iloc[i, 0]] for i in (3, 0)]
    assert [out.iloc[i, 1] for i in (7, 1, 2)] == [answers.iloc[i, 1] for i in (7, 1, 2)]
    assert list(out["id"]) == list(answers["id"])


def test_a_sample_with_other_columns_or_ids_is_refused(tmp_path):
    other = tmp_path / "sample.csv"
    pd.read_csv(SAMPLE).iloc[1:].to_csv(other, index=False)
    with pytest.raises(qualify.Refused, match="sample"):
        qualify.build_controls(ANSWERS, other, grader(), tmp_path)


def test_a_line_the_sample_also_passes_is_recorded_as_unbuilt(tmp_path):
    def grade(path):
        return grader()(path) | {"bronze_threshold": 0.4}
    built = qualify.build_controls(ANSWERS, SAMPLE, grade, tmp_path)
    assert built["unbuilt"] == ["bronze"]
    assert sorted(built["controls"]) == ["median-past", "median-short"]


# --- the ten lines ------------------------------------------------------------------------------------------------

SCORED = {"reward": 0, "valid_submission": 1, "above_median": 0, "medal": 0, "grader_exception": 0, "score": 0.5,
          "percentile": 0.0, **LINES}
UNSCORED = {"reward": 0, "valid_submission": 0, "above_median": 0, "medal": 0, "grader_exception": 0, **LINES}
GOLD = SCORED | {"reward": 1, "above_median": 1, "medal": 3, "score": 1.0, "percentile": 100.0}
CONTROLS = {
    "lines": {"bronze": 0.83113, "median": 0.806165}, "lower_is_better": False, "unbuilt": [],
    "controls": {
        "bronze-past": {"rows_replaced": 20, "score": 0.83333, "expected": {"reward": 1, "above_median": 1}},
        "bronze-short": {"rows_replaced": 21, "score": 0.8125, "expected": {"reward": 0, "above_median": 1}},
        "median-past": {"rows_replaced": 21, "score": 0.8125, "expected": {"reward": 0, "above_median": 1}},
        "median-short": {"rows_replaced": 22, "score": 0.79, "expected": {"reward": 0, "above_median": 0}}}}


def outcomes():
    control = {"bronze-past": SCORED | {"reward": 1, "medal": 1, "above_median": 1, "score": 0.83333,
                                        "percentile": 65.0},
               "bronze-short": SCORED | {"above_median": 1, "score": 0.8125, "percentile": 60.0},
               "median-past": SCORED | {"above_median": 1, "score": 0.8125, "percentile": 60.0},
               "median-short": SCORED | {"score": 0.79, "percentile": 45.0}}
    return {"answers-1": GOLD, "answers-2": GOLD, "sample-1": SCORED, "sample-2": SCORED,
            "untouched-1": UNSCORED, "untouched-2": UNSCORED, **{f"control-{k}": v for k, v in control.items()}}


def verdicts(recorded, controls=CONTROLS, floor=None):
    return [line.split(":")[1].split()[0] for line in qualify.lines(recorded, controls, floor)]


def test_ten_lines_all_ok_in_the_planned_order():
    shown = qualify.lines(outcomes(), CONTROLS, None)
    assert [line.split(":")[0] for line in shown] == [
        "answers 1", "answers 2", "sample 1", "sample 2", "untouched 1", "untouched 2", "control bronze-past",
        "control bronze-short", "control median-past", "control median-short"]
    assert verdicts(outcomes()) == ["ok"] * 10


def failed(recorded, **kw):
    return [i for i, v in enumerate(verdicts(recorded, **kw)) if v != "ok"]


def test_an_answers_run_without_gold_fails():
    assert failed(outcomes() | {"answers-1": GOLD | {"medal": 2}}) == [0]


def test_a_second_run_whose_score_differs_from_the_first_fails():
    assert failed(outcomes() | {"sample-2": SCORED | {"score": 0.50001}}) == [3]


def test_a_sample_run_that_is_not_valid_or_earns_a_medal_fails():
    assert failed(outcomes() | {"sample-1": UNSCORED, "sample-2": UNSCORED}) == [2, 3]
    assert failed(outcomes() | {"sample-1": GOLD, "sample-2": GOLD}) == [2, 3]


def test_a_sample_run_must_score_the_listed_floor_where_one_is_given():
    assert failed(outcomes(), floor=0.5) == []
    assert failed(outcomes(), floor=0.4) == [2, 3]


def test_an_untouched_run_needs_a_written_reward_of_0():
    assert failed(outcomes() | {"untouched-1": None}) == [4]
    assert failed(outcomes() | {"untouched-2": GOLD}) == [5]


def test_a_control_outside_its_expected_class_fails():
    recorded = outcomes()
    recorded["control-bronze-short"] = recorded["control-bronze-short"] | {"above_median": 0}
    recorded["control-median-short"] = recorded["control-median-short"] | {"reward": 1, "medal": 1}
    assert failed(recorded) == [7, 9]


def test_a_control_whose_verifier_score_is_not_its_host_score_fails():
    recorded = outcomes()
    recorded["control-median-past"] = recorded["control-median-past"] | {"score": 0.81251}
    assert 8 in failed(recorded)


def test_percentiles_out_of_the_order_of_the_scores_fail_every_control():
    recorded = outcomes()
    recorded["control-median-short"] = recorded["control-median-short"] | {"percentile": 70.0}
    assert failed(recorded) == [6, 7, 8, 9]


def test_a_missing_control_fails_its_line():
    recorded = outcomes()
    del recorded["control-bronze-past"]
    assert 6 in failed(recorded)


def test_an_unbuilt_pair_fails_its_two_lines():
    controls = copy.deepcopy(CONTROLS)
    controls["unbuilt"] = ["median"]
    for label in ("median-past", "median-short"):
        del controls["controls"][label]
    assert failed(outcomes(), controls=controls) == [8, 9]


@pytest.mark.parametrize("label", ["answers-1", "untouched-2", "control-bronze-past"])
def test_a_reward_file_with_keys_this_run_did_not_record_fails(label):
    recorded = outcomes()
    recorded[label] = recorded[label] | {"any_medal": 1}
    assert len(failed(recorded)) >= 1
    recorded = outcomes()
    recorded[label] = {k: v for k, v in recorded[label].items() if k != "grader_exception"}
    assert len(failed(recorded)) >= 1


# --- reading Harbor's trial record --------------------------------------------------------------------------------

def trial(jobs, rewards, exception=None, name="task__abc"):
    path = jobs / "job" / name / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"verifier_result": None if rewards is None else {"rewards": rewards},
                                "exception_info": exception}))


def test_record_keeps_the_rewards_the_harness_read_under_the_label(tmp_path):
    trial(tmp_path / "a", GOLD)
    trial(tmp_path / "b", None, {"exception_type": "VerifierTimeoutError"})
    out = tmp_path / "outcomes.json"
    qualify.record("answers-1", tmp_path / "a", out)
    qualify.record("untouched-1", tmp_path / "b", out)
    assert json.loads(out.read_text()) == {"answers-1": GOLD, "untouched-1": None}


def test_record_refuses_a_jobs_directory_without_exactly_one_trial(tmp_path):
    with pytest.raises(qualify.Refused):
        qualify.record("answers-1", tmp_path, tmp_path / "outcomes.json")
    trial(tmp_path, GOLD)
    trial(tmp_path, GOLD, name="task__def")
    with pytest.raises(qualify.Refused):
        qualify.record("answers-1", tmp_path, tmp_path / "outcomes.json")


# --- qualify.sh: what it refuses before anything is built ---------------------------------------------------------

def run_sh(tmp_path, *args, **env):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    full = {"PATH": os.environ["PATH"], "HOME": str(home), **env}
    return subprocess.run(["bash", str(QUALIFY_SH), *args], capture_output=True, text=True, env=full, timeout=60)


FIXTURE_ARGS = ("tinytab", str(TINY / "competition"), str(TINY.parent))


@pytest.mark.parametrize("args", [(), ("tinytab",), FIXTURE_ARGS + ("extra",)])
def test_qualify_refuses_another_number_of_arguments(tmp_path, args):
    done = run_sh(tmp_path, *args)
    assert (done.returncode, done.stderr.startswith("qualify.sh: refused: usage")) == (2, True)


@pytest.mark.parametrize("name", ["Tiny", "-tiny", "a-name-too-long"])
def test_qualify_refuses_a_task_name_the_launcher_cannot_use(tmp_path, name):
    done = run_sh(tmp_path, name, *FIXTURE_ARGS[1:])
    assert (done.returncode, "task name" in done.stderr) == (2, True)


def test_qualify_refuses_a_competition_directory_without_config(tmp_path):
    done = run_sh(tmp_path, "tinytab", str(tmp_path), FIXTURE_ARGS[2])
    assert (done.returncode, "config.yaml" in done.stderr) == (2, True)


def test_qualify_refuses_an_output_directory_that_holds_earlier_runs(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "earlier").touch()
    done = run_sh(tmp_path, *FIXTURE_ARGS, OUT=str(out))
    assert (done.returncode, "earlier runs" in done.stderr) == (2, True)


def test_qualify_refuses_a_recordings_directory_that_is_a_link_and_writes_nothing(tmp_path):
    mle = tmp_path / "home" / "mle-cache"
    mle.mkdir(parents=True)
    (mle / "recordings").symlink_to(tmp_path)
    done = run_sh(tmp_path, *FIXTURE_ARGS)
    assert (done.returncode, "recordings" in done.stderr) == (2, True)
    assert sorted(p.name for p in mle.iterdir()) == ["recordings"]


def test_qualify_creates_the_recordings_directory_mode_700_before_its_later_refusals(tmp_path):
    """The setup of M4: ~/mle-cache/recordings, a directory of its own, mode 700 (here the run then stops at the
    harness environment, which the stand-in home does not have)."""
    done = run_sh(tmp_path, *FIXTURE_ARGS)
    recordings = tmp_path / "home" / "mle-cache" / "recordings"
    assert (done.returncode, "harness environment" in done.stderr) == (2, True)
    assert (recordings.is_dir(), recordings.is_symlink(), recordings.stat().st_mode & 0o777) == (True, False, 0o700)
