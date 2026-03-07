# Provider Session Resume Workflows Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add first-class workflow support for patterns where one provider session is created once, reviewed by a fresh agent, then resumed in later workflow steps using the prior session handle plus new feedback.

**Architecture:** Extend the DSL and runtime so provider steps can be either `fresh` or `resume` invocations, with a normalized session-handle contract and provider-specific capability metadata. Keep workflow control flow artifact-driven: an implementation step publishes a typed `session_id` artifact and later resume steps consume that artifact plus review artifacts. Avoid ad hoc shell glue; the runtime should own session-handle capture, prompt delivery, resume-argument shaping, and provider metadata persistence. The first implementation slice should prove the Codex path end-to-end before generalizing the provider schema.

**Tech Stack:** YAML DSL/specs, Python orchestrator runtime, provider templates/executor, state.json/runtime observability, pytest.

---

## Design Constraints

- The feature must support the concrete pattern: fresh Agent A -> fresh review B -> resume Agent A with review feedback -> fresh review B again.
- The workflow-level abstraction must not hard-code Codex, but the first implementation may only support providers that explicitly declare resume capability.
- Resume-capable providers need a normalized typed session handle. Current scalar artifacts do not support arbitrary strings, so `string` support must be added before session handles can be first-class artifacts.
- The workflow runtime already supports workflow `resume`; this feature is separate and must not blur run-resume with provider-session-resume.
- Control flow should stay artifact/gate driven. A resume step still succeeds/fails like any other provider step; no hidden magic branches.
- The first pass should avoid nested `call` or new structured DSL features. This can be implemented within current step sequencing.
- The runtime must preserve current provider stdout/stderr and `output_file` semantics. Session capture cannot silently repurpose stdout into a metadata channel unless the provider path explicitly models that behavior and preserves normal step output capture.
- Session metadata capture is runtime-owned. Provider-authored files may remain useful for ordinary workflow outputs, but the session-handle artifact itself must be synthesized by the runtime from provider execution metadata before deterministic output validation runs.
- Resume invocation must inherit the same provider param surface as fresh invocation. We should not introduce a second unrelated command template that can silently diverge on model, reasoning, or future provider flags.
- The first slice must account for `expected_outputs` prompt injection. If the runtime owns the session-id file, the provider prompt must not instruct the agent to write that file.

## Proposed Surface Design

### New artifact/output type

Add `string` as a scalar output/artifact type:
- `expected_outputs[].type: string`
- `output_bundle.fields[].type: string`
- top-level `artifacts.<name>.type: string` when `kind: scalar`

This is required for provider session handles (`session_id`, thread names, resume tokens).

### Provider template capability

Extend provider templates with optional session-resume support:

```yaml
providers:
  codex:
    command: ["codex", "exec", "--json", "--model", "${model}", "--config", "model_reasoning_effort=${reasoning_effort}"]
    input_mode: "stdin"
    defaults:
      model: "gpt-5.3-codex"
      reasoning_effort: "high"
    session_support:
      metadata_mode: json_events_stdout
      resume:
        argv_prefix: ["resume", "${SESSION_ID}"]
        inherit_base_command: true
```

Notes:
- `session_support` is provider-template level; steps opt into it.
- The runtime should fail validation if a step requests resume mode on a provider that does not declare `session_support`.
- The first implementation can support only one metadata mode if needed (Codex JSON events on stdout).
- `inherit_base_command: true` means the runtime derives the resume invocation from the same base provider command/params as fresh invocation, then inserts the provider-specific resume prefix/arguments. This avoids model/reasoning drift between fresh and resume modes.
- The ADR must define the exact command-derivation rule for Codex. If later providers cannot fit this model, broaden the schema only after a second concrete provider proves the need.
- For the Codex-first slice, `metadata_mode: json_events_stdout` means `--json` is part of the command contract. The runtime must parse JSONL events from stdout, extract the final assistant message for normal step output, and separately capture session metadata from the same stream.

### Step-level provider session mode

Add an optional step field:

```yaml
provider_session:
  mode: fresh|resume
  session_id_from: <artifact-name>   # required for resume
```

Rules:
- default is no provider-session semantics (existing provider behavior)
- `mode: fresh` tells runtime to capture a provider session handle if the provider supports it
- `mode: resume` requires the provider to support resume and requires `session_id_from`
- `session_id_from` should reference a consumed scalar `string` artifact name, not a raw path

### Runtime metadata persistence

Every provider step with `provider_session.mode: fresh|resume` should persist provider metadata in a deterministic runtime-owned file under the run root using an append-only path, for example:
- `.orchestrate/runs/<run_id>/provider_sessions/<step_index>-<Step>.json`
- or `.orchestrate/runs/<run_id>/provider_sessions/<Step>__v<invocation_ordinal>.json`

