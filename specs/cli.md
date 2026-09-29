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
provider in the workspace), `input answer|cancel`, `report` and `dashboard`.

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
read-only reporting remains available. Concurrent execution requires separate
workspaces. Result bundle paths and persisted result identities are unchanged.

- Commands
  - `orchestrate run <workflow.orc> [--context k=v ...] [--context-file path] [--input name=value ...] [--input-file path] [--clean-processed] [--archive-processed <dst>]`
    - `--dry-run` validates the workflow and may emit advisory lint warnings; warnings do not change the exit code for an otherwise valid workflow.
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
--force-restart         # Ignore existing state
--repair                # Attempt state recovery
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
