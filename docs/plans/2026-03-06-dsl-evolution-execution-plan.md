# DSL Evolution Remaining Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the remaining ADR-defined DSL evolution work in this repo after the already-shipped `v1.5`/`v1.6` gate and typed-predicate tranches, without regressing existing `v1.4` through `v1.6` workflows.

**Architecture:** Keep the rollout in three dependency layers. First extend the current flat executor only with top-level runtime primitives that preserve the pre-`v2` name-keyed state shape (`scalar` bookkeeping, then cycle guards). Next ship the explicit `v2.0` identity boundary: stable step IDs, qualified lineage/freshness, scoped refs, and typed workflow signatures. Only after that foundation lands should the loader/executor gain a structured statement IR and lowering path for `if/else`, `finally`, and inline `call`, with the reusable-call risk contract and source-relative import handling defined before runtime work starts.

**Tech Stack:** Python orchestrator runtime, strict YAML loader/validator, `state.json` persistence, pytest unit/integration coverage, workflow example smoke checks, normative specs under `specs/`, and authoring/runtime docs under `docs/`.

---

## Current Baseline

- `assert` gates are already present in `orchestrator/loader.py`, `orchestrator/workflow/executor.py`, `orchestrator/workflow/conditions.py`, `specs/dsl.md`, `specs/versioning.md`, `tests/test_runtime_step_lifecycle.py`, and `workflows/examples/assert_gate_demo.yaml`.
- Typed predicates, structured `ref:`, and normalized outcomes are already present in `orchestrator/workflow/predicates.py`, `orchestrator/workflow/references.py`, `orchestrator/workflow/executor.py`, `specs/dsl.md`, `specs/state.md`, `specs/versioning.md`, `tests/test_typed_predicates.py`, and `workflows/examples/typed_predicate_routing.yaml`.
- This plan does not reopen the shipped `D1`/`D2` runtime unless later tasks require narrow regression additions around those surfaces.

## Scope Guardrails

- Preserve `version: "1.4"` behavior exactly unless a workflow opts into a newer version gate.
- Keep legacy `${steps.<Name>.*}` semantics inside `for_each` unchanged until the explicit `v2.0` scoped-ref and stable-ID migration lands.
- Treat `v2.0` as the first durable state/lineage identity boundary. Pre-`v2.0` work may add fields to the current top-level name-keyed state, but must not silently change durable producer/consumer keys.
- Do not ship nested structured control flow or `call` until stable internal IDs, scoped refs, and typed workflow signatures exist together.
- Do not claim loader-enforced filesystem isolation for reusable subworkflows. The ADR only supports an accepted-risk first tranche.
- Keep this landing plan scoped to the ADR's core execution model through reusable `call` (`D2a` through `D9`). `match`, `repeat_until`, score-aware gates, and lint/normalization stay documented follow-ons after the primary control-flow-and-reuse substrate is in place.
- If a task adds or renames tests, run `pytest --collect-only` on those modules before broader verification.
- Any task that changes workflow semantics, prompts, contracts, or examples must include at least one orchestrator example smoke check in addition to pytest selectors.

## Cross-Cutting Risks

- The executor and artifact ledgers still key most durable state by display `name`; that makes resume, freshness, and nested lowering unsafe until the `v2.0` identity migration is complete.
- Cycle guards are resume-sensitive. Incorrect counter update points will either under-protect loops or break legitimate retries/resume.
- Workflow signatures and finalization interact: output export timing must be implemented behind a single completion hook so `finally` can delay export without another state rewrite.
- Call frames need dual provenance: caller-visible outputs must appear produced by the outer call step, while internal lineage and freshness stay keyed by qualified callee identities.
- Imported workflow path semantics split into workflow-source-relative reference assets and workspace-relative runtime writes. Mixing those semantics in one resolver will create subtle regressions.

### Task 1: Rebaseline the Roadmap Against the Current Repo

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `workflows/README.md`

**Step 1: Mark shipped vs planned ADR tranches**

Update the docs so `D1`/`D2` are described as current behavior and `D2a` through `D9` are described as planned tranches with explicit version gates. Keep the `v1.5` and `v1.6` wording aligned with the implementation already in-tree.

**Step 2: Lock the remaining version and schema boundaries**

