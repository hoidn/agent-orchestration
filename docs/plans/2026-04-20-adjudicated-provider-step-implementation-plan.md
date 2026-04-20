# Adjudicated Provider Step Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved DSL `2.11` `adjudicated_provider` first release so one logical provider step can run isolated candidates, evaluate output-valid artifacts, select deterministically, promote only declared selected outputs, and record stable adjudication state and score ledgers.

**Architecture:** Treat the approved ADR at `docs/plans/2026-04-20-adjudicated-provider-step-design.md` as the full first-release contract. Keep authoring, candidate execution, scoring, ledger, promotion, resume, and publication as separate runtime responsibilities with explicit data contracts between them. Existing adjudication code and tests in the checkout are starting material only; this plan is not a preservation pass over the previous stale plan.

**Tech Stack:** Python 3.11+, YAML DSL loader, typed workflow AST/IR, existing provider executor, output-contract validators, workflow state manager, pytest unit/integration suites, orchestrator dry-run smoke checks.

---

## Current Scope

Current scope is the whole approved first-release design, not a loader-only or scoring-only slice. The implementation must deliver the DSL `2.11` authored surface, isolated candidate workspaces, same-trust-boundary evaluator scoring, deterministic selection, transactional selected-output promotion, run-local and workspace-visible score ledgers, additive step state, timeout/retry behavior, resume reconciliation, observability projection, an example workflow, and updated specs/docs.

The implementation is large, but it is still one coherent release because the material requirements are mutually dependent:

- candidate isolation is needed before scoring because score evidence must come from deterministic candidate output state
- scorer identity and evidence hashes are needed before selection because rows and resume keys depend on them
- selection is not useful without promotion because downstream steps must consume ordinary deterministic artifacts
- promotion is not safe without baseline preimages and resume-safe manifests
- ledgers and step state cannot be finalized correctly until selection and promotion reach terminal state

No material requirement from the design is deferred. Follow-up work is limited to the ADR's explicit future extensions and is listed at the end.

## Implementation Architecture

Correctness and maintainability depend on boundary decisions across authored DSL validation, runtime sidecars, provider execution, scoring, promotion, state, and docs. This section translates the approved design into implementable ownership without changing the design.

### Unit 1: Authored Surface, Validation, And Typed Workflow Preservation

**Owned files:**

