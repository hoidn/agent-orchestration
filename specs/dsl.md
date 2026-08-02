# Workflow DSL and Control Flow (Normative)

## Authored frontend and persisted compatibility boundary

Fresh workflow execution accepts only Workflow Lisp source whose path suffix,
compared case-insensitively, is `.orc`. `run` rejects YAML/YML and every other
non-`.orc` path with a diagnostic containing `.orc required` before creating
run state. The production YAML parser is retired.

`resume` loads the selected run's persisted state before applying the frontend
boundary. Once state is loaded, every recorded workflow suffix other than
`.orc` fails closed with `.orc required`, regardless of run terminality or
force-restart selection. A non-`.orc` source is neither compiled nor executed.
`report` and dashboard surfaces remain state-only observability for legacy
runs, but must not parse authored YAML to reconstruct workflow semantics.

The schema below remains the normative Core workflow contract produced by the
`.orc` compiler and consumed by shared validation/runtime code. YAML-fenced
snippets are structural notation for that mapping, not accepted fresh workflow
source.

- Top-level workflow keys
  - `version`: string (supported revisions extend through `"2.25"`). Strict gating: unknown fields at a given version -> validation error (exit 2).
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
    - v2.19 additionally accepts the exact opaque pair `kind: value`,
      `type: value`. It forbids `allowed`, `under`, `must_exist_target`,
      `item`, `items`, `keys`, and `values`; it is never inferred from payload
      shape.
  - `outputs`: workflow-boundary output contracts (v2.1+).
    - Keys are output names; values reuse the same typed contract fields as `inputs` plus required `from`.
    - Preferred authoring style for relpath boundaries: use `type: relpath` alone; explicit `kind: relpath` remains valid for backward compatibility.
    - `from` must be exactly `{ ref: "root.steps.<Step>.artifacts.<name>|exit_code|outcome.<field>" }`.
    - Export validation runs after the workflow body completes successfully and, for v2.3+ workflows with `finally`, only after finalization completes successfully.
    - v2.15 widens `outputs`
      (not `inputs`) to accept `kind: collection` (`optional|list|map`) in
      addition to the existing scalar/enum/relpath contracts, so a public
      workflow may directly export a collection value produced by a
      Workflow-Lisp-compiled root return. Lower-level Core mappings on other DSL
      versions do not gain this widening.
    - v2.19 additionally accepts `kind: value`, `type: value` for a public
      opaque strict-JSON value. Its `from` ref and exposure semantics are
      unchanged.
  - `result_guidance` (v2.15+, optional): closed, non-empty metadata describing
    the workflow's overall declared return. It accepts only `description:
    string`, `format_hint: string`, and JSON-compatible `example`; requires at
    least one declared `outputs` entry; and is not an output, artifact, prompt
    instruction, reference target, or runtime value. It is valid with direct,
    flattened-record, and flattened-union output maps and never changes them.
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
    - Lowered Workflow Lisp bundles may additionally carry compiler-classified executable-private artifacts that are not part of the public Core contract. A private executable artifact does not widen the authored `.orc` surface and does not reuse the public runtime ledgers as authority.
    - v2.19 accepts `kind: value`, `type: value` without a pointer or narrower
      schema keys. It uses the ordinary artifact value/lineage store; it does
      not introduce a second payload store.
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
    - `provider: string` (+ optional `provider_params`; provider strings may use `${...}` substitution and resolve at provider-step execution time) OR
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
    - Adjudicated provider execution form (v2.11):
      - `adjudicated_provider` is mutually exclusive with every other execution form, including `provider`, `command`, `wait_for`, `assert`, scalar bookkeeping, `call`, and structured control forms.
      - Minimal shape:
        ```yaml
        adjudicated_provider:
          candidates:
            - id: codex_high
              provider: codex
              provider_params:
                model: gpt-5.4
          evaluator:
            provider: claude
            input_file: workflows/library/prompts/adjudication/evaluate_candidate.md
            evidence_confidentiality: same_trust_boundary
          selection:
            tie_break: candidate_order
          score_ledger_path: artifacts/evaluations/example.candidate_scores.jsonl
        ```
      - The step must declare exactly one deterministic output contract surface: `expected_outputs` or `output_bundle`.
      - The step must declare exactly one base prompt source, `asset_file` or `input_file`, unless every candidate declares its own `asset_file` or `input_file` override.
      - Candidate ids must be non-empty, unique within the step, and match the stable step-id token pattern. Candidate and evaluator providers must reference known provider templates in the active workflow provider namespace.
      - Candidate prompt overrides may use only one of `asset_file` or `input_file`. Candidate entries must not define `consumes`, `depends_on`, `publishes`, `expected_outputs`, `output_bundle`, or `output_file`; those surfaces remain step-wide.
      - Evaluator prompt source may use only one of `asset_file` or `input_file`. Evaluator rubric source may use only one of `rubric_asset_file` or `rubric_input_file`.
      - `evaluator.evidence_confidentiality` is required and must be the literal `same_trust_boundary`.
      - `evaluator.evidence_limits`, when present, may only contain literal positive integer `max_item_bytes` and `max_packet_bytes`; `max_packet_bytes` must be greater than or equal to `max_item_bytes`.
      - `provider_session`, `output_file`, `output_capture`, and `allow_parse_error` are invalid with `adjudicated_provider` in v2.11. Candidate/evaluator stdout is runtime log state only and is not projected to `steps.<Step>.output`, `.lines`, or `.json`.
      - `selection.tie_break`, when present, must be `candidate_order`; `selection.require_score_for_single_candidate`, when present, must be boolean.
      - `score_ledger_path`, when present, must resolve under `artifacts/` and must not collide with statically known step-managed output files. Dynamic relpath-target collisions fail at runtime.
      - Candidate-managed path fields that depend on `${run.root}` or name the parent run root are invalid in v2.11.
      - Evaluator score JSON must contain matching `candidate_id`, finite numeric `score` in `[0.0, 1.0]`, and non-empty `summary`.
    - Artifact materialization execution form (v2.14):
      - `materialize_artifacts` is mutually exclusive with other execution forms.
      - `values` resolves typed values from `source.input`, `source.ref`, `source.literal`, or `source.runtime: now_ns`.
      - `input_values` is an optional shorthand for repeated workflow-input materialization. Each entry supplies `names: string[]`, the literal `contract: inherit`, and a `pointer_template` containing `{name}`; frontend lowering expands it into the equivalent long-form `values` entries before shared validation.
      - `source.input` inherits the workflow input contract; `source.ref` inherits the referenced artifact contract; `source.literal` requires an explicit contract; `runtime: now_ns` uses a built-in integer scalar contract.
      - Contract refinements may only narrow the source contract. They may require an existing target, narrow `under` to a child root, or narrow enum values. Type changes, kind changes, broader roots, broader enum sets, and weakened `must_exist_target` are rejected.
      - `input_values` names must reference declared workflow inputs, must not duplicate existing `values[*].name`, and must obey the same path-safety validation as authored long-form pointers.
      - `pointer.path` is allowed only for relpath materializations. A local relpath value published to a top-level relpath artifact must either omit its local pointer or use the artifact's canonical pointer path.
      - `ensure_parent: true` creates the parent directory for a relpath target after path-safety validation.
    - Variant selector execution form (v2.14):
      - `select_variant_output` is mutually exclusive with other execution forms.
      - It selects one tagged-union variant from durable `snapshot_diff` evidence, constructs a JSON bundle in memory, validates it against the embedded variant contract, writes it with an atomic temp-file/rename commit, and exposes only the discriminant plus selected-variant fields as artifacts.
      - Phase 1 evidence mode is `snapshot_diff` with `sha256`; exactly one candidate must be created or content-changed relative to the producer step's `pre_snapshot`.
      - Variant field extractors are intentionally narrow in v2.14. The supported text extractor reads a line with an authored prefix and optional strip characters.
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
      - shape: `{ id?, outputs: WorkflowOutputMap, condition: TypedPredicate, max_iterations: integer, on_exhausted?, steps: Step[] }`
      - `repeat_until.id` uses the same pattern as step `id`
      - post-test semantics: iteration `0` always executes once, then `condition` is evaluated after each completed iteration
      - `condition` must be a typed predicate and may read loop-frame outputs through `self.outputs.<name>`
      - `condition` must not bypass the loop frame by reading `self.steps.<Inner>...` directly
      - selected iteration outputs are materialized onto the loop frame itself and become available at `root.steps.<Statement>.artifacts.<name>`
      - v2.12 `repeat_until.on_exhausted.outputs` is optional and maps declared loop-frame output names to literal scalar overrides applied only when the body succeeds, outputs resolve, the condition evaluates false, and `max_iterations` is exhausted
      - without `on_exhausted`, exhausting `max_iterations` remains a failed loop with `error.type: repeat_until_iterations_exhausted`
      - `on_exhausted.outputs` may override scalar loop outputs only; body-step failures, output-resolution failures, and predicate failures are still failures and do not use exhaustion overrides
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
      - Applies to provider steps with `expected_outputs`, `output_bundle`, or
        `variant_output`.
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
      - Below target 2.21, it cannot be combined with `expected_outputs` on
        the same step. At target 2.21+, `expected_outputs` may coexist with
        exactly one `output_bundle`; every other multi-contract combination
        remains invalid. The two contracts must have disjoint artifact names
        and resolved destinations.
      - `OutputBundleField`:
        - `name: string` (required artifact key; unique within `fields`)
        - `json_pointer: string` (required RFC 6901 pointer; `""` allowed for root)
        - `type: enum|integer|float|bool|string|relpath|optional|list|map|value`
          (required; collection types require v2.15 for ordinary authored DSL)
        - `allowed: string[]` (required when `type: enum`)
        - `under: string` (optional root for `relpath` target validation)
        - `must_exist_target: boolean` (optional, `relpath` only)
        - `required: boolean` (optional, default true; when false, missing pointer is allowed)
        - v2.15 optional guidance keys are `description: string`,
          `format_hint: string`, JSON-compatible and schema-valid `example`,
          and ordered `guidance_context` rows. Each context row contains an
          RFC 6901 `json_pointer` that is a strict ancestor of the field
          pointer plus at least one guidance value; rows are shallow-to-deep.
      - Runtime enforcement runs only when the step process exits with code `0`.
      - For command and provider steps, runtime must expose the resolved `path`
        as `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` before process/provider launch.
        See `specs/io.md`.
      - Parsed values are exposed as `steps.<Step>.artifacts` (unless `persist_artifacts_in_state:false`).
      - A bundle whose sole field uses `json_pointer: ""` treats the entire
        JSON document as that field's value (a "direct root" contract): the
        producer writes the plain scalar/enum/relpath JSON value, not an
        object envelope.
      - A Workflow-Lisp-compiled direct `Value` result is exactly one such
        field, named `__result__`, with `json_pointer: ""` and `type: value`.
        The producer writes the root JSON value itself; `{"value": ...}` is
        not a wire envelope. Authored Workflow Lisp cannot name or project
        `__result__`.
      - `type: value` requires v2.19. It recursively accepts only strict JSON
        (`null`, boolean, integer, finite float, string, list, or string-keyed
        object), and forbids `allowed`, `under`, `must_exist_target`, `item`,
        `items`, `keys`, and `values`. It may appear beneath v2.15
        `optional`, `list`, and `map` descriptors. `expected_outputs` remains
        a file-per-value narrower channel and does not accept `value`.
        `description` and `format_hint` guidance are allowed on a
        `Value`-bearing field, while `example` fails with
        `value_guidance_example_unsupported`.
      - `kind: scalar|collection` (optional; default `scalar`; `collection`
        requires v2.15 for ordinary authored DSL; compiler-private v2.14
        contracts may use the separately validated lowered lane).
        `kind: collection` fields use
        `type: optional|list|map` instead of the scalar type list:
        `optional` requires an `item` schema, `list` requires an `items`
        schema, and `map` requires `keys` (must resolve to `type: string`)
        and `values` schemas, each itself an `OutputBundleField`-shaped spec.
    - `variant_output` (optional; v2.14+): deterministic artifacts extracted from one JSON bundle with a tagged-union shape.
      - It is mutually exclusive with `output_bundle` and
        `select_variant_output`. Below target 2.21 it is also mutually
        exclusive with `expected_outputs`; at target 2.21+,
        `expected_outputs` may coexist with exactly one `variant_output`.
        Every other multi-contract combination remains invalid, and the two
        admitted contracts must have disjoint artifact names and resolved
        destinations.
      - The contract declares a `discriminant` artifact with enum `allowed` values and a `variants` map keyed by those values.
      - `shared_fields` is optional and defaults to `[]`. Shared fields are always present after bundle validation, are exposed without variant proof, and must not duplicate artifact names or JSON pointers used by the discriminant or any field in the same selected variant. Variant-only fields may reuse an artifact name or JSON pointer across distinct variants because only one variant is active.
      - Each variant declares required `fields` and optional `forbidden` JSON pointers. Runtime validation selects exactly one variant, enforces that variant's fields, rejects forbidden fields, and exposes the discriminant, any shared fields, and the selected-variant fields as `steps.<Step>.artifacts`.
      - v2.15 may add closed non-empty bundle `guidance`, direct field
        guidance, ordered `guidance_context`, and `guidance_by_variant` on a
        shared field. `guidance_by_variant` keys must be known variants in
        discriminant order and are mutually exclusive with direct guidance on
        that field. Guidance never changes variant selection or value validity.
      - For command steps, the runtime ensures command steps receive the resolved `path` as runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, prepares the bundle parent before launch, and still treats the declared bundle file as authority rather than stdout during post-success validation.
      - Provider and adjudicated-provider steps inject the variant contract into the prompt unless `inject_output_contract: false`, and receive the resolved `path` as runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
      - Variant-only fields require proof before downstream use. v2.14 supports proof through a `match` over the same discriminant artifact or through step-level `requires_variant`.
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
      - compiler-classified executable-private artifacts append lineage to `private_artifact_versions`; ordinary authored artifacts continue to use `artifact_versions`
    - `consumes`: list of contracts
      - `artifact`: artifact name from top-level `artifacts`
      - `producers: string[]` (optional producer step-name filter)
      - `policy: latest_successful` (MVP)
      - `freshness: any|since_last_consume` (default `any`)
      - `prompt` (optional additive prompt-view metadata for provider/adjudicated-provider consume injection; v1.2+)
        - `mode: content|reference|none` (optional; default `content`)
        - `label: string` (optional)
        - `description: string` (optional prompt guidance only)
        - `format_hint: string` (optional prompt guidance only)
        - `example: string` (optional prompt guidance only)
        - `role: string` (optional prompt guidance only)
      - `description: string` (optional prompt guidance for consumed-artifact injection; no runtime validation impact)
      - `format_hint: string` (optional prompt guidance for consumed-artifact injection; no runtime validation impact)
      - `example: string` (optional prompt guidance for consumed-artifact injection; no runtime validation impact)
      - nested `prompt.*` guidance overrides row-level `description`, `format_hint`, and `example` when both are present
      - `prompt.mode: none` suppresses only prompt text; it does not change consume lineage, freshness, resolved values, or `consume_bundle`
      - runtime preflight:
        - `kind: relpath` artifacts:
          - `version: "1.2"` / `"1.3"`: materialize the selected value to the canonical pointer file
          - `version: "1.4"`: read-only consume resolution (no pointer-file mutation)
        - `kind: scalar` artifacts never write pointer files and use the typed value directly
        - compiler-classified executable-private artifacts resolve from `private_artifact_versions`, commit freshness to `private_artifact_consumes`, and expose resolved native values through the same `_resolved_consumes` semantic handoff used by provider prompt composition and consume-bundle materialization
      - v2.10 `provider_session.mode: resume` reserves one consume for runtime `${SESSION_ID}` binding rather than prompt or consume-bundle output
    - `managed_jobs` (optional; v2.13+; provider steps only)
      - step modifier for runtime-owned managed-job interception, audit, recovery, and resume semantics
      - initial shape:
        ```yaml
        managed_jobs:
          policy: workflows/managed_jobs/policy.json
          watch_roots:
            - scripts/training
          backend: auto
          poll_budget_sec: 82800
          on:
            complete: Review
            failed: Fix
            invalid: Fix
            outstanding: fail_resumable
        ```
      - `policy` and `watch_roots` are relative paths governed by the normal path-safety model.
      - `backend` is `auto`, `local`, or `slurm` in the first tranche.
      - `poll_budget_sec` is a positive integer and must not exceed `timeout_sec` when the step declares one.
      - `managed_jobs.on.complete`, `.failed`, and `.invalid` are validated like ordinary goto targets.
      - `managed_jobs.on.outstanding` is the literal `fail_resumable` in the first tranche.
      - The first tranche rejects `managed_jobs` on non-provider steps, adjudicated provider steps, steps with `retries`, and steps with ordinary `on` handlers.
      - The policy file referenced by `managed_jobs.policy` is external JSON that classifies provider-launched payloads. It is not provider-template configuration and does not change prompt delivery.
      - Policy entries use `mode: force_managed|auto_managed|force_local|unmanaged`. Managed entries must provide `job` metadata or a named `extractor`; unmanaged and force-local entries bypass managed launch.
      - Explicit `job` metadata includes `name_template`, `state_root_template`, optional `output_root_arg`, `verify_files`, `snapshot_roots`, and optional `config_globs`. See `providers.md` for the policy JSON contract and shim behavior.
    - `pre_snapshot` (optional; v2.14+; provider, adjudicated-provider, and command producer steps):
      - Captures bounded `sha256` evidence for named candidate relpath artifacts immediately before the producer executes.
      - Snapshot records are durable under `root.steps.<Step>.snapshots.<name>` and are not ordinary artifacts.
      - Snapshot refs are valid only in `select_variant_output.evidence.snapshot.ref`; they are not publishable, consumable, prompt-injected, or valid as `materialize_artifacts.source.ref`.
      - Candidate files are hashed by streaming content. Directories, unsafe paths, and files larger than the declared limit are rejected.
    - `requires_variant` (optional; v2.14+):
      - Provides an author-time proof that a step may reference fields available only for one selected variant from a variant-producing step.
      - Runtime still checks the producer discriminant before execution and fails with `variant_unavailable` if the selected variant does not match.
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
  - A step may specify exactly one of `provider`, `command`, `assert`, `set_scalar`, `increment_scalar`, `wait_for`, `adjudicated_provider`, `call`, `materialize_artifacts`, or `select_variant_output`.
  - `assert` is a first-class execution form and cannot be combined with `provider`/`command`/`wait_for`/`for_each` on the same step.
  - `set_scalar` and `increment_scalar` are first-class execution forms and cannot be combined with `provider`/`command`/`wait_for`/`assert`/`for_each` on the same step.
  - `for_each` is a block form and cannot be combined with `provider`/`command`/`wait_for`/`assert` on the same step.
  - `goto` targets must reference an existing step name or `_end`. Unknown targets are a validation error (exit code 2) reported at workflow load time.
  - Deprecated `command_override` is not supported and must be rejected by the frontend/shared validator.
  - Version gating:
    - `depends_on.inject` requires `version: "1.1.1"` or higher.
    - `artifacts`, `publishes`, `consumes`, `inject_consumes`, `consumes_injection_position`, and `prompt_consumes` require `version: "1.2"` or higher.
    - `output_bundle` and `consume_bundle` require `version: "1.3"` or higher.
    - `assert` requires `version: "1.5"` or higher.
    - Typed predicates and structured `ref:` require `version: "1.6"` or higher.
    - `set_scalar` and `increment_scalar` require `version: "1.7"` or higher.
    - `max_transitions` and `max_visits` require `version: "1.8"` or higher.
    - scalar `string`, `provider_session`, and provider `session_support` require `version: "2.10"` or higher.
    - `adjudicated_provider` requires `version: "2.11"` or higher.
    - `managed_jobs` requires `version: "2.13"` or higher.
    - `materialize_artifacts`, `pre_snapshot`, `variant_output`, `select_variant_output`, and `requires_variant` require `version: "2.14"` or higher.
    - `type: value` and `kind: value` require `version: "2.19"` or higher and
      fail earlier loads with `value_contract_requires_dsl_2_19`.
  - authored step `id` plus scoped `self`/`parent` refs require `version: "2.0"` or higher.
  - top-level `inputs`, `outputs`, and `inputs.*` typed refs require `version: "2.1"` or higher.
  - structured `if` / `then` / `else` require `version: "2.2"` or higher.
  - top-level `finally` requires `version: "2.3"` or higher.
  - structured `match` requires `version: "2.6"` or higher.
  - structured `repeat_until` requires `version: "2.7"` or higher.
  - `repeat_until.on_exhausted` requires `version: "2.12"` or higher.
  - Advisory authoring-time linting:
    - `orchestrate run --dry-run` and `orchestrate report` may surface non-fatal warnings for migration patterns such as shell gates that should become `assert`, stringly `when.equals` routing that should become typed predicates, raw `goto` diamonds that should become structured control, and imported/exported output-name collisions.
    - Lint warnings are advisory only in the first pass and never change workflow load validity or runtime exit codes.

  - Workflow Lisp `provider-result` call policy:
    - The source grammar adds exactly `:model <String expr>`, `:effort <String
      expr>`, `:timeout-sec <positive Int literal>`, `:delivery
      :composed|:phased`, and `:materialization-attempts <Int literal>` as
      optional keyword/value pairs. Each occurs at most once; missing values,
      duplicates, and unknown keywords fail with the established
      provider-result diagnostics.
    - Model and effort must typecheck as exact `String`, have no direct or
      transitive runtime effects, and belong to the existing inline-lowerable
      scalar/template subset. Procedure-reference edges alone are allowed;
      computed expressions outside that subset are rejected rather than lowered
      through a generated projection.
    - Timeout must be a literal exact `Int` greater than zero. It lowers to the
      existing `timeout_sec` field and retains the ordinary elapsed-time exit
      `124` contract; dynamic, boolean, float, string, zero, and negative timeout
      forms are invalid.
    - Present call-policy values lower to the closed compiler-owned
      `provider_call_policy` mapping in canonical `model`, `effort`, `delivery`,
      then `materialization_attempts` order. Model and effort are
      provider-bound. Delivery and materialization attempts are runtime-only
      coordinator inputs and never become provider parameters or argv
      fragments. Timeout remains outside this mapping as `timeout_sec`.
      Absent keywords remain absent; no empty mapping, parameter, argv
      fragment, or serialized `null` is synthesized.
    - The two delivery keywords require target 2.23. Below target 2.23 either
      fails with `provider_phased_delivery_requires_dsl_2_23`.
      `:materialization-attempts` is legal only with explicit
      `:delivery :phased`; it must be a non-boolean literal exact `Int` in
      `1..3` and defaults to `2` only for explicit phased delivery. Omitted
      delivery carries neither delivery key. Explicit `:delivery :composed`
      carries only `delivery: composed` and forbids materialization attempts.
    - Explicit phased delivery is legal only for a direct fragment application
      whose rendered provider contract has a non-empty contract suffix.
      Otherwise compilation fails with
      `provider_phased_delivery_policy_invalid` and reason
      `fragment_application_required` or `contract_suffix_required`.
    - A target-2.23 phased call carries exact
      `workflow_prompt_attempt_identity.v2`; an omitted or explicit composed
      call retains identity v1. Missing, malformed, downgraded, or mixed
      delivery/identity carriers fail closed with
      `provider_phased_delivery_carriage_mismatch`; identity-version
      disagreement uses reason `attempt_identity_version_mismatch`.
    - Authored `.orc` cannot directly supply `provider_call_policy` or
      `call_policy_bindings`; both are compiler/runtime-owned internal surfaces.
      The lower-level Core `provider_params` and `timeout_sec` semantics remain
      unchanged.
    - Runtime plans, semantic/runtime reports, dashboard/debug projections,
      `expanded.debug.yaml`, and source maps are non-authoritative views for
      call-policy execution. `expanded.debug.yaml` is an intentionally
      historical filename for a JSON-rendered projection; it is not authored
      YAML and is never reparsed. The validated executable provider-step
      configuration is execution authority.

  - Workflow Lisp prompt output positions (target 2.21):
    - The sole output-position grammar is
      `(slot-name :path :out [PathType])`. `:out` occurs at most once,
      immediately after `:path`, and is a role modifier rather than a kind,
      type, caller keyword, or result-field mapping.
    - The optional refinement and resolved fill type must each be a
      workspace-relative `relpath` with `must_exist=false`. The ordinary named
      fill and placeholder rules still apply.
    - The compiler projects one declaration-ordered `expected_outputs` row
      named after the slot, with the same binding-ref or literal path source,
      `type: string`, and `required: true`. No caller-authored output
      declaration may override that row.
    - A Q2 application carries
      `compiled_prompt_fragment_identity.v2` and
      `compiler_prompt_fragment_contract.v2`. The latter's ordered
      `output_positions[*].expected_output` objects are pair-validated against
      the exact provider `expected_outputs` rows before provider preparation.
    - Targets below 2.21 reject the `:out` token with
      `prompt_output_positions_require_dsl_2_21`. A prompt application without
      `:out` retains the exact target-2.20 v1 identity, carrier, diagnostics,
      and behavior even when compiled at target 2.21.

  - Workflow Lisp prompt-attempt identity and diagnostics (target 2.22):
    - Every direct fragment-backed `provider-result` carries the exact pair
      `prompt_attempt_identity_version =
      "workflow_prompt_attempt_identity.v1"` and
      `compiler_prompt_attempt_binding_plan.v1`. Targets 2.20 and 2.21 omit
      both fields byte-for-byte.
    - The compiler-owned binding plan is declaration ordered and agrees
      exactly with the existing document, rendered-slot, renderer, refinement,
      and output-position carriers. Runtime never reconstructs it from source.
    - Missing, malformed, or disagreeing version/plan carriers fail before
      provider preparation with the exact diagnostics
      `prompt_attempt_identity_version_missing`,
      `prompt_attempt_identity_version_invalid`,
      `prompt_attempt_identity_version_mismatch`,
      `prompt_attempt_binding_plan_missing`,
      `prompt_attempt_binding_plan_invalid`, or
      `prompt_attempt_binding_plan_mismatch`.
    - The remaining closed runtime diagnostics are
      `prompt_attempt_identity_role_invalid`,
      `prompt_attempt_identity_policy_invalid`,
      `prompt_attempt_identity_final_prompt_mismatch`,
      `prompt_attempt_identity_composition_invalid`, and
      `prompt_identity_composition_mismatch`.
    - These carriers and records are compiler/runtime evidence surfaces, not
      caller-authored fields, workflow values, result contracts, checkpoint
      results, or resume guards. Coordinated-provider and non-fragment calls
      are outside target 2.22 Q3.

  - Workflow Lisp phased contract delivery (target 2.23):
    - Omitted delivery and explicit `:delivery :composed` execute the ordinary
      composed provider route. They do not create the phased coordinator or
      infer support from provider capability.
    - Explicit `:delivery :phased` requires the exact structural
      `interactive_terminal_turn_queue.v1` capability. Missing, malformed, or
      unsupported capability fails closed without composed fallback.
    - The compiler renders one canonical prompt `C` once and partitions it
      into exact byte slices `T1 || T2 == C`; protocol, submit, and retry
      diagnostic frames are outside `C`. The task is offered exactly once.
      Initial materialization is submission one; a bounded correction reuses
      unchanged `T2` for submission two or three with separately accounted
      diagnostics.
    - A phased call requires attempt identity v2 and functional evidence v3.
      Canonical composition and actual delivered turns remain distinct,
      content-free claims. The phase ledger, reports, submit receipts, stdout,
      and protocol frames are never workflow result authority.

  - Workflow Lisp pinned child execution (target 2.24):
    - `run-ref` is a step-level durable effect, distinct from `call`, command,
      provider, closure, and runtime evaluation. Its two closed authored forms
      are:

      ```lisp
      (run-ref
        :source (:repo "<canonical-locator>" :commit "<40-lowercase-hex>")
        :program (:bundle <static-workflow-name>)
        :inputs (:name <value-expr> ...)
        :policy (:setup ((:argv ("/absolute/program" "literal" ...)
                          :env (:NAME "literal" ...)) ...)))
      ```

      ```lisp
      (run-ref
        :source (:repo "<canonical-locator>" :commit "<40-lowercase-hex>")
        :program (:path "relative/program.orc" :entry <static-workflow-name>)
        :inputs (:name <value-expr> ...)
        :returns Value
        :policy (:environment :deterministic-effect-free :setup ()))
      ```

    - Keys are closed, unique, and compile-time literal except input value
      expressions. Source and program discriminators are mutually exclusive.
      A commit is exactly one lowercase 40-hex object ID. Accepted locators
      are canonical absolute paths normalized to `file://`, canonical
      `file://`, `https://`, or `ssh://` URIs; userinfo, query, fragment, scp
      shorthand, and implicit relative paths reject. A clone program path is
      normalized relative POSIX `.orc` with no empty, dot, parent, absolute,
      or backslash segment.
    - Mode 1 (`:bundle`) statically selects a workflow from the reachable
      compiled catalog, validates all inputs against its exact signature, and
      derives its exact return type. It forbids `:returns` and
      `:environment`. Its reachable compiled graph and exact source/asset
      closure travel in a private, version-local
      `run_ref_bundle_capsule.v1`; the child validates the parent-bound capsule
      digest and existing IR cross-views, stages closure bytes below its own
      `.orchestrate`, and executes the ordinary loaded-bundle route without
      recompiling or reading mutable controller source.
    - Mode 2 (`:path`) runs the ordinary full compiler in the pinned child
      root. Its result defaults to exact opaque `Value`; optional
      `:returns T` may name any existing transportable type and is a runtime
      claim checked exactly against the child signature. V1 requires
      `:environment :deterministic-effect-free`; any provider, command,
      unknown, or otherwise non-pure effect rejects with
      `trial_candidate_environment_not_admissible`. Compiler rejection is the
      stable structured `trial_program_compile_rejected` envelope, never a
      parallel checker or parsed human stderr.
    - Every target-2.19 transportable value is valid as an input and result,
      including direct roots, records, unions, optionals, lists, maps,
      relpaths, and exact `Value`. Relpath inputs are copied to deterministic
      child-workspace destinations and rebound only after contract validation;
      host source paths do not cross the boundary.
    - Each site has one compiler-generated monomorphic result type:

      ```text
      RunRefResult$<site-digest> = {
        value: T,
        workspace_delta: WorkspaceDelta,
        accounting: RunRefAccounting
      }

      WorkspaceDelta = {
        base: RepositoryRevisionId,
        changed_files: List[WorkspaceEntryDelta],
        deleted_files: List[WorkspaceEntryDelta],
        untracked_files: List[WorkspaceEntryDelta],
        normalized_diff: NormalizedWorkspaceDiff,
        declared_artifacts: List[DeclaredWorkspaceArtifact]
      }

      RunRefAccounting = {
        child_run_id: RunId,
        attempt_ordinal: Int,
        terminal_status: String,
        elapsed_ms: Int,
        setup_ms: Int,
        compile_ms: Int,
        provider_attempts: Value,
        token_usage: Value,
        cost: Value
      }
      ```

      `WorkspaceDelta` carries the exact `RepositoryRevisionId`, complete
      sorted changed/deleted/untracked metadata, bounded normalized diff, and
      declared artifacts. `RunRefAccounting` carries child run/attempt/status
      and elapsed/setup/compile/provider/token/cost facts; unknown usage or
      cost is the exact string `"UNKNOWN"`, never numeric zero. The specialized
      result-contract encoder preserves the child's exact root contract under
      `value`; it does not introduce general generic records.
    - `RepositoryRevisionId` hashes exactly normalized locator, resolved
      commit SHA, materializer version, submodule policy, LFS policy, and
      authored setup-command identity. Verified Git tree, compiler/runtime
      identity, and post-setup baseline digest are separate bound facts; setup
      output is evidence, not repository identity.
    - Setup is an ordered literal argv plus declared-env list, never a shell.
      `argv[0]` is absolute or a canonical `./` workspace-relative executable.
      Setup receives only that declared environment plus runtime-owned `PWD`
      and evidence variables. Its output is evidence and excluded from the
      workspace delta. V1 rejects `.gitmodules` and committed LFS filters.
      Materialization uses a sealed content-addressed mirror followed by one
      ordinary fresh detached clone; Git worktrees are not used.
    - `run-ref` is admitted in ordinary workflow bodies, `let*`, `if`,
      `match`, reusable calls, and effectful procedures. Target 2.24 rejects it
      in pure functions, pure settlement/evaluation bodies, `loop/recur`,
      `list/map-effect`, and generated repeat/for-each effect frames. A later
      reviewed target owns effect-loop settlement.
    - The closed structural refusal codes owned by E1 are
      `trial_source_unresolvable`, `trial_source_submodules_unsupported`,
      `trial_source_lfs_unsupported`,
      `trial_source_revision_digest_mismatch`,
      `trial_materialization_digest_mismatch`,
      `trial_workspace_preexisting`, `trial_setup_failed`,
      `trial_program_missing`, `trial_program_compile_rejected`,
      `trial_program_signature_mismatch`, and
      `trial_candidate_environment_not_admissible`. Each envelope carries
      `code`, `rejected_value`, and stable secondary causes. Runtime-only
      failures use the separate closed codes `run_ref_ledger_invalid`,
      `run_ref_capsule_invalid`, `run_ref_child_launch_failed`,
      `run_ref_child_result_invalid`, `run_ref_delta_capture_failed`, and
      `run_ref_workspace_discard_failed`. Human prose is never routing
      authority.
    - Targets below 2.24 reject the form with
      `run_ref_target_dsl_unsupported`. Missing values, duplicate or unknown
      keys, nonliteral identity/policy fields, mixed program discriminators,
      or placement outside the admitted effect contexts reject through the
      closed compiler diagnostics `run_ref_shape_invalid`,
      `run_ref_literal_required`, `run_ref_program_mode_invalid`, and
      `run_ref_placement_invalid`; each carries a stable reason and source
      span.
    - The external child compile boundary emits exactly one
      `workflow_lisp_compile_diagnostics.v1` JSON document. It has
      `status: accepted|rejected`, ordered existing serialized diagnostics,
      and, on acceptance, the selected entry/signature and normalized program
      identity. The opt-in surface is
      `orchestrator compile <program.orc> --diagnostics-json`; accepted exits
      zero and rejected exits two. Human compiler output remains unchanged
      when this machine surface is not requested.

  - Workflow Lisp bounded static trials (target 2.25):
    - `trial` is one step-level durable `TRIAL` effect over two or more
      statically elaborated target-2.24 `run-ref` configurations. It is not a
      first-class effect value, general parallel block, dynamic arm builder,
      selection primitive, source-promotion primitive, closure, or runtime
      evaluation surface. Its closed authored form is:

      ```lisp
      (trial
        :arms ((:id "direct"
                :run-ref
                (run-ref
                  :source (:repo "/absolute/repository"
                           :commit "0123456789abcdef0123456789abcdef01234567")
                  :program (:bundle direct)
                  :inputs (:task task)
                  :policy (:setup ())))
               (:id "orc"
                :run-ref
                (run-ref
                  :source (:repo "/absolute/repository"
                           :commit "89abcdef0123456789abcdef0123456789abcdef")
                  :program (:path "experiments/orc.orc" :entry orchestrated)
                  :inputs (:task task)
                  :returns Value
                  :policy (:environment :deterministic-effect-free
                           :setup ()))))
        :reps 3
        :max-concurrency 4
        :evaluation
        (record
          :checks (list
            (record :id "correctness"
                    :command (list "python" "-m" "pytest" "-q")
                    :authority "correctness"
                    :required true
                    :timeout-ms 600000))
          :judgment
          (record :provider "scorer"
                  :rubric-asset "rubrics/trial.md"
                  :evidence-confidentiality "same_trust_boundary"
                  :evidence-limits
                  (record :max-item-bytes 65536
                          :max-packet-bytes 262144))
          :observation
          (record :include
                  (list "task_spec" "validated_result" "workspace_delta"
                        "check_results" "declared_artifacts"
                        "failure_evidence")
                  :diff-cap-bytes 262144
                  :reveal-provider-identity false)
          :aggregation
          (record :mode "independent_rubric"
                  :rep-combine "median"
                  :tie "authored_order")
          :success-rule
          (record
            :superior
            (record :min-abs-improvement 0.10 :max-cost-ratio 1.5)
            :non-inferior
            (record :min-cost-reduction 0.20)
            :count-failures-as-outcomes true))
        :budget
        (record :arm-timeout-ms 900000
                :trial-timeout-ms 3600000
                :max-evaluator-attempts 6
                :max-evaluator-concurrency 2))
      ```

    - The top-level keys are closed, unique, and all required. There are
      2–16 authored arms with unique non-empty literal string IDs, 1–64
      repetitions, at most 256 total `(arm, rep)` cells, and arm concurrency
      in 1–32 that does not exceed the cell count. Each `:run-ref` is nested
      syntax elaborated into one static E1 configuration and retains E1's
      literal source, program, and policy identity plus ordinary dynamic input
      expressions. All arms must have the same normalized child `value`
      descriptor; exact `Value` is the opt-in common boundary for otherwise
      heterogeneous JSON values.
    - Target 2.25 admits recursively transportable records and closed unions
      below bounded list, optional, and string-keyed map containers for
      authored values and compiler-owned result contracts. This is one generic
      structural transport rule, not a `trial`-name exception; every leaf,
      union tag, depth limit, size limit, and direct strict-JSON wire value is
      still validated. The maximum descriptor/value nesting depth is 64 with
      root depth 0; the first child at depth 65 rejects. The maximum canonical
      compact UTF-8 JSON value size is 16,777,216 bytes inclusive, measured
      after direct-value normalization with sorted keys, `ensure_ascii=False`,
      and separators `(",", ":")`, not from raw bundle or file bytes. These
      are generic transport resource bounds, not security or isolation claims.
      Targets through 2.24 retain their narrower accepted source and transport
      behavior.
    - `:evaluation` and `:budget` are compile-time pure closed structural
      record values. Checks have unique non-empty literal IDs, literal argv
      executed without a shell, authority exactly `correctness|invariant`, a
      Boolean `required`, and a positive `timeout-ms`. Judgment resolves one
      provider alias and one rubric asset for every cell, requires exact
      `same_trust_boundary`, and has positive canonical item/packet byte caps
      with packet cap greater than or equal to item cap. Observation uses only
      the six shown include names, has a positive diff cap, and requires
      `reveal-provider-identity` to be false. Aggregation is exactly
      independent-rubric scoring, median repetition combination, and
      authored-order tie handling; one frozen success rule applies to every
      arm.
    - Arm and trial timeouts are positive. `max-evaluator-attempts` is one
      positive total ceiling across the trial and
      `max-evaluator-concurrency` is positive and no larger than that ceiling.
      Exhausting a deadline or evaluator-attempt ceiling settles work that has
      not started as explicit failed outcomes. Already running child or
      evaluator work finishes and remains fully charged. Provider attempts,
      elapsed time, tokens, and cost are recorded; unknown tokens or cost stay
      the exact fact `"UNKNOWN"` and are never replaced with zero.
    - `trial` is admitted wherever `run-ref` is admitted, including ordinary
      workflow bodies, branches, reusable calls, and effectful procedures. It
      remains invalid in pure functions, pure settlement/evaluation bodies,
      `loop/recur`, `list/map-effect`, generated iteration frames, or any site
      whose reachable trial or arm graph contains another `trial`. Failures
      are values and do not cancel completed or in-flight siblings.
    - Each site receives compiler-generated monomorphic contracts. `T` is the
      one normalized arm value descriptor:

      ```text
      TrialResult$<site-digest> = {
        outcomes: List[TrialArmOutcome$<site-digest>],
        verdict: TrialVerdict,
        verdict_artifact: TrialVerdictPath
      }

      TrialArmOutcome$<site-digest> =
          Completed { arm_id: String, rep: Int, value: T,
                      evidence: CompletedTrialEvidence$<site-digest> }
        | Failed    { arm_id: String, rep: Int, failure: TrialFailure,
                      evidence: PartialTrialEvidence }

      TrialFailure = {
        code: String,
        phase: String,
        retryable: Bool,
        secondary_causes: List[Value]
      }
      ```

      Completed evidence retains the validated E1 workspace delta and
      accounting, deterministic checks, opaque evaluation label,
      packet/scorer identity, score, and exact run/attempt lineage. Partial
      evidence contains only facts that exist and never fills absent facts
      with defaults. `TrialVerdict` records authored arm order, per-repetition
      outcomes and scores, aggregates, ranking, nullable selected arm,
      success-rule disposition, and complete budget accounting.
      `TrialVerdictPath` is a load-bearing existing relpath rooted below
      `artifacts/trials/`. Authored arm IDs enter the result only after scoring
      and the sealed unblinding join; packets and trial score rows use opaque
      labels.
    - `TrialStaticConfig.digest` hashes target and lowering versions, source
      site identity, authored arm order and E1 config digests, the common
      result contract, repetitions, evaluation, budget, and compiler/runtime
      identity. The runtime request digest adds the complete parent
      run/frame/step/visit identity and resolved input values. Completion
      order, timestamps, workspace paths, opaque-label salt, provider output,
      and report bytes enter neither identity. The lexical checkpoint policy
      is exactly `reuse_validated_trial_result` and preserves every existing
      root, callee, input, checkpoint, and result guard.
    - Targets below 2.25 reject `trial` with
      `trial_target_dsl_unsupported`. Closed shape/type/placement refusals are
      `trial_arms_invalid`, `trial_arm_result_mismatch`,
      `trial_nested_unsupported`, `trial_evaluation_contract_not_pure`,
      `trial_evaluation_contract_invalid`,
      `trial_evaluation_provider_unresolved`,
      `trial_evaluation_rubric_unresolved`, `trial_reps_invalid`,
      `trial_concurrency_invalid`, `trial_budget_invalid`,
      `trial_packet_policy_invalid`, `trial_packet_limit_invalid`,
      `trial_blinding_policy_invalid`, and
      `trial_packet_citation_invalid`. E1 source, program, environment, and
      runtime failures retain their existing closed codes per arm. Every
      refusal includes its `code`, rejected value, stable secondary causes,
      and source span when available; human prose is never routing authority.

  - Workflow Lisp WCC child-call argument projection:
    - Within existing bounded `list/map-effect`, an existing typed
      `path/join-under` expression may be evaluated in the caller iteration
      scope and its typed path value passed as an ordinary child input through
      the admitted WCC route.

  - reusable-call contract boundary:
    - Task 10 reserves `imports`, `call`, `with`, `asset_file`, and `asset_depends_on` semantics before execution support lands.
    - When Task 11 lands, those fields require `version: "2.5"` or higher.
    - `version: "2.4"` is a documentation/contract boundary, not a promise that the current compiler/runtime executes reusable-call workflows.

### Retired YAML authoring surface

The former fresh-load YAML/YML deprecation advisory is retired with its parser.
Fresh non-`.orc` execution now fails at the frontend boundary described above;
there is no YAML warning followed by parsing. Historical warning records and
YAML-shaped state fields remain evidence only. Their presence does not reopen
an authored YAML frontend or affect `.orc` compilation, validation, bundle
identity, execution, or exit codes.

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
  - The first tranche does not claim sandboxing or frontend-proved isolation of child-process filesystem effects.
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
