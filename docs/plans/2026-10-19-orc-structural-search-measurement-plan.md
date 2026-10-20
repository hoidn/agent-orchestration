# ORC Structural Search Measurement Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** offline preparation selected by the owner's instruction to execute the experiments (2026-10-19); Tasks 1–5 remain unimplemented. This revision prepares a concrete, reviewable calibration experiment. Each paid step keeps its own owner budget decision and stated call estimate; no paid approval is inferred from the preparation instruction.

> **Revision 2026-10-19** (after the independent review, coordinator rulings C1 and I1–I10 applied): a fourth blind control per task, the `mutant` (upstream with one behaviour-breaking edit), and rule P3 `total(upstream) − total(mutant) ≥ 2`, so a judge that scores similarity to the disclosed reference fails calibration; fillers are only patches that pass `git apply --check` on the amended seeded base, drawn from the retained Phase 1 pools and the three-arm final patches, with exact counts and a minimum; the authoritative gate-3 check is controller-side and restores the package's `dev-check.json` and promoted test before running (`evaluation.check_first_attempt`); Step C (the check-gated seed's own coder) is required and is the gate-3 measurement, Step B's figure beside it; a new `calibration-amends-5.json` references the unchanged historical criterion and records `amends_5` (frozen implementation commit, reviewer `gpt-6.1-sol`, amended package hashes) before Step B; B2 has its own per-pool verdict plus `summarize.calibration_over`; the failure-policy rerun is its own owner-gated step (A′) and the worst-case total is stated (50 calls); the driver design and harness D6 are amended offline before any spend; `summarize` skips `reference` clones and reads a mapping without `rubric` as the historical rubric; `score_ref.orc` runs end to end with scripted providers before the criterion freezes; no `calibrate.py` (shared `pool.write_pool`, `pool.pool_from_diffs`); citation, count, metering-mapping, measurement-order, batch-size, judge-scan and ledger minors applied.

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
- Work in the isolated `feat/structural-search-measurement` checkout from merged `main` at `62e3776f`; no file under `orchestrator/` changes. Every touched module stays ≤ 500 lines and every function ≤ cyclomatic complexity 12; no test asserts prompt text. Reuse the current responsibilities instead of stale line counts. Preserve historical `calibration.json`, its continuation, the three structural criteria, provider JSON and `score.orc` byte-for-byte; create a separate amendment and calibration criteria.
- Family: `experiments/compare/tasks/resume-projection-integrity` (rpi, base `1cd607673c89170dc96c74a0b5eb4aef204da82d`) and `pure-result-replay` (prr, base `f80e551a6cdeca6a2913ce640326495be1ae1cc5`); rung 1 `cf1-generic-unions` is reserved for a later sealed split and is not amended. Solution hashes are operator-supplied (`--hash`/`--solution`), never written into a package or criterion.
- Rubric v2 (`score_ref.orc`): criteria `completeness`, `correctness`, `scope`, `layering`, each `S0|S1|S2`, total 0–8, averaged over judges; one disclosed reference clone per batch (the upstream anchor applied; arm `reference`, never rated, never scored); blind anchors in every batch, four roles: `<pkg>-upstream`, `<pkg>-stub`, `<pkg>-partial`, `<pkg>-mutant`. A batch holds at most 10 repositories including the reference (D4): reference + 4 anchors + ≤ 5 fillers.
- Calibration predicate, frozen in `experiments/compare/criteria/judge-calibration.json` before any judge call, per (judge, batch) with failing fraction ≤ `error_rate = 0` for each rule: P1 (the design's rule) `total(upstream) − total(stub) ≥ margin = 4`; P2 strict ordering `stub < partial < upstream`; P3 `total(upstream) − total(mutant) ≥ mutant_margin = 2`; cross-batch spread of each blind anchor per judge ≤ `anchor_spread_limit = 2`. The denominator is every predeclared judge × batch pair; an excluded or absent judge, missing control or incomplete rating fails its pair, never shrinks the denominator. A pool passes when P1, P2, P3 and the spread hold; calibration needs both tasks' accepted Step A pools (A′ if that rerun passed instead). B2 must pass and `calibration_over` compares it with that actual accepted A or A2 baseline, keeping every anchor's spread within 2.
- Judges: `claude-opus-5-5` (`experiments/compare/score.providers.json`) and `gpt-6.1-sol` (`experiments/compare/providers/score_codex.json`), effort `high`, `:timeout-sec 3600` per batch; Step A: 2 batches per task, 5 fillers each when available, minimum 4 per batch (8 per task; `pool_from_diffs` refuses below), fillers disjoint across a task's batches, dealt by `random.Random(filler_seed)`; B2: 1 batch per task, fillers = the Step B single-call patches plus unused applicable fillers up to 5, minimum 2.
- Fillers: only patches that pass `git apply --check` on the amended seeded base (Task 2 records the applicable list and its sha256s in the criterion). Candidates verified read-only on 2026-10-19: rpi 20 (14 Phase 1 non-anchor + 6 three-arm `collected/final.diff`), of which 11 touch `tests/test_runtime_step_lifecycle.py` and at least 10 apply (the reviewer's scratch check: 8 of the 14 Phase 1 patches; 2 three-arm patches touch neither frozen path); prr 19 (13 + 6), none touching a frozen path, all applicable. Exact applicable counts are recorded by Task 2 Step 5 before the freeze.
- Family rule: new `calibration-amends-5.json` references unchanged `calibration.json` (`amends_4`) and declares `amends_5` (Task 5): k = 2 `direct_task` single calls (`gpt-6.1-sol`, `high`, 14,400 s), one `review_once` each with reviewer `gpt-6.1-sol` (owner directive 2026-10-19), the first two samples qualify at mean blockers ≥1.5, an initial mean in [1,1.5) requires a third pair and final mean ≥1, and an initial mean below1 fails; valid runtime = this plan's frozen `RT` commit; amended package sha256s recorded. Step B does not run without `amends_5`.
- Gate 3 (predeclared): measured in Step C on the check-gated seed `implement_check_diagnose_repair` (coder `claude-sonnet-5-5` medium 5,400 s; reviewer `gpt-6-sol` as frozen in the seed), 2 evaluations per task; band: at least one of the two evaluations per task has a failing first `dev-check` under the controller-side check (`evaluation.check_first_attempt` on the first coder call's patch, package files restored). Step B's first-attempt figure (the `gpt-6.1-sol` single calls) is reported beside it and decides nothing. The agent-side `dev_check.py` in the clone is advisory.
- Metering: retain raw `receipt_usage` and existing per-call/model provenance from `metering.receipts`; price at report time through `pricing.cost(row, criterion["price_table"])`. `price_table` has `currency: "USD"`, positive `tokens_per_unit`, `source`, ISO `date`, and `models` with `input`, `output`, `cache_read`, `cache_write` rates. Copy rates from official provider pricing on the freeze date; select none here. Existing receipt mapping charges Claude's four categories directly; Codex uses the last cumulative total to distinguish cache-write inside input from separate cache-write and never adds reasoning output. Missing or inconsistent receipt/category/model/rate evidence remains `unavailable`. Do not add `metering.consumption`, `metering.price`, a second session discoverer or a pricing `models` alias.
- Budgets (provider calls, charged as in Phase 1; immediate zero-work refusals listed, not silently subtracted): Step A judge calibration 8, cap 10; Step A′ (rerun after the one predeclared revision, only if A fails) 8, cap 10, its own approval with the revised hash; Step B family re-qualification 8 (+2 per borderline task, +1 per frozen-rule review rerun), cap 14; Step B2 replicate 4, cap 4; Step C gate-3 measurement ≤ 12 (2 tasks × 2 evaluations × ≤ 3 calls), cap 12. Planned without A′: 32; worst-case total across all steps: 50. Order A → (A′) → B → B2 → C; A first because it is the cheapest step that can falsify the evaluator. Codex quota floor as in Phase 1 (no new launch below the owner-stated window floor unless the credit policy covers it).
- Live roots: runtime `RT=/home/ollie/sc-runtime` is detached at the frozen implementation commit; criteria freeze afterward outside that runtime. Work root `W=/home/ollie/sc-work` uses separate `W/B` and `W/C`; pools `P=/home/ollie/sc-pools/<task>/<A|A2|B2>`; evidence/ledger `E=/home/ollie/sc-evidence` holds `ledger.md`, criterion/source hashes, `solutions.txt` and `E/C` driver evidence. Roots stay outside the main prefix and `/tmp`, `/dev/shm`, `/var/tmp`. Existing `ss-*`, `ss3-*`, `calib-*` evidence is read-only. C masks each earlier evidence/work/pool root with inherited `COMPARE_HIDE` and repeats it as `--holdout` for scanning; `--hide` alone masks episodes only. Never mask shared ancestor `W`, runtime or the current C tree.
- Verification: narrow selectors first, `pytest --collect-only` on new or parametrised test modules, then `pytest -q -n 16 --dist=worksteal tests/experiments/ tests/test_workflow_evaluated_compare_score.py`; commits with pathspecs, one per task, messages in the repository's existing style.

## Review Focus

1. A judge that scores similarity to the disclosed reference passes P1 and P2 by construction (upstream is byte-identical to the reference, partial is the reference minus a module, stub is nothing); only P3 catches it, because the mutant keeps ≥ 95% of the reference's lines and must still lose ≥ 2 points (Task 2 `test_calibration_verdict_fails_a_similarity_judge_on_the_mutant`). "A different correct implementation scores like upstream" stays untested: no retained patch reaches hidden 1.00 (maximum 0.843), so no such control exists; Task 9 reports this.
2. An agent that edits the promoted visible test, `dev-check.json` or its `argv` so its own check passes: the controller-side check restores those files from the package before running and reports which frozen paths the patch touched (Task 3 `test_check_first_attempt_restores_frozen_files_before_running`).
3. A pool whose `rubric` differs from the criterion's is refused; a historical mapping without `rubric` summarises under the `score.orc` rubric without refusal; a reference clone never enters run rows, anchor figures, ratings or hidden acceptance (Task 1 `test_summarize_refuses_a_criterion_whose_rubric_differs_from_the_pools`, `test_summarize_reads_a_mapping_without_rubric_as_the_historical_rubric`, `test_summarize_skips_reference_clones_everywhere`).
4. A metered run with one unmatched shim call, a Codex rollout without a model name, or a nonzero `cache_write_input_tokens` inside `input_tokens` must price `unavailable` or by the design's clause, never 0 or double-charged (Task 4 `test_price_is_unavailable_with_an_unmatched_call_or_unknown_model`, `test_codex_cache_write_inside_input_is_charged_once`).
5. Four anchor files per package change every future pool's arithmetic: batches must carry every package anchor and never exceed 10 repositories including the reference (Task 1 `test_pool_batches_carry_every_package_anchor_and_stay_within_ten`); the extra anchors also enter `anchor_checks`' spread under the frozen `phase2.json` (ladder note, Task 3).

## Decisions

1. **Evaluator: intent-anchored absolute rubric with a disclosed reference (recommended).** Alternatives weighed: (a) pairwise comparison against the upstream fix: removes batch effects but yields no scale for a frontier and cannot separate a stub from a partial without magnitude; rejected. (b) Rubric change only (add `completeness`, blind batches, no reference): cheaper, but the judge still rates within the batch, so drift remains; kept as the one predeclared revision (Step A′) if (c) fails. (c) Absolute rubric plus a disclosed reference clone per batch: the reference fixes the top of the scale in every batch; the instruction is to rate against the intent and the reference, not the other repositories; a repository implementing none of the intended behaviours scores S0 on every criterion (the Phase 1 defect: the stub earned `scope`/`layering` points for doing nothing); a different implementation providing the behaviours scores S2 on `completeness`. The risk that a judge scores similarity to the reference is controlled by the mutant and P3, not by prompt wording. Hidden acceptance as primary is offered only in Task 9's failure branch.
2. **Calibration experiment.** Controls per task, all blind, authored offline at zero spend: upstream; stub (existing); partial (the upstream diff with one coherent source module's hunks excluded, hidden fraction over the remaining set 0.3–0.7); mutant (the upstream diff with one behaviour-breaking edit, an inverted guard or early return, in a module implementing a behaviour `intent.txt` names, keeping ≥ 95% of the upstream's diff lines, failing a listed subset of the remaining hidden nodes with fraction 0.3–0.8). Margins: P1 = 4 because a stub can earn at most 4 points on `scope` and `layering` under the S0-everywhere rule and an upstream copy earns 8; P3 = 2 because a behaviour-reading judge must drop the mutant's `correctness` to S0 or S1 and its `completeness` to at most S1 for the broken behaviour, one full step on two criteria, while a similarity judge gives a 95%-identical tree 7 or 8; error rate 0 over 8 (judge, batch) pairs per rule. Control order rests on construction; hidden fractions confirm it and decide nothing (ledger entry, owner acknowledgement in the Task 6 ask). Fillers are retained patches, so judges see realistic batches at zero spend. Failure policy: one revision only, alternative (b) or one judge swap, a new criterion hash and Step A′ under its own approval; a second failure declares the judge measure uncalibrated for the family (Task 9 failure branch).
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
- `control/review_once.orc` binds the reviewer `:model "gpt-6-sol"`; `test_compare_review_once.py::test_review_once_compiles_the_reviewer_of_reviewed_change` asserts the reviewer call equals `reviewed_change`'s, so the `gpt-6.1-sol` ruling needs the model literal changed in `review_once.orc` and that contract test to mask `model`.
- `prepare.run --arm direct_task --set model=gpt-6.1-sol --set effort=high` and `--arm review_once --apply <final.diff>` are the frozen rule's arms; `collect` records `blockers`; the harness refuses roots under the main prefix or `/tmp`. The current harness differs from the historical frozen runtime, so the new amendment must declare the new implementation commit; rewriting `amends_4` in place would destroy its evidence identity.

---

### Task 1: Rubric v2 workflow, criterion-selected rubric, shared pool writer, end-to-end check

**Files:**
- Create: `experiments/compare/score_ref.orc` (module `score_ref`, export `score`; `Rating` with `clone`, `completeness`, `correctness`, `scope`, `layering`, `reason`; `Batch` with `clones List[String]`, `reference String`; `rate-batch` fills `intent`, `reference`, `clones`; `providers.judge` as in `score.orc`)
- Modify: `experiments/compare/pool.py` (`DEFAULT_RUBRIC`, `rubric()`, `write_pool()`, reference clone per batch in `build_batches`, `write_score_inputs`), `experiments/compare/summarize.py` (criteria from the mapping, reference skipping, rubric refusal), `experiments/orc_structural_search/scoring.py` (`build_pool` calls `write_pool`; anchor count from the package; `split_batches` size = `10 − anchors − (1 if reference)`), `experiments/orc_structural_search/adaptive.py` (task-specific capacity in existing `planned_judged` budget estimates through `scoring.fillers_per_batch(task, rubric)`; fresh adaptive launch remains unsupported), `experiments/compare/README.md` (score section)
- Modify: `tests/test_workflow_evaluated_compare_score.py` (parametrise `Program` over both workflows)
- Test: `tests/experiments/test_compare_pool_summarize.py`, `tests/experiments/test_orc_structural_search_scoring.py`

**Interfaces:**
- Produces: `pool.DEFAULT_RUBRIC = {"workflow": "score.orc", "entry": "score::score", "criteria": ["root_cause","scope","generality","layering"], "reference": None}`; `pool.rubric(criterion: Path) -> dict` = `criterion.get("rubric", DEFAULT_RUBRIC)`.
- Produces: `pool.write_pool(task: Path, criterion: Path, out: Path, judges: Sequence[str], ref: Mapping, rows: dict, batches: list, *, qualification: Mapping | None = None) -> dict` (guard, sandbox visibility, mkdir, `build_batches`, mapping with `rubric`, `references`, `runs`, `clones`, `batches`, `write_score_inputs`, chmod; returns the mapping). `pool.pool` and `scoring.build_pool` call it. The structural caller keeps `qualification.validate` before this call and passes its verified proof through to `mapping.qualification`; generic callers do not gain structural quality authority.
- Produces: mapping gains `rubric` and, with a reference, `references: [clone id per batch]`; reference clone entries carry `arm: "reference"`, `labels: ["reference"]`; `score-inputs-<judge>.json` batches carry `"reference": <path>` and exclude it from `clones`; `score-<judge>.sh` names `rubric["workflow"]`/`rubric["entry"]`.
- Produces: `summarize.criteria_of(mapping) -> tuple[str, ...]` (`mapping.get("rubric", DEFAULT_RUBRIC)["criteria"]`); `summarize()` refuses when `pool.rubric(criterion) != mapping.get("rubric", DEFAULT_RUBRIC)`; clones with `arm == "reference"` are excluded from `clone_scores`, ratings, `run_rows`, anchor figures and hidden acceptance and reported under `clones` with `score: null`.
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
- [ ] **Step 5 (operator, offline, free, after Task 3's packages exist): record the applicable fillers.** `python -c` over `pool.applicable(RT, base, task/seed, diffs)` for each task's 20 and 19 candidates; expected rpi ≥ 10, prr 19; write the applicable paths and sha256s into the criterion's `fillers` (Task 5) and the counts into the ledger. If rpi < 8, promote-file selection is revisited in Task 3 before the freeze (M3's stop rule applies).
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
Task 2 Step 5 remains open until the real amended Task 3 packages exist.

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

**Interfaces:**
- Produces: `evaluation.FROZEN_PATHS = ("dev-check.json", "tests/")` relative to `seed/`; `evaluation.check_first_attempt(task: Path, patch: Path, runtime: Path, python: str = sys.executable) -> dict`: builds a seeded clone (`repos.build_candidate`), applies `patch` with `git apply --exclude=<each seeded frozen path>`, copies `seeds/dev_check.py` beside, runs `python dev_check.py` with `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` at a temp file and `PYTHONPATH` at the clone, returns `{"passed", "failing", "excerpt", "touched_frozen": [paths the patch changed among the frozen set]}`; CLI `python -m experiments.orc_structural_search.evaluation check --task T --patch P --runtime RT`.
- Produces: per package four anchors and a `dev-check.json` whose `argv` starts with `tests/test_runtime_step_lifecycle.py`; `hidden_tests.txt` with 111 and 129 nodes.

- [ ] **Step 1: Write the failing tests** in `tests/experiments/test_orc_structural_search_evaluation.py`:

```python
def test_check_first_attempt_restores_frozen_files_before_running(world): ...
    # a patch that rewrites the promoted test to `assert True` and edits dev-check.json's argv: result passed False,
    # touched_frozen lists both paths, the clone's files equal the package's
def test_check_first_attempt_passes_on_the_upstream_anchor(world): ...
```

- [ ] **Step 2: Run to verify they fail**; implement `check_first_attempt`; run to PASS (`evaluation.py` stays within the global ≤500-line / complexity12 bounds).
- [ ] **Step 3: Promote the check per task.** `git mv hidden/tests/test_runtime_step_lifecycle.py seed/tests/`; delete its node ids from `hidden_tests.txt`; prepend the file to `dev-check.json` `argv`. Verify with `check_first_attempt` (an empty patch for the base) and record in the ledger: base `passed: false`; upstream anchor `passed: true`; stub `passed: false`; the remaining hidden set keeps upstream 1.00 and stub ≤ 0.01 (`summarize.hidden_failures`).
- [ ] **Step 4: Author the partial anchor per task (offline, free), after Step 3.** In a scratch seeded clone: `git apply --exclude='orchestrator/<module>' anchors/<pkg>-upstream.diff`, then `repos.patch_of(clone, seeded_base) > anchors/<pkg>-partial.diff`; measure the hidden fraction over the remaining 111/129 nodes; accept 0.3–0.7; at most three candidate modules, each attempt recorded in the ladder; if none fits, exclude two modules together (one more attempt) and record it. Record the module(s), the fraction and the check result.
- [ ] **Step 5: Author the mutant anchor per task (offline, free).** Apply the upstream diff, make one behaviour-breaking edit (an inverted guard or an early return) in a module implementing a behaviour `intent.txt` names, regenerate the diff; verify: ≥ 95% of the upstream diff's added lines retained (`diff` line count), hidden fraction 0.3–0.8 over the remaining set, the failing node ids listed in the ladder, the check result recorded; at most three attempts, each recorded.
- [ ] **Step 6: Blind first-attempt figure at zero spend.** Run `check_first_attempt` on every applicable filler (Task 2 Step 5's list); record `failed/applicable` per task in the ledger as the upper-bound estimate (patches made without seeing the test).
- [ ] **Step 7: Ladder rows.** Record per package: promoted file and its node ids, new hidden counts, partial and mutant construction, fractions and failing nodes, the note that the two extra anchors enter `anchor_checks`' spread under the frozen `phase2.json` for any future pool of the package, and the package sha256 (`find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum`).
- [ ] **Step 8: Run** `pytest tests/experiments/test_orc_structural_search_evaluation.py tests/experiments/test_orc_structural_search_seeds.py -v` — PASS. **Commit** — "feat(tasks): partial and mutant controls, promoted agent-visible check and a controller-side first-attempt check for rungs 2 and 4".

### Task 4: Reuse native receipts and readout pricing

**Files:**
- Inspect/reuse: `experiments/orc_structural_search/{metering.py,pricing.py,driver.py,evaluation.py}`; existing receipt/metering/pricing tests.
- Modify only missing calibration/report joins in `experiments/compare/summarize.py` and relevant guides/tests; do not rebuild driver wiring or session discovery.

**Interfaces:**
- Reuse `metering.receipts(records_dir, tree=..., since=..., home=...)` and its existing `receipt_usage`; evaluation/episode rows already record the scoped receipt evidence.
- Reuse `pricing.cost(row, criterion["price_table"])` where `row` carries `provider_calls` and `receipt_usage`. A calibration judge report derives these inputs from the existing judge call directories, recorded tree and start time. Preserve provenance and incomplete markers; add only the reporting join needed by this plan.
- Use the current `price_table` contract (USD/unit/source/date/model rates). Keep both Codex total-consistency cases and Claude categories from the design; never add reasoning output or infer missing usage. No new consumption/pricing/session-discovery function or metering CLI.

- [ ] **Step 1: Audit the existing checks** for mixed native models, cache-write inside/separate input, malformed totals, missing receipts/rates and unknown models. Reuse passing evidence; write a small behavioral test only for a new calibration-report join.
- [ ] **Step 2: Implement only missing reporting dataflow**, taking judge receipts from recorded call identities and applying the criterion's readout price table. Do not put prices into launch configuration or rewrite raw log rows.
- [ ] **Step 3: Verify** the new join with synthetic native receipts and existing receipt/pricing selectors. Show complete mixed-model coverage prices correctly and incomplete or unknown-model coverage stays `unavailable`. Run the relevant scripted compare smoke.
- [ ] **Step 4: Record** exact reused/new verification and any unavailable real-receipt coverage in the ledger; update current guides to use these existing APIs.
- [ ] **Step 5: Commit only an actual reporting/doc delta** if needed; a verified reuse-only Task 4 closes without an artificial code change.


### Task 5: Document calibration scope, freeze implementation, then new criteria

**Files:**
- Modify: driver/harness designs to distinguish generic reference-rubric calibration from admitted structural V1 quality; `experiments/compare/control/review_once.orc` reviewer model and its behavioral contract test; current guides/index/roadmap/module-gate routing.
- Create after the implementation commit is frozen: `experiments/compare/criteria/calibration-amends-5.json`, `experiments/compare/criteria/judge-calibration.json`, and a separate Step-C measure-free criterion/configuration in the experiment evidence root.
- Preserve byte-for-byte: historical `calibration.json`, its continuation, structural `phase1.json`/`phase2.json`/`three_arm.json`, provider JSON and `score.orc`.

**Interfaces:**
- The generic comparator supports `score_ref.orc`, four blind control roles and an unscored disclosed reference. P1/P2/P3 and spread remain the predeclared scientific rules. The structural `qualification.validate` contract stays V1: no new schema, rubric hash acceptance or family-rule bypass is implemented here. A successor V2 validator/receipt is explicitly deferred until a later quality study is selected.
- New `calibration-amends-5.json` references the historical rule by path/hash and records `previous_sha256`, date/reason, unchanged k/thresholds/borderline/stop rules, the new implementation runtime commit, reviewer `gpt-6.1-sol`, amended task/package/control hashes and 111/129 remaining hidden node IDs. No historical file is amended in place. Step B requires owner acceptance of this concrete amendment, recorded in the ledger.
- `judge-calibration.json` has `purpose: "calibration"`; task/base/package hashes; declared judges and their bindings; Task-1 `rubric` with upstream reference; four-role `anchors`; control fractions as confirmation only; `calibration: {margin: 4, mutant_margin: 2, error_rate: 0, ordering: "stub < partial < upstream, strict, per (judge, batch)"}`; `anchor_spread_limit: 2`; A/B2 batch counts; exact applicable filler paths/hashes, seed and minima; a path/hash reference to the new family amendment; gate-3 rule; separate `price_table`; frozen `model_policy`, `failure_policy` and `budget` (A8/cap10, A′8/cap10, B8/cap14, B2 4/cap4, C12/cap12, maximum50). Preserve `written_before_scoring: true`.
- C uses its own `purpose: "measure-free"` criterion with tasks, the frozen implementation identity and its declared cap12; the existing `ExperimentConfig.criterion_sha256` equals that file's actual SHA. It cannot pool/judge/select quality. Do not submit either calibration criterion or amended family evidence to structural V1 as a substitute for qualification.
- Retain raw evidence for future V2: criterion/source/workflow/binding hashes, package/control/filler identities, pool mapping and clone-ID joins, patches/results, original records/inputs/applied paths, scans/verdicts, calls, native receipt provenance and the accepted A or A2 identity. A passed calibration does not itself select or authorize a successor quality study.

- [ ] **Step 1: Verify behavioral contracts** for reference exclusion, the complete calibration denominator, amendment/frozen-file identity and `review_once`'s `gpt-6.1-sol` reviewer. Compare the shared reviewer contract with model masked and pin the deliberate new model separately; no literal prompt tests.
- [ ] **Step 2: Complete offline implementation and documentation**, run all required scripted tests, confirm immutable bytes and create an independently reviewed implementation commit `I`. Record `I` before authoring criteria that name it. Detach `RT` at `I`; keep the new criterion artifacts outside that runtime so no commit hash refers to itself.
- [ ] **Step 3: Freeze criteria against `I`**, with exact amended package/control/filler hashes, official readout price sources/date, the new family amendment and the separate C criterion/configuration. Verify hashes and complete field/dataflow checks, run the reduced scripted reference-rubric and four-evaluation zero-episode C smoke. Commit the new criterion artifacts separately as freeze `F`, retain both `I` and `F` in `E/criterion.sha256` and the ledger. `RT` remains at `I`; operator commands use criterion files from `F`/the evidence root explicitly.
- [ ] **Step 4: Present the concrete Step-A approval packet**, after offline review: criterion hashes, implementation runtime/bindings, control construction, exact applicable filler counts, prices, quota reading, 8 calls/cap10 and overall maximum50. This completes preparation; no paid step launches without its recorded approval.


### Task 6: Live Step A — judge calibration on known controls (owner gate: 8 calls, cap 10)

**Files:** operator commands only; outputs under `P/<task>/A`, `E`; ledger entries.

- [ ] **Step 1: Ask the owner**, stating: 2 tasks × 2 batches × 2 judges = 8 judge calls, cap 10 (2 for one resumed judge run); the worst-case total across all steps, 50; the Codex window reading; the design amendments of Task 5 for selection; and the acknowledgement that the controls' order rests on construction with hidden fractions as confirmation only. Record approval, selection and acknowledgement in the ledger before any launch.
- [ ] **Step 2: Use the frozen `RT`** at Task 5's implementation commit `I`, with criteria from freeze `F`/the evidence root; per task: `$PY $H/prepare.py calibrate --task $RT/experiments/compare/tasks/<task> --criterion <criterion> --out $P/<task>/A --judge claude-opus-5-5 --judge gpt-6.1-sol=$H/providers/score_codex.json --runtime $RT --batches 2 --per-batch 5 --min-per-batch 4 --filler-seed <seed> --filler <applicable paths>`.
- [ ] **Step 3: Score** one judge after another behind the shims (`bash $P/<task>/A/records/score-<judge>.sh`; `verify-pool` after each; `scan --pool --judge --hash SOL`; adjudicate, with `judge ran tests` hits reported; a stopped judge is resumed, never rerun).
- [ ] **Step 4: Summarize** each pool; read `results.json["calibration"]`; count, by reading each judge's `reason` fields, ratings stating a blind clone equals the reference (reported). Read each judge's scoped native receipts through the existing receipt/report join and price with `criterion.price_table`; record unavailable coverage explicitly.
- [ ] **Step 5: Decide under the frozen rule**: both pools `passed` → the measure is calibrated for the family; proceed to Task 7. Otherwise record the failure and the one revision (Decision 2) in the ledger, write the revised criterion with a new hash, and go to Task 6b.

### Task 6b: Live Step A′ — one rerun after the predeclared revision (owner gate: 8 calls, cap 10)

- [ ] **Step 1: Ask the owner** with the revised criterion hash, the revision (alternative (b) rubric-only, or one judge swap), 8 calls, cap 10, and the remaining worst-case total. Nothing runs without approval.
- [ ] **Step 2: Repeat** Task 6 Steps 2–4 under the revised criterion in fresh pools `P/<task>/A2`.
- [ ] **Step 3: Decide**: both pools `passed` → calibrated; otherwise the judge measure is uncalibrated for the family, no further live step runs, and Task 9's failure branch applies.

### Task 7: Live Step B — family re-qualification under `amends_5` (owner gate: 8 calls, cap 14) and B2 (4 calls, cap 4)

**Files:** operator commands only; `W/B/records/{direct_task,review_once}/run-k`; `P/<task>/B2`; ledger entries.

- [ ] **Step 1: Ask the owner** with: `amends_5` text for acceptance; per task 2 `direct_task` + 2 `review_once` = 8, +2 per borderline task, +1 per frozen-rule review rerun, cap 14; B2's 4; the remaining worst-case total. Step B does not launch without `amends_5` accepted in the ledger.
- [ ] **Step 2: Run** `prepare.py run --task <task> --arm direct_task --root $W/B --runtime $RT --set model=gpt-6.1-sol --set effort=high` (k = 2 per task, in tmux), `collect`, `scan --hash SOL`, adjudicate; then `--arm review_once --apply <final.diff>` per patch, `collect` (records `blockers`), scan, adjudicate.
- [ ] **Step 3: Step B first-attempt figure (reported, not the gate)**: `python -m experiments.orc_structural_search.evaluation check --task --patch <final.diff> --runtime $RT` per single-call patch; record pass/fail and `touched_frozen`; measure each patch's hidden fraction (descriptive).
- [ ] **Step 4: Qualification**: the first two samples qualify a task at mean blockers ≥1.5; an initial mean in [1,1.5) adds the third pair (owner notified, within the cap) and qualifies only with final mean ≥1; an initial mean below1 fails. Record every original sample/paired review and any frozen-rule rerun. Two qualified tasks are required before any later live arm; this does not admit the amended family into structural V1.
- [ ] **Step 5 (B2)**: per task `prepare.py calibrate ... --out $P/<task>/B2 --batches 1 --per-batch 5 --min-per-batch 2 --filler <Step B patches> --filler <unused applicable fillers>`; score both judges; summarize; then `summarize.py --calibration-over <accepted-A-or-A2-results.json> $P/<task>/B2/records/results.json --criterion <criterion>`: the B2 pool must pass P1–P3 and the cross-pool spread must stay ≤ 2 for the measure to remain calibrated.

### Task 8: Live Step C — measure-free gate-3 check (owner gate: ≤ 12 calls, cap 12)

**Files:** existing driver CLI only; `W/C`, `E/C`, the separate C criterion/configuration, first-attempt checks and ledger.

- [ ] **Step 1: Ask the owner** with the concrete C criterion/configuration hashes and runtime: 2 tasks × 2 evaluations of the frozen `implement_check_diagnose_repair` seed (≤ 3 calls each), ≤12 calls/cap12 and the remaining overall allocation. This step records execution/check outcomes and cost, not quality comparison.
- [ ] **Step 2: Verify the exact launch inputs.** `C_CONFIG` has the existing ExperimentConfig shape, I1/legacy condition and entry `implement_check_diagnose_repair::run`; its `criterion_sha256` matches the independent `C_CRITERION` with `purpose: "measure-free"`. `EARLIER_ROOTS` names each previous work/evidence/pool directory, including `W/B`, never ancestor `W`, runtime or the current `W/C` tree. Set inherited `COMPARE_HIDE` to that colon-separated list and supply every same root as a repeated `--holdout` for scans. `--hide` alone is insufficient for these evaluations.
- [ ] **Step 3: Run the actual existing CLI** in tmux after approval (paths/hashes are frozen operator inputs):

```bash
IFS=: read -r -a C_HIDDEN_ROOTS <<< "$EARLIER_ROOTS"
C_SCAN_ROOTS=()
for C_HIDDEN_ROOT in "${C_HIDDEN_ROOTS[@]}"; do
  C_SCAN_ROOTS+=(--holdout "$C_HIDDEN_ROOT")
done
COMPARE_HIDE="$EARLIER_ROOTS" PYTHONPATH="$RT" python -m experiments.orc_structural_search.driver \
  --config "$C_CONFIG" --criterion "$C_CRITERION" \
  --seeds "$RT/experiments/orc_structural_search/seeds/implement_check_diagnose_repair.orc" \
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
| Owner instruction selects offline preparation (Tasks 1–5) | Implement/review a concrete experiment packet; all task checkboxes remain open until verified, and each paid step still needs its stated approval |
| Reuse the merged receipt/pricing apparatus | No second metering API, price-table alias or session discovery path |
| Keep generic calibration separate from structural V1 quality | Preserve `qualification.validate` and `mapping.qualification`; defer V2 until a later successor study is selected |
| Freeze implementation before criteria that name it | Runtime commit `I` and criterion freeze `F` are distinct; preserve all historical bytes |
| Missing observations fail the full predeclared denominator | No excluded judge, missing control or incomplete rating can silently improve calibration |
| B2 compares the actual accepted A or A2 | Never substitute the failed original A after an approved rerun |
| Explicit measure-free C and separate B/C roots | Existing driver flags, matching criterion hash, inherited masks plus scan roots; no quality bypass or ancestor mask |
| Preserve scientific rules and proposed allocation | P1/P2/P3/spread, controls, gate-3 band and planned32/maximum50 unchanged; no paid approval recorded |
