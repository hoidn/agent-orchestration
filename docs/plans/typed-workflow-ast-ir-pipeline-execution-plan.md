# Typed Workflow AST / Executable IR Pipeline Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the approved typed workflow surface AST and executable IR pipeline so authored YAML is elaborated into an immutable AST, lowered into immutable executable IR, and executed via IR-driven runtime collaborators without changing first-tranche external DSL or persisted state behavior.

**Architecture:** Land the refactor in dependency order. First lock current behavior with characterization coverage around lowering, state, resume, call, and reporting surfaces. Then introduce the typed surface AST and loaded-workflow bundle behind a compatibility boundary, add executable IR plus compatibility projection, migrate executor/runtime collaborators to IR/node-id dispatch, and only then delete the legacy lowered-dict plumbing. Treat projection-backed compatibility as the only bridge to existing `state.json` and reporting surfaces, and stop the rollout if any step requires an external contract change.

**Tech Stack:** Python 3.11+, YAML loader, dataclasses/enums for internal node models, current `orchestrator/` runtime modules, pytest unit/integration suites, targeted orchestrator dry-run/example smoke checks.

---

## Global Guardrails

- Land tranches in order; later tranches assume earlier bundle/IR contracts already exist.
- Keep the first cut internal-only: same authored YAML syntax, same version gates, same `state.json` schema/version, same presentation keys, same `step_id` ancestry.
- Treat the typed surface AST as the authored-shape truth and the executable IR as the execution-shape truth once each tranche lands; do not keep two competing authorities for the same phase.
- Keep AST and IR immutable after construction.
- Split tests by phase so authored validation, lowering, projection, and runtime regressions can fail independently.
- Preserve resume compatibility for existing persisted runs in this slice; if implementation proves that impossible, stop and write a separate ADR/spec change before continuing.
- Do not mix unrelated provider transport, output-capture, demo, or DSL feature work into this refactor.

## Compatibility And Migration Boundary

- This slice is an internal runtime migration. Workflow authors should not have to change YAML, prompts, or state roots.
- Persisted `step_id`, presentation key, `current_step.index`, `finalization.*`, `repeat_until.*`, `for_each.*`, `call_frames.*`, `step_visits`, and `transition_count` remain the compatibility surface.
- The projection layer is the sole authority for mapping IR node ids to persisted/reporting surfaces. Runtime code must not infer that mapping from ordered dict lists, name scans, or helper metadata keys.
- Temporary adapters are allowed only at narrow boundaries:
  - a loader-owned bundle that can still hand legacy callers a compatibility projection of the workflow
  - leaf-node adapters from IR configs into existing command/provider/wait/assert/scalar executors
  - persisted step-result/state payload dictionaries, because `state.json` is intentionally unchanged in this tranche
  - provenance/import shims while asset resolution and nested-call helpers are migrated
- Not allowed as the steady state:
  - new runtime behavior keyed off `structured_if_branch`, `structured_if_join`, `structured_match_case`, `structured_match_join`, or `workflow_finalization`
  - runtime lookup of workflow provenance/imports from `__workflow_path`, `__source_root`, `__imports`, or `__managed_write_root_inputs` once typed bundle data exists
  - executor paths that interpret both lowered dicts and IR nodes for the same concept beyond the temporary adapter boundary
  - feature work that extends the legacy lowered-dict representation instead of the typed AST/IR pipeline

## Explicit Non-Goals

- DSL syntax redesign or new authored workflow features.
- `state.json` redesign, on-disk IR serialization, or automatic state migration.
- General compiler infrastructure, plugin systems, or optimization passes unrelated to correctness.
- Provider transport/output capture redesign beyond what is necessary to preserve existing leaf-step execution through IR adapters.
- Removal of useful executor seam extractions that already help isolate runtime responsibilities.

### Tranche 1: Lock Current External Behavior With Phase-Oriented Characterization

**Files:**
- Create: `tests/test_workflow_lowering_invariants.py`
- Create: `tests/test_workflow_state_compatibility.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_structured_control_flow.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_workflow_executor_characterization.py`

**Work:**
- Add focused characterization coverage for the compatibility surfaces the ADR says must survive:
  - stable `step_id` assignment for top-level, structured branches/cases, `repeat_until`, `for_each`, `finally`, and `call`
  - lowered step ordering and presentation-key surfaces that drive `steps.*`, `current_step.index`, finalization bookkeeping, and report output
  - `repeat_until` frame persistence, call-frame checkpoints, and `transition_count` semantics during resume/re-entry
  - report/status rendering for structured helper nodes, finalization, and loop progress
