# Providers and Prompt Delivery (Normative)

- Provider templates
  - Define CLI command and input mode:
    - `command: string[]` may reference `${PROMPT}` in argv mode.
    - `input_mode: 'argv' | 'stdin'` (default: 'argv').
  - `defaults`: map of provider parameters (e.g., `model`).

- Step usage
  - `provider: <name>` uses the template; merge `defaults` overlaid by `provider_params` (step wins).
  - In argv mode, `${PROMPT}` is replaced by the composed prompt (see below).
  - In stdin mode, the composed prompt is piped to the child stdin; provider templates MUST NOT include `${PROMPT}`.

- Prompt composition
  - Read `input_file` literally.
  - Apply dependency injection in-memory if `depends_on.inject` is enabled (see `dependencies.md`).
  - Do not modify files on disk; only the composed prompt is delivered to the provider.

- Placeholder and parameter substitution
  - Substitution pipeline:
    1) Compose prompt from `input_file` and optional dependency injection.
    2) Merge `providers.<name>.defaults` overlaid by `step.provider_params` (step wins).
    3) Substitute inside `provider_params` values (strings only; recursively visit arrays/objects; non-strings unchanged).
    4) Substitute template tokens: `${PROMPT}` (argv mode only), `${<provider_param>}`, and `${run|context|loop|steps.*}`.
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
  - Claude: `command: ["claude","-p","${PROMPT}","--model","${model}"]`, defaults `{ model: "claude-sonnet-4-20250514" }`.
  - Codex CLI: `command: ["codex","exec"]`, `input_mode: 'stdin'` (prompt via stdin).

## Direct CLI Integration (details)

Workflow-level templates:
```yaml
providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    defaults:
      model: "claude-sonnet-4-20250514"
  gemini:
    command: ["gemini", "-p", "${PROMPT}"]
  codex:
    command: ["codex", "exec"]
    input_mode: "stdin"
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
| claude | `claude -p ${PROMPT} --model ${model}` | argv | Default model via provider defaults (e.g., `claude-sonnet-4-20250514`) or CLI config/env. |
| gemini | `gemini -p ${PROMPT}` | argv | Model selection may not be supported via CLI; rely on CLI configuration if applicable. |
| codex | `codex exec` (prompt via stdin) | stdin | Reads prompt from stdin; `${PROMPT}` must not appear in template. Defaults (e.g., `model: gpt-5`) may be provided in provider defaults or via Codex CLI config. |

Exit code mapping:
- 0 = Success
- 1 = Retryable API error
- 2 = Invalid input (non-retryable)
- 124 = Timeout (retryable)
