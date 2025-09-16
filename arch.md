# Multi-Agent Orchestrator v1.1 — Implementation Architecture

Document version: 1.1 (updated for modular specs)
Target spec: specs/index.md (modular master spec)
Implementation target: Python (>=3.11). Interface/type blocks may use TypeScript-style for clarity; implement with Python dataclasses and runtime validation.

## Spec vs Architecture Precedence

- **Normative contract:** The `specs/` directory, with `specs/index.md` as its entry point, defines the normative contract. This includes the DSL, state schema, CLI behavior, and Acceptance Tests. Each file covers a specific domain (e.g., `specs/cli.md` for the CLI, `specs/dsl.md` for the workflow language) and takes precedence for externally visible behavior in its domain.
- **Implementation guidance:** This `arch.md` documents ADRs and concrete implementation details used to realize the spec.
- **Conflict resolution:** If `arch.md` and a spec file disagree, implement to the spec and raise an `arch.md` change to realign.
- **Underspecification:** When the specs are silent, follow the ADRs here. If experience shows a spec needs additions, propose a PR against the relevant spec file.

## 1) Goals & Non‑Goals

- Goals
  - Execute YAML-defined workflows deterministically and sequentially.
  - Support branching (`on.success`/`on.failure`) and simple conditionals (`when.equals`).
  - Support for-each loops driven by previous step outputs (`items_from` pointers) or literal arrays.
  - Integrate directly with provider CLIs (e.g., Claude Code) via argv composition.
  - File-based inbox/processed/failed queues for inter-agent communication.
  - Persist authoritative state under `.orchestrate/runs/<run_id>/state.json` with atomic updates and backups.
  - Robust debug/observability, safe flags (`--clean-processed`, `--archive-processed`).
  - Strict DSL validation (unknown fields rejected) and version gating (e.g., `depends_on.inject` requires `version: "1.1.1"`).

- Non-goals (per `specs/index.md#out-of-scope`)
  - Concurrency/parallel blocks, while-loops, complex expressions.
  - Event-driven triggers beyond simple polling (`wait_for`).


## 2) Workspace & Runtime Layout

- Workspace (all paths relative to WORKSPACE)
  - `src/` user code
  - `prompts/` reusable templates
  - `artifacts/{architect,engineer,qa}/` agent outputs
  - `inbox/{architect,engineer,qa}/` file queues (`*.task`)
  - `processed/{ts}/` completed tasks
  - `failed/{ts}/` failed tasks

- Run state directory
  - `RUN_ROOT = .orchestrate/runs/<run_id>`
  - `state.json` (authoritative)
  - `logs/` (orchestrator.log, StepName.{stdout,stderr,debug})
  - `artifacts/` (optional mirror of step spills if needed)

- Path resolution rule: Use literal paths provided in workflow; resolve against WORKSPACE; no agent-based auto-prefixing.

## 2a) Architectural Decisions (ADRs)

- ADR-01 Filesystem as Source of Truth and Path Safety
  - All state, artifacts, and inter-agent communication live in the filesystem under WORKSPACE.
  - Enforce strict path safety rules as defined in `specs/security.md#path-safety`.
  - Enforce these rules at load/validation time and before any filesystem operation.

- ADR-02 Declarative YAML, Sequential Execution
  - YAML defines the workflow; the engine executes one step at a time, deterministically.

- ADR-02b Version Gating & Strict Validation
  - Loader enforces a strict schema; unknown fields are rejected at the declared `version:`.
  - Feature availability is gated by the `version:` field.
  - **See spec:** `specs/versioning.md`

- ADR-03 Provider as Managed Black Box (with assumed side effects)
  - Orchestrator manages the provider's inputs and outputs per a strict contract.
  - Providers may have side effects (reading/writing files); subsequent steps validate these effects.
  - **See spec:** `specs/providers.md`

- ADR-04 Authoritative JSON Run State
  - `state.json` is authoritative; update after every step attempt to support resumability and auditability.
  - **See spec:** `specs/state.md`


## 3) High-level System Architecture

- **CLI Layer (`orchestrate`)**
  - Defines commands (`run`, `resume`) and flags.
  - Implements safety rails for destructive operations.
  - **See spec:** `specs/cli.md`

- **Orchestration Engine**
  - Loads & validates workflow YAML.
  - Manages sequential execution, branching (`goto`), and conditionals (`when`).
  - Manages variable substitution, loop scope, and pointer resolution.
  - **See spec:** `specs/dsl.md`, `specs/variables.md`

