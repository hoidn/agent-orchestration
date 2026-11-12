"""Seed-set spend guard (experiments/seed_set/spend.py), the order and stop rules (rules.py), the per-unit checks
(units.py, host.py) and the runner's refusals before any provider start (study.py). Nothing here launches a
provider process; the end-to-end launch path is in test_seed_set_e2e.py."""

import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from experiments.compare.repos import sha256_file
from experiments.seed_set import host, layout, rules, spend, study, units

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
                    "redraw": {"candidate": {H: 40, S: 0}, "judge": {H: 0, S: 0}}}  # review2 M4: probe only


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
    """A study whose runtime is a git checkout holding only the programs, with a small task list, a frozen
    criterion pair and its own state directory."""
    runtime = tmp_path / "runtime"
    shutil.copytree(ROOT / layout.PROGRAMS, runtime / layout.PROGRAMS, ignore=shutil.ignore_patterns("__pycache__"))
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "rt"]):
        subprocess.run(["git", "-C", str(runtime), *args], check=True)
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text("".join(json.dumps({"id": i, "set": s, "commit": "f" * 40, "tier": "T3", "form": "in-tree"}) + "\n"
                             for i, s in (("t1", "drawn"), ("t2", "drawn"), ("r1", "reserve"), ("r2", "smoke"))))
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / layout.CHOSEN).write_text(json.dumps({"tasks": [{"id": "t1", "rung": "T3"},
                                                                            {"id": "t2", "rung": "T3"}]}))
    criterion = tmp_path / "judge-calibration.json"
    criterion.write_text(json.dumps({"judges": [H, S], "rubric": layout.RUBRIC}))
    (tmp_path / "criterion.json").write_text(json.dumps({"plan": "frozen"}))
    return layout.Study(runtime, tmp_path / "work", tmp_path / "pools", tmp_path / "results", tasks, criterion,
                        tmp_path / "state")


def ready(runner, smoke=True, chosen=True):
    """The ledger as the calibration needs it: a freeze and, unless told otherwise, a passed smoke and the probe
    readout's hash of the chosen tasks (t1 and t2)."""
    rules.record_freeze(runner)
    if smoke:
        spend.record(runner.ledger, "smoke", passed=True)
    if chosen:
        spend.record(runner.ledger, "probe_readout", answer={"chosen": "T3"},
                     chosen_sha256=sha256_file(runner.results / layout.CHOSEN))


def run_dir(runner, arm="direct", k=1, calls=0, **facts):
    """A candidate run's records directory with `calls` recorded calls and its study.json."""
    records = runner.work / "records" / arm / f"run-{k}"
    for n in range(1, calls + 1):
        (records / "calls" / str(n)).mkdir(parents=True)
        (records / "calls" / str(n) / "prompt.txt").write_text("p")
    records.mkdir(parents=True, exist_ok=True)
    (records / "record.json").write_text(json.dumps(facts.pop("record", {})))
    (records / "study.json").write_text(json.dumps({"tranche": "calibration", "task": "t1", "arm": arm,
                                                    "model": H, "effort": "medium", "max_calls": 1} | facts))
    return records


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
    ("redraw", "direct", ["t1"], "ladder probe only"),
])
def test_a_run_outside_the_tranches_plan_refuses(runner, monkeypatch, tranche, arm, tasks, match):
    monkeypatch.setenv(AUTH, tranche)
    with pytest.raises(SystemExit, match=match):
        study.candidates(runner, tranche, arm, tasks)


def test_planned_runs_already_started_are_not_launched_again(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    for k in range(4):
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, f"/w/{k}", task="t1", arm="direct")
    assert study.candidates(runner, "calibration", "direct", ["t1", "t1"]) == []


def test_the_ledger_lies_in_the_home_state_directory_whatever_the_results_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    ledgers = {study.study_of(study.parser().parse_args(["--results", str(tmp_path / name), "ledger"])).ledger
               for name in ("a", "b")}
    assert ledgers == {tmp_path / ".local" / "state" / "seed-set" / "spend-ledger.jsonl"}


