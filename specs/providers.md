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
  - `provider` may contain `${run|context|inputs|steps.*}` substitutions. The resolved provider name is validated immediately before provider template lookup and execution.
  - Provider aliases resolve in the active workflow provider namespace. Imported workflows do not inherit or merge caller provider templates; pass role choices through declared inputs and define supported aliases inside the callee.
  - v2.10 top-level provider steps may also declare `provider_session` to select either `session_support.fresh_command` or `session_support.resume_command`.
  - In this tranche, `provider_session` steps require a static provider alias because loader-time session-support validation must inspect the provider template.
  - Provider steps with `output_bundle.path` or `variant_output.path` receive the runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding for the resolved workspace-relative bundle target. The runtime creates or validates the declared parent directory before launch, and that declared bundle file remains the only structured-output authority.
  - For v2.15 contracts, provider prompt composition renders validated
    effect-boundary `guidance`, field guidance, ordered `guidance_context`, and
    discriminant-ordered `guidance_by_variant` as data in the output-contract
    suffix. It does not render top-level workflow `result_guidance`, and no
    guidance container changes the value schema or bundle authority.
  - `provider_session` command selection changes only the provider command template. It preserves any preexisting runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding on the prepared invocation.
  - v2.13 provider steps may declare `managed_jobs` as a step modifier. The provider template remains ordinary; after existing provider and provider-session command selection, the runtime wraps the selected invocation with the managed-job guard and owns audit/recovery state.
  - `managed_jobs` wrapping preserves any preexisting runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding while adding `MANAGED_JOB_*` transport metadata. Guard state, audit files, and provider-session spools are not alternate structured-output authorities.
  - In argv mode, `${PROMPT}` is replaced by the composed prompt (see below).
  - In stdin mode, the composed prompt is piped to the child stdin; provider templates MUST NOT include `${PROMPT}`.
  - Provider prompt sources are distinct from workflow-boundary `inputs` / `outputs`, runtime dependencies (`depends_on`, `consumes`), and artifact storage / lineage (`artifacts`, `expected_outputs`, `output_bundle`, `publishes`).
  - Reusable-workflow prompt assets:
    - `input_file` stays workspace-relative and is for workspace-owned or runtime-generated prompt material.
    - `asset_file` is the workflow-source-relative prompt/template surface for bundled reusable-workflow assets.

- Workflow Lisp call-local provider policy
  - Ordinary Workflow Lisp `provider-result` may author the closed canonical
    options `model` and `effort`, plus a positive literal timeout. The compiler
    carries only present model/effort values in the internal
    `provider_call_policy` mapping; timeout remains the existing common
    `timeout_sec` field. Complete absence emits neither field and preserves the
    provider template's existing defaults and argv behavior.
  - `ProviderTemplate.call_policy_bindings` is declarative provider data. Its
    keys are exactly `model` and `effort`, and each value must be a public
    `CallPolicyBinding(target_param: str, argv_fragment: Sequence[str] | None)`
    imported from `orchestrator.providers`. Programmatic custom templates must
    construct that dataclass; arbitrary dictionaries are invalid. Both built-in
    registry initialization and public registration run the same validation.
    The public construction contract is:
    ```python
    from orchestrator.providers import CallPolicyBinding, ProviderTemplate

    custom = ProviderTemplate(
        name="custom",
        command=["custom", "--model", "${model}"],
        call_policy_bindings={
            "model": CallPolicyBinding(target_param="model"),
        },
    )
    ```
  - `target_param` is one non-reserved bare provider-parameter identifier, not a
    `${...}` token. General command placeholder extraction continues to accept
    dotted runtime/context placeholders such as `${inputs.model}` and
    `${steps.Prepare.output}`; only `target_param` uses the separate bare-name
    validator. Targets are unique across one declaration and need not have a
    provider default.
  - Declaration validation counts unescaped placeholders after the ordinary
    command-token escape processing. A direct binding requires exactly one
    `${<target_param>}` in every applicable base, fresh-session, and
    resume-session command. A fragment binding requires zero such placeholders
    in those commands and exactly one dynamic placeholder—the matching target—in
    its ordered `argv_fragment`. Missing, duplicate, mismatched, extra, reserved,
    or non-string fragment placeholders reject registration.
  - Preparation translates canonical values without substitution, then performs
    exactly one merge with precedence `provider defaults < provider_params <
    translated canonical overrides`. It applies the existing parameter
    substitution exactly once to that merged mapping, appends present fragments
    in canonical `model`, then `effort` order, and invokes the existing command
    builder. The existing substitution owner retains `substitution_error`.
  - A present canonical option without a declared binding fails before process or
    session creation with exit `2` and
    `error.type: provider_call_policy_unsupported`. Its bounded context contains
    only the resolved provider identifier and canonical option; enclosing
    provider-result provenance may be retained, but policy values, prompts,
    secrets, and invented field spans may not be exposed.
  - Authored YAML/YML reserves and rejects both the internal step key
    `provider_call_policy` and provider-template key `call_policy_bindings`.
    Existing YAML `provider_params` behavior is unchanged.

