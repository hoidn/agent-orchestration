# Research-track audit: what has been learned, and is the programme well conceived?

Task id: `review_design_research_track_audit`. Role: reviewer (read-only). Scope: plans, reports, experiment
code and evidence of the research/experiments track of `/home/ollie/Documents/agent-orchestration` (main).
No edits, no provider calls. Paths are repo-relative unless absolute. Figures come from the reports; where I
estimate, I say so.

---

## 0. Bottom line first

- **ORC vs direct:** after roughly 700 provider calls across nine studies, no comparison shows a robust advantage
  for a structured workflow over one strong agent call. The only positive results are small, judge-dependent
  rubric gains on one easy September bug (+0.33 and +0.42 out of 8 over single calls, E-A). On the one task
  measured with executed tests, the gain was exactly 0.00 at 2–5× the wall clock (E-B2). Every later comparison
  ended *not evaluated* or *incomplete* (E-B3, PRR-P2). No comparison has used a Python/script control, so even
  the small gains are not ORC-specific (the September report itself says "a script that generates four
  candidates and selects one would show it too").
- **LLM-driven structural search:** never tested on its core claim. Phase 1 enumerated 5 seeds plus 2 unguided
  children: nothing separated and the anchors were inverted. In the three-arm readout, 18 of 18 mutated
  children converged on the same obvious idea, implement → check → repair, and the check never failed, so these
  children behave exactly like `direct`. The compiler rejected 0 proposals in all three interfaces, so typed
  admission did not discriminate either.
- **The LLM-judge evaluator:** it can tell *absent* from *working-partial* (0 vs 6, twice, PRR-P2). With a
  disclosed reference it can tell upstream from stub (8 vs 0, Step A). It has **not** been shown to rank
  working solutions reliably:
  - the 4-criterion rubric ranked the merged upstream fix at or below candidates (E-B2, Phase 1) and below the
    inert stub (E-B3 `gpt-6-sol`; Phase 1 PRR batch 0);
  - the rubric rewarded tidy, incomplete work: Luna-low, using about 1/20 of the tokens, outscored Luna-high
    (LH);
  - the functional rubric re-scored identical code 4/4 → 3/3 (LS10 → LS11);
  - test–retest error is about 1 point on a scale where the effects of interest are 0.3–1 point.

---

## 1. Evidence ledger (every experiment that spent provider calls)

"Calls" means registered CLI invocations (each typically 15–60 min of agent work, often tens of millions of
cumulative tokens). The October ledger "overall starts" counter (16 → 80) covers TD … PRR-P2 only.

| # | Date | Study (report) | Question | Design | Calls / cost | Outcome | Strongest legitimate claim |
|---|---|---|---|---|---|---|---|
| 1 | 07-26/31 | Lean pilot A1-v7 (`docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md`, `…2026-08-01-lean-pilot-forensics…`) | DIRECT vs COORDINATOR vs ORC on nanoBragg task | 3 blocks × 3 arms, 2 blind reviewers | ~19 arm calls + 6 reviews; cost UNKNOWN | DIRECT "3/3", but 2 blocks were forfeits by one identical `product_manifest_guard` event (pytest cache) | "No demonstrated orchestration benefit on a one-context task; real protocol fragility" (forensics F3). Nothing about quality |
| 2 | 09-08/09 | R1a reduced pilot + assisted C1 (`docs/reports/2026-09-08-orc-research-demonstration.md`; `experiments/orc_research_demo/`) | ORC as a programming medium: authoring, reuse, introspection | OMP/OpenRouter constructions C1–C3 + Python; diagnosis pairs | ≥ USD 250.75 charged (cap raised 50 → 100 → 150 → 300 → 375) | C1 2/3, C2 0/3 build failures, C3/Python checker outputs withdrawn as "avoidable brittle evaluation design"; structured diagnosis 1/2 vs 0/2 | Qualitative: "for this small value-in/value-out task, ordinary reusable Python is the more direct control representation" (§Code-grounded ergonomic assessment) |
| 3 | 09-28 | Flat-route ORC vs single call (`docs/reports/2026-09-28-orc-versus-single-call.md`) | best-of-4 and review/revise vs one call | 1 easy bug (`468e7908`), 6 runs/config, 2 blind Opus judges | ~150+ agent calls (estimate; not totaled) | best-of-4 with `gpt-6-sol` selector +0.83/+1.02 over group mean; review with stronger reviewer +0.58; same-model review −0.5…0 | On one easy task, cross-family selection/review adds ~0.5–1 rubric point over the author's own output; same-model review adds nothing |
| 4 | 10-14 | E-A (`…2026-10-14-orc-versus-single-call-evaluated.md`) | Replicate #3 on evaluated route | 18 runs, 2 judges, frozen criterion | 55 agent + 17 judge calls + ~13 discarded runs (~40 calls); Codex weekly 82 → 96% | `reviewed_change` holds (+0.67 paired); `best_of_n` misses a run count (4/6). vs single call: +0.33, +0.42 | "Small positive effect, not robustly above the bar" (postmortem). Reviewer approved 4/6 first patches, so the task was too easy |
| 5 | 10-14 | E-B qualification (`…design-review-execute-versus-single-call.md`) | DRE vs one call on the REPL feature | 2 single-call qualification runs | 4 Sol calls (2 discarded for tmux `PYTHONPATH` leak) | One call passed 16/16 and 14/16 hidden tests | One `gpt-6.1-sol` call ships a ~1,800-line, well-specified feature |
| 6 | 10-14/15 | Difficulty ladder + continuation (`…task-difficulty-calibration.md`, `…calibration-continuation.md`) | Find a rung one call cannot finish | 4 rungs × 2 calls + review; rung 1 third sample | 18 + 2 calls; 1,245 Codex credits | Hidden pass rates 0.31–0.94; every review blocked (1–4 blockers); only post-data rung 1 "qualifies" | Task size does not limit a single call; it still leaves ≥1 concrete defect a reviewer can name |
| 7 | 10-15 | E-B2 (`…2026-10-15-calibrated-orc-versus-single-call.md`), retro-labelled "not calibration-qualified" | DRE and `reviewed_change` vs one call, hidden tests primary | Rung 3, 3 runs/arm, 2 judges | 31 + 6 judges + 10 smoke ≈ 47 | DRE hidden gain **0.00** (0.49 vs 0.49) at 4.9× wall clock; review loop moved hidden tests by 0 in 3/3 runs; judges +1.0 for DRE while scoring upstream 2–8 | Strongest clean null in the repo: on executed tests, neither workflow added anything on this task. The rubric did not track tests |
| 8 | 10-15/16 | E-B3 (`…2026-10-16-eb3-…rung1.md`, posthoc) | Same, rubric primary (amended after launch) | Rung 1, 3 runs/arm | 28 + 6 judges + 5 probe = 39; 78,579 s summed agent time | DRE 0/3 valued (2 timeouts, 1 contaminated); RC 2/3 (1 host-pause timeout). Both claims NOT EVALUATED; `gpt-6-sol` scored upstream ≤ stub | None about effects. Posthoc: specific revision repairs were real (5 test cases), magnitude unknown |
| 9 | 10-18/19 | Structural search Phase 1 (`…2026-10-18-orc-structural-search-phase1.md`) | Do 5 seeds + unguided I1 children differ by > 2 pooled SD? | 2 tasks × 2 reps, 2 judges | **159 charged** (+19 free refusals; 178 registered; 21 lost to incident 1) | `anchors_inverted` fired; max gaps 1.13 vs 1.86 and 2.00 vs 2.39 thresholds; DIRECT ranked 5th/6 and 3rd; 4/6 episodes contaminated | Inconclusive. The separation threshold exceeded the upstream–stub anchor gap, so the instrument could not have detected the effect it sought |
| 10 | 10-19 | Three-arm readout (same report, §Three-Arm Readout) | Compile-only behaviour of I1/I2/I3 | 6 episodes/arm, 12 paid evaluations | 32 calls (all Sol high) | 18/18 accepted; 17 distinct skeletons; **all one idea** (implement → check → repair); no repair ever ran | Mutators produce syntactic variety, not idea diversity; typed admission rejected nothing |
| 11 | 10-19 | Step A judge calibration (`…2026-10-19-…measurement-calibration.md`) | Does the reference rubric order known controls? | 2 tasks × 2 batches × 2 judges; upstream/stub/partial/mutant | 8 calls, USD 7.88 | P1/P2/P3 all pass (8/0 upstream/stub everywhere); fails only on Terra mutant spread 0 vs 4 | With a disclosed reference, judges separate controls. Likely partly similarity-to-reference (the doc itself warns there is no structurally different correct control) |
| 12 | 10-20 | AT, Terra-only, reference-free (`…measurement-at.md`, `…at-completion.md`) | Same, no reference | 1 judge, 4 pairs | 12 sessions (6 unrequested native children), ≥ USD 4.35 | RPI pass; PRR batch 0 partial = stub = 0 → P2 fails, so FAIL_NOT_QUALIFIED | Without a reference, a single judge cannot reliably order partial above stub |
| 13 | 10-22 | AS (`docs/plans/2026-10-22-simple-evaluation-calibration-plan.md` §Superseded AS) | `control-means-v1` evaluator check | 4 Terra calls | USD 3.76 | PRR judge excluded (read archived JUnit); objective superseded mid-flight | None |
| 14 | 10-22 | TD / TD2 natural difficulty (`…natural-task-difficulty-calibration.md`, `…recovery.md`) | Luna-high vs Terra-high gap ≥ 2 | 2 × 2 × 2 tasks + 2 judges | 6 (incident: 4 forbidden Fable probes) + 10; Terra-known USD 10.20 | RPI Terra − Luna = **−1.5**; PRR judge excluded (sandbox masks looked like deletions) | The "stronger" model was not observed stronger on RPI |
| 15 | 10-22/23 | LH Luna low vs high (`…luna-effort-task-difficulty-calibration.md`) | Effort gap ≥ 2 plus 3 < high < 5 | 8 gen + 2 Sol judges | 10 | RPI low/high 6/5, PRR 4.5/4. Low used ~88 s and ~1/20 of the tokens of high | The 4-criterion rubric rewards scope/layering of small, incomplete patches over functional coverage |
| 16 | 10-23 | LS1–LS5 functional rubric (`…luna-sol-functional-calibration.md`; `docs/plans/2026-10-22-functional-calibration-plan.md` status) | Luna-high vs Sol-low gap ≥ 2, 3 < Sol < 5 | Carry-over of 7 captures + 1 fresh, 2 judges | 4 + 2 + 4 + 4 + 3 = 17 (LS1/LS2 detector false positives on `--help`; LS3 NVMe failure; LS4 `server_overloaded`) | Gaps 2 and 2.5 pass; Sol means 6/6 → `too_easy` | Separation observed; the target interval failed |
| 17 | 10-23 | LS6/LS7 (`docs/plans/2026-10-23-functional-calibration-single-call-recovery-plan.md`, `…filesystem-isolation-plan.md`) | Harder in-place-failure tasks | 8 gen + 2 judges each | 7 + 6 = 13 | LS6 stopped: Sol launched 3 unapproved CLI sessions. LS7 stopped: Luna copied a historical implementation from an unmasked home | None (pure apparatus) |
| 18 | 10-23 | LS8 / LS9 (`…filesystem-isolation-calibration.md`, `…shared-contract-calibration.md`) | Same with explicit mounts; re-judge with full contract | 8 gen + 2 judges; then 2 re-judges | 10 + 2 | LS8 RPI judge brief contradicted solver contract; LS9 RPI gap 1.5, PRR −1.5 (Sol 2/2 vs Luna 4/3) | Stronger-model ordering is not stable across tasks; judge brief wording moves scores by ~2 points (PRR Sol 0/0 → 2/2) |
| 19 | 10-23 | LS10 / LS11 command-recovery PRR (`…command-recovery-calibration.md`, `…high-command-recovery-calibration.md`) | Smaller PRR rung; then Sol-high | 4 + 1; then 2 Sol-high + 1 judge (Luna reused) | 5 + 3 | LS10: Sol-low quit after ~2 min, 2/2 vs Luna 4/4. LS11: Sol-high 7/6 vs the same Luna code re-scored 3/3; **passes the relaxed rule** (mean ≥ 4, gap > 0, no upper bound) | One task where Sol-high beats Luna-high by a large margin (n = 2, one judge). Judge re-score drift is 1 point on unchanged code |
| 20 | 10-23 | PRR P1 control preflight (`…prr-pilot-control-preflight.md`) | Does Sol patch > Luna patch on executed checks? | Local reconstruction and fixtures | 0 calls | Both pass the same behaviours; the frozen fixture contradicted the task text | The LS11 ordering is **not** corroborated by behaviour; one fixture bug found |
| 21 | 10-24 | PRR-P2 direct vs ICDR pilot (`…2026-10-24-prr-direct-orc-pilot.md`) | Evaluator check, then 2 direct vs 2 ICDR | 2 judges + 2 + 2 authors + 1 judge | 4 starts, USD 2.22 (11 authorized) | Evaluator: baseline 0 vs partial 6, twice → PASS. Direct ×2 delivered; ICDR never started (`.codex/config.toml` trust stanza tripped integrity); closed INCOMPLETE | Only coarse absent-vs-partial discrimination |
| 22 | 10-23 | Adversarial DAQ (untracked `experiments/adversarial_daq/`, `docs/plans/2026-10-23-adversarial-daq-launch.md` inside it) | Builder/skeptic search for a scoped ORC advantage over LangGraph/Python for DAQ debugging | 4 rounds, Sol-high both roles, "calibration waived by owner" | ~16–17 Sol-high calls (+1 capacity failure) | 4 claims (C1–C4) all ended in parity or counterexample (0 vs 0 unapproved dispatches); ORC case wall time 137 s vs 40 s for LangGraph | A motivated adversarial search found no advantage for ORC over strong existing tools on its chosen claims |

**Not live or no provider result:**
- `experiments/orc_gp_example` (offline toy GP);
- `experiments/mlevolve_pair` (deterministic leaves; in September the ORC version was blocked by a 256-node limit);
- `orc_repetition_census` (static census);
- `orc_effectiveness` (frozen lean-pilot evidence; ES F1 declared invalid, never ran an arm);
- `evaluated_execution_spike` (historical prototype);
- `orc_vs_python_showcase` (conceptual);
- `agent_chess` (toy; no recorded games);
- `orc_repl_feature` (the orchestrator built its own REPL on 2026-10-12, a real dog-food use, never measured).

Section 6 gives one line per directory.

### Bottom-line paragraph

**(a) ORC vs direct.** Nothing decision-grade is known beyond this: on one easy bug, adding an independent
stronger-model selector or reviewer yields a ~0.3–0.4-point rubric gain over a single call at 1.5–2.6× the wall
clock. On a harder task measured by executed tests, design-review-execute and review/revise added exactly
nothing (E-B2). Every attempt to measure a calibrated task since has failed to complete (E-B3: 4/9 runs lost;
PRR-P2: ORC arm never started). No study has included the Python/script control the charter requires before any
ORC-specific claim (`docs/plans/2026-09-08-orc-research-charter.md` lines 129–137, 164–166).

**(b) Structural search.** No evidence either way on whether search *improves* workflows. The one-step
neighbourhood around `direct` is, in practice, one idea. The instrument used to look for improvement had a
noise floor larger than the gap between the merged fix and an inert stub.

**(c) The evaluator.** The LLM judge separates feature-absent from feature-present (and stub from reference when
the reference is disclosed). It has not been shown to rank two *working* solutions correctly:
- its absolute scores drift ~1 point on unchanged code;
- they depend on batch composition (Phase 1: the upstream anchor scored 5/4 alone vs 3/3 in a batch);
- they depend on the wording of the judge brief (LS8 → LS9: ±2).

The only behavioural check of a judged ordering (P1 preflight) failed to corroborate it.

---

## 2. Yield analysis

### Spend vs findings

Approximate totals (registered CLI calls):

| Block | Calls | Decision-relevant findings produced |
|---|---|---|
| Jul lean pilot | ~25 | 1 (protocol fragility; no quality signal) |
| Sep R1a + Sep single-call study | ≥ USD 250 + ~150 calls | 3 (cross-family selection/review helps a little on an easy task; same-model review does not; Python is more direct for value-flow tasks) |
| Oct 14–16 E-A/E-B/ladder/E-B2/E-B3 | ~250 | 4 (E-A small effect; one call finishes big specified features; E-B2 hidden-test null; rubric does not track tests) |
| Oct 18–19 Phase 1 + three-arm | ~191 | 2 (mutator convergence on one idea; instrument noise ≥ anchor gap) |
| Oct 19–24 calibration era (A, AT, AS, TD…PRR-P2) | ~108 (8 + 12 + 4 + 80 + adversarial excluded) | 3 (judge needs reference or functional framing; rubric rewards tidy incomplete work; judge drift ~1 point; plus one task "qualified" under a relaxed rule) |
| Adversarial DAQ | ~17 | 1 (no ORC advantage vs LangGraph/Python found) |
| **Total** | **≈ 740 calls + ≥ USD 250 OpenRouter** | **≈ 14 findings, all null/negative or about the instrument, except two small positives on one easy task** |

### Spend lost to apparatus rather than the question

My count from the reports:
- E-A: ~40 discarded calls (R34/R35/R37 harness defects).
- E-B: 2 of 4 calls (shared tmux `PYTHONPATH`).
- E-B3: effectively all 39 calls bought no verdict (ENOSPC, host pause, contamination).
- Phase 1: 21 calls in incident 1, 10 charged refusals, attempt rate 2.15 vs a 1.5 budget, 16 child evaluations
  excluded for contamination.
- AT: 6 unrequested native children + 2 interrupted roots.
- AS: 4 calls whose objective was superseded.
- TD: 6 calls (Fable probes).
- TD2: 5 (PRR judge excluded).
- LS1–LS4: 7 uncaptured.
- LS6: 7. LS7: 6.
- PRR-P2: 2 direct authors never judged.

That is **≈ 33 of the 80 ledger starts (41%) in the calibration series**, and **≈ 35–40% of all October spend**.

Since the "no uncalibrated experiments" rule was adopted (2026-10-19), ~110 provider calls have been spent and
**zero treatment-vs-control comparisons have completed**. The last completed comparison with a result is E-B2
(2026-10-15).

### Recurring incident classes

1. **Isolation leaks into the solution or into siblings:**
   - shared `/tmp`/tmux server carrying `PYTHONPATH` at the main checkout (E-B);
   - executor child reading main-checkout files (E-B3 DRE2);
   - episodes reading sibling episodes and the evidence root (Phase 1: 4/6), plus a relative-path read the scan
     missed;
   - author copying a historical implementation from home (LS7);
   - the stale editable install resolving to `.worktrees/omp-i1-prerequisites` (every study since E-A);
   - judges reading their own earlier ratings (E-B2) or archived JUnit (AS).
2. **Model-policy breaches through nested routes:**
   - the repo's own tests calling `claude -p --model fable` (100 + 120 sessions in calibration and E-B2; TD);
   - interactive-bash PATH bypass of the guard (TD);
   - Codex native subagents despite disabled flags, because the CLI discards top-level config under `exec`
     (AT; and `AGENTS.md` delegation in E-B3);
   - unapproved shell CLI sessions (LS6).
3. **Guard and integrity false positives that stop paid runs:**
   - `codex --help` and `codex exec --help` treated as dispatch (LS1, LS2);
   - scanner model fallback (PRR-P2);
   - Codex writing a trust stanza into a hash-bound config (PRR-P2);
   - operator effect-identity parser (AT).
4. **Result delivery and environment bleed:**
   - relative result paths (R34);
   - `best_of_n` writing results inside `cand-k` (R37);
   - `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` inherited by the task repo's tests (Phase 1 incident 1);
   - `provider_result_missing` (TD2);
   - `agent_turn_unresolved` on loop turns (Phase 1);
   - a coder printing a final summary and then not exiting (Phase 1 timeout scored 0).
5. **Host and provider capacity:**
   - ENOSPC from pytest temporaries (62 GB in E-B3, 78 GB in Phase 1);
   - NVMe failure (LS3);
   - session limits and `capacity` refusals (Phase 1: 29; LS4; DAQ);
   - CLI version drift 0.163 → 0.164 (LS10).
6. **Evaluator-input contradictions:**
   - mask-induced apparent deletions penalized as scope (TD2);
   - judge brief contradicting the solver contract (LS8);
   - frozen public fixture contradicting the task text (PRR P1);
   - judge alleging malformed indentation in byte-identical code (E-B3 posthoc).
7. **Operator / readout errors:**
   - positional join that told the owner the workflows were losing (E-A);
   - `pkill` matching its own shell;
   - scanning before adjudication (LS10);
   - relaunch instead of resume.

Classes 1–4 share one root cause. Real agent CLIs run inside a copy of *this* repository, against *this* user's
home, with the user's global skills, `AGENTS.md`, CLI configs and editable install, and the task's own tests
spawn providers. The harness design said it in 2026-10-14 (`docs/design/orc_effectiveness_comparison_harness.md`,
Problem): "control machinery placed in the path of the treatment became the failure mode". The October
calibration series repeated that pattern eleven times.

---

## 3. Methodology critique

### 3.1 What genuinely protects validity (keep)

- **Preregistered, hashed criteria before scores.** This caught real post-hoc temptations (lessons table; E-A
  amendments).
- **The summarizer's clone-id join.** The positional-join incident shows why it matters.
- **Blind pools with anchors in every batch.** The anchors are exactly what exposed the rubric's failure (E-B2,
  E-B3, Phase 1).
