# Workflow programming for LLM agents 

## Executive Summary

Versioning note: This document describes the v1.1 baseline and includes the v1.1.1 additions for dependency injection. The state schema uses `schema_version: "1.1.1"` to reflect these additions. Workflows written against v1.1 (without injection) remain valid. The workflow DSL `version:` and the state `schema_version` follow separate version tracks by design. DSL validation is strict: unknown fields are rejected. Therefore, workflows that use `depends_on.inject` MUST set `version: "1.1.1"` (or higher); v1.1 workflows must not include `inject`.

This specification defines a workflow orchestration system that executes sequences of commands, including LLM model invocations, in a deterministic order. The system uses YAML to define workflows with branching logic. Filesystem directories serve as task queues for inter-agent communication. Each workflow step can invoke shell commands or language model CLIs (Claude Code or Gemini CLI), capture its output in structured formats (text, lines array, or JSON), and have output files (including those created by agent invocation) registered as read dependencies for subsequent steps. The YAML-based orchestration DSL supports string comparison, conditional branching, and loop constructs.

## Architecture Overview

### Directory Layout

```
workspace/
├── src/                    # User source code
├── prompts/               # Reusable prompt templates
├── artifacts/             # Agent-generated outputs
│   ├── architect/
│   ├── engineer/
│   └── qa/
├── inbox/                 # Agent work queues
│   ├── architect/
│   ├── engineer/
│   └── qa/
├── processed/             # Completed work items
│   └── {timestamp}/
└── failed/               # Failed work items (quarantine)
    └── {timestamp}/
```

Path Resolution Rule: All user-declared paths remain explicit and resolve against WORKSPACE. No auto-prefixing based on agent.

Path Safety (MVP default):
- Reject absolute paths and any path that contains `..` during validation.
- Follow symlinks, but if the resolved real path escapes WORKSPACE, reject the path.
- Enforce these checks at load time and before filesystem operations.
 - Note: These safety checks apply to paths the orchestrator resolves (e.g., `input_file`, `output_file`, `depends_on`, `wait_for`). Child processes invoked by `command`/`provider` can read/write any locations permitted by the OS; use OS/user sandboxing if stricter isolation is required.

### Run Identity and State Management

#### Run Identification
- **run_id format**: `YYYYMMDDTHHMMSSZ-<6char>` (timestamp + random suffix)
- **RUN_ROOT**: `.orchestrate/runs/${run_id}` under WORKSPACE
- **State persistence**: All run data stored under RUN_ROOT

#### State File Schema

The state file (`${RUN_ROOT}/state.json`) is the authoritative record of execution:

```json
{
  "schema_version": "1.1.1",
  "run_id": "20250115T143022Z-a3f8c2",
  "workflow_file": "workflows/pipeline.yaml",
  "workflow_checksum": "sha256:abcd1234...",
  "started_at": "2025-01-15T14:30:22Z",
  "updated_at": "2025-01-15T14:35:47Z",
  "status": "running",  // running | completed | failed
  "context": {
    "key": "value"
  },
  "steps": {
    "StepName": {
      "status": "completed",
      "exit_code": 0,
      "started_at": "2025-01-15T14:30:23Z",
      "completed_at": "2025-01-15T14:30:25Z",
      "duration_ms": 2145,
      "output": "...",
      "truncated": false,
      "debug": {
        "command": ["echo", "hello"],
        "cwd": "/workspace",
        "env_count": 42
      }
    }
  },
  "for_each": {
    "ProcessItems": {
      "items": ["file1.txt", "file2.txt"],
      "completed_indices": [0],
      "current_index": 1
    }
  }
}
```

Step Status Semantics:
- Step `status` values: `pending | running | completed | failed | skipped`.
- Conditional steps with `when` that evaluate false are marked `skipped` and do not execute a process (treat as `exit_code: 0`).

#### State Integrity

**Corruption Detection:**
- State file includes `workflow_checksum` to detect workflow modifications
- Each state update atomically writes to `.state.json.tmp` then renames
- Malformed JSON or schema violations trigger recovery mode

**Recovery Mechanisms:**
```bash
# Resume with state validation
orchestrate resume <run_id>  # Validates and continues

# Force restart ignoring corrupted state
orchestrate resume <run_id> --force-restart  # Creates new state

# Attempt repair of corrupted state
orchestrate resume <run_id> --repair  # Best-effort recovery

# Archive old runs
orchestrate clean --older-than 7d  # Remove old run directories
```

**State Backup (MVP policy):**
- When `--backup-state` is enabled (or in `--debug`), before each step execution copy `state.json` to `state.json.step_${step_name}.bak`.
- Keep last 3 backups per run (rotating).
- On corruption, attempt rollback to last valid backup.

### Task Queue System

Writing Tasks:
1. Create as `*.tmp` file
2. Atomic rename to `*.task`

Processing Results (Recommended Pattern — user‑managed):
- Success: Use an explicit workflow step to `mv <task> processed/{timestamp}/`
- Failure (non-retryable): Use an explicit workflow step to `mv <task> failed/{timestamp}/`

Ownership Clarification:
- The orchestrator does not automatically move, archive, or delete task files.
- Queue directories and `*.task` files are conventions used by workflows; authors are responsible for file lifecycle via explicit steps.
- The orchestrator provides blocking (`wait_for`) and safe CLI helpers (`--clean-processed`, `--archive-processed`) but never moves individual tasks on step success/failure.

Post‑MVP note (planned/v1.2): An optional, version‑gated declarative helper for per‑item lifecycle (see “Declarative Task Lifecycle for for_each (v1.2)” below) can move items at the end of an iteration. This is opt‑in and does not change MVP defaults.

File Content: Freeform text; JSON recommended for structured data

Configuration:
```yaml
# Top-level workflow config (with defaults)
inbox_dir: "inbox"
processed_dir: "processed"
failed_dir: "failed"
task_extension: ".task"
```

## Declarative Task Lifecycle for for_each (v1.2)

Status: Planned future feature. Opt‑in, version‑gated. Does not change MVP defaults.

Version gating:
- Requires `version: "1.2"` or higher. Using `on_item_complete` at lower versions is a validation error (exit code 2).

Purpose:
- Reduce boilerplate by declaratively moving a per‑item task file after an iteration completes, based on item success/failure.

Schema (inside `for_each`):
```yaml
on_item_complete?:
  success?:
    move_to?: string   # Destination directory under WORKSPACE; variables allowed
  failure?:
    move_to?: string   # Destination directory under WORKSPACE; variables allowed
```

Semantics:
- Trigger timing: Evaluated once per item after its `steps` finish.
- Success: All executed steps ended with `exit_code: 0` after retries, and no `goto` escaped the loop before finishing.
- Failure: Any step failed after retries, or a timeout (124) remained, or a `goto` jumped outside the loop/`_end` before finishing.
- Recovery: If a step fails but is recovered by `on.failure` and the item completes, the item counts as success.
- Variable substitution: `${run.*}`, `${loop.*}`, `${context.*}`, `${steps.*}` are supported in `move_to`.
- Path safety: `move_to` follows the same rules as other paths and must resolve within WORKSPACE. Absolute/parent‑escape paths are rejected.
- Missing source: If the original item path no longer exists when applying the action, record a lifecycle error; do not change the item’s result.
- Idempotency/resume: Lifecycle is idempotent; on resume, previously applied actions are not repeated.

State recording (per iteration):
```json
{
  "lifecycle": {
    "result": "success|failure",
    "action": "move",
    "from": "inbox/engineer/task_001.task",
    "to": "processed/20250115T143022Z/task_001.task",
    "action_applied": true,
    "error": null
  }
}
```

Example:
```yaml
version: "1.2"
steps:
  - name: CheckEngineerInbox
    command: ["find", "inbox/engineer", "-name", "*.task", "-type", "f"]
    output_capture: "lines"

  - name: ProcessEngineerTasks
    for_each:
      items_from: "steps.CheckEngineerInbox.lines"
      as: task_file
      on_item_complete:
        success:
          move_to: "processed/${run.timestamp_utc}"
        failure:
          move_to: "failed/${run.timestamp_utc}"
      steps:
        - name: Implement
          provider: "claude"
          input_file: "${task_file}"

        - name: CreateQATask
          command: ["bash", "-lc", "echo 'Review ${task_file}' > inbox/qa/$(basename \"${task_file}\").task"]

        - name: WaitForQAVerdict
          wait_for:
            glob: "inbox/qa/results/$(basename \"${task_file}\").json"
            timeout_sec: 3600

        - name: AssertQAApproved
          command: ["bash", "-lc", "jq -e '.approved == true' inbox/qa/results/$(basename \"${task_file}\").json >/dev/null"]
          on:
            failure: { goto: _end }  # Forces item failure; lifecycle will move to failed/
```

