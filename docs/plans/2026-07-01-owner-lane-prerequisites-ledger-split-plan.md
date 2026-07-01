# Plan: Split The Shared Owner-Lane Prerequisite Ledger Out Of Runtime-Native Drain Authoring

Date: 2026-07-01
Status: executed with this change

## Intent

`docs/design/workflow_lisp_runtime_native_drain_authoring.md` Section 9 has
accreted a four-level prerequisite tree (9.1, 9.1.0, 9.1.0.1, 9.1.1, 9.1.1.1,
9.1.2, 9.1.2.1, 9.1.3, 9.2.1-9.2.5, 9.3), each repeating the same
minimum-contract / minimum-behavior-check / adoption-claim template. Each
subsection is effectively a gap design authored inside the target, and
Section 16 mirrors every prerequisite as a negative bullet, creating a
two-list sync obligation.

## Change

1. Move the full prerequisite ledger (former Sections 9.1-9.3, content
   unchanged except renumbering and folding in workaround details that only
   existed in Section 16 mirrors) into a new companion document:
   `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`.
2. Include a former-section mapping table in the new document so existing
   citations (for example the R17 gap design citing Section 9.2.5) stay
   resolvable.
3. Replace Sections 9.1-9.3 in the parent document with one compact
   "Shared Owner-Lane Prerequisites" section: lane summaries, the uniform
   adoption-claim rule, and a pointer to the ledger.
4. Collapse the twelve Section 16 prerequisite-mirror bullets into one
   generic owner-lane-workaround bullet referencing the ledger. Keep
   non-prerequisite stop criteria unchanged.
5. Also apply two small independent fixes from the same review: the
   Section 9 sequencing list numbering skip (1-6, 8, 9) and the Section 13.4
   duplicate acceptance list.
6. Add authority/related-docs entries and routing lines in
   `docs/design/README.md` / `docs/index.md`.

## Non-Goals

- No semantic change to any prerequisite contract, behavior check, or claim
  rule.
- No change to the drain's pending hunks in the parent document; they ride
  untouched.

## Verification

- Grep both documents for stale `9.x` prerequisite references after the move.
- Confirm heading sequence and provenance mapping are complete.
- Confirm the parent document retains all non-prerequisite Section 9 content
  (sequencing list, independent/waiting work).
