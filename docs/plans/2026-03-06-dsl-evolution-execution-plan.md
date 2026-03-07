# DSL Evolution Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the DSL evolution ADR as a staged, opt-in extension of the orchestrator without regressing existing `version: "1.4"` workflows.

**Architecture:** Implement the roadmap in dependency order. Start with low-risk gates and typed predicates, then add the runtime/state foundations they depend on, then layer structured statements and reusable subworkflows on top of stable internal identities. Keep legacy `${...}` substitution semantics and current flat-step execution unchanged for existing workflows; new behavior only activates behind new DSL version gates and the new structured `ref:` model.

**Tech Stack:** Python orchestrator runtime, YAML DSL loader/validator, `state.json` persistence, pytest unit/integration coverage, example workflow smoke checks, normative specs under `specs/`, and authoring guidance under `docs/`.

---

## Scope Guardrails

- Preserve `version: "1.4"` behavior exactly unless a workflow opts into the new versioned features.
- Do not reinterpret legacy `${steps.<Name>.*}` semantics inside `for_each`; typed predicates must use structured `ref:` operands.
- Keep lightweight scalar bookkeeping as its own tranche before cycle guards, structured control flow, and `call`.
- Ship state-schema changes, resume behavior, and observability updates together; do not silently reinterpret persisted keys.
- Treat Task 6 as the explicit durable-identity migration boundary: Tasks 2-5 may extend only the current top-level name-keyed state shape, and the move to qualified internal identities must happen via an explicit schema bump plus documented resume invalidation for pre-Task-6 state unless a tested upgrader lands in the same tranche.
- Any tranche that changes report, status, or diagnostic surfaces must update `specs/observability.md` alongside runtime/report code.
- Do not land `call` execution before the accepted-risk reusable-call contract, typed workflow signatures, and source-relative asset taxonomy are specified.
- Keep `call` path handling split between workflow-source-relative assets and workspace-relative runtime writes exactly as described in the ADR.

## Cross-Cutting Risks

- The current executor keys most runtime state by display `name`; stable internal IDs and qualified lineage must land before structured blocks or `call`.
- Typed failure routing is only valid for observable failures; the implementation must not imply failed steps can be inspected after terminal stop behavior.
- Scalar bookkeeping adds a new local-produced-value execution path; it must not bypass declared artifact typing or `publishes.from` lineage rules.
- Resume compatibility becomes fragile as soon as state starts storing counters, frame identities, or lowered helper nodes; every such change needs explicit checksum/resume tests.
- Pre-Task-6 state is intentionally limited to top-level name-keyed semantics; if any earlier tranche starts depending on lowered or nested durable identities, the rollout order is wrong and the task must stop until the Task 6 migration moves earlier.
- Workflow signatures are the boundary contract for top-level inputs now and subworkflow `call` later; they need dedicated end-to-end smoke coverage before `call` depends on them.
- `call` has a dual-identity artifact boundary: exported callee outputs must appear externally as produced by the outer call step while internal provenance, `artifact_versions`, `artifact_consumes`, and `since_last_consume` freshness stay keyed by call-scoped producer/consumer identities.
- Imported workflows can improve reuse before they improve isolation; the first `call` tranche must document that undeclared child-process writes remain an accepted operational risk.