Document that:
- `v1.7` is reserved for scalar bookkeeping.
- `v1.8` is reserved for cycle guards.
- `v2.0` is the first schema/identity migration and includes stable IDs, qualified lineage/freshness, scoped refs, and typed workflow signatures.
- Tasks 4 and 5 are two implementation checkpoints for that same `v2.0` boundary; do not treat the state/identity half as a separately shippable version.
- `v2.1` through `v2.4` cover `if/else`, `finally`, the reusable-call contract plus source-relative asset fields, and `call`.

Make the pre-`v2.0` versus post-`v2.0` durability boundary explicit in `specs/state.md`, `specs/versioning.md`, and `specs/acceptance/index.md`.

**Step 3: Add acceptance placeholders for every remaining invariant**

Add planned acceptance bullets for:
- scalar bookkeeping typing, top-level declared-artifact targeting, and `publishes.from`-only registry mutation
- `max_visits` / `max_transitions`
- stable `step_id` and qualified lineage/freshness
- `root` / `self` / `parent` refs
- typed workflow `inputs` / `outputs`
- structured branch outputs, structured-boundary transfer rejection, and `exited_via_transfer` reporting semantics
- reusable-call write-root requirements and explicit source-relative asset handling through `asset_file` / `asset_depends_on`

**Verification:**

Run:
```bash
pytest tests/test_typed_predicates.py tests/test_loader_validation.py -k "assert or typed or version" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/assert_gate_demo.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --dry-run
```

### Task 2: Land `D2a` Lightweight Scalar Bookkeeping as a Runtime Primitive

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/state.py`
- Create: `orchestrator/workflow/scalars.py`
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Create: `tests/test_scalar_bookkeeping.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Create: `workflows/examples/scalar_bookkeeping_demo.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

**Step 1: Freeze the exact first-tranche scalar-step contract before coding**

Lock the first tranche to exactly two runtime-owned operations:
- `set_scalar`
- `increment_scalar`

Freeze the rest of the contract up front:
- `artifact:` must name a scalar artifact already declared in the top-level artifact registry
- `value` / `by` may use literals and structured `ref:` operands only
- no arbitrary expressions and no third primitive in this tranche
- each step materializes its result as a same-named local step artifact under `steps.<Step>.artifacts.*`
- top-level artifact lineage must still advance only through `publishes.from`; scalar steps must not mutate the top-level registry directly

**Step 2: Implement validation and execution in one narrow module**

Validate the new step shape in `orchestrator/loader.py`, execute it from `orchestrator/workflow/executor.py`, and isolate the operation logic in `orchestrator/workflow/scalars.py`. Keep failure shape aligned with existing contract/pre-execution failures.

**Step 3: Reuse existing artifact and predicate machinery**

Allow scalar-step outputs to participate in:
- typed predicates through `ref: root.steps.<Step>.artifacts.<name>`
- `publishes.from`
- state persistence and report output

Do not add a new variable namespace in this tranche, and add explicit negative coverage that executing a scalar step without `publishes.from` does not advance top-level artifact state. The purpose is to remove shell glue, not to create a second data model.

**Verification:**

Run:
```bash
pytest tests/test_scalar_bookkeeping.py --collect-only -q
pytest tests/test_scalar_bookkeeping.py tests/test_loader_validation.py tests/test_artifact_dataflow_integration.py -k "scalar or bookkeeping" -v
pytest tests/test_workflow_examples_v0.py -k scalar_bookkeeping -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/scalar_bookkeeping_demo.yaml --dry-run
```

### Task 3: Land `D3` Resume-Safe Cycle Guards for Raw Graph Workflows

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Create: `tests/test_control_flow_foundations.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_retry_behavior.py`
- Create: `workflows/examples/cycle_guard_demo.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

**Step 1: Add loader gating for `max_transitions` and `max_visits`**

Validate top-level `max_transitions` and step-level `max_visits`, including:
- positive integer requirements
- incompatibilities with impossible locations
- version gating to `v1.8+`

**Step 2: Persist counters at the exact runtime boundaries defined by the ADR**

In `orchestrator/workflow/executor.py` and `orchestrator/state.py`, persist:
- workflow transition count after control-flow resolution chooses the next executable step
- step visit count when control actually enters an executable step after `when` evaluation

Skipped steps must not consume visit budget, and retries must not count as extra visits.

**Step 3: Make the counters resume-visible and report-visible**

