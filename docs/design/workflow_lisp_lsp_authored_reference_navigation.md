# Workflow Lisp LSP Authored Reference Navigation

- **Status:** accepted for implementation planning after ordered independent
  specification then quality review at commit `b8a41172`; the 2026-07-27
  read-only feasibility gate admits prompt heads and only direct-retained,
  unexpanded `proc-ref` occurrences in authored non-generated,
  non-specialized owners. Macro heads defer shape-wide. The proposed
  [implementation plan](../plans/2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md)
  still requires ordered plan review before execution. Shipped content folds
  into `docs/design/workflow_lisp_language_server.md` as the owning amendment,
  per the L-series convention.
- **Kind:** L-series language-server amendment — definition-index extension
  over already-retained compiler structure
- **Owner:** `orchestrator/lsp` navigation index; read-only consumer of
  existing compile results, per the standing L-series bounds
- **Motivating evidence:** a successful live-stdio probe of
  `workflows/examples/review_revise_design_docs.orc` on 2026-07-27 returned
  null for the fragment application head, both macro-consumed `proc-ref`
  arguments, and the macro head. The direct `(call ...)` callee already
  resolved to its authored `defworkflow`; L5 preserves that implemented
  behavior as regression coverage rather than claiming it as new work.
- **Related authority:**
  - `docs/design/workflow_lisp_language_server.md` (implemented v1 + L0–L2
    amendments; the closed navigation contract this extends)
  - `docs/design/workflow_lisp_prompt_calculus.md` (Q1 prompt catalog and
    application identity)
  - `docs/design/workflow_lisp_macro_surface_contract.md` (macro lookup and
    expansion provenance)
  - `docs/design/workflow_language_design_principles.md` principles 24
    (source maps are semantic infrastructure), 28, 29, and 30

## Problem

Go-to-definition already indexes exact direct procedure call heads and exact
`(call ...)` workflow callee tokens. It does not index authored prompt
application heads, `proc-ref` name arguments, or macro heads.

The compiler has enough already-retained structure to project prompt heads,
but retention is not uniform across the other two shapes. A
`ProcRefLiteralExpr` retains a canonical target and the whole
`(proc-ref ...)` span, not the exact name-token span; macro expansion or
specialization can erase that occurrence entirely. Macro expansion frames
retain call and definition provenance, but not the canonical/module-qualified
own-definition identity required for every local/imported use. L5 must
therefore distinguish proven retained joins from attractive
source shapes. It must not fill a gap by parsing text, resolving names in the
server, or inventing compiler metadata.

## Scope And Retention Gates

| Shape | Existing retained join | L5 disposition |
| --- | --- | --- |
| Direct-authored fragment application head, such as `(review-design-doc ...)` in `provider-result :prompt` | the final typed prompt application retains its whole application span and canonical prompt identity; the Q1 prompt catalog retains the authored `defprompt` span; original syntax retains the exact application-head token | selected, through the fail-closed projection below |
| Direct retained `proc-ref` occurrence whose final Stage-3 result still contains its unexpanded `ProcRefLiteralExpr` inside a non-generated, non-specialized authored owner | the typed occurrence retains the whole form span and canonical procedure target; original syntax retains the exact second token; the procedure catalog retains the authored `defproc` span | selected after the read-only feasibility proof established the complete join across the required import cases |
| A `proc-ref` occurrence consumed or erased by macro expansion, specialization, or another lowering | no final occurrence-level span-to-canonical-identity join is retained; this includes both `proc-ref` arguments in the motivating review workflow | deferred; it remains null under this design |
| Direct-authored macro head | expansion provenance retains the whole call span and own-definition span while original syntax retains the exact head token, but `ExpansionFrame` has no canonical/module-qualified macro identity and export metadata retains only an unqualified raw name | deferred shape-wide; current retained facts cannot prove the required local/imported canonical own-definition join |
| Direct procedure call head and direct `(call X)` workflow callee | exact `authored_callee_span`, canonical target, and authored definition span are already implemented | existing behavior only; regression coverage, not new L5 scope |
| WCC-reconstructed, generated, expanded, or ambiguous call | `authored_callee_span=None` by the owning language-server contract | excluded unchanged |

