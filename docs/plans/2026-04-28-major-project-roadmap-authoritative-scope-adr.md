# ADR: Roadmap-Authoritative Tranche Scope

**Status:** Proposed

**Date:** 2026-04-28

**Decision Owner:** agent-orchestration workflow authors

**Related Work:**
- `workflows/library/major_project_tranche_drain_iteration.yaml`
- `workflows/library/major_project_tranche_implementation_phase.yaml`
- `workflows/library/prompts/major_project_stack/draft_plan.md`
- `workflows/library/prompts/major_project_stack/review_plan.md`
- `workflows/library/prompts/major_project_stack/review_implementation.md`
- `docs/plans/2026-04-26-major-project-implementation-escalation-ladder-design.md`
- `docs/plans/2026-04-28-major-project-phase-reentry-write-root-plan.md`
- `docs/plans/2026-04-28-approved-design-redesign-routing-principled-fix-plan.md`

## Context

Major-project tranche workflows currently let design, plan, implementation, and review phases return local decisions that drive the drain manifest. The intended model is that these phases refine and execute the selected tranche, while roadmap revision owns changes to tranche boundaries.

A failure mode showed that the current contracts do not fully enforce that model. A selected tranche can have a roadmap-level objective, then later phases can narrow the active implementation frame to a smaller slice. If implementation review approves that slice, the drain layer currently treats the tranche as completed because it sees `implementation_review_decision=APPROVE` and `item_outcome=APPROVED`.

That is wrong when the omitted work is part of the selected tranche's roadmap-approved acceptance boundary. Local phase approval must not mean "this smaller repair pass is internally consistent"; it must mean "the selected tranche's acceptance boundary is satisfied."

The root issue is split between prompt semantics and deterministic workflow routing:

- Plan prompts currently allow a "current implementation scope" or justified slice.
- Implementation review prompts currently mention explicit deferrals and follow-up work.
- Implementation review has no roadmap-revision escalation outcome.
- Drain completion only sees an approved implementation outcome, not whether the roadmap acceptance boundary was met.

Prompt tightening helps but is not sufficient. The workflow needs a deterministic scope-authority contract.

## Decision

Only roadmap revision may reduce, split, recharter, or move selected-tranche scope.

Design, plan, implementation, and implementation review may discover that the selected tranche scope is too broad, under-specified, wrongly ordered, or impossible under current prerequisites. They may not locally approve a narrower tranche. If satisfying the selected tranche requires changing the tranche boundary, the workflow must route to roadmap revision.

`APPROVE` at the implementation gate means the roadmap-authoritative tranche acceptance boundary is met. It does not mean the latest local implementation slice has no defects.

## Authority Model

### Roadmap Revision

Roadmap revision owns all semantic changes to selected-tranche scope:

- reducing scope
- splitting scope across tranches
- moving work to a successor tranche
- changing prerequisites
- changing completion gates
- changing the acceptance boundary
- reclassifying omitted in-scope work as non-goal, blocked work, or future work

Any such change must update the roadmap, tranche manifest, and generated tranche brief or equivalent selected-tranche context.

### Design

Design owns architecture inside the selected tranche boundary. It may clarify:

- component boundaries
- data contracts
- public and internal behavior
- invariants
- evidence expectations
- risks and blockers

Design may say that the roadmap boundary is incoherent, but it must escalate rather than silently narrow the tranche.

### Plan

Plan owns executable sequencing inside the selected tranche boundary. It may:

- split implementation into tasks
- order prerequisites before dependent work
- define interim checks
- identify independent later tasks inside the same tranche

Plan may use staged implementation steps, but it may not make tranche-defining work non-blocking follow-up unless that deferral is already authorized by roadmap revision.

### Implementation

Implementation owns code and artifact changes needed to satisfy the approved plan and selected-tranche boundary. It may:

- complete the work
- report evidence
- preserve blockers honestly
- fix review findings

It may not redefine completion by normalizing blocked, unsupported, candidate-only, fixture-backed, or partial behavior into the accepted path.

### Implementation Review

Implementation review owns judgment over whether implementation satisfies the selected tranche boundary. It may:

- approve only when the boundary is met
- request local revision for actionable implementation defects
- escalate to replanning for task sequence or decomposition problems
- escalate to roadmap revision for scope-boundary problems
- block when artifacts are insufficient or unsafe to review

It may not approve a smaller delivered scope while recording tranche-defining work as follow-up.

