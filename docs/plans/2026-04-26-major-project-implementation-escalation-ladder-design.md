# Major-Project Implementation Escalation Ladder Design

## Purpose

Define a principled escalation path for major-project tranche stacks so long implementation churn can stop cleanly when the real problem is no longer local implementation work.

The motivating failure is EasySpin `T26`, where the implementation phase could detect that the tranche remained on a preview-only blocked route, but the workflow only allowed `APPROVE` or `REVISE`, so the loop kept taking local implementation passes until the iteration cap fired.

## Scope

This design applies only to the major-project tranche stack family:

- `workflows/library/tracked_big_design_phase.yaml`
- `workflows/library/major_project_tranche_plan_phase.yaml` (new major-project-local plan phase)
- `workflows/library/major_project_tranche_implementation_phase.yaml` (new major-project-local implementation phase)
- `workflows/library/major_project_roadmap_revision_phase.yaml` (new major-project-local roadmap-revision phase)
- `workflows/library/major_project_tranche_design_plan_impl_stack.yaml`
- `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml`
- the major-project drain workflow(s) that call those stacks

The existing shared generic phases remain unchanged:

- `workflows/library/tracked_plan_phase.yaml`
- `workflows/library/design_plan_impl_implementation_phase.yaml`
- prompt assets under `workflows/library/prompts/design_plan_impl_stack_v2_call/`

This is not a repo-wide change to all workflow families. The implementation should introduce major-project-local wrappers or copies rather than editing shared generic prompt families in place.

## Principles

1. Prompts own local non-deterministic judgment; workflows own deterministic counters, thresholds, artifacts, and routing.
2. Escalation after many implementation iterations is advisory first, not mandatory.
3. Implementation review may diagnose that the wrong phase owns the remaining work, but it should not directly rewrite the roadmap.
4. Roadmap revision is mediated by redesign, because roadmap change is a program-shaping decision rather than a local implementation decision.
5. The default execution authority chain remains `roadmap -> design -> plan -> implementation`.
6. If the escalation ladder is introduced for major-project workflows only, both the workflow files and their prompt assets must remain major-project-local so non-major-project stacks do not acquire new escalation behavior by accident.

## Problem Statement

The current generic implementation phase has:

- authoritative inputs: `design`, `plan`, then `execution_report` / `implementation_review_report`
- decisions: `APPROVE` or `REVISE`

This works for local implementation defects. It fails when the correct diagnosis is:

- the plan is no longer adequate
- the approved design is not converging
- the tranche should likely be split or rechartered

The current system has no clean upward semantic route for those cases.

## Escalation Ladder

### Implementation review decisions

- `APPROVE`
- `REVISE`
- `ESCALATE_REPLAN`
- `BLOCK`

### Plan review decisions

- `APPROVE`
- `REVISE`
- `ESCALATE_REDESIGN`
- `BLOCK`

### Big design review decisions

- `APPROVE`
- `REVISE`
- `ESCALATE_ROADMAP_REVISION`
- `BLOCK`

This is the full escalation ladder. Escalation is adjacent-only: implementation routes to planning, planning routes to design, and design routes to roadmap revision.

## Soft Escalation Threshold

Add a workflow-owned parameter:

- `soft_escalation_iteration_threshold = 10`

This threshold is advisory only. Crossing it does not force escalation.

### Threshold accounting

The threshold is not scoped only to the current implementation-loop visit. It is:

- cumulative implementation review iterations for the current tranche since the last approved design

Implications:

- if implementation escalates to replan and later returns under the same approved design, the counter does not reset
- if the tranche receives a newly approved redesign, the counter resets to `0`

## New Workflow-Owned Artifacts

### `implementation_iteration_ledger.json`

Path:

- `${implementation_phase_state_root}/implementation_iteration_ledger.json`

Purpose:

- track cumulative implementation review iterations since the last approved design

Schema:

```json
{
  "design_epoch": 1,
  "cumulative_review_iterations_since_design_approval": 0
}
```

### `implementation_iteration_context.json`

Path:

- `${implementation_phase_state_root}/implementation_iteration_context.json`

Purpose:

- give implementation review/fix steps deterministic loop context owned by the workflow

Schema:

```json
{
  "phase_iteration_index": 0,
  "phase_iteration_number": 1,
  "cumulative_review_iterations_since_design_approval": 1,
  "soft_escalation_iteration_threshold": 10,
  "threshold_crossed": false,
  "max_phase_iterations": 40
}
```

