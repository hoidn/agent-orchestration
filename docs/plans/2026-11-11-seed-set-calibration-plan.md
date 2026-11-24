# Seed-Set Calibration Plan

**Status: Plan; the kit is on `main` (`09068ec8`, 2026-11-15; entry point
[`experiments/seed_set/README.md`](../../experiments/seed_set/README.md)) after five review rounds.** The first smoke stopped after one `claude-haiku-5-5` call (priced USD 0.0323) on an
isolation incident: the session loaded the account's claude.ai connectors (ledger row of 2026-11-18). The second
smoke (owner approval of 2026-11-23, after the isolation fix) ran its 8 calls on 2026-11-23 (priced USD 0.9902) with
no isolation breach and failed its check: scanner false positives left its pool without a summary. The third smoke
(scanner fixed; under the owner's allowance of 2026-11-23) passed all its checks the same day (7 calls, priced USD
1.4603). The ladder probe, the plan's one redraw, is under way: its first step stopped on two runs that lost their
login and a settlement crash, both fixed (ruling R16), and it resumed on the freeze of `dbe97cf0` and answered: rung T0, with the 20 calibration tasks drawn (9 of T0, 11 of T2).
Two probe runs were cut at the 20-minute call limit after making their change, so every candidate prompt now states
the limit and old-prompt probe runs are not reused (ruling R17; freeze of `352fbbaa`). Spend to date: 26 calls, USD
3.6620 priced settled; no calibration call. **The calibration is ready and held:** the owner's allowance of 2026-11-23
was used up at 23:58 PST that day (weekly meter 27%), mostly by coordination and not by experiment calls; it starts
on the owner's word or after 2026-11-24 17:00 PST, with its own spend row. The [ledger](#ledger) has every step. This page plans the scaled-down research step
the owner set on 2026-11-11: calibrate a small task set and a judge, then find
two to four simple workflow programs that run reliably and do at least as well
as one direct call at acceptable cost, and package them as seeds for a later
genetic search. The [current roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md)
owns the direction; `AGENTS.md` ("Experiment rules") and the
[structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator)
own the calibration, dominance and cost rules; the
[comparison harness](../../experiments/compare/README.md) owns sandboxing, the
model guard, the scan, the blind pool and the clone-id join. This plan owns
its task set, thresholds, budget and selection rule. Its commands are for this
machine and are not copyable examples. Spend is authorized only as the
[ledger](#ledger) records.

**Changes since acceptance (2026-11-12; the [ledger](#ledger) has each ruling).**
Zero-spend preparation is built on the branch `feat/seed-set-prep` and is
being fixed after its pre-spend review; nothing is spent. Where the text
below differs, these hold:

- The task ladder has rungs T0 to T5. T6 is not a rung. Task `a8ffc5997a`
  failed the leak audit and left the draw; reserve `4da856acda` replaces it.
- The calibration runs at 20 tasks with the frozen thresholds, or it does not
  run. A fill rung that adds no new task is replaced by T2; a split side
  shorter than ten is topped up from the other side; a fill tie goes to the
  easier rung; a draw that still cannot reach 20, and a probe whose results
  come out of order, are stops reported to the owner.
- The ladder probe is the one redraw: its 20 Haiku calls come from the redraw
  allowance, whose Sonnet and judge allowances stay unused and are set to
  zero in the runner. A probe run that ends in a provider incident is resumed
  once from the remaining redraw Haiku allowance and is never counted as a
  task failure.
- The four programs and `common.orc` declare `(:target-dsl "2.40")` (they
  build the same program as at 2.39).
- Blinding: candidates and anchors are built in random order; every pooled
  patch is scanned for model, arm and program names before any judge call and
  a hit refuses the pool; each rating is bound to the digest of the patch the
  judge read.
- A readout that ends in a stop prints no quality figure.

**Changes since review 2 (2026-11-13 and 2026-11-14, with fix round 1 after
review 3 and fix round 2 after its re-review; the [ledger](#ledger) has each
ruling).** Where the text below differs, these hold:

- *Usage limits (rulings R1 and R2).* A call the vendor answers with a usage
  limit (the result event's `api_error: usage_limit_reached`, status 429) cuts
  its unit. Recognition fails closed (review 3): an error result with status
  429 (a number or a string), an error result beside a rejected rate-limit
  event, or a provider error line in a session- or usage-limit wording that no
  other named status explains cuts the unit too, flagged "unrecognised limit
  shape"; the model's and the tools' own text is never read. The wording rule
  reads only a call that did not succeed (an error result, or no result event
  at all), never a warning beside a call that succeeded or a stream line cut
  mid-write (fix round 2). The pause and every refusal name the rule that fired
  and the line it read, and an older CLI's `...|<epoch>` gives the reset. A
  call whose stream shows paid extra usage (a rate-limit event with overage in
  use, or a rejected limit with overage allowed) closes every start as "paid
  extra usage" until `resume-after-limit`; a call that ended normally stays an
  observation (its slot does not run again, a judge's pool is not rebuilt),
  one that did not is cut, and
  either is priced at its metered tokens (final scoped check M1). `not-a-limit`
  refuses a pause by the recorded answer or by paid extra usage.
  When the raw result shows no limit, `study.py not-a-limit UNIT --reason R` records
  that decision while the pause is open: the unit becomes what the rules make
  it (an incident or its outcome), the pause stops closing starts, and nothing
  runs again. A unit its killed runner left unsettled refuses, and the pause
  and the refusal say the way out (fix round 3): `settle` the run first; a
  probe run, which only `probe` settles and `probe` refuses while starts are
  closed, reopens by `resume-after-limit` after the reset, and the next
  `probe` settles it as a cut run. A cut unit is not
  an incident and not an observation: it is recorded `cut`, never pooled or
  scored, and not counted by the 10% incident stop. The cut writes a `pause`
  event as soon as the unit's process ends, which closes every start; calls in
  flight finish or are cut. The refusal names the call's raw result, which the
  operator reads before resuming. Starts reopen only by `study.py
  resume-after-limit` with the reset the vendor's answer named and the owner's
  meter reading (the five-hour and weekly meters in percent, both below 100,
  and the time read); it refuses before that reset, and where no pause named a
  reset, a typed reset earlier than the limit. Outside the smoke, each planned
  slot whose run was cut runs again once, as a new unit, from the same cap; a
  pool with a judge cut is rebuilt once from the same run records and judged
  again by both judges. The smoke never runs a cut slot again: a smoke with a
  unit cut, a planned program without its run or a reserved unit not settled
  fails its check, and the cut run never sets the flat-or-bisect choice.
- *The launch guard and the host checks (fix rounds 2 and 3).* A unit's
  command runs as its guard's child from its first instant; the guard is a
  child subreaper, so what a root shell that died leaves behind is killed too,
  and a kill reaches a pid only while its start time matches, so a reused pid
  is never signalled. The host-side checks of candidate code (`settle`'s
  visible check, the probe's hidden check, `summarize`'s hidden tests) run
  under the same guard with two bounds. Each hidden test has 240 s, twice the
  120 s of Step 1's whole hidden run (the kit passes it to `summarize.py`,
  whose own default of 1,800 s stays): a hidden test that hangs past it counts
  as that test failing, and the pool is summarised (fix round 3). Each check
  has a backstop for a harness that itself hangs: 600 s (five times the
  120 s) plus 240 s per hidden test for a patch's hidden set, 1,200 s for the
  visible check, and for a pool's summary 600 s per clone plus 240 s per
  hidden test of each clone that runs them (final scoped check M2). A check past its backstop is recorded as timed out,
  never as a pass or a failure: a probe run with one is an incident, a summary
  that times out makes its pool an incident, and the readout counts timed-out
  visible checks apart. Every hidden test can hang to its own bound and fail
  before the backstop, so only a harness that itself hangs reaches it. The checks'
  temporary directories are recorded beside the ledger with the process that
  made them, the checks' own temporary directories go inside them, and the
  sweep at the start of every study command that takes the lock removes the
  recorded ones whose maker and check no longer run (a launcher killed with
  SIGKILL runs no cleanup) and prints their paths (fix round 3).
- *Concurrency (R3):* two runs at a time, and one study command that starts,
  prepares or settles units at a time (a lock beside the ledger), so two
  commands cannot put four units in flight.
- *Priced ceiling (R4).* Candidates and judges run the metered template (the
  judges through the study's own `programs/judge.providers.json`). Each unit
  is settled at its metered tokens times the frozen price table, whose sha256
  `criterion.json` names; a call with missing usage counts at the per-call
  worst case and is flagged. A start is refused when the tranche's priced total
  plus its worst case would pass the tranche's ceiling. Ceilings and per-call
  worst cases are read from `criterion.json`, with no default; the unit's worst
  case, times the price table's highest tier over its ordinary rate for the
  model (5 for Haiku, whose long-context rates are five times its ordinary
  ones; 1 for Sonnet), goes to the runtime as `--max-cost-usd`, because the
  runtime counts every call at the highest tier. `record-freeze` refuses a
  per-call worst case below that ratio times the largest ordinary-rate call
  `criterion.json` names for the model (`largest_call_usd`), and a tranche
  ceiling below two units in flight at its largest unit's worst case. A unit
  settled above its reserved worst case is flagged and closes every start with
  a `pause`.
- *CLI pin (R5).* Every start checks that the unit's Claude CLI is the
  criterion's pinned absolute path and answers `--version` with the pinned
  version, and records both in its ledger row; a mismatch refuses the start.
- *Sonnet judge only on a Haiku failure (R6):* not built. It needs a redesign of
  pool storage and of the summary and readout flow (the [ledger](#ledger) row
  says what); both judges still judge every pool, as the 2026-11-11 ruling set.
- *Credential (R7):* the route is unchanged and the owner's decision. Each
  unit's private home (`<work>/.private-homes/<id>` for a run,
  `<pool>/.private-homes/<id>` for a judge, both on `/home`) gets a copy of the
  subscription login file. It is removed when the unit ends, is refused or
  raises. A launcher killed with SIGKILL, or a host reboot, runs no clean-up:
  the copy then stays on disk until the next study command, which starts by
  removing every copy no live unit holds and prints the paths. The unit's
  agent dies with its launcher (a guard kills the unit's whole process tree).
  During its call the agent under test can read the copy (it runs as the same
  user inside the sandbox, which keeps network access); a copy it makes under
  another name, or the text it writes into its output or its patch, is not
  removed.
- *Re-runs and the caps.* "From the same cap" means a cut slot runs again only
  where its cap has room. The smoke's caps (10/1 candidates, 1/1 judges), the
  calibration's Sonnet candidates (20 of 20) and both judges' calibration caps
  (30 of 30) are fully planned, so a cut there is not run again: a smoke cut
  fails the smoke, and a calibration judge cut costs its task's pool. A re-run
  beyond the room is left out with a message, and its task keeps the runs it
  has; a pool whose two judges the caps cannot both hold, or whose first judge
  started and never settled, gets no judge, and the command names it after
  judging the others; a probe step the redraw allowance cannot hold is a stop.
- *Tasks rejected on 2026-11-13* (anchor stability):
  `1fd10ab4c3`, both forms (its reference fails
  `tests/test_run_lock.py` under load, 3 of 3; stable at load 13 on
  2026-11-15, and it stays rejected because the study runs under load);
  `9a7547ed4c` (T1) and `9a7547ed4c-t0` (T0), whose reference fails its hidden
  test every time under the kit's own temporary directory (a socket path one
  byte over the limit; ledger, 2026-11-15). `a8ffc5997a` had already
  left for the leak audit. Usable: T0 9, T1 11, T2 11 plus the smoke task, T3 19
  drawn, T4 6, T5 5.
- *Rehearsal 4* (2026-11-13) ran to the end and its readout stopped on an anchor
  failure: the reference of `1fd10ab4c3` passed 0.667 of its hidden tests. That
  is the runner's anchor check finding a real defect, which the rejection above
  removed. Its rerun on the merged tree with four calibration tasks (the
  independent status assessment, 65 minutes at load 57 to 170) ended with exit
  0: the smoke check passed, the probe chose T3 and drew 20 tasks, no anchor
  failed, and the decision was `stop: no judge passed its gate`, the expected
  result with 16 of the 20 tasks missing by construction.
- *Rehearsal 5* (2026-11-14, the code with R1 to R5, four calibration tasks, 54
  minutes): exit 0, smoke check passed, one injected usage limit in the probe
  was cut, closed starts and ran again after `resume-after-limit`, one start
  beyond the redraw ceiling was refused, and the priced totals equal the
  stand-in's known usage; decision `stop: no judge passed its gate`, as
  expected with 16 of 20 tasks missing. A 20-task rehearsal is still owed.
- *Rehearsals after fix round 1* (2026-11-14, stand-ins only, own ledgers,
  four calibration tasks). A: one usage limit cut the smoke's Haiku `direct`
  run; after the resume the other four programs ran and the pool was judged;
  the smoke check failed (a cut unit; the provider error), and neither the probe
  nor the calibration could start ("no passed smoke"), with no start after the
  smoke event. B: the limit in the probe, as in rehearsal 5, with the same
  result; its first attempt (B1) found that the rehearsal's separate
  check-withheld launch had no freeze on its own ledger, which every start now
  checks, and was rerun after the fix. A 20-task rehearsal is still owed.
- *Rehearsals after fix round 2* (2026-11-14, on `76b967f3`, the same form).
  A, the cut in the smoke: the smoke check failed, and nothing started after
  the smoke event. B, the cut in the probe, with every call that succeeded
  after the resume printing a limit warning on stderr: 19 such calls and no
  pause after the resume; the other figures equal rehearsal 5's. A 20-task
  rehearsal is still owed.
- *Found while building R1:* the harness's model scan counted a session row
  answered by `<synthetic>` (the CLI's own message at an API error or a usage
  limit) as a forbidden model, which would have stopped the study at its first
  usage limit. It no longer counts (`experiments/compare/scan.py`).
- *Text corrections:* Step 1c named a `calibration/direct_sonnet.orc`; there is
  none, and the `direct_sonnet` arm of `arms.json` runs `direct.orc` with the
  Sonnet model. The summary above said "the five programs"; there are four plus
  `common.orc`. Both are corrected in place.

**Headline exit test (fails today):** `experiments/seed_set/results/seeds.json`
exists, names its criterion and task-list hashes, and lists either two to four
programs that passed the frozen selection rule or the stop that prevented it.

## What this size can and cannot support

Quality is a blind judge's functional score from 0 to 8; hidden tests are
secondary evidence. This is seed selection, not a test of the roadmap's H-Q.
With 12 to 16 tasks, 6 direct and 3 workflow runs per task, the 90% interval
on a workflow's difference from direct is roughly ±0.8 point (planner's
estimate, for a per-run standard deviation near 2.5 points).

- **Can show:** a program that breaks or fails to finish; its call cost; a
  difference from direct of about 1 point or more; whether a direct run ever
  fails the visible check (if not, retry and repair do nothing).
- **Cannot show:** differences under about 0.75 point; an ordering among the
  seeds; equality with direct (one truly half a point worse passes half the
  time); anything beyond small fixes in this repository on Haiku at medium
  effort, or about long pipelines.
- **"Better":** a seed with direct's quality and more calls is dominated by
  direct. The readout says so for each seed; it is not the selection test.

## Facts established while planning

Checked 2026-11-11 with provider-free probes. *Probe* rows are single runs.

| Fact | State |
| --- | --- |
| Haiku in the harness | Not possible today. `experiments/compare/shim/model-guard` admits only `claude-sonnet-5-5` for Claude (a stub-CLI probe refused `claude-haiku-5-5`, with and without `ORC_ALLOWED_CLAUDE_MODELS`); `scan.find_hits` marks any other Claude model a non-clearable hit, for runs and for judges; both shims force subagents onto Sonnet |
| Task supply, this repository | Non-merge commits since 2026-07-01 that are fix-worded and change `tests/` plus at most 5 files and 200 lines under `orchestrator/`: 58 on the first-parent line, 114 in all history, 393 without the fix wording. Of the 58, 28 have two or more new test functions that fail on the parent and pass on the fix (*probe*, one run per side). A clone builds in 3 s and takes 141 MB; the new tests run in a median 8 s, at most 62 s (*probe*) |
| Judge route (read, not run) | `score_functional.orc` returns one score S0–S8 per clone at effort `high`. A pool is one task; a batch holds at most ten clones, every `anchors/*.diff` included; clone ids are random and each judge gets its own order. `summarize.py` writes per clone id each judge's rating, the hidden pass fraction and the run record. A pool takes one scoring run per judge. The harness's own control rule (`control-means-v1`) needs a third, hand-made control |

## Step 1: Zero-spend preparation (6 to 7 working days)

Every command runs with `experiments/thread_m/no_provider/` first on `PATH`
and `export PYTHONPATH=$PWD`; at the end `experiments/thread_m/no-provider.log`
does not exist. Stop below 20 GB free. Also reused from Thread M:
`env-freeze.txt`, the 2026-07-01 date floor, and item 5's method.

**1a. Admit Haiku (1 day).** `shim/model-guard` accepts the exact ID
`claude-haiku-5-5` only when `ORC_ALLOWED_CLAUDE_MODELS` lists it; the default
stays Sonnet-only. Both shims pin `CLAUDE_CODE_SUBAGENT_MODEL` to the single
allowed Claude model. `scan.find_hits` takes an `expected_claude_model`, from
`prepare.scan` for a run and `pool.scan_judge` for a judge;
`pool.write_score_inputs` sets `COMPARE_CLAUDE_MODELS` for a Claude judge.
`tests/experiments/test_compare_model_cap.py` gains: Haiku admitted only when
listed; Opus, Fable and unknown IDs still refused; a Sonnet answer in a
Haiku-bound run or judge is a non-clearable hit; the pin is the bound model.

**1b. Task packages (2 days), `experiments/seed_set/build_tasks.py`.**

- *Mine:* the facts table's filter over all non-merge history, no reverts,
  one commit per `git patch-id --stable`, a base that ignores
  `.orchestrate/`. Order by `sha256("seed-set-2026-11-11|" + sha)`; at most
  two tasks share a changed source file.
- *Oracle and split:* as
  [Thread M item 5](2026-11-11-roadmap-thread-m-zero-spend-measurement-plan.md#item-5-task-pool-for-the-phase-5-benchmark),
  steps 4 and 5: five runs each on parent and fix; two or more fail-to-pass
  test functions, the first in seed order being the visible check; a hidden
  run under 120 s; no hidden function name in the seeded tree.
- *Package* (`experiments/seed_set/tasks/<sha10>/`, the harness layout):
  `base_commit`; `seed/tests/…` (the fix's test files without the hidden
  fail-to-pass functions) and `seed/dev-check.json` (the visible node);
  `hidden/tests/…` and `hidden_tests.txt` (each hidden fail-to-pass function
  and each touched test file); `anchors/<sha10>-base.diff` (empty: the
  untouched base) and `anchors/<sha10>-upstream.diff` (the fix without its
  tests); `intent.txt` (commit subject and body: what judges and reviewers
  receive); `task.txt` (the same text, the visible check command, and the
  instruction to leave `dev-check.json` and existing tests alone). Drop a
  task whose text is under 80 characters or repeats a line the fix adds.
- *Freeze:* stop at 40 admitted tasks, listed in seed order in `tasks.jsonl`
  with hashes and changed-line counts: 20 drawn, the rest in reserve. Under
  20 admitted: drop the fix-wording filter once, then stop.

**1c. Programs (1 day), `experiments/seed_set/programs/`,** in the layout and
`run((task) (intent) (repo)) -> Outcome` contract of the seed catalog
(`experiments/orc_structural_search/seeds/`), target 2.39, every call
`claude-haiku-5-5`, `:timeout-sec 1200`, effort `medium` (bound explicitly:
the vendor's defaults differ). Drafts of the three new ones compiled while
planning; a loop iteration is its own effect identity, so a retry is a new
call.

**Size limit (owner, 2026-11-11).** A seed is simple only if it is short:
every seed program file has fewer than 50 physical lines of `.orc`, counting
code, comments and blank lines. The shared `common.orc` holds only the two
result types every seed returns (the interface to the harness: `Change`,
`CheckReport`, `Outcome`); it is not
counted and is frozen, so a seed cannot move its own definitions there. The
limit is checked by a test and by the selection step, and it travels with the
seed set: a later genetic search admits a child only under the same limit.
The four programs are 22, 31, 40 and 45 lines.

| File | Calls | State |
| --- | --- | --- |
| `direct.orc` | 1 | Copy of the catalog seed, rebound |
| `retry_until_check.orc` | 1–3 | New. At most three rounds of: `reset_clone.py` (restore the seeded tree), implement, `dev_check.py`; stop at the first pass |
| `implement_check_repair.orc` | 1–3 | New, from the catalog's check-diagnose-repair. Implement, check, repair in place with the check output, at most two repairs |
| `implement_review_revise.orc` | 2–3 | New, from the catalog's three-round version. Implement, one review, one revision if asked |

Plus `common.orc`, `dev_check.py`, `providers.json`, `commands.json` and
`arms.json`, whose `direct_sonnet` arm runs `direct.orc` with the model bound
to `claude-sonnet-5-5` (there is no separate Sonnet program). Compile each and
run each once through the public CLI behind the shims with a scripted provider.

**1d. Runner and readout (1.5 days), `experiments/seed_set/study.py`.** One
run: `prepare.run_arm(spec=ArmSpec(...))` with `COMPARE_CLAUDE_MODELS` and
`COMPARE_MAX_CALLS` set, launch, `collect`, `scan --hash <fix>`,
`check_first_attempt` on the final patch (the visible result, stored with the
run record), then delete the run's `cand-*` trees; two runs at a time. One
task: build its pool, run the judges, `verify-pool`, `scan --pool --judge`,
`summarize.py`, then delete the pool's clones and keep its records; at most
two pools on disk (a pool is 1 to 3 GB). `tests/experiments/test_seed_set.py`
checks on fixtures: a deterministic split, no hidden function in a seeded
file, the offline retry, the judge gate and the selection rule.

**1e. Offline checks (0.5 day).** Every task's base fails and its reference
fix passes the visible check and the hidden set, five of five. A sandbox run
with a stand-in CLI that applies the fix passes the visible check inside the
sandbox. One pool with scripted judges proves the route: the empty base
anchor pools as an unchanged clone, both judges' ratings and the hidden
results land in `results.json`, and a second pool of the same records matches
the first by run record and patch hash.

**1f. Freeze.** Commit; `git worktree add --detach /home/ollie/seedset-rt
<commit>`; work root `/home/ollie/seedset-work`. Write
`experiments/seed_set/criterion.json`: model IDs and efforts, runtime commit,
hashes of `tasks.jsonl`, every program, `score_functional.orc` and the two
harness criterion files (`judge-calibration.json` naming both judges,
`judge-seeds.json` naming the selected one; rubric `score_functional.orc`,
`criteria: ["quality"]`, `reference: null`, no `calibration` block), and
every threshold, rule, cap and stop of this plan. Its sha256 goes in the
ledger before the first call. A later apparatus fix is a ledger row with the
new hash; thresholds do not change.

## Probable calibration failures and the response to each

Added 2026-11-11 on the owner's instruction to preempt them. Each response is
fixed here, before any spend, and stays inside the authorized calibration and
redraw caps. Where this section and Step 2 differ, this section governs.

| Probable failure | Why it is likely | Response |
| --- | --- | --- |
| Tasks too easy for Haiku: G1 and G2 fail high, G3 has no room, V4 has too few failing candidates | In the Phase 1 authoring check three of three Haiku sessions passed in about 100 seconds; every task hands the agent a failing test it can run | The difficulty ladder and its probe, below |
| The workflows' check steps never fire, so no workflow differs from `direct` | A single agent session can run the visible test itself and iterate | The probe measures it; the check-withheld form, below |
| Tasks too hard: Haiku cannot find the change from a short commit message | The repository is large and statements are short | The ladder's easy tiers |
| A judge cannot tell the fix from no change, or ranks the fix below candidates | October's failures; judges run no tests | An early judge look on three tasks before the rest of the judge calls |
| Apparatus incidents eat the tranche | About 40% of October's calibration starts were lost to them | The mechanical smoke check; first wave two at a time; the subagent tool off in candidate sessions; launches halt on the incident rule |
| A candidate can reach the fix | Clones are built from this repository | A zero-spend audit that no clone holds objects after its base commit and that the scan for the fix hash fires on a planted copy |

**Difficulty ladder (owner, 2026-11-11: "by designing significantly harder /
easier tasks").** Tasks are built in five tiers that differ by design, not by
a few lines. Every tier holds natural changes from this repository with their
own tests, admitted through the same oracle, split, leak and provider-guard
checks. No flaw is ever planted.

| Tier | What makes it that hard |
| --- | --- |
| T1, very easy | One source file, at most 20 changed source lines; the statement names the file; the failing test is in the tree |
| T2, easy | At most two source files and 60 lines; the statement is the short commit message plus the names of the files to change (a recorded deviation, coordinator ruling on review 2 M8: with the message alone every T2 statement falls under the 80-character floor); the failing test is in the tree |
| T3, medium | The 20 tasks already built: at most five files and 200 lines; the failing test is in the tree |
| T4, hard | Six to fifteen source files or 200 to 600 lines; the statement is the commit message; the failing test is in the tree |
| T5, very hard | A feature, not a fix: a commit or a run of consecutive commits that adds new behavior with at least 300 added source lines; the statement is the commit message; check-withheld form, so there is no test to run |

At least eight tasks per tier, twelve where the history allows.

**Check-withheld form.** The visible test is not in the candidate's tree; it
exists only in the check command that a workflow runs, which puts the test in
place, runs it and removes it. `direct` then has no test to run, and a
workflow's check step is the only executed signal. T5 always uses it. Any
tier can be built in it; calibration and seed evaluation always use the same
form for a task.

**Ladder probe (20 Haiku candidate calls, charged to the redraw tranche).**
Before any other calibration call: `direct` once on the first four tasks of
each tier in seed order, hidden tests run, no judges. Per tier it gives the
number of tasks whose hidden set passes, and the share of runs in which the
agent itself ran the visible test.

| Probe result | Calibration's 20 tasks |
| --- | --- |
| Some tier has 1 to 3 passes of 4 | Drawn in seed order from that tier, filled from the adjacent tier whose count is nearer to 2 |
| No tier is in that band, but the tiers straddle it | Ten from the hardest tier with 3 or 4 passes and ten from the easiest tier with 0 or 1 |
| Every tier has 3 or 4 passes (all too easy) | One extension probe, below, on the harder end |
| Every tier has 0 or 1 passes (all too hard) | Read the 20 transcripts first; then one extension probe, below, on the easier end |
| The agent ran the visible test in 80% or more of the in-tree runs, and the chosen tier is T1 to T4 | The chosen tasks are used in the check-withheld form |

**If the whole ladder misses (one extension probe, 20 more Haiku calls, the
rest of the redraw cap).** Four probe tasks cannot tell 3 of 4 from 4 of 4
reliably, so this is a coarse screen, and its only job is to avoid spending
the calibration tranche on a task set that cannot pass its gates.

- *All too easy.* The ladder is extended upward without planting anything:
  T1 to T4 in the check-withheld form (the agent loses the test it was
  iterating against), and a tier T6 of larger features (several commits on
  one topic, at least 1,000 added source lines). The extension probe runs
  `direct` on four tasks of each of the two hardest available rungs and four
  each of T3 and T4 withheld, as far as 20 calls go.
- *All too hard.* That is more likely an apparatus fault than difficulty,
  because T1 names the file and ships a failing test: the agent may be unable
  to run tests in the sandbox, or to write its result. The transcripts are
  read before another call; a fault is fixed and the ladder probe's failed
  runs are reported as incidents, not as difficulty. If the runs are sound,
  the extension probe adds a tier T0 (the statement also quotes the visible
  test's failing assertion) and runs it and T1 again.
- *If the extension probe still finds no tier in the band:* stop. No
  calibration call is made, at most 40 probe calls have been spent, and the
  result goes to the owner as a finding with two options that both need a
  new decision: a different author model (all too hard), or tasks of another
  kind, longer and multi-stage, since a model that finishes every task of
  this family in one call leaves a workflow nothing to add (all too easy).

**Bisection instead of the flat probe (owner, 2026-11-11: "consider binary
search type strategies if this turns out to be inefficient").** The flat
probe is the default because its 20 runs go out as one batch, it measures on
every tier whether the agent runs the test itself, and it shows whether the
tiers are really ordered by difficulty, which a bisection assumes. It is
replaced by a bisection over the rungs, ordered T0, T1, T2, T3, T4, T5, T6,
in either of these cases:

- the smoke shows a `direct` run is expensive: a median above 15 minutes or
  above USD 0.50 by the CLI's own figure;
- more than five rungs have to be searched, which is the extension probe:
  it then bisects the rungs not yet probed instead of probing them all.

The rule: probe four tasks of the middle rung; 4 passes of 4 moves to the
middle of the harder half, 0 of 4 to the middle of the easier half, 1 to 3
stops there. When two adjacent rungs come out 4 and 0, calibration takes ten
tasks from each. Seven rungs need at most three steps, 12 calls, against 28
for a flat pass. What it costs: the steps run one after another, it gives no
check that the rungs are ordered, and a rung decided on four tasks can send
the search the wrong way; so if a step contradicts an earlier one (a harder
rung passes more than an easier one), the search stops and the remaining
rungs are probed flat within the cap.

Tasks are chosen by tier and seed order, never by their own probe outcome; a
probed task that is drawn keeps its probe run as the first of its four Haiku
runs unless the form changed; the programs' text is part of the form (ruling
R17). The ladder probe is the plan's one redraw,
taken before calibration instead of after it: no later redraw follows, and
Step 2's redraw paragraph does not apply. Worst case in Haiku candidate
calls: 40 from the redraw cap (probe and extension probe) and 80 from the
calibration cap.

**Early judge look (6 judge calls from the calibration cap).** After the
first three tasks have their runs, pool and judge them with both judges. If,
for both judges, the reference scores less than 4 points above the base on
two of the three, stop and report to the owner before any further judge call.

## Step 2: Calibration (paid)

**Smoke,** on the manifest's smoke task `194ad866a1`, the first T2 task that is
not a probe task (coordinator ruling 1, 2026-11-12; it replaced the last
reserve task when the leaking T3 task left the draw): one direct
run per model, one run of each workflow, then one pool scored by both judges.
Pass: sessions show only the bound models, the scans are clean, and
`results.json` holds both judges' ratings and a hidden result for every
clone. Whether token receipts are complete is recorded.

**Candidates (80 Haiku, 20 Sonnet):** on the 20 drawn tasks, `direct.orc` four
times (so a task's Haiku mean does not rest on one or two draws) and the
`direct_sonnet` arm (`direct.orc` on Sonnet) once.

**Judging (30 Haiku and 30 Sonnet judge calls).** The route is the harness's:
one pool per task, `prepare.py pool` with `judge-calibration.json`,
`--judge claude-haiku-5-5 --judge claude-sonnet-5-5` and the task's run
records. The pool is one batch, the five candidates plus the two anchors, as
applied-patch clones under random ids, in a separate random order per judge;
one judge call scores it. The rubric is the harness's functional one,
unchanged: one score from S0 (none of the required behavior works) to S8
(complete and credibly correct) for how much of the intended behavior works
through its normal entry points, with no separate points for organization,
size or style. Judges read the clones, change nothing and run no tests.
`summarize.py` then runs the hidden nodes on every clone. For the first ten
tasks a second pool of the same run records (new ids, new order) is scored by
both judges: the retest. A failed run is not pooled and scores 0.

**Where every number comes from.** Each pool's `records/results.json` gives,
per clone id, each judge's rating, the hidden pass fraction, the run record
and the anchor label. The readout aggregates these files and nothing else,
anchors first; a retest clone is matched to its first judgment by run record
and patch hash, never by position.

**Judge gate, per judge, first judgment unless stated.** The study computes
it; the harness's control rule needs a third, hand-made control per task.

| Check | Threshold | A failure means |
| --- | --- | --- |
| V1 controls | Reference minus base at least 4 points on at least 18 of 20 tasks; mean reference at least 6; mean base at most 1 | The judge cannot tell a merged fix from no change |
| V2 reference rank | The reference scores at least the mean of its batch's candidates on at least 17 of 20 tasks | October's first failure: the merged fix ranked at or below candidates |
| V3 retest | On the ten retest tasks, mean absolute difference per clone at most 0.75 point, and at most 10% of clones differ by 2 or more | October's second failure: identical code scored 4 then 3. Scores cannot carry a half-point tolerance |
| V4 agreement with tests | Over the 100 natural candidates, the probability that a hidden-passing one outscores a hidden-failing one (ties count half) is at least 0.75; needs 15 in each class, else recorded as not assessed | Judge and tests measure different things. The ten largest disagreements are read by hand and reported; the tests may be the brittle side |

A judge passes on V1 to V4. The cheapest passing judge is used: Haiku, else
Sonnet. If neither passes, the hidden-test pass rate becomes the primary
measure and is reported as such (survivors have 1 to 3 passes of 4; Haiku
pass rate 20% to 80%; Sonnet minus Haiku at least 10 points), and the plan
stops for the owner before any seed evaluation.

**Task gates, on the selected judge's scores,** with the test figure beside
each as secondary. A **survivor** is a task whose Haiku mean is between 2.0
and 6.5 (beside: passes of 4); above is too easy, below too hard.

- (G1) at least 12 survivors;
- (G2) Haiku mean over all drawn tasks between 2.5 and 6.5 (pass rate);
- (G3) Sonnet mean minus Haiku mean at least 0.5 point over all drawn tasks
  (pass-rate gap): the difficulty rule's observed advantage under the rubric.
  If it fails while the pass-rate gap is at least 10 points, the judge is
  treated as insensitive and the other judge is tried;
- (G4) at least 90% of runs end pooled and rated; no forbidden-model hit in a
  run or a judge; no judge excluded on more than two pools.

**One redraw** if G1, G2 or G3 fails: ten reserve tasks, those with the most
changed source lines if the Haiku mean was above 6.5, the fewest if below
2.5, otherwise the next in seed order; retest on the first five; every gate
recomputed over all 30 with the counts scaled (V1 27 of 30, V2 25 of 30). If
a gate still fails: stop, report the calibration table, and make no quality
claim. Survivors beyond 16 are cut in seed order.

## Step 3: Seed evaluation (paid; not authorized until calibration is reported)

| Arm | Runs per task | How |
| --- | --- | --- |
| Direct | 6, fresh | Live |
| Re-roll `Q(k)`: retry with at most `k` = 2, 3 attempts (best-of-`k` by visible check has the same quality at `k` calls); random-of-3; any-of-3 (upper bound) | none | Offline, averaged over every ordered triple of a task's six direct runs. The visible check picks the run; the baseline takes that run's judged score. `Q(1)` is direct |
| Retry parity | 2, on the first six survivors | Live `retry_until_check.orc`; passes if every run completes, mean calls are within 0.5 and mean score within 1.5 points of the offline figure for those tasks |
| Implement-check-repair | 3 | Live |
| Implement-review-revise | 3 | Live |

Direct runs first. They are fresh because the calibration runs chose the
tasks and would bias the baseline. If the visible check failed in under 20%
of them, the parity runs and implement-check-repair are not launched and the
readout says the check has no selecting power on this set.

**Judging (32 calls of the selected judge).** One pool per task through
`pool.write_pool`, in two batches of at most eight candidates plus the two
anchors; each arm's runs are dealt alternately into the batches, so a batch
shift cancels in arm differences. If reference minus base falls under 4 in
more than three of the 32 batches, no quality claim is made.

**Envelope and scoring.** 1,200 s per call, `COMPARE_MAX_CALLS` 1 or 3,
3,600 s per run. Every candidate prompt states the call's 20 minutes (ruling R17). A failed run or a timeout scores 0; a provider or sandbox
incident is resumed once with `resume.sh`, then excluded and listed. Quality
`q` is the mean over tasks of the per-task mean score, with the hidden pass
rate beside it. Cost `c` is mean provider calls per run, admissible because
every candidate call is one model at one effort; judge calls are evaluation
cost, reported apart. Metered tokens (`metering.receipts`) are reported
beside `c`; if nested sessions appear in over 10% of an arm's runs, cost
comparisons use tokens only.

**Selection rule (frozen).** `direct` is always in the set as the reference.
Another program is a seed when all hold:

1. at least 95% of its runs complete;
2. `q ≥ q_direct − 0.5`;
3. re-rolling at equal calls does not beat it: `q ≥ Q(k) − 0.5`, `k` being
   its mean calls rounded to 1, 2 or 3, halves up (vacuous for retry);
4. `c ≤ 3.0 × c_direct`, and the same for priced tokens where metered;
5. its distinctive step (a second attempt, a repair, a revision) ran in at
   least 20% of its runs;
6. for retry, the parity check passed.

The readout gives each arm's `q` and each difference from direct with a 90%
bootstrap interval over tasks (10,000 resamples, fixed seed), names every
comparison whose interval spans the tolerance, and applies the driver's
dominance test against direct with `tau_q` 0.5 point and `tau_c` 0.10.

**Extension (reserved).** A live workflow within 0.25 point of the line in
rule 2 or 3 gets two more runs per task, once, judged in one further batch.

**Search dimensions around one seed (proposed 2026-11-12; not authorized, not yet built).**
Owner question: is it better, in the Pareto sense, to plan with a mid model
and implement with a weak one, to use the weak model for both, or the mid
model for both, with the reviewer's strength as a further axis. The owner's
framing: one seed and declared search dimensions, not several seeds. No
measurement in this repository answers the question, and the four programs
above cannot: none has a plan step and all run on Haiku.

The seed is one program, `plan_implement_review.orc` (new, under 50 lines):
plan, implement, review, revise at most once. The dimensions a later search
may vary are listed below. Each point is a program of its own, made from the seed by
rewriting literals at call sites (the model and effort of a role are string literals at
that role's calls), and not a binding of the seed's inputs: a run resumed with changed
inputs reuses nothing, so points that differed only in inputs would share no recorded work
([mutant generator plan](2026-11-13-phase-6-mutant-generator-plan.md#the-first-space-is-programs-not-bindings)):

| Dimension | Values |
| --- | --- |
| Planner | absent, Haiku, Sonnet |
| Implementer | Haiku, Sonnet |
| Reviewer | absent, Haiku, Sonnet |
| Effort per role (owner, 2026-11-13) | for each role that is present, one of the CLI's levels `low`, `medium`, `high`, `xhigh`, `max`; chosen per role, independently of that role's model |
| Revision rounds (reviewer present) | 1, 2 |
| Conversation (owner decision 11 of the roadmap keeps Agent Sessions) | each later step of a role starts fresh, or continues that role's session; only between steps bound to one model |
| Prompt wording (owner, 2026-11-13: "remember that the prompt too is mutable") | the text of any step's prompt. For the long-horizon seed this includes what the setup step initialises (`AGENTS.md`, the project layout, the document catalogue, the log, the topic notes) and the documentation rules it writes for later steps: the current wording is a starting point, not a fixed part of the seed. A mutation rewrites one prompt and changes nothing else. Coordinator's reading: text has no small set of values to enumerate, so it is searched by proposal after the effort space, not inside the first space below |

That is 18 model placements before effort, rounds and conversation. With effort per role the
space is no longer small: three roles, two models and even three effort levels give 216
combinations.

**First space to search (owner, 2026-11-13): one model, effort per role.** Every role runs
`claude-haiku-5-5` and only the effort level of each role varies; Sonnet placement is a later
extension. With three roles and three levels (`low`, `medium`, `high`) that is 27 points. It
rests on one assumption, which is measured before it is used: Haiku's success rate does not
fall as effort rises. The check is an effort ladder on the direct call (the same tasks at each
level, same tools and limits); it doubles as the difficulty calibration with effort as the
varied quantity, which `AGENTS.md` allows, and it shows at which level each task sits in the
target band. If the ladder is monotone, the search need not visit all 27 points: start from
the cheapest point, raise one role's effort at a time, and keep a step only when it buys
quality at a price the equal-cost re-roll curve does not beat (seven points for three roles
and three levels, plus the all-high corner as a ceiling). If the ladder is not monotone on
these tasks, the assumption is dropped and the points are compared directly. Cost is priced
tokens throughout, since a higher effort spends more tokens per call. `direct.orc` is the point (absent,
Haiku, absent) and `implement_review_revise.orc` is (absent, Haiku, Haiku),
so the study's existing arms are points of the same space.

What this study does for it: qualify the seed and freeze the rules of the
space. It does not evaluate the placements; that is the search's work, under
its own plan and budget.

- Seed qualification: the all-Haiku full form (Haiku, Haiku, Haiku) runs
  three times per task and must meet selection rules 1 and 2. About 60 runs,
  180 to 240 Haiku calls, and one more judge batch per task.
- Cost in this space is priced tokens only (frozen price table). Provider
  calls are not a cost proxy once points differ in model.
- The front a point is judged on includes the offline re-roll curve `Q(k)`
  priced at `k` direct Haiku runs: a Sonnet step must beat spending the same
  money on more Haiku attempts.
- Each step's model is verified per step from the run's receipts; a run
  whose step did not run on the declared model is excluded and listed.
- Limit of any claim: the task set is chosen so that Sonnet beats Haiku on
  it (gate G3), so results hold for tasks where the model matters.

The calibration already measures two points of the space with priced tokens
(direct on Haiku four times and direct on Sonnet once, per task); they are
reported with the calibration result. Zero-spend preparation: the program,
per-step model binding through the shims' model guard, and the per-step
model check. The qualification spend is requested with the seed-evaluation
budget. Note for the search plan: 18 points is small enough for a full grid
or successive halving; a genetic search earns its cost only when the
program's structure also mutates.

## Step 4: Output

`experiments/seed_set/`: `programs/`, `tasks/`, `tasks.jsonl`,
`criterion.json`, the pools' `results.json` under `results/pools/`,
`results/readout.md` (one page: judge gate, calibration table, arm table with
intervals, the rule applied, limits) and `results/seeds.json` (selected
programs with hashes, `q`, `c`, intervals, the judge used, and the criterion,
task-list and runtime hashes). A later search passes the program paths as
seeds; `mode1.check_seed_catalog` pins
`experiments/orc_structural_search/seeds/capped` today, so its plan copies
the seeds there or changes that check.

## Budget

Caps, as candidate calls and judge calls, Haiku / Sonnet.

| Tranche | Candidates | Judges | State |
| --- | --- | --- | --- |
| Smoke | 10 / 1 | 1 / 1 | Candidates authorized; judges to request |
| Calibration | 80 / 20 | 30 / 30 | Candidates authorized; judges to request |
| **Calibration total (smoke + calibration)** | **90 / 21** | **31 / 31** | **The judge column is the addition asked of the owner** |
| Redraw, if a gate fails | 40 / 10 | 15 / 15 | Candidates authorized; judges to request |
| Seed evaluation | 420 / 0 | 32 of the selected judge | Not authorized |
| Extension | 192 / 0 | 16 of the selected judge | Not authorized |

A Sonnet token lists at about 20 times a Haiku token (vendor table cached
2026-11-03; re-read at freeze). Tokens per call are unknown until the smoke.
Allowance does not move between tranches; there is no top-up after a null.

Each tranche also has a priced-token ceiling in USD (metered tokens times the
frozen `orchestrator/providers/price_table.json`), and each model a per-call
worst case. Both are set by the coordinator in `criterion.json` at the freeze
and written to the ledger before the first call; the kit has no default and
refuses a start without them. A start is refused when the tranche's committed
priced total (settled units at their metered price, open ones at their worst
case) plus its own worst case would pass the ceiling. A call cut by a usage
limit counts like any other call; a slot run again after it takes its calls
from the same cap, so a re-run is possible only where the cap has room. The
criterion also names, per model, the largest ordinary-rate call it expects
(`largest_call_usd`, from the smoke or earlier sessions): the per-call worst
case must be at least the table's highest-tier ratio times it, and each
ceiling at least two units in flight at the tranche's largest unit's worst
case, or `record-freeze` refuses.

## Stop rules

- Fewer than 20 tasks admitted after the one widening: stop before spend. The
  next source is external repositories by Thread M item 5's method, which
  needs the harness to accept another candidate source.
- A smoke failure, or neither judge passing its gate: stop for the owner.
- A hidden function name in a transcript or patch, a scan hit on
  `github.com`, `git fetch` or the fix hash, or a judge that ran tests: the
  run or judgment is contaminated; three such tasks stop the study.
- A forbidden-model hit, over 10% of a tranche's runs excluded as incidents,
  a cap reached, or under 20 GB free: stop.
- A usage limit is not a stop and not an incident: every start closes until the
  vendor's named reset has passed and the owner has given a meter reading
  (`study.py resume-after-limit`); the cut runs are no observations, and each
  cut slot outside the smoke runs again once from the same cap. A smoke with a
  cut unit fails, which is the stop above. A unit settled above its worst case
  also closes every start until `resume-after-limit`.
- A probe step the redraw allowance cannot hold (relaunches and re-runs used
  its room): stop.
- Only `direct` passes the rule: record "no workflow qualified at this size".

## What this plan makes harder

- The seeds are tuned to one repository, one language, one model tier and
  one judge; a later search must reuse that judge or recalibrate.
- Hidden tests and reference patches sit in this repository from the freeze
  commit on; a later task set must use earlier bases or move the packages.

## Not verified while planning

- Whether the GitHub repository is public. If it is, the fixes are fetchable;
  the sandbox keeps network access, so the scan is the control.
- Call duration and tokens per call, for candidates and judges (the smoke
  measures both), and how often a direct run fails the visible check.
- The judge route was read, not run: that an empty anchor pools cleanly and
  that Haiku returns a valid rating list for seven clones (Step 1e and the
  smoke). `score_functional.orc` fixes judge effort at `high`.
- How judge scores spread on small fixes. If nearly every candidate scores 7
  or 8, G2 fails and the redraw goes to larger fixes.
- Whether `metering.receipts` returns complete Claude usage (the Phase 1
  search logged it as unavailable); if not, cost is calls only. Whether
  in-process subagents can be switched off; they are pinned and counted.
- The oracle yield beyond one run per side and off the first-parent line.

## Ledger

| Date | Entry | Detail |
| --- | --- | --- |
| 2026-11-11 | Owner decision, scoring: "tests are brittle. subagents as judge preferred if it works". The blind judge's functional score is primary, on condition that the judge passes the gate of Step 2; hidden tests are secondary evidence. |
| 2026-11-11 | Owner decision, budget: "Calibration first". Authorized: the smoke and calibration candidate calls (90 Haiku, 21 Sonnet) and one redraw (40 Haiku, 10 Sonnet). Not yet authorized: the judge calls of those tranches (31 Haiku and 31 Sonnet; 15 and 15 more for a redraw). The seed evaluation and its extension stay unauthorized until the calibration result is reported. |
| 2026-11-11 | Owner decision, elsewhere: the Phase 1 authoring check (six Haiku sessions, USD 12) is approved separately and is not part of this plan's budget. |
| 2026-11-11 | Owner decision, judge calls: "Approve both judges". Authorized in addition: 31 Haiku-judge and 31 Sonnet-judge calls for the smoke and calibration tranches, and up to 15 of each on the one redraw. Authorized in total for calibration: 121 Haiku and 52 Sonnet calls, or 176 and 77 with the redraw. The seed evaluation and its extension remain unauthorized. |
| 2026-11-11 | Owner decision, judge gate: "Two natural controls". The judge is validated on the untouched base and the reference fix of each task, plus the retest, test-agreement and stronger-arm checks of Step 2. This is a study-local gate computed from the pools' `results.json`; it is recorded in the `AGENTS.md` experiment rules. |
| 2026-11-11 | Coordinator ruling: both judges are calibrated on the same batches (the planner's alternative of running the Sonnet judge only on a Haiku failure is not taken). Spend to date: 0. |
| 2026-11-11 | Owner requirement: "part of the seed's simplicity req should be a challenging loc limit (eg <50 lines of orc". Recorded as the size limit in step 1c: under 50 physical lines per seed program, `common.orc` exempt and frozen. The owner confirmed on 2026-11-11 that `common.orc` does not count; the four programs pass at 22, 31, 40 and 45 lines (44 to 67 if `common.orc` were counted). |
| 2026-11-11 | Owner instruction: "preempt probable calibration failures". The section "Probable calibration failures and the response to each" is added: a 20-call Haiku probe before anything else, hard and easy reserves mined before spend, a check-withheld task form, an early judge look on three tasks, and apparatus measures. All inside the authorized caps; the early replacement of tasks is the plan's one redraw. Coordinator rulings; the check-withheld form changes what `direct` can do and is used only on the probe's evidence. |
| 2026-11-11 | Owner clarification: preempt "by designing significantly harder / easier tasks". The reserves and the single-tier probe of the previous row are replaced by a five-tier difficulty ladder (very easy to very hard, the hardest being features in the check-withheld form) and a ladder probe of four tasks per tier that picks the tier calibration draws from. No flaw is planted in any task. |
| 2026-11-11 | Owner question: "what if all tiers are too easy or all tiers are too hard". The ladder section gains the two cases: one extension probe of 20 calls inside the redraw cap (harder rungs: the check-withheld form and a tier of larger features; or, after reading the transcripts for an apparatus fault, an easier rung), then a stop with a report to the owner if no tier lands in the band. No calibration call is made on a task set the probe shows cannot pass. |
| 2026-11-11 | Owner suggestion: "consider binary search type strategies if this turns out to be inefficient". Recorded as a pre-decided switch: the flat ladder probe stays the default; a bisection over the ordered rungs replaces it when a `direct` run proves expensive in the smoke (median above 15 minutes or USD 0.50) and is always used for the extension probe. Thresholds are the coordinator's. |
| 2026-11-11 | Runner reviewed and revised (branch `feat/seed-set-prep`, not merged). The independent review confirmed the caps, the locking and the gate formulas, and found one blocker and nine majors, all fixed: the visible check and the hidden tests now run behind refusing stubs with an empty home, so candidate code cannot start a provider outside the guard; the spend ledger lives at a fixed path under the home directory; planning and reserving share one lock; order and stop rules are enforced in code (criterion frozen, smoke passed, stops on a forbidden model, three contaminated tasks or the incident rule); provider incidents are not scored as zeros; an unsummarizable pool is an incident, not a suppressed readout; resume scripts are disabled. Spend to date: 0. |
| 2026-11-11 | Coordinator rulings recorded with the runner: there is no later redraw (the ladder probe is the one redraw; the redraw cap's 40 Haiku calls serve only the probe, its Sonnet and judge allowances stay unused; a failed calibration gate is a stop with no quality claim). A judge whose agreement with the hidden tests cannot be assessed (fewer than 15 candidates in a class) is not failed for that, and the decision line and the result say in plain words that it passed on V1 to V3 alone. When two rungs are in band the one nearer 2 of 4 wins, ties to the harder. |
| 2026-11-11 | Known limits of the runner, accepted: the subagent tool cannot be switched off (the provider command is a fixed registry template), so the model pin and the call cap are the bound; the session audit cannot see a session kept only in memory or a direct API request made with the sandbox's copied credential; the detector for "the agent ran the visible test itself" misses wrappers and test files run directly, and over-counts a `-k` filter that deselects the test. |
| 2026-11-12 | Owner question: which model placement is Pareto-better (plan mid and implement weak, weak for both, mid for both; reviewer strength as another axis), clarified as "1 seed + defining the search dimensions" rather than several seeds. Coordinator ruling: recorded in Step 3 as "Search dimensions around one seed", proposed and not authorized. This study only qualifies the one seed in its all-Haiku form and freezes the space's rules (priced-token cost, equal-price re-roll curve on the front, per-step model check); evaluating placements belongs to the search. Coordinator's reading, to be corrected by the owner if wrong: the four existing programs and their selection rule stay as planned. Spend to date: 0. |
| 2026-11-12 | Coordinator rulings with the ladder and runner integration (branch `feat/seed-set-prep`, not merged) | The task that fails the leak audit (`a8ffc5997a`) leaves the draw and reserve `4da856acda` replaces it; T6 is dropped as a rung; the three blinding gaps are closed (random build order of candidates and anchors, an identity scan of every pooled patch before any judge call with a hit refusing the pool, each rating bound to the sha256 of the patch read); the network limit is stated on every readout. A zero-spend rehearsal on the real packages with stand-in agent and judges ran the whole path inside the caps (117 of 121 Haiku and 52 of 52 Sonnet reserved for smoke and calibration, 20 of 40 for the probe). Spend to date: 0. |
| 2026-11-12 | Coordinator ruling: 20 tasks at the frozen thresholds, or no calibration | No scaled gate ever starts spend; the scaling code is deleted. A fill rung that adds no new task (T0 for T1 or the reverse) is replaced by T2 (40 more Haiku and 8 more Sonnet candidate calls, inside the caps); a split side shorter than ten is topped up from the other side; any draw that still cannot reach 20 is a stop with no task list (T4 and T5 together; the four splits that arise only when probe results come out of order). The programs move to target 2.40. Recorded limits, not changed: the visible check runs candidate code on the host; the per-run time limit excludes time in checks; a patch that legitimately contains a scanned token costs its whole task; the withheld check was rehearsed through one run on a separate ledger. |
| 2026-11-12 | Pre-spend review of the builder and the integration: ready only after fixes (1 blocker, 9 majors, 12 minors) | Confirmed: only the two model ids pass and every launch is reserved before it starts (60 concurrent tries against a 40-call cap granted exactly 40); the probe-to-draw rule matches an independent rebuild over every probe result; 17 sampled packages pass the base and reference checks; the leak audit is clean except the task already rejected. Rulings on the findings: gate comparisons use exact arithmetic (an exact 0.5 gap had failed G3 by float rounding); a fill tie goes to the easier rung; an interrupted or incident probe run is resumed once from the remaining redraw Haiku allowance and is never a task failure, and a rung with fewer than three usable runs stops the probe; the redraw tranche's judge and Sonnet allowances are zero in the runner; judging refuses a pool with no clean identity scan; the freeze covers the study and harness code, the task list, the drawn packages and the programs, and a run refuses code loaded from outside the frozen checkout; a stop readout prints no quality figure; T2 statements are rebuilt as the commit message alone (they carried T1's file-name hint). Fixes in progress; a scoped re-review precedes any spend. Spend to date: 0. |
| 2026-11-13 | Owner direction: mutate model and effort per role | "for mutations of that seed, consider using a combination of model choice (haiku sonnet) and effort level for different agent roles". Recorded as a search dimension beside model per role: each present role (planner, implementer or coder, reviewer) has its own model (`claude-haiku-5-5` or `claude-sonnet-5-5`) and its own effort level. Consequences: a seed's entry takes a model and an effort per role (the long-horizon seed has one shared effort input today); cost stays priced tokens, since effort changes tokens per call and calls stop being comparable even within one model; the equal-price re-roll curve remains the bar. Reason recorded for using Sonnet in experiments under the Haiku default: model placement per role is itself the variable. Public figures (not ours) suggest effort is a large lever for Haiku: a benchmark write-up reports an aggregate from about 13 percent at `low` to 39 percent at `max`. Only `high` has been observed accepted for Haiku on this machine; the other levels are verified in the first probe. Spend to date: 0. |
| 2026-11-13 | Owner direction: if the space is too large, one model and effort per role | "consider just one model (haiku) and different effort levels (assuming performance of haiku increases monotonically with increasing effort level)". Recorded as the first space to search: all roles on `claude-haiku-5-5`, effort per role varied (27 points at three levels); Sonnet placement deferred to a later extension. The monotonicity assumption is measured, not assumed: an effort ladder on the direct call, which also serves as the difficulty calibration (effort is the varied quantity) and places each task relative to the 10 to 30 percent band. Public figures, not ours, show the aggregate rising with every level for this model on one benchmark. With a monotone ladder the search walks one role's effort at a time from the cheapest point (seven points plus one corner) rather than the full grid. No Sonnet call is needed for this space. Spend to date: 0. |
| 2026-11-14 | Correction to the row "mutate model and effort per role": a role's model and effort are literals at its call sites, not entry inputs | That row says "a seed's entry takes a model and an effort per role". It does not. The mutant generator's measurements showed that `resume` gives no plan when an input, or a default that takes effect, changes, so two points that differ only in inputs share no recorded work. The ruling of the [mutant generator plan](2026-11-13-phase-6-mutant-generator-plan.md#the-first-space-is-programs-not-bindings) holds: a point of the search space is a program, effort and model per role are string literals at each of the role's call sites, and a mutation rewrites them. The earlier row is kept as written. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling R1: a call cut by a usage limit | Not an incident and not an observation. The unit is recorded `cut`, does not count toward the 10% incident stop and never scores 0; its slot runs again once, as a new unit id, from the same cap, so total calls never pass the cap and every unit still launches once. A judge pool cut by a limit is rebuilt once as a new pool from the same kept run records, judged by both judges. Built: `units.usage_limit` recognises the vendor's answer from the stream-json result event (`api_error: usage_limit_reached`, status 429, shape of the long-horizon fixture `token-usage-limit-NonZeroAgentExitCodeError`); `study.cut_reruns`, `layout.current_pool`, `probing.allowed`. Found while building it: the harness's model scan counted the CLI's `<synthetic>` session rows (its own error and usage-limit messages) as a forbidden model, which would have stopped the study at the first limit; fixed in `experiments/compare/scan.py`. Consequence recorded: re-runs fit only where the cap has room; the smoke's caps, the calibration's Sonnet candidates and both judges' calibration caps have none. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling R2: starts close at a usage limit | At the first usage-limit answer the runner writes a `pause` event that `spend.reserve` honours: nothing more starts, calls in flight finish or are cut. Starts reopen only by `study.py resume-after-limit --reset T --five-hour P --weekly P --read-at T`: the reset named by the vendor's answer and the owner's meter reading (two percentages and the time read), recorded in the spend ledger; it refuses before the latest named reset and a reading taken before it. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling R3: concurrency two | Two runs at a time, not four, so that a usage limit cuts at most two calls in flight. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling R4: a priced-token ceiling per tranche, enforced by the kit | Candidates and judges use `claude_unrestricted_workspace_metered` (the judges through the study's own `programs/judge.providers.json`; the shared `experiments/compare/score.providers.json` is unchanged). Each unit is settled after it ends at its metered tokens times `orchestrator/providers/price_table.json` (per call, the larger of the table's ordinary-rate price of `modelUsage` and the CLI's reported cost); the table's sha256 is named in `criterion.json` and recorded in the freeze event. `spend.reserve` refuses a start when the tranche's committed total (settled units at their price, open ones at their worst case) plus its own worst case would pass the ceiling. A call with missing usage counts at the per-call worst case and is flagged. Ceilings per tranche and worst cases per model are read from `criterion.json` (`"spend"`), with no default: the coordinator sets the figures at freeze. The unit's worst case (its calls times the per-call figure) goes to the runtime as `--max-cost-usd`; the runtime prices at a model's highest tier, so the per-call figure must cover a call at Haiku's long-context rate, or a later call of a multi-call unit is refused and the run ends as an incident. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling R5: the CLI pinned by path and version | Before every start the unit's declared Claude CLI must be the criterion's pinned absolute path and answer `--version` (run with an empty home) with the pinned version; both go into the start's ledger row, and a mismatch refuses the start before anything is reserved. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling R6: the Sonnet judge only on a Haiku judge failure | Not built: it exceeds the bound the ruling set (about three hours, no redesign of pool storage). What it takes: (1) the same frozen pools for the later Sonnet judge, so either every pool's clones stay on disk until both judges are decided (30 pools of 1 to 3 GB; at most two fit today) or the harness gains a rebuild of a pool's clones under its recorded clone ids from the kept patches and mapping; (2) a summary per judge: `summarize.py` writes one `results.json` per pool with every judge of the mapping and runs the hidden tests on the clones, so a Haiku-only summary marks Sonnet excluded and a later Sonnet pass needs the clones again and a merge of ratings by clone id; (3) a two-phase readout: Haiku's gate (V1 to V4, and G3's insensitivity switch, which also hands over to the other judge) decides whether the Sonnet phase opens; (4) rulings for the early judge look and the smoke check, which require both judges today. Estimate 6 to 10 hours with tests and a rehearsal. Both judges keep judging every pool, as the 2026-11-11 ruling set. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling R7: the credential route is the owner's | `sandbox.prepare_unit` is unchanged: each unit's private home gets a copy of the subscription login file, removed when the unit ends. Whether that copy satisfies the subscription-only rule is for the owner. No API-key route exists in the kit. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling R8: records | The status line and the section "Changes since review 2" record rulings R1 to R7, the tasks rejected on 2026-11-13 (`1fd10ab4c3` in both forms, its reference failing `tests/test_run_lock.py` under load 3 of 3; `9a7547ed4c` and `9a7547ed4c-t0` with unstable anchors; `a8ffc5997a` earlier, for the leak audit), rehearsal 4 (stopped by its anchor check on `1fd10ab4c3`) and its rerun on the merged tree after the rejections (exit 0, decision `stop: no judge passed its gate` with 16 of 20 tasks missing by construction), and two text corrections (no `calibration/direct_sonnet.orc` exists; four programs, not five). Rehearsal 5 on the code with R1 to R5 (`426031e2`, stand-ins only, its own ledger, four calibration tasks, 54 minutes at load 56 to 100): exit 0; the smoke check passed on all nine checks; one usage limit injected into the ladder probe on T1 task `2aaf1ecc8e` cut its run, closed every start, was lifted, and after `resume-after-limit` the slot ran again and completed (redraw 21 of 40 Haiku calls, 0 incidents); the probe chose T3 and drew 20 tasks; a start of 12 calls whose worst case (USD 3) would pass the redraw ceiling of USD 3 (USD 0.0756 committed) was refused and wrote nothing; the priced totals equal the stand-in's known usage (smoke USD 0.1664, redraw 0.0756, calibration 0.876, none open, no missing usage); no anchor failure, every identity scan 0 hits; decision `stop: no judge passed its gate`, as with 16 of 20 tasks missing by construction; the check-withheld run completed in 2 calls. Spend to date: 0. |
| 2026-11-14 | Correction to the rows of 2026-11-12 (review 3 X4, records) | Kept as written; these hold. (1) T2 statements: the row "Pre-spend review of the builder and the integration" says they "are rebuilt as the commit message alone". The coordinator's ruling on review 2 M8 (commit `198736f0`) went the other way: a T2 statement is the short commit message plus the names of the files to change, a recorded deviation, because with the message alone every T2 statement falls under the 80-character floor and the rung disappears; T2 differs from T1 by the commits selected, not by the statement's form (`programs/README.md`, the readout's limits, Step 1b's table). (2) The smoke task: coordinator ruling 1 of 2026-11-12 moved the smoke to `194ad866a1`, the first T2 task that is not a probe task, when the leaking T3 task left the draw and the reserve took its place (Step 2 said "on the last reserve task"). (3) Recorded, the kit's behavior on review 2 minor 1: when every rung has 3 or 4 passes of 4 and some has 3, `ladder.table` answers "all too easy" (the extension), not "chosen", since the plan says 3 of 4 cannot be told from 4 of 4. (4) Recorded, the kit's behavior on review 2 minor 11: the hard extension bisects T0 and T1 (the row "bisection always for the extension"); if T0 is 0 of 4 it stops without probing T1 again, where the probe section says "runs it and T1 again". Neither (3) nor (4) has a coordinator ruling; either can be overruled before the freeze. Spend to date: 0. |
| 2026-11-14 | Correction to the row "Coordinator ruling R7" (review 3 X5) | Kept as written; it says each unit's copy of the subscription login file is "removed when the unit ends". It is removed when the unit ends normally, is refused or raises. A launcher killed with SIGKILL, or a host reboot, runs no clean-up, and the copy stays on `/home` (`<work>/.private-homes/<id>/.claude/.credentials.json` for a run, `<pool>/.private-homes/<id>/...` for a judge) until the next study command that starts, prepares or settles units, which begins by removing every copy no live unit holds and prints each path. The agent under test can read its unit's copy during its call (the sandbox runs it as the same user and keeps network access); a copy it makes under another name, or text it writes into its output or its patch (which the judges see and the results keep), is not removed. Whether this route is acceptable stays the owner's decision; fix round 1 adds nothing to it beyond the clean-up and the process guard. Spend to date: 0. |
| 2026-11-14 | Fix round 1 after review 3 (1 blocker, 5 majors, 11 minors; branch `feat/seed-set-prep`, `main` `e60b027f` merged first) | Blocker X1: a smoke with a unit cut by a usage limit, a planned program without its run, or a reserved unit not settled fails `smoke-check` (`no_unit_cut_by_a_usage_limit`, `every_reserved_unit_settled`), the cut run never sets the flat-or-bisect choice, and the smoke never runs a cut slot again. X2: usage-limit recognition fails closed (an error result with status 429 as a number or a string, an error result beside a rejected rate-limit event, or a provider error line in a limit wording no other named status explains, the wordings kept in one list in `units.py`); such a cut is flagged "unrecognised limit shape", and every pause refusal names the raw result to read before `resume-after-limit`; the model's and tools' own text is never read. X3: the runtime's `--max-cost-usd` is the unit's worst case times the table's highest tier over its ordinary rate for the model (5 for Haiku, 1 for Sonnet); `record-freeze` refuses a per-call worst case below that ratio times the criterion's `largest_call_usd` for the model, and a ceiling below two units in flight at the tranche's largest unit's worst case (correcting the R4 row's "must cover a call at Haiku's long-context rate, or a later call of a multi-call unit is refused"). X4: the correction row above. X5: a unit's whole process tree, its provider calls' own sessions and sandboxes included, dies with its launcher (`reaper.py`, the launch's guard; a kill -9 test with stand-ins), and every unit command starts by removing the copies no live unit holds; the R7 correction row above. X6: `settle` refuses a unit whose session still runs. Minors: the pause is written when the cut unit's process ends (1); one unit command at a time per study, a lock beside the ledger (2); a unit settled above its worst case is flagged and pauses starts (3); a call whose usage names no model counts at the worst case (4); the scan's `<synthetic>` exemption covers Claude assistant rows only (5); the freeze is checked before every unit, not once per command (6); a pool whose judges the caps cannot both hold, or whose first judge never settled, gets no judge and the command names it after judging the others (7); a re-run of a cut slot beyond the cap's room is left out with a message, and a probe step the redraw allowance cannot hold is a stop (8); `tiers.build` at statement-level complexity 12 (9; the radon-style count, with boolean operators and comprehensions, is not applied, and which count binds stays open); `resume-after-limit` refuses a meter at 100%, a truth value as a percentage, and, where no pause named a reset, a typed reset earlier than the limit (10); the runner's limits name a kill between reservation and launch as an incident priced at USD 0 (11). Not in this round: R6 stays unbuilt; whether re-runs may come from outside the caps is the owner's. Spend to date: 0. |
| 2026-11-14 | Fix round 1: the two rehearsals (stand-ins only, own ledgers, four calibration tasks) | A, the cut in the smoke (on `3810d77f`, 140 s; the same on `aa26ab5c`): the stand-in answered the smoke's Haiku `direct` call with the usage-limit shape; the run was cut and a `pause` closed starts (the next program's start was refused with the raw result named); after `resume-after-limit` the other four programs completed, the pool was judged by both judges and summarized, and `smoke-check` failed (`no_unit_cut_by_a_usage_limit` and `no_provider_errors` false, the rest true; `direct_median_wall_sec` none); then the probe and the calibration both refused ("no passed smoke") and the ledger holds no start after the smoke event (smoke 10 of 10 Haiku and 1 of 1 Sonnet candidate calls reserved, 8 and 1 made; judges 1 and 1; priced USD 0.1664; calibration and redraw 0). B, the cut in the probe (on `3810d77f`, 35 minutes at load about 40 to 60; the same on `22c2ea40`): exit 0; the smoke check passed; the probe's cut on T1 task `2aaf1ecc8e` (runs: cut, completed) paused at seq 19 and resumed at seq 22 with no start between; 0 incidents; redraw 21 of 40; the probe chose T3 and drew 20 tasks; the 12-call start against the redraw ceiling of USD 3 was refused and wrote nothing; priced smoke USD 0.1664, redraw 0.0756, calibration 0.876, none open, none missing or over its reservation; no anchor failure, every identity scan 0 hits; decision `stop: no judge passed its gate` with 16 of 20 tasks missing by construction; the check-withheld run completed in 2 calls. Its first attempt (B1, `aa26ab5c`) reached the same readout and ledger, then its separate check-withheld launch refused "no freeze in the ledger": the rehearsal never froze that launch's own ledger, which every start now checks (minor 6); fixed in `1e423fc5`. Found by the kit tests between the two: `spend.rows` read the ledger without a lock, so a unit reading it while the other unit in flight appended a long row could fail on a half-written line (two e2e tests did); the ledger is now read under a shared lock (`3810d77f`). Spend to date: 0. |
| 2026-11-14 | Fix round 2 after the re-review of fix round 1 (2 majors, 7 minors; branch `feat/seed-set-prep`, `main` `b7e2e2b5` merged first) | N1: the usage-limit wording, and the provider-error rule of incidents, read only a call that did not succeed (an error result, or no result event at all); a stdout line that starts with `{` and is not JSON (a stream event cut mid-write) is never read; every must-cut shape of the re-review stays cut. N2: the host-side checks of candidate code (`settle`'s visible check, the probe's hidden check, `summarize`'s hidden tests) run under the launch guard with a bound: 600 s for a patch's hidden set (five times the 120 s of Step 1's hidden run), 1,200 s for the visible check (dev-check.json's 600 s plus 600 s), 600 s per clone for a summary; a check past its bound is recorded as timed out, never as a pass or a zero (a probe run with one is an incident, a summary that times out makes its pool an incident, the readout counts timed-out visible checks apart). Assumption recorded for the coordinator: `summarize.py` gives each hidden test 1,800 s and counted a hanging one as failing; past the new per-clone bound such a hang now costs its pool, and a probe run with one is relaunched once. n1: a kill reaches a pid only while its start time matches the scan (a pidfd, then the start time). n2: the unit's command runs as its guard's child from its first instant; the guard is a child subreaper, so what a root shell that died leaves is killed when the command ends; a guard killed by the operator leaves the launcher to kill the command's session tree. n3: the pause and every refusal name the rule that fired and the line it read; an older CLI's `...\|<epoch>` gives the reset; `study.py not-a-limit UNIT --reason R` records, while the unit's usage-limit pause is open, that its raw result shows no limit: the unit becomes what the rules make it, the pause stops closing starts, and nothing runs again. n4: the cut-unit table gains `settle`'s session audit and the redraw's planned units, each checked by a test. n7: `spend.rows` parses after releasing its lock; 120 writers beside 16 readers all finish. Minor 9: the ten functions the re-review listed are at radon 12 or below (`tiers.build` 35 to 6, `rules.smoke_check` 28 to 11, `probing.recover` 16 to 12, the others 10 or below), split with no behaviour change, and no function is new above 12. The merge of `main` renamed two long-horizon fixtures the kit tests read; the tests follow. Not in this round: R6, re-runs outside the caps, the credential route. Spend to date: 0. |
| 2026-11-14 | Fix round 2: the two rehearsals (stand-ins only, own ledgers, four calibration tasks, on `76b967f3`) | A, the cut in the smoke (158 s at load about 55): exit 0; the smoke check failed on `no_unit_cut_by_a_usage_limit` and `no_provider_errors`, the other nine true; `direct` cut, the other four completed; the refusal named the unit, the reset, the rule that fired (the recorded answer) and its line, and `not-a-limit`; the probe and the calibration both refused ("no passed smoke") and no start follows the smoke event (smoke 10 of 10 Haiku and 1 of 1 Sonnet candidate calls reserved, 8 and 1 made; judges 1 and 1; priced USD 0.1664). B, the cut in the probe (40 minutes at load about 50 to 60): exit 0; the smoke check passed; the cut on T1 task `2aaf1ecc8e` (runs: cut, completed) paused at seq 19 and resumed at seq 22 with no start between; after the resume 19 calls that succeeded printed a limit warning on stderr and no pause followed; 0 incidents; redraw 21 of 40; the probe chose T3 and drew 20 tasks; the 12-call start against the redraw ceiling of USD 3 was refused and wrote nothing; priced smoke USD 0.1664, redraw 0.0756, calibration 0.876, none open, none missing or over its reservation; no anchor failure, every identity scan 0 hits; decision `stop: no judge passed its gate` with 16 of 20 tasks missing by construction; the check-withheld run completed in 2 calls. Spend to date: 0. |
| 2026-11-14 | Fix round 3 on the coordinator's rulings after fix round 2 (branch `feat/seed-set-prep`; rehearsal on `2e272c8e`) | Ruling 1: a hidden test that hangs is a failure of that test, not the loss of the pool. Each hidden test has 240 s (twice Step 1's 120 s for a whole hidden run), passed by the kit to `summarize.py` (`--hidden-test-timeout-sec`; the harness default of 1,800 s is unchanged) and to the probe's hidden check; the 600 s per clone (and 600 s per patch's hidden set, 1,200 s per visible check) stays as the backstop for a harness that itself hangs, and a summary past it is still an incident. This replaces fix round 2's assumption that such a hang costs its pool; past the backstop it still does (more than two hanging tests in a patch's hidden set, about two and a half per clone on average in a summary). Ruling 2: `not-a-limit` still refuses an unsettled unit; the pause's refusal and that refusal now say the way out (`settle` the run first; a probe run, which only `probe` settles and `probe` refuses while starts are closed: `resume-after-limit` after the reset, then `probe` settles it as a cut run). Ruling 3: the host checks' temporary directories are recorded with their maker (pid and start time) in `host-temp.jsonl` beside the ledger, the checks' own temporary directories go inside them (`TMPDIR`), and the sweep at the start of every command that takes the study lock removes the recorded ones whose maker and check no longer run and prints their paths (never a listing of `/tmp`; a record naming a directory the kit does not make refuses). Rehearsal (stand-ins only, own ledger, four calibration tasks, the cut in the probe; 2,636 s, beside the kit tests): exit 0; the stand-in Sonnet's code on the first calibration task `12ea8483f0` made one hidden test hang 300 s in host-side checks; it hung twice (the first and the retest pool), each time counted as that test failing, both pools were summarised with only that test failed on the Sonnet clone, and no hanging process was left; the rest as fix round 2's rehearsal B (smoke check passed; the cut on `2aaf1ecc8e` paused and resumed at seq 22, its runs cut then completed; 19 warned calls and no pause after the resume; 0 incidents; the 12-call start against the redraw ceiling refused with the ledger unchanged; priced smoke USD 0.1664, redraw 0.0756, calibration 0.876, none open, missing or over its reservation; no anchor failure, every identity scan 0 hits; decision `stop: no judge passed its gate; hidden-test pass rate is primary; stop for the owner` with 16 of 20 tasks missing by construction; the check-withheld run completed in 2 calls). Spend to date: 0. |
| 2026-11-14 | Fix round 4 on the final scoped check (1 blocker, 2 majors, 3 minors; branch `feat/seed-set-prep`, `main` `27a5b30b` merged after the fixes) | B1: the temporary-directory sweep acts on a recorded directory only when it is a direct child of the temp directory with a kit prefix and its real path is the recorded one, and runs `chmod` only after that check; any other record line is named on stderr, skipped and kept, and no longer stops a locked command. M1: paid extra usage (a `rate_limit_event` with overage in use, or a rejected limit with overage allowed; the long-horizon kit's rule read from the stream) closes every start under its own rule, "paid extra usage", until `resume-after-limit`; by the coordinator's follow-up rulings, a call that ended normally stays an observation (a candidate's result is used and its slot does not run again; a judge's judgment is kept and its pool is not rebuilt) and one that did not is cut like any limit; either is priced at its metered tokens. The pause of the recorded answer or of paid extra usage names `resume-after-limit` only, not `not-a-limit`. M2: a hidden set's backstop is 600 s plus 240 s per hidden test, summed over the clones whose hidden tests run for a summary, so hanging hidden tests fail at their own bound instead of timing the check out. n9: a session file whose recorded start time is not its live leader's reads as dead. n10: `not-a-limit` refuses a pause by the recorded answer or by paid extra usage. A guard killed before it wrote its session file gives a status saying so, and an empty file reads as no session. After the independent check of round 4, the sweep also skips, names and keeps a line naming a file or one it cannot read and gives a kit directory mode 700 before reading it, a unit with paid extra usage on any call is paused under that rule (so `not-a-limit` refuses it), overage flags are read case-insensitively, and the reset is the last rejected event's that names one. Kit tests 664 passed, compare-harness tests 558 passed (stand-ins only). The owner's check that paid extra usage is off on the account stays owed before the first call. Spend to date: 0. |
| 2026-11-15 | The kit is on `main` (`09068ec8`, merge of `feat/seed-set-prep` at `f4ceafaa`) | After the independent check of fix round 4 ("ready after fixes": the six earlier findings closed, 72 of 73 recorded streams classify as before and the one that differs is the intended paid-usage change) and its six small items (a record line naming a regular file or an unreadable line is named, skipped and kept; a pause names a unit's paid-usage call so only `resume-after-limit` reopens it; overage flags given as strings are read; the reset comes from the last rejected event that names one), which the coordinator checked by reading the diff. Kit tests 664 passed. Full suite on the merge: 23,768 passed, 6 failed (the four nanoBragg tests of the standing baseline; two load failures that pass alone). No provider call was made; spend 0. **Still owed before the first paid call, in order:** the owner's decisions (the credential route of ruling R7; that paid extra usage is off; the allowance hours and shares and the meter-reading protocol; whether a cut slot may run again outside the caps); the freeze on the merged commit (runtime worktree, the anchors' stability run, `judge-calibration.json` and `judge-seeds.json`, the price table re-read, `criterion.json` with its `spend` and `sha256` blocks, `record-freeze`, the hashes in this ledger); the 20-task rehearsal on the frozen code at low load; the tranche's spend row; then the smoke. |
| 2026-11-15 | Anchors re-checked under the current scoring path (`feat/seed-set-anchors` `c8b2f587`; zero spend) | The record of 2026-11-13 predated the scoring-path changes of 2026-11-14 (guarded host checks; the checks' own temporary directory, `b18da922`), and one of them changes a test outcome, so all 110 packages the study can draw, probe or smoke on were re-run by name: 61 minutes at load 10 to 16, no errored repetition, every one stable with the outcomes of 2026-11-13. `tiers verify`: 118 packages of 67 tasks verified, anchors stable. The four unstable entries are the two tasks already rejected: `1fd10ab4c3` (load: stable 3 of 3 at load 13) and `9a7547ed4c` (the reference fails `test_subreaper_controller_reaps_only_its_exact_owned_server` 3 of 3 with `socket path too long`: under `TMPDIR=/tmp/seed-set-host-XXXXXXXX/tmp` the test's tmux socket path is 104 bytes against a limit of 103; under `/tmp` it was 77). Usable packages are unchanged: T0 9, T1 11, T2 11, T3 19, T4 6, T5 5. **Ruling: `9a7547ed4c` stays rejected and the kit's temporary path is not shortened** — the usable set passes under the path as it is, T0 and T1 are above their floor without the task, and a shorter path is a kit change that needs its own tests, review and a third anchors run — if wrong, the study has one task fewer in T0 and T1, and a later package whose tests build a longer socket path is rejected at its anchors check instead of used. **Ruling: an anchors record holds only for the scoring path it was measured under** — this run showed a kit change can flip a reference's outcome while the package hash stays the same — so the freeze runs the anchors on the frozen runtime commit, and binding the record to the scoring path in code is owed before the freeze — if wrong, an hour of machine time per freeze. |
| 2026-11-17 | The owner's answers to the open decisions; coordinator rulings R9 and R10 | **Paid extra usage is off for the account:** "yes". **The credential route:** "whatever easier". **Ruling R9: the route as built stays** (ruling R7: each unit's private home gets a copy of the subscription login file, removed as the correction row of 2026-11-14 says) — it is built, reviewed and rehearsed, and the host-side passthrough would be a kit change with its own tests, review and rehearsal — if wrong, the price is the one that correction row names: the agent under test can read its unit's copy during its call. **Whether a cut slot may run again outside the caps:** "you decide". **Ruling R10: no** — a cut slot runs again only inside its cap, as ruling R1 built it; the authorised call counts of `AGENTS.md` stay the bound — if wrong, a usage limit in a tranche with no room (the smoke, the calibration's Sonnet candidates, both judges' calibration caps) loses that observation, and a calibration left short of its 20 tasks stops with no quality claim. **The allowance:** "30 percent weekly". Not settled, and asked again: whether that is the share kept free or the share the study may use, the five-hour share, the hours, and a meter reading before the first call. Still owed before the first paid call, in order: the allowance, the freeze on the merged commit, the 20-task rehearsal, the tranche's spend row, the smoke. Spend to date: 0. |
| 2026-11-17 | The task builder's oracle could read the base run's bytecode on the fix side (debug_code, then fixed by the coordinator as `cb818f0d`; zero spend) | **Found** because `tests/experiments/test_seed_set_build_tasks.py` failed on `main` in every whole-module run (`visible check fails on the fix (run 1)`). **Cause:** since `31c5c8e5` (2026-11-12) `sandboxed()` keeps bytecode under `PYTHONPYCACHEPREFIX=<box>/pycache` instead of setting `PYTHONDONTWRITEBYTECODE`. `oracle()` runs the base side and then the fix side in one clone; Python accepts cached bytecode when the source's size and its mtime in whole seconds match, so a fix of the same byte size applied within the base run's second ran as the base's code. Shown by trace (the fixed source on disk, `add(2, 3) == -1` from the cached file), by onset (6 of 6 module runs pass at `31c5c8e5^`, 6 of 6 fail at `31c5c8e5`) and by a deterministic test. **Reach:** `oracle()` is the only place that runs Python in a tree and then rewrites that tree's sources in place. Every scoring path (`pool.add_clone`, `summarize.hidden_failures`, `anchors.score`, `host._hidden`, `evaluation.check_first_attempt`, `prepare.apply_patch`) builds a fresh tree before any interpreter starts, and the check-withheld form uses a new prefix per call. On recorded real tasks the base side took at least 3.5 s between checkout and the fix (69 rows of `ladder_screening.jsonl`, 30 of `screening.jsonl`), so the same-second condition cannot hold; the fault can only reject a task, never admit one, and no recorded rejection has its pattern. **The anchors and recorded screening results stand.** Not exercised: an agent's own visible check in its working tree during a real launch (it could read stale bytecode after a same-size, same-second edit; that affects the agent's feedback, not its score, which is rebuilt from the recorded patch). **Fix:** after the fix-side `git apply`, `oracle()` removes the clone's directory under the bytecode prefix. A test that stamps the fixed file into the base run's second fails without it. Checks: the module 20 passed in 5 of 5 runs; the 12 seed-set modules, 566 passed. This precedes the freeze, which binds the merged commit. |
| 2026-11-17 | The anchors record is bound to its scoring path in code (`feat/seed-set-anchor-binding`, reviewed, fixed on `feat/seed-set-freeze-prep`, merged as `978ae954`; zero spend) | What the row of 2026-11-15 said was owed before the freeze. Each entry of `anchor_stability.json` carries `scoring_path`; `tiers verify`, `record-freeze` and every start refuse a package without a stable entry at its hash and the current scoring path, naming it "not measured", "other scoring path" or "unstable"; `reject-unstable` rejects only on an entry unstable under the current path. **Independent review: merge as is**, with one major and five minors; four applied, two declined. **Applied.** (M1) The hash also covers `sys.version` and the installed pytest's version, so an update of either makes every entry "other scoring path" and refuses a start. (m4) The anchors score each hidden test under the study's `host.HIDDEN_TEST_SEC` (240 s), not 1,800 s. (m3) The freeze and each start compute the hash from the runtime's files, not the checkout's. (m2) A test asserts that every `experiments` module scoring loads is among the hashed files. (m5) The refusal names `--work` and says that another scoring path after a kit commit or a Python or pytest update calls for a new freeze, not the anchors run alone. The README lists what stays unbound: the environment variables `host.guarded` passes through, the git binary and its configuration, the other site-packages, the no-provider stubs. **Declined:** narrowing the hash to the 12 modules scoring loads (over-inclusion costs an hour per kit change, not correctness), and the slow exit of a stopped anchors run. Checks: the seed-set modules, 595 passed; the whole suite on the branch tip, 71 failed, all of them the launch context (67, which pass rerun directly: 263 passed) or the nanoBragg sibling path (4). **A first freeze attempt the same day, on `e85ea6fb`, is superseded:** the coordinator started it before this branch was merged; its anchors run (110 stable, 51 minutes) and drafts are not the record. The README no longer lists `judge-seeds.json` at the freeze: it names the judge the calibration selects and is written after it. |
| 2026-11-17 | The freeze is recorded on `592ed731`; coordinator ruling R11 sets the priced ceilings (run_experiment; zero spend) | **Runtime** `/home/ollie/seedset-rt`, detached at `592ed731` (`978ae954` plus the anchors record; `main` fast-forwarded to it). Scoring path `aed8b26a…` (Python 3.13.9, pytest 8.4.1). **Anchors** run from the runtime on all 110 drawable, probe and smoke packages by name, hidden tests bounded at 240 s: 50 minutes (2026-11-18T00:51Z to 01:41Z), load 5.3 to 11.7, no errored repetition, every package stable, per-anchor outcomes identical to the record of 2026-11-15; record sha256 `4df49436…`. `tiers verify`: 118 packages of 67 tasks, anchors stable. **Files:** `judge-calibration.json` `15748aea…` (both judges, the functional rubric, no calibration block); `criterion.json` `ce1289a9…`; `tasks.jsonl` `c5793e1b…`; price table `77a237c6…`; programs `common.orc` `d8c46f53…`, `direct.orc` `acfc8ba5…`, `implement_check_repair.orc` `ef8f286c…`, `implement_review_revise.orc` `547754ad…`, `retry_until_check.orc` `c7592336…`; code trees `experiments/seed_set` `ce9516f4…`, `experiments/compare` `2aaa787d…`. The two criterion files are untracked in the runtime, as the kit expects, and kept by the same bytes in `c0774047` on `feat/seed-set-freeze-2`. **`record-freeze` exit 0:** freeze event seq 1 in `~/.local/state/seed-set/spend-ledger.jsonl` (sha256 `b0e45c90…`). **Ruling R11, the `spend` block.** Per-call worst case: `claude-haiku-5-5` USD 0.50, `claude-sonnet-5-5` USD 2.00. Largest ordinary-rate call expected: Haiku USD 0.10 (the largest recorded Haiku call of this repository's sessions is about USD 0.06, PQ-1c), Sonnet USD 2.00 (no Sonnet call is recorded; twenty times Haiku's figure, the price ratio). Ceilings: smoke USD 10, calibration USD 60, redraw USD 8; USD 78 in all, inside the budget delegation. Caps of calls are the kit's (`spend.CAPS`: 121 Haiku and 52 Sonnet for the smoke and calibration; the redraw 40 Haiku candidates). The smoke's ceiling covers every one of its calls at the worst case (USD 9.50). The calibration's and the redraw's do not (USD 155 and USD 20 at the worst case): they are set at about twice what earlier sessions suggest, so a tranche whose calls price near the worst case stops at its ceiling before its call cap — if wrong, the calibration stops short of its 20 tasks and reports no quality claim, and a higher ceiling needs a new row before more spend. Both per-call figures sit on their bound, so a larger `largest_call_usd` after the smoke means raising the per-call figure and recording the freeze again. **Price table read again:** the vendor page of 2026-11-17 gives the table's figures (Haiku 0.10 / 0.50, cache read 0.01, five times those above 100,000 prompt tokens; Sonnet 2 / 10, cache read 0.10, no tier). The table holds one cache-write rate per model, the one-hour rate (0.20 and 4); a five-minute write (0.125 and 2.50 on the page) is priced at the higher rate, and a call is settled at the larger of the table's price and the CLI's reported cost. **CLI pin:** `/home/ollie/.local/share/claude/versions/2.1.327`, `2.1.327 (Claude Code)`. The CLI updated itself twice in two days (2.1.326 on 2026-11-16, 2.1.327 on 2026-11-17); another update before the first start means renewing the pin and recording the freeze again, which needs no reason while no start exists. A paid start must not have the no-provider stubs first on `PATH`, or the unit declares the stub and the pin check refuses. **Still owed before the first paid call, in order:** the allowance (owner), the 20-task rehearsal on the frozen code at low load, the tranche's spend row, the smoke. The owner's weekly limit stood at 98% on 2026-11-17 and resets on 2026-11-21 at 09:00 PST (long-horizon plan's ledger), so no paid call can start before then. Spend to date: 0. |
| 2026-11-17 | The 20-task rehearsal on the frozen code passed its mechanics; coordinator ruling R12 takes it as the owed rehearsal (run_experiment; stand-ins only, own ledger; zero spend) | On `592ed731`, run from `/home/ollie/seedset-rt` with `/home/ollie/miniconda3/bin/python` (3.13.9, pytest 8.4.1), `--calibration-tasks 20`, the cut in the probe; 5,769 s (17:47 to 19:24 PST), exit 0. **Mechanics:** the smoke check passed (11 of 11). The usage limit cut T1 task `2aaf1ecc8e` (runs: cut, completed), closed starts at seq 19 and resumed at seq 22; 19 calls that succeeded after the resume printed a limit warning and no pause followed; 0 incidents. The probe chose T3 and drew 20 tasks (T2 1, T3 19). A 12-call start against the rehearsal's redraw ceiling of USD 3 was refused with the ledger unchanged; one Haiku judge call beyond the calibration cap was refused. The injected hidden-test hang on `12ea8483f0` hung in both pools and counted each time as that one test failing on the Sonnet clone; no process was left. **Calls made against caps:** smoke Haiku 8 of 10, Sonnet 1 of 1, judges 1 and 1; redraw 21 of 40; calibration Haiku 75 of 80 (5 probe runs on chosen tasks count toward the 80), Sonnet 20 of 20, judges 30 of 30 each. Priced USD 0.1664, 0.0756 and 3.728, equal to the stand-in's known usage; none open, missing or over its reservation. No anchor failure; 31 identity scans, 0 hits. The check-withheld run completed in 2 calls. **Gates:** both judges passed V1 to V4 (V1 20 of 20, reference 8 and base 0; V2 20 of 20; V3 mean difference 0 over 70 clones; V4 0.9865 over 63 hidden-passing and 37 hidden-failing candidates); Haiku was selected; G2 (4.4), G3 (3.6) and G4 passed; G1 failed with 0 survivors of the 12 needed. Decision `stop: a gate fails and the ladder probe was the one redraw; no quality claim`. The gate figures were recomputed read-only by the operator with `gates.calibration`, since a stopped readout keeps only pass or fail. **What the stop means:** nothing about the real study. The stand-in fixes a task on its first call or never, and its judge gives 8 to any changed clone and 0 otherwise, so each task's Haiku mean is 0 or 8 and none falls in the survivor band of 2 to 6.5; the judge gate's pass is as automatic. **Load:** the plan asked for low load; it was 8.9 at the start and 6.4 at the end, and other sessions' jobs pushed the 1-minute figure to 189 in between. No hidden test timed out apart from the injected one and no run became an incident. **Ruling R12:** this run is the owed 20-task rehearsal. The load was higher than asked, which tests the time limits harder, not less; a rerun at low load would show less. If wrong: a rerun is about 1 h 40 min, costs nothing and needs no new freeze. **Not shown by any rehearsal:** the path on which every gate passes (the stand-in cannot reach it, and the four-task rehearsals stopped at the judge gate). That path ends in a report to the owner and starts no call, so it is left to the gates' unit tests. **Checked by the coordinator afterwards:** the real ledger unchanged (sha256 `b0e45c90…`, 1 row); the runtime at `592ed731` with only its two untracked criterion files; no guard-stub log; the rehearsal's root and host temporary directories removed. "No real provider CLI started" rests on the closed `PATH`, the empty home, the pinned stand-in and the empty guard logs, not on a process audit. The run left five gitignored bytecode files in the runtime (outside the scoring path, which hashes `*.py`). **Kept:** `~/lh-cache/logs/seedset-rehearsal-2026-11-17/` (`rehearsal.json` sha256 `3d74377a…`, `sr20.log` `5e13f7d4…`, the operator's `readout.md` and `gate-figures.json`). **Still owed before the first paid call, in order:** the allowance (owner), the tranche's spend row, the smoke; none before the weekly reset of 2026-11-21 09:00 PST. Spend to date: 0. |
| 2026-11-17 | The owner's answer on the allowance | Asked whether "30 percent weekly" is the share experiments may use or the share kept free, the owner answered at about 22:10 PST: "share experimnets may use". So experiments may take up to 30% of the weekly limit. The same evening: "dont hold it. need to burn 10% of my weekly limit between now and 9 am" (said of the development work the coordinator was holding back to spare the limit; that work was started). **Not settled by this:** the five-hour share, the hours and the meter-reading protocol, and the state of the meter itself: the vendor's headers of 01:00 that day gave the weekly limit as 98% used with its reset on 2026-11-21 09:00 PST, which leaves 2%, not 10%. The coordinator asked the owner for both meters' readings; no paid call starts before a reading is recorded here, because a unit cut by a usage limit fails the smoke and a smoke slot is never run again. Spend to date: 0. |
| 2026-11-17 | Smoke tranche approved; the owner's meter reading; coordinator ruling R13 (the allowance's remaining terms) | **The owner's meter, pasted at about 22:15 PST** (the Claude Code usage screen): current session (five-hour) 69% used, resets 23:49; current week, all models, 56% used, resets 2026-11-18 08:59; current week, Fable, 72% used, same reset; usage credits off. This replaces the figure in the row above: the 98% and the reset of 2026-11-21 came from the vendor's headers on the long-horizon probe's token and describe another meter than the one the owner sees (not explained; it matters to the long-horizon ladder, not to this study, whose units use the owner's login). **Ruling R13, the allowance.** (1) Share: experiments may use 30% of the weekly limit (owner). It is applied to the owner's all-models weekly meter: no tranche starts when that meter reads 30 points or more above the week's first reading before an experiment call (56% for the week ending 2026-11-18 08:59, so 86%). The meter counts every session of the owner, so this stops early, never late. (2) Five-hour: no tranche starts with the five-hour meter above 50% used; a tranche in flight is paused only by the vendor's limit answer, as the kit does. (3) Hours: any hour (owner, 2026-11-17: unattended runs are allowed; "need to burn 10% of my weekly limit between now and 9 am"). (4) Reading: the usage screen, read by the owner, or by the coordinator in a terminal pane of the owner's CLI with no prompt sent, recorded in this ledger with its time before a tranche's first start and at every `resume-after-limit`. If wrong: the share or the threshold is changed by a new row; nothing in the freeze depends on them. **Smoke tranche approved** under the budget delegation: on the frozen runtime `/home/ollie/seedset-rt` at `592ed731` (criterion sha256 `ce1289a9…`, CLI 2.1.327), task `194ad866a1`, the planned arms once each, then one pool scored by both judges and `smoke-check`. Caps: 10 `claude-haiku-5-5` and 1 `claude-sonnet-5-5` candidate calls, 1 judge call on each model (13 calls); priced ceiling USD 10; worst case per call USD 0.50 on Haiku and USD 2.00 on Sonnet (ruling R11). No retry: a unit cut by a usage limit is not run again and fails the check. **First start not before 23:52 PST,** after the five-hour reset, because the meter is above the threshold of (2) until then and a cut would fail the smoke for good. At a limit: starts close (the kit's pause), the operator stops and reports, and the cut unit is counted as cut, never as an observation. A CLI update before the first start means recording the freeze again first. Run by an operator subagent under this row; it starts nothing else. The probe and the calibration get their own row after the smoke's result is read. Spend to date: 0. |
| 2026-11-18 | The smoke's first start was refused before any call; started again under the same approval (no spend by the refusal) | **What happened.** The operator's script opened its gate at 23:52:19 PST on 2026-11-17, passed its checks (CLI pin, runtime HEAD, ledger `b0e45c90…` with 1 row) and ran `study.py candidates --tranche smoke --arm direct 194ad866a1`. It ended at 23:52:20 with `ValueError: the default public catalog requires Codex 0.163.0; declare reviewed dependencies` from the harness's `sandbox.dependencies`, called while the unit was being prepared: the owner's login `PATH` holds Codex 0.167.2, and the harness refuses any Codex other than the one its catalog names. The refusal came before the reservation: the ledger is unchanged (1 row, the same hash), no unit exists, no provider process started. The script stopped at that exit. The coordinating session then ended for an unrelated reason and the operator with it; the coordinator picked the run up at 01:40. **Why the rehearsal did not show it:** the rehearsal's `PATH` held the stand-in `codex` and no real one. **Remedy, no code change:** the study calls no Codex, so the start runs with `PATH=/home/ollie/miniconda3/bin:/home/ollie/.local/bin:/usr/bin:/bin`, on which no `codex` is found; `sandbox.dependencies` then returns `codex: null`, `claude` as the pinned 2.1.327 and the unit path `/usr/bin`, `/home/ollie/miniconda3/bin`, `/usr/bin`, `/bin`, the same as in the rehearsal (checked dry, no start). `PATH` is not bound by the freeze, so the freeze stands. The refused start left one prepared clone and an `inputs.json` under `~/seedset-work` (no private home, no credential copy); the coordinator removed them so the work root is as the rehearsal began. **This is not a second smoke:** no slot was reserved or run; every cap of the approval row is untouched. **Meter, read by the coordinator at 01:50 PST** (the usage screen in a pane of the owner's CLI, no prompt sent): five-hour 13% used, resets 04:49; week, all models, 66% used, resets 08:59; week, Fable, 85%. The weekly meter rose 10 points since 22:15 with no experiment call (development agents and the coordinator); the 86% bound of ruling R13 leaves 20 points. Run by the coordinator from the operator's script with the `PATH` changed and the wait removed (`~/lh-cache/logs/seedset-smoke-2026-11-17/run-smoke-2.sh`, log `run2.log`). Spend to date: 0. |
| 2026-11-18 | The smoke stopped after its first run: a stop for the owner (run_experiment; 1 `claude-haiku-5-5` candidate call, priced USD 0.0323) | **The run.** Started by the coordinator at 01:42:34 PST (the meter reading of the row above was taken at about 01:41, not 01:50). `candidates --tranche smoke --arm direct 194ad866a1` reserved one Haiku call (USD 0.50 worst case), ran the pinned CLI 2.1.327 for 8 min 20 s (one session of 28 turns, `completed`, then two one-turn continuations woken by the session's own background test run), settled at USD 0.032298 with no usage missing, and exited 0. **The stop.** The session audit classed the run as an incident: "sessions outside the unit tree's store", naming `.jsonl` files under the unit's private home in `.cache/claude-cli-nodejs/<project>/mcp-logs-claude-ai-Claude-Docs/`, `-Google-Drive/` and `-Google-Slides/`. One incident is over 10% of the smoke's planned runs, so the kit wrote a `stop` event (ledger seq 4) and the script ended; no other arm, pool or judge started. The plan's stop rule applies: a smoke failure is a stop for the owner. **What the incident shows (more than a false alarm).** With the owner's login in the unit (the credential route of rulings R7 and R9), the CLI connected the account's claude.ai connectors inside the candidate's session: Claude Docs, Google Slides and Google Drive, 26 tools, among them Drive's create, update, share and trash. The session's permission mode lets it call any tool unasked. **It called none of them:** its tool calls were Bash 19, Monitor 3, Edit 2, Write 1, ToolSearch 1 (to load TaskStop) and TaskStop 1. The rehearsals could not show this: a stand-in CLI has no account. Whether the earlier paid runs through this harness (PQ-1c, 16 calls on 2026-11-12; none in this study) had the connectors too is not checked. **Also seen, not yet judged:** the scan printed "other sessions' files" on the three init events, whose `memory_paths` name a `.claude/projects/…/memory/` directory, so every real run may carry that hit; the run's stream holds three init and three result events. **State.** Ledger 4 rows (freeze, the reservation, the settle, the stop), sha256 `69c49282…`; no credential copy is left in the unit's home; the runtime is unchanged at `592ed731`; the work root `~/seedset-work` is kept; records copied to `~/lh-cache/logs/seedset-smoke-2026-11-17/run-1/`, log `run2.log`. **Needed before any further call:** a kit change that keeps the account's connectors (and any other account-supplied tool) out of candidate and judge sessions, checked against the real CLI without a model call; a decision on the scan hit; a new freeze; and the owner's word on a second smoke, since the first is spent and the plan allows none (its Haiku cap of 10 has 1 used). Nothing further runs under the approval row above. Spend to date: 1 call, USD 0.0323. |
| 2026-11-23 | The owner approves a second smoke | Asked "May I run a second seed-set smoke once the isolation fix is reviewed and merged, the anchors re-run and the freeze recorded again with the CLI pinned to 2.1.330?" (about 13 calls, smoke ceiling USD 10), the owner answered "yes" on 2026-11-23. **Conditions carried by the approval:** the revision `522cbd18` on `feat/seed-set-real-cli` passes an independent re-check and the whole suite, and is merged; the anchors are re-run on the merged code; the freeze is recorded again with `spend.cli` renewed to 2.1.330; a new spend row and a fresh meter reading (R13) precede the first call. The second smoke runs under the same tranche caps and counts against the plan's authorized calls with the first smoke's 1 Haiku call (USD 0.0323). Its run is not a retry of the stopped slot: the stopped `direct` run stays recorded as an incident. |
| 2026-11-23 | The isolation fix on `main`; ruling R14; the freeze recorded again on `219ee75b` with the CLI pin 2.1.331 (impl_code, independent review twice, coordinator fixes and integration; zero spend) | **The fix** (`feat/seed-set-real-cli`: `1d456f93`, `522cbd18`, coordinator's `67ed8032`): every Claude launch of a unit mounts `sandbox.CLAUDE_SETTINGS` from a pipe as the sandbox's managed settings (`/etc/claude-code/managed-settings.json`, read-only, above every user, project, local and `--settings` value): no claude.ai connectors, synced skills or plugins, managed MCP servers only, MCP resource, Artifact, agent, messaging and wake-up tools denied, auto memory, Artifacts and scheduled tasks off, and `CLAUDE_ENV` (connectors, background tasks, auto memory, cron off) both as the process environment and as the managed `env`, so a session's own `~/.claude/settings.json` cannot undo them for the next call of a multi-call arm. `units.isolation_breach` reads every init event against `sandbox.CLAUDE_TOOLS`, the 13 tools of a clean session (an allowlist); any other tool, any MCP server, an account skill or a non-builtin plugin is an incident. The scan drops only the CLI's own paths from init events. **Evidence, zero spend** (sandbox network namespace unshared, checked by a probe that could neither resolve nor connect, the session killed at its first event; the unit's credential copy removed by `forget_credentials`): CLI 2.1.330 on 2026-11-22 and 2.1.331 on 2026-11-23 list exactly the 13 tools, no MCP server, no account skill, built-in plugins only; a CLI the agent starts itself inside the sandbox lists no claude.ai connector under the managed settings, and three without them. **Reviews:** the first independent review (ready after fixes) led to the managed-settings delivery, the allowlist, the documented limit and the scan change (rulings 1 to 6 of 2026-11-18); its re-check found one should-fix (background tasks could be turned on again through the session's own settings `env`, the first smoke's continuation pattern) and four nits, all applied by the coordinator. Seed-set and harness tests 1,170 passed; whole suite on the branch: only the known launch artefacts (71, all in the four modules and nanoBragg tests named in earlier rows; 263 of 263 pass serially). `main` fast-forwarded to `604c074a`. **Anchors** from the runtime at `604c074a`: all 110 drawable, probe and smoke packages stable, 50 minutes (13:47 to 14:36 PST), load 3 to 16, per-repetition outcomes identical to the record of 2026-11-17; scoring path `876101bb…`; record `5af2ced3…`, committed as `219ee75b` (`main` fast-forwarded). `tiers verify`: 118 packages of 67 tasks, anchors stable. **Price table read again:** the vendor page on 2026-11-23 gives the table's figures (Haiku 0.10 / 0.50, cache read 0.01, five times above 100,000 prompt tokens; Sonnet 2 / 10, cache read 0.10). **CLI pin:** the installed CLI updated itself to 2.1.331 on 2026-11-23 13:35. The pin is the version file `/home/ollie/.local/share/claude/versions/2.1.331`, reached through `~/seedset-pin/bin/claude` first on the operator's `PATH`, so a later self-update of `~/.local/bin/claude` does not move it; the version files are kept by the installer (2.1.327 to 2.1.331 present). `criterion.json` changed only in `spend.cli`; its other hashes and `judge-calibration.json` are unchanged; both files are kept by the same bytes in `019e54c9` on `feat/seed-set-freeze-3`. **Ruling R14 (coordinator):** a stop in the spend ledger is final (`spend.refuse_closed`), and the smoke cap already counted the stopped smoke's call. The owner's approval of a second smoke is carried out by archiving, not by a code path that lifts stops: the ledger moved to `~/.local/state/seed-set/spend-ledger-smoke1-20261118.jsonl` (read-only, sha256 `69c49282…`, 4 rows) and the work root to `~/seedset-work-smoke1-20261118` (no credential copy in it); the new freeze starts a fresh ledger. The first smoke's 1 Haiku call (USD 0.0323) stays counted in this plan: with the second smoke, at most 122 Haiku calls are made under the study's approvals, one above the 121 of the original authorization, inside the owner's approval of a second smoke of about 13 calls. If wrong: an archived ledger is outside the guard's view, so the plan's ledger, not the guard, carries the first smoke's spend. **`record-freeze` exit 0:** freeze event seq 1 in the fresh ledger (sha256 `41864831…`), runtime `219ee75b`, criterion `b0115c65…`. |
| 2026-11-23 | Spend row: the second smoke (run_experiment, under the owner's approval of 2026-11-23) | **Tranche** `smoke` on task `194ad866a1`, the five arms in the first smoke's order, then pool, judge, summarize and smoke-check, from the runtime at `219ee75b`, through `~/lh-cache/logs/seedset-smoke2-2026-11-23/run-smoke.sh` (pin, HEAD and ledger checks; stops at the first non-zero exit, pause or stop). **Caps:** the kit's smoke caps, 10 `claude-haiku-5-5` and 1 `claude-sonnet-5-5` candidate calls, 1 judge call each: 13 calls; priced ceiling USD 10, per-call worst case Haiku USD 0.50 and Sonnet USD 2.00 (ruling R11). **Meter** (R13, read by the coordinator at 14:39 PST in a CLI pane with no prompt sent): week, all models, 38%, resets 2026-11-27 14:00 PST; Fable week 70%; no five-hour meter shown (no window open); usage credits off. This is the week's first reading, so no tranche starts once the weekly meter reads 68% or more. Spend before this row: USD 0.0323 (the first smoke). |
| 2026-11-23 | The second smoke's five runs; its pool ended as an incident on unadjudicated scan hits, before any judge call (run_experiment; 6 candidate calls, priced USD 0.7741; operator error; open) | **Runs** (14:49 to 15:19 PST, runtime `219ee75b`, CLI 2.1.331): `direct` Haiku `failed` (provider timeout at 1,200 s while the session ran broad test sweeps; 1 call settled at its worst case USD 0.50 because a cut call has no final usage), `direct_sonnet` `completed` (1 call, USD 0.1837), `retry_until_check` `completed` (1 of 3 calls, USD 0.0314), `implement_check_repair` `completed` (1 of 3, USD 0.0257), `implement_review_revise` `completed` (2 of 3, USD 0.0333). Every unit one session per call, metering complete, no incident, no isolation breach, no pause. Calls: Haiku 5 of 10, Sonnet 1 of 1; judges 0 of 2. **What stopped it:** `implement_review_revise` had 2 scan hits; the kit pools only runs with a verdict, and the operator's script (copied from the first smoke's) had no adjudication step between the candidates and `pool`. `pool` recorded `POOL INCIDENT 194ad866a1/first: not pooled: 2 scan hits and no verdict` (exit 0), `judge` found no pool (exit 0, no call), `summarize` refused the incident's directory (exit 1), and the script stopped. A pool ended as an incident is never built again (`pool_to_build`), so `smoke-check` would fail on `clone_count` and the pool checks; it has not been run. **Verdict recorded after** (coordinator, `prepare.py scan --verdict cleared`): both hits are scanner false positives: (1) `main checkout prefix` matched text of a plan document of the task's own repository that the agent read with a relative `cat` inside its clone; (2) `other sessions' files` matched the CLI's persisted-output file in the unit's own home, in the project folder of the unit's own tree. **Two findings for the apparatus:** the scanner flags the repository's own documents that name the main checkout path (many do), and flags the unit's own session project under its own home; and the operator sequence needs a stop for adjudication after any run with hits, before `pool`. **Open (owner):** finish this smoke by removing the pool's incident record (an operator-sequence artefact, no judge reserved) and running `pool`, `judge` (2 calls), `summarize` and `smoke-check`; or record the smoke as failed, with a third smoke after the scanner fix. Spend so far, both smokes: USD 0.8064 priced. |
| 2026-11-23 | The owner: finish this smoke; the pool's incident record archived (no spend by this row) | Asked whether to finish the second smoke by removing the pool's incident record (caused by the operator script's missing adjudication step; no judge reserved) or to record it failed and run a third smoke, the owner chose "Finish this smoke (Recommended)". The incident directory `experiments/seed_set/results/pools/194ad866a1-first` (its `incident.json`: not pooled, 2 scan hits and no verdict) is moved, not deleted, to `~/lh-cache/logs/seedset-smoke2-2026-11-23/pool-incident-archived/`. The smoke then continues on the unchanged frozen runtime `219ee75b` with `pool`, `judge` (2 calls, inside the smoke caps), `summarize` and `smoke-check`, from `finish-smoke.sh` in the same folder. The scanner fix and the pool guard (`a81c7bad`, `87654d13`, in review) are apparatus fixes recorded at the next freeze, before calibration, with the anchors re-run. |
| 2026-11-23 | The second smoke failed its check: judges ran, the pool could not be summarized (run_experiment; 2 judge calls; smoke total 8 calls, priced USD 0.9902; a stop for the owner, answered in the next row) | **Judges** (16:20 to 16:22 PST): the pool built 6 clones (the 4 completed runs and both anchors); Haiku judge 1 call USD 0.0282, Sonnet judge 1 call USD 0.1880, both one session, metering complete. **Scan hits on both judges:** 68 (Haiku) and 21 (Sonnet), all the `solution hash` pattern: the task id `194ad866a1` is the solution commit's first 10 characters and the pool lives at `/home/ollie/seedset-pools/194ad866a1/first`, so every line naming the judge's own cwd or a clone path matched; the full hash occurs 0 times. Verdicts `cleared` recorded by the coordinator. **What failed:** `summarize` met the judges' hits before their verdicts, recorded a pool incident (exit 0) and, as it does after every summarize, removed the clones; `smoke-check` then recorded `passed: false`. With the owner's second answer (finish with no spend) the incident record was archived and `summarize` run again: it could not run the hidden tests on the removed clones (a third incident), and `smoke-check` again recorded `passed: false`. The kit's only rebuild needs new judge calls, so the smoke was not pursued further. The three incident records are under `~/lh-cache/logs/seedset-smoke2-2026-11-23/pool-incident-archived{,-2,-3}/`; the ledger after the smoke is copied there. **`smoke-check` (last):** true: every program ran without incident, no unit cut, every reserved unit settled, bound model and effort on every call, calls within the reservation, no provider error. False: clone count, both judges rated every clone, hidden result on every clone, ratings bound (no summary), and clean scans (the frozen check fails any hit, cleared or not; with the fixed scanner these records have none). **Figures:** wall clock per call: `direct` 1,202 s (cut at the 1,200 s provider timeout), `direct_sonnet` 75, `retry_until_check` 208, `implement_check_repair` 106, `implement_review_revise` 88, Haiku judge 97, Sonnet judge 39; `direct` median wall above the plan's 15-minute line, so `bisect: true` (the plan's rule for bisecting the ladder from the start). **What the smoke showed:** the isolation holds on the real CLI (no breach in 8 calls), the caps, reservations, settlement, metering and session audits work; the scanner has three false-positive patterns on real records, and two kit steps turn a missing verdict into a permanent record. Both are being fixed (`a81c7bad`, `87654d13`, `a6770881`, `29bac011`, review findings pending). Spend, both smokes: USD 0.9902 + 0.0323 = 1.0225 priced, 9 calls. |
| 2026-11-23 | The owner's allowance for the next 24 hours; coordinator reading: a third smoke | The owner, about 17:00 PST: "proceed with making progress on this project. you can spend up to 10% of weekly usage quota in the next 24 hours". **Coordinator reading (recorded as an assumption):** this is the owner's word for the next paid step of this study, the third smoke, after the scanner fixes are reviewed and merged, the anchors re-run and the freeze recorded again (ruling R14's archive applies again); the calibration tranche is not started under it without a passed smoke. **Limit:** experiment starts until 2026-11-24 17:00 PST stop once the all-models weekly meter reads 10 points above the coordinator's reading before the first call (tighter than R13's 30). If wrong (the owner meant development work only): the third smoke's spend is about USD 1 priced and a small share of the meter. |
| 2026-11-23 | The scanner's three false positives, the verdict guards and two older faults fixed (impl_code in four rounds, independent review and re-check, coordinator integration; zero spend) | **Scanner** (`experiments/compare/scan.py`; `a81c7bad`, `a6770881`, `dce95c3b`): (a) the main-checkout prefix is not matched against tool results in Claude stream-json stdout (tool inputs, assistant text, plain lines and Codex output still are), in line with the session-file scan; it rests on the sandbox mounting no part of the main checkout, now enforced: every unit's preparation, candidates and judges, refuses a read-only mount under or around it (`a66bb09a`). Limit: a path reached without the prefix in an input and shown only in a result is not counted. (b) `other sessions' files` does not count the project folders the CLI made in the unit's own home for its own tree (exact names; a `..` after the folder cancels the exemption). (c) `solution hash` does not count the prefix inside the judge's own pool root `<pools>/<task>/<kind>` (the task id is the solution's first 10 characters); the full hash, `<pools>/<task>` alone and another pool's path still count. A hit's excerpt is taken from the recorded line. On the second smoke's real records all three kinds of hit are gone. **Guards** (`87654d13`, `29bac011`, `22fb0efe`): `pool`, `summarize` and `smoke-check` refuse, writing nothing, while a run or judge has hits and no verdict, and print the `prepare.py scan … --verdict` command; incidents remain for genuine failures. **Ruling R15 (coordinator):** the smoke's scan check passes a hit adjudicated `cleared`; `contaminated` or no verdict fails it; model-policy hits cannot be cleared. If wrong: a wrongly cleared hit passes the smoke; the verdict and its reason are in the unit's record. **Older fault found by the review** (`3ed70029`): `repos.dump` truncated then wrote, so a unit's thread could read another unit's half-written `study.json` or `record.json` in the stop rules and abort a batch; records are now written to a temporary file, synced and renamed. **Review:** ready after fixes twice (the `..` escape and the unenforced mount premise; then the judges' mounts and the race); all applied; one nit left (a `..` in a later shell word after `cd` into the own project; the unit's home holds only its own sessions). **Checks:** seed-set and harness tests 1,174 passed; whole suite on the integration branch with `main` and the MLE-bench Task 5 branch: 24,763 passed, 72 failed, 71 the known launch artefacts and one test of the isolation branch that did not record its scan as the kit does (fixed, `test_seed_set_real_cli.py`). **Owed before the third smoke:** the anchors on the merged code, the freeze recorded again (ruling R14's archive of the second smoke's ledger and work root), the spend row with a meter reading; the operator's script stops for adjudication through the kit's own refusals. |
| 2026-11-23 | The freeze recorded again on `a012638b`; the second smoke archived (run_experiment; zero spend) | **Anchors** from the runtime at `cf5477c3`: all 110 drawable, probe and smoke packages stable, 53 minutes (17:45 to 18:38 PST), load 13 to 27, per-repetition outcomes identical to the records of 2026-11-17 and of this afternoon; scoring path `54f6c589…`; record `c0607eaf…`, committed as `54df4747`. `tiers verify`: 118 packages of 67 tasks, anchors stable. **Runtime** `/home/ollie/seedset-rt` at `a012638b`: `54df4747` merged with the documentation pass `5cbfadf9` (Markdown only; the scoring path covers the kit's and the harness's `.py` modules and is unchanged, `tiers verify` repeated on the merge); `main` fast-forwarded to it. **Unchanged since the freeze of this afternoon:** `criterion.json` `b0115c65…` (CLI pin `/home/ollie/.local/share/claude/versions/2.1.331`, still the installed version), `judge-calibration.json` `15748aea…`, `tasks.jsonl`, the price table (read this afternoon), the five programs; both criterion files kept in `fffa257d` on `feat/seed-set-freeze-4`. Code trees: `experiments/compare` `3eecd39c…`, `experiments/seed_set` `c5015ee6…`. **Archive (R14):** the second smoke's ledger moved to `~/.local/state/seed-set/spend-ledger-smoke2-20261123.jsonl` (read-only, sha256 `3ea7e307…`, 17 rows), its work root to `~/seedset-work-smoke2-20261123`, its pools root to `~/seedset-pools-smoke2-20261123`; no credential copy in either. **`record-freeze` exit 0:** freeze event seq 1 in the fresh ledger (sha256 `23ae5e83…`). |
| 2026-11-23 | Spend row: the third smoke (run_experiment, under the owner's allowance of 2026-11-23) | **Tranche** `smoke` on task `194ad866a1`, the five arms in order, then pool, judge, summarize and smoke-check, from the runtime at `a012638b`, through `~/lh-cache/logs/seedset-smoke3-2026-11-23/run-smoke.sh` (pin, HEAD and ledger checks; stops at the first non-zero exit, pause, stop or pool incident; a step refused for a missing verdict is run again with `FROM=<step>` after the coordinator's verdict). **Caps:** the kit's smoke caps, 10 `claude-haiku-5-5` and 1 `claude-sonnet-5-5` candidate calls, 1 judge call each: 13 calls; priced ceiling USD 10; per-call worst case Haiku USD 0.50 and Sonnet USD 2.00 (ruling R11). **Meter** (read by the coordinator at 18:39 PST in a CLI pane with no prompt sent): week, all models, 17%, resets 2026-11-27 13:59 PST; Fable week 25%; no five-hour meter shown; usage credits not shown on the excerpt read. **Not explained:** the same screen read 38% (all models) and 70% (Fable) at 14:39 the same day with the same reset; the account's limits may have changed in between (the owner's sessions changed model at about 17:30). The stop line follows this reading: no experiment start once the weekly meter reads 27% or more (the owner's 10 points), until 2026-11-24 17:00 PST. Spend before this row: USD 1.0225 priced, 9 calls (both smokes). |
| 2026-11-23 | The third smoke passed its check (run_experiment; 7 calls, priced USD 1.4603) | **Run** 18:40 to 19:38 PST from the runtime at `a012638b`, CLI 2.1.331, one pass of the operator's script with no refusal and no verdict needed (0 scan hits on every run and on both judges). **`smoke-check`: passed**, all eleven checks true (every program ran without incident, no unit cut, every reserved unit settled, clone count, both judges rated every clone, hidden result on every clone, ratings bound to the judged patches, clean scans and session audits, bound model and effort on every call, calls within the reservation, no provider error). **Units:** `direct` Haiku `failed` (provider timeout at 1,200 s; 1 call settled at its worst case USD 0.50, a cut call has no final usage); `direct_sonnet` `completed` (1 call, 49 s, USD 0.1837); `retry_until_check` `completed` (1 of 3 calls, 792 s, USD 0.0358); `implement_check_repair` `completed` (1 of 3, 69 s, USD 0.0235); `implement_review_revise` `failed` (provider timeout at 1,200 s on its first call, USD 0.50 worst case); Haiku judge 1 call, 86 s, USD 0.0285; Sonnet judge 1 call, 40 s, USD 0.1888. Calls: Haiku candidates 4 of 10, Sonnet 1 of 1, judges 1 and 1. The pool held 5 clones (3 completed runs and both anchors). **Bisect:** the `direct` median wall clock is 1,202 s, above the plan's 15-minute line, so the smoke row records `bisect: true` and the ladder probe bisects the rungs. **Observation, no claim:** `direct` on Haiku reached the 1,200 s provider timeout on this task in both the second and the third smoke, and `implement_review_revise` once in two; a timeout is a natural failure of the run. Its priced cost is the per-call worst case, which is what the tranche ceilings count. The pool's ratings are in `results/pools/194ad866a1-first/` of the runtime; the judge is not yet qualified, so no rating is reported here. **Meter after** (19:39 PST, no prompt sent): week, all models, 17%; Fable week 26%. **Spend to date:** 16 calls, USD 2.4828 priced (three smokes). The ledger after the smoke is copied to `~/lh-cache/logs/seedset-smoke3-2026-11-23/`. |
| 2026-11-23 | Spend row: the ladder probe (run_experiment; the plan's one redraw, authorized with the calibration; under the owner's allowance of 2026-11-23) | **Tranche** `redraw`: `study.py probe` and `probe-readout` in turn, `direct` on `claude-haiku-5-5` once on the four probe tasks of each rung the answer asks for, bisecting T0 to T5 (the smoke's `bisect: true`), from the runtime at `a012638b` on the ledger that holds the passed smoke. **Caps:** 40 Haiku candidate calls (the kit's redraw cap, shared by the probe, its relaunches after an incident and the extension probe); priced ceiling USD 8; per-call worst case USD 0.50 (R11). A bisection of the first phase needs at most 12 runs. No judge call. **Stops:** the kit's (an incident above 10% of the tranche's runs, a pause on a usage limit, the ceiling), and the coordinator's: after each step the answer is read before the next rung starts; an all-too-hard answer waits for the transcripts to be read (`record-transcripts`); an extension probe is not started without a new row. No start once the weekly meter reads 27% or more (the owner's 10 points above the reading of 18:39), until 2026-11-24 17:00 PST. **Meter before** (19:39 PST): week 17%, Fable week 26%, no five-hour meter shown. |
| 2026-11-23 | The ladder probe's first step stopped: two runs lost their login mid-session and the runner crashed while settling one (run_experiment; 4 `claude-haiku-5-5` calls, USD 0.0614 settled for three, one reservation open; paid starts held by the coordinator) | **Step** 19:40 to 19:55 PST, bisection's first rung T2, tasks `cc4f804136`, `9f46516eae`, `53e7ea6a0d`, `3442aef203`, two at a time. **Outcomes:** `cc4f804136` and `53e7ea6a0d` `completed`, hidden set failed (USD 0.0201 and 0.0214); `9f46516eae` an incident, `provider: call 1: Failed to authenticate: OAuth session expired and could not be refreshed` (USD 0.0199); `3442aef203` ended the same way (its stream's last event) and is not settled: `settle` raised `PermissionError` in `shutil.rmtree` of the unit tree on a read-only directory the agent's own test run left under the unit's `tmp` (`…/provider_environment_snapshots/…/rootfs/workspace`), after copying the run state and before the credential clean-up; `probe` exited 1 and `probe-readout` did not run. No stop or pause event; the reservation of `direct/run-5` (USD 0.50) is open; no credential copy is left in the unit homes (none found by name). **Cause of the lost logins (confirmed by file time only; the login file is never read):** the owner's `~/.claude/.credentials.json` was rewritten at 19:50:26, a token refresh by one of the owner's own sessions; both units in flight held copies made at 19:40 and 19:43, and failed within minutes. With the copy route (R7, kept by R9) a unit alive when the access token expires either fails (the owner's side refreshed first, as here) or refreshes first itself, which would leave the owner's sessions with a rotated refresh token. The second has not been observed; it would cost the owner a new login in every session. The three smokes met no expiry. **Ruling R16 (coordinator), two apparatus fixes before any further paid start:** (1) `settle` removes a unit tree that holds read-only directories (make writable, then remove), and a failure to remove the tree no longer loses the settlement; (2) a unit, candidate or judge, starts only if the access token in the login file it copies outlives the unit's worst-case wall clock (its reserved calls times the provider timeout) plus a margin; otherwise the start is refused with the expiry time, nothing is reserved, and the operator starts again after the owner's side has refreshed. The kit reads the expiry time and nothing else from the file; it fails closed when the field is absent. No unit then lives across an expiry, so none is cut by a refresh and none refreshes. If wrong (a refresh before expiry, for example a new login by the owner): the units in flight end as incidents, as here. A route without a refreshing credential (the long-horizon kit's host-held token) stays the owner's decision. **Then:** the fixes reviewed and merged, the anchors on that code, `record-freeze --reason` (the passed smoke stays in the ledger), the unit tree made removable, and `probe` again: it settles `direct/run-5` and launches each incident's task once more from the same 40-call allowance. Spend to date: 20 calls, USD 2.5442 priced settled, USD 0.50 reserved. |
| 2026-11-23 | Ruling R16's two fixes on `main` (impl_code, independent review and re-check, coordinator integration; zero spend) | **The login check** (`80ef4244`, `b642da81`): `units.login_expiry` reads `claudeAiOauth.expiresAt` and nothing else from the login file a unit would copy (the same file `sandbox.prepare_unit` resolves), fails closed when it cannot be read as a finite time, and no message carries the file's content. `units.require_login` refuses a start, before anything is prepared or reserved, unless the token outlives the unit's wall-clock limit plus 15 minutes. The limit is one value, `study.unit_sec` (reserved calls times the per-call timeout, 1,200 s for candidates and probe runs and 3,600 s for a judge batch, plus 600 s), and the launch guard kills the unit's whole process tree at it, the checks between calls included. Every start passes it (`one_run`: candidates, probe runs, relaunches and reruns; `one_judge`: judges, a rebuilt pool); the settling and recovery paths do not. `study.py login-expiry` prints the expiry time only. **Measured with it:** the owner's token was refreshed at 19:50:26 and expires at 03:50:26, a life of 8 hours. **The settlement** : the credential copy is removed first; `units.remove_tree` makes directories writable and removes the tree without following a link and only under its root; a tree that still cannot be removed is recorded in the run's facts (`tree_left`) and the settlement is kept; a second settlement of a run replaces its earlier state copy (the stuck run's case). **Review:** needs changes (the check's bound was used up by the launch's own slack and covered neither preparation nor the checks between calls; missing tests for links and for re-settling a failed login; `remove_tree` depended on a `chmod` binary and followed a root link), all applied; re-check: pass, one nit left (a tree equal to its root passes the root check; no caller passes one). **Checks:** seed-set and harness tests 1,217 passed; whole suite on the integration branch with the MLE-bench review fixes: 24,808 passed, 71 failed, all the known launch artefacts. **Owed before the probe resumes:** the anchors on the merged code, `record-freeze --reason`, then `probe` (it settles `direct/run-5` and launches each incident's task once more). The reviewer's count: the two login incidents are 10% of the probe's 20 planned runs, at the stop rule's line and not over it; a third incident stops the tranche. |
| 2026-11-23 | The freeze recorded again on `dbe97cf0`; the ladder probe resumes (run_experiment; zero spend for the freeze) | **Anchors** from the runtime at `7592f6d1`, 21:00 to 21:55 PST: 110 packages stable, and every package's per-repetition outcome equal to the previous record; only the scoring path changed (`54f6c589…` to `80d98547…`). `tiers verify` passes (118 packages of 67 tasks). The record is commit `dbe97cf0`, now the runtime commit and on `main`. **Freeze** (`record-freeze --reason`, ledger row 24, on the same ledger so the passed smoke and the probe's rows stay): criterion `b0115c65…` and judge criterion `15748aea…` unchanged, so the stored copy on `feat/seed-set-freeze-4` still holds them; code trees `experiments/seed_set` `f0c7ac9f…` and `experiments/compare` `3eecd39c…`; anchors record `b35b5d3a…`. **Meter** at 22:01 PST, read with no prompt sent: 21% of the week on all models (17% at 18:39; the line for experiment starts is 27% until 2026-11-24 17:00 PST). The rise since 18:39 is mostly the coordinating session and its subagents: the experiments made 11 Haiku calls in that time. **Login**: `login-expiry` reports 2026-11-24 03:50:26 PST, 350 minutes ahead. **The probe's resumed step** runs under the spend row above with nothing changed (`redraw`, at most 40 Haiku calls, USD 8): it first settles `direct/run-5` (task `3442aef203`, the run the crash left open) as an incident, then launches again the two tasks that lost their login (`9f46516eae`, `3442aef203`). Two incidents are 10% of the probe's 20 planned runs; one more stops the tranche. **Where**: runtime `/home/ollie/seedset-rt` at `dbe97cf0`; anchors work directory `~/seedset-anchors-20261123c`; operator script `~/lh-cache/logs/seedset-probe-2026-11-23/probe-step.sh` |
| 2026-11-23 | The ladder probe's answer: rung T0, and the 20 calibration tasks drawn (run_experiment; tranche `redraw` 10 `claude-haiku-5-5` calls, priced USD 1.1792; study total 26 calls, USD 3.6620) | **Steps** from the runtime at `dbe97cf0`, 22:01 to 22:44 PST. Step 1 resumed: `direct/run-5` settled (USD 0.0169; counted an incident with the earlier login loss), and the two tasks that lost their login ran again. **Rung T2** (6 runs, 4 usable, 2 incidents): 0 of 4 hidden sets pass; all four runs completed, none was cut. The readout asked for T0. **Rung T0** (4 runs, 4 usable, no incident): 1 of 4 passes; one run completed and failed its hidden set; two (`2aaf1ecc8e-t0`, `e0e53c4dda-t0`) were cut at the 1,200 s call limit and settled at the worst case USD 0.50 each, which is most of the tranche's priced figure. **Answer** (`probe_readout`, ledger row 39): `chosen` T0, in the band of 1 to 3 passes; the 20 calibration tasks are 9 of T0 and 11 of T2 (`chosen_sha256` `437bc1ca…`). The agent ran the visible check itself in every usable run (`self_check_share` 1.0). No pause, no stop; incidents 2 of the 20 planned runs. **Read with care:** four tasks a rung is a coarse screen, and the two cuts are an envelope effect, not difficulty (next row). |
| 2026-11-23 | Coordinator ruling R17: every candidate prompt states the call's 20-minute limit (run_experiment finding, coordinator's change to the programs; zero spend; before any calibration call) | **Finding.** Five candidate units so far ended at the 1,200 s call limit: `direct` on Haiku in the second and third smokes, `implement_review_revise` in the third, and the two T0 probe runs above. The two probe transcripts were read: each agent made its edit and ran the visible check, then ran broad selections of the repository's tests one after another (commands with their own limits of 900 to 1,500 s, then background runs and `sleep`) until the call was killed. No prompt told the agent the call has 20 minutes, and the task repository's own `AGENTS.md` tells an agent to run a broad check after narrow selectors. A cut scores 0 ("Envelope and scoring"), so on this evidence a large share of `direct` runs would score 0 for a limit the agent was never told. **Ruling.** The seven candidate prompts of the four programs gain one sentence: the call ends after 20 minutes of wall-clock time, and work not finished and reported by then is lost. Nothing else changes: the limit stays 1,200 s, a cut still scores 0, and the sentence is the same for every arm and model. The judge's prompts are untouched. **Why the probe's answer stands.** T0 had 1 pass, 1 completed failure and 2 cuts: whatever the two cut runs would have scored, T0 stays at 1 to 3 passes of 4, so the chosen rung and the draw are the same. T2's four usable runs all completed. The kit's records are unchanged; the two cuts are reported here as envelope cuts, not as difficulty. **No new smoke.** The mechanics are unchanged: prompt strings only, no `*.py` file, so the anchors record holds; the programs' and the end-to-end offline tests pass (56). The freeze is recorded again with this reason. **Not shown:** that the sentence removes the cuts. The calibration reports each arm's cut rate beside its scores, and a cut rate that stays high is reported as a limit of the envelope, not tuned again. **Assumption, the coordinator's:** this is an apparatus fix of the kind the ladder section foresees ("the transcripts are read before another call; a fault is fixed"), decided before any calibration data exists; the owner may reverse it before the calibration's first call. |
| 2026-11-23 | Correction to the row "Coordinator ruling R17" after its independent review (review_code: sound with fixes; zero spend) | Kept as written; these hold. **(1) Probe runs made under the old prompts do not become calibration data.** That row says "the kit's records are unchanged" as if that settled it. It does not: `study.slot_limits` counts a drawn task's probe run as the first of its four Haiku `direct` runs, and all eight usable probe runs are of drawn tasks, the two cuts among them, so eight tasks would mix one old-prompt run with three new ones. Ruling: the programs' text is part of a task's form ("keeps its probe run … unless the form changed"), so a probe run counts only when the programs frozen at its start are the programs frozen now. After the new freeze none of the eight counts; the calibration plans 80 Haiku `direct` starts, its whole cap, which leaves no room to run a slot again after a usage-limit cut (the task then keeps the runs it has). The change is in the kit's code, so the anchors run again before the freeze. **(2) A cut is not only "reported": it can end the calibration.** A run cut at the limit is not rated, and gate G4 needs 90% of the candidate runs rated; more than 10 cuts among the 100 candidates fail G4, which the redraw cannot repair. That row's "reported as a limit of the envelope" understates this. Stop rule for the tranche, set here before its first call: the Haiku runs go out in four stages of five tasks; if more than 2 of the first stage's 20 runs are cut at the limit, no further stage starts and the result goes to the owner. **(3) The freeze identity changes.** `criterion.json` names every program's hash, so the criterion is rewritten and its hash changes; the chosen task list (`chosen_sha256`) and the passed smoke carry over. **(4) The probe's reading.** The rung was decided by the kit's rule, which counts a cut as a usable failure: T0 is 1 pass of 4 usable, and any outcome of the two cut runs keeps it at 1 to 3. Under the other reading (a cut is not difficulty) T0 would have two usable runs, below the kit's minimum; the kit's reading governs the draw, and the draw does not use pass counts within the rung. **(5) Cost of a cut.** A cut call is priced at the worst case, USD 0.50, because it has no final usage; the two probe cuts are USD 1.00 of the tranche's USD 1.18. The calibration reports cut runs' cost apart from completed runs'. **(6) What the review verified in the two transcripts:** both agents made the edit and passed the visible check, then ran serial broad selections (commands the CLI caps at 10 minutes, then background runs and `sleep`); neither was a hang. In `e0e53c4dda-t0` an end-to-end test also fails on untouched code in the unit's environment, which sent the agent into further comparison runs. Not verified: the three smoke cuts, and whether the sentence lowers the cut rate. |
| 2026-11-23 | Ruling R17's fix on `main` and its re-check; the stop rule tightened (impl_code by an implementer, independent re-check: the code sound; zero spend) | **The fix** (`79668cb2`): `layout.counted_runs` leaves out the probe runs reserved under a freeze whose `programs` hashes differ from the latest freeze's; the planned starts (`slot_limits`), the pool builder, the records and the readout read it. The probe's own readout, the incident stop, the ledger audit and the spend totals still see every run. Tests: one freeze keeps the reuse, a freeze with changed programs ends it, a code-only freeze keeps it, and 80 starts fit the cap. **Re-check:** the rule filters the live ledger as intended, and no place was missed. Two limits it names: the calibration's readout will not show the probe's runs or its two cuts (their record is the probe's readout, ledger row 39, and the rows above); and a freeze that changed the programs again during the calibration would not be caught, so **no freeze is recorded between the calibration's first call and its readout**. **Corrections to the correction row above, which stays as written.** (a) It leaves out the review's fourth finding: the ruling can be reversed only by an owner who knows of it. The owner was told in the session at about 22:50 and 23:10 PST, with the ruling, its corrections and the chance to reverse them; no reply had come when this row was written, and the tranche starts on the coordinator's recorded assumption. (b) Its item (5) omits that a cut run still records `metering_complete: true` (the check reads the receipt only) and that the transcript's per-message usage could price a cut call below the USD 0.50 placeholder; the kit is not changed for this, and cut runs' cost is reported apart. (c) Its stop rule was weaker than G4. G4 counts every candidate run that is not rated (a cut at the limit, a failure without a patch, an incident), Sonnet's 20 included, and 2 of 20 projects to exactly G4's limit with no re-runs left. **The rule as applied:** before each further candidate stage (the three later Haiku stages and the Sonnet stage), if the calibration runs that cannot be rated are 10% or more of the runs so far (2 of 20, 4 of 40, 6 of 60, 8 of 80), no further stage starts and the result goes to the owner. The operator's script applies it (`calib-step.sh`, `gate`); the kit has no stages. |
| 2026-11-23 | The freeze recorded again on `352fbbaa`; the calibration is held: the owner's allowance is used up (run_experiment; zero spend) | **Anchors** from the runtime at `79668cb2`, 23:06 to 23:57 PST: 110 packages stable, every per-repetition outcome equal to the previous record; `tiers verify` passes (118 packages of 67 tasks). The record is `352fbbaa` in the runtime (`b9281de5` on `main`). **Freeze** (`record-freeze --reason`, ledger row 40, same ledger): criterion `82668110…` (the four changed programs' hashes; nothing else in it changed; its earlier copy is kept beside the operator's script), judge criterion `15748aea…` unchanged, code trees `experiments/seed_set` `3924ea8a…` and `experiments/compare` `3eecd39c…`, anchors record `b915a404…`, price table unchanged. The criterion files are stored on `feat/seed-set-freeze-5` (`d6fe3f8e`). The chosen task list and the passed smoke carry over. **Meter** at 23:58 PST, read with no prompt sent: 27% of the week on all models (21% at 22:01, 17% at 18:39). That is the line set with the owner's allowance of 2026-11-23 (10 points above the 18:39 reading), so **no experiment call starts** until 2026-11-24 17:00 PST or the owner's word. The experiments made 26 calls in all; nearly all of the ten points went to the coordinating session and its subagents (the fixes and reviews of rulings R15 to R17, and the kit work for the third model tier), not to experiment calls. **Login**: expiry 2026-11-24 03:50:26 PST. **Disk**: `/home` had 12 GB free at about 23:20, under the kit's 20 GB guard; after the coordinator removed finished agent worktrees and download caches, and the anchors run ended, 25.6 GB (24,367 MiB). The margin is thin and another session writes to the same disk. **Ready, not started:** the calibration's spend row is not written, since a spend row precedes a start and none is allowed. The operator's script (`~/lh-cache/logs/seedset-calib-2026-11-23/calib-step.sh`) runs the tranche in stages with the stop rule of the row above. |
