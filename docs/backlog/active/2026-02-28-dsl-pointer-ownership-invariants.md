# Backlog Item: Prewritten Output Pointer Mode Follow-On

- Status: parked
- Created on: 2026-02-28
- Prior plan: `docs/plans/2026-02-28-dsl-pointer-ownership-invariants-implementation.md` (superseded in part by `docs/plans/2026-03-02-v14-consumes-read-only-pointer-semantics.md`)
- Plan: none yet

## Reactivation Rule
Do not reactivate this item unless a concrete workflow or example demonstrates that `v1.4` read-only consume semantics are still insufficient and that an explicit prewritten-output-pointer contract would remove real prompt discipline or shell-glue burden.

## Scope
Reframe the old pointer-ownership backlog around the narrower feature that still appears useful after the `v1.4` consume-semantics change: an optional authored way to declare that an `expected_outputs.path` file is prewritten before step execution and must remain unchanged across the step.

This is no longer the primary mechanism for preventing consume-time pointer clobbering. `v1.4` already moved relpath consumes to read-only pointer semantics, so the remaining problem is smaller and more specific:
- some deterministic handoff patterns still want a step to read a preselected output pointer file
- that pointer file should be treated as an immutable contract input to the step
- the runtime should be able to enforce that invariant instead of relying on prompt discipline

## Why The Old Framing Is Out Of Date
The original February item assumed pointer ownership had to be fixed by introducing `expected_outputs.path_mode` as the main contract for preventing downstream consume-time pointer mutation.

That is no longer the right framing because:
- the later `v1.4` design and implementation direction already addressed the major ownership bug by making relpath consumes read-only
- the current remaining gap is not "make pointer ownership sane everywhere"
- the current gap is "add an optional stronger contract for workflows that intentionally prewrite an output pointer and want the runtime to verify it stayed immutable"

So this item should not be executed as the original February plan. It now needs a new, narrower design.

## Desired Outcome
This follow-on should leave the DSL/runtime with:
- an optional deterministic contract for prewritten output pointer files on provider/command steps
- no change to normal `expected_outputs` behavior by default
- no regression to the already-established `v1.4` read-only consume semantics
- clear docs distinguishing:
  - producer-owned artifact pointers
  - `v1.4` consume-time read-only behavior
  - optional prewritten-pointer step contracts

## Likely Design Direction
The follow-on plan should evaluate an additive surface such as:
- `expected_outputs[*].path_mode: write|prewritten`

with semantics like:
- `write` keeps current behavior
- `prewritten` requires the pointer file to exist before step execution
- `prewritten` verifies the pointer file contents remain unchanged across the step
- existing relpath validation (`under`, `must_exist_target`, canonicalization) still applies to the referenced target

The plan should also evaluate whether this belongs on `expected_outputs` at all, or whether there is a cleaner contract surface now that `v1.4` has already changed consume ownership semantics.

## Non-Goals
This backlog item should not be used to justify:
- reworking `v1.4` consume semantics again
- redesigning the top-level artifact registry
- adding broad new output policy families beyond the specific prewritten-pointer use case
- treating pointer immutability as a general "plan completion" or workflow correctness validator

## Entry Criteria For A Follow-On Plan
Before implementation starts, the follow-on plan should:
- explain exactly what user-visible problem still remains after `v1.4`
- justify why a new authored surface is better than prompt guidance plus existing dataflow contracts
- decide whether the right home is `expected_outputs.path_mode` or another narrower contract
- identify the compatibility story for existing workflows
- include focused regression coverage for prewritten-pointer immutability without reopening legacy consume-pointer behavior

## Success Criteria
This backlog item is satisfied only if a follow-on design and implementation:
- addresses a real remaining deterministic handoff gap after `v1.4`
- keeps normal `expected_outputs` flows unchanged by default
- preserves current consume ownership semantics
- documents the ownership model clearly enough that authors do not confuse this feature with the already-landed read-only consume behavior