def test_a_run_with_calls_but_no_ledger_row_refuses_every_start(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    run_dir(runner, calls=1, exit=0)  # the ledger that held it is gone, or belongs to another study
    with pytest.raises(SystemExit, match="has no row"):
        study.candidates(runner, "calibration", "direct", ["t2"])


def test_a_unit_with_more_calls_than_reserved_refuses(runner):
    records = run_dir(runner, calls=2, exit=0)
    spend.reserve(runner.ledger, "calibration", "candidate", H, 1, records, env("calibration"))
    with pytest.raises(SystemExit, match="2 calls made, 1 reserved"):
        rules.audit_ledger(runner)


def test_starts_beyond_the_planned_runs_of_a_task_and_arm_refuse_under_the_lock(ledger):
    won = []

    def take(k):
        try:
            spend.reserve(ledger, "calibration", "candidate", H, 1, f"/w/{k}", env("calibration"), limit=4,
                          task="t1", arm="direct")
            won.append(k)
        except SystemExit:
            pass
    threads = [threading.Thread(target=take, args=(k,)) for k in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(won) == 4


def test_no_start_before_the_freeze_is_recorded(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "smoke")
    with pytest.raises(SystemExit, match="no freeze"):
        study.candidates(runner, "smoke", "direct", ["r2"])


def test_no_start_once_the_frozen_criterion_changed(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "smoke")
    ready(runner)
    runner.frozen.write_text(json.dumps({"plan": "edited"}))
    with pytest.raises(SystemExit, match="changed since the freeze"):
        study.candidates(runner, "smoke", "direct", ["r2"])


def test_no_calibration_without_a_passed_smoke(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner, smoke=False)
    spend.record(runner.ledger, "smoke", passed=False)
    with pytest.raises(SystemExit, match="no passed smoke"):
        study.candidates(runner, "calibration", "direct", ["t1"])


def test_no_calibration_before_the_probe_readout_chose_its_tasks(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner, chosen=False)
    with pytest.raises(SystemExit, match="no chosen calibration tasks"):
        study.candidates(runner, "calibration", "direct", ["t1"])


def test_no_calibration_once_the_chosen_list_was_edited(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    (runner.results / layout.CHOSEN).write_text(json.dumps({"tasks": [{"id": "t1", "rung": "T3"}]}))
    with pytest.raises(SystemExit, match="no chosen calibration tasks"):
        study.candidates(runner, "calibration", "direct", ["t1"])


def test_nothing_starts_after_a_stop(ledger):
    spend.record(ledger, "stop", reason="forbidden model in a run")
    with pytest.raises(SystemExit, match="stopped"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-1", env("smoke"))


def test_three_contaminated_tasks_stop_the_study(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    verdict = {"scan": {"verdict": {"verdict": "contaminated", "reason": "read the fix"}}}
    for k, task in enumerate(("t1", "t2", "r1"), 1):
        records = run_dir(runner, k=k, task=task, record=verdict)
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, records, task=task, arm="direct")
    with pytest.raises(SystemExit, match="stopped"):
        study.candidates(runner, "calibration", "direct", ["t2"])


def test_incidents_over_a_tenth_of_the_planned_runs_stop_the_study(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)  # 2 drawn tasks: 10 planned runs, so 2 incidents are over 10%
    for k in (1, 2):
        records = run_dir(runner, k=k, incident="provider: call 1: API Error: 429")
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, records, task="t1", arm="direct")
    with pytest.raises(SystemExit, match="stopped"):
        study.candidates(runner, "calibration", "direct", ["t2"])


def test_a_single_incident_of_ten_planned_runs_does_not_stop(runner):
    run_dir(runner, incident="provider: call 1: overloaded")
    assert rules.stop_reasons(runner) == []


@pytest.mark.parametrize("text, incident", [
    ("API Error: 429 rate_limit_error", True), ("Claude AI usage limit reached", True),
    ("Invalid API key · Please run /login", True), ("API Error: 529 overloaded_error", True),
    ("shim: call 2 refused by COMPARE_MAX_CALLS=1", True), ("AssertionError: expected 5, got 3", False), ("", False)])
def test_provider_errors_are_incidents_and_task_failures_are_not(tmp_path, text, incident):
    (tmp_path / "calls" / "1").mkdir(parents=True)
    (tmp_path / "calls" / "1" / "stderr.txt").write_text(text)
    assert (units.provider_incident(tmp_path) is not None) == incident


def test_a_refused_call_directory_is_not_a_physical_call(tmp_path):
    for n, prompt in ((1, True), (2, False)):
        (tmp_path / "calls" / str(n)).mkdir(parents=True)
        if prompt:
            (tmp_path / "calls" / str(n) / "prompt.txt").write_text("p")
    assert units.physical_calls(tmp_path) == 1


def session(home, directory, model, name="s1.jsonl"):
    slug = "".join(c if c.isalnum() else "-" for c in str(directory))
    path = Path(home) / ".claude" / "projects" / slug / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "assistant", "sessionId": "x", "message": {"model": model}}) + "\n")
    return path


