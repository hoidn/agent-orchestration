# ORC Structural Search Measurement Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** selected for offline Tasks 1–5 and live Step A. The owner explicitly approved Step A at 8 calls, cap 10 on 2026-10-19 (`ac58e0ba`); do not ask for the same approval again. Offline Tasks 1–5 are complete and verified; implementation `I=25ca21e1` and criterion freeze `F=cc5464ac` passed independent review. Task4 reuses audited receipt/pricing APIs. Step A completed exactly 8 calls under its approved cap 10 and failed: RPI exceeded the spread limit, while PRR passed. [The A report](../reports/2026-10-19-orc-structural-search-measurement-calibration.md) records the joined results, scans and complete receipt costs. The reference-free A′ implementation passed offline review and verification; its offline packet is ready and frozen at `I_A2=49cd27e6` / `F2=f58d70db`, but the owner reiterated the no-Claude restriction on 2026-10-20 without an expiry while authorizing A′'s 8 planned calls, cap 10, subject to that restriction. The frozen Sonnet/Terra packet is incompatible and remains blocked; a prospective Terra-only amendment is under design review, with no model/rule change or new criterion accepted yet. B, B2 and C retain separate approval gates. Preparation and freeze establish no calibration or quality result.

> **Revision 2026-10-19** (after the independent review, coordinator rulings C1 and I1–I10 applied): a fourth blind control per task, the `mutant` (upstream with one behaviour-breaking edit), and rule P3 `total(upstream) − total(mutant) ≥ 2`, so a judge that scores similarity to the disclosed reference fails calibration; fillers are only patches that pass `git apply --check` on the amended seeded base, drawn from the retained Phase 1 pools and the three-arm final patches, with exact counts and a minimum; the authoritative gate-3 check is controller-side and restores the package's `dev-check.json` and promoted test before running (`evaluation.check_first_attempt`); Step C (the check-gated seed's own coder) is required and is the gate-3 measurement, Step B's figure beside it; a new `calibration-amends-5.json` references the unchanged historical criterion and records `amends_5` (frozen implementation commit, reviewer `gpt-6.1-sol`, amended package hashes) before Step B; B2 has its own per-pool verdict plus `summarize.calibration_over`; the failure-policy rerun is its own owner-gated step (A′) and the worst-case total is stated (50 calls); the driver design and harness D6 are amended offline before any spend; `summarize` skips `reference` clones and reads a mapping without `rubric` as the historical rubric; `score_ref.orc` runs end to end with scripted providers before the criterion freezes; no `calibrate.py` (shared `pool.write_pool`, `pool.pool_from_diffs`); citation, count, metering-mapping, measurement-order, batch-size, judge-scan and ledger minors applied.

> **Owner model-cap amendment 2026-10-19 (prospective):** every experiment route, including judges, reviewers, coders, nested CLI processes and native agents, is limited to mid/low tiers at or below Sonnet/Terra; Fable remains forbidden. This measurement uses exactly `claude-sonnet-5-5` and `gpt-5.6-terra`. No provider spend is authorized by this amendment. Historical criteria, provider JSON, `score.orc` and the revision chronology above remain unchanged; historical high-model arms refuse until separately amended.

### Selected offline model-cap task

- [x] Extend the existing basename-dispatched guard to both `claude` and `codex`, default/pin Sonnet and default Terra, and reject higher/unknown explicit/fallback models even when a criterion allowlist includes them. Keep narrower criterion restrictions.
- [x] Install both guarded names atomically, preserve stdin, arguments, live capture and status, and cover nested PATH launches. Disable Codex `multi_agent`, `multi_agent_v2` and `multi_agent_v2_dynamic_tools`; reject model/config/profile/provider and multiagent-enabling overrides while retaining ordinary effort overrides.
- [x] Make actual Claude `message.model` and Codex `turn_context.model` violations non-clearable; printed model names remain ordinary text. Absolute CLI paths, reset PATH and direct APIs remain explicit prevention boundaries.
- [x] Bind the current `review_once` reviewer to Terra high and compare its shared review contract with model masked. Dedicated guard/scan, parallel installation and scripted public-CLI checks passed; guard `9b878563` was independently approved with 14 additional targeted checks. Broad integration remains a separate pending gate; no new criterion was frozen and no paid call ran.
- [x] Before Task 5 freezes prospective inputs, verify judges Sonnet/Terra high; Step B direct/review Terra high; Step C coder Sonnet medium and diagnosis Terra high in the external measurement-specific seed copy, preserving the historical seed. Step A′ retains both judge IDs and selects only the predeclared alternative (b), rubric-only without a reference; there is no third admitted judge ID to swap in.

Model-cap offline evidence (2026-10-19): implementation commits `c639f171` and
`f900bf5d`; dedicated guard/scan suite **75 passed in 5.00 s**, including public
`orchestrator run` with scripted Terra completion and forbidden Sol refusal.
Remote-dispatch restrictions had 18 failing regressions before the correction;
local CLI help identifies their independent cloud/server routes. Actual local
`codex ... features list` reports all three multiagent features false. Copies of
launch fixtures use capped models while historical workflow sources stay unchanged.
I3/ORC copied-parent checks passed **4 in 23.01 s**; repair/mutator checks passed
**3 in 18.26 s**; dual-CLI parallel installation and allowlist checks passed
**5 in 25.29 s**. Touched-test collection found **315 tests**. The first full
experiment suite under tmux reported **42 failed, 1040 passed in 203.65 s**:
21 existing Phase-2 readout failures concern descriptive historical `rubric`
strings (one reproduced on unchanged `f8d0ce7b`); the remaining launch-fixture
failures prompted the capped-copy changes. Full green integration is pending the
separate historical-rubric correction and final fixture verification. Logs are
`/tmp/measurement-model-cap-{suite,baseline,final-suite,final-collect}.log`.
The changed production scanner is 166 lines, maximum counted complexity 6;
both Bash guards pass syntax checks. No provider spend or criterion freeze ran.

Independent guard-review corrections: reject Codex `app-server` (its protocol
can choose a per-turn model), and validate the primary model as one exact ID;
only fallback arguments split comma-separated lists. Five new regressions
failed before these fixes. Capped temporary three/four-arm criteria now match
the Terra mutator envelope and capped copied parents, while historical criteria
remain unchanged. The focused guard/three/four-arm suite collected **99 tests**
and passed **98 in 94.99 s**; its one remaining uncapped Python-copy fixture was
corrected with the existing helper and that selector then passed **1 in 31.75 s**.
The dedicated guard/public-CLI and preflight selectors passed **82 in 5.72 s**;
refused-module and public parent-smoke selectors passed **2 in 30.79 s**.
Evidence: `/tmp/measurement-model-cap-review-{suite,collect}.log`; final full
integration is retained for the coordinator after the remaining Task 3 changes.
No provider call ran.

