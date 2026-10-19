"""Quota guard: provider quota messages make a launch an incident, pause new launches until the reset, relaunch the
job as a new attempt, and let a mode 1 run continue past them. Scripted providers print the Claude limit line and
exit 1 (no provider is called)."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.driver import LAUNCH_ENV, archive, evaluate_all, run_mode1
from experiments.orc_structural_search.evaluation import evaluate, evaluation_id, records_root
from experiments.orc_structural_search.quota import (
    QuotaGuard, next_attempts, quota_hit, quota_reason, resume_time, with_retries)
from experiments.orc_structural_search.records import read_records
from experiments.orc_structural_search.scoring import latest_evaluations, policy_stats, scored_outcome
from tests.experiments.compare_harness_support import skip_without_sandbox
from tests.experiments.orc_structural_search_support import MUTATOR, SEEDS, script, world  # noqa: F401 (fixture)
from tests.experiments.test_orc_structural_search_driver import ANSWERS, CONFIG

LIMIT = "You've hit your session limit · resets 5:30pm (America/Los_Angeles)"
LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 18, 14, 0, tzinfo=LA)
CHANGE = {"match": "Implement this change", "result": {"summary": "set VALUE", "account": "edited pkg"}}
QUOTA_CHANGE = {"match": "Implement this change", "print": LIMIT, "exit": 1}
MUTATOR_ASKS_CLAUDE = f"""#!{sys.executable} -I
import subprocess
from pathlib import Path
subprocess.run(["claude", "-p"], input=Path("EPISODE.md").read_text(), text=True, check=True)
"""


@pytest.fixture
def sandboxed():
    skip_without_sandbox()


def call_records(tmp_path, stdout="", stderr=""):
    call = tmp_path / "records" / "calls" / "1"
    call.mkdir(parents=True)
    (call / "stdout.txt").write_text(stdout)
    (call / "stderr.txt").write_text(stderr)
    return tmp_path / "records"


class FakeClock:
    """A clock that `sleep` advances, running `on_sleep` first (a test changes the providers' answers there)."""

    def __init__(self, now=NOW, on_sleep=lambda: None):
        self.now, self.on_sleep, self.slept, self.said = now, on_sleep, [], []

    def guard(self, retries=3):
        return QuotaGuard(retries=retries, clock=lambda: self.now, sleep=self.sleep, say=self.said.append)

    def sleep(self, seconds):
        self.on_sleep()
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


def test_the_claude_session_limit_line_in_call_stdout_is_a_quota_hit(tmp_path):
    assert quota_hit(call_records(tmp_path, stdout=LIMIT + "\n")) == LIMIT


def test_the_codex_model_at_capacity_line_in_call_stderr_is_a_quota_hit(tmp_path):
    line = "ERROR: Selected model is at capacity. Please try a different model."
    assert quota_hit(call_records(tmp_path, stderr=line + "\n")) == line


def test_a_quota_phrase_quoted_mid_line_is_not_a_quota_hit(tmp_path):
    records = call_records(tmp_path, stderr="the docs say the run stops once a usage limit reached message appears\n")
    assert quota_hit(records) is None


def test_a_failed_row_from_before_the_guard_is_a_quota_incident_from_its_records(tmp_path):
    row = {"kind": "evaluation", "outcome": "failed", "incidents": [],
           "records_dir": str(call_records(tmp_path, stdout=LIMIT + "\n"))}
    assert (quota_reason(row), scored_outcome(row)) == (LIMIT, "quota_incident")


def test_a_genuine_failure_is_not_a_quota_incident(tmp_path):
    row = {"kind": "evaluation", "outcome": "failed", "incidents": [],
           "records_dir": str(call_records(tmp_path, stderr="Traceback: boom\n"))}
    assert scored_outcome(row) == "failed"


def test_the_pause_lasts_until_the_named_reset_plus_five_minutes():
    assert resume_time(LIMIT, NOW) == datetime(2026, 10, 18, 17, 35, tzinfo=LA)


def test_a_reset_time_more_than_three_hours_past_is_tomorrows():
    assert resume_time(LIMIT, NOW.replace(hour=21)) == datetime(2026, 10, 19, 17, 35, tzinfo=LA)


def test_a_reset_time_at_most_three_hours_past_resumes_in_five_minutes():
    assert resume_time(LIMIT, NOW.replace(hour=18)) == NOW.replace(hour=18, minute=5)


def test_a_retry_follows_the_attempt_the_launch_actually_ran_as():
    seen = []

    def launch(attempt):  # attempt `attempt` was skipped (a killed launch's records): it ran as the next one
        seen.append(attempt)
        return {"kind": "evaluation", "outcome": "incident", "attempt": attempt + 1, "incidents": [f"quota: {LIMIT}"]}
    with_retries(launch, FakeClock().guard(retries=1), 2)
    assert seen == [2, 4]


def test_an_unparsed_quota_message_pauses_thirty_minutes():
    assert resume_time("Rate limit reached for requests", NOW) == NOW + timedelta(minutes=30)


def test_a_second_quota_hit_during_a_pause_joins_it_and_prints_one_line():
    clock = FakeClock()
    guard = clock.guard()
    guard.pause(LIMIT)
    clock.now += timedelta(minutes=10)
    guard.pause(LIMIT)
    guard.wait()
    assert (len(clock.said), "2026-10-18T17:35:00-07:00" in clock.said[0], clock.now) == (
        1, True, datetime(2026, 10, 18, 17, 35, tzinfo=LA))


def test_a_retry_attempt_has_another_evaluation_id_and_a_first_attempt_keeps_its_id():
    ids = [evaluation_id("sha256:c", "task-1", "v1", "sha256:e", 1, attempt) for attempt in (1, 2)]
    assert (ids[0] == evaluation_id("sha256:c", "task-1", "v1", "sha256:e", 1), ids[0] != ids[1]) == (True, True)


def test_a_retry_supersedes_its_jobs_quota_incident_in_scoring(tmp_path):
    job = {"kind": "evaluation", "candidate_id": "sha256:c", "task_id": "task-1", "replicate": 1}
    quota = job | {"evaluation_id": "a", "outcome": "failed", "records_dir": str(call_records(tmp_path, LIMIT))}
    retry = job | {"evaluation_id": "b", "outcome": "completed", "attempt": 2}
    assert latest_evaluations([quota, retry]) == [retry]


def test_policy_stats_exclude_quota_incidents_and_count_them():
    rows = [{"outcome": "quota_incident", "value": None, "hidden": None, "calls": 1, "wall_clock_sec": 1.0},
            {"outcome": "completed", "value": 6.0, "hidden": None, "calls": 2, "wall_clock_sec": 2.0}]
    stats = policy_stats(rows)
    assert (stats["mean"], stats["failed"], stats["incidents"], stats["quota_incidents"]) == (6.0, 0, 0, 1)


def test_a_continued_run_relaunches_only_quota_jobs_as_their_next_attempt(tmp_path):
    def row(cid, outcome, **extra):
        return {"kind": "evaluation", "candidate_id": cid, "task_id": "t", "replicate": 1, "outcome": outcome,
                "incidents": [], **extra}
    prior = [row("done", "completed"), row("broken", "failed"), row("quota", "incident", incidents=[f"quota: {LIMIT}"]),
             row("again", "incident", attempt=2, incidents=[f"quota: {LIMIT}"]), row("killed", "incident")]
    keys = [(cid, "t", 1, None, None) for cid in ("done", "broken", "quota", "again", "killed", "new")]
    assert next_attempts(keys, prior) == [None, None, 2, 3, None, 1]


def scripted_env(world):
    return {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}


EVAL_CONFIG = ExperimentConfig(
    mutable_files=("direct.orc",), mutable_definitions=("run",), condition="topology-only", interface="I1",
    entry_workflow="direct::run", source_root=".", providers_file="providers.json",
    command_boundaries_file="commands.json", episode_wall_clock_sec=600, criterion_sha256=None)


def test_a_provider_printing_the_session_limit_makes_the_evaluation_a_quota_incident(sandboxed, world):
    script(world, [QUOTA_CHANGE])
    record = evaluate(world.candidate, EVAL_CONFIG, task_package=world.task, work_root=world.evidence, replicate=1,
                      runtime=world.runtime, env=scripted_env(world), timeout_sec=600)
    assert (record.outcome, record.incidents[-1]) == ("incident", f"quota: {LIMIT}")


def test_a_quota_incident_is_relaunched_after_the_pause_as_a_new_attempt(sandboxed, world):
    script(world, [QUOTA_CHANGE])
    clock = FakeClock(on_sleep=lambda: script(world, [CHANGE]))
    evidence = world.tmp / "evidence"
    cid, root = archive(world.candidate, evidence, world.runtime)
    (row,) = evaluate_all([(root, EVAL_CONFIG, {"candidate_id": cid})], tasks=[world.task],
                          replicates=1, concurrency=2, guard=clock.guard(), work_root=world.outside / "work",
                          evidence_root=evidence, runtime=world.runtime, env=scripted_env(world), timeout_sec=600,
                          solutions={world.task.name: world.solution}, holdouts=(), call_cap=160)
    logged = read_records(evidence / "log.jsonl")
    assert ([(r["attempt"], r["outcome"]) for r in logged], logged[0]["evaluation_id"] != row["evaluation_id"],
            [r["evaluation_id"] for r in latest_evaluations(logged)] == [row["evaluation_id"]], clock.slept,
            len(clock.said)) == (
        [(1, "incident"), (2, "completed")], True, True, [(17 * 60 + 35 - 14 * 60) * 60.0], 1)


def mode1_run(world, *, agent: str, continue_run: bool):
    (world.tmp / "config.json").write_text(json.dumps(CONFIG))
    mutator = world.outside / "mutator.py"
    mutator.write_text(agent)
    return run_mode1(world.tmp / "config.json", seeds=[SEEDS / f"{name}.orc" for name in
                                                       ("direct", "plan_then_implement", "implement_review_revise")],
                     tasks=[world.task], work_root=world.outside / "work", evidence_root=world.tmp / "evidence",
                     episodes=1, agent_cmd=[sys.executable, "-I", str(mutator)], replicates=1, runtime=world.runtime,
                     env=scripted_env(world), timeout_sec=600, solutions={world.task.name: world.solution},
                     call_cap=160, concurrency=2, continue_run=continue_run, guard=FakeClock().guard(retries=0))


def as_old_format(log):
    """Rewrite the log's quota rows as the driver wrote them before the quota guard (a failed evaluation, an
    episode incident without an incidents entry)."""
    rows = read_records(log)
    for row in rows:
        if (row.get("incidents") or [""])[-1].startswith("quota: "):
            row.update(incidents=[]) if row["kind"] == "episode" else row.update(outcome="failed", incidents=[])
            row.pop("attempt", None)
    log.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    return log.read_text()


def test_continue_keeps_completed_and_genuine_failures_and_relaunches_only_quota_jobs(sandboxed, world):
    script(world, [{"match": "# Episode", "print": LIMIT, "exit": 1},
                   {"match": "Plan this task", "print": LIMIT, "exit": 1}, *ANSWERS])
    mode1_run(world, agent=MUTATOR_ASKS_CLAUDE, continue_run=False)
    log = world.tmp / "evidence" / "log.jsonl"
    before = as_old_format(log)
    script(world, ANSWERS)
    readout = mode1_run(world, agent=MUTATOR, continue_run=True)
    added = read_records(log)[len(before.splitlines()):]
    assert (log.read_text().startswith(before),
            [(r.get("seed") or r["mode"], r.get("attempt"), r["outcome"]) for r in added if r["kind"] == "evaluation"],
            [(r["episode_index"], r["outcome"]) for r in added if r["kind"] == "episode"],
            readout["catalog"]["plan_then_implement"]["outcomes"], readout["episodes"]) == (
        True, [("plan_then_implement", 2, "completed"), ("unguided", 1, "completed")], [(1, "accepted")],
        ["quota_incident", "completed"], {"quota_incident": 1, "accepted": 1})


def test_a_continue_after_an_interrupted_continue_skips_and_settles_the_killed_launches(sandboxed, world):
    script(world, [{"match": "# Episode", "print": LIMIT, "exit": 1},
                   {"match": "Plan this task", "print": LIMIT, "exit": 1}, *ANSWERS])
    mode1_run(world, agent=MUTATOR_ASKS_CLAUDE, continue_run=False)
    evidence, work = world.tmp / "evidence", (world.outside / "work").resolve()
    log = evidence / "log.jsonl"
    (job,) = [r for r in read_records(log) if r.get("seed") == "plan_then_implement"]
    killed = [records_root(Path(job["candidate_root"]), task_package=world.task, work_root=work, replicate=1,
                           runtime=world.runtime, env={**scripted_env(world), **LAUNCH_ENV}, attempt=2) / "run-1",
              evidence / "episodes" / "sha256:killed"]  # attempt 2 and episode 1 died in flight: no log rows
    (work / "episodes" / "episode-1").mkdir(parents=True)
    for records in killed:
        (records / "calls" / "1").mkdir(parents=True)
    ledger = json.loads((evidence / "calls.json").read_text()) + [
        {"kind": "evaluation", "key": f"{job['candidate_id']} {world.task.name} replicate 1 attempt 2", "planned": 9,
         "calls": None}, {"kind": "episode", "key": "sha256:killed", "planned": 1, "calls": None}]
    (evidence / "calls.json").write_text(json.dumps(ledger))
    before = len(read_records(log))
    script(world, ANSWERS)
    mode1_run(world, agent=MUTATOR, continue_run=True)
    added = read_records(log)[before:]
    settled = json.loads((evidence / "calls.json").read_text())[len(ledger) - 2:len(ledger)]
    assert ([(r.get("seed") or r["mode"], r.get("attempt"), r["outcome"]) for r in added if r["kind"] == "evaluation"],
            [(r["episode_index"], r["outcome"]) for r in added if r["kind"] == "episode"],
            [entry["calls"] for entry in settled]) == (
        [("plan_then_implement", 3, "completed")], [(2, "rejected")], [1, 1])  # the mutator's episode 2 is refused
