"""The three-arm run's launch gate (three_arm.CapGate): reservation-aware launches under the quota guard, and the
stop once quota incidents use up the relaunches; stub launches against a real ledger and a fake clock (no provider
is called)."""

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from experiments.orc_structural_search import ledger, three_arm
from experiments.orc_structural_search.driver import Unit, launch_units
from experiments.orc_structural_search.quota import MAX_QUOTA_RETRIES, QuotaGuard
from tests.experiments.orc_structural_search_support import I3_CONFIG
from tests.experiments.test_orc_structural_search_three_arm import QUOTA, QUOTA_PLAIN, unparsed_quota_guard


def test_a_launch_waiting_at_the_cap_waits_out_a_quota_pause_before_it_relaunches(tmp_path):
    """A (in flight) holds the cap; B is refused and waits; A ends with a quota incident: B relaunches only after the
    guard's pause."""
    now, events = [datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)], []

    def sleep(seconds):
        events.append("pause")
        now[0] += timedelta(seconds=seconds)

    gate = three_arm.CapGate(QuotaGuard(clock=lambda: now[0], sleep=sleep, say=lambda line: None))
    reserved, finish = threading.Event(), threading.Event()

    def launch(name, row, hold=False):
        def go():
            events.append(name)
            slot = ledger.reserve(tmp_path, kind="evaluation", key=name, planned=8, cap=10)
            reserved.set()
            if hold:
                finish.wait(30)
            ledger.settle(tmp_path, slot, tmp_path / name)
            return row
        return go

    quota_row = {"kind": "evaluation", "evaluation_id": "a", "candidate_id": "c", "task_id": "t", "replicate": 1,
                 "outcome": "incident", "incidents": [f"quota: {QUOTA}"]}
    first = threading.Thread(target=gate.run, args=(launch("A", quota_row, hold=True),))
    first.start()
    reserved.wait(30)
    rows = []
    second = threading.Thread(target=lambda: rows.append(gate.run(launch("B", {"outcome": "completed"}))))
    second.start()
    deadline = time.monotonic() + 30
    while not (events.count("B") == 1 and gate.running == 1) and time.monotonic() < deadline:
        time.sleep(0.01)  # until B was refused at the cap while A is in flight
    finish.set()
    first.join(30)
    second.join(30)
    assert (events, rows) == (["A", "B", "pause", "B"], [{"outcome": "completed"}])


def test_an_evaluation_that_keeps_hitting_an_unparsed_quota_stops_every_further_launch(tmp_path):
    """Three units behind one gate, one at a time; every launch returns a quota incident with no parsed reset: the
    first unit's relaunches are used up, and no other unit launches."""
    launches = []

    def quota_incident():
        launches.append(len(launches) + 1)
        return {"kind": "evaluation", "evaluation_id": f"e{len(launches)}", "candidate_id": "c", "task_id": "t",
                "replicate": 1, "outcome": "incident", "incidents": [f"quota: {QUOTA_PLAIN}"],
                "attempt": len(launches)}

    guard = unparsed_quota_guard()
    gate = three_arm.CapGate(guard)
    units = [Unit(tmp_path, I3_CONFIG, {}, tmp_path / f"task-{n}", 1) for n in range(3)]
    with pytest.raises(three_arm.QuotaExhausted, match="rerun with --continue"):
        launch_units(units, concurrency=1, guard=guard, gate=lambda _evaluate: gate.run(quota_incident))
    assert (len(launches), bool(gate.exhausted)) == (1 + MAX_QUOTA_RETRIES, True)


def test_quota_incidents_of_launches_in_flight_together_stop_the_run_within_one_wave(tmp_path):
    """Twelve units behind one gate, four in flight; every launch returns a quota incident with no parsed reset, and
    the guard's pause outlasts the launches in flight (its sleep returns once all four ended): four launches in all,
    max(concurrency, 1 + MAX_QUOTA_RETRIES), then QuotaExhausted."""
    now, launches, lock = [datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)], [], threading.Lock()
    wave = threading.Barrier(4, timeout=10)  # the first four launches are in flight together

    def sleep(seconds):
        deadline = time.monotonic() + 10
        while gate.ended < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        now[0] += timedelta(seconds=seconds)

    def quota_incident():
        with lock:
            launches.append(len(launches) + 1)
            n = len(launches)
        if n <= 4:
            wave.wait()
        return {"kind": "evaluation", "evaluation_id": f"e{n}", "candidate_id": f"c{n}", "task_id": "t",
                "replicate": 1, "outcome": "incident", "incidents": [f"quota: {QUOTA_PLAIN}"], "attempt": 1}

    guard = QuotaGuard(retries=MAX_QUOTA_RETRIES, clock=lambda: now[0], sleep=sleep, say=lambda line: None)
    gate = three_arm.CapGate(guard)
    units = [Unit(tmp_path, I3_CONFIG, {}, tmp_path / f"task-{n}", 1) for n in range(12)]
    with pytest.raises(three_arm.QuotaExhausted, match="rerun with --continue"):
        launch_units(units, concurrency=4, guard=guard, gate=lambda _evaluate: gate.run(quota_incident))
    assert len(launches) == max(4, 1 + MAX_QUOTA_RETRIES)