Planned acceptance (v1.2):
1. Success path moves to `processed/…`; failure path moves to `failed/…`.
2. Failure recovered by `on.failure` and item completes → success move.
3. `goto` escaping the loop triggers failure move.
4. Unsafe `move_to` (outside WORKSPACE) rejected at validation.
5. Variable substitution in `move_to` resolves correctly.
6. Idempotent on resume; no double move.
7. Missing source logs lifecycle error; item result unchanged.

---

## CLI Contract

```bash
# Run workflow from beginning
orchestrate run workflows/demo.yaml \
  --context key=value \
  --context-file context.json \
  --clean-processed \           # Empty processed/ before run
  --archive-processed output.zip # Archive processed/ on success

# Resume failed/interrupted run
orchestrate resume <run_id>

# Execute single step
orchestrate run-step <step_name> --workflow workflows/demo.yaml   # Optional (post-MVP)

# Watch for changes and re-run
orchestrate watch workflows/demo.yaml                             # Optional (post-MVP)
```

Safety: The `--clean-processed` flag operates only on the configured `processed_dir` if and only if it resides under WORKSPACE; otherwise it fails. The `--archive-processed` destination path must be outside of the configured `processed_dir`. If a destination is not provided, the archive defaults to `RUN_ROOT/processed.zip`.

### Extended CLI Options

#### Debugging and Recovery Flags

```bash
# Debug and observability
--debug                 # Enable debug logging
--progress              # Show real-time progress (post-MVP)
--trace                 # Include trace IDs in logs (post-MVP)
--dry-run              # Validate without execution

# State management
--force-restart        # Ignore existing state
--repair               # Attempt state recovery
--backup-state         # Force state backup before each step
--state-dir <path>     # Override default .orchestrate/runs

# Error handling
--on-error stop|continue|interactive  # Error behavior (interactive optional/post-MVP)
--max-retries <n>      # Retry failed steps (default: 0)
--retry-delay <ms>     # Delay between retries

# Output control  
--quiet                # Minimal output
--verbose              # Detailed output
--json                 # JSON output for tooling (optional/post-MVP)
--log-level debug|info|warn|error
```

#### Environment Variables

```bash
# Override defaults
ORCHESTRATE_DEBUG=1              # Same as --debug
ORCHESTRATE_STATE_DIR=/tmp/runs # Custom state location
ORCHESTRATE_LOG_LEVEL=debug     # Default log level
ORCHESTRATE_KEEP_RUNS=30         # Days to keep old runs
```

Cross-platform note: Examples in this document use POSIX shell utilities (`bash`, `find`, `mv`, `test`). On Windows, use WSL or equivalent tooling, or adapt commands to PowerShell/Windows-native equivalents (e.g., `find` → `Get-ChildItem -Recurse`, `test -f` → `Test-Path`, `mv` → `Move-Item -Force`).

## Variable Model

### Namespaces (precedence order)

1. Run Scope
   - `${run.id}` - The run identifier (e.g., `YYYYMMDDTHHMMSSZ-<6char>`)
   - `${run.root}` - Run root directory path relative to WORKSPACE (e.g., `.orchestrate/runs/${run.id}`)
   - `${run.timestamp_utc}` - The start time of the run, formatted as `YYYYMMDDTHHMMSSZ`

2. Loop Scope
   - `${item}` - Current iteration value
   - `${loop.index}` - Current iteration (0-based)
   - `${loop.total}` - Total iterations

3. Step Results
  - `${steps.<name>.exit_code}` - Step completion code
  - `${steps.<name>.output}` - Step stdout (text mode)
  - `${steps.<name>.lines}` - Array when `output_capture: lines`
  - `${steps.<name>.json}` - Object when `output_capture: json`
  - `${steps.<name>.duration_ms}` - Execution time in milliseconds (preferred)
  - `${steps.<name>.duration}` - Alias for milliseconds (deprecated; use `duration_ms`)

4. Context Variables
   - `${context.<key>}` - Workflow-level variables

### Variable Substitution Scope

Where Variables Are Substituted:
- Command arrays: `["echo", "${context.message}"]`
- File paths: `"artifacts/${loop.index}/result.md"`
- Provider parameters: `model: "${context.model_name}"`
- Conditional values: `left: "${steps.Previous.output}"`
- Dependency paths: `depends_on.required: ["data/${context.dataset}/*.csv"]`

Variable substitution applies to `provider_params` values. It does not occur inside `env` values.

Where Variables Are NOT Substituted:
- File contents: The contents of files referenced by `input_file`, `output_file`, or any other file parameters are passed as-is without variable substitution

Dynamic Content Pattern:

To include dynamic content in files, use a pre-processing step:

```yaml
steps:
  # Step 1: Create dynamic prompt with substituted variables
  - name: PreparePrompt
    command: ["bash", "-c", "echo 'Analyze ${context.project_name}' > temp/prompt.md"]
    
  # Step 2: Use the prepared prompt
  - name: Analyze
    provider: "claude"
    input_file: "temp/prompt.md"  # Contains substituted content
```

Template processing for file contents is not currently supported. Files are passed literally without variable substitution.

### MVP Defaults and Edge Cases

Undefined Variables (MVP default):
- Referencing an undefined variable is an error; the step halts with exit code 2 and records error context. A future flag may allow treating undefined as empty string.

Type Coercion in Conditions (MVP default):
- Conditions compare as strings; JSON numbers and booleans are coerced to strings prior to comparison.

Escape Syntax (MVP default):
- Use `$$` to render a literal `$`. To render the sequence `${`, write `$${`.

Portability Recommendations:
- Initialize variables before use via `context` or prior steps.
- Prefer explicit strings in conditions: `"true"` rather than boolean `true`.
- Avoid literal `${` in strings unless escaped as `$${`.

### Environment & Secrets

Per-step environment injection (no orchestrator substitution):
```yaml
steps:
  - name: Build
    env:
      LOG_LEVEL: "debug"      # Non-secret env vars
    secrets:
      - GITHUB_TOKEN          # Secret env vars (masked in logs)
    command: ["npm", "run", "build"]
```

Semantics:
- `env` is a string map that is passed to the child process environment as-is. The orchestrator does not perform variable substitution inside `env` values.
- `secrets` is a list of environment variable names that must be present in the orchestrator’s own environment. Values are passed through to the child process and are masked in orchestrator logs/state/debug outputs.
- Missing secret: If a named secret is not present at execution time, the step fails with exit code 2 and an error context entry `missing_secrets: [..]`.
- Masking: When `--debug` and standard logging capture environment snapshots or process output, occurrences of exact secret values are replaced with `***` where feasible. Note: masking is best-effort and based on known values at runtime.

Environment inheritance and precedence (normative):
- Base environment: child processes inherit the orchestrator’s current environment (e.g., `PATH`, `HOME`, etc.).
- Secrets pass-through: for each name in `secrets`, the value is read from the orchestrator environment and included in the child environment.
- Step `env` overlay: keys in `env` are overlaid last and take precedence over both base env and `secrets`.
- Precedence summary: `child_env = base_env ∪ secrets ∪ env` with later sources winning on key conflicts.

Source & precedence (clarified):
- Secrets are sourced exclusively from the orchestrator process environment in v1.1. There is no implicit `.env` loading and no keychain integration.
- If a key appears in both `env` and `secrets`, the child receives the `env` value; the key is still treated as a secret for masking.
- Empty-string secret values count as present; only undefined variables are considered missing.
- On missing secrets, the step exits 2 and `error.context.missing_secrets` lists all missing names.

---

## Workflow Schema (Top-Level)

The workflow file defines these top-level keys:

```yaml
version: string                 # Workflow DSL version (e.g., "1.1"); independent of state schema_version
name: string                    # Human-friendly name
strict_flow: boolean            # Default: true; non-zero exit halts unless on.failure.goto present
context: { [key: string]: any } # Optional key/value map available via ${context.*}

# Provider templates available to steps
providers:                      # Optional
  <provider-name>:
    command: string[]           # May include ${PROMPT} in argv mode
    input_mode: argv|stdin      # Default: argv
    defaults: { [key: string]: any }

# Directory configuration (all paths relative to WORKSPACE)
inbox_dir: string               # Default: "inbox"
processed_dir: string           # Default: "processed" (must be under WORKSPACE)
failed_dir: string              # Default: "failed"   (must be under WORKSPACE)
task_extension: string          # Default: ".task"

steps: Step[]                   # See Step Schema
```

