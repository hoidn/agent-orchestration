# String Artifacts And Provider Session Resume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add first-class scalar `string` support and a provider-session resume feature to the DSL/runtime so workflows can create one provider session, review its output, then resume that same session in later steps without embedding provider-specific shell commands in YAML.

**Architecture:** Use the next DSL version gate (`2.10`) for both features. Add `string` to the scalar contract family everywhere typed values can cross workflow boundaries or artifact/dataflow boundaries. Add a provider-agnostic `provider_session` step surface plus provider-template session capability metadata, but implement only the Codex path in the first runtime slice. Keep session capture runtime-owned: the runtime should publish the session handle as a scalar artifact and persist provider metadata under `.orchestrate/runs/<run_id>/provider_sessions/`, rather than asking prompts to write session-id files. Migrate the current `dsl_review_first_fix_loop` pattern into a new example that uses the new feature while leaving the old `1.4` workflow in place.

**Tech Stack:** YAML DSL/specs, Python orchestrator runtime, provider registry/executor, state.json/run metadata, pytest loader/runtime/example smoke tests, orchestrator dry-run validation.

---

## Recommended Design

Recommended approach:
- add `string` as a scalar type across workflow `inputs` / `outputs`, top-level `artifacts`, `expected_outputs`, and `output_bundle`
- add provider-template resume capability metadata plus a step-level `provider_session` block
- let `provider_session.mode: fresh` publish a runtime-captured scalar session-handle artifact directly, without routing through `expected_outputs`
- let `provider_session.mode: resume` consume that scalar artifact and bind it into the provider invocation
- implement only one metadata capture mode in the first pass: Codex JSON event stream on stdout

Rejected alternatives:
- hard-code `codex exec resume` as a DSL step feature: too provider-specific
- continue with literal provider shell templates only: not first-class, not portable, still brittle
- synthesize session-id files through `expected_outputs`: reintroduces prompt leakage and runtime-owned file confusion

## Proposed Surface

### Scalar `string` support

Add `string` to the allowed scalar type family:
- workflow `inputs` / `outputs`
- top-level `artifacts` with `kind: scalar`
- `expected_outputs[].type`
- `output_bundle.fields[].type`
- typed predicate comparison refs/literals for `eq` / `ne` only
- `set_scalar` values when the target artifact is `type: string`

Keep `relpath` rules unchanged:
- `kind: relpath` still requires `type: relpath`
- `string` is scalar only

### Provider template session capability

Add an optional provider-template section:

```yaml
providers:
  codex:
    command: ["codex", "exec", "--model", "${model}", "--config", "reasoning_effort=${effort}"]
    resume_command:
      ["codex", "exec", "resume", "${SESSION_ID}", "--model", "${model}", "--config", "reasoning_effort=${effort}"]
    input_mode: "stdin"
    defaults:
      model: "gpt-5.4"
      effort: "high"
    session_support:
      metadata_mode: codex_jsonl_stdout
```

Notes:
- `resume_command` is optional and only meaningful when `session_support` is declared
- `${SESSION_ID}` is a provider-session-specific placeholder, not a general workflow variable
- first pass supports only one `metadata_mode`: `codex_jsonl_stdout`

### Step-level session mode

Add an optional step field:

```yaml
provider_session:
  mode: fresh | resume
  publish_artifact: implementation_session_id   # fresh only
  session_id_from: implementation_session_id    # resume only
```

Rules:
- steps without `provider_session` keep existing behavior
- `mode: fresh` requires the provider template to declare `session_support`
- `mode: fresh` requires `publish_artifact`, which must name a top-level scalar artifact of `type: string`
- `mode: resume` requires `session_id_from`, and the step must consume that artifact
- the runtime, not the prompt, captures and publishes the session handle

### Runtime-owned metadata persistence

Every provider-session step persists append-only metadata under:

```text
.orchestrate/runs/<run_id>/provider_sessions/<step_id>__v<visit>.json
```

Suggested contents:
- provider name
- mode (`fresh` or `resume`)
- session id
- provider-native raw session metadata
- fully resolved command
- timestamps

This file is for observability/debugging. Workflow control flow should use published scalar artifacts, not these files directly.

## Task Breakdown

