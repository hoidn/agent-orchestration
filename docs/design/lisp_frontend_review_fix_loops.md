# Lisp Frontend Review/Fix Loops

Status: design draft

## Problem

The Lisp frontend autonomous drain currently uses single-pass plan and
implementation phases. The plan phase drafts once and reviews once. The
implementation phase executes once and reviews once. A review provider can
write `REVISE`, but there is no deterministic workflow path that invokes
`RevisePlan` or `FixImplementation`.

That makes review decisions advisory text instead of control-flow authority.
It also lets the work-item layer record a selected item or design gap as
completed even when the phase review decision is `REVISE`.

## Design Principles

1. Review decisions route workflow control.
   A review decision is not just a report field. `APPROVE` exits the loop,
   `REVISE` invokes the corresponding revision/fix step, and loop exhaustion
   is a terminal non-completion state.

2. Prompts judge; workflows route.
   Review prompts decide whether the artifact is acceptable. The YAML owns the
   loop, branch, publication, and final state transitions.

3. Completion requires approval.
   A work item may be recorded as completed only after the plan and
   implementation phases have terminal approved states. A `REVISE` terminal
   state is not completion.

4. Updated artifacts must be republished before the next review.
   `RevisePlan` republishes `plan`. `FixImplementation` republishes
   `execution_report`, and checks are rerun before the next implementation
   review.

5. Exhaustion is explicit.
   If the loop reaches `max_iterations` without approval, the phase finalizer
   records `REVISE`, and the work-item workflow records a blocked item with a
   reason such as `plan_review_exhausted` or
   `implementation_review_exhausted`.

## Plan Phase Shape

`workflows/library/lisp_frontend_plan_phase.v214.yaml` should keep the existing
input materialization and initial `DraftPlan` step, then wrap review and
revision in a `repeat_until` loop.

The target shape mirrors
`workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`:

```text
MaterializePlanInputs
DraftPlan
PlanReviewLoop repeat_until review_decision == APPROVE
  ReviewPlan
  RoutePlanDecision match plan_review_decision
    APPROVE:
      WriteApprovedPlanDecision
    REVISE:
      RevisePlan
      WriteRevisedPlanDecision
FinalizePlanPhaseOutputs
```

`ReviewPlan` publishes:

- `plan_review_report`
- `plan_review_decision`

`RevisePlan` consumes:

- `full_design`
- `mvp_design`
- `work_item_context`
- `plan`
- `plan_review_report`

`RevisePlan` publishes:

- `plan`

`FinalizePlanPhaseOutputs` writes final pointer files and exposes:

- `plan_path`
- `plan_review_report_path`
- `plan_review_decision`

The phase output `plan_review_decision` must come from
`FinalizePlanPhaseOutputs`, not from the first review step.

## Implementation Phase Shape

`workflows/library/lisp_frontend_implementation_phase.v214.yaml` should keep
the existing input materialization and initial `ExecuteImplementation` step.
When `implementation_state == BLOCKED`, the phase should skip review and emit
`implementation_review_decision = NOT_APPLICABLE`. When
`implementation_state == COMPLETED`, it should enter an implementation
review/fix loop.

The target shape mirrors
`workflows/library/neurips_backlog_implementation_phase.v214.yaml`:

```text
MaterializeImplementationInputs
ExecuteImplementation
ImplementationReviewLoop repeat_until review_decision == APPROVE
  RouteIterationWork match implementation_state
    COMPLETED:
      RunChecks
      ReviewImplementation
      FixImplementation when implementation_review_decision == REVISE
      PublishUpdatedExecutionReport when implementation_review_decision == REVISE
      WriteLoopReviewDecision
    BLOCKED:
      WriteSkippedReviewDecision APPROVE
FinalizeImplementationPhaseOutputs
```

`RunChecks` must publish `checks_report` so each review consumes fresh check
evidence. `ReviewImplementation` publishes:

- `implementation_review_report`
- `implementation_review_decision`

`FixImplementation` consumes:

- `full_design`
- `mvp_design`
- `plan`
- `execution_report`
- `checks_report`
- `implementation_review_report`

`FixImplementation` updates the implementation and execution report. The
subsequent `PublishUpdatedExecutionReport` step republishes `execution_report`
before the next loop iteration.

`FinalizeImplementationPhaseOutputs` exposes:

- `implementation_state`
- `execution_report_path` when completed
- `checks_report_path` when completed
- `implementation_review_report_path` when completed
- `implementation_review_decision`
- `progress_report_path` when blocked

The phase output `implementation_review_decision` must come from
`FinalizeImplementationPhaseOutputs`, not from the first review step.

## Work-Item Terminal Routing

`workflows/library/lisp_frontend_work_item.v214.yaml` must stop treating a
returned implementation phase as automatically complete.

The work-item workflow should route terminal state as follows:

```text
RunPlanPhase
RoutePlanTerminal
  APPROVE:
    RunImplementationPhase
    RouteImplementationTerminal
      implementation_state == COMPLETED and review_decision == APPROVE:
        RecordCompletedWorkItem
      implementation_state == COMPLETED and review_decision == REVISE:
        RecordBlockedWorkItem reason=implementation_review_exhausted
      implementation_state == BLOCKED:
        RecordBlockedWorkItem reason=implementation_blocked
  REVISE:
    RecordBlockedWorkItem reason=plan_review_exhausted
```

The existing `update_lisp_frontend_run_state.py blocked` command can record
blocked items and design gaps. The work-item workflow should expose
`drain_status` from whichever terminal record step actually ran.

## Prompt Impact

The existing prompts are sufficient for the first implementation:

- `workflows/library/prompts/lisp_frontend_plan_phase/revise_plan.md`
- `workflows/library/prompts/lisp_frontend_implementation_phase/fix_implementation.md`

They may need small wording updates after wiring if provider behavior shows
ambiguity, but the primary fix is workflow control flow, not prompt text.

## Testing Strategy

Add runtime tests to `tests/test_lisp_frontend_autonomous_drain_runtime.py`
with fake providers that force revision paths:

1. Plan review returns `REVISE`, `RevisePlan` writes an updated plan, then
   plan review returns `APPROVE`.
2. Implementation review returns `REVISE`, `FixImplementation` writes an
   updated execution report, then implementation review returns `APPROVE`.
3. Plan review always returns `REVISE` until loop exhaustion; the work item is
   recorded blocked, not completed.
4. Implementation review always returns `REVISE` until loop exhaustion; the
   work item is recorded blocked, not completed.

Keep tests behavioral. Do not assert literal prompt text.

## Non-Goals

- Do not add a new DSL feature.
- Do not add a Lisp frontend language feature.
- Do not change provider execution semantics.
- Do not make prompts own loop counters or routing.
- Do not rewrite the whole autonomous drain.

## Acceptance Criteria

- Plan `REVISE` invokes `RevisePlan` and re-reviews the updated plan.
- Implementation `REVISE` invokes `FixImplementation`, republishes the updated
  execution report, reruns checks, and re-reviews.
- `APPROVE` is required before a work item can be recorded completed.
- Exhausted plan or implementation loops record blocked state.
- Existing one-pass approve smoke coverage still passes.
- New revision-path tests pass.