Path safety: Absolute paths and any path containing `..` are rejected during validation; symlinks are followed but must resolve within WORKSPACE.

Versioning: The workflow DSL `version:` and the persisted state `schema_version` follow separate version tracks.

Validation policy (DSL): The schema validator is strict and rejects unknown fields at the declared DSL `version`. Feature availability is gated by `version:`. Using fields introduced in 1.1.1 (e.g., `depends_on.inject`) requires `version: "1.1.1"` or higher.

---

### Version Gating Summary

| DSL version | Key features enabled | Notes |
| --- | --- | --- |
| 1.1 | Baseline DSL; providers (argv/stdin), `wait_for`, `depends_on` (required/optional), `when` (equals/exists/not_exists), retries/timeouts, strict path safety | State schema initially 1.1.1 (separate track). Unknown DSL fields rejected. |
| 1.1.1 | `depends_on.inject` (list/content/none), injection truncation recording | Workflows must declare `version: "1.1.1"` to use `inject`. |
| 1.2 (planned) | `for_each.on_item_complete` declarative per‑item lifecycle (move_to on success/failure) | Opt‑in; path safety and substitution apply. State gains per‑iteration `lifecycle` fields; state schema will bump accordingly when released. |
| 1.3 (planned) | JSON output validation: `output_schema`, `output_require` for steps with `output_capture: json` | Enforces schema and simple assertions; incompatible with `allow_parse_error: true`. |

The workflow DSL `version:` and the persisted state `schema_version` follow separate version tracks. Validators MUST enforce that DSL fields are only available at or above their introducing version.

---

## Step Schema

### Fields

```yaml
# Agent label (optional)
agent: "engineer"  # Informational label only; doesn't affect path resolution

# Output capture mode
output_capture: "text"  # Default: text | lines | json

# Dynamic for-each from prior step
for_each:
  items_from: "steps.CheckInbox.lines"  # Reference array from prior step
  # OR literal array:
  items: ["a", "b", "c"]
  as: item
  steps: [...]

# Optional, only applies when output_capture: json
allow_parse_error: false

# Provider specification
provider: "claude"
provider_params:
  model: "claude-sonnet-4-20250514"  # Options: claude-opus-4-1-20250805

# Raw command (mutually exclusive with provider)
command: ["claude", "-p", "Custom prompt"]

# Wait for files (blocking primitive for inter-agent communication)
wait_for:
  glob: "inbox/engineer/replies/*.task"  # File pattern to watch
  timeout_sec: 1800                      # Max wait time (default: 300)
  poll_ms: 500                          # Poll interval (default: 500)
  min_count: 1                          # Min files required (default: 1)
  # Note: wait_for is mutually exclusive with command/provider/for_each in the same step.

# Dependency validation and injection
depends_on:
  required:   # Files that must exist
    - "config/*.yaml"
    - "data/${context.dataset}/*.csv"
  optional:   # Files that may exist
    - "cache/previous.json"
  inject: true  # Auto-inject file list
  # OR advanced form:
  inject:
    mode: "list"  # How to inject: list | content | none
    instruction: "Custom instruction for these files:"
    position: "prepend"  # Where to inject: prepend | append
```

### Step Schema — Consolidated (MVP + 1.1.1)

```yaml
# Required
name: string

# Optional metadata
agent: string                                 # Informational only

# Execution (mutually exclusive)
provider: string                              # Name of provider template
provider_params: object                       # Overrides for template defaults
command: string[]                             # Raw command; no provider when set

# IO
input_file: string                            # Read as prompt/input; literal contents
output_file: string                           # Redirect STDOUT to file
output_capture: text|lines|json               # Default: text
allow_parse_error: boolean                    # Only when output_capture: json; default: false

# Future (v1.3): JSON output validation (opt-in, version-gated)
# Only valid when `version: "1.3"` or higher AND `output_capture: json` AND `allow_parse_error` is false
output_schema?: string                         # Path to JSON Schema under WORKSPACE; variables allowed
output_require?:                               # Simple built-in assertions on parsed JSON
  - pointer: string                            # RFC 6901 JSON Pointer (e.g., "/approved")
    exists?: boolean                           # Default: true; require presence
    equals?: string|number|boolean|null        # Optional exact match
    type?: string                              # One of: string|number|boolean|array|object|null

# Environment
env: { [key: string]: string }                # No orchestrator substitution
secrets: string[]                             # Names of required env vars to pass-through and mask

# Dependencies
depends_on:
  required: string[]                          # POSIX glob patterns; must match ≥1 path
  optional: string[]                          # Missing → no error
  inject: boolean |                           # false (default) or
    {
      mode: list|content|none                 # Default: none
      instruction?: string                    # Default text if omitted
      position?: prepend|append               # Default: prepend
    }

# Waiting (mutually exclusive with provider/command/for_each)
wait_for:
  glob: string                                # Required
  timeout_sec?: number                         # Default: 300
  poll_ms?: number                             # Default: 500
  min_count?: number                           # Default: 1

State recording for `wait_for`:
- `files`: array of matched file paths at completion
- `wait_duration_ms`: total milliseconds waited
- `poll_count`: number of polls performed
- `timed_out`: boolean indicating whether timeout was reached

Example state fragment (`steps.<StepName>`):
```json
{
  "status": "completed",
  "files": ["inbox/engineer/replies/task_001.task"],
  "wait_duration_ms": 12345,
  "poll_count": 25,
  "timed_out": false
}
```

# Control
timeout_sec?: number                           # Applies to provider/command; exit 124 on timeout
retries?:                                      # Optional per-step override
  max: number                                  # Default: 0
  delay_ms?: number                            # Optional backoff delay

when?:                                         # Basic conditionals
  equals?:
    left: string                               # After variable substitution
    right: string                              # Compared as strings
  exists?: string                               # POSIX glob; true if ≥1 match within WORKSPACE
  not_exists?: string                           # POSIX glob; true if 0 matches within WORKSPACE

on?:
  success?: { goto: string }                   # Step name or _end
  failure?: { goto: string }                   # Takes effect on non-zero exit
  always?:  { goto: string }                   # Runs regardless; evaluated after success/failure

for_each?:                                     # Dynamic block iteration
  items_from?: string                          # Pointer to array in prior step
  items?: any[]                                # Literal array alternative
  as?: string                                  # Variable name for current item (default: item)
  steps: Step[]                                # Nested steps executed per item

  # Future (v1.2): Declarative per-item lifecycle (opt-in, version-gated)
  # Only valid when `version: "1.2"` or higher
  on_item_complete?:
    success?:
      move_to?: string                         # Destination dir under WORKSPACE; vars allowed
    failure?:
      move_to?: string                         # Destination dir under WORKSPACE; vars allowed
```

Notes:
- Mutual exclusivity is validated: a step may specify exactly one of `provider`, `command`, or `wait_for`; `for_each` is a separate block form.
- `timeout_sec` maps timeouts to exit code `124` and records timeout context in `state.json`.
- `retries` applies only to the current step. If not set, CLI/global retry policy applies.
- `when` supports `equals`, `exists`, and `not_exists` in v1.1; `equals` compares values as strings (see Type Coercion in Conditions).
- `on` handlers take precedence over `strict_flow`: if an appropriate `goto` is present it is honored; otherwise `strict_flow` and CLI `--on-error` determine behavior.
- Retry policy defaults: Provider steps consider exit codes `1` and `124` retryable; raw `command` steps are not retried unless a per-step `retries` block is specified. Step-level settings override CLI/global defaults.
 - Validation of `goto` targets: A `goto` must reference an existing step name or `_end`. Unknown targets are a validation error (exit code 2) reported at workflow load time.

### Loop Scoping and State Representation

Semantics within a `for_each` block:
- Variable scope: `${item}` (or the alias from `as:`), `${loop.index}` (0-based), and `${loop.total}` are available to nested steps.
- Step result references: Inside the loop, `${steps.<StepName>.*}` refers to the result of `<StepName>` from the current iteration.
- Name resolution: Step names must be unique within the loop block; the same step name may appear in other scopes.
- Cross-iteration access is not supported in v1.1 (e.g., referencing results from a different index).

State storage for looped steps is indexed by iteration:

