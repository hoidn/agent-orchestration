# What The Experiments Established, July–October 2026

**Status: Historical record (captured evidence), not a contract.** This page
lists every experiment that spent provider calls from July to October 2026,
with what each one showed and what none of them showed. It condenses section 1
of the [research audit note](2026-11-11-project-audit/research.md), checked
against the cited reports; each report owns its own numbers, and where the
audit note and a report differ, this page follows the report and says so
(see [Differences from the audit note](#differences-from-the-audit-note)). It
makes no new claims. The [current roadmap](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md)
owns what happens next; this page selects no work and is not a launch recipe.

"Calls" are registered CLI invocations or physical starts as each report
counts them. USD figures are what each report states: OpenRouter charges for
R1a, frozen list-price equivalents elsewhere. Most studies have no complete
monetary total.

## Experiments

| Date | Study | Question | Spend | Result | Main limit |
| --- | --- | --- | --- | --- | --- |
| 07-26/31 | [Lean pilot A1](2026-07-26-orc-effectiveness-lean-pilot.md), [forensics](2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md) | DIRECT vs COORDINATOR vs ORC on one task | 19 arm calls plus blind reviews; cost not reported | DIRECT "won 3/3", but two blocks were forfeits on one identical `product_manifest_guard` event | No quality signal; protocol fragility |
| 09-08/09 | [R1a research demonstration](2026-09-08-orc-research-demonstration.md) | ORC as a programming medium, against matched Python | USD 250.75 charged (cap raised to 375) | C1 2/3; C2 0/3 build failures; C3 and Python checker outputs called "avoidable brittle evaluation design"; Python judged the more direct representation for value flow | Qualitative; checker design errors |
| 09-28 | [Flat-route ORC vs single call](2026-09-28-orc-versus-single-call.md) | Best-of-4 and review/revise vs one call | Not totalled in the report | Best-of-4 with `gpt-6-sol` selector +0.83 and +1.02; cross-model review +0.58; same-model review −0.5 | One easy bug, 6 runs, model judges; no script control |
| 10-14 | [E-A](2026-10-14-orc-versus-single-call-evaluated.md) | Replicate the September result on the evaluated route | 55 agent + 17 judge calls; about 13 runs discarded | `reviewed_change` holds (+0.67 paired); `best_of_n` one run short; vs single calls +0.33 and +0.42 | Reviewer approved the first patch in 4 of 6 runs; "small positive effect, not robustly above the bar" ([postmortem](2026-10-14-effectiveness-experiments-postmortem.md)) |
| 10-14 | [E-B qualification](2026-10-14-design-review-execute-versus-single-call.md) | Can one call finish the REPL feature? | 4 Sol calls, 2 discarded (`PYTHONPATH` leak) | One `gpt-6.1-sol` call passed 16/16 and 14/16 hidden tests (about 1,800 added lines) | Qualification only |
| 10-14/15 | [Difficulty ladder](2026-10-14-task-difficulty-calibration.md), [continuation](2026-10-15-calibration-continuation.md) | Find a rung one call cannot finish | 18 + 2 calls; 1,245 Codex credits | Single-call hidden fractions 0.31–0.94; all 8 reviews requested changes; rung 1 qualified only on a third sample | Qualifying rule changed after data |
| 10-15 | [E-B2](2026-10-15-calibrated-orc-versus-single-call.md) | DRE (`design_review_execute`) and `reviewed_change` vs one call, hidden tests primary | 31 + 6 judge + 10 smoke calls | DRE hidden gain 0.00 (0.49 vs 0.49) at 4.9× wall clock; review loop raised hidden acceptance in no run | One task, 3 runs per arm; labelled "not calibration-qualified" |
| 10-15/16 | [E-B3](2026-10-16-eb3-orc-versus-single-call-rung1.md), [posthoc](2026-10-16-eb3-posthoc-review.md) | Same on rung 1, rubric primary | 28 + 6 judge + 5 probe calls | Both claims NOT EVALUATED: DRE 0/3 valued (2 timeouts, 1 contaminated), RC (`reviewed_change`) 2/3; `gpt-6-sol` scored upstream at or below the stub | Disk exhaustion, host pause, contamination; primary measure amended after launch |
| 10-18/19 | [Structural search Phase 1](2026-10-18-orc-structural-search-phase1.md) | Do catalog seeds and unguided children separate? | 159 charged of 160 (178 registered) | Not separated (1.13 vs 1.86; 2.00 vs 2.39); `anchors_inverted` fired; Phase 2 not selected | 4 of 6 unguided episodes contaminated; threshold above the anchor gap |
| 10-19 | [Three-arm readout](2026-10-18-orc-structural-search-phase1.md#three-arm-readout) | Compile-only behaviour of three mutation interfaces | 32 calls, all Sol high | 18/18 accepted, 17 distinct skeletons, all one idea (implement, check, repair); no repair ran | No quality measured |
| 10-19 | [Step A judge calibration](2026-10-19-orc-structural-search-measurement-calibration.md) | Does the reference rubric order known controls? | 8 calls, USD 7.88 | P1/P2/P3 pass in all four pairs; fails on Terra's mutant spread (0 vs 4) | Reference disclosed to the judges |
| 10-20 | [AT](2026-10-20-orc-structural-search-measurement-at.md), [completion](2026-10-20-orc-structural-search-measurement-at-completion.md) | Same, reference-free, one Terra judge | 12 sessions (6 unrequested native children), ≥ USD 4.35 | FAIL_NOT_QUALIFIED: PRR's first partial tied the stub at 0 | One judge |
| 10-22 | [AS](../plans/2026-10-22-simple-evaluation-calibration-plan.md) | `control-means-v1` evaluator check | 4 Terra sessions, USD 3.76 | No accepted verdict: PRR judge excluded (it saw archived JUnit) | Objective superseded |
| 10-22 | [TD](2026-10-22-natural-task-difficulty-calibration.md), [TD2](2026-10-22-natural-task-difficulty-recovery.md) | Natural Luna-high vs Terra-high gap ≥ 2 | 6 incident starts (4 forbidden Claude/Fable probes) + 10; TD2 Terra USD 10.20 | RPI Terra − Luna = −1.5; PRR judge excluded | n = 2, one judge |
| 10-22/23 | [LH](2026-10-22-luna-effort-task-difficulty-calibration.md) | Luna low vs high effort gap | 10 sessions | RPI low/high 6/5, PRR 4.5/4; low used about 1/20 of the tokens | 4-criterion rubric rewards tidy incomplete work |
| 10-23 | [LS1–LS5](2026-10-23-luna-sol-functional-calibration.md) | Luna-high vs Sol-low on the functional rubric | 17 starts (43 overall) | Gaps 2 and 2.5 pass; Sol means 6 and 6, so `too_easy` | LS1–LS4 stopped on apparatus incidents ([plan](../plans/2026-10-22-functional-calibration-plan.md)) |
| 10-23 | LS6, LS7 ([LS6 plan](../plans/2026-10-23-functional-calibration-inplace-failure-plan.md), [LS7 record](../plans/2026-10-23-functional-calibration-single-call-recovery-plan.md)) | Harder in-place-failure tasks | 7 + 6 starts (56 overall) | Both stopped: undeclared nested Sol CLI sessions (LS6); an author copied a historical implementation (LS7) | No result |
| 10-23 | [LS8](2026-10-23-luna-sol-filesystem-isolation-calibration.md), [LS9](2026-10-23-luna-sol-shared-contract-calibration.md) | Same with explicit mounts; rejudge with the full contract | 10 + 2 starts (68 overall) | LS8 RPI judge brief contradicted the solver contract; LS9 RPI gap 1.5, PRR −1.5 | Not qualified |
| 10-23 | [LS10](2026-10-23-luna-sol-command-recovery-calibration.md), [LS11](2026-10-23-luna-sol-high-command-recovery-calibration.md) | Smaller PRR rung; then Sol high | 5 + 3 starts (76 overall) | LS10 Sol-low 2/2 vs Luna 4/4; LS11 Sol-high 7/6 vs the same Luna code rescored 3/3, qualified under the owner-confirmed rule (Sol ≥ 4, gap > 0) | n = 2, one judge; the [P1 preflight](2026-10-23-prr-pilot-control-preflight.md) (no calls) found both patches pass the same behaviours |
| 10-23 | [Adversarial DAQ](../../experiments/adversarial_daq/RECORD.md) | Builder/skeptic search for an ORC advantage over LangGraph or Python on synthetic DAQ debugging | 16 controller sites; 18 starts (1 pre-inference, 1 paid capacity failure); Sol high | INCONCLUSIVE; claims C1–C4 each refuted at parity; ORC case wall time higher every round (137 s vs 40 s in round 1) | Calibration waived; synthetic; round 4 evidence failed its integrity check |
| 10-24 | [PRR-P2](2026-10-24-prr-direct-orc-pilot.md) | Evaluator check, then 2 direct vs 2 ICDR (`implement_check_diagnose_repair`) | 4 starts (80 overall), USD 2.22 | Evaluator passed (baseline 0, partial 6, twice); two direct attempts delivered, unjudged; ICDR never started; INCOMPLETE | Only absent vs partial was discriminated |

## Established

- On one easy bug, an independent stronger-model selector or reviewer added a
  small rubric gain over one call; same-model review added nothing
  ([September](2026-09-28-orc-versus-single-call.md), [E-A](2026-10-14-orc-versus-single-call-evaluated.md)).
- On a harder task scored by hidden tests, design-review-execute and
  review/revise added 0.00 ([E-B2](2026-10-15-calibrated-orc-versus-single-call.md)).
- One `gpt-6.1-sol` call delivers a large, well-specified feature that passes
  most hidden tests, yet still leaves at least one defect a reviewer can name
  ([E-B](2026-10-14-design-review-execute-versus-single-call.md), [ladder](2026-10-14-task-difficulty-calibration.md)).
- The 4-criterion rubric did not track hidden tests, placed the upstream fix
  at or below candidates or the stub, and rewarded tidy incomplete work
  ([E-B2](2026-10-15-calibrated-orc-versus-single-call.md), [E-B3](2026-10-16-eb3-orc-versus-single-call-rung1.md), [LH](2026-10-22-luna-effort-task-difficulty-calibration.md)).
- The functional judge separates a feature-absent baseline from a working
  partial ([PRR-P2](2026-10-24-prr-direct-orc-pilot.md)); with a disclosed
  reference, judges separate upstream from stub ([Step A](2026-10-19-orc-structural-search-measurement-calibration.md)).
- Judge scores moved by one point on unchanged code ([LS11](2026-10-23-luna-sol-high-command-recovery-calibration.md))
  and with the wording of the judge brief ([LS9](2026-10-23-luna-sol-shared-contract-calibration.md)).
- Given freedom, mutators produced syntactic variety around one idea, and
  typed admission rejected nothing ([three-arm readout](2026-10-18-orc-structural-search-phase1.md#three-arm-readout)).
- A motivated adversarial search found no ORC advantage over LangGraph or
  strict Python on its four claims ([DAQ record](../../experiments/adversarial_daq/RECORD.md)).
- Apparatus incidents (isolation leaks, nested model calls, guard false
  positives, disk exhaustion) stopped or voided a large share of October runs
  ([audit, section 2](2026-11-11-project-audit/research.md)).

## Not established

- A robust quality advantage of any ORC workflow over one strong call: E-A is
  small, E-B2 is null, E-B3 was not evaluated and PRR-P2 is incomplete.
- An ORC-specific advantage: no quality comparison included the Python or
  script control the [research charter](../plans/2026-09-08-orc-research-charter.md#decision-rule)
  requires, and the [September report](2026-09-28-orc-versus-single-call.md)
  says a script would show the same gain.
- That structural search improves workflows: Phase 1 was inconclusive, and
  its threshold exceeded the upstream–stub anchor gap ([Phase 1](2026-10-18-orc-structural-search-phase1.md)).
- That the judge ranks two working solutions correctly: the only behavioural
  check of a judged ordering did not corroborate it ([P1 preflight](2026-10-23-prr-pilot-control-preflight.md)).
- A calibrated task family: one task qualified, under a relaxed rule, with
  n = 2 and one judge ([LS11](2026-10-23-luna-sol-high-command-recovery-calibration.md)).
- Measured ORC engineering advantages (resume, introspection, reuse) against a
  control: only the DAQ study compared them, and found parity.
- Complete monetary cost for most studies: receipts are partial or
  list-price equivalents only.

## Sources for interruptions, resumes and relaunches

Thread M's resume retrospective can count these from the following records
(not counted here):

- E-A to E-B3: the [effectiveness plan's rulings](../plans/2026-10-14-effectiveness-harness-and-experiments-plan.md#appendix-rulings-made-during-execution),
  [E-A Runs](2026-10-14-orc-versus-single-call-evaluated.md#runs) (discarded runs),
  [E-B3 Runs](2026-10-16-eb3-orc-versus-single-call-rung1.md#runs) and
  [Incidents](2026-10-16-eb3-orc-versus-single-call-rung1.md#incidents).
- Phase 1 and three-arm: [Allocation, Calls And Wall Clock](2026-10-18-orc-structural-search-phase1.md#allocation-calls-and-wall-clock).
- Step A and AT: the [measurement plan's Decision Ledger](../plans/2026-10-19-orc-structural-search-measurement-plan.md#decision-ledger)
  and the [AT completion report](2026-10-20-orc-structural-search-measurement-at-completion.md).
- AS, TD, TD2, LH: the [simple-evaluation calibration ledger](../plans/2026-10-22-simple-evaluation-calibration-plan.md#authorized-budget-and-chronological-decision-ledger).
- LS1–LS11: the [functional-calibration Decision ledger](../plans/2026-10-22-functional-calibration-plan.md#decision-ledger),
  which carries the overall-start counter, and the LS6–LS11 plans linked above.
- PRR-P2: its [plan's ledger](../plans/2026-10-23-prr-direct-orc-pilot-plan.md#decision-and-discrepancy-ledger).
- DAQ: its [launch record](../../experiments/adversarial_daq/docs/plans/2026-10-23-adversarial-daq-launch.md)
  (one resume after a CLI failure, one after a capacity failure).
- The canonical inventories these cite live in the evidence root
  `/home/ollie/sc-evidence/`, outside the repository and not durable.

## Differences from the audit note

- **DAQ spend:** the note says about 16–17 calls plus one capacity failure;
  the launch record says all 16 controller sites committed with 18 started
  attempts, one failing before inference and one paid capacity failure.
- **DAQ round 4:** the note groups all four claims as parity or
  counterexample; the record has round 4 ending in matching REVISE votes with
  its official evidence failing integrity, and the builder's reproduction
  showing zero saving.
- **E-A discarded runs:** the note's "about 40 calls" is its estimate; the
  report says "about 13 more runs' worth of calls" without a count.
