"""Reservation-aware concurrent baseline/child launches and quota pauses."""
import threading
from collections.abc import Callable, Mapping

from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.quota import QuotaGuard, quota_reason

CONTINUE = "rerun with --continue after the provider's reset"


class QuotaExhausted(RuntimeError):
    """A launch's quota relaunches are used up: the run stops before any further launch (see CONTINUE)."""


class CapGate:
    """Reservation-aware launches (criterion i3.planned_maximum) under the run's quota guard: `run` waits out a quota
    pause before every launch and relaunch, retries a launch refused at the call cap (ledger.reserve, before any
    workspace) once another launch of the gate has ended, and raises the refusal when no other launch is in flight
    and none ended since it started. A launch that returns a quota incident pauses the guard before the waiters
    wake, so none relaunches into the provider's limit. Once more than guard.retries launches of the gate, any job's,
    have ended in a quota incident since the last launch that did not (`streak`), no further launch starts: `run`
    raises QuotaExhausted (`exhausted`). Under a lasting limit at most max(concurrency, 1 + guard.retries) launches
    happen; a capacity blip that hits that many launches in flight at once also stops the run (for --continue)."""

    def __init__(self, guard: QuotaGuard) -> None:
        self.guard, self.running, self.ended, self.changed = guard, 0, 0, threading.Condition()
        self.streak, self.exhausted = 0, None  # quota incidents since the last launch that ended without one

    def run(self, launch: Callable[[], dict]) -> dict:
        while True:
            self.guard.wait()
            with self.changed:
                if self.exhausted:
                    raise QuotaExhausted(self.exhausted)
                self.running, seen = self.running + 1, self.ended
            try:
                row = launch()
            except ledger.CallCapExceeded as refusal:
                self.refused(refusal, seen)
                continue
            except BaseException:
                self.end(None)
                raise
            self.end(row)
            return row

    def refused(self, refusal: ledger.CallCapExceeded, seen: int) -> None:
        """Leave the gate; raise `refusal` when no launch is in flight and none ended since this one started (`seen`),
        else wait for one to end, unless one already has."""
        with self.changed:
            self.running -= 1
            if self.ended == seen and self.running == 0:
                self.changed.notify_all()  # waiters retry and find nothing in flight either
                raise refusal
            if self.ended == seen:
                self.changed.wait()

    def end(self, row: Mapping | None) -> None:
        """Leave the gate after a launch ended (`row`, None when it raised) and wake the waiters."""
        reason = quota_reason(row) if row is not None else None
        if reason:
            self.guard.pause(reason)
        with self.changed:
            if row is not None:
                self.streak = self.streak + 1 if reason else 0
            if reason and self.streak > self.guard.retries:
                self.exhausted = (f"{self.streak} evaluation launches in a row ended in a quota incident (the last "
                                  f"{row['evaluation_id']}: {reason}); {CONTINUE}")
            self.running, self.ended = self.running - 1, self.ended + 1
            self.changed.notify_all()
