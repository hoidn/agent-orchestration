# Workflow DSL and Control Flow (Normative)

- Top-level workflow keys
  - `version`: string (e.g., "1.1", "1.1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "2.0", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", or "2.10"). Strict gating: unknown fields at a given version → validation error (exit 2).
  - `name`: optional string.
  - `strict_flow`: boolean (default true). Non-zero exit halts the run unless `on.failure.goto` is present.
  - `providers`: map of provider templates (see `providers.md`).
  - Queue defaults: `inbox_dir`, `processed_dir`, `failed_dir`, `task_extension` (see `queue.md`).
  - `context`: key/value map available via `${context.*}` (see `variables.md`).
  - `inputs`: workflow-boundary input contracts (v2.1+).
    - Separate contract family from runtime dependencies, provider prompt sources, and the v1.2+ artifact registry; no pointer semantics.
    - Keys are input names; values reuse typed contract fields:
      - `kind: relpath|scalar` (optional; default `relpath`)
      - `type: enum|integer|float|bool|string|relpath` (required)
      - `allowed: string[]` (enum only)
      - `under`, `must_exist_target` (relpath only)
      - `required: boolean` (optional; default true)
      - `default` (optional)
      - `description: string` (optional)
    - Preferred authoring style for relpath boundaries: use `type: relpath` alone; explicit `kind: relpath` remains valid for backward compatibility.
    - Successful binding is exposed inside the workflow through `${inputs.<name>}` and typed `ref: inputs.<name>`.
  - `outputs`: workflow-boundary output contracts (v2.1+).
    - Keys are output names; values reuse the same typed contract fields as `inputs` plus required `from`.
    - Preferred authoring style for relpath boundaries: use `type: relpath` alone; explicit `kind: relpath` remains valid for backward compatibility.
    - `from` must be exactly `{ ref: "root.steps.<Step>.artifacts.<name>|exit_code|outcome.<field>" }`.
    - Export validation runs after the workflow body completes successfully and, for v2.3+ workflows with `finally`, only after finalization completes successfully.
  - `imports`: reusable workflow aliases (v2.5+).
    - Shape: `{ <alias>: "<workflow-source-relative path>" }`.
    - Import paths resolve relative to the directory containing the authored workflow file and must remain within WORKSPACE.
    - Imported workflows validate independently and, in the first `call` tranche, caller and callee must declare the same DSL version.
    - Imported workflows keep their own private `providers`, `artifacts`, and `context` defaults at runtime.
  - `finally`: structured workflow finalization (v2.3+).
    - Accepts either `Step[]` or `{ id?, steps: Step[] }`.
    - `id` uses the same pattern as step `id`.
    - Finalization steps are recorded under `finally.<StepName>` presentation keys and durable `step_id` ancestry rooted under `root.finally.<block-id-or-finally>`.
    - First tranche restrictions:
      - top-level only
      - `goto` / `_end` routing inside finalization steps is rejected
      - workflow outputs remain unmaterialized until finalization succeeds and are suppressed on finalization failure
  - `artifacts`: map of named artifact contracts (v1.2+).
    - `kind: relpath|scalar` (optional; default `relpath`)
    - `type: enum|integer|float|bool|string|relpath` (required)
    - `kind: relpath`:
      - requires `type: relpath`
      - requires `pointer: string` (canonical pointer file path, usually under `state/`)
      - optional constraints: `under`, `must_exist_target`
    - `kind: scalar`:
      - supports only `type: enum|integer|float|bool|string`
      - forbids `pointer`, `under`, and `must_exist_target`
    - `allowed: string[]` required for enum artifacts
  - `steps`: ordered list of step objects.
  - `max_transitions: integer` (v1.8+; optional; must be `> 0`)
    - Counts routed transfers between settled top-level steps.
    - Terminal workflow completion does not consume another transition.
    - When exceeded, the target step fails pre-execution with `error.type: "cycle_guard_exceeded"`.
  - `observability` is intentionally not a DSL key; run observability is configured via CLI/runtime flags (see `cli.md`).

