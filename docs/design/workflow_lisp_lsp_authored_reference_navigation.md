# Workflow Lisp LSP Authored Reference Navigation

- **Status:** proposed (owner-directed 2026-07-27); independent specification
  review, then independent quality review, required before implementation
  planning. Accepted content folds into
  `docs/design/workflow_lisp_language_server.md` as the owning amendment,
  per the L-series convention.
- **Kind:** L-series language-server amendment — definition-index extension
  over already-retained compiler structure
- **Owner:** `orchestrator/lsp` navigation index; read-only consumer of
  existing compile results, per the standing L-series bounds
- **Motivating evidence:** in
  `workflows/examples/review_revise_design_docs.orc` — the estate's most
  edited workflow — every callable-reference position returns null today
  (probed 2026-07-27 over live stdio): the fragment application head, both
  `proc-ref` arguments, the `(call ...)` callee, and the macro head. The
  implemented definition surface (exact direct authored call heads) is
  test-proven but nearly disjoint from production authoring style, which
  references callables through forms, macros, proc-refs, and fragment
  applications.
- **Related authority:**
  - `docs/design/workflow_lisp_language_server.md` (implemented v1 + L0–L2
    amendments; the closed navigation contract this extends)
  - `docs/design/workflow_lisp_prompt_calculus.md` (Q1 prompt catalog and
    application spans; Q1/Q3 fragment identity)
  - `docs/design/workflow_language_design_principles.md` principles 24
    (source maps are semantic infrastructure), 28, and 30

## Problem

Go-to-definition indexes only bare direct authored calls
(`(identity report_path)`), while authored workflows reference callables
almost exclusively through four other shapes. All four are authored tokens
whose resolutions the compiler already computes; the navigation index simply
never consumed them. The result: a feature that is implemented, tested, and
unusable in the files it exists for.

## Scope: Four Reference Shapes

| # | Shape | Resolves to | Compiler retention already present | Status in this design |
| --- | --- | --- | --- | --- |
| 1 | Fragment application head — `(review-design-doc ...)` in `provider-result :prompt` | the `defprompt` declaration's authored span | Q1 prompt catalog (module-namespaced declarations with source locations); typed applications checked with exact spans | selected |
| 2 | `proc-ref` name argument — `(proc-ref review-design-docs)` | the `defproc` authored span | proc-refs resolve through typecheck to canonical callable identity (the same identity the existing index keys on) | selected |
| 3 | `(call X)` callee token | the target workflow/procedure authored span | the `call` form's callee is compiler-resolved against the workflow catalog with an authored token span | selected |
| 4 | Macro head — `(review-revise-loop ...)` | the `defmacro`'s own authored span — never through the expansion | expansion provenance exists (expansion IDs, stacks); whether the *use-site head token span* survives Stage 3 in an indexable form is unproven | conditional — feasibility probe first |

Shape 4's rule is categorical: navigation may target the macro's authored
definition, and must never tunnel into expansion products — the existing
"generated call provenance is never indexed" prohibition is about expansion
*outputs* and is unchanged. If the probe shows the use-site head span is not
retained without new compiler work, shape 4 joins the type-reference
exclusion (deferred until the compiler retains the spans) rather than
motivating frontend churn from an L stage.

## Contract

- **Same closed discipline as the existing index, extended, not relaxed.**
  Hits require the cursor inside the exact authored reference token span;
  every current null category (dirty, pending, invalidated, stale,
  generated, ambiguous, arguments outside the indexed token, unsupported
  kinds) remains null. Resolution uses canonical compiler identity with the
  same namespace/visibility/ambiguity rules L1 applies to completion —
  ambiguity is null, never a guess.
- **No new server analysis.** The index is built from compiler-retained
  catalogs and spans exactly as today; the server does not parse source,
  resolve names itself, or infer from text (standing L-series bound).
- **Authored-to-authored only.** Every edge added by this amendment starts
  at an authored token and ends at an authored declaration. No edge crosses
  a generation boundary in either direction.
- **Freshness unchanged.** The current-snapshot gating, restart latches, and
  L2 recovery-state classifications apply to the new shapes identically.

## Non-Goals

- No references, rename, or type-reference definition (still excluded until
  the compiler retains authored occurrence spans for them).
- No navigation into macro expansions, generated procedures, or specialized
  variants.
- No compiler/frontend changes; if a shape needs new retention, it defers
  (shape 4's contingency) rather than expanding this amendment's blast
  radius.
- No completion or symbol changes; this is the definition index only.

## Verification Sketch

Per-shape hit fixtures plus per-shape null fixtures (ambiguous twin names,
stale document, cursor adjacent to but outside the token). The review
workflow itself is the end-to-end gate: over real stdio, the fragment head,
both proc-ref names, and the call callee resolve to their declarations —
the exact positions probed null on 2026-07-27 — with shape 4 asserted per
its feasibility outcome. Existing navigation suites must pass unchanged
(the direct-call surface and all null categories are regression-locked).

## Sequencing

Single L-series stage (L5 in the language-quality roadmap). Entry needs
only landed structure: Q1 catalog, L1 index infrastructure. No dependency
on L3 (blocked on substrate MR-4) or L4; under the L-series' standing
owner-reordering rule it is eligible to execute next while L3 waits.
Required order per the roadmap standard: this design reviewed
(specification, then quality), reviewed implementation plan, TDD, real
stdio E2E, ordered final reviews.
