# Observability Step-Visit Summaries

Status: draft implementation design

## Problem

The summary observer currently behaves as if a logical step has one summary.
That is wrong for structured loops and repeated visits. A provider step can run
many times inside `repeat_until`, `match`, or a called workflow, but the
observable event is the executed visit, not the authored step name.

The current behavior creates two failures:

- provider steps executed inside nested loop bodies can be persisted without
  emitting a provider summary;
- repeated summaries use filenames derived only from the step name and summary
  kind, so later visits can overwrite earlier observability artifacts.

This is an observability bug, not workflow state. The fix must not affect
routing, dataflow, artifact authority, retries, resume, or step results.

## Design

Treat generated summaries as step-visit records.

Each summary record should have:

- logical step name;
- summary kind: `provider`, `phase`, or `step`;
- run id and workflow name;
- stable runtime step id when available;
- visit count when available;
- call-frame root via the existing aggregate index;
- output status, duration, outcome, artifacts, and debug fields.

The summary file stem should remain simple when there is no collision risk.
Top-level first visits keep their historical names. When the runtime identity
shows a repeated visit or loop iteration, the stem should include a sanitized
runtime step id and visit count:

```text
<safe-step-name>.<kind>.<safe-step-id>.visit-<n>
```

For looped body steps, the runtime step id already contains the loop iteration,
for example:

```text
root.implementation_review_loop#2...review_implementation
```

That gives each loop iteration its own summary file without inventing a new
global iteration counter.

## Runtime Emission

Top-level step persistence already emits summaries through
`OutcomeRecorder.persist_step_result`. Nested loop body execution must do the
same after it has:

1. executed the nested step;
2. recorded published artifacts;
3. attached normalized outcome;
4. recorded the result in loop state;
5. finalized consumes.

Only then should it call the existing summary emitter. This keeps summary
snapshots aligned with the persisted result and prevents summaries from
becoming a source of runtime truth.

The same rule applies to provider and phase-like nested body steps, but the
existing `phase-performance` filter still suppresses plain deterministic
command summaries.

## Indexing

The aggregate `RUN_ROOT/summaries/index.json` remains the dashboard source of
truth for generated summaries. It should append one entry per summary visit.
Entries should include `step_id` and `visit_count` when the snapshot contains
them. The dashboard can group or collapse by logical step, but it must not
discard visit records.

## Compatibility

Existing summary snapshots without `step_id` or `visit_count`, plus ordinary
top-level first visits, keep their current filename behavior. This preserves
old run artifact shape while allowing loop iterations and repeated visits to
become visit-scoped before they can overwrite each other.

## Non-Goals

- Do not change workflow execution semantics.
- Do not add a global workflow iteration counter.
- Do not make summaries authoritative state.
- Do not summarize every deterministic command in `phase-performance` mode.
- Do not redesign live agent notes or tmux capture in this tranche.

## Verification

Required coverage:

- summary observer writes visit-unique paths when snapshot identity is present;
- nested `repeat_until` provider visits emit provider summaries;
- repeated nested provider visits produce multiple index entries and distinct
  summary files;
- existing provider/phase summary behavior remains compatible for snapshots
  without runtime identity.