def test_the_session_audit_accepts_one_session_per_call_in_the_trees_store(tmp_path):
    session(tmp_path / "home", tmp_path / "tree" / "cand-1", H)
    assert units.audit_sessions(tmp_path / "home", tmp_path / "tree", 1, H)[:2] == (None, None)


def test_a_session_outside_the_trees_store_fails_the_unit(tmp_path):
    session(tmp_path / "home", tmp_path / "tree" / "cand-1", H)
    session(tmp_path / "home", "/tmp", H)  # the real CLI started by absolute path from /tmp
    reason, policy, _ = units.audit_sessions(tmp_path / "home", tmp_path / "tree", 1, H)
    assert ("outside the unit tree" in reason, policy) == (True, None)


def test_more_sessions_than_recorded_calls_fail_the_unit(tmp_path):
    for name in ("s1.jsonl", "s2.jsonl"):
        session(tmp_path / "home", tmp_path / "tree" / "cand-1", H, name)
    assert "2 sessions for 1 recorded calls" in units.audit_sessions(tmp_path / "home", tmp_path / "tree", 1, H)[0]


def test_a_session_answered_by_another_model_anywhere_in_the_home_is_a_policy_hit(tmp_path):
    session(tmp_path / "home", "/elsewhere", "claude-fable-5-1")
    assert units.audit_sessions(tmp_path / "home", tmp_path / "tree", 1, H)[1] is not None


def test_a_disabled_resume_script_refuses_and_names_why(tmp_path):
    script = tmp_path / "resume.sh"
    script.write_text("echo resumed\n")
    units.disable_resume(script)
    done = subprocess.run(["bash", str(script), "run-1"], capture_output=True, text=True)
    assert (done.returncode, "never resumes" in done.stderr, "resumed" in done.stdout) == (64, True, False)


def test_a_guarded_host_command_sees_only_the_stubs_an_empty_home_and_no_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "secret")
    probe = ("import os, shutil, subprocess; print(sorted(os.listdir(os.environ['HOME'])), "
             "'secret' in os.environ.values(), shutil.which('claude').endswith('no_provider/claude')); "
             "subprocess.run(['claude', '-p', '--model', 'claude-fable-5-1'])")
    done, attempts = host.guarded([sys.executable, "-c", probe])
    assert (done.stdout.split(), [line.split(" ", 1)[1] for line in attempts]) == (
        ["[]", "False", "True"], ["claude -p --model claude-fable-5-1"])


def test_a_provider_attempt_in_the_hidden_tests_refuses_the_summary(tmp_path, monkeypatch):
    fake = tmp_path / "experiments" / "compare"
    fake.mkdir(parents=True)
    (tmp_path / "experiments" / "__init__.py").write_text("")
    (fake / "__init__.py").write_text("")
    (fake / "summarize.py").write_text("import subprocess\nsubprocess.run(['claude', '-p'])\n")
    monkeypatch.setattr(host, "ROOT", tmp_path)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    with pytest.raises(SystemExit, match="PROVIDER ATTEMPT"):
        host.summarize(tmp_path / "pool", tmp_path / "criterion.json")


@pytest.mark.parametrize("change", [{"model": "claude-fable-5-1"}, {"model": "claude-opus-5-5"},
                                    {"effort": "high"}, {"max_calls": 4}])
