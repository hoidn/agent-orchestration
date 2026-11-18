# Seed-Set Calibration Plan

**Status: Plan; the kit is on `main` (`09068ec8`, 2026-11-15; entry point
[`experiments/seed_set/README.md`](../../experiments/seed_set/README.md)) after five review rounds; nothing spent.** Owed
before the first paid call, in the [ledger](#ledger)'s order: the owner's decisions, the freeze with
`criterion.json`, the 20-task rehearsal, the tranche's spend row, then the smoke. The freeze waits for the owner's
credential-route decision. This page plans the scaled-down research step
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
runs unless the form changed. The ladder probe is the plan's one redraw,
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
3,600 s per run. A failed run or a timeout scores 0; a provider or sandbox
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

| Date | Entry |
| --- | --- |
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
| 2026-11-14 | Fix round 2 after the re-review of fix round 1 (2 majors, 7 minors; branch `feat/seed-set-prep`, `main` `b7e2e2b5` merged first) | N1: the usage-limit wording, and the provider-error rule of incidents, read only a call that did not succeed (an error result, or no result event at all); a stdout line that starts with `{` and is not JSON (a stream event cut mid-write) is never read; every must-cut shape of the re-review stays cut. N2: the host-side checks of candidate code (`settle`'s visible check, the probe's hidden check, `summarize`'s hidden tests) run under the launch guard with a bound: 600 s for a patch's hidden set (five times the 120 s of Step 1's hidden run), 1,200 s for the visible check (dev-check.json's 600 s plus 600 s), 600 s per clone for a summary; a check past its bound is recorded as timed out, never as a pass or a zero (a probe run with one is an incident, a summary that times out makes its pool an incident, the readout counts timed-out visible checks apart). Assumption recorded for the coordinator: `summarize.py` gives each hidden test 1,800 s and counted a hanging one as failing; past the new per-clone bound such a hang now costs its pool, and a probe run with one is relaunched once. n1: a kill reaches a pid only while its start time matches the scan (a pidfd, then the start time). n2: the unit's command runs as its guard's child from its first instant; the guard is a child subreaper, so what a root shell that died leaves is killed when the command ends; a guard killed by the operator leaves the launcher to kill the command's session tree. n3: the pause and every refusal name the rule that fired and the line it read; an older CLI's `...|<epoch>` gives the reset; `study.py not-a-limit UNIT --reason R` records, while the unit's usage-limit pause is open, that its raw result shows no limit: the unit becomes what the rules make it, the pause stops closing starts, and nothing runs again. n4: the cut-unit table gains `settle`'s session audit and the redraw's planned units, each checked by a test. n7: `spend.rows` parses after releasing its lock; 120 writers beside 16 readers all finish. Minor 9: the ten functions the re-review listed are at radon 12 or below (`tiers.build` 35 to 6, `rules.smoke_check` 28 to 11, `probing.recover` 16 to 12, the others 10 or below), split with no behaviour change, and no function is new above 12. The merge of `main` renamed two long-horizon fixtures the kit tests read; the tests follow. Not in this round: R6, re-runs outside the caps, the credential route. Spend to date: 0. |
| 2026-11-14 | Fix round 2: the two rehearsals (stand-ins only, own ledgers, four calibration tasks, on `76b967f3`) | A, the cut in the smoke (158 s at load about 55): exit 0; the smoke check failed on `no_unit_cut_by_a_usage_limit` and `no_provider_errors`, the other nine true; `direct` cut, the other four completed; the refusal named the unit, the reset, the rule that fired (the recorded answer) and its line, and `not-a-limit`; the probe and the calibration both refused ("no passed smoke") and no start follows the smoke event (smoke 10 of 10 Haiku and 1 of 1 Sonnet candidate calls reserved, 8 and 1 made; judges 1 and 1; priced USD 0.1664). B, the cut in the probe (40 minutes at load about 50 to 60): exit 0; the smoke check passed; the cut on T1 task `2aaf1ecc8e` (runs: cut, completed) paused at seq 19 and resumed at seq 22 with no start between; after the resume 19 calls that succeeded printed a limit warning on stderr and no pause followed; 0 incidents; redraw 21 of 40; the probe chose T3 and drew 20 tasks; the 12-call start against the redraw ceiling of USD 3 was refused and wrote nothing; priced smoke USD 0.1664, redraw 0.0756, calibration 0.876, none open, none missing or over its reservation; no anchor failure, every identity scan 0 hits; decision `stop: no judge passed its gate` with 16 of 20 tasks missing by construction; the check-withheld run completed in 2 calls. Spend to date: 0. |
| 2026-11-14 | Fix round 3 on the coordinator's rulings after fix round 2 (branch `feat/seed-set-prep`; rehearsal on `2e272c8e`) | Ruling 1: a hidden test that hangs is a failure of that test, not the loss of the pool. Each hidden test has 240 s (twice Step 1's 120 s for a whole hidden run), passed by the kit to `summarize.py` (`--hidden-test-timeout-sec`; the harness default of 1,800 s is unchanged) and to the probe's hidden check; the 600 s per clone (and 600 s per patch's hidden set, 1,200 s per visible check) stays as the backstop for a harness that itself hangs, and a summary past it is still an incident. This replaces fix round 2's assumption that such a hang costs its pool; past the backstop it still does (more than two hanging tests in a patch's hidden set, about two and a half per clone on average in a summary). Ruling 2: `not-a-limit` still refuses an unsettled unit; the pause's refusal and that refusal now say the way out (`settle` the run first; a probe run, which only `probe` settles and `probe` refuses while starts are closed: `resume-after-limit` after the reset, then `probe` settles it as a cut run). Ruling 3: the host checks' temporary directories are recorded with their maker (pid and start time) in `host-temp.jsonl` beside the ledger, the checks' own temporary directories go inside them (`TMPDIR`), and the sweep at the start of every command that takes the study lock removes the recorded ones whose maker and check no longer run and prints their paths (never a listing of `/tmp`; a record naming a directory the kit does not make refuses). Rehearsal (stand-ins only, own ledger, four calibration tasks, the cut in the probe; 2,636 s, beside the kit tests): exit 0; the stand-in Sonnet's code on the first calibration task `12ea8483f0` made one hidden test hang 300 s in host-side checks; it hung twice (the first and the retest pool), each time counted as that test failing, both pools were summarised with only that test failed on the Sonnet clone, and no hanging process was left; the rest as fix round 2's rehearsal B (smoke check passed; the cut on `2aaf1ecc8e` paused and resumed at seq 22, its runs cut then completed; 19 warned calls and no pause after the resume; 0 incidents; the 12-call start against the redraw ceiling refused with the ledger unchanged; priced smoke USD 0.1664, redraw 0.0756, calibration 0.876, none open, missing or over its reservation; no anchor failure, every identity scan 0 hits; decision `stop: no judge passed its gate; hidden-test pass rate is primary; stop for the owner` with 16 of 20 tasks missing by construction; the check-withheld run completed in 2 calls). Spend to date: 0. |
| 2026-11-14 | Fix round 4 on the final scoped check (1 blocker, 2 majors, 3 minors; branch `feat/seed-set-prep`, `main` `27a5b30b` merged after the fixes) | B1: the temporary-directory sweep acts on a recorded directory only when it is a direct child of the temp directory with a kit prefix and its real path is the recorded one, and runs `chmod` only after that check; any other record line is named on stderr, skipped and kept, and no longer stops a locked command. M1: paid extra usage (a `rate_limit_event` with overage in use, or a rejected limit with overage allowed; the long-horizon kit's rule read from the stream) closes every start under its own rule, "paid extra usage", until `resume-after-limit`; by the coordinator's follow-up rulings, a call that ended normally stays an observation (a candidate's result is used and its slot does not run again; a judge's judgment is kept and its pool is not rebuilt) and one that did not is cut like any limit; either is priced at its metered tokens. The pause of the recorded answer or of paid extra usage names `resume-after-limit` only, not `not-a-limit`. M2: a hidden set's backstop is 600 s plus 240 s per hidden test, summed over the clones whose hidden tests run for a summary, so hanging hidden tests fail at their own bound instead of timing the check out. n9: a session file whose recorded start time is not its live leader's reads as dead. n10: `not-a-limit` refuses a pause by the recorded answer or by paid extra usage. A guard killed before it wrote its session file gives a status saying so, and an empty file reads as no session. After the independent check of round 4, the sweep also skips, names and keeps a line naming a file or one it cannot read and gives a kit directory mode 700 before reading it, a unit with paid extra usage on any call is paused under that rule (so `not-a-limit` refuses it), overage flags are read case-insensitively, and the reset is the last rejected event's that names one. Kit tests 664 passed, compare-harness tests 558 passed (stand-ins only). The owner's check that paid extra usage is off on the account stays owed before the first call. Spend to date: 0. |
| 2026-11-15 | The kit is on `main` (`09068ec8`, merge of `feat/seed-set-prep` at `f4ceafaa`) | After the independent check of fix round 4 ("ready after fixes": the six earlier findings closed, 72 of 73 recorded streams classify as before and the one that differs is the intended paid-usage change) and its six small items (a record line naming a regular file or an unreadable line is named, skipped and kept; a pause names a unit's paid-usage call so only `resume-after-limit` reopens it; overage flags given as strings are read; the reset comes from the last rejected event that names one), which the coordinator checked by reading the diff. Kit tests 664 passed. Full suite on the merge: 23,768 passed, 6 failed (the four nanoBragg tests of the standing baseline; two load failures that pass alone). No provider call was made; spend 0. **Still owed before the first paid call, in order:** the owner's decisions (the credential route of ruling R7; that paid extra usage is off; the allowance hours and shares and the meter-reading protocol; whether a cut slot may run again outside the caps); the freeze on the merged commit (runtime worktree, the anchors' stability run, `judge-calibration.json` and `judge-seeds.json`, the price table re-read, `criterion.json` with its `spend` and `sha256` blocks, `record-freeze`, the hashes in this ledger); the 20-task rehearsal on the frozen code at low load; the tranche's spend row; then the smoke. |
| 2026-11-15 | Anchors re-checked under the current scoring path (`feat/seed-set-anchors` `c8b2f587`; zero spend) | The record of 2026-11-13 predated the scoring-path changes of 2026-11-14 (guarded host checks; the checks' own temporary directory, `b18da922`), and one of them changes a test outcome, so all 110 packages the study can draw, probe or smoke on were re-run by name: 61 minutes at load 10 to 16, no errored repetition, every one stable with the outcomes of 2026-11-13. `tiers verify`: 118 packages of 67 tasks verified, anchors stable. The four unstable entries are the two tasks already rejected: `1fd10ab4c3` (load: stable 3 of 3 at load 13) and `9a7547ed4c` (the reference fails `test_subreaper_controller_reaps_only_its_exact_owned_server` 3 of 3 with `socket path too long`: under `TMPDIR=/tmp/seed-set-host-XXXXXXXX/tmp` the test's tmux socket path is 104 bytes against a limit of 103; under `/tmp` it was 77). Usable packages are unchanged: T0 9, T1 11, T2 11, T3 19, T4 6, T5 5. **Ruling: `9a7547ed4c` stays rejected and the kit's temporary path is not shortened** — the usable set passes under the path as it is, T0 and T1 are above their floor without the task, and a shorter path is a kit change that needs its own tests, review and a third anchors run — if wrong, the study has one task fewer in T0 and T1, and a later package whose tests build a longer socket path is rejected at its anchors check instead of used. **Ruling: an anchors record holds only for the scoring path it was measured under** — this run showed a kit change can flip a reference's outcome while the package hash stays the same — so the freeze runs the anchors on the frozen runtime commit, and binding the record to the scoring path in code is owed before the freeze — if wrong, an hour of machine time per freeze. |
| 2026-11-17 | The owner's answers to the open decisions; coordinator rulings R9 and R10 | **Paid extra usage is off for the account:** "yes". **The credential route:** "whatever easier". **Ruling R9: the route as built stays** (ruling R7: each unit's private home gets a copy of the subscription login file, removed as the correction row of 2026-11-14 says) — it is built, reviewed and rehearsed, and the host-side passthrough would be a kit change with its own tests, review and rehearsal — if wrong, the price is the one that correction row names: the agent under test can read its unit's copy during its call. **Whether a cut slot may run again outside the caps:** "you decide". **Ruling R10: no** — a cut slot runs again only inside its cap, as ruling R1 built it; the authorised call counts of `AGENTS.md` stay the bound — if wrong, a usage limit in a tranche with no room (the smoke, the calibration's Sonnet candidates, both judges' calibration caps) loses that observation, and a calibration left short of its 20 tasks stops with no quality claim. **The allowance:** "30 percent weekly". Not settled, and asked again: whether that is the share kept free or the share the study may use, the five-hour share, the hours, and a meter reading before the first call. Still owed before the first paid call, in order: the allowance, the freeze on the merged commit, the 20-task rehearsal, the tranche's spend row, the smoke. Spend to date: 0. |
| 2026-11-17 | The task builder's oracle could read the base run's bytecode on the fix side (debug_code, then fixed by the coordinator as `cb818f0d`; zero spend) | **Found** because `tests/experiments/test_seed_set_build_tasks.py` failed on `main` in every whole-module run (`visible check fails on the fix (run 1)`). **Cause:** since `31c5c8e5` (2026-11-12) `sandboxed()` keeps bytecode under `PYTHONPYCACHEPREFIX=<box>/pycache` instead of setting `PYTHONDONTWRITEBYTECODE`. `oracle()` runs the base side and then the fix side in one clone; Python accepts cached bytecode when the source's size and its mtime in whole seconds match, so a fix of the same byte size applied within the base run's second ran as the base's code. Shown by trace (the fixed source on disk, `add(2, 3) == -1` from the cached file), by onset (6 of 6 module runs pass at `31c5c8e5^`, 6 of 6 fail at `31c5c8e5`) and by a deterministic test. **Reach:** `oracle()` is the only place that runs Python in a tree and then rewrites that tree's sources in place. Every scoring path (`pool.add_clone`, `summarize.hidden_failures`, `anchors.score`, `host._hidden`, `evaluation.check_first_attempt`, `prepare.apply_patch`) builds a fresh tree before any interpreter starts, and the check-withheld form uses a new prefix per call. On recorded real tasks the base side took at least 3.5 s between checkout and the fix (69 rows of `ladder_screening.jsonl`, 30 of `screening.jsonl`), so the same-second condition cannot hold; the fault can only reject a task, never admit one, and no recorded rejection has its pattern. **The anchors and recorded screening results stand.** Not exercised: an agent's own visible check in its working tree during a real launch (it could read stale bytecode after a same-size, same-second edit; that affects the agent's feedback, not its score, which is rebuilt from the recorded patch). **Fix:** after the fix-side `git apply`, `oracle()` removes the clone's directory under the bytecode prefix. A test that stamps the fixed file into the base run's second fails without it. Checks: the module 20 passed in 5 of 5 runs; the 12 seed-set modules, 566 passed. This precedes the freeze, which binds the merged commit. |
| 2026-11-17 | The anchors record is bound to its scoring path in code (`feat/seed-set-anchor-binding`, reviewed, fixed on `feat/seed-set-freeze-prep`, merged as `978ae954`; zero spend) | What the row of 2026-11-15 said was owed before the freeze. Each entry of `anchor_stability.json` carries `scoring_path`; `tiers verify`, `record-freeze` and every start refuse a package without a stable entry at its hash and the current scoring path, naming it "not measured", "other scoring path" or "unstable"; `reject-unstable` rejects only on an entry unstable under the current path. **Independent review: merge as is**, with one major and five minors; four applied, two declined. **Applied.** (M1) The hash also covers `sys.version` and the installed pytest's version, so an update of either makes every entry "other scoring path" and refuses a start. (m4) The anchors score each hidden test under the study's `host.HIDDEN_TEST_SEC` (240 s), not 1,800 s. (m3) The freeze and each start compute the hash from the runtime's files, not the checkout's. (m2) A test asserts that every `experiments` module scoring loads is among the hashed files. (m5) The refusal names `--work` and says that another scoring path after a kit commit or a Python or pytest update calls for a new freeze, not the anchors run alone. The README lists what stays unbound: the environment variables `host.guarded` passes through, the git binary and its configuration, the other site-packages, the no-provider stubs. **Declined:** narrowing the hash to the 12 modules scoring loads (over-inclusion costs an hour per kit change, not correctness), and the slow exit of a stopped anchors run. Checks: the seed-set modules, 595 passed; the whole suite on the branch tip, 71 failed, all of them the launch context (67, which pass rerun directly: 263 passed) or the nanoBragg sibling path (4). **A first freeze attempt the same day, on `e85ea6fb`, is superseded:** the coordinator started it before this branch was merged; its anchors run (110 stable, 51 minutes) and drafts are not the record. The README no longer lists `judge-seeds.json` at the freeze: it names the judge the calibration selects and is written after it. |
| 2026-11-17 | The freeze is recorded on `592ed731`; coordinator ruling R11 sets the priced ceilings (run_experiment; zero spend) | **Runtime** `/home/ollie/seedset-rt`, detached at `592ed731` (`978ae954` plus the anchors record; `main` fast-forwarded to it). Scoring path `aed8b26a…` (Python 3.13.9, pytest 8.4.1). **Anchors** run from the runtime on all 110 drawable, probe and smoke packages by name, hidden tests bounded at 240 s: 50 minutes (2026-11-18T00:51Z to 01:41Z), load 5.3 to 11.7, no errored repetition, every package stable, per-anchor outcomes identical to the record of 2026-11-15; record sha256 `4df49436…`. `tiers verify`: 118 packages of 67 tasks, anchors stable. **Files:** `judge-calibration.json` `15748aea…` (both judges, the functional rubric, no calibration block); `criterion.json` `ce1289a9…`; `tasks.jsonl` `c5793e1b…`; price table `77a237c6…`; programs `common.orc` `d8c46f53…`, `direct.orc` `acfc8ba5…`, `implement_check_repair.orc` `ef8f286c…`, `implement_review_revise.orc` `547754ad…`, `retry_until_check.orc` `c7592336…`; code trees `experiments/seed_set` `ce9516f4…`, `experiments/compare` `2aaa787d…`. The two criterion files are untracked in the runtime, as the kit expects, and kept by the same bytes in `c0774047` on `feat/seed-set-freeze-2`. **`record-freeze` exit 0:** freeze event seq 1 in `~/.local/state/seed-set/spend-ledger.jsonl` (sha256 `b0e45c90…`). **Ruling R11, the `spend` block.** Per-call worst case: `claude-haiku-5-5` USD 0.50, `claude-sonnet-5-5` USD 2.00. Largest ordinary-rate call expected: Haiku USD 0.10 (the largest recorded Haiku call of this repository's sessions is about USD 0.06, PQ-1c), Sonnet USD 2.00 (no Sonnet call is recorded; twenty times Haiku's figure, the price ratio). Ceilings: smoke USD 10, calibration USD 60, redraw USD 8; USD 78 in all, inside the budget delegation. Caps of calls are the kit's (`spend.CAPS`: 121 Haiku and 52 Sonnet for the smoke and calibration; the redraw 40 Haiku candidates). The smoke's ceiling covers every one of its calls at the worst case (USD 9.50). The calibration's and the redraw's do not (USD 155 and USD 20 at the worst case): they are set at about twice what earlier sessions suggest, so a tranche whose calls price near the worst case stops at its ceiling before its call cap — if wrong, the calibration stops short of its 20 tasks and reports no quality claim, and a higher ceiling needs a new row before more spend. Both per-call figures sit on their bound, so a larger `largest_call_usd` after the smoke means raising the per-call figure and recording the freeze again. **Price table read again:** the vendor page of 2026-11-17 gives the table's figures (Haiku 0.10 / 0.50, cache read 0.01, five times those above 100,000 prompt tokens; Sonnet 2 / 10, cache read 0.10, no tier). The table holds one cache-write rate per model, the one-hour rate (0.20 and 4); a five-minute write (0.125 and 2.50 on the page) is priced at the higher rate, and a call is settled at the larger of the table's price and the CLI's reported cost. **CLI pin:** `/home/ollie/.local/share/claude/versions/2.1.327`, `2.1.327 (Claude Code)`. The CLI updated itself twice in two days (2.1.326 on 2026-11-16, 2.1.327 on 2026-11-17); another update before the first start means renewing the pin and recording the freeze again, which needs no reason while no start exists. A paid start must not have the no-provider stubs first on `PATH`, or the unit declares the stub and the pin check refuses. **Still owed before the first paid call, in order:** the allowance (owner), the 20-task rehearsal on the frozen code at low load, the tranche's spend row, the smoke. The owner's weekly limit stood at 98% on 2026-11-17 and resets on 2026-11-21 at 09:00 PST (long-horizon plan's ledger), so no paid call can start before then. Spend to date: 0. |