- `orchestrator/loader.py`
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/runtime_step.py`
- `specs/dsl.md`
- `specs/providers.md`
- `specs/io.md`
- `specs/security.md`
- `specs/state.md`
- `specs/versioning.md`
- `specs/acceptance/index.md`
- `tests/test_adjudicated_provider_loader.py`
- `tests/test_workflow_surface_ast.py`
- `tests/test_workflow_ir_lowering.py`

**Stable interfaces owned:**

- DSL step form `adjudicated_provider`, gated at `version: "2.11"`.
- Candidate config shape: `id`, `provider`, optional `provider_params`, optional `asset_file` xor `input_file`, optional `prompt_variant_id`.
- Evaluator config shape: `provider`, optional `provider_params`, `asset_file` xor `input_file`, optional rubric source, required `evidence_confidentiality: same_trust_boundary`, optional literal `evidence_limits`.
- Selection config shape: `tie_break: candidate_order`, optional boolean `require_score_for_single_candidate`.
- Optional `score_ledger_path`, loader-checked for static path safety and static collisions.
- AST/IR preservation of the adjudicated config without turning it into an ordinary provider step.

**Must not own:**

- Provider subprocess execution.
- Filesystem baseline copy and promotion logic.
- Evaluator packet construction.
- Score ledger row generation.

**Dependency direction:** loader/elaboration produce typed AST/IR; executor consumes typed IR. Runtime helpers must not revalidate authoring syntax that the loader can reject statically, except for dynamic path and resume integrity checks.

**Compatibility boundary:** existing `provider` steps keep current behavior. `adjudicated_provider` is invalid below DSL `2.11`; state schema remains `2.1`.

### Unit 2: Adjudication Runtime Package And Sidecar Data Model

**Owned files:**

- Move/split: `orchestrator/workflow/adjudication.py` into a package rooted at `orchestrator/workflow/adjudication/`
- Create: `orchestrator/workflow/adjudication/__init__.py`
- Create: `orchestrator/workflow/adjudication/models.py`
- Create: `orchestrator/workflow/adjudication/paths.py`
- Create: `orchestrator/workflow/adjudication/baseline.py`
- Create: `orchestrator/workflow/adjudication/evidence.py`
- Create: `orchestrator/workflow/adjudication/scoring.py`
- Create: `orchestrator/workflow/adjudication/ledger.py`
- Create: `orchestrator/workflow/adjudication/promotion.py`
- Create: `orchestrator/workflow/adjudication/resume.py`
- Modify: import sites in `orchestrator/workflow/executor.py` and existing adjudication tests

The current single-file module may already contain partial helpers. Split it only along the package boundaries above, and keep `orchestrator.workflow.adjudication` re-exporting the public helper names that tests and the executor import today.

**Stable interfaces owned:**

- Constants: `adjudicated_provider.baseline_copy.v1`, `adjudicated_provider.local_secret_denylist.v1`, `adjudication.evaluation_packet.v1`, `adjudication.evaluator_json.v1`, `workflow_declared_secrets.v1`, `adjudicated_provider.score.v1`.
- Sidecar paths:
  - `.orchestrate/runs/<run_id>/adjudication/<frame_scope>/<step_id>/<visit_count>/...`
  - `.orchestrate/runs/<run_id>/candidates/<frame_scope>/<step_id>/<visit_count>/<candidate_id>/...`
  - `.orchestrate/runs/<run_id>/promotions/<frame_scope>/<step_id>/<visit_count>/manifest.json`
- Dataclasses for visit paths, candidate paths, baseline manifests, scorer snapshots, scorer-resolution failures, candidate metadata, selection results, promotion results, and deadline handling.

**Must not own:**

- Workflow traversal or next-step routing.
- Provider registry lookup semantics beyond data needed for hashing.
- Artifact publication into state.

**Dependency direction:** executor calls package services; package services may use `orchestrator.contracts.output_contract` for deterministic validation and basic path helpers. The package must not import the workflow executor.

**Compatibility boundary:** the package split is internal. Public behavior and existing import path `orchestrator.workflow.adjudication` remain available through `__init__.py` re-exports during the release.

### Unit 3: Baseline Snapshot And Candidate Workspace Authority

**Owned files:**

- `orchestrator/workflow/adjudication/baseline.py`
- `orchestrator/workflow/adjudication/paths.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/contracts/output_contract.py` only if an existing generic path helper must be reused or lightly generalized
- `tests/test_adjudicated_provider_baseline.py`
- `tests/test_adjudicated_provider_runtime.py`

**Stable interfaces owned:**

- One immutable baseline per current-frame step visit after `when` and consume preflight.
- Fixed baseline copy policy with excluded roots, local-secret denylist, and safe-relative-symlink handling.
- Manifest fields for included entries, excluded entries, null-path comparison, workflow checksum, consume selections, policy versions, and `baseline_digest`.
- Candidate workspace copy from immutable baseline for each candidate attempt.
- Candidate WORKSPACE as the logical authority for candidate-managed paths even when physical path is under the parent run root.

**Must not own:**

- Arbitrary subprocess containment or OS sandboxing.
- Prompt source resolution for workflow-source-relative `asset_file`; executor/prompting owns that.
- Promotion commit behavior beyond baseline preimage calculation.

**Dependency direction:** baseline is created before candidate execution and before scorer/evaluator work. Promotion reads baseline preimages; baseline code does not know selection or publication rules.

**Compatibility boundary:** do not honor `.gitignore` or tool ignore files. Do not change ordinary provider path behavior.

### Unit 4: Candidate Provider Execution Adapter

**Owned files:**

- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/prompting.py`
- `orchestrator/providers/executor.py` only for narrowly reusable execution result fields if needed
- `tests/test_adjudicated_provider_runtime.py`
- `tests/test_provider_execution.py` only for provider-executor compatibility coverage

**Stable interfaces owned:**

- Consume preflight runs once in the current execution frame.
- Each candidate gets uniform step-level `consumes`, `prompt_consumes`, `inject_consumes`, `asset_depends_on`, `depends_on`, and output contract suffix.
- Candidate prompt override replaces only the base prompt source.
- Provider command `cwd` is the candidate WORKSPACE.
- Provider params substitution uses candidate execution context and active workflow provider namespace.
- Candidate stdout/stderr are runtime-owned logs, not step-visible stdout capture.
- Step-level retries apply independently to each candidate provider attempt; each retry starts from a fresh baseline copy.
- Step-level `timeout_sec` is one logical deadline across baseline, candidates, evaluators, ledgers, promotion, and final validation.

**Must not own:**

- Evaluator scoring decisions.
- Ledger row shape.
- Promotion file-copy transaction internals.

**Dependency direction:** executor coordinates candidate generation, then hands output-valid candidates to scoring. Provider executor remains provider-generic and must not embed adjudication policy.

**Compatibility boundary:** ordinary provider execution, output capture, retries, and stdout state remain unchanged.

### Unit 5: Scorer Snapshot, Evidence Packet, Evaluator Execution, And Selection

**Owned files:**

- `orchestrator/workflow/adjudication/evidence.py`
- `orchestrator/workflow/adjudication/scoring.py`
- `orchestrator/workflow/executor.py`
- `workflows/library/prompts/adjudication/evaluate_candidate.md`
- `tests/test_adjudicated_provider_scoring.py`
- `tests/test_adjudicated_provider_runtime.py`

