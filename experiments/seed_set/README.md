# Seed-set study kit

The kit of the [seed-set calibration plan](../../docs/plans/2026-11-11-seed-set-calibration-plan.md) (roadmap
Phase 5): calibrate about 20 small bug-fix tasks from this repository and a blind judge, then find two to four
simple workflows that do at least as well as one direct call, as seeds for a later search. The plan owns the task
set, the thresholds, the budget, the stop rules and the ledger. This page only routes. Its commands are for this
machine and are not copyable examples.

**Spend before the calibration: 26 calls, priced USD 3.66 settled** (three smokes and the ladder probe). The
calibration tranche started on 2026-11-25; the plan's ledger has its spend row and every stage's result. The smoke and the calibration tranches, and a smoke repeated on the owner's word after an apparatus failure,
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
| The seed evaluation's report (anchor and control checks per batch, arm figures, the selection rule, `seeds.json`); not yet wired to a command | The docstring of `seeds.py`, and the [seed evaluation apparatus plan](../../docs/plans/2026-11-25-seed-evaluation-apparatus-plan.md) |

## Before a tranche's first start

Each tranche (the smoke, the ladder probe, the calibration) starts only after these, in the ledger's order. The
same steps repeat after any change to the kit's code, with `record-freeze --reason` once a start exists:

1. **The freeze recorded again on the merged commit:** the runtime worktree, the anchors' stability run on that
   code, `judge-calibration.json`, the price table read again, `criterion.json` with its `spend` and `sha256`
   blocks and the CLI pins (`spend.cli`: one path and version per CLI, `{"claude": …, "codex": …}`; a single pin
   is the Claude CLI's), `study.py record-freeze`, and the hashes in the ledger. `judge-seeds.json`
   is not part of the freeze: it names the judge the calibration selects (plan Step 1f). A CLI self-update before
   the first start means recording the freeze again.
2. **The tranche's spend row** in the ledger, with the meter reading ruling R13 asks for.
3. **The tranche**, through `study.py` with `SEED_SET_AUTHORIZED_TRANCHE` set to its name.

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
refuses the start unless the token outlives the unit's wall-clock limit plus 15 minutes
(`units.EXPIRY_MARGIN_SEC`: the preparation before the launch and the CLI's refresh ahead of the expiry). The limit
is `study.unit_sec`, the same value at which the launch guard kills the unit's whole tree, checks between calls
included: 1,200 s a candidate call or 3,600 s a judge batch, plus 600 s. A file without a numeric expiry refuses
too. After a refusal nothing is reserved; start again once the owner's own session has refreshed the
login. `study.py login-expiry` prints `expires <ISO time>, in <N> minutes` without opening anything else. A
refresh before the expiry, such as a new login by the owner, still ends the units in flight as incidents.

A Codex unit's guard (`units.require_login(..., provider="codex")`, ruling L-R3 of the
[Luna plan](../../docs/plans/2026-11-23-gpt-6-luna-third-tier-plan.md)) reads from the Codex login file
(`$CODEX_HOME/auth.json`, default `~/.codex/auth.json`) only whether `OPENAI_API_KEY` is set, whether it is a
ChatGPT login (`auth_mode` exactly `chatgpt`, with `tokens.access_token`), and the access token's JWT `exp` claim,
decoded and not verified. It refuses an API key, a login that is not ChatGPT's, a token whose expiry cannot be read,
and one that does not outlive the unit by the same bound. `study.py login-expiry --provider codex` prints that
expiry. A unit takes the guard of its arm's CLI (`spend.CLI`: `gpt-6-luna` runs on Codex, the two Claude models on
Claude), and its copy of the Codex login carries an empty refresh token (`sandbox.codex_login`). `spend.CAPS`
refuses Luna in the smoke, the calibration and the redraw; only the Luna smoke (below) holds Luna calls.

The long-horizon kit's route,
where one host process holds the token and no copy enters a unit
([its README](../long_horizon_tasks/README.md)), would be a kit change with its own tests, review and rehearsal.

## The Luna smoke

