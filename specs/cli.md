# CLI Contract (Normative)

## Workspace execution ownership

Only one run may execute in a workspace at a time. `run` and `resume`
(including `--force-restart`) acquire a workspace lock before compilation or
execution-state mutation. A competing invocation is refused with
`workspace_run_already_active`, naming the active run, and `run`, `resume` and
`trial` exit 2. Exit 2 means the request was refused before execution; exit 1
stays the status of a workflow that ran and failed. Exit 2 is also the status
of a compile or validation error, so a caller that must tell those apart reads
the code. Changing `--state-dir` does not bypass this rule. The trial SDK/CLI
uses the same workspace lock; nested workflow calls belong to their root run
and do not acquire it again.
Run-ref children own their separate clone workspace. `prompt run` can prepare
or reserve its scaffold before entering the ordinary `run` owner, but cannot
execute a provider while another run owns the workspace. The lock is not a
transaction over scaffold authoring or reservation. Commands that are not
runs take no workspace lock: `prompt resume` (with `--in-place` it runs a
provider in the workspace), `input answer|cancel`, `invalidate` (it takes
only the run's writer lock), `report` and `dashboard`. A target-2.35
evaluated `run` or `resume` takes the same workspace and run writer locks
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

A `run`, `resume`, or `trial` started from inside an active run (by one of its
command steps or providers) in that run's workspace is a competing invocation
and is refused the same way; only nested workflow calls belong to the root run.
A run that supervises another run therefore uses its own workspace: it reads
the other run's workspace by path and starts `resume` or `run` for it with that
workspace as the working directory.

- Commands
  - `orchestrate run <workflow.orc> [--context k=v ...] [--context-file path] [--input name=value ...] [--input-file path] [--clean-processed] [--archive-processed <dst>]`
    - `--dry-run` validates the workflow and may emit advisory warnings that do not change the exit code. A pure-result replay-index failure is an error only when the compiled structure guarantees that the call is reached; failures along a path under a branch, match arm, or loop body are warnings. Conditions are not evaluated, and a real run is refused if it reaches the call.
  - `orchestrate resume <run_id>`
    - If persisted authoritative state proves an exact interrupted in-flight
      ordinary, session, supervision, peer-group, phased, or adjudicated
      provider visit, resume preserves completed-boundary reuse, discards only
      the partial visit authority, emits
      `provider_attempt_interrupted_rerun` (or the adjudication-specific
      `adjudication_state_mismatch_rerun`), and re-enters normal execution with
      fresh identities. Force restart is not required.
    - Missing, malformed, ambiguous, checksum-incompatible, or otherwise
      unprovable recovery state still fails before provider launch.
    - A durable host request that is `pending` keeps the run suspended without
      entering the execution prologue. An `answered` request is consumed only
      after ordinary source, scope, node, visit, and reply validation; a
      consumed reply uses the existing completed-effect recovery policy or
      fails closed. Resume never creates a replacement question automatically.
  - `orchestrate input get <run_id> [--state-dir <runs-root>]`
    - Prints the current root host-request record. It does not resume or
      mutate execution.
  - `orchestrate input answer <run_id> <request_id> --text <text> [--state-dir <runs-root>]`
    - Validates and records one `ANSWERED` reply under the existing root writer
      lock. Empty text is valid. It does not execute or resume the workflow.
  - `orchestrate input cancel <run_id> <request_id> [--state-dir <runs-root>]`
    - Validates and records the `CANCELLED` reply under the same lock. It does
      not execute or resume the workflow.
    - Answer/cancel are idempotent only for an identical reply to the latest
      request; conflicting, stale, or overlapping submissions fail without
      replacing persisted data. They preserve the original bound inputs and
      recorded launch arguments.
    - These are thin clients of the durable host-input API. They apply only to
      a target-2.32 run carrying a request record; they do not parse state,
      acquire an alternate lock, or resume execution themselves.
    - Each successful input command prints the complete current request record
      as JSON and exits 0. Missing/invalid requests or submission conflicts
      exit 2; they never launch a provider.
  - `orchestrate report [--run-id <id>] [--runs-root <dir>] [--format md|json] [--output <path>]`
    - Report output may include advisory lint warnings (`lint.warnings[]` in JSON or an appendix in Markdown); warnings remain informational only.
    - Report output may include active runtime fields derived from executor sessions, including `run.active_runtime_ms`, `run.active_runtime`, `run.executor_session_count`, and `run.excluded_suspended_ms`. These fields exclude suspended gaps between executor processes and are informational only.
    - Report output may surface provider-session metadata paths and bounded
      interrupted-rerun diagnostic context; partial provider evidence remains
      non-authoritative.
  - `orchestrate prompt run (--prompt TEXT | --prompt-file PATH) --provider (omp|omp_no_tools|omp_conf|omp_unrestricted_workspace) [--conf PATH] [--model MODEL] [--returns JSON | --output TEXT]`
    - Generation requires exactly one prompt source and one public provider.
      `--conf` is required only for `omp_conf`. `--returns` supplies the exact
      semantic contract; `--output` is mutually exclusive and performs one
      internal `omp_conf_inference` call, so ambient providers reject it.
    - The command captures all source inputs before inference or destination
      creation, publishes or reuses one content-addressed target-2.27 scaffold,
      executes its ordinary compiled `run.orc`, and prints one success summary
      naming the run and generated scaffold. Existing mismatched occupants,
      source drift, and malformed or semantically invalid inferred contracts
      fail without replacement.
  - `orchestrate prompt run --scaffold PATH`
    - Rerun accepts only a fully verified scaffold root and is mutually
      exclusive with every generation flag. It executes a run-owned private
      snapshot; mutable generated files are never the execution authority.
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
    - Import resolves one exact linked active primary journal, verifies the
      full continuation chain and source scaffold/run evidence, extracts only
      authored user-message content, and then uses the ordinary prompt
      generation path. Without `--reuse-run-contract`, the caller supplies the
      new provider/contract flags. With it, provider, model, semantic contract,
      conf, and composed prompt bytes come only from the fully verified source
      scaffold; incompatible flags reject.
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
  - Runtime observability: `--step-summaries`, `--summary-mode async|sync`, `--summary-provider <name>`, `--summary-timeout-sec <n>`, `--summary-max-input-chars <n>`, `--summary-profile basic|phase-performance`, `--live-agent-notes`, `--live-agent-note-provider <name>`, `--live-agent-note-interval-sec <n>`, `--live-agent-note-timeout-sec <n>`, `--live-agent-note-max-tail-chars <n>`
    - `--summary-profile phase-performance` enables advisory provider-step and phase-boundary summaries with performance judgments. It implies step summaries if `--step-summaries` was not otherwise provided.
    - `--live-agent-notes` enables advisory live notes from bounded tmux pane tails, using `claude_haiku_summary` by default. Provider-session transport may be used as a fallback when tmux pane capture is unavailable. It implies step summaries if `--step-summaries` was not otherwise provided.
  - `--force-restart`, `--repair`, `--backup-state`, `--state-dir <path>`
    (`--force-restart` is refused and `--repair` is not read for a
    target-2.35 evaluated run; see [Evaluated execution](#evaluated-execution-target-235))
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
# Run a Workflow Lisp workflow from the beginning
orchestrate run workflows/examples/cycle_guard_demo.orc \
  --entry-workflow cycle-guard-demo \
  --source-root workflows/examples \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/cycle_guard_demo.commands.json \
  --input terminal_status=READY \
  --input guard_cycles=0

# Resume failed/interrupted run
orchestrate resume <run_id>

# Render status report for latest run
orchestrate report --format md

# Serve local dashboard for one or more explicit workspaces
orchestrate dashboard --workspace "$(pwd)" --host 127.0.0.1 --port 8765

# Monitor configured workspaces once without sending email
orchestrator monitor --config ~/.config/orchestrator/monitor.json --once --dry-run

# Validate the same Workflow Lisp source without executing
orchestrate run workflows/examples/cycle_guard_demo.orc \
  --entry-workflow cycle-guard-demo \
  --source-root workflows/examples \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/cycle_guard_demo.commands.json \
  --input terminal_status=READY \
  --input guard_cycles=0 \
  --dry-run

# Execute single step (optional/post-MVP)
orchestrate run-step <step_name> --workflow workflows/examples/cycle_guard_demo.orc

# Watch for changes and re-run (optional/post-MVP)
orchestrate watch workflows/examples/cycle_guard_demo.orc
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

The public command compiles the selected entry with the ordinary full compiler
and runs it with the ordinary executor. The entry must target DSL `2.25` and
its terminal public result must be the exact compiler-owned trial result.
Inputs bind through `--input` (repeatable) or `--input-file`; provide source
roots and extern manifests required by that workflow. Raw executable configs,
non-trial terminal results, other targets, and privileged bypasses are refused.

The command prints one closed `workflow_trial_run_result.v1` JSON record. It
contains the run ID and terminal status; completed results also contain the
verdict digest and path, while failed results contain a bounded failure
diagnostic. Exit `0` means completed, `1` means the trial ran and failed, and
`2` means validation or admission refused before execution. As elsewhere, exit
`2` alone does not distinguish compile errors from other refusals; read the
diagnostic code.

`--run-ref-root` sets the canonical absolute child-workspace root. When
omitted, it defaults to `~/.local/state/orchestrator/run-ref`. An explicit
value must already be canonical and absolute, and resume must use the root
bound to the persisted run. Trial has no dry-run mode.

### Evaluated execution (target 2.35)

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
2.34 keep the flat route, and every flag below keeps its meaning there.

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
```

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
  `run_ref_root`. The route does not read `--on-error`, `--max-retries`,
  `--retry-delay`, `--stream-output`, `--step-summaries`, the `--summary-*` and
  `--live-agent-*` flags, `--clean-processed` or `--archive-processed`;
  `--backup-state` has no effect, and `--debug`, `--quiet`, `--verbose` and
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
- `invalidate RUN_ID IDENTITY [--state-dir DIR]` (also
  `python -m orchestrator invalidate ...`) uses the same path resolution as
  `resume` (`.orchestrate/runs/RUN_ID`, or `DIR/RUN_ID`); unlike `resume`,
  every refusal, including a missing run directory or a symlinked
  `.orchestrate`, prints `[code] detail` and exits `2`. A run directory
  without any evaluated authority file (`run.json`, `closed_program.json`,
  `memo.jsonl`) that holds a flat-route `state.json` refuses with
  `invalidate_profile_unsupported`, exit `2`, nothing written. A
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
  run reference refuses whole with `invalidate_coordinator_committed`. A
  journal or view failure after the checks (`memo_*`, `view_write_failed`)
  also exits `2`; after `view_write_failed` the range record is already
  durable, which is the lost-acknowledgment case above. Invalidation cancels
  commits only: a newer uncommitted attempt whose closure changed is still
  refused on resume by C4.
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

1. The run root exists (otherwise exit `1`, "No run found"); the workspace
   lock (`workspace_run_already_active`) and the run writer lock
   (`run_already_active`) are acquired.
2. Header shape: `run.json` is present (a journal or program without it is
   `memo_inconsistent`), the profile/schema pair, the exact key set, the run
   id and the spelling of any present `resume_request`, `run_ref_root` and
   `result_root` (`memo_inconsistent`). A schema-2.1 header selects the flat
   route instead; any other pair is `memo_inconsistent`.
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
    sources in memory).
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
| `evaluated_execution_unavailable` | `resume --force-restart` on an evaluated run, and every flat-route build or run of a 2.35 entry: `resume` of a schema-2.1 run whose source targets 2.35; `run` whose compiled snapshot targets 2.35 after the early target read; `explain` and `trial` on a 2.35 entry; a target ≤2.34 parent whose path child targets 2.35 (reason `flat_execution_unavailable`; the parent run fails) | 2 | None on the evaluated route; a legacy parent records its failed state |
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
| `invalidate_profile_unsupported`, `invalidate_not_committed`, `invalidate_coordinator_committed` | `invalidate` | 2 | None |
| `undefined_variables`, `effect_input_invalid` | a reached command's template or input document before its `started` | 1; 2 in resume preflight at a command with a retry baseline | No `started`, directory or dispatch; failed terminal where the journal permits. Against an active commit the same condition is `effect_input_diverged`; with only a prior start the code is kept |
| `command_closure_unreadable` | a reached command's closure before a first attempt (missing, unreadable, cyclic or unsupported entry), or a C4 destination overlap (reason `runtime destination overlaps command closure`) | 1 | No `started`, directory or dispatch; failed terminal where the journal permits. Against a prior start or commit a resolution failure is `effect_input_diverged`; a destination overlap keeps this code |
| `effect_attempt_path_exists`, `effect_attempt_allocation_failed` | attempt allocation after `started` | 1 | `failed` row with `exit_info {errno}`; the existing directory is preserved; failed terminal where permitted |
| `command_exit_nonzero`, `command_result_missing`, `command_result_unreadable`, `command_result_contract`, `command_result_projection`, `command_module_origin_mismatch`, `command_closure_written`, `provider_preparation_failed`, `provider_exit_nonzero`, `provider_timeout`, `provider_result_missing`, `provider_result_unreadable`, `provider_result_invalid`, `provider_result_contract`, `provider_result_projection` | a dispatched attempt (no timeout is applied to an evaluated command, so `command_timeout` is not raised on this route) | 1 | `failed` row (`exit_info` where [State](state.md#memo-records) gives one; `violations` for `provider_result_invalid`) and the attempt files kept; failed terminal where permitted; `resume` retries at the next ordinal |
| `evaluated_execution_failed` | a command `result.json` that fails its declared contract (`failed` row with `exit_info {}` and `violations`); any other failure during evaluation that carries no code of its own; the `failed` code of a run reference that fails before its child | 1 | As above |
| `pure_expr_*` (a pure operator or refinement failure, for example `pure_expr_division_by_zero`, or `pure_expr_operand_type_mismatch` at a result-path form whose run root is not under `.orchestrate/runs`), `provider_result_path_missing` (a result-path form whose producer is not in scope) | `run`; continuation of `resume` (reached in resume replay it is a refusal, exit 2) | 1 | Failed terminal carrying that code; no `failed` row, since no effect is involved; read-only replay reports the run as it stands |
| `view_write_failed` | derived-view replacement after an append | `run`/`resume` 1; `invalidate` 2 | The appended record stays authority; no `failed` row or terminal; readers reconstruct the view |
| `memo_torn_tail`, `memo_write_failed`, `memo_sync_failed`, `memo_changed` | journal append or tail repair | 1 during execution; 2 in `resume` tail repair and in `invalidate` | No partial record is authority; a complete row that survived a failed sync still consumes its ordinal |
| (no code) | an I/O failure during initial authority publication | 1 | Nothing dispatched; printed as `Unexpected error` with the errno (a named code is a recorded follow-up) |
| `effect_rerun` | `resume` retrying an uncommitted attempt | diagnostic | Logged with the earlier attempt ordinals |
| `parallel_workspace_shared` | a later release | — | Not raised |

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
--force-restart         # Ignore existing state (flat route; refused for an evaluated run)
--repair                # Attempt state recovery (flat route only)
--backup-state          # Backup state before each step
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
