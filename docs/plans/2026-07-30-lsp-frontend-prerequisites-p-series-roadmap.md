# LSP Frontend Prerequisites P-Series Roadmap

Status: tracked, sequenced after the E program (2026-07-30 owner decision).
Not active work instructions and not a selector: no P item is selected by
listing, and P implementation remains unselected until this document's entry
conditions hold and the owner records a selection act. The P-series was
introduced and deferred together in the accepted
[language server design](../design/workflow_lisp_language_server.md)
(proposed 2026-07-13, accepted 2026-07-25), which owns each item's technical
definition; this document adds only tracking, ordering, and gates.

Created: 2026-07-30

Copy safety: planning reference only; do not use this document as evidence
that any P capability is implemented. The language server remains the v1
read-only surface plus the completed L-series increments until an owning P
stage is implemented, verified, reviewed, and reflected in the capability
matrix.

## Scope

The five deferred compiler-frontend prerequisites, defined in the language
server design:

| Item | Work | Unlocks |
| --- | --- | --- |
| P1 | Diagnostic accumulation: shared typecheck raise helpers and the validation-pipeline continuation policy collect multiple diagnostics per pass before failing | many diagnostics per compile; the design ranks P1 highest UX value per unit of work and recommends it first |
| P2 | Reader error recovery: partial-AST production from malformed buffers, synchronizing on list boundaries | any analysis of mid-edit buffers |
| P3 | Span-to-type metadata: the compiler retains a queryable span-to-type mapping | arbitrary-expression hover types; span-exact type presentation |
| P4 | Source overlays: compiling from in-memory buffer contents overlaid over disk sources | unsaved-buffer diagnostics and navigation |
| P5 | Compile caching/incrementality | interactive-latency feedback; affordable frequent recompiles |

Dependent editor features (multi-diagnostic recovery, arbitrary expression
hover, as-you-type checking, unsaved-buffer navigation) remain owned by the
language server design and its amendments; this roadmap schedules
prerequisites, not features.

## Sequencing

- **Position: after the E program.** The P-series enters selection only
  after the E-series (tracked in the incorporated
  [evolution follow-on roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md))
  reaches its recorded completion or an explicit owner decision closes or
  re-parks it. Rationale: E-series trial-run authoring is the expected
  driver of `.orc` authoring volume, and authoring volume is the recorded
  justification trigger for core-frontend surgery.
- **Owner acceleration:** the owner may select a P item earlier by explicit
  decision; nothing else may.
- **Internal order:** P1 first per the design's recommendation, unless the
  selecting decision records otherwise. P2+P4 compose toward dirty-buffer
  analysis; P3 and P5 are independently selectable.

## Entry Conditions And Gates

- Entry: E-program completion (or explicit owner re-park/closure decision),
  plus a design amendment to the language server design for the selected P
  item, plus its own reviewed component plan. The accepted design requires
  exactly this: scheduling P work needs an explicit amendment and a roadmap
  slot; this document is that slot.
- Standing bounds inherited from the language-quality roadmap remain
  binding: the language server stays a read-only consumer of production
  compile entry points; no second analyzer; no diagnostic-prose parsing;
  CLI/LSP compile-request parity and compiler authority are preserved. P
  items change the shared production frontend and therefore carry
  compiler-side evidence (frontend tests and CLI parity), not LSP-only
  evidence.
- Completion per item: implemented, verified with TDD plus narrow-then-broad
  non-security checks, ordered independent specification then quality
  review, and the capability matrix plus authoring guidance updated.