```json
{
  "steps": {
    "ProcessEngineerTasks": [
      {
        "ImplementWithClaude": { "status": "completed", "exit_code": 0 },
        "WriteStatus":        { "status": "completed", "json": {"success": true} }
      },
      {
        "ImplementWithClaude": { "status": "failed", "exit_code": 2 }
      }
    ]
  }
}
```

Pointer syntax: `for_each.items_from` must target an array produced by a prior step (e.g., `steps.List.lines` or `steps.Parse.json.files`). See also “For-Each Pointer Syntax”.

### Output Capture Modes

#### For-Each Pointer Syntax

See also: Loop Scoping and State Representation for how looped step results are stored and referenced.

The `for_each.items_from` value must be a string in the format `steps.<StepName>.lines` or `steps.<StepName>.json[.<dot.path>]`. The referenced value must resolve to an array. Dot-paths do not support wildcards or advanced expressions.
If the reference is missing or not an array, the step fails with exit code 2 and records error context.

`text` (default): Traditional string capture
```json
{
  "output": "First line\nSecond line\n",
  "truncated": false
}
```

`lines`: Split into array of lines
```json
{
  "output_capture": "lines",
  "lines": ["inbox/engineer/task1.task", "inbox/engineer/task2.task"],
  "truncated": false
}
```

Line-splitting and normalization:
- Lines are split on LF (`\n`). CRLF (`\r\n`) is normalized to LF in the `lines[]` entries.
- The raw, unmodified stdout stream is preserved in `logs/<StepName>.stdout` only when truncation occurs (see Limits) or when JSON parsing fails.

`json`: Parse as JSON object
```json
{
  "output_capture": "json",
  "json": {"success": true, "files": ["a.py", "b.py"]},
  "truncated": false
}
```

Parse failure → exit code 2 unless `allow_parse_error: true`

When `allow_parse_error: true` and parsing fails due to invalid JSON or size overflow:
- The step completes with `exit_code: 0`.
- `state.json` stores the raw text in `steps.<StepName>.output` (subject to the 8 KiB text limit) and sets `truncated` accordingly.
- No `json` field is present.
- A diagnostic entry is recorded at `steps.<StepName>.debug.json_parse_error: { reason: "invalid|overflow" }`.

Limits:
- text: The first 8 KiB of stdout is stored in the state file. If stdout exceeds 8 KiB, `truncated: true` is set and the full stdout stream is written to `${RUN_ROOT}/logs/<StepName>.stdout`.
- lines: A maximum of 10,000 lines are stored. If exceeded, the `lines` array will contain the first 10,000 entries and a `truncated: true` flag will be set.
- json: The orchestrator will buffer up to 1 MiB of stdout for parsing. If stdout exceeds this limit, parsing fails with exit code 2 (unless `allow_parse_error: true`). Invalid JSON also results in exit code 2.

State Fields: When `output_capture` is set to `lines` or `json`, the raw `output` field is omitted from the step's result in `state.json` to avoid data duplication.

### Control Flow Defaults (MVP)
- `strict_flow: true` means any non-zero exit halts the run unless an `on.failure.goto` is defined for that step.
- `_end` is a reserved `goto` target that terminates the run successfully.
- Precedence: `on` handlers on the step (if present) are evaluated first; if none apply, `strict_flow` and the CLI `--on-error` setting determine whether to stop or continue.
 - Validation: `goto` targets must reference an existing step or `_end`; unknown targets are a validation error (exit 2) at validation time.

## Provider Execution Model

### Command Construction and ${PROMPT}

Mutual exclusivity (MVP rule):
- A step must specify either `provider` (with optional `provider_params`) or a raw `command`, but not both. Using both is a validation error.
- The deprecated `command_override` field is not supported; use a raw `command` step instead for fully manual invocations.

Execution:
- If `provider` is set, use the provider template with merged parameters (`defaults` overridden by `provider_params`).
- If `command` is set (and no `provider`), execute the raw command array as-is.

Timeouts:
- When `timeout_sec` is set on a step, the orchestrator enforces it for provider/command executions. On timeout, the process receives a graceful termination signal, followed by a hard kill after a short grace period; the step records exit code `124` and timeout context in state.

Reserved placeholder `${PROMPT}` and input modes:
- Provider templates may include `${PROMPT}` to receive the composed input text as a single argv token when using argv mode.
- Providers may also declare `input_mode: "stdin"`, in which case the orchestrator pipes the composed prompt to the process stdin (and `${PROMPT}` must not be used in the template).
- In both modes, the prompt is composed from `input_file` contents after optional dependency injection. Injection is performed in-memory; input files are never modified on disk.
- If `${PROMPT}` is absent in `argv` mode, no prompt is passed via argv (this is valid; some CLIs read their own inputs or reference files directly).
- If `${PROMPT}` appears in a template that declares `input_mode: "stdin"`, validation fails (see substitution semantics below).

Arg length guidance:
- Some operating systems impose limits on total argv size. When dependency injection (especially `content` mode) or large prompts are expected, prefer providers with `input_mode: "stdin"`.
- The orchestrator does not automatically fall back to stdin when argv size is large; selection is explicit via the provider template.

Provider template substitution (clarified):
1) Compose prompt: Read `input_file` literally, apply `depends_on.inject` in-memory (if any) → composed prompt string.
2) Merge params: `providers.<name>.defaults` overlaid by `step.provider_params` (step wins).
3) Substitute inside merged params: Apply variable substitution to string values in `provider_params` (recursively visiting nested objects/arrays), using all namespaces (`run`, `context`, `loop`, `steps`). Non-string values are left unchanged.
4) Substitute template tokens (single pass): In each command token, replace
   - `${PROMPT}` (argv mode only) with the composed prompt,
   - `${<provider_param_key>}` with the resolved provider parameter value from step+defaults,
   - `${run.*}`, `${context.*}`, `${loop.*}`, `${steps.*}` using current scopes.
5) Escaping: Apply escapes before substitution — `$$` → `$`, `$${` → `${`.
6) Unresolved placeholders: Any `${...}` remaining after substitution is a validation error. The step fails with exit code 2 and `error.context.missing_placeholders: ["key", ...]` (bare keys, without `${}`), or `invalid_prompt_placeholder` when `${PROMPT}` appears in `stdin` mode.
7) Reference errors: If a referenced `steps.*` value is missing or of the wrong type (e.g., non-array where an array is required), the step fails with exit code 2 and `error.context.invalid_reference` details.

### Input/Output Contract

When a step specifies both `provider` and `input_file`:

1. Input Handling:
   - argv mode (default): The orchestrator reads `input_file` contents and passes them as a single CLI argument via `${PROMPT}` in the provider template.
   - stdin mode: The orchestrator reads `input_file` contents and writes them to the child process stdin. The template must not use `${PROMPT}`.
2. Output Handling: If `output_file` is specified, STDOUT is tee'd to that file and to the orchestrator's capture pipeline.
3. File contents passed literally: No variable substitution occurs inside the file; injection happens in-memory before passing to argv or stdin as per mode.

Example Execution:
```yaml
steps:
  - name: Analyze
    provider: "claude"
    input_file: "prompts/analyze.md"
    output_file: "artifacts/analysis.md"

# Orchestrator reads the file:
PROMPT_CONTENT=$(cat prompts/analyze.md)

# Then executes:
claude -p "$PROMPT_CONTENT" --model claude-sonnet-4-20250514 > artifacts/analysis.md
#      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#      Prompt text as CLI arg + model selection
```

Prompt Contents:
```markdown
# prompts/analyze.md
Analyze the system requirements and create a detailed architecture.
Consider scalability, security, and maintainability.
Read any files in artifacts/requirements/ for context.
```

Key Benefits:
- No duplication: Prompt doesn't need to reference itself
- Natural prompts: Write prompts as you normally would
- Provider flexibility: Provider can still read other files mentioned IN the prompt
- Clean separation: `input_file` = the prompt, other files = data the prompt references

Output capture with `output_file` (tee semantics):
- When `output_file` is set, the orchestrator duplicates STDOUT to both the file and an in-memory buffer used for `output_capture` processing. This ensures the file receives the full stream while state/logs follow capture limits.

Tee semantics details:
- `text`: Store up to 8 KiB in `state.json`; if exceeded, set `truncated:true` and write full stdout to `logs/<StepName>.stdout`. The `output_file` always receives the full stream.
- `lines`: Store up to 10,000 lines; if exceeded, set `truncated:true` and write full stdout to `logs/<StepName>.stdout`. The `output_file` always receives the full stream.
- `json`: Buffer up to 1 MiB for parsing. On success, store parsed JSON; on overflow or invalid JSON, exit 2 unless `allow_parse_error:true`. The `output_file` always receives the full stream regardless of parse outcome.
- Stderr is captured separately and written to `logs/<StepName>.stderr` when non-empty.