Suggested contents:
- provider name
- invocation mode (`fresh|resume`)
- captured `session_id`
- provider-native thread/session metadata if available
- command shape used
- timestamp

This file is for observability/debugging. Workflow control flow should still move through typed artifacts, not implicit metadata reads.

### Publishing session handles

Keep publish/consume aligned with current contracts:
- runtime captures provider session metadata, writes the run-owned metadata file, and synthesizes a deterministic workspace-local session-id file before output-contract validation
- `expected_outputs` validates/parses that synthesized file as `string`
- `publishes` can publish it into a scalar artifact such as `implementation_session_id`
- resume steps `consume` that artifact and bind it through `provider_session.session_id_from`

This keeps provider-session state in the same artifact/dataflow model as the rest of the DSL.

### Runtime ownership and stdout semantics

The ADR/spec task must pin down this ordering explicitly:

1. compose provider prompt using the existing prompt rules
2. execute the provider command
3. capture stdout/stderr according to the provider-session-aware runtime path
4. if `provider_session.mode: fresh`, parse provider session metadata from the declared provider metadata channel
5. persist runtime-owned provider metadata under an append-only path in `.orchestrate/runs/<run_id>/provider_sessions/`
6. synthesize any runtime-owned deterministic session-id file needed by `expected_outputs`
7. run normal deterministic output validation

For the Codex-first slice, the implementation should explicitly model how JSON event parsing coexists with normal stdout capture. The planned contract should be:
- Codex session-enabled steps run with `--json`
- runtime parses stdout as JSONL events
- runtime extracts the final assistant text and feeds that into the existing `output_file` / `output_capture` path
- runtime extracts session metadata from the same event stream
- raw JSONL may still be preserved under run logs for debugging

This must be implemented in the workflow execution/output-capture path, not only in provider-layer helpers.

### Output-contract injection rule for runtime-owned session files

The ADR/spec task must define one of these explicit rules for the first slice:

1. provider-session fresh steps require `inject_output_contract: false`, and prompts must describe only provider-authored outputs; or
2. runtime-owned `expected_outputs` entries are excluded from automatic provider output-contract injection.

Do not leave this implicit. The provider must not be instructed to write the runtime-owned session-id file.

## Task Breakdown

### Task 1: Write the feature ADR/spec note

**Files:**
- Create: `docs/plans/2026-03-06-provider-session-resume-workflows-adr.md`
- Reference: `specs/providers.md`
- Reference: `specs/dsl.md`
- Reference: `specs/io.md`
- Reference: `specs/state.md`
- Reference: `specs/observability.md`
- Reference: `specs/variables.md`

**Step 1: Write the ADR/spec note**

Document:
- the fresh-review-resume-review use case
- why provider-session-resume is distinct from workflow `resume`
- why `string` typed artifacts are required
- proposed provider/session fields
- whether provider-session metadata files are part of the stable run-state contract or only auxiliary observability
- how session metadata capture interacts with existing stdout/stderr and `output_file` semantics
- whether `${SESSION_ID}` is a normal provider-template placeholder, a provider-session-only token, or an internal runtime substitution token
- invariants and non-goals

**Step 2: Read the ADR back**

Run: `sed -n '1,220p' docs/plans/2026-03-06-provider-session-resume-workflows-adr.md`
Expected: coherent design with explicit runtime/dataflow boundaries

**Step 3: Commit**

```bash
git add docs/plans/2026-03-06-provider-session-resume-workflows-adr.md
git commit -m "docs: define provider session resume workflow design"
```

### Task 2: Add failing spec/loader/runtime tests for `string` artifacts

**Files:**
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_output_contract.py`
- Modify: `tests/test_artifact_dataflow_integration.py`

**Step 1: Write failing tests for `string` support**

Cover:
- `expected_outputs.type: string`
- `output_bundle.fields[].type: string`
- top-level scalar artifacts with `type: string`
- loader still rejects `kind: relpath` with `type: string`
- publish/consume of scalar `string` artifacts behaves like other scalar artifact types

**Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py -k string -q`
Expected: FAIL because `string` is not yet supported

**Step 3: Implement minimal support**

Modify:
- `orchestrator/loader.py`
- `orchestrator/contracts/output_contract.py`
- `orchestrator/workflow/executor.py`
- any shared type/validation helpers touched by those modules

Implementation rules:
- `string` is allowed only for scalar outputs/artifacts
- parsing is raw trimmed UTF-8 text, no enum restriction
- current numeric/bool/relpath behavior must not change