**Stable interfaces owned:**

- Scorer snapshot under the visit's `scorer/` directory before first evaluator launch.
- `scorer_identity_hash` canonical object.
- Scorer-resolution failure metadata and `scorer_resolution_failure_key`.
- Evaluation packet schema `adjudication.evaluation_packet.v1`.
- Evidence limits defaults: `max_item_bytes: 262144`, `max_packet_bytes: 1048576`.
- Complete UTF-8 score-critical evidence only: rendered candidate prompt with output suffix, output value files, required relpath targets, bundle JSON and required bundle targets, optional rubric content, and injected consume relpath target content.
- Secret detection for non-empty workflow-declared secret values before packet persistence and evaluator launch.
- Evaluator stdout strict JSON with matching `candidate_id`, finite score in `[0.0, 1.0]`, and non-empty `summary`.
- Selection rules for no valid candidates, optional-score single candidate, required-score single candidate, multi-candidate partial scoring, highest score, and candidate-order ties.

**Must not own:**

- Runtime logs as scoring evidence.
- Path-based evaluator reads from candidate or parent workspaces.
- Pass/fail evaluator semantics or score thresholds.

**Dependency direction:** scorer uses candidate metadata and validated output artifacts. Ledger consumes scorer/evaluation results; scorer does not write ledgers.

**Compatibility boundary:** evaluator packet evidence is sensitive unmasked run state. The runtime must not attempt broad redaction beyond declared-secret detection.

### Unit 6: Score Ledger And Workspace-Visible Mirror

**Owned files:**

- `orchestrator/workflow/adjudication/ledger.py`
- `orchestrator/workflow/executor.py`
- `tests/test_adjudicated_provider_scoring.py`
- `tests/test_adjudicated_provider_runtime.py`

**Stable interfaces owned:**

- Run-local ledger path `candidate_scores.jsonl`.
- Optional workspace-visible mirror under `artifacts/`.
- Normative row schema `adjudicated_provider.score.v1`.
- `candidate_run_key` and `score_run_key` idempotency semantics.
- Owner tuple: `row_schema`, `run_id`, `execution_frame_id`, `step_id`, `visit_count`.
- Terminal mirror materialization only after no-selection failure, promotion failure, or committed promotion plus parent validation.
- Static and dynamic collision checks with step-managed dataflow paths.

**Must not own:**

- Artifact publication.
- Promotion transaction.
- Cross-run aggregation.

**Dependency direction:** ledger generation reads terminal candidate metadata, scorer metadata, selection, and promotion status. Publication waits for terminal mirror success when a mirror is configured.

**Compatibility boundary:** mirror is observability, not an output artifact unless a workflow separately declares/export it through normal workflow outputs.

### Unit 7: Promotion Transaction

**Owned files:**

- `orchestrator/workflow/adjudication/promotion.py`
- `orchestrator/contracts/output_contract.py` only through existing deterministic validators
- `tests/test_adjudicated_provider_promotion.py`
- `tests/test_adjudicated_provider_runtime.py`

**Stable interfaces owned:**

- Promotion manifest schema and statuses: `prepared`, `committing`, `rolling_back`, `failed`, `committed`.
- Promotion source plan for non-`relpath` expected outputs, `relpath` value files and required targets, output bundle JSON, and required bundle relpath targets.
- Baseline and current parent destination preimage comparison before staging and immediately before commit.
- Staging validation before parent writes.
- Atomic per-file replacement, backups, rollback, directory cleanup, and conflict detection.
- Resume behavior for prepared, committing, rolling_back, failed, and committed manifests.

**Must not own:**

- Candidate selection.
- Artifact lineage publication after commit.
- General merge/conflict resolution for undeclared source edits.

**Dependency direction:** promotion consumes the selected candidate workspace, output contract specs, and baseline manifest. State publication depends on committed promotion and canonical parent validation.

**Compatibility boundary:** only selected declared outputs are promoted. Candidate-local source edits outside declared output contracts are retained for inspection only.

### Unit 8: State, Resume, Publication, And Observability

**Owned files:**

- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/dataflow.py`
- `orchestrator/workflow/resume_planner.py`
- `orchestrator/workflow/outcomes.py`
- `orchestrator/state.py`
- `orchestrator/observability/report.py`
- `orchestrator/cli/commands/report.py`
- `tests/test_adjudicated_provider_runtime.py`
- Create: `tests/test_adjudicated_provider_resume.py`
- `tests/test_adjudicated_provider_outcomes.py`
- `tests/test_observability_report.py`
- `tests/test_subworkflow_calls.py`

**Stable interfaces owned:**

- Additive `steps.<Step>.adjudication` payload under state schema `2.1`.
- No `steps.<Step>.output`, `.lines`, `.json`, `.truncated`, or `.debug.json_parse_error` from candidate/evaluator stdout.
- Current-frame artifact publication only after promotion commit, terminal ledger regeneration, optional mirror materialization, and parent output validation.
- Call-frame-local storage for adjudicated steps inside reusable calls.
- Resume mismatch detection for baseline, candidate config, composed prompt, scorer identity/failure key, evaluation packets, ledger rows, and promotion manifest.
- Outcome/error mapping for adjudication-specific terminal failures.
- Report/status projection for selected candidate, score, ledger paths, promotion status, and failure type.

**Must not own:**

- Low-level promotion file writes.
- Evaluator JSON parsing.
- Baseline copy policy internals.

**Dependency direction:** state and report layers read normalized adjudication state. They do not reconstruct candidate/evaluator behavior.

**Compatibility boundary:** older runtimes reject DSL `2.11` before interpreting adjudication state. No state migration is required.

### Unit 9: Examples, Prompts, And Durable Documentation

**Owned files:**

- `workflows/library/prompts/adjudication/evaluate_candidate.md`
- `workflows/examples/adjudicated_provider_demo.yaml`
- `workflows/README.md`
- `docs/runtime_execution_lifecycle.md`
- `docs/workflow_drafting_guide.md`
- `docs/index.md`
- `tests/test_workflow_examples_v0.py`

**Stable interfaces owned:**

- One reusable evaluator prompt that asks for strict JSON only.
- One dry-run-valid example workflow demonstrating candidates, evaluator, selected artifact promotion, and score ledger mirror.
- Docs that explain the stdout suppression contract, same-trust-boundary evidence attestation, sensitive sidecars, ledger mirror semantics, and first-release non-goals.

**Must not own:**

- Normative acceptance details that belong in `specs/`.
- Workflow-specific evaluator rubrics as the shared prompt default.

**Dependency direction:** docs/examples land after the runtime contract exists, except for the shared evaluator prompt which can be introduced with scoring.

## Explicit Non-Goals

- No pass/fail evaluator semantics, thresholds, or score bands.
- No prompt-text-based provider routing or selection.
- No provider sessions inside adjudicated candidates.
- No arbitrary source-edit promotion, patch merging, or conflict resolution.
- No stdout-derived downstream dataflow from adjudicated steps.
- No OS-level sandboxing guarantee for provider/evaluator subprocesses.
- No generic parallel execution framework.
- No generic data-loss prevention or broad automatic redaction of score-critical evidence.
- No aggregate append-only ledger mode.
- No state schema bump unless implementation proves the additive `steps.<Step>.adjudication` boundary cannot hold; if that happens, stop and write a design update.

## Task Checklist

### Task 1: Baseline The Current Checkout And Lock The Execution Contract

**Files:**

- Read: `docs/plans/2026-04-20-adjudicated-provider-step-design.md`
- Read/modify as needed: `specs/dsl.md`, `specs/providers.md`, `specs/io.md`, `specs/security.md`, `specs/state.md`, `specs/versioning.md`, `specs/acceptance/index.md`
- Read: existing `orchestrator/workflow/adjudication.py`
- Read: existing `tests/test_adjudicated_provider_*.py`

- [ ] Run the current adjudication test collection:

```bash
pytest --collect-only -q tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py
```

Expected: collection succeeds. If it does not, fix test names/imports before adding behavior.

- [ ] Run the current focused adjudication tests to establish the starting point:

```bash
pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py -v
```

Expected: either pass or expose concrete gaps in the current partial implementation. Record failures in implementation notes before editing runtime code.

- [ ] Compare the specs against the ADR and add missing normative bullets for every current-scope design requirement: DSL validation, path authority, baseline policy, confidentiality, evaluator evidence, selection, failure outcomes, ledger ownership, state, resume, and non-goals.

- [ ] Run the spec-only diff through a quick review before runtime edits:

```bash
git diff -- specs/dsl.md specs/providers.md specs/io.md specs/security.md specs/state.md specs/versioning.md specs/acceptance/index.md
```

Expected: docs/spec changes describe the approved design; they do not introduce implementation-only behavior.

### Task 2: Complete The DSL `2.11` Authored Surface And Loader Validation

**Files:**

- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `tests/test_adjudicated_provider_loader.py`
- Modify: `tests/test_workflow_surface_ast.py`
- Modify: `tests/test_workflow_ir_lowering.py`

- [ ] Add or tighten failing loader tests for all static validation obligations:
  - version gate below `2.11`
  - execution-form mutual exclusivity
  - non-empty unique candidate ids matching the step id token pattern
  - known candidate/evaluator providers in the active workflow namespace
  - candidate prompt override xor rules and unsupported candidate fields
  - evaluator prompt/rubric xor rules
  - required literal `same_trust_boundary`
  - literal positive evidence limits and `max_packet_bytes >= max_item_bytes`
  - exactly one of `expected_outputs` or `output_bundle`
  - required base prompt source unless every candidate overrides it
  - rejected `provider_session`, `output_file`, `output_capture`, and `allow_parse_error`
  - selection and score-ledger static validation
  - rejection of candidate-managed paths depending on `${run.root}`

- [ ] Run the failing-test selector:

```bash
pytest tests/test_adjudicated_provider_loader.py tests/test_workflow_surface_ast.py tests/test_workflow_ir_lowering.py -k "adjudicated or ADJUDICATED" -v
```

Expected: new tests fail only because the validation or typed preservation is incomplete.

- [ ] Implement the loader and AST/IR preservation changes. Keep typed configs as immutable mappings and avoid normalizing adjudicated steps into ordinary provider steps.

- [ ] Re-run:

```bash
pytest tests/test_adjudicated_provider_loader.py tests/test_workflow_surface_ast.py tests/test_workflow_ir_lowering.py -k "adjudicated or ADJUDICATED" -v
```

Expected: pass.

### Task 3: Split The Adjudication Runtime Helpers Into Owned Submodules

**Files:**

- Move/split: `orchestrator/workflow/adjudication.py`
- Create: `orchestrator/workflow/adjudication/__init__.py`
- Create: `orchestrator/workflow/adjudication/models.py`
- Create: `orchestrator/workflow/adjudication/paths.py`
- Create: `orchestrator/workflow/adjudication/baseline.py`
- Create: `orchestrator/workflow/adjudication/evidence.py`
- Create: `orchestrator/workflow/adjudication/scoring.py`
- Create: `orchestrator/workflow/adjudication/ledger.py`
- Create: `orchestrator/workflow/adjudication/promotion.py`
- Create: `orchestrator/workflow/adjudication/resume.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_adjudicated_provider_*.py`

- [ ] Move constants, dataclasses, and small pure helpers into `models.py` and `paths.py`.

- [ ] Move baseline copy/manifest code into `baseline.py`, evidence packet code into `evidence.py`, scorer/evaluator/selection code into `scoring.py`, ledger code into `ledger.py`, promotion code into `promotion.py`, and resume reconciliation primitives into `resume.py`.

- [ ] Re-export the public helper names used by executor/tests from `orchestrator/workflow/adjudication/__init__.py`.

- [ ] Keep the executor importing from `orchestrator.workflow.adjudication` unless a narrower import materially improves clarity.

- [ ] Run:

```bash
pytest --collect-only -q tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py
pytest tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_outcomes.py -v
```

Expected: collection and current helper-level tests pass with the package layout.

### Task 4: Implement Baseline Snapshot, Null-Path Comparison, And Candidate Workspace Copy

**Files:**

- Modify: `orchestrator/workflow/adjudication/baseline.py`
- Modify: `orchestrator/workflow/adjudication/paths.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_adjudicated_provider_baseline.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [ ] Add failing tests for the fixed copy policy:
  - includes regular files, directories, executable bit, hashes, and safe relative symlinks
  - excludes `.orchestrate/`, `.git/`, dependency/cache roots, and local-secret denylist entries
  - rejects absolute, broken, escaping, and excluded-target symlinks
  - does not honor `.gitignore`
  - required excluded paths fail before provider launch
  - optional excluded paths are recorded as absent/excluded
  - physical candidate path under run root still uses logical candidate workspace authority