### Provider File Operations

### Concurrent File and Stream Output

Providers can read and write files directly from/to the filesystem while also outputting to STDOUT. These capabilities coexist:

1. Direct File Operations: Providers may create, read, or modify files anywhere in the workspace based on prompt instructions
2. STDOUT Capture: The `output_file` parameter captures STDOUT (typically logs, status messages, or reasoning process)
3. Simultaneous Operation: A provider invocation may write multiple files AND produce STDOUT output

Example:
```yaml
steps:
  - name: GenerateSystem
    agent: "architect"
    provider: "claude"
    input_file: "prompts/design.md"
    output_file: "artifacts/architect/execution_log.md"  # Captures STDOUT
    # Provider may also create files directly:
    # - artifacts/architect/system_design.md
    # - artifacts/architect/api_spec.md
    # - artifacts/architect/data_model.md
```

### Best Practices

- Use `output_file` to capture execution logs and agent reasoning for debugging
- Design prompts to write primary outputs as files to appropriate directories
- Use subsequent steps to discover and validate created files
- Document expected file outputs in step comments for clarity

### File Dependencies

#### Optional Dependency Declaration

Steps may declare file dependencies for pre-execution validation and documentation:

**Syntax:**
```yaml
steps:
  - name: ProcessData
    provider: "claude"
    input_file: "prompts/process.md"
    depends_on:
      required:  # Must exist or step fails
        - "config.json"
        - "data/*.csv"
        - "artifacts/architect/*.md"
      optional:  # Warning if missing, continues execution
        - "cache/previous.json"
        - "docs/reference.md"
```

#### Behavior Rules

1. **Validation Time**: Immediately before step execution (after previous steps complete)
2. **Variable Substitution**: `${...}` variables ARE substituted using current context
3. **Pattern Syntax**: POSIX glob patterns (`*` and `?` wildcards); globstar `**` is not supported in v1.1
4. **Pattern Matching**: 
   - `required` + 0 matches = exit code 2 (non-retryable failure)
   - `optional` + 0 matches = no warning (intentional)
5. **Existence Check**: File OR directory present = exists
6. **Path Resolution**: Relative to WORKSPACE
7. **Symlinks**: Followed
   - Safety: Symlinks must resolve within WORKSPACE; if a symlink’s real path escapes WORKSPACE, validation fails.
8. **Loop Context**: Re-evaluated each iteration with current loop variables
9. **Matching Semantics**: Matching uses POSIX-style globbing; dotfiles are matched only when explicitly specified; case sensitivity follows the host filesystem

#### Error Handling

- Missing required dependency produces exit code 2 (non-retryable)
- Standard `on.failure` handlers apply
- Error message includes the missing path/pattern

#### Benefits

- **Fail Fast**: Detect missing files before expensive provider calls
- **Documentation**: Explicit declaration of file relationships  
- **Better Errors**: Clear messages about what's missing
- **Future-Ready**: Enables caching and change detection in v2

#### Dependency Injection

The orchestrator can automatically inject dependency information into the provider's input, eliminating the need to manually maintain file lists in prompts.

##### Basic Injection

```yaml
depends_on:
  required:
    - "artifacts/architect/*.md"
  inject: true  # Enable auto-injection with defaults
```

When `inject: true`, the orchestrator behaves exactly as if `inject: { mode: "list", position: "prepend" }` were specified, using the default instruction text. It prepends:
```
The following files are required inputs for this task:
- artifacts/architect/system_design.md
- artifacts/architect/api_spec.md

[original prompt content]
```

##### Advanced Injection

```yaml
depends_on:
  required:
    - "artifacts/architect/*.md"
  optional:
    - "docs/standards.md"
  inject:
    mode: "list"  # list | content | none (default: none)
    instruction: "Review these architecture files:"  # Custom instruction
    position: "prepend"  # prepend | append (default: prepend)
```

##### Injection Modes

**`list` mode**: Injects file paths with instruction
```
Review these architecture files:
Required:
- artifacts/architect/system_design.md
- artifacts/architect/api_spec.md
Optional (if available):
- docs/standards.md

[original prompt content]
```

**`content` mode**: Injects full file contents
```
Review these architecture files:

=== File: artifacts/architect/system_design.md ===
[full content of file]

=== File: artifacts/architect/api_spec.md ===
[full content of file]

[original prompt content]
```

**`none` mode** (default): No injection, manual coordination required

##### Default Instructions

If `instruction` is not specified, the orchestrator uses context-appropriate defaults:

- **list mode**: "The following files are required inputs for this task:"
- **content mode**: "The following file contents are provided for context:"

##### Injection Rules

1. **Pattern Resolution**: Glob patterns are resolved to actual file paths before injection
2. **Variable Substitution**: Variables in paths are substituted before injection
3. **Missing Optional Files**: Omitted from injection without error
4. **Empty Required Patterns**: If a required pattern matches no files, dependency validation fails (no injection occurs)
5. **Position**: 
   - `prepend`: Injection appears before original prompt content
   - `append`: Injection appears after original prompt content
6. **Injection Target**: Injection modifies the in-memory prompt passed to the provider; the input_file on disk is not changed
7. **Deterministic Ordering**: Resolved file paths are injected in stable lexicographic order (byte-wise, ascending)
8. **File Headers (content mode)**: Each file is preceded by a header line `=== File: <relative/path> (<size info>) ===`; when truncated, `<size info>` shows `<shown_bytes>/<total_bytes>`; when not truncated, it may show either total bytes or a human-readable size
9. **Shorthand Equivalence**: `inject: true` is equivalent to `inject: { mode: "list", position: "prepend" }`.

##### Size Limits and Truncation

**Rationale:** The 256 KiB cap prevents memory exhaustion while accommodating typical use cases (100+ file paths or several configuration files).

**Truncation Behavior:**

In **list mode:**
```
Review these files:
- file1.md
- file2.md
...
- file99.md
[... 47 more files truncated (312 KiB total)]
```

In **content mode:**
```
=== File: config.yaml (45 KiB) ===
[content]

=== File: data.json (180 KiB) ===
[partial content]
[... truncated: 125 KiB of 180 KiB shown]

=== Files not shown (5 files, 892 KiB) ===
- archived/old1.json (201 KiB)
- archived/old2.json (189 KiB)
[... 3 more files]
```

**Truncation Record:**
When truncation occurs, state.json records (at `steps.<StepName>.debug.injection`):
```json
{
  "injection_truncated": true,
  "truncation_details": {
    "total_size": 524288,
    "shown_size": 262144,
    "files_shown": 2,
    "files_truncated": 1,
    "files_omitted": 5
  }
}
```

#### Migration Notes

##### From v1.1 to v1.1.1
Existing workflows with `depends_on` continue to work unchanged. To adopt injection:

**Before (v1.1):**
```yaml
# Had to maintain file list in both places
depends_on:
  required:
    - "artifacts/architect/*.md"
input_file: "prompts/implement.md"  # Must list files manually
```

**After (v1.1.1):**
```yaml
# Single source of truth
version: "1.1.1"
depends_on:
  required:
    - "artifacts/architect/*.md"
  inject: true  # Automatically informs provider
input_file: "prompts/generic_implement.md"  # Can be generic
```

##### Benefits of Injection
- **DRY Principle**: Declare files once in YAML
- **Pattern Support**: `*.md` expands automatically
- **Maintainability**: Change file lists in one place
- **Flexibility**: Generic prompts work across projects

---

## Provider Configuration

### Direct CLI Integration

The providers are Claude Code (`claude`), Gemini CLI (`gemini`), Codex CLI (`codex`), and similar tools — not raw API calls.

Workflow-level templates:
```yaml
providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    defaults:
      model: "claude-sonnet-4-20250514"  # Options: claude-opus-4-1-20250805
  
  gemini:
    command: ["gemini", "-p", "${PROMPT}"]
    # Gemini CLI doesn't support model selection via CLI

  codex:
    command: ["codex", "exec"]
    input_mode: "stdin"   # Read prompt from stdin
    defaults:
      model: "gpt-5"      # Example default; can be overridden if CLI supports it
```

