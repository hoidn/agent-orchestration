# Workflow Lisp Refactor Architecture: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_refactor_architecture.md](../../design/workflow_lisp_refactor_architecture.md).

### Compiler Pipeline

`compiler.py` should coordinate passes, not own every pass boundary.

Target ownership:

- pipeline entrypoints and result assembly stay in compiler coordination;
- graph compilation accumulators move into a named compile-state object;
- command adapter defaults move to a stdlib/adapter registry;
- executable-validation remapping is exposed through public lowering/source-map
  APIs, not private helper imports;
- single-file and linked-module stage-3 paths share a common pipeline object.

### Lowering

Lowering is the most important split. It is allowed to remain the runtime-facing
frontend boundary, but operation families should not all live in one file and
one mutable context.

Target ownership:

- lowering facade: public entrypoints and compatibility exports;
- lowering context: split into frozen config, lexical scope, and mutable output
  sinks;
- structured-result lowering: provider-result, command-result, produce-one-of;
- phase lowering: with-phase, phase-target, run-provider-phase,
  review-revise-loop, resume-or-start;
- resource/drain lowering: resource-transition, finalize-selected-item,
  backlog-drain;
- procedure lowering: inline/private/specialized procedure workflow generation;
- source-map bridge: generated step origins, hidden input origins, validation
  subject remapping.

The package split may happen before or after the first helper extractions, but
the long-term shape should preserve `orchestrator.workflow_lisp.lowering` as a
facade while moving implementation clusters behind it.

## Implementation Handoff

Use the execution plan at
[Workflow Lisp Low-Hanging Refactor Implementation Plan](../../plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md).
The first implementation tranche should address the concrete hazards and
expression traversal before larger package or registry moves.
