# Effect Contracts And Pure-Call Composition: Design Drafting Plan

Status: documentation task; not an implementation plan or work-selection record.

## Scope And Authority

The owner requested designs corresponding to the
[effect-tracking audit](../reports/2026-09-08-workflow-lisp-effect-tracking-audit.md)
and the subsequent design-implications discussion. Revise the existing
[EL-1 proposal](../design/workflow_lisp_effect_ledger_simplification.md), draft a
separate pure-call composition target, and reconcile dependent design/routing
text. Preserve unrelated working-tree changes. Do not implement, commit,
activate roadmap work, or steer an external agent as part of this task.

The documentation hub, language principles, current frontend/effect contracts,
WCC normalization contract, and provider-context proposal govern drafting.
Current authoring guidance remains current; future behavior must be labelled.

## Drafting Sequence

1. Confirm source consumers, specialization semantics, current normalization,
   and persistence boundaries with a read-only scout and local inspection.
2. Revise EL-1 around inference-default optional identity-aware restrictions,
   explicit-empty semantics, imported/generated contract provenance, migration,
   inferred inspection, and independently justified metadata cleanup.
3. Draft pure-call composition separately: semantic effects versus expression
   representability; ordinary inline helpers as the first proof; evaluation,
   source/call identity, and replay obligations; principled expansion or
   foundational revision if useful composition remains blocked.
4. Align provider-context implications and add narrow proposed-design pointers
   to baseline/authoring docs. Update design/capability/index routing and stale
   EL-1 roadmap summaries without changing selection or allocation.
5. Obtain a read-only technical design review, adjudicate findings, and inspect
   the final task-specific diff and link/consistency checks.

## Acceptance And Claim Limits

- No apparently checked subject becomes unchecked decoration.
- No old generic or generated empty declaration is silently reinterpreted.
- Annotation relief, expression composition, and representation cleanup have
  independent contracts and evidence; none claims another's benefits.
- Runtime evidence is retained; no execution-safety investment criterion or
  direct tool executor is introduced.
- All five research axes include consequent improvement, reconsideration, or
  simplification, not merely a passing minimum example.
- Feasibility gaps are explicit; examples for proposed behavior are not
  advertised as runnable. Plans for implementation follow resolution/selection,
  not this drafting task.
- Document checks and review verify this change. Runtime tests would not prove
  an unimplemented proposal; future implementation designs require public-entry
  compile/run/resume evidence and proportional regression checks.

## Routing Boundary

The follow-on roadmap identifies itself as authored prose, not an executable
selector. This task introduces no queue, manifest, target version, or new
selected item. EL-1 and PC-1 retain their existing selection/allocation gates;
pure-call composition is a separately reviewable companion, not an implicit
prerequisite for all research or all context work.

## Drafting Result And Verification

Drafting steps 1–5 are complete. The revised EL-1 and separate pure-call target
remain proposed, with feasibility prerequisites rather than implementation
claims. Provider-context and discoverability/roadmap text now distinguish the
independent changes. The audit retains its original findings with an explicit
note identifying the earlier EL-1 revision it reviewed.

Read-only technical review approved the artifacts as proposed designs, not as
resolved implementation architecture. Defining-scope subject resolution,
restriction-origin/version carriage, early-enough normalization, once-only
pure-payload representation, and inferred editor projection remain prerequisites.

Fresh documentation checks passed: 87 local link targets and code-fence balance
across the two effect/composition targets, provider-context design, this plan,
and audit; both targets are discoverable from all three canonical routing
surfaces. Whitespace/diff checks passed. No code, tests, workflow prompts,
machine-readable selection state, runtime behavior, or live runs were changed
by this drafting task; runtime tests would not verify these unimplemented
proposals and were not run. No commit or implementation selection was made.