### `upstream_escalation_context.json`

Path:

- tranche/item state root

Purpose:

- carry structured escalation evidence from one phase into the next higher phase

Schema:

```json
{
  "active": false,
  "source_phase": null,
  "decision": null,
  "recommended_next_phase": null,
  "reason_summary": "",
  "must_change": [],
  "evidence_paths": {}
}
```

This file always exists. Normal downward flow uses `active=false`. Escalation flow overwrites it with a live context.

### `upstream_escalation_context_archive.jsonl`

Path:

- tranche/item state root

Purpose:

- append-only archive of prior upstream escalation contexts, including their resolution path, so the active context can be reset deterministically without losing provenance

Each line is one JSON object containing:

- archived context payload
- archive timestamp
- resolution event such as `consumed_by_plan`, `consumed_by_redesign`, `reset_on_design_approval`, `tranche_completed`, `tranche_blocked`, or `tranche_superseded`

### `implementation_escalation_context.json`

Purpose:

- emitted by implementation review for all decisions, including plain `REVISE`

Schema:

```json
{
  "active": true,
  "source_phase": "implementation",
  "decision": "ESCALATE_REPLAN",
  "recommended_next_phase": "plan",
  "reason_summary": "The approved design still looks coherent, but the approved plan omitted executable decomposition needed to close the tranche.",
  "must_change": [
    "add executable solver-family completion tasks",
    "separate preview cleanup from denominator-closing work"
  ],
  "threshold_crossed": true,
  "cumulative_review_iterations_since_design_approval": 12,
  "evidence_paths": {
    "design": "docs/plans/...",
    "plan": "docs/plans/...",
    "execution_report": "artifacts/work/...",
    "implementation_review_report": "artifacts/review/..."
  }
}
```

### `plan_escalation_context.json`

Purpose:

- emitted by plan review when the plan phase determines that redesign is required

### `design_escalation_context.json`

Purpose:

- emitted by big-design review when the design phase determines that roadmap revision may be required

### `roadmap_change_request.json`

Purpose:

- deterministic structured handoff from big design to roadmap revision

Schema:

```json
{
  "source_phase": "design",
  "decision": "ESCALATE_ROADMAP_REVISION",
  "reason_summary": "The tranche should be split; local redesign alone is not enough.",
  "requested_program_change": "split_tranche",
  "requested_changes": [
    "separate preview cleanup from denominator-closing solver tranche",
    "insert prerequisite solver-substrate tranche before public chili promotion"
  ],
  "superseded_tranche_ids": ["T26"],
  "proposed_new_tranche_ids": ["T26A", "T26B"]
}
```

This avoids forcing roadmap revision to parse freeform markdown.

### `implementation_iteration_ledger_archive.jsonl`

Path:

- `${implementation_phase_state_root}/implementation_iteration_ledger_archive.jsonl`

Purpose:

- append-only archive of prior implementation iteration ledgers whenever a newly approved redesign resets the active ledger or the tranche reaches a terminal outcome

Each archived row records:

- prior `design_epoch`
- final `cumulative_review_iterations_since_design_approval`
- archive timestamp
- reset reason

## Workflow Changes

## Deterministic Escalation-State Lifecycle

### Initialization

At the beginning of selected-tranche execution, before the first big-design draft:

- write inactive `upstream_escalation_context.json`
- create empty `upstream_escalation_context_archive.jsonl` if missing
- do not create implementation-iteration files yet

### Activation

Whenever implementation or plan escalates upward:

- append the previous active `upstream_escalation_context.json` to `upstream_escalation_context_archive.jsonl` if it was active
- overwrite `upstream_escalation_context.json` with the new active escalation payload

### Consumption and clear

Whenever the next higher phase reaches a normal downward handoff:

- after plan approval, append the active upstream escalation context to `upstream_escalation_context_archive.jsonl` with resolution `consumed_by_plan`, then reset `upstream_escalation_context.json` to inactive before entering implementation
- after new design approval, append the active upstream escalation context to `upstream_escalation_context_archive.jsonl` with resolution `consumed_by_redesign`, then reset `upstream_escalation_context.json` to inactive before entering plan

### Ledger reset

Whenever a newly approved redesign replaces the prior approved design:

