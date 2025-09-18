# Acceptance Tests (Normative)

For E2E execution guidance, see `tests/README.md` and informative narratives in `specs/examples/e2e.md`.

- Conformance areas
  - DSL validation: version gating, mutual exclusivity, `goto` target validation, strict unknown-field rejection.
  - Variable substitution: namespaces, escapes, undefined variable handling.
  - Dependency resolution: required vs optional, glob behavior, deterministic ordering.
  - Injection (v1.1.1): modes, default instruction, prepend/append position, truncation record.
  - IO capture: modes, limits, tee semantics, JSON parse behavior and `allow_parse_error`.
  - Providers: argv vs stdin, placeholder validation, unresolved placeholders, parameter merge.
  - Wait-for: exclusivity, timeout semantics, state metrics.
  - State integrity: atomic writes, backups, resume/repair, checksum.
  - CLI safety: `--clean-processed` & `--archive-processed` constraints.
  - Security: path safety, secrets handling and masking.

- Mapping to modules
  - See `dsl.md`, `variables.md`, `dependencies.md`, `io.md`, `providers.md`, `queue.md`, `state.md`, `cli.md`, `security.md`, `observability.md`.

- Future acceptance (planned)
  - v1.2 lifecycle: per-item success/failure moves; idempotency and resume.
  - v1.3 JSON validation: schema pass/fail, require-pointer assertions, variable substitution in schema path.

## Canonical List (v1.1 + v1.1.1)

1. Lines capture: `output_capture: lines` → `steps.X.lines[]` populated
2. JSON capture: `output_capture: json` → `steps.X.json` object available
3. Dynamic for-each: `items_from: "steps.List.lines"` iterates correctly
4. Status schema: Write/read status.json with v1 schema
5. Inbox atomicity: `*.tmp` → `rename()` → visible as `*.task`
6. Queue management is user-driven: Steps explicitly move tasks to `processed/{ts}/` or `failed/{ts}/` (orchestrator does not move individual tasks)
7. No env namespace: `${env.*}` rejected by schema validator
8. Provider templates: Template + defaults + params compose argv correctly (argv mode)
9. Provider stdin mode: provider with `input_mode: "stdin"` receives prompt via stdin and does not require `${PROMPT}`
10. Provider/Command exclusivity: Validation error when a step includes both `provider` and `command`
11. Clean processed: `--clean-processed` empties directory
12. Archive processed: `--archive-processed` creates zip on success
13. Pointer Grammar: `items_from: "steps.X.json.files"` iterates over nested `files` array
14. JSON Oversize: >1 MiB JSON fails with exit 2
15. JSON Parse Error Flag: The same step succeeds if `allow_parse_error: true` is set
16. CLI Safety: `run --clean-processed` fails if processed dir is outside WORKSPACE
17. Wait for files: `wait_for` blocks until matches or timeout
18. Wait timeout: exits 124 and sets `timed_out: true`
19. Wait state tracking: records `files`, `wait_duration_ms`, `poll_count`
20. Timeout (provider/command): enforces `timeout_sec` and records 124
21. Step retries: provider steps retry on 1/124 per policy; raw commands only when `retries` set
22. Dependency Validation: missing required fails with exit 2
23. Dependency Patterns: POSIX glob matching
24. Variable in Dependencies: substitution before validation
25. Loop Dependencies: re-evaluated each iteration
26. Optional Dependencies: missing optional omitted without error
27. Dependency Error Handler: `on.failure` catches validation failures (exit 2)
28. Basic Injection: `inject: true` prepends default instruction + file list
29. List Mode Injection: correctly lists all resolved file paths
30. Content Mode Injection: includes file contents with truncation metadata
31. Custom Instruction: `inject.instruction` overrides default text
32. Append Position: `inject.position: "append"` places injection after prompt content
33. Pattern Injection: globs resolve to full list before injection
34. Optional File Injection: missing optional files omitted from injection
35. No Injection Default: without `inject`, prompt unchanged
36. Wait-For Exclusivity: step combining `wait_for` with `command`/`provider`/`for_each` is rejected
37. Conditional Skip: false `when` → `skipped` with `exit_code: 0`
38. Path Safety (Absolute): absolute paths rejected at validation
39. Path Safety (Parent Escape): `..` or symlinks escaping WORKSPACE rejected
40. Deprecated override: `command_override` usage rejected
41. Secrets missing: missing declared secret yields exit 2 and `missing_secrets`
42. Secrets masking: secret values masked as `***` where feasible
43. Loop state indexing: results stored as `steps.<LoopName>[i].<StepName>`
44. Provider params substitution: variable substitution supported in `provider_params`
   - Undefined variables in provider_params: If `provider_params` contain undefined variables (including within nested dicts/lists), invocation preparation fails with `error.type: "substitution_error"` and `error.context.errors` lists all unresolved variable paths; no invocation is executed.
