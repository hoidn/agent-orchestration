# Backlog Item: Backport Context And Closure Discipline To Generic Stack

- Status: active
- Created on: 2026-04-13
- Plan: none yet

## Scope
Improve the generic design-plan-implement stack by backporting the reusable context and review-discipline patterns that proved useful in the revision-study stack, without importing revision-study-specific manuscript or metrics policy.

The current generic stack carries the original `brief` into design, but later phases primarily judge against the approved design and plan. That lets a narrowed plan be approved as complete even when the original backlog item or epic still has major unfinished work. The stack should preserve the original task authority through plan and implementation review, and should support narrow optional context when a caller has extra source material that affects judgment.

## Required Work
- Pass the original `brief` artifact through the generic plan phase and implementation phase where it is needed for scope and closure review.
- Update generic plan and implementation review prompts to compare the design/plan/execution report against the original brief before declaring the item complete.
- Add a generic optional context artifact, such as `supporting_context`, only if it can stay narrow and typed at the workflow boundary.
- If optional context is added, consume it in design, plan, and implementation review prompts as advisory task context, not as a broad mandatory documentation glob.
- Backport implementation-loop open-findings tracking from the revision-study implementation phase where it is useful for long generic implementation loops.
- Add generic prompt guidance for architecture or contract-affecting design/review/planning steps to read `docs/index.md` first when present, then select relevant specs, architecture docs, workflow guides, and findings docs.
- Add regression coverage or a smoke workflow showing that a broad brief with an intentionally narrowed plan cannot be marked fully complete unless the remaining work is explicitly classified and preserved.

## Non-Goals
- Do not copy revision-study-specific manuscript, figure, metric, changelog, reviewer-response, or scientific-provenance requirements into the generic stack.
- Do not introduce broad `docs/**/*.md` or `specs/**/*.md` injection into provider steps.
- Do not add prompt snapshot tests that assert literal wording.
- Do not create a large canonical phase-interface redesign as part of this item.

## Success Criteria
- Generic plan and implementation reviews can see the original brief when deciding scope and completion.
- The generic stack has a narrow, documented way to pass optional supporting context, or the work records why the current `brief` surface is sufficient.
- Long generic implementation loops can reconcile carried-forward implementation findings instead of relying only on prose in the previous review.
- A smoke run or focused regression demonstrates that a narrowed prerequisite tranche is not silently treated as completion of the original broad backlog item.