- append the current `implementation_iteration_ledger.json` to `implementation_iteration_ledger_archive.jsonl` with reason `reset_on_design_approval`
- write a fresh `implementation_iteration_ledger.json` with incremented `design_epoch` and `cumulative_review_iterations_since_design_approval=0`

### Tranche terminal cleanup

When the tranche reaches `APPROVED`, `BLOCKED`, or `superseded`:

- append any active `upstream_escalation_context.json` to the archive with the matching terminal resolution
- append any active `implementation_iteration_ledger.json` to the ledger archive with the matching terminal resolution
- reset `upstream_escalation_context.json` to inactive

These resets and archives are deterministic workflow responsibilities, not prompt responsibilities.

## Workflow Changes

### 1. `major_project_tranche_implementation_phase.yaml`

Introduce a major-project-local implementation phase instead of editing the shared generic implementation phase in place.

Add a new deterministic step inside `ImplementationReviewLoop`, before `ReviewImplementation`:

- `WriteImplementationIterationContext`

Responsibilities:

- read/update `implementation_iteration_ledger.json`
- write `implementation_iteration_context.json`

Inject `implementation_iteration_context.json` into:

- `ReviewImplementation`
- `FixImplementation`

Expand `implementation_review_decision` from:

- `APPROVE`
- `REVISE`

to:

- `APPROVE`
- `REVISE`
- `ESCALATE_REPLAN`
- `BLOCK`

Add required output publication for `implementation_escalation_context.json`.

Routing:

- `APPROVE` -> complete phase successfully
- `REVISE` -> `FixImplementation`
- `ESCALATE_REPLAN` -> complete phase successfully with that decision
- `BLOCK` -> complete phase successfully with that decision

Escalation is a semantic outcome, not a step failure.

This phase should reuse the generic implementation-phase shape where possible, but it must source its prompts from a major-project-local prompt family so non-major-project stacks do not inherit the escalation ladder by accident.

### 2. `major_project_tranche_plan_phase.yaml`

Introduce a major-project-local plan phase instead of editing the shared generic tracked plan phase in place.

Add deterministic state/inputs for:

- `upstream_escalation_context.json`

Add review output publication for:

- `plan_escalation_context.json`

Expand plan review decision enum from:

- `APPROVE`
- `REVISE`
- `BLOCK`

to:

- `APPROVE`
- `REVISE`
- `ESCALATE_REDESIGN`
- `BLOCK`

This phase should reuse the generic tracked-plan loop shape where possible, but it must source plan prompts from a major-project-local prompt family.

### 3. `tracked_big_design_phase.yaml`

Add deterministic state/inputs for:

- `upstream_escalation_context.json`

Add review output publication for:

- `design_escalation_context.json`
- `roadmap_change_request.json` when needed

Expand big-design review decision enum from:

- `APPROVE`
- `REVISE`
- `BLOCK`

to:

- `APPROVE`
- `REVISE`
- `ESCALATE_ROADMAP_REVISION`
- `BLOCK`

Because `tracked_big_design_phase.yaml` is already major-project-specific, it is the correct place to add the redesign-to-roadmap-revision decision.

### 4. `major_project_roadmap_revision_phase.yaml`

Introduce a dedicated major-project-local roadmap-revision entry workflow rather than routing `roadmap_change_request.json` back through the initial roadmap-drafting entrypoint.

Inputs:

- `project_brief_path`
- `current_project_roadmap_path`
- `current_tranche_manifest_path`
- `roadmap_change_request_path`
- optional `selected_tranche_id`

Outputs:

- `roadmap_revision_decision`: `APPROVE`, `REVISE`, or `BLOCK`
- `updated_project_roadmap_path`
- `updated_tranche_manifest_path`
- `roadmap_revision_report_path`

Responsibilities:

- consume the current approved roadmap and manifest, not regenerate them from scratch
- revise narrowly around the structured `roadmap_change_request.json`
- preserve unaffected tranche ordering and status
- explicitly mark superseded tranches when the approved revision replaces them

Routing:

- `APPROVE` -> parent drain updates authoritative roadmap/manifest pointers and reselects
- `REVISE` -> internal roadmap revision loop continues inside this phase
- `BLOCK` -> parent drain terminates with roadmap-level block

### 5. `major_project_tranche_design_plan_impl_stack.yaml`

This stack must stop being a one-way `design -> plan -> implementation` pipeline.