### Task 1: Lock the normative rollout and version/state boundaries

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`

**Step 1: Translate the ADR into concrete feature tranches**

Define the release order and version gates for:
- D1 `assert`
- D2 typed predicates + `ref:` + normalized outcomes
- D2a scalar bookkeeping
- D3 cycle guards
- D4-D6 scoped refs, stable IDs, workflow signatures
- D7 structured `if/else`
- D8 structured `finally`
- D9 accepted-risk reusable-call contract
- D10 imports + `call`
- D11 `match`
- D12 `repeat_until`
- D13 linting / normalization
- D14 score-aware gates

Keep the new `ref:` model opt-in and explicitly separate from legacy `${...}` interpolation.

**Step 2: Define the state schema changes before touching runtime code**

Document which tranches require `schema_version` updates, new persisted counters, qualified step identities, local produced values, finalization progress, workflow/call output-export progress, call-frame metadata, bound workflow inputs, and versioned artifact-state changes for call-scoped producer/consumer identities. State exactly which fields are presentation-only versus durable lineage/resume keys, including the split between caller-visible call outputs, external producer identity, preserved internal provenance, and qualified freshness bookkeeping.

Lock the migration policy here instead of leaving it implicit:
- Tasks 2-5 may append fields under the existing top-level name-keyed schema only for features that remain top-level and pre-lowering.
- Task 6 is the first tranche allowed to change durable producer/consumer/resume keys, and it must do so behind an explicit schema bump that does not promise in-place upgrade or resume continuity from pre-Task-6 state unless a tested upgrader ships in the same tranche.

**Step 3: Add acceptance coverage entries for every new invariant and map them to later executable proof**

Add acceptance cases for:
- `assert_failed` vs contract/preflight failures
- statically invalid `ref:` targets
- load-time rejection of `ref:` operands that target provably multi-visit steps in the first D2 tranche
- statically provable predicate type errors, including `artifact_bool` against non-`bool` artifacts and ordered comparisons against non-numeric / `relpath` / `enum` operands
- runtime-only predicate failures
- scalar local-value typing and `publishes.from` composition
- `max_visits` / `max_transitions` resume behavior
- explicit schema-boundary behavior between pre-Task-6 name-keyed state and post-Task-6 qualified-identity state, including documented resume rejection unless a tested upgrader exists
- top-level workflow input binding / output export
- workflow-output export contract failures for missing `from`, unresolved sources, and type-invalid or invalid-`relpath` exports
- top-level output export withholding until finalization completes, plus suppression on finalization failure
- branch/block output visibility
- `call` export boundaries and relative-path taxonomy
- reusable-workflow rejection when DSL-managed write roots stay hard-coded instead of being surfaced as typed `relpath` inputs
- call-site rejection for missing required write-root bindings or aliased per-invocation write roots where concurrent/repeated calls would collide
- caller-visible `call` producer identity plus preserved callee-internal provenance
- callee-private `context` defaults staying isolated from caller state unless explicitly bound or exported
- call-scoped `artifact_versions`, `artifact_consumes`, and `since_last_consume` freshness across call frames
- callee output export withholding until callee finalization completes, plus suppression on callee finalization failure

For each acceptance addition, point to the later task and verification block that will make the invariant executable so Task 1 locks the rollout contract and ownership boundaries without pretending the docs-only tranche has already proven runtime behavior.

**Verification:**

Run:
```bash
pytest tests/test_loader_validation.py -k "version or unknown or for_each" -v
pytest tests/test_workflow_examples_v0.py -k for_each_demo -v
```

Before moving to Task 2, cross-check that every new acceptance item added here is referenced by a later task's test or smoke coverage block.

Risk focus: avoid documenting semantics the current runtime cannot actually enforce, and avoid claiming Task 1 verification proves more than rollout/version-boundary stability.

### Task 2: Land D1 with first-class `assert` / gate steps

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/conditions.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/state.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/acceptance/index.md`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_conditional_execution.py`
- Modify: `tests/test_observability_report.py`
- Create: `workflows/examples/assert_gate_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Write failing loader and runtime tests**

Cover:
- `assert` schema exclusivity against `provider` / `command` / `wait_for` / `for_each`
- reuse of the current `equals|exists|not_exists` condition surface
- false assertions failing with `exit_code: 3` and `error.type: "assert_failed"`
- `on.failure.goto` recovery from assertion failure

**Step 2: Implement loader validation and executor support**

Add an `assert` step kind that evaluates a condition without shelling out. Record the result as a normal step result and keep contract/preflight failures on exit code `2`.

**Step 3: Keep observability and state output explicit**

Persist enough structured error context for reports and status output to distinguish assertion failures from validation or command failures, and document that diagnostic surface in `specs/observability.md`. Do not add synthetic artifact publishing in this tranche.

**Step 4: Add one example workflow and smoke coverage**

Use a minimal example that demonstrates approval/revise gating without shell glue and add it to the example-workflow test module.

**Verification:**

Run:
```bash
pytest tests/test_loader_validation.py tests/test_conditional_execution.py tests/test_runtime_step_lifecycle.py tests/test_observability_report.py -k "assert or gate" -v
pytest tests/test_workflow_examples_v0.py -k assert_gate -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/assert_gate_demo.yaml --dry-run
```

Risk focus: do not let `assert` silently drift into a general expression language.

### Task 3: Land D2 typed predicates, structured `ref:` operands, and normalized outcomes