45. STDOUT capture threshold: `text` > 8 KiB truncates state and spills to logs
46. When exists: `when.exists` true when ≥1 match exists
47. When not_exists: `when.not_exists` true when 0 matches exist
48. Provider unresolved placeholders: `${model}` missing value → exit 2 with `missing_placeholders:["model"]`
49. Provider stdin misuse: `input_mode:"stdin"` with `${PROMPT}` → validation error (`invalid_prompt_placeholder`)
50. Provider argv without `${PROMPT}`: runs and does not pass prompt via argv
51. Provider params substitution: supports `${run|context|loop|steps.*}`
52. Output tee semantics: `output_file` receives full stdout while limits apply to state/logs
   - Path substitution in tee: Variable substitution (including `${run.root}`) is applied to `output_file` before writing; the fully resolved path receives the full stdout regardless of truncation/JSON-parse behavior.
53. Injection shorthand: `inject:true` ≡ `{mode:"list", position:"prepend"}`
54. Secrets source: read exclusively from orchestrator environment; empty strings accepted
55. Secrets + env precedence: `env` wins on conflicts; still masked as secret

56. Strict flow stop: Non-zero exit halts run when no applicable goto and `on_error=stop` (default)
57. on_error continue: With `--on-error continue`, run proceeds after non-zero exit
58. Goto precedence: `on.success`/`on.failure` goto targets execute (including `_end`) before strict_flow applies
59. Goto always ordering: `on.always` evaluated after success/failure handlers; ordering respected
60. Wait-for integration: Engine executes `wait_for` steps and records `files`, `wait_duration_ms`, `poll_count`, `timed_out`; downstream steps run on success
61. Wait-for path safety (runtime): absolute paths or `..` in `wait_for.glob` rejected with exit 2 and error context
62. Wait-for symlink escape: matches whose real path escapes WORKSPACE are excluded; returned paths are relative to WORKSPACE
63. Undefined variable in commands: referencing undefined `${run|context|steps|loop.*}` yields exit 2 with `error.context.undefined_vars` and no process execution
   - Multiple undefineds (string): For string commands, if multiple placeholders are undefined, `error.context.undefined_vars` includes all unique unresolved variable paths; `error.context.substituted_command` is present (single-element list) showing best-effort substitution with unresolved tokens left intact.
   - Multiple undefineds (list): For list commands, unresolved placeholders across separate tokens are all reported in `error.context.undefined_vars`; `error.context.substituted_command` lists all tokens after best-effort substitution.
   - Determinism: `error.context.undefined_vars` ordering is deterministic (e.g., sorted ascending) for reproducibility.
64. `${run.root}` variable: resolves to `.orchestrate/runs/<run_id>` and is usable in paths/commands
   - Applies in commands, provider_params, and output_file; resolved value is persisted in state (see 72).
65. Loop scoping of `steps.*`: inside `for_each`, `${steps.<Name>.*}` refers only to the current iteration’s results
66. `env` literal semantics: orchestrator does not substitute variables inside `env` values
67. Tee on JSON parse failure: with `output_capture: json` and parse failure (`allow_parse_error: false`), `output_file` still receives full stdout while state/log limits apply
68. Resume force-restart: `resume --force-restart` starts a new run (new `run_id`) and ignores existing state
   - Resume skip (steps): With `resume`, already completed or skipped steps are not re-executed; state remains unchanged for those steps and run proceeds without error.
   - Resume skip (for_each): With `resume`, completed iterations are not re-executed; incomplete iterations continue; state retains both array and flattened forms per (43); no errors are thrown.
69. Debug backups: `--debug` produces `state.json.step_<Step>.bak` backups with rotation (keep last 3)
70. Prompt audit & masking: with `--debug`, write `logs/<Step>.prompt.txt` containing composed prompt; known secret values masked as `***`
71. Retries + on.failure goto: after exhausting retries, `on.failure.goto` triggers and control follows the target step

72. Provider state persistence: after executing a provider step, `steps.<Name>` is persisted to `state.json` with `exit_code`, captured output per mode, and any `error`/`debug` fields; after reload (`state_manager.load()`), the provider result is present and unchanged.

## Supplemental: E2E Validation (Non‑Normative)

