# Seed-set study kit

The kit of the [seed-set calibration plan](../../docs/plans/2026-11-11-seed-set-calibration-plan.md) (roadmap
Phase 5): calibrate about 20 small bug-fix tasks from this repository and a blind judge, then find two to four
simple workflows that do at least as well as one direct call, as seeds for a later search. The plan owns the task
set, the thresholds, the budget, the stop rules and the ledger. This page only routes. Its commands are for this
machine and are not copyable examples.

**Nothing is spent.** The smoke and the calibration tranches are the only authorized spend (`AGENTS.md`,
"Experiment rules"); the seed evaluation needs a new owner approval. Every call uses the owner's subscription.

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

## Owed before the first paid call

In the ledger's order (row of 2026-11-15, "The kit is on `main`"):

1. **The allowance** (owner decision, still open): the hours and shares of the owner's usage the study may take,
   and the meter-reading protocol. The first paid call waits for it; the freeze and the rehearsal do not. The
   other three decisions were answered on 2026-11-17 (plan ledger, rulings R9 and R10): the credential route
   stays as built (below); paid extra usage is off for the account; a slot cut by a usage limit runs again only
   inside its cap.
2. **The freeze on the merged commit:** the runtime worktree, the anchors' stability run on that code,
   `judge-calibration.json` and `judge-seeds.json`, the price table read again, `criterion.json` with its `spend`
   and `sha256` blocks, `study.py record-freeze`, and the hashes in the ledger.
3. **The 20-task rehearsal** on the frozen code at low load.
4. **The tranche's spend row** in the ledger.
5. **The smoke.**

## The credential route

Each unit's private home gets a copy of the subscription login file, removed when the unit ends normally, is
refused or raises (ruling R7 and its correction; the limits of that clean-up are in
[programs/README.md](programs/README.md), "Known limits"). The agent under test can read its unit's copy during
its call. The owner kept this route on 2026-11-17 (ruling R9 in the plan's ledger). The long-horizon kit's route,
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
  module directly in `experiments/seed_set/` and `experiments/compare/` when it was measured. An outcome also
  depends on that code (the pool's clone builder, the hidden-test scorer, the guard), so an entry measured under
  another scoring path, or with none, says nothing about stability under the current code.
- **Such an entry is refused:** `anchors.unstable`, `tiers verify` and the freeze check name its package
  "(other scoring path)" as lacking a stable anchor, and `tiers reject-unstable` skips it instead of rejecting on
  it, saying how many it skipped. A run without ids measures it again, as it does a package whose hash changed,
  and skips a package already recorded at its current hash and scoring path, which makes it resumable.
- **The freeze runs the anchors on the frozen code,** so that its record carries the frozen code's scoring path:

  ```
  python -m experiments.seed_set.anchors --work <dir>
  ```

Any edit to a module in either directory invalidates the record; a re-run takes about an hour.