**Files:**
- Create: `orchestrator/workflow/references.py`
- Create: `orchestrator/workflow/predicates.py`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/conditions.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Create: `tests/test_typed_predicates.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_conditional_execution.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_observability_report.py`
- Create: `workflows/examples/typed_predicate_routing.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Write failing tests for the new predicate surface**

Cover:
- `artifact_bool`
- `compare` with `eq|ne|lt|lte|gt|gte`
- `all_of|any_of|not`
- root-scoped `ref: root.steps.<Step>...`
- load-time rejection of `ref:` operands that point at provably multi-visit or otherwise ambiguous step identities
- static type rejection for `artifact_bool` on non-`bool` artifacts and ordered comparisons on non-numeric / `relpath` / `enum` operands
- statically invalid refs rejected at load time
- runtime-only missing values producing structured predicate failures
- the normalized outcome matrix for command failure, provider failure, timeout, contract/preflight failure, and undefined-substitution-at-step-execution
- legacy `version: "1.4"` `for_each` workflows keeping `${steps.<Name>.*}` loop-local substitution unchanged while typed `ref:` remains opt-in and version-gated

**Step 2: Add normalized outcome projection and make the matrix executable**

Project step results into:
- `outcome.status`
- `outcome.phase`
- `outcome.class`
- `outcome.retryable`

Keep this projection available only for observable step results, document the normalization matrix in the spec, and add direct test coverage that each documented tuple maps to the expected normalized outcome fields.

**Step 3: Enforce the first-tranche safety boundary in the loader**

Typed predicates must resolve structured refs directly and must not reuse `${...}` string substitution. In the first tranche, allow only root-scoped single-visit step refs plus literals, reject provably multi-visit targets at load time, and fail statically provable predicate type mismatches during workflow validation instead of deferring them to runtime.

**Step 4: Surface the new fields in reports and examples**

Update status rendering so tests can assert on normalized outcomes and add an example workflow that routes on a typed artifact or recovered failure outcome.

**Verification:**

Run:
```bash
pytest --collect-only tests/test_typed_predicates.py -q
pytest tests/test_typed_predicates.py tests/test_loader_validation.py tests/test_conditional_execution.py tests/test_runtime_step_lifecycle.py tests/test_for_each_execution.py tests/test_observability_report.py -v
pytest tests/test_workflow_examples_v0.py -k "typed_predicate or for_each_demo" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --dry-run
```

Risk focus: keep the first `ref:` rollout narrow enough that multi-visit ambiguity cannot leak into runtime behavior.

### Task 4: Land D2a lightweight scalar bookkeeping as a dedicated runtime primitive

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Create: `tests/test_scalar_bookkeeping.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Create: `workflows/examples/scalar_bookkeeping_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Write failing tests for scalar-local value production**

Cover:
- `set_scalar`
- `increment_scalar`
- one scalar-emission path for producing a local typed artifact without shelling out
- undeclared-artifact rejection and runtime type mismatch failures
- `publishes.from` advancing top-level lineage while direct registry mutation stays impossible

**Step 2: Implement the new execution and state semantics**

Add a narrow runtime primitive for scalar bookkeeping, persist local produced values in the same durable/result surfaces as other step outputs, and document the resulting debug/reporting shape in `specs/observability.md`.

**Step 3: Add an example that proves bookkeeping composes with publication**

Use a minimal loop-free example that initializes, increments, and publishes a scalar artifact so the smoke test covers both local value production and `publishes.from`.

**Verification:**

Run:
```bash
pytest --collect-only tests/test_scalar_bookkeeping.py -q
pytest tests/test_scalar_bookkeeping.py tests/test_loader_validation.py tests/test_artifact_dataflow_integration.py tests/test_runtime_step_lifecycle.py -v
pytest tests/test_workflow_examples_v0.py -k scalar_bookkeeping -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/scalar_bookkeeping_demo.yaml --dry-run
```

Risk focus: keep this as a typed, declared-artifact primitive, not a second general-purpose mutation channel.

### Task 5: Land D3 cycle guards with resume-safe persisted counters

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Create: `tests/test_control_flow_foundations.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_retry_behavior.py`
- Create: `workflows/examples/cycle_guard_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Write failing tests for `max_transitions` and `max_visits`**

Cover:
- skips not consuming visit budget
- retries not consuming additional visit budget
- back-edge loops consuming transition budget
- counter persistence across resume
- deterministic failure shape when a guard trips

**Step 2: Extend state and executor together**

Persist workflow-level transition counts and per-step visit counts in `state.json`, update them at the exact control-transfer points defined in the ADR, and make resume reload them instead of recomputing them from prior results. Keep these counters inside the pre-Task-6 top-level name-keyed schema only; do not introduce partial qualified lineage keys or imply those counters auto-upgrade across the Task 6 identity migration.