Required routing:

- first design approval:
  - reset `implementation_iteration_ledger.json`
  - clear `upstream_escalation_context.json`
  - run plan

- if plan approves:
  - clear `upstream_escalation_context.json`
  - run implementation

- if implementation returns `ESCALATE_REPLAN`:
  - copy `implementation_escalation_context.json` to `upstream_escalation_context.json`
  - rerun plan with the same approved design
  - do not reset the implementation iteration ledger

- if plan returns `ESCALATE_REDESIGN`:
  - copy `plan_escalation_context.json` to `upstream_escalation_context.json`
  - rerun big design

- if big design returns `ESCALATE_ROADMAP_REVISION`:
  - surface `roadmap_change_request.json`
  - complete the selected-tranche stack with tranche outcome `ESCALATE_ROADMAP_REVISION`

### 6. `major_project_tranche_plan_impl_from_approved_design_stack.yaml`

Use the same upward-routing behavior, but start from approved design instead of draft design.

### 7. Major-project drain workflow

Parent drain must handle selected-tranche outcomes:

- `APPROVED`
- `BLOCKED`
- `ESCALATE_ROADMAP_REVISION`

For `ESCALATE_ROADMAP_REVISION`:

1. call `major_project_roadmap_revision_phase.yaml`
2. update roadmap plus manifest
3. reselect next tranche
4. do not mark the current tranche completed
5. if roadmap change supersedes the current tranche, mark it `superseded` in manifest state

## Manifest and Selector Changes

Add terminal manifest status:

- `superseded`

Meaning:

- tranche replaced by roadmap revision
- not selectable
- not counted as completed
- retained for provenance and audit

Selector behavior:

- ignore `superseded` entries

## Decision-Boundary Semantics

### Plan review: `BLOCK` versus `ESCALATE_REDESIGN`

Plan review should use:

- `ESCALATE_REDESIGN` when there is enough design and repository evidence to conclude the tranche or approved design must change
- `BLOCK` only when the plan cannot be completed because required authority or prerequisites are missing outside the plan/design artifacts

Use `BLOCK` for:

- missing or contradictory tranche authority between brief and roadmap that redesign cannot resolve safely
- missing external prerequisite data or repo state that the plan phase cannot infer
- a required human scope decision that the available artifacts do not authorize

Do not use `BLOCK` for:

- a tranche that is too broad
- a design that is internally non-executable
- an approved design that clearly needs to be reshaped or narrowed

Those should route to `ESCALATE_REDESIGN`.

### Big-design review: `BLOCK` versus `ESCALATE_ROADMAP_REVISION`

Big-design review should use:

- `ESCALATE_ROADMAP_REVISION` when there is enough evidence to propose a concrete program-level repair such as split, reorder, prerequisite insertion, or ownership reassignment
- `BLOCK` only when the design/roadmap/brief context is too incomplete or contradictory to author a safe roadmap change request

Use `BLOCK` for:

- project brief is materially missing or contradictory
- required upstream facts are absent and any roadmap change request would be speculative
- repo state lacks the evidence needed to propose a responsible roadmap revision

Do not use `BLOCK` merely because the current tranche should not continue as-is. If there is enough information to request a program-level change, use `ESCALATE_ROADMAP_REVISION`.

## Early-Phase Executability Expectations

The escalation ladder should not wait for implementation churn when tranche shape is already visibly non-executable.

### Initial big-design review

Even on the first design-review pass, big-design review should explicitly assess whether the selected tranche appears executable in one implementation phase under the current roadmap partitioning.

If the design evidence already shows the tranche likely needs split, reorder, or prerequisite insertion, big-design review may choose `ESCALATE_ROADMAP_REVISION` immediately rather than approving a knowingly oversized design.

### Initial plan review

Even without upstream escalation context, plan review should explicitly assess whether the approved design supports an executable plan for one tranche-sized implementation effort.

If the first-pass plan can only be made executable by changing tranche shape, changing accepted architecture, or deferring central acceptance criteria, plan review should choose `ESCALATE_REDESIGN` immediately rather than approving a knowingly non-closing plan.

## Prompt Changes

### Major-project-local prompt family

Do not edit shared prompts under `workflows/library/prompts/design_plan_impl_stack_v2_call/` for this feature.

Instead, add a major-project-local prompt family, for example:

- `workflows/library/prompts/major_project_stack/implement_plan.md`
- `workflows/library/prompts/major_project_stack/review_implementation.md`
- `workflows/library/prompts/major_project_stack/fix_implementation.md`
- `workflows/library/prompts/major_project_stack/draft_plan.md`
- `workflows/library/prompts/major_project_stack/review_plan.md`
- `workflows/library/prompts/major_project_stack/revise_plan.md`

The new major-project-local plan and implementation phases should source those prompts directly.

### `workflows/library/prompts/major_project_stack/implement_plan.md`

No escalation logic change. This step runs before the review loop and does not need the threshold.

### `workflows/library/prompts/major_project_stack/review_implementation.md`

Add:

1. read injected `Implementation iteration context`
2. if `threshold_crossed=false`, escalation is optional
3. if `threshold_crossed=true`, explicitly assess whether local implementation is still the right locus
4. allowed decisions become:
   - `APPROVE`
   - `REVISE`
   - `ESCALATE_REPLAN`
   - `BLOCK`
5. always write `implementation_escalation_context.json`
6. if the decision remains `REVISE` after threshold crossing, include `## Escalation Assessment` explaining why continued local implementation is still justified
7. decision definitions:
   - `ESCALATE_REPLAN`: plan/task decomposition or sequencing is the problem, including cases where plan review may need to escalate to redesign
   - `BLOCK`: the implementation cannot be reviewed safely from the available artifacts

### `workflows/library/prompts/major_project_stack/fix_implementation.md`

Add:

1. read injected `Implementation iteration context`
2. read consumed `implementation_escalation_context`
3. if threshold crossed and latest decision is still `REVISE`, the execution report must include a short escalation assessment stating why local implementation still appears to be the right locus
4. do not silently widen tranche scope or redesign architecture under a `REVISE` path

### `workflows/library/prompts/major_project_stack/draft_plan.md`

Add:

1. read consumed `upstream_escalation_context`
2. if `active=true`, treat it as authoritative evidence about why the prior implementation phase could not close locally
3. the new plan must either:
   - directly address the named plan-level gaps, or
   - make clear that redesign is still required
4. even when `active=false`, explicitly assess whether the tranche already appears too broad or structurally non-executable for one implementation phase

### `workflows/library/prompts/major_project_stack/review_plan.md`

Add:

1. read consumed `upstream_escalation_context`
2. decision enum becomes:
   - `APPROVE`
   - `REVISE`
   - `ESCALATE_REDESIGN`
   - `BLOCK`
3. use `ESCALATE_REDESIGN` when the approved design still does not support an executable plan, either on the first pass or after reconciling the upstream escalation context
4. use `BLOCK` only for missing authority, external prerequisites, or unresolved contradictions that redesign cannot safely repair from the available artifacts
5. write `plan_escalation_context.json`

### `workflows/library/prompts/major_project_stack/revise_plan.md`

Add:

- same escalation-context reading rules
- if the review decision stayed `REVISE`, revise locally
- if the review evidence shows redesign is required, do not fake local plan closure
- if the plan remains non-executable because the tranche is oversized, say so plainly instead of papering over it with more task detail

### `workflows/library/prompts/major_project_stack/draft_big_design.md`

Add:

- read consumed `upstream_escalation_context`
- if `active=true`, treat it as required downstream evidence about why lower phases failed to converge
- even when `active=false`, explicitly assess whether the tranche appears too broad or wrongly partitioned to execute as one implementation phase

### `workflows/library/prompts/major_project_stack/review_big_design.md`

Add:

1. decision enum becomes:
   - `APPROVE`
   - `REVISE`
   - `ESCALATE_ROADMAP_REVISION`
   - `BLOCK`
2. use `ESCALATE_ROADMAP_REVISION` when the problem cannot be repaired by redesigning the current tranche alone and requires a program-level change, including on the first review pass when tranche shape is already visibly wrong:
   - split tranche
   - reorder tranche
   - add prerequisite tranche
   - reassign ownership to another tranche
3. use `BLOCK` only when the available brief, roadmap, and repository evidence are too incomplete or contradictory to author a safe roadmap change request
4. write:
   - `design_escalation_context.json`
   - `roadmap_change_request.json` when escalating roadmap revision

### `workflows/library/prompts/major_project_stack/revise_big_design.md`

Add:

- consume `upstream_escalation_context`
- preserve its downstream evidence rather than discarding it as review noise

### `workflows/library/prompts/major_project_stack/draft_project_roadmap_revision.md`
### `workflows/library/prompts/major_project_stack/review_project_roadmap_revision.md`
### `workflows/library/prompts/major_project_stack/revise_project_roadmap_revision.md`

Add:

- consume `roadmap_change_request.json`
- when active, treat it as authoritative evidence that the roadmap needs revision
- revise narrowly to resolve the requested program-level issue instead of restyling the entire roadmap
- preserve completed and unaffected pending tranche status unless the approved revision explicitly supersedes or reorders them

## Escalation Semantics

### `ESCALATE_REPLAN`

Use when:

- design still looks coherent
- local implementation keeps running into missing executable decomposition, bad sequencing, or omitted prerequisite tasks
- remedy remains within the approved tranche and design

### `ESCALATE_REDESIGN`

Use when:

- implementation remains on a preview/interim route that is structurally incapable of closing the approved denominator
- local fixes would require inventing architecture or silently narrowing scope
- the approved design or tranche shape is the problem

### `ESCALATE_ROADMAP_REVISION`

Use when:

- redesign concludes that tranche-local repair is insufficient
- the fix requires split, reorder, prerequisite insertion, or ownership reassignment at the program level

### `BLOCK`

Use when:

- the current phase lacks enough authoritative information to continue safely
- the required next move is external to the authored artifacts and cannot be repaired by escalating one level up with the available evidence
- any proposed redesign or roadmap revision would be speculative rather than grounded

## T26 Outcome Under This Design

For T26, once cumulative implementation review iterations crossed `10` under the same approved design:

- implementation review would have been forced to explicitly assess whether local implementation was still the right locus
- because the work remained on a preview-only blocked route, `REVISE` would have required a strong justification
- the likely implementation outcome would have been `ESCALATE_REPLAN`
- planning could then decide whether T26 needed plan repair, tranche-local redesign, or a roadmap-level split/recharter

This would not have guaranteed success, but it would likely have prevented the 40-iteration implementation churn.

## Testing Requirements

Add behavior tests, not prompt-phrasing tests.

### Workflow tests

- implementation phase writes and injects `implementation_iteration_context.json` into `ReviewImplementation`
- implementation phase writes and injects it into `FixImplementation`
- implementation phase accepts `ESCALATE_REPLAN` and `BLOCK`
- implementation escalation behavior is exercised only through the new major-project-local implementation phase
- selected-tranche stack routes `ESCALATE_REPLAN` back to plan
- selected-tranche stack does not route implementation directly to big design
- plan phase routes `ESCALATE_REDESIGN` upward
- plan phase distinguishes `BLOCK` from `ESCALATE_REDESIGN` with behavioral fixtures
- big design phase routes `ESCALATE_ROADMAP_REVISION` upward
- big design phase distinguishes `BLOCK` from `ESCALATE_ROADMAP_REVISION` with behavioral fixtures
- roadmap-revision phase consumes `roadmap_change_request.json` and updates the authoritative roadmap plus manifest pointers
- drain workflow handles `ESCALATE_ROADMAP_REVISION` by running roadmap revision and reselection
- selector ignores `superseded`
- upstream escalation context is archived and reset at the documented phase transitions
- implementation iteration ledgers archive and reset only on new design approval or tranche-terminal cleanup

### Resume and migration tests

- resumed runs fail cleanly at phase boundary if required new context artifacts are absent
- rerunning from the affected phase regenerates those artifacts deterministically

## Migration and Rollout

This change is not safely resumable mid-loop without a phase-boundary restart.

Reasons:

- decision enums change
- new required context artifacts appear
- new routing cases appear

Operational rule:

- existing in-flight runs should restart from the affected phase boundary:
  - implementation phase if only implementation escalation support lands
  - plan or design phase if their enums/artifacts change too
- canonical implementation lives in this repository. Downstream repos that vendor or copy these workflows/prompts must sync from the canonical files before launching or resuming affected runs. Downstream-only edits are not the durable implementation.

## Non-Goals

This design does not:

- hard-require escalation after iteration `10`
- inject the full roadmap into implementation prompts
- let implementation review directly mutate the roadmap
- weaken approval gates
- treat environmental/tool failures as redesign unless they actually reveal a wrong phase boundary