- Step schema (consolidated; MVP + v1.1.1)
  - Required: `name: string`.
  - Optional metadata: `agent: string` (informational).
  - Optional stable identity: `id: string` (v2.0+; unique within the lexical sibling scope; pattern `[A-Za-z][A-Za-z0-9_]*`)
  - Execution (mutually exclusive in a single step):
    - `provider: string` (+ optional `provider_params`) OR
    - `command: string[]` OR
    - `assert: Condition|TypedPredicate` (v1.5+; exclusive with provider/command/wait_for/for_each) OR
    - `set_scalar: { artifact, value }` (v1.7+; exclusive with provider/command/wait_for/assert/for_each) OR
    - `increment_scalar: { artifact, by }` (v1.7+; exclusive with provider/command/wait_for/assert/for_each) OR
    - `wait_for: { ... }` (exclusive with provider/command/for_each)
    - Reusable execution form (v2.5; contract fixed in v2.4 docs):
      - `call: <import alias>`
      - `with: { <callee-input-name>: Literal|{ref} }`
      - first tranche requires an authored stable `id` on the outer call step so call-frame identities survive sibling insertion or import-alias reshaping
      - only declared callee `outputs` cross the boundary back to the caller
  - Structured control (v2.2+):
    - top-level `if: Condition|TypedPredicate`
    - `then: Step[] | { id?, steps: Step[], outputs: WorkflowOutputMap }`
    - `else: Step[] | { id?, steps: Step[], outputs: WorkflowOutputMap }`
    - branch `id` uses the same pattern as step `id`
    - branch-local steps are visible only inside that branch's local scope; downstream refs must target `root.steps.<Statement>.artifacts.<name>` from the statement outputs
    - first tranche restrictions:
      - top-level only
      - `goto` / `_end` are rejected inside branch steps
      - branch outputs must use matching contracts across `then` and `else`
    - v2.6 top-level `match:`
      - `ref: StructuredRef` resolving to an enum artifact or input
      - `cases: { <allowed-enum-value>: Step[] | { id?, steps: Step[], outputs: WorkflowOutputMap } }`
      - case `id` uses the same pattern as step `id`
      - case-local steps are visible only inside that case's local scope; downstream refs must target `root.steps.<Statement>.artifacts.<name>` from the statement outputs
      - first tranche restrictions:
        - top-level only
        - `goto` / `_end` are rejected inside case steps
        - `cases` must cover every allowed enum value on the selected ref
        - case outputs must use matching contracts across every case
    - v2.7 top-level `repeat_until:`
      - shape: `{ id?, outputs: WorkflowOutputMap, condition: TypedPredicate, max_iterations: integer, steps: Step[] }`
      - `repeat_until.id` uses the same pattern as step `id`
      - post-test semantics: iteration `0` always executes once, then `condition` is evaluated after each completed iteration
      - `condition` must be a typed predicate and may read loop-frame outputs through `self.outputs.<name>`
      - `condition` must not bypass the loop frame by reading `self.steps.<Inner>...` directly
      - selected iteration outputs are materialized onto the loop frame itself and become available at `root.steps.<Statement>.artifacts.<name>`
      - first tranche restrictions:
        - top-level only
        - `goto` / `_end` are rejected inside body steps
        - nested `for_each` and nested `repeat_until` are rejected inside the body
        - direct nested `call`, `match`, and `if/else` bodies are lowered into loop-local executable nodes; body-local structured refs stay on `self.steps.*` and outer lexical refs stay on `parent.steps.*`
  - Cycle guards:
    - `max_visits: integer` (v1.8+; optional; must be `> 0`)
    - First tranche is limited to top-level non-`for_each` steps.
    - Visit counts increment after `when` evaluation and before consume/execution preflight; skipped steps do not consume visit budget, internal retries do not consume extra visits.
    - When exceeded, the step fails pre-execution with `error.type: "cycle_guard_exceeded"`.
  - IO:
    - `input_file: string`
      - Provider-only workspace-relative prompt source for workspace-owned or runtime-generated prompt material, even when the workflow later runs under `call`.
    - `asset_file: string` (v2.5+)
      - Provider-only workflow-source-relative prompt/template asset for bundled reusable-workflow material.
      - Mutually exclusive with `input_file`.
      - Resolves relative to the directory containing the authored workflow file and must remain within that workflow source tree.
    - `output_file: string`
      - Workspace-relative runtime path. `call` namespaces step/result identities, not authored output files.
    - `asset_depends_on: string[]` (v2.5+)
      - Provider-only list of exact workflow-source-relative reference files injected into the composed prompt.
      - Not a substitute for workspace-relative `depends_on`.
      - No globbing or optional/mode variants in the first tranche; the author controls the exact ordered file list.
    - `output_capture: text|lines|json` (default text)
    - `allow_parse_error: boolean` (json mode only)
    - `expected_outputs: ExpectedOutput[]` (optional deterministic artifact contracts)
      - `name: string` (required artifact key; exposed at `steps.<Step>.artifacts.<name>` when artifact persistence is enabled)
      - `path: string` (required, relative file written by the step)
      - `type: enum|integer|float|bool|string|relpath` (required)
      - `bool` token policy: case-insensitive `true|false|1|0|yes|no`
      - `allowed: string[]` (required when `type: enum`)
      - `under: string` (optional root for `relpath` target validation)
      - `must_exist_target: boolean` (optional, `relpath` only)
      - `required: boolean` (optional, default true; when false, missing file is allowed)
      - `description: string` (optional prompt guidance; no runtime validation impact)
      - `format_hint: string` (optional prompt guidance; no runtime validation impact)
      - `example: string` (optional prompt guidance; no runtime validation impact)
      - Runtime enforcement runs only when the step process exits with code `0`.
      - Path checks are canonicalized (`resolve`) and must remain under WORKSPACE.
    - `persist_artifacts_in_state: boolean` (optional; default true)
      - When true (default), validated `expected_outputs` are mirrored into `steps.<Step>.artifacts` in `state.json`.
      - When false, `expected_outputs` are still fully validated, but artifact values are not duplicated into `state.json`.
      - Use this when on-disk files (for example `state/*.txt` pointers) are the intended single source of truth.
      - Steps that declare `publishes` must keep this as `true` (or omit it) so publish runtime can read `steps.<Step>.artifacts`.
    - `inject_output_contract: boolean` (optional; default true)
      - Consumed only by provider steps to control prompt suffix injection.
      - Accepted on non-provider steps as a compatibility no-op.
    - `inject_consumes: boolean` (optional; default true; v1.2+)
      - Provider steps only: controls automatic consumed-artifact prompt block injection for steps with `consumes`.
    - `consumes_injection_position: prepend|append` (optional; default `prepend`; v1.2+)
      - Provider steps only: controls where the consumed-artifact block is placed relative to prompt body.
    - `prompt_consumes: string[]` (optional; v1.2+)
      - Provider steps only: subset of `consumes[*].artifact` that should be injected into prompt text.
      - If omitted, all resolved consumed artifacts are injected (backward-compatible default).
      - If `[]`, no consumed-artifacts prompt block is injected.
    - `output_bundle` (optional; v1.3+): deterministic artifacts extracted from one JSON file.
      - `path: string` (required, relative JSON file written by the step)
      - `fields: OutputBundleField[]` (required, non-empty)
      - Mutual exclusion: cannot be combined with `expected_outputs` on the same step.
      - `OutputBundleField`:
        - `name: string` (required artifact key; unique within `fields`)
        - `json_pointer: string` (required RFC 6901 pointer; `""` allowed for root)
        - `type: enum|integer|float|bool|string|relpath` (required)
        - `allowed: string[]` (required when `type: enum`)
        - `under: string` (optional root for `relpath` target validation)
        - `must_exist_target: boolean` (optional, `relpath` only)
        - `required: boolean` (optional, default true; when false, missing pointer is allowed)
      - Runtime enforcement runs only when the step process exits with code `0`.
      - Parsed values are exposed as `steps.<Step>.artifacts` (unless `persist_artifacts_in_state:false`).
    - `consume_bundle` (optional; v1.3+): materialize resolved consumes into one JSON file.
      - `path: string` (required output JSON path under WORKSPACE)
      - `include: string[]` (optional subset of consumed artifact names; default all resolved consumes)
      - Requires step `consumes`; `include` must be subset of `consumes[*].artifact`.
      - Written only after consume preflight succeeds.
    - `provider_session` (optional; v2.10+; provider steps only)
      - valid only on provider steps authored directly under the root workflow `steps:` list
      - `mode: fresh|resume`
      - `mode: fresh` requires `publish_artifact: string`
      - `mode: resume` requires `session_id_from: string`
      - `publish_artifact` and `session_id_from` must name declared top-level scalar `type: string` artifacts
      - `publish_artifact` is a runtime-owned local artifact key and must not collide with `expected_outputs.name`, `output_bundle.fields[*].name`, or `publishes.from`
      - `session_id_from` must match exactly one `consumes[*].artifact`; that reserved consume must omit `freshness` or set it to `any`
      - the reserved `session_id_from` consume is excluded from automatic prompt injection and `consume_bundle`
      - authored `retries` are invalid on session-enabled steps
      - `persist_artifacts_in_state: false` is invalid on fresh session steps
  # Future (post-v1.3): additional JSON stdout validation (opt-in, version-gated)
  # Only valid when enabled in a future version AND `output_capture: json` AND `allow_parse_error` is false
  - `output_schema?: string`                         # Path to JSON Schema under WORKSPACE; variables allowed
  - `output_require?:`                               # Simple built-in assertions on parsed JSON
      - `pointer: string`                            # RFC 6901 JSON Pointer (e.g., "/approved")
      - `exists?: boolean`                           # Default: true; require presence
      - `equals?: string|number|boolean|null`        # Optional exact match
      - `type?: string`                              # One of: string|number|boolean|array|object|null
  - Environment & secrets: see `security.md`.
  - Dependencies: `depends_on: { required[], optional[], inject }` (see `dependencies.md`).
  - Dataflow (v1.2+):
    - `publishes`: list of `{ artifact, from }`
      - `artifact`: artifact name from top-level `artifacts`
      - `from`: local `expected_outputs.name`, `output_bundle.fields[*].name`, or scalar-bookkeeping output artifact name produced by the same step
      - requires `persist_artifacts_in_state` to be `true` for that step
      - runtime: on successful step, publication appends a new artifact version record
    - `consumes`: list of contracts
      - `artifact`: artifact name from top-level `artifacts`
      - `producers: string[]` (optional producer step-name filter)
      - `policy: latest_successful` (MVP)
      - `freshness: any|since_last_consume` (default `any`)
      - `description: string` (optional prompt guidance for consumed-artifact injection; no runtime validation impact)
      - `format_hint: string` (optional prompt guidance for consumed-artifact injection; no runtime validation impact)
      - `example: string` (optional prompt guidance for consumed-artifact injection; no runtime validation impact)
      - runtime preflight:
        - `kind: relpath` artifacts:
          - `version: "1.2"` / `"1.3"`: materialize the selected value to the canonical pointer file
          - `version: "1.4"`: read-only consume resolution (no pointer-file mutation)
        - `kind: scalar` artifacts never write pointer files and use the typed value directly
        - v2.10 `provider_session.mode: resume` reserves one consume for runtime `${SESSION_ID}` binding rather than prompt or consume-bundle output
        - fail with `contract_violation` (exit 2) when missing/stale/type-invalid
  - Control:
    - `timeout_sec: number` (applies to provider/command; exit 124 on timeout)
    - `retries: { max: number, delay_ms?: number }`
    - `when`: condition object; any of
      - `equals: { left: string, right: string }` (string comparison)
      - `exists: string` (POSIX glob; true if ≥1 match within WORKSPACE)
      - `not_exists: string` (POSIX glob; true if 0 matches within WORKSPACE)
      - v1.6 typed predicates:
        - `artifact_bool: { ref: "root.steps.<Step>.artifacts.<name>" }`
        - `compare: { left: Literal|{ref}, op: eq|ne|lt|lte|gt|gte, right: Literal|{ref} }`
        - `all_of: TypedPredicate[]`
        - `any_of: TypedPredicate[]`
        - `not: TypedPredicate`
      - v2.8 score helper:
        - `score: { ref: "root.steps.<Step>.artifacts.<name>", gt?: number, gte?: number, lt?: number, lte?: number }`
      - `score` is thin sugar over numeric `compare` / `all_of`; it requires a numeric structured ref plus at least one bound and may not declare both `gt`+`gte` or both `lt`+`lte`.
      - Initial structured refs are limited to `root.steps.<Step>.artifacts.<name>`, `root.steps.<Step>.exit_code`, and `root.steps.<Step>.outcome.{status|phase|class|retryable}`.
      - Bare `steps.<Name>`, `self.*`, `parent.*`, and untyped `context.*` are invalid in structured predicates for v1.6.
      - v2.0 scoped refs:
        - `root.steps.<Step>...` addresses the root workflow scope
        - `self.steps.<Step>...` addresses the current lexical scope
        - `parent.steps.<Step>...` addresses the immediately enclosing lexical scope
        - bare `steps.<Name>...` remains invalid in the structured `ref:` model
      - v2.1 workflow signatures:
        - `inputs.<name>` addresses one bound workflow input
      - v2.2 structured branch outputs:
        - downstream refs target `root.steps.<IfStatement>.artifacts.<name>`
      - v2.6 structured match outputs:
        - downstream refs target `root.steps.<MatchStatement>.artifacts.<name>`
      - v2.7 structured repeat_until outputs:
        - loop conditions use `self.outputs.<name>`
        - downstream refs target `root.steps.<RepeatUntilStatement>.artifacts.<name>`
    - `assert`: gate object; any of
      - v1.5: legacy `equals|exists|not_exists`
      - v1.6+: legacy conditions or typed predicates
      - False assertions fail the step with `exit_code: 3` and `error.type: "assert_failed"`.
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
  - A step may specify exactly one of `provider`, `command`, `assert`, or `wait_for`.
  - A step may specify exactly one of `provider`, `command`, `assert`, `set_scalar`, `increment_scalar`, or `wait_for`.
  - `assert` is a first-class execution form and cannot be combined with `provider`/`command`/`wait_for`/`for_each` on the same step.
  - `set_scalar` and `increment_scalar` are first-class execution forms and cannot be combined with `provider`/`command`/`wait_for`/`assert`/`for_each` on the same step.
  - `for_each` is a block form and cannot be combined with `provider`/`command`/`wait_for`/`assert` on the same step.
  - `goto` targets must reference an existing step name or `_end`. Unknown targets are a validation error (exit code 2) reported at workflow load time.
  - Deprecated `command_override` is not supported and must be rejected by the loader/validator.
  - Version gating:
    - `depends_on.inject` requires `version: "1.1.1"` or higher.
    - `artifacts`, `publishes`, `consumes`, `inject_consumes`, `consumes_injection_position`, and `prompt_consumes` require `version: "1.2"` or higher.
    - `output_bundle` and `consume_bundle` require `version: "1.3"` or higher.
    - `assert` requires `version: "1.5"` or higher.
    - Typed predicates and structured `ref:` require `version: "1.6"` or higher.
    - `set_scalar` and `increment_scalar` require `version: "1.7"` or higher.
    - `max_transitions` and `max_visits` require `version: "1.8"` or higher.
    - scalar `string`, `provider_session`, and provider `session_support` require `version: "2.10"` or higher.
  - authored step `id` plus scoped `self`/`parent` refs require `version: "2.0"` or higher.
  - top-level `inputs`, `outputs`, and `inputs.*` typed refs require `version: "2.1"` or higher.
  - structured `if` / `then` / `else` require `version: "2.2"` or higher.
  - top-level `finally` requires `version: "2.3"` or higher.
  - structured `match` requires `version: "2.6"` or higher.
  - structured `repeat_until` requires `version: "2.7"` or higher.
  - Advisory authoring-time linting:
    - `orchestrate run --dry-run` and `orchestrate report` may surface non-fatal warnings for migration patterns such as shell gates that should become `assert`, stringly `when.equals` routing that should become typed predicates, raw `goto` diamonds that should become structured control, and imported/exported output-name collisions.
    - Lint warnings are advisory only in the first pass and never change workflow load validity or runtime exit codes.
  - reusable-call contract boundary:
    - Task 10 reserves `imports`, `call`, `with`, `asset_file`, and `asset_depends_on` semantics before execution support lands.
    - When Task 11 lands, those fields require `version: "2.5"` or higher.
    - `version: "2.4"` is a documentation/contract boundary, not a promise that the current loader/runtime executes reusable-call workflows.