- **State Manager**
  - Handles Run ID creation, atomic state writes, backups, and recovery.
  - Enforces workflow checksum validation on resume.
  - **See spec:** `specs/state.md`

- **Step Executor**
  - Constructs and executes `command` or `provider` invocations.
  - Manages timeouts, retries, and environment/secret injection.
  - Handles all `output_capture` modes and truncation semantics.
  - **See spec:** `specs/io.md`, `specs/security.md`

- **Provider Registry**
  - Manages provider templates and parameter merging.
  - Governs `input_mode` rules (`argv` vs `stdin`) and placeholder substitution.
  - **See spec:** `specs/providers.md`

- **Dependency Resolver & Injector**
  - Validates `depends_on` file globs.
  - Composes `inject` payload (list or content) into the in-memory prompt.
  - **See spec:** `specs/dependencies.md`

- **Wait/Poll Subsystem**
  - Implements the `wait_for` blocking primitive.
  - **See spec:** `specs/queue.md`

- **Queue Manager**
  - Provides conventions for filesystem-based queues but leaves lifecycle management to the workflow author.
  - **See spec:** `specs/queue.md`

- **Observability**
  - Manages structured logging, progress UI, and debug artifacts.
  - **See spec:** `specs/observability.md`


## 4) Module Structure (suggested)

```
orchestrator/
  cli/
    __init__.py
    main.py                 # argparse/click wiring; routes to handlers
    commands/
      __init__.py
      run.py
      resume.py
      run_step.py
      watch.py
      clean.py
  config/
    __init__.py
    types.py                # CLI options, global config (typing/datataclasses)
    defaults.py
  workflow/
    __init__.py
    loader.py               # YAML load + schema validation + checksum
    types.py                # Workflow, Step, Provider, Condition, DependsOn
    pointers.py             # steps.X.lines / steps.X.json.path resolution
    substitution.py         # variable interpolation (context/run/loop/steps)
  state/
    __init__.py
    run_state.py            # in-memory model + read/write/backup/repair
    persistence.py          # atomic write helpers, checksum
  exec/
    __init__.py
    runner.py               # low-level process spawn, env/secrets, timeouts
    step_executor.py        # command construction, uses runner + output_capture
    output_capture.py       # text/lines/json parse, truncation, spill
    retry.py                # retry policy helpers
  providers/
    __init__.py
    registry.py             # register/get provider templates
    types.py                # ProviderSpec, ProviderParams
  deps/
    __init__.py
    resolver.py             # glob resolve, required/optional, errors
    injector.py             # list/content injection composition
  fsq/
    __init__.py
    queue.py                # inbox read/write, processed/failed moves
    wait.py                 # wait_for polling with timeout
  logging/
    __init__.py
    logger.py               # levels, masking, trace IDs, progress
  observe/
    __init__.py
    status.py               # status JSON writer/validator
  watch/
    __init__.py
    watcher.py              # rerun on file changes (if implemented)
  utils/
    __init__.py
    fs.py, glob.py, time.py, json.py, zip.py, mask.py
```


## 5) Data Models (TypeScript-style interfaces; implement with Python dataclasses)

### 5.1 Workflow spec

