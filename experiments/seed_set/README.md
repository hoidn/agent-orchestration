# Seed-set study kit

The kit of the [seed-set calibration plan](../../docs/plans/2026-11-11-seed-set-calibration-plan.md) (roadmap
Phase 5): calibrate about 20 small bug-fix tasks from this repository and a blind judge, then find two to four
simple workflows that do at least as well as one direct call, as seeds for a later search. The plan owns the task
set, the thresholds, the budget, the stop rules and the ledger. This page only routes. Its commands are for this
machine and are not copyable examples.

**Spend so far: 9 calls, priced USD 1.0225** (7 `claude-haiku-5-5`, 2 `claude-sonnet-5-5`): the first smoke
stopped after one call on an isolation incident, and the second ran its 8 calls and failed its check on scanner
false positives (plan ledger, rows of 2026-11-18 and 2026-11-23). No smoke has passed and no calibration call is
made. The smoke and the calibration tranches, and a smoke repeated on the owner's word after an apparatus failure,
are the only authorized spend (`AGENTS.md`, "Experiment rules"); the seed evaluation needs a new owner approval. Every call uses the owner's subscription.

## Where to read

| Need | Read |
| --- | --- |
| The rules, the budget and what has been decided | The plan and its ledger |
| The runner's commands and the order they run in | The docstring of `study.py`; every command runs from the frozen runtime |
| The four programs, what the runner can and cannot see, the known limits, and how a usage limit or paid extra usage pauses the study | [programs/README.md](programs/README.md) |
| The freeze, the order of starts and the stops | The docstring of `rules.py` |
| The caps, the priced ceiling and the pause events | The docstring of `spend.py` |
| The task packages and the difficulty ladder | `build_tasks.py`, `tiers.py`, `tasks.jsonl`, `tasks/` |
| The anchors' stability record | `anchors.py`, `anchor_stability.json`, and the section below |

## Owed before the third smoke

Done: the allowance (ruling R13, and the owner's 24-hour allowance of 2026-11-23), the 20-task rehearsal (ruling
R12), the isolation of Claude sessions, the scanner fixes and the verdict guards (plan ledger, rows of 2026-11-23).
In the ledger's order:

1. **The freeze recorded again on the merged commit:** the runtime worktree, the anchors' stability run on that
   code, `judge-calibration.json`, the price table read again, `criterion.json` with its `spend` and `sha256`
   blocks and the CLI pin (`spend.cli`), `study.py record-freeze`, and the hashes in the ledger. `judge-seeds.json`
   is not part of the freeze: it names the judge the calibration selects (plan Step 1f). A CLI self-update before
   the first start means recording the freeze again.
2. **The tranche's spend row** in the ledger, with the meter reading ruling R13 asks for.
3. **The smoke.**

## Running a tranche again after a stop or a failed smoke

A `stop` in the spend ledger is final and a failed `smoke` row stays: no command lifts either, and the caps count
the calls already made. A tranche the owner approves again (ruling R14) starts from a new freeze with a fresh
ledger: the old ledger moves beside it under a dated name, read-only, with its SHA-256 in the plan's ledger, and
the old work root (`~/seedset-work`) and pools root (`~/seedset-pools`) move aside the same way. The plan's
ledger, not the guard, then carries the earlier spend.

## Scan hits need a verdict before the pool

Every run and every judge is scanned for contamination when it settles. A run or judge with hits and no verdict
stops `pool`, `summarize` and `smoke-check`: each refuses with a non-zero exit, writes nothing, and prints the
command for each unit. Read the hits (`scan` in the run's `record.json`, or the judge's `scan.json`), record
`cleared` or `contaminated` with a reason, then run the refused step again:

```
python experiments/compare/prepare.py scan --run <records>/<arm>/run-<n> --verdict cleared --reason "<why>"
python experiments/compare/prepare.py scan --pool <pools>/<task>/<kind> --judge <model> --verdict cleared --reason "<why>"
```