### Task 1: Pin the design contract in specs before changing runtime code

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/providers.md`
- Modify: `specs/io.md`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Reference: `docs/plans/2026-03-06-provider-session-resume-workflows-implementation-plan.md`

**Step 1: Update the DSL spec with the new `2.10` gate**

Document:
- `2.10` as the next DSL version
- `string` support for scalar contract families
- `provider_session` step schema
- `resume_command` and `session_support` on provider templates
- `${SESSION_ID}` as a provider-session-only placeholder

**Step 2: Clarify runtime ownership**

Spell out:
- provider-session capture is runtime-owned
- prompts must not be asked to create session-id files
- fresh session handles publish directly into scalar artifacts
- resume steps still use ordinary `consumes` for flow/data dependencies

**Step 3: Clarify the Codex-first limit**

State that:
- the DSL/schema is provider-agnostic
- the first runtime implementation supports only `metadata_mode: codex_jsonl_stdout`
- providers without `session_support` fail validation when `provider_session` is requested

**Step 4: Add acceptance bullets**

Add acceptance items covering:
- `string` scalar contracts
- fresh session capture
- resume invocation using consumed session id
- append-only metadata persistence
- example workflow validation

**Step 5: Read back the edited spec sections**

Run:

```bash
sed -n '1,260p' specs/dsl.md
sed -n '1,220p' specs/providers.md
sed -n '1,220p' specs/versioning.md
```

Expected:
- `2.10` and the new surfaces are documented consistently

**Step 6: Commit**

```bash
git add specs/dsl.md specs/providers.md specs/io.md specs/state.md specs/observability.md specs/versioning.md specs/acceptance/index.md
git commit -m "docs: define string artifacts and provider session resume"
```

### Task 2: Add failing tests for scalar `string` support

**Files:**
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_output_contract.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add failing loader tests for `string` contract surfaces**

Cover:
- workflow `inputs` / `outputs` with `type: string`
- top-level scalar artifacts with `type: string`
- `expected_outputs.type: string`
- `output_bundle.fields[].type: string`
- rejection of `kind: relpath` + `type: string`

**Step 2: Add failing runtime tests for `string` parsing and publication**

Cover:
- raw text `expected_outputs` parsed as string
- `output_bundle` string field extraction
- publish/consume of string scalar artifacts
- `set_scalar` into a string artifact

**Step 3: Run the narrow selectors to verify failure**

Run:

```bash
pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py -k string -v
```

Expected:
- failing tests showing `string` is still unsupported

**Step 4: Collect-only if test names/files changed**

Run:

```bash
pytest --collect-only tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py -q
```

Expected:
- new tests are collected

**Step 5: Commit the failing tests**

```bash
git add tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py
git commit -m "test: pin string scalar contract support"
```

### Task 3: Implement scalar `string` support end-to-end

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/contracts/output_contract.py`
- Modify: `orchestrator/workflow/signatures.py`
- Modify: `orchestrator/workflow/predicates.py`
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_loader_validation.py`
- Test: `tests/test_output_contract.py`
- Test: `tests/test_artifact_dataflow_integration.py`

**Step 1: Extend loader type validation**

Implement:
- `string` allowed only for scalar contracts
- workflow `inputs` / `outputs`
- top-level scalar artifacts
- `expected_outputs` / `output_bundle`

**Step 2: Extend output-contract parsing**

Implement:
- raw UTF-8 text returned as string
- no enum coercion or numeric parsing for `string`
- preserve existing `relpath`, `bool`, numeric behavior

**Step 3: Extend signatures and predicates**

Implement:
- workflow input/output validation for string
- typed `compare.eq` / `compare.ne` against string refs/literals
- reject `lt` / `lte` / `gt` / `gte` on string operands

**Step 4: Re-run the targeted tests**

Run:

```bash
pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py -k string -v
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add orchestrator/loader.py orchestrator/contracts/output_contract.py orchestrator/workflow/signatures.py orchestrator/workflow/predicates.py orchestrator/workflow/executor.py tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py
git commit -m "feat: add string scalar contracts"
```

### Task 4: Add failing schema tests for provider-session DSL surfaces

**Files:**
- Create: `tests/test_provider_session_schema.py`
- Modify: `tests/test_loader_validation.py`

**Step 1: Add failing loader tests for provider template session fields**

Cover:
- valid `resume_command`
- valid `session_support.metadata_mode`
- invalid `${SESSION_ID}` outside `resume_command`
- invalid `provider_session` on a step whose provider lacks `session_support`

**Step 2: Add failing loader tests for step-level `provider_session`**

Cover:
- valid `mode: fresh` + `publish_artifact`
- valid `mode: resume` + `session_id_from`
- invalid missing `publish_artifact` on fresh mode
- invalid missing `session_id_from` on resume mode
- invalid `publish_artifact` pointing at non-string or non-scalar artifacts
- invalid resume step that does not consume the named session artifact

**Step 3: Run the schema tests to verify failure**

Run:

```bash
pytest tests/test_provider_session_schema.py -v
```

Expected:
- FAIL because schema/runtime support is not present yet

**Step 4: Collect-only**

Run:

```bash
pytest --collect-only tests/test_provider_session_schema.py -q
```

Expected:
- the new tests are collected

**Step 5: Commit**

```bash
git add tests/test_provider_session_schema.py tests/test_loader_validation.py
git commit -m "test: pin provider session schema"
```

### Task 5: Implement the provider-session schema and loader validation

**Files:**
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/registry.py`
- Modify: `orchestrator/loader.py`
- Modify: `specs/providers.md`
- Modify: `specs/dsl.md`
- Modify: `specs/versioning.md`
- Test: `tests/test_provider_session_schema.py`