- Control flow defaults
  - `strict_flow: true`: any non-zero exit halts unless an applicable `on.failure.goto` exists.
  - `_end`: reserved goto target that terminates the run successfully.
  - Precedence: step `on.*` handlers are evaluated first; if none apply, `strict_flow` and CLI `--on-error` govern.
  - `cycle_guard_exceeded` always stops routed step execution; step-level `on.failure.goto` cannot continue past a tripped guard, even when CLI `--on-error continue` is set.
  - Retry policy defaults: provider steps consider exit codes `1` and `124` retryable; raw `command` steps are not retried unless a per-step `retries` block is set. Step-level settings override CLI/global defaults.

- Loop scoping and state
  - Loop variables inside `for_each`: `${item}` (or alias), `${loop.index}` (0-based), `${loop.total}`.
  - Inside the loop, `${steps.<StepName>.*}` references results from the current iteration only.
  - State storage is indexed per iteration: `steps.<LoopName>[i].<StepName>` (see `state.md`).
  - v2.0 adds durable per-iteration internal identities for lineage/freshness bookkeeping while keeping those indexed keys as compatibility views.

- For-Each pointer syntax
  - Allowed forms: `steps.<Name>.lines` or `steps.<Name>.json[.<dot.path>]`.
  - The referenced value must resolve to an array; otherwise the step fails with exit 2 and error context.
  - Dot-paths do not support wildcards or advanced expressions.