**Step 3: Keep the first tranche top-level only**

Reject or defer nested/lowered guard usage until stable internal IDs exist. The initial implementation should work only for the pre-lowering top-level step graph.

**Verification:**

Run:
```bash
pytest --collect-only tests/test_control_flow_foundations.py -q
pytest tests/test_control_flow_foundations.py tests/test_state_manager.py tests/test_resume_command.py tests/test_retry_behavior.py -k "max_visits or max_transitions" -v
pytest tests/test_workflow_examples_v0.py -k cycle_guard -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --state-dir /tmp/dsl-evolution-cycle-guard-demo
```

Risk focus: counter semantics must stay stable under retry, skip, and resume or the feature will be unusable in real loops.

### Task 6: Build the D4-D6 foundations: scoped refs, stable internal step IDs, and typed workflow signatures

**Files:**
- Create: `orchestrator/workflow/identity.py`
- Create: `orchestrator/workflow/signatures.py`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/variables/substitution.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/contracts/output_contract.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/variables.md`
- Modify: `specs/cli.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_at65_loop_scoping.py`
- Modify: `tests/test_cli_safety.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_control_flow_foundations.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_output_contract.py`
- Modify: `tests/test_workflow_output_contract_integration.py`
- Create: `workflows/examples/workflow_signature_demo.yaml`
- Create: `workflows/examples/inputs/workflow_signature_demo.json`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Write failing tests for identity and scope rules**

Cover:
- `root` / `self` / `parent` ref requirements
- bare `steps.<Name>` being invalid in the new `ref:` model
- authored `id` shape and uniqueness validation, plus version-gated migration rules for introducing it
- stable `step_id` persistence across sibling insertion when authored IDs are preserved
- compiler-generated IDs being checksum-stable only until the workflow file changes
- qualified lineage keys for `for_each` iterations
- explicit resume rejection at the schema boundary when post-Task-6 code loads pre-Task-6 name-keyed state, unless the same tranche adds a tested upgrader
- legacy `version: "1.4"` `${steps.<Name>.*}` loop-local substitution remaining unchanged in existing `for_each` workflows after scoped refs and typed `inputs` land
- typed `inputs` visibility through both `${inputs.<name>}` and structured `ref:`
- persisted bound inputs being available after resume reload

**Step 2: Introduce a stable internal identity model**

Add the optional authored stable `id` surface in the loader/spec, validate its shape and uniqueness independently from display `name`, assign internal `step_id` values during validation/lowering, and derive those internal identities from authored IDs where present. Keep display `name` for UX, document the checksum-only stability boundary for compiler-generated IDs, and move lineage/freshness bookkeeping to qualified internal identities instead of bare display names.

This tranche is also the explicit schema boundary for durable identity migration: bump the persisted state schema, reject resume from pre-Task-6 name-keyed state rather than silently remapping old lineage/freshness keys, and only add an upgrader if it is fully specified and covered by targeted state-manager/resume tests in this same task.

**Step 3: Add typed workflow `inputs` / `outputs` plus the normative read surfaces**

Reuse the existing artifact-contract validators where possible, but keep workflow signatures as a separate boundary contract family. Make `inputs.<name>` readable through both `${inputs.<name>}` and typed `ref:` resolution, update substitution to recognize the new namespace, and document the variables-spec boundary instead of leaving `inputs` implicit in the DSL spec alone.

**Step 4: Bind and validate top-level workflow inputs before execution starts**

Define the first concrete top-level input binding path in CLI/runtime terms. Extend the run path so top-level runs can bind typed workflow `inputs` from explicit CLI data and/or a file-backed input source, validate those values before execution starts, persist the bound inputs in run state for observability/resume, and keep legacy `context` semantics unchanged for backward compatibility.

**Step 5: Add direct end-to-end signature verification before `call` depends on it**

Create one example workflow that consumes a bound input and exports a typed output, then cover the same path in targeted tests so the verification evidence proves input binding, output export timing, persisted bound inputs across resume, and contract-style failures for missing `outputs[*].from`, unresolved export sources, and invalid typed or `relpath` output exports.

**Step 6: Keep resume behavior explicit**

If checksum-changing edits still invalidate resume, preserve that rule and document it. Do not imply cross-checksum resume compatibility just because internal IDs exist.

**Verification:**

Run:
```bash
pytest tests/test_loader_validation.py tests/test_control_flow_foundations.py tests/test_state_manager.py tests/test_cli_safety.py tests/test_resume_command.py -k "step_id or scoped_ref or inputs or outputs or bound_inputs or schema" -v
pytest tests/test_artifact_dataflow_integration.py tests/test_for_each_execution.py tests/test_at65_loop_scoping.py -k "legacy or qualified or lineage or freshness or for_each or loop_scoping" -v
pytest tests/test_output_contract.py tests/test_workflow_output_contract_integration.py -v
pytest tests/test_workflow_examples_v0.py -k "workflow_signature or for_each_demo" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/workflow_signature_demo.yaml --input-file workflows/examples/inputs/workflow_signature_demo.json --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/workflow_signature_demo.yaml --input-file workflows/examples/inputs/workflow_signature_demo.json --state-dir /tmp/dsl-evolution-workflow-signature-demo
```

Risk focus: this is the foundation for every later structured feature; do not ship `call` or structured blocks before these invariants hold.

### Task 7: Add a structured statement layer with `if/else`

**Files:**
- Create: `orchestrator/workflow/statements.py`
- Create: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Create: `tests/test_structured_control_flow.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_resume_command.py`
- Create: `workflows/examples/structured_if_else_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Write failing tests for block semantics**

