# Provider Structured Output Path Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider `output_bundle` and `variant_output` write targets runtime-owned instead of relying only on prompt-text path obedience.

**Architecture:** Mirror the existing command structured-output authority model for provider steps: resolve the structured bundle path before provider launch, pass the exact path through a reserved runtime-owned environment variable and invocation context, render prompt text that names the runtime-owned path as authoritative, and keep post-execution validation as the semantic gate. This is a narrow runtime contract hardening; StateLayout path simplification remains a follow-on tranche.

**Tech Stack:** Python, pytest, orchestrator provider runtime, Workflow Lisp lowering, DSL/spec docs.

---

## Background

The generic review/revise design-doc workflow failed after the reviewer returned
`REVISE`. The provider wrote a valid-looking JSON bundle to:

```text
.../__result_bundle/result_bundle.json
```

but runtime validation expected:

```text
.../__result_bundle.json
```

The prompt contract had the correct expected file path. The provider still
used a directory-style interpretation. That means the current provider
structured-output path contract is too prompt-dependent. Command steps already
have a stronger boundary through `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; provider
steps need an equivalent runtime-owned binding.

Do not fix this by copying wrong-path files into place. That would recover one
run while preserving the weak authority boundary.

## File Structure

- Modify `specs/io.md`
  - Owns normative IO behavior for provider structured-output path binding.
- Modify `specs/dsl.md`
  - Owns provider-step `output_bundle` / `variant_output` semantics.
- Modify `docs/design/workflow_lisp_runtime_migration_foundation.md`
  - Records the migration foundation and should name provider structured-output
    path authority as a foundation gap or tranche requirement.
- Modify `docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md`
  - Add the provider-output path authority failure as an observed gap.
- Modify `orchestrator/workflow/executor.py`
  - Resolve provider structured-output paths before launch and pass reserved
    env/context into provider invocation.
- Modify `orchestrator/providers/executor.py`
  - Ensure reserved env values win over provider/user env and reach the child
    provider process for argv and stdin providers.
- Modify `orchestrator/workflow/prompting.py`
  - Render prompt contract wording that says the runtime-provided path is the
    authoritative write target.
- Modify `orchestrator/contracts/prompt_contract.py`
  - Add stable wording for provider structured-output path authority.
- Modify or add tests:
  - `tests/test_prompt_contract_injection.py`
  - `tests/test_workflow_lisp_examples.py` or a narrower Workflow Lisp example
    test if available
  - `tests/test_provider_executor.py` if present; otherwise use the existing
    provider runtime tests closest to `ProviderExecutor.prepare_invocation`.
  - `tests/test_workflow_lisp_phase_translation.py` or
    `tests/test_workflow_lisp_examples.py` for the generic review workflow
    launch/dry-run path.

## Contract Decisions

Use one reserved variable for both provider and command structured bundles:

```text
ORCHESTRATOR_OUTPUT_BUNDLE_PATH
```

Rationale:

- the variable already names the semantic concept, not the execution kind;
- provider steps have at most one deterministic structured bundle surface per
  step;
- reusing the variable avoids creating separate prompt instructions for
  output bundles versus variant bundles.

Runtime rules:

- For provider steps with `output_bundle.path` or `variant_output.path`, resolve
  the path before provider invocation through the same path-safety logic used
  for post-execution validation.
- Pass the resolved workspace-relative path as
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
- Runtime-owned value wins over authored/provider-template env values.
- Prompt text still includes the path and schema, but also states that
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is the authoritative write target.
- Post-execution validation remains authoritative. If the provider writes any
  other path, the step fails with `missing_bundle_file`.
- Do not add compatibility normalization from
  `.../__result_bundle/result_bundle.json` to `.../__result_bundle.json` in the
  first tranche. That would hide path-authority violations.

## Task 1: Add Failing Provider Env Binding Test

**Files:**

- Modify: `tests/test_prompt_contract_injection.py`

- [x] **Step 1: Add a provider `variant_output` env binding regression**

Add a test near the existing provider variant-output prompt tests:

```python
def test_provider_variant_output_receives_runtime_bundle_env(tmp_path: Path, monkeypatch) -> None:
    """Provider structured outputs receive the runtime-owned bundle path out of band."""
    workflow = {
        "version": "2.14",
        "name": "provider-variant-output-env",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; test \"$ORCHESTRATOR_OUTPUT_BUNDLE_PATH\" = \"state/review.json\""],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompt.md",
            "variant_output": {
                "path": "state/review.json",
                "discriminant": {
                    "name": "variant",
                    "json_pointer": "/variant",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                },
                "variants": {
                    "APPROVE": {"fields": []},
                    "REVISE": {"fields": []},
                },
            },
        }],
    }