## Required Workflow Changes

### 1. Add a Scope Boundary Artifact

At tranche selection, write a scope boundary artifact for the selected tranche. This artifact should be generated from the roadmap entry, selected tranche brief, and any active roadmap-revision context.

Suggested path:

`<item_state_root>/scope_boundary.json`

Suggested shape:

```json
{
  "tranche_id": "TNN-example",
  "objective": "one-sentence selected-tranche objective",
  "required_deliverables": [
    "behavior, artifact, public API, workflow, or evidence deliverable"
  ],
  "required_evidence": [
    "test, report, catalog, workflow, or benchmark evidence required for completion"
  ],
  "authorized_non_goals": [
    "work explicitly outside this tranche"
  ],
  "authorized_deferred_work": [
    {
      "work": "work not required for this tranche",
      "authority": "roadmap revision, manifest field, or tranche brief reference",
      "handoff": "successor tranche, blocker, or explicit non-goal"
    }
  ],
  "completion_gate": "implementation_approved"
}
```

The artifact should be treated as a deterministic workflow input for design, plan, implementation, and implementation review. Lower phases may explain ambiguity or contradiction in it, but they may not rewrite it.

### 2. Add `ESCALATE_ROADMAP_REVISION` to Lower-Phase Outcomes

Implementation review needs a direct route for scope-boundary failure:

- `APPROVE`
- `REVISE`
- `ESCALATE_REPLAN`
- `ESCALATE_ROADMAP_REVISION`
- `BLOCK`

Plan review should keep `ESCALATE_REDESIGN`, but if plan review determines that the consumed design can only succeed by changing selected-tranche scope, the route should eventually reach roadmap revision rather than repeated local redesign.

Design review already has `ESCALATE_ROADMAP_REVISION`; preserve that route and ensure it is used for tranche-boundary changes.

### 3. Add a Deterministic Completion Guard

Before the drain marks a tranche `completed`, run a guard that compares:

- `scope_boundary.json`
- implementation review decision
- implementation review report
- execution report
- any structured implementation escalation context

The first version can be conservative and mostly structural:

- If implementation decision is not `APPROVE`, do not complete.
- If review or escalation context says required tranche work remains, do not complete.
- If execution report records required deliverables as blocked or deferred without roadmap authority, do not complete.
- If required evidence named in `scope_boundary.json` is absent, blocked, or stale, do not complete.

The guard should produce a structured result:

```json
{
  "completion_status": "COMPLETE|SCOPE_MISMATCH|MISSING_EVIDENCE|BLOCKED|INVALID",
  "scope_boundary_path": "state/.../scope_boundary.json",
  "blocking_reasons": [
    "reason tied to a required deliverable or evidence item"
  ],
  "recommended_route": "complete|revise_implementation|escalate_replan|escalate_roadmap_revision|block"
}
```

Drain completion should use this result, not raw implementation `APPROVE` alone.

### 4. Make Scope Deferral Provenance Explicit

Prompts should use one rule consistently:

> A lower phase may defer work only when the deferral is authorized by the roadmap-level scope boundary. Otherwise, remaining tranche-defining work blocks approval or escalates.

Remove or rewrite language that makes "current implementation scope", "explicit deferrals", or "follow-up work" sound like local authority to reduce the tranche. Those terms are still useful, but only after they are tied to the scope boundary artifact.

## Prompt Contract Changes

### Plan Drafting

Plan drafting should consume `scope_boundary.json` and state whether the plan covers the whole selected-tranche boundary.

Allowed plan behavior:

- sequence tranche work into tasks
- identify dependencies and checks
- call out roadmap-authorized non-goals or deferrals
- state that the scope boundary is not executable and needs escalation

Disallowed plan behavior:

- moving required deliverables to follow-up without roadmap authority
- defining "current implementation scope" as a smaller acceptance target
- using staged implementation as a different definition of done

### Plan Review

Plan review should reject any plan that makes required scope non-blocking follow-up without roadmap authority.

If the design and scope boundary conflict, plan review should escalate to redesign or roadmap revision depending on the locus:

- design lacks architecture but scope is coherent: `ESCALATE_REDESIGN`
- selected tranche boundary itself must change: route to roadmap revision

### Implementation Review

Implementation review should approve only when all required deliverables and required evidence from `scope_boundary.json` are satisfied.

It should treat these as blockers:

- required deliverable remains unimplemented
- required evidence remains blocked or stale
- report says target behavior is still blocked
- local slice is complete but tranche boundary is not
- blocked-state honesty is substituted for target-behavior completion

It should use `ESCALATE_ROADMAP_REVISION` when the only plausible path is to split, reduce, defer, or recharter selected-tranche scope.

## Deterministic Routing

Recommended routing:

1. Tranche selection writes `scope_boundary.json`.
2. Design, plan, implementation, and review consume `scope_boundary.json`.
3. Implementation review may emit `ESCALATE_ROADMAP_REVISION`.
4. A completion guard runs after implementation review `APPROVE`.
5. If the guard returns `COMPLETE`, drain updates the manifest to `completed`.
6. If the guard returns `SCOPE_MISMATCH`, drain routes to roadmap revision instead of completing.
7. If the guard returns `MISSING_EVIDENCE` or `BLOCKED`, drain routes according to the recommended route.

This keeps provider judgment local while giving the workflow deterministic enforcement over completion.

## Backward Compatibility

Existing workflows that do not emit `scope_boundary.json` can initially use a compatibility adapter that derives a minimal boundary from the manifest and tranche brief. The adapter should be strict enough to prevent silent completion when required work is explicitly reported as blocked or deferred.

For existing major-project drain state, do not mutate old item outcomes in place by default. Provide a targeted repair command or runbook for rechecking completed items against the new guard.

## Test Plan

Add behavioral tests, not prompt-text tests.

Required cases:

1. **Approved Slice Does Not Complete Tranche**
   - Scope boundary requires deliverables A and B.
   - Execution report says A complete and B deferred.
   - Implementation review says `APPROVE`.
   - Completion guard returns `SCOPE_MISMATCH`.
   - Drain does not mark the tranche completed.

2. **Roadmap-Authorized Deferral Can Complete**
   - Scope boundary requires A and explicitly authorizes B as successor work.
   - Execution report says A complete and B deferred to the authorized successor.
   - Implementation review says `APPROVE`.
   - Completion guard returns `COMPLETE`.

3. **Missing Evidence Blocks Completion**
   - Scope boundary requires an evidence artifact.
   - Implementation review says `APPROVE`.
   - Evidence artifact is absent or reports blocked.
   - Completion guard returns `MISSING_EVIDENCE`.

4. **Implementation Review Can Escalate To Roadmap Revision**
   - Review decision is `ESCALATE_ROADMAP_REVISION`.
   - Workflow routes to roadmap revision.
   - Manifest is not marked completed.

5. **Plan Cannot Locally Recharter**
   - Plan moves required scope into follow-up without roadmap authority.
   - Plan review does not approve.

## Migration Plan

1. Add the scope boundary artifact generator to major-project tranche selection.
2. Thread the artifact through design, plan, implementation, and review workflow inputs.
3. Add `ESCALATE_ROADMAP_REVISION` to implementation review output contracts and routing.
4. Implement the completion guard as a script with focused unit tests.
5. Update major-project prompts to make roadmap authority explicit.
6. Add workflow-level regression tests for the T26-style approved-slice failure.
7. Run an orchestrator dry-run or smoke check for a major-project tranche workflow.
8. Sync the workflow and prompt changes into downstream repos that vendor these workflows.

## Consequences

### Positive

- A local implementation slice can no longer complete a broader tranche.
- Scope changes become auditable roadmap decisions.
- Review reports can still be honest about blockers without turning blockers into acceptance.
- The drain manifest becomes a stronger source of truth.
- Future failures route to the phase that has authority to fix them.

### Negative

- Tranche selection gains one more artifact.
- Some existing plans that use follow-up sections loosely will need stricter wording.
- Completion may become more conservative until scope boundaries are explicit enough.

### Accepted Tradeoff

The extra boundary artifact and guard are worth the added process because the alternative is a manifest that can record completed work while the project-level deliverable remains blocked.

## Open Questions

1. Should `scope_boundary.json` be fully generated deterministically from the manifest and tranche brief, or provider-authored then reviewed?
2. Should the completion guard parse free-form reports in the first version, or require structured completion fields from implementation review?
3. Should existing completed tranches be rechecked automatically, or only when a downstream dependency fails?

## Recommendation

Adopt this design narrowly for major-project tranche workflows first. Do not generalize it to every review loop until the major-project path proves the artifact shape and guard semantics are stable.
