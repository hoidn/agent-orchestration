# Seed evaluation apparatus

**Status: Working plan, zero spend; no task started.** This page plans the offline apparatus for Step 3 ("Seed
evaluation") and Step 4 ("Output") of the [seed-set calibration plan](2026-11-11-seed-set-calibration-plan.md):
what to build, in which order, and what it must take from the calibration's results. That plan stays the
authority for the study: its Step 3 and Step 4, thresholds, Budget, Stop rules and ledger rulings govern, and
where this page reads them differently, that plan wins. The seed evaluation's spend is **not authorized**: it needs
a new owner approval after the calibration is reported (`AGENTS.md`, "Experiment rules"; the seed-set plan's
[Budget](2026-11-11-seed-set-calibration-plan.md#budget)); what that request must contain is in
[For the owner's approval request](#for-the-owners-approval-request). Nothing here is a copyable command. Until
this plan is built, the kit ([`experiments/seed_set/README.md`](../../experiments/seed_set/README.md)) runs only the
smoke, the probe, the calibration and the Luna smoke.

## Scope and non-goals

- **In scope:** the code, tests and offline rehearsal that let the kit run Step 3 as written (live arms, offline
  baselines, pools, judging, the selection rule) and write Step 4's outputs, inside the kit's existing guards.
- **Not in scope:** the spend itself and its approval; the extension tranche (only where it attaches is named);
  the seed qualification of `plan_implement_review.orc` from "Search dimensions around one seed"; any Luna arm or
  the Luna placement step; the later genetic search; a tests-primary seed evaluation.
- **The runtime does not move.** The calibration runs on the frozen runtime `/home/ollie/seedset-rt` at
  `352fbbaa`, and no freeze is recorded between its first call and its readout (seed-set ledger, 2026-11-23). Every
  task below merges to `main` after review and takes effect at one freeze after the calibration's readout.

### What exists and is reused

The kit already holds most of Step 3's arithmetic and all of its guards. The apparatus extends these; it does not
replace them.

| Need | Existing function (path) |
| --- | --- |
| Offline re-roll baselines over ordered triples | `selection.rerolls`, `selection.baselines` (`experiments/seed_set/selection.py`) |
| Selection rules 1 to 6, the size limit (rule 7), interval and dominance | `selection.rules`, `selection.select_seeds`, `selection.bootstrap` (10,000 resamples, seed 20261111), `selection.calls_k`, `selection.program_lines`; `pareto.dominates` (`experiments/orc_structural_search/pareto.py`) |
| Exact means | `gates.mean` (a `Fraction` over whole-number scores) |
| A clone's score, 0 for a failed run, None when left out; hidden pass; rating bound to the judged patch | `gates.pool_records`, `gates.score`, `gates.hidden_pass`, `gates.bound_scores`, `gates.binding_failures` |
| Anchor checks | `gates.pool_anchor_failures` (one base and one reference per pool, so it is applied per batch here) |
| Measure-free run table, unusual runs, the order "anchors first", Fractions to floats | `readout.measure_free`, `readout.unusual_runs`, `readout.report`, `readout.direct_runs`, `readout.plain`, `readout.LIMITS` |
| Starts: caps, slots, cut re-runs, login and disk guards, settlement | `study.candidates`, `study.slot_limits`, `study.due_jobs`, `study.cut_reruns`, `study.one_run`, `study.settle` (already records `sessions`), `study.finish`; `spend.reserve`, `spend.authorize`, `spend.CAPS`, `spend.UNAUTHORIZED`; `units.require_login`, `units.audit_sessions`; `rules.require_free` |
| Pools, judges, summaries | `study.build_pools`, `study.judge`, `study.one_judge` (reserves one call per batch), `study.judge_blocked`, `study.summarize_pools`, `study.summarized_pool`; `pool.pool_runs`, `pool.write_pool`, `pool.build_batches` (every anchor in every batch) in `experiments/compare/pool.py`; `summarize.anchor_scores` |
| Blinding | `blinding.identity_tokens`, `blinding.scan_pool`, `blinding.judged_patches` |
| Tranche facts | `layout.PLANNED`, `layout.RETESTS`, `layout.STUDY_TRANCHES`, `layout.tranche_tasks`, `layout.require_tasks`, `layout.require_pool_kind`, `layout.tranche_judges`, `layout.pool_criterion`, `layout.load_criterion`, `layout.counted_runs` |
| Order, freeze and stops | `rules.require_order`, `rules.enforce`, `rules.planned_runs`, `rules.stop_reasons`, `rules.record_freeze`, `rules.frozen_identity`, `rules.require_tracked`, `rules.required_hashes`, `rules.require_spend_bounds`, `rules.bounded` |
| A once-written task list with its hash in the ledger | `probing.probe_readout` writing `results/calibration-tasks.json` (`layout.CHOSEN`) |
| An incident's one relaunch as a new unit | `probing.allowed` (the probe's rule) |
| Adding a tranche | the Luna smoke: `layout.STUDY_TRANCHES`, `layout.SMOKES`, `layout.LUNA_POOL`, `rules.smoke_check(tranche=...)` |
| Offline rehearsal | `rehearsal.stages`, `rehearsal.calibration`, `rehearsal.pools`, `rehearsal.stand_in_plan`; the stand-ins of `tests/experiments/seed_set_offline_support.py` |

### Facts the plan rests on, read in the code

- **A cut on a later call loses the whole run's patch.** The three workflow programs (`programs/*.orc`) have no
  handler around `provider-result`, so a provider timeout fails the run; `prepare.collect` (through
  `prepare.outcome_of`) copies patches only for a `completed` run. A cut on the second or third call of a
  multi-call program therefore scores 0 like a cut on the first.
- **A judge makes one call per batch.** `experiments/compare/score_functional.orc` maps one `provider-result` over
  the batches, each with `:timeout-sec 3600`; `study.one_judge` reserves `len(mapping["batches"])` calls. A seed pool
  of two batches is a two-call judge unit.
- **Nested sessions are expected to be zero.** `sandbox.CLAUDE_SETTINGS` denies the `Agent` and `Task` tools, and a
  nested CLI an agent starts through Bash shows as extra top-level sessions, which `units.audit_sessions` makes an
  incident. The count is recorded (task B4) so the readout shows it rather than assumes it.
- **Survivors come rung first.** `ladder.choose` lists the chosen rung's tasks first, then the fill rung's; the
  calibration's list is 9 T0 tasks, then 11 T2 tasks. Survivors keep that order, so the six parity tasks are likely
  all T0, and a cut at 16 survivors drops T2 tasks.

## Step 3 and Step 4 as apparatus requirements

Quoted from the seed-set plan's Step 3 and Step 4 unless marked. "Q" numbers refer to the decisions below; the
seven that change a selection reading are frozen in `criterion.json` (see the freeze gate under [Tasks](#tasks)).

**Live arms** (Step 3 table): Direct "6, fresh"; Retry parity "2, on the first six survivors", live
`retry_until_check.orc`; Implement-check-repair 3; Implement-review-revise 3. All on `claude-haiku-5-5` at effort
`medium` (`programs/arms.json`; `layout.load_arms`). The kit needs a `seed_evaluation` tranche whose planned runs
per task and arm are these, with the retry arm limited to the first six survivors in their order.

**Ordering and the selecting-power rule.** "Direct runs first. They are fresh because the calibration runs chose the
tasks and would bias the baseline. If the visible check failed in under 20% of them, the parity runs and
implement-check-repair are not launched and the readout says the check has no selecting power on this set." The
kit needs a checkpoint after every direct slot has settled (cut re-runs and incident relaunches first, where the
cap has room), a recorded rate, and start rules that refuse every workflow arm before it and the parity and
implement-check-repair arms when the rate is under 20%. The rate is over the direct runs whose patch the host
visible check ran on (Q1).

**Offline baselines.** "Re-roll `Q(k)`: retry with at most `k` = 2, 3 attempts (best-of-`k` by visible check has
the same quality at `k` calls); random-of-3; any-of-3 (upper bound)", "Offline, averaged over every ordered triple
of a task's six direct runs. The visible check picks the run; the baseline takes that run's judged score. `Q(1)` is
direct." `selection.rerolls` computes all of them over `itertools.permutations(runs, 3)`; the apparatus feeds it
the seed evaluation's own direct runs, never the calibration's, leaving out runs whose visible check timed out (as
`readout.direct_runs` does) and tasks with fewer than three usable direct runs.

**Retry parity.** "passes if every run completes, mean calls are within 0.5 and mean score within 1.5 points of the
offline figure for those tasks". Not built; the offline figure is `Q3` and `Q3_calls` over the six parity tasks
(Q4). Offline `Q(k)` moves past a cut attempt to the next one, while the live program ends at a provider timeout;
the parity check measures that gap and nothing corrects it.

**Judging.** "Judging (32 calls of the selected judge). One pool per task through `pool.write_pool`, in two batches
of at most eight candidates plus the two anchors; each arm's runs are dealt alternately into the batches, so a batch
shift cancels in arm differences. If reference minus base falls under 4 in more than three of the 32 batches, no
quality claim is made." `pool.pool` cannot do this (its `compose` puts every plain run in one batch, which passes
ten repositories), so the kit composes the two batches itself and calls `pool.write_pool`. The anchor check runs per
batch; a missing batch counts as under 4, and with fewer than 16 survivors the bound is the proportion 3 of 32
(Q3).

**Envelope.** "1,200 s per call, `COMPARE_MAX_CALLS` 1 or 3, 3,600 s per run. Every candidate prompt states the
call's 20 minutes (ruling R17)." The kit's per-unit limit is `study.unit_sec` (1,800 s for one call, 4,200 s for
three), not 3,600 s (Q9). The prompts already state the limit.

**Incidents.** "A failed run or a timeout scores 0; a provider or sandbox incident is resumed once with
`resume.sh`, then excluded and listed." The kit disables every `resume.sh` and `spend.reserve` refuses a unit
started before; the slot is relaunched once as a new unit (Q2).

**Quality and cost.** "Quality `q` is the mean over tasks of the per-task mean score, with the hidden pass rate
beside it. Cost `c` is mean provider calls per run, admissible because every candidate call is one model at one
effort; judge calls are evaluation cost, reported apart. Metered tokens (`metering.receipts`) are reported beside
`c`; if nested sessions appear in over 10% of an arm's runs, cost comparisons use tokens only." The kit records
physical calls (`units.physical_calls`), metering and the priced `settle` event per run, and `settle` records the
number of session files (`sessions`), not how many are nested (Q16).

**Selection rule (frozen).** `direct` is always in the set. Another program is a seed when all hold: "1. at least
95% of its runs complete; 2. `q ≥ q_direct − 0.5`; 3. re-rolling at equal calls does not beat it: `q ≥ Q(k) − 0.5`,
`k` being its mean calls rounded to 1, 2 or 3, halves up (vacuous for retry); 4. `c ≤ 3.0 × c_direct`, and the
same for priced tokens where metered; 5. its distinctive step (a second attempt, a repair, a revision) ran in at
least 20% of its runs; 6. for retry, the parity check passed." Rule 7 is the size limit of Step 1c ("fewer than 50
physical lines"). "The readout gives each arm's `q` and each difference from direct with a 90% bootstrap interval
over tasks (10,000 resamples, fixed seed), names every comparison whose interval spans the tolerance, and applies
the driver's dominance test against direct with `tau_q` 0.5 point and `tau_c` 0.10." `selection.select_seeds`
does all of this except rule 5's per-arm step, rule 6's check and the nested-session switch, and it compares in
floats (Q5). Rule 4's priced half is applied at two bounds (Q7); rule 1's denominator is in Q13.

**After the selection rule.** "Extension (reserved). A live workflow within 0.25 point of the line in rule 2 or 3
gets two more runs per task, once, judged in one further batch." The readout names the eligible arms; the
extension tranche is not built. "Search dimensions around one seed" proposes the seed qualification of
`plan_implement_review.orc` ("About 60 runs, 180 to 240 Haiku calls, and one more judge batch per task"), "requested
with the seed-evaluation budget"; it is not in the Budget table's 420 and is out of scope here (Q10). The Stop
rules add: "Only `direct` passes the rule: record 'no workflow qualified at this size'." That is a readout outcome
(a `seed_decision` event), not a `stop` event.

**Step 4 outputs.** "`results/readout.md` (one page: judge gate, calibration table, arm table with intervals, the
rule applied, limits) and `results/seeds.json` (selected programs with hashes, `q`, `c`, intervals, the judge used,
and the criterion, task-list and runtime hashes)", with the pools' `results.json` under `results/pools/`. The
headline exit test: `seeds.json` "exists, names its criterion and task-list hashes, and lists either two to four
programs that passed the frozen selection rule or the stop that prevented it". The readout also states the size
section's limits (differences under about 0.75 point, an ordering among the seeds and equality with direct cannot
be shown; a seed with direct's quality and more calls is dominated by direct, `dominated_by_direct`) and one of its
own: the direct runs ran days before the workflow arms, so a drift of the provider or the machine in between is
inside every arm's difference from direct.

## How the calibration's outcomes change the apparatus

Every outcome below is read from the calibration's results files, written once into the seed evaluation's own
task file (task B1), never written as code. The only calibration outcome that enters code is the selected judge's
model in `spend.CAPS`, written by the authorization task after the owner's approval names it, and checked against
the results file at every start.

| Outcome | Effect on the apparatus | Read from |
| --- | --- | --- |
| The selected judge is Haiku or Sonnet (G3's insensitivity switch included) | One judge per seed pool; `judge-seeds.json` (Step 1f) names it; the per-call worst case and the judge unit's worst case follow the model (USD 0.50 or 2.00 a call, ruling R11) | `results/calibration.json` (`calibration.selected`, `insensitive`, `v4_note`) |
| Neither judge passes; hidden tests become primary | The calibration readout records `stop: no judge passed its gate; hidden-test pass rate is primary; stop for the owner`, and `rules.stop` makes it final for the ledger (ruling R14), so no seed-evaluation start is possible and none is built for this branch. A tests-primary evaluation would need owner thresholds in pass-rate units (rules 2, 3 and the batch check are in points) and a new ledger by R14's archive. Room left: the arm summaries of task A4 take per-run scores as input, so a hidden pass fraction could stand in without new arithmetic | the `decision` event and `calibration.json` |
| 12 to 16 survivors | The task list is the survivors in the chosen list's order (already cut at 16 by `gates.task_gates`); the parity tasks are the first six of them; caps stay the Budget table's, used in part; the batch check's bound is 3 of 32 as a proportion (Q3) | `calibration.json` (`calibration.survivors`) |
| The visible check lacks selecting power | Read from the seed evaluation's own direct runs, not from the calibration: after the direct stage the kit records the rate; under 20%, implement-check-repair and retry never start, `rules.planned_runs` counts them as zero, and the readout says "the check has no selecting power on this set". The calibration's first stage suggests this branch is likely: 11 of 12 direct runs passed the visible check, the twelfth was cut at the call limit (seed-set ledger, 2026-11-25), and the agent ran the visible check itself in every usable probe run | the seed evaluation's run facts (`visible`) |

## Tasks

"Freeze: yes" means the change reaches a paid run only through the post-calibration freeze. Group A is pure
arithmetic on records and can be built and reviewed while the calibration runs; group B touches the runner but not
what may start; group C changes the start rules; group D needs B and C. Each task names its tests; tests use the
kit's stand-ins and fixtures, never a provider CLI, and assert no prompt wording. Implementers run narrow
selectors with at most four workers while a paid tranche runs (Luna plan, ruling L-R6) and `pytest --collect-only`
on new or renamed test modules.

| Id | Files | Change | Proof | Freeze | Size | Depends |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | `experiments/seed_set/selection.py`, `tests/experiments/test_seed_set.py` | Exact arithmetic in the thresholded comparisons (Q5): `rerolls`, `baselines` and `rules` use `gates.mean` (`statistics.mean` of ints is a float); `TAU_Q`, `COST_LIMIT`, `COMPLETION`, `DISTINCTIVE` become Fractions and `calls_k` adds `Fraction(1, 2)`; the `pareto.dominates` call keeps floats (its `tolerances` accepts only int or float, through `pricing.number`), and `bootstrap` stays in floats (display only); `readout.plain` already converts | A test where `q` is exactly `q_direct − 0.5` with means in thirds passes rule 2 (it can fail in floats); `calls_k` of exactly 1.5 is 2; the existing selection tests pass unchanged | yes | S | none |
| A2 | `selection.py`, `test_seed_set.py` | Step 3's missing rules, as pure functions: `visible_power(direct_runs)` (the 20% rule as Q1 rules it, with `rerolls`' `visible_fail_rate` returned beside it); `parity(runs, baseline)` (Q4); the distinctive step per arm by physical calls, retry and implement-check-repair at 2 or more, implement-review-revise at 3 (read from the three programs); rules 2 and 3 on the tasks an arm shares with direct that have at least three usable direct runs (Q6); rule 4's priced half at both bounds, an arm passing only if it passes at both (Q7); rule 1 over the runs Q13 counts; `extension_eligible` (within 0.25 point of the rule-2 or rule-3 line); the cost basis: tokens only when nested sessions are in over 10% of an arm's runs; and a refusal of calls as the cost when the arms do not share one model and effort (two lines over the arms' `model` and `effort`) | One test per rule on hand-built records: rate 19% withholds, 20% launches, cuts and check timeouts in neither count; parity off by 0.6 calls fails; an arm whose third call ran in 19% of runs fails rule 5; an arm that passes rule 4 with cuts at the worst case and fails on metered runs only fails; the nested switch changes the dominance input | yes | M | A1 |
| A3 | `experiments/seed_set/study.py` (a pure `seed_batches`), a new `tests/experiments/test_seed_set_seed_pools.py` | The two batches: the usable runs of each arm (in `arms.json` order, each arm's runs in records order) dealt round-robin into two batches, the first batch of the deal alternating by the task's index in the seed task list, so a three-run arm puts two runs in batch 0 on one task and in batch 1 on the next; the planned 14 runs give 7 and 7; the shape `pool.write_pool` takes (`(records, record, ["final"])`); refuses more than 16 usable runs; one usable run gives one batch | Each run is dealt once; every arm alternates; no batch passes 8; over two consecutive tasks each three-run arm has three runs in each batch; 17 runs refuse | yes | S | none |
| A4 | new `experiments/seed_set/seeds.py`, `experiments/seed_set/gates.py` (`pool_records` keeps the clone id), `test_seed_set_seed_pools.py` | The seed report from records, anchors first as `readout.report` does: `gates.pool_anchor_failures` per batch (records grouped by the batches of the pool's copied `mapping.json`) and `gates.binding_failures`, and on any failure measure-free figures only; then the per-batch control check (reference minus base by the selected judge's bound ratings; a missing batch counts as under 4; Q3); per arm `q`, the hidden pass rate, `c` (Q18), tokens and priced USD at both bounds (Q7), completion (Q13), distinctive share, parity; the baselines (`selection.baselines`) over the seed direct runs, leaving out those whose visible check timed out and tasks with fewer than three usable runs; `select_seeds`; judge calls and their priced cost apart from candidates'; the cut table per arm and call position (a cut run's last call is its physical call count); the extension-eligible arms; the `seeds.json` dict and the readout's arm section with its limits; a no-claim readout keeps measure-free figures only, as `readout.stopped` does; only `direct` passing gives "no workflow qualified at this size" | Fixture tests: a pool with two base anchors in one batch gives an anchor failure and no figure; four of 32 batches under 4 gives no quality figure, three gives one, a pool incident counts its two batches under 4; only direct passing gives the stop text; a run left out as an incident is listed and not scored | yes | M | A1, A2, A3 |
| B1 | `experiments/seed_set/layout.py`, `study.py`, `rules.py` | The seed task list, judge criterion and pool kind: `SEED_EVALUATION` and `SEED_POOL` (`seed`) names; a command `seed-tasks` that writes `results/seed-tasks.json` once from `calibration.json` (decision `qualified`, survivors in the chosen list's order, the selected judge, `v4_note`) and records a `seed_tasks` event with the sha256 of both files, as `probe_readout` does for `calibration-tasks.json`; `tranche_tasks` and `require_tasks` for the tranche; `layout.arm_tasks` (retry: the first six); `require_pool_kind` (the tranche builds `seed` pools only); `pool_criterion("seed")` returns `judge-seeds.json` beside `judge-calibration.json`. `judge-seeds.json` is bound as the two criterion files are: `rules.require_tracked` exempts it, `rules.required_hashes` requires its sha256 in `criterion.json` whenever `criterion.json` names it, and a seed start (C2) refuses unless it is named; a check like `layout.load_criterion` refuses it unless it names exactly one judge, the selected one, the functional rubric and no calibration purpose or block. This is smaller than committing it into the runtime: it is written after the calibration, like the two criterion files, which the runtime keeps untracked by design | `seed-tasks` refuses a decision other than `qualified` and a second write; the retry tasks are the first six survivors; a calibration pool kind refuses the tranche; `judge-seeds.json` naming both judges, another judge or a calibration block refuses; an edit to it after the freeze refuses the next start | yes | M | none |
| B2 | `study.py` (`runs_to_pool`, `write_readout`) | Tranche isolation (hazard e): `runs_to_pool` takes the runs of the pool kind's own tranche (`seed`: `seed_evaluation` alone; `first` and `retest`: neither the seed evaluation nor the Luna smoke); the calibration `readout` refuses once a `seed_tasks` event exists, so seed runs never reach `unpooled_runs` or the calibration's run facts and no second `decision` event is recorded | With calibration and seed runs on one task, the first pool holds only calibration runs and the seed pool only seed runs; `readout` refuses after `seed-tasks`. (`calibration.json` embeds `spend.totals` and `spend.priced` over every tranche in `CAPS`, so it cannot be byte-compared across D2) | yes | S | B1 |
| B3 | `study.py` (`build_pools`, `parser`), `experiments/seed_set/README.md` | Seed pools: for kind `seed`, `pool.pool_runs` and A3's batches go to `pool.write_pool` in place of `pool.pool`; the blinding scan, the incident rules, `MAX_POOLS` and the disk check unchanged; `--kind seed` for `pool`, `judge` and `summarize` | On fabricated, collected and scanned run records (no start needed): a pool of 14 runs builds two batches of 7 plus both anchors, the one judge's command reserves 2 calls, the summary holds both batches' anchors and a hidden result per clone. The path through real starts is D1's | yes | M | A3, B1, B2 |
| B4 | `study.py` (`settle`, a `seed-readout` command), `units.py` (`audit_sessions`), `readout.py` (one heading) | `settle` records `nested_sessions` beside the `sessions` it already records (a one-field change: `audit_sessions` returns the count of session files below the top level of the unit's project store); `seed-readout` loads the summarized `seed` pools, the unpooled seed runs and each run's settle event, calls A4, writes `results/seeds.json` (with the program, criterion, task-list and runtime hashes and those of `seed-tasks.json` and `judge-seeds.json`) and `results/readout.md` as the calibration page from the stored `calibration.json` plus the seed section, and records a `seed_decision` event (never a `stop`). The calibration page's "Offline re-roll baselines" heading names its runs ("calibration Haiku direct runs, not the seed baseline") so the page holds two clearly labelled baselines | On fixture pools: `seeds.json` names its criterion and task-list hashes and lists the seeds or the stop (the plan's headline exit test); "no workflow qualified" writes no `stop` event; a run with a nested session counts it | yes | M | A4, B3 |
| C1 | `layout.py`, `rules.py`, `study.py` (`slot_limits`, `due_jobs`) | Planned runs and slots: `PLANNED["seed_evaluation"]` (`direct` 6, `implement_check_repair` 3, `implement_review_revise` 3, `retry_until_check` 2), `RETESTS` 0, the tranche in `STUDY_TRANCHES` (its incidents count toward the 10% stop, and every freeze then needs its spend terms); `rules.planned_runs` sums each arm over `arm_tasks` and counts a withheld arm as zero; `slot_limits` adds one relaunch per incident slot, as `probing.allowed` does (Q2), beside the cut re-runs. **Room** for a re-run or relaunch is the cap left minus the maximum calls of every arm's planned, unstarted slots over `arm_tasks` (a withheld arm at zero; before the checkpoint, every arm counts), because the four Haiku arms share one cap: today `due_jobs` subtracts only the current arm's unstarted slots, so after the 96 direct starts a cut direct slot would see room, run again, and the last workflow arm would fail its up-front check with the cap spent. `require_spend_bounds` counts a seed pool's judge unit at two batches. The tranche joins `layout.STUDY_TRANCHES` only in D2, together with its `spend.CAPS` row, so no loop over the study's tranches meets a tranche without caps; C1's tests add both in their own process | 16 survivors plan 204 runs and exactly 420 Haiku candidate calls; with one cut direct slot at 16 survivors no re-run starts and every workflow arm still fits its up-front check; with the two arms withheld the same cut runs again; an incident slot gets one more start only where room exists; probe runs never fill a seed slot | yes | M | B1 |
| C2 | `rules.py`, `study.py` | Order and the direct-first checkpoint: `require_order` for the tranche needs a passed smoke, the latest `decision` `qualified`, the `seed_tasks` event matching both files' hashes, `judge-seeds.json` named in `criterion.json`, and the judge of `spend.CAPS`, `judge-seeds.json` and `seed-tasks.json` the same; a command `visible-power` refuses while any direct slot is unstarted, unsettled or due another start (a cut re-run or an incident relaunch, Q2, where room exists), then records the rate (Q1) and whether the parity and implement-check-repair arms launch; no direct start after that event; a workflow start before it refuses, as do those two arms when it says withheld (Q11: implement-review-revise waits too); once a seed start exists, `record-freeze` refuses a `criterion.json` whose selection readings differ from the freeze in force at the first seed start | A workflow start before `visible-power` refuses; at 19% only implement-review-revise starts; a judge mismatch refuses every start; a changed reading in a later freeze refuses | yes | M | A2, B1, C1 |
| C3 | `rules.py` (`require_free`), `layout.Study`, `study.py` (`settle`) | Disk (hazard a, ruling R18): a start is refused with no stop while the filesystem that holds the work root has less than 50 GB free; every other filesystem a start writes to, and that one below 20 GB, keeps the plan's 20 GB stop; `settle` records the agents' tree's size at settlement (`tree_bytes`) before removing it | With a stand-in disk figure: the work root's filesystem at 30 GB refuses and writes no `stop`; at 15 GB the stop is recorded; another written filesystem at 30 GB passes; a settled run names its tree's size | yes | S | none |
| D1 | `experiments/seed_set/rehearsal.py`, `tests/experiments/seed_set_offline_support.py` | A seed stage in the rehearsal: a stand-in plan whose Haiku fixes a deterministic share of a task's units (keyed by the unit, so runs of one task differ and the calibration can qualify, which no rehearsal has reached: ruling R12); after the calibration readout a second `record-freeze` with `judge-seeds.json` and the readings, as the real freeze does; `--seed-tasks N` runs the seed stage on the first N survivors (direct, `visible-power`, the workflow arms, seed pools with the selected judge, summaries, `seed-readout`), with one injected usage-limit cut and one incident; a second run, or a stand-in setting, where every direct run passes the check, rehearses the withheld branch; until D2 the rehearsal sets the tranche's authorization and caps in its own process | `rehearsal.json`: the calibration `qualified`; `seeds.json` written; every planned arm run in the launched branch and only direct and implement-review-revise in the withheld one; priced totals equal the stand-ins' usage; the calibration `readout` refuses after `seed-tasks` | yes | L | A1 to C3 |
| D2 | `experiments/seed_set/spend.py`, `tests/experiments/test_seed_set_spend.py` | The authorization, only after the owner's approval row: `CAPS["seed_evaluation"]` = 420 `claude-haiku-5-5` candidate calls and 32 calls of the selected judge; the tranche leaves `UNAUTHORIZED` (`extension` stays); `test_caps_are_the_plans_budget` gains the row; the tranche joins `layout.STUDY_TRANCHES` in the same change | The caps test; a start of the other judge refuses | yes | S | calibration readout, owner approval |

**Gate after D2, the coordinator's (not an implementer task):** the post-calibration freeze, one for this plan and
the Luna plan's T1 to T8 (L-R2): the anchors on the merged code; `judge-seeds.json` written beside
`judge-calibration.json` and named in `criterion.json`'s hashes; in `criterion.json`, the seed evaluation's `spend`
terms and the **selection readings** of Q1, Q3, Q4, Q6, Q7, Q13 and Q18 as ruled here, which do not change after the
first seed start (C2 refuses a freeze that changes them); the CLI pin renewed if the CLI updated; `record-freeze
--reason`. Then the rehearsal with D1's seed stage on the frozen code (the owed rehearsal, as ruling R12 took the
calibration's), `seed-tasks`, the tranche's spend row with a meter reading, and the first start. No freeze is
recorded between the first seed start and the seed readout except an apparatus fix that leaves the programs and
the readings unchanged (`layout.counted_runs` does not catch a program change in the middle of a tranche).

**Where the extension attaches (not built):** an `extension` entry in `spend.CAPS` (192 Haiku candidate and 16
judge calls, the Budget table) and `layout.PLANNED` (two runs per task of the arms A4 lists as extension-eligible),
its own pool kind judged in one further batch per task, after a new owner approval.

**Room for Luna (not built).** The Luna plan's placement step (L-R5) is its own tranche and pool kind after the Luna
smoke and reads the calibration's records, not the seed evaluation's. A Luna arm of the seed evaluation would need
a `PLANNED` and `CAPS` entry under its own approval (the arms `direct_luna` and `retry_until_check_luna` exist), a
third batch once a task has more than 16 usable runs (A3 refuses that today), and cost in priced tokens: A2 refuses
calls as the cost when the arms differ in model, so that choice is made then, not here.

## Caps and terms

**Caps** (Budget table, "Seed evaluation | 420 / 0 | 32 of the selected judge | Not authorized"):

| Survivors | Direct | Implement-check-repair | Implement-review-revise | Retry parity | Candidate calls reserved | Judge calls (2 per pool) | Planned runs (10% stop) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 96 | 144 | 144 | 36 | 420 | 32 | 204 |
| 12 | 72 | 108 | 108 | 36 | 324 | 24 | 156 |
| 16, check without selecting power | 96 | 0 | 144 | 0 | 240 | 32 | 144 |

A unit reserves its maximum calls (`spend.reserve`), so at 16 survivors with every arm launched the candidate cap
is exactly the planned reservations. With C1's room rule no cut slot re-runs and no incident relaunches there, and
a pool whose judge is cut cannot be rebuilt (rulings R1 and R10). Without C1, `due_jobs` would let a direct re-run
take a workflow arm's reservation. With fewer survivors, or once the checkpoint withholds the two arms (180 calls
at 16 survivors), there is room for workflow re-runs; the direct stage is closed by then.

**Terms the coordinator sets at the freeze** (ruling R4; `layout.spend_terms`; the kit has no default):

- the priced ceiling `ceiling_usd.seed_evaluation`;
- the per-call worst cases: ruling R11's USD 0.50 for Haiku and USD 2.00 for Sonnet stand unless the calibration's
  metered calls show a larger `largest_call_usd`, in which case the figure rises and the freeze is recorded again.
  At those figures the worst case is USD 210 for the 420 candidate calls, and USD 16 (Haiku) or USD 64 (Sonnet) for
  the 32 judge calls;
- `record-freeze` refuses a ceiling below two units in flight at the largest unit's worst case: with C1's two-batch
  judge unit, USD 3.00 with a Haiku judge and USD 8.00 with a Sonnet judge.

**Proposed method for the ceiling:** from the calibration's `settle` events, take the largest priced completed
Haiku candidate call, the cut rate of Haiku runs, and the largest priced call of the selected judge; the ceiling is
the planned reserved candidate calls times that candidate call's price, plus the expected cuts at USD 0.50 each (a
cut call has no final usage and settles at the worst case), plus the 32 judge calls at the judge call's price, times
two, as R11 set the calibration's at about twice what earlier sessions suggested. The calibration's first stage
priced its metered candidate calls at USD 0.0131 to 0.0211 each (seed-set ledger, 2026-11-25). Since the worst case
passes USD 100, the approval is the owner's in any case (budget delegation).

**The spend row must also state:** the meter rule in force (ruling R13 as replaced on 2026-11-25: 20 points of the
weekly meter a day); the stages (direct first, the checkpoint read by the coordinator before any workflow stage);
a stage gate like the calibration's (seed-set ledger, 2026-11-23: unrated runs at a stated share hold further
stages for the owner), with its share; the free-disk rule (C3); the login refresh procedure; and how a usage-limit
pause is resumed.

## Hazards

| Hazard | Proposed handling | Open |
| --- | --- | --- |
| (a) Disk. A unit's own test runs write into its tree (its `/tmp` is there): run-23 of the calibration wrote 5.6 GB, a whole-suite run holds about 15 GB, and `rules.require_free` records a final stop under 20 GB at any start. With 204 runs, three-call units of up to 70 minutes and two in flight, the exposure is larger. Seed pools hold 18 clones (14 runs and four anchors), about 2.5 GB at 141 MB a clone | C3 turns ruling R18 into code for the work root's filesystem: a start below 50 GB free there waits (refused, no stop), so a stop needs a fall of about 30 GB during one in-flight unit; the other written filesystems keep the 20 GB stop. `tree_bytes` gives each unit's tree size at settlement, a lower bound on its peak, so the floor can be revisited from data. The agents' environment is not changed (a size-limited `/tmp` would change the form between calibration and seed evaluation). Owner action that would add room: lower the root reserve (`tune2fs -m 1`, ruling R18's row) | none (Q8 ruled) |
| (b) Candidate runs cut at the 20-minute call limit while waiting on broad test runs (R17; one of the first 12 calibration runs despite the prompt's sentence; a first-call cut of `implement_review_revise` in the third smoke) | Scored as the plan says: a failed run, 0, a natural failure (not an incident, not a usage-limit cut); `(0, False)` in the offline baselines; in rule 1's denominator as a run that does not complete (Q13); in neither count of the 20% rule (Q1). A cut on a later call loses the whole run's patch (see "Facts the plan rests on"). The readout reports the cut rate per arm and per call position, and cut runs' priced cost apart. Not tuned again (R17's row). What this does to rule 1 is in [For the owner's approval request](#for-the-owners-approval-request) | none |
| (c) The login guard (R16) refuses a start unless the token outlives the unit plus 15 minutes: 85 minutes for a three-call unit, 145 minutes for a two-call judge unit. Usage limits pause every start (R1, R2) | A refused start reserves nothing and is not a stop; `candidates` starts only what has not started, so the operator runs the stage again after the owner's side has refreshed. A cut slot runs again only inside its cap's room (R10, C1). The tranche spans days (about 200 runs at two in flight; the first calibration stage ran 12 runs in 35 minutes), so it meets several refreshes and the daily meter line | none |
| (d) "Resumed once with `resume.sh`" against "a unit is launched once, never retried or relaunched" (`spend.reserve`) and the disabled resume scripts | C1 reads it as the probe's rule: the incident's slot starts once more as a new unit, from scratch, inside the cap's room; the incident stays recorded and counts toward the 10% stop; a second incident excludes the slot and lists it. No resume path is built | Q2 |
| (e) Calibration runs in the seed baseline, and seed runs in calibration counts | Fresh by construction: slots are counted per tranche (`due_jobs`) and the probe-run reuse in `slot_limits` applies only to `calibration`. Not yet safe: `runs_to_pool` gives a pool every non-Luna run of its task, and `unpooled_runs` and `write_readout` take every non-smoke run of a calibration task. B2 filters `runs_to_pool` by tranche and makes the calibration `readout` refuse once `seed_tasks` exists; caps, `planned_runs`, `stop_reasons` and the early look are already per tranche | none |
| (f) Blinding. One identity hit refuses the whole pool (`blinding.scan_pool`, a recorded limit); a seed pool holds 14 runs, so a hit costs a task's every arm, about three times the calibration's exposure | Kept as frozen; the readout lists such tasks as missing and their two batches count as under 4 (Q3) | none |

## Decisions

The coordinator has ruled Q1, Q3, Q7, Q8 and Q13; the others are the recommended defaults in force. Q1, Q3, Q4, Q6,
Q7, Q13 and Q18 change how a selection rule reads, so they are written into `criterion.json` at the
post-calibration freeze and do not change after the first seed start.

| Id | Decision | In force | Why | What it makes harder |
| --- | --- | --- | --- | --- |
| Q1 | What counts for the 20% rule (ruled) | The rate is over the direct runs whose final patch the host visible check ran on: numerator, those whose check did not pass. Cuts, failed runs without a patch and checks past their bound are in neither count; `rerolls`' `visible_fail_rate` (every run not passing) is shown beside it. Stated in the approval request and frozen before the direct stage | Retry and repair act only on a completed call with a failing check | If cuts are frequent the rate rests on fewer runs |
| Q2 | How an incident is "resumed once" | A new unit from scratch, once, inside the cap's room (the probe's rule); never `resume.sh` | The kit never resumes, `spend.reserve` refuses a second start of a unit, and the probe set this precedent | A relaunch is a new draw and costs a full run; at 16 survivors with every arm launched there is no room, so incidents are excluded and listed |
| Q3 | The batch check (ruled) | No quality claim when the batches under 4 are more than 3/32 of the planned batches (two per survivor; exact: `under × 32 > 3 × batches`); a missing batch (a pool incident, a blinding hit, the second batch of a task with one usable run) counts as under 4 | The plan's bound is a proportion of the batches it names | At 24 batches three failing batches already end the claim |
| Q4 | Retry parity's "offline figure" | `Q3` and `Q3_calls` over the six parity tasks; "every run completes" as in Q13 | Retry has at most three attempts | None beyond the reading |
| Q5 | Floats in `selection.py` | Exact Fractions (A1), floats only at `pareto.dominates` and the bootstrap | The kit's ruling on B1 (2026-11-12) requires exact comparisons at thresholds; an exact 0.5 gap had failed G3 in floats | Nothing |
| Q6 | Rules 2 and 3 for retry, which runs on six tasks | Compare on the tasks the arm shares with direct that have at least three usable direct runs (all of them for the other arms, as far as direct has them) | `q_direct` over 16 tasks against retry over six compares different tasks | Retry's `q` rests on six tasks; its interval is wider |
| Q7 | Rule 4's priced tokens with cut calls priced at the worst case (ruled) | Applied at two bounds: every run with cut calls at the per-call worst case, and metered runs only (no missing usage); an arm passes only if it passes at both; both figures are reported, cut runs' cost apart. Reading partial usage from a cut session is not built | A cut call's placeholder is about 25 times a metered Haiku call (USD 0.0131 to 0.0211); either bound alone could pass an arm the other fails | An arm near the line fails on whichever bound is worse |
| Q8 | The disk floor in code (ruled) | C3: the 50 GB start floor on the work root's filesystem, the 20 GB stop elsewhere as written, `tree_bytes` recorded | R18 is an operator rule today; a start during another unit's peak could end the tranche | The tranche waits rather than stops; long waits meet more login refreshes |
| Q9 | "3,600 s per run" | Keep `study.unit_sec` (1,800 s and 4,200 s) and correct the seed-set plan's text by a ledger row there | It is what the smoke and calibration ran under, and the login guard is computed from it | A three-call run may run 10 minutes past the plan's figure |
| Q10 | The seed qualification of `plan_implement_review.orc` | Out of this apparatus | The program does not exist, is not authorized and is not in the Budget table's 420; it also needs a third judge batch | It needs its own plan and approval; deferring it changes the request (see below) |
| Q11 | Does implement-review-revise wait for the direct stage | Yes: every workflow starts after `visible-power` | "Direct runs first" names no exception; one checkpoint is simpler | Implement-review-revise starts later, days after direct (a stated limit) |
| Q12 | `UNAUTHORIZED` until the owner's approval | Keep; the rehearsal sets the authorization in its own process until D2 | The plan says not authorized; a code path that could start it before the approval is worse than a later rehearsal | The frozen rehearsal comes after the approval |
| Q13 | Rule 1's denominator and "complete" (ruled) | A run excluded as an incident or as contaminated leaves the denominator and is listed; a cut stays in it as not complete; a usage-limit cut is no observation; `BLOCKED` is complete | The program returning `BLOCKED` finished inside its envelope; an incident is the apparatus's fault, a cut is the run's outcome | Cuts weigh fully against rule 1 |
| Q14 | One freeze with the Luna plan's tasks | Yes (L-R2): one anchors run, one rehearsal | Each freeze costs an anchors run of about 50 minutes and a rehearsal | A fault in either plan's code holds both |
| Q15 | A re-run reserve at 16 survivors | None: R10 holds; the approval request states that a cut or an incident then loses its observation | Allowance does not move between tranches; counting settled units at their physical calls would free room but changes the most reviewed guard | A run lost to a usage limit at 16 survivors is not replaced |
| Q16 | How nested sessions are counted | Session files below the top level of the unit's project store, recorded at settle (B4) | `audit_sessions` already separates them; the expected count is zero (see "Facts the plan rests on"), which the record shows | Nothing |
| Q17 | Which comparisons get an interval | The differences from direct, as `select_seeds` does | The quoted sentence ties the interval to "each difference from direct" | Rule 3's margin against `Q(k)` is reported as a point figure only |
| Q18 | `c`'s denominator | Every run that is an observation, failures and cuts included (incidents, contaminated runs and usage-limit cuts out) | The driver: "A timeout, invalid submission or task failure is an outcome whose consumption still counts" | None |

## For the owner's approval request

What the coordinator puts to the owner with the seed evaluation's request, with the evidence and the coordinator's
recommendation where one is given.

- **Rule 1 on cuts.** 48 runs an arm (16 tasks, 3 runs) at 95% allow two that do not complete. At the calibration
  first stage's cut rate (1 in 12), even a one-call arm passes with about 20% probability, and a three-call arm less.
  The likely result is "no workflow qualified at this size" for a reason that is not quality. No recommendation yet:
  the calibration's full cut rate decides.
- **No live test of the new paid paths.** The last smoke predates ruling R17's prompt change to the three workflow
  programs, a two-batch judge has never run live, and at 16 survivors the judge cap is 32 of 32 (no rebuild after a
  cut). Either a seed smoke (its own small tranche and spend row) or an accepted risk. Recommendation: a seed smoke.
- **Q10.** The seed-set plan says the seed qualification of `plan_implement_review.orc` "is requested with the
  seed-evaluation budget"; deferring it, as this apparatus does, changes the request.
- **Q1, Q2 and Q9 as they will be frozen:** the visible-check rate over runs whose patch the host check ran on; an
  incident relaunched once as a new unit, not resumed, and only inside the cap's room; the kit's per-unit limits of
  1,800 s and 4,200 s in place of "3,600 s per run".
- **Disk.** No candidate start while the work root's filesystem has under 50 GB free (Q8); `/home` needs room first
  (on 2026-11-25 it had 24 to 27 GB free; lowering the root reserve needs the owner's `sudo`).

## Where the seed-set plan is ambiguous or disagrees with itself or the code

- "3,600 s per run" (Step 3, Envelope) against the kit's `study.unit_sec` (Q9).
- "resumed once with `resume.sh`" against `spend.reserve` ("never retried or relaunched"), the disabled resume
  scripts and the probe's relaunch practice (Q2).
- "more than three of the 32 batches" assumes 16 survivors; Step 2 allows 12 to 16 (Q3).
- "the visible check failed in under 20% of them": failed is undefined for runs with no patch (Q1).
- "the offline figure for those tasks" (parity) names no `k` (Q4); "every run completes" and rule 1's "complete"
  are undefined for `BLOCKED` results, cuts and excluded runs (Q13).
- Retry runs on six tasks, while rules 2 and 3 compare with `q_direct` over all tasks (Q6).
- "names every comparison whose interval spans the tolerance" does not say which comparisons (Q17).
- The Budget table's 420 equals 16 survivors at maximum calls, while ruling R1 and the Stop rules assume cut slots
  run again "from the same cap"; at 16 survivors with every arm launched there is no room (Q15).
- "Search dimensions" says the seed qualification "is requested with the seed-evaluation budget", which the Budget
  table does not include (Q10).
- "Direct runs first" does not say whether implement-review-revise, which the 20% rule does not withhold, waits
  (Q11).
- Step 1f lists `judge-seeds.json` among the freeze's files; the README (ledger, 2026-11-17) writes it after the
  calibration. Consistent once it is written at the post-calibration freeze, and bound there by B1.
- Code: `selection.py` compares in floats, against the kit's exact-arithmetic ruling on B1 (Q5);
  `gates.pool_anchor_failures` requires one base and one reference per pool, which a two-batch pool cannot meet;
  `pool.pool` puts every plain run in one batch, which passes ten repositories; `runs_to_pool`, `unpooled_runs`
  and `write_readout` do not separate tranches (hazard e); `study.due_jobs` counts room against the current arm
  only, though the seed evaluation's arms share one cap (C1); `rules.require_spend_bounds` counts a judge unit at
  one batch; `judge-seeds.json` is neither exempted by `rules.require_tracked` nor named by
  `rules.required_hashes` (B1).

## What this plan makes harder

- Seed pools have two batches; the calibration's per-pool anchor checks and judge gates do not apply to them
  unchanged, and any comparison across the two kinds of pool reads per batch.
- An arm added to the seed evaluation (a Luna arm, the plan-implement-review seed) needs a third batch, a new judge
  count and its own approval.
- `seed-tasks.json` is written once and the calibration `readout` refuses after it: the seed task list cannot follow
  a recomputed calibration without a new ledger (R14's archive).
- The selected judge's model is written into `spend.CAPS` at the authorization; changing judge mid-tranche is not
  possible.
- The selection readings are frozen at the first seed start; correcting one afterwards needs a new ledger.
- An incident is relaunched from scratch, not resumed, and only where the cap has room, which at 16 survivors with
  every arm launched it does not.
- The disk floor makes the tranche wait instead of stop.

## Not verified by reading

- That the stand-in CLI can make a task's runs differ by a key of the unit (D1); no shared counter outside the
  sandbox was checked.
- A three-call unit's disk peak (`tree_bytes` gives only its size at settlement) and the tranche's wall clock; both
  are estimates from the calibration's first stage.
- Whether `summarize.anchor_scores`' `total` equals the functional quality score; A4 reads the bound clone ratings
  instead.

## Ledger

| Date | Entry | Detail |
| --- | --- | --- |
| 2026-11-25 | The plan (planning, read-only; zero spend) | Written from a read of `main` on 2026-11-25 (the seed-set plan to ruling R18, the Luna plan to L-R9, the kit and the comparison harness); no code changed, no task started, no provider call |
| 2026-11-25 | Coordinator: the plan is taken as the working plan; the recommended defaults of Q1 to Q18 are in force until a row here changes one | Planning was done by an Opus subagent, not the Fable planner the role table names: the Fable weekly meter stood at 86% and is kept for running the calibration. Tasks A1 to A3 (pure functions, no start rule touched) may be built now; an independent review of this plan comes before A4 and the B, C and D tasks. Q8 puts the seed-set plan's ruling R18 in code for later tranches; the calibration in flight stays on its frozen code. Q12 stands: the tranche stays unauthorized until the owner approves its spend |
| 2026-11-25 | Revision after the independent review (accept after fixes; planning, read-only; zero spend) | The coordinator's rulings applied: C1 counts room against every arm's unstarted reservations (the shared cap); B1 binds `judge-seeds.json` in the freeze and checks its shape; A1 keeps floats at `pareto.dominates`; A3 alternates the first batch by task; A4 runs the anchor and binding checks first; Q1, Q3, Q7, Q8 and Q13 ruled; B2 makes the calibration `readout` refuse after `seed_tasks`; C3's floor applies to the work root's filesystem only; three facts read in the code moved into the body; a section for the owner's approval request added. **This row replaces, for Q1, Q3, Q4, Q6, Q7, Q13 and Q18, the words "until a row here changes one" of the row above:** those seven are written into `criterion.json` at the post-calibration freeze and do not change after the first seed start; the other decisions stay in force until a row here changes one |
| 2026-11-25 | Coordinator: the tranche joins `STUDY_TRANCHES` with its caps | C1 planned to add `seed_evaluation` to `layout.STUDY_TRANCHES` while D2 adds its `spend.CAPS` row only after the owner approves; between the two, code that loops over the study's tranches and indexes `CAPS` (`layout.tranche_judges` is one path) would raise on `main`. Both are added in D2; C1 and D1 add them in their own process |
