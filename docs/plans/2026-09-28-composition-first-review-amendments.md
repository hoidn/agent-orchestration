# Composition-First Review Amendments Plan

> For agentic workers: use subagent-driven review for the bounded documentation
> changes; the coordinator integrates and verifies the final diff.

**Goal:** apply the owner's requested corrections from the
[composition-first review](../reports/2026-09-28-workflow-lisp-composition-first-review.md).

**Scope:** design and roadmap amendments, plus the separately supplied
feasibility report and regression test. No language implementation, research
selection, or provider calls. The owner's subsequent request authorizes staging
and committing this package. Preserve the concurrent
owner selection of CF-1a and slating of CF-1b ahead of R1b; this amendment task
does not close the remaining feasibility checks or start CF-1b implementation.

**Approach:** keep one type-system owner, an ordinary library helper, and
domain-owned migration adapters. The initial prompt route uses concrete
provider results; direct generic prompt results remain a separate extension.
That keeps the initial change smaller but requires explicit domain adapters.

## Tasks

- [x] Amend `docs/design/workflow_lisp_parametric_type_system.md` with a bounded,
  proposed generic-union contract: constructor identity, recursive argument
  binding, concrete instantiation, diagnostics, and compatibility boundaries.
  Do not relabel the existing implementation or introduce a parallel pipeline.
- [x] Correct `docs/design/workflow_lisp_composition_first.md`: preserve domain
  validation and return data through explicit adapters; identify real callers;
  correct loop capture, retain the owner-chosen first-delivery `S is-record`
  limit and drop the constraint on `I`; separate prerequisite
  investigation from new-feature acceptance; retire only displaced declarations.
- [x] Align CF-1 in
  `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md` with those
  contracts, including the initial concrete-prompt route and subsequent actions.
- [x] Update `docs/index.md`, `docs/design/README.md`, and
  `docs/capability_status_matrix.md` for the corrected scope. Preserve the
  findings report as historical evidence and append its amendment disposition.
- [x] Obtain independent contract and simplification review; inspect the final
  diff, check local links and whitespace, and sweep for stale conflicting claims.

## Verification and routing

Documentation checks cover the amendments; collect and run the supplied
regression module before committing its evidence. No production workflow,
compiler, prompt, or runtime implementation is changed. Earlier runnable checks
remain evidence of the reviewed baseline, not of the proposed capability.

The roadmap is authored prose, not an executable selector. The focused routing
search found no CF-1 manifest/tranche entry. Keep four named foundation
workstreams and the current owner selection; create no queue or manifest.

## Completion evidence

Completed as documentation amendments on 2026-09-28. A Luna implementer amended
the type owner; the coordinator integrated the composition/migration and roadmap
changes and checked the resulting diff. Separate Sol contract and simplification
reviews approved the amended documentation; the obsolete trigger reference
identified by the contract review was removed.

Scoped whitespace checks passed, including the new report and this plan, and
all 25 local link targets in the two governing designs, report and amendment
plan existed. The stale-contract sweep found no remaining requirement for
generic prompt results in the initial slice, whole-module retirement, unchanged
historical hooks or non-record subjects in the first delivery.

Before the owner-requested commit, the other session supplied the
[generic-record exhaustion check](../reports/2026-09-28-cf1a-exhaustion-projection-check.md)
and its regression module. A fresh collect-only run found two tests; execution
returned **1 passed, 1 strict xfailed**. The prerequisite holds, blocked on a
bounded runtime selector fix; this amendment does not implement that fix or
close CF-1a. The roadmap also records the separate pure-inline-hook elaboration
defect and the command/provider-backed test route. Capture/resume and `ctx`
dependency evidence are not claimed. No language implementation or provider
allocation was performed.