Step-level usage:
```yaml
steps:
  - name: Analyze
    provider: "claude"
    provider_params:
      model: "claude-3-5-sonnet"  # or claude-3-5-haiku for faster/cheaper
    input_file: "prompts/analyze.md"
    output_file: "artifacts/architect/analysis.md"

  - name: ManualCommand
    command: ["claude", "-p", "Special prompt", "--model", "claude-opus-4-1-20250805"]

  - name: PingWithCodex
    provider: "codex"
    input_file: "prompts/ping.md"
    output_file: "artifacts/codex/ping_output.txt"
    # Orchestrator pipes prompt to `codex exec` stdin
```

Claude Code is invoked with `claude -p "prompt" --model <model>`. Available models:
- `claude-sonnet-4-20250514` - balanced performance
- `claude-opus-4-1-20250805` - most capable

Model can also be set via `ANTHROPIC_MODEL` environment variable or `claude config set model`.

Codex CLI is invoked with `codex exec` and reads the prompt from stdin. The orchestrator handles piping the composed prompt into stdin when `input_mode: "stdin"` is set for the provider template. Defaults such as model may be configured via provider defaults or the Codex CLI’s own configuration.

### Provider Templates — Quick Reference

| Provider | Command template | Input mode | Notes |
| --- | --- | --- | --- |
| claude | `claude -p ${PROMPT} --model ${model}` | argv | Default model via provider defaults (e.g., `claude-sonnet-4-20250514`) or CLI config/env. |
| gemini | `gemini -p ${PROMPT}` | argv | Model selection may not be supported via CLI; rely on CLI configuration if applicable. |
| codex | `codex exec` (prompt via stdin) | stdin | Reads prompt from stdin; `${PROMPT}` must not appear in template. Defaults (e.g., `model: gpt-5`) may be provided in provider defaults or via Codex CLI config. |

Exit code mapping:
- 0 = Success
- 1 = Retryable API error
- 2 = Invalid input (non-retryable)
- 124 = Timeout (retryable)

Note: Exit codes are intentionally coarse; consult `state.json` for rich error context (e.g., undefined variables, missing dependencies, JSON parse errors).

Parameter handling: If a provider template does not reference a given `provider_params` key (e.g., `model` for a CLI that lacks model selection), the parameter is ignored with a debug log entry; this is not a validation error in v1.1.

---

## Status Communication

### Status JSON Schema

```json
{
  "schema": "status/v1",
  "correlation_id": "uuid-or-opaque",
  "agent": "engineer",
  "run_id": "20250115T143022Z-a3f8c2",
  "step": "ImplementFeature",
  "timestamp": "2025-01-15T10:30:00Z",
  "success": true,
  "exit_code": 0,
  "outputs": ["artifacts/engineer/implementation.py"],
  "metrics": {
    "files_modified": 3,
    "lines_added": 150
  },
  "next_actions": [
    {
      "agent": "qa",
      "file": "inbox/qa/review_implementation.task"
    }
  ],
  "message": "Feature implemented successfully"
}
```

Default path: `artifacts/<agent>/status_<step>.json` (recommended). Alternative convention: `artifacts/<agent>/status.json` to represent the most recent agent status.

Path Convention: All file paths included within a status JSON file (e.g., in the `outputs` array) must be relative to the WORKSPACE directory.

Orchestrator interaction: The orchestrator does not consume or act on status JSON files. They are for observability and external tooling only; control flow derives solely from the workflow YAML and `state.json`.

## Debugging and Observability

### Debug Mode

Enable comprehensive logging with `--debug` flag:

```bash
orchestrate run workflow.yaml --debug
```

Debug mode captures:
- Variable substitution traces
- Dependency resolution details  
- Command construction logs
- Environment variable snapshot
- File operation details

### Execution Logs

Each run creates structured logs:

```
${RUN_ROOT}/
├── state.json           # Authoritative state
├── logs/
│   ├── orchestrator.log # Main execution log
│   ├── StepName.stdout  # Step stdout (if >8KB or JSON parse error)
│   ├── StepName.stderr  # Step stderr (always if non-empty)
│   └── StepName.debug   # Debug info (if --debug)
└── artifacts/          # Step-created files

Prompt audit (debug): When `--debug` is enabled, the composed prompt text (after dependency injection) is written to `logs/<StepName>.prompt.txt` with known secret values masked.
```

### Error Context

On step failure, the orchestrator records:

```json
{
  "error": {
    "message": "Command failed with exit code 1",
    "exit_code": 1,
    "stdout_tail": ["last", "10", "lines"],
    "stderr_tail": ["error", "messages"],
    "context": {
      "undefined_vars": ["${context.missing}"],
      "failed_deps": ["data/required.csv"],
      "substituted_command": ["cat", "data/file_20250115.csv"]
    }
  }
}
```

### Observability Features

**Progress Reporting:**
```bash
# Real-time progress
orchestrate run workflow.yaml --progress

# Output:
[2/5] ProcessData: Running (15s)...
  └─ for_each: [3/10] Processing item3.csv
```

**Metrics Collection:**
State file includes timing for performance analysis:
- Step duration
- Queue wait time (for wait_for steps)
- Provider execution time
- File I/O operations

**Trace Context:**
Each step can emit trace IDs for correlation with external systems. Use variable substitution in the command itself (env values are literal):
```yaml
steps:
  - name: CallAPI
    command: ["bash", "-c", "TRACE_ID=${run.id} curl https://example/api"]
```

## Example: Multi-Agent Inbox Processing

```yaml
version: "1.1.1"
name: "multi_agent_feature_dev"
strict_flow: true

providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    defaults:
      model: "claude-sonnet-4-20250514"  # Options: claude-opus-4-1-20250805

steps:
  # Architect creates design documents
  - name: ArchitectDesign
    agent: "architect"
    provider: "claude"
    input_file: "prompts/architect/design_system.md"
    output_file: "artifacts/architect/design_log.md"  # Captures thinking
    # Claude creates: artifacts/architect/system_design.md, api_spec.md
    
  # Check what architect created
  - name: ValidateArchitectOutput
    command: ["test", "-f", "artifacts/architect/system_design.md"]
    on:
      failure:
        goto: ArchitectFailed
        
  # Check for engineer tasks in inbox
  - name: CheckEngineerInbox
    command: ["find", "inbox/engineer", "-name", "*.task", "-type", "f"]
    output_capture: "lines"
    on:
      success:
        goto: ProcessEngineerTasks
      failure:
        goto: CreateEngineerTasks
        
  # Create tasks from architect output
  - name: CreateEngineerTasks
    command: ["bash", "-c", "
      echo 'Implement the system described in:' > inbox/engineer/implement.tmp &&
      ls artifacts/architect/*.md >> inbox/engineer/implement.tmp &&
      mv inbox/engineer/implement.tmp inbox/engineer/implement.task
    "]
    on:
      success:
        goto: CheckEngineerInbox
        
  # Process each engineer task
  - name: ProcessEngineerTasks
    for_each:
      items_from: "steps.CheckEngineerInbox.lines"
      as: task_file
      steps:
        - name: ImplementWithClaude
          agent: "engineer"
          provider: "claude"
          input_file: "prompts/engineer/generic_implement.md"  # Now can be generic!
          output_file: "artifacts/engineer/impl_log_${loop.index}.md"
          depends_on:
            required:  # Must have architect's designs
              - "artifacts/architect/system_design.md"
              - "artifacts/architect/api_spec.md"
            optional:  # Nice to have if available
              - "docs/coding_standards.md"
              - "artifacts/architect/examples.md"
            inject:
              mode: "list"
              instruction: "Implement the system based on these architecture documents:"
          on:
            failure:
              goto: HandleMissingDependencies
          # Claude writes: src/impl_${loop.index}.py
          
        - name: WriteStatus
          command: ["echo", '{"success": true, "task": "${task_file}", "impl": "src/impl_${loop.index}.py"}']
          output_file: "artifacts/engineer/status_${loop.index}.json"
          output_capture: "json"
          
        - name: MoveToProcessed
          command: ["bash", "-c", "mkdir -p processed/${run.timestamp_utc}_${loop.index} && mv ${task_file} processed/${run.timestamp_utc}_${loop.index}/"]
          
        - name: CreateQATask
          when:
            equals:
              left: "${steps.WriteStatus.json.success}"
              right: "true"
          command: ["echo", "Review src/impl_${loop.index}.py from ${task_file}"]
          output_file: "inbox/qa/review_${loop.index}.task"
          depends_on:
            required:
              - "src/impl_${loop.index}.py"  # Verify engineer created it

  # Error handlers
  - name: ArchitectFailed
    command: ["echo", "ERROR: Architect did not create required design files"]
    on:
      success:
        goto: _end
        
  - name: HandleMissingDependencies  
    command: ["echo", "ERROR: Required architect artifacts missing for engineer"]
    on:
      success:
        goto: _end
```

