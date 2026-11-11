# Experiment-design review: ORC roadmap "Usable Pipelines First, Then Program Evolution"

Task id: `review_plan_roadmap_experiment_design`. Role: reviewer (read-only). Artifact: draft roadmap
`docs/plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md` (Phase 4 PQ-1c, Phase 5, Phase 6, stop
rules, Process rules). No repository edits, no provider calls, no test suites. Arithmetic:
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/roadmap-review/experiment-design-power.py`
(output in `experiment-design-power.out` beside it).

Claim tags: **[C]** computed by that script or by closed form shown here; **[V]** verified by reading the cited
file; **[I]** inferred (my reasoning, not checked against a file or a run).

## Verdict

As written, the Phase 5 benchmark cannot answer its own question, and its stop rule would decide the project's
quality claim mostly by chance. With 30–50 tasks and one run per program per task, the smallest difference
detectable at 80% power is 16–29 pass-rate points, not 10; power for a true 10-point gain is 14–34%. The stop
rule is a bare point-estimate threshold applied to about seven workflows that share one direct run: with no true
effect at all, some workflow clears the bar in 29–51% of experiments, and a true 15-point gain is frozen as a
null in 19–26%. Three further defects are independent of sample size. The roadmap does not say which tests
select and which tests score, and scoring-test selection alone yields +15 to +25 points with zero skill. Its bar
("10 points at up to 3× the tokens") is not the binding definition of "better" (Pareto dominance on priced,
metered cost), and metering has never been available in a live run. Phase 6b has no split design, so its winner
would "beat" the incumbent by 10 points in 42–84% of runs where nothing is better. The direction is right:
executed tests on small external tasks is the correct replacement for the rubric. The fix costs about the same
provider calls as the roadmap's real (understated) call count, spent on two or three live arms with replicates
instead of eight programs once each.

Findings: **5 blockers, 8 major, 6 minor.**

## Headline numbers

All [C]. `psi` is the share of tasks on which two programs disagree in a single run. Two runs of the *same*
program already disagree on 13–33% of tasks under plausible task mixes (per-task pass probability Beta-distributed
with mean 0.5–0.85), so 0.2–0.4 is the plausible range for a workflow against direct.

| Quantity (one run per task, paired, one-sided α = 0.05) | n = 30 | n = 40 | n = 50 |
| --- | --- | --- | --- |
| Power for a true +10 points (psi 0.2 / 0.3 / 0.4) | 0.18 / 0.15 / 0.14 | 0.26 / 0.21 / 0.20 | 0.34 / 0.28 / 0.23 |
| Minimum detectable gain at 80% power (psi 0.2 / 0.3 / 0.4) | 20 / 25 / 29 pts | 18 / 22 / 25 pts | 16 / 19 / 22 pts |
| Same, Bonferroni over 7 workflows | 27 / 33 / 38 pts | 23 / 29 / 33 pts | 21 / 26 / 29 pts |
| 95% interval half-width on the difference | ±16 / 20 / 23 pts | ±14 / 17 / 20 pts | ±12 / 15 / 18 pts |
| P(bar "met" by some workflow of 7, no true effect; direct 0.5 / 0.7) | 0.51 / 0.46 | 0.42 / 0.36 | 0.35 / 0.29 |
| P(bar missed → freeze, true +15; direct 0.5 / 0.7) | 0.26 / 0.22 | 0.24 / 0.21 | 0.23 / 0.19 |

Tasks needed to detect +10 points at 80% power with one run per task: 122 / 183 / 245 for one comparison
(psi 0.2 / 0.3 / 0.4); 155 / 233 / 312 for two pre-registered comparisons; 214 / 322 / 431 for seven.

Replicates buy the same precision on fewer tasks. Design "60 tasks × 6 direct runs × 4 workflow runs" under the
three-region rule of finding B2: true effect 0 → refute 0.85, inconclusive 0.15, false support 0.00; true +15 →
support 0.98; true +10 (exactly at the bar) → support 0.69, inconclusive 0.31, never refuted. The cheaper
"40 tasks × 5 × 3" supports a 15-point bar (support 0.95 at +15) but refutes a true null only 53% of the time.
The roadmap's "40 × 1" under the same rule is inconclusive in 84% of true-null experiments.

## Findings, most severe first

### Blockers

**B1. Phase 5 step 3 cannot resolve its own 10-point bar.** Section: Phase 5, benchmark step 3 and exit test.
- Evidence: table above [C]. Exact McNemar power for +10 points is 0.14–0.34 across n = 30–50; the detectable
  difference is 16–29 points. Bootstrap intervals do not help: they are honest but ±12–23 points wide, so the
  exit test's "reports, with bootstrap intervals, whether any workflow Pareto-dominates direct" will nearly
  always report "cannot tell".
- The roadmap's own findings row for Phase 5 carries a power statement for the old rubric (σ ≈ 1, 16 samples
  per arm) and none for the new binary measure [V, roadmap line 40].
- Proposed text: replace "once per task" with "direct ×6 and each live workflow ×4 per task on 60 evaluation
  tasks (or 40 tasks × 5 × 3 with the bar raised to 15 points)"; add "the plan states the minimum detectable
  difference before spend, from the pilot's observed discordance".

**B2. The stop rule is a point-estimate threshold with no error control, and it is one-sided and terminal.**
Section: Phase 5 stop rule; Phase 6 opening condition.
- Evidence [C]: with no true effect, some workflow of seven shows ≥ +10 points in 29–51% of experiments (they
  share one noisy direct run, so their errors are correlated). A true +15 is "frozen" in 19–26%; a true +10 in
  42–45%. Multiple comparisons are not mentioned anywhere in Phases 5–6 [V].
- A null at this power does not justify "the quality claim is frozen". It justifies "not shown at this budget".
- Proposed text (three regions, frozen in the criterion before spend; Δ is the paired, task-clustered difference
  in pass rate between a pre-registered primary workflow and direct on the same model; at most two primaries,
  Holm-adjusted one-sided 95% bounds [L, U]):
  - **Support:** for some primary, L > 0, the estimate is ≥ 0.10, priced cost is ≤ 3× direct, and no
    direct-family baseline (B4) dominates it. Phase 6 may open.
  - **Refute:** for every primary, U < 0.10. The quality claim is frozen for this family and model tier; Phase 6
    does not open.
  - **Inconclusive:** anything else. One pre-declared extension (the reserved tranche: two more runs per task per
    arm, each look tested at α/2). If still inconclusive: record "unresolved at this budget"; the claim stays
    "not shown", is not called refuted, and Phase 6b does not open.

**B3. Selector, repair loop and score are not separated; as written the result is either leaked or signal-free.**
Section: Phase 5 step 3 ("best-of-3 with executed-test selection", "implement–test–repair"); Phase 4 ("a
best-of-N consumer selected by executed tests").
- The roadmap never says which tests the selector and the repair loop execute [V].
- If they are the scoring tests: best-of-3 becomes "any of 3 passes". That alone adds +19 points (per-task pass
  probability Beta(0.5, 0.5), mean 0.5), +25 (uniform) or +15 (mean 0.7) with no selection skill [C, closed form
  E[1 − (1 − θ)³] − E[θ]]. The bar is cleared by construction. The harness already treats scoring with
  agent-runnable tests as a defect (audit §3.1, unverified; the harness keeps `hidden/` outside every candidate
  [V, `experiments/compare/README.md` lines 28–35]).
- If they are the repository's pre-existing tests at base: those are green at base, so nothing branches. Phase 1
  recorded exactly this: "`dev-check` … passed on the first try in every evaluation that ran it", so
  `implement_check_diagnose_repair` realized one call, like `direct` [V,
  `docs/reports/2026-10-18-orc-structural-search-phase1.md` lines 62, 385–388].
- Proposed text: "Each task has a *visible* failing check (a reproduction test or a declared subset of the
  fail-to-pass tests) given identically to every arm including direct, and a disjoint *hidden* scoring set
  (remaining fail-to-pass tests plus the regression tests) that no arm, selector or repair loop can read or run.
  Tasks without a visible failing check are excluded. Selection and repair use visible tests only; pass/fail is
  the hidden set only."

**B4. The bar is not the binding definition of "better", and the cost axis does not exist yet.** Sections:
Phase 5 exit test and stop rule; Phase 6 fitness; Dispositions (backlog row).
- Binding rule: "better" is Pareto dominance over quality and model-aware cost; A dominates B iff
  q_A ≥ q_B − τ_q and c_A ≤ c_B(1 + τ_c), with one strict [V, `docs/design/orc_structural_search_driver.md`
  lines 939–949]. A workflow at 3× cost cannot dominate direct; the exit test ("Pareto-dominates direct") and the
  stop rule ("+10 points at ≤ 3× tokens") are two different criteria, and the second is not "better" [I].
- "Three times the tokens" is not model-aware, yet the step varies model placement. The binding unit is metered
  tokens by category (input, output, cache read, cache write) × a per-model price table frozen in the criterion
  [V, driver lines 1036–1061]. Raw token ratios are dominated by cache reads [I].
- Metering has never worked in a live run: "All 79 log rows record `consumption: "unavailable"`" (Phase 1) and
  "Metering is not wired" (three-arm) [V, Phase 1 report lines 102–103, 313–315]; "The evaluated runtime
  persists no provider usage" [V, driver line 1009]. The calls proxy is admissible only when every candidate
  uses one (model, effort) pair, which model placements break; otherwise "a candidate without metered cost has
  cost `unavailable`, is not placed on the frontier" [V, driver lines 1055–1061]. The roadmap keeps token
  accounting only as a retained backlog item, in no phase [V, roadmap line 217].
- No τ_q, τ_c or quality floor is named, though the criterion must predeclare them [V, driver lines 945–965].
- Proposed text: "Step 2 exit gate: every pilot row has complete metered usage; a price table with source and
  date is frozen in the criterion together with τ_q, τ_c and the quality floor. Cost is priced metered tokens per
  task, all calls of the run included. 'Better' is claimed only by dominance over a direct-family baseline of
  equal or higher cost (direct on each model; direct retried up to three times against the visible check). The
  10-point/3× region is a decision threshold for opening Phase 6, not a 'better' claim."

**B5. Phase 6b has no split design and drops the gate that makes selection meaningful.** Section: Phase 6b table
(Fitness, Apparatus), exit test.
- Winner's curse [C]: if every generated program is exactly as good as the incumbent, the best of 8 / 20 / 40
  candidates on a 40-task search split shows a mean apparent margin of +8 / +10 / +12 points and "beats" the
  incumbent by ≥ 10 points in 42% / 56% / 67% of runs; on 20 tasks, 63% / 77% / 84%.
- "Fresh tasks" do not exist: Phase 5 assembles 30–50 tasks and uses all of them for the table [V, roadmap lines
  147–156]. The boundary invariants require three sets: adaptive search data, validation data, and a sealed
  promotion holdout opened only after selection freezes [V,
  `docs/design/workflow_lisp_program_search_boundaries.md` lines 73–76]. The driver also requires the authored
  reference seed to be re-run on the validation split beside the finalists [V, driver lines 970–972]; comparing a
  finalist against the incumbent's Phase 5 number is biased in both directions [I].
- "Reused without its qualification gates" contradicts "the calibrated-evaluator gate stays a precondition of
  any adaptive claim" [V, driver lines 965–968; roadmap line 188].
- The number of generations, population size and proposer model are not fixed; "a fixed budget set at phase
  start" does not stop repeated peeking at the comparison [I].
- Proposed text: see the corrected Phase 6 protocol below; replace "without its qualification gates" with
  "with the Phase 5 family and measure qualification as its gate; the receipt machinery is not reused".

### Major

**M1. The qualification in step 2 is weaker than the binding rule, and it is not zero-spend.** Section: Phase 5
step 2.
- Family (b) qualification "shows the oracle accepting two structurally different correct submissions and
  rejecting a broken one" [V, driver lines 606–607]. The roadmap checks only "fail at base, pass at the reference
  fix" [V, roadmap lines 148–151]: it never tests whether the tests over-fit the reference implementation, which
  is the "hidden tests pin internal names" failure of the earlier family (audit §3.3, unverified).
- `AGENTS.md` requires a *separate* evaluator check on known controls; "the measure on the same known controls"
  folds both checks into one [V, roadmap line 150].
- "A family every seed solves or every seed fails is uninformative" [V, driver line 603]. That cannot be known
  without running direct on the tasks, which is a calibration run, and "calibration runs are separate, budgeted
  experiments" (`AGENTS.md`). So step 2 needs a small spend tranche.
- Proposed text: "2a (zero spend): per task, base fails and reference passes the hidden set in 5 of 5 runs (no
  flaky task admitted). 2b (calibration spend, own ledger row): on a 20-task development split, two direct runs
  per model and one implement–test–repair run. Gates: direct pass rate between 0.25 and 0.75; the repair branch
  is entered in at least 30% of runs; on 10 tasks a natural passing submission that differs structurally from
  the reference is accepted; metering is complete. Development tasks never enter the evaluation table."

**M2. The spend estimate is in the wrong unit and understated about threefold.** Section: Phase 5 step 3
("Estimate: 240–320 short runs"); Process ("budget requested once per phase").
- 240–320 is about 8 programs × 30–40 tasks counted as *runs*. Catalog programs realized 4 calls
  (`plan_then_implement`, `best_of_n`) and 6 calls (`implement_review_revise`) per run [V, Phase 1 report lines
  56–62]. At roughly 24 calls per task that is 720–960 provider calls, plus 180–240 for the Python control [I].
  The largest allocation approved so far was 160 calls [V,
  `docs/plans/2026-10-18-orc-structural-search-roadmap.md` line 211].
- Phase 1 needed 43 attempts for 20 jobs (2.15 per job, budget 1.5) [V, Phase 1 report lines 373–376]. No
  attempt allowance, retry rule or missing-data rule is stated here.
- Proposed text: state the budget as provider calls and a priced-token ceiling with an attempt allowance (1.2);
  adopt the driver's failure rule (a failed evaluation or envelope timeout scores fail; other incidents are
  excluded and counted) and a written one-retry rule for infrastructure incidents.

**M3. The Python control is undefined and tests a hypothesis the design cannot resolve.** Section: Phase 5,
"A Python control".
- "The same three programs" does not say which three of about eight [V, roadmap lines 163–164].
- Its expected effect is exactly zero (same prompts, models and calls). Showing that takes an equivalence test;
  at 30–50 tasks × 1 run the interval on ORC − Python is ±12–23 points [C], so "attributable to the structure
  and not the tool" cannot be concluded either way.
- The question it should answer is different: does *structure* (information passed between calls) beat
  *re-rolling* at equal budget? The roadmap has no equal-budget direct baseline at all.
- Proposed text: "Controls: (a) direct retried up to three times until the visible check passes, with no
  information carried between attempts; (b) any-of-3 on hidden tests as the selection upper bound; (c)
  random-of-3 as the selection floor. All three, and best-of-3 itself, are computed offline from the six direct
  runs per task. The ORC-versus-Python question is a measure-free parity check: byte-identical rendered prompts
  (static) and call/token parity on 10 tasks; no quality claim is made about the tool." This keeps the charter's
  requirement to compare a Python control before any ORC-specific claim [V,
  `docs/plans/2026-09-08-orc-research-charter.md` lines 129–137, 164–166] by making no ORC-specific quality claim.

**M4. Selecting tasks by the oracle check alone does not make the task set valid.** Section: Phase 5 step 2.
- Contamination: public bug corpora are probably in the models' training data [I]. This raises the direct pass
  rate, compresses headroom and measures recall. Needed: fix commits dated after the bound models' training
  cutoffs where possible, no network, history after the base commit removed, the existing solution-hash scan.
- Ceiling and floor: only tasks direct sometimes fails and sometimes passes carry information; at a direct pass
  rate of 0.85 a 10-point gain means fixing two thirds of all failures [C]. The range must be set on the
  development split with runs that are not reused in the comparison (otherwise regression to the mean favours
  the workflows) [I].
- Independence: tasks from one repository are clustered. Cap tasks per repository (at most 5, at least 10
  repositories) and resample repositories in the bootstrap [I].
- "Never add deliberate flaws to establish difficulty" (`AGENTS.md`) rules out mutation-injected bugs; tasks must
  be natural fix commits. The roadmap should say so.
- No held-out split is reserved for Phase 6b (B5).
- Proposed text: add these five conditions to step 2 and "the split into development, evaluation, validation and
  sealed sets is drawn by a seeded shuffle and its hash list frozen before any run".

**M5. The zero-spend reanalysis (step 1) can only be descriptive.** Section: Phase 5 step 1.
- The pools hold at most five tasks, all features of this repository, the family the roadmap itself calls
  contaminated. E-A has no hidden-test results at all (the report never mentions them) [V,
  `docs/reports/2026-10-14-orc-versus-single-call-evaluated.md`]. E-B2: 12 patches on one task, clustered at
  three hidden values, three runs per arm, and the report is labelled "Historical, not calibration-qualified"
  [V, `docs/reports/2026-10-15-calibrated-orc-versus-single-call.md` lines 3–10, 121–135]. E-B3: seven versions
  on one task spanning 152–158 of 164 nodes [V, `docs/reports/2026-10-16-eb3-orc-versus-single-call-rung1.md`
  lines 450–462]. Phase 1: two tasks, two runs per arm, anchors inverted, hidden "descriptive only" [V, Phase 1
  report lines 10–11, 49, 114–139].
- "Selection by tests" uses the scoring tests as selector, so it is the any-of-N upper bound (B3), not an
  estimate of deployable selection. Pools mix arms and models, so they are not N draws from one generator. With
  2–3 runs per cell the selection gain (max minus mean) is noise [I].
- What it can show: an upper bound on selection gain on these tasks, and how often each judge's top pick agrees
  with the hidden-test top pick. What it cannot show: any effect size, or anything about the new task family.
- Proposed text: "Step 1 is descriptive, gates nothing, makes no quality claim, uses the harness clone-id joins
  and preserves historical scores unchanged."

**M6. Phase 6a is not a test of search.** Section: Phase 6a.
- With eight programs, random order finds the table's best in 4.5 evaluations on average, and a policy that
  finds it on the first try has p = 1/8 = 0.125 against random order. One table cannot reach p < 0.05 [C].
- The "best recorded program" is mostly noise: with true pass rates spread over 5 / 10 / 20 points and 40 tasks
  × 1 run, the table's best is the true best in 21% / 30% / 43% of tables [C].
- "An LLM proposer choosing among recorded programs" is provider spend, not zero spend, and it tests the model's
  prior about program names, not search [I]. At the cell level the replay is ordinary best-arm identification,
  whose answer is known and says nothing about program-space structure [I].
- Proposed text: "6a is a descriptive readout with no gate and no LLM proposer: rank stability of the recorded
  programs under task resampling. It supports no search claim."

**M7. PQ-1c cannot be decided by "one comparison", and its default models exceed the ceiling.** Section:
Phase 4 work and spend.
- Its definition needs four real-provider runs at minimum (variant and baseline, each clean and failed/resumed),
  six judged axes and an explicit owner judgment, with three outcomes: retain, improve, retire [V,
  `docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md` lines 256–262;
  `docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md` line 674]. The roadmap reduces this to "run
  once and then either add `Agent` … or retire" [V, roadmap lines 128–129].
- The consumer defaults to `claude-opus-5-5` and `gpt-6.1-sol` at high effort and the gate says "same
  models/effort" as the baseline [V, `workflows/examples/design_review_execute_agents.orc` lines 60–64]. That is
  above Sonnet/Terra and outside the two scoped exceptions in `AGENTS.md`. The gate also says the owner
  authorizes it separately (D8), not inside a phase's general request.
- One run per cell can decide only measure-free axes (usage, elapsed time, repeated first turns, whether
  `invalidate` is refused). "Retained useful context" is a quality judgment with no qualified measure. The same
  consumer delivered 0 of 3 valued runs in E-B3 [V, E-B3 report line 163], so a single attempt is likely to
  return nothing.
- Proposed text: "PQ-1c runs its four defined cells with models rebound to the Sonnet/Terra ceiling (or under a
  recorded owner exception), is authorized separately, and reports measure-free figures only. Decision rule,
  written before the runs: retire unless both resumed cells complete and the variant's priced usage is below the
  baseline's; 'improve' remains an outcome. One infrastructure retry per cell."

**M8. Process rules conflict with the experiment rules in three places.** Sections: Phases preamble; Process
rules; Dispositions ("Stop").
- "Provider budget is requested once per phase, at its start" against "calibration runs are separate, budgeted
  experiments" and "no spend before qualification": a single up-front approval covers main-table spend before
  the qualification result exists.
- "No … hash packets … in design docs" against the hygiene rule that the criterion is "frozen and hashed before
  scoring and bound into `run.json`" [V, driver lines 1087–1088]. The pre-registration hash is the one piece of
  ceremony that protected validity; the rule should name it as retained.
- "Stop … per-step governance for pilots of one to three calls" against "record experiment decisions, including
  spending limits, in the plan's ledger" for every experiment that spends provider calls.
- Proposed text: "Budget is requested once per phase as gated tranches (calibration; main; one reserved
  extension), each a ledger row with its limit; a tranche is released by its predeclared gate, with no new
  approval and no top-up after a null. Every experiment keeps one frozen, hashed criterion and one ledger row;
  nothing else is required for pilots."

### Minor

- **m1. Interval method unspecified.** "Bootstrap intervals" for "Pareto-dominates" has no defined statistic.
  Use a paired bootstrap that resamples repositories, report the interval on Δq and on the cost ratio, and the
  bootstrap probability of dominance; give exact McNemar as a cross-check. [I]
- **m2. Incident asymmetry.** Multi-call workflows meet more infrastructure failures than one call. Scoring
  incidents as fail biases against workflows; excluding them biases for. Report both and state the primary
  before spend. [I]
- **m3. "Two or three model placements" multiplies comparisons.** Name the primaries (at most two); everything
  else is descriptive. [I]
- **m4. Phase 5 findings row quotes rubric noise** (σ ≈ 1 on 8 points) as the motivation, which says nothing
  about the binary measure; replace with the planned minimum detectable difference. [V, roadmap line 40]
- **m5. Phase 6b search-split leakage.** A proposer that sees per-task results can fit the search tasks; the
  driver's extra scan channels (archive, lineage, sealed lists) [V, driver lines 1095–1106] must stay even if
  the receipt gates go.
- **m6. The consumer exit test** ("completes a real multi-day task with at least one resume") is one
  uncontrolled case. It supports the engineering claim only and should be labelled measure-free. [I]

## Answers to the nine questions (short form)

1. Detectable difference at n = 30 / 40 / 50 is 20–29 / 18–25 / 16–22 points (one comparison, one-sided);
   10 points is not distinguishable from noise; it needs 122–245 tasks × 1 run, or about 60 tasks × (6 direct,
   4 workflow) runs; the eight-program multiplicity is unhandled (B1, B2). [C]
2. No. Use support / refute / inconclusive with one pre-declared extension (B2).
3. Oracle check alone is insufficient; selection and scoring tests must be disjoint and the visible check must
   fail at base (B3, M1, M4).
4. The Python control is undefined and unresolvable; the clean control is equal-budget re-rolling; the cost axis
   is priced metered tokens per task (M3, B4).
5. Step 1 is descriptive only; 6a tests nothing at eight programs (M5, M6).
6. Not at the Phase 5 scale: the sealed confirmation alone needs about 480 runs; guards are a three-way split, a
   fixed generation count, one finalist and one opening of the sealed set (B5).
7. No: four cells minimum, three outcomes, models over the ceiling, separate authorization (M7).
8. Yes: weaker oracle qualification, calibration spend labelled zero, bar not Pareto, cost in raw tokens,
   metering absent, gates dropped in 6b, budget-once against separate calibration budgets (M1, B4, B5, M8).
9. Below.

## Corrected minimal protocol

### Phase 5 step 3 (replaces steps 2–3)

1. **Task pool (zero spend).** Natural fix commits with their own tests, outside this repository; at most 5 per
   repository, at least 10 repositories; fix dates after the bound models' cutoffs where available. Each task:
   one visible failing check, a disjoint hidden scoring set, base fails and reference passes hidden in 5 of 5
   runs. Seeded split, hash list frozen: development 20, evaluation 60. If Phase 6 may open, also name
   validation 30 and sealed 60 now (they need only the zero-spend check).
2. **Calibration tranche (about 120 calls, own ledger row).** On the development split: direct × 2 on each of two
   models at or below Sonnet/Terra (80 calls) and implement–test–repair × 1 (about 40 calls). Gates: direct pass
   rate 0.25–0.75; repair branch entered in ≥ 30% of runs; structurally different natural pass accepted on 10
   tasks; metering complete on every row; no contamination verdict; attempt rate ≤ 1.2. One redraw allowed, then
   stop. Freeze the criterion: price table, τ_q, τ_c, quality floor, primaries, decision regions, failure and
   retry rules, observed discordance and the resulting minimum detectable difference.
3. **Main tranche.** Evaluation split, 60 tasks:
   - direct, model A: 6 runs per task = 360 calls;
   - direct, cheaper model B: 6 runs per task = 360 calls (drop for a single-model version);
   - implement–test–repair, model A, visible check, at most 3 coder calls: 4 runs per task = 240 runs, about
     430 calls.
   - Computed offline from the direct runs, no spend: best-of-3 with visible-test selection (all 3-subsets of
     the 6 runs), retry-until-visible-pass up to 3, any-of-3 upper bound, random-of-3. This assumes best-of-3
     candidates are independent direct calls with the direct prompt [I]; confirm with a 10-task live parity run
     of the ORC program (30 calls, measure-free).
   - Total about 1,180 calls two-model, 820 single-model; with the 1.2 allowance, about 1,400 / 1,000. Reserved
     extension tranche: 2 more runs per task per live arm.
   - Cheaper variant with a 15-point bar: 40 tasks × (5 direct, 3 workflow), single model: about 450 calls.
4. **Primaries (two, Holm):** best-of-3 visible-selected on model A against direct A; implement–test–repair A
   against direct A. Paired, repository-clustered bootstrap.
5. **Decision:** the three regions of B2. "Better" is stated only as dominance over a direct-family baseline
   (direct A, direct B, retry-3 A, retry-3 B) under the frozen tolerances; implement–test–repair must in
   particular not be dominated by retry-3, or its structure adds nothing over re-rolling.
6. **Operating characteristics [C, simplified model: Beta(0.5, 0.5) task mix, both primaries share the true
   effect, cost conditions not simulated]:** 60 × (6, 4): null → refute 0.85 / inconclusive 0.15 / support 0.00;
   +15 → support 0.98; +10 → support 0.69 / inconclusive 0.31.

### Phase 6

- **6a:** descriptive readout only (rank stability under task resampling); no gate, no LLM proposer, no claim.
- **6b**, opened only on a Phase 5 "support":
  1. **Frozen before any call:** proposer model (at or below Sonnet/Terra, not Fable), 2 generations × 6
     children, admission = compiles and priced cost ≤ 3× direct on the search split, the final-choice rule, the
     claim (one of: higher pass rate at cost ≤ incumbent × (1 + τ_c); or non-inferior pass rate, margin 0.10, at
     cost < incumbent × (1 − τ_c)).
  2. **Search** on the Phase 5 evaluation split: each child on a fixed 20-task subset × 1 run, top 2 per
     generation on the other 40 tasks: 200 runs per generation, 400 runs, about 800 calls plus 12 proposer calls.
     The proposer sees aggregate results only.
  3. **Validation** (30 fresh tasks × 2 runs): two finalists and the incumbent, all freshly run: 180 runs, about
     360 calls. Pick one finalist by the frozen rule.
  4. **Sealed confirmation** (60 tasks × 4 runs), opened once: finalist and incumbent, both freshly run: 480
     runs, about 960 calls. One one-sided test at α = 0.05; minimum detectable difference about 9 points [C:
     (1.645 + 0.84) × sqrt(2 × 0.125 / 240 + between-task term) ≈ 0.087].
  5. **Total about 2,100 calls.** A 15-point version (sealed 40 × 3) is about 1,600. Below that, 6b should not
     open: record "not tested" instead of a measured negative.
  6. **Stop:** the fixed budget; no second finalist, no reopening of the sealed set, no extension after a null.

## What I did not check

- The audit's numbers (`audit/research.md`) other than those re-read in the cited reports.
- Whether a suitable public task corpus with post-cutoff fix commits and split visible/hidden tests exists in
  the needed quantity (170 tasks for both phases); this is the main feasibility risk of the corrected protocol.
- Real per-call token cost on the new family; all budgets above are in provider calls.
- The simulation model is a simplification (Beta task mix, independent runs); the pilot's observed discordance
  should replace it before spend.