```

Write the prompt file and use the existing helper style in this module. Mock the
provider execution if that is how adjacent tests inspect invocation env; if not,
let the command run and make it write the required bundle to the env path:

```bash
python - <<'PY'
import json, os
path = os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
os.makedirs(os.path.dirname(path), exist_ok=True)
open(path, "w", encoding="utf-8").write(json.dumps({"variant": "REVISE"}) + "\n")
PY
```

- [x] **Step 2: Run the failing test**

Run:

```bash
pytest tests/test_prompt_contract_injection.py::test_provider_variant_output_receives_runtime_bundle_env -q
```

Expected before implementation:

- fail because provider env lacks `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; or
- fail because provider env has an override value instead of the runtime path.

## Task 2: Pass Runtime-Owned Bundle Env Into Provider Invocation

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/providers/executor.py`

- [x] **Step 1: Locate provider execution env merge**

Read the provider-step execution path in `orchestrator/workflow/executor.py`.
Find where it calls:

```python
self.provider_executor.prepare_invocation(...)
```

and where provider step `env` is prepared.

- [x] **Step 2: Resolve structured output contract paths for provider steps**

In the provider path, call the existing:

```python
_, resolved_output_bundle, path_error = self._resolve_output_contract_paths(
    step,
    state,
    context=context,
)
```

before provider invocation.

If `path_error` is not `None`, persist a contract violation and do not call the
provider.

- [x] **Step 3: Add runtime-owned env var after authored env merge**

When `resolved_output_bundle` is a dict with a string `path`, create an env map:

```python
provider_env = {}
if isinstance(step.get("env"), dict):
    provider_env.update(step["env"])
provider_env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = bundle_path
```

Use assignment, not `setdefault`, so runtime wins over authored env. The command
path currently uses `setdefault`; update command behavior only if tests show it
violates `specs/io.md`, but avoid broad refactors in this task unless needed.

- [x] **Step 4: Ensure ProviderExecutor preserves caller env**

In `orchestrator/providers/executor.py`, verify that `prepare_invocation` stores
the supplied `env` on the `ProviderInvocation`, and that `execute` merges it
into the child process environment after provider-template env values.

If it currently drops `env`, add the field or merge. Keep this generic; do not
special-case output bundles inside `ProviderExecutor`.

- [x] **Step 5: Run the provider env test**

Run:

```bash
pytest tests/test_prompt_contract_injection.py::test_provider_variant_output_receives_runtime_bundle_env -q
```

Expected: PASS.

- [x] **Step 6: Add output-bundle sibling test**

Add:

```python
def test_provider_output_bundle_receives_runtime_bundle_env(...)
```

Use `output_bundle.path`, write the JSON bundle through the env path, and assert
the parsed artifact appears in state.

Run:

```bash
pytest tests/test_prompt_contract_injection.py::test_provider_output_bundle_receives_runtime_bundle_env -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add orchestrator/workflow/executor.py orchestrator/providers/executor.py tests/test_prompt_contract_injection.py
git commit -m "runtime: pass provider bundle paths out of band"
```

## Task 3: Make Prompt Contract Wording Match The New Authority Boundary

**Files:**

- Modify: `orchestrator/contracts/prompt_contract.py`
- Modify: `tests/test_prompt_contract_injection.py`

- [x] **Step 1: Add failing prompt wording assertion**

Update or add a test near `test_provider_variant_output_appends_variant_contract_block_to_prompt`:

```python
assert "ORCHESTRATOR_OUTPUT_BUNDLE_PATH" in captured["prompt"]
assert "authoritative write target" in captured["prompt"]
```

Do the same for provider `output_bundle`.

- [x] **Step 2: Run the prompt tests to see failure**

Run:

```bash
pytest tests/test_prompt_contract_injection.py -k "provider_variant_output_appends or provider_output_bundle_appends" -q
```

Expected before implementation: FAIL because prompt suffix does not mention the
runtime-owned env path.

- [x] **Step 3: Update prompt contract renderer**

In `orchestrator/contracts/prompt_contract.py`, update both
`render_output_bundle_contract_block(...)` and
`render_variant_output_contract_block(...)` to include concise wording:

```text
When ORCHESTRATOR_OUTPUT_BUNDLE_PATH is present, write the JSON bundle to that
exact file. The path shown below is the same runtime-owned target and is not a
directory.
```

Keep the existing literal `path:` line because it remains useful in logs,
provider prompts, and non-env providers.

- [x] **Step 4: Run prompt tests**

Run:

```bash
pytest tests/test_prompt_contract_injection.py -k "provider_variant_output_appends or provider_output_bundle_appends or runtime_bundle_env" -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/contracts/prompt_contract.py tests/test_prompt_contract_injection.py
git commit -m "providers: clarify structured output path authority"
```

## Task 4: Add Wrong-Path Negative Test For Provider Bundles

**Files:**

- Modify: `tests/test_prompt_contract_injection.py`

- [x] **Step 1: Add regression for directory-style wrong path**

Add:

```python
def test_provider_variant_output_rejects_directory_style_result_bundle_path(tmp_path: Path) -> None:
    ...
