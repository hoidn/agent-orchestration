# ORC Structural Search `module` Condition: Remaining Offline Implementation

- **Status:** active delta plan, 2026-10-19; requirements pending verification.
  Baseline: delivery `efa79ef9`, with owner revisions merged at `3947ceb1`.
  The earlier 774-test result in the [decision's prior evidence](2026-10-19-orc-structural-search-module-rewrite-plan.md#prior-offline-execution-evidence)
  covers the earlier delivery, not these additions.
- **Purpose:** implement the remaining owner requirements in the experiment
  apparatus using scripted providers. No live run, provider spend, calibration
  experiment, new frozen criterion or runtime/spec change is selected here.
- **Authority:** [driver design](../design/orc_structural_search_driver.md),
  especially "Edit Validation And Transactions", "Objective, Selection And Local
  Observations", "Task Family And Evaluator" and "Metering And Consumption";
  [module decision](2026-10-19-orc-structural-search-module-rewrite-plan.md);
  [roadmap](2026-10-18-orc-structural-search-roadmap.md). This plan owns execution,
  remaining decisions and verification; those documents own the semantics.
- **Execution:** use Subagent-Driven Development; a reviewer distinct from the
  author checks each substantive package. A and B can proceed independently;
  C's qualification contract and A/B's recorded data precede D; E integrates all.
  This is a manually executed plan, with no machine-readable selector or queue.

## Approach And Constraints

Extend the delivered driver and harness in place, keeping working interfaces.
This makes reconstruction from the old task list unnecessary, but requires
explicit tests at the joins between admission, launch, receipts and readout.
Whole-module changes remain harder to attribute; ablations explain a gain,
whereas retention requires reproduction on the validation split, at least three
replicates per task under the frozen measure and within the approved allocation.

Keep the existing `models` mapping from model ID to allowed effort lists,
`per_call_timeout_sec`, top-level criterion `arms`, the workspace check CLI,
local parent/configuration metadata and structured JSON compile diagnostics.
Preserve source frozen-surface guards, the compiled public-contract backstop,
private ordinal metric invariants, model refusal codes and implemented ceiling,
graph and Claude model-guard hardening. No aliases or cosmetic API renames.
The fifth condition, private definitions/types, existing check, criterion hashes
on rows and receipt discovery are delivered; do not rebuild them mechanically.

Every changed/new module must remain at most 500 lines and every function at
most cyclomatic complexity 12. Split at existing responsibilities where needed
(one-site transactions, catalog enumeration, record metrics); update all callers,
tests, fixtures and exports together. Preserve validation and error handling.
Use the standard library and existing dependencies only. No `orchestrator/`
changes, bundle imports, new optimizer framework or Fable experiment calls.

Remove the committed illustrative `criteria/module.json`; successor fixtures
construct criteria in temporary directories. No successor criterion is committed
or frozen by this work. Keep `criteria/phase1.json`, `phase2.json`,
`three_arm.json` and `experiments/compare/providers/*.json` byte-identical.
Their captured interpretation remains reproducible; historical identity does
not grant a fresh quality launch permission under today's calibration rule.

## A. Sound Reservations, Shim Cap And Admission

**Reach:** `acceptance.py`, `ledger.py`, `driver.py`, `evaluation.py`, `check.py`,
`experiments/compare/shim/{claude,codex}`, their direct callers and scripted
admission, bounds, workspace and shim tests. Reuse `acceptance.compiled_refusal`
and the compiler-produced closed program; extract a helper only to keep the
responsibility or size bounded.

- [ ] Refuse `provider_phased`, `agent` and `agent_turn` perform shapes under
  every condition as `unsupported_effect_shape`, including parent/evaluation
  admission where needed. Preserve module-only policy validation and complete
  compile diagnostics; compiler crashes remain infrastructure incidents.
- [ ] Compute a module evaluation's planned maximum from the checked closed
  program rather than the authored-source counter. Traverse the executed entry,
  expand resolved procedure calls **per invocation**, and include their argument
  evaluation and imported definitions. Counting each definition once is unsound.
  Read the actual `loop.budget` literal, not a source `:max` or guessed `max`
  artifact field; account for nested budgets, exhausted paths and par-map maxima.
  Count provider classes, including classes refused by admission so the counter
  itself does not silently assign them zero. Refuse unresolved calls, recursion
  or unknown/unbounded effect shapes unless a sound finite bound is established.
  Sum sequencing and conservatively cover alternative paths. A checked artifact
  is input to the proof, not proof that a generic recursive JSON sum is sound.
- [ ] Reserve this maximum before launch and pass that same reservation to both
  shims. Enforce it before invoking the real provider, including concurrent call
  allocation, zero cap, retries and resumed launches. A recorded refused attempt
  identifies the cap and fails as a provider failure; the ledger settles recorded
  attempts without disguising refusal as successful usage. Keep the launch cap
  out of agent/tool environment alongside other controller-only `COMPARE_*` data.
- [ ] Keep the workspace check tied to the controller's staged parent even when
  the mutator commits or rewrites workspace Git history. Finalization rechecks
  against controller-owned inputs; a successful intermediate check is insufficient.
- [ ] Split oversized touched modules at natural boundaries, preserving source
  and metric behavior. Add no speculative compatibility wrappers.

**Acceptance evidence:** a helper invoked twice counts twice; a locally bound
`proc-ref` and imported helper count correctly; nested loops include exhaustion;
unresolved/unbounded paths refuse; each unsupported class refuses under legacy
and module conditions. A scripted launch at its cap succeeds, the next call is
recorded and refused before the executable runs, and concurrent attempts cannot
overspend. A mutator history rewrite cannot replace the check's parent.

**Integration decision resolved:** the driver's
[closed-program reservation contract](../design/orc_structural_search_driver.md#edit-validation-and-transactions)
uses real AST edges, actual `loop.budget`, per-invocation calls and argument
evaluation, exhaustion even at zero budget, and fail-closed effectful list-map
cardinality. Literal mappings are data, not traversable AST. A's implementation
is recorded at `fbae5d4b`; acceptance remains subject to this plan's verification
and integration checks. No runtime change or admission-policy rename is implied.

## B. Receipts, Allocation And Site Evidence

**Reach:** `metering.py`, `driver.py`, `evaluation.py`, record/metric helpers and
scripted receipt/row tests. Retain per-call/model usage so readout can price it
under its frozen criterion; do not price against process-global configuration.

- [ ] Keep unambiguous workspace/start-time receipt joins and native episode
  session paths. Preserve per-model counters and their evidence provenance;
  incomplete, ambiguous, malformed or truncated coverage is `unavailable`, never
  zero. Evaluation rows retain consumption without exposing native paths.
- [ ] Record `allocation_changed` on episode and evaluation rows by comparing
  compiled per-call-site `(provider, model, effort)` with the parent's. Retain
  `allocation_distinct` for collapse reporting: extern-only allocation and a
  skeleton hash cannot detect every model/effort change. Identify unavailable
  comparison evidence explicitly.
- [ ] Record planned perform sites and realized effects from validated memo
  evidence, with unexercised planned sites reported only when the join supports
  that statement. Preserve identities, effect classes, attempts and outcomes;
  an I3 generic command has no ORC memo. Do not claim source-branch coverage.

**Frozen receipt-to-price mapping for readout:** a Claude usage row charges
`input_tokens` at input, `output_tokens` at output,
`cache_read_input_tokens` at cache-read and `cache_creation_input_tokens` at
cache-write, at that row's model. A Codex rollout uses the last cumulative
`total_token_usage`: charge `input_tokens - cached_input_tokens` at input,
`cached_input_tokens` at cache-read, `cache_write_input_tokens` at cache-write
and `output_tokens` at output, at the call's model. Never add
`reasoning_output_tokens`, already contained in `output_tokens`. Sum per
evaluation/episode as list-price equivalent, not billed spend. The successor
criterion supplies each model's input/output/cache-read/cache-write prices,
source and date; invent no prices. Missing coverage or a missing model price
makes cost `unavailable`. Reject invalid counters/prices rather than fabricating
usage. Calls and wall clock remain reported beside cost.

**Acceptance evidence:** synthetic Claude and Codex receipts price mixed models
without double-charging reasoning or cumulative totals; incomplete receipts and
unknown models remain unavailable. A pure model change changes
`allocation_changed` even when skeleton and extern allocation are identical;
planned/realized joins preserve attempts without asserting branch coverage.

## C. Explicit Precalibration Qualification

**Reach:** experiment configuration/criterion loading, launch boundaries,
`judging.py`, scoring/readout entry points and qualification tests. The durable
contract belongs to the driver's
[external qualification receipt](../design/orc_structural_search_driver.md#external-qualification-receipt).

- [ ] Require explicit qualification from hashed external precalibration evidence
  for both the task family under its frozen rule and the quality measure under
  its predeclared control rule. Bind evidence to the criterion and relevant
  family/evaluator inputs; reject missing, mismatched or unqualified evidence.
- [ ] For each judge and batch, upstream anchor total minus stub total must be
  at least `calibration.margin`. The fraction of failing `(judge, batch)` pairs
  must be at most `calibration.error_rate` (default 0). Both are predeclared;
  candidate ranks impose no qualification condition. In-run anchors monitor the
  experiment and cannot substitute for the pre-experiment qualification.
- [ ] Guard quality candidate evaluation launches, judging and quality/frontier
  readouts. Unqualified operation can report only measure-free compile,
  execution and cost figures. Existing frozen criteria or legacy row exceptions
  do not automatically authorize a new quality launch or claim. Separate
  calibration runs need their own declared budget and owner approval; do not
  trigger them automatically or spend providers in this implementation.

**Integration decision resolved:** implement `orc-structural-qualification-v1`
and the common `measurement: {evaluator, tasks}` identity block in study and
calibration criteria; retain the study's existing top-level task-path list.
Compare verified component hashes, not whole study/calibration criterion hashes
or reference file locations. Recompute R55 difficulty from raw records/diffs and
measure calibration from every expected judge/batch pair, including missing or
excluded ratings as failures. Verify the actual runtime workflow and selected
judge bindings. Family B's narrow oracle-control receipt qualifies the family
only; final scoring remains the blind rubric.

Thread `criterion: Path | None` through structural launch/resume/judge boundaries
and validate before reservation. Default purpose is quality and a missing
criterion fails closed. An explicit measure-free criterion permits execution
without quality claims; a readout-only `--measure-free`/keyword also projects
historical evidence without modifying frozen criteria. Invalid quality never
silently downgrades. Calibration is external, independently budgeted and limited
to declared controls/difficulty jobs; structural launchers reject that purpose.
Do not add a calibration launcher or extend generic compare launchers here.

**Acceptance evidence:** scripted boundary tests reject absent, stale/mismatched
and failed qualification before provider invocation; valid frozen evidence passes.
Tests exercise margin and tolerated error rate independently, and demonstrate
that historical criteria get no implicit fresh-launch bypass. Measure-free
readouts remain possible without emitting quality endpoints. Include borderline
difficulty and raw patch/review pairing, stale runtime/bindings, missing-judge
denominators, disguised candidates in calibration pools and calibration-purpose
launch refusal. This decision resolves the schema; implementation remains pending
the listed checks.

## D. Parents And Calibrated Pareto Endpoints

**Reach:** `three_arm.py`, `three_arm_readout.py`, scoring/judging joins,
`records.final_choice` consumers and successor-only adaptive selection if used.
Depends on A/B data and C's qualification decision.

- [ ] Evaluate each distinct parent on the same tasks/replicates as the relevant
  child subset. Shared ORC parents are evaluated once per unique evaluation
  identity and projected to their arms; do not launch duplicate evaluations or
  count a projection as fresh evidence. Resume retains evaluation identity.
- [ ] Join all evaluated children and parents through harness clone IDs and
  criterion hashes, with matched task/replicate support. Do not silently pool
  studies, duplicate projected rows or compare unmatched means.
- [ ] Read prices at readout from the successor criterion. Quality tolerance is
  `final_choice.equivalence_tolerance`; relative cost tolerance is
  `dominance_cost_tolerance`; also require the quality floor and `calibration`
  object. Keep run configuration free of price tables and retain existing arm
  and model configuration names.
- [ ] Implement dominance literally for means over the same tasks/replicates:
  `q_A >= q_B - tau_q` and `c_A <= c_B * (1 + tau_c)`, and
  (`q_A > q_B + tau_q` or `c_A < c_B * (1 - tau_c)`). A candidate within both
  tolerances neither dominates nor is dominated. Apply the quality floor before
  frontier placement; recompute the frontier from all valued evaluated
  candidates independently of insertion order.
- [ ] Report dominating improvements over the matched parent and frontier entries
  per completed episode, split by `allocation_changed` and structure-only.
  Report each unvalued child, exclude it from numerators, retain it in the
  completed-episode denominator. A candidate with unavailable cost stays off the
  frontier and is reported beside it. Calls are a cost proxy only if **every**
  compared candidate's calls resolve to one and the same `(model, effort)` pair;
  the condition name or declared allowlist does not prove that.
- [ ] Keep deployment choice over every validated candidate including the
  reference seed under `records.final_choice`; do not replace it with whichever
  child arrived last. Report the adjudicated per-arm frozen-surface-workaround
  figure; unresolved or malformed scan evidence stays pending, never clean.
- [ ] Do not rewrite frozen Phase 2 interpretation. If successor adaptive use is
  implemented, select its criterion explicitly and apply calibrated metered-cost
  dominance, tolerances, quality floor and the design's bounded frontier/spread
  rule there. Otherwise refuse unsupported successor adaptive selection and
  document the limit; never silently use the old calls-only retention policy.

**Acceptance evidence:** parent launch deduplication and projections, matched
replicate rejection, tolerance edges, quality floor, order-independent frontier,
unavailable cost, homogeneous-vs-mixed model cost proxies, unvalued denominator
and allocation splits. A scripted fourth-arm run exercises all joins and reports
control anchors first. These synthetic checks establish mechanics, not utility.

## E. Documentation And Final Verification

- [ ] Remove illustrative `criteria/module.json` and change its consumers,
  fixtures and README examples to temporary or explicitly external successor
  criteria. Verify the three historical criterion hashes and provider JSON bytes
  against `efa79ef9`. Retain prior artifact hashes as historical evidence.
- [ ] Reconcile driver design, decision, roadmap, experiment/compare READMEs,
  capability matrix and documentation index with the delivered behavior and
  remaining gates. State module's intended future primary role, legacy/I2
  controls and ablations, and the absence of live selection or quality evidence.
  Record exact verification commands/results and any remaining limit here.
- [ ] Run narrow selectors for each package, and `pytest --collect-only -q` for
  every new or renamed test module. Assert behavior, contracts, lineage and
  outcomes, never literal prompt phrasing. Run the relevant public compile/run
  scripted integration and workspace-check repair path; include cap refusal and
  the successor fourth-arm end-to-end path.
- [ ] Run `pytest -q tests/experiments/test_compare_pool_summarize.py
  tests/test_demo_trial_smoke.py` for shim/brief/harness changes. Then run the
  experiments suite from the repo root in tmux using the tmux skill:
  `PYTHONPATH=. pytest -q -n 16 --dist=worksteal tests/experiments/`.
  Inspect fresh command output, do not inherit the prior 774 result as new proof.
- [ ] Verify module line/function complexity budgets, documentation links and
  `git diff --check`; inspect the final diff and results as coordinator. Commit
  only scoped files. No provider run or live calibration follows automatically.

## Decision Ledger

| Decision | Reason / consequence |
| --- | --- |
| Replace the original rebuild checklist with A–E deltas | The fifth condition, check and core records already exist; old names and "not implemented" statements caused contradictory instructions |
| Retain `models` mapping, `per_call_timeout_sec`, top-level `arms`, check metadata and refusal/diagnostic interfaces | Equivalent delivered contracts work; aliases and cosmetic migrations add no owner requirement |
| Keep private ordinal metrics and all delivered hardening | New semantics do not justify weakening existing source, graph, policy or diagnostic checks |
| Closed bound and shim cap are module v1 requirements | Bundle imports are still deferred; source counting alone cannot reserve rewritten helper calls soundly |
| Remove illustrative committed successor criterion; generate test criteria | Prior artifact remains historical evidence; no new study criterion or prices are selected here |
| Adopt external qualification receipt v1 and the closed-AST bound recurrence | Decisions resolved in the driver design; implementation and integration still require fresh verification |
| Normalize the shared measurement identity by component hashes | Study and calibration criteria may have different purposes, budgets and file locations without changing the calibrated evaluator |
| Keep calibration external and measure-free selection explicit | No candidate can obtain a calibration bypass; historical readout projection does not mutate frozen criteria or restore quality claims |
| Shared parent evidence is projected by identity | Avoid duplicate launches and preserve arm attribution without inventing additional observations |
| Historical criteria stay byte-identical without a fresh-launch exemption | Preserve captured reproducibility while enforcing today's calibration gates |
| No provider allocation requested | All listed implementation and verification uses scripted providers; any later calibration/live experiment is separately budgeted and owner approved |
