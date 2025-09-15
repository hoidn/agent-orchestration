# CLI Contract (Normative)

- Commands
  - `orchestrate run <workflow.yaml> [--context k=v ...] [--context-file path] [--clean-processed] [--archive-processed <dst>]`
  - `orchestrate resume <run_id>`
  - Optional/post-MVP: `orchestrate run-step <step_name> --workflow <file>`, `orchestrate watch <workflow.yaml>`

- Debugging and recovery flags
  - `--debug`, `--progress` (post-MVP), `--trace` (post-MVP), `--dry-run`
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
# Run workflow from beginning
orchestrate run workflows/demo.yaml \
  --context key=value \
  --context-file context.json \
  --clean-processed \           # Empty processed/ before run
  --archive-processed output.zip # Archive processed/ on success

# Resume failed/interrupted run
orchestrate resume <run_id>

# Execute single step (optional/post-MVP)
orchestrate run-step <step_name> --workflow workflows/demo.yaml

# Watch for changes and re-run (optional/post-MVP)
orchestrate watch workflows/demo.yaml
```

### Extended CLI Options

```bash
# Debug and observability
--debug                 # Enable debug logging
--progress              # Show real-time progress (post-MVP)
--trace                 # Include trace IDs in logs (post-MVP)
--dry-run               # Validate without execution

# State management
--force-restart         # Ignore existing state
--repair                # Attempt state recovery
--backup-state          # Backup state before each step
--state-dir <path>      # Override default .orchestrate/runs

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