Cover:
- branch-local visibility rules
- block outputs
- explicit recording of non-taken branches
- conservative rejection of `goto` / `_end` escaping structured boundaries
- interrupted execution resuming at the correct lowered node without replaying completed branch work
- durable lowered-node identity/state shape staying stable across resume reload

**Step 2: Lower structured statements to executable nodes with stable IDs**

Keep lowering explicit instead of pretending the new syntax is state-transparent. The lowered nodes should carry stable identities into logs, status output, and resume state.

**Step 3: Keep the rollback boundary narrow**

Do not couple `if/else` rollout to finalization state. The first structured-control tranche should ship only branch semantics, block outputs, and lowering/debug identity rules so failures can be isolated to the statement layer without mixing in teardown behavior.

**Step 4: Make resume evidence explicit for lowered structured execution**

Add targeted state-manager and resume-command coverage that interrupts a real run after entry into a lowered branch, verifies the persisted lowered identities/state shape, and resumes from the first unfinished lowered node instead of replaying completed branch work.

**Verification:**

Run:
```bash
pytest --collect-only tests/test_structured_control_flow.py -q
pytest tests/test_structured_control_flow.py tests/test_state_manager.py -k "if_else or lowered" -v
pytest tests/test_resume_command.py -k "if_else and resume" -v
pytest tests/test_workflow_examples_v0.py -k structured_if_else -v
pytest tests/test_workflow_examples_v0.py -k for_each_demo -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/structured_if_else_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
pytest tests/test_resume_command.py -k structured_if_else_smoke -v
```

Risk focus: structured lowering must not create ambiguous state entries, hidden control transfers, or resume-time replay of completed lowered nodes.

### Task 8: Add structured finalization (`finally`) as a separate tranche

**Files:**
- Modify: `orchestrator/workflow/statements.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `tests/test_structured_control_flow.py`
- Modify: `tests/test_resume_command.py`
- Create: `workflows/examples/finally_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Write failing tests for finalization-only invariants**

Cover:
- `finally` running once after both success and failure of the guarded region
- resuming from the first unfinished finalization step instead of replaying completed cleanup
- primary guarded failure remaining primary when `finally` also fails
- dedicated failure classification when the guarded region succeeds and `finally` fails
- top-level workflow outputs staying unmaterialized until finalization completes successfully
- top-level workflow outputs being suppressed when finalization fails

**Step 2: Extend lowering and state with explicit finalization progress**

Record finalization progress and workflow-output export progress in durable state, surface the structured diagnostics in reports, and keep finalization identities distinct from the main body so resume/debug output is not ambiguous. Wire top-level workflow output materialization to occur only after successful finalization and suppress exports on finalization failure.

**Step 3: Keep rollback and verification independent from `if/else`**

Treat `finally` as a separate release boundary with its own example and regression checks. If finalization semantics slip, the `if/else` tranche remains independently shippable.

**Verification:**

Run:
```bash
pytest tests/test_structured_control_flow.py tests/test_resume_command.py -k finally -v
pytest tests/test_workflow_examples_v0.py -k finally -v
pytest tests/test_workflow_examples_v0.py -k for_each_demo -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/finally_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/finally_demo.yaml --state-dir /tmp/dsl-evolution-finally-demo
```