- [ ] Run:

```bash
pytest tests/test_adjudicated_provider_baseline.py -v
```

Expected: new tests fail for missing policy details only.

- [ ] Implement or tighten baseline manifest creation, sorted included/excluded entries, `baseline_digest`, null-path comparison, and candidate workspace copy from immutable baseline.

- [ ] Wire executor order so consume preflight and parent-side consume materialization happen before baseline creation, and every candidate attempt copies from the same baseline.

- [ ] Re-run:

```bash
pytest tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_runtime.py -k "baseline or candidate_workspace or excluded or symlink" -v
```

Expected: pass.

### Task 5: Execute Candidates With Ordinary Provider Semantics In Candidate Workspaces

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify: `orchestrator/providers/executor.py` only if an execution-result extension is required
- Modify: `tests/test_adjudicated_provider_runtime.py`
- Modify: `tests/test_provider_execution.py` if provider executor compatibility is touched

- [ ] Add failing runtime tests for:
  - candidate provider `cwd` is candidate workspace
  - candidate prompt override changes only the base prompt source
  - step-level dependencies/consumes/output suffix remain uniform across candidates
  - provider params substitution uses candidate context
  - candidate stdout/stderr are logs only and not projected as step output
  - provider failure, timeout, prompt failure, and contract failure map to candidate metadata
  - provider retries start from fresh baseline copies
  - logical `timeout_sec` is not restarted per candidate or retry