**Goal:** Close gates 2–4 of the [module plan](2026-10-19-orc-structural-search-module-rewrite-plan.md#gate-for-a-live-module-arm) and the roadmap's Calibration decision point: a blind judge measure that passes a predeclared calibration on known controls (upstream, stub, partially reverted upstream, and a near-copy mutant), a task family whose agent-visible `dev-check` fails at the first attempt often enough that check-gated control flow branches, both on family (a) rungs 2 and 4 under the frozen difficulty rule, and metering wired with a frozen per-model price table, so the owner can assess the remaining prerequisites for a later live Phase 2 or `module` arm. A future structural quality study still needs its separately selected V2 qualification integration.

**Architecture:** Extend `experiments/compare/` in place: a second scoring workflow `score_ref.orc` (intent-anchored absolute rubric with one disclosed reference clone per batch), rubric selection through the criterion in `pool.py`/`summarize.py`, a shared `pool.write_pool` used by `pool.pool`, `scoring.build_pool` and the new `pool.pool_from_diffs` (calibration pools from recorded diffs), and `calibration`/`calibration_over` verdicts in `summarize.py`. Task packages gain `-partial.diff` and `-mutant.diff` anchors and a promoted visible test file; the authoritative check of a first-attempt patch is controller-side in `evaluation.py`. The driver already records native receipts; reuse `metering.receipts` and `pricing.cost` with the criterion's separate `price_table`, extending only missing calibration reporting joins. Preserve structural quality admission before the shared writer and its `mapping.qualification` receipt. Calibration uses the generic comparison harness; Step C uses the explicit measure-free structural route. Qualification V2 for a future rubric/task-family study is deferred. No duplicate metering/discovery API or change under `orchestrator/`.

**Tech Stack:** Python 3.13 standard library; `orchestrator` public CLI (judge runs of `score_ref.orc`); `experiments/compare` shims (bubblewrap), `pool.py`, `summarize.py`, `prepare.py run/collect/scan`; retained evidence `/home/ollie/ss-pools/phase1/*` and `/home/ollie/ss3-work/records/*` (patches as fillers, zero spend); tests with the scripted judge in `tests/experiments/compare_harness_support.py`, `orc_structural_search_support.py` and the evaluated-route consumer shims in `tests/workflow_evaluated_consumer_sources.py`.

**Spec:** `docs/design/orc_structural_search_driver.md` ("Task Family And Evaluator": the P1 rule; "Objective, Selection And Local Observations"; "Metering And Consumption": the field mapping, including the cache-write-inside-input clause); `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (Decision Points: Calibration row; Phase 2 gates; Family candidates and cost inputs); `docs/reports/2026-10-18-orc-structural-search-phase1.md` (Anchors And Judges; "The agent-visible check carried no signal"; Next Step); `experiments/compare/criteria/calibration.json` `amends_4` with its `runtime.validity`, `rung_packages` and `review` clauses; `docs/design/orc_effectiveness_comparison_harness.md` D4–D6 and the 2026-10-15 evaluation policy; the module plan's gates 2–4.

## Integration Scope And Tradeoff

Use the merged apparatus at `62e3776f` and implement only the reference-rubric,
calibration-pool/verdict and controller-check deltas. This keeps a future quality
study harder to launch until its V2 qualification contract is selected, but avoids
an unrequested receipt framework or a bypass of the current fail-closed V1 gate.
Tasks 1–5 use scripted providers only; their completion does not qualify the family,
calibrate the measure or select a live structural-search study.

## Global Constraints

- Owner rules, binding: no provider spend on a quality comparison before both calibrations pass; "better" is Pareto over quality and metered deployed cost; no Fable model in any call (the shims' guard and scan apply to judges, single calls, reviews, coders); every live step is approved by the owner with its call estimate and the worst-case total before launch; hidden acceptance stays descriptive, and making it primary is offered to the owner as an explicit policy decision only in Task 9's failure branch.
- Work in the isolated `feat/structural-search-measurement` checkout from merged `main` at `62e3776f`; no file under `orchestrator/` changes. Every touched production apparatus module stays ≤ 500 lines and every function ≤ cyclomatic complexity 12 (verbatim promoted/captured test fixtures are exempt from this apparatus budget); no test asserts prompt text. Reuse the current responsibilities instead of stale line counts. Preserve historical `calibration.json`, its continuation, the three structural criteria, provider JSON and `score.orc` byte-for-byte; create a separate amendment and calibration criteria.
- Family: `experiments/compare/tasks/resume-projection-integrity` (rpi, base `1cd607673c89170dc96c74a0b5eb4aef204da82d`) and `pure-result-replay` (prr, base `f80e551a6cdeca6a2913ce640326495be1ae1cc5`); rung 1 `cf1-generic-unions` is reserved for a later sealed split and is not amended. Solution hashes are operator-supplied (`--hash`/`--solution`), never written into a package or criterion.
- Rubric v2 (`score_ref.orc`): criteria `completeness`, `correctness`, `scope`, `layering`, each `S0|S1|S2`, total 0–8, averaged over judges; one disclosed reference clone per batch (the upstream anchor applied; arm `reference`, never rated, never scored); blind anchors in every batch, four roles: `<pkg>-upstream`, `<pkg>-stub`, `<pkg>-partial`, `<pkg>-mutant`. A batch holds at most 10 repositories including the reference (D4): reference + 4 anchors + ≤ 5 fillers.
- Calibration predicate, frozen in `experiments/compare/criteria/judge-calibration.json` before any judge call, per (judge, batch) with failing fraction ≤ `error_rate = 0` for each rule: P1 (the design's rule) `total(upstream) − total(stub) ≥ margin = 4`; P2 strict ordering `stub < partial < upstream`; P3 `total(upstream) − total(mutant) ≥ mutant_margin = 2`; cross-batch spread of each blind anchor per judge ≤ `anchor_spread_limit = 2`. The denominator is every predeclared judge × batch pair; an excluded or absent judge, missing control or incomplete rating fails its pair, never shrinks the denominator. A pool passes when P1, P2, P3 and the spread hold; calibration needs both tasks' accepted Step A pools (A′ if that rerun passed instead). B2 must pass and `calibration_over` compares it with that actual accepted A or A2 baseline, keeping every anchor's spread within 2.
- Judges: `claude-sonnet-5-5` (`experiments/compare/score.providers.json`) and `gpt-5.6-terra` (`experiments/compare/providers/score_codex.json`), effort `high`, `:timeout-sec 3600` per batch; Step A: 2 batches per task, 5 fillers each when available, minimum 4 per batch (8 per task; `pool_from_diffs` refuses below), fillers disjoint across a task's batches, dealt by `random.Random(filler_seed)`; B2: 1 batch per task, fillers = the Step B single-call patches plus applicable fillers unused in the union of every earlier A/A2 pool (including failed A), up to5/minimum2; the two or three B patches can satisfy the minimum without any retained filler.
- Fillers: only patches that pass `git apply --check` on the amended seeded base (Task 2 records the applicable list and its sha256s in the criterion). Candidates verified read-only on 2026-10-19: rpi 20 (14 Phase 1 non-anchor + 6 three-arm `collected/final.diff`), of which 11 touch `tests/test_runtime_step_lifecycle.py` and at least 10 apply (the reviewer's scratch check: 8 of the 14 Phase 1 patches; 2 three-arm patches touch neither frozen path); prr 19 (13 + 6), none touching a frozen path, all applicable. Exact applicable counts are recorded by Task 2 Step 5 before the freeze.
- Family rule: new `calibration-amends-5.json` references unchanged `calibration.json` (`amends_4`) and declares `amends_5` (Task 5): k = 2 `direct_task` single calls (`gpt-5.6-terra`, `high`, 14,400 s), one `review_once` each with reviewer `gpt-5.6-terra` (owner directive 2026-10-19), the first two samples qualify at mean blockers ≥1.5, an initial mean in [1,1.5) requires a third pair and final mean ≥1, and an initial mean below1 fails; valid runtime = this plan's frozen `RT` commit; amended package sha256s recorded. Step B does not run without `amends_5`.
- Gate 3 (predeclared): measured in Step C on the check-gated seed `implement_check_diagnose_repair` (coder `claude-sonnet-5-5` medium 5,400 s; diagnosis `gpt-5.6-terra` high in a measurement-specific copy of the seed), 2 evaluations per task; band: at least one of the two evaluations per task has a failing first `dev-check` under the controller-side check (`evaluation.check_first_attempt` on the first coder call's patch, package files restored). Step B's first-attempt figure (the `gpt-5.6-terra` single calls) is reported beside it and decides nothing. The agent-side `dev_check.py` in the clone is advisory.
- Metering: retain raw `receipt_usage` and existing per-call/model provenance from `metering.receipts`; price at report time through `pricing.cost(row, criterion["price_table"])`. `price_table` has `currency: "USD"`, positive `tokens_per_unit`, `source`, ISO `date`, and `models` with `input`, `output`, `cache_read`, `cache_write` rates. Copy rates from official provider pricing on the freeze date; select none here. Existing receipt mapping charges Claude's four categories directly; Codex uses the last cumulative total to distinguish cache-write inside input from separate cache-write and never adds reasoning output. Missing or inconsistent receipt/category/model/rate evidence remains `unavailable`. Do not add `metering.consumption`, `metering.price`, a second session discoverer or a pricing `models` alias.
- Budgets (provider calls, charged as in Phase 1; immediate zero-work refusals listed, not silently subtracted): Step A judge calibration 8, cap 10; Step A′ (rerun after the one predeclared revision, only if A fails) 8, cap 10, its own approval with the revised hash; Step B family re-qualification 8 (+2 per borderline task, +1 per frozen-rule review rerun), cap 14; Step B2 replicate 4, cap 4; Step C gate-3 measurement ≤ 12 (2 tasks × 2 evaluations × ≤ 3 calls), cap 12. Planned without A′: 32; worst-case total across all steps: 50. These are planning bounds; A (8 calls, cap 10) was approved, and A′ now has conditional authorization for 8 planned calls, cap 10, under the continuing no-Claude restriction. Its incompatible frozen packet remains blocked; B, B2 and C need separate approval. Order A → (A′) → B → B2 → C; A first because it is the cheapest step that can falsify the evaluator. Codex quota floor as in Phase 1 (no new launch below the owner-stated window floor unless the credit policy covers it).
- Live roots: historical A used `RT=/home/ollie/sc-runtime` at I. Prospective A′, B, B2 and C bind `RT=/home/ollie/sc-runtime-a2` at `I_A2=49cd27e6`, with external inputs under `E/freeze-a2` and repository criterion freeze F2; neither runtime is repinned by later documentation merges. Work root `W=/home/ollie/sc-work` uses separate `W/B` and `W/C`; pools `P=/home/ollie/sc-pools/<task>/<A|A2|B2>`; evidence/ledger `E=/home/ollie/sc-evidence` holds `ledger.md`, criterion/source hashes, `solutions.txt` and `E/C` driver evidence. Roots stay outside the main prefix and `/tmp`, `/dev/shm`, `/var/tmp`. Existing `ss-*`, `ss3-*`, `calib-*` evidence is read-only. C masks each earlier evidence/work/pool root with inherited `COMPARE_HIDE` and repeats it as `--holdout` for scanning; `--hide` alone masks episodes only. Never mask shared ancestor `W`, runtime or the current C tree.
- Verification: narrow selectors first, `pytest --collect-only` on new or parametrised test modules, then `pytest -q -n 16 --dist=worksteal tests/experiments/ tests/test_workflow_evaluated_compare_score.py`; commits with pathspecs, one per task, messages in the repository's existing style.

## Review Focus

1. A judge that scores similarity to the disclosed reference passes P1 and P2 by construction (upstream is byte-identical to the reference, partial is the reference minus a module, stub is nothing); only P3 catches it, because the mutant keeps ≥ 95% of the reference's lines and must still lose ≥ 2 points (Task 2 `test_calibration_verdict_fails_a_similarity_judge_on_the_mutant`). "A different correct implementation scores like upstream" stays untested: no retained patch reaches hidden 1.00 (maximum 0.843), so no such control exists; Task 9 reports this.
2. An agent that edits the promoted visible test, `dev-check.json` or its `argv` so its own check passes: the controller-side check restores those files from the package before running and reports which frozen paths the patch touched (Task 3 `test_check_first_attempt_restores_frozen_files_before_running`).
3. A pool whose `rubric` differs from the criterion's is refused; a historical mapping without `rubric` summarises under the `score.orc` rubric without refusal; a reference clone never enters run rows, anchor figures, ratings or hidden acceptance (Task 1 `test_summarize_refuses_a_criterion_whose_rubric_differs_from_the_pools`, `test_summarize_reads_a_mapping_without_rubric_as_the_historical_rubric`, `test_summarize_skips_reference_clones_everywhere`).
4. A metered run with one unmatched shim call, a Codex rollout without a model name, or a nonzero `cache_write_input_tokens` inside `input_tokens` must price `unavailable` or by the design's clause, never 0 or double-charged (Task 4 `test_price_is_unavailable_with_an_unmatched_call_or_unknown_model`, `test_codex_cache_write_inside_input_is_charged_once`).
5. Four anchor files per package change every future pool's arithmetic: batches must carry every package anchor and never exceed 10 repositories including the reference (Task 1 `test_pool_batches_carry_every_package_anchor_and_stay_within_ten`); the extra anchors also enter `anchor_checks`' spread under the frozen `phase2.json` (ladder note, Task 3).

## Decisions

1. **Evaluator: intent-anchored absolute rubric with a disclosed reference (recommended).** Alternatives weighed: (a) pairwise comparison against the upstream fix: removes batch effects but yields no scale for a frontier and cannot separate a stub from a partial without magnitude; rejected. (b) Rubric change only (add `completeness`, blind batches, no reference): cheaper, but the judge still rates within the batch, so drift remains; kept as the one predeclared revision (Step A′) if (c) fails. (c) Absolute rubric plus a disclosed reference clone per batch: the reference fixes the top of the scale in every batch; the instruction is to rate against the intent and the reference, not the other repositories; a repository implementing none of the intended behaviours scores S0 on every criterion (the Phase 1 defect: the stub earned `scope`/`layering` points for doing nothing); a different implementation providing the behaviours scores S2 on `completeness`. The risk that a judge scores similarity to the reference is controlled by the mutant and P3, not by prompt wording. Hidden acceptance as primary is offered only in Task 9's failure branch.
2. **Calibration experiment.** Controls per task, all blind, authored offline at zero spend: upstream; stub (existing); partial (an existing upstream patch with one integration component omitted, proved to preserve one named required behavior and omit another); mutant (an existing upstream patch with one behavior-breaking edit affecting an explicit requirement and retaining ≥95% of upstream added lines). The selected semantic construction amendment below supersedes the original hidden-fraction selection bands; fractions are descriptive. Margins: P1 = 4 because a stub can earn at most 4 points on `scope` and `layering` under the S0-everywhere rule and an upstream copy earns 8; P3 = 2 because a behaviour-reading judge must drop the mutant's `correctness` to S0 or S1 and its `completeness` to at most S1 for the broken behaviour, one full step on two criteria, while a similarity judge gives a 95%-identical tree 7 or 8; error rate 0 over 8 (judge, batch) pairs per rule. Control order rests on construction; hidden fractions confirm it and decide nothing (ledger entry, owner acknowledgement in the Task 6 ask). Fillers are retained patches, so judges see realistic batches at zero spend. Failure policy: one revision only, alternative (b) rubric-only without a reference, retaining both judges, a new criterion hash and Step A′ under its own approval; a second failure declares the judge measure uncalibrated for the family (Task 9 failure branch).
3. **Family and check.** Keep rpi and prr. Promote one whole hidden test file per task, `tests/test_runtime_step_lifecycle.py` (8 and 5 hidden nodes; failed on 13/14 and 13/13 retained blind patches), into `seed/tests/`, drop its node ids from `hidden_tests.txt` (111 and 129 remain), add it to the front of `dev-check.json` `argv`. Alternatives weighed: hand-written check commands (authoring cost, unverified against the solution); the full suite as a regression net (slow inside 1,800 s, rate unknown); a larger promoted file (51 or 104 nodes would make the task a visible-test task). Because a coder can run a visible test in-call, the first-attempt failure rate is unknown and is measured in Step C on the seed's own coder, Step B's figure beside it. The agent-side `dev_check.py` is advisory; the authoritative measurement restores the package's files (I2). The package change needs re-qualification under the frozen rule with `amends_5`; two tasks now, rung 1 reserved.
4. **Metering.** Reuse recorded native receipt usage and `pricing.cost` with `criterion.price_table`; re-pricing never rewrites a log. No duplicate consumption or pricing implementation.
5. **Minimal footprint.** No new module: `pool.write_pool` is shared by `pool.pool`, `scoring.build_pool` and `pool.pool_from_diffs`; `score.orc` stays frozen as the historical rubric and the ablation control; the extra anchors join every future pool through the existing `anchors/*.diff` glob.

## Feasibility And Existing Boundaries (merged `62e3776f`)

- `pool.pool(task, criterion, out, judges, runs)` already receives the criterion path; its tail (guard, mkdir, `build_batches`, mapping, `write_score_inputs`, chmod) is what `write_pool` extracts; `write_score_inputs` hard-codes `score.orc` and `score::score` (`pool.write_score_inputs`); `scoring.build_pool` is a declared copy (`scoring.py`, `ponytail:` note) and gains the same call.
- `summarize.CRITERIA` is a module constant used by `join`, `agreement` and the totals; `clone_scores` in `summarize.py` and the per-clone ratings in that module iterate every id in `mapping["clones"]`, so a reference clone outside the judges' batch lists would raise `KeyError` unless skipped; `hidden_acceptance` would run on it; `scoring_run` checks only the bound criterion hash and judge model; `anchor_scores` keys on `arm == "anchor"`; Phase 1 `mapping.json` files carry no `rubric` key.
- Anchors are discovered by `sorted((task / "anchors").glob("*.diff"))` in `pool.build_batches`; `scoring.ANCHORS_PER_BATCH = 2` sizes `split_batches` (`scoring.split_batches`) and `adaptive.planned_judged`; `anchor_checks` reads roles `upstream`/`stub` only.
- `seed/dev-check.json` lists base-green modules in all three packages (cf1 in `37a9ff5c`, rpi and prr in `66fedf1e`); `dev_check.py` reads `dev-check.json` from the clone, needs `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, and is copied into the clone and git-excluded by `evaluation.evaluate` (`evaluation.py:162–165`); `dev-check.json` is seeded, committed and editable by the agent, which is why the authoritative check is controller-side.
- Retained patches: `/home/ollie/ss-pools/phase1/<task>/records/{mapping.json,patches/<id>.diff,results.json}` (rpi 18 clones, 14 non-anchor; prr 17, 13) and `/home/ollie/ss3-work/records/<eid>/run-1/collected/final.diff` (6 per task); counts of patches touching the promoted file per the Global Constraints; `results.json` carries `clones.<id>.hidden_failed`.
- `metering.receipts(records_dir, tree=, since=, home=)` already discovers scoped native sessions and returns `consumption`, `receipt_usage` and native episode paths; driver/evaluation rows already carry its output. `pricing.cost` validates the current `price_table` and complete receipt coverage. Codex cache-write handling is implemented and verified by the merged delivery; reuse it.
- `scoring.build_pool` calls `qualification.validate` before writing and stores the proof in `mapping.qualification`. Preserve both when extracting the shared writer. Current structural V1 admits only its pinned shipped `score.orc`, two-control measurement identity and frozen R55 family rule; the new rubric/amended packages cannot be relabeled to enter it. Generic comparison calibration and explicit measure-free C avoid no quality gate because neither selects or claims candidate quality.
- The existing driver accepts `--criterion`, `--seeds`, `--episodes`, `--agent-cmd`, `--replicates`, `--holdout`, and inherited `COMPARE_HIDE`. `mode1.run_mode1` validates the configuration criterion hash before reservation. There is no `--policies`; `--hide` is an episode mask, so zero-episode C needs the inherited mask plus explicit scan roots.
- `tests/test_workflow_evaluated_compare_score.py` runs `score.orc` on the evaluated route with the consumer shim as judge (`Program`, `install_shims`, `current_route`), so a parametrised copy of its inputs with a `reference` per batch exercises `score_ref.orc` end to end offline.
- `control/review_once.orc` binds the reviewer `:model "gpt-6-sol"`; `test_compare_review_once.py::test_review_once_compiles_the_reviewer_of_reviewed_change` asserts the reviewer call equals `reviewed_change`'s, so the `gpt-5.6-terra` ruling needs the model literal changed in `review_once.orc` and that contract test to mask `model`.
- `prepare.run --arm direct_task --set model=gpt-5.6-terra --set effort=high` and `--arm review_once --apply <final.diff>` are the frozen rule's arms; `collect` records `blockers`; the harness refuses roots under the main prefix or `/tmp`. The current harness differs from the historical frozen runtime, so the new amendment must declare the new implementation commit; rewriting `amends_4` in place would destroy its evidence identity.

---

### Task 1: Rubric v2 workflow, criterion-selected rubric, shared pool writer, end-to-end check

**Files:**
- Create: `experiments/compare/score_ref.orc` (module `score_ref`, export `score`; `Rating` with `clone`, `completeness`, `correctness`, `scope`, `layering`, `reason`; `Batch` with `clones List[String]`, `reference String`; `rate-batch` fills `intent`, `reference`, `clones`; `providers.judge` as in `score.orc`)
- Modify: `experiments/compare/pool.py` (`DEFAULT_RUBRIC`, `rubric()`, `write_pool()`, reference clone per batch in `build_batches`, `write_score_inputs`), `experiments/compare/summarize.py` (criteria from the mapping, reference skipping, rubric refusal), `experiments/orc_structural_search/scoring.py` (`build_pool` calls `write_pool`; anchor count from the package; `split_batches` size = `10 − anchors − (1 if reference)`), `experiments/orc_structural_search/adaptive.py` (task-specific capacity in existing `planned_judged` budget estimates through `scoring.fillers_per_batch(task, rubric)`; fresh adaptive launch remains unsupported), `experiments/compare/README.md` (score section)
- Modify: `tests/test_workflow_evaluated_compare_score.py` (parametrise `Program` over both workflows)
- Test: `tests/experiments/test_compare_pool_summarize.py`, `tests/experiments/test_orc_structural_search_scoring.py`

**Interfaces:**
- Produces: `pool.DEFAULT_RUBRIC = {"workflow": "score.orc", "entry": "score::score", "criteria": ["root_cause","scope","generality","layering"], "reference": None}`; `pool.rubric(criterion: Path | Mapping) -> Mapping`: absent or historical descriptive-string `rubric` means `DEFAULT_RUBRIC`; a mapping selects the workflow; other field types refuse explicitly. Pool construction, input writing, summarization and V1 dispatch share this normalizer.
- Produces: `pool.write_pool(task: Path, criterion: Path, out: Path, judges: Sequence[str], ref: Mapping, rows: dict, batches: list, *, qualification: Mapping | None = None) -> dict` (guard, sandbox visibility, mkdir, `build_batches`, mapping with `rubric`, `references`, `runs`, `clones`, `batches`, `write_score_inputs`, chmod; returns the mapping). `pool.pool` and `scoring.build_pool` call it. The structural caller keeps `qualification.validate` before this call and passes its verified proof through to `mapping.qualification`; generic callers do not gain structural quality authority.
- Produces: mapping gains `rubric` and, with a reference, `references: [clone id per batch]`; reference clone entries carry `arm: "reference"`, `labels: ["reference"]`; `score-inputs-<judge>.json` batches carry `"reference": <path>` and exclude it from `clones`; `score-<judge>.sh` names `rubric["workflow"]`/`rubric["entry"]`.
- Produces: `summarize.criteria_of(mapping) -> tuple[str, ...]` (`pool.rubric(mapping)["criteria"]`); `summarize()` refuses when `pool.rubric(criterion) != pool.rubric(mapping)`; clones with `arm == "reference"` are excluded from `clone_scores`, ratings, `run_rows`, anchor figures and hidden acceptance and reported under `clones` with `score: null`.
- Produces: `scoring.fillers_per_batch(task: Path, rubric: Mapping) -> int` = `10 − len(anchors) − (1 if rubric["reference"] else 0)`.

- [x] **Step 1: Write the failing tests** in `tests/experiments/test_compare_pool_summarize.py`:

```python
def test_pool_with_a_reference_rubric_adds_one_reference_clone_per_batch_outside_the_blind_list(world): ...
    # mapping["references"] has one id per batch, arm "reference"; score inputs carry "reference" and exclude it from
    # "clones"; score-<judge>.sh names score_ref.orc and --entry-workflow score_ref::score
def test_summarize_joins_the_pools_criteria_names_and_reports_them(world): ...        # totals 0-8 over the v2 names
def test_summarize_skips_reference_clones_everywhere(world): ...
    # no run row, anchor row, rating or hidden fraction names the reference id; clones[ref]["score"] is None
def test_summarize_refuses_a_criterion_whose_rubric_differs_from_the_pools(world): ...  # SystemExit mentioning rubric
def test_summarize_reads_a_mapping_without_rubric_as_the_historical_rubric(world): ...
    # mapping.json with the "rubric" key deleted, criterion without "rubric": summarises, criteria are the four old names
def test_pool_batches_carry_every_package_anchor_and_stay_within_ten(world): ...
    # four anchors + reference: each batch has four arm=="anchor" clones, at most 5 fillers, 10 repositories in all
```

and in `tests/experiments/test_orc_structural_search_scoring_rubric.py`: verify the shared writer preserves the validated `mapping.qualification`, unqualified structural pooling refuses before creating a pool, and reference-rubric structural quality pooling still refuses. Exercise the four-anchor/reference batch capacity through the generic comparison writer and verify `planned_judged` reserves the matching number of batches; do not weaken V1 to make either fixture pass.

- [x] **Step 2: Run them to verify they fail**: `pytest tests/experiments/test_compare_pool_summarize.py tests/experiments/test_orc_structural_search_scoring.py -k "reference or rubric or every_package_anchor or shared_writer" -v` — FAIL.
- [x] **Step 3: Write `experiments/compare/score_ref.orc`.** Same shape as `score.orc` (`:target-dsl "2.35"`, `list/map-effect ... :max 24`, `provider-result providers.judge ... :model judge_model :effort "high" :timeout-sec 3600`); `Batch` gains `(reference String)`, `rate-batch` fills `(reference :text)`. Prompt rules (behaviour, never asserted): rate each repository against the intent and the reference, not against the other repositories; the reference is the accepted implementation and shows which behaviours are required, not how to implement them; a repository implementing none of the intended behaviours scores S0 on every criterion; a different implementation providing the behaviours scores S2 on `completeness`; change nothing, run no tests. Criteria text: `completeness` (the behaviours the intent names are implemented: all S2, part S1, none S0), `correctness` (the implemented behaviours hold for the cases the intent names, judged by reading the code against the reference's behaviour), `scope` and `layering` as in `score.orc`.
- [x] **Step 4: Implement** `rubric`, `write_pool` (extracted from `pool.pool`'s tail; `pool.pool` keeps record loading, `pool_runs`, `compose` and calls it), the reference clone per batch in `build_batches` when `rubric["reference"]` (from `anchors/<task.name>-<reference>.diff`, entry `{"run": None, "arm": "reference", "labels": ["reference"]}`, ids into `references`), `write_score_inputs` from `mapping["rubric"]`; in `summarize.py` `criteria_of`, the reference exclusions and the rubric refusal beside the judges check; in `scoring.py` retain `qualification.validate`, call `write_pool` with the resulting proof, retain `mapping.qualification`, and use `fillers_per_batch`/`split_batches(size=...)`. The existing V1 guard still rejects the reference rubric for structural quality operations; generic calibration uses its independent writer route. Existing `planned_judged` call budgeting must use the actual per-task filler capacity as well, including four anchors plus reference; preserve the historical two-anchor case. Update its callers/tests without enabling fresh adaptive launches.
- [x] **Step 5: Run** the tests of Step 1 and the existing selectors: `pytest tests/experiments/test_compare_pool_summarize.py tests/experiments/test_orc_structural_search_scoring.py tests/experiments/test_orc_structural_search_adaptive.py tests/experiments/test_orc_structural_search_three_arm.py -v` — PASS (old-rubric pools keep their shape).
- [x] **Step 6: End-to-end with scripted providers.** In `tests/test_workflow_evaluated_compare_score.py` parametrise `SCORE` over `("experiments/compare/score.orc", "score::score")` and `("experiments/compare/score_ref.orc", "score_ref::score")`; for the second, `_inputs` adds `"reference": str(tmp_path / "pool" / "ref1")` per batch and `_ratings` uses the v2 names; assert one `Rating` per blind clone per batch in order and that no request's `repos` list and no rating names the reference path. Run `pytest --collect-only tests/test_workflow_evaluated_compare_score.py` then the module — PASS.
- [x] **Step 7: Commit** `experiments/compare/score_ref.orc experiments/compare/pool.py experiments/compare/summarize.py experiments/orc_structural_search/scoring.py experiments/orc_structural_search/adaptive.py experiments/compare/README.md tests/...` — "feat(compare): intent-anchored rubric score_ref.orc with a disclosed reference; shared pool writer; rubric selected by the criterion".

Task 1 verification (2026-10-19, scripted only): the new narrow selector failed six
expected missing-feature assertions, then passed 10 tests; reference binding drift
failed one test, then passed. The required selectors plus qualification and both
public scoring workflows passed **185 tests in 76.60 s** under tmux with
`python -m pytest -q -n 16 --dist=worksteal`. After the V1 dispatch closure,
qualification/scoring passed **105 tests in 8.69 s** and the extracted focused
rubric module passed **5 tests in 2.12 s**. Final collection of touched test modules:
**52 tests**. Evidence: `/tmp/measurement-task1-{red,green,suite,v1-suite,collect}.log`.
New structural rubric tests live in `test_orc_structural_search_scoring_rubric.py`
because the unchanged historical scoring module already has 520 lines. Every
changed production module remains below 500 lines and an AST branch-count check
found no function above 12. The necessary adjacent `qualification_measure.dispatch`
closure rejects a top-level selected rubric even with otherwise valid V1 evidence;
without it the proof validated `score.orc` while the writer selected `score_ref.orc`.
The regression demonstrated that path before the fix. No historical criterion,
provider binding, `score.orc`, or orchestrator file changed; no provider call ran.

Task 1 historical-rubric correction (2026-10-19): the broader suite exposed
that frozen `criteria/phase2.json` already has a descriptive string under
`rubric`. Treating every present field as a workflow selector incorrectly rejected
its otherwise valid V1 qualification and failed pool construction. The shared
normalizer now accepts a criterion path or decoded mapping: absent/string fields
select the historical workflow, mappings retain explicit selection, and invalid
field types refuse. Every rubric reader and V1 dispatch uses this one owner.
The actual frozen Phase 2 description is exercised through normalization,
pool/input construction, summarization and qualified dispatch; a reference mapping
still fails V1. The new module initially had **10 failing tests and 1 passing V1
rejection**, then passed **11 tests in 1.27 s**; **11 tests collected**. The existing
Phase 2 readout, qualification, rubric, pool, calibration, reference-integrity and
public `score`/`score_ref` scripted workflow selectors passed **176 tests in
28.86 s**, with `-q -n 16 --dist=worksteal` under tmux. Evidence:
`/tmp/measurement-rubric-compat-{red,green,collect,suite}.log`. Changed production
modules have 340/414/193 lines and AST complexity maxima 11/12/9. Frozen
criterion/provider/workflow bytes remain unchanged; no provider calls ran.

### Task 2: Calibration pools from applicable recorded diffs and the calibration verdicts

**Files:**
- Modify: `experiments/compare/pool.py` (`applicable()`, `pool_from_diffs()`), `experiments/compare/summarize.py` (`calibration()`, `calibration_over()`), `experiments/compare/prepare.py` (subcommand `calibrate`; judge-scan pattern), `experiments/compare/scan.py` (pattern `pytest|dev_check` for judges, reported), `experiments/compare/README.md` (calibration recipe)
- Test: `tests/experiments/test_compare_calibration.py`

**Interfaces:**
- Produces: `pool.applicable(runtime: Path, base: str, seed: Path, diffs: Sequence[Path]) -> list[Path]`: builds one seeded clone and keeps the diffs for which `git apply --check` exits 0.
- Produces: `pool.pool_from_diffs(task: Path, criterion: Path, out: Path, judges: Sequence[str], runtime: Path, fillers: Sequence[Path], batches: int, per_batch: int, min_per_batch: int, filler_seed: int) -> dict`: `ref` from the runtime and the seeded clone (`main`, `runtime`, `base`, `compare_base`), `rows = {}`, members `{"run": None, "arm": "filler", "labels": [diff stem]}` dealt without replacement by `random.Random(filler_seed)` into `batches` batches of `per_batch`; refuses when any batch would hold fewer than `min_per_batch` fillers or more than `10 − anchors − 1` repositories; calls `write_pool`.
- Produces: `summarize.calibration(results: dict, mapping: dict, criterion: dict) -> dict | None` when the criterion explicitly has `purpose: "calibration"` and `criterion["calibration"]` exists: `{"pairs": [{"judge","batch","upstream","stub","partial","mutant","p1","p2","p3"}], "p1_failing", "p2_failing", "p3_failing", "anchor_spread": {judge: {anchor: max}}, "passed"}`; roles from `criterion["anchors"][task.name]`; enumerate all declared judges × batches, including absent/excluded judges and missing/incomplete control ratings as failures; `passed` iff every failing fraction ≤ `error_rate` and every spread ≤ `anchor_spread_limit`; written into `results.json`/`results.md`.
- Produces: `summarize.calibration_over(results_paths: Sequence[Path], criterion: Path) -> dict`: `{"pools": {path: passed}, "anchor_spread": {judge: {anchor: max over all batches of all pools}}, "passed"}` (every pool passed and every spread ≤ limit); CLI `summarize.py --calibration-over R1 R2 ... --criterion C`.
- Produces: `prepare.py calibrate --task --criterion --out --judge ... --runtime --filler DIFF ... --batches N --per-batch N --min-per-batch N --filler-seed N` printing the applicable list and the refusals; `scan_judge` gains the reported pattern `judge ran tests` (`pytest`, `dev_check`) through the existing scan/adjudication flow: the hit remains pending until the operator inspects and records a cleared/contaminated verdict. It adds no automatic exclusion or informational-hit bypass; Fable remains non-clearable.

- [x] **Step 1: Write the failing tests** in `tests/experiments/test_compare_calibration.py` (fixtures from `compare_harness_support.world`; a package with four anchors; filler diffs including one that does not apply on the seeded base):

```python
def test_applicable_keeps_only_diffs_that_apply_on_the_seeded_base(world): ...
def test_pool_from_diffs_deals_disjoint_fillers_and_every_anchor_into_each_batch(world): ...  # refuses below min_per_batch and above ten
def test_calibration_verdict_passes_when_every_rule_holds_in_every_pair(world): ...           # upstream 8, partial 5, mutant 5, stub 1
def test_calibration_verdict_requires_the_partial_ordering(world): ...                        # partial 0 in one pair -> p2_failing 0.25
def test_calibration_verdict_fails_a_similarity_judge_on_the_mutant(world): ...               # mutant 7 or 8 everywhere, P1/P2 hold -> passed False
def test_calibration_verdict_fails_on_anchor_spread_above_the_limit(world): ...               # upstream 8 then 5 for one judge
def test_calibration_over_combines_pools_and_their_cross_pool_spread(world): ...              # two passing pools, upstream 8 and 5 across them -> passed False
def test_calibration_missing_or_excluded_judges_and_controls_fail_the_declared_denominator(world): ...
def test_calibration_over_uses_the_actual_accepted_a_or_a2_baseline(world): ...
def test_judge_scan_reports_test_runs(world): ...                                             # a judge session running pytest -> a hit with that pattern
```

- [x] **Step 2: Run to verify they fail**: `pytest tests/experiments/test_compare_calibration.py -v` — FAIL.
- [x] **Step 3: Implement** as specified, reusing `repos.{build_candidate, main_checkout, runtime_commit, git}`; `pool.py` and `prepare.py` remain within the global ≤500-line / complexity12 bounds; discard stale baseline estimates rather than refactoring unrelated code to meet them.
- [x] **Step 4: Run** the tests — PASS; `pytest --collect-only tests/experiments/test_compare_calibration.py`.
- [x] **Step 5 (operator, offline, free, after Task 3's packages exist): record the applicable fillers.** `python -c` over `pool.applicable(RT, base, task/seed, diffs)` for each task's 20 and 19 candidates; expected rpi ≥ 10, prr 19; write the applicable paths and sha256s into the criterion's `fillers` (Task 5) and the counts into the ledger. If rpi < 8, promote-file selection is revisited in Task 3 before the freeze (M3's stop rule applies).
- [x] **Step 6: Commit** — "feat(compare): calibration pools from applicable recorded diffs; calibration and cross-pool verdicts; judge test-run pattern".

Task 2 verification (2026-10-19, scripted only): the initial 22 tests failed
for absent interfaces; the joined-report integration case also failed before
implementation. New calibration selectors then passed, and an existing V1
summarization regression exposed its historical `calibration` field. A focused
regression failed before restricting the new report to explicit
`purpose: "calibration"`, then passed alongside the new joined-report case.
The coordinator accepted this discriminator: V1 quality rules remain untouched.
Final narrow verification passed **24 tests in 5.13 s**; collection found
**24 tests**. Harness, calibration, reference integrity, generic collection,
structural scoring/qualification and both public scoring workflows passed
**267 tests in 23.52 s**, under tmux with `python -m pytest -q -n 16
--dist=worksteal`. Evidence: `/tmp/measurement-task2-{red,green,v1-red,
final-narrow,collect,final-suite}.log` (brace notation names separate files).
Changed production modules remain below 500 lines and every AST-counted function
is at most complexity 12. Historical criterion/provider/`score.orc` bytes match
plan commit `1710e99b`; no provider call or orchestrator change occurred.
Task2 Step5 completed against the integrated packages: production
`pool.applicable` reproduced RPI11/20 and PRR19/19. The criterion freeze still
needs to bind the exact selected filler membership/hashes.

The independent Task 1 reference-metadata finding was corrected separately in
`b864724f`: missing/empty/truncated reference lists, unknown clone identities,
wrong clone arms and references in the blind lists now refuse before reading
judges. Six regressions failed before the correction; the focused reference and
historical-compatibility selector passed 10 tests afterward; six new tests were
collected. No informational-hit adjudication bypass was introduced.

### Task 3: Family packages: partial and mutant controls, promoted visible check, controller-side first-attempt check

**Files:**
- Modify: `experiments/compare/tasks/{resume-projection-integrity,pure-result-replay}/{seed/dev-check.json, hidden_tests.txt}`; move `hidden/tests/test_runtime_step_lifecycle.py` → `seed/tests/`; create `anchors/<pkg>-partial.diff`, `anchors/<pkg>-mutant.diff`
- Modify: `experiments/orc_structural_search/evaluation.py` (`check_first_attempt`), `experiments/compare/tasks/calibration-ladder.md` (amended rows)
- Test: `tests/experiments/test_orc_structural_search_evaluation.py`

**Selected control-construction amendment (2026-10-19, before judge data):** the original protocol failed: neither task produced a partial in 0.3–0.7; PRR produced no mutant in 0.3–0.8. All 12 original attempts remain in `/home/ollie/sc-evidence/preparation/task3/manifest.json`: each task exhausted three single-module partial attempts plus one double-module attempt; PRR exhausted three mutant attempts, while RPI's first mutant met its original band. No further candidate editing or construction is selected. Hidden fractions remain descriptive, and the spend packet must disclose this post-fraction, pre-judge protocol revision.

Select the first semantically adequate existing candidate in original construction order. A partial must have concrete upstream-pass/partial-fail evidence for one required behavior and upstream-pass/partial-pass evidence for another retained behavior. A mutant must have one behavior-breaking edit affecting an explicit requirement, ≥95% upstream added-line retention, and a functional counterexample passing upstream and failing under the mutant. Import/collection/infrastructure errors do not establish adequacy. Exact requirement, source, patch, test-node and JUnit lineage and independent review are required before freeze; if no existing candidate qualifies, stop the task. P1/P2/P3, spread, the complete denominator, family qualification, gate 3 and budgets are unchanged.

Independent coordinator review approved `/home/ollie/sc-evidence/preparation/task3/semantic-proof.json` (SHA-256 `eae7669a73755809e3e096b44ab8ed82008e364d98645a1716a26aa5714345d5`) in `semantic-review.json`. Existing first partials omit `calls.py` (RPI) and `executor.py` (PRR); first mutants add one early return in `audit_scope` (RPI) and `required_node_ids_for_boundary` (PRR). These partials omit integration components; PRR's runtime absent-API failure does not isolate atomicity. Review establishes semantic adequacy, not predicted judge scores or calibration success. External prepared package hashes are RPI `b2c9cfcae5b8e8b91ac115af518f90c092b7fbd245d253d70dea0bb001879136`, PRR `08696557c2de2d8d2e521b7e9fed8c05f365c058df43bf5813910ad6a4645278`; verify these before integration.

**Interfaces:**
- Produces: `evaluation.FROZEN_PATHS = ("dev-check.json", "tests/")` relative to `seed/`; `evaluation.check_first_attempt(task: Path, patch: Path, runtime: Path, python: str = sys.executable) -> dict`: builds a seeded clone (`repos.build_candidate`), applies `patch` with `git apply --exclude=<each seeded frozen file>`, restores only those actual seeded files (preserving base-owned visible tests), copies trusted `seeds/dev_check.py` beside, runs it with `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` at a temp file and `PYTHONPATH` at the clone, returns `{"passed", "failing", "excerpt", "touched_frozen": [changed frozen paths, including rename/delete endpoints]}`; CLI `python -m experiments.orc_structural_search.evaluation check --task T --patch P --runtime RT`.
- Produces: per package four anchors and a `dev-check.json` whose first pytest test target is `tests/test_runtime_step_lifecycle.py`, after Python/pytest executable and options; `hidden_tests.txt` with 111 and 129 nodes.

- [x] **Step 1: Write the failing tests** in `tests/experiments/test_orc_structural_search_evaluation.py`:

```python
def test_check_first_attempt_restores_frozen_files_before_running(world): ...
    # a patch that rewrites the promoted test to `assert True` and edits dev-check.json's argv: result passed False,
    # touched_frozen lists both paths, the clone's files equal the package's
def test_check_first_attempt_passes_on_the_upstream_anchor(world): ...
```

- [x] **Step 2: Run to verify they fail**; implement `check_first_attempt`; run to PASS (`evaluation.py` stays within the global ≤500-line / complexity12 bounds).
- [x] **Step 3: Promote the check per task.** `git mv hidden/tests/test_runtime_step_lifecycle.py seed/tests/`; delete its node ids from `hidden_tests.txt`; place the file as the first test target in `dev-check.json` `argv`, after Python/pytest executable and options. RPI also requires the verbatim `tests/workflow_bundle_helpers.py` fixture in the seed. Package files are integrated/hash-verified; the root real-package controller matrix confirmed: base `passed: false`; upstream anchor `passed: true`; stub `passed: false`; the remaining hidden set keeps upstream 1.00 and stub ≤ 0.01 (`summarize.hidden_failures`).
- [x] **Step 4: Integrate the existing partial anchors, without new construction.** Verify the independently reviewed proof and selected patch hashes, retained/omitted requirement lineage and exact JUnit node outcomes; copy the approved first RPI/PRR partials from the external prepared packages. Retain all original attempt/fraction records and disclose the superseded selection bands.
- [x] **Step 5: Integrate the existing mutant anchors, without new construction.** Verify selected patch hashes, the single early-return edit, ≥95% retained upstream added lines and the exact upstream-pass/mutant-fail functional counterexample; copy the approved first mutants. Record hidden fractions, failing nodes and visible-check results descriptively. Preserve the independent proof/review identities before any criterion freeze.
- [x] **Step 6: Blind first-attempt figure at zero spend.** Run `check_first_attempt` on every applicable filler (Task 2 Step 5's list); record `failed/applicable` per task in the ledger as the upper-bound estimate (patches made without seeing the test).
- [x] **Step 7: Ladder rows.** Record per package: promoted file and its node ids, new hidden counts, partial and mutant construction, fractions and failing nodes, the note that the two extra anchors enter `anchor_checks`' spread under the frozen `phase2.json` for any future pool of the package, and the package sha256 (`find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum`).
- [x] **Step 8: Verify both evaluation/seed modules and commit.** The original narrow invocation was interrupted; the complete 1124-test suite below covered both modules and passed. Task 3 was committed at `2f495d0a`, with the calibration hidden-run skip at `3655c6f4`.

Task3 integration at `2f495d0a` preserves approved package hashes and exposes the
controller check through the existing evaluation API/CLI. The root's clean-`3655c6f4` controller matrix completed 36 real checks, exit0:
both bases/stubs fail and both upstream controls pass; all applicable historical
fillers fail the promoted check (RPI11/11, PRR19/19). These were actual pytest
exit1 failures, without patch-application or report errors. Production
applicability reproduced11/20 and19/19. Evidence:
`/home/ollie/sc-evidence/preparation/controller-checks/results.json`.
This is an upper-bound estimate on historical patches made before the promoted
check; it is not StepC's live first-attempt gate. Independent Task3 review
approved nine targeted checks. Final broad integration passed; the completed
Task5 evidence below records its scope and frozen identities.
Calibration hidden-run skip `3655c6f4` has a behavioral test that makes any hidden
execution raise and confirms null clone hidden fields with score joins/verdicts
retained. No live calibration or quality claim follows.

### Task 4: Reuse native receipts and readout pricing

**Files:**
- Inspect/reuse: `experiments/orc_structural_search/{metering.py,pricing.py,driver.py,evaluation.py}`; existing receipt/metering/pricing tests.
- Modify only missing calibration/report joins in `experiments/compare/summarize.py` and relevant guides/tests; do not rebuild driver wiring or session discovery.

**Interfaces:**
- Reuse `metering.receipts(records_dir, tree=..., since=..., home=...)` and its existing `receipt_usage`; evaluation/episode rows already record the scoped receipt evidence.
- Reuse `pricing.cost(row, criterion["price_table"])` where `row` carries `provider_calls` and `receipt_usage`. A calibration judge report derives these inputs from the existing judge call directories, recorded tree and start time. Preserve provenance and incomplete markers; add only the reporting join needed by this plan.
- Use the current `price_table` contract (USD/unit/source/date/model rates). Keep both Codex total-consistency cases and Claude categories from the design; never add reasoning output or infer missing usage. No new consumption/pricing/session-discovery function or metering CLI.

- [x] **Step 1: Audit the existing checks** for mixed native models, cache-write inside/separate input, malformed totals, missing receipts/rates and unknown models. Reuse passing evidence; write a small behavioral test only for a new calibration-report join.
- [x] **Step 2: Implement only missing reporting dataflow**, taking judge receipts from recorded call identities and applying the criterion's readout price table. Do not put prices into launch configuration or rewrite raw log rows.
- [x] **Step 3: Verify** the new join with synthetic native receipts and existing receipt/pricing selectors. Show complete mixed-model coverage prices correctly and incomplete or unknown-model coverage stays `unavailable`. Run the relevant scripted compare smoke.
- [x] **Step 4: Record** exact reused/new verification and any unavailable real-receipt coverage in the ledger; update current guides to use these existing APIs.
- [x] **Step 5: Commit only an actual reporting/doc delta** if needed; a verified reuse-only Task 4 closes without an artificial code change.

Task4 closes as reuse-only: the operator joins recorded judge call directories,
trees and `created_at` with `metering.receipts`, then passes physical call count
and `receipt_usage` to `pricing.cost`. External evidence is
`/home/ollie/sc-evidence/preparation/historical-receipt-audit.json` (read-only native
receipts from historical high-model runs) and `capped-model-pricing-check.json`
(synthetic Sonnet/Terra receipts, complete/missing/unknown-model assertions).
These establish the existing API/dataflow and list-price calculation, not native
live receipt coverage for the current capped pair. No new metering API, provider
call or price inference from incomplete evidence was added.

### Task 5: Document calibration scope, freeze implementation, then new criteria

**Files:**
- Modify: driver/harness designs to distinguish generic reference-rubric calibration from admitted structural V1 quality; `experiments/compare/control/review_once.orc` reviewer model and its behavioral contract test; current guides/index/roadmap/module-gate routing.
- Generate after implementation commit `I` is frozen: all criterion artifacts under `E/freeze`. Copy only the exact `calibration-amends-5.json` and `judge-calibration.json` bytes into `experiments/compare/criteria/` for separate git freeze `F`. C's criterion/configuration/capped seed remain external only; their hashes go in `E/freeze/identities.json`.
- Preserve byte-for-byte: historical `calibration.json`, its continuation, structural `phase1.json`/`phase2.json`/`three_arm.json`, provider JSON and `score.orc`.

**Interfaces:**
- The generic comparator supports `score_ref.orc`, four blind control roles and an unscored disclosed reference. P1/P2/P3 and spread remain the predeclared scientific rules. With `purpose: "calibration"`, summarization skips fresh per-node hidden acceptance and leaves `hidden`/`hidden_failed` null; retained exact control-construction fractions remain frozen diagnostics. A/B2 obtain no new filler hidden rates. Other purposes preserve their existing hidden-measure behavior. The structural `qualification.validate` contract stays V1: no new schema, rubric hash acceptance or family-rule bypass is implemented here. A successor V2 validator/receipt is explicitly deferred until a later quality study is selected.
- New `calibration-amends-5.json` references the historical rule by path/hash and records `previous_sha256`, date/reason, unchanged k/thresholds/borderline rules, the historical ladder stop rule as provenance, an explicit current requirement that both selected tasks qualify with no new rungs, and the new implementation runtime commit, reviewer `gpt-5.6-terra`, amended task/package/control hashes and 111/129 remaining hidden node IDs. Retain the original failure text verbatim as `historical_failed_runs`; preserve failure/resume/replacement semantics, but supersede its obsolete “at most four live runs” count. All prospective B direct/review launches, borderline extensions, replacements and reruns share cap14; stop before exceeding it and make no unbudgeted replacement. No historical file is amended in place. Step B requires owner acceptance of this concrete amendment, recorded in the ledger.
- `judge-calibration.json` has `purpose: "calibration"`; task/base/package hashes; declared judges and their bindings; Task-1 `rubric` with upstream reference; four-role `anchors`; control fractions as confirmation only; `calibration: {margin: 4, mutant_margin: 2, error_rate: 0, ordering: "stub < partial < upstream, strict, per (judge, batch)"}`; `anchor_spread_limit: 2`; A/B2 batch counts; exact applicable filler paths/hashes, seed and minima; a path/hash reference to the new family amendment; B2 membership requiring every usable B single-call patch used in qualification plus unused applicable fillers to maximum5/minimum2, deterministic `filler_seed`, no selective omission and no filler reuse from any earlier A/A2 pool, including failed A; gate-3 rule; separate `price_table`; frozen `model_policy`, `failure_policy` and `budget` (A8/cap10, A′8/cap10, B8/cap14, B2 4/cap4, C12/cap12, maximum50). Preserve `written_before_scoring: true`.
- C uses its own `purpose: "measure-free"` criterion with tasks, the frozen implementation identity, external capped seed path/hash and its declared cap12; the existing `ExperimentConfig.criterion_sha256` equals that file's actual SHA. It cannot pool/judge/select quality. Do not submit either calibration criterion or amended family evidence to structural V1 as a substitute for qualification.
- Retain raw evidence for future V2: criterion/source/workflow/binding hashes, package/control/filler identities, pool mapping and clone-ID joins, patches/results, original records/inputs/applied paths, scans/verdicts, calls, native receipt provenance and the accepted A or A2 identity. A passed calibration does not itself select or authorize a successor quality study.

- [x] **Step 1: Complete final behavioral verification** for reference exclusion, the complete calibration denominator, amendment/frozen-file identity and `review_once`'s `gpt-5.6-terra` reviewer. Compare the shared reviewer contract with model masked and pin the deliberate new model separately; no literal prompt tests.
- [x] **Step 2: Complete offline implementation and documentation**, run all required scripted tests, confirm immutable bytes and create an independently reviewed implementation commit `I`. Record `I` before authoring criteria that name it. Detach `RT` at `I`; keep the new criterion artifacts outside that runtime so no commit hash refers to itself.
- [x] **Step 3: Freeze criteria against `I`**, with exact amended package/control/filler hashes, official readout price sources/date, the new family amendment and the separate C criterion/configuration. Verify hashes and complete field/dataflow checks, run the reduced scripted reference-rubric and four-evaluation zero-episode C smoke. Generate `E/freeze` artifacts first, copy the exact amendment and judge-criterion bytes into the repository and commit those two files separately as git freeze `F`. Keep C's criterion/configuration/seed external; hash them in `E/freeze/identities.json`. Record `F` in `E/criterion.sha256` and the ledger after that commit to avoid self-reference. `RT` stays at `I`; every live operator command explicitly uses the `E/freeze` copies.
- [x] **Step 4: Finalize the concrete Step-A packet**, after offline review: criterion hashes, implementation runtime/bindings, control construction and its disclosed pre-judge amendment, exact applicable filler counts, prices, quota reading, 8 calls/cap10 and overall maximum50. Cite the existing `ac58e0ba` approval and verify this packet stays within it; no duplicate approval is requested. This completes preparation; later paid steps keep their own recorded gates.

**Completed offline verification and freeze.** Implementation `I` is
`25ca21e1476f5c060feb04a838e1a6cbf844c63b`; `RT=/home/ollie/sc-runtime` stays
detached there. Its code is identical to `3ce4ea72`, where the complete experiment
and public scoring suite passed **1124 tests in 228.63 s**, exit0
([verification record](/home/ollie/sc-evidence/preparation/final-verification.json)).
The preceding run's two stale anchor-inventory expectations were corrected;
its native quiescence failure passed isolated and in the full repeat. Final-I
reference compile/run/resume and invalid-rating smoke passed **3 in 17.09 s**.
The [final C scripted smoke](/home/ollie/sc-evidence/preparation/taskc-smoke/run-final-I/verification.json)
completed four evaluations, twelve fake calls and all seventeen assertions.
These are offline apparatus checks, not live calibration or gate-3 results.
Earlier pending-verification paragraphs preserve their checkpoint history;
this completion record supersedes that status.

Independent [freeze review](/home/ollie/sc-evidence/preparation/freeze-review.json)
passed. Git freeze `F=cc5464acc0aa7bebe07964f073886bfda09114ba` contains exact
copies of the external [family amendment](../../experiments/compare/criteria/calibration-amends-5.json)
and [judge criterion](../../experiments/compare/criteria/judge-calibration.json).
Their SHA-256 values are respectively
`8cef38ccaf7600b9add5bb51a231e242a00796a424fa92cc5eefb1739b26498e` and
`5991b7ce208c53d6b33654a0d8d644574798a1eaf26826632703c7541ff87796`.
The external [identity manifest](/home/ollie/sc-evidence/freeze/identities.json)
and [hash record](/home/ollie/sc-evidence/criterion.sha256) also bind the external-only
C criterion, configuration and capped seed. Historical criteria, provider files,
`score.orc` and the original seed remain unchanged. Live commands use the explicit
`E/freeze` copies with runtime I. The concrete approved-A packet, quota observation
and unchanged approval for 8 calls, cap 10, plus planning maximum 50 (not an approved allocation) are recorded in the
[operator ledger](/home/ollie/sc-evidence/ledger.md). Step A has since completed eight calls and failed
the combined predicate (RPI spread 4 > 2; PRR passed), with all receipts complete
and USD 7.8836138 list-price equivalent. The [A report](../reports/2026-10-19-orc-structural-search-measurement-calibration.md)
records closure. All later live gates remain open.


### Task 6: Live Step A — judge calibration on known controls (owner gate: 8 calls, cap 10)

**Files:** operator commands only; outputs under `P/<task>/A`, `E`; ledger entries.

- [x] **Step 1: Owner approval recorded.** `ac58e0ba` selects Step A: 2 tasks × 2 batches × 2 judges = 8 calls, cap10, with the other paid stages separately gated. Before launch, attach the verified freeze/runtime/bindings, current Sonnet/Terra pair, control-construction amendment, quota reading and overall maximum50 to the ledger. Approval is already granted; the verified packet and freeze are recorded in Task5 and the external ledger.
- [x] **Step 2: Use the frozen `RT`** at Task 5's implementation commit `I`, with the explicit `E/freeze` criterion copies byte-identical to git freeze `F`; per task: `$PY $H/prepare.py calibrate --task $RT/experiments/compare/tasks/<task> --criterion <criterion> --out $P/<task>/A --judge claude-sonnet-5-5 --judge gpt-5.6-terra=$H/providers/score_codex.json --runtime $RT --batches 2 --per-batch 5 --min-per-batch 4 --filler-seed <seed> --filler <applicable paths>`.
- [x] **Step 3: Score** one judge after another behind the shims (`bash $P/<task>/A/records/score-<judge>.sh`; `verify-pool` after each; `scan --pool --judge --hash SOL`; adjudicate, with `judge ran tests` hits reported; a stopped judge is resumed, never rerun).
- [x] **Step 4: Summarize** each pool; read `results.json["calibration"]`; count, by reading each judge's `reason` fields, ratings stating a blind clone equals the reference (reported). Read each judge's scoped native receipts through the existing receipt/report join and price with `criterion.price_table`; record unavailable coverage explicitly.
- [x] **Step 5: Decide under the frozen rule**: both pools `passed` → the measure is calibrated for the family; proceed to Task 7. Otherwise record the failure and the one revision (Decision 2) in the ledger and go to Task 6b; freeze its revised criterion with a new hash before any A′ launch.

**Result:** completed and failed after exactly 8 calls, within cap 10; both pools
were verified/scanned and all 72 reasons audited. Every P1/P2/P3 pair passed.
RPI failed Terra mutant spread (0 versus 4, limit 2); PRR passed with maximum
spread 1. Complete receipts price at USD 7.8836138 list equivalent. Proceed only
to preparation of the predeclared A′ option; its launch requires separate approval.

### Task 6b: Live Step A′ — one rerun after the predeclared revision (owner gate: 8 calls, cap 10)

**Current launch restriction (2026-10-20):** in response to the concrete A′
request for 8 planned calls, cap 10, the owner said “still no claude, everythign
else is fine”. This authorizes that call budget subject to the continuing
no-Claude restriction; no expiry is assumed. It does not authorize the frozen
Sonnet/Terra F2 packet, which remains incompatible and must not launch. A
prospective Terra-only amendment is under design review; no model assignment,
scientific rule, new criterion or launch packet has been accepted or changed
here. I_A2/F2 and their runtime/criterion bytes remain frozen. The earlier
2026-10-19 restriction remains historical provenance, not an expiry. Other
measurement stages keep their separate owner gates.

Offline preparation at `eb2b0636` adds `score_absolute.orc` for the predeclared reference-free revision; independent review approved it. The first broad run had 1127 passed and one unchanged native-session timing-test failure (229.39 s); both timeout cases passed narrow repeat, then the unchanged full suite passed 1128 in 227.79 s, exit 0. The offline packet is now frozen as recorded below. No A2 launch is selected: a prospective packet keeps both models, controls, fillers and thresholds, with nine blind clones per batch and eight calls, cap 10, under separate owner approval.

**Original offline packet frozen; incompatible with the continuing no-Claude restriction.** Runtime
`RT=/home/ollie/sc-runtime-a2` is detached at
`I_A2=49cd27e6d3c059092e38fcf9836aa4bc50ae8b52`. Git freeze
`F2=f58d70dba4ce2e857e9e5951f76821a20d4efc22` contains exact copies of
[judge-calibration-a2.json](../../experiments/compare/criteria/judge-calibration-a2.json)
(SHA-256 `6b0c4610ff276fa81177107d9fab54652ead0b3d83b4d564b2999d216370fd10`)
and [calibration-amends-5-a2.json](../../experiments/compare/criteria/calibration-amends-5-a2.json)
(SHA-256 `9296362093716b66349d817ccd83b95192fd9450720a726f0e8fe80b56c1fbcb`).
The [identity manifest](/home/ollie/sc-evidence/freeze-a2/identities.json) and
[hash record](/home/ollie/sc-evidence/criterion-a2.sha256) bind every input.
Independent [actual-artifact review](/home/ollie/sc-evidence/preparation/freeze-a2-review.json)
and [field/configuration checks](/home/ollie/sc-evidence/preparation/freeze-a2-field-check.json)
passed. Final-I_A2 public-CLI absolute-scoring checks passed **3 in 15.84 s**
with fake providers only. Code matches the 1128-test verification above.

These bindings apply only to prospective, separately approved launches:

| Stage | Runtime and frozen operator inputs |
| --- | --- |
| A′ (A2 pools) | I_A2; `E/freeze-a2/judge-calibration-a2.json`; `score_absolute.orc`; two batches per task, nine blind clones per batch and no reference |
| B | I_A2; `E/freeze-a2/calibration-amends-5-a2.json`; unchanged `amends_5` scientific qualification rules and both-task scope |
| B2 | I_A2; the same new judge/family criteria; compare only with the accepted A2 readout if A′ passes; retain every usable B qualification patch and the frozen unused-filler rule |
| C | I_A2; `E/freeze-a2/measure-free.json`, `E/freeze-a2/measure-free.config.json`, and `E/freeze-a2/measure-free-seed/implement_check_diagnose_repair.orc` |

A's original I/F, criteria, pools, results and receipts remain historical and
unchanged. The new family copy supersedes its unexecuted predecessor only for
prospective B; it changes runtime identity, not qualification science or
thresholds. Controls, fillers, models, prices, budgets and B2 exclusions are
unchanged. C's seed bytes and scientific configuration are unchanged; only
runtime/path identities and the linked criterion SHA are rebound. Its existing
four-evaluation/twelve-fake-call scripted smoke remains applicable evidence for
those unchanged mechanics; no new C live measurement is implied. A2 pool
preparation exited 0; four dry runs passed. The independent
[pool verification](/home/ollie/sc-evidence/A2/pool-verification.json) confirms
18 clones per task (two batches of nine blind clones, no references), fresh
clone IDs disjoint from A, identical per-batch five filler/four control patch
hashes, and exact runtime/criterion/model/input bindings. `verify-pool` found
all 18 clones unchanged per task. Both pools remain unscored, with no run or
call records and zero provider calls. The packet is ready offline and authorizes
no calls; the dated no-Claude restriction still applies.

- [ ] **Step 1: Complete a compatible launch packet.** The owner has authorized 8 planned calls, cap 10, subject to no Claude. The frozen Sonnet/Terra packet cannot satisfy that restriction. After the prospective amendment is accepted, record its concrete runtime/criterion hashes and the remaining worst-case total against that authority before launching; any changed spend or scope needs owner approval. No compatible amendment or new criterion is accepted by this status update.
- [ ] **Step 2: Use the prospective I_A2/F2 bindings above** and repeat Task 6's pool/scoring/scan/readout mechanics under the new absolute criterion in fresh pools `P/<task>/A2`; do not reuse A's runtime or reference criterion. A′ may reuse the same A fillers; this does not make them unused for B2.
- [ ] **Step 3: Decide**: both pools `passed` → calibrated; otherwise the judge measure is uncalibrated for the family, no further live step runs, and Task 9's failure branch applies.

### Task 7: Live Step B — family re-qualification under `amends_5` (owner gate: 8 calls, cap 14) and B2 (4 calls, cap 4)

**Files:** operator commands only; `W/B/records/{direct_task,review_once}/run-k`; `P/<task>/B2`; ledger entries.

- [ ] **Step 1: Ask the owner** with: `amends_5` text for acceptance; per task 2 `direct_task` + 2 `review_once` = 8, +2 per borderline task, +1 per frozen-rule review rerun, cap 14; B2's 4; the remaining worst-case total. Step B does not launch without `amends_5` accepted in the ledger.
- [ ] **Step 2: Run** `prepare.py run --task <task> --arm direct_task --root $W/B --runtime $RT --set model=gpt-5.6-terra --set effort=high` (k = 2 per task, in tmux), `collect`, `scan --hash SOL`, adjudicate; then `--arm review_once --apply <final.diff>` per patch, `collect` (records `blockers`), scan, adjudicate.
- [ ] **Step 3: Step B first-attempt figure (reported, not the gate)**: `python -m experiments.orc_structural_search.evaluation check --task --patch <final.diff> --runtime $RT` per single-call patch; record pass/fail and `touched_frozen`; measure each patch's hidden fraction (descriptive).
- [ ] **Step 4: Qualification**: the first two samples qualify a task at mean blockers ≥1.5; an initial mean in [1,1.5) adds the third pair (owner notified, within the cap) and qualifies only with final mean ≥1; an initial mean below1 fails. Record every original sample/paired review and any frozen-rule rerun. All B launches/extensions/replacements/reruns count against cap14; check the ledger before each launch and stop without an unbudgeted replacement. The old four-run count is historical only. Two qualified tasks are required before any later live arm; this does not admit the amended family into structural V1.
- [ ] **Step 5 (B2)**: freeze the membership from all usable B single-call patches used in qualification, then deterministically add unused applicable fillers to maximum5/minimum2 under `filler_seed`. Do not selectively omit B qualification patches. Exclude the union of fillers selected in every earlier A/A2 pool, including failed A; A′ may reuse A fillers, but B2 may not. Two or three usable B patches satisfy minimum2 even with zero unused retained fillers; preserve existing duplicate-patch refusals. Per task run `prepare.py calibrate ... --out $P/<task>/B2 --batches 1 --per-batch 5 --min-per-batch 2 --filler <all usable Step B qualification patches> --filler <unused applicable fillers>`; score both judges; summarize; then `summarize.py --calibration-over <accepted-A-or-A2-results.json> $P/<task>/B2/records/results.json --criterion <criterion>`: the B2 pool must pass P1–P3 and the cross-pool spread must stay ≤ 2 for the measure to remain calibrated.

### Task 8: Live Step C — measure-free gate-3 check (owner gate: ≤ 12 calls, cap 12)

**Files:** existing driver CLI only; `W/C`, `E/C`, the separate C criterion/configuration, first-attempt checks and ledger.

- [ ] **Step 1: Ask the owner** with the concrete C criterion/configuration and external seed hashes and runtime: 2 tasks × 2 evaluations of the capped `implement_check_diagnose_repair` copy (≤ 3 calls each), ≤12 calls/cap12 and the remaining overall allocation. This step records execution/check outcomes and cost, not quality comparison.
- [ ] **Step 2: Verify the exact launch inputs.** `C_CONFIG` has the existing ExperimentConfig shape, I1/legacy condition and entry `implement_check_diagnose_repair::run`; its `criterion_sha256` matches the independent `C_CRITERION` with `purpose: "measure-free"`. For this prospective packet, `C_CRITERION=E/freeze-a2/measure-free.json` and `C_CONFIG=E/freeze-a2/measure-free.config.json`; `RT` is I_A2. `C_SEED` names `E/freeze-a2/measure-free-seed/implement_check_diagnose_repair.orc`: the coder stays Sonnet medium, diagnosis is Terra high, and the original source with Sol diagnosis remains unchanged. Verify the copied source/dependency hashes and planned maximum3 against the freeze manifest. `EARLIER_ROOTS` names each previous work/evidence/pool directory, including `W/B`, never ancestor `W`, runtime or the current `W/C` tree. Set inherited `COMPARE_HIDE` to that colon-separated list and supply every same root as a repeated `--holdout` for scans. `--hide` alone is insufficient for these evaluations.
- [ ] **Step 3: Run the actual existing CLI** in tmux after approval (paths/hashes are frozen operator inputs):

```bash
IFS=: read -r -a C_HIDDEN_ROOTS <<< "$EARLIER_ROOTS"
C_SCAN_ROOTS=()
for C_HIDDEN_ROOT in "${C_HIDDEN_ROOTS[@]}"; do
  C_SCAN_ROOTS+=(--holdout "$C_HIDDEN_ROOT")
done
COMPARE_HIDE="$EARLIER_ROOTS" PYTHONPATH="$RT" python -m experiments.orc_structural_search.driver \
  --config "$C_CONFIG" --criterion "$C_CRITERION" \
  --seeds "$C_SEED" \
  --tasks "$RT/experiments/compare/tasks/resume-projection-integrity" "$RT/experiments/compare/tasks/pure-result-replay" \
  --episodes 0 --agent-cmd false --replicates 2 --concurrency 2 \
  --runtime "$RT" --work-root "$W/C" --evidence "$E/C" --eval-timeout-sec 14400 \
  --solution "resume-projection-integrity=$SOL_RPI" --solution "pure-result-replay=$SOL_PRR" \
  --call-cap 12 "${C_SCAN_ROOTS[@]}"
```

The command derives its repeated `--holdout` arguments from exactly the inherited mask roots; the offline smoke checks their equality. Four evaluations, zero mutator episodes, zero judge calls and an enforced cap12 must be demonstrated with scripted providers before this paid launch. No `--policies` selector or quality-launch exemption is added.

- [ ] **Step 4: Measure gate 3.** For each evaluation, apply `evaluation.check_first_attempt` to `calls/1/patch-cand-1.diff`, restoring frozen package files. Also record the first memo `dev-check` report as advisory and realized calls/receipt coverage. Per task at least one of its two controller checks must fail. Step B's corresponding figure remains descriptive beside C.
- [ ] **Step 5: Verdict.** Both tasks in band closes gate 3; otherwise record the measured rates and keep it open. No judged candidate quality, frontier, deployment choice or successor permission follows from this measure-free stage.


### Task 9: Report, gate verdicts and successor-criterion inputs

**Files:**
- Create: `docs/reports/2026-10-<dd>-orc-structural-search-measurement-calibration.md`
- Modify: `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (Calibration row: outcome and hashes), `docs/plans/2026-10-19-orc-structural-search-module-rewrite-plan.md` (gates 2–4 status), `experiments/compare/tasks/calibration-ladder.md`, `docs/index.md`

- [ ] **Step 1: Write the report** from each pool's `results.json` (`calibration`, `calibration_over`, `anchors`, `agreement`, recognition count, judge test-run hits), the harness `collect` records (blockers, Step B check figures, hidden fractions), the Step C log rows and first-attempt checks, and the existing receipt/pricing report output (coverage per provider and criterion-priced cost of judges, single calls and Step C), with every spent call against the caps, every refusal listed, and file hashes of the evidence. State explicitly that "a different correct implementation scores like upstream" is untested (no such control exists).
- [ ] **Step 2: Gate verdicts**, one line each: gate 2 (calibrated measure: criterion hash, P1/P2/P3 and spread figures over the accepted A or A2 and B2), gate 3 (Step C band per task; Step B figure beside it), gate 4 (metering coverage per provider; price table frozen), and what a successor criterion inherits (`rubric`, four-role `anchors`, `calibration`, `price_table`, amended package/control hashes and the separate `amends_5` file).
- [ ] **Step 3: Failure branch** (Step A′ failed, or a task did not qualify, or gate 3 is open): the report states which gate is open, lists the owner's options verbatim as options, not recommendations: (i) hidden acceptance primary, an explicit reversal of the 2026-10-15 evaluation policy; (ii) a harder promoted check as a new owner decision; (iii) stop live structural search on family (a) and reconsider family (b). No live arm is selected.
- [ ] **Step 4: Run** `pytest -q -n 16 --dist=worksteal tests/experiments/ tests/test_workflow_evaluated_compare_score.py` — PASS; **commit** — "docs(search): measurement calibration report and gate verdicts".

## Decision Ledger

| Decision | Consequence |
| --- | --- |
| Owner selects offline preparation and approves Step A | `ac58e0ba` approves A (8 calls, cap 10); verified I/F and the concrete packet are recorded, and A completed eight calls but failed the combined calibration (RPI failed; PRR passed). A′, B, B2 and C retain separate approvals |
| Reuse the merged receipt/pricing apparatus | No second metering API, price-table alias or session discovery path |
| Keep generic calibration separate from structural V1 quality | Preserve `qualification.validate` and `mapping.qualification`; defer V2 until a later successor study is selected |
| Freeze implementation before criteria that name it | Runtime commit `I` and criterion freeze `F` are distinct; preserve all historical bytes |
| Missing observations fail the full predeclared denominator | No excluded judge, missing control or incomplete rating can silently improve calibration |
| B2 compares the actual accepted A or A2 | Never substitute the failed original A after an approved rerun |
| Explicit measure-free C and separate B/C roots | Existing driver flags, matching criterion hash, inherited masks plus scan roots; no quality bypass or ancestor mask |
| Owner handoff: preserve measurement interfaces and splits | Keep measurement I/F and historical bytes frozen; preserve `pool.rubric`/`write_pool`, `scoring.fillers_per_batch`/`read_pool` clone joins and qualification proof, `metering.receipts`/`pricing.cost`, V1 receipts and capped copies of historical seeds. Rung 1 stays sealed and never reaches a pool or mutator; rung 3's validation third sample needs its own owner approval. No C1/store/reservoir/V2 implementation or extra spend is selected by this handoff |
| C1 rubric coordination — resolved | Resolved by cumulative design `bfb4323c` and pilot plan `1c8c45e6`: C1 Task 6 admits the accepted measure's rubric, either A's reference rubric or the owner-approved A′ revision without a reference |
| C1 gate routing coordination — resolved | Resolved by cumulative design `bfb4323c` and pilot plan revisions `53053291` / `1c8c45e6`: gate 1 requires the accepted measure (A or owner-approved A′), and C1 Task 8 references the design's single authoritative ten-item gate list |
| Round-3 coordination preserves this measurement scope | The earlier owner handoff mentioned rung 3's third sample; cumulative-design round 3 now requires fresh extra-package qualification under `amends_6`, with no historical sample carryover. The C1 plan still reflects round 2 at this checkpoint. This is coordination chronology only: extra packages, `amends_6`, C1/store/reservoir/V2 changes and spend stay outside this `amends_5` measurement revision |
| No further Claude experiments today | Owner directive after A completed: no Claude experiment launches on 2026-10-19, America/Los_Angeles; A′ remains offline and blocked today, with no unilateral model substitution |
| Preserve scientific rules and allocation | P1/P2/P3/spread, reviewed controls, gate-3 band and planned 32/maximum 50 unchanged; only A (8 calls, cap 10) is approved |
| Calibration skips fresh hidden acceptance | A/B2 use retained construction diagnostics; no new filler hidden rates, and other purposes keep their existing hidden behavior |
| Current family scope is exactly the selected two tasks | Preserve the old first-qualifying-rung rule as history; require both current tasks to qualify and select no additional rungs |
| B failure history does not impose the old four-run count | Retain `historical_failed_runs`; count all B launches/extensions/replacements/reruns against cap14 and stop before any excess |
| B2 membership is frozen by provenance | Include all usable B qualification patches, deterministic unused fillers, maximum5/minimum2; no selective omission or reuse of fillers from any earlier A/A2 pool, including failed A; A′ itself may reuse A fillers |

Current budget after A: 8 realized calls; remaining separately gated caps are
10 + 14 + 4 + 12 = 40, so realized plus remaining worst case is 48. The original
planning maximum 50 is not an allocation, and A's unused two-call reserve is
not transferred. Remaining planned calls are 32, or 40 including A and A′.

### Owner Steering — 2026-10-20

| Decision | Consequence |
| --- | --- |
| Conditional A′ budget authorization with continuing no-Claude restriction | The owner answered the concrete 8-planned-call/cap-10 request with “still no claude, everythign else is fine”. Record the budget authority subject to no Claude, without assuming an expiry. This does not approve launching the frozen Sonnet/Terra F2 packet or silently replacing its judges |
| Prospective Terra-only amendment remains under design review | No new model assignment, scientific rule or criterion is selected by this status edit. Preserve I_A2/F2, historical A, all frozen criteria and runtime bytes. A compatible accepted amendment and matching packet must precede any launch; no call is launched here |
| Offline C1 Tasks 1–7 selected on the reused branch | The owner selected offline implementation in the [C1 plan](2026-10-19-orc-structural-search-cumulative-pilot-plan.md), with Task 1 `6c0082e1` still under independent review. This does not select a paid campaign or waive B/B2/C and extra-package qualification gates |
