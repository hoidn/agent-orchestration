# Workflow Lisp Composition-First Procedures

- **Status:** proposed; not an implemented authoring surface
- **Kind:** language and standard-library architecture decision
- **Owner:** Workflow Lisp frontend (parametric type system) and standard library
- **Created:** 2026-09-28
- **Implementation target:** unassigned; the parametric type system owner selects
  the generic-union target boundary
- **Roadmap:** [CF-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#cf-1--composition-first-procedures-pending-unselected),
  pending and unselected; it owns ordering, entry conditions, and consequences.
  EL-1 stays independently owned by
  [its own section](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#el-1--effect-contracts-and-analysis-cleanup-pending-unselected).
- **Inspected baseline:** `31580550` (main, 2026-09-28). Every file cited below
  is unchanged since `2574fa2`. The README compile command was run at this
  baseline and exits 0.
- **Supersedes as inputs:** the 2026-09-24 value-oriented procedures draft, the
  2026-09-24 procedure composition and authoring simplification draft, the
  2026-09-28 composition-first draft, and the value-preserving review protocol
  draft they cite. None of those is in the repository. This document is the
  single governing proposal; the owning specifications remain authoritative
  until amended.
- **Notation:** every signature below is schematic. It follows the `:forall`,
  `:where`, `ProcRef[(A B) -> C]`, and `(variant ...)` spellings that exist
  today, but it is not copy-safe `.orc` syntax.

## 1. Decision

Make reusable agent procedures compose as ordinary typed programs. A helper
takes meaningful inputs and compile-time procedure references, and returns the
value it computed together with the domain outcome the caller branches on.
Review/revise is the first worked example, not the organizing abstraction.

Three deliverables, in dependency order:

1. First-order generic unions: compile-time only, instantiated to ordinary
   concrete descriptors before typecheck and lowering.
2. A value-returning `improve` helper in a new library module whose result is
   the flat generic union `Improvement[S F B]`.
3. Inference-default effects through the existing EL-1 design, independently.

Selected over the alternatives: a flat union rather than a record wrapper around
the legacy concrete result; the existing bounded-loop semantics rather than a
reserved final review; no counters, seeds, snapshots, version identifiers,
explanation surfaces, or executor extraction in the first release.

## 2. What the repository shows

| Observation | Locator | Consequence |
| --- | --- | --- |
| `review-revise-loop-proc` takes an unused `ctx`, seeded `initial_review_report` and `initial_findings`, fixes inside the `REVISE` branch before `continue`, and its `:on-exhausted` projection returns the previous iteration's review beside the already-fixed candidate. The result carries no candidate. | `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` | This is the defect. It is a value-return and evidence-pairing problem, not a budget problem. |
| Two example callers restate the three-variant result union and re-wrap every arm; a third matches and re-wraps two arms. | `workflows/examples/review_revise_design_docs.orc`, `review_revise_parametric_design_docs.orc`, `kiss_backlog_item.orc` | The type-system owner's recorded revisit trigger for generic type definitions is "a second migration-destined form whose callers must each restate a stdlib-shaped union of three or more variants." Drain callers were the first; review callers are arguably the second, at HEAD, before any new feature. |
| Genericity is `defproc`-only. `ProcRef` signatures are "the primary binding source for type parameters that do not appear in first-order parameter positions"; matching is invariant; specialization identity already includes concrete type argument identities. | `docs/design/workflow_lisp_parametric_type_system.md`, Core Model, Deferred Extensions, Specialization Pipeline, Interaction With Macros and ProcRef | Binding `F` and `B` through hook return positions needs no new inference rule, only type application in type positions. |
| At target 2.29+, initial state, `continue`, `done`, explicit exhaustion, and committed resume preserve whole record/union values; `:on-exhausted` projects state roots and fields with no exhaustion-time evaluator. Without `:on-exhausted`, exhaustion is a failed loop. Top-level `Optional` loop state is not admitted. | `docs/design/workflow_lisp_frontend_specification.md` §13.1; `specs/dsl.md` loop/recur and `repeat_until.on_exhausted` | `EXHAUSTED (value state.current)` is inside the supported projection. A seedless "last feedback" field would need `Optional` loop state, which is not available; that is why exhaustion carries no feedback. |
| The findings validator checks the schema string, a safe relative path, and the presence of an `items` key. | `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py` | The legacy carrier is intentionally minimal. It is preserved, not tightened. |
| The README compile command succeeds and the example is already exercised by `tests/test_workflow_lisp_examples.py` and nine other modules. | `README.md` First Compile Check | No new CI gate is needed. The `(call build-review-runtime-owned)` shape is the runtime-bootstrapped `RunCtx` contract, not a defect. |
| EL-1 distinguishes omitted from explicit-empty clauses; the audit shows specialized forwarding helpers acquire effects under empty clauses. | `docs/design/workflow_lisp_effect_ledger_simplification.md`; `docs/reports/2026-09-08-workflow-lisp-effect-tracking-audit.md` | Adopt EL-1 as written. Migration must be definition-origin aware. |

## 3. Interface

```text
(defunion Decision :forall (F B)
  (APPROVE (evidence F))
  (REVISE  (feedback F))
  (BLOCKED (reason B)))

(defunion Improvement :forall (S F B)
  (APPROVED  (value S) (evidence F))
  (BLOCKED   (value S) (reason B))
  (EXHAUSTED (value S)))

(defproc improve
  :forall (S I F B)
  ((initial S)
   (inputs I)
   (review ProcRef[(S I) -> Decision[F B]])
   (revise ProcRef[(S I F) -> S])
   (limit Int))
  :where ((S is-record) (I is-record))
  -> Improvement[S F B])
```

`S` is the subject, `I` the fixed inputs, `F` the domain's assessment or
feedback type, `B` the domain's blocker type. `S` and `I` bind from the
first-order parameters; `F` and `B` bind from the hook signatures.

What each variant promises:

- **APPROVED.** The selected `review` procedure approved `value` under the
  domain's policy, and `evidence` is the assessment that approved it. Ordinary
  local dataflow establishes that pairing for an immutable record. Approval is
  not proof of substantive correctness.
- **BLOCKED.** `value` is the candidate the reviewer refused to assess further.
  It is available for intervention. It is not approved.
- **EXHAUSTED.** `value` is the latest valid candidate the loop produced. It may
  be an unreviewed final revision. The variant carries nothing that could be
  mistaken for an assessment of it.

Why a flat union rather than `{candidate, outcome}`: no cross-field status
relationship, no seed state, no `Optional` loop state, no candidate/evidence
mismatch on exhaustion, and no generic records. It also matches the shape the
type-system owner's trigger describes.

**Accepted tradeoff.** Both document examples today consume
`last_review_report` and `findings` in their `EXHAUSTED` arm. Under this
contract a domain that needs the feedback that produced the final revision
folds it into `S` in its `revise` hook, for example a `last_review_report`
field on the document subject record. The loop does not change for it.

**Fixer-side blockage** is an extension point. A sibling helper whose `revise`
returns a value-carrying union can be added when a maintained caller needs it.
In that extension, a blocked revision must return the last reviewed candidate,
never a partially modified one carrying the old assessment.

## 4. Loop and termination

```text
state = {current: initial, inputs: inputs}

(loop/recur :max limit
  :state state
  :on-exhausted (variant Improvement EXHAUSTED :value state.current)
  (fn (state)
    (match (review state.current state.inputs)
      ((APPROVE a) (done (variant Improvement APPROVED :value state.current :evidence a.evidence)))
      ((BLOCKED b) (done (variant Improvement BLOCKED  :value state.current :reason b.reason)))
      ((REVISE r)  (continue (loop-state :like state
                               :current (revise state.current state.inputs r.feedback)))))))
```

- One iteration reviews the current candidate and, when asked, revises it. The
  final permitted iteration may therefore end in an unreviewed revision. That
  is the existing bounded-loop policy and it is what `EXHAUSTED` means.
- `limit` keeps the existing `:max` semantics, including zero handling. No
  positive-limit precondition is added: the frontend has no such contract and
  this change does not justify one.
- `inputs` stays in loop state because loop bodies do not close over outer
  bindings. That is carriage, not policy state.
- Cancellation, malformed hook output, timeouts, and provider failures remain
  runtime outcomes under the existing recovery contract. None becomes a
  fabricated `EXHAUSTED`.
- The exhaustion projection uses a direct state field, which the 2.29+
  projection rules admit. No counter, evaluator, or seeded evidence is needed.

## 5. Boundaries

**Typed feedback.** `F` is domain-owned. Validate provider output at the
provider result boundary, once, and forward the typed value. A caller whose
review hook is a `defprompt` declares its result as the instantiated
`Decision[MyFeedback MyBlocker]` once instantiation precedes prompt-contract
generation. Until the prompt-contract owner admits that, a caller-side pure
adapter converts a concrete decision type into the instantiated union. The
legacy `ReviewFindings.v1` carrier and validator stay as they are.

**Documents.** `is-record` cannot express immutability, so a path-bearing `S`
is admitted with exactly the semantics the examples have today: approval refers
to the reviewed read of that path. Snapshot or version references are adapter
work owned by a named caller and the artifact allocator, not by the loop, and
not by this release.

**Inputs.** Semantic requirements and execution settings may be grouped in
application-owned records. No universal configuration record. Removing `ctx`
from the helper must first confirm that no resource dependency reaches the
identity or resume checks only through it.

## 6. Language delta: generic unions

- `defunion` accepts `:forall`. Type application is admitted in type positions,
  including `ProcRef` parameter and return positions and `defprompt` results.
- Instantiate through the existing pipeline: resolve call-site types, check
  constraints, instantiate, typecheck, lower. Constructor identity is the
  defining module and declaration plus canonical concrete argument identities.
  Imported aliases do not create new constructors; equal short names in
  different modules stay distinct.
- Reject wrong arity, unresolved parameters, unsupported payload shapes at the
  boundaries where they are used, and instantiation cycles. Argument matching
  is invariant, consistent with `ProcRef` matching.
- Demonstrate an unrelated `Outcome[T E]` union so the mechanism is not keyed
  to review names. No `Decision`, `Improvement`, or `Outcome` name exists in
  the stdlib or `workflows/` today. Do not reuse `Selection`; `std/drain`
  owns that vocabulary.
- Generic records are not required by this design. Add them only for a named
  caller, through the same owner.
- Owner action: amend the Deferred Extensions entry. The recorded trigger is
  arguably met by the review callers listed in §2; the owner decides. No
  return-only inference, explicit type application at call sites, generic
  workflows, or trait aliases are requested.

## 7. Effects

Adopt EL-1 unchanged: omitted clause infers; explicit empty requires no tracked
effects after hook resolution; explicit nonempty requires a subset with
provider and command identities preserved. Migrate forwarding helpers to
omission on the new regime, definition-origin aware.

Before EL-1 lands, `improve` declares no command effect, because it runs no
validator command, and relies on the current regime's forwarding through
specialized hooks. Record that summary in its specialization evidence; EL-1
later replaces it with omission. Neither change waits for the other.

## 8. Migration

- New module, provisionally `std/improve`, exporting `Decision`, `Improvement`,
  and `improve`. `std/phase` is retained unchanged; its semantics, including
  the terminal-evidence mismatch, are documented as legacy.
- New declarations change bundled-module digests and require a target bump.
  No checkpoint compatibility is claimed between the two APIs.
- The two document examples migrate with a concrete adapter procedure per
  caller that converts their existing `ReviewDecision` into
  `Decision[ReviewEvidence BlockerClass]`, hooks untouched. That is also the
  first substitution demonstration.
- Delete `std/phase` and its macro only after the eight repository callers
  are migrated. That deletion is a later decision, not part of this design.

## 9. Feasibility prerequisites

The design depends on four capabilities that no current specification or
fixture demonstrates. Each needs a minimal executable proof, or a recorded
design gap, before an implementation plan is accepted. None is settled by this
document.

| Prerequisite | Why it is unproven | Proof required |
| --- | --- | --- |
| Generic unions (`defunion :forall`, type application in type positions) | The parametric type system defers generic type definitions; only `defproc` genericity exists. | The type-system owner amends the Deferred Extensions entry, then a fixture instantiates a union through an imported generic procedure, a `ProcRef` return position, loop state, a terminal result, and downstream consumption. |
| `:on-exhausted` projecting a type-parameter-typed record state field | The 2.29+ rules admit record fields of transportable state, but every in-repo generic loop fixture (`generic_loop_union_*`, `std/phase`, `std/drain`) projects only scalar or concrete fields. | A generic `defproc` with `:where ((S is-record))` whose `:on-exhausted` returns `state.current` of type `S`, exercised through instantiation, run, and committed-boundary resume. If unsupported, correct the loop/exhaustion owner; do not reintroduce seeds or counters. |
| `defprompt` results as instantiated generic unions | Prompt contracts are generated from concrete descriptors; ordering against instantiation is unspecified. | Either a provider hook declares `Decision[MyFeedback MyBlocker]` and its contract validates, or the caller-side pure adapter route is recorded as the supported path for the first slice. |
| No compiler branch keyed to review names | A negative architecture claim. | An unrelated `Outcome[T E]` union passes the same boundaries with no consumer-specific code. |

Removing `ctx` from the helper is not a capability question but still needs a
check: confirm that no resource dependency reaches identity or resume
validation only through that parameter.

## 10. Evidence requirements

These requirements are status-independent. The roadmap decides when each is
exercised.

- **Value return.** A changed candidate reaches a deterministic downstream
  consumer through the helper's return value, never through private state,
  an output directory, or an alias to external mutation.
- **Terminal pairing.** Approval carries the assessment that approved the
  returned value. Exhaustion after a changed final candidate carries that
  candidate and nothing that could be read as its assessment. Reviewer
  blockage returns the candidate that was refused.
- **Malformed feedback.** A hook result that fails its declared type is a
  contract failure at the provider or adapter boundary; no result variant is
  published.
- **Inline and imported agreement.** The same hooks and supplied operation
  results produce the same semantic outcome and ordered logical hook
  operations whether the helper is inline or imported, on fresh runs.
  Identical generated identifiers across changed source are not required.
- **Recovery.** Interruption after a committed review and after a committed
  revision restores the committed values and continues under the existing
  recovery contract. No exactly-once claim for external effects.
- **Substitution.** Replacing the selected review procedure with a sequential
  two-review-plus-adjudication procedure changes only the selected hook and
  its implementation.
- **Migration.** The two document examples migrate through caller-side
  adapter procedures with their hooks unchanged, and the README compile
  command keeps passing through the existing example test.
- **Realistic change.** Adding a typed proposal field consumed downstream is
  recorded as the edited files and any leaked execution plumbing. This is a
  qualitative record, not a productivity score, and needs no new harness.

Verification follows AGENTS.md: narrow selectors first, then the full suite,
plus a public compile/run/resume path for the new caller.

## 11. Dropped from the input drafts, with reason

- Invariants V1–V8 and the C01–C22 acceptance matrix as gates: no current
  authority creates them; §9 keeps the checks that protect real contracts.
- R0 contract freeze, O1 explanations, M1 executor extraction: no named
  problem.
- README CI gate: it already exists.
- Positive-budget precondition and `max_reviews` with a reserved final review:
  no frontend support for the former; the latter changes the last permitted
  action and published artifacts to fix a mismatch that dropping exhaustion
  evidence already fixes.
- `ReviewResult[T]` record wrapper and generic records: unnecessary once the
  result is a flat union.
- `SubjectVersion`, `BoundReview`, universal revision identifiers: adapter
  concerns for a named document caller.
- `Selection[T]` as the non-review example: collides with `std/drain`.
- The 363-sequence standalone model: validates pseudocode, not this repository.