```ts
type OutputCapture = 'text' | 'lines' | 'json';

interface ProviderParams { [k: string]: string; }

interface ProviderTemplate {
  name: string;                 // e.g., 'claude'
  command: string[];            // argv template e.g., ["claude","-p","${PROMPT}","--model","${model}"]
  defaults?: ProviderParams;    // e.g., { model: 'claude-sonnet-4-20250514' }
  input_mode?: 'argv' | 'stdin';// default: 'argv'; 'stdin' means pipe composed prompt to stdin
}

interface DependsOnConfigBasic {
  required?: string[];          // globs (after var-substitution)
  optional?: string[];
  inject?: boolean | DependsOnInjection;
}

interface DependsOnInjection {
  mode?: 'list' | 'content' | 'none';   // default: none
  instruction?: string;                 // default text per spec
  position?: 'prepend' | 'append';      // default: prepend
}

interface WaitForConfig {
  glob: string;
  timeout_sec?: number;   // default 300
  poll_ms?: number;       // default 500
  min_count?: number;     // default 1
}

interface ForEachBlock {
  items_from?: string;    // pointer e.g., 'steps.Check.lines' or 'steps.X.json.arr'
  items?: string[];       // literal
  as?: string;            // variable name (default: 'item')
  steps: Step[];          // nested steps
}

interface ConditionEquals {
  equals: { left: string; right: string };
}

interface StepBase {
  name: string;
  agent?: string;                         // label only
  when?: ConditionEquals;                 // optional, skip step if false
  on?: {                                  // goto branching
    success?: { goto: string };
    failure?: { goto: string };
  };
  env?: Record<string, string>;
  secrets?: string[];                     // env var names to expose, masked in logs
  output_capture?: OutputCapture;         // default: text
  allow_parse_error?: boolean;            // for json capture
  depends_on?: DependsOnConfigBasic;
  wait_for?: WaitForConfig;               // mutually exclusive with command/provider
}

interface StepCommand extends StepBase {
  command: string[];                      // e.g., ["echo","hello"]
}

interface StepProvider extends StepBase {
  provider: string;                       // e.g., 'claude'
  provider_params?: ProviderParams;       // e.g., { model: "..." }
  input_file?: string;                    // prompt path (read into PROMPT)
  output_file?: string;                   // redirect stdout to file
}

interface StepForEach extends StepBase {
  for_each: ForEachBlock;
}

// Validation: Steps must specify either provider (with optional provider_params) or a raw command, but not both.
// The deprecated `command_override` field is not supported and should be rejected by the loader/validator.
type Step = StepCommand | StepProvider | StepForEach | StepBase; // StepBase used only for wait_for-only steps

interface WorkflowSpec {
  version: string;                        // '1.1'
  name?: string;
  strict_flow?: boolean;                  // sequential default; goto allowed
  providers?: Record<string, ProviderTemplate>;
  inbox_dir?: string;                     // defaults per spec
  processed_dir?: string;
  failed_dir?: string;
  task_extension?: string;                // default: '.task'
  steps: Step[];
  context?: Record<string, string>;       // initial context vars
}
```

### 5.2 Run state (authoritative)

```ts
interface StepDebugInfo {
  command?: string[];
  cwd?: string;
  env_count?: number;
  // Present when dependency injection truncation occurs
  injection?: {
    injection_truncated?: boolean;
    truncation_details?: {
      total_size?: number;
      shown_size?: number;
      files_shown?: number;
      files_truncated?: number;
      files_omitted?: number;
    };
  };
}

interface StepErrorContext {
  message: string;
  exit_code: number;
  stdout_tail?: string[];
  stderr_tail?: string[];
  context?: {
    undefined_vars?: string[];
    failed_deps?: string[];
    substituted_command?: string[];
    missing_secrets?: string[];
    missing_placeholders?: string[];
    invalid_prompt_placeholder?: boolean;
  };
}

interface StepResultBase {
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  exit_code?: number;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  truncated?: boolean;
  debug?: StepDebugInfo;
  error?: StepErrorContext;
}

interface StepResultText extends StepResultBase { output?: string; }
interface StepResultLines extends StepResultBase { lines?: string[]; }
interface StepResultJson extends StepResultBase { json?: any; }
type StepResult = StepResultText | StepResultLines | StepResultJson;

interface ForEachRunState {
  items: string[];
  completed_indices: number[];
  current_index?: number;
}

interface RunState {
  schema_version: '1.1.1';
  run_id: string;                          // e.g., 20250115T143022Z-a3f8c2
  workflow_file: string;
  workflow_checksum: string;               // sha256
  started_at: string;
  updated_at: string;
  status: 'running' | 'completed' | 'failed' | 'suspended';
  context: Record<string, string>;
  steps: Record<string, StepResult | Array<Record<string, StepResult>>>;
  for_each?: Record<string, ForEachRunState>;
}
```

### 5.3 Status JSON

```ts
interface StatusJsonV1 {
  schema: 'status/v1';
  correlation_id?: string;
  agent?: string;
  run_id?: string;
  step?: string;
  timestamp: string;
  success: boolean;
  exit_code: number;
  outputs?: string[];          // relative to WORKSPACE
  metrics?: Record<string, number>;
  next_actions?: { agent: string; file: string }[];
  message?: string;
}
```


## 6) Execution Flow (pseudocode)

