# Workflow Lisp Language Server L6 Utility Roadmap

Status: owner-selected 2026-07-31 as the tracked L6 stage. The predecessor
language-quality roadmap is complete (L0–L5 closed) and is not reopened by
this document; L6 is a successor stage under the same L-series discipline,
carried by this standalone surface. Selection here authorizes the design
act only: implementation requires an accepted design amendment to the
[language server design](../design/workflow_lisp_language_server.md),
ordered specification then quality reviews, and a reviewed component plan.

Created: 2026-07-31

Copy safety: planning reference only; do not use this document as evidence
that any L6 capability is implemented. Authoring guidance continues to
describe the shipped surface until L6 is implemented, verified, reviewed,
and reflected in the capability matrix.

## Scope

Server-side utility increments over the existing clean-compile snapshot.
L6 touches no compiler frontend code and requires no P-series prerequisite.

| Item | Work | Source of truth consumed |
| --- | --- | --- |
| L6a | Hover: signature and declared-type presentation for authored callables and symbols at the cursor | the existing L1 symbol/signature catalogs on the current successful snapshot |
| L6b | References: `textDocument/references` as the reverse of the L5 definition index, over exactly the L5-admitted shapes | the existing L5 read-only occurrence index |
| L6c | Syntax grammar: a dedicated `.orc` tree-sitter or TextMate grammar | separable deliverable; the language server design already records it as architecturally independent; no server change |

## Bounds (inherited from the L-series, binding)

- The server remains a read-only consumer of production compile entry
  points: no second analyzer, no diagnostic-prose parsing, no
  independently inferred types, no frontend edits.
- Fail-closed freshness is unchanged: hover and references answer only from
  the current successful snapshot; dirty, pending, stale, failed, closed,
  and unassociated states return null, mirroring L5's silent-null contract.
- L6b returns hits only for L5-admitted shapes; macro-consumed, erased,
  expanded, generated-owner, and specialized-owner occurrences remain
  excluded. L6a presents only compiler-rendered signatures and declared
  types; arbitrary-expression type-at-cursor remains P3-gated and is
  explicitly out of L6 scope.
- Diagnostic identity and CLI/LSP compile-request parity are untouched.

## Sequencing And Concurrency

- Independent of the E program and of the P-series: L6 surfaces
  (`orchestrator/lsp/*`, grammar assets) are disjoint from E's
  experiment/runtime seams and from P's compiler-frontend scope. L6 is
  concurrent-safe beside both and is not gated on either.
- L6 is not P work: the
  [P-series roadmap](2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md)
  remains sequenced after the E program and is unaffected by this
  selection.
- L6a/L6b/L6c are independently selectable and reviewable; L6c may proceed
  or be dropped without affecting L6a/L6b.

## Completion

Per item: implemented with TDD plus narrow-then-broad non-security checks,
one repository-real stdio (or editor) gate for server-facing items, ordered
independent specification then quality review, and capability matrix plus
setup-doc updates.
