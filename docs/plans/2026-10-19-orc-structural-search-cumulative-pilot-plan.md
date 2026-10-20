# ORC Structural Search Stage C1: Cumulative Whole-Program Campaign Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** proposed, unselected (2026-10-19); offline tasks need no allocation; every live campaign is its own owner budget decision; prerequisites: the measurement plan's Step A (and B/B2 for a qualified family), metering, a sealed split, the module condition's offline tasks.

**Goal:** Implement Stage C1 of the [cumulative campaigns design](../design/orc_structural_search_cumulative_campaigns.md#summary-and-scope) offline with scripted providers (persistent evidence store, campaign checkpoint/resume, results archive with the metered Pareto frontier beside a bounded reservoir, two parent policies at equal budget, diversity pressure with the revisit and futility rules, the successor loop under `module` with capped models, the cumulative budget readout and equal-budget campaign comparison, a versioned successor criterion), then stage a live pilot as owner-gated steps whose size is derived from a predeclared power estimate.

**Architecture:** One new module, `experiments/orc_structural_search/campaign.py`, owns the durable evidence store (append-only versioned JSONL records, one writer, rebuildable indexes, atomic checkpoint), the C1 identities, the breeding pool (bounded frontier subset plus bounded reservoir, the two parent policies), the diversity summaries, the revisit and futility rules and the receipt-union budget. `adaptive.py` gains the successor loop `run_campaign` (mode 3) beside its refusing historical `run_mode2`; `briefs.py` renders the structural summaries; `pareto_readout.py` gains the campaign endpoints and the equal-budget comparison; `qualification*.py` gain the V2 receipt the successor criterion needs. The driver, mutator sessions, evaluation launch, ledger, judging and the harness are reused unchanged. Nothing under `orchestrator/` changes; no population, score, policy or fitness enters it ([boundary compliance](../design/orc_structural_search_cumulative_campaigns.md#boundary-compliance)).

**Tech Stack:** Python 3.13 standard library (`json`, `os.replace`, `random`, `hashlib`, `statistics`); `experiments/compare` shims (bubblewrap), `pool.py`, `summarize.py`, `score_ref.orc` (rubric v2 from the measurement plan); tests with the scripted `claude`/`codex` executables, a scripted mutator and a scripted judge (`tests/experiments/orc_structural_search_support.py`, `test_orc_structural_search_three_arm.py`, `qualification_support.py`); no provider is called offline.

**Spec:** `docs/design/orc_structural_search_cumulative_campaigns.md` ([Identities](../design/orc_structural_search_cumulative_campaigns.md#identities), [Persistent Evidence Store](../design/orc_structural_search_cumulative_campaigns.md#persistent-evidence-store), [Campaign Protocol](../design/orc_structural_search_cumulative_campaigns.md#campaign-protocol), [Breeding Pool And Parent Policies](../design/orc_structural_search_cumulative_campaigns.md#breeding-pool-and-parent-policies), [Diversity Pressure And Revisits](../design/orc_structural_search_cumulative_campaigns.md#diversity-pressure-and-revisits), [Endpoints, Budget Accounting And Power](../design/orc_structural_search_cumulative_campaigns.md#endpoints-budget-accounting-and-power), [Estimates And Attribution](../design/orc_structural_search_cumulative_campaigns.md#estimates-and-attribution), [Staging And Gates](../design/orc_structural_search_cumulative_campaigns.md#staging-and-gates), [Verification](../design/orc_structural_search_cumulative_campaigns.md#verification)); `docs/design/orc_structural_search_driver.md` ("Objective, Selection And Local Observations": the Pareto objective, tolerances and `above_stub` floor; "Metering And Consumption": the price table and receipt mapping; "Records"; "Task Family And Evaluator": the calibration rule and the external qualification receipt); the [measurement plan](2026-10-19-orc-structural-search-measurement-plan.md) on `feat/structural-search-measurement` (rubric v2, four-role anchors with P1/P2/P3, `amends_5`, judges `claude-sonnet-5-5`/`gpt-5.6-terra`, the price table, the model cap in that branch's `AGENTS.md`); the [module decision](2026-10-19-orc-structural-search-module-rewrite-plan.md#gate-for-a-live-module-arm) gates 1–6; the [Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md) (spread, wall clock, calls, the three-arm convergence); the [roadmap](2026-10-18-orc-structural-search-roadmap.md) as amended for Phase 2 (C1).

## Global Constraints

- Binding decisions C1–C10 of the coordinator (2026-10-19) and the design above. Stage C1 has identities `candidate_id`, `campaign_id`, `trial_id`, `context_key` only; no `fragment_id`, `site_id` persistence, `invocation_id` or context schema; a campaign's context is frozen.
- Offline tasks (1–7) call no provider and need no allocation; sandboxed tests skip without bubblewrap as today; no test asserts prompt text. They start after `feat/structural-search-measurement` merges (its Task 1 delivered `scoring.fillers_per_batch`, `pool.rubric`, `pool.write_pool`; its Task 5 freezes the capped judges and seed copies this plan inherits). Until then no file under `experiments/` or `tests/` is edited (C10).
- Model cap (C4, the owner's 2026-10-19 amendment in that branch's `AGENTS.md`): every call in any C1 campaign resolves to `claude-sonnet-5-5` or `gpt-5.6-terra`; mutator `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --model gpt-5.6-terra --config model_reasoning_effort=high` behind the shims; `config.models = {"claude-sonnet-5-5": ["low", "medium", "high"], "gpt-5.6-terra": ["low", "medium", "high"]}`, `per_call_timeout_sec` 5400; judges `claude-sonnet-5-5` and `gpt-5.6-terra` at `high`; seeds are capped copies (coder Sonnet `medium`, diagnosis/reviewer Terra `high`); historical seeds, criteria, provider JSON and `score.orc` stay byte-identical; Fable refused everywhere.
- Objective: Pareto over (quality, metered deployed cost) with `final_choice.equivalence_tolerance` τ_q = 0.5 rubric points, `dominance_cost_tolerance` τ_c = 0.10, `quality_floor: {"kind": "above_stub"}`; cost is `pricing.cost` over the frozen `price_table`; a candidate without metered cost is off the frontier and reported; **no calls-only selection, no proxy fallback** (C7). Calls and wall clock are always reported beside cost.
- Breeding pool frozen in the criterion: frontier subset size 6 (the driver design's spread rule); reservoir capacity 4, admission `valued_non_frontier`, eviction `fifo`; exploration fraction 0.25 (with 4 episodes per generation, exactly one reservoir draw per generation, draw index 0); policies `frontier_only` and `mixture`; both campaigns use identical mutation facilities, horizon, budget, warm start and `run_seed`.
- Diversity: every brief carries skeleton-level descriptors of already evaluated or scheduled children (never scores, pool paths or evidence paths); revisit key `skeleton+policy` (a child whose `program_digest` equals an evaluated or scheduled candidate's, or whose skeleton hash equals one's while its set of distinct (provider, model, effort) policies is unchanged, is logged `revisit`, never evaluated; a policy-only change is a fresh child, per the design's revisit rule); futility `consecutive: 4` (four consecutive episodes that are revisits or rejections stop the campaign); no QD grid.
- Persistence: durable store root `S` (operator `--store`), outside every work root, evidence root, pools root, `/tmp`, `/dev/shm`, `/var/tmp` and the main checkout prefix, never in `COMPARE_HIDE`'s complement (it is masked from every episode like the evidence root); append-only `S/evidence.jsonl` with `schema: "campaign-evidence-v1"` rows; `S/candidates/<candidate_id>/` via `driver.archive`; `S/campaigns/<campaign_id>/checkpoint.json` written with `os.replace`; one writer process per store (`S/.lock`, `fcntl.flock`); dispositions supersede, nothing is deleted.
- Splits: adaptive = rung 2 `resume-projection-integrity` and rung 4 `pure-result-replay` (the measurement plan's amended packages); sealed = rung 1 `cf1-generic-unions` (reserved by the measurement plan; needs the same four-anchor and promoted-check amendment plus its own qualification before P4); validation = a qualified fourth package (rung 3 `adopted-attempt-lineage` after its third sample) when one exists, else the validation stage is skipped and disclosed. The sealed package path is a `--holdout` root of every episode and adaptive evaluation scan and appears in no brief.
- Every touched module ≤ 500 lines, every function ≤ cyclomatic complexity 12; splits only at existing responsibilities; commits with pathspecs, one per task; `pytest --collect-only` on new test modules; narrow selectors first, then `pytest -q -n 16 --dist=worksteal tests/experiments/` in tmux.
- Live roots: runtime `RT=/home/ollie/sc1-runtime` detached at the frozen implementation commit `I`; store `S=/home/ollie/sc1-store`; per campaign `W=/home/ollie/sc1-work/<campaign_id>`, `E=/home/ollie/sc1-evidence/<campaign_id>`, pools `P=/home/ollie/sc1-pools/<campaign_id>`; every earlier `ss*`, `ss3*`, `calib*`, `sc-*` root is read-only and passed as `--hide`/`--holdout`; solution hashes only via `--solution`.

## Review Focus

1. A resumed campaign must continue the interrupted one, not restart it: the same `run_seed` and scripted outcomes draw the same parents as an uninterrupted run, no trial is added by the resume, and the ingestion position advances (Task 4 `test_resume_continues_the_same_draws_and_adds_no_trial`).
2. Calls must never become the cost axis of a campaign frontier: a candidate whose receipts are incomplete stays off the frontier and is reported even when every call resolves to one (model, effort) pair (Task 2 `test_campaign_frontier_refuses_the_calls_proxy_and_keeps_unmetered_candidates_off`).
3. The brief's structural summaries must carry structure only: no judged value, hidden fraction, pool or evidence path, other candidate's cost or sealed outcome reaches `EPISODE.md` (Task 3 `test_structural_summaries_carry_no_scores_paths_or_outcomes`).
4. Reservoir membership must convey nothing: a reservoir member never enters the frontier, the endpoints or the final choice while it is dominated, even as the parent of a frontier entry (Task 4 `test_stepping_stone_reaches_c_only_through_the_mixture_and_b_stays_off_the_frontier`).
5. The sealed split must open once and never reach a mutator: a second `open_sealed` refuses, the sealed package path is in no brief or adaptive evaluation, and finalist assessment refuses before the analysis-freeze disposition exists (Task 5 `test_sealed_split_opens_once_after_freeze_and_never_reaches_an_episode`).

## Decisions

1. **One new module, `campaign.py`; the loop lives in `adaptive.py`.** `adaptive.py` (353 lines) keeps its refusing `run_mode2` and historical helpers and gains `run_campaign` (about 140 lines). If it would exceed 500 lines, `validate_finalists` and `mode2_readout` (read-only interpreters of frozen Phase 2 evidence) move to `scoring_phase2.py` (294 lines), a split at an existing responsibility. Reason: C6's minimal footprint and the module plan's size rule.
2. **Store records are five kinds** on one JSONL file, each `{"schema": "campaign-evidence-v1", "kind": ..., "seq": n, ...}`: `campaign` (header: `campaign_id`, `context_key`, `policy`, `run_seed`, `criterion_sha256`, roots), `subject` (`candidate_id`, lineage parent, skeleton, behaviour descriptor), `trial` (`trial_id`, `campaign_id`, `evaluation_id`, `attempt`, `context_key`, `candidate_id`, task, replicate, split, generation, outcome, calls, wall clock, `receipt_usage`, `records_dir`), `assessment` (`trial_id`, pool results path, judge totals, value, hidden, `criterion_sha256`), `disposition` (`target_kind` trial or campaign, `target_id`, `kind` in `contaminated | invalidated | superseded | frozen | sealed_opened`, reason). Reason: C6 names subject/trial/assessment/disposition; the header and the campaign-level dispositions are the least that make freeze and sealed-open auditable.
3. **Identities.** `context_key = "ctx1:" + sha256` over the sorted tuple (adaptive task package sha256s, criterion sha256, runtime commit, `EVALUATOR_VERSION`, episode and evaluation wall clocks, replicates); `trial_id = "trial:" + sha256(campaign_id, evaluation_id)` so a resumed incident (same evaluation id) is the same trial and a fresh run in another campaign is a new trial; `campaign_id` is the operator's label (`[a-z0-9-]{1,40}`), unique in the store. Cross-campaign pooling of whole-program evidence requires equal `context_key` (C1).
4. **Estimates** are empirical: per candidate and context, per-task primary means (`scoring.primary_value`, failure-inclusive) over non-disposed trials, quality = equal-weight mean over the adaptive tasks with every task observed (`support: every_adaptive_task`), cost = mean `pricing.cost` per trial (any unavailable → unavailable); `n_trials`, `n_tasks`, excluded and disposed counts reported; no trials → `unobserved`, never a score (A2).
5. **Quality floor** = the mean stub-anchor total per task over the campaign's own adaptive pools (`pareto_readout.stub_floor` over `read_pool` results), recomputed at every checkpoint; missing stub evidence → floor unavailable → no frontier that generation.
6. **Reservoir and policies.** Admission: valued, uncontaminated, non-frontier candidates (quality numeric under the failure rule, floor irrelevant: "neutral or worse" is the point); eviction FIFO by admission generation when over capacity 4. `frontier_only`: every draw uniform over the bounded frontier; `mixture`: draw index 0 of each generation uniform over the reservoir (empty → frontier draw, logged `reservoir_empty`), the rest uniform over the frontier. The fraction is positional, not Bernoulli, so both campaigns spend exactly the same draws. Reservoir membership is never reported as a result.
7. **Revisit key is the skeleton plus the policy set** (C2, the design's rule). `record_normalization.skeleton_hash` maps `:model`/`:effort` to `#lit`, so a policy-only rewrite hashes equal to its parent; it is a fresh child when its set of distinct (provider, model, effort) policies differs (model selection is a search dimension under the Pareto objective), and a revisit otherwise. A prompt-only rewrite under `module` still hashes equal and is a revisit in C1: a disclosed ceiling, named in the criterion (`revisit_key: "skeleton+policy"`) so a later criterion can widen the key without a code change.
8. **Warm start is shared and separately costed.** Generation 0 (capped `direct` and `implement_check_diagnose_repair`, 2 replicates per adaptive task) runs once into the store under the common `context_key`; both campaigns ingest the same trials (identical initial evidence, A4); its acquisition cost is recorded as `warm_start`, never inside a campaign's cumulative budget.
9. **Budget is a union of receipts** keyed by (`records_dir`, `call_id`) over every episode, evaluation (superseded quota attempts included, as in Phase 1) and judge row of the campaign; priced cost is `unavailable` when any receipt is, calls and wall clock always; unpriced work (operator adjudications, reruns) is a counted list, not a number.
10. **Endpoints** per checkpoint `g`: best frontier quality under deployed-cost ceilings {1, 2, 4} × `c_ref` and cheapest frontier cost meeting quality targets `q_ref` + {0.5, 1.0, 2.0}, where `c_ref`, `q_ref` are the reference's warm-start figures (the rule is frozen; the resolved values are recorded in the ledger after P0); the equal-budget comparison reads each campaign at the last checkpoint whose cumulative metered cost does not exceed the common budget B* = min over campaigns of the final cumulative cost, and at B*/2. Final independent assessment: the sealed-split quality of each campaign's final choice and the reference.
11. **Two splits by default.** Selection and the final choice use adaptive evidence; the sealed split (rung 1) is the independent assessment, opened once after the `frozen` disposition. The validation stage runs only with a qualified fourth package; without one the report says so. Reason: no qualified fourth package exists today and authoring one is its own cost.
12. **Power first, then size** (C3): the Power And Budget section shows the affordable design cannot detect a plausible campaign-level effect; the live steps therefore stage a descriptive pilot (one campaign per policy) whose predeclared outputs are the variance estimates a powered study needs. No policy claim is preregistered.

## Feasibility And Existing Boundaries (verified on `main` at `ac58e0ba`; branch facts named)

- `driver.archive(root, evidence_root, runtime)` copies a candidate to `<root>/candidates/<candidate_id>/` and `check_archived` refuses tampering (`driver.py:87-103`): the durable store reuses both with `S` as the root. `records.append_record`/`read_records` are the JSONL conventions (`records.py:19-31`); `ledger.reserve`/`settle` key entries by kind and key (`ledger.py:44-65`); `quota.job_key` is (candidate, task, replicate, split, generation) (`quota.py:145-148`), so `generation` and `split` on evaluation rows already distinguish campaign jobs within one evidence root; two campaigns in separate roots can produce equal `evaluation_id`s, which is why `trial_id` includes `campaign_id`.
- `run_episode(..., feedback: Mapping)` passes `feedback` to `briefs.episode_brief`, and `briefs.feedback_text` renders only the `mean_value` and `runs` keys (`briefs.py:103-111`); the structural summaries ride on a new `feedback["evaluated_structures"]` key rendered there, so `driver.py` (482 lines) is untouched. `test_the_i2_brief_carries_the_site_and_feedback_but_no_hidden_figures_or_evidence_path` is the precedent for Review Focus 3.
- `adaptive.evaluate_and_judge(jobs, generation, tasks, replicates, launch, judge, include)` reserves against the cap (`check_budget`, `planned_judged`), evaluates through `driver.evaluate_all` and judges through `judging.judge_generation` with per-generation pools (`adaptive.py:170-184`); on the measurement branch `planned_judged` sizes batches with `scoring.fillers_per_batch(task, rubric)` (10 − 4 anchors − 1 reference = 5 fillers). `check_pools_root` and `check_splits` are reusable; `mode1.archive_seed`, `seed_config`, `catalog_jobs` build warm-start jobs.
- `pareto.frontier(rows, tau_q, tau_c)` takes rows with `quality`, `cost`, `above_floor`, `candidate_id` (`pareto.py:18-22`); `pareto_readout.rules`, `stub_floor`, `dominating_children`, `episode_change_class`, `arm_endpoints` are reusable per campaign (`pareto_readout.py:15-36, 131-186`); `report` applies the calls proxy only through `homogeneous(...)` (`pareto_readout.py:200-203`), which the campaign path must not call.
- `pricing.cost(row, table)` needs `receipt_usage` with one `call_id` per call and complete coverage (`pricing.py:91-110`); `metering.receipts` names `call_id` as the shim's `calls/<n>` directory name (`metering.py:242`), unique only within a records directory, hence the (`records_dir`, `call_id`) union key.
- `readout.diversity`/`revisit_count` already count skeleton revisits (`readout.py:43-62`); `record_normalization.control_heads` gives the control-head counts; evaluation rows carry `provider_calls`, `realized_perform_sites`, `provider_allocation` and `allocation_changed` (`driver.py:141-148`, `site_evidence.evaluation_comparison`), the behaviour descriptor's inputs.
- `selection.final_choice(rows, criterion=...)` is the frozen deployment rule (`selection.py:8-30`); it needs `is_reference`, `mean_cost`, `validation_success`, `provider_calls` rows.
- `qualification.validate` admits only `orc-structural-qualification-v1` (`qualification.py:66`), whose measure part binds `score.orc` and two controls; the measurement plan defers V2 "until a later quality study is selected": this plan is that study, so Task 6 adds V2 (schema `orc-structural-qualification-v2`: rubric v2 with the disclosed reference, four-role anchors with P1/P2/P3 and spread recomputed from the judge-calibration pools, `amends_5` family evidence recomputed with `prepare.blockers` as V1 does). V1 stays untouched for the historical criteria.
- `three_arm.check_run` compares a run configuration's `criterion_sha256`, `models`, `per_call_timeout_sec`, wall clocks and mutator with the criterion (`three_arm.py:205-220`): the pattern for `adaptive.check_campaign`.
- Metering offline: `test_orc_structural_search_module_execution.py::test_episode_records_identified_native_path_even_without_complete_usage` monkeypatches `metering.receipts`; the campaign fixtures use the same seam to synthesize complete receipts (one Sonnet usage row per shim call) so the frontier has a metered cost axis without a provider.
- Phase 1 figures used below: pooled within-arm SD 0.93 (rpi) and 1.20 (prr) rubric points with two replicates; per-evaluation wall clock 908–1,072 s on the three-arm paid subset and 1,754–4,718 s on the Phase 1 catalog; one realized call per evaluation at the parent's structure, planned maximum 3 for the check-gated repair loop; 18 of 18 three-arm children converged on one idea (the reason for C2).

## Power And Budget (C3)

**Outcome and formula.** The campaign-level outcome is Q_c, the best supported quality under a fixed deployed-cost ceiling at the common cumulative budget, measured on the independent split. The policy effect is Δ = mean(Q_M) − mean(Q_F) over R replicate campaigns per policy. For a two-sided α = 0.05, power 0.8 two-sample comparison:

R per policy = 2 · (z₀.₉₇₅ + z₀.₈)² · s_c² / δ² = 15.7 · (s_c / δ)²,

where s_c is the SD of Q_c across replicate campaigns of one policy and δ the minimal detectable effect.

**Assumptions (from Phase 1).**

| Quantity | Value used | Source |
| --- | --- | --- |
| Per-evaluation SD σ | 1.1 rubric points (0–8) | pooled within-arm SD 0.93 and 1.20; rubric v2's SD is unmeasured and assumed equal |
| Independent-split replicates per finalist | 1 task × 3 replicates | sealed rung 1, the module decision's "at least three replicates" |
| Measurement component of s_c | σ/√3 = 0.64 | |
| Search component s_s | unknown; bracketed 0 to σ | Phase 1's spread of arm means (SD 0.40 on rpi, 0.68 on prr) lies below the noise of a two-replicate mean (0.78), so Phase 1 cannot estimate s_s |
| s_c | 0.64 (s_s = 0) to 1.27 (s_s = σ) | √(0.64² + s_s²) |
| Wall clock per evaluation | 25 min mean (15–20 min at one call; up to 80 min for 4–6 call structures) | three-arm subset 908–1,072 s; Phase 1 catalog 1,754–4,718 s |
| Calls per evaluation | 1 at the parent's structure, planned maximum 3, 1.5 realized (gate 3 makes the check fail sometimes) | Phase 1 and the measurement plan's gate 3 |
| Episode | 1 call, 10 min (three-arm 80–153 s under topology-only; `module` rewrites repair longer) | three-arm readout |
| Judge | 1 call per batch per judge, 5 candidate evaluations per batch | rubric v2 batch: reference + 4 anchors + 5 fillers |
| Acceptance 0.8, revisits 0.15 | 0.68 fresh evaluable children per episode | three-arm 1.0 accepted; Phase 1 revisit 0.17 |

**Minimal detectable effect: δ = 1.0 rubric point.** Rationale: two equivalence tolerances (τ_q = 0.5), so a one-point gain changes the deployment rule's outcome; it is below Phase 1's largest observed arm gaps (1.13 and 2.00) and half the P3 mutant margin (2) the calibrated judge must resolve. Required replicates at δ = 1: R = 15.7 · (0.64/1)² = 7 per policy at the optimistic bracket, 15.7 · (1.27/1)² = 26 at the pessimistic one, so 14 to 52 campaigns (about 1,000 to 3,500 calls at the per-campaign cost below). At δ = 2: 2 to 7 per policy (4 to 14 campaigns, about 300 to 1,000 calls), and only the optimistic end is affordable, on an assumption (s_s ≈ 0) nothing has measured.

**Honest conclusion.** The affordable design (one campaign per policy) has no degrees of freedom for a policy test and would detect only δ ≈ s_c · √15.7 ≈ 2.5 to 5 points, implausible on this rubric. Stage C1 therefore runs as a **descriptive pilot**: R = 1 per policy, G = 4 generations, E = 4 episodes per generation, 2 adaptive tasks, 1 replicate per adaptive evaluation, 3 sealed replicates per finalist. Its predeclared outputs are the first estimates of s_c's components (checkpoint-to-checkpoint and across the two campaigns), the realized acceptance, revisit, futility and reservoir-draw rates under `module` with capped models, the per-episode and per-evaluation cost under the price table, and the live mechanics of store, checkpoint and budget union. The policy difference is reported with its measurement-only interval (±1.96 · 0.64 · √2 ≈ ±1.8 points, search variance excluded) and no claim; a null is not evidence of no effect; the horizon is not extended after seeing outcomes. A powered follow-up is sized from the pilot's s_c, as its own owner decision. Common random numbers (one `run_seed` for both campaigns) and the shared warm start reduce, not remove, the between-campaign variance.

**Planned calls and hard cap** (charged as in Phase 1; immediate zero-work refusals listed, not silently subtracted):

| Step | Calls planned | Derivation | Cap |
| --- | --- | --- | --- |
| P0 warm start (shared) | 14 | 2 seeds × 2 tasks × 2 replicates = 8 evaluations at 1 and 1.5 calls → 10; judges 2 tasks × 1 batch × 2 → 4 | 20 |
| P1 campaign `frontier_only` | 65 | 16 episodes → 16; 16 × 0.68 ≈ 11 children × 2 tasks = 22 evaluations × 1.5 → 33; judges 4 generations × 2 tasks × 1 batch × 2 → 16 | 80 |
| P2 campaign `mixture` | 65 | as P1 | 80 |
| P3 validation (conditional on a qualified fourth package) | 29 | 5 candidates × 3 replicates = 15 evaluations × 1.5 → 23; judges 3 batches × 2 → 6 | 36 |
| P4 sealed assessment | 18 | 3 candidates × 3 replicates = 9 evaluations × 1.5 → 14; judges 2 batches × 2 → 4 | 22 |
| **Total** | **162 (191 with P3)** | | **202 (238 with P3)** |

Caps carry slack for reservations in flight (concurrency 4 × (planned 3 − realized 1.5) = 6 calls) and quota relaunches. Wall clock at concurrency 4, episodes one at a time: P0 ≈ 1.5 h; each campaign ≈ 7 h (episodes 2.7 h, evaluations 2.3 h, judging and hidden-acceptance passes 2 h); P4 ≈ 2 h; about 18 h of generation time, 1–2 days with quota pauses (Phase 1: two pauses, 3.6 h, per 160 calls). Each step is a separate owner approval; the ledger records the approval, the Codex window reading and the quota policy before any launch.

---

### Task 1: Persistent evidence store and campaign checkpoint (C6)

**Files:**
- Create: `experiments/orc_structural_search/campaign.py`
- Test: `tests/experiments/test_orc_structural_search_campaign.py`

**Interfaces (produces):**
- `context_key(criterion: Mapping, *, tasks: Sequence[Path], runtime_commit: str, evaluator_version: str, config: ExperimentConfig, timeout_sec: float, replicates: int) -> str`; `trial_id(campaign_id: str, evaluation_id: str) -> str`; `check_campaign_id(label: str) -> str`.
- `open_store(root: Path, *, writer: bool) -> Store` (refuses a root inside a work, evidence or pools root or the main prefix; takes `S/.lock` when `writer`; validates every line's `schema`, `kind`, `seq` and required fields, refusing a malformed file). `Store.append(record) -> int` (assigns `seq`); `Store.rows(kind=None)`; `Store.index()` rebuilds `{trial_id: trial}`, `{trial_id: [assessment]}`, `{target_id: [disposition]}` from the rows, never cached across appends.
- `ingest(store: Store, campaign_id: str, context: str, evidence_root: Path, pools: Sequence[Path]) -> dict`: one `trial` per evaluation row (`records.read_records`, every attempt, not `latest_evaluations`), one `assessment` per `scoring.join_scores` row, idempotent by `trial_id` and (`trial_id`, results path); a quota-superseded attempt gets a `superseded` disposition; returns counts and the new ingestion position (line count of `E/log.jsonl`).
- `register_subject(store, candidate_root: Path, *, runtime: Path, parent: str | None, skeleton: str, descriptor: Mapping) -> str` (archives into `S/candidates/` through `driver.archive`).
- `dispose(store, *, target_kind: str, target_id: str, kind: str, reason: str) -> int`.
- `evidence(store, candidate_id: str, context: str, *, tasks: Sequence[str], price_table: Mapping) -> dict`: `{"status": "observed" | "unobserved", "quality", "cost", "per_task": {task: {"mean", "n"}}, "n_trials", "excluded", "disposed", "trial_ids"}` per Decision 4.
- `write_checkpoint(store, campaign_id, state: Mapping) -> Path` (`campaign-checkpoint-v1`, temp file plus `os.replace`); `read_checkpoint(store, campaign_id) -> dict | None` (refuses a checkpoint whose `campaign_id`, `context_key` or `criterion_sha256` disagree with the header record).

- [ ] **Step 1: Write the failing tests**:

```python
def test_store_refuses_a_malformed_line_and_an_unknown_kind(tmp_path)
def test_ingest_is_idempotent_across_processes_and_a_rerun_adds_a_trial(tmp_path)
    # process A ingests E1; process B reopens S and re-ingests E1: trial count unchanged; a fresh evaluation of the
    # same candidate/task/replicate in campaign c2 adds a trial with another trial_id
def test_evidence_pools_equal_context_and_partitions_a_changed_context(tmp_path)
def test_evidence_is_unobserved_without_trials_and_excludes_disposed_ones(tmp_path)
    # a contaminated disposition removes the trial from quality and cost; the line stays in evidence.jsonl
def test_cost_is_unavailable_when_any_trial_receipt_is_incomplete(tmp_path)
def test_checkpoint_is_atomic_and_rejects_another_campaigns_state(tmp_path)
    # a crash between temp write and replace leaves the previous checkpoint readable
def test_second_writer_is_refused_while_the_lock_is_held(tmp_path)
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_campaign.py` — expected: ImportError.
- [ ] **Step 3: Implement** the interfaces above in `campaign.py` (store, identities, ingest, evidence, checkpoint only; the rest of the module comes in Tasks 2–3 and 5).
- [ ] **Step 4: Run** the module's tests and `pytest --collect-only` on it — expected: PASS.
- [ ] **Step 5: Commit** `feat(search): campaign evidence store, identities, idempotent ingestion, dispositions and atomic checkpoint`.

### Task 2: Results archive, metered frontier, reservoir and the two parent policies (A3, C7)

**Files:**
- Modify: `experiments/orc_structural_search/campaign.py`
- Test: `tests/experiments/test_orc_structural_search_campaign.py`

**Interfaces (produces):**
- `candidate_table(store, context: str, *, candidates: Collection[str], tasks, price_table, floor: float | str) -> dict[str, dict]`: `pareto.frontier`-shaped rows (`candidate_id`, `quality`, `cost`, `above_floor`, `reason`, `support`, `provider_calls`, `wall_clock_sec`) from `evidence`; cost is metered or unavailable, never calls.
- `quality_floor(pools: Sequence[Mapping], criterion: Mapping) -> float | str` (delegates to `pareto_readout.stub_floor`).
- `bounded_frontier(table: Mapping, *, size: int, tau_q: float, tau_c: float) -> list[str]`: `pareto.frontier` then the design's spread rule (keep the cheapest and the highest-quality members, then those with the largest cost gaps to their neighbours).
- `reservoir_update(reservoir: Sequence[Mapping], table: Mapping, frontier: Collection[str], *, generation: int, capacity: int, contaminated: Collection[str]) -> list[dict]` (`{candidate_id, admitted_generation}`; admission and FIFO eviction per Decision 6; a member that becomes a frontier member leaves the reservoir).
- `select_parent(policy: str, *, draw: int, episodes: int, fraction: float, frontier: Sequence[str], reservoir: Sequence[Mapping], rng: random.Random) -> tuple[str, str]` → (candidate id, source `frontier | reservoir | reservoir_empty`).

- [ ] **Step 1: Write the failing tests**:

```python
def test_candidate_table_uses_metered_cost_and_leaves_unmetered_candidates_off_the_frontier(tmp_path)
def test_campaign_frontier_refuses_the_calls_proxy_and_keeps_unmetered_candidates_off(tmp_path)
    # every call resolves to one (model, effort) pair, one candidate lacks a receipt: it is off the frontier, reason
    # "cost_unavailable"; no provider_calls axis is offered anywhere in the result
def test_bounded_frontier_keeps_cheapest_highest_and_largest_gaps()
def test_frontier_is_independent_of_the_order_candidates_arrive_in()
def test_a_child_within_both_tolerances_neither_dominates_nor_is_dominated()
def test_reservoir_admits_valued_non_frontier_candidates_and_evicts_fifo_at_capacity()
def test_reservoir_member_promoted_to_the_frontier_leaves_the_reservoir()
def test_frontier_only_never_draws_from_the_reservoir_and_mixture_draws_index_zero_from_it()
    # same rng seed, same inputs: frontier_only draws equal mixture's draws 1..3; draw 0 differs; empty reservoir → frontier, source "reservoir_empty"
```

- [ ] **Step 2: Run** the selectors — expected: FAIL.
- [ ] **Step 3: Implement**; reuse `pareto.dominates/frontier`, `pareto_readout.rules/stub_floor`.
- [ ] **Step 4: Run** the module's tests — expected: PASS; `wc -l campaign.py` ≤ 400 at this point.
- [ ] **Step 5: Commit** `feat(search): campaign results archive with the metered frontier, bounded reservoir and the two parent policies`.

### Task 3: Diversity pressure, the revisit rule and the futility rule (C2)

**Files:**
- Modify: `experiments/orc_structural_search/campaign.py`, `experiments/orc_structural_search/briefs.py`
- Test: `tests/experiments/test_orc_structural_search_campaign.py`, `tests/experiments/test_orc_structural_search_briefs.py`

**Interfaces (produces):**
- `structural_summary(candidate_root: Path, config: ExperimentConfig, *, runtime: Path) -> dict`: `{"control_heads": {...}, "provider_roles": [...], "call_sites": n, "loop": bool, "private_definitions": n}` from authored source (`record_normalization.control_heads`, `metrics.allocation`), never from evaluator artifacts.
- `behaviour_descriptor(evaluation_rows: Sequence[Mapping], episode_row: Mapping | None) -> dict`: `{"realized_provider_calls": [...], "distinct_provider_roles": n, "loop_present": bool, "allocation_changed": bool | "unavailable"}` recorded on the `subject` record (reporting only; no grid).
- `evaluated_structures(store, context: str, *, scheduled: Sequence[Mapping]) -> list[dict]`: the summaries of every evaluated or scheduled candidate, ordered by candidate id, capped at 12 entries (the most recent), for the brief's `feedback["evaluated_structures"]`.
- `briefs.feedback_text` renders `evaluated_structures` as a "Structures already tried" section with the instruction that the proposal must differ structurally from each; every other key is still dropped.
- `is_revisit(skeleton: str, program_digest: str | None, policies: frozenset, *, known: Mapping[str, frozenset], known_digests: Collection[str]) -> bool` (`known` maps each evaluated or scheduled skeleton to its policy set; equal digest, or equal skeleton with an equal policy set, is a revisit); `futility(outcomes: Sequence[str], *, consecutive: int) -> bool` over the campaign's episode outcome sequence (`accepted_fresh | revisit | rejected | exhausted | incident`; only `revisit` and `rejected` count, an incident resets nothing and counts nothing).

- [ ] **Step 1: Write the failing tests**:

```python
def test_structural_summary_reads_authored_source_only(world)
def test_structural_summaries_carry_no_scores_paths_or_outcomes(world)
    # feedback with evaluated_structures plus stray keys (value, hidden, pool, evidence_root, sealed): the brief
    # contains each structure's heads and roles, none of the stray values, no path under E, S or P
def test_a_child_with_a_known_digest_or_a_known_skeleton_and_policy_set_is_a_revisit_and_a_policy_only_change_is_not()
def test_futility_fires_on_four_consecutive_revisits_or_rejections_and_not_on_three()
def test_behaviour_descriptor_reports_realized_calls_roles_loop_and_allocation_change()
```

- [ ] **Step 2: Run** — expected: FAIL. **Step 3: Implement.** **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_campaign.py tests/experiments/test_orc_structural_search_briefs.py` — expected: PASS.
- [ ] **Step 5: Commit** `feat(search): structural summaries in the brief, the revisit rule, the futility rule and the behaviour descriptor`.

### Task 4: The successor loop under `module` with capped models, checkpoint/resume, the stepping-stone and diversity fixtures (C4, C6)

**Files:**
- Modify: `experiments/orc_structural_search/adaptive.py` (`check_campaign`, `warm_start`, `campaign_generation`, `run_campaign`; `run_mode2` keeps refusing), `experiments/orc_structural_search/campaign.py` (CLI `run | resume | readout`)
- Create: `experiments/orc_structural_search/seeds/capped/` (capped copies of `direct.orc` and `implement_check_diagnose_repair.orc` with `common.orc`, `providers.json`, `commands.json`, `dev_check.py`) unless the measurement plan's capped seed copy already exists, in which case reuse it and add only `direct.orc`
- Modify: `tests/experiments/orc_structural_search_support.py` (`MUTATOR_STEPPING_STONE`, `MUTATOR_SAME_IDEA`, `synthetic_receipts`)
- Test: `tests/experiments/test_orc_structural_search_campaign_loop.py`

**Interfaces:**
- `adaptive.check_campaign(config_path, criterion: Path, *, agent_cmd, timeout_sec, policy: str) -> dict`: as `three_arm.check_run` plus `policy in criterion["policies"]`, `config.condition == "module"`, `config.models == criterion["models"]`, every model in the criterion's `model_policy.admitted`, the mutator argv's `--model` admitted, `purpose == "quality"`, and `qualification.validate(..., operation="launch")` under V2 (Task 6).
- `adaptive.warm_start(store, criterion, config_path, *, seeds, adaptive_tasks, launch, judge) -> dict`: `mode1.catalog_jobs` on the capped seeds, `evaluate_and_judge(..., generation=0)`, `ingest` with `campaign_id="warm-start"`, cost recorded as `warm_start`; refuses when the store already holds a warm start of the same context (reuse it instead).
- `adaptive.campaign_generation(n, state, config, *, store, criterion, rng, adaptive_tasks, launch, judge) -> dict`: per episode `select_parent` → `run_episode(..., mode="campaign", feedback={..., "evaluated_structures": ...}, generation=n, run_seed=..., fields={"campaign_id", "policy", "parent_source"})`; an accepted child is `is_revisit`-checked against the store and the generation's scheduled children (a revisit is logged `{"kind": "revisit", ...}` and skipped); fresh children are registered, evaluated once per adaptive task and judged (`evaluate_and_judge`), ingested; the floor, table, frontier and reservoir are recomputed from the store; the checkpoint is written; the futility rule is evaluated over the campaign's episode outcomes.
- `adaptive.run_campaign(config_path, *, criterion, campaign_id, policy, store, seeds, adaptive_tasks, sealed_task, generations, episodes_per_generation, run_seed, work_root, evidence_root, pools_root, agent_cmd, runtime, env, timeout_sec, solutions, call_cap, concurrency, judges, hide=(), continue_run=False, scorer=None) -> dict`: `check_campaign`, `check_roots`, `check_pools_root`, the store outside all three roots and in `hide`; fresh: write the `campaign` header, restore nothing; `continue_run`: `read_checkpoint`, `random.Random().setstate`, re-`ingest` from the ingestion position, resume at the next generation; the sealed task is a `holdout` of every scan and never a task of any job; stops on horizon, futility, `CallCapExceeded`, `QuotaExhausted` or a second judge incident, each recorded in the checkpoint's `stopped` field; writes `E/readout.json` (per-generation trajectory and the diversity figures).
- `MUTATOR_STEPPING_STONE`: from a parent without the `helper-b` marker writes B (a private `defproc helper-b` making a second coder call; same quality under the scripted judge, twice the metered cost); from B writes C (one call, an `if` on the check report; a third skeleton; rated 7). `MUTATOR_SAME_IDEA`: writes the first child's skeleton unless the brief's "Structures already tried" lists it, then a second skeleton; a `--deaf` variant ignores the brief. `synthetic_receipts(monkeypatch)`: `metering.receipts` returns one complete Sonnet usage row per shim call.

- [ ] **Step 1: Write the failing tests** (fixtures `sandboxed`, `world`, `install`, `add_anchors` (four roles plus the reference per the measurement branch), `scripted_judge` extended to rate C 7, B and A 5, anchors upstream 8, partial 5, mutant 5, stub 0; a test-constructed criterion from Task 6's builder):

```python
def test_check_campaign_refuses_an_unadmitted_model_a_legacy_condition_and_an_unknown_policy(world)
def test_warm_start_runs_once_per_context_and_both_campaigns_ingest_the_same_trials(sandboxed, world)
def test_stepping_stone_reaches_c_only_through_the_mixture_and_b_stays_off_the_frontier(sandboxed, world)
    # G=2, E=2, same run_seed: frontier_only's final frontier == {A}, C never evaluated; mixture's frontier ⊇ {C},
    # C's parent is B, B's parent_source is "reservoir", B is in no frontier and no endpoint
def test_same_idea_children_are_revisits_that_are_logged_not_evaluated_and_futility_stops_the_deaf_mutator(sandboxed, world)
    # the brief-reading mutator yields two skeletons; the deaf one yields four consecutive revisits and the checkpoint reads stopped: "futility"
def test_resume_continues_the_same_draws_and_adds_no_trial(sandboxed, world)
    # run G=1, resume with G=2: parents and trial ids equal an uninterrupted G=2 run; ingestion_position advanced
def test_sealed_task_is_a_holdout_of_every_scan_and_in_no_brief_or_job(sandboxed, world)
def test_cap_refusal_leaves_the_log_checkpoint_and_store_consistent(sandboxed, world)
def test_run_mode2_still_refuses_fresh_adaptive_work(tmp_path)   # unchanged behaviour
```

- [ ] **Step 2: Run** `pytest -q tests/experiments/test_orc_structural_search_campaign_loop.py` — expected: FAIL.
- [ ] **Step 3: Implement**; verify the mutator argv passes the capped guard with the scripted CLIs; `wc -l adaptive.py` ≤ 500 or apply Decision 1's split.
- [ ] **Step 4: Run** the module's tests, `test_orc_structural_search_adaptive.py`, `--collect-only`, then `pytest -q -n 16 --dist=worksteal tests/experiments/` in tmux — expected: PASS.
- [ ] **Step 5: Commit** `feat(search): cumulative campaign loop under module with capped models, warm start, checkpoint/resume, revisits and futility`.

### Task 5: Cumulative budget, endpoints and the equal-budget campaign comparison (A4)

**Files:**
- Modify: `experiments/orc_structural_search/campaign.py` (`budget_union`, `open_sealed`, `freeze`), `experiments/orc_structural_search/pareto_readout.py` (`campaign_endpoints`, `compare_campaigns`)
- Test: `tests/experiments/test_orc_structural_search_campaign_readout.py`

**Interfaces (produces):**
- `campaign.budget_union(rows: Sequence[Mapping], judge_pools: Sequence[Path], price_table) -> dict`: `{"calls", "wall_clock_sec", "metered_cost" | "unavailable", "receipts": n, "unpriced_work": [...], "by_kind": {"episode", "evaluation", "judge"}}`, each receipt counted once by (`records_dir`, `call_id`); superseded attempts included; warm start excluded and reported beside as `warm_start`.
- `campaign.freeze(store, campaign_ids, reason) -> int` (the `frozen` disposition on each campaign; refuses when a campaign has no final checkpoint); `campaign.open_sealed(store, campaign_ids, sealed_task) -> int` (requires `frozen`, refuses a second opening: `sealed_opened` disposition).
- `pareto_readout.campaign_endpoints(trajectory: Sequence[Mapping], *, ceilings, targets) -> list[dict]` per checkpoint: cumulative budget, `best_quality_under` per ceiling, `cheapest_meeting` per target, frontier ids, improvements and frontier entries per completed episode (`dominating_children` against each child's parent), diversity, reservoir draws and the frontier entries whose parent came from the reservoir, lineage depth.
- `pareto_readout.compare_campaigns(campaigns: Mapping[str, Sequence[Mapping]], *, criterion) -> dict`: B* and B*/2 cuts, per campaign the checkpoint read at each cut, the endpoint table, and `final_assessment` from the sealed pool when `sealed_opened` exists (`selection.final_choice` per campaign over adaptive evidence with the reference; the sealed quality of each choice and the reference).
- `campaign.py` CLI `readout --store S --criterion C --campaign ID ... [--sealed-results R]` printing the comparison.

- [ ] **Step 1: Write the failing tests**:

```python
def test_budget_union_counts_an_overlapping_receipt_once_and_includes_superseded_attempts()
def test_budget_cost_is_unavailable_with_a_missing_receipt_while_calls_and_wall_clock_remain()
def test_warm_start_cost_is_reported_beside_not_inside_the_campaign_budget()
def test_endpoints_read_best_quality_under_ceilings_and_cheapest_meeting_targets_per_checkpoint()
def test_equal_budget_comparison_reads_each_campaign_at_the_common_budget_and_half_of_it()
def test_sealed_split_opens_once_after_freeze_and_never_reaches_an_episode(tmp_path)
    # open_sealed before freeze refuses; after freeze succeeds once; a second call refuses; the finalist stage
    # refuses without sealed_opened
def test_reservoir_member_never_appears_in_endpoints_or_final_choice()
```

- [ ] **Step 2: Run** — expected: FAIL. **Step 3: Implement.** **Step 4: Run** the module's tests and `test_orc_structural_search_pareto_readout.py` — expected: PASS; `wc -l pareto_readout.py` ≤ 500.
- [ ] **Step 5: Commit** `feat(search): cumulative budget union, campaign endpoints, equal-budget comparison and the sealed-once rule`.

### Task 6: The successor criterion (versioned) and qualification V2

**Files:**
- Modify: `experiments/orc_structural_search/qualification.py`, `qualification_measure.py`, `qualification_family.py` (schema `orc-structural-qualification-v2`), `tests/experiments/qualification_support.py` (`campaign_criterion(root, ...)` builder, `qualified_v2(...)`)
- Test: `tests/experiments/test_orc_structural_search_qualification.py`, `tests/experiments/test_orc_structural_search_campaign.py` (criterion shape)

**Interfaces:**
- Criterion `criteria/cumulative_c1.json` (written only at the live freeze `F`, Task 8; tests build it in temporary directories): `purpose: "quality"`, `experiment`, `plan`, `tasks` (adaptive paths), `sealed_task`, `validation_task | null`, `base_commits`, `judges`, `judge_bindings`, `rubric` (the measurement criterion's mapping with the reference), `anchors` (four roles per package), `calibration` (`margin` 4, `mutant_margin` 2, `error_rate` 0, `anchor_spread_limit` 2), `qualification: {file, sha256}` (V2 receipt), `measurement` (inherited identity block), `price_table` (inherited), `models`, `per_call_timeout_sec`, `model_policy: {"admitted": ["claude-sonnet-5-5", "gpt-5.6-terra"], "mutator": "<argv>"}`, `envelope` (episode 3,600 s, evaluation 14,400 s, concurrency 4), `quality_floor: {"kind": "above_stub"}`, `dominance_cost_tolerance` 0.10, `final_choice: {"equivalence_tolerance": 0.5, "mean_cost": "metered_USD", "mean_cost_ceiling": <4 × c_ref rule>, "provider_calls": "mean"}`, `support: {"rule": "every_adaptive_task", "task_weights": "equal"}`, `archive: {"size": 6, "spread_rule": "cheapest_highest_largest_gaps"}`, `reservoir: {"capacity": 4, "admission": "valued_non_frontier", "eviction": "fifo"}`, `exploration_fraction` 0.25, `policies: ["frontier_only", "mixture"]`, `revisit_key: "skeleton+policy"`, `futility: {"consecutive": 4}`, `horizon: {"generations": 4, "episodes_per_generation": 4, "adaptive_replicates": 1, "sealed_replicates": 3, "warm_start": {"seeds": [...], "replicates": 2}}`, `checkpoints: "after every generation"`, `endpoints: {"cost_ceilings": [1, 2, 4], "quality_targets": [0.5, 1.0, 2.0], "budget_cuts": ["B*", "B*/2"]}`, `power` (the formula, assumptions, δ = 1.0, the bracket, the descriptive-pilot statement), `budget` (the step table with caps), `campaigns: [{"campaign_id", "policy", "run_seed"}]`, `context` (the fields hashed into `context_key`), `stop_rules`, `not_tested` (no policy claim), `written_before_scoring: true`.
- V2 receipt: `schema: "orc-structural-qualification-v2"`; `family` as V1's `review-blockers-r55` but under `amends_5` (`rule: {file, sha256}` naming `calibration-amends-5.json`, reviewer `gpt-5.6-terra`, k = 2 with the borderline third pair), raw records recomputed with `prepare.blockers`; `measure` names the judge-calibration criterion and the accepted A or A2 pools plus B2, and the validator recomputes P1, P2, P3 and the spread over the full judge × batch denominator from `results.json` ratings (the four roles from the criterion's `anchors`), rejecting a mapping whose `rubric` differs from the study's or whose reference clone is rated. V1 is unchanged; V2 is admitted only when the criterion's `rubric` is the reference mapping.
- `qualification_support.campaign_criterion(root, *, tasks, judges, models, price_table, **overrides) -> Path` and `qualified_v2(root, ...)` writing a passing synthetic V2 receipt (the pattern of `qualified`).

- [ ] **Step 1: Write the failing tests**:

```python
def test_v2_receipt_recomputes_p1_p2_p3_and_spread_over_the_full_denominator(tmp_path)
def test_v2_rejects_a_rated_reference_clone_a_rubric_mismatch_and_a_missing_mutant(tmp_path)
def test_v2_family_requires_amends_5_and_recomputes_blockers_from_raw_records(tmp_path)
def test_v1_criteria_still_validate_and_cannot_use_a_v2_receipt(tmp_path)
def test_campaign_criterion_requires_every_frozen_field_and_refuses_a_calls_cost_axis(tmp_path)
def test_check_campaign_refuses_a_criterion_without_qualification_or_with_an_unadmitted_judge(tmp_path)
```

- [ ] **Step 2: Run** — expected: FAIL. **Step 3: Implement** (each touched qualification module ≤ 500 lines; split `qualification_measure.py` at the V1/V2 boundary if needed).
- [ ] **Step 4: Run** `pytest -q tests/experiments/test_orc_structural_search_qualification.py tests/experiments/test_orc_structural_search_qualification_lineage.py tests/experiments/test_orc_structural_search_campaign*.py` — expected: PASS.
- [ ] **Step 5: Commit** `feat(search): successor campaign criterion schema and qualification receipt v2`.

### Task 7: Documentation hooks

**Files:**
- Modify: `experiments/orc_structural_search/README.md` (campaign recipe: store layout `S/evidence.jsonl`, `S/candidates/`, `S/campaigns/<id>/checkpoint.json`; `campaign run|resume|readout`; the "Adaptive mode 2" row becomes "historical; cumulative campaigns (mode 3) implemented offline"), `docs/plans/2026-10-18-orc-structural-search-phase2-plan.md` (status note at the top: its calls-based archive and generation protocol are superseded by this plan and the cumulative campaigns design; no calls-only selection returns; the plan stays as a record (C7)), `docs/capability_status_matrix.md` and `docs/design/README.md` (the structural-search rows: offline mode 3 implemented; only if `git status --short` shows them clean), the driver design's status bullet (one sentence pointing at the cumulative design; the "Search Modes" mode-3 pointer itself belongs to the design amendment)
- Not touched: `docs/index.md` (the row is staged by the coordinator, C10), `AGENTS.md`, the measurement plan.

- [ ] **Step 1:** Write the docs; run `python scripts/check_doc_links.py` on each changed file — expected: no broken links.
- [ ] **Step 2: Commit** `docs(search): campaign recipe, Phase 2 plan supersession note and status rows`.

---

### Task 8: Live pilot preconditions and freeze (owner-gated, no spend)

Each item recorded in `E/ledger.md` with hashes before any call; the gate is C5 and the design's [Staging And Gates](../design/orc_structural_search_cumulative_campaigns.md#staging-and-gates):

- [ ] Measurement plan Step A passed (judge calibration under rubric v2; A′ if the rerun was approved) and Steps B/B2 qualified both adaptive packages under `amends_5`; Step C's gate 3 closed for both tasks; the V2 receipt validates with `qualification.validate(..., operation="launch")`.
- [ ] Metering wired: receipt coverage for Sonnet and Terra judges and coders measured complete in Steps A–C; the price table frozen with source and date.
- [ ] Sealed split: rung 1 `cf1-generic-unions` amended like rungs 2 and 4 (four anchors, promoted visible check, `dev-check.json`) and qualified under `amends_5`; its own owner-gated cost (about 8 calls, cap 14, plus 4 judge-calibration calls); never an adaptive task; never shown to an agent. Validation package (rung 3) only if the owner selects it (third sample plus the same amendment).
- [ ] The amendment accepted together: roadmap Phase 2 (C1) rows, boundaries invariant 4 change note `proposed-amendment-2026-10-19`, the cumulative design, the capability matrix and the README.
- [ ] Tasks 1–7 merged; full `tests/experiments/` green on commit `I`; `RT` detached at `I`; `criteria/cumulative_c1.json` frozen afterwards as commit `F` with the inherited measurement block, the V2 receipt hash, the price table, the two campaign rows (`c1-frontier`, `c1-mixture`, one `run_seed`), and the Power And Budget table; `E/criterion.sha256` records `I` and `F`.
- [ ] Offline dress rehearsal on `RT` with the scripted CLIs: warm start, both campaigns at G = 1, resume, freeze, sealed-open and readout, under the frozen criterion; the exact operator commands captured in `E/commands.md`.

### Task 9: Step P0, shared warm start (owner gate: 14 calls, cap 20)

- [ ] Ask the owner with the call estimate, cap, the Codex window reading, the quota policy and the worst-case total (202, or 238 with P3). Record approval.
- [ ] `python -m experiments.orc_structural_search.campaign warm-start --store S --criterion F --config C1_CONFIG --seeds <capped direct, icdr> --tasks <rpi> <prr> --holdout <cf1> --work-root W/warm --evidence E/warm --pools P/warm --runtime RT --eval-timeout-sec 14400 --concurrency 4 --call-cap 20 --solution ... --judge claude-sonnet-5-5 --judge gpt-5.6-terra=RT/experiments/compare/providers/score_codex.json` in tmux; adjudicate scans; verify the two seeds' trials and assessments in the store; record `c_ref`, `q_ref`, the resolved ceilings and targets, and the warm-start cost in the ledger.

### Task 10: Step P1, campaign `c1-frontier` (owner gate: 65 calls, cap 80)

- [ ] Ask the owner (estimate, cap, window reading, remaining worst case). `campaign run --store S --criterion F --campaign c1-frontier --policy frontier_only --run-seed <seed> --generations 4 --episodes-per-generation 4 --agent-cmd "<capped Codex mutator>" --work-root W/c1-frontier --evidence E/c1-frontier --pools P/c1-frontier --holdout <cf1> --hide <every earlier root> --call-cap 80 ...` in tmux; incidents resumed through `--continue`, never relaunched outside the quota rule; scans adjudicated at each generation's wait; the checkpoint trajectory and budget union recorded per generation in the ledger. Early stop under a predeclared rule is valid and reported as incomplete.

### Task 11: Step P2, campaign `c1-mixture` (owner gate: 65 calls, cap 80)

- [ ] As Task 10 with `--campaign c1-mixture --policy mixture`, the same `run_seed`, the same horizon and cap, `E/c1-frontier` and `W/c1-frontier` among `--hide`.

### Task 12: Step P3, validation on a qualified fourth package (conditional owner gate: 29 calls, cap 36)

- [ ] Only when Task 8's validation package exists: finalists = top 2 of each campaign's final bounded frontier plus the reference, 3 replicates on the validation task, judged in one pool; `final_choice` per campaign over validation rows; shrinkage (adaptive mean minus validation mean) reported. Without the package: skipped, and the report states that selection rests on adaptive evidence.

### Task 13: Step P4, analysis freeze, sealed assessment and report (owner gate: 18 calls, cap 22)

- [ ] `campaign freeze --store S --campaign c1-frontier --campaign c1-mixture --reason "<ledger entry>"` after the readout script and the report's tables are written from adaptive evidence only (committed before any sealed call: the analysis freeze).
- [ ] Ask the owner; `campaign open-sealed ...` (once); evaluate each campaign's final choice and the reference 3 times on rung 1; one pool, both judges; `campaign readout --sealed-results ...`.
- [ ] Write `docs/reports/2026-10-<dd>-orc-structural-search-cumulative-pilot.md` from the store, the ledgers, the pools' `results.json` and the readout only: anchors first (P1/P2/P3 per pool), endpoints per checkpoint and at B*/B*/2, the sealed table, the budget union per campaign beside the warm-start cost and the unpriced-work list, acceptance/revisit/futility/reservoir-draw rates, diversity, lineage, the variance estimates (checkpoint-to-checkpoint and across campaigns) with the sizing of a powered follow-up, refusals and incidents against the caps, scan verdicts, file hashes; state the pilot's descriptive status and that no policy claim follows. Update the roadmap's decision row and the capability matrix; link-check; commit.

## Decision Ledger

| Decision | Consequence |
| --- | --- |
| Descriptive pilot, R = 1 per policy | The affordable design cannot detect δ = 1; outputs are variance estimates and live mechanics; no policy claim preregistered |
| One new module (`campaign.py`); loop in `adaptive.py` | `run_mode2` keeps refusing; historical calls-based helpers stay read-only; split at an existing responsibility only if the 500-line rule forces it |
| Metered cost only on the campaign frontier | `pareto_readout.homogeneous` is never consulted by the campaign path; unmetered candidates are reported off the frontier (C7) |
| Skeleton-plus-policy revisit key | Prompt-only module rewrites are revisits in C1 (disclosed ceiling, widened only by a later criterion); a policy-only rewrite is a fresh child |
| Shared, separately costed warm start | Identical initial evidence for both policies; acquisition cost outside each campaign's budget (A4) |
| Two splits by default, validation conditional | No qualified fourth package exists; the sealed split is the independent assessment, opened once after freeze |
| Qualification V2 in this plan | The measurement plan deferred it to the study that needs it; V1 and the historical criteria stay byte-identical |
| Store masked like the evidence root | A mutator never reads another campaign's candidates or trials; the scan patterns cover `S` |
| Every live step its own approval | The caps in Power And Budget are ceilings per step, never a pooled allocation |