1. CLI parses command and options; resolves `WORKSPACE` (cwd) and `RUN_ROOT`.
2. Load YAML workflow → validate against schema (`specs/dsl.md`) → compute checksum.
3. Create run_id and initialize `state.json` (`specs/state.md`); or load/validate existing on `resume`.
4. For each top-level step index i:
   - Evaluate `when` condition (`specs/dsl.md`). If false, mark skipped and continue.
   - If `wait_for`: run wait loop (`specs/queue.md`).
   - If `for_each`: resolve items and iterate nested steps (`specs/dsl.md`).
   - Else (command/provider step):
     - Resolve dependencies (`specs/dependencies.md`).
     - Build `PROMPT` from `input_file` + injection.
     - Build and execute process (`specs/providers.md`).
     - Capture output with truncation (`specs/io.md`).
     - Record result in state.
   - Apply branching (`on.success`/`on.failure` goto).
5. On success, optionally `--archive-processed`.
6. Finalize run status.


## 7) Variable Model & Substitution

- Namespaces (precedence): run scope → loop scope → step results → context.
- Substitution locations: argv arrays, file paths, provider parameters, conditional values, dependency globs.
- No substitution inside file contents; to include dynamic content, preprocess in a step and reference that file.
- Implementation-defined choices (defaults for this implementation):
  - Undefined variables: error and halt with exit code 2. Flag `--undefined-as-empty` downgrades to empty string with warning.
  - Type coercion in conditions: compare as strings; JSON numbers are stringified.
  - Escape syntax: treat `$$` as a single literal `$`. To render `${`, write `$${`.
  - Disallow `${env.*}` namespace in workflows; loader rejects such references.
  - `when.exists`/`when.not_exists` use POSIX globs; paths resolve relative to WORKSPACE; symlinks must resolve within WORKSPACE.


## 8) Provider Integration

- Provider registry holds templates:
  - Example (Claude): `command: ["claude","-p","${PROMPT}","--model","${model}"]`, `input_mode: 'argv'`
  - Example (Codex): `command: ["codex","exec","--model","${model}","--dangerously-bypass-approvals-and-sandbox"]`, `input_mode: 'stdin'` (prompt via stdin)
  - `defaults.model = 'claude-sonnet-4-20250514'` (configurable when CLI supports it)
- Command construction rules:
  - Mutual exclusivity: a step may have either `provider` or `command`, not both. Validation error if both are present.
  - If `provider` is present, use provider template + merged params (`defaults` overridden by `provider_params`).
  - If `command` is present, execute it as-is.
- Input handling: if `input_file`, compose the prompt after optional dependency injection.
  - If `input_mode` is 'argv' (default), pass the composed prompt via `${PROMPT}` as a single CLI argument (argv token).
  - If `input_mode` is 'stdin', pipe the composed prompt to the child process stdin; provider templates MUST NOT reference `${PROMPT}` in this case.
  - In argv mode, a provider template that omits `${PROMPT}` runs without receiving the prompt via argv (allowed).
- Output handling: if `output_file`, redirect child stdout to that file while still capturing for state until size limits.
- Exit codes: 0 success; 1 retryable API error; 2 invalid input/non-retryable; 124 timeout (retryable).

Contracts (summary):
- Mutual exclusivity enforced by loader/validator; using both `provider` and `command` is invalid.
- Template interpolation errors surface as `MissingTemplateKeyError` and map to exit code 2 at the step level.
- Prompt handling is in-memory; composed prompt is delivered via argv token or piped to stdin depending on provider template `input_mode`.


## 9) Dependency Validation & Injection

- Resolution
  - Evaluate `required` and `optional` globs after variable substitution against WORKSPACE.
  - required + 0 matches → exit code 2; optional + 0 matches → continue.
  - Directories count as existing; follow symlinks; re-evaluate each loop iteration.

- Injection
  - Defaults: `inject: true` ≡ `{ mode: 'list', position: 'prepend' }` with default instruction.
  - Ordering: resolved file paths are injected in deterministic lexicographic order.
  - list mode: prepend/append instruction then bullet list of matched files (relative paths).
  - content mode: include file contents; each file prefixed with a header line `=== File: <relative/path> (<shown_bytes>/<total_bytes>) ===`.
  - Size cap: limit injected material to ~256 KiB; when truncated, record `steps.<StepName>.debug.injection` with `injection_truncated: true` and truncation details.
  - No modification to source `input_file`; the composed prompt string is passed to provider argv.

Contracts (summary):
- Validate required and optional patterns after variable substitution; use POSIX globs (`*` and `?`). Do not support `**` (globstar).
- Missing required → non-retryable validation error mapped to exit code 2; optional missing → proceed without warning unless `--verbose`.
- Injection modifies only the in-memory prompt composition; never edits files on disk.