def test_arms_binding_another_model_effort_or_call_count_refuse(runner, change):
    path = runner.programs / "arms.json"
    arms = json.loads(path.read_text())
    arms["direct"] |= change
    path.write_text(json.dumps(arms))
    with pytest.raises(SystemExit):
        layout.load_arms(runner)


@pytest.mark.parametrize("change", [{"purpose": "calibration"}, {"calibration": {"rule": "control-means-v1"}},
                                    {"judges": [H]}, {"rubric": {**layout.RUBRIC, "workflow": "score.orc"}}])
def test_a_criterion_that_would_skip_hidden_tests_or_drop_a_judge_refuses(runner, change):
    runner.criterion.write_text(json.dumps({"judges": [H, S], "rubric": layout.RUBRIC} | change))
    with pytest.raises(SystemExit, match="judge-calibration criterion"):
        layout.load_criterion(runner)


def test_a_run_refuses_to_start_below_the_free_disk_floor(runner):
    full = layout.Study(*[getattr(runner, f) for f in ("runtime", "work", "pools", "results", "tasks_file",
                                                        "criterion", "state")], min_free=10**18)
    with pytest.raises(SystemExit, match="GB free"):
        layout.require_free(full, full.work)


def test_a_third_live_pool_refuses(runner):
    for task in ("t1", "t2"):
        (runner.pools / task / "first" / "clones").mkdir(parents=True)
    with pytest.raises(SystemExit, match="two pools still hold clones"):
        study.build_pools(runner, "calibration", "retest", ["t1"])


def test_a_retest_takes_only_the_tranches_first_tasks(runner):
    with pytest.raises(SystemExit, match="takes tasks among"):
        study.build_pools(runner, "smoke", "retest", ["r2"])


def test_the_command_line_refuses_an_unauthorized_launch_before_preparing_anything(runner, monkeypatch, tmp_path):
    monkeypatch.delenv(AUTH, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    args = ["--runtime", str(runner.runtime), "--work", str(runner.work), "--pools", str(runner.pools),
            "--results", str(runner.results), "--task-list", str(runner.tasks_file), "--criterion", str(runner.criterion)]
    with pytest.raises(SystemExit, match="provider spend refused"):
        study.main([*args, "candidates", "--tranche", "calibration", "--arm", "direct", "t1", "t2"])
    assert not runner.work.exists()


@pytest.mark.parametrize("step", ["pool", "judge"])
def test_the_redraw_tranche_never_pools_or_judges(runner, monkeypatch, step):  # review2 M4
    monkeypatch.setenv(AUTH, "redraw")
    ready(runner)
    pool_dir_of(runner, "t1")
    with pytest.raises(SystemExit, match="ladder probe only"):
        (study.build_pools if step == "pool" else study.judge)(runner, "redraw", "first", ["t1"])
    assert not [row for row in spend.rows(runner.ledger) if row["kind"] == "judge"]


def pool_dir_of(runner, task, scan=None):
    """A built pool's records as the judge reads them; `scan` is the identity scan's hits, None for no scan."""
    records = runner.pools / task / "first" / "records"
    (records / "judges").mkdir(parents=True)
    (records / "mapping.json").write_text(json.dumps({"batches": [[1]], "clones": {}, "judges": {}}))
    if scan is not None:
        (records / "identity-scan.json").write_text(json.dumps({"hits": scan}))
    return records


@pytest.mark.parametrize("scan", [None, ["direct.orc in clone-1"]])
def test_a_judge_refuses_a_pool_without_a_clean_identity_scan_before_any_launch(runner, monkeypatch, scan):  # M5
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    pool_dir_of(runner, "t1", scan)
    monkeypatch.setattr(study, "launch", lambda *a, **k: pytest.fail("a judge was launched"))
    with pytest.raises(SystemExit, match="identity scan"):
        study.judge(runner, "calibration", "first", ["t1"])
    assert not [row for row in spend.rows(runner.ledger) if row["kind"] == "judge"]


def test_a_pool_that_ended_as_an_incident_is_never_built_again(runner):
    (runner.results / "pools" / "t1-first").mkdir(parents=True)
    (runner.results / "pools" / "t1-first" / "incident.json").write_text("{}")
    with pytest.raises(SystemExit, match="a pool is built once"):
        study.build_pools(runner, "calibration", "first", ["t1"])