Status: Non‑normative, process/release gate. These items validate the presence and minimal viability of end‑to‑end tests using real provider CLIs. They must be segregated from the main suite and skipped by default when CLIs/secrets are unavailable. See `docs/ci-e2e.md` for suggested CI wiring.

- E2E-01 E2E Test Presence (Process Gate)
  - Scope: Repository hygiene and release readiness.
  - Preconditions: None.
  - Procedure:
    - Verify that `pyproject.toml` registers a `e2e` pytest marker.
    - Verify at least one test is decorated with `@pytest.mark.e2e` and collected by `pytest -m e2e`.
    - Verify E2E tests skip gracefully when required CLIs are absent (e.g., `shutil.which("claude")`/`shutil.which("codex")` is None) or when a guard env such as `ORCHESTRATE_E2E` is not set.
  - Expected:
    - At least one E2E test exists and is discoverable via `-m e2e`.
    - Default CI (without CLIs/secrets) collects but skips E2E tests without failing.
    - A dedicated CI job can run `pytest -v -m e2e` successfully in an environment with CLIs configured.

- E2E-02 Claude Provider (argv mode) Minimal Flow
  - Scope: Real CLI invocation using argv prompt delivery via `${PROMPT}`.
  - Preconditions: `claude` CLI available on PATH and authorized.
  - Procedure:
    - In a temporary workspace, write a workflow that defines a `claude` provider template with `command: ["claude","-p","${PROMPT}","--model","${model}"]`, `input_mode: "argv"`, and a valid `defaults.model`.
    - Create `prompts/ping.md` with a short prompt (e.g., "Reply with OK").
    - Add a single step `GenerateWithClaude` using `provider: "claude"`, `input_file: "prompts/ping.md"`, `output_file: "artifacts/architect/execution_log.txt"`, `output_capture: "text"`.
    - Run `orchestrate run <workflow.yaml>`.
  - Expected:
    - Run status `completed` in state.
    - Step exit_code `0`; state captures non‑empty output or a `logs/GenerateWithClaude.stdout` file exists.
    - `artifacts/architect/execution_log.txt` exists and is non‑empty.
  - Skip conditions: If `claude` not in PATH, or `ORCHESTRATE_E2E` not set, mark test skipped.

- E2E-03 Codex Provider (stdin mode) Minimal Flow
  - Scope: Real CLI invocation using stdin prompt delivery.
  - Preconditions: `codex` CLI available on PATH and authorized.
  - Procedure:
    - In a temporary workspace, write a workflow that defines a `codex` provider template with `command: ["codex","exec","--model","${model}","--dangerously-bypass-approvals-and-sandbox"]`, `input_mode: "stdin"`, and a valid `defaults.model`.
    - Create `prompts/ping.md` with a short prompt (e.g., "Print OK and exit").
    - Add a single step `PingWithCodex` using `provider: "codex"`, `input_file: "prompts/ping.md"`, `output_file: "artifacts/engineer/execution_log.txt"`, `output_capture: "text"`.
    - Run `orchestrate run <workflow.yaml>`.
  - Expected:
    - Run status `completed` in state.
    - Step exit_code `0`; state captures non‑empty output or a `logs/PingWithCodex.stdout` file exists.
    - `artifacts/engineer/execution_log.txt` exists and is non‑empty.
  - Skip conditions: If `codex` not in PATH, or `ORCHESTRATE_E2E` not set, mark test skipped.

Notes
- These E2E items avoid content‑specific assertions to reduce brittleness; they assert only exit status and artifact presence.
- All normative DSL/behavioral guarantees remain covered by the main acceptance list using unit/integration tests with fakes/mocks.
- CI segregation is required to keep default PR runs deterministic and fast.

## Future Acceptance (v1.2)

1. Success path: item moved to `processed/<ts>/...` per `success.move_to`.
2. Failure path: item moved to `failed/<ts>/...` per `failure.move_to`.
3. Recovery within item: recovered failure treated as success; success move.
4. Goto escape: escape marks failure and triggers failure move.
5. Path safety: invalid `move_to` rejected.
6. Variable substitution: `${run.timestamp_utc}` and `${loop.index}` resolve correctly.
7. Idempotency/resume: lifecycle actions not applied twice; `action_applied: true` recorded.
8. Missing source: record lifecycle error; result unchanged.
9. State recording: per-iteration `lifecycle` object present.

## Future Acceptance (v1.3)

1. Schema pass; 2. Schema fail with `json_schema_errors`; 3. Parse fail; 4. Parse allowed is incompatible with schema; 5. Require pointer exists; 6. Require equals; 7. Require type; 8. Multiple requirements; 9. Variable substitution in schema path; 10. Large JSON overflow behavior.
