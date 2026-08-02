# Workflow Lisp Recursion REC-Series Roadmap

Status: tracked (per the
[2026-08-01 owner direction record](2026-08-01-workflow-lisp-rec-series-owner-direction.md)).
Pre-incorporation review: an independent
[contract review](../../artifacts/review/rec-series-roadmap-contract-review.md)
(`APPROVE_WITH_CHANGES`, ten findings, all incorporated) and an independent
[fact-check review](../../artifacts/review/rec-series-roadmap-fact-check-review.md)
(`APPROVE`, zero wrong citations, advisories incorporated), delivered in the
drafting session and persisted as review artifacts; incorporation-time
verification additionally ran the routing test suite. A second reviewer
pair in a concurrent session was cancelled by owner direction and no
further review round is required. Not active work instructions and not a selector: no
REC item is selected by listing, and REC implementation remains unselected
until this document's entry conditions hold and the owner records a
selection act. Technical definitions for REC1/REC1b land in their own
accepted design amendments at selection time; this document adds only
tracking, ordering, gates, and binding design constraints for those future
amendments.

Created: 2026-08-01

Naming: discussion refers to this as the recursion or "R-series" program.
Item identifiers use the `REC` prefix because `R1`/`R2` already name
PtychoPINN replay tasks in the superseded
[2026-07-23 experiment design](../superpowers/specs/2026-07-23-orc-vs-one-shot-experiment-design.md)
and remain greppable in historical records.

Copy safety: planning reference only; do not use this document as evidence
that any recursion or ergonomics capability is implemented. Authored
workflows remain bound by the current drafting-guide loop rules (bounded
iteration or explicit termination proof) until an owning REC stage is
implemented, verified, reviewed, and reflected in the capability matrix.

## Problem And Evidence Base

Bounded effectful iteration exists only through shape-specific authored
forms: `loop/recur` with `:max` and typed `loop-state`,
`review-revise-loop`, `backlog-drain`, and bounded `list/map-effect`
([drafting guide](../lisp_workflow_drafting_guide.md) §13, §17). The
underlying DSL's own bounded forms — `repeat_until` (v2.7, exhaustion
outputs v2.12) and `for_each` bookkeeping — are not authored Lisp surface.
Pipelines that match none of the authored shapes are hand-unrolled into
cascades of named workflows with full parameter re-threading. The recorded
exemplar is the lean-pilot treatment workflow
`workflows/experiments/repository_task_pilot/task_loop.orc`: 978 lines at
target 2.20 for a 5-8 provider-call pipeline, twelve `after-*` continuation
workflows, and up to 16 re-threaded parameters per stage (the
[pilot forensics report](../reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md)
records how this exemplar's pilot arms actually executed and decomposes the
pilot outcome).

Two distinct verbosity roots follow:

1. **Control flow:** no generic bounded effectful self-call; novel loop
   shapes unroll by hand.
2. **Dataflow:** call sites re-thread individual fields because a typed
   record cannot be spread into a parameter block.

The unrolled cascade was also partly an authoring choice for a frozen
experiment treatment; how much of the exemplar's verbosity survives the
*current* surface is unmeasured. REC0 exists to measure it before any
language change is justified.

## Invariants This Program May Not Weaken

Every REC item preserves, and its reviews must check:

- static step identity (v2.0 stable IDs) and deterministic expansion;
- checkpoint/resume semantics and M2 persistence;
- precommitted budgets and per-step accounting;
- E1 certification through the ordinary full compiler, and E2 exact cost
  recording and accounting parity — both of which assume statically
  expanded programs;
- the master spec's out-of-scope list in
  [`specs/index.md`](../../specs/index.md) (no while loops; the
  v2.16/v2.17/v2.25 nodes stay the only bounded-concurrency exceptions)
  except where an accepted REC1 or REC1b design amendment narrowly extends
  the *authored* surface without changing runtime semantics;
- effect visibility, source-map provenance, and the closed pure-expression
  operator surface.

## Tracked Items