Risk focus: finalization must be resume-idempotent and must not silently replace the guarded region's primary result.

### Task 9: Lock the accepted-risk reusable-call contract before execution work

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/dependencies.md`
- Modify: `specs/providers.md`
- Modify: `specs/io.md`
- Modify: `specs/security.md`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/workflow_drafting_guide.md`

**Step 1: Specify the source-relative versus workspace-relative path taxonomy**

Document the dedicated source-relative asset surface for reusable workflows, and explicitly keep runtime write paths and existing workspace-relative authored paths separate from imported-library assets.

**Step 2: Specify the accepted operational-risk boundary**

Document the first `call` tranche as inline and non-isolating, require every DSL-managed reusable-workflow write root to be surfaced as a typed `relpath` input, require call sites to bind distinct per-invocation write roots where repeated/concurrent calls could alias the same managed paths, and state that undeclared child-process filesystem effects remain an accepted risk rather than a loader-proved invariant. If the existing registry/pointer state cannot represent call-scoped internal producer/consumer identities cleanly, schedule the explicit versioned artifact-state change here instead of deferring it into Task 10 implementation.

**Step 3: Add acceptance coverage for the contract boundary**

Add normative acceptance entries covering caller/callee version compatibility, typed `with:` binding against callee inputs, declared-output export boundaries, reusable-workflow rejection when managed write roots are hard-coded instead of parameterized typed `relpath` inputs, call-site rejection for missing or colliding required write-root bindings, caller-visible external producer identity for exported call outputs, preserved callee-internal provenance metadata, private callee `providers`, `artifacts`, and `context` defaults unless explicitly bound or exported, call-scoped `artifact_versions` / `artifact_consumes` / `since_last_consume` freshness bookkeeping, callee output export timing after callee finalization, and the diagnostic/reporting surfaces expected for call frames.

**Verification:**

Run:
```bash
pytest tests/test_loader_validation.py -k "call or import or version" -v
```

Risk focus: do not hide operational-risk boundaries inside implementation details; make them explicit before runtime work starts.

### Task 10: Land imports and `call` on top of typed boundaries and qualified identities

**Files:**
- Modify: `orchestrator/loader.py`
- Create: `orchestrator/workflow/assets.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/signatures.py`
- Modify: `orchestrator/workflow/identity.py`
- Modify: `orchestrator/deps/resolver.py`
- Modify: `orchestrator/deps/injector.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/security/secrets.py`
- Modify: `specs/dsl.md`
- Modify: `specs/dependencies.md`
- Modify: `specs/providers.md`
- Modify: `specs/io.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/security.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/workflow_drafting_guide.md`
- Create: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_dependency_resolution.py`
- Modify: `tests/test_dependency_injection.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_provider_execution.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_secrets.py`
- Modify: `tests/test_state_manager.py`
- Create: `workflows/library/review_fix_loop.yaml`
- Create: `workflows/examples/call_subworkflow_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Write failing tests for import and call boundaries**

Cover:
- imported workflows validating independently
- caller/callee same-version requirement in the first tranche
- typed `with:` binding against callee inputs
- reusable-workflow rejection when DSL-managed write roots remain fixed instead of parameterized typed `relpath` inputs
- call-site rejection when required write-root inputs are missing or when repeated/concurrent calls bind colliding managed paths
- caller-visible outputs surfacing as `steps.<CallStep>.artifacts.<name>`
- exported call outputs entering caller-visible lineage with the outer call step as the external producer
- preserved callee-internal provenance and qualified `artifact_versions` / `artifact_consumes` / `since_last_consume` bookkeeping inside the call frame
- private provider/artifact/context namespaces and callee-default isolation inside the call frame
- callee outputs materializing only after callee finalization completes successfully, and staying absent if callee finalization fails
- explicit source-relative asset resolution via a dedicated asset surface distinct from workspace-relative runtime paths
- preservation of workspace-relative semantics for legacy runtime path fields under `call`
- rejection of asset-path traversal outside the imported workflow source tree

**Step 2: Define the import-path taxonomy and concrete source-relative asset API**

Implement the source-relative asset fields and version/boundary rules documented in Task 9. Keep authored workspace-relative runtime paths (`input_file`, `depends_on`, `output_file`, deterministic relpath outputs, bundle paths) distinct from workflow-source-relative library assets. Do not overload `input_file` or plain `depends_on` with import-local semantics.