A feasibility gate is shape-wide, not a best-effort permission. If every
field and cross-check required below is not already available for the named
subshape, that whole subshape defers. L5 does not add retention fields,
frontend state, source maps, or compiler projections to legalize it.

## Exact Authored Reference Projection

Every selected hit is an immutable row:

```text
(reference_kind, reference_span, canonical_target, target_kind, definition_span)
```

`reference_kind` keeps prompt, procedure, workflow, and macro namespaces
distinct. `reference_span` is the exact half-open authored token span.
`canonical_target` and `definition_span` come from compiler semantic
authority, never from the spelling of that token.

For prompt and admitted macro heads, the navigation projection:

1. consumes the retained typed prompt application or compiler expansion
   assertion, including its source and exact whole-form/call span;
2. matches that assertion to exactly one original-syntax list of the expected
   semantic kind at the identical source and whole span;
3. takes only that list's exact authored head-token span;
4. requires one compiler-owned canonical target of the expected target kind
   and one authored definition span; and
5. emits the row only after all required facts agree.

Repeated byte-for-byte-identical compiler assertions may collapse to one
assertion. Conflicting assertions at one source/span are ambiguous and fail
the projection. A missing original-syntax match, multiple matches, wrong
syntax or target kind, absent canonical target, absent/invalid definition
span, or generated target fails navigation-index construction; it never
produces a partial row or a whole-form fallback.

The conditional direct-retained `proc-ref` projection follows the same rule,
except that its typed `ProcRefLiteralExpr` supplies the whole form and canonical
procedure target and the uniquely matching original `(proc-ref NAME)` syntax
supplies only `NAME`'s exact span. An original `proc-ref` form with no retained
typed occurrence is outside the admitted subshape and remains null; the server
must not resolve it from its text. Within the admitted subshape, a missing,
multiple, kind-mismatched, target-mismatched, or span-mismatched join fails the
whole navigation index.

For macros, the compiler assertion must identify the macro's own canonical
target and authored `defmacro` span. Expansion IDs, expansion stacks, generated
expressions, and same-spelled expansion products are not definition targets.
If current retained expansion provenance cannot prove that own-definition
identity for local and imported macros without server resolution, the macro
shape defers in full.

## Contract

- **One common availability preflight.** Every new hit passes through the
  existing definition-request current-snapshot/configuration/source preflight
  before index lookup. There is no shape-specific bypass or last-good
  fallback.
- **Exact token only.** A hit requires the cursor inside `reference_span`.
  The opening delimiter, closing delimiter, adjacent whitespace, arguments,
  fill names, and any other part of the whole form return null.
- **No new server analysis.** The index consumes compiler-retained original
  syntax, semantic identities, catalogs, and provenance. The server does not
  read or parse source text, resolve a spelling, infer an import, or synthesize
  a canonical name.
- **Authored-to-authored only.** Every edge added by this amendment starts
  at an authored token and ends at an authored declaration. No edge crosses
  a generation boundary in either direction.
- **Separate namespaces and compiler visibility.** Prompt, procedure,
  workflow, and macro rows never merge even when their visible labels are
  equal. Local, import-alias-qualified, canonical-module-qualified, and
  `:only` spellings navigate only when the successful compiler result already
  binds that spelling to the retained canonical target in that reference
  kind. A private or ambiguous import rejected by the compiler has no
  successful snapshot and therefore returns null. Multiple or conflicting
  targets inside a nominally successful projection fail index construction;
  the LSP never guesses.
