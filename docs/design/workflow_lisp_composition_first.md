# Workflow Lisp Composition-First Procedures

- **Status:** proposed; not an implemented authoring surface
- **Kind:** language and standard-library architecture decision
- **Owner:** Workflow Lisp frontend (parametric type system) and standard library
- **Created:** 2026-09-28
- **Implementation target:** unassigned; the parametric type system owner selects
  the generic-union target boundary
- **Roadmap:** [CF-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#cf-1--composition-first-procedures-pending-unselected),
  which owns selection, ordering, entry conditions, and consequences.
  EL-1 stays independently owned by
  [its own section](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#el-1--effect-contracts-and-analysis-cleanup-pending-unselected).
- **Evidence:** original repository inspection at `31580550`; the
  [design review](../reports/2026-09-28-workflow-lisp-composition-first-review.md)
  records baseline checks, corrections and their limits. The
  [exhaustion projection check](../reports/2026-09-28-cf1a-exhaustion-projection-check.md)
  separates generic record expressibility from runtime state-selection correctness.
  This proposal does not treat existing-example compilation as proof of the new
  generic-union surface.
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

The language/library contract has two parts:

1. First-order generic unions: compile-time only, instantiated to ordinary
   concrete descriptors before typecheck and lowering.
2. A value-returning `improve` helper in a new library module whose result is
   the flat generic union `Improvement[S F B]`.

Inference-default effects remain independently owned by EL-1, not a third
prerequisite. The initial provider route uses concrete prompt result types and
domain adapters; direct generic `defprompt` results are a separate extension.

Selected over the alternatives: a flat union rather than a record wrapper around
the legacy concrete result; the existing bounded-loop semantics rather than a
reserved final review; no counters, seeds, snapshots, version identifiers,
explanation surfaces, or executor extraction in the first release.

## 2. What the repository shows

| Observation | Locator | Consequence |
| --- | --- | --- |
| `review-revise-loop-proc` takes an unused `ctx`, seeded `initial_review_report` and `initial_findings`, fixes inside the `REVISE` branch before `continue`, and its `:on-exhausted` projection returns the previous iteration's review beside the already-fixed candidate. The result carries no candidate. | `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` | This is the defect. It is a value-return and evidence-pairing problem, not a budget problem. |
| The maintained document-review caller restates the three-variant result and re-wraps each arm; `kiss_backlog_item` also projects review outcomes. The parametric-document example retains an older provider/prompt macro interface, with a source-shape test rather than compile evidence. | `workflows/examples/review_revise_design_docs.orc`, `kiss_backlog_item.orc`, `review_revise_parametric_design_docs.orc`; `tests/test_workflow_lisp_examples.py` | The maintained callers motivate the generic-union extension. The historical parametric example is not a hook-preserving migration demonstration; converting it would be separate work. |
| Genericity is `defproc`-only. `ProcRef` signatures bind type parameters, with invariant matching. Existing inference does not decompose arbitrary nominal type applications; union compatibility can compare short names and shapes. | `docs/design/workflow_lisp_parametric_type_system.md`; `procedure_typecheck.py::_infer_parametric_type_bindings`; `type_env.py::type_refs_compatible` | Generic unions require constructor-aware recursive argument binding and identity preservation, not just parser syntax. The type-system owner defines that extension. |
| At target 2.29+, the contract covers transportable structured values through initial state, `continue`, `done`, exhaustion, and committed resume. Exhaustion projects state roots/fields without an evaluator. Top-level `Optional` state is not admitted. | `docs/design/workflow_lisp_frontend_specification.md` §13.1; `specs/dsl.md` loop/recur and `repeat_until.on_exhausted` | Projection expressibility does not prove selection of the final committed state; §9 requires both. Omitting feedback from exhaustion is a domain-neutral contract choice, not proof that typed absence/history is impossible. |
| An imported generic loop uses `(selector ctx)` with `ctx` outside its loop state. | `tests/fixtures/workflow_lisp/modules/valid/generic_loop_union_cross_module/generic_loop_union_cross_module/helper.orc`; `test_cross_module_generic_loop_projects_caller_union_fields` | Fixed inputs can remain lexical bindings. Verify their preservation through the helper's own specialization and resume path rather than declaring capture unavailable. |
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
  :where ((S is-record))
  -> Improvement[S F B])
```

`S` is the subject, `I` the fixed inputs, `F` the domain's assessment or
feedback type, `B` the domain's blocker type. `S` and `I` bind from the
first-order parameters; `F` and `B` bind from the hook signatures.
The first delivery keeps `S is-record` as an explicit scope limit: `S` is
carried through loop state and projected by `:on-exhausted`, whose generic-record
path requires its own proof. This is not a claim that non-record subjects are
conceptually invalid or that the underlying loop cannot project them. Widening
`S` requires a named use and boundary evidence. `I` has no record constraint:
it is a fixed lexical input, not loop state. Each specialization must satisfy
the existing transport, projection and result contracts where used; no new
constraint vocabulary is introduced.

What each variant promises:

- **APPROVED.** The selected `review` procedure approved `value` under the
  domain's policy, and `evidence` is the assessment that approved it. Ordinary
  local dataflow establishes that pairing for an immutable value. Approval is
  not proof of substantive correctness.
- **BLOCKED.** `value` is the candidate the reviewer refused to assess further.
  It is available for intervention. It is not approved.
- **EXHAUSTED.** `value` is the latest valid candidate the loop produced. It may
  be an unreviewed final revision. There is no generic assessment field. Any
  domain history inside `value` must distinguish previous-review feedback from
  assessment of the returned candidate, as in §8.

Why a flat union rather than `{candidate, outcome}`: no cross-field status
relationship, no seed state, no `Optional` loop state, no candidate/evidence
mismatch on exhaustion, and no generic records.

**Accepted tradeoff.** The maintained callers consume previous-review metadata
on exhaustion. A caller that retains this public result must carry that metadata
explicitly in its domain subject, with typed absence before the first revision;
§8 specifies the adapter contract. It is feedback used to produce a revision,
not an assessment of that revised value. The generic helper owns no history and
does not fabricate a report to satisfy a legacy return type.

**Fixer-side blockage** is an extension point. A sibling helper whose `revise`
returns a value-carrying union can be added when a maintained caller needs it.
In that extension, a blocked revision must return the last reviewed candidate,
never a partially modified one carrying the old assessment.

## 4. Loop and termination

```text
state = {current: initial}

(loop/recur :max limit
  :state state
  :on-exhausted (variant Improvement[S F B] EXHAUSTED :value state.current)
  (fn (state)
    (match (review state.current inputs)
      ((APPROVE a) (done (variant Improvement[S F B] APPROVED :value state.current :evidence a.evidence)))
      ((BLOCKED b) (done (variant Improvement[S F B] BLOCKED  :value state.current :reason b.reason)))
      ((REVISE r)  (continue (loop-state :like state
                               :current (revise state.current inputs r.feedback)))))))
```

- One iteration reviews the current candidate and, when asked, revises it. The
  final permitted iteration may therefore end in an unreviewed revision. That
  is the existing bounded-loop policy and it is what `EXHAUSTED` means.
- `limit` keeps the existing `:max` semantics, including zero handling. No
  positive-limit precondition is added: the frontend has no such contract and
  this change does not justify one.
- `inputs` remains a fixed lexical binding. The compiler owns any internal
  capture needed by lowering/resume; it is not authored mutable policy state.
  A limitation in the specialized capture path belongs to that compiler owner,
  not to a new helper-specific state protocol.
- Cancellation, malformed hook output, timeouts, and provider failures remain
  runtime outcomes under the existing recovery contract. None becomes a
  fabricated `EXHAUSTED`.
- The exhaustion projection uses a direct state field, which the 2.29+
  projection rules admit. No counter, evaluator, or seeded evidence is needed.

## 5. Boundaries

**Typed feedback.** `F` is domain-owned. The selected hook is a `defproc`, not
a `defprompt` reference. In the initial contract its provider call retains an
existing concrete result declaration; an ordinary procedure converts that
result into `Decision[MyFeedback MyBlocker]`. The value conversion can be pure,
but the enclosing adapter is effectful when it calls a provider or validates
external artifacts. Direct instantiated-union declarations on `defprompt` are
outside this slice, not an alternative mandatory completion gate.

Provider result validation does not establish arbitrary properties of referenced
files. Legacy `ReviewFindings.v1` adapters retain the existing validator's exact
schema-string and JSON-envelope checks before publishing findings and before
the fixer consumes them after resume. The schema is neither tightened nor
silently weakened. `improve` knows nothing about that file format; adapter
effects remain visible in its specialized transitive summary.

**Documents.** A value's record shape does not express immutability. A path-bearing `S`
is admitted with exactly the semantics the examples have today: approval refers
to the reviewed read of that path. Snapshot or version references are adapter
work owned by a named caller and the artifact allocator, not by the loop, and
not by this release.

**Inputs.** Semantic requirements and execution settings may be grouped in
application-owned records. No universal configuration record. Removing `ctx`
from the helper must first confirm that no resource dependency reaches the
identity or resume checks only through it.

## 6. Language delta: generic unions

The [parametric type-system design](workflow_lisp_parametric_type_system.md)
owns generic-union application, recursive argument binding, constructor
identity, diagnostics, and the existing specialization pipeline. This document
consumes that proposed extension; it does not define a second type system.

- `defunion` accepts `:forall`, with applications in ordinary value/procedure
  type positions, constructors and `ProcRef` signatures. The initial prompt
  route remains the concrete-result adapter described in §5.
- Concrete descriptors must reach ordinary typechecking/lowering without
  unresolved parameters or runtime type values. Binding `F` and `B` inside a
  hook's `Decision[F B]` requires the constructor-aware rule in the type owner.
- Demonstrate an unrelated `Outcome[T E]` union so the mechanism is not keyed
  to review names. No `Decision`, `Improvement`, or `Outcome` name exists in
  the stdlib or `workflows/` today. Do not reuse `Selection`; `std/drain`
  owns that vocabulary.
- Generic records are not required by this design. Add them only for a named
  caller, through the same owner.
- No return-only inference, explicit type application at procedure call sites,
  generic workflows, or trait aliases are requested. The roadmap owns adoption
  and target selection; describing the extension does not enable its syntax.

## 7. Effects

Adopt EL-1 unchanged: omitted clause infers; explicit empty requires no tracked
effects after hook resolution; explicit nonempty requires a subset with
provider and command identities preserved. Migrate forwarding helpers to
omission on the new regime, definition-origin aware.

Before EL-1 lands, `improve` has no direct validator command and uses the current
generic-hook forwarding regime. Its inferred transitive summary must nevertheless
include all provider/command effects of the selected domain adapters, including
findings validation. Preserve definition-origin rules when EL-1 later migrates
forwarding declarations to omission. Neither change waits for the other.

## 8. Migration

- New module, provisionally `std/improve`, exporting `Decision`, `Improvement`,
  and `improve`. `std/phase` remains available; its review/revise helper's
  terminal-evidence mismatch is legacy behavior, not a designation of every
  export in that module.
- New declarations change bundled-module digests and require a target bump.
  No checkpoint compatibility is claimed between the two APIs.
- The maintained migration consumers are `review_revise_design_docs.orc` and
  `kiss_backlog_item.orc`. Their existing provider procedures can stay intact,
  but both review and revision require caller-owned adapters. The historical
  `review_revise_parametric_design_docs.orc` is not counted as an unchanged-hook
  consumer; conversion of its old macro interface is separate work.
- Domain `ReviewEvidence` contains the existing review report and findings.
  Domain `ReviewBlocker` contains the report, findings and `BlockerClass`;
  `BlockerClass` alone cannot preserve the existing blocked result.
- The review adapter calls the existing reviewer on the underlying subject,
  validates findings under §5, and converts to
  `Decision[ReviewEvidence ReviewBlocker]`. The revision adapter accepts
  `ReviewEvidence`, validates findings at the required consumption boundary,
  and calls the existing fixer with `.findings`, not the entire evidence record.
- To retain exhaustion metadata, the caller's subject pairs its original value
  with a concrete domain union: `UNREVIEWED` initially, or
  `REVISED_FROM(evidence ReviewEvidence)` after a successful fix. No fake path,
  initial report or generic-library seed is introduced. The adapter stores the
  evidence used by that fix, explicitly not a review of its returned value.
  Initial/revised wrapping and unwrapping belong to the caller adapters.
- The selected callers have positive fixed limits. Their approved/blocked and
  exhausted result projections preserve the existing public fields using actual
  evidence. Preserve the existing zero-limit runtime outcome when checking the
  general helper; never manufacture a report-bearing legacy result from
  `UNREVIEWED`. Any caller that exposes an absence case must represent it in its
  declared result, or explicitly change its caller contract before migration.
- Retirement is per declaration: remove `review-revise-loop` and
  `review-revise-loop-proc` only after their maintained consumers migrate.
  Inventory supporting review types separately. Keep `with-phase`,
  `phase-scope`, path types and other independently used exports. An importer
  count is not evidence that the entire `std/phase` module can be deleted.

## 9. Feasibility and integration evidence

Distinguish evidence about the existing substrate from acceptance of newly
implemented capabilities. A plan must resolve material contract/ownership
choices and explicitly include any necessary substrate correction; it need not
implement generic unions before it is allowed to plan them. An unproven claim
is recorded as a gap, not silently treated as working or made into an informal
pre-plan implementation obligation. The roadmap owns investigation order.

| Capability | Design boundary | Required evidence |
| --- | --- | --- |
| Generic unions | New type-system capability, not a prerequisite implementation. | Implementation acceptance must cover imported generic procedures, argument binding through `ProcRef`, alias/homonym identity, loop state, terminal results and downstream consumption, plus the type owner's diagnostics and unused-argument identity cases. |
| Generic exhaustion and lexical inputs | Projection expressibility and selection of the final committed state are separate obligations; neither alone proves the combined specialized/resume path. `S is-record` bounds the first delivery, not the proof. | Probe available substrate without requiring generic-union syntax. Record owner-level gaps in the plan; the final helper must project the latest `state.current` of specialized record type `S`, including after the final `continue` with two or more iterations, and preserve fixed `inputs` on run/resume. Include a supported non-record `I`, with unsupported shapes rejected at their actual boundary. Exercise the generic exhaustion path after committed-boundary resume as well as on a fresh run. |
| Concrete prompt results and domain adapters | The initial provider route uses existing result declarations; generic prompt-result declarations are outside scope. | Show value conversion plus required artifact validation, compatible hooks, preserved public report fields and consumption-time validation after resume. Direct generic prompt results require separate extension evidence, not closure of this slice. |
| No compiler branch keyed to review names | A mechanism-level requirement, verified on the implementation. | An unrelated `Outcome[T E]` union passes the same boundaries with no consumer-specific code. |

Removing `ctx` from the helper is not a capability question but still needs a
check: confirm that no resource dependency reaches identity or resume
validation only through that parameter.

Deterministic hooks must exercise a supported executable route. The roadmap
and linked exhaustion check record frontend limitations and the corresponding
command/provider-backed test route; a test-helper limitation does not itself
become a new prerequisite for the library abstraction.

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
- **Malformed feedback.** A hook result that fails its declared type, or legacy
  findings that fail the required schema/envelope checks, is a contract failure
  at the provider or domain-adapter boundary. No `Decision` reaches the helper
  from that invalid result. Restored file-backed findings meet the same
  consumption rules.
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
- **Migration.** The two maintained consumers named in §8 use explicit review
  and revision adapters, preserve required public metadata and domain validation,
  and distinguish revision feedback from approval evidence. Their provider
  procedure bodies need not change. The README compile command keeps passing;
  the historical parametric source-shape test is not migration evidence.
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