**Step 4: Re-run targeted tests**

Run: `pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py -k string -q`
Expected: PASS

**Step 5: Collect-only if tests were added/renamed**

Run: `pytest --collect-only tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py -q`
Expected: new string tests are collected

**Step 6: Commit**

```bash
git add tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py orchestrator/loader.py orchestrator/contracts/output_contract.py orchestrator/workflow/executor.py
git commit -m "feat: support string artifact contracts"
```

### Task 3: Prove the Codex-only provider-session runtime shape before generic schema work

**Files:**
- Create: `tests/test_provider_session_codex_runtime.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/registry.py`
- Modify: `orchestrator/workflow/executor.py`

**Step 1: Write failing runtime tests for the concrete Codex path**

Cover:
- fresh Codex invocation with session capture enabled preserves current stdin prompt delivery
- fresh Codex invocation can parse session metadata from the chosen metadata channel
- resume Codex invocation derives from the same base provider command/params as fresh invocation
- resume Codex invocation inserts the session id without dropping model/reasoning config
- runtime can persist session metadata and synthesize a deterministic session-id file before output validation
- session-enabled Codex steps preserve a coherent `output_file` / `output_capture` contract by extracting final assistant text from the JSONL stream
- provider-session fresh steps do not instruct the model to write the runtime-owned session-id file
- explicit failure if the provider output does not contain a session id in the declared format

Prefer faked provider execution / monkeypatched executor over real CLI calls.

**Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_provider_session_codex_runtime.py -q`
Expected: FAIL because runtime has no provider-session path yet

**Step 3: Implement minimal Codex runtime support**

Modify:
- `orchestrator/providers/executor.py`
- `orchestrator/providers/types.py`
- `orchestrator/providers/registry.py`
- `orchestrator/workflow/executor.py`
- any helper/result types needed by those modules

Implementation shape:
- extend prepared provider invocation/result models with optional session metadata
- support one concrete metadata mode for Codex
- on `mode: fresh`, runtime captures provider session metadata
- on `mode: resume`, runtime derives the Codex resume command from the base provider command + provider params
- extract final assistant text from Codex JSONL for normal output capture
- persist runtime-owned session metadata under run root
- synthesize the deterministic session-id file before output validation
- make output-contract injection safe for runtime-owned session files in the first slice
- keep existing non-session provider path unchanged

**Step 4: Re-run targeted tests**

Run: `pytest tests/test_provider_session_codex_runtime.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_provider_session_codex_runtime.py orchestrator/providers/executor.py orchestrator/providers/types.py orchestrator/providers/registry.py orchestrator/workflow/executor.py
git commit -m "feat: add codex provider session runtime support"
```

### Task 4: Add failing provider-session schema tests

**Files:**
- Create: `tests/test_provider_session_schema.py`
- Modify: `orchestrator/loader.py`
- Modify: `specs/providers.md`
- Modify: `specs/dsl.md`

**Step 1: Write failing loader tests for provider session fields**

Cover:
- valid `provider_session.mode: fresh`
- valid `provider_session.mode: resume` with `session_id_from`
- invalid mode value
- `resume` on provider without `session_support`
- `resume` without `session_id_from`
- `session_id_from` referencing non-consumed / non-string artifact should be rejected (or at minimum validated later with explicit runtime error if cross-step validation is too hard for first pass)

**Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_provider_session_schema.py -q`
Expected: FAIL because schema/validation does not exist

**Step 3: Implement loader/schema support**

Modify:
- `orchestrator/loader.py`
- any provider template models in `orchestrator/providers/types.py`

Add:
- provider-template `session_support`
- step-level `provider_session`
- validation rules listed above

**Step 4: Update specs**

Modify:
- `specs/providers.md`
- `specs/dsl.md`
- `specs/versioning.md`
- `specs/acceptance/index.md`
- `specs/state.md`
- `specs/observability.md`
- `specs/io.md`
- `specs/variables.md` (if the final design introduces normative placeholder behavior beyond existing provider-param substitution)

Be explicit about version gating and first-pass limitations.

**Step 5: Re-run targeted tests**

Run: `pytest tests/test_provider_session_schema.py -q`
Expected: PASS

**Step 6: Commit**

```bash
git add tests/test_provider_session_schema.py orchestrator/loader.py orchestrator/providers/types.py specs/providers.md specs/dsl.md specs/versioning.md specs/acceptance/index.md
git commit -m "feat: add provider session workflow schema"
```

### Task 5: Add an example workflow covering fresh-review-resume-review