- **Contamination detection with adjudication.** It found real contamination: E-B3 DRE2, LS7, and 4/6 Phase 1
  episodes.
- **The functional single-score rubric** ("how much required behaviour works"). It fixed the demonstrated
  tidy-incomplete bias (LH).
- **"Do not score with tests the agent can run".** This was an observed defect in September.
- **The natural weak/strong idea of task difficulty.** It is a sound idea: difficulty is relative to a capability
  gradient, without synthetic defects. As executed (n = 2, one judge, one or two tasks), though, it is a noisy
  test.
- **Sealed holdout and validation separation for any search claim** (boundaries invariant 5). This is genuinely
  necessary once selection happens. It is not necessary before anything has been selected.

### 3.2 What has become a procedural ratchet

**1. The criteria have moved in step with the results.** The regime changed nine times in ten days:

1. blockers ≥ 1 and hidden < 0.5 (10-14);
2. blockers only (R55, post-data);
3. a third sample to rescue rung 1 (R56, post-data);
4. hidden tests demoted mid-launch (E-B3);
5. P1/P2/P3/spread with error 0 (10-19);
6. `control-means-v1` (10-22);
7. a natural gap ≥ 2 (10-22);
8. plus a target interval 3 < m < 5, added during generation (LH);
9. relaxed to Sol ≥ 4 and gap > 0 after four failures (LS11).

