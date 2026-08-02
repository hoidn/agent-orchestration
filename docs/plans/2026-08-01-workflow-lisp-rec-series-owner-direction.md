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

The directed subagent critique completed in the drafting session and its
verdicts are persisted as concrete review artifacts:

- [contract/design review](../../artifacts/review/rec-series-roadmap-contract-review.md):
  `APPROVE_WITH_CHANGES`, ten findings, every finding incorporated into the
  revision that entered commit `27c71084`;
- [repository fact-check](../../artifacts/review/rec-series-roadmap-fact-check-review.md):
  `APPROVE`, thirty-one findings, zero wrong citations, all advisories
  incorporated.

A concurrent session, unable to observe those in-session deliveries,
spawned a second reviewer pair; Ollie cancelled it, directing: "dont re
review the roadmap" [verbatim]. That direction stands: with the original
verdicts persisted above and their findings demonstrably present in the
incorporated text, no further pre-incorporation review round is required or
authorized. This section supersedes the earlier statement in this record
that no subagent review verdict existed; that statement reflected the
concurrent session's vantage before the artifacts were persisted.
Incorporation-time verification additionally includes the passing
`tests/test_workflow_lisp_drain_roadmap_routing.py` suite.

## Limits

Incorporation is not selection. This record:

- selects no REC item; every item requires its own owner selection act under
  the roadmap's entry conditions;
- waives no gate, design amendment, reviewed component plan, TDD, ordered
  review, or capability-matrix obligation — the owner's no-re-review
  direction above covers only the one-time pre-incorporation critique of
  the roadmap document itself, whose verdicts are persisted;
- does not amend the E-series program, the P-series slating, or the L6
  utility lane;
- sets no relative priority between the REC-series and the P-series; and
- schedules no REC2 work: REC2 remains a horizon marker behind Gate REC.