Resume must reload persisted counters instead of recomputing them from prior results. Report output should expose guard-failure context clearly enough to diagnose why a workflow stopped.

**Verification:**

Run:
```bash
pytest tests/test_control_flow_foundations.py --collect-only -q
pytest tests/test_control_flow_foundations.py tests/test_state_manager.py tests/test_resume_command.py tests/test_retry_behavior.py -k "max_visits or max_transitions" -v
pytest tests/test_workflow_examples_v0.py -k cycle_guard -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --dry-run
```

### Task 4: Land the First Half of `v2.0` With Stable Step IDs and Qualified Lineage

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Create: `orchestrator/workflow/identity.py`
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Create: `tests/test_stable_step_ids.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_observability_report.py`

**Step 1: Add authored `id` support and deterministic internal `step_id` generation**

Teach the loader to accept optional authored `id` fields, validate uniqueness within lexical scope, and generate internal qualified IDs for all executable nodes. Compiler-generated IDs may remain checksum-stable only within the same validated workflow; authored IDs must preserve descendant identity across rename/insert refactors.

**Step 2: Migrate durable state and lineage away from display-name keys**

Update `state.json` and artifact ledger persistence so durable producer/consumer identities use qualified internal IDs. Keep display names in reports and compatibility views, but do not keep using them as freshness or resume keys.

**Step 3: Make the migration explicit in resume and observability**

`resume` must reject pre-`v2.0` state for post-`v2.0` workflows unless a tested upgrader exists in the same tranche. Observability should show both `name` and `step_id` for lowered or nested execution so debugging remains readable.

This task starts the `v2.0` migration but does not finish the public `v2.0` surface. Task 5 must land before the `v2.0` boundary is considered review-ready or releasable.

**Verification:**

Run:
```bash
pytest tests/test_stable_step_ids.py --collect-only -q
pytest tests/test_stable_step_ids.py tests/test_state_manager.py tests/test_for_each_execution.py tests/test_artifact_dataflow_integration.py tests/test_resume_command.py tests/test_observability_report.py -k "step_id or lineage or freshness or schema" -v
pytest tests/test_typed_predicates.py -k "multi-visit or ref" -v
```

### Task 5: Complete `v2.0` With `D4` Scoped References and `D6` Typed Workflow Signatures

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/variables/substitution.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Create: `orchestrator/workflow/signatures.py`
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/workflow_drafting_guide.md`
- Create: `tests/test_scoped_references.py`
- Create: `tests/test_workflow_signatures.py`
- Modify: `tests/test_cli_safety.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_resume_command.py`
- Create: `workflows/examples/workflow_signature_demo.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

**Step 1: Add the scoped `ref:` model on top of qualified identities**

Teach `orchestrator/workflow/references.py` to resolve:
- `root.steps.<Name>...`
- `self.steps.<Name>...`
- `parent.steps.<Name>...`
- `inputs.<name>`

Reject bare `steps.<Name>` in the new model. Keep legacy string interpolation semantics untouched.

**Step 2: Add typed workflow `inputs` / `outputs` with direct boundary validation**

Implement top-level `inputs` / `outputs` as a contract family distinct from the top-level artifact registry. Bind top-level inputs from existing CLI/context sources in `orchestrator/cli/commands/run.py`, validate them before execution starts, and expose them through both `${inputs.<name>}` and `ref: inputs.<name>`.

**Step 3: Export outputs through one completion hook**

Add one executor completion path that validates and exports workflow outputs only after the body succeeds. Implement it behind a single hook so Task 7 can later delay export until finalization completes without reworking signature plumbing.

This task closes the same `v2.0` version boundary started in Task 4. Keep docs, migration notes, and acceptance language aligned to one `v2.0` release rather than a `v2.0`/`v2.1` split.

**Verification:**

Run:
```bash
pytest tests/test_scoped_references.py --collect-only -q
pytest tests/test_workflow_signatures.py --collect-only -q
pytest tests/test_scoped_references.py tests/test_workflow_signatures.py tests/test_cli_safety.py tests/test_artifact_dataflow_integration.py tests/test_resume_command.py -k "root or self or parent or inputs or outputs" -v
pytest tests/test_workflow_examples_v0.py -k workflow_signature -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/workflow_signature_demo.yaml --dry-run
```