- Keep these tests compatibility-oriented. Assert durable ids, ordering, routing, and persisted state surfaces, not incidental dict layout or helper-key placement that will intentionally disappear later.
- Introduce separate test buckets for authored validation, lowering invariants, and runtime compatibility so later tranches can move implementation without losing regression signal.

**Verification:**
```bash
pytest --collect-only -q tests/test_workflow_lowering_invariants.py tests/test_workflow_state_compatibility.py
pytest tests/test_loader_validation.py tests/test_workflow_lowering_invariants.py tests/test_workflow_state_compatibility.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_resume_command.py tests/test_observability_report.py tests/test_workflow_executor_characterization.py -k "step_id or structured or repeat_until or finalization or call or current_step or transition_count" -v
```

**Checkpoint:** Do not start AST work until the repo has passing characterization coverage for the current compatibility surfaces that the projection layer must preserve.

### Tranche 2: Introduce The Typed Surface AST And Loaded-Workflow Bundle

**Files:**
- Create: `orchestrator/workflow/surface_ast.py`
- Create: `orchestrator/workflow/elaboration.py`
- Create: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/identity.py`
- Modify: `orchestrator/workflow/statements.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/workflow/predicates.py`
- Modify: `orchestrator/workflow/prompting.py`
- Create: `tests/test_workflow_surface_ast.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_lowering_invariants.py`

**Work:**
- Define immutable authored-shape types for:
  - workflow root and workflow-level contracts
  - step unions for provider, command, wait, assert, scalar bookkeeping, `for_each`, `repeat_until`, `call`, `if/else`, `match`, and `finally`
  - typed provenance/import metadata, including workflow path, source root, imported workflow bindings, and managed write-root input requirements
  - parsed reference and predicate nodes instead of runtime string parsing as the source of truth
- Move normalization, version-gated validation, stable-id assignment, and provenance capture into `elaboration.py`.
- Add a `LoadedWorkflowBundle` that carries at least the surface AST, typed provenance/import metadata, and a temporary compatibility slot for unchanged callers.
- Keep `WorkflowLoader.load()` externally compatible during this tranche. It can delegate to a new typed load path internally, but unchanged callers should still be able to run while the executor remains on the legacy adapter.
- Update prompt/source-root consumers to read typed provenance from the bundle/adapters instead of depending on raw dict magic metadata as soon as that typed data is available.

**Verification:**
```bash
pytest --collect-only -q tests/test_workflow_surface_ast.py
pytest tests/test_workflow_surface_ast.py tests/test_loader_validation.py tests/test_workflow_lowering_invariants.py -k "surface or provenance or imports or step_id or repeat_until or call" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
```

**Checkpoint:** The surface AST is now the authored-shape authority. Raw YAML dicts should not escape parse/elaboration except through the explicit compatibility adapter carried by the loaded bundle.

### Tranche 3: Lower Surface AST To Executable IR And Compatibility Projection

**Files:**
- Create: `orchestrator/workflow/executable_ir.py`
- Create: `orchestrator/workflow/state_projection.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/loader.py`
- Create: `tests/test_workflow_ir_lowering.py`
- Create: `tests/test_workflow_state_projection.py`
- Modify: `tests/test_structured_control_flow.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_workflow_state_compatibility.py`

**Work:**
- Define immutable executable-node types and topology records for:
  - leaf execution nodes
  - explicit helper nodes such as branch markers/joins, case markers/joins, finalization steps, repeat-until frames, and call boundaries
  - node-kind enums, region membership, fallthrough successors, routed transfers, and `counts_as_transition` routing metadata
- Make lowering a pure AST-to-IR transform that:
  - resolves goto targets and structured routes to node ids
  - binds executable references to durable target addresses instead of leaving runtime string parsing/name scans in place
  - preserves presentation names and compatibility indices only via projection tables, not as execution truth
- Generate compatibility projection tables for:
  - `node_id <-> compatibility_index`
  - presentation keys and display names used in `steps.*`, `step_visits`, and reporting
  - finalization local-index bookkeeping
  - `repeat_until`, `for_each`, and call-frame compatibility key templates
  - restart mappings from persisted `step_id` to IR node ids
- Keep one narrow IR-to-legacy adapter only while the executor and collaborators still expect dict-shaped lowered workflows.

**Verification:**
```bash
pytest --collect-only -q tests/test_workflow_ir_lowering.py tests/test_workflow_state_projection.py
pytest tests/test_workflow_ir_lowering.py tests/test_workflow_state_projection.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_workflow_state_compatibility.py -k "lowering or projection or repeat_until or finalization or call or compatibility_index" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
```

**Checkpoint:** Helper/runtime nodes now exist only as typed IR. Any remaining lowered-dict representation must be generated by the temporary adapter, not by the core lowering pipeline.

### Tranche 4: Migrate Executor, Resume, And Reporting To Consume IR + Projection

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/finalization.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/dataflow.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify: `orchestrator/workflow/linting.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/cli/commands/report.py`
- Modify: `tests/test_workflow_executor_characterization.py`
- Modify: `tests/test_for_each_execution.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_cli_report_command.py`
- Modify: `tests/test_subworkflow_calls.py`

**Work:**
- Change runtime entrypoints to accept the loaded bundle / executable IR and advance by node ids plus explicit routed transfers instead of list indices, key-presence dispatch, or step-name scans.
- Keep leaf-step execution narrow: IR leaf nodes should adapt into the existing command/provider/wait/assert/scalar executors rather than redesigning subprocess/provider internals in this tranche.
- Replace runtime structured-ref parsing with bound-address lookup through the projection/state machinery.
- Migrate loop, call, finalization, and resume planning code to use:
  - typed provenance/import metadata from the bundle
  - projection-driven `step_id -> node_id` restart planning
  - projection-backed compatibility indices/presentation keys as integrity cross-checks only
- Update report/status generation and CLI report surfaces to enumerate nodes through projection ordering instead of helper-key inspection on dict steps.

**Verification:**
```bash
pytest tests/test_workflow_executor_characterization.py tests/test_for_each_execution.py tests/test_artifact_dataflow_integration.py tests/test_state_manager.py tests/test_resume_command.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_subworkflow_calls.py -k "current_step or transition_count or repeat_until or finalization or call or report" -v
```

**Checkpoint:** Runtime collaborators consume only executable IR, projection tables, and typed provenance/import metadata. Dict-shaped lowered helpers are no longer allowed to drive execution, resume, or reporting decisions.

### Tranche 5: Remove Legacy Dict Plumbing And Close The Maintainer-Docs Gap

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/references.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/linting.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/orchestration_start_here.md`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_structured_control_flow.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_workflow_examples_v0.py`

**Work:**
- Delete the remaining runtime dependence on legacy magic metadata:
  - `__workflow_path`
  - `__source_root`
  - `__imports`
  - `__managed_write_root_inputs`
  - `structured_if_branch`
  - `structured_if_join`
  - `structured_match_case`
  - `structured_match_join`
  - `workflow_finalization`
- Remove the temporary IR-to-legacy execution adapter once all runtime collaborators are fully migrated.
- Keep only compatibility projection/state payloads that intentionally preserve external surfaces; do not leave parallel legacy code paths in place "just in case."
- Update maintainer-facing docs to describe the new internal phase boundaries: parse -> elaborate -> lower -> execute, plus projection-backed resume/report semantics.
- Run focused example/runtime smoke coverage to prove that structured control, nested call, finalization, and resume behavior still work through the typed pipeline.

**Verification:**
```bash
pytest tests/test_loader_validation.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_resume_command.py tests/test_workflow_examples_v0.py tests/test_observability_report.py tests/test_cli_report_command.py -k "structured or repeat_until or finalization or call or report or design_plan_impl_review_stack_v2_call" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run
```

**Checkpoint:** The steady state is now the typed pipeline only. If any execution path still requires raw lowered dicts or magic workflow metadata after this tranche, the migration is incomplete and should not be declared done.

## Exit Criteria

The implementation is complete only when all of the following are true:

- Authored YAML is elaborated into immutable surface AST nodes before lowering.
- Lowering produces immutable executable IR plus a projection that is the sole bridge to persisted/reporting compatibility surfaces.
- Executor, loops, calls, finalization, resume, and reporting all consume IR/projection instead of raw dict workflows.
- Existing external DSL behavior and persisted-state behavior remain unchanged for covered workflows and tests.
- The repo has independent passing coverage for authored validation, lowering/projection invariants, and runtime compatibility.
- Legacy lowered-dict helper metadata is gone from steady-state runtime code.
