# CLI Contract (Normative)

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
  - `orchestrate report [--run-id <id>] [--runs-root <dir>] [--format md|json] [--output <path>]`
    - Report output may include advisory lint warnings (`lint.warnings[]` in JSON or an appendix in Markdown); warnings remain informational only.
    - Report output may include active runtime fields derived from executor sessions, including `run.active_runtime_ms`, `run.active_runtime`, `run.executor_session_count`, and `run.excluded_suspended_ms`. These fields exclude suspended gaps between executor processes and are informational only.
    - Report output may surface provider-session metadata paths and bounded
      interrupted-rerun diagnostic context; partial provider evidence remains
      non-authoritative.
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

- Environment variables
  - `ORCHESTRATE_DEBUG=1`, `ORCHESTRATE_STATE_DIR=/tmp/runs`, `ORCHESTRATE_LOG_LEVEL=debug`, `ORCHESTRATE_KEEP_RUNS=30`

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

### Environment Variables

```bash
ORCHESTRATE_DEBUG=1
ORCHESTRATE_STATE_DIR=/tmp/runs
ORCHESTRATE_LOG_LEVEL=debug
ORCHESTRATE_KEEP_RUNS=30
```

Cross-platform note: Examples use POSIX shell utilities (`bash`, `find`, `mv`, `test`). On Windows, use WSL or adapt to PowerShell equivalents.