- [ ] Run:

```bash
pytest tests/test_adjudicated_provider_runtime.py tests/test_provider_execution.py -k "adjudicated or candidate or timeout or retry or stdout" -v
```

Expected: new tests fail only where candidate execution orchestration is incomplete.

- [ ] Implement candidate execution in the workflow executor. The executor may adapt an adjudicated candidate into an ordinary provider-shaped step for prompt composition and output validation, but the original logical step result must remain adjudicated-only.

- [ ] Persist candidate sidecar metadata after terminal candidate generation states so resume can reconcile candidates without rerunning completed work.

- [ ] Re-run the selector above.

Expected: pass and ordinary provider tests remain unchanged.

### Task 6: Resolve Scorer Identity And Build Complete Evaluation Packets

**Files:**

- Modify: `orchestrator/workflow/adjudication/evidence.py`
- Modify: `orchestrator/workflow/adjudication/scoring.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/security/secrets.py` only if existing secret-value extraction needs a reusable helper
- Modify: `tests/test_adjudicated_provider_scoring.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [ ] Add failing tests for scorer resolution:
  - evaluator provider, params, prompt, optional rubric, evidence limits, confidentiality, and contract versions produce stable `scorer_identity_hash`
  - scorer snapshot persists before first evaluator launch
  - scorer resolution failure persists separate `resolution_failure.json`
  - unresolved scorer blocks required scoring but allows optional-score single candidate promotion

- [ ] Add failing tests for packet evidence:
  - full rendered candidate prompt including output suffix is embedded
  - output value files and required relpath targets are embedded
  - output bundle JSON and required bundle relpath targets are embedded
  - injected consume relpath target content is embedded
  - optional rubric content is embedded
  - non-UTF-8, read error, truncation/size overflow, and declared-secret evidence prevent packet persistence and evaluator launch
  - non-scoring sidecars, stdout/stderr, and bounded previews are not included

- [ ] Run:

```bash
pytest tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py -k "scorer or evidence or packet or secret or rubric" -v
```

Expected: new tests fail for missing scorer/evidence behavior only.

- [ ] Implement scorer snapshot/failure metadata and packet construction. Keep packet construction deterministic and hash canonicalized.

- [ ] Re-run the selector above.

Expected: pass.

### Task 7: Invoke Evaluators, Parse Scores, And Apply Selection Semantics

**Files:**

- Modify: `orchestrator/workflow/adjudication/scoring.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_adjudicated_provider_scoring.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [ ] Add failing tests for:
  - evaluator `cwd` is runtime-owned evaluator workspace
  - evaluator receives reusable prompt plus one `Evaluator Packet` block through normal prompt delivery
  - stdout strict JSON rejects invalid JSON, NaN/Infinity, wrong candidate id, out-of-range score, empty summary, and non-object output
  - evaluator retries reuse the same packet and never rerun the candidate
  - exactly one output-valid candidate with optional score promotes despite scorer/evaluator/evidence failure
  - exactly one output-valid candidate with required score fails without a valid finite score
  - multi-candidate selection fails closed on scorer unavailable or partial scoring
  - all-scored multi-candidate selection chooses highest score and candidate-order ties

- [ ] Run:

```bash
pytest tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py -k "evaluator or selection or score or tie" -v
```

Expected: new tests fail only for evaluator/selection gaps.

- [ ] Implement evaluator launch, retry/deadline integration, JSON parsing, candidate metadata updates, and selection.

- [ ] Re-run the selector above.

Expected: pass.

### Task 8: Materialize Run-Local Ledgers And Terminal Workspace Mirrors

**Files:**

- Modify: `orchestrator/workflow/adjudication/ledger.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_adjudicated_provider_scoring.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [ ] Add failing tests for the normative row schema, nullable fields, `candidate_run_key`, `score_run_key`, candidate statuses, score statuses, selection reasons, and promotion statuses.

- [ ] Add failing tests for mirror semantics:
  - `score_ledger_path` substitution in current frame
  - path must resolve under parent workspace `artifacts/`
  - symlink escapes are rejected
  - static output path collisions fail before candidate launch
  - dynamic relpath target and selected promotion destination collisions fail before promotion
  - existing non-empty mirror must contain valid JSONL with matching owner tuple
  - terminal mirror write happens only after no-selection failure, promotion failure, or committed promotion plus parent validation
  - mirror failure after committed promotion withholds publication and can be retried on resume

- [ ] Run:

```bash
pytest tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_runtime.py -k "ledger or mirror or score_run_key or candidate_run_key or collision" -v
```

Expected: new tests fail for missing ledger/mirror behavior only.

- [ ] Implement ledger row generation from terminal metadata and atomic materialization of run-local and mirror ledgers.

- [ ] Re-run the selector above.

Expected: pass.

### Task 9: Promote Selected Declared Outputs Transactionally

**Files:**

- Modify: `orchestrator/workflow/adjudication/promotion.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_adjudicated_provider_promotion.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [ ] Add failing promotion tests for:
  - non-`relpath` expected output value files
  - `relpath` value files plus required targets
  - output bundle JSON plus required bundle relpath targets
  - duplicate destinations allowed only for exact same source hash and role
  - baseline preimage `file`, `absent`, and `unavailable`
  - parent destination changed since baseline fails before parent writes
  - staging validation before touching parent outputs
  - parent validation after commit
  - rollback restores only transaction-touched files and empty transaction-created directories
  - rollback conflict maps to `promotion_rollback_conflict`
  - resume for `prepared`, `committing`, `rolling_back`, `failed`, and `committed`

