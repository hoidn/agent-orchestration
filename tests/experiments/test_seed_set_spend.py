"""Seed-set spend guard (experiments/seed_set/spend.py) and the runner's refusals before any provider start
(experiments/seed_set/study.py). Nothing here launches a process; the end-to-end launch path is in
test_seed_set_e2e.py."""

import json
import shutil
from pathlib import Path

import pytest

from experiments.seed_set import spend, study

H, S = spend.HAIKU, spend.SONNET
ROOT = Path(__file__).resolve().parents[2]
AUTH = spend.AUTHORIZATION


def env(tranche):
    return {AUTH: tranche}


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "results" / "spend-ledger.jsonl"


def test_no_authorization_variable_refuses():
    with pytest.raises(SystemExit, match="provider spend refused"):
        spend.authorize("calibration", {})


def test_an_authorization_for_another_tranche_refuses():
    with pytest.raises(SystemExit, match="provider spend refused"):
        spend.authorize("calibration", env("smoke"))


@pytest.mark.parametrize("tranche", ["seed_evaluation", "extension"])
def test_an_unauthorized_tranche_refuses_even_when_named(tranche):
    with pytest.raises(SystemExit, match="not authorized"):
        spend.authorize(tranche, env(tranche))


def test_an_unknown_tranche_refuses():
    with pytest.raises(SystemExit, match="unknown tranche"):
        spend.authorize("bonus", env("bonus"))


def test_caps_are_the_plans_budget():
    caps = {t: {k: dict(m) for k, m in kinds.items()} for t, kinds in spend.CAPS.items()}
    assert caps == {"smoke": {"candidate": {H: 10, S: 1}, "judge": {H: 1, S: 1}},
                    "calibration": {"candidate": {H: 80, S: 20}, "judge": {H: 30, S: 30}},
                    "redraw": {"candidate": {H: 40, S: 10}, "judge": {H: 15, S: 15}}}


def test_a_start_is_appended_before_it_is_returned(ledger):
    row = spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/records/retry/run-1", env("smoke"), task="t")
    assert spend.rows(ledger) == [row]


