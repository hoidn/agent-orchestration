# Seed-Set Calibration Plan

**Status: Plan (not started).** This page plans the scaled-down research step
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
result types every seed returns (the interface to the harness); it is not
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
`calibration/direct_sonnet.orc`, which differs from `direct.orc` in the model
literal only. Compile each and run each once through the public CLI behind
the shims with a scripted provider.

**1d. Runner and readout (1.5 days), `experiments/seed_set/study.py`.** One
run: `prepare.run_arm(spec=ArmSpec(...))` with `COMPARE_CLAUDE_MODELS` and
`COMPARE_MAX_CALLS` set, launch, `collect`, `scan --hash <fix>`,
`check_first_attempt` on the final patch (the visible result, stored with the
run record), then delete the run's `cand-*` trees; four runs at a time. One
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

## Step 2: Calibration (paid)

**Smoke,** on the last reserve task, which then leaves the reserve: one direct
run per model, one run of each workflow, then one pool scored by both judges.
Pass: sessions show only the bound models, the scans are clean, and
`results.json` holds both judges' ratings and a hidden result for every
clone. Whether token receipts are complete is recorded.

**Candidates (80 Haiku, 20 Sonnet):** on the 20 drawn tasks, `direct.orc` four
times (so a task's Haiku mean does not rest on one or two draws) and
`direct_sonnet.orc` once.

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
| 2026-11-11 | Owner requirement: "part of the seed's simplicity req should be a challenging loc limit (eg <50 lines of orc". Recorded as the size limit in step 1c: under 50 physical lines per seed program, `common.orc` exempt and frozen. Coordinator's reading of the counting rule; the four programs pass at 22, 31, 40 and 45 lines (44 to 67 if `common.orc` were counted). |
