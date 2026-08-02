# Workflow Lisp Post-E2 Stage Sequencing

Status: applied owner-delegated stage picks; every named stage remains
plan- and review-gated.

Date: 2026-08-01

## Decision

In the repository owner's interactive session, Ollie delegated the next
picks for the mandatory serial spine ("pick the next couple things for the
mandatory serial spine", clarified "i meant stage level picks" [verbatim]).
This record applies the delegated picks at the program's one open
sequencing joint, `PASS_E2`:

1. **ES — first effectiveness study (on-spine).** Immediately after
   `PASS_E2`, the post-E2 study program recorded in the
   [pilot forensics and study-inputs report](../reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md)
   executes its first preregistered effectiveness study: the QA-placement
   factorial arm set (DIRECT; design-QA with single-shot implementation;
   product-QA; rich topology), a realistic task per the recorded
   F1 candidate conditions, and a `decision_lock.v1` numeric decision rule
   as required by the
   [lean-pilot design](../superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md).
   ES results are a required additional input to the E3
   continue/narrow/stop review, alongside the accepted E2 plan's Task-10
   mechanism-study review; the future E3 component plan must bind both.
   Rationale: E3 presupposes that orchestrated candidates are worth
   searching over; ES buys that evidence before controller machinery is
   built.
2. **Phase ME — lean-pilot apparatus retirement (off-spine, same
   trigger).** Runs at `PASS_E2` in parallel with ES; it shares no owner
   surface with ES and blocks nothing downstream. Its content stays owned
   by the substrate maintenance track.

Resulting stage spine: E2 close → `PASS_E2` → ES → E3 gate review → E3 or
narrow/stop → P-series (slated successor), with Phase ME parallel at the
`PASS_E2` joint and the L6 lane independent throughout.

## Limits

- Neither pick selects implementation work: ES requires its own
  preregistration and reviewed study plan; Phase ME requires its own
  selection under the substrate maintenance track.
- Nothing here amends `PASS_E2`, the accepted E2 plan, or its Task-10
  study; ES is additive review input for the E3 decision, not a
  replacement for the Task-10 review.
- The E3, P-series, and L6 gates, orders, and entry conditions are
  otherwise unchanged; the completed REC program is unaffected.
- If `PASS_E2` is not reached, this record schedules nothing.