```

Provider command should intentionally write:

```text
state/review/result_bundle.json
```

while contract expects:

```text
state/review.json
```

Assert:

```python
assert state["status"] == "failed"
error = state["steps"]["Review"]["error"]
assert error["type"] == "contract_violation"
assert error["context"]["violations"][0]["type"] == "missing_bundle_file"
assert error["context"]["violations"][0]["context"]["path"] == "state/review.json"
```

- [x] **Step 2: Run the negative test**

Run:

```bash
pytest tests/test_prompt_contract_injection.py::test_provider_variant_output_rejects_directory_style_result_bundle_path -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_prompt_contract_injection.py
git commit -m "providers: test wrong structured bundle paths"
```

## Task 5: Verify Workflow Lisp Generic Review Workflow Path

**Files:**

- Modify: `tests/test_workflow_lisp_examples.py` if a runnable generic review
  fixture test exists there; otherwise add a focused test in
  `tests/test_workflow_lisp_examples.py`.

- [x] **Step 1: Use existing generic review `.orc` compile/shared-validation test**

Use:

```text
workflows/examples/review_revise_design_docs.orc
```

Assert that lowered provider review/fix steps with `variant_output` or
`output_bundle` receive hidden result-bundle inputs and that runtime invocation
will expose `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

If this is hard to assert without executing providers, keep the test at the
runtime provider level and add a dry-run check only.

- [x] **Step 2: Run focused Workflow Lisp test**

Run the narrowest test selector added or changed:

```bash
pytest tests/test_workflow_lisp_examples.py -k "review_revise_design_docs" -q
```

Expected: PASS.

- [x] **Step 3: Run the real dry-run command**

Run:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc \
  --entry-workflow review-revise-design-docs \
  --provider-externs-file .orchestrate/tmp/review-revise-design-docs-runtime-foundation/providers.json \
  --prompt-externs-file .orchestrate/tmp/review-revise-design-docs-runtime-foundation/prompts.json \
  --input-file .orchestrate/tmp/review-revise-design-docs-runtime-foundation/inputs.json \
  --dry-run
```

Expected: validation succeeds. Existing redundant-relpath lint warnings may
remain unless this task explicitly removes them.

- [ ] **Step 4: Commit**

```bash
git add tests/test_workflow_lisp_examples.py
git commit -m "workflow_lisp: cover generic review provider bundle path"
```

Skip this commit if no Workflow Lisp test file needed changes.

## Task 6: Update Specs And Design Docs

**Files:**

- Modify: `specs/io.md`
- Modify: `specs/dsl.md`
- Modify: `docs/design/workflow_lisp_runtime_migration_foundation.md`
- Modify: `docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md`

- [x] **Step 1: Update `specs/io.md`**

In the structured bundle section, add provider behavior:

```markdown
- Provider structured-bundle environment:
  - For provider steps with `output_bundle.path` or `variant_output.path`, the
    runtime resolves the workspace-relative bundle path before provider launch
    and exposes it as `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
  - The runtime-owned value wins over provider-template or authored env values.
  - The prompt contract may repeat the path and schema, but the runtime-owned
    path remains the semantic write target.
  - If the provider exits successfully but the declared bundle is missing or
    invalid, the step fails as an output-contract failure.
```

- [x] **Step 2: Update `specs/dsl.md`**

Under `output_bundle` and `variant_output`, clarify provider handling:

```markdown
Provider steps receive the resolved bundle path out of band through
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; prompt injection describes the same contract
but is not the only authority for the write location.
```

- [x] **Step 3: Update runtime migration foundation design**

In `docs/design/workflow_lisp_runtime_migration_foundation.md`, add provider
structured-output path authority to the foundation:

- either as a subsection of Tranche 1; or
- as a prerequisite under command/provider structured-output authority.

Avoid broad StateLayout edits in this task except to explicitly say path
simplification is follow-up.

- [x] **Step 4: Update runtime gap report**