---

## Prompt Management Patterns

### Directory Purpose Clarification

- **`prompts/`**: Static, reusable prompt templates created by workflow authors before execution
- **`inbox/`**: Dynamic task files for agent coordination, created during workflow execution
- **`temp/`**: Temporary files for dynamic prompt composition and intermediate processing

### Multi-Agent Coordination Pattern

When agent B needs to process outputs from agent A:

```yaml
# Note: Using depends_on.inject requires version: "1.1.1"

steps:
  # Step 1: Agent A creates artifacts
  - name: ArchitectDesign
    agent: "architect"
    provider: "claude"
    input_file: "prompts/architect/design.md"  # Contains prompt text
    output_file: "artifacts/architect/log.md"   # Captures STDOUT
    # Claude writes: artifacts/architect/system_design.md, api_spec.md

  # Step 2: Drop a small queue task (atomic write)
  - name: PrepareEngineerTask
    command: ["bash", "-lc", "printf 'Implement the architecture.' > inbox/engineer/task_${run.timestamp_utc}.tmp && mv inbox/engineer/task_${run.timestamp_utc}.tmp inbox/engineer/task_${run.timestamp_utc}.task"]

  # Step 3: Agent B processes task; inputs declared and injected
  - name: EngineerImplement
    agent: "engineer"
    provider: "claude"
    input_file: "inbox/engineer/task_${run.timestamp_utc}.task"
    output_file: "artifacts/engineer/impl_log.md"
    depends_on:
      required:
        - "artifacts/architect/system_design.md"
        - "artifacts/architect/api_spec.md"
      inject: true  # list/prepend with default instruction
```

### Best Practices

- Keep static templates generic (reference concepts, not specific files)
- Build dynamic prompts at runtime to reference actual artifacts
- Use `inbox/` for agent work queues to maintain clear task boundaries
- Document the expected flow between agents in workflow comments

Guidance: Prefer declaring inputs with `depends_on` and using `inject` to inform providers, rather than composing prompt text via shell (`cat`/`echo`). Keep shell usage focused on filesystem lifecycle (atomic writes/moves); let the orchestrator handle prompt composition and validation.

---

### Non‑Normative Example: QA Verdict Pattern

This section documents a recommended pattern for capturing QA approvals as JSON. It is application‑level (not required by the DSL).

- Prompt and schema:
  - `prompts/qa/review.md` — instructs QA agent to output only a single JSON object to STDOUT (or to write to a verdict file); includes guidance on logging explanations to `artifacts/qa/logs/`.
  - `schemas/qa_verdict.schema.json` — JSON Schema defining the verdict shape (approved, reason, issues, outputs, task_id).
- Usage patterns:
  - STDOUT JSON gate: Set `output_capture: json` on the QA step and add an assertion step to gate success/failure deterministically.
  - Verdict file gate: Instruct the agent to write JSON to `inbox/qa/results/<task_id>.json`, then `wait_for` the file and assert via `jq`.
- Examples:
  - `workflows/examples/qa_gating_stdout.yaml`
  - `workflows/examples/qa_gating_verdict_file.yaml`

Notes:
- These patterns keep control flow deterministic without parsing prose. They complement (but do not depend on) the planned v1.3 hooks (`output_schema`, `output_require`).


## Example: File Dependencies in Complex Workflows

This example demonstrates all dependency features including patterns, variables, and loops:

```yaml
version: "1.1"
name: "data_pipeline_with_dependencies"

context:
  dataset: "customer_2024"
  model_version: "v3"

steps:
  # Validate all input data exists
  - name: ValidateInputs
    command: ["echo", "Checking inputs..."]
    depends_on:
      required:
        - "config/pipeline.yaml"
        - "data/${context.dataset}/*.csv"  # Variable substitution
        - "models/${context.model_version}/weights.pkl"
      optional:
        - "cache/${context.dataset}/*.parquet"
    
  # Process each CSV file
  - name: ProcessDataFiles
    command: ["find", "data/${context.dataset}", "-name", "*.csv"]
    output_capture: "lines"
    
  - name: TransformFiles
    for_each:
      items_from: "steps.ProcessDataFiles.lines"
      as: csv_file
      steps:
        - name: ValidateAndTransform
          provider: "data_processor"
          input_file: "${csv_file}"
          output_file: "processed/${loop.index}.parquet"
          depends_on:
            required:
              - "${csv_file}"  # Current iteration file
              - "config/transformations.yaml"
            optional:
              - "processed/${loop.index}.cache"  # Previous run cache
              
        - name: GenerateReport
          provider: "claude"
          input_file: "prompts/analyze_data.md"
          output_file: "reports/analysis_${loop.index}.md"
          depends_on:
            required:
              - "processed/${loop.index}.parquet"  # From previous step
              
  # Final aggregation needs all processed files
  - name: AggregateResults
    provider: "aggregator"
    input_file: "prompts/aggregate.md"
    output_file: "reports/final_report.md"
    depends_on:
      required:
        - "processed/*.parquet"  # Glob pattern for all outputs
      optional:
        - "reports/analysis_*.md"  # All analysis reports
```

---

## Example: Dependency Injection Modes

```yaml
version: "1.1.1"
name: "injection_modes_demo"

steps:
  # Simple injection with defaults
  - name: SimpleReview
    provider: "claude"
    input_file: "prompts/generic_review.md"
    depends_on:
      required:
        - "src/*.py"
      inject: true  # Uses default instruction
    
  # List mode with custom instruction
  - name: ImplementFromDesign
    provider: "claude"
    input_file: "prompts/implement.md"
    depends_on:
      required:
        - "artifacts/architect/*.md"
      inject:
        mode: "list"
        instruction: "Your implementation must follow these design documents:"
        position: "prepend"
    
  # Content mode for data processing
  - name: ProcessJSON
    provider: "data_processor"
    input_file: "prompts/transform.md"
    depends_on:
      required:
        - "data/input.json"
      inject:
        mode: "content"
        instruction: "Transform this JSON data according to the rules below:"
        position: "prepend"
    # The actual JSON content is injected before the transformation rules
    
  # Append mode for context
  - name: GenerateReport
    provider: "claude"
    input_file: "prompts/report_template.md"
    depends_on:
      optional:
        - "data/statistics/*.csv"
      inject:
        mode: "content"
        instruction: "Reference data for your report:"
        position: "append"
    # Template comes first, data is appended as reference
    
  # Pattern expansion with injection (non-recursive)
  - name: ReviewAllCode
    provider: "claude"
    input_file: "prompts/code_review.md"
    depends_on:
      required:
        - "src/*.py"      # POSIX glob; non-recursive
        - "tests/*.py"
      inject:
        mode: "list"
        instruction: "Review all these Python files for quality and consistency:"
    # All matched files are listed with clear instruction
    # Note: For recursive discovery, first generate a file list via a step like
    #   command: ["bash", "-c", "find src tests -name '*.py' -type f"] with output_capture: lines,
    # then pass that list through a for_each loop or render into a prompt file.
    
  # No injection (classic mode)
  - name: ManualCoordination
    provider: "claude"
    input_file: "prompts/specific_files_mentioned.md"
    depends_on:
      required:
        - "data/important.csv"
      inject: false  # Or omit inject entirely
    # Prompt must manually reference the files
```

---

## Example: Debugging Failed Runs

```yaml
version: "1.1"
name: "debugging_example"

steps:
  - name: ProcessWithDebug
    command: ["python", "process.py"]
    env:
      DEBUG: "0"  # env values are literal; orchestrator does not substitute
    on:
      failure:
        goto: DiagnoseFailure
        
  - name: DiagnoseFailure
    command: ["bash", "-c", "
      echo 'Checking failure context...' &&
      cat ${run.root}/logs/ProcessWithDebug.stderr &&
      jq '.steps.ProcessWithDebug.error' ${run.root}/state.json
    "]
```

### Investigating Failures

```bash
# Run with debugging
orchestrate run workflow.yaml --debug

# On failure, check logs
cat .orchestrate/runs/latest/logs/orchestrator.log

# Examine state
jq '.steps | map_values({status, exit_code, error})' \
  .orchestrate/runs/latest/state.json

# Resume after fixing issue
orchestrate resume 20250115T143022Z-a3f8c2 --debug
```