The tranche `luna_smoke` (ruling L-R8 of the [Luna plan](../../docs/plans/2026-11-23-gpt-6-luna-third-tier-plan.md))
runs on the smoke task: `direct_luna` and `retry_until_check_luna` once each, then one pool of those two runs and
both anchors, scored by one `claude-haiku-5-5` judge call. Its caps are in `spend.CAPS` (4 Luna candidate calls, 1
Haiku judge call). Its priced ceiling (`ceiling_usd.luna_smoke`) and Luna's per-call worst case and largest call
(`per_call_usd` and `largest_call_usd` for `gpt-6-luna`) are criterion terms set at the freeze, with the Codex pin
in `spend.cli`. A criterion without the ceiling still freezes for the three other tranches, and a Luna smoke start
then refuses (`rules.bounded`, `layout.spend_terms`). The authorization, the freeze, the pause rules and the login
guards (Codex for the candidates, Claude for the judge) are those of every tranche, and so are the study's stops for
a forbidden model, three contaminated tasks, too little free disk and a `stop:` decision of the calibration's readout.
The incident stop is not: an incident in the Luna smoke fails its check and stops nothing (ruling L-R9), since the
10% rule counts the incidents of the smoke, the probe and the calibration only (`layout.STUDY_TRANCHES`).

```
SEED_SET_AUTHORIZED_TRANCHE=luna_smoke python -m experiments.seed_set.study candidates --tranche luna_smoke --arm direct_luna TASK
SEED_SET_AUTHORIZED_TRANCHE=luna_smoke python -m experiments.seed_set.study candidates --tranche luna_smoke --arm retry_until_check_luna TASK
SEED_SET_AUTHORIZED_TRANCHE=luna_smoke python -m experiments.seed_set.study pool --tranche luna_smoke --kind luna TASK
SEED_SET_AUTHORIZED_TRANCHE=luna_smoke python -m experiments.seed_set.study judge --tranche luna_smoke --kind luna TASK
python -m experiments.seed_set.study summarize --kind luna TASK
python -m experiments.seed_set.study smoke-check --tranche luna_smoke
```

Its pool has its own kind, `luna` (`<pools>/<task>/luna`, `results/pools/<task>-luna`), and holds the Luna smoke's
runs alone; the smoke's pools hold none of them. It is built and summarized under a copy of the judge criterion
naming only the Haiku judge (`results/luna_smoke-criterion.json`, `layout.pool_criterion`), since the summary takes
the criterion's judges to be the pool's. `smoke-check --tranche luna_smoke` is the smoke's check with one judge: every
planned unit settled, none cut by a usage limit and none an incident; the bound model and effort on every call and
in every rollout, no forbidden model; scans clean or cleared by a verdict; the judge's rating and a hidden result
on every clone; and no pause of the Codex starts (a credit balance) that one of its units recorded or that is open.
Each run's metering completeness is recorded in the row and decides nothing. It records a `luna_smoke` event, pass or
fail, which stays; the `smoke` event the probe and the calibration require is the Claude smoke's alone, so the
Luna smoke gates none of the three other tranches, and the calibration's readout reads no `luna` pool. A cut slot
is not run again, as in the smoke.

## Usage limits and paid extra usage

A usage limit cuts its unit and closes every start. A call whose stream shows paid extra usage closes every start
too; if that call ended normally its result is kept, and if it did not its unit is cut. A pause by the vendor's
recorded limit answer or by paid extra usage is reopened only by `study.py resume-after-limit`, with the reset and
the owner's meter reading. `not-a-limit` refuses both; it serves a pause flagged "unrecognised limit shape" whose
raw result shows no limit.
A Codex call's limit is read from its own error lines (a limit wording, status 429) and from the last
`rate_limits` snapshot of its own session record, matched by thread id (a used-up window names the reset); no
Codex limit answer is recorded yet, so each such pause is flagged "unrecognised limit shape". Credits held
(`credits.has_credits`) with a limit reached pause as paid credits; credits held without one record a pause whose
`closes` is `codex`: it closes the Codex starts only, since a Luna tranche runs with credits off (ruling L-R7).
Claude starts go on, and the call is scored as it ended. Only `resume-after-limit --cli codex`, with the owner's
meter reading as the owner's word that credits are off, reopens it; a `resume-after-limit` without `--cli` reopens
only the pauses that close every start, and the one with it only the Codex pause. A Codex call is priced at ordinary rates
from its summed turn, so a request above 272K input tokens is under-priced; the Luna smoke's ledger row must state
this.
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
