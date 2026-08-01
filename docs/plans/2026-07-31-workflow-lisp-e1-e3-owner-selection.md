# Workflow Lisp E1-E3 Owner Selection

Status: applied owner selection; implementation remains predecessor- and
review-gated.

Date: 2026-07-31

## Decision

In the repository owner's interactive session, Ollie directed: "select e1
through e3. continue executing roadmap". This record applies that direction
to the authoritative current E-series mapping without importing the
superseded historical E-numbering.

- E1 (`run-ref`) is selected and enters component planning at target 2.24.
- E2 (`trial`) is selected-pending the canonical E1 exit gate and is assigned
  target 2.25.
- E3 (the external gene-bounded controller) is selected-pending the canonical
  E2 exit gate plus review of the first fixed-study results. E3 adds no
  language target.

Selection is not implementation completion and does not waive accepted
feasibility proofs, spec-first amendments, reviewed component plans,
dependency order, TDD, ordered reviews, focused/broad non-security tests,
end-to-end evidence, or tranche exit gates.

## Limits

This decision does not select C1, C2, or C3 from the typed-program-gates
companion; any L6 implementation unit; any P-series item; any remaining
substrate tranche; the parked historical evolution machinery; or security and
isolation work. C1-C3 remain Designed and unselected. The accepted trial-runs
design and program-search boundary invariants continue to govern E1-E3.

E1, E2, and E3 remain separate closure units. Implementation advances in
order even though all three are selected: E2 cannot begin before the
canonical E1 exit gate, and E3 cannot begin before the canonical E2 exit gate
and the fixed-study review.

E1 planning must include the stable structured batch-compiler rejection
surface that the accepted trial-runs design assigns to E1 admission and that
the external E3 controller consumes. That external diagnostic API is not the
separate C1 durable Workflow Lisp `check-workflow` step and does not select
C1.
