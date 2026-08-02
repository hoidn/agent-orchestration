# Workflow Lisp REC-Series Owner Direction

Status: applied owner direction; REC selection remains entry- and
review-gated.

Date: 2026-08-01

## Decision

In the repository owner's interactive session, following the bounded-versus-
general-recursion design discussion, Ollie directed: "draft the program; use
subagents to critique/ review; then, if / when you're satisfied with it,
incorporate the finalized program into the roadmaqp" [verbatim]. This record
applies that direction to the
[REC-series roadmap](2026-08-01-workflow-lisp-recursion-rec-series-roadmap.md),
which is incorporated as a tracked program with routing from
`docs/index.md` and the E-series roadmap's successor-ordering paragraph.

## Review Provenance

The subagent critique step did not produce review verdicts. Two independent
reviewers (contract/design and repository fact-check) were spawned; their
outputs were lost before delivery when the session's wait was interrupted. A
second pair was spawned and then cancelled when Ollie directed: "dont re
review the roadmap" [verbatim]. That direction is recorded as an owner
waiver of independent pre-incorporation review. No subagent review verdict
exists for this roadmap; any later claim of one must cite a concrete review
artifact. Incorporation-time verification is the maintainer's directly
measured citation base recorded in the roadmap plus the passing
`tests/test_workflow_lisp_drain_roadmap_routing.py` suite.

## Limits

Incorporation is not selection. This record:

- selects no REC item; every item requires its own owner selection act under
  the roadmap's entry conditions;
- waives no gate, design amendment, reviewed component plan, TDD, ordered
  review, or capability-matrix obligation — the review waiver above covers
  only the one-time pre-incorporation critique of the roadmap document
  itself;
- does not amend the E-series program, the P-series slating, or the L6
  utility lane;
- sets no relative priority between the REC-series and the P-series; and
- schedules no REC2 work: REC2 remains a horizon marker behind Gate REC.
