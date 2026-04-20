# Providers and Prompt Delivery (Normative)

- Provider templates
  - Define CLI command and input mode:
    - `command: string[]` may reference `${PROMPT}` in argv mode.
    - `input_mode: 'argv' | 'stdin'` (default: 'argv').
  - `defaults`: map of provider parameters (e.g., `model`).
  - v2.10 session-capable templates may also declare `session_support`:
    - `metadata_mode`
    - `fresh_command`
    - optional `resume_command`
  - `${SESSION_ID}` is legal only inside `session_support.resume_command`, which must contain exactly one placeholder when present.

- Step usage
  - `provider: <name>` uses the template; merge `defaults` overlaid by `provider_params` (step wins).
  - v2.10 top-level provider steps may also declare `provider_session` to select either `session_support.fresh_command` or `session_support.resume_command`.
  - In argv mode, `${PROMPT}` is replaced by the composed prompt (see below).
  - In stdin mode, the composed prompt is piped to the child stdin; provider templates MUST NOT include `${PROMPT}`.
  - Provider prompt sources are distinct from workflow-boundary `inputs` / `outputs`, runtime dependencies (`depends_on`, `consumes`), and artifact storage / lineage (`artifacts`, `expected_outputs`, `output_bundle`, `publishes`).
  - Reusable-workflow prompt assets:
    - `input_file` stays workspace-relative and is for workspace-owned or runtime-generated prompt material.
    - `asset_file` is the workflow-source-relative prompt/template surface for bundled reusable-workflow assets.

- Prompt composition
  - Read exactly one base prompt source:
    - `input_file` literally from WORKSPACE for workspace-owned or runtime-generated prompt material, or
    - `asset_file` literally from the directory containing the authored workflow file for bundled reusable-workflow assets.
  - `asset_depends_on` source assets are injected in-memory as deterministic content blocks in declared order.
  - Apply workspace dependency injection in-memory if `depends_on.inject` is enabled (see `dependencies.md`).
  - For `version: "1.2"` provider steps with `consumes`, inject a deterministic `Consumed Artifacts` block by default using resolved consume values from preflight (not prompt-authored paths).
    - Disable with `inject_consumes: false`.
    - Position with `consumes_injection_position: prepend|append` (default `prepend`).
    - Limit scope with `prompt_consumes: [artifact_name, ...]` to inject only selected consumed artifacts.
    - `prompt_consumes: []` suppresses the consumed-artifacts block entirely.
    - Optional `consumes` guidance annotations (`description`, `format_hint`, `example`) are included per injected artifact when present.
    - These annotations are prompt guidance only and do not change runtime consume enforcement semantics.
    - v2.10 resume steps reserve the `session_id_from` consume for runtime `${SESSION_ID}` binding; that consume is excluded from prompt injection and `consume_bundle`.
  - If the step defines `expected_outputs` and `inject_output_contract` is not `false`, append a deterministic `Output Contract` suffix describing required artifacts (`name`, `path`, `type`, optional constraints).
    - `expected_outputs.path` entries in this suffix are rendered after applying the same runtime variable substitution used for output-contract validation, so provider prompts show workspace-relative concrete paths rather than unresolved `${...}` templates.
    - Optional `expected_outputs` guidance annotations (`description`, `format_hint`, `example`) are included in this suffix when present.
    - These annotations are prompt guidance only and do not change runtime contract validation semantics.
  - Do not modify files on disk; only the composed prompt is delivered to the provider.

- Adjudicated provider prompt and evaluator delivery (v2.11)
  - Each candidate uses the ordinary provider prompt composition contract, including step-wide `asset_depends_on`, `depends_on`, `consumes` injection, and deterministic output-contract suffixes. A candidate `asset_file` or `input_file` override replaces only the base prompt source.
  - Candidate provider commands run with `cwd` set to that candidate's isolated workspace. Provider templates, provider params, env, secrets, and prompt transport otherwise follow the normal provider contract.
  - The evaluator prompt is composed from the declared evaluator prompt source plus one runtime-built `Evaluator Packet` block. The evaluator output is strict JSON and does not use the adjudicated step's `output_capture`, `allow_parse_error`, `expected_outputs`, or `output_bundle` settings.
  - Evaluator scoring uses the persisted scorer snapshot and complete embedded score-critical evidence only: rendered candidate prompt, declared output value files, required relpath targets, bundle JSON and required bundle targets, optional rubric content, and injected consume relpath target content when applicable.
  - Evaluators must not depend on reading candidate or parent workspace files, bounded prompt previews, candidate stdout/stderr, transport logs, or other non-scoring sidecars. Those paths may be retained for audit, but they are not score-critical evidence.

- Reusable-call provider boundary
  - `asset_file` and `asset_depends_on` resolve relative to the authored workflow file and must stay within that workflow source tree.
  - `input_file` and plain `depends_on` remain workspace-relative, even under `call`.
  - Imported workflows bring private `providers` namespaces; caller/callee provider-template name collisions do not merge unless a later contract adds explicit binding rules.
  - The first `call` tranche is inline and non-isolating: provider child processes may still perform undeclared filesystem reads/writes permitted by the OS.
  - Caller and callee are expected to use the same DSL version in the first tranche.

