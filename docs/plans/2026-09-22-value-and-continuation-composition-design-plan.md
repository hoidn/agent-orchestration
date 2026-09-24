# Value And Continuation Composition: Design Drafting Plan

Status: documentation task, not an implementation plan or roadmap selection.

## Scope

Draft incremental corrections to the composition and conversational-handoff
issues exposed by the progressive-execution design. Reuse the existing pure-call
and provider-context proposals rather than creating competing contracts. Keep
unrelated working-tree changes, experiment budgets, and workflow execution out
of this task. Do not implement or commit.

## Drafting Work

1. Check current target-aware transport, loop projection, prompt rendering, and
   existing helper/context designs. Distinguish typechecking from runtime proof.
2. Define independently useful increments for union prompt inputs, rich loop
   state/exit values, pure helper composition, portable provider context, and a
   minimal host-mediated human-input boundary.
3. Specify each increment's owner, semantic contract, limits, removed workaround,
   and integration evidence. Keep new syntax out of ordinary composition fixes.
4. Link the design from the existing proposals and documentation indexes. Correct
   only directly relevant capability wording; do not reschedule roadmap work or
   promote draft behavior into normative specs.
5. Obtain a bounded read-only review, inspect the final changes, and check local
   links, formatting, and consistency. Runtime proof belongs to implementation,
   not to this documentation task.

## Handoff

The deliverable is a draft design with explicit feasibility questions, not a
claim that the increments are implemented. Individual increments may proceed
without waiting for unrelated later ones once their implementation prerequisites
are resolved. Ordinary interface fixes are not gated on research-study outcomes.

## Drafting Result

The incremental design and scoped routing updates are drafted. Read-only review
found no substantive contradictions or overclaims. Local link/code-fence checks
and whitespace checks passed. These verify documentation, not proposed runtime
behavior; implementation prerequisites remain explicit.