## 10) Wait / Queue Semantics

- `wait_for` steps
  - Poll `glob` every `poll_ms` until `min_count` matches or `timeout_sec` elapses.
  - Exclusive with `provider`, `command`, and `for_each` in the same step.
  - On timeout, exit 124; record `files`, `wait_duration_ms`, `poll_count`, `timed_out: true` in state.

- Queue operations
  - Write task: create `*.tmp` then atomic rename to `*.task`.
  - Lifecycle is workflow-authored: add explicit steps to move items to `processed/{timestamp}/` or `failed/{timestamp}/`.

Inter‑Agent Example (worked):
- Architect step prompts provider to write `artifacts/architect/system_design.md`.
- A subsequent bash step lists architect artifacts and writes `inbox/engineer/task_X.tmp` → rename to `.task`.
- Engineer step requires `artifacts/architect/system_design.md`; with `depends_on.inject: true`, the orchestrator prepends a file list to the in-memory prompt before invoking the provider.
- Engineer produces code; orchestrator writes a QA review task to `inbox/qa/` and optionally waits for feedback with `wait_for` on `inbox/engineer/*.task`.


## 11) Observability & Logs

- Logs under `RUN_ROOT/logs/`:
  - `orchestrator.log` main log
  - `StepName.stdout` (>8KB or JSON parse error)
  - `StepName.stderr` (if non-empty)
  - `StepName.debug` (when `--debug`)
  - When `--debug`, include prompt audit: the composed prompt snapshot (with secrets masked) and provider command context.
- Progress UI (when `--progress`): `[n/N] StepName: Running (Xs)...` with for-each progress `[i/total]`.
- JSON output mode (`--json`): stream machine-readable updates to stdout (optional enhancement).
- Secrets masking: redact values of `secrets` env names in logs and command echoes, including real-time masking for streamed output.


## 12) Error Handling & Retry

- Per-step outcome → apply `on.success`/`on.failure` goto if present; otherwise continue sequentially.
- CLI `--on-error stop|continue|interactive` governs default behavior when not overridden.
- Retries: `--max-retries`, `--retry-delay` apply to retryable exit codes (1, 124).
- On failure, record error context (message, exit_code, tails, substituted command, failed deps, undefined vars).


## 13) State Integrity, Resume, and Cleanup

- Atomic state writes: write `state.json.tmp` then `rename`.
- Before each step, if `--backup-state` (or always per spec recommendation): copy `state.json` → `state.json.step_<step>.bak` (keep last 3).
- On corruption: `resume --repair` attempts last valid backup; `resume --force-restart` starts new run (new run_id); always validate checksum.
- `clean --older-than 7d` removes old run directories; `--state-dir` can override default base path.

Contracts (summary):
- Persist `state.json` after every step attempt (success or failure) to enable deterministic resume.
- On parse or write failure, do not partially overwrite: use tmp + atomic rename.


## 14) CLI Contract & Safety Rails

- Run
  - `orchestrate run <workflow.yaml> --context k=v --context-file ctx.json [--clean-processed] [--archive-processed <dst>]`
  - `--clean-processed` only operates on `WORKSPACE/processed/`; refuse others.
  - `--archive-processed` must target path outside `processed/`; default to `RUN_ROOT/processed.zip`.

- Resume / Run-step / Watch
  - `orchestrate resume <run_id>` validates state, resumes.
  - `orchestrate run-step <name> --workflow <file>` executes a single step in isolation (advanced usage).
  - `orchestrate watch <workflow.yaml>` (optional): re-run on file changes.


## 15) Implementation Details & Libraries

- Parsing & schema: `PyYAML` for YAML; minimal shape checks (pydantic or custom validators); enforce pointer grammar strings.
- Parsing & schema: `PyYAML` for YAML; strict validation via pydantic/dataclasses with custom validators (unknown fields rejected); enforce version gating (e.g., `inject` only when `version: "1.1.1"`).
- FS ops: `pathlib`, `os`, `shutil`, `tempfile`; POSIX globs via `glob`/`fnmatch`; follow symlinks with `pathlib.Path.resolve()` and validate WORKSPACE containment.
- CLI: `argparse` (baseline) or `click` (optional); `rich` (optional) for progress output.
- Process exec: `subprocess` with env overrides and timeouts.
- Zipping/archiving: `zipfile` or `shutil.make_archive`.
- Time/IDs: `datetime` (UTC ISO), `time`, `secrets`/`random` for 6-char suffix; run_id format `YYYYMMDDTHHMMSSZ-<6char>`.


