# Seed-Set Calibration Plan

**Status: Plan; zero-spend preparation in progress, no spend yet.** This page plans the scaled-down research step
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
- The five programs declare `(:target-dsl "2.40")` (they build the same
  program as at 2.39).
- Blinding: candidates and anchors are built in random order; every pooled
  patch is scanned for model, arm and program names before any judge call and
  a hit refuses the pool; each rating is bound to the digest of the patch the
  judge read.
- A readout that ends in a stop prints no quality figure.

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
| T2, easy | At most two source files and 60 lines; the statement is the commit message; the failing test is in the tree |
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

**Search dimensions around one seed (proposed 2026-11-12; not authorized, not yet built).**
Owner question: is it better, in the Pareto sense, to plan with a mid model
and implement with a weak one, to use the weak model for both, or the mid
model for both, with the reviewer's strength as a further axis. The owner's
framing: one seed and declared search dimensions, not several seeds. No
measurement in this repository answers the question, and the four programs
above cannot: none has a plan step and all run on Haiku.

The seed is one program, `plan_implement_review.orc` (new, under 50 lines):
plan, implement, review, revise at most once. The dimensions a later search
may vary, each a binding of that program and not a new program:

| Dimension | Values |
| --- | --- |
| Planner | absent, Haiku, Sonnet |
| Implementer | Haiku, Sonnet |
| Reviewer | absent, Haiku, Sonnet |
| Effort per role (owner, 2026-11-13) | for each role that is present, one of the CLI's levels `low`, `medium`, `high`, `xhigh`, `max`; chosen per role, independently of that role's model |
| Revision rounds (reviewer present) | 1, 2 |
| Conversation (owner decision 11 of the roadmap keeps Agent Sessions) | each later step of a role starts fresh, or continues that role's session; only between steps bound to one model |

That is 18 model placements before effort, rounds and conversation. With effort per role the
space is no longer small: three roles, two models and even three effort levels give 216
combinations, so a search (or successive halving) earns its cost there, where a grid did for 18. `direct.orc` is the point (absent,
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