| Item | Work | Kind |
| --- | --- | --- |
| REC0 | Current-surface residual measurement: rewrite the exemplar topology at the newest implemented target using supported forms where their lowering contracts apply; publish a report quantifying residual verbosity by class (control-flow vs dataflow vs instrumentation) with per-item attribution | Authoring + report only; no compiler, runtime, spec, or prompt changes |
| Gate REC0 | Per-item proceed/stop decision over the REC0 report | Reviewed decision record |
| REC1 | Fuel-bounded self-call as frontend expansion: an effectful-body bounded recursion form with a compile-time literal `:max`, unrolled by the compiler into existing statement families; no runtime schema change | Compiler frontend + design amendment |
| REC1b | Call-argument record spread: pass one typed record where a matching parameter block is expected | Compiler frontend + design amendment; separately selectable |
| Gate REC | Evidence gate deciding whether any dynamic-recursion work is ever scheduled | Reviewed decision record |
| REC2 | General (dynamic) in-run recursion | Horizon marker, not scheduled work |
| REC2' | Run-boundary unboundedness: formalize the existing bounded-run re-entry substrate — `resume-or-start` (drafting guide §13.3), `backlog-drain` (§13.6), and the implemented generic run watchdog — as the recorded alternative pattern (bounded runs, durable typed state between runs) | Design/documentation route; alternative terminal |

## Binding REC1 Design Constraints

The future REC1 design amendment must satisfy all of:

1. **Recursion semantics, not loop-counter semantics.** The surface form
   expresses self-call with a required `:max` fuel annotation. The
   amendment must state, as a reviewable obligation, full observable
   equivalence for both outcome classes: for every program and fuel `N`,
   the unrolled implementation and any conforming future dynamic runtime
   with budget `N` agree on the effect sequence, checkpoint identities, and
   terminal — for programs that converge within fuel `N` and for programs
   that exhaust it (reaching the same typed exhaustion terminal after the
   same effect prefix). Authored programs are thereby forward-valid without
   edits.
2. **Call-path-shaped step identity.** Unroll ordinals are structured as
   (call-site, depth) paths, so checkpoints, source maps, and diagnostics
   already carry the identity scheme a dynamic implementation would keep.
3. **Typed exhaustion terminal.** Fuel exhaustion is a typed terminal
   distinct from convergence, matching the existing `loop/recur` exhaustion
   contract; callers must handle it explicitly.
4. **Recorded non-goals.** No runtime frames, no dynamic dispatch, no
   unbounded traversal, no procedure-valued state. REC2 is not implied,
   authorized, or partially implemented by REC1; a dynamic-recursion
   capability may not be smuggled into REC1 as a "small capability
   extension" (the E5 rule, applied here).
5. **Declared cost guardrails.** The amendment names a maximum IR blowup
   policy for nested `:max` unrolling, a diagnostics-legibility requirement
   at depth ordinals, and a drafting-guide review-checklist line requiring
   justification of each authored bound (guarding against `:max 50` as de
   facto unbounded).

## Binding REC1b Design Constraints

The future REC1b design amendment must satisfy all of:

1. **Spread is elaboration, not semantics.** A spread call site is
   observably identical to its hand-threaded equivalent, including step
   identity, source-map provenance, and generated statement families; the
   verification floor proves this equivalence and that no runtime schema
   changes.
2. **Compile-time-total matching.** Record-field-to-parameter matching is
   decided entirely at compile time with typed diagnostics for missing,
   extra, or type-mismatched fields.
3. **Recorded non-goals.** No partial spread, no dynamic or conditional
   spread, no runtime record introspection.

## Sequencing

- **REC0: selectable at any time.** Authoring and report work only; it
  touches no owner surface named by the E-series roadmap's Concurrency And
  Shared-Surface Rules section.
- **REC1/REC1b: after the E program, or by explicit owner acceleration.**
  Both edit the shared compiler frontend. The active E2 component plan owns
  compiler IR/lowering/persistence surfaces, and the E-series rule that no
  two active plans may edit the same compiler owner without a reviewed
  sequencing amendment applies; acceleration therefore requires both the
  owner's decision and that amendment. This roadmap sets no relative
  priority between the REC-series and the
  [slated P-series](2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md);
  the owner orders them at selection time.
- **Gate REC: only after REC1 has post-landing authored usage** (defined
  under Entry Conditions). Not schedulable by listing.
- **REC2: unscheduled horizon.** Enters planning only through Gate REC's
  `PROCEED_TO_REC2` plus its own accepted design and reviewed plan.

## Entry Conditions And Gates