- [ ] Run:

```bash
pytest tests/test_adjudicated_provider_promotion.py -v
```

Expected: new tests fail only where promotion transaction semantics are incomplete.

- [ ] Implement promotion manifest/staging/commit/rollback/resume behavior.

- [ ] Re-run:

```bash
pytest tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py -k "promotion or promoted or parent validation or rollback" -v
```

Expected: pass.

### Task 10: Finalize Step State, Publication, Outcomes, And Stdout Suppression

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/dataflow.py`
- Modify: `orchestrator/workflow/outcomes.py`
- Modify: `orchestrator/state.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`
- Modify: `tests/test_adjudicated_provider_outcomes.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_subworkflow_calls.py`

- [ ] Add failing tests that a successful step records:
  - `status: completed`, `exit_code: 0`, completed outcome
  - promoted selected artifacts in normal current-frame artifact state
  - `steps.<Step>.adjudication` with selected id, score/null, selection reason, promotion status, scorer fields, ledger paths, manifest paths, and per-candidate terminal metadata
  - no stdout-derived output fields
  - publication only after promotion commit and terminal ledger/mirror success

- [ ] Add failing tests for terminal failure outcome mapping:
  - no valid candidates
  - scorer unavailable
  - partial scoring
  - timeout
  - ledger path collision
  - ledger conflict
  - ledger mirror failed
  - promotion conflict
  - promotion validation failed
  - promotion rollback conflict
  - adjudication resume mismatch

- [ ] Add call-frame tests proving adjudicated state and artifact lineage remain callee-local unless exported through normal call outputs.

- [ ] Run:

```bash
pytest tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_outcomes.py tests/test_artifact_dataflow_integration.py tests/test_subworkflow_calls.py -k "adjudicated or publish or outcome or output or call_frame" -v
```

Expected: new tests fail only where state/publication/outcome behavior is incomplete.

- [ ] Implement final state block, publication ordering, stdout suppression, and call-frame integration.

- [ ] Re-run the selector above.

Expected: pass.

### Task 11: Implement Resume Reconciliation, Deadline Continuation, And Idempotency

**Files:**

- Create: `tests/test_adjudicated_provider_resume.py`
- Modify: `orchestrator/workflow/adjudication/resume.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [ ] Add resume tests for:
  - no sidecars means a not-yet-started step can create a baseline normally
  - missing baseline with candidate/scorer/packet/ledger sidecars fails `adjudication_resume_mismatch`
  - candidate config hash and composed prompt hash mismatch fail
  - persisted scorer snapshot is reused and current scorer identity mismatch fails
  - persisted scorer-resolution failure is reused and mismatch or later success fails
  - terminal scored/evaluation-failed metadata without matching scorer snapshot fails
  - scorer-unavailable rows without matching failure metadata fail
  - candidate generation resumes into evaluation
  - evaluation resumes into ledger materialization
  - ledger materialization resumes into promotion
  - promotion resumes through manifest status rules
  - committed promotion resumes into terminal ledger/mirror/publication if needed
  - failed candidates are not retried on resume
  - previous visit sidecars block accidental fresh rerun unless the operator explicitly forces rerun through an existing supported force mechanism

- [ ] Run collection for the new test module:

```bash
pytest --collect-only -q tests/test_adjudicated_provider_resume.py
```

Expected: collection succeeds.

- [ ] Run failing resume tests:

```bash
pytest tests/test_adjudicated_provider_resume.py tests/test_resume_command.py -k "adjudicated or resume or mismatch or promotion" -v
```

Expected: new tests fail for missing resume behavior only.

- [ ] Implement resume reconciliation in the adjudication package and executor. Reuse terminal sidecars and regenerate ledgers idempotently instead of appending duplicate rows.

- [ ] Re-run:

```bash
pytest tests/test_adjudicated_provider_resume.py tests/test_resume_command.py tests/test_adjudicated_provider_runtime.py -k "adjudicated or resume or mismatch or timeout" -v
```

Expected: pass.

### Task 12: Add Observability, Report Projection, And Operator-Facing Failure Context

