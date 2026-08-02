# REC-Series Roadmap Contract Review

- **Verdict:** `APPROVE_WITH_CHANGES`
- **Reviewer:** independent contract/design review subagent
  (`RecContractReviewer`), spawned 2026-08-01 in the drafting session
- **Subject:** the pre-incorporation draft of
  `docs/plans/2026-08-01-workflow-lisp-recursion-rec-series-roadmap.md`
- **Disposition:** all ten findings incorporated into the revision that
  entered commit `27c71084`; the reviewer judged them "wording-level fixes;
  no structural rework is needed"
- **Provenance note:** delivered in-session on 2026-08-01 and persisted to
  this artifact afterward; a concurrent session, unable to observe the
  delivery, temporarily recorded the review as lost/waived.

## Findings And Dispositions

1. **Invert Gate REC's impact-review burden of proof** (P1). The
   forced-outcome rule triggered only on an adverse impact-review finding,
   leaving "no finding" as a wiggle path to `PROCEED_TO_REC2` even though
   the Invariants section asserts certification/accounting assume statically
   expanded programs; supersession of a forced outcome was undefined.
   [Incorporated: `PROCEED_TO_REC2` now requires an impact review
   affirmatively demonstrating preservation, or a prior accepted E-series
   amendment; a forced or recorded outcome is superseded only by a fresh
   Gate REC record after the enabling change.]
2. **Give Gate REC0 an enumerated, per-item decision contract** (P1). No
   decision artifact kind, only the stop token named, and aggregate
   materiality let an immaterial item ride a material one. [Incorporated:
   Gate REC0 table row (reviewed decision record); exactly-one outcomes
   `PROCEED_BOTH | PROCEED_REC1_ONLY | PROCEED_REC1B_ONLY |
   STOP_REC_SUGAR`; per-item materiality from the report's per-class
   attribution.]
3. **Close the REC1b-only completion hole; fix ADOPT_RUN_BOUNDARY timing**
   (P1). A program narrowed to REC1b could never complete (Gate REC is
   REC1-gated), and the gate record alone read as completion, which the
   E-series pattern rejects. [Incorporated: completion state 2 "REC1b lands
   as the sole authorized item"; `ADOPT_RUN_BOUNDARY` completes only when
   the REC2' documentation lands.]
4. **Pin the semantic-subset claim to exhaustion terminals and effect
   traces** (P2). The forward-compatibility promise covered only the
   convergent case and was untestable as stated. [Incorporated: constraint
   1 now states full observable equivalence — effect sequence, checkpoint
   identities, terminal — for both convergent and exhaustion outcomes, as a
   reviewable obligation on the REC1 amendment.]
5. **State where REC0's rewrite lands and protect the frozen treatment**
   (P2). The rewrite artifact's location was unstated; committing it in the
   pilot tree would mutate frozen treatment evidence; an under-ambitious
   rewrite could inflate residual. [Incorporated: rewrite committed outside
   `workflows/experiments/repository_task_pilot/`, frozen tree unmodified,
   and the report review checks supported forms were used wherever their
   lowering contracts apply.]
6. **Define "real authored usage" for Gate REC entry** (P2). The
   verification-floor exemplar could satisfy the entry reading days after
   landing. [Incorporated: usage authored for real work after landing,
   beyond the floor exemplar; the gate record names the audited corpus and
   time span.]
7. **Cite the exact non-goal list** (P3). "The spec's non-goal list" was
   ambiguous against the frontend specification's own §3 Non-Goals.
   [Incorporated: `specs/index.md` linked explicitly; carve-out names both
   REC1 and REC1b amendments.]
8. **Constraint 5's checklist line amends drafting guide §28** (P3). Entry
   conditions promised a §17-only amendment. [Incorporated: "§17 and §28
   (review checklist)".]
9. **Give REC1b minimal binding constraints and a verification floor**
   (P2). REC1b inherited only generic machinery. [Incorporated: Binding
   REC1b Design Constraints (elaboration-not-semantics equivalence
   including step identity; compile-time-total matching with typed
   diagnostics; non-goals: no partial/dynamic spread) plus a REC1b
   verification floor.]
10. **Link the owner-direction record in the status header** (P3). House
    style makes direction acts linkable artifacts. [Incorporated: status
    links `2026-08-01-workflow-lisp-rec-series-owner-direction.md`.]

## Reviewer's Overall Assessment (verbatim)

"The program shape, ratchet guards (E5 rule application,
never-an-argument-for-REC2 clause, not-schedulable-by-listing), house
style, and evidence base all check out against the repo, but the gate
contracts have four fixable defects […] All are wording-level fixes; no
structural rework is needed."
