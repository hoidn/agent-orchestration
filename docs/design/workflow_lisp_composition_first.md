# Workflow Lisp Composition-First Procedures

- **Status:** generic unions and `std/improve` (§§3–6) are implemented at
  target 2.33, with the effect behavior §7 describes for the period before
  EL-1; the reference module is
  [`std/improve.orc`](../../orchestrator/workflow_lisp/stdlib_modules/std/improve.orc)
  and its rules and known defects are in §11. Not implemented: the EL-1 effect
  rules that §7 adopts, and the §8 consumer migration. The roadmap owns their
  entry conditions.
- **Kind:** language and standard-library architecture decision
- **Owner:** Workflow Lisp frontend (parametric type system) and standard library
- **Created:** 2026-09-28
- **Implementation target:** 2.33 for generic unions and `std/improve`
  together; [versioning](../../specs/versioning.md) owns target admission
- **Roadmap:** [CF-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#cf-1--composition-first-procedures-pending-unselected)
  owns selection, ordering, entry conditions, and consequences. Effect
  contracts remain owned by
  [EL-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#el-1--effect-contracts-and-analysis-cleanup-pending-unselected).
- **Type-system delta:** [first-order generic unions](workflow_lisp_parametric_type_system.md#proposed-cf-1-first-order-generic-unions)
  in the parametric type-system design; it owns application, argument
  binding, constructor identity, and diagnostics.
- **Evidence record:** the [design review](../reports/2026-09-28-workflow-lisp-composition-first-review.md)
  and the [exhaustion projection check](../reports/2026-09-28-cf1a-exhaustion-projection-check.md).
- **Notation:** signatures below are schematic. They use the `:forall`,
  `:where`, `ProcRef[(A B) -> C]`, and `(variant ...)` spellings that exist
  today, but they are not copy-safe `.orc` syntax.

## 1. Decision

Reusable agent procedures compose as ordinary typed programs. A helper takes
meaningful inputs and compile-time procedure references, and returns the value
it computed together with the domain outcome the caller branches on.
Review/revise is the first worked example, not the organizing abstraction.

The contract has two parts:

1. First-order generic unions: compile-time only, instantiated to ordinary
   concrete descriptors before typecheck and lowering.
2. A value-returning `improve` helper in a new library module whose result is
   the flat generic union `Improvement[S F B]`.

Inference-default effects are EL-1's independent concern, not a prerequisite.
A provider-backed hook may return an instantiated `Decision` directly from
`provider-result :returns`, or convert an existing concrete result through a
domain adapter (§5). A `defprompt` may also declare an applied union as its
result (§5).

Not in this design: a record wrapper around the legacy concrete result, a
reserved final review, review counters, seeded evidence, snapshot or version
identifiers, explanation surfaces, or executor extraction.

## 2. Baseline observations

| Observation | Locator | Consequence |
| --- | --- | --- |
| `review-revise-loop-proc` takes an unused `ctx`, seeds `initial_review_report` and `initial_findings`, revises inside the `REVISE` branch before `continue`, and its `:on-exhausted` projection returns the previous iteration's review beside the already-revised candidate. The result carries no candidate. | `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` | The defect is at the return boundary: value return and evidence pairing. |
| The maintained document-review caller restates the three-variant result and re-wraps each arm; `kiss_backlog_item` projects review outcomes; the design-delta library's plan and implementation phases use the same loop and publish the last review in a materialized progress report. The parametric-document example uses the older provider/prompt macro interface and has a source-shape test rather than compile evidence. | `workflows/examples/review_revise_design_docs.orc`, `kiss_backlog_item.orc`, `review_revise_parametric_design_docs.orc`; `workflows/library/lisp_frontend_design_delta/plan_phase.orc`, `implementation_phase.orc`; `tests/test_workflow_lisp_examples.py` | These consumers motivate the generic-union extension. The parametric example needs conversion of its macro form, not a hook-preserving migration. |
| Genericity is `defproc`-only. `ProcRef` signatures bind type parameters with invariant matching. Inference does not decompose nominal type applications; union compatibility can compare short names and shapes. | `docs/design/workflow_lisp_parametric_type_system.md`; `procedure_typecheck.py::_infer_parametric_type_bindings`; `type_env.py::type_refs_compatible` | Generic unions need constructor-aware recursive argument binding and identity preservation, owned by the type system. |
| At target 2.29+, transportable structured values flow through initial state, `continue`, `done`, exhaustion, and committed resume. Exhaustion projects state roots and fields without an evaluator. Top-level `Optional` loop state is not admitted. | `docs/design/workflow_lisp_frontend_specification.md` §13.1; `specs/dsl.md` loop/recur and `repeat_until.on_exhausted` | Projection expressibility and selection of the final committed state are separate obligations (§9). Omitting feedback from exhaustion is a contract choice, not a limitation. |
| An imported generic loop body uses `(selector ctx)` with `ctx` outside its loop state. | `tests/fixtures/workflow_lisp/modules/valid/generic_loop_union_cross_module/generic_loop_union_cross_module/helper.orc` | Fixed inputs are lexical bindings, not loop state. |
| The findings validator checks the schema string, a safe relative path, and the presence of an `items` key. | `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py` | The legacy carrier is intentionally minimal. It is preserved, not tightened. |
| EL-1 distinguishes omitted from explicit-empty effect clauses; specialized forwarding helpers acquire effects under empty clauses. | `docs/design/workflow_lisp_effect_ledger_simplification.md`; `docs/reports/2026-09-08-workflow-lisp-effect-tracking-audit.md` | Adopt EL-1 as written. Migration must be definition-origin aware. |

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

`S is-record` is the first delivery's scope limit: `S` is carried through loop
state and projected by `:on-exhausted`, and those boundaries are proven for
records, including records with `List[record]` fields. Widening `S` requires a
named use and boundary evidence. `I` has no record constraint: it is a fixed
lexical input, not loop state. The supported shapes are a record or a `String`
workflow parameter; a `String` or `Int` literal passed as `inputs` is
rejected. Each
specialization must satisfy the existing transport, projection, and result
contracts where used; no new constraint vocabulary is introduced.

What each variant promises:

- **APPROVED.** The selected `review` procedure approved `value` under the
  domain's policy, and `evidence` is the assessment that approved it. Ordinary
  local dataflow establishes that pairing for an immutable value. Approval is
  not proof of substantive correctness.
- **BLOCKED.** `value` is the candidate the reviewer refused to assess further.
  It is available for intervention. It is not approved.
- **EXHAUSTED.** `value` is the latest valid candidate the loop produced. It may
  be an unreviewed final revision. There is no generic assessment field. Any
  history a domain keeps inside `value` must distinguish the feedback that
  produced a revision from an assessment of the returned candidate (§8).

A flat union rather than `{candidate, outcome}` because it has no cross-field
status relationship, no seed state, no `Optional` loop state, no
candidate/evidence mismatch on exhaustion, and no need for generic records.

**Exhaustion metadata.** Publishing previous-review metadata on exhaustion is
the consumer's choice. A consumer that publishes it holds it in its domain
subject, with typed absence before the first revision (§8). A consumer that
does not keeps its original subject and publishes only its own exhaustion
outcome. The generic helper owns no history and fabricates no report to
satisfy a legacy return type.

**Fixer-side blockage** is an extension point. A sibling helper whose `revise`
returns a value-carrying union may be added when a maintained caller needs it.
In that extension, a blocked revision returns the last reviewed candidate,
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

The listing is schematic. The shipped
[`std/improve.orc`](../../orchestrator/workflow_lisp/stdlib_modules/std/improve.orc)
is the reference; it binds both hook results with `let*` before use.

- One iteration reviews the current candidate and, when asked, revises it. The
  final permitted iteration may end in an unreviewed revision; that is the
  existing bounded-loop policy and what `EXHAUSTED` means.
- `limit` has the existing `:max` semantics: it is a compile-time integer
  constant of at least 1, written as a literal, a `let*`-bound literal, or a
  field of a literal record. A workflow parameter is rejected, and `0` is
  rejected at compile time, as for `:max` on any loop.
- `inputs` is a fixed lexical binding. Any capture the compiler needs for
  lowering or resume is the compiler's, not authored loop state.
- Cancellation, malformed hook output, timeouts, and provider failures remain
  runtime outcomes under the existing recovery contract. None becomes a
  fabricated `EXHAUSTED`.
- The exhaustion projection is a direct state field. No counter, evaluator, or
  seeded evidence is needed.

## 5. Boundaries

**Typed feedback.** `F` is domain-owned. The selected hook is a `defproc`. A
provider-backed review hook may declare
`provider-result :returns Decision[MyFeedback MyBlocker]` and return the
provider's result directly. Output that does not satisfy the instantiated
contract is a contract violation at the provider boundary
(`variant_discriminant_invalid`, `variant_required_field_missing`,
`variant_forbidden_field_present`, `variant_field_type_invalid`) and never
reaches the helper. A hook whose provider call keeps an existing concrete
result declaration, such as a legacy `ReviewFindings.v1` review, uses an
ordinary adapter procedure that converts that result into
`Decision[MyFeedback MyBlocker]`. The conversion may be pure; the enclosing
adapter is effectful when it calls a provider or validates external artifacts.
A `defprompt` whose result is an applied union, such as
`-> Decision[MyFeedback MyBlocker]`, has the same contract at target 2.33:
the instantiated descriptor is the provider's output contract, no type
parameter reaches it, and malformed output fails at the provider boundary
with the four codes above before any later step runs.

**Hooks.** `review` and `revise` are command- or provider-backed `defproc`s
with `:lowering inline`, directly or through an adapter. A composite reviewer,
such as two reviews plus an adjudication, is an ordinary `defproc` with the
review hook's signature; converting adapters may be nested in it. Hooks may be
declared in another module and passed with `proc-ref`; from a caller at
target 2.33 their effects are part of the specialized summary (§7).

Provider result validation establishes nothing about referenced files. Legacy
`ReviewFindings.v1` adapters run the existing validator's schema-string and
JSON-envelope checks before publishing findings and before the fixer consumes
them, including after resume. The schema is neither tightened nor weakened.
`improve` knows nothing about that file format; adapter effects stay visible in
its specialized transitive summary.

**Documents.** A record shape does not express immutability. A path-bearing
`S` is admitted with the semantics the examples have today: approval refers to
the reviewed read of that path. Snapshot or version references are adapter work
owned by a named caller and the artifact allocator, not by the loop.

**Inputs.** Semantic requirements and execution settings may be grouped in
application-owned records; there is no universal configuration record. The
helper takes no runtime context parameter. An adapter that needs a resource
handle receives it through its own typed inputs.

## 6. Language delta: generic unions

The [parametric type-system design](workflow_lisp_parametric_type_system.md#proposed-cf-1-first-order-generic-unions)
owns generic-union application, recursive argument binding, constructor
identity, diagnostics, and the specialization pipeline. This document consumes
that extension:

- `defunion` accepts `:forall`, with applications in value and procedure type
  positions, constructors, and `ProcRef` signatures. Binding `F` and `B`
  inside a hook's `Decision[F B]` uses the type owner's constructor-aware rule.
- Concrete descriptors reach ordinary typechecking and lowering with no
  unresolved parameters and no runtime type values.
- An unrelated `Outcome[T E]` union exercises the same mechanism, so nothing is
  keyed to review names. `Selection` is not reused; `std/drain` owns it.
- Generic records are not required. Add them only for a named caller, through
  the same owner.
- No return-only inference, explicit type application at procedure call sites,
  generic workflows, or trait aliases are requested.

## 7. Effects

Adopt EL-1 unchanged: an omitted clause infers; explicit empty requires no
tracked effects after hook resolution; explicit nonempty requires a subset with
provider and command identities preserved. Migrate forwarding helpers to
omission on the new regime, definition-origin aware.

Before EL-1 lands, `improve` has no direct command effect and uses the current
generic-hook forwarding regime. Its inferred transitive summary includes all
provider and command effects of the selected domain adapters, including
findings validation. For a caller at target 2.33 this holds wherever the hooks
are declared: effect inference includes the effects of imported procedures and
of hooks passed from another module. For a caller below 2.33 the effects of
hooks declared in another module are missing from that summary (§11). Neither
change waits for the other.

## 8. Migration

- New module `std/improve`, exporting `Decision`, `Improvement`, and
  `improve`. `std/phase` remains available; its review/revise helper's
  terminal-evidence mismatch is legacy behavior of that helper, not of every
  export in the module.
- New declarations change bundled-module digests and require a target bump.
  No checkpoint compatibility is claimed between the two APIs.
- The consumers are the three examples (`review_revise_design_docs.orc`,
  `kiss_backlog_item.orc`, `review_revise_parametric_design_docs.orc`) and the
  design-delta library's plan and implementation phases. Their provider
  procedures stay intact; both review and revision go through caller-owned
  adapters. The parametric example first converts its macro provider form to
  hook procedures.
- The shared review domain lives in one module, provisionally `std/review`:
  `ReviewEvidence`, `ReviewBlocker`, and the findings validation procedure.
  Adapters stay with each consumer.
- Domain `ReviewEvidence` holds the existing review report and findings.
  Domain `ReviewBlocker` holds the report, findings, and `BlockerClass`;
  `BlockerClass` alone cannot preserve the existing blocked result.
- The review adapter calls the existing reviewer on the underlying subject,
  validates findings (§5), and converts to
  `Decision[ReviewEvidence ReviewBlocker]`. The revision adapter accepts
  `ReviewEvidence`, validates findings at the consumption boundary, and calls
  the existing fixer with `.findings`.
- The examples publish no previous-review metadata on exhaustion. Their
  subject stays the original record and their exhausted result carries the
  reason alone; the review reports remain at the paths the caller supplied.
- The design-delta phases keep exhaustion metadata, because their materialized
  progress report links the last review. Their subject pairs its value with a
  concrete domain union: `UNREVIEWED` initially, `REVISED_FROM(evidence
  ReviewEvidence)` after a successful revision. That evidence is what the
  revision responded to, not a review of the returned value. Wrapping and
  unwrapping belong to the consumer's adapters; no fake path, initial report,
  or library seed exists. Because `limit` is at least 1 (§4), exhaustion
  always follows a revision and returns `REVISED_FROM`; `UNREVIEWED` is used
  only as the history value before the first revision.
- Approved and blocked projections preserve the existing public fields from
  actual evidence.
- Retirement is per declaration: remove `review-revise-loop` and
  `review-revise-loop-proc` only after their maintained consumers migrate, and
  inventory supporting review types separately. `with-phase`, `phase-scope`,
  path types, and other independently used exports stay.

## 9. Feasibility obligations

A plan resolves the contract and ownership choices below and includes any
substrate correction they require. Evidence about the existing substrate is
distinct from acceptance of the new capability: an unproven claim is recorded
as a gap, and a gap in existing runtime behavior is corrected at its owner.

| Capability | Boundary | Required evidence |
| --- | --- | --- |
| Generic unions | New type-system capability. | Acceptance covers imported generic procedures, argument binding through `ProcRef`, alias and homonym identity, loop state, terminal results, downstream consumption, and the type owner's diagnostics and phantom-argument identity cases. |
| Generic exhaustion and lexical inputs | Projection expressibility and selection of the final committed state are separate obligations. | The helper projects the latest `state.current` of specialized record type `S`, including after the final `continue` with two or more iterations, on a fresh run and after committed-boundary resume, and preserves fixed `inputs` on both. A supported non-record `I` is included; unsupported shapes are rejected at their boundary. The exhaustion projection check records the final-state defect, its owner-level correction and acceptance tests; fixed-input capture is a separate obligation. |
| Provider results and domain adapters | A provider-backed hook returns an instantiated `Decision` from `provider-result :returns`, or an adapter converts an existing concrete result declaration. | Direct returns: malformed output fails at the provider boundary with the four variant contract-violation codes (§5). Adapters: value conversion plus required artifact validation, compatible hooks, preserved public report fields, and consumption-time validation after resume. Direct generic `defprompt` results: the same four codes at the provider boundary, no later step, and no type parameter in the contract (`tests/test_workflow_lisp_generic_union_defprompt_results.py`). |
| No compiler branch keyed to review names | A mechanism-level requirement. | An unrelated `Outcome[T E]` union passes the same boundaries with no consumer-specific code. |

Deterministic test hooks use a supported executable route: command-backed or
provider-backed hooks (§5). Pure hooks are not supported.

## 10. Evidence requirements

- **Value return.** A changed candidate reaches a deterministic downstream
  consumer through the helper's return value, never through private state, an
  output directory, or an alias to external mutation.
- **Terminal pairing.** Approval carries the assessment that approved the
  returned value. Exhaustion after a changed final candidate carries that
  candidate and nothing that could be read as its assessment. Reviewer
  blockage returns the candidate that was refused.
- **Malformed feedback.** A hook result that fails its declared type, or legacy
  findings that fail the required schema and envelope checks, is a contract
  failure at the provider or adapter boundary. No `Decision` reaches the helper
  from an invalid result. Restored file-backed findings meet the same rules.
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
- **Migration.** Each migrated consumer uses explicit review and revision
  adapters, preserves domain validation and its approved and blocked public
  fields, and either omits exhaustion metadata or types it as feedback
  distinct from approval evidence. Provider procedure bodies need not change.
  The README compile command keeps passing.
- **Realistic change.** Adding a typed proposal field consumed downstream is
  recorded as the edited files and any leaked execution plumbing: a
  qualitative record, not a productivity score, with no new harness.

Verification follows AGENTS.md: narrow selectors first, then the full suite,
plus a public compile/run/resume path for the new caller.

## 11. Known defects and rules at target 2.33

A **rule** is a restriction the language makes on purpose; its diagnostic
names it. A **defect** is a failure after typecheck, a wrong diagnostic, or
behavior that contradicts a contract. The
[decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md)
traces most defects below to one cause: at run time a value exists only as the
output of a step. It weighs the repairs. Its cases a to f are in
[section 2.1](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md#21-six-reproduced-limits).
The [totality matrix](../../tests/workflow_lisp_totality_matrix_sources.py)
pins each defect it names with a strict `xfail` that must fail as recorded.

### 11.1 Rules

- `S is-record` (§3) and `limit` (§4). A `limit` of `0` is rejected with
  `workflow_boundary_type_invalid` ("max_iterations must be > 0"), and a
  workflow parameter with `workflow_return_not_exportable` ("must lower from a
  literal integer"); both point into `std/improve.orc`.
- No generic records and no explicit procedure type arguments (§6).
- Record and variant fields are pure: an effectful call written there is
  rejected with `effect_not_permitted`. The `:on-exhausted` value is pure:
  `loop_recur_contract_invalid`.
- The workflow return boundary rejects a union inside a returned variant with
  `workflow_boundary_type_invalid`.

The caller shape is in the
[drafting guide](../lisp_workflow_drafting_guide.md#137-improve). Its
[rejection table](../lisp_workflow_drafting_guide.md#improve-rejections) lists
the compile-time rejections a caller of `improve` may hit, with each code,
where it points, and whether it is a rule or a defect.

### 11.2 Defects met by callers of `improve`

These belong to the owners of the flat lowering route and of
[pure-result replay](workflow_lisp_pure_result_replay.md); the
[decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md) weighs their repair.

| What the author sees | Cause | Write instead | Pinned by |
| --- | --- | --- | --- |
| Resume after a failure in a step downstream of the result fails with `pure_result_replay_unavailable` (`dependency_index_invalid`, "unknown result member"); the failed step does not run again | Lowering reads a member of the loop result that its contract does not declare (case d) | - | No test yet |
| A pure `match` over the result whose arms build a record that holds a literal, such as `(record Out :outcome "approved" :title a.value.title)`, fails `--dry-run` and the run start with `pure_result_replay_unavailable` ("unknown result member") at the `match`, before any hook runs | Case d, as above | Arms that return a scalar such as `a.value.title`, arms that call a command-backed procedure, or a record whose fields all read the result | `tests/test_workflow_dry_run_replay_index.py::test_dry_run_rejects_a_record_building_tail_match_as_the_run_start_does`; matrix label `d` |
| A pure review hook ends in `compiler_defect` (an internal `KeyError`) at the `review` call in `std/improve.orc`; a pure revise hook in `workflow_return_not_exportable` ("does not support let* binding") at the `revise` call | The loop lowerer does not support the inlined pure hook body: a pure call bound in the loop body and then matched (review), or a `let*` produced by the inlined body (revise) | Command- or provider-backed hooks (§5) | No test yet |
| A `String` or `Int` literal as `inputs` is rejected with `workflow_signature_mismatch` ("requires same-file call bindings to resolve to workflow inputs") at the `review` call | In a loop body a hook call lowers as a private-workflow call whose arguments must be references; a literal has none (matrix label `loop-call-argument`) | A record, or a `String` workflow parameter (§3) | Matrix label `loop-call-argument` |
| `initial` written as a record literal that contains a list of record literals is rejected with `type_unknown` at the inner record's type name | The list's element type is resolved in `std/improve`, where the caller's type is not visible | Build `initial` in a procedure of the calling module | No test yet |
| For a caller below 2.33, the effects of hooks declared in another module are missing from the specialized summary | Older targets keep the earlier effect inference | Target 2.33 | `tests/test_workflow_lisp_imported_effects.py::test_target_232_specialized_improve_summary_keeps_its_result` |

### 11.3 Defects of the language at target 2.33

Labels are those of the totality matrix, or the case letters of the
[decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md#21-six-reproduced-limits).

| Label | What the author sees | Cause | Write instead | Pinned by |
| --- | --- | --- | --- | --- |
| `subject-producer` (case a, bound form) | `workflow_return_not_exportable` or `wcc_lowering_route_unsupported` ("requires case subjects with stable producer step identities") | A union that no step produced, a variant built without effects or the result of a pure call, is a `match` subject | - | Matrix label `subject-producer` |
| `loop-call-argument` | `workflow_signature_mismatch` ("requires same-file call bindings to resolve to workflow inputs") | In a `loop/recur` body a command-backed procedure lowers as a private-workflow call whose scalar arguments must be references; a literal, or a field of a record literal bound by `let*`, is not one | Pass a value a step produced, such as a field of the loop state | Matrix label `loop-call-argument` |
| Scalar result in a loop body | Exit 1 with an internal `AssertionError` from `lowering/procedures.py`, not a diagnostic, for a command-backed procedure that returns a scalar and is called in a `loop/recur` body, bound or not | The private-workflow lowering of the call assumes a record or union result, and the compiler-defect boundary lets an `AssertionError` pass | Return a record, or write the `command-result` directly in the field | No test yet |
| `done-call`, `done-match` | `compiler_defect` ("unsupported WCC elaboration node") | The elaborator has no rule for an effectful call or a `match` as a `done` value | - | Matrix labels `done-call`, `done-match` |
| `continue-typed-state` (case c at a second site) | `proc_ref_signature_invalid` for a generic call with hooks in a `loop-state` field under `continue` | The `continue` handler keeps the authored state, so specialization does not see the generic call | - | Matrix label `continue-typed-state` |
| Effectful control value in a loop body | `compiler_defect_loop_control_value` at the form, for an effectful `if` or `match` used as a `loop-state` field or bound by `let*` in a loop body | The loop lowering route cannot lower an effectful value of an `if` or `match` bound inside a `loop/recur` body | A `match` in tail position whose arms `continue` | `tests/test_workflow_lisp_prefix_scope.py::test_an_effectful_control_value_bound_in_a_loop_body_is_a_located_compiler_defect` |
| `loop-state-union`, `loop-state-match`, `on-exhausted-match` | `compiler_defect` ("unsupported pure projection expression") or `workflow_return_not_exportable` ("could not project") | The older loop lowerer's pure projection has no case for a union-typed `loop-state` field, a `match` in a `loop-state` field, or a `match` as the `:on-exhausted` value | - | Matrix labels `loop-state-union`, `loop-state-match`, `on-exhausted-match` |
| `nested-union-result` | `collection_element_type_unsupported`, whose message wrongly speaks of a "collection-valued structured result" | The result contract of the step that carries a variant cannot hold a union field; no route reads such a field back | - | Matrix label `nested-union-result` |
| `replay-union-argument` | `pure_result_replay_unavailable` ("union binding must have a literal variant") at `--dry-run` and run start | The replay index cannot bind a union procedure argument, literal or produced by a step | - | Matrix label `replay-union-argument` |
| `replay-frame-scope` | `pure_result_replay_unavailable` ("crosses the indexed frame scope") | A pure call in a `match` arm, or pure bindings in an `if` branch over the result of a `call` made in that branch, are indexed in the wrong frame | Pass the fields to the next effect instead of binding them | Matrix label `replay-frame-scope`; the `if` branch shape has no test yet |
| `d` | `pure_result_replay_unavailable` ("unknown result member") | See §11.2 | See §11.2 | Matrix label `d` |
| f | At 2.33, `pure_result_replay_unavailable` ("source contract disagrees with its binding type") at `--dry-run`; at 2.32, `workflow_boundary_type_invalid` ("without required author-time variant proof") | A `match` whose arms mix a plain variant with a loop: the result reads a variant field with no proof of the selected variant | - | No test yet |
| `on-exhausted-call-edge` | `loop_recur_contract_invalid` ("exhaustion projection must be pure") for a call to a `defproc` declared `:effects ()` | The check compares the whole effect summary, call edges included, with the empty summary | Write the variant directly | Matrix label `on-exhausted-call-edge` |
| Path field in a loop result | From target 2.29, `workflow_boundary_type_invalid` ("may only override scalar repeat_until outputs") for a loop result union with a path field outside the exhausted variant | Shared validation admits only scalar outputs in the exhaustion override of a loop | Target 2.28 | No test yet |
| `match` subject identity | A generic call without a type-dependent hook, written directly as a `match` subject, lowers under different step identities from the same call bound by `let*` | At 2.33 the typed `match` keeps the authored subject except for type-dependent hooks and typed prompts, so that older programs keep their identities; from 2.34 it carries the typed subject always | - | `tests/test_workflow_lisp_match_subject_calls.py::test_generic_helper_that_already_compiled_as_match_subject_keeps_its_lowered_output` |
| Sibling field renaming | A record field that holds a `match` skips the renaming of hoisted bindings of its sibling fields (`wcc/elaborate.py`); no wrong value is known, because such a run stops earlier at the replay index | The elaborator's path for a constructor field that holds a `match` does not compose the other fields' prefixes, so a sibling field's hoisted binding wraps the arms | - | No test yet |
| Copied pure procedure target | A pure procedure copied by the resolved-inline normalizer is elaborated under the caller's target, against the per-module admission of [versioning](../../specs/versioning.md) | The normalizer does not carry the defining module's target | - | No test yet |
| Unknown binder forms | The use-site renaming pass does not know three binder forms: frontend binders other than `let*` inside an opaque value, provider supervision and peer-group member bindings, and specialization bindings of an inlined procedure. No program that reaches one is known | The pass must name every binder form it renames across | - | No test yet |

### 11.4 Runtime and tooling defects

| What the operator sees | Cause | Pinned by |
| --- | --- | --- |
| A `must_not_repeat` command inside a called workflow is refused with `lexical_restore_pending_effect_unsafe` but no source location | The callee bundle has no source trace, so its origin index is empty | `tests/test_workflow_resume_known_defects.py::test_nonrepeatable_command_inside_a_called_workflow_is_refused_with_a_location` (strict `xfail`) |
| Resume refuses an interrupted command in the second or later call of the same called workflow, such as a later loop iteration, with `lexical_restore_invalid` and `lexical_checkpoint_completed_effect_invalid`, also when it must not repeat | Restore selection in the later call finds the record the earlier call wrote and refuses it as invalid; records are not keyed by call frame | `tests/test_workflow_resume_known_defects.py::test_interrupted_command_in_a_later_loop_iteration_runs_again` (strict `xfail`) |
| Resume refuses an interrupted command whose nearest earlier effect is a provider group, with `lexical_default_resume_prior_boundary_not_restorable` | The provider group writes no checkpoint record, so resume finds no restorable prior boundary | `tests/test_workflow_resume_known_defects.py::test_interrupted_command_after_a_provider_group_runs_again` (strict `xfail`) |
| A failed run reference reruns on resume without a `workflow_effect_rerun` row; the interrupted variant gets its row | The failure leaves no failed step row, so the rerun is not recorded as the current effect's attempt | No test yet |
| `workflows/examples/review_revise_design_docs.orc` does not pass the command-line entry: `--dry-run` exits 2 with `workflow_signature_mismatch` at line 139 ("call is missing required binding `run`") and the note `entry_bootstrap_name_gate_denied` | The entry bootstrap accepts only entries named `entry`, `drain` or `promoted-entry-resume-plan-gate-wrapper` | No test yet |
| `scripts/watch_workflow_usage_limit.sh` decides from pane captures: a refusal printed after `POLL_SECONDS` is read as an admitted run and is not retried | The script waits `POLL_SECONDS` for the exit marker in pane captures and treats a missing marker as an admitted run | No test yet |
| The generic run watchdog cannot resume a stalled target while the stalled process holds the target's workspace lock | One run at a time in a workspace (`specs/cli.md`) | No test of a stalled target |