**Step 1: Extend provider data models**

Add typed dataclasses/enums for:
- `session_support`
- `metadata_mode`
- optional `resume_command`

**Step 2: Extend step schema validation**

Validate:
- `provider_session.mode`
- fresh/resume field requirements
- artifact-type constraints on `publish_artifact`
- resume-step requirement to consume `session_id_from`

**Step 3: Re-run the schema tests**

Run:

```bash
pytest tests/test_provider_session_schema.py -v
```

Expected:
- PASS

**Step 4: Commit**

```bash
git add orchestrator/providers/types.py orchestrator/providers/registry.py orchestrator/loader.py tests/test_provider_session_schema.py specs/providers.md specs/dsl.md specs/versioning.md
git commit -m "feat: add provider session DSL schema"
```

### Task 6: Add failing Codex runtime tests for fresh capture and resume invocation

**Files:**
- Create: `tests/test_provider_session_codex_runtime.py`
- Modify: `tests/test_workflow_examples_v0.py`

**Step 1: Add a failing fresh-session runtime test**

Cover:
- provider step with `provider_session.mode: fresh`
- mocked Codex JSONL stdout containing both final assistant text and session metadata
- runtime publishes the session id as a string artifact
- output capture still preserves assistant text semantics

**Step 2: Add a failing resume-session runtime test**

Cover:
- consumed string session id artifact
- `provider_session.mode: resume`
- resolved command uses `resume_command` with `${SESSION_ID}` substituted
- provider params still populate model/effort placeholders in the resume command

**Step 3: Add a failing metadata-persistence test**

Cover:
- `.orchestrate/runs/<run_id>/provider_sessions/<step_id>__v<visit>.json` is written
- visit ordinals append rather than overwrite

**Step 4: Run the Codex runtime tests to verify failure**

Run:

```bash
pytest tests/test_provider_session_codex_runtime.py -v
```

Expected:
- FAIL because runtime does not yet understand provider sessions

**Step 5: Collect-only**

Run:

```bash
pytest --collect-only tests/test_provider_session_codex_runtime.py -q
```

Expected:
- the new tests are collected

**Step 6: Commit**

```bash
git add tests/test_provider_session_codex_runtime.py tests/test_workflow_examples_v0.py
git commit -m "test: pin codex provider session runtime"
```

### Task 7: Implement Codex-first provider-session runtime support

