# Backlog Item: `depends_on.inject` in Imported `2.x` Workflows

Current disposition: **historical YAML/import proposal; no current execution selected.**

The loader/import problem describes retired YAML execution. Current file-content injection uses typed provider-result prompt dependencies; the original implementation criteria are not declared complete.

Gate retained: No YAML loader restoration or new port selected.
This is a documentation disposition, not evidence of implementation completion
or authorization for new execution, spend, prompt edits or runtime work.
Current owners: [lisp workflow drafting guide](../../lisp_workflow_drafting_guide.md), [workflow lisp evaluated execution](../../design/workflow_lisp_evaluated_execution.md), [cli](../../../specs/cli.md).
[Backlog status inventory](../README.md).

Original proposal / historical checkpoint begins below. Its original status,
commands, measurements and tense are preserved; they do not override the current
scope notice.


- Status: active
- Created on: 2026-03-09
- Plan: `docs/plans/2026-03-09-follow-on-v2-call-extraction.md`

## Scope
Resolve the loader/runtime gap that rejects `depends_on.inject` inside imported `2.x` workflows used via `call`, so reusable library workflows can inject small dynamic path manifests or similar prompt inputs without falling back to extra state-file boilerplate.