## Planned Reusable-Call Contract Boundary (v2.4 docs, v2.5 execution)

- Path taxonomy
  - Workflow-source-relative paths:
    - `imports`
    - nested import targets
    - `asset_file`
    - `asset_depends_on`
  - Workspace-relative runtime paths:
    - `input_file`
    - `depends_on`
    - `output_file`
    - `expected_outputs.path`
    - `output_bundle.path`
    - `consume_bundle.path`
    - deterministic `relpath` outputs and authored `state/*` / `artifacts/*` paths
  - `call` does not reinterpret authored workspace-relative paths; it only introduces call-scoped identities for state, lineage, freshness, and logs.

- Boundary semantics
  - `call` executes inline within the same run once Task 11 lands.
  - Caller-visible results remain on the outer step at `steps.<CallStep>.artifacts.<output-name>`.
  - Only declared callee `outputs` cross back into the caller.
  - Imported workflow `providers`, `artifacts`, and `context` defaults remain private to the callee unless a future contract explicitly binds or exports them.
  - The first tranche requires caller/callee same-version execution to avoid mixed-version lowering and state semantics.

- Accepted-risk constraint
  - Reusable workflows may still include `command` and `provider` steps.
  - The first tranche does not claim sandboxing or loader-proved isolation of child-process filesystem effects.
  - Every DSL-managed reusable-workflow write root that must remain distinct across invocations is expected to be surfaced as a typed `relpath` workflow input and bound explicitly by each call site.
  - Call sites are expected to bind distinct per-invocation values whenever repeated or concurrent calls could otherwise alias the same managed paths.

