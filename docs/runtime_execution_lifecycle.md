# Runtime Execution Lifecycle

This document describes what the orchestrator does at runtime for a workflow run.
It focuses on execution order and state transitions, not DSL authoring style.

Normative behavior is defined by `specs/`. This file is explanatory.

## Frontend And Compatibility Boundary

Fresh `run` accepts only a workflow path whose suffix compares
case-insensitively as `.orc`. YAML/YML and every other non-`.orc` path fail
with `.orc required` before a run root or `state.json` is created. There is no
production YAML parser.

`resume` recognizes an evaluated run (target 2.35) by its header before any
flat-route state check ([CLI](../specs/cli.md#evaluated-execution-target-235));
for a flat run it loads the selected run's persisted state first. Once state
is loaded, every recorded workflow suffix other than `.orc` fails closed with
`.orc required`, regardless of run terminality or force-restart selection. A
non-`.orc` source is neither compiled nor executed. `report` and dashboard
views remain state-only observability for legacy runs; they do not parse
authored source or reconstruct executable workflow structure from it.

## Execution Profiles

A run belongs to one of two profiles, selected by its target and recorded in
its header; nothing converts a run from one to the other.

| Profile | Targets | Authority on disk | Sections |
| --- | --- | --- | --- |
| Flat (legacy) | through 2.34 | `state.json` (schema `2.1`, optionally `derived_pure_replay.v1`) | Execution Timeline, Run Artifacts, Step State Machine and the flat sections that follow them, up to the evaluated section |
| Evaluated | 2.35 | `run.json` + `closed_program.json` + `memo.jsonl` (schema `3.0`, `evaluated_execution.v1`); `state.json` is a derived view | [Evaluated Profile (Target 2.35)](#evaluated-profile-target-235) |

The flat sections below describe the flat profile only. The normative owner
of both is [State](../specs/state.md), with the evaluated profile in its
[target-2.35 section](../specs/state.md#evaluated-execution-persistence-profile-target-235);
the evaluated profile's design is
[evaluated execution](design/workflow_lisp_evaluated_execution.md).

## Execution Timeline

Flat profile (targets through 2.34).

```text
1) Enforce the `.orc` source boundary, then parse/typecheck Workflow Lisp
2) Elaborate the source into immutable typed surface AST nodes
   - run version-gated validation
   - normalize authored shapes (`if`, `match`, `repeat_until`, `finally`, `call`, `for_each`)
   - assign durable `step_id` values
   - capture typed provenance/import metadata and parse structured refs/predicates
3) Lower the surface AST into immutable executable IR plus a compatibility projection
   - bind refs/predicates to durable addresses
   - resolve routed transfers (`goto`, branch/case routing, loop/call/finalization edges) to node ids
   - map node ids back to compatibility surfaces such as `steps.*`, `current_step.index`, `finalization.*`, and report ordering
4) After successful frontend build and validation, initialize run root and `state.json`
5) Iterate executable nodes in IR order (or explicit routed transfers)
6) For each node:
   a) apply workflow/step cycle guards for the routed target (`max_transitions`, then `max_visits`)
   b) evaluate `when` (may skip)
   c) enforce consumes preflight (if configured)
   c1) for v2.10 session-enabled provider steps, create the canonical provider-session metadata + transport-spool artifacts before persisting `current_step`
   d) execute the node body (`assert`/command/provider/wait_for/for_each/call)
   e) validate deterministic outputs (`expected_outputs` or `output_bundle`)
   f) record published artifacts (if configured)
   f1) project normalized step `outcome` metadata for observable results
   g) compute the next node from IR fallthrough or routed transfers (`on.success`, `on.failure`, `on.always`, structured control, loop/call return)
   h) increment `transition_count` if control transfers into another top-level compatibility step
7) If declared, run workflow `finally` exactly once after the body settles on success or failure
8) Export workflow `outputs` (v2.1+, if declared) only after successful finalization, then persist final run status and report artifacts
```

Identity note:
- v2.0 assigns every step a durable internal `step_id`.
- Surface AST is the authored-shape truth; executable IR is the execution-shape truth.
- Presentation keys in `state.steps` remain name-oriented for compatibility, but lineage/freshness bookkeeping, resume planning, and report ordering now flow through the IR compatibility projection rather than raw lowered dict layout.
- `for_each` iterations derive qualified identities such as `root.loop_publish#0.produce_in_loop`.
- v2.2 structured `if/else` lowers to branch markers, lowered branch-body nodes, and a join node that keeps the authored statement presentation key.
- v2.3 structured `finally` lowers to stable cleanup-step identities under `finally.<StepName>` while keeping durable ancestry rooted under `root.finally.<block-id-or-finally>`.
- v2.5 `call` keeps the authored outer step as the caller-visible node and persists nested callee execution under `state.call_frames[call_frame_id]`.
- v2.7 `repeat_until` keeps the authored loop frame as the caller-visible node, derives per-iteration nested identities such as `root.review_loop#1.iteration_body.run_review_loop` or `root.review_loop#1.iteration_body.route_decision.revise_path.write_revision`, and persists resume bookkeeping under `state.repeat_until`.
- `resume` uses persisted run position only to choose the initial top-level restart point. After execution reaches that point, normal control-flow semantics resume, so a later `goto` may revisit the same top-level step name without being auto-skipped.
- v2.10 provider-session resume is distinct from workflow resume:
  - workflow `resume` restarts the orchestrator run
  - `provider_session.mode: resume` resumes one provider-native session inside a later step
- When finalization is partially complete, `resume` restarts at the first unfinished cleanup step instead of replaying completed cleanup.
- When a run stops inside a `call`, `resume` reuses the unfinished `call_frame_id` and restarts the callee from its first unfinished nested step instead of replaying completed nested work.
- When a run stops inside `repeat_until`, `resume` uses `state.repeat_until` plus indexed nested step results to restart from the first unfinished nested step in the current iteration; if that iteration's condition already evaluated, resume advances without replaying the settled iteration.
- Provider attempts are at-least-once across ordinary, session, supervision,
  peer-group, and phased execution. Compatible completed results remain
  invocation-free. After ordinary source, checksum, projection, checkpoint,
  and completed-result guards validate an exact interrupted in-flight visit,
  `resume` discards only that visit's partial result authority, emits exactly
  one `provider_attempt_interrupted_rerun`, and lets ordinary dispatch enter a
  fresh visit with fresh attempt identities. No interrupted provider session
  is resumed and no peer message is retargeted.
- Missing, malformed, conflicting, ambiguous, or checksum-incompatible
  provider-recovery state still fails closed before provider launch.
- During such revisits, `state.steps.<StepName>` still stores the latest completed/skipped/failed result for that top-level name, while `current_step` may refer to a later in-flight visit of the same step. The visit ordinals distinguish them: `current_step.visit_count` is the active visit, and `steps.<StepName>.visit_count` is the last persisted result visit.
- Runtime code no longer needs workflow-path/import magic fields or helper-key inspection to resume/report typed runs; typed provenance/import metadata plus the compatibility projection are the maintained bridge back to the persisted compatibility surfaces.
- `expanded.debug.yaml` is an intentionally historical filename for an optional
  JSON-rendered projection. It is never source authority and is not read by
  fresh execution or legacy compatibility views.

## Run Artifacts

Flat profile. Primary run directory:
- `.orchestrate/runs/<run_id>/`

Core files/directories:
- `state.json`: authoritative execution record
- `logs/`: stdout/stderr spill files, prompt audits (debug mode), orchestrator logs
- `summaries/`: optional advisory step summaries when enabled by CLI flags

Console visibility:
- `--stream-output` live-streams provider stdout/stderr to the terminal during execution.
- `--debug` also streams provider output, but additionally enables prompt-audit and debug-mode artifacts.

## Step State Machine

Flat profile.

```text
pending -> running -> completed
pending -> running -> failed
pending -> skipped
```

Key notes:
- `when` false produces `skipped` with `exit_code: 0`.
- `assert` false produces `failed` with `exit_code: 3` and `error.type: "assert_failed"`.
- `cycle_guard_exceeded` fails the target step before body execution and stops further routed step execution; step-level recovery edges do not override it.
- `contract_violation` failures are represented as failed steps (typically exit code `2`).
- `call` executes an imported workflow inline with its own nested state, private providers/artifacts/context defaults, and caller-visible outputs exported only after the callee body and callee finalization succeed.
- Non-zero exits route through failure handlers if defined; otherwise strict-flow/on-error policy applies.
- Ordinary resumed execution clears `current_step` when it reaches terminal
  state. Early root checksum or projection rejection before the prologue is an
  exception: it may retain the unchanged cursor for forensics. The root
  `status` and `error` govern observability; the retained cursor is not live
  for status, heartbeat, or stalled-run interpretation. See the [state
  integrity contract](../specs/state.md#state-integrity-and-recovery).
- For structured `if/else`, non-selected lowered branch nodes appear as `skipped`, while the selected-branch outputs are materialized on the join node under the authored statement name.
- For `repeat_until`, the loop frame stays `running` while iterations are in progress, materializes declared loop outputs after each completed iteration, and fails with `repeat_until_iterations_exhausted` if `max_iterations` is reached before the condition becomes true.
- For structured `finally`, cleanup failures after body success become the run's primary failure; if the body already failed, cleanup failures are recorded as secondary diagnostics under `state.finalization`.

## Provider Step Runtime Order

Authoring-surface note:
- Workflow-boundary `inputs` / `outputs` are interface contracts, not prompt sources.
- Runtime dependencies (`depends_on`, `consumes`) are resolved before execution; they are distinct from both boundary contracts and prompt-source selection.
- Provider prompt sources are `input_file`, `asset_file`, and `asset_depends_on`.
- Artifact storage / lineage surfaces are `artifacts`, `expected_outputs`, `output_bundle`, and `publishes`.

For provider steps, runtime behavior is effectively:

```text
compose prompt
  = base prompt source literal (input_file from WORKSPACE, or asset_file from the workflow source tree)
  + optional asset_depends_on injection
  + optional depends_on injection
  + optional consumed-artifacts injection (v1.2+)
  + optional output-contract suffix

execute provider command template (argv or stdin mode)

capture stdout/stderr

validate deterministic outputs if declared
```

For v2.10 session-enabled provider steps, runtime behavior adds:
- select `command`, `session_support.fresh_command`, or `session_support.resume_command`
- bind `${SESSION_ID}` only from the reserved `session_id_from` consume
- normalize provider transport before `output_capture`
- publish fresh session handles only after the exact visit's terminal step result, same-visit lineage appends, and matching `current_step` clearance are committed together

Prompt composition details are normative in `specs/providers.md`.

## Consume/Publish Runtime Semantics (v1.2+)

Before step execution:
- `consumes` preflight selects artifact versions according to policy/freshness.
- Missing or stale required artifacts fail preflight with `contract_violation`.
- In v1.2 / v1.3, relpath consume preflight materializes the selected value to the canonical pointer file.
- In v1.4, relpath consume preflight is pointer-safe/read-only (no pointer-file mutation).
- Scalar consumes never write pointer files.
- Optional `consume_bundle` writes resolved consume values to deterministic JSON for the step.

After successful step execution + output validation:
- `publishes` appends new artifact versions to `artifact_versions` in state.
- `artifact_consumes` tracks last consumed version(s) for freshness enforcement.
- For `call`, callee-private publish/consume state remains inside the persisted call frame; only declared callee outputs cross back to the caller-visible outer step.

## Control-Flow Resolution Order

Runtime resolves next step in this order:
1. Applicable `on.success` or `on.failure`
2. `on.always` (if present)
3. Default flow behavior (next sequential step or strict-flow/on-error behavior)

After the next top-level target is known, the executor increments `transition_count`. If the next routed target would exceed `max_transitions`, that target fails pre-execution on entry.

Special target:
- `_end`: explicit successful termination.

## Retry and Timeout Behavior

- `timeout_sec` applies to command/provider execution and can produce exit code `124`.
- Provider steps have retry defaults for retryable exit codes.
- Command steps retry only when per-step retry config is present.
- Step-level retry config overrides default/global retry behavior.

See `specs/dsl.md`, `specs/providers.md`, and `specs/io.md` for normative details.

## for_each Runtime Shape

At runtime, loop results are recorded per iteration:
- `steps.<LoopName>[i].<NestedStepName>`

Loop variables are resolved per iteration (`item`, alias, `loop.index`, `loop.total`).
Typed predicates in v2.0 may also read scoped refs from the current loop scope (`self.steps.*`) or the enclosing scope (`parent.steps.*`) without changing legacy `${steps.*}` substitution semantics.

## Failure Taxonomy (Common)

- process failure: command/provider non-zero exit
- gate failure: first-class `assert` evaluated false
- timeout failure: enforced timeout (often exit `124`)
- parse failure: invalid JSON capture when strict JSON mode required
- contract failure: deterministic output or consume/publish contract violation
- predicate evaluation failure: typed predicate/ref resolution failed before the step body could complete

These are reflected in step `status`, `exit_code`, and `error` fields in `state.json`.

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

## Runtime vs Authoring Boundary

This file describes runtime behavior.
For writing Workflow Lisp and prompt patterns, use:
- `docs/orchestration_start_here.md`
- `docs/lisp_workflow_drafting_guide.md`

Use `docs/workflow_drafting_guide.md` only to translate or audit historical
YAML/YML definitions.