- **Freshness and failure behavior unchanged.** Unavailable/unreadable, dirty,
  compile-pending, dependency-invalidated, language-failed, server-failed,
  superseded, closed, unassociated, configuration-stale, source-stale,
  source/configuration-stale, clean-idle, malformed/internally inconsistent,
  navigation-index-failed, unsupported, generated, ambiguous, and
  outside-token requests retain the existing silent null result. Compiler
  diagnostics remain the explanation for compiler-rejected private or
  ambiguous references; L5 adds no competing diagnostic authority.

## Non-Goals

- No references, rename, or type-reference definition (still excluded until
  the compiler retains authored occurrence spans for them).
- No navigation into macro expansions, generated procedures, or specialized
  variants.
- No new navigation behavior for direct procedure calls, direct `(call ...)`
  workflow calls, or WCC-reconstructed/generated calls.
- No compiler/frontend changes, no invented metadata, and no source-map
  extension. A shape needing any of them defers rather than expanding this
  amendment's blast radius.
- No completion or symbol changes; this is the definition index only.

## Closed Feasibility Evidence

Read-only executable compiler probes closed the gate on 2026-07-27 without
modifying compiler/frontend code. Prompt heads establish the unique
whole-span-and-kind original-syntax join, exact head token, canonical
`PromptCatalog` target, and authored `defprompt` span in the final successful
Stage-3 result. Direct-retained unexpanded proc-refs establish the analogous
join through `ProcRefLiteralExpr`, the original exact `(proc-ref NAME)` form,
and the canonical procedure-catalog definition across:

- local, import-alias-qualified, canonical-module-qualified, and `:only`
  successful references;
- private and ambiguous imports failing through compiler authority;
- legal same-visible-label rows across callable families remaining distinct;
- exact-token and adjacent-outside-token behavior; and
- negative generated, expanded, specialized, erased, missing, duplicate,
  kind-mismatched, identity-mismatched, and span-mismatched cases.

The proof separately showed that macro-consumed, erased, generated-owner, and
specialized-owner proc-refs have no admitted final occurrence join. They
remain null. The macro probe found call and definition provenance but no
canonical/module-qualified own-definition identity that works across local and
imported macros; the macro shape therefore defers in full rather than shipping
a best-effort subset.

## Verification

- Compiler/projection fixtures prove every selected row field, the exact
  whole-span-and-kind join, deterministic ordering, and fail-closed
  missing/multiple/kind/identity/span mismatches.
- Local/imported fixtures prove alias-qualified, canonical-module-qualified,
  and `:only` visibility; private and ambiguous compiler failures; legal
  duplicate labels across prompt/procedure/workflow families; and no
  cross-family target substitution.
- Boundary fixtures put the cursor at the first and last in-token positions
  and at the opening delimiter, end boundary, adjacent whitespace, and every
  non-head argument.
- Every selected shape is exercised under the common preflight for
  unavailable/unreadable, dirty, compile-pending, dependency-invalidated,
  language-failed, server-failed, superseded, closed, unassociated,
  configuration-stale, source-stale, source/configuration-stale, clean-idle,
  malformed/internally inconsistent, and navigation-index-failed states.
  Every case returns null and no retained row bypasses the preflight.
- Existing direct local/imported procedure-call and direct `(call ...)`
  workflow-call hits remain exact. WCC reconstruction, generated/expanded
  calls, null `authored_callee_span`, unsupported kinds, and positions outside
  existing exact tokens remain null.
- A real stdio check against
  `workflows/examples/review_revise_design_docs.orc` resolves the fragment
  application head and preserves the already-working `(call ...)` result. Its
  two macro-consumed proc-refs and its macro head remain null and are
  regression-locked.

## Sequencing

Single L-series stage (L5 in the language-quality roadmap). Entry needs
only landed structure: Q1 catalog and L1 index infrastructure. It has no
dependency on L3 or L4. Ordered design reviews and read-only feasibility gates
are complete. The proposed L5 implementation plan contains only prompt heads
and the narrowly admitted direct-retained proc-ref shape; macro heads remain
deferred. Implementation selection requires ordered plan specification then
quality approval, followed by TDD, real stdio E2E, durable baseline
incorporation, and ordered final reviews.