## 16) Testing Strategy (maps to `specs/acceptance/index.md`)

- **Unit tests (pytest/unittest)**
  - `substitution`: namespaces, precedence, undefined handling (see `specs/variables.md`)
  - `pointers`: `steps.X.lines`, `steps.X.json.path` (see `specs/dsl.md`)
  - `depends_on`: required/optional, globs, loop re-eval (see `specs/dependencies.md`)
  - `injector`: modes, positioning, truncation metadata (see `specs/dependencies.md`)
  - `output_capture`: text/lines/json, limits, `allow_parse_error` (see `specs/io.md`)
  - `wait_for`: timeout code 124, metrics recorded (see `specs/queue.md`)
  - `provider rules`: template merging, argv/stdin modes, error conditions (see `specs/providers.md`)
  - `conditions`: `when` clauses (see `specs/dsl.md`)
  - `secrets`: handling and masking (see `specs/security.md`)
  - `CLI safety`: clean/archive constraints (see `specs/cli.md`)

- **Integration tests (pytest)**
  - end-to-end sample workflow mirroring spec examples (`specs/examples/`)
  - inbox atomicity, processed/failed moves
  - resume after simulated crash; repair from backup


## 17) Step-by-step Build Plan (for implementation)

1) Scaffolding
  - CLI command skeletons; logging; basic config defaults.

2) Workflow loader
  - YAML load; strict validation (unknown fields rejected); version gating for features; checksum.

3) State manager
  - Run ID, RUN_ROOT, atomic writes, backups, resume/repair.

4) Substitution & pointers
  - Implement namespace precedence; `${}` scanning; `$$` escape; pointer resolution.

5) Dependency resolver
  - Globs, required/optional semantics; symlink behavior; error mapping.

6) Injector
  - list/content modes; prepend/append; compose prompt string.

7) Step executor
  - Provider registry, argv builder; env/secrets; spawn; capture modes; truncation; retries.

8) Control flow
  - when.equals; on.success/on.failure goto; strict sequential default.

9) Wait/Queue
  - `wait_for` polling and metrics; atomic queue ops; processed/failed moves.

10) Observability
  - Logs, progress output; JSON mode; error context tails.

11) CLI safety & utilities
  - clean/archive; state-dir override; environment variables mapping.

12) Tests
  - Implement unit + integration tests mapped to acceptance list.


## 18) Implementation-defined Defaults (explicit choices)

- Undefined variable policy: error (exit 2). Optional `--undefined-as-empty` flag replaces with empty string and logs a warning once per var.
- Condition comparisons: strict string comparison; both sides coerced to strings.
- Escape syntax: `$$` → `$`, `$${` → `${`.
- **Output capture limits:** as defined in `specs/io.md` (text: 8 KiB in state; lines: 10,000 in state; json: 1 MiB parse buffer).
- Retries: default 0; classify 1 and 124 as retryable.


## 19) Security & Safety

- **Secrets handling:** per `specs/security.md`.
- **Path safety:** enforce ADR-01 rules strictly per `specs/security.md#path-safety`.
- **Clean/archive safeguards:** strictly enforced per `specs/cli.md`.


## 20) Developer Notes

- Keep step names unique (keys in state map).
- Avoid modifying input files during injection; always compose in-memory prompt string.
- Ensure state updates are granular: write after each step attempt to support robust resumes.
- Preserve compatibility with future v2 caching by being explicit about dependencies in state for each step.
- Testability: design for dependency injection—wire Engine with pluggable StateManager, StepExecutor, and Runner to ease unit testing and mocking.


## 21) Appendix — Main Run Loop Sketch

```py
def run(workflow_path: str, opts: CliOptions) -> None:
    wf = load_workflow(workflow_path)
    run_state = create_or_load_run_state(wf, opts)
    i = 0
    while i < len(wf.steps):
        step = wf.steps[i]
        backup_state(run_state, step.name, opts)
        outcome = execute_step(step, run_state, wf, opts)
        write_state(run_state)
        next_idx = next_index_from_outcome(outcome, wf, i)
        if next_idx == 'END':
            break
        i = next_idx if next_idx is not None else (i + 1)
    finalize_run(run_state)
```

This architecture maps 1:1 with the v1.1 spec and provides enough structure for a junior engineer to start implementing modules in order, with clear interfaces and well-defined behaviors.