A cleared hit passes the smoke's scan check (ruling R15); a contaminated run is left out of its pool. What the
scan counts, and what it deliberately does not, is in the harness's [README](../compare/README.md) ("Scan, then
adjudicate"). An operator script must stop at the first non-zero exit and must not go on to the next step.

## The credential route

Each unit's private home gets a copy of the subscription login file, removed when the unit ends normally, is
refused or raises (ruling R7 and its correction; the limits of that clean-up are in
[programs/README.md](programs/README.md), "Known limits"). The agent under test can read its unit's copy during
its call. The owner kept this route on 2026-11-17 (ruling R9 in the plan's ledger).

A copy goes stale when the owner's side refreshes the login, so no unit may live across the access token's expiry
(ruling R16). Before a candidate run, a probe run or a judge is prepared or reserved, the kit reads the expiry time,
and nothing else, from the login file the unit would copy (`units.login_expiry`: `claudeAiOauth.expiresAt`) and
refuses the start unless the token outlives the unit's reserved calls times its provider timeout (1,200 s a
candidate call, 3,600 s a judge batch) plus 10 minutes (`units.EXPIRY_MARGIN_SEC`). A file without a numeric expiry
refuses too. After a refusal nothing is reserved; start again once the owner's own session has refreshed the
login. `study.py login-expiry` prints `expires <ISO time>, in <N> minutes` without opening anything else. A
refresh before the expiry, such as a new login by the owner, still ends the units in flight as incidents.

The long-horizon kit's route,
where one host process holds the token and no copy enters a unit
([its README](../long_horizon_tasks/README.md)), would be a kit change with its own tests, review and rehearsal.

## Usage limits and paid extra usage

A usage limit cuts its unit and closes every start. A call whose stream shows paid extra usage closes every start
too; if that call ended normally its result is kept, and if it did not its unit is cut. A pause by the vendor's
recorded limit answer or by paid extra usage is reopened only by `study.py resume-after-limit`, with the reset and
the owner's meter reading. `not-a-limit` refuses both; it serves a pause flagged "unrecognised limit shape" whose
raw result shows no limit.
The plan ("Changes since review 2", usage limits) and [programs/README.md](programs/README.md) hold the detail.

## The anchors' record and what it does not show

`anchors.py` checks, with no model call, that each task's reference fix passes its hidden tests and its untouched
base fails some, three times with identical outcomes, under the study's own scoring path. It writes
`anchor_stability.json`, and the freeze refuses a package without a stable entry.

- **An entry holds for its package hash and its scoring path.** Each entry carries `scoring_path`, a hash of every
  module directly in `experiments/seed_set/` and `experiments/compare/`, the Python version and the installed
  pytest's version when it was measured. An outcome also depends on that code (the pool's clone builder, the
  hidden-test scorer, the guard), so an entry measured under another scoring path, or with none, says nothing about
  stability under the current code. A Python or pytest update makes every entry "other scoring path". The freeze
  and each start compute the scoring path from the runtime's files.
- **What the scoring path does not bind:** the environment variables `host.guarded` passes through (for example
  `PYTEST_ADDOPTS`, `PYTHONHASHSEED`, `LC_ALL`, `TZ`), the git binary and its configuration, the other
  site-packages the hidden tests import, and the no-provider stubs in `experiments/thread_m/no_provider`. A change
  to any of them leaves the record in force without a new measurement.
- **Such an entry is refused:** `anchors.unstable`, `tiers verify` and the freeze check name its package
  "(other scoring path)" as lacking a stable anchor, and `tiers reject-unstable` skips it instead of rejecting on
  it, saying how many it skipped. A run without ids measures it again, as it does a package whose hash changed,
  and skips a package already recorded at its current hash and scoring path, which makes it resumable.
- **The freeze runs the anchors on the frozen code,** so that its record carries the frozen code's scoring path:

  ```
  python -m experiments.seed_set.anchors --work <dir>
  ```

Any edit to a module in either directory invalidates the record; a re-run takes about an hour.
