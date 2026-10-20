"""Provider quota incidents: detection in shim call records, the reset time, the pause before relaunching, and the
rows a continued mode 1 run keeps or relaunches.

In the live Phase 1 run (2026-10-18) 16 of 20 evaluations and all 6 unguided episodes ended at the Claude
subscription session limit: the CLI printed `You've hit your session limit · resets 5:30pm (America/Los_Angeles)` on
stdout and exited 1, the runtime wrote a failed terminal (provider_exit_nonzero) and the driver logged `failed`
(evaluations) or `incident` (episodes). Such a launch is an infrastructure incident, not an agent failure.

Detection (quota_hit) reads <records>/calls/<n>/stdout.txt and stderr.txt. A quota line is a line of at most
MAX_LINE characters that starts (after leading punctuation) with one of, case-insensitively:
  you've hit your <word> limit    Claude's session or weekly limit; Codex's usage limit
  [claude ai ]usage limit reached Claude's older wording; Codex
  (Codex) rate limit reached
or that starts, with no leading punctuation, with Codex's transient capacity refusal (seen 2026-10-18 on the
reviewer; Codex echoes its transcript, quotes and patch lines included, to stderr):
  [error: ]selected model is at capacity
The match is anchored at the line start so a transcript or a document quoting these words mid-line does not match.
QUOTA_LINE matches plain-text lines only, so a quota message inside a stream-json line (agent-session children,
whose session commands print `--output-format stream-json`) is not detected (unverified: no provider call has
shown how the CLI prints the limit there).

A quota launch is relaunched as a new attempt after a pause (QuotaGuard): until the reset time the message names
(`resets H[:MM]am|pm (Zone)`, that wall-clock time in that zone today, plus RESET_MARGIN; a time at most
RECENT_RESET past resumes at now plus RESET_MARGIN, an earlier one tomorrow) or, when none parses, UNPARSED_PAUSE; at most `retries` (MAX_QUOTA_RETRIES) relaunches per job and driver invocation.
A continued mode 1 run (prior_rows, next_attempts) relaunches each job whose latest log row is a quota incident as
its next attempt and keeps every other job. A launch killed in flight (the driver died) left no log row: a
continue skips each attempt number and episode index whose records already exist (an attempt only when no log row
names its id; a logged one is refused) and settles the killed launch's ledger reservation from its shim records
(driver.py, mode1.py, ledger.settle_killed).
"""

import functools
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from experiments.orc_structural_search.records import read_records

QUOTA_LINE = re.compile(r"^(?:\W*(?:you['’]ve hit your \w+ limit|(?:claude ai )?usage limit reached|rate limit reached)"
                        r"|(?:error:\s*)?selected model is at capacity)", re.IGNORECASE)
MAX_LINE = 300
RESET = re.compile(r"resets (\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*\(([^)]+)\)", re.IGNORECASE)
RESET_MARGIN = timedelta(minutes=5)
RECENT_RESET = timedelta(hours=3)
UNPARSED_PAUSE = timedelta(minutes=30)
MAX_QUOTA_RETRIES = 3
PREFIX = "quota: "  # the incidents entry of a quota launch: "quota: <first matching line>"


def quota_hit(records_dir: Path | str, after: int = 0) -> str | None:
    """The first quota line in the stdout or stderr of the shim calls under `records_dir` numbered above `after`
    (a resumed launch reads only its own calls), or None."""
    calls = [p for p in (Path(records_dir) / "calls").glob("*") if p.name.isdigit() and int(p.name) > after]
    for call in sorted(calls, key=lambda p: int(p.name)):
        for path in (call / "stdout.txt", call / "stderr.txt"):
            lines = path.read_text(errors="replace").splitlines() if path.is_file() else ()
            found = next((s for s in map(str.strip, lines) if len(s) <= MAX_LINE and QUOTA_LINE.match(s)), None)
            if found:
                return found
    return None


def quota_reason(row: Mapping, evidence_root: Path | None = None) -> str | None:
    """The quota line of a failed or incident evaluation or episode log row: its latest incidents entry (this
    driver's rows), else a scan of its records (rows from before the quota guard: an evaluation's `records_dir`, an
    episode's <evidence_root>/episodes/<episode_id>, only when `evidence_root` is given); None otherwise."""
    if row.get("outcome") not in ("failed", "incident"):
        return None
    incidents = row.get("incidents") or ()
    if incidents and incidents[-1].startswith(PREFIX):
        return incidents[-1].removeprefix(PREFIX)
    if row.get("kind") == "evaluation" and row.get("records_dir"):
        return quota_hit(row["records_dir"])
    if row.get("kind") == "episode" and evidence_root is not None:
        return quota_hit(Path(evidence_root) / "episodes" / row["episode_id"])
    return None


def resume_time(line: str, now: datetime) -> datetime:
    """When to relaunch after the quota message `line` seen at `now` (timezone-aware)."""
    found = RESET.search(line)
    if not found:
        return now + UNPARSED_PAUSE
    hour, minute, half, zone = found.groups()
    try:
        local = now.astimezone(ZoneInfo(zone.strip()))
    except (ZoneInfoNotFoundError, ValueError):  # the zone name comes from the CLI's text
        return now + UNPARSED_PAUSE
    reset = local.replace(hour=int(hour) % 12 + (12 if half.lower() == "pm" else 0), minute=int(minute or 0),
                          second=0, microsecond=0)
    if reset <= local:  # a reset just past (the clocks disagree, or the CLI lags): retry soon; else tomorrow's
        return now + RESET_MARGIN if local - reset <= RECENT_RESET else reset + timedelta(days=1) + RESET_MARGIN
    return reset + RESET_MARGIN