**Files:**
- Create: `workflows/examples/provider_session_review_loop.yaml`
- Create: `prompts/workflows/provider_session_review_loop/implement.md`
- Create: `prompts/workflows/provider_session_review_loop/review.md`
- Create: `prompts/workflows/provider_session_review_loop/fix.md`
- Create: `tests/test_provider_session_example.py`

**Step 1: Write the example workflow**

Pattern:
- `ImplementFresh` publishes `implementation_session_id` and `implementation_report`
- `ReviewFresh` publishes `review_report` and `review_decision`
- gate to `ResumeImplementation` on `REVISE`
- `ResumeImplementation` consumes `implementation_session_id` and `review_report`
- `ReviewFresh` (new step name or repeated review step) runs again on the updated artifact

Use deterministic artifacts for:
- session id (`string`)
- implementation report (`relpath`)
- review report (`relpath`)
- review decision (`enum`)

**Step 2: Write validation/example tests**

Test:
- loader accepts the workflow
- dry-run validation succeeds
- example uses only documented fields

**Step 3: Run targeted tests**

Run: `pytest tests/test_provider_session_example.py -q`
Expected: PASS

**Step 4: Dry-run the example**

Run: `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/provider_session_review_loop.yaml --dry-run`
Expected: workflow validation successful

**Step 5: Commit**

```bash
git add workflows/examples/provider_session_review_loop.yaml prompts/workflows/provider_session_review_loop tests/test_provider_session_example.py
git commit -m "docs: add provider session review loop example"
```

### Task 6: Update docs and run full relevant verification

**Files:**
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `tests/README.md`
- Modify: `docs/index.md`
- Modify: `workflows/examples/README_v0_artifact_contract.md` only if the example/runbook index should explicitly point readers to the new provider-session workflow pattern

**Step 1: Document the feature**

Add:
- distinction between workflow run resume and provider session resume
- how session ids are published/consumed
- provider capability limitations
- warning that provider-session-resume is opt-in per provider template
- how provider-session metadata files should be interpreted (stable contract vs debug artifact)
- any stdout/event-channel caveats for resume-capable providers

**Step 2: Run the focused verification stack**

Run:
```bash
pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py tests/test_provider_session_codex_runtime.py tests/test_provider_session_schema.py tests/test_provider_session_example.py -q
```
Expected: PASS

**Step 3: Collect-only for new test modules**

Run:
```bash
pytest --collect-only tests/test_provider_session_codex_runtime.py tests/test_provider_session_schema.py tests/test_provider_session_example.py -q
```
Expected: all new tests collected

**Step 4: Re-run an orchestrator smoke check**

Run:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/provider_session_review_loop.yaml --dry-run
```
Expected: workflow validation successful

**Step 5: Commit**

```bash
git add docs/runtime_execution_lifecycle.md docs/workflow_drafting_guide.md tests/README.md docs/index.md
git commit -m "docs: document provider session resume workflows"
```

## Recommended First Slice

The main plan should follow the smallest proven path:
1. add scalar `string` artifacts, including publish/consume coverage
2. prove one concrete Codex runtime path end-to-end
3. add the DSL/schema surface only after the Codex runtime semantics are stable
4. add one example workflow using fresh-review-resume-review
5. defer broader provider generalization until a second provider creates real pressure for it

This is the fastest path to proving the feature without over-designing a provider-agnostic abstraction.

## Key Risks

1. **Session handle capture may be provider-specific**
   - Codex may expose session IDs differently than Claude or other CLIs.
   - Mitigation: prove the Codex path first and only then stabilize the generic provider schema around what actually worked.

2. **Provider stdout may be dual-purpose (logs vs structured metadata)**
   - If session capture depends on stdout JSON events, naive parsing can corrupt ordinary step output capture.
   - Mitigation: define one explicit metadata channel, require `--json` for Codex session steps, and test extraction of final assistant text into the normal output-capture path before broad rollout.

3. **Arbitrary shell/provider writes can bypass runtime namespace assumptions**
   - This is why repo-root `cwd` should not be the default inside call-frame-like provider session flows if we later combine these features.
   - For this feature, keep focus on provider command shaping and deterministic artifacts, not filesystem sandboxing.

4. **Confusing workflow resume with provider session resume**
   - Mitigation: specs/docs/examples must distinguish them aggressively.

5. **Publishing session handles without string artifacts would create ugly file-pointer workarounds**
   - Mitigation: do not implement provider session resume before `string` support exists.

6. **Repeated resume/fix loops can overwrite provider-session metadata**
   - Mitigation: use append-only provider-session metadata paths keyed by step index or invocation ordinal, not one file per step name.
