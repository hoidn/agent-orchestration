# ORC Structural Search Measurement Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** proposed, unselected (2026-10-19). Offline tasks need no allocation. Each live step is its own owner budget decision with the call estimate stated in its task; nothing live runs before the owner approves that step.

**Goal:** Close gates 2–4 of the [module plan](2026-10-19-orc-structural-search-module-rewrite-plan.md#gate-for-a-live-module-arm) and the roadmap's Calibration decision point: a blind judge measure that passes a predeclared calibration on known controls (upstream, stub, and a partially reverted upstream), a task family whose agent-visible `dev-check` fails at the first attempt often enough that check-gated control flow branches, both on family (a) rungs 2 and 4 under the frozen difficulty rule, and metering wired with a frozen per-model price table, so a live Phase 2 or `module` arm can be selected.

**Architecture:** Extend `experiments/compare/` in place: a second scoring workflow `score_ref.orc` (intent-anchored absolute rubric with a disclosed reference clone per batch), rubric selection through the criterion in `pool.py`/`summarize.py`, a calibration pool builder from recorded diffs (`calibrate.py`) and a `calibration` verdict in `summarize.py`. Task packages gain a `-partial.diff` anchor and a promoted visible test file whose digest `dev_check.py` freezes. `experiments/orc_structural_search/metering.py` gains per-model field sums and a pricing function, and the driver logs it instead of `unavailable`. No new module beyond `calibrate.py`; no change under `orchestrator/`.

**Tech Stack:** Python 3.13 standard library; `orchestrator` public CLI (judge runs of `score_ref.orc`); `experiments/compare` shims (bubblewrap), `pool.py`, `summarize.py`, `prepare.py run/collect/scan`; retained evidence `/home/ollie/ss-pools/phase1/*` (patches as fillers, zero spend); tests with the scripted judge in `tests/experiments/compare_harness_support.py` and `orc_structural_search_support.py`.

**Spec:** `docs/design/orc_structural_search_driver.md` ("Task Family And Evaluator": the calibration predicate; "Objective, Selection And Local Observations"; "Metering And Consumption": the field mapping); `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (Decision Points: Calibration row; Phase 2 gates; Family candidates and cost inputs); `docs/reports/2026-10-18-orc-structural-search-phase1.md` (Anchors And Judges; "The agent-visible check carried no signal"; Next Step); `experiments/compare/criteria/calibration.json` `amends_4` (the frozen difficulty rule); `docs/design/orc_effectiveness_comparison_harness.md` D4–D6 and the 2026-10-15 evaluation policy; the module plan's gates 2–4.

## Global Constraints

- Owner rules, binding: no provider spend on a quality comparison before both calibrations pass; "better" is Pareto over quality and metered deployed cost; no Fable model in any call (judges, single calls, reviews, coders; the shims' guard and scan apply); every live step is approved by the owner with its call estimate before launch; hidden acceptance stays descriptive, and making it primary is offered to the owner as an explicit policy decision only in Task 8's failure branch.
- Work in a worktree of `main` from `fcc2ada2`; no file under `orchestrator/` changes; every module ≤ 500 lines (`summarize.py` 301, `pool.py` 254, `metering.py` ≈ 150, `driver.py` 484, `evaluation.py` 233 today); no test asserts prompt text.
- Family: `experiments/compare/tasks/resume-projection-integrity` (base `1cd607673c89170dc96c74a0b5eb4aef204da82d`) and `pure-result-replay` (base `f80e551a6cdeca6a2913ce640326495be1ae1cc5`); rung 1 `cf1-generic-unions` is reserved for a later sealed split and is not amended here. Solution hashes are operator-supplied (`--hash`/`--solution`), never written into a package or criterion.
- Rubric v2 (`score_ref.orc`): criteria `completeness`, `correctness`, `scope`, `layering`, each `S0|S1|S2`, total 0–8, averaged over judges; one disclosed reference clone per batch (the upstream anchor applied), blind controls in every batch: `<pkg>-upstream`, `<pkg>-stub`, `<pkg>-partial`.
- Calibration predicate, frozen in `experiments/compare/criteria/judge-calibration.json` before any judge call: P1 (the design's rule) for each (judge, batch): `total(upstream) − total(stub) ≥ calibration.margin = 4`, failing fraction ≤ `calibration.error_rate = 0`; P2 (this plan, required): strict ordering `stub < partial < upstream` per (judge, batch), failing fraction ≤ 0; cross-batch spread of each blind anchor per judge ≤ `anchor_spread_limit = 2`. A pool passes when P1, P2 and the spread hold; the measure is calibrated for the family when both tasks' pools pass.
- Judges: `claude-opus-5-5` (`experiments/compare/score.providers.json`) and `gpt-6.1-sol` (`experiments/compare/providers/score_codex.json`), effort `high`, `:timeout-sec 3600` per batch; 2 batches per task; each batch = 1 reference + 3 blind anchors + 5 fillers (≤ 10 blind clones, D4), fillers disjoint across the task's two batches, drawn by `random.Random(filler_seed)` from the retained Phase 1 pool patches, seed recorded in the criterion.
- Family rule unchanged: `calibration.json` `amends_4` (k = 2 `direct_task` single calls `gpt-6.1-sol`/`high`/14400 s, one `review_once` each, qualifies at mean blockers ≥ 1, borderline 1 ≤ mean < 1.5 adds a third pair). Gate 3 band, predeclared: per task, the `dev-check` fails on at least one of the k first-attempt single-call patches.
- Metering: per-model field sums priced by the criterion's `models` table (USD per 1M tokens: `input`, `output`, `cache_read`, `cache_write`; `source` URL and `date` per row, copied from the providers' official pricing pages on the freeze date; no price is stated in this plan); the receipt-to-price mapping is the design's; a run with any unmatched call or incomplete receipt prices as `unavailable`, never 0.
- Budgets (provider calls, charged as in Phase 1; immediate zero-work refusals listed, not silently subtracted): Step A judge calibration 8, cap 10; Step B family re-qualification 8 (+2 per borderline task, +1 per frozen-rule review rerun), cap 14; Step B2 replicate on unseen fillers 4, cap 4; Step C optional live branch smoke ≤ 6, cap 6. Order A → B → B2 → C; A runs first because it is the cheapest step that can falsify the evaluator.
- Live roots: runtime worktree `RT=/home/ollie/sc-runtime` at the frozen commit, work root `W=/home/ollie/sc-work`, pools `P=/home/ollie/sc-pools/<task>/<batch set>`, evidence and ledger `E=/home/ollie/sc-evidence` (`ledger.md`, `criterion.sha256`, `solutions.txt`); none under `/home/ollie/Documents/agent-orchestration*`, `/tmp`, `/dev/shm`, `/var/tmp`; existing roots (`ss-*`, `ss3-*`, `calib-*`) are read only for fillers and never modified.
- Verification: narrow selectors first, `pytest --collect-only` on new test modules, then `pytest -q -n 16 --dist=worksteal tests/experiments/`; commits with pathspecs, one per task, messages in the repository's existing style.

## Review Focus

1. A judge that copies the reference's ratings onto a blind clone merely because the trees are byte-identical: P1 alone would pass trivially; P2's ordering on the partial control and the reported "recognition" count (Task 6) carry the falsification (Task 2 `test_calibration_verdict_requires_the_partial_ordering`).
2. An agent that edits the promoted visible test so the check passes: `dev_check.py` must fail closed on a digest mismatch (Task 3 `test_dev_check_fails_closed_when_a_frozen_file_changes`).
3. A pool whose `rubric` differs from the criterion's (an old-rubric criterion summarising a `score_ref` pool, or the reverse) must be refused, not silently joined by position (Task 1 `test_summarize_refuses_a_criterion_whose_rubric_differs_from_the_pools`).
4. A metered run with one unmatched shim call, or a Codex rollout without a model name, must price `unavailable` and never 0 (Task 4 `test_price_is_unavailable_with_an_unmatched_call_or_unknown_model`).
5. A third anchor file in a package changes every future pool's batch arithmetic: the scoring module's per-batch anchor count must follow the package, not the constant 2 (Task 3 `test_pool_batches_carry_every_package_anchor`).

## Decisions

1. **Evaluator: intent-anchored absolute rubric with a disclosed reference (recommended).** Alternatives weighed: (a) pairwise comparison against the upstream fix: removes batch effects by construction but yields no scale for a frontier and cannot separate a stub from a partial without magnitude, and costs a call per pair; rejected. (b) Rubric change only (add `completeness`, keep batches blind, no reference): cheaper, but the judge still rates within the batch, so drift remains; kept as the one predeclared revision if (c) fails. (c) Absolute rubric plus a disclosed reference clone per batch: the reference fixes the top of the scale in every batch; the instruction is to rate against the intent and the reference, not the other repositories; a repository implementing none of the intended behaviours scores S0 on every criterion (this is the Phase 1 defect: the stub earned `scope`/`layering` points for doing nothing); a different implementation that provides the behaviours scores S2 on `completeness`, so a candidate may equal or beat upstream. Hidden acceptance as primary is not an alternative here; it is offered to the owner only in Task 8's failure branch.
2. **Calibration experiment.** Controls per task: blind upstream, blind stub, blind partial (the upstream diff with one coherent source module's hunks excluded, verified offline to pass a hidden fraction strictly between the stub's 0.00 and the upstream's 1.00, target 0.3–0.7). Fillers are retained Phase 1 patches (13 per task), so the judge sees realistic batches at zero spend. Judges as in the three-arm criterion. P1 margin 4 because a stub can earn at most 4 points on the two non-behaviour criteria under the new rule and an upstream copy earns 8; error rate 0 over 8 (judge, batch) pairs; P2 strict ordering is the load-bearing check against reference recognition. Failure policy, predeclared: one revision only (alternative (b), or one judge swap), a new criterion hash and one rerun of Step A at the same cap; a second failure declares the judge measure uncalibrated for the family, and the report then offers the owner the explicit policy decision (hidden acceptance primary) or stopping.
3. **Family and check.** Keep rungs 2 and 4 (qualified, Phase 1 evidence and fillers exist). Promote one whole hidden test file per task, `tests/test_runtime_step_lifecycle.py` (8 and 5 hidden nodes; failed on 13/14 and 13/13 retained blind patches), into `seed/tests/`, drop its node ids from `hidden_tests.txt`, add it to `dev-check.json` beside the existing base-green modules, and freeze its digest. Alternatives weighed: new hand-written check commands (authoring cost, unverified against the solution); the full test suite as a regression net (slow inside the 1,800 s check timeout, failure rate unknown); a larger promoted file (51 or 104 nodes would make the task a visible-test task). Because a coder can run a visible test in-call, the first-attempt failure rate is an unknown that Step B measures under the predeclared band; the package change needs re-qualification under the frozen rule (owner may rule it transfers; default: re-qualify, since the same runs measure gate 3). Two tasks now; rung 1 is reserved for a sealed split.
4. **Metering.** Log raw per-model field sums per evaluation; price at readout from the criterion's `models` table, so re-pricing never rewrites a log. The price table is filled from the providers' official pricing pages on the freeze date, with URL and date in the criterion.
5. **Minimal footprint.** One new module (`calibrate.py`); `score.orc` stays frozen as the historical rubric and remains the ablation control; the partial anchor joins every future pool automatically through the existing `anchors/*.diff` glob, so in-run calibration monitoring needs no further code.

## Feasibility (verified in the code at `fcc2ada2`)

- `pool.pool(task, criterion, out, judges, runs)` already receives the criterion path; `write_score_inputs` hard-codes `score.orc` and `score::score` (`pool.py:188`), so rubric selection is a mapping field read there; `scoring.build_pool` is a declared copy of `pool.pool` (`scoring.py`, `ponytail:` note) and must gain the same field.
- `summarize.CRITERIA` is a module constant used by `join`, `agreement`, `totals` and the tests; `scoring_run` checks only the bound criterion hash and judge model; `anchor_scores` keys on `arm == "anchor"`, so a reference clone with `arm == "reference"` is invisible to anchor figures and `verify_pool` restores it like any clone.
- Anchors are discovered by `sorted((task / "anchors").glob("*.diff"))` in `pool.build_batches`; `scoring.ANCHORS_PER_BATCH` is a constant used for batch sizing; `anchor_checks` reads roles `upstream`/`stub` only.
- All three `seed/dev-check.json` files list base-existing modules (commit `37a9ff5c`); `dev_check.py` reads `dev-check.json` from the clone and fails closed without it; `evaluation.evaluate` copies `dev_check.py` from the candidate root into the clone and excludes it from patches, so a digest check belongs in `dev_check.py` and its data in `dev-check.json` (seeded, committed onto base).
- Retained Phase 1 pools: `/home/ollie/ss-pools/phase1/<task>/records/{mapping.json,patches/<id>.diff,results.json}`, 17 clones in 2 batches per task, 13 non-anchor patches each (D8-stripped); `results.json` carries `clones.<id>.hidden_failed`, from which the per-file failure counts above were computed.
- `metering.claude_usage` yields `model` plus the four usage fields per assistant message; `codex_usage` reads `total_token_usage` with `input_tokens`, `cached_input_tokens`, `output_tokens`, `total_tokens`; a 2026-10-19 rollout holds `"model":"gpt-6.1-sol"` entries, so the model is recoverable from the rollout; `coverage` joins shim calls to sessions by user-turn text. The driver writes `consumption: UNAVAILABLE` at `driver.py:184` (episodes) and `:439` (evaluations). Shim call records (`calls/<n>/`) hold no model, so pricing must read the sessions.
- `scan.claude_sessions(tree, home)` and the Codex filter inside `scan.sources` (rollouts whose `cwd` lies under the tree, modified since a time) locate receipts for a run; `scan_judge` computes the judge's tree from `mapping.judges[judge].dir`.
- `prepare.run --arm direct_task --set model=gpt-6.1-sol --set effort=high` and `--arm review_once --apply <final.diff>` are the frozen rule's arms; `collect` records `blockers`; the harness refuses roots under the main prefix or `/tmp`.
- The scripted judge in `tests/experiments/test_compare_pool_summarize.py::score` writes a completed scoring run per judge from `score-inputs-<judge>.json`, so rubric-v2 pools are testable offline by extending its `rating` tokens.

---

### Task 1: Rubric v2 scoring workflow and criterion-selected rubric

**Files:**
- Create: `experiments/compare/score_ref.orc` (module `score_ref`, export `score`; `Rating` with `clone`, `completeness`, `correctness`, `scope`, `layering`, `reason`; `Batch` with `clones List[String]` and `reference String`; `rate-batch` prompt fills `intent`, `reference`, `clones`; `providers.judge` as in `score.orc`)
- Modify: `experiments/compare/pool.py` (`rubric()`, `build_batches` reference clone per batch, `write_score_inputs`, mapping fields), `experiments/compare/summarize.py` (criteria from the mapping; refusal on rubric mismatch), `experiments/orc_structural_search/scoring.py` (`build_pool` mapping gains `rubric`; anchor count from the package)
- Modify: `experiments/compare/README.md` (score section: the two rubrics and the `rubric` criterion object)
- Test: `tests/experiments/test_compare_pool_summarize.py`, `tests/experiments/test_orc_structural_search_seeds.py` (compile check of the new workflow)

**Interfaces:**
- Produces: `pool.rubric(criterion: Path) -> dict` = `{"workflow": "score_ref.orc", "entry": "score_ref::score", "criteria": [...], "reference": "upstream" | None}` from `criterion["rubric"]`, default `{"workflow": "score.orc", "entry": "score::score", "criteria": ["root_cause","scope","generality","layering"], "reference": None}`; mapping gains `rubric` and, with a reference, `references: [clone id per batch]`; each clone entry may carry `arm: "reference"`.
- Produces: `summarize.criteria_of(mapping) -> tuple[str, ...]`; `summarize()` refuses when `rubric(criterion) != mapping["rubric"]`.
- Consumes: `repos.build_candidate`, `pool.add_clone` unchanged.

- [ ] **Step 1: Write the failing tests** in `tests/experiments/test_compare_pool_summarize.py`:

```python
def test_pool_with_a_reference_rubric_adds_one_reference_clone_per_batch_outside_the_blind_list(world):
    # criterion {"rubric": {"workflow": "score_ref.orc", "entry": "score_ref::score",
    #            "criteria": ["completeness","correctness","scope","layering"], "reference": "upstream"}}
    # assert: mapping["references"] has one id per batch; that id is in mapping["clones"] with arm "reference";
    # score-inputs-<judge>.json batches carry "reference" = its path and exclude it from "clones";
    # records/score-<judge>.sh names score_ref.orc and --entry-workflow score_ref::score

def test_summarize_joins_the_pools_criteria_names_and_reports_them(world):
    # scripted judge returns completeness/correctness/scope/layering tokens; totals 0-8; agreement keys are these names

def test_summarize_refuses_a_criterion_whose_rubric_differs_from_the_pools(world):
    # pool built with the reference rubric, summarize called with a criterion lacking "rubric" -> SystemExit mentioning rubric
```

- [ ] **Step 2: Run them to verify they fail**: `pytest tests/experiments/test_compare_pool_summarize.py -k "reference_rubric or criteria_names or rubric_differs" -v` — FAIL (`rubric` not defined / wrong workflow in script).
- [ ] **Step 3: Write `experiments/compare/score_ref.orc`.** Same shape as `score.orc` (`:target-dsl "2.35"`, `list/map-effect ... :max 24`, `provider-result providers.judge ... :model judge_model :effort "high" :timeout-sec 3600`), `Batch` gains `(reference String)`, `rate-batch` fills `(reference :text)`. Prompt rules (behaviour, not asserted): rate each repository against the intent and the reference, not against the other repositories; the reference is the accepted implementation and shows which behaviours are required, not how to implement them; a repository implementing none of the intended behaviours scores S0 on every criterion; a different implementation providing the behaviours scores S2 on `completeness`; change nothing, run no tests. Criteria text: `completeness` (the behaviours the intent names are implemented: all S2, part S1, none S0), `correctness` (the implemented behaviours hold for the cases the intent names, judged by reading the code against the reference's behaviour), `scope` and `layering` as in `score.orc`.
- [ ] **Step 4: Implement** `pool.rubric(criterion)`; in `pool.pool` and `scoring.build_pool` put `"rubric": rubric(criterion)` into the mapping; in `build_batches`, when `rubric["reference"]`, build one extra clone per batch from `anchors/<task.name>-<reference>.diff` with entry `{"run": None, "arm": "reference", "labels": ["reference"]}`, collect ids into `references`; in `write_score_inputs`, write `"reference": str(out/"clones"/references[i])` per batch when present and take `workflow`/`entry` from `mapping["rubric"]`. In `summarize.py`, `criteria_of(mapping)` replaces every use of `CRITERIA` (keep the constant as the default), and `summarize()` refuses a rubric mismatch beside the existing judges check. In `scoring.py`, replace the `ANCHORS_PER_BATCH` constant by `len(list((task/"anchors").glob("*.diff")))` where batch sizes are computed.
- [ ] **Step 5: Run the tests and the existing pool/summarize/scoring selectors**: `pytest tests/experiments/test_compare_pool_summarize.py tests/experiments/test_orc_structural_search_scoring.py tests/experiments/test_orc_structural_search_adaptive.py -v` — PASS (old-rubric pools keep their shape).
- [ ] **Step 6: Add a compile check** in `tests/experiments/test_orc_structural_search_seeds.py` style for `score_ref.orc` (`python -m orchestrator compile`, entry `score_ref::score`, `--provider-externs-file score.providers.json`). Run it: PASS.
- [ ] **Step 7: Commit** `experiments/compare/score_ref.orc experiments/compare/pool.py experiments/compare/summarize.py experiments/orc_structural_search/scoring.py experiments/compare/README.md tests/experiments/...` — "feat(compare): intent-anchored rubric score_ref.orc with a disclosed reference clone; rubric selected by the criterion".

### Task 2: Calibration pool from recorded diffs and the calibration verdict

**Files:**
- Create: `experiments/compare/calibrate.py` (≤ 120 lines)
- Modify: `experiments/compare/summarize.py` (`calibration()` block in results), `experiments/compare/prepare.py` (subcommand `calibrate` → `calibrate.pool_from_diffs`), `experiments/compare/README.md` (calibration recipe)
- Test: `tests/experiments/test_compare_calibration.py`

**Interfaces:**
- Produces: `calibrate.pool_from_diffs(task: Path, criterion: Path, out: Path, judges: Sequence[str], runtime: Path, fillers: Sequence[Path], batches: int, filler_seed: int) -> dict`: builds `P` exactly as `pool.pool` does (guard, sandbox visibility, runtime commit, `rubric`, anchors in every batch, reference per batch) but with `runs: {}` and members `{"run": None, "arm": "filler", "labels": [diff stem]}`; fillers are dealt without replacement into `batches` batches by `random.Random(filler_seed)`; refuses when fillers < 5 × batches.
- Produces: `summarize.calibration(results_anchors, mapping, criterion) -> dict | None` when `criterion["calibration"]` exists: `{"pairs": [{"judge","batch","upstream","stub","partial","gap","p1","p2"}], "p1_failing": fraction, "p2_failing": fraction, "anchor_spread": {judge: max}, "passed": bool}` with `passed = p1_failing ≤ error_rate and p2_failing ≤ error_rate and every spread ≤ anchor_spread_limit`; roles from `criterion["anchors"][task.name]` (`upstream`, `stub`, `partial`); written into `results.json` and `results.md`.
- Consumes: Task 1's `rubric`, `references`; `pool.add_clone`, `pool.write_score_inputs`.

- [ ] **Step 1: Write the failing tests** in `tests/experiments/test_compare_calibration.py` (fixtures from `compare_harness_support.world`, a task with three anchors `-upstream`, `-stub`, `-partial`, seven filler diffs):

```python
def test_pool_from_diffs_deals_disjoint_fillers_and_every_anchor_into_each_batch(world): ...
    # 2 batches, 5 fillers each would need 10 -> with 7 fillers refuse; with 10 fillers: disjoint, 3 anchors + reference per batch
def test_calibration_verdict_passes_when_margin_and_ordering_hold_in_every_pair(world): ...
    # scripted judges: upstream 8, partial 5, stub 1 in both batches -> passed True, p1_failing 0.0, p2_failing 0.0
def test_calibration_verdict_requires_the_partial_ordering(world): ...
    # judge-b batch 1: upstream 8, stub 1, partial 0 -> p1 holds, p2 fails -> passed False, p2_failing 0.25
def test_calibration_verdict_fails_on_anchor_spread_above_the_limit(world): ...
    # upstream 8 in batch 0 and 5 in batch 1 for one judge -> spread 3 > 2 -> passed False
```

- [ ] **Step 2: Run to verify they fail**: `pytest tests/experiments/test_compare_calibration.py -v` — FAIL (`calibrate` missing).
- [ ] **Step 3: Implement `calibrate.pool_from_diffs`** reusing `pool.add_clone`, `pool.write_score_inputs`, `repos.{guard, visible_in_sandbox, runtime_commit, main_checkout, build_candidate, dump, sha256_file}`; the seeded commit comes from the first clone built. Implement `summarize.calibration` and call it from `summarize()`; add the `calibrate` subcommand to `prepare.py` (`--task --criterion --out --judge ... --runtime --filler DIFF ... --batches N --filler-seed N`).
- [ ] **Step 4: Run the tests**: PASS. Run `pytest --collect-only tests/experiments/test_compare_calibration.py`.
- [ ] **Step 5: Commit** — "feat(compare): calibration pools from recorded diffs and the predeclared calibration verdict".

### Task 3: Family packages: partial anchor, promoted visible check, frozen check digest

**Files:**
- Modify: `experiments/compare/tasks/resume-projection-integrity/{seed/dev-check.json, hidden_tests.txt}`; create `seed/tests/test_runtime_step_lifecycle.py` (moved from `hidden/tests/`), `anchors/resume-projection-integrity-partial.diff`; same for `pure-result-replay`
- Modify: `experiments/orc_structural_search/seeds/dev_check.py` (frozen digests), `experiments/compare/tasks/calibration-ladder.md` (amended-package rows: promoted file, new hidden counts, partial's hidden fraction, package sha256)
- Test: `tests/experiments/test_orc_structural_search_seeds.py`, `tests/experiments/test_compare_pool_summarize.py`

**Interfaces:**
- Produces: `dev-check.json` gains `"frozen": {"tests/test_runtime_step_lifecycle.py": "<sha256>"}`; `dev_check.check()` returns `{"passed": False, "failing": ["frozen file modified: <path>"], "excerpt": ""}` before running argv when any listed file is missing or its digest differs.
- Produces: per package a third anchor `<pkg>-partial.diff` (joins every batch by the existing glob) and the ladder rows that record what was excluded and the measured hidden fractions.

- [ ] **Step 1: Write the failing tests**:

```python
# tests/experiments/test_orc_structural_search_seeds.py
def test_dev_check_fails_closed_when_a_frozen_file_changes(tmp_path): ...   # digest mismatch -> passed False, argv not run
def test_dev_check_runs_argv_when_frozen_files_match(tmp_path): ...
# tests/experiments/test_compare_pool_summarize.py
def test_pool_batches_carry_every_package_anchor(world): ...                # three anchors -> each batch has three arm=="anchor" clones
```

- [ ] **Step 2: Run to verify they fail**; implement the `frozen` check in `dev_check.py` (`hashlib.sha256` over bytes); run to PASS.
- [ ] **Step 3: Author the partial anchor per task (offline, free).** In a scratch clone built by `repos.build_candidate(RT, base, task/seed, dest)`: `git apply --exclude='orchestrator/<one source module of the upstream diff>' anchors/<pkg>-upstream.diff`, then `repos.patch_of(clone, seeded_base) > anchors/<pkg>-partial.diff`. Choose the excluded module so imports still resolve; measure `1 - len(summarize.hidden_failures(clone, task, nodes, PY)) / len(nodes)` and require 0.3 ≤ fraction ≤ 0.7, else exclude another module and repeat. Record the module and fraction in the ladder.
- [ ] **Step 4: Promote the check per task.** `git mv hidden/tests/test_runtime_step_lifecycle.py seed/tests/`; delete its node ids from `hidden_tests.txt` (expected remaining: 111 and 129); add `tests/test_runtime_step_lifecycle.py` to the front of `dev-check.json` `argv` and its sha256 under `frozen`. Verify in scratch clones and record outputs in the ledger: at the seeded base `python dev_check.py` reports `passed: false`; with the upstream anchor applied `passed: true`; with the stub applied `passed: false`; with the partial applied record the result; the remaining hidden set keeps upstream 1.00 and stub ≤ 0.01 (`summarize.hidden_failures`).
- [ ] **Step 5: Measure the blind first-attempt failure rate of the promoted check at zero spend**: apply each retained Phase 1 patch (`/home/ollie/ss-pools/phase1/<task>/records/patches/*.diff`, non-anchor) to a scratch clone and run `python dev_check.py`; record `failed/13` per task in the ledger as the upper-bound estimate (patches made without seeing the test).
- [ ] **Step 6: Record each amended package's sha256** (the ladder's `find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum`) in the ladder and in Task 5's criterion.
- [ ] **Step 7: Run** `pytest tests/experiments/test_orc_structural_search_seeds.py tests/experiments/test_compare_pool_summarize.py -v` — PASS. **Commit** — "feat(tasks): partial anchors and a promoted agent-visible check with frozen digests for rungs 2 and 4".

### Task 4: Metering wired into the driver and priced at readout

**Files:**
- Modify: `experiments/orc_structural_search/metering.py` (`consumption`, `price`, `__main__`), `experiments/compare/scan.py` (factor `codex_rollouts(tree, since, home)` out of `sources`), `experiments/orc_structural_search/driver.py:184,439` (log `metering.consumption(...)`), `experiments/orc_structural_search/README.md` ("Not implemented": remove the metering line; add the readout pricing rule)
- Test: `tests/experiments/test_orc_structural_search_metering.py`, `tests/experiments/test_orc_structural_search_driver.py`

**Interfaces:**
- Produces: `scan.codex_rollouts(tree: Path, since: float, home: Path) -> list[Path]` (the filter now inline in `sources`, which calls it).
- Produces: `metering.consumption(records_dir: Path, tree: Path, since: float, home: Path) -> dict | "unavailable"`: `{"calls": n, "unmatched_calls": m, "by_model": {model: {"input","output","cache_read","cache_write"}}}` using `coverage`'s join; Codex rows take the model from the rollout's model entries and map `input_tokens - cached_input_tokens` → `input`, `cached_input_tokens` → `cache_read`, `cache_write_input_tokens` (0 if absent) → `cache_write`, `output_tokens` → `output`; Claude rows map the four usage fields as the design states; `"unavailable"` when any call is unmatched or any matched receipt lacks a field or model.
- Produces: `metering.price(consumption, models: Mapping[str, Mapping[str, float]]) -> float | "unavailable"` (USD; `unavailable` when consumption is unavailable or a model has no row); `python -m experiments.orc_structural_search.metering --records R --tree T --since EPOCH --criterion C` prints both.
- Consumes: criterion `models` table (Task 5).

- [ ] **Step 1: Write the failing tests** (fixture session files as the module's existing tests build them, plus a `turn_context`-style Codex entry carrying `"model"`):

```python
def test_consumption_sums_fields_per_model_across_claude_and_codex_receipts(tmp_path): ...
def test_price_is_unavailable_with_an_unmatched_call_or_unknown_model(tmp_path): ...
def test_price_applies_the_frozen_field_mapping(tmp_path): ...   # one Claude row, one Codex row, a two-model table -> exact USD
# test_orc_structural_search_driver.py
def test_evaluation_rows_carry_consumption_when_receipts_exist(sandboxed, world): ...  # scripted claude writes a session file; row["consumption"]["by_model"] present
```

- [ ] **Step 2: Run to verify they fail**; **Step 3: Implement** as specified (the driver passes `records_dir`, the clone tree from `record.json`'s `candidates[0]`, `since` = the records' `created` time, `Path.home()`); **Step 4: Run** the metering, driver and compare-harness selectors — PASS.
- [ ] **Step 5: Commit** — "feat(search): metered consumption per model on log rows; priced from the criterion's table at readout".

### Task 5: Freeze the calibration criterion, the ledger and the documentation hooks

**Files:**
- Create: `experiments/compare/criteria/judge-calibration.json`
- Modify: `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (Decision Criteria: the measurement plan is this file), `docs/plans/2026-10-19-orc-structural-search-module-rewrite-plan.md` (gates 2–4 cite this plan), `experiments/compare/README.md` (criterion fields `rubric`, `calibration`, `models`), `docs/index.md` (plan row)
- Test: `tests/experiments/test_compare_calibration.py::test_frozen_criterion_has_every_required_field`

**Interfaces:**
- Produces: the criterion with exactly these fields: `experiment`, `plan`, `tasks` (the two packages), `base_commits`, `package_sha256` (Task 3), `judges`, `judge_bindings`, `rubric` (Task 1's object with `reference: "upstream"`), `anchors` per task `{upstream, stub, partial}`, `partial_hidden_fraction` per task (Task 3), `calibration: {"margin": 4, "error_rate": 0, "ordering": "stub < partial < upstream, strict, per (judge, batch)", "ordering_error_rate": 0}`, `anchor_spread_limit: 2`, `batches_per_task: 2`, `fillers: {"source": "/home/ollie/ss-pools/phase1/<task>/records/patches", "per_batch": 5, "seed": <int>, "sha256": {...}}`, `family_rule: "experiments/compare/criteria/calibration.json amends_4, k = 2, borderline third pair; dev-check band: at least one of k first-attempt patches fails"`, `models` (price table with `source`, `date` per model: `claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-6.1-sol`, `gpt-6-sol`), `failure_policy` (Decision 2's text), `budget: {"A": 8, "A_cap": 10, "B": 8, "B_cap": 14, "B2": 4, "B2_cap": 4, "C": 6, "C_cap": 6}`, `model_policy`, `written_before_scoring: true`.

- [ ] **Step 1: Write the test** asserting the field set and the exact numbers above; run it to FAIL; write the file; PASS.
- [ ] **Step 2: Record** `sha256sum experiments/compare/criteria/judge-calibration.json` in `E/criterion.sha256` and the ledger's first entry; the hash is bound into every scoring run through `pool`.
- [ ] **Step 3: Documentation hooks** as listed (one row each; no narrative). **Commit** — "docs(search): freeze the judge-calibration criterion and route the measurement plan".

### Task 6: Live Step A — judge calibration on known controls (owner gate: 8 calls, cap 10)

**Files:** operator commands only; outputs under `P`, `E`; `E/ledger.md` entries.

- [ ] **Step 1: Ask the owner** with the estimate: 2 tasks × 2 batches × 2 judges = 8 judge calls, cap 10 (the extra 2 cover one resumed judge run). Record the approval in the ledger before any launch.
- [ ] **Step 2: Create `RT`** (`git worktree add --detach /home/ollie/sc-runtime <commit of Task 5>`); build the pools: `$PY $H/prepare.py calibrate --task $RT/experiments/compare/tasks/<task> --criterion <criterion> --out $P/<task>/A --judge claude-opus-5-5 --judge gpt-6.1-sol=$H/providers/score_codex.json --runtime $RT --batches 2 --filler-seed <seed> --filler <13 patch paths>` per task.
- [ ] **Step 3: Score** one judge after another behind the shims (`bash $P/<task>/A/records/score-<judge>.sh`; `verify-pool` after each; scan each judge with `--hash SOL`, adjudicate hits; a stopped judge is resumed, never rerun).
- [ ] **Step 4: Summarize** (`summarize.py --pool ... --criterion ...`); read `results.json["calibration"]`; also count, by reading each judge's `reason` fields, ratings that state the blind clone is identical to the reference (reported as the recognition count, not a gate). Run `python -m experiments.orc_structural_search.metering` over each judge's records and tree to report receipt coverage per provider.
- [ ] **Step 5: Decide under the frozen rule**: both pools `passed` → the measure is calibrated for the family, proceed to Task 7. Otherwise apply Decision 2's failure policy once (ledger entry, new criterion hash, rerun Step A within its cap); a second failure ends live work and goes to Task 8's failure branch.

### Task 7: Live Step B — family re-qualification and the check-failure band (owner gate: 8 calls, cap 14; B2: 4, cap 4)

**Files:** operator commands only; `W/records/{direct_task,review_once}/run-k`; ledger entries.

- [ ] **Step 1: Ask the owner** with the estimate (per task 2 `direct_task` + 2 `review_once` = 8; +2 per borderline task; +1 per frozen-rule review rerun; cap 14) and state the alternative ruling (qualification transfers from the unamended package; then only Step 3 below runs on the existing retained patches and gate 3 rests on the blind upper bound of Task 3 Step 5). Default: run.
- [ ] **Step 2: Run** `prepare.py run --task <task> --arm direct_task --root $W --runtime $RT --set model=gpt-6.1-sol --set effort=high` (k = 2 per task, in tmux), `collect`, `scan --hash SOL`, adjudicate; then `--arm review_once --apply <final.diff>` per patch, `collect` (records `blockers`), scan, adjudicate.
- [ ] **Step 3: Measure gate 3**: for each single-call clone, apply its `final.diff` to a scratch seeded clone and run `python dev_check.py` with the package's `dev-check.json`; record pass/fail per patch. Band: ≥ 1 failing first-attempt patch per task. Measure the hidden fraction of each patch (descriptive) with `summarize.hidden_failures`.
- [ ] **Step 4: Qualification**: mean blockers ≥ 1 per task qualifies; 1 ≤ mean < 1.5 adds the third pair (owner notified, within the cap); a task that fails either the rule or the band is reported, and the family keeps only qualifying tasks (two are required for a live arm; one leaves the family unqualified).
- [ ] **Step 5 (B2, owner gate, 4 calls)**: one further batch per task with the new single-call patches as fillers (same controls and reference, `--batches 1`), scored by both judges; the calibration verdict is recomputed over all three batches per task (P1, P2, spread; error rate 0 still). This checks the evaluator on fillers no judge has seen.
- [ ] **Step 6 (C, optional, owner gate, ≤ 6 calls)**: one driver evaluation per task of the `implement_check_diagnose_repair` seed on the amended package (measure-free: no judge), to show the repair branch realised live and to record metered consumption for a Claude coder and a Codex reviewer. Not required for the gates.

### Task 8: Report, gate verdicts and successor-criterion inputs

**Files:**
- Create: `docs/reports/2026-10-<dd>-orc-structural-search-measurement-calibration.md`
- Modify: `docs/plans/2026-10-18-orc-structural-search-roadmap.md` (Calibration row: outcome and the frozen hash), `docs/design/orc_structural_search_driver.md` ("Task Family And Evaluator": the rubric v2, partial control and ordering rule, if accepted by the owner), `docs/plans/2026-10-19-orc-structural-search-module-rewrite-plan.md` (gates 2–4 status), `experiments/compare/tasks/calibration-ladder.md`, `docs/index.md`

- [ ] **Step 1: Write the report** from `results.json` (`calibration`, `anchors`, `agreement`, recognition count), the harness `collect` records (blockers, dev-check pass/fail per patch, hidden fractions) and the metering CLI output (receipt coverage per provider, priced judge and single-call cost), with every spent call listed against the caps and the file hashes of the evidence.
- [ ] **Step 2: Gate verdicts**, one line each: gate 2 (calibrated measure: criterion hash, P1/P2 figures), gate 3 (band met per task, with the blind upper bound beside it), gate 4 (metering coverage per provider; price table frozen), and what a successor criterion for a live Phase 2 or `module` arm inherits (`rubric`, `anchors` with `partial`, `calibration`, `models`, the amended package hashes).
- [ ] **Step 3: Failure branch** (only if Step A failed twice or the family did not qualify): the report states the measure as uncalibrated for family (a), lists the two options for the owner verbatim as options, not recommendations: (i) hidden acceptance primary, an explicit reversal of the 2026-10-15 evaluation policy; (ii) stop live structural search on family (a) and reconsider family (b). No live arm is selected.
- [ ] **Step 4: Run** `pytest -q -n 16 --dist=worksteal tests/experiments/` — PASS; **commit** — "docs(search): measurement calibration report and gate verdicts".

---
