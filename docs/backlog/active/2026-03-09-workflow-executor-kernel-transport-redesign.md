# Backlog Item: Workflow Executor Kernel / Transport Redesign

- Status: deferred
- Created on: 2026-03-09
- Plan: `docs/plans/2026-03-09-workflow-executor-kiss-refactor-plan.md` (precursor; follow-on redesign plan still needed)
- Blocked on: `docs/backlog/active/2026-03-09-typed-workflow-ast-ir-pipeline.md`

## Scope
Follow the completed KISS consolidation with a narrower but deeper redesign of the remaining `executor.py` hot spots: the top-level execution kernel, provider/command transport seam, and the integration boundary between routing authority and step-kind execution.

This item is deferred because the repo now also has an active follow-on for a typed surface AST plus lowered executable IR. Until that direction is planned concretely, another round of dict-shaped executor cleanup risks churn or duplicated work. If this item is reactivated before the AST/IR item lands, it should be narrowed to transport/kernel work that will clearly survive an AST/IR migration.

## Why This Is Still Backlog-Worthy
The KISS consolidation removed obvious non-paying abstractions and made outcome recording explicit, but it did not materially shrink the core orchestration nexus. `executor.py` still carries too much of:
- the top-level run state machine
- provider/command transport preparation and normalization
- call/subworkflow integration glue
- kernel-to-collaborator reshaping code

That means the file is still harder to reason about than it should be, even though the current authority boundaries are better than before. The remaining problem is no longer simple extraction hygiene; it is that some of the last high-LOC clusters are still real architectural seams that deserve a more principled redesign.

## Why This Is Deferred
The newer typed AST / executable IR backlog item is a better umbrella for the next architectural step. That work explicitly changes the loader/lowering/executor boundary, while this item assumes the current dict-shaped runtime model. Doing this redesign first would likely produce one more cleanup pass that the AST/IR work would later need to revisit.

## Desired Outcome
This follow-on should leave the runtime with:
- a smaller and more explicit execution kernel in `WorkflowExecutor`
- a clearer, more self-contained provider/command transport seam
- less kernel-local glue for reshaping results between helpers
- stable external workflow behavior and `state.json` semantics

The target is not a minimal line count. The target is a runtime where a reader can answer:
- how a top-level step is chosen and finalized
- how provider/command execution is prepared and normalized
- how routing decisions re-enter the kernel

without following a maze of thin wrappers or hidden authority transfers.

## Likely Redesign Targets
The next plan should evaluate these areas explicitly:

1. Provider/command transport
- Move only the transport-heavy logic that is semantically self-contained.
- Keep top-level routing, cursor movement, and run status in the kernel.
- Avoid inventing a generic execution framework.

2. Kernel return contracts
- Reduce result-shape reshuffling between executor and collaborators.
- Standardize the minimal concrete payloads needed for persistence and routing.

3. Call integration boundary
- Keep `CallExecutor` if it continues to own real call-specific behavior.
- Reduce the remaining executor-side glue that exists only to bridge call results back into top-level lifecycle semantics.

4. `execute()` readability
- Make the main control path read as a kernel:
  - select step
  - initialize lifecycle
  - delegate
  - persist/finalize
  - route

## Non-Goals
This backlog item should not be used as justification for:
- another round of mindless file-splitting
- abstract base classes, handler registries, or plugin systems
- event-bus or reducer-architecture redesign
- DSL changes
- `StateManager` storage redesign
- speculative cleanup outside the remaining executor/kernel/transport seams
- broad loader/lowering representation redesign before the AST/IR direction is decided

## Entry Criteria For A Follow-On Plan
Before implementation starts, the follow-on plan should:
- identify the concrete remaining hotspots in the current `executor.py`
- explain why each proposed extraction or redesign reduces conceptual load, not just LOC
- state what authority remains exclusively in `WorkflowExecutor`
- include characterization/regression coverage for routing, persistence, and resume behavior
- name the exact modules expected to change

## Success Criteria
This backlog item is satisfied only if a follow-on redesign:
- materially reduces the size or complexity of the remaining kernel path
- makes provider/command transport easier to trace independently of top-level routing
- does not reintroduce thin pass-through abstractions
- preserves current external behavior unless a separate design explicitly changes it