**Step 3: Implement import loading, asset resolution, and call-frame execution**

Keep `call` inline within the same run, but record call-frame-local identities in state and logs. Route workflow-source-relative asset loads through the new asset resolver, update provider prompt loading plus dependency resolution/content reads so they use the correct source/workspace base for the new fields, preserve private callee `context` defaults unless the call contract explicitly binds or exports them, and keep only declared callee outputs crossing the boundary into the caller. Export those outputs only after the callee body and any callee finalization succeed, surface the outer call step as the external producer for caller-visible artifacts, and preserve call-scoped internal provenance plus freshness bookkeeping under qualified identities.

**Step 4: Make resume/export evidence explicit for nested call frames**

Add targeted state-manager and resume-command coverage that interrupts a real run inside a call frame, verifies persisted call-frame identities plus deferred export state, and resumes without replaying completed callee work or leaking caller-visible outputs before callee finalization completes.

**Step 5: Make the operational-risk boundary explicit**

Do not promise loader-enforced proof of child-process filesystem effects. Enforce the managed-write-root contract the runtime can actually check: reusable workflows must expose DSL-managed write roots as typed `relpath` inputs, and call sites must bind non-colliding values for those inputs when multiple invocations could share a workspace. Document the remaining risk in the spec and authoring guide.

**Verification:**

Run:
```bash
pytest --collect-only tests/test_subworkflow_calls.py -q
pytest tests/test_subworkflow_calls.py tests/test_loader_validation.py tests/test_artifact_dataflow_integration.py tests/test_state_manager.py tests/test_resume_command.py -k "call or call_frame or resume" -v
pytest tests/test_dependency_resolution.py tests/test_dependency_injection.py tests/test_prompt_contract_injection.py tests/test_provider_execution.py tests/test_provider_integration.py tests/test_secrets.py -k "asset or import or call or path or context" -v
pytest tests/test_workflow_examples_v0.py -k call_subworkflow -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --state-dir /tmp/dsl-evolution-call-subworkflow-demo
pytest tests/test_resume_command.py -k call_subworkflow_smoke -v
```

Risk focus: keep caller-visible artifact/state names simple while retaining qualified internal provenance underneath, preserve the source-relative/workspace-relative path boundary exactly, and do not let resume replay or prematurely export nested call outputs.

### Task 11: Add `match` as a separate structured-control tranche

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/predicates.py`
- Modify: `orchestrator/workflow/statements.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `tests/test_structured_control_flow.py`
- Modify: `tests/test_loader_validation.py`
- Create: `workflows/examples/match_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add `match` over typed refs**

Write tests and implementation for enum branching over typed refs, reusing the same block/output and stable-ID rules as `if/else`.

**Step 2: Keep example and verification distinct from loops**

Add a dedicated `match` example and keep its smoke check separate so regressions in enum branching are not hidden inside later loop work.

**Verification:**

Run:
```bash
pytest tests/test_loader_validation.py tests/test_structured_control_flow.py -k match -v
pytest tests/test_workflow_examples_v0.py -k match_demo -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/match_demo.yaml --dry-run
```

Risk focus: `match` should remain a structured enum branch primitive, not a generic pattern-matching language.

### Task 12: Add post-test `repeat_until` as its own loop tranche

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/statements.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/observability.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `tests/test_structured_control_flow.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_loader_validation.py`
- Create: `workflows/examples/repeat_until_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add post-test `repeat_until`**

Keep iteration outputs explicit on the loop frame, require post-test semantics, and store enough iteration/condition-evaluation state for resume to continue safely.

**Step 2: Verify loop resume and diagnostics directly**

Cover iteration index persistence, condition-evaluation replay safety, and loop-frame reporting so this tranche has its own state and observability evidence.

**Verification:**

Run:
```bash
pytest tests/test_loader_validation.py tests/test_structured_control_flow.py tests/test_resume_command.py -k repeat_until -v
pytest tests/test_workflow_examples_v0.py -k repeat_until -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --state-dir /tmp/dsl-evolution-repeat-until-demo
```

Risk focus: keep loop refs constrained to declared loop-frame outputs so multi-visit inner-step ambiguity does not leak back in.

### Task 13: Add authoring-time linting and normalization after the new syntax exists

