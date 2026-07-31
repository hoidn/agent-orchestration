# Workflow Lisp Language Server L6 Utility Roadmap

Status: accepted design; no implementation selected. The owner-selected L6
design act is complete at commit
`e7de48e2710dddefbf14717575973b4ce41b5a06`, tree
`0a2bb399c10b4242c314f9fcc924cf89f6a6b9b6`, with accepted
[language-server design](../design/workflow_lisp_language_server.md) SHA-256
`3c52e3d0fb9c5683eae80ae3d81aae7d6e75bef71ef72c7daf19e6da1ecee338`
after ordered `L6_DESIGN_SPEC_APPROVED` then
`L6_DESIGN_QUALITY_APPROVED`; see the
[exact design review](../../artifacts/review/workflow-lisp-language-server-l6-design-review.md).
The predecessor language-quality roadmap remains complete (L0-L5 closed) and
is not reopened. The proposed
[L6 utility component plan](2026-07-31-workflow-lisp-language-server-l6-utility-component-plan.md)
is pending ordered specification then quality review and selects nothing.
Implementation still requires an accepted plan plus explicit owner activation
naming the exact independently selected unit or units.

Created: 2026-07-31

Copy safety: planning reference only; do not use this document as evidence
that any L6 capability is implemented. Authoring guidance continues to
describe the shipped surface until L6 is implemented, verified, reviewed,
and reflected in the capability matrix.

## Scope

Server-side utility increments over the existing clean-compile snapshot.
L6 touches no compiler frontend code and requires no P-series prerequisite.

| Item | Accepted design work | Source of truth consumed | Design/selection status |
| --- | --- | --- | --- |
| L6a | Hover: signature and declared-type presentation for authored callables and symbols at the cursor | the existing L1 symbol/signature catalogs on the current successful snapshot | Accepted design; unselected. The proposed [component plan](2026-07-31-workflow-lisp-language-server-l6-utility-component-plan.md) is pending ordered review and selects nothing. |
| L6b | References: `textDocument/references` as the reverse of the L5 definition index, over exactly the L5-admitted shapes | the existing L5 read-only occurrence index | Accepted design; unselected. The proposed [component plan](2026-07-31-workflow-lisp-language-server-l6-utility-component-plan.md) is pending ordered review and selects nothing. |
| L6c | Syntax grammar: the accepted standalone `.orc` TextMate JSON grammar with its bounded acceptance-only tokenizer oracle | separable deliverable; the language server design records it as architecturally independent; no server change | Accepted design; unselected. The proposed [component plan](2026-07-31-workflow-lisp-language-server-l6-utility-component-plan.md) is pending ordered review and selects nothing. |

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