## Workflow Schema (Top-Level)

```yaml
version: string                 # Workflow DSL version (e.g., "1.1"); independent of state schema_version
name: string                    # Human-friendly name
strict_flow: boolean            # Default: true; non-zero exit halts unless on.failure.goto present
context: { [key: string]: any } # Optional key/value map available via ${context.*}
max_transitions: integer        # v1.8+ optional workflow-level cycle budget (> 0)
inputs: { [name: string]: WorkflowInput }   # v2.1+ workflow-boundary typed inputs
outputs: { [name: string]: WorkflowOutput } # v2.1+ workflow-boundary typed outputs
imports: { [alias: string]: string }        # v2.5 reusable workflow aliases (workflow-source-relative)

# v1.2+: canonical artifact contracts for publish/consume dataflow
artifacts:                      # Optional
  <artifact-name>:
    kind: relpath|scalar        # Optional, default relpath
    type: string                # enum|integer|float|bool|string|relpath
    pointer: string             # Required for kind=relpath; forbidden for kind=scalar
    allowed: string[]           # enum only
    under: string               # kind=relpath only (optional)
    must_exist_target: boolean  # kind=relpath only (optional)

# Provider templates available to steps
providers:                      # Optional
  <provider-name>:
    command: string[]           # May include ${PROMPT} in argv mode
    input_mode: argv|stdin      # Default: argv
    defaults: { [key: string]: any }
    session_support:            # v2.10+ optional provider-session command variants
      metadata_mode: string
      fresh_command: string[]
      resume_command: string[]  # Optional unless a resume-capable step uses this provider

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