- Shared unrestricted invocation profiles
  - `codex_unrestricted_workspace` has no defaults, uses stdin, binds
    `model -> model` and `effort -> reasoning_effort`, and has exact command
    `["codex", "exec", "--dangerously-bypass-approvals-and-sandbox",
    "--skip-git-repo-check", "--model", "${model}", "--config",
    "reasoning_effort=${reasoning_effort}"]`.
  - `claude_unrestricted_workspace` has no defaults, uses stdin, binds
    `model -> model` and `effort -> effort`, and has exact command
    `["claude", "-p", "--model", "${model}", "--effort", "${effort}",
    "--permission-mode", "bypassPermissions"]`.
  - These profiles are generic provider data. Their presence does not prove
    workflow-family parity, promotion eligibility, or YAML deletion.

- Managed provider job policy YAML (v2.13)
  - `managed_jobs.policy` points to workspace-relative YAML that classifies payloads launched by the guarded provider process. It is separate from provider-template YAML.
  - Minimal explicit-metadata shape:
    ```yaml
    backend_defaults:
      backend: local        # auto|local|slurm
    entries:
      - id: train_model
        mode: force_managed # force_managed|auto_managed|force_local|unmanaged
        path: scripts/training/train.py
        backend: slurm      # optional override; auto|local|slurm
        job:
          name_template: train-{job_identity_hash}
          state_root_template: state/managed_jobs/{entry_id}/{job_identity_hash}
          output_root_arg: --output-dir
          verify_files:
            - "{output_root}/metrics.json"
          snapshot_roots:
            - scripts/training
          config_globs:
            - configs/training/*.yaml
    ```
  - Named extractors may be declared under top-level `extractors` and referenced from an entry with `extractor: <name>` instead of inline `job` metadata.
  - Managed modes (`force_managed`, `auto_managed`) require complete `job` metadata or an `extractor` that derives the same metadata. Missing state root, verification targets, snapshot inputs, or extractor output is invalid before launch.
  - Unmanaged modes (`force_local`, `unmanaged`) run locally through the original payload path and do not append managed-job audit events.
  - `state_root_template` and snapshot/config paths are workspace-relative and path-safe. `state_root_template` may use `{entry_id}` and `{job_identity_hash}`.
  - Job identity includes normalized payload arguments, source hashes, config hashes, extractor identity/version, policy-entry hash, and snapshot manifest inputs.
  - `backend: local` executes the payload from the immutable snapshot workspace and records the same identity metadata as Slurm. `backend: slurm` generates a snapshot-bound submission script or a script with preflight source/config hash checks.
  - Supported shim payloads are direct `python`, `python3`, and `torchrun`; `conda run ... python|torchrun ...`; and `uv run python|torchrun ...`. Unsupported `conda`/`uv` forms fail closed unless explicitly classified unmanaged.

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
    - Each selected `consumes[*]` row may also declare `prompt.mode: content|reference|none` plus additive prompt guidance (`label`, `description`, `format_hint`, `example`, `role`).
    - Omitted `prompt.mode` defaults to `content`. Nested `prompt.*` guidance overrides row-level `description`, `format_hint`, and `example` when both are present.
    - `content` preserves ordinary consumed-artifact prompt rendering for the selected resolved value.
    - `reference` renders deterministic metadata only (`mode: reference`, artifact identity, optional label/role/guidance, and the resolved value/path). It must not read or embed relpath target body content in the candidate prompt.
    - `none` suppresses only candidate-prompt text for that consume row. It does not change consume selection, lineage, freshness, resolved values, or `consume_bundle`.
    - If every selected consume row resolves to `mode: none`, omit the consumed-artifacts block entirely.
    - Footer text depends on the rendered row mix:
      - content-only rows: use the consumed artifacts as prompt context
      - reference-only rows: open referenced artifacts only when needed
      - mixed content/reference rows: use embedded content as context and open references only when needed
    - Scalar values render directly; list/map consume values render as deterministic JSON text. Prompt rendering is a view over resolved consume values, not semantic authority.
    - These annotations and render modes are prompt guidance only and do not change runtime consume enforcement semantics.
    - v2.10 resume steps reserve the `session_id_from` consume for runtime `${SESSION_ID}` binding; that consume is excluded from prompt injection and `consume_bundle`.
  - If the step defines `expected_outputs`, `output_bundle`, or `variant_output` and `inject_output_contract` is not `false`, append a deterministic `Output Contract` or `Variant Output Contract` suffix describing required artifacts (`name`, `path`, `type`, optional constraints) or the required JSON bundle (`path`, `fields[*].json_pointer`, `fields[*].type`, optional constraints).
    - An `output_bundle` whose sole field uses `json_pointer: ""` (a direct
      root value) renders a "write one JSON value" suffix describing the root
      type and its resolved path, not an object/`fields:` list — the prompt
      never claims a JSON object for a scalar/enum/relpath/optional/list/map
      root result, and never names or requests the compiler-owned `__result__`
      field key.
    - `expected_outputs.path`, `output_bundle.path`, and `variant_output.path` entries in this suffix are rendered after applying the same runtime variable substitution used for output-contract validation, so provider prompts show workspace-relative concrete paths rather than unresolved `${...}` templates.
    - Optional `expected_outputs` guidance annotations (`description`, `format_hint`, `example`) are included in this suffix when present.
    - These annotations and rendered concrete paths are prompt guidance only. Prompt text does not replace the runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding or change runtime contract validation semantics.
  - Do not modify files on disk; only the composed prompt is delivered to the provider.