def test_a_unit_is_never_started_twice(ledger):
    spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/records/direct/run-1", env("smoke"))
    with pytest.raises(SystemExit, match="never retried"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/records/direct/run-1", env("smoke"))


def test_the_call_beyond_a_cap_refuses_and_writes_nothing(ledger):
    for k in range(10):
        spend.reserve(ledger, "smoke", "candidate", H, 1, f"/w/run-{k}", env("smoke"))
    before = ledger.read_bytes()
    with pytest.raises(SystemExit, match="cap reached"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-10", env("smoke"))
    assert ledger.read_bytes() == before


def test_a_start_reserves_its_maximum_calls_against_the_cap(ledger):
    spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/a", env("smoke"))
    spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/b", env("smoke"))
    spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/c", env("smoke"))
    with pytest.raises(SystemExit, match="cap reached"):
        spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/d", env("smoke"))


def test_tranches_and_kinds_do_not_share_allowance(ledger):
    spend.reserve(ledger, "smoke", "judge", S, 1, "/p#s", env("smoke"))
    with pytest.raises(SystemExit, match="cap reached"):
        spend.reserve(ledger, "smoke", "judge", S, 1, "/q#s", env("smoke"))
    assert spend.reserve(ledger, "calibration", "judge", S, 1, "/q#s", env("calibration"))["seq"] == 2


def test_a_batch_that_does_not_fit_is_refused_before_any_start(ledger):
    with pytest.raises(SystemExit, match="21 calls planned but 20"):
        spend.check(ledger, "calibration", "candidate", S, 21, env("calibration"))


@pytest.mark.parametrize("model", ["claude-fable-5-1", "claude-opus-5-5", "claude-haiku", "haiku", "", None])
def test_a_model_outside_the_two_exact_ids_refuses_and_writes_nothing(ledger, model):
    with pytest.raises(SystemExit, match="exact IDs"):
        spend.reserve(ledger, "smoke", "candidate", model, 1, "/w/run-1", env("smoke"))
    assert not ledger.exists()


@pytest.fixture
def runner(tmp_path):
    """A study whose runtime holds only a copy of the programs, with an empty task list and criterion."""
    programs = tmp_path / "runtime" / study.PROGRAMS
    shutil.copytree(ROOT / study.PROGRAMS, programs)
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text("".join(json.dumps({"id": i, "set": s, "commit": "f" * 40}) + "\n"
                             for i, s in (("t1", "drawn"), ("t2", "drawn"), ("r1", "reserve"), ("r2", "reserve"))))
    criterion = tmp_path / "criterion.json"
    criterion.write_text(json.dumps({"judges": [H, S], "rubric": study.RUBRIC}))
    return study.Study(tmp_path / "runtime", tmp_path / "work", tmp_path / "pools", tmp_path / "results", tasks,
                       criterion)


def test_candidates_without_authorization_refuse_before_preparing_anything(runner, monkeypatch):
    monkeypatch.delenv(AUTH, raising=False)
    with pytest.raises(SystemExit, match="provider spend refused"):
        study.candidates(runner, "calibration", "direct", ["t1"])
    assert not runner.work.exists()


def test_the_seed_evaluation_refuses_outright(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "seed_evaluation")
    with pytest.raises(SystemExit, match="not authorized"):
        study.candidates(runner, "seed_evaluation", "direct", ["t1"])


def test_judges_without_authorization_refuse(runner, monkeypatch):
    monkeypatch.delenv(AUTH, raising=False)
    with pytest.raises(SystemExit, match="provider spend refused"):
        study.judge(runner, "calibration", "first", ["t1"])


@pytest.mark.parametrize("tranche, arm, tasks, match", [
    ("calibration", "retry_until_check", ["t1"], "not retry_until_check"),
    ("calibration", "direct", ["r1"], "takes tasks among"),
    ("smoke", "direct", ["r1"], "takes tasks among"),  # the smoke runs on the last reserve task only
    ("redraw", "direct", ["r2"], "takes tasks among"),
])
def test_a_run_outside_the_tranches_plan_refuses(runner, monkeypatch, tranche, arm, tasks, match):
    monkeypatch.setenv(AUTH, tranche)
    with pytest.raises(SystemExit, match=match):
        study.candidates(runner, tranche, arm, tasks)


def test_planned_runs_already_started_are_not_launched_again(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    for k in range(4):
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, f"/w/{k}", task="t1", arm="direct")
    assert study.candidates(runner, "calibration", "direct", ["t1"]) == []


@pytest.mark.parametrize("change", [{"model": "claude-fable-5-1"}, {"model": "claude-opus-5-5"},
                                    {"effort": "high"}, {"max_calls": 4}])
def test_arms_binding_another_model_effort_or_call_count_refuse(runner, change):
    path = runner.programs / "arms.json"
    arms = json.loads(path.read_text())
    arms["direct"] |= change
    path.write_text(json.dumps(arms))
    with pytest.raises(SystemExit):
        study.load_arms(runner)


@pytest.mark.parametrize("change", [{"purpose": "calibration"}, {"calibration": {"rule": "control-means-v1"}},
                                    {"judges": [H]}, {"rubric": {**study.RUBRIC, "workflow": "score.orc"}}])
def test_a_criterion_that_would_skip_hidden_tests_or_drop_a_judge_refuses(runner, change):
    runner.criterion.write_text(json.dumps({"judges": [H, S], "rubric": study.RUBRIC} | change))
    with pytest.raises(SystemExit, match="judge-calibration criterion"):
        study.load_criterion(runner)


def test_a_run_refuses_to_start_below_the_free_disk_floor(runner):
    full = study.Study(*[getattr(runner, f) for f in ("runtime", "work", "pools", "results", "tasks_file",
                                                       "criterion")], min_free=10**18)
    with pytest.raises(SystemExit, match="GB free"):
        study.require_free(full, full.work)


def test_a_third_live_pool_refuses(runner):
    for task in ("t1", "t2"):
        (runner.pools / task / "first" / "clones").mkdir(parents=True)
    with pytest.raises(SystemExit, match="two pools still hold clones"):
        study.build_pools(runner, "calibration", "retest", ["t1"])


def test_a_retest_takes_only_the_tranches_first_tasks(runner):
    with pytest.raises(SystemExit, match="takes tasks among"):
        study.build_pools(runner, "smoke", "retest", ["r2"])