**Files:**
- Create: `orchestrator/workflow/linting.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/cli.md`
- Modify: `specs/versioning.md`
- Modify: `docs/workflow_drafting_guide.md`
- Create: `tests/test_dsl_linting.py`
- Modify: `tests/test_cli_report_command.py`

**Step 1: Add authoring-time lint rules**

Start with warnings for:
- shell gates that should become `assert`
- stringly `when.equals` that should become typed predicates
- raw `goto` diamonds that should become `if` / `match`
- import/output collisions

**Step 2: Keep linting advisory in the first pass**

Expose lint results in report or dry-run output without turning them into hard validation failures until the rule set is proven stable.

**Verification:**

Run:
```bash
pytest --collect-only tests/test_dsl_linting.py -q
pytest tests/test_dsl_linting.py tests/test_cli_report_command.py -v
```

Risk focus: linting should accelerate migration without blocking valid legacy workflows.

### Task 14: Add score-aware gates on top of the stable predicate system

**Files:**
- Modify: `orchestrator/workflow/predicates.py`
- Modify: `orchestrator/loader.py`
- Modify: `specs/dsl.md`
- Modify: `specs/versioning.md`
- Modify: `docs/workflow_drafting_guide.md`
- Create: `tests/test_score_gates.py`
- Modify: `tests/test_structured_control_flow.py`
- Create: `workflows/examples/score_gate_demo.yaml`
- Modify: `workflows/README.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add score-threshold helpers without creating a parallel routing model**

Standardize numeric-threshold gates and optional score-band decisions on top of the existing typed predicate system rather than inventing a separate control-flow surface.

**Step 2: Add one focused example and test surface**

Use a dedicated score-gate example so benchmark-oriented authoring guidance stays separate from general `match` and loop behavior.

**Verification:**

Run:
```bash
pytest --collect-only tests/test_score_gates.py -q
pytest tests/test_score_gates.py tests/test_structured_control_flow.py -v
pytest tests/test_workflow_examples_v0.py -k score_gate -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/score_gate_demo.yaml --dry-run
```

Risk focus: keep score helpers as thin predicate sugar over typed numeric artifacts.

### Task 15: Run the final compatibility and smoke sweep before merge

**Files:**
- No file changes

**Step 1: Re-run the targeted unit and integration suites**

Run:
```bash
pytest tests/test_loader_validation.py \
       tests/test_conditional_execution.py \
       tests/test_runtime_step_lifecycle.py \
       tests/test_typed_predicates.py \
       tests/test_retry_behavior.py \
       tests/test_state_manager.py \
       tests/test_resume_command.py \
       tests/test_artifact_dataflow_integration.py \
       tests/test_for_each_execution.py \
       tests/test_at65_loop_scoping.py \
       tests/test_output_contract.py \
       tests/test_workflow_output_contract_integration.py \
       tests/test_dependency_resolution.py \
       tests/test_dependency_injection.py \
       tests/test_prompt_contract_injection.py \
       tests/test_provider_execution.py \
       tests/test_provider_integration.py \
       tests/test_secrets.py \
       tests/test_structured_control_flow.py \
       tests/test_subworkflow_calls.py \
       tests/test_observability_report.py \
       tests/test_dsl_linting.py \
       tests/test_scalar_bookkeeping.py \
       tests/test_score_gates.py \
       tests/test_cli_safety.py \
       tests/test_workflow_examples_v0.py -v
```

**Step 2: Re-run existing orchestrator smoke checks to prove legacy compatibility**

Run:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run
```

**Step 3: Re-run one new-DSL smoke example from each major tranche**

Run the dry-run commands from Tasks 2, 3, 4, 7, 11, and 14, and run the isolated real orchestrator commands from Tasks 5, 6, 8, 10, and 12. The evidence set must therefore include real execution output for cycle guards, workflow signatures, finalization, subworkflow calls, and loops alongside validation-only smoke checks for the syntax-heavy tranches and the legacy compatibility smoke check.

**Completion criteria:**

- Legacy `1.4` examples still validate and targeted tests pass.
- Normalized outcome routing and legacy `${steps.<Name>.*}` loop-local substitution are both revalidated in the final sweep.
- Each new tranche has spec coverage, implementation coverage, and at least one example workflow smoke check; stateful tranches also have at least one isolated real orchestrator run.
- State-schema changes are paired with resume tests and explicit documentation updates.
- Shared primitives touched by foundational or `call` tranches (`output_contract`, provider execution) are revalidated in the final sweep.
- No feature depends on ambiguous multi-visit refs or bare step-name lineage keys.