- Adjudicated provider prompt and evaluator delivery (v2.11)
  - Each candidate uses the ordinary provider prompt composition contract, including step-wide `asset_depends_on`, `depends_on`, `consumes` injection, and deterministic output-contract suffixes. A candidate `asset_file` or `input_file` override replaces only the base prompt source.
  - Candidate provider commands run with `cwd` set to that candidate's isolated workspace. Provider templates, provider params, env, secrets, and prompt transport otherwise follow the normal provider contract.
  - The evaluator prompt is composed from the declared evaluator prompt source plus one runtime-built `Evaluator Packet` block. The evaluator output is strict JSON and does not use the adjudicated step's `output_capture`, `allow_parse_error`, `expected_outputs`, or `output_bundle` settings.
  - Evaluator scoring uses the persisted scorer snapshot and complete embedded score-critical evidence only: rendered candidate prompt, declared output value files, required relpath targets, bundle JSON and required bundle targets, optional rubric content, and selected consume values plus consume relpath target content when applicable.
  - Candidate-prompt consume rendering modes do not weaken evaluator evidence. After reserved-session exclusion and `prompt_consumes` filtering choose the selected consume rows, evaluator packets continue to carry the normalized selected consume values and any selected relpath target file content even when the candidate prompt rendered a row as `reference` or suppressed it with `none`.
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
    2) Translate any compiler-owned canonical call policy declaratively, without substitution.
    3) Merge `providers.<name>.defaults`, then `step.provider_params`, then translated canonical overrides (rightmost wins).
    4) Substitute inside the one merged parameter mapping exactly once (strings only; recursively visit arrays/objects; non-strings unchanged).
    5) Select the command variant and append any present canonical fragments in `model`, then `effort` order.
    6) Protect each selected command-template token with the provider command escape processing before any placeholder scan: escaped `$$` and `$${...}` become protected literal tokens rather than substitution candidates.
    7) Extract only unescaped placeholders from that protected representation. Provider declaration validation uses this same extraction to enforce exact binding consumption. Invocation substitutes the command template once: `${SESSION_ID}` only for a resume command, merged `${<provider_param>}` and `${run|context|loop|steps.*}` values, then literal `${PROMPT}` delivery in argv mode after other substitutions so prompt content is not rescanned.
    8) Restore the protected escaped dollar and braced-dollar literals only after command-template substitution. Any unresolved unescaped `${...}` fails validation (exit 2) and records bounded `error.context.missing_placeholders` (bare keys); `${PROMPT}` in stdin mode records `invalid_prompt_placeholder`.

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
  - Managed provider invocations run in a process group/session boundary so a timeout terminates the guard and its provider child process tree. Already-submitted managed jobs are recovered from persisted managed-job state rather than by relaunching the provider.

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
      model: "gpt-5.4"
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
| claude_haiku_summary | `claude -p ${PROMPT} --model ${model}` | argv | Built-in low-cost observability summary alias. Default model: `claude-3-5-haiku-20241022`. Advisory only; not for control-flow gates. |
| gemini | `gemini -p ${PROMPT}` | argv | Model selection may not be supported via CLI; rely on CLI configuration if applicable. |
| codex | `codex exec --dangerously-bypass-approvals-and-sandbox --model ${model} --config reasoning_effort=${reasoning_effort}` (prompt via stdin) | stdin | Reads prompt from stdin; `${PROMPT}` must not appear in template. Built-in defaults are `model: gpt-5.4`, `reasoning_effort: high` (can be overridden in workflow/defaults/provider_params). Use only for trusted workflow workspaces because it disables Codex's own approval and sandbox layer. |

Exit code mapping:
- 0 = Success
- 1 = Retryable API error
- 2 = Invalid input (non-retryable)
- 124 = Timeout (retryable)