- Placeholder and parameter substitution
  - Substitution pipeline:
    1) Compose prompt from the selected base prompt source plus any source/workspace dependency injection.
    2) Merge `providers.<name>.defaults` overlaid by `step.provider_params` (step wins).
    3) Substitute inside `provider_params` values (strings only; recursively visit arrays/objects; non-strings unchanged).
    4) Substitute template tokens: `${PROMPT}` (argv mode only), `${SESSION_ID}` (resume-command only), `${<provider_param>}`, and `${run|context|loop|steps.*}`.
    5) Apply escapes before substitution: `$$` → `$`, `$${` → `${`.
    6) Any unresolved `${...}` after substitution fails validation (exit 2) and records `error.context.missing_placeholders` (bare keys) or `invalid_prompt_placeholder` when `${PROMPT}` appears in stdin mode.

- Exit codes
  - 0 = success
  - 1 = retryable API error
  - 2 = invalid input (non-retryable)
  - 124 = timeout (retryable)

- Arg length guidance
  - Large prompts or content injection may exceed argv limits; prefer `input_mode: 'stdin'` for such cases.
  - The orchestrator does not auto-fallback; input mode is explicit per template.

- Timeouts
  - When `timeout_sec` is set, the orchestrator enforces it: sends a graceful termination signal and then a hard kill after a short grace period. Records exit code `124` and timeout context in state.

- Examples
- Claude: `command: ["claude","-p","${PROMPT}","--model","${model}"]`, defaults `{ model: "claude-opus-4-6" }`.
- Claude summary alias: `command: ["claude","-p","${PROMPT}","--model","${model}"]`, defaults `{ model: "claude-sonnet-4-6" }`.
- Codex CLI: `command: ["codex","exec","--dangerously-bypass-approvals-and-sandbox","--model","${model}","--config","reasoning_effort=${reasoning_effort}"]`, `input_mode: 'stdin'` (prompt via stdin).
- Codex session-capable CLI (v2.10): `session_support.fresh_command: ["codex","exec","--json",...]`, `session_support.resume_command: ["codex","exec","resume","${SESSION_ID}","--json",...]`.

## Direct CLI Integration (details)

Workflow-level templates:
```yaml
providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    defaults:
      model: "claude-opus-4-6"
  gemini:
    command: ["gemini", "-p", "${PROMPT}"]
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--model", "${model}", "--config", "reasoning_effort=${reasoning_effort}"]
    input_mode: "stdin"
    defaults:
      model: "gpt-5.3-codex"
      reasoning_effort: "high"
```

Step-level usage:
```yaml
steps:
  - name: Analyze
    provider: "claude"
    provider_params:
      model: "claude-3-5-sonnet"
    input_file: "prompts/analyze.md"
    output_file: "artifacts/architect/analysis.md"

  - name: ManualCommand
    command: ["claude", "-p", "Special prompt", "--model", "claude-opus-4-1-20250805"]

  - name: PingWithCodex
    provider: "codex"
    input_file: "prompts/ping.md"
    output_file: "artifacts/codex/ping_output.txt"
```

Parameter handling: If a provider template does not reference a given `provider_params` key, the parameter is ignored with a debug log entry; not a validation error.

## Provider File Operations

Providers can read and write files directly from/to the filesystem while also outputting to STDOUT. These capabilities coexist:

1. Direct File Operations: Providers may create, read, or modify files anywhere in the workspace based on prompt instructions.
2. STDOUT Capture: The `output_file` parameter captures STDOUT (typically logs, status messages, or reasoning process).
3. Simultaneous Operation: A provider invocation may write multiple files AND produce STDOUT output.

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

- Use `output_file` to capture execution logs and agent reasoning for debugging.
- Design prompts to write primary outputs as files to appropriate directories.
- Use subsequent steps to discover and validate created files.
- Document expected file outputs in step comments for clarity.

## Provider Templates — Quick Reference

| Provider | Command template | Input mode | Notes |
| --- | --- | --- | --- |
| claude | `claude -p ${PROMPT} --model ${model}` | argv | Default model via provider defaults (e.g., `claude-opus-4-6`) or CLI config/env. |
| claude_sonnet_summary | `claude -p ${PROMPT} --model ${model}` | argv | Built-in observability summary alias. Default model: `claude-sonnet-4-6`. Advisory only; not for control-flow gates. |
| gemini | `gemini -p ${PROMPT}` | argv | Model selection may not be supported via CLI; rely on CLI configuration if applicable. |
| codex | `codex exec --dangerously-bypass-approvals-and-sandbox --model ${model} --config reasoning_effort=${reasoning_effort}` (prompt via stdin) | stdin | Reads prompt from stdin; `${PROMPT}` must not appear in template. Built-in defaults are `model: gpt-5.3-codex`, `reasoning_effort: high` (can be overridden in workflow/defaults/provider_params). Use only for trusted workflow workspaces because it disables Codex's own approval and sandbox layer. |

Exit code mapping:
- 0 = Success
- 1 = Retryable API error
- 2 = Invalid input (non-retryable)
- 124 = Timeout (retryable)
