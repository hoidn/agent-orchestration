# Backlog Item: Workflow Executor Kernel / Transport Redesign

- Status: active
- Created on: 2026-03-09
- Plan: `docs/plans/2026-03-09-workflow-executor-kiss-refactor-plan.md` (precursor; follow-on redesign plan still needed)

## Scope
Follow the completed KISS consolidation with a narrower but deeper redesign of the remaining `executor.py` hot spots: the top-level execution kernel, provider/command transport seam, and the integration boundary between routing authority and step-kind execution. The goal is not to split the file further for its own sake, but to reduce real conceptual load by making the kernel smaller, making transport execution more self-contained, and preserving explicit authority over run status, cursor movement, routing, and persistence. Any follow-on work should stay concrete, avoid framework-style abstractions, and preserve external workflow/state behavior unless a deliberate contract change is separately designed and reviewed.