### Task 6: Land `D7` Structured `if/else` Through a Statement IR and Lowering Pass

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/observability/report.py`
- Create: `orchestrator/workflow/statements.py`
- Create: `orchestrator/workflow/lowering.py`
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`
- Create: `tests/test_structured_if_else.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_observability_report.py`
- Create: `workflows/examples/structured_if_else_demo.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

**Step 1: Validate structured branch syntax separately from flat steps**

Extend the loader with a statement layer instead of pretending `if` is just another step record. Branch-local steps must stay branch-local, and any value needed downstream must be surfaced through explicit block outputs.

Define the first-tranche transfer rule here instead of leaving it implicit:
- authored `goto` / `_end` may not escape a structured boundary
- the loader must reject branch-local transfers that target outer-scope steps or `_end`
- any permitted transfer behavior inside the lowered statement must stay intra-frame and versioned with the structured statement semantics

**Step 2: Lower the statement IR to executable nodes with stable identities**

Create a lowering pass that generates executable nodes with stable IDs and explicit branch metadata. Non-taken branches must be recorded as non-executed, not silently absent.

The lowering contract must also define the structured control-effect model:
- intra-frame transfers may target only lowered nodes inside the same structured statement
- escaping transfers are invalid in this tranche and should fail validation, not inherit raw-graph behavior
- when a structured frame is left via an allowed transfer, state/reporting must record that frame as `exited_via_transfer`

**Step 3: Keep branch execution observable and resume-safe**

Persist enough branch/frame state in `state.json` for resume and report output to show:
- which branch executed
- which block outputs were materialized
- which nodes were skipped because their branch was not taken
- which structured frames exited via an allowed intra-frame transfer

**Verification:**

Run:
```bash
pytest tests/test_structured_if_else.py --collect-only -q
pytest tests/test_structured_if_else.py tests/test_loader_validation.py tests/test_resume_command.py tests/test_observability_report.py -k "if_else or branch or goto or transfer" -v
pytest tests/test_workflow_examples_v0.py -k structured_if_else -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/structured_if_else_demo.yaml --dry-run
```

### Task 7: Land `D8` Structured Finalization

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Create: `tests/test_finalization.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_queue_operations.py`
- Modify: `tests/test_observability_report.py`
- Create: `workflows/examples/finally_demo.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

**Step 1: Add top-level `finally` syntax and explicit failure precedence**

Implement top-level `finally` only. The guarded workflow result remains primary; a cleanup failure should either replace a successful run with a finalization failure or be recorded as a secondary diagnostic when the guarded region already failed.

**Step 2: Persist finalization progress for resume**

State must record which finalization steps have completed so resume continues from the first unfinished cleanup node rather than replaying the whole block.

**Step 3: Gate workflow-output export through finalization completion**

Hook the Task 5 workflow-output export path into finalization so outputs are materialized only after the guarded body and `finally` both complete successfully.

**Verification:**

Run:
```bash
pytest tests/test_finalization.py --collect-only -q
pytest tests/test_finalization.py tests/test_resume_command.py tests/test_queue_operations.py tests/test_observability_report.py -k "finally or finalization" -v
pytest tests/test_workflow_examples_v0.py -k finally_demo -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/finally_demo.yaml --dry-run
```

### Task 8: Land `D8a` Reusable-Call Risk Contract and Path Taxonomy Before Runtime Work

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/dependencies.md`
- Modify: `specs/providers.md`
- Modify: `specs/security.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `workflows/README.md`
- Create: `orchestrator/workflow/paths.py`
- Modify: `orchestrator/loader.py`
- Create: `tests/test_reusable_workflow_contract.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_execution_safety.py`
- Modify: `tests/test_provider_integration.py`
- Create: `workflows/library/reusable_asset_contract.yaml`
- Create: `workflows/examples/reusable_asset_contract_demo.yaml`

**Step 1: Document the first reusable-call tranche as non-isolating**

Make the accepted-risk contract explicit:
- imported workflows may still contain `provider` / `command` steps
- undeclared child-process writes remain author responsibility
- reusable workflows must expose every DSL-managed write root as a typed `relpath` input

**Step 2: Freeze the explicit source-relative asset surface before `call` runtime work**