**Files:**
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/registry.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/state.py`
- Modify: `specs/io.md`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Test: `tests/test_provider_session_codex_runtime.py`

**Step 1: Extend provider invocation/result types**

Add fields for:
- optional provider-session request metadata on invocation
- parsed session metadata on execution result
- provider-authored assistant text separate from raw event stream when needed

**Step 2: Implement Codex JSONL parsing in the provider executor**

Implement first-pass rules:
- only when provider declares `metadata_mode: codex_jsonl_stdout`
- parse stdout JSONL events
- extract final assistant text for normal `output_file` / capture semantics
- extract session id + raw provider metadata for runtime publication
- preserve raw event stream in run logs for debugging

**Step 3: Implement fresh-session artifact publication**

In workflow execution:
- validate the target `publish_artifact`
- publish the runtime-captured session id as a string scalar artifact
- persist append-only metadata JSON under `.orchestrate/runs/<run_id>/provider_sessions/`

**Step 4: Implement resume invocation**

In provider preparation:
- resolve `session_id_from` from consumed artifacts
- substitute `${SESSION_ID}` into `resume_command`
- preserve normal provider param substitution for model/effort/etc.

**Step 5: Re-run the runtime tests**

Run:

```bash
pytest tests/test_provider_session_codex_runtime.py -v
```

Expected:
- PASS

**Step 6: Commit**

```bash
git add orchestrator/providers/executor.py orchestrator/providers/types.py orchestrator/providers/registry.py orchestrator/workflow/executor.py orchestrator/state.py tests/test_provider_session_codex_runtime.py specs/io.md specs/state.md specs/observability.md
git commit -m "feat: add codex provider session runtime"
```

### Task 8: Migrate the review-first upstream example to a first-class provider-session workflow

**Files:**
- Create: `workflows/examples/dsl_review_first_fix_loop_v2_session.yaml`
- Create: `prompts/workflows/dsl_review_fix_loop_v2_session/review.md`
- Create: `prompts/workflows/dsl_review_fix_loop_v2_session/fix.md`
- Modify: `workflows/README.md`
- Modify: `docs/workflow_drafting_guide.md`
- Create: `tests/test_provider_session_example.py`

**Step 1: Create the new example workflow**

Keep the old workflow untouched. The new example should:
- use `version: "2.10"`
- start with a fresh review/implementation step that captures a session id
- publish that session id as a string artifact
- use a later fix step with `provider_session.mode: resume`
- preserve the existing review-first loop shape so the feature migration is isolated from control-flow changes

**Step 2: Keep prompts narrow**

Prompts should:
- not mention runtime metadata files
- not ask the provider to write session ids
- continue to focus on the ADR review/fix task only

**Step 3: Add a focused example runtime smoke test**

Cover:
- fresh step publishes session id
- fix step resumes from that session id
- loop still exits when review stops emitting `## High`

**Step 4: Run the example test**

Run:

```bash
pytest tests/test_provider_session_example.py -v
```

Expected:
- PASS

**Step 5: Run a dry-run smoke check**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_review_first_fix_loop_v2_session.yaml --dry-run --stream-output
```

Expected:
- workflow validation successful

**Step 6: Commit**

```bash
git add workflows/examples/dsl_review_first_fix_loop_v2_session.yaml prompts/workflows/dsl_review_fix_loop_v2_session workflows/README.md docs/workflow_drafting_guide.md tests/test_provider_session_example.py
git commit -m "docs: add provider session review loop example"
```

### Task 9: Final regression sweep and documentation alignment

**Files:**
- Modify as needed based on failures from prior tasks

**Step 1: Run the targeted test suite**

Run:

```bash
pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py tests/test_provider_session_schema.py tests/test_provider_session_codex_runtime.py tests/test_provider_session_example.py tests/test_workflow_examples_v0.py -k "string or provider_session or dsl_review_first_fix_loop_v2_session or workflow_examples_v0_load" -v
```

Expected:
- all targeted feature tests pass

**Step 2: Run collection for new modules**

Run:

```bash
pytest --collect-only tests/test_provider_session_schema.py tests/test_provider_session_codex_runtime.py tests/test_provider_session_example.py -q
```

Expected:
- new tests are collected cleanly

**Step 3: Re-run the example workflow dry-run**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_review_first_fix_loop_v2_session.yaml --dry-run --stream-output
```

Expected:
- validation successful

**Step 4: Commit final cleanup**

```bash
git add specs providers orchestrator tests workflows prompts docs
git commit -m "feat: add first-class provider session resume workflows"
```

## Risks And Mitigations

1. **Prompt leakage through runtime-owned session files**
   - Mitigation: do not route provider-session handles through `expected_outputs`; publish them directly from runtime capture.

2. **Command divergence between fresh and resume modes**
   - Mitigation: both `command` and `resume_command` must share the same provider-param substitution path and must be covered by runtime tests.

3. **Codex event-stream parsing breaks existing stdout semantics**
   - Mitigation: keep raw event stream in logs, but feed only final assistant text into the existing `output_file` / output-capture path.

4. **String support leaks into relpath semantics**
   - Mitigation: loader rejects `kind: relpath` + `type: string`; tests pin that boundary.

5. **Workflow resume confused with provider-session resume**
   - Mitigation: specs and example docs must explicitly distinguish them; provider-session metadata is step-local runtime state, not run-resume state.

6. **The migrated example drifts into a broader control-flow rewrite**
   - Mitigation: keep the first migrated example structurally close to `dsl_review_first_fix_loop.yaml`; migrate only the provider-session behavior in this tranche.
