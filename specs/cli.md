# CLI Contract (Normative)

## Executable support boundary

The owner selected retirement of the flat executor on 2026-10-13. This
contract describes the implemented cutoff candidate; [gate R and its
closeout](../docs/reports/2026-10-13-best-of-n-and-executor-retirement-closeout.md)
own qualification and delivery, not a published package-version claim.

Only evaluated entries at 2.35/2.36, bounded 2.37, bounded 2.38 (command-only
confined run-ref and agent sessions), and target 2.39 procedure authoring and
bounded phased provider delivery are executable, with their existing admission
and qualification limits
([versioning](versioning.md#version-gating-summary)).
`compile`, `run` and `run --dry-run` reject entry targets through 2.34 with
`workflow_execution_target_retired`, exit 2, before build/run publication or
execution locks. The captured compiled entry is checked again before
publication. The selected source floor also rejects every pre-2.35 dependency
header from compilation, typed import, REPL loading/type queries and LSP
analysis. The syntax/import diagnostic is `target_dsl_unsupported` at the
unsupported module header; existing public old-entry retirement refusal keeps
its precedence and exit 2. No automatic header conversion or diagnostic-only
legacy compiler is available. Evaluated path
children obey the same entry boundary; retired flat/staged child execution
has no fallback.

`resume` (including `--force-restart` and `--repair`) and `invalidate` reject
historical workflow profiles with `workflow_execution_profile_retired`, exit
2, before locks or run-state mutation. `prompt run` in every generation or
scaffold mode and both `prompt import` branches reject with
`prompt_execution_retired`, exit 2, before scaffold/run/session writes or
effects. Native `prompt resume [--in-place]` remains an independent,
compiler-free continuation of an existing linked session.

The target-2.25 trial CLI/compile-and-run SDK, old `WorkflowExecutor` and flat
lowerer execution APIs, ES/research trial execution, generic workflow watchdog
execution and flat `explain`/IR views are selected for retirement; no replacement
port is selected. `explain` refuses with `workflow_explain_retired`, exit 2,
before source/build/export reads or writes; `compile --diagnostics-json`
remains available for current source validation. Parser/types, admitted closed compilation, REPL/LSP
inspection admit only source graphs at 2.35 or newer. Shared provider/read
services retain their current consumers. A stale old-target LSP snapshot must
not supply callables after floor refusal; static recovery is not legacy
analysis. Imported typed-program/bundle objects must obey the same source-target
floor rather than bypassing it through a Python or manifest door.
Current compiler/build calls expose no `lowering_route` selector; retained
artifact schema fields cannot select historical compilation. LSP evaluated
semantic qualification remains **OPEN_NOT_WAIVED**, independently of the floor.
Historical `report`, dashboard and `input get` read retained evidence without
compiling source or rewriting it. Original run data is preserved. Recovery
requires the exact complete release/environment qualified for the particular
family; preserved source or a package pin alone is no universal recovery
guarantee ([retirement policy](../docs/design/workflow_lisp_executor_retirement.md#7-recovery-policy-and-one-deletion-gate)).

## Workspace execution ownership

Only one admitted evaluated run may execute in a workspace at a time.
`run` and `resume` acquire a workspace lock before execution-state mutation.
Retired-target/profile refusals above precede locks. A competing invocation is
refused with `workspace_run_already_active`, naming the active run, and exits
2. Exit 2 means refusal before execution or a compile/validation error; read
the diagnostic code to distinguish them. Exit 1 is a workflow that ran and
failed. Changing `--state-dir` does not bypass this rule. Nested workflow
calls belong to their root run; run-reference children own separate clone
workspaces. `prompt resume` (including a provider launched with `--in-place`),
`input get`, `report` and `dashboard` take no workspace execution lock.
`invalidate` takes only the admitted run's writer lock
([Evaluated execution](#evaluated-execution-target-235)).

The workspace is the physical current directory: a path that reaches it through
a symbolic link names the same workspace. The lock is an exclusive `flock` on
`.orchestrate/workspace.lock`, which records the owner's run ID as metadata. A
starter holds `.orchestrate/workspace.guard` while it takes the lock and
records its ID, so a refusal names the current owner. A starter waits at most
5 seconds for the guard; if another starter still holds it, the request is
refused with `workspace_run_already_active` and a message that the guard is
held. Exclusion assumes a local filesystem. On NFS, `flock` is emulated with
byte-range locks on the server, and with `local_lock=flock` or
`local_lock=all` it excludes only processes on one host.

The operating system releases ownership when execution returns (including
failure or suspension) or the process dies. Retained lock metadata is not
authority: a dead process's lock file does not prevent a later run. Lock files
are not removed on release. `--dry-run` neither acquires nor requires this
lock. Existing per-run writer locks still coordinate mutation of a run;
read-only reporting remains available. When another process holds a run's
writer lock, `run` and `resume` refuse with `run_already_active` and exit 2, as
for `workspace_run_already_active`. Concurrent execution requires separate
workspaces. Result bundle paths and persisted result identities are unchanged.

An admitted `run` or `resume` started from inside an active run (by one of its
command steps or providers) in that run's workspace is a competing invocation
and is refused the same way; only nested workflow calls belong to the root run.
Execution in separate workspaces must still satisfy the admission boundary;
this locking rule does not retain workflow supervision or watchdog execution.

- Commands
  - `orchestrate run <workflow.orc> [--context k=v ...] [--context-file path] [--input name=value ...] [--input-file path] [--clean-processed] [--archive-processed <dst>]`
    - `--dry-run` builds and binds an admitted evaluated entry without executing
      effects; retired targets refuse before publication.
  - `orchestrate resume <run_id>`
    - The evaluated memo/profile recovery and preflight contract below applies.
      Retired profiles refuse before locks, source rebuild or mutation; historical
      session/supervision/peer/phased/adjudicated recovery is not admitted.
  - `orchestrate input get <run_id> [--state-dir <runs-root>]`
    - Prints the current root host-request record. It does not resume or
      mutate execution.
  - `orchestrate input answer <run_id> <request_id> --text <text> [--state-dir <runs-root>]`
    - Retired: exits 2 with `workflow_execution_profile_retired` before locks
      or writes, including an otherwise valid target-2.32 request.
  - `orchestrate input cancel <run_id> <request_id> [--state-dir <runs-root>]`
    - Same no-write retirement refusal as `input answer`. Historical settlement
      semantics are retained in [State](state.md#durable-host-input-state-and-recovery);
      `input get` remains a read-only client, printing the recorded request as
      JSON with exit 0, or exit 2 for a missing/invalid request.
  - `orchestrate report [--run-id <id>] [--runs-root <dir>] [--format md|json] [--output <path>]`
    - Report output may include advisory lint warnings (`lint.warnings[]` in JSON or an appendix in Markdown); warnings remain informational only.
    - Report output may include active runtime fields derived from executor sessions, including `run.active_runtime_ms`, `run.active_runtime`, `run.executor_session_count`, and `run.excluded_suspended_ms`. These fields exclude suspended gaps between executor processes and are informational only.
    - Report output may surface provider-session metadata paths and bounded
      interrupted-rerun diagnostic context; partial provider evidence remains
      non-authoritative.
  - `orchestrate prompt run (--prompt TEXT | --prompt-file PATH) --provider (omp|omp_no_tools|omp_conf|omp_unrestricted_workspace) [--conf PATH] [--model MODEL] [--returns JSON | --output TEXT]`
    - Retired in every default/exact/inferred contract mode: exits 2 with
      `prompt_execution_retired` before reading inputs, inference or writes.
  - `orchestrate prompt run --scaffold PATH`
    - Same refusal before scaffold verification, reservation or execution.
  - `orchestrate prompt resume ID [--in-place]`
    - This foreground command requires fd 0, 1, and 2 to be TTYs before lock
      acquisition or child launch. The default is one full-id fork into a new
      session; `--in-place` resumes the linked primary session. It accepts only
      one exact linked primary OMP journal, holds one per-session lock through
      preflight, child, validation, and one no-replace continuation append, and
      exits 0 on success, 1 on any failed post-start outcome, and 2 on
      grammar errors. The continuation record retains the observed child exit
      code; every post-start outcome publishes exactly one closed record.
  - `orchestrate prompt import ID --provider NAME [--conf PATH] [--model MODEL] [--returns JSON | --output TEXT] [--reuse-run-contract]`
    - Both ordinary import and `--reuse-run-contract` are retired with
      `prompt_execution_retired`, exit 2, before journal/scaffold reads or writes.
  - `orchestrate provider-isolation-environment-manifest --root <absolute-source> --provider-prefix <absolute-prefix> --output <absolute-manifest>`
    - Prospectively validates and canonicalizes one provider rootfs, including
      the runtime-reserved launch shim row, without mutating the source or
      creating a runtime snapshot.
    - Prints the canonical `sha256:<hex>` environment digest and atomically
      publishes the canonical manifest as a new single-link `0600` file.
    - The output parent must already be a real controller-owned, xattr-free
      `0700` directory reached through a trusted ancestor chain. The output
      must not exist, alias the source, overlap the source authority in either
      containment direction, or reuse the basename of any scanned source
      entry.
    - This controller-only authoring command proves the fixed packaged
      shim/interpreter bootstrap closure. It does not launch a provider and
      does not by itself make provider-phase isolation available.
  - `orchestrate dashboard --workspace <root> [--workspace <root> ...] [--host 127.0.0.1] [--port <port>]`
    - Serves a local, read-only dashboard for explicit workspace roots.
    - The dashboard scans `<workspace>/.orchestrate/runs/*/state.json` at request time and keys runs by `(resolved workspace root, run directory name)`.
    - The default bind host is `127.0.0.1`; binding to another host is an explicit operator choice.
    - Routes include `/runs`, `/runs/<workspace_id>/<run_dir>`, `/runs/<workspace_id>/<run_dir>/summaries`, `/runs/<workspace_id>/<run_dir>/summaries/live.json`, step detail, state preview, and route-scoped workspace/run file previews.
    - Dashboard routes must not execute `resume`, `report`, tmux, provider CLIs, shell commands, or child processes. Copyable commands are rendered as inert text only.
  - `orchestrator monitor --config <path> [--once] [--dry-run] [--dry-run-mark-sent] [--ledger <path>]`
    - Monitors explicit workspace roots from the config file and sends email notifications for completed, failed, crashed, or stalled workflow runs.
    - `--once` performs one scan and exits; without it, the monitor polls until interrupted.
    - `--dry-run` renders notifications without SMTP delivery and does not mark them sent by default.
    - `--dry-run-mark-sent` may be used only with `--dry-run`; it updates the ledger after rendering so duplicate suppression can be rehearsed.
    - `--ledger` overrides the default notification ledger path.
    - Exit code `0` means the scan completed and eligible notifications were handled; `1` means config, scan, or delivery failed; `130` means polling was interrupted.
  - Optional/post-MVP: `orchestrate run-step <step_name> --workflow <workflow.orc>`, `orchestrate watch <workflow.orc>`

- Debugging and recovery flags
  - `--debug`, `--stream-output`, `--progress` (post-MVP), `--trace` (post-MVP), `--dry-run`
  - Historical flat observability flags (not read by evaluated execution): `--step-summaries`, `--summary-mode async|sync`, `--summary-provider <name>`, `--summary-timeout-sec <n>`, `--summary-max-input-chars <n>`, `--summary-profile basic|phase-performance`, `--live-agent-notes`, `--live-agent-note-provider <name>`, `--live-agent-note-interval-sec <n>`, `--live-agent-note-timeout-sec <n>`, `--live-agent-note-max-tail-chars <n>`
    - `--summary-profile phase-performance` enables advisory provider-step and phase-boundary summaries with performance judgments. It implies step summaries if `--step-summaries` was not otherwise provided.
    - `--live-agent-notes` enables advisory live notes from bounded tmux pane tails, using `claude_haiku_summary` by default. Provider-session transport may be used as a fallback when tmux pane capture is unavailable. It implies step summaries if `--step-summaries` was not otherwise provided.
  - `--force-restart`, `--repair`, `--backup-state`, `--state-dir <path>`
    (`--force-restart` is refused for evaluated runs; `--repair` and
    `--backup-state` have no evaluated recovery effect. Retired profiles refuse
    regardless of these flags; see [Evaluated execution](#evaluated-execution-target-235))
  - Error handling: `--on-error stop|continue|interactive` (interactive optional/post-MVP)
  - Retries: `--max-retries <n>`, `--retry-delay <ms>`

- Output control
  - `--quiet`, `--verbose`, `--json` (optional/post-MVP), `--log-level debug|info|warn|error`

- Planned environment defaults (not implemented)
  - `ORCHESTRATE_DEBUG=1`, `ORCHESTRATE_STATE_DIR=/tmp/runs`, `ORCHESTRATE_LOG_LEVEL=debug`, `ORCHESTRATE_KEEP_RUNS=30`
  - These reserved names currently have no CLI effect. Use `run --debug`,
    `run --log-level`, and `run`/`resume --state-dir` for supported controls.
    Automatic retention is not implemented; its deletion and precedence
    contract must be specified before `ORCHESTRATE_KEEP_RUNS` is activated.

- Safety
  - `--clean-processed` only operates on the configured `processed_dir` when it resolves within WORKSPACE.
  - `--archive-processed` destination must not be inside the configured `processed_dir`. Default output is `RUN_ROOT/processed.zip`.

## Commands and Examples

```bash
# Run an admitted evaluated entry (provider execution changes the workspace)
orchestrate run workflows/examples/plan_review_execute.orc \
  --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json \
  --input task="Describe the repository architecture"

# Resume failed/interrupted run
orchestrate resume <run_id>

# Render status report for latest run
orchestrate report --format md

# Serve local dashboard for one or more explicit workspaces
orchestrate dashboard --workspace "$(pwd)" --host 127.0.0.1 --port 8765

# Monitor configured workspaces once without sending email
orchestrator monitor --config ~/.config/orchestrator/monitor.json --once --dry-run

# Build and bind the same source without executing providers
orchestrate run workflows/examples/plan_review_execute.orc \
  --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json \
  --input task="Describe the repository architecture" \
  --dry-run
```

### Workflow Lisp trials (target 2.25)

```text
orchestrate trial WORKFLOW --entry-workflow NAME
  [--input NAME=VALUE ...] [--input-file JSON]
  [--source-root DIR ...]
  [--provider-externs-file JSON] [--prompt-externs-file JSON]
  [--imported-workflow-bundles-file JSON] [--command-boundaries-file JSON]
  [--state-dir DIR] [--run-ref-root DIR]
```

Historical grammar only: trial execution is retired. The CLI and
`run_trial_entry` SDK refuse with `workflow_execution_target_retired` before
execution/publication (CLI exit 2), rather than compiling or creating a trial
run/result. The historical `workflow_trial_run_result.v1` wire remains useful
for reading retained trial evidence; it does not admit new trials. ES/research
callers share this retirement, with no evaluated trial port. The current CLI
report keeps state-only trial rows with identity, kind and status and empty
input/output payloads; detailed trial budgets, score/ranking and verdict-join
rendering are withdrawn. Dashboard generic raw/debug inspection is separate
and does not inherit this redaction. The
[observability contract](observability.md#target-225-trial-observability) owns
the historical detail format and retained read-only boundary.

### Evaluated execution (target 2.35)

This contract applies to evaluated entries at 2.35/2.36, the admitted
bounded 2.37 surface, bounded 2.38 Agent Sessions and command-only confined
run-ref children, and target-2.39 procedure authoring and bounded phased provider
delivery. Procedure authoring itself changes no lifecycle or transport; the
[phased provider contract](providers.md#evaluated-phased-provider-delivery-target-239)
and [attempt-state contract](state.md#evaluated-phased-provider-attempts-target-239)
own the additive phased coordinator, memo commit/settlement and exact-attempt
recovery under the same profile. Use the [phased recipe](../docs/lisp_workflow_drafting_guide.md#authoring-phased-contract-delivery-target-239)
for deterministic public checks; paid-provider qualification remains unselected.
Neither extension changes confinement qualification. See the
[procedure guide](../docs/lisp_workflow_drafting_guide.md#procedure-contracts-at-target-239). The [confined-command recipe](../docs/lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only)
records host/image prerequisites; public confined providers remain closed. W3 changes
authoring, not command/provider IO or the public lifecycle; 2.37 registration
does not establish full parallel delivery. For Agent Sessions,
[PQ-1a](../docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md) records
deterministic proofs and bounded adapter smokes; the real-provider comparison
(PQ-1c) has not run and requires separate owner authorization.
See [versioning](versioning.md#version-gating-summary) for qualification limits.

An entry whose `:target-dsl` is `2.35` selects the evaluated route: `run`
builds the checked closed program, binds inputs and evaluates it on a
memo-backed run (`result_persistence_profile: evaluated_execution.v1`, state
schema `3.0`); `resume` and `invalidate` operate on that run; readers render
its derived view. The run contract is owned by
[State](state.md#evaluated-execution-persistence-profile-target-235) and the
command/provider requests by
[Step IO](io.md#evaluated-command-and-provider-io-target-235); this section
owns the public commands, their flags, the resume precedence and the exit
codes. Availability: implemented at target 2.35; Phase 3 is complete and delivered
at `06130a53` ([closeout report](../docs/reports/2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md)). Owners: `orchestrator/cli/main.py`,
`orchestrator/cli/commands/{run,resume,evaluated,invalidate,compile,report}.py`.
Evidence: `tests/test_workflow_evaluated_cli.py`,
`tests/test_workflow_lisp_closed_program_compile_cli.py`,
`tests/test_workflow_evaluated_resume_replay_boundary.py`,
`tests/test_workflow_evaluated_invalidate.py`,
`tests/test_workflow_evaluated_invalidate_smoke.py` and
`tests/test_workflow_lisp_target_evaluated_execution.py`. Targets through
2.34 are subject to the [retirement boundary](#executable-support-boundary).

```text
orchestrator compile WORKFLOW [--entry-workflow NAME] [--source-root DIR ...]
  [--provider-externs-file JSON] [--prompt-externs-file JSON]
  [--imported-workflow-bundles-file JSON] [--command-boundaries-file JSON]
  [--diagnostics-json]
orchestrator run WORKFLOW [the same frontend flags] [--input NAME=VALUE ...]
  [--input-file JSON] [--state-dir DIR] [--run-ref-root DIR] [--dry-run]
orchestrator resume RUN_ID [--state-dir DIR] [--run-ref-root DIR]
orchestrator invalidate RUN_ID IDENTITY [--state-dir DIR]
orchestrator report [--run-id RUN_ID] [--runs-root DIR] [--format md|json] [--output PATH]
orchestrator repl [WORKFLOW] [the same frontend flags] [--run-id RUN_ID] [--state-dir DIR]
```

- `repl` loads and inspects module declarations/types, launches its entry through public `run`, attaches
  read-only to an evaluated run and evaluates pure expressions over captured
  bindings; see [REPL commands and diagnostics](#workflow-lisp-repl-targets-235-and-236).
- `compile` writes `.orchestrate/build/<build key>/closed_program.json` and
  `manifest.json` (`schema_version: closed-program-build/1`, with
  `build_key`, `program_digest`, `representation`, `target`, `entry_workflow`,
  `sites`, absolute `source_path` and `source_roots`, and `artifact_paths`).
  The manifest is build metadata, not run authority and not a resume recipe.
  The flat-route export flags (`--emit-executable-ir`, `--emit-core-ast`,
  `--emit-runtime-plan`, `--emit-semantic-ir`, `--emit-source-map`,
  `--emit-debug-yaml`) refuse with `workflow_lisp_cli_input_unsupported`.
- `run` builds the same bundle (publishing the build directory), binds
  `--input` overrides over `--input-file` against the fresh program, takes the
  workspace lock, publishes the run authority under the run writer lock and
  evaluates. `--dry-run` builds (still publishing the build directory) and
  binds without a lock or a run root and exits `0`, `2` for a compile or
  binding error, or `1` for a missing `--input-file`. `--state-dir DIR` places
  the run at `DIR/RUN_ID` and records its relationship to the workspace as the
  header `result_root`; `--run-ref-root DIR`, or its default, is recorded as
  `run_ref_root`. Provider stdout and stderr are streamed to the process's
  own stdout and stderr while each provider runs, by default; `--quiet`
  suppresses that stream (for `run` and `resume`), and `--stream-output` is
  accepted without changing anything. A `print` operator in the program
  writes its JSON line to the same stdout during the attempt's own evaluation;
  `--quiet` does not affect it, and readers never print. Streaming does not change the bytes
  captured in the attempt's `stdout.txt` and `stderr.txt`, nor the result
  file transport. The route does not read `--on-error`, `--max-retries`,
  `--retry-delay`, `--step-summaries`, the `--summary-*` and
  `--live-agent-*` flags, `--clean-processed` or `--archive-processed`;
  `--backup-state` has no effect, and `--debug`, `--verbose` and
  `--log-level` affect logging only. The run's workflow
  outputs are the terminal value, as `{"__result__": value}` for a non-object
  value.
- `resume RUN_ID` recognizes the run by its header before any flat-route
  state check and performs the read-only preflight below under the workspace
  and run writer locks. `--force-restart` is refused with
  `evaluated_execution_unavailable`; `--repair` and the flat-route retry and
  observability flags are not read. An explicit `--run-ref-root` must be a
  canonical absolute path (a `..` or symlinked spelling refuses with
  `[resume_preflight_failed] --run-ref-root must be a canonical absolute path`,
  exit `2`) and must equal the recorded root. A completed run resumes to its
  recorded terminal with exit `0` and no write, however often it is repeated.
  - Target 2.38 confined-child amendment: a completed run that records a pending run-ref
    workspace-cleanup obligation retries that cleanup on resume, records the
    outcome and dispatches nothing; a completed run without one keeps the
    no-write rule above
    ([State](state.md#run-ref-confined-child-state-target-238)).
    For a valid completed run, resume exits `0` when no cleanup obligation
    is pending or all known obligations complete. If a cleanup retry leaves
    an obligation pending, resume exits `2` and emits
    `[run_ref_cleanup_pending]` with the existing coordinator identity,
    attempt and bounded reason, including the preserved private location
    when a replacement was moved there. The persisted terminal remains
    completed with its original value; cleanup failure neither appends a
    workflow failure nor alters parent commitment or settlement. The pending
    obligation survives for a later resume. Integrity and preflight refusals
    retain their existing codes and do not authorize mutation of invalid
    authority. These paths dispatch no child effect, start no holder and
    allocate no child. A completed run without pending cleanup retains the
    no-write rule.
    `report` projects pending obligations read-only and preserves the
    completed status, workflow outputs and run-level error of the terminal.
    Successfully reading and rendering a report exits `0` even when cleanup
    is pending; report never attempts cleanup. The pending projection is
    specified in [Observability](observability.md).
- `invalidate RUN_ID IDENTITY [--state-dir DIR]` (also
  `python -m orchestrator invalidate ...`) uses the same path resolution as
  `resume` (`.orchestrate/runs/RUN_ID`, or `DIR/RUN_ID`); unlike `resume`,
  every refusal, including a missing run directory or a symlinked
  `.orchestrate`, prints `[code] detail` and exits `2`. A run directory
  without any evaluated authority file (`run.json`, `closed_program.json`,
  `memo.jsonl`) that holds a flat-route `state.json` refuses with
  `workflow_execution_profile_retired`, exit `2`, before locking or writing. A
  `state.json` that carries the evaluated view hint (schema `3.0` or the
  profile) without the authority files is `memo_inconsistent`, as for
  readers. An authority file without `run.json` and a symlinked run
  directory are also `memo_inconsistent`. `IDENTITY` is one shell argument holding the exact canonical
  identity text that `report` shows, for example
  `'workflow:invalidate_public::run / writer'`, not a label, prefix, digest or
  filename. Under the run writer lock it validates stored authority and the
  complete journal prefix, then appends one synchronized `invalidated` range
  record cancelling the chosen active commit and every later active commit in
  journal order (rule C8 of the
  [design](../docs/design/workflow_lisp_evaluated_execution.md#85-explicit-continuation-after-a-divergence)).
  It compiles no source, compares no current inputs, resumes nothing, has no
  force, cascade or scope option, and does not narrow the suffix by value
  dependencies; a torn journal tail is truncated only after every refusal
  check passed. Success prints the appended record as one JSON line
  (`{"from_commit": <byte offset>, "record": "invalidated", "time": <seconds>}`)
  and exits `0`; a refusal prints `[code] detail` on stderr and exits `2`.
  Repeating the command after the record survived, including after a lost
  acknowledgment, reports `invalidate_not_committed` and leaves the run
  resumable with the whole suffix cancelled. A suffix containing a committed
  run reference or a committed agent turn refuses whole with
  `invalidate_coordinator_committed`; a suffix (by journal order of starts,
  including abandoned bootstrap attempts) containing an agent turn attempt that
  was dispatched, advanced its native session or is of uncertain outcome
  refuses `invalidate_agent_session_advanced`. A pending agent attempt in the
  suffix always refuses (resume first, so it is reconciled or bootstrapped).
  Only attempts started at or after the chosen commit are affected; the
  receipts required are those of such attempts closed `failed` with a
  non-dispatched code, and one that is unreadable is `memo_inconsistent`;
  unused allocations and proven-undispatched attempts invalidate normally.
  All checks precede tail repair or any write. A
  journal or view failure after the checks (`memo_*`, `view_write_failed`)
  also exits `2`; after `view_write_failed` the range record is already
  durable, which is the lost-acknowledgment case above. Invalidation cancels
  the committed suffix and retires pending starts in that journal suffix,
  while preserving attempt history. A newer uncommitted attempt still
  supplies its C4/§8.1 retry baseline and `must_not_repeat` restriction when
  its identity is reached again; pending starts before the anchor remain
  pending.
- Readers: `report`, `dashboard` and `monitor` recognize an evaluated run
  root and render its [derived view](state.md#derived-view-statejson)
  (`steps` keyed by identity, `current_step`, `next_effect`, `error`,
  `workflow_outputs`, and `interrupted` from writer-lock liveness). `report`
  previews a row as the `repr` of its committed value from the view;
  `dashboard` locates `stdout.txt`, `stderr.txt` and, for a provider,
  `prompt.txt` beside the row's `result_path`; `monitor` locates
  `stdout.txt` and `stderr.txt` only. `report` exits `1`
  with `memo_inconsistent` when the authority or journal is invalid. Readers
  never repair, resume or reconcile a run.

Example, from the public fixture of
`tests/test_workflow_evaluated_invalidate_smoke.py` (paths relative to its
workspace):

```bash
python -m orchestrator compile main.orc --entry-workflow main::run --source-root . \
  --provider-externs-file providers.json --prompt-externs-file prompts.json \
  --command-boundaries-file commands.json
python -m orchestrator run main.orc --entry-workflow main::run --source-root . \
  --provider-externs-file providers.json --prompt-externs-file prompts.json \
  --command-boundaries-file commands.json --input 'message=typed input'
python -m orchestrator resume "$run_id"
python -m orchestrator invalidate "$run_id" 'workflow:main::run / built'
python -m orchestrator resume "$run_id"
```

#### Resume preflight precedence

Resume refuses at the first failing step, with exit `2` and no change to
authority, memo, attempts or views, in this order:

1. The run root exists (otherwise exit `1`, "No run found"). Read-only profile
   selection rejects schema-2.1 historical headers or a run without evaluated
   authority with `workflow_execution_profile_retired`, before workspace/run
   locks. An evaluated journal/program without its header, malformed header or
   unknown profile/schema is `memo_inconsistent`. Only an admitted profile
   then acquires the workspace (`workspace_run_already_active`) and run writer
   (`run_already_active`) locks.
2. Header shape under those locks: `run.json` is present (a journal or program
   without it is `memo_inconsistent`), the profile/schema pair, the exact key set, the run
   id and the spelling of any present `resume_request`, `run_ref_root` and
   `result_root` (`memo_inconsistent`). A retired profile refuses with
   `workflow_execution_profile_retired`; any other pair is `memo_inconsistent`.
3. `resume_request` is present (`resume_request_missing`); a historical
   header without it stays readable and invalidatable.
4. Not `--force-restart` (`evaluated_execution_unavailable`).
5. An explicit `--run-ref-root` is a canonical absolute path (otherwise
   `resume_preflight_failed`) and equals the recorded `run_ref_root`
   (`resume_run_ref_root_changed`); only spellings that path normalization
   makes equal (a trailing separator, `.`, an interior `//`; a leading `//`
   is refused) count as the same root, and
   a historical header without the root accepts the flag without adopting it.
6. The selected run root's relationship to the resume workspace equals the
   recorded `result_root` (`resume_result_root_changed`), for every program,
   including one that reaches no result-path form; relocating the workspace
   with the run inside it, or an explicit `--state-dir` naming the same
   relationship, is accepted.
7. A fresh in-memory build from the recipe (source, ordered roots, entry and
   manifests resolved under the effective workspace; no build cache read or
   published): compile errors refuse; `resume_program_changed` when the
   fresh digest differs. Formatting and provenance-only changes build the
   same digest; `workflow_checksum` is not compared.
8. Fresh inputs: the recipe's `input_file` is read anew, `input_overrides`
   applied and the result bound against the fresh program; binding errors
   refuse; `resume_inputs_changed` when the digest differs.
9. Stored authority: the artifact's checked form and header digest (a
   stored command without argv transport is `memo_inconsistent` here; step
   7 normally refuses such a run first with `resume_program_changed`) and
   interpreter pins (`resume_interpreter_missing`; `interpreter_changed` is
   logged and execution continues on the recorded path).
10. Memo replay: reduce the journal (`memo_inconsistent`), replay the active
    committed prefix in journal order re-resolving every input
    (`effect_input_diverged` at the first divergence; `result_root_missing`
    at a reached result-path form of a header without `result_root`;
    `resume_run_ref_root_missing` at any reached run reference, committed or
    not, of a header without `run_ref_root`), and at the first uncommitted
    effect check the retry baseline (`effect_input_diverged` for changed
    implementation files, `lexical_restore_pending_effect_unsafe` for a
    `must_not_repeat` command; a pending provider start re-reads its C6
    sources in memory). An agent turn with a pending start is classified
    from its receipt and the native store, never by the retry baseline, and
    nothing is signalled: a live recorded process group is admitted and
    stopped under the writer lock before reconciliation; `recoverable`
    (adapter-confirmed native completion bound to the attempt, with a result
    file present for a first turn) enters result validation at the same ordinal
    without dispatch and commits only a valid result. A completed first turn
    with no result file takes the bootstrap path on its first explicit resume.
    A later completed turn enters validation even with no result file; a
    conclusively missing/invalid result closes
    `failed agent_turn_result_invalid` during continuation (exit `1`); a
    subsequent resume refuses that failure at preflight (exit `2`);
    `not_dispatched` (no `launching` receipt, or a stopped group and an
    adapter-proven unchanged predecessor head) closes the attempt `failed`
    and allocates the next one; `unresolved` refuses `agent_turn_unresolved`
    after the agent's first committed turn and takes the bootstrap path
    before it. Bootstrap is admitted at preflight without writing and executed
    under the writer lock before the next `started`: the old candidate's
    receipt becomes `abandoned` and `abandoned.json` is written, the attempt is
    closed `failed agent_bootstrap_restarted` if still pending (never twice
    after a crash), and `[agent_bootstrap_restarted]` is logged; a first turn
    whose latest attempt failed after dispatch (`provider_result_invalid`)
    restarts the same way. A later turn whose latest attempt closed
    `agent_turn_result_invalid` refuses with that code, before any
    native-head check.
11. Only then is a torn tail repaired (a failure there is still a refusal,
    exit `2`) and evaluation continued. A condition of step 10 that is first
    reached after continuation has committed new effects fails the run with
    exit `1` instead of `2`, keeping the earlier commits: `effect_input_diverged`
    and `lexical_restore_pending_effect_unsafe` stop without a terminal;
    `resume_run_ref_root_missing` and `result_root_missing` append a failed
    terminal where the journal permits one. The next resume refuses the same
    condition in replay with exit `2` without another terminal.

#### Diagnostics

Exit `2` is a refusal before execution; exit `1` is a run that executed and
failed, or stopped without a terminal where noted; exit `0` includes a resume
that returns the recorded terminal. `run` prints a publication-time refusal
as `Validation error: <message>` without a code; `resume` prints
`[<code>] <message>`, using `resume_preflight_failed` for a refusal that has
no code of its own; `invalidate` prints `[<code>] <detail>`.

| Code | Raised by | Exit | Effect on evidence |
| --- | --- | --- | --- |
| `closed_program_gap`, `compiled_workflow_source_required`, `compiled_workflow_snapshot_conflict`, `command_boundary_closure_missing`, `command_boundary_manifest_invalid`, `command_result_inputs_invalid` | `compile`; `run`; the fresh build of `resume` | 2 | None; `run` creates no run root |
| `workflow_lisp_cli_input_unsupported` | `compile` with a flat-route export flag | 2 | None |
| Workflow input binding failure (a missing, unknown, mistyped or non-finite input): no named code; `run` and `--dry-run` print `Validation error: Workflow input binding failed`, `resume` prints `[resume_preflight_failed] Workflow input binding failed`; a `: <detail>` suffix follows only for a conversion or non-finite failure, a missing or unknown input prints the bare message | `run`; the fresh inputs of `resume` | 2 | None; `run` creates no run root |
| `resume_preflight_failed` | `resume` refusals without a code of their own: a non-canonical `--run-ref-root`, an input binding failure, an unreadable recipe input file | 2 | None |
| `command_transport_required`, `command_interpreter_missing` | `run` publication (a checked command without argv transport; a bare interpreter that does not resolve on `PATH` or is not launchable), printed as `Validation error: …` | 2 | None; no run root |
| `reserved_run_root_changed` | any writer whose locked run root no longer matches its path: publication, execution, `resume` preflight, `invalidate` | publication and execution 1; `resume` preflight and `invalidate` 2 | Nothing written into the substitute root |
| `memo_inconsistent` | `resume` preflight (including stored authority without command transport); `invalidate`; readers; during execution when evidence is unsettled at a start or at `halt` | 2 (`report`: 1; during execution 1 without a terminal) | None; readers report no outputs |
| `resume_request_missing` | `resume` | 2 | None |
| `workflow_execution_target_retired` | `compile`, `run`, `run --dry-run` on an entry through 2.34; retired trial CLI/SDK; old path child before child publication; flat/staged child execution (`flat_execution_retired` / `staged_execution_retired`) | 2 at public admission; reached run-reference failure follows the evaluated parent's failure contract | No build/run/child publication at admission; a reached evaluated parent retains its own attempt evidence |
| `workflow_execution_profile_retired` | `resume` including restart/repair, `invalidate` of a retired profile; `input answer`/`cancel` | 2 | None; before locks or writes |
| `prompt_execution_retired` | Every `prompt run` and `prompt import` mode | 2 | None; before inputs, inference, scaffold/run/session writes or effects |
| `workflow_explain_retired` | `explain`, independent of entry target or export flags | 2 | None; before source/build/export reads or writes |
| `evaluated_execution_unavailable` | `resume --force-restart` on an admitted evaluated run | 2 | None |
| `resume_run_ref_root_changed`, `resume_result_root_changed` | `resume` header/option preflight | 2 | None |
| `resume_program_changed`, `resume_inputs_changed` | `resume` fresh build and inputs | 2 | None |
| `resume_interpreter_missing` | `resume` stored authority | 2 | None |
| `interpreter_changed` | `resume` | diagnostic | Logged; execution continues on the pinned path |
| `effect_input_diverged` | `resume` replay of a committed effect or retry baseline; a later reached effect after continuation | 2; later 1 | Preflight: none. Later: stops without a terminal; prior commits kept |
| `lexical_restore_pending_effect_unsafe` | `resume` at an uncommitted `must_not_repeat` command | 2; later 1 | As above; the pending start is preserved |
| `resume_run_ref_root_missing` | a run reference reached in replay; reached after continuation | 2; later 1 | Preflight: none. Later: failed terminal where the journal permits; prior commits kept |
| `result_root_missing` | a result-path form reached in replay (header without `result_root`); reached after continuation | 2; later 1 | As above; read-only replay stops at the form with no error row |
| `run_already_active`, `workspace_run_already_active` | `run`, `resume` | 2 | None |
| `memo_busy` | `invalidate` | 2 | None |
| `invalidate_not_committed`, `invalidate_coordinator_committed` | `invalidate` | 2 | None |
| `agent_session_unavailable`, `agent_session_diverged`, `agent_policy_mismatch` | a reached agent turn (target 2.38) before its `started` and dispatch of a new turn | 1 during execution; 2 in `resume` preflight | No dispatch; failed terminal where the journal permits |
| `agent_turn_unresolved` | a dispatched agent turn attempt whose completion or result cannot be established | 1 during execution; 2 in `resume` preflight | The `started` stays pending: no `failed` row and no terminal; `resume` reconciles the attempt |
| `agent_turn_result_invalid` | a later agent turn that completed natively with a missing/invalid result | 1 when first classified (`run` or `resume` continuation); 2 on subsequent `resume` preflight | `failed` row with `exit_info {}` and no `violations`; public validation diagnostic contains only logical agent identity and safe code; the attempt files kept |
| `agent_bootstrap_restarted` | `resume` abandoning a first-turn candidate | diagnostic | Logged; the abandoned attempt's `failed` row carries this code with `exit_info {abandoned_attempt, locator}` |
| `invalidate_agent_session_advanced` | `invalidate` over an agent turn attempt whose native session advanced or may have advanced | 2 | None written |
| `undefined_variables`, `effect_input_invalid` | a reached command's template or input document before its `started` | 1; 2 in resume preflight at a command with a retry baseline | No `started`, directory or dispatch; failed terminal where the journal permits. Against an active commit the same condition is `effect_input_diverged`; with only a prior start the code is kept |
| `command_closure_unreadable` | a reached command's closure before a first attempt (missing, unreadable, cyclic or unsupported entry), or a C4 destination overlap (reason `runtime destination overlaps command closure`) | 1 | No `started`, directory or dispatch; failed terminal where the journal permits. Against a prior start or commit a resolution failure is `effect_input_diverged`; a destination overlap keeps this code |
| `effect_attempt_path_exists`, `effect_attempt_allocation_failed` | attempt allocation after `started` | 1 | `failed` row with `exit_info {errno}`; the existing directory is preserved; failed terminal where permitted |
| `command_exit_nonzero`, `command_result_missing`, `command_result_unreadable`, `command_result_contract`, `command_result_projection`, `command_module_origin_mismatch`, `command_closure_written`, `provider_preparation_failed`, `provider_exit_nonzero`, `provider_timeout`, `provider_result_missing`, `provider_result_unreadable`, `provider_result_invalid`, `provider_result_contract`, `provider_result_projection` | a dispatched attempt (no timeout is applied to an evaluated command, so `command_timeout` is not raised on this route) | 1 | `failed` row (`exit_info` where [State](state.md#memo-records) gives one; `violations` for ordinary-provider `provider_result_invalid`; a first Agent turn's `provider_result_invalid` instead has `exit_info {}`, no `violations` and only logical agent identity/safe code in its public validation diagnostic) and the attempt files kept; failed terminal where permitted; `resume` retries at the next ordinal under the class-specific rules above |
| `evaluated_execution_failed` | a command `result.json` that fails its declared contract (`failed` row with `exit_info {}` and `violations`); any other failure during evaluation that carries no code of its own; the `failed` code of a run reference that fails before its child | 1 | As above |
| `pure_expr_*` (a pure operator or refinement failure, for example `pure_expr_division_by_zero`, or `pure_expr_operand_type_mismatch` at a result-path form whose run root is not under `.orchestrate/runs`), `provider_result_path_missing` (a result-path form whose producer is not in scope) | `run`; continuation of `resume` (reached in resume replay it is a refusal, exit 2) | 1 | Failed terminal carrying that code; no `failed` row, since no effect is involved; read-only replay reports the run as it stands |
| `view_write_failed` | derived-view replacement after an append | `run`/`resume` 1; `invalidate` 2 | The appended record stays authority; no `failed` row or terminal; readers reconstruct the view |
| `memo_torn_tail`, `memo_write_failed`, `memo_sync_failed`, `memo_changed` | journal append or tail repair | 1 during execution; 2 in `resume` tail repair and in `invalidate` | No partial record is authority; a complete row that survived a failed sync still consumes its ordinal |
| (no code) | an I/O failure during initial authority publication | 1 | Nothing dispatched; printed as `Unexpected error` with the errno (a named code is a recorded follow-up) |
| `effect_rerun` | `resume` retrying an uncommitted attempt | diagnostic | Logged with the earlier attempt ordinals |
| `parallel_workspace_shared` | a later release | — | Not raised |

<a id="workflow-lisp-repl-targets-235-and-236"></a>

### Workflow Lisp REPL (targets 2.35–2.39)

`repl` loads an evaluated Workflow Lisp module, inspects its declarations and
expression types, attaches to a checked run and accepts pure expressions in
the captured lexical environment. It uses the
ordinary frontend and closed evaluator; it adds no source definitions,
operator semantics or persistence format. Owners are
`orchestrator/cli/commands/repl.py`, `orchestrator/workflow_lisp/repl_expr.py`,
`orchestrator/workflow_lisp/repl_inspect.py`
and `orchestrator/workflow/evaluated/capture.py`; behavioral integration coverage
is `tests/test_workflow_evaluated_repl.py` and
`tests/test_workflow_evaluated_repl_introspection.py`. See the
[REPL design](../docs/design/workflow_lisp_repl.md),
[introspection design](../docs/design/workflow_lisp_repl_introspection.md) and
[author recipe](../docs/lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl).

```text
orchestrator repl [WORKFLOW] [--entry-workflow NAME] [--source-root DIR ...]
  [--provider-externs-file JSON] [--prompt-externs-file JSON]
  [--imported-workflow-bundles-file JSON] [--command-boundaries-file JSON]
  [--run-id RUN_ID] [--state-dir DIR]
:load PATH [the same frontend flags]
:run [--input NAME=VALUE ...] [--input-file JSON] [--state-dir DIR] [--run-ref-root DIR]
:attach RUN_ID
:bindings
:result
:where [NAME]
:browse
:info NAME
:source NAME
:type EXPR
:help
:quit
```

The frontend flags have the same meanings as `compile` and `run`. Startup
loads `WORKFLOW` before attaching `--run-id`. `:load` publishes the ordinary
closed-program build bundle; failed compilation reports ordinary rendered
diagnostics and retains the previous module. `:run` requires a loaded module,
uses public run option/input parsing and `run_workflow`, and forwards the
session state directory unless the command overrides it. It attaches the
returned run root after public execution releases its writer locks. This
explicit command has ordinary run effects, lock ownership and evidence writes.

`:attach` resolves `RUN_ID` under `.orchestrate/runs`, or the session's
`--state-dir`, and reads checked `run.json`, `closed_program.json` and one
`memo.jsonl` prefix through `WorkspaceFiles`. It uses stored bound inputs and
ordinary memo reduction, replay commit checks and completed-terminal validation.
It takes no writer lock, launches no effects and neither repairs/appends the
memo nor publishes a derived view. `state.json` is not authority. Attachment
captures a prefix, not a live subscription to a running writer.

A loaded module's program digest must match the run. A mismatch reports
`resume_program_changed` and clears attachment. Without a loaded module,
attachment rebuilds the durable `resume_request` in memory using the ordinary
resume build request and `prepare_closed_program_bundle`; no build artifact
or cache is published. Missing recipe reports `resume_request_missing`, and
changed fresh program reports `resume_program_changed`. Fresh input files are
not rebound for inspection. A matching explicitly loaded module allows reading
a historical run without a recipe. Ordinary checked-authority, memo and compile
errors retain their codes.

The four module inspection commands require a loaded or recipe-reconstructed
module, and work without running it or attaching a run:

| Command | Output and scope |
| --- | --- |
| `:browse` | Module name, target, selected entry, loaded/reconstructed source label and per-file snapshot revisions, imports/aliases, then visible names grouped by kind. |
| `:info NAME` | Every matching declaration's kind, accepted spellings, declaring module and source location, followed by its known contract. |
| `:source NAME` | Every matching exact authored declaration form, labelled with kind, module, path/location and loaded/reconstructed snapshot revision. |
| `:type EXPR` | Two stdout lines: `type: <rendered type>`, then `effects: <rendered inferred effect set>` when complete. At 2.39 an unresolved generic call instead prints `effects: incomplete (<unresolved names>); known <rendered known effect set>`. Ordinary frontend analysis only; no authored-restriction display, lowering or evaluation. |

Coverage is named types, functions, procedures, workflows, prompts and externs.
`:info` shows record fields; union type parameters and variants/fields; enum
members; path kind, `under` constraint and existence requirement; builtin type identity; callable
parameter/return types and available inferred effects; and prompt slots in
declaration order with kind, refinement, output role and return type. At 2.39,
procedure `:info` separates `restriction: omitted` or the authored checked
restriction from `inferred effects`, and reports `effect status: complete` or
`effect status: incomplete (<unresolved names>)`. This is declaration inspection;
`:type` reports expression inference without the authored restriction. Externs
show declared provider/prompt kind and unavailable contract facts; no manifest
payload, provider arguments, credentials or external prompt-file contents are
displayed. `:source` on a `defprompt` includes its authored template, rather
than a rendered invocation.

Kinds/names sort deterministically; contract fields, variants, parameters and
slots keep declaration order. Aliases of one canonical identity share a row
or section. A spelling present in distinct compiler namespaces returns every
match labelled by kind; same-namespace ambiguity retains the compiler refusal.
Imports and aliases follow the entry module's actual compiler resolution,
including qualified spellings available beyond an unqualified `:only`
selection. This is neither project-wide discovery nor implicit module loading.
Help and browse state the exclusions: macros, schemas, resources, transitions,
operator documentation, applied generic type syntax as `NAME`, generated local
definitions and specializations. Builtin named types are inspectable; missing
facts are explicitly unavailable.

`:info` and `:source` query module declarations independently of captured
values. A run-local value belongs in `:bindings` or `:type EXPR`. Type queries
use supported captured lexical type refs when attached, with ordinary shadowing;
without attachment, run-local names retain `name_unknown`. Effectful type
queries report inferred effects without provider dispatch or run creation.
Ordinary target-dependent frontend diagnostics still apply, including constant
division-by-zero diagnostics; a runtime-only failure is never evaluated by
`:type`. Synthesized runtime variant-case values supply no additional proof.

`:browse` takes no arguments. `:info`/`:source` require exactly one
S-expression reader symbol, rejecting strings, lists and additional datums
with `repl_command_invalid`. `:type` sends the untouched command remainder to
the ordinary reader, preserving Lisp strings, escapes and spaces; zero or
multiple expressions report `repl_expression_arity`, and malformed syntax keeps
the ordinary reader diagnostic. `:load`/`:run` retain shell-style parsing.

Source comes from the accepted compiler read snapshot, with CRLF/CR normalized
to LF as the reader does. It includes the full declaration and its internal
comments; surrounding comments outside the form are excluded. Inspection
performs no fresh source or extern-payload reads. Editing/deleting files after
load leaves the retained source unchanged; successful load replaces source and
context together, and failed load preserves the previous module/snapshot and
compatible attachment. Builtins, externs or definitions without provable exact
authored spans refuse `repl_source_unavailable`; there is no filesystem fallback.
All source matches are validated before output: any unavailable match refuses
with all unavailable matches named and no partial source.

Explicit load labels source `loaded snapshot`; recipe-only attachment labels it
`reconstructed module source`. A matching program digest proves semantic
compatibility, and does not prove that reconstructed comments/formatting are
the historical text of the run. There is no persistent source archive.

Expressions are one datum per input line and require attachment. Lexical
shadowing chooses the innermost binding; compiler names beginning with `%`
are hidden. Ordinary field/list operations and pure module `defun`/`defproc`
calls are admitted. Equality `=` / `!=` retains the
[ordinary frontend §10.2](../docs/design/workflow_lisp_frontend_specification.md#102-closed-pure-expression-surface)
contract for supported scalars and same-type enums; lists do not gain deep
equality semantics. Use the ordinary `list/empty?` operator to test list
emptiness. The frontend rejects transitive effects; a recursive
lowered-body guard and the evaluator with no effect callback also refuse
`perform`. Synthesized runtime variant-case bindings may be displayed but do
not supply frontend proof for expression evaluation. The session accepts no
multiline expressions, definitions, interactive effects, resume command,
module editing, completion/history or flat-profile attachment through 2.34.

`:bindings` shows visible names/types in outer-frame order, capture position
and run identity. `:result` prints the completed entry result with the entry's
return type, including completion through a loop's `done`, or `repl_no_result`
when stopped or failed. Its value is the ordinary evaluator's final return,
not an incidental operand or loop-seed completion. `:where NAME` prints one
stdout line: the absolute path of the result file the named binding was read
from, under the attached run root; `:where` alone does the same for the entry
result. A binding that was computed rather than performed reports
`repl_no_result_file`; an unknown name reports `name_unknown`. Expression and result
values use two stdout lines: canonical UTF-8 compact sorted-key JSON, then
exactly `: <rendered type>`. REPL and runtime errors print `[code] detail`
on stderr. Frontend errors retain ordinary localized `render_diagnostic`
output, including diagnostic code and `kind`/`form` context. A prompt and
readline are enabled only for a TTY; piped input receives no prompt.

EOF and `:quit` exit `0`. A startup load/attach refusal exits `2`; an unexpected
failure exits `1`. Expected command/expression errors keep the session usable
and eventual normal EOF/quit still exits `0`. Failed ordinary commands retain
compatible session state; digest mismatch leaves it detached. Read-only startup,
attachment, module inspection/type queries, bindings, result and pure/refused expressions leave run authority,
memo, views and attempt evidence byte-identical; `:load` can publish only build
artifacts. `:run` remains the explicit exception using public execution.

| Diagnostic | Condition | Session/startup behavior | Run evidence |
| --- | --- | --- | --- |
| `repl_effect_refused` | Entered expression or called procedure has effects, or a lowered/evaluated `perform` is reached | Session continues | None |
| `repl_run_not_found` | Requested run root does not exist | Session continues; startup exits 2 | None |
| `repl_profile_unsupported` | Requested run uses the flat profile | Session continues; startup exits 2 | None |
| `repl_not_attached` | Expression, `:bindings`, `:result` or `:where` without an attached run | Session continues | None |
| `repl_module_required` | `:run`, `:browse`, `:info`, `:source` or `:type` without a loaded module | Session continues | None |
| `repl_command_invalid` | Invalid command arguments; module-name queries require exactly one reader symbol | Session continues | None |
| `repl_expression_arity` | Expression line or `:type` remainder does not contain exactly one datum | Session continues | None |
| `repl_name_unknown` | No matching supported module declaration; directs values to `:type`/`:bindings` | Session continues | None |
| `repl_source_unavailable` | Any source match lacks a validated exact authored snapshot/span | Session continues; no partial source | None |
| `repl_no_result` | Attached replay has no halted entry result | Session continues | None |
| `repl_no_result_file` | `:where` names a computed binding or an entry result that no effect produced | Session continues | None |
| `repl_module_context_missing` | Module call or inspection needs unavailable transient compiler facts | Session continues | None |

Reused `name_unknown`, `resume_program_changed`, `resume_request_missing`,
`memo_inconsistent` and ordinary frontend/value diagnostics retain their
codes and the appropriate rendering above; session errors continue, startup
errors exit `2`, with no inspection evidence writes. A public `:run` failure retains ordinary run
behavior and any evidence that public execution legitimately wrote.

### Extended CLI Options

```bash
# Debug and observability
--debug                 # Enable debug logging
--stream-output         # Stream provider stdout/stderr live without full debug side effects
--progress              # Show real-time progress (post-MVP)
--trace                 # Include trace IDs in logs (post-MVP)
--dry-run               # Validate without execution
--step-summaries
--summary-mode async|sync
--summary-provider <name>
--summary-timeout-sec <n>        # Default: 300
--summary-max-input-chars <n>
--summary-profile basic|phase-performance

# State management
--force-restart         # Refused for evaluated runs; retired profiles also refuse
--repair                # No effect on evaluated recovery; retired profiles refuse
--backup-state          # No effect on evaluated runs
--state-dir <path>      # Override default .orchestrate/runs

# Workflow signatures (v2.1+)
--input name=value      # Bind one workflow input
--input-file <path>     # Bind workflow inputs from one JSON object file

# Error handling
--on-error stop|continue|interactive
--max-retries <n>
--retry-delay <ms>

# Output control
--quiet
--verbose
--json                  # Optional/post-MVP
--log-level debug|info|warn|error
```

### Planned Environment Defaults

The following legacy proposal is not implemented. Setting these variables
does not change run location, logging, or retention. Use the supported flags
listed above; these names do not imply an automatic cleanup policy.

```bash
ORCHESTRATE_DEBUG=1
ORCHESTRATE_STATE_DIR=/tmp/runs
ORCHESTRATE_LOG_LEVEL=debug
ORCHESTRATE_KEEP_RUNS=30
```

Cross-platform note: Examples use POSIX shell utilities (`bash`, `find`, `mv`, `test`). On Windows, use WSL or adapt to PowerShell equivalents.