Add one shared path-resolution helper in `orchestrator/workflow/paths.py` and document the full first-tranche field split:
- `asset_file` and `asset_depends_on` are workflow-source-relative and resolve against the imported workflow file
- `asset_file` / `asset_depends_on` must validate inside the imported workflow source tree and reject traversal outside it
- `input_file` and plain `depends_on` remain workspace-relative and are not overloaded with imported-asset semantics
- source/reference assets and runtime/write paths must stay separate in both the spec text and the loader

**Step 3: Add pre-runtime validation for reusable workflow authoring constraints**

Teach the loader to:
- reject reusable workflows and call sites that keep managed write roots hard-coded instead of typed/bound through `inputs`
- reject imported workflows that use source-relative bundled assets through `input_file` / `depends_on` instead of `asset_file` / `asset_depends_on`
- inspect imported workflows during dry-run/validation deeply enough to verify bundled-asset path rules before Task 9 adds call-frame execution

**Step 4: Add an imported-workflow contract smoke case before Task 9**

Add one minimal library workflow and one example caller that exercise `asset_file` / `asset_depends_on` through import resolution in a validation/dry-run path. This tranche should prove the asset taxonomy before inline `call` execution starts, not after.

**Verification:**

Run:
```bash
pytest tests/test_reusable_workflow_contract.py --collect-only -q
pytest tests/test_reusable_workflow_contract.py tests/test_loader_validation.py tests/test_execution_safety.py tests/test_provider_integration.py -k "reusable or write_root or source_relative or asset_file or asset_depends_on" -v
pytest tests/test_workflow_examples_v0.py -k reusable_asset_contract -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/reusable_asset_contract_demo.yaml --dry-run
```

### Task 9: Land `D9` Imports and Inline `call`

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/paths.py`
- Create: `orchestrator/workflow/imports.py`
- Create: `orchestrator/workflow/call_frames.py`
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`
- Create: `tests/test_call_subworkflows.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_observability_report.py`
- Create: `workflows/library/review_loop.yaml`
- Create: `workflows/examples/call_subworkflow_demo.yaml`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

**Step 1: Add import loading and typed `with:` binding**

Extend the Task 8 import-aware validation path into execution-ready import loading. Load imported workflow files relative to the parent workflow file, validate `with:` bindings against the callee's declared `inputs`, and reject missing or type-invalid bindings before execution starts.

**Step 2: Execute callees inline as call frames with qualified internal identities**

Implement call-frame lowering/runtime so:
- callee steps run inside the same top-level run
- internal lineage/freshness keys are call-scoped
- runtime-owned metadata roots live under `.orchestrate/call_frames/<call-step-id>/<invocation-id>/...`

**Step 3: Export callee outputs through the outer call step only**

Caller-visible outputs must surface as `steps.<CallStep>.artifacts.<name>`, with the outer call step as the external producer identity. Preserve the internal `outputs[*].from` origin as secondary provenance in state/reporting instead of flattening callee internals into the caller namespace.

**Verification:**

Run:
```bash
pytest tests/test_call_subworkflows.py --collect-only -q
pytest tests/test_call_subworkflows.py tests/test_artifact_dataflow_integration.py tests/test_resume_command.py tests/test_observability_report.py -k "call or import or call_frame or provenance" -v
pytest tests/test_workflow_examples_v0.py -k call_subworkflow -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --dry-run
```

## Completion Criteria

- The repo supports scalar bookkeeping and cycle guards without shell glue on pre-`v2.0` workflows.
- `v2.0` introduces stable `step_id` identities, qualified lineage/freshness, scoped refs, and typed workflow signatures without silently reusing display names as durable keys.
- Structured `if/else`, top-level `finally`, and inline `call` run through a statement/lowering layer with resume-visible frame state.
- Reusable-call semantics are documented honestly: `asset_file` / `asset_depends_on` stay source-relative, workspace write roots remain explicit typed inputs, and no false isolation guarantees are claimed.
- Every added test module has `pytest --collect-only` coverage, every new example has at least a dry-run smoke check, and the final tranche reruns the current `assert`/typed-predicate examples to confirm no regression in shipped behavior.

## Deferred Follow-Ons

- `D10` `match`
- `D11` `repeat_until`
- `D12` linting / normalization
- `D13` score-aware gates

These remain in the ADR and `specs/versioning.md`, but should not start until the Task 9 call-frame substrate is stable and the core landing criteria above are met.
