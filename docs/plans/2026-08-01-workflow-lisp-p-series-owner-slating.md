# Workflow Lisp P-Series Owner Slating

Status: applied owner slating; P selection remains entry- and review-gated.

Date: 2026-08-01

## Decision

In the repository owner's interactive session, Ollie directed: "slate P
behind E". This record applies that direction to the tracked
[P-series roadmap](2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md)
and the incorporated
[E-series program](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md):

- The P-series (P1-P5) is slated as the successor program queued behind the
  E program. On the E program's recorded completion, or on an explicit owner
  closure/re-park decision for E, the P-series becomes the next program
  eligible for selection without a separate what-comes-next decision.
- P1 remains first in internal order per the accepted
  [language server design](../design/workflow_lisp_language_server.md)
  recommendation, unless the selecting decision records otherwise.

## Limits

Slating is not selection. This record:

- selects no P item and creates no component plan;
- waives no P entry condition: each selected item still requires a
  language-server design amendment, its own reviewed component plan, TDD with
  narrow-then-broad non-security checks, ordered independent specification
  then quality review, and capability-matrix plus authoring-guidance updates;
- does not close, re-park, bound, or otherwise change the E program or any
  E-series gate;
- leaves owner acceleration as the sole path to an earlier P selection; and
- does not touch the L6 utility lane, which remains P-independent and
  requires its own explicit owner activation naming the selected unit or
  units.

Standing bounds inherited from the language-quality roadmap remain binding:
the language server stays a read-only consumer of production compile entry
points, with no second analyzer and preserved CLI/LSP compile-request parity.