class QuotaGuard:
    """The pause state one driver invocation shares across its launches (threads): `wait` blocks while a pause
    lasts; `pause` starts one (printing one line with the resume time) unless one already lasts, which the caller
    joins. `clock` returns an aware datetime; `sleep` takes seconds."""

    def __init__(self, *, retries: int = MAX_QUOTA_RETRIES, clock: Callable[[], datetime] = lambda: datetime.now(
            timezone.utc), sleep: Callable[[float], None] = time.sleep,
                 say: Callable[[str], None] = functools.partial(print, flush=True)):
        self.retries, self.clock, self.sleep, self.say = retries, clock, sleep, say
        self.until: datetime | None = None
        self._lock = threading.Lock()

    def pause(self, reason: str) -> None:
        now = self.clock()
        with self._lock:
            if self.until is not None and self.until > now:
                return
            self.until = resume_time(reason, now)
        self.say(f"quota: pausing new launches until {self.until.isoformat()} ({reason})")

    def wait(self) -> None:
        while True:
            with self._lock:
                until = self.until
            remaining = 0 if until is None else (until - self.clock()).total_seconds()
            if remaining <= 0:
                return
            self.sleep(remaining)


def with_retries(launch: Callable[[int], dict], guard: QuotaGuard, first_attempt: int = 1) -> dict:
    """Launch attempt `first_attempt` after any pause; after a quota incident, pause and relaunch as the next
    attempt (after the attempt the row names, when it names one), at most guard.retries times; the last row."""
    attempt = first_attempt
    for retry in range(guard.retries + 1):
        guard.wait()
        row = launch(attempt)
        reason = quota_reason(row)
        if reason is None or retry == guard.retries:
            return row
        guard.pause(reason)
        attempt = row.get("attempt", attempt) + 1  # a launch skipping a killed attempt ran as a later one
    raise AssertionError("unreachable")


def job_key(row: Mapping) -> tuple:
    """An evaluation's job: candidate, task and replicate, and mode 2's split and generation (a retry attempt
    carries them all but has another evaluation id)."""
    return row["candidate_id"], row["task_id"], row["replicate"], row.get("split"), row.get("generation")


def next_attempts(keys: Iterable[tuple], prior: Iterable[Mapping]) -> list[int | None]:
    """Per job key, in order: the attempt to launch in a continued run (1 when the log has no row of it, the
    latest row's attempt + 1 when that row is a quota incident) or None (completed, a genuine failure or another
    incident: kept)."""
    latest = {job_key(row): row for row in prior if row["kind"] == "evaluation"}
    rows = [latest.get(key) for key in keys]
    return [1 if row is None else (row.get("attempt", 1) + 1 if quota_reason(row) else None) for row in rows]


def prior_rows(work_root: Path, evidence_root: Path, continue_run: bool) -> list[dict]:
    """The log rows a continued run builds on ([] for a fresh one); refuses an existing log without `continue_run`,
    `continue_run` without a log, and a work root other than the run's (its evaluations' records lie there)."""
    log = evidence_root / "log.jsonl"
    if not continue_run:
        if log.exists():
            raise FileExistsError(f"{log} exists: give every mode 1 run a fresh evidence root, or pass --continue to "
                                  "continue that run (the driver never resumes an incident)")
        return []
    if not log.exists():
        raise FileNotFoundError(f"--continue: {log} does not exist, so there is no run to continue")
    rows = read_records(log)
    foreign = sorted({row["records_dir"] for row in rows if row["kind"] == "evaluation"
                      and not Path(row["records_dir"]).is_relative_to(work_root)})
    if foreign:
        raise ValueError(f"--continue needs the run's own work root: {foreign[0]} is not under {work_root}")
    return rows


def campaign_guard(state, save, lock, *, clock=lambda: datetime.now(timezone.utc), sleep=time.sleep):
    """Use the existing quota guard while checkpointing actual pause intervals, including interrupted waits."""
    intervals = state.setdefault('quota_intervals', [])
    now, until = clock().timestamp(), state.get('quota_until')
    for interval in intervals:
        if interval[1] is None:
            interval[1] = min(now, until) if until is not None else now
    def paused_sleep(seconds):
        with lock:
            position = len(intervals)
            intervals.append([clock().timestamp(), None])
            state['quota_until'] = guard.until.timestamp()
            save()
        try:
            sleep(seconds)
        finally:
            with lock:
                intervals[position][1] = clock().timestamp()
                save()
    guard = QuotaGuard(clock=clock, sleep=paused_sleep)
    if until is not None:
        guard.until = datetime.fromtimestamp(until, timezone.utc)
    return guard


def campaign_elapsed(state, now):
    """Controller wall time minus the union of actual quota waits; unit duration accounting stays separate."""
    intervals = sorted((start, min(now, end if end is not None else state.get('quota_until', now)))
                       for start, end in state.get('quota_intervals', ()))
    paused, last = 0, float('-inf')
    for start, end in intervals:
        paused += max(0, end - max(start, last))
        last = max(last, end)
    return max(0, now - state['started_at'] - paused)