Each change is locally reasonable. Together they amount to a qualification target that tightens on mechanism
(hashes, packets, reviews) and loosens on substance (thresholds) whenever results disappoint. That is the worst
combination for both cost and validity.

**2. Zero-error, every-pair, every-task gates on n = 2–4 noisy ordinal observations are lotteries, not
calibration.** Take per-judgment noise σ ≈ 1 point:
- the reports show 4 → 3 on unchanged code, Terra's mutant 0 vs 4, and PRR Sol 0/0 → 2/2;
- the mean of 2 then has SD ≈ 0.7, and a two-arm gap has SD ≈ 1.0.

For a *perfectly suitable* task (true Sol = 4, true Luna = 2), the LS5 rule passes per task with probability
≈ P(gap ≥ 2) × P(3 < m < 5) ≈ 0.5 × 0.84 ≈ 0.42. Requiring both tasks gives **≈ 0.18**. The observed record
(LS5, LS8, LS9 and LS10 fail; LS11 passes after the rule was relaxed) is exactly what that arithmetic predicts.
Iterating fresh draws until one passes is then selection on noise: the "qualified" task is qualified partly by
luck (winner's curse).

Similarly, `error_rate = 0` over 4 judge×batch pairs, with strict P2 ordering where partial and stub sit 2–3
points apart, fails a good judge often (AT failed on one tie at 0 = 0).

**3. All-or-nothing denominators combined with a no-retry policy on flaky infrastructure.** E-B3 (one timeout
per arm), PRR-P2 (one config stanza) and AT (one PRR batch) all turned a single infrastructure event into "no
result at all". Missing-data rules are meant to stop cherry-picking. Here they also make every study's success
probability the product of all infrastructure success probabilities.

**4. Per-call governance overhead out of proportion to the spend:**
- LS packets bind 820–1,669 files by SHA;
- each 1–5-call step gets an independent packet review, a budget declaration, an integrity review per judge, an
  adjudication crosswalk, a canonical closure audit and updates to 4–6 hub documents;
- `docs/plans/2026-10-19-orc-structural-search-measurement-plan.md` is 132 KB;
- `docs/design/orc_structural_search_driver.md` is 1,336 lines;
- the structural-search experiment code is 11.6 k lines, with ~21 k lines of experiment tests;
- experiment-specific exceptions now live in the global `AGENTS.md` (the PRR-P2 paragraph).

The LS11 qualification cost 3 calls. Its surrounding paperwork is larger than most of the code under test.

**5. Gates that guard surfaces that do not exist yet:**
- V1/V2 qualification receipts;
- `amends_6` for packages not chosen;
- split-role exposure checks;
- a sealed rung 1 that never reaches a pool;
- `purpose: calibration` criteria that deliberately omit the `calibration` block so that generic results return
  `None`.

All of this is machinery for a campaign whose prerequisite (a measure that separates working solutions) has
never been met. It is a ratchet in the sense of the `auditing-procedural-ratchets` skill: optional diagnostics
promoted to blockers, with authority accumulating per incident.

### 3.3 Is the task family a sound testbed?

No, for three independent reasons.

1. **Contamination is structural, not incidental.**
   - The solutions are commits of this repository.
   - The agents run inside clones of it, on the same machine, with the user's home and an editable install
     pointing at a worktree whose history contains the solution.
   - Every incident class 1 item follows from this, and the harness can only *detect*, not prevent, reads of
     home, transcripts and network (repeated in every report's Limits).
2. **Prescriptive specification and enormous cost per sample.**
   - Hidden tests pin internal names, so `task.txt` must name every entry point and literal (calibration report,
     Interpretation; E-B2 Limits). That makes the task "fill in a spec" rather than a design problem — precisely
     the regime where a strong single call is expected to do well.
   - Each sample is a 2,000–4,000-line change in a large runtime: 15–100 min of agent time, tens of millions of
     cached tokens per Luna-high session (LH table: 58–66 M), and 60–78 GB of pytest temporaries per batch.
3. **Narrow and self-referential.**
   - Four to six rungs exist, all features of one idiosyncratic workflow runtime (resume integrity, pure replay,
     generic unions, attempt lineage).
   - Judges need deep knowledge of that runtime to score function by code inspection (and are forbidden to run
     tests).
   - External validity for "ORC beats direct" is nil, and split exhaustion is already acknowledged
     (`docs/design/orc_structural_search_cumulative_campaigns.md`, What This Makes Harder).

The September bug task was the opposite failure: so easy that a reviewer approved 4/6 first patches.

### 3.4 Can the n's answer the question at any affordable budget?

Using the design's own formula (`orc_structural_search_cumulative_campaigns.md`, Endpoints … Power), with
α = 0.05, power 0.8 ((z sum) ≈ 2.8) and σ ≈ 1.0 (Phase 1 pooled 0.93 / 1.20, each on 1 df, plus judge drift):

| Effect to detect | Evaluations per arm per task | Notes |
|---|---|---|
| 2.8 points (≈ upstream-vs-stub) | 2 | current designs; detects only "absent vs present" |
| 1.0 point | ≈ 16 | ≈ 32 evaluations × 35 min ≈ 19 agent-hours per two-arm comparison per task, before judging |
| 0.5 point (E-A-sized) | ≈ 63 | ≈ 125 evaluations, 300–700 calls depending on arm structure, ~75 agent-hours per task |

The effects actually observed (E-A +0.33 to +0.42) sit at or below 0.5. On this task family, at this cost per
sample, the question "does a workflow add ~0.5 point?" is **unanswerable at any budget the owner has approved so
far** (the largest single allocation was 160 calls). A structural-search *campaign* comparing two parent
policies with campaign-level variance on top is an order of magnitude further away. The C1 design concedes
this: "the first pilot is likely descriptive; a null result is a valid outcome".

---

## 4. Conceptual critique of structural search / cumulative campaigns

**The idea.** An LLM mutates a whole `.orc` module, the compiler admits it, a judge scores it, and a Pareto
archive plus reservoir guides further mutation. It is GP with an LLM mutation operator and an LLM fitness
function. For this system, as evidenced, it is not promising.

1. **The fitness function is the bottleneck, and it does not work.** GP needs many cheap, low-noise fitness
   evaluations. Here each one costs 30–80 min, 1–6 calls and millions of tokens, has σ ≈ 1 on an 8-point
   ordinal scale with batch effects, and placed the known-best solution at or below the candidates. Selection
   on that signal is selection on noise; a Pareto archive over noise is noise. All of C1 (store, reservoir, two
   parent policies, revisit/futility rules, budget cuts at 50/75/100% of `B_plan`) sits downstream of a measure
   that has never passed.
2. **The search space is tiny and already enumerated.** For a single coding task under a two-model cap, the
   meaningful design choices are about five: direct, plan-first, review/revise, best-of-n with a selector, and
   check/repair, crossed with which model sits where. The authored catalog *is* that space. Phase 1 enumerated
   it, and nothing separated. The three-arm mutators, given freedom, rediscovered one member of the catalog
   (after reading it: "the episode-1 mutator read the catalog seed `implement_check_diagnose_repair.orc`"). When
   enumeration of the whole neighbourhood is flat, multi-generation stepping-stone search has nothing to climb.
3. **The environment gives feedback-shaped programs nothing to use.** `dev-check` passed at base in every
   evaluation, so every check-gated child degenerated to `direct` plus a check. Orchestration can only matter
   where intermediate signals exist (failing tests, reviewers with different knowledge, independent
   candidates). The task family supplies none by default.
4. **The typed representation has not shown discriminative value.**
   - Admission accepted 18/18 proposals in all three interfaces, including the Python diff arm.
   - The I3 Python arm converged on the same idea.
   - The representation hypothesis ("operator-design freedom beats proposer fluency", roadmap §Thesis) needs
     arms that *differ* in proposal quality. None did.
5. **The prior literature result the roadmap cites (LLM mutation chains collapse onto few structural forms) was
   reproduced on the first try.** That should have redirected the programme, not motivated a reservoir.

**A much cheaper, sharper test of the core hypothesis** ("searching orchestration programs finds better
quality/cost trade-offs than the obvious hand-written ones"):

- **Step 1 — enumerate once on a cheap oracle.** Pick 30–50 small, independent tasks with pre-existing
  executable tests, not authored per task. Examples: a public bug corpus subset, or this repo's own small
  historical bug fixes with their regression tests, run outside this repo's home and installs.
- **Step 2 — tabulate.** Run the existing 5-seed catalog, plus 2–3 model placements, once per task with mid-tier
  models. That is about 8 programs × 40 tasks ≈ 320 evaluations at ~5 min each. Record pass/fail and metered
  tokens.
- **Step 3 — run search on the cached table at zero marginal cost** (a "NAS-Bench" surrogate).
  - Does any program Pareto-dominate `direct` (pass rate vs tokens), with bootstrap CIs?
  - Would a search policy (random, greedy, an LLM proposer choosing among recorded programs from feedback) find
    it with fewer evaluations than exhaustive enumeration?
- **Step 4 — only if a program dominates by a material margin** (e.g. ≥ 10 pass-rate points at ≤ 2× tokens),
  test LLM *generation* of new programs. A generated child must then beat the best enumerated one on fresh
  tasks.

This replaces C1/C2 with a single table. It answers whether there is anything to search for, which is the
question the current apparatus cannot reach.

---

## 5. Directions

### Most promising (with the cheapest decisive experiment)

1. **Oracle-scored small-task benchmark as the primary measure.**
   - Reverse the "no hidden tests as primary" policy *for tests that pre-exist the task*. The owner's objection
     ("too brittle and hard to design correctly", E-B3 §The amendment) applies to tests written per task for
     prescriptive internal features, not to an existing test suite.
   - The measurement plan already lists "(i) hidden acceptance primary" as a failure-branch option
     (`docs/plans/2026-10-19-orc-structural-search-measurement-plan.md` line 560).
   - Decisive experiment: 30 tasks × {direct, best-of-3 with *executed-test* selection, implement → test →
     repair} × 1 rep, with Luna/Terra-class models: ~30 × (1 + 4 + 3) ≈ 240 short calls. Freeze the "ORC
     workflow > direct" line if neither workflow beats direct by ≥ 10 pass points within 3× tokens.
2. **Selection and verification as the lever, analysed from data already collected (zero spend).**
   - Both positive results come from selection or an independent reviewer. E-A shows candidate spread up to
     3.5–8 within a run, with the selector picking at or below the group mean 2/6 times.
   - E-A, E-B2, E-B3 and Phase 1 pools already hold dozens of patches with per-clone hidden results and two
     judges' scores.
   - Compute offline what selection by hidden tests, by each judge, or by agreement would have gained. If even
     an oracle selector gains little on these tasks, best-of-n is not worth live spend here.
3. **One judge-reliability study, run once, cheaply, to settle (c).**
   - Re-judge ~20 already-captured natural patches that have hidden results, twice each, absolute and pairwise
     against upstream (Phase 1 Next Step item 1). That is ~6–10 judge calls.
   - Report test–retest SD, rank correlation with hidden fraction, and batch-composition effects. If ρ with
     tests is < 0.5 or retest SD ≥ 1, stop using rubric scores for anything finer than absent/present.
4. **Measure ORC's distinctive engineering properties, offline and deterministically.**
   - The charter's other hypotheses (resume, introspection, reuse) need no LLM judge. Use kill-at-every-commit
     resume correctness, typed-outcome routing and provenance for a long multi-call workflow vs an equivalent
     LangGraph/Python version, with scripted providers.
   - The adversarial DAQ run found parity on its claims. One focused comparison where ORC should win by
     construction (e.g. exact-once side effects across crash/resume) either establishes a niche or confirms
     parity.
5. **If search is pursued at all, the cached-table surrogate of §4.** It costs the enumeration only and answers
   both "is there a better program?" and "does LLM-guided choice beat random choice?".

### Stop or freeze

1. **C1 cumulative campaigns, C2 fragment evidence, V2 receipts, `amends_6`, sealed-split exposure machinery
   and the `module` live arm** (`docs/design/orc_structural_search_cumulative_campaigns.md`, the C1 plan, the
   driver's qualification sections). Their prerequisites failed, and power is unattainable (§3.4). Keep the
   offline code; do not maintain gates for it.
2. **The RPI/PRR natural-difficulty iteration loop.** 11 iterations and 80 starts produced one pass, and only
   under a relaxed rule. The pass probability arithmetic (§3.2) means more iterations mostly buy noise. Do not
   build further studies on repo-internal features of this runtime.
3. **The 4-criterion additive rubric** (`score.orc`: root cause / scope / generality / layering) as a quality
   measure. It ranks upstream below candidates and rewards incomplete tidy work. Keep it historical only.
4. **Design-review-execute / plan-first as a treatment line** for coding tasks: 0.00 hidden gain at 4.9× wall
   clock (E-B2), and 0/3 valid runs (E-B3). Do not revisit without a reason from direction 1.
5. **The per-step governance apparatus for small pilots.** This covers multi-thousand-file hash packets,
   per-judge integrity reviews and budget declarations for 1–3 calls, experiment-specific exceptions in
   `AGENTS.md`, and 5-document status synchronization per run. Replace it with one short protocol per study:
   frozen criterion hash, clone-id join, contamination scan, receipts, and one report. Also close out the R1a
   `orc_research_demo` (decide whether to commit or delete its September untracked evidence; the proposed
   USD 15 repair is low value) and record adversarial DAQ as a negative result.

---

## 6. Experiment directories (one line each)

| Dir | What it is | Produced a result? | Alive? |
|---|---|---|---|
| `adversarial_daq` | **Untracked.** Builder/skeptic `.orc` debate seeking a scoped advantage of ORC/typed Python over LangGraph/Python for LCLS-II DAQ debugging (synthetic plant; 47 k files, including a vendored copy of the repo) | Yes: 4 rounds, all claims refuted or at parity; ORC slower in case wall time | Finished 10-23; uncommitted and undocumented in `docs/` |
| `agent_chess` | Toy two-agent chess loop (Sol vs Opus) | No recorded games | Dormant demo |
| `compare` | The comparison harness: shims, bubblewrap, scan, pools, `score*.orc`, criteria, task packages | Basis of E-A…PRR-P2 | Alive (last change 10-24) |
| `evaluated_execution_spike` | Throwaway September prototype for the evaluated-route decision | Historical design decision | Dead (read-only history) |
| `mlevolve_pair` | ORC vs Python MLEvolve-like search with deterministic leaves | September: ORC blocked by a 256-node limit; now runs at 2.39, no live claim | Maintained specimen, no research use |
| `orc_effectiveness` | Frozen lean-pilot evidence; ES F1 schemas (study declared invalid) | Lean pilot: forfeits; ES: none | Dead |
| `orc_gp_example` | Offline toy (mu+lambda) GP over ORC programs with a scripted agent | Toy only; no claim | Demo |
| `orc_repetition_census` | Static census of repetition in `.orc` sources | Yes (language-design evidence) | Done |
| `orc_repl_feature` | The `design_review_execute` variant that built `orchestrator repl` (Fable/Sol, 10-12) | Shipped a feature; unmeasured | Dormant |
| `orc_research_demo` | September R1a "ORC as programming medium" pilot: four-arm trials, OMP cost gate, independent assessment, assisted C1 ORC/Python handoff. **The many untracked files** (assessment API/binding/evidence, cost gate, `development/`, sessions) are its 09-08/09 evidence and development artifacts; the only 10-19 edits add a "next owner decision" for a USD 15 invocation-guidance repair | Yes (qualitative: Python more direct for value flow; checker design errors) | Closed; untracked evidence needs a commit-or-delete decision |
| `orc_structural_search` | Driver, mutator interfaces I1/I2/I3, module condition, C1 campaign store/reservoir, qualification V1/V2, metering/pricing (11.6 k lines) | Phase 1 inconclusive; three-arm measure-free | Offline only; no live selection |
| `orc_vs_python_showcase` | Conceptual ORC/Python snippets | No | Static docs |
| `orc_vs_single_call` | September best-of-n / reviewed_change workflows, rubric, task | Yes (#3, the only positive result) | Workflows maintained; study closed |
