# Runtime Execution Lifecycle

This document describes what the orchestrator does at runtime for a workflow run.
It focuses on execution order and state transitions, not DSL authoring style.

Normative behavior is defined by `specs/`. This file is explanatory.

## Frontend And Compatibility Boundary

Fresh `run` accepts only a workflow path whose suffix compares
case-insensitively as `.orc`. YAML/YML and every other non-`.orc` path fail
with `.orc required` before a run root or `state.json` is created. There is no
production YAML parser.

Executable entries through 2.34 are retired. `resume` admits only a supported
evaluated header and refuses old profiles, including force-restart, before
changing their run contents. Invalidation has the same old-profile boundary;
see [CLI](../specs/cli.md#executable-support-boundary). Historical `report` and
dashboard views read state without compiling source or reconstructing an
executor. Native `prompt resume [--in-place]` is a separate retained session
bridge; it does not resume old workflow execution.

## Execution Profiles

Evaluated execution is the sole current workflow runtime. Historical flat
states remain readable; nothing converts a run between profiles.

| Profile | Targets | Authority on disk | Sections |
| --- | --- | --- | --- |
| Flat (historical, read-only) | through 2.34 | `state.json` (schema `2.1`, optionally `derived_pure_replay.v1`) | [Historical protocol](#execution-timeline); no creation, replay, repair or translation in this package |
| Evaluated | 2.35/2.36, bounded 2.37 and bounded 2.38 Agent Sessions and command-only confined run-ref children | `run.json` + `closed_program.json` + `memo.jsonl` (schema `3.0`, `evaluated_execution.v1`); `state.json` is a derived view | [Evaluated Profile (Target 2.35)](#evaluated-profile-target-235); [Agent Sessions guide](lisp_workflow_drafting_guide.md#agent-sessions-target-238); [confined-command recipe](lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only) (public confined providers remain closed) |

The linked flat record preserves the historical protocol for interpreting
old state, not commands to execute with this package. Recovery requires an
exact retained release/environment and evidence for that run family; the
[retirement contract](design/workflow_lisp_executor_retirement.md#7-recovery-policy-and-one-deletion-gate)
states the limits. The normative format owner is [State](../specs/state.md), with the evaluated profile in its
[target-2.35 section](../specs/state.md#evaluated-execution-persistence-profile-target-235);
the evaluated profile's design is
[evaluated execution](design/workflow_lisp_evaluated_execution.md).

<a id="execution-timeline"></a>
<a id="run-artifacts"></a>
<a id="step-state-machine"></a>
<a id="provider-step-runtime-order"></a>
<a id="consumepublish-runtime-semantics-v12"></a>
<a id="control-flow-resolution-order"></a>
<a id="retry-and-timeout-behavior"></a>
<a id="for_each-runtime-shape"></a>
<a id="failure-taxonomy-common"></a>

The retired flat timeline/state machine/provider/call protocol is preserved for historical interpretation. No creation, replay, repair or translation is supported; historical recovery needs demonstrated exact-release/environment evidence under the retirement contract. See the [preserved record](reports/documentation-history/docs-runtime_execution_lifecycle-history.md#historical-operational-record-1).

## Evaluated Profile (Target 2.35)

A target-2.35 program is compiled to a checked closed program and evaluated;
there is no flat IR, no `step_id`, no `call_frames`, no heartbeat and no
`transition_count` for it. Normative keys and transitions are in
[State](../specs/state.md#evaluated-execution-persistence-profile-target-235);
entries, exits and locks in [CLI](../specs/cli.md#evaluated-execution-target-235)
and its [resume preflight precedence](../specs/cli.md#resume-preflight-precedence);
command closure and typed inputs in
[Step IO](../specs/io.md#evaluated-command-and-provider-io-target-235); the design is
[evaluated execution §§7–10](design/workflow_lisp_evaluated_execution.md#7-the-effect-memo).
The [drafting guide recipe](lisp_workflow_drafting_guide.md#a-complete-235-recipe-compile-run-resume-report-invalidate)
shows the commands on one public fixture.

### Run

Four phases; the exact order inside each is normative in
[writer sequence and durability](../specs/state.md#writer-sequence-and-durability)
and [CLI](../specs/cli.md#evaluated-execution-target-235).

```text
1) Build and bind, with no lock: build the closed program from source, roots, entry and
   the four manifests (publishing the same build directory `compile` writes under
   .orchestrate/build/<key>/), then bind the typed inputs (--input / --input-file).
   --dry-run returns here: exit 0, no lock, no run root (exit 2 on a compile or binding
   error)
2) Take the workspace lock, then the run writer lock; publish run authority durably
   before any effect, in this order: empty memo.jsonl, closed_program.json, run.json
   (program/input digests, bound inputs, representation, pinned interpreters, the
   rebuild recipe `resume_request`, `run_ref_root`, `result_root`), each synchronized
3) Evaluate the program from its entry. Each reached effect is identified by its site and
   activation path; its input is resolved (argv/closure/contract and implementation-file
   digests for a command; prompt source, dependency and policy digests for a provider;
   config and inputs for a run reference). An active commit in the memo for that identity
   is reused and nothing is dispatched. Otherwise: synchronized `started` row with the
   next attempt ordinal, exclusive creation of effects/<sha256(identity)>/attempt-N/,
   one dispatch, validation of the result file against the declared type, rehash of the
   command's closure, then `committed` or `failed`; a path run reference adds `settled`
   after its child completes (or by reconciliation on the next resume). After every
   synchronized record, including `started`, state.json is atomically replaced
4) Append the `terminal` record (`completed` with the value, or `failed` with the code),
   replace the view, release the locks. Exit 0 or 1
```

### Run artifacts

- `.orchestrate/runs/<run_id>/run.json`: immutable header (authority)
- `closed_program.json`: the checked program (authority; digest in the header)
- `memo.jsonl`: append-only journal of `started`, `committed`, `failed`, `settled`,
  `invalidated` and `terminal` rows (authority)
- `effects/<sha256(identity)>/attempt-N/`: `result.json`, `stdout.txt`, `stderr.txt`,
  `prompt.txt` (provider), `inputs.json` (typed external document); a run-reference
  attempt holds only `result.json`
- `state.json`: derived view, replaced after every synchronized row; never authority
- `run.lock`, `run-ref-attempts.jsonl` (coordinator ledger)
- `.orchestrate/build/<key>/manifest.json`: build metadata, not a resume recipe

### Status and effect rows

Run `status` comes from the last record and the writer lock, not from a
heartbeat ([derived view](../specs/state.md#evaluated-execution-persistence-profile-target-235)):
`completed`/`failed` from the terminal; otherwise `settling` when a writer
holds the lock and replay reaches `halt`, `running` when a writer holds the
lock, `interrupted` when none does. A stored `state.json`
never says `interrupted`; only a reader's reconstruction can. Effect rows,
keyed by identity in order of first `started`, are `running`, `completed`,
`settling` (coordinator between `committed` and `settled`), `failed` or
`invalidated`; `current_step` is the effect in flight, `workflow_outputs` the
terminal value. A failed attempt is retried on the next resume with the next
ordinal, never by rewriting the old one.

### Resume

```text
1) Load and validate the header (profile, schema, run id, shapes of the recipe and roots)
   without reading the program or the memo; a header without a recipe refuses
   `resume_request_missing`; `--force-restart` refuses `evaluated_execution_unavailable`
2) Compare an explicit --run-ref-root with the header (`resume_run_ref_root_changed`), then
   the run root's relation to the workspace (`resume_result_root_changed`)
3) Rebuild the program in memory from the recipe and compare digests
   (`resume_program_changed`); re-read the input file, apply the overrides, bind and compare
   (`resume_inputs_changed`). Fresh build and binding publish nothing
4) Load the stored artifact and pins (`interpreter_changed` is a warning; a missing pin
   refuses); read the complete memo prefix, ignoring a torn tail
5) Replay the committed prefix in journal order, checking each resolved input
   (`effect_input_diverged` at the first divergence) before any launch, reconciliation or
   tail repair; a completed terminal that replay reaches returns without writing
6) Continue evaluation as in Run from the first uncommitted effect; retried attempts take
   the next ordinal
```

Every refusal in steps 1–5 exits 2 and writes nothing; exit 1 is a run that
executed and failed.

### Invalidation

`orchestrator invalidate RUN_ID IDENTITY [--state-dir DIR]` takes the writer
lock, validates the whole suffix from the chosen active commit in journal
order, and appends one synchronized `invalidated` row (`from_commit` is the
commit's byte offset); the next resume runs those effects again as new
attempts, earlier commits stay. It never resumes, forces, cascades by value
dependence or bypasses C4; a suffix containing a committed coordinator is
refused whole; a chosen identity without an active commit refuses
`invalidate_not_committed`.

### Readers

`report`, the dashboard scanner, the monitor classifier and scanner, the
watchdog probe and the usage-limit watcher share one read-only projection,
`orchestrator/workflow/evaluated/views.py::load_evaluated_view`, which
reconstructs the view from header, program and memo when `state.json` is
missing, stale or unparseable. Readers never append, repair or rebuild; a
preview or an explicit output of a reader is the reader's file, not a
mutation of the observed run. `monitor --once --dry-run` reads and
classifies; it is not an installed service and sends nothing.

The shared watchdog probe remains a reader. The watchdog workflow's executable
route is retired; keeping its probe does not preserve that runtime.

## Runtime vs Authoring Boundary

This file describes runtime behavior.
For writing Workflow Lisp and prompt patterns, use:
- `docs/orchestration_start_here.md`
- `docs/lisp_workflow_drafting_guide.md`

Use `docs/workflow_drafting_guide.md` only to translate or audit historical
YAML/YML definitions.