In
`docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md`, add
the observed provider failure:

- expected `...__result_bundle.json`;
- provider wrote `...__result_bundle/result_bundle.json`;
- root cause is provider structured-output path authority being prompt-only;
- principled fix is runtime-owned provider bundle path binding.

- [x] **Step 5: Run docs sanity checks**

Run:

```bash
git diff --check -- specs/io.md specs/dsl.md docs/design/workflow_lisp_runtime_migration_foundation.md docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add specs/io.md specs/dsl.md docs/design/workflow_lisp_runtime_migration_foundation.md docs/reports/2026-06-08-generic-review-revise-orc-runtime-gap-report.md
git commit -m "docs: define provider bundle path authority"
```

## Task 7: End-To-End Verification

**Files:**

- No code changes expected.

- [x] **Step 1: Run narrow provider/prompt tests**

Run:

```bash
pytest tests/test_prompt_contract_injection.py -k "bundle_env or output_bundle_receives_runtime or variant_output_receives_runtime or directory_style_result_bundle" -q
```

Expected: PASS.

- [x] **Step 2: Run output-contract tests touched by adjacent runtime work**

Run:

```bash
pytest tests/test_output_contract.py::test_validate_contract_value_accepts_json_string_list_contracts tests/test_dataflow.py::test_enforce_consumes_contract_accepts_collection_artifacts tests/test_v214_runtime_semantics.py::test_materialize_artifacts_writes_pointer_for_string_input -q
```

Expected: PASS.

- [x] **Step 3: Relaunch the generic review workflow**

Run without summaries or notes:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc \
  --entry-workflow review-revise-design-docs \
  --provider-externs-file .orchestrate/tmp/review-revise-design-docs-runtime-foundation/providers.json \
  --prompt-externs-file .orchestrate/tmp/review-revise-design-docs-runtime-foundation/prompts.json \
  --input-file .orchestrate/tmp/review-revise-design-docs-runtime-foundation/inputs.json \
  --stream-output
```

Expected:

- provider review step reaches execution;
- if reviewer returns `REVISE`, runtime finds the declared result bundle at the
  exact `variant_output.path`;
- loop proceeds into fix step rather than failing with `missing_bundle_file`.

- [x] **Step 4: Inspect run state**

Run:

```bash
python - <<'PY'
from pathlib import Path
import json
run = "<new-run-id>"
d = json.loads((Path(".orchestrate/runs") / run / "state.json").read_text())
print(d.get("status"))
for name, step in d.get("steps", {}).items():
    if isinstance(step, dict) and step.get("status") == "failed":
        print(name, step.get("error"))
PY
```

Expected: no provider review `missing_bundle_file` failure.

Observed while executing this plan:

- launched run `20260608T231536Z-ig5heu` in tmux session `rr-runtime-fix`;
- bounded polling showed the run still active in the review loop with no failed
  step recorded;
- no `missing_bundle_file` failure had occurred during the polling window.

- [ ] **Step 5: Commit verification-only fixture updates if any**

If the real run requires only generated artifacts, do not commit run artifacts.
If a checked-in fixture or prompt needed a durable correction, commit it with:

```bash
git add <fixture-or-prompt>
git commit -m "workflow_lisp: keep generic review fixture runnable"
```

## Task 8: Final Cleanup And Push

**Files:**

- No code changes expected.

- [x] **Step 1: Run final narrow suite**

Run:

```bash
pytest tests/test_prompt_contract_injection.py tests/test_output_contract.py::test_validate_contract_value_accepts_json_string_list_contracts tests/test_dataflow.py::test_enforce_consumes_contract_accepts_collection_artifacts tests/test_v214_runtime_semantics.py::test_materialize_artifacts_writes_pointer_for_string_input -q
```

Expected: PASS.

- [x] **Step 2: Check staged/unstaged state**

Run:

```bash
git status --short
```

Expected: only unrelated pre-existing dirty files remain.

- [ ] **Step 3: Push**

Run:

```bash
git push
```

Expected: current branch updates its upstream.

## Follow-On Work Not In This Plan

- Do not simplify all generated hidden bundle paths in this tranche.
- Do not move SourceMap or Semantic IR entry construction into
  `PathAllocator`.
- Do not normalize wrong provider bundle paths as a compatibility bridge unless
  a separate migration design accepts that behavior.
- Do not redesign provider sessions, summaries, live notes, or command adapter
  contracts.

The next StateLayout tranche should make generated file-vs-directory path
roles less ambiguous, but this plan fixes the immediate authority bug without
waiting for full path-layout migration.