- **REC0 entry:** owner selection act. The rewrite is a non-executed study
  artifact committed outside `workflows/experiments/repository_task_pilot/`
  and named by the report; the frozen pilot treatment tree is not modified.
  REC0 produces
  `docs/reports/<date>-workflow-lisp-rec0-residual-measurement.md` binding
  the rewrite artifact, the measured residual by class with per-item
  attribution (REC1 vs REC1b), and a recommendation. The report's
  independent review must also check that supported forms were used
  wherever their lowering contracts apply, so residual verbosity is not
  inflated by an under-ambitious rewrite.
- **Gate REC0 (reviewed decision record, exactly one outcome):**
  - `PROCEED_BOTH`: the report shows material residual attributable to each
    item;
  - `PROCEED_REC1_ONLY` / `PROCEED_REC1B_ONLY`: only the named item's
    residual is material; the other records stop;
  - `STOP_REC_SUGAR`: neither item's attributable residual is material; the
    report stands as the durable answer.
  Materiality is judged per item from the report's per-class attribution —
  the report must project the further reduction each item would yield on
  the exemplar and justify the projection; an immaterial item may not ride
  a material one. Smallness is decided by the reviewed record, not preset
  here.
- **REC1/REC1b entry:** a Gate REC0 outcome authorizing the item;
  compiler-owner availability per Sequencing; an accepted design amendment
  to the
  [frontend specification](../design/workflow_lisp_frontend_specification.md),
  [design principles](../design/workflow_language_design_principles.md), and
  [drafting guide](../lisp_workflow_drafting_guide.md) §17 and §28 (review
  checklist); an assigned DSL target; a reviewed component plan; TDD with
  narrow-then-broad non-security checks; ordered independent specification
  then quality review; capability matrix and authoring guidance updated at
  completion.
- **REC1 verification floor:** unroll determinism and step-identity tests;
  source-map provenance through depth ordinals; typed-exhaustion tests;
  checkpoint/resume parity between a hand-unrolled cascade and the sugared
  equivalent; proof of no runtime schema change; one end-to-end authored
  usage; IR-size guardrail test at the declared blowup policy.
- **REC1b verification floor:** spread-vs-hand-threaded equivalence tests
  (behavior, step identity, source maps); typed-diagnostic tests for
  missing/extra/mismatched fields; proof of no runtime schema change; one
  end-to-end authored usage.
- **Gate REC entry:** REC1 landed, plus authored usage created for real
  work after landing, beyond the verification-floor exemplar; the gate
  record names the audited corpus and its time span.
- **Gate REC inputs:** an authored-corpus audit of `:max` values and
  exhaustion terminals in committed workflows and run reports; named use
  cases blocked by boundedness with their run-boundary workarounds; a
  feasibility probe report on durable frame persistence, resume
  reconciliation, and dynamic budget accounting; an E-program impact review
  covering certification decidability and exact cost/accounting parity.
- **Gate REC outcomes (exactly one):**
  - `PROCEED_TO_REC2`: requires evidence of material, recurring need that
    run-boundary patterns cannot serve, **and** either an impact review
    affirmatively demonstrating that certification decidability and exact
    cost/accounting parity are preserved, or a prior accepted E-series
    amendment removing the static-expansion dependency. Absent that
    affirmative demonstration or amendment, this outcome is not available;
  - `STAY_BOUNDED`: bounded forms suffice; REC2 remains a horizon marker;
  - `ADOPT_RUN_BOUNDARY`: REC2' is selected as the route; the program
    completes only when the REC2' documentation lands — the gate record
    alone is not completion.
  A forced or recorded outcome may be superseded only by a fresh Gate REC
  decision record issued after the enabling change (such as an accepted
  E-series amendment), never by reinterpreting the existing record.

## Program Stop And Completion

The program is complete under any of:

1. Gate REC0 records `STOP_REC_SUGAR` and the REC0 report stands as the
   durable answer;
2. REC1b lands as the sole authorized item and its acceptance evidence
   stands (Gate REC never convenes without REC1);
3. REC1 lands (with or without REC1b) and Gate REC records `STAY_BOUNDED`;
4. REC1 lands, Gate REC records `ADOPT_RUN_BOUNDARY`, and the REC2'
   documentation lands; or
5. a gated REC2 lands under its own reviewed design and plan.

Landing REC1 is never, by itself, an argument for REC2: acceptance evidence
for each item is its own.