---

## Acceptance Tests

1. Lines capture: `output_capture: lines` → `steps.X.lines[]` populated
2. JSON capture: `output_capture: json` → `steps.X.json` object available
3. Dynamic for-each: `items_from: "steps.List.lines"` iterates correctly
4. Status schema: Write/read status.json with v1 schema
5. Inbox atomicity: `*.tmp` → `rename()` → visible as `*.task`
6. Queue management is user-driven: Steps explicitly move tasks to `processed/{ts}/` or `failed/{ts}/`; the orchestrator does not move individual tasks automatically
7. No env namespace: `${env.*}` rejected by schema validator
8. Provider templates: Template + defaults + params compose argv correctly (argv mode)
9. Provider stdin mode: A provider with `input_mode: "stdin"` receives the composed prompt via stdin; `${PROMPT}` is not required in the template
10. Provider/Command exclusivity: Validation error when a step includes both `provider` and `command`
11. Clean processed: `--clean-processed` empties directory
12. Archive processed: `--archive-processed` creates zip on success
13. Pointer Grammar: A workflow with `items_from: "steps.X.json.files"` correctly iterates over the nested `files` array
14. JSON Oversize: A step producing >1 MB of JSON correctly fails with exit code 2
15. JSON Parse Error Flag: The same step from above succeeds if `allow_parse_error: true` is set
16. CLI Safety: `orchestrate run --clean-processed` fails if the processed directory is configured outside WORKSPACE
17. Wait for files: `wait_for` step blocks until matching files appear or timeout
18. Wait timeout: `wait_for` with no matching files exits with code 124 after timeout and sets `timed_out: true`
19. Wait state tracking: `wait_for` records `files`, `wait_duration_ms`, `poll_count` in state.json
20. Timeout (provider/command): A step with `timeout_sec` terminates process and records exit code 124
21. Step retries: A provider step with `retries.max: 2` retries on exit codes 1/124 and respects `retries.delay_ms`; raw command steps retry only when `retries` is set
22. Dependency Validation: Step with `depends_on.required: ["missing.txt"]` fails with exit code 2
23. Dependency Patterns: `depends_on.required: ["*.csv"]` correctly matches files using POSIX glob
24. Variable in Dependencies: `depends_on.required: ["${context.file}"]` substitutes variable before validation
25. Loop Dependencies: Dependencies re-evaluated each iteration with current loop context
26. Optional Dependencies: Missing optional dependencies are omitted from injection and do not fail the step
27. Dependency Error Handler: `on.failure` catches dependency validation failures (exit code 2)
28. Basic Injection: Step with `inject: true` prepends default instruction and file list
29. List Mode Injection: `inject.mode: "list"` correctly lists all resolved file paths
30. Content Mode Injection: `inject.mode: "content"` includes full file contents with truncation metadata when applicable
31. Custom Instruction: `inject.instruction` replaces default instruction text
32. Append Position: `inject.position: "append"` places injection after prompt content
33. Pattern Injection: Glob patterns resolve to full file list before injection
34. Optional File Injection: Missing optional files omitted from injection without error
35. No Injection Default: Without `inject` field, no modification to prompt occurs
36. Wait-For Exclusivity: A step that combines `wait_for` with `command`/`provider`/`for_each` is rejected by validation
37. Conditional Skip: When `when.equals` evaluates false, step `status` is `skipped` with `exit_code: 0`
38. Path Safety (Absolute): Absolute paths are rejected at validation time
39. Path Safety (Parent Escape): Paths containing `..` or symlinks resolving outside WORKSPACE are rejected
40. Deprecated override: Using `command_override` is rejected by the schema/validator; authors must use `command` for manual invocations
41. Secrets missing: Declared `secrets: ["X"]` with `X` absent causes exit code 2 and `error.context.missing_secrets: ["X"]`
42. Secrets masking: When a secret value appears in logs/state, it is masked as `***` where feasible (exact-value replacement based on known secret values)
43. Loop state indexing: Results for `for_each` are stored as `steps.<LoopName>[i].<StepName>`
44. Provider params substitution: Values in `provider_params` support variable substitution
45. STDOUT capture threshold: When stdout exceeds 8 KiB, `state.output` is truncated and the full stream is written to `logs/<StepName>.stdout`
46. When exists: A step with `when.exists: "path/*.txt"` evaluates true when ≥1 match exists
47. When not_exists: A step with `when.not_exists: "missing/*.bin"` evaluates true when 0 matches exist

48. Provider unresolved placeholders: A provider template containing `${model}` without a value in defaults or `provider_params` fails with exit 2 and `error.context.missing_placeholders:["model"]`
49. Provider stdin misuse: A provider declaring `input_mode:"stdin"` and using `${PROMPT}` fails validation with exit 2 and `error.context.invalid_prompt_placeholder`
50. Provider argv without `${PROMPT}`: In `argv` mode, a template without `${PROMPT}` runs and does not pass the prompt via argv
51. Provider params substitution: Values in `provider_params` can reference `${run.*}`, `${context.*}`, `${loop.*}`, and `${steps.*}` and are resolved correctly
52. Output tee semantics: With `output_file` set, the file contains the full stdout while state/log limits apply (`text` 8 KiB, `lines` 10k, `json` 1 MiB parse buffer)
53. Injection shorthand: `inject:true` is equivalent to `inject:{mode:"list",position:"prepend"}` with default instruction
54. Secrets source: Secrets are read exclusively from the orchestrator environment; absent variables cause exit 2 with `missing_secrets` and present empty strings are accepted
55. Secrets + env precedence: When a key is in both `env` and `secrets`, the child receives the `env` value and it is masked in logs as a secret

---

## Out of Scope

- Concurrency (sequential only)
- While loops
- Parallel execution blocks
- Complex expression evaluation
- Event-driven triggers

---

## Future Acceptance (v1.2)

Planned acceptance tests for the declarative per‑item lifecycle helper (`for_each.on_item_complete`) and related semantics:

1. Success path: After all item steps succeed, the item is moved to `processed/<ts>/...` per `success.move_to`.
2. Failure path: If any item step fails after retries or times out, the item is moved to `failed/<ts>/...` per `failure.move_to`.
3. Recovery within item: A step fails but an `on.failure` handler recovers and the item reaches the end → treated as success, item moved via `success.move_to`.
4. Goto escape: A `goto` that exits the loop or jumps to `_end` before finishing marks the item as failure and triggers `failure.move_to`.
5. Path safety: A workflow specifying a `move_to` outside WORKSPACE (absolute or `..`) is rejected at validation time.
6. Variable substitution: `${run.timestamp_utc}` and `${loop.index}` in `move_to` resolve correctly and deterministically.
7. Idempotency/resume: Re‑running/resuming does not apply lifecycle actions twice; state reflects `action_applied: true` after the first application.
8. Missing source: If the item file no longer exists at lifecycle time, the orchestrator records a lifecycle error but does not change the item’s success/failure result.
9. State recording: Per‑iteration `lifecycle` object is present with `result`, `action`, `from`, `to`, `action_applied`, and optional `error`.

---

## Future Acceptance (v1.3)

Planned acceptance tests for JSON output validation hooks on steps with `output_capture: json`:

1. Schema pass: A step with `output_schema` whose stdout JSON conforms exits 0; state includes parsed JSON.
2. Schema fail: Violating `output_schema` yields exit 2 and `error.context.json_schema_errors` with human‑readable messages.
3. Parse fail: Non‑JSON stdout with `allow_parse_error: false` yields exit 2 and `error.message` indicating parse failure.
4. Parse allowed: Using `allow_parse_error: true` together with `output_schema` is rejected at validation time (exit 2) as incompatible.
5. Require pointer exists: `output_require: [{pointer: "/approved"}]` fails with exit 2 when pointer missing; passes when present.
6. Require equals: `output_require: [{pointer: "/approved", equals: true}]` fails when value is not boolean true; passes otherwise.
7. Require type: `output_require: [{pointer: "/issues", type: "array"}]` enforces JSON type; mismatch → exit 2.
8. Multiple requirements: All listed `output_require` constraints must pass; first failure is recorded in `error.context.json_require_failed` with the pointer and reason.
9. Variable substitution: `output_schema` path supports `${context.*}` substitution and follows path safety rules under WORKSPACE.
10. Large JSON: Oversize JSON (>1 MiB) remains governed by existing buffer limits and fails with exit 2 before validation.
