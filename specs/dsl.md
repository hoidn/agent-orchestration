# Workflow DSL and Control Flow (Normative)

- Top-level workflow keys
  - `version`: string (e.g., "1.1" or "1.1.1"). Strict gating: unknown fields at a given version → validation error (exit 2).
  - `name`: optional string.
  - `strict_flow`: boolean (default true). Non-zero exit halts the run unless `on.failure.goto` is present.
  - `providers`: map of provider templates (see `providers.md`).
  - Queue defaults: `inbox_dir`, `processed_dir`, `failed_dir`, `task_extension` (see `queue.md`).
  - `context`: key/value map available via `${context.*}` (see `variables.md`).
  - `steps`: ordered list of step objects.

- Step schema (consolidated; MVP + v1.1.1)
  - Required: `name: string`.
  - Optional metadata: `agent: string` (informational).
  - Execution (mutually exclusive in a single step):
    - `provider: string` (+ optional `provider_params`) OR
    - `command: string[]` OR
    - `wait_for: { ... }` (exclusive with provider/command/for_each)
  - IO:
    - `input_file: string`
    - `output_file: string`
    - `output_capture: text|lines|json` (default text)
    - `allow_parse_error: boolean` (json mode only)
  # Future (v1.3): JSON output validation (opt-in, version-gated)
  # Only valid when `version: "1.3"` or higher AND `output_capture: json` AND `allow_parse_error` is false
  - `output_schema?: string`                         # Path to JSON Schema under WORKSPACE; variables allowed
  - `output_require?:`                               # Simple built-in assertions on parsed JSON
      - `pointer: string`                            # RFC 6901 JSON Pointer (e.g., "/approved")
      - `exists?: boolean`                           # Default: true; require presence
      - `equals?: string|number|boolean|null`        # Optional exact match
      - `type?: string`                              # One of: string|number|boolean|array|object|null
  - Environment & secrets: see `security.md`.
  - Dependencies: `depends_on: { required[], optional[], inject }` (see `dependencies.md`).
  - Control:
    - `timeout_sec: number` (applies to provider/command; exit 124 on timeout)
    - `retries: { max: number, delay_ms?: number }`
    - `when`: condition object; any of
      - `equals: { left: string, right: string }` (string comparison)
      - `exists: string` (POSIX glob; true if ≥1 match within WORKSPACE)
      - `not_exists: string` (POSIX glob; true if 0 matches within WORKSPACE)
    - `on`: branching with goto
      - `success?: { goto: string }`
      - `failure?: { goto: string }`
      - `always?:  { goto: string }` (evaluated after success/failure)
  - Loops: `for_each`
    - `items_from: string` pointer to prior step array (`steps.X.lines` or `steps.X.json[.dot.path]`)
    - `items: any[]` literal array alternative
    - `as: string` alias for current item (default `item`)
    - `steps: Step[]` nested steps executed per item
    - v1.2 planned: `on_item_complete` (see `versioning.md`)

- Mutual exclusivity and validation
  - A step may specify exactly one of `provider`, `command`, or `wait_for`.
  - `for_each` is a block form and cannot be combined with `provider`/`command`/`wait_for` on the same step.
  - `goto` targets must reference an existing step name or `_end`. Unknown targets are a validation error (exit code 2) reported at workflow load time.
  - Deprecated `command_override` is not supported and must be rejected by the loader/validator.

- Control flow defaults
  - `strict_flow: true`: any non-zero exit halts unless an applicable `on.failure.goto` exists.
  - `_end`: reserved goto target that terminates the run successfully.
  - Precedence: step `on.*` handlers are evaluated first; if none apply, `strict_flow` and CLI `--on-error` govern.
  - Retry policy defaults: provider steps consider exit codes `1` and `124` retryable; raw `command` steps are not retried unless a per-step `retries` block is set. Step-level settings override CLI/global defaults.

- Loop scoping and state
  - Loop variables inside `for_each`: `${item}` (or alias), `${loop.index}` (0-based), `${loop.total}`.
  - Inside the loop, `${steps.<StepName>.*}` references results from the current iteration only.
  - State storage is indexed per iteration: `steps.<LoopName>[i].<StepName>` (see `state.md`).

- For-Each pointer syntax
  - Allowed forms: `steps.<Name>.lines` or `steps.<Name>.json[.<dot.path>]`.
  - The referenced value must resolve to an array; otherwise the step fails with exit 2 and error context.
  - Dot-paths do not support wildcards or advanced expressions.

## Workflow Schema (Top-Level)

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

Path safety: Absolute paths and any path containing `..` are rejected; symlinks must resolve within WORKSPACE (see `security.md`).

### Control Flow Defaults (MVP)
- `strict_flow: true` means any non-zero exit halts the run unless an `on.failure.goto` is defined for that step.
- `_end` is a reserved `goto` target that terminates the run successfully.
- Precedence: `on` handlers on the step (if present) are evaluated first; if none apply, `strict_flow` and the CLI `--on-error` setting govern whether to stop or continue.
