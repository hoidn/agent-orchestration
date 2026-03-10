# Backlog Item: Right-Size Typed Pipeline And Remove Duplication

- Status: active
- Created on: 2026-03-10
- Depends on:
  - `docs/backlog/active/2026-03-09-typed-workflow-ast-ir-pipeline.md`
- Plan: none yet

## Scope
Reassess the current typed workflow pipeline after the AST / executable-IR migration work and deliberately reduce LOC, complexity, and duplicated representations where the new architecture is not paying for itself.

This item is not a generic cleanup ticket. It is a principled follow-on to answer a specific architectural question:

- which parts of the typed surface AST / executable IR / projection stack are permanent and worth keeping
- which parts are temporary migration scaffolding or duplicated compatibility surfaces
- which parts should be collapsed into a simpler steady-state runtime model

The goal is to preserve the real benefits of the migration while removing unnecessary architectural tax.

## Why This Is Backlog-Worthy
The typed-pipeline migration appears to have added substantially more code than the final cleanup tranche is likely to remove. That creates a real risk that the repo is carrying:

- a second architecture without proportional payoff
- compatibility layers that are no longer necessary
- duplicated representations of the same workflow facts across surface AST, executable IR, projection metadata, and runtime step dicts
- complexity that makes future maintenance harder even if correctness improves

The current project should not assume that "finish Tranche 5" is enough. If the permanent architecture is too expensive relative to the defects it prevents and the capabilities it unlocks, the steady-state design should be simplified explicitly rather than preserved through inertia.

## Desired Outcome
This follow-on should leave the repo with:

- a measured split between:
  - permanent typed-language architecture
  - temporary migration scaffolding
  - duplicated compatibility layers
- a clear decision on the steady-state middle ground:
  - keep typed surface AST
  - keep only the executable-IR and projection pieces that materially improve correctness or maintainability
  - remove or collapse layers whose only purpose is historical transition
- a smaller and easier-to-reason-about workflow runtime
- less duplicated logic between loader, lowering, projection, and executor paths

This item is successful only if it reduces architectural surface area in a justified way, not merely by deleting code opportunistically.

## Required Review Questions
Any follow-on plan must answer these questions explicitly:

1. Permanent architecture
- Which typed pipeline pieces are clearly worth keeping?
- What concrete defect classes or feature extensions do they enable?

2. Transitional scaffolding
- Which modules, helpers, and compatibility adapters exist only because of migration staging?
- Can they be deleted now, or are they still required by unresolved callers?

3. Duplicated representations
- Where does the same workflow fact currently exist in more than one form?
- Which representation should be the single source of truth in steady state?

4. Cost / benefit
- How many LOC are permanent architecture versus transitional overlap?
- What runtime or maintenance problems are prevented by the permanent pieces?
- Are there simpler alternatives that preserve most of the value?

## Measurement Expectations
Before implementation begins, the follow-on plan should quantify at least:

- LOC added by permanent typed-pipeline architecture
- LOC still attributable to transitional scaffolding or compatibility overlap
- concrete defects prevented or capabilities unlocked by the permanent architecture

This is not for vanity metrics. It is the minimum evidence needed to justify whether the current design should be simplified, preserved, or narrowed.

## Likely Redesign Targets
The follow-on plan should evaluate at least these areas:

1. Runtime step representations
- determine whether the executor still needs both typed node metadata and reconstructed runtime step dicts
- collapse to one authoritative runtime representation wherever possible

2. Bundle / projection / compatibility helpers
- identify which helpers are true steady-state API and which are historical compatibility shims
- remove or merge helpers that merely translate between adjacent internal layers without adding meaningful abstraction

3. Lowering and projection boundaries
- keep projection metadata that is necessary for reporting, resume, and loop bookkeeping
- remove projection or compatibility fields that only exist to mirror legacy indices or payloads no longer needed

4. Executor layering
- identify where the executor still pays a complexity tax for a more IR-pure design than the repo actually needs
- simplify toward a stable middle ground rather than further increasing abstraction depth

5. Test architecture
- distinguish tests that protect real architectural invariants from tests that only pin transitional compatibility shapes
- retire or rewrite the latter as simplification lands

## Non-Goals
This item should not be used to justify:

- reverting to raw mutable workflow dicts everywhere
- deleting typed surface AST without a replacement design
- broad runtime rewrites unrelated to the typed-pipeline cost question
- performance work that is not tied to representation simplification
- speculative compiler infrastructure work

## Entry Criteria For A Follow-On Plan
Before implementation starts, the plan should:

- identify the minimum permanent architecture worth preserving
- name the specific modules/symbols likely to be deleted or collapsed
- explain the target steady-state data flow from authored YAML to runtime execution
- separate "delete now" work from "only after active migrations finish" work
- include characterization coverage to prove the simplification does not regress current behavior

## Success Criteria
This backlog item is satisfied only if a follow-on design and implementation:

- materially reduces internal duplication or architectural surface area
- produces a simpler steady-state story for how workflows move from source to execution
- preserves the defect-prevention and feature-extension value that justified typed internals in the first place
- leaves the repo with fewer migration-era abstractions than it has today