**Files:**

- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/cli/commands/report.py`
- Modify: `orchestrator/workflow/outcomes.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_cli_report_command.py`
- Modify: `tests/test_adjudicated_provider_runtime.py`

- [ ] Add failing tests for status JSON and markdown projection of selected candidate, selected score/null, selection reason, score ledger paths, promotion status, and failure type.

- [ ] Ensure report output does not expose full evaluator packets, score-critical evidence, or candidate stdout/stderr content by default.

- [ ] Run:

```bash
pytest tests/test_observability_report.py tests/test_cli_report_command.py tests/test_adjudicated_provider_runtime.py -k "adjudication or selected_candidate or promotion_status or score_ledger" -v
```

Expected: new tests fail only for missing report projection.

- [ ] Implement projection and rendering.

- [ ] Re-run the selector above.

Expected: pass.

### Task 13: Ship The Shared Evaluator Prompt, Example Workflow, And Docs

**Files:**

- Create/modify: `workflows/library/prompts/adjudication/evaluate_candidate.md`
- Create/modify: `workflows/examples/adjudicated_provider_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_examples_v0.py`

- [ ] Write the shared evaluator prompt so it requests strict JSON with `candidate_id`, `score`, and `summary`, and does not ask the evaluator to read files from paths.

- [ ] Add or update one example workflow that validates under DSL `2.11` and demonstrates:
  - two candidate providers
  - same-trust-boundary evaluator
  - deterministic `expected_outputs` or `output_bundle`
  - selected artifact promotion
  - workspace-visible score ledger mirror under `artifacts/`

- [ ] Update docs to explain authoring guidance, runtime lifecycle, sidecar sensitivity, stdout suppression, and first-release non-goals.

- [ ] Update `docs/index.md` if new durable docs or examples are added, or if existing index entries no longer describe the implemented behavior.

- [ ] Run:

```bash
pytest tests/test_workflow_examples_v0.py -k "adjudicated" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run
```

Expected: tests pass and dry-run validation succeeds.

### Task 14: Final Integration Gate

**Files:**

- All files touched above.

- [ ] Run the complete adjudicated-provider suite:

```bash
pytest tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_scoring.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_resume.py tests/test_adjudicated_provider_outcomes.py -v
```

Expected: pass.

- [ ] Run affected cross-module suites:

```bash
pytest tests/test_workflow_surface_ast.py tests/test_workflow_ir_lowering.py tests/test_provider_execution.py tests/test_artifact_dataflow_integration.py tests/test_subworkflow_calls.py tests/test_resume_command.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_workflow_examples_v0.py -k "adjudicated or provider or output or call or resume or report" -v
```

Expected: pass.

- [ ] Run a broader regression set for loader, contracts, runtime, and examples:

```bash
pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_dependency_injection.py tests/test_provider_integration.py tests/test_workflow_executor_characterization.py tests/test_workflow_output_contract_integration.py tests/test_workflow_examples_v0.py -v
```

Expected: pass.

- [ ] Run the smoke workflow:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/adjudicated_provider_demo.yaml --dry-run
```

Expected: dry-run succeeds. If the smoke is changed from dry-run to a real run, inspect `state.json`, selected promoted files, run-local ledger, workspace-visible mirror, and report output before claiming completion.

## Release Exit Criteria

- DSL `2.11` accepts valid `adjudicated_provider` workflows and rejects invalid authoring shapes at load time.
- Candidate workspaces are copied from one immutable baseline, and orchestrator-managed candidate paths use candidate WORKSPACE authority.
- Output-valid candidates are evaluated from complete same-trust-boundary score-critical evidence packets only.
- Selection follows the approved single-candidate and multi-candidate rules, with no silent demotion of unscored output-valid candidates when a score is required.
- Score ledgers use the normative row schema and idempotency keys; workspace-visible mirrors are terminal, owner-checked, and collision-checked.
- Promotion is transactional, resume-safe, and limited to declared selected outputs.
- `steps.<Step>.adjudication` is additive under state schema `2.1`; stdout-derived step output fields remain absent.
- Resume reconciles persisted adjudication sidecars and fails closed on mismatches.
- Docs/specs/examples describe the implemented first-release contract and its confidentiality/non-goal boundaries.
- All final integration commands above pass with fresh command output.

## Follow-Up Work

The following items are intentionally outside the current first-release scope because the approved design lists them as future extensions, not V1 obligations:

- `max_concurrency` for parallel candidate execution.
- Command evaluators for deterministic score extraction.
- Source-edit candidate promotion through selected patch application.
- Candidate workspace overlays instead of full copies.
- Provider-session support inside candidate workspaces.
- Aggregate score-report tooling over per-run JSONL ledgers.
- Optional aggregate append-only ledger mode with cross-run duplicate reconciliation.
