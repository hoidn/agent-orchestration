# KISS Provider Role Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let reusable workflow stacks route selected provider steps, starting with `ExecuteImplementation`, to a caller-selected provider alias such as `claude_opus` while preserving current all-Codex defaults.

**Architecture:** Keep the existing `provider:` field and add compatible runtime substitution for provider names, for example `provider: "${inputs.implementation_execute_provider}"`. Reusable workflows define their own supported provider aliases and expose role-specific typed inputs with defaults; callers pass those inputs through existing `call.with` refs. This avoids PATH shims, prompt-text routing, implicit provider namespace merging, and new provider-map/plugin surfaces.

**Tech Stack:** Python orchestrator runtime, YAML DSL workflows, existing `VariableSubstitutor`, provider registry/executor, pytest.

---

## File Structure

- Modify `orchestrator/loader.py`
  - Allow `${...}` validation in the provider field.
  - Reject dynamic provider fields on `provider_session` steps for this first tranche because loader-time session-support validation requires a known static provider template.

- Modify `orchestrator/workflow/executor.py`
  - Resolve `step["provider"]` through the existing provider substitution context before calling `ProviderExecutor.prepare_invocation`.
  - Fail with exit code `2` and clear context when the provider field resolves to an empty value, has undefined variables, or names an unknown provider alias.

- Modify `specs/dsl.md`, `specs/providers.md`, and `specs/variables.md`
  - Document that provider steps may use variable substitution in `provider`.
  - State that provider aliases remain scoped to the active workflow/callee namespace.
  - State that adjudicated provider candidate/evaluator provider fields and provider-session steps remain static in this tranche.

- Modify `workflows/library/neurips_backlog_implementation_phase.yaml`
  - Add role inputs:
    - `implementation_execute_provider`
    - `implementation_review_provider`
    - `implementation_fix_provider`
  - Add a callee-local `claude_opus` provider alias.
  - Change implementation execute/review/fix steps to use the role inputs.

- Modify `workflows/library/neurips_selected_backlog_item.yaml`
  - Add the same role inputs with defaults.
  - Pass role inputs to `RunImplementationPhase` using `{ref: inputs.<role>}`.

- Modify `workflows/examples/neurips_steered_backlog_drain.yaml`
  - Add the same top-level role inputs with defaults.
  - Pass role inputs to `RunSelectedItem` using `{ref: inputs.<role>}`.

- Modify or add tests:
  - `tests/test_loader_validation.py`
  - `tests/test_provider_role_routing.py`
  - `tests/test_neurips_workflow_validation.py` if an existing NeurIPS workflow validation test file exists; otherwise add coverage to the closest existing NeurIPS workflow test module.

- Modify the one downstream PtychoPINN NeurIPS workflow after canonical verification:
  - `/home/ollie/Documents/PtychoPINN/workflows/examples/neurips_steered_backlog_drain.yaml`
  - `/home/ollie/Documents/PtychoPINN/workflows/library/neurips_selected_backlog_item.yaml`
  - `/home/ollie/Documents/PtychoPINN/workflows/library/neurips_backlog_implementation_phase.yaml`
  - keep canonical/library defaults as `codex` with `gpt-5.4` and `high`
  - configure only that NeurIPS workflow/run surface so `ExecuteImplementation` is assigned to Claude Opus 4.7 high
  - do not change global provider defaults or unrelated workflows in PtychoPINN

## Design Constraints

- Do not introduce `provider_ref`, provider maps, provider plugins, or caller/callee provider namespace merging.
- Do not route based on prompt content.
- Do not change `adjudicated_provider` candidate or evaluator provider fields in this item.
- Do not make dynamic provider selection work with `provider_session` in this item; reject that combination explicitly.
- Preserve existing workflow behavior when no role inputs are supplied.
- Keep the default implementation provider as Codex/GPT-5.4 high. The Claude Opus assignment is only for `/home/ollie/Documents/PtychoPINN/workflows/examples/neurips_steered_backlog_drain.yaml`, not a global default.

## Task 1: Runtime Provider Field Substitution Tests

**Files:**
- Create: `tests/test_provider_role_routing.py`
- Modify: none

- [ ] **Step 1: Write a failing test for dynamic provider selection**

Create a minimal workflow with two provider aliases and a provider step that uses `${inputs.selected_provider}`:

```python
def test_provider_field_can_resolve_from_workflow_input(tmp_path, monkeypatch):
    workflow_path = tmp_path / "dynamic-provider.yaml"
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Say hello.", encoding="utf-8")
    workflow_path.write_text(
        """
version: "2.7"
name: dynamic-provider-test
inputs:
  selected_provider:
    type: enum
    allowed: ["alpha", "beta"]
    default: "beta"
providers:
  alpha:
    command: ["bash", "-lc", "printf alpha"]
    input_mode: stdin
  beta:
    command: ["bash", "-lc", "printf beta"]
    input_mode: stdin
steps:
  - name: Ask
    provider: "${inputs.selected_provider}"
    input_file: prompt.md
    output_capture: text
""",
        encoding="utf-8",
    )

    result = run_workflow_for_test(workflow_path, workspace=tmp_path)

    assert result["steps"]["Ask"]["status"] == "completed"
    assert result["steps"]["Ask"]["output"] == "beta"
```

Use the helper style already present in nearby workflow execution tests rather than inventing a separate runner.

- [ ] **Step 2: Run the new test to verify it fails**

Run: `pytest tests/test_provider_role_routing.py::test_provider_field_can_resolve_from_workflow_input -q`

Expected: FAIL because `step["provider"]` is currently passed literally as `"${inputs.selected_provider}"`.

- [ ] **Step 3: Write a failing test for unknown resolved provider**

Add a workflow where `selected_provider` defaults to `"missing"` and the only provider alias is `alpha`.

Expected result:

```python
assert result["steps"]["Ask"]["status"] == "failed"
assert result["steps"]["Ask"]["exit_code"] == 2
assert result["steps"]["Ask"]["error"]["type"] == "provider_not_found"
assert result["steps"]["Ask"]["error"]["context"]["provider"] == "missing"
```

- [ ] **Step 4: Run both tests to verify they fail for the expected reasons**

Run:

```bash
pytest --collect-only tests/test_provider_role_routing.py -q
pytest tests/test_provider_role_routing.py -q
```

Expected: FAIL before implementation.

## Task 2: Implement Provider Name Resolution

**Files:**
- Modify: `orchestrator/workflow/executor.py`

- [ ] **Step 1: Add a helper to resolve provider names**

Add a small helper near provider execution helpers:

```python
def _resolve_provider_name_for_step(
    self,
    step: Dict[str, Any],
    provider_context: Dict[str, Any],
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    raw_provider = step.get("provider")
    step_name = step.get("name", f"step_{self.current_step}")
    if not isinstance(raw_provider, str) or not raw_provider.strip():
        return None, {
            "type": "validation_error",
            "message": "Provider step requires a non-empty provider name",
            "context": {"step": step_name, "provider": raw_provider},
        }
    try:
        resolved = self.variable_substitutor.substitute(raw_provider, provider_context)
    except ValueError as exc:
        return None, {
            "type": "substitution_error",
            "message": "Failed to substitute provider name",
            "context": {"step": step_name, "provider": raw_provider, "error": str(exc)},
        }
    if not isinstance(resolved, str) or not resolved.strip():
        return None, {
            "type": "validation_error",
            "message": "Provider name resolved to an empty value",
            "context": {"step": step_name, "provider": raw_provider, "resolved_provider": resolved},
        }
    return resolved.strip(), None
```

- [ ] **Step 2: Use the helper before `prepare_invocation`**

In `_execute_provider_with_context`, after `provider_context = self._create_provider_context(context, state)` and before the retry loop prepares an invocation, resolve once:

```python
resolved_provider_name, provider_name_error = self._resolve_provider_name_for_step(step, provider_context)
if provider_name_error is not None:
    return {
        "status": "failed",
        "exit_code": 2,
        "error": provider_name_error,
    }
```

Then pass `provider_name=resolved_provider_name` to `prepare_invocation`.

- [ ] **Step 3: Keep retry behavior unchanged**

Do not re-resolve the provider inside the retry loop. The provider selection is step-visit data, not an attempt-local decision.

- [ ] **Step 4: Run provider role tests**

Run: `pytest tests/test_provider_role_routing.py -q`

Expected: PASS.

## Task 3: Loader Guardrails and Spec Tests

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `tests/test_loader_validation.py`

- [ ] **Step 1: Allow `${env.*}` rejection to cover `provider`**

Change `_validate_variables_usage` so `provider` is in `variable_fields`:

```python
variable_fields = ["command", "input_file", "output_file", "provider", "provider_params"]
```

- [ ] **Step 2: Reject dynamic provider names with `provider_session`**

In `_validate_provider_session`, before looking up `provider_template`, reject templated provider names:

```python
provider_name = step.get("provider")
if isinstance(provider_name, str) and "${" in provider_name:
    self._add_error(f"{context} requires a static provider template")
    return
```

- [ ] **Step 3: Add loader validation tests**

Add tests that assert:

- `provider: "${context.provider_alias}"` is accepted on an ordinary provider step.
- `provider: "${env.PROVIDER}"` is rejected.
- `provider_session` plus `provider: "${context.provider_alias}"` is rejected with `requires a static provider template`.

- [ ] **Step 4: Run loader tests**

Run: `pytest tests/test_loader_validation.py -q`

Expected: PASS.

## Task 4: NeurIPS Workflow Role Inputs

**Files:**
- Modify: `workflows/library/neurips_backlog_implementation_phase.yaml`
- Modify: `workflows/library/neurips_selected_backlog_item.yaml`
- Modify: `workflows/examples/neurips_steered_backlog_drain.yaml`

- [ ] **Step 1: Add role inputs to the implementation phase**

Add these inputs to `workflows/library/neurips_backlog_implementation_phase.yaml`:

```yaml
  implementation_execute_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude_opus"]
    default: "codex"
  implementation_review_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude_opus"]
    default: "codex"
  implementation_fix_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude_opus"]
    default: "codex"
```

- [ ] **Step 2: Add the callee-local Claude provider alias**

In the same workflow, add:

```yaml
  claude_opus:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]
    input_mode: "argv"
    defaults:
      model: "claude-opus-4.7"
      effort: "high"
```

If the installed Claude CLI requires a different model identifier or high-thinking flag, keep the alias name `claude_opus` and adjust only the provider template command/defaults after checking the local CLI/docs. Do not change the `codex` default provider template, which should remain `gpt-5.4` with `high` effort.

- [ ] **Step 3: Route implementation phase steps through role inputs**

Change:

```yaml
provider: codex
```

to:

```yaml
provider: "${inputs.implementation_execute_provider}"
```

for `ExecuteImplementation`.

Use the review and fix inputs for the review and fix provider steps.

- [ ] **Step 4: Add matching inputs to selected backlog item workflow**

Add the same three inputs with the same defaults to `workflows/library/neurips_selected_backlog_item.yaml`.

- [ ] **Step 5: Pass selected backlog item inputs to implementation phase**

In `RunImplementationPhase.with`, add:

```yaml
      implementation_execute_provider:
        ref: inputs.implementation_execute_provider
      implementation_review_provider:
        ref: inputs.implementation_review_provider
      implementation_fix_provider:
        ref: inputs.implementation_fix_provider
```

- [ ] **Step 6: Add top-level inputs to the NeurIPS drain workflow**

Add the same three inputs with defaults to `workflows/examples/neurips_steered_backlog_drain.yaml`.

- [ ] **Step 7: Pass top-level role inputs to selected item workflow**

In the `RunSelectedItem.with` block, add the same three `{ref: inputs.<role>}` bindings.

- [ ] **Step 8: Validate workflow loading**

Run:

```bash
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-design.md \
  --input roadmap_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-roadmap.md \
  --input roadmap_gate_path=docs/backlog/roadmap_gate.json \
  --input progress_ledger_path=state/NEURIPS-HYBRID-RESNET-2026/progress_ledger.json \
  --input implementation_execute_provider=claude_opus
```

Expected: dry-run validation succeeds.

## Task 5: Workflow Routing Regression

**Files:**
- Modify or create: closest NeurIPS workflow test module, likely `tests/test_neurips_*workflow*.py` or `tests/test_major_project_workflows.py` depending on existing helper coverage.

- [ ] **Step 1: Add a mocked-provider smoke test**

Use existing mocked provider execution helpers to run a minimal call stack or the NeurIPS implementation phase with:

```yaml
implementation_execute_provider: claude_opus
implementation_review_provider: codex
implementation_fix_provider: codex
```

Assert that `ProviderExecutor.prepare_invocation` receives:

```python
["claude_opus", "codex", "codex"]
```

for execute/review/fix visits that occur in the test scenario.

- [ ] **Step 2: Add a default-preservation test**

Run the same harness without role inputs and assert the implementation provider aliases are all `codex`.

- [ ] **Step 3: Run the focused workflow tests**

Run the narrowest relevant selector, for example:

```bash
pytest tests/test_provider_role_routing.py tests/test_loader_validation.py::<relevant-loader-class-or-test> tests/test_neurips_<module>.py::<new-test-name> -q
```

Expected: PASS.

## Task 6: Documentation Updates

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/providers.md`
- Modify: `specs/variables.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `workflows/README.md`

- [ ] **Step 1: Update normative DSL docs**

In `specs/dsl.md`, change provider step schema from `provider: string` to explain that the string may include variable substitution and resolves at provider-step execution time.

- [ ] **Step 2: Update provider docs**

In `specs/providers.md`, add:

- provider name resolution happens before provider template lookup
- provider aliases are resolved in the active workflow provider namespace
- imported workflows do not inherit caller provider templates
- `provider_session` requires a static provider alias in this tranche

- [ ] **Step 3: Update variable docs**

In `specs/variables.md`, add `provider` to the list of fields where variables are substituted.

- [ ] **Step 4: Update workflow authoring guide**

Add a short role-routing pattern:

```yaml
inputs:
  implementation_execute_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude_opus"]
    default: "codex"
steps:
  - name: ExecuteImplementation
    provider: "${inputs.implementation_execute_provider}"
```

State that reusable workflows should define supported aliases locally.

- [ ] **Step 5: Update workflow index if needed**

If the NeurIPS drain entry mentions all-Codex behavior, update `workflows/README.md` to mention role-provider inputs.

- [ ] **Step 6: Run docs diff check**

Run:

```bash
git diff --check -- specs/dsl.md specs/providers.md specs/variables.md docs/workflow_drafting_guide.md workflows/README.md
```

Expected: no output.

## Task 7: Final Verification

**Files:**
- No new files beyond previous tasks.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/test_provider_role_routing.py tests/test_loader_validation.py -q
```

Expected: PASS.

- [ ] **Step 2: Run targeted workflow validation**

Run the NeurIPS dry-run command from Task 4 with default provider inputs and with `implementation_execute_provider=claude_opus`.

Expected: both dry-runs succeed.

- [ ] **Step 3: Run broader relevant tests**

Run:

```bash
pytest tests/test_provider_execution.py tests/test_workflow_output_contract_integration.py -q
```

Expected: PASS.

- [ ] **Step 4: Apply the one-workflow PtychoPINN ExecuteImplementation override**

After the canonical orchestrator workflow/tests are verified, propagate only the import-closure support files required by `/home/ollie/Documents/PtychoPINN/workflows/examples/neurips_steered_backlog_drain.yaml`:

- `/home/ollie/Documents/PtychoPINN/workflows/examples/neurips_steered_backlog_drain.yaml`
- `/home/ollie/Documents/PtychoPINN/workflows/library/neurips_selected_backlog_item.yaml`
- `/home/ollie/Documents/PtychoPINN/workflows/library/neurips_backlog_implementation_phase.yaml`

In the PtychoPINN example workflow only, set `inputs.implementation_execute_provider.default` to `claude_opus`. Keep `implementation_review_provider.default` and `implementation_fix_provider.default` as `codex`; keep canonical orchestrator defaults and copied library defaults as Codex/GPT-5.4 high.

Then validate that one PtychoPINN NeurIPS workflow:

```bash
cd /home/ollie/Documents/PtychoPINN
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml --dry-run \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-design.md \
  --input roadmap_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-roadmap.md \
  --input roadmap_gate_path=docs/backlog/roadmap_gate.json \
  --input progress_ledger_path=state/NEURIPS-HYBRID-RESNET-2026/progress_ledger.json \
  --input implementation_review_provider=codex \
  --input implementation_fix_provider=codex
```

Expected: dry-run validation succeeds, library defaults remain Codex/GPT-5.4 high, and the PtychoPINN example workflow default assigns `ExecuteImplementation` to `claude_opus`.

Do not change PtychoPINN global provider defaults, shell aliases, environment defaults, or unrelated workflow files to route implementation through Claude.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git diff -- orchestrator/loader.py orchestrator/workflow/executor.py specs/dsl.md specs/providers.md specs/variables.md docs/workflow_drafting_guide.md workflows/README.md workflows/library/neurips_backlog_implementation_phase.yaml workflows/library/neurips_selected_backlog_item.yaml workflows/examples/neurips_steered_backlog_drain.yaml tests/test_provider_role_routing.py tests/test_loader_validation.py
```

Expected: diff is limited to provider role routing, docs, tests, and the explicit one-workflow PtychoPINN NeurIPS override/support files if those copied files are present.

- [ ] **Step 6: Commit**

Stage only files changed for this item:

```bash
git add docs/backlog/active/2026-04-20-phase-specific-provider-routing.md docs/plans/2026-05-01-kiss-provider-role-routing-implementation-plan.md orchestrator/loader.py orchestrator/workflow/executor.py specs/dsl.md specs/providers.md specs/variables.md docs/workflow_drafting_guide.md workflows/README.md workflows/library/neurips_backlog_implementation_phase.yaml workflows/library/neurips_selected_backlog_item.yaml workflows/examples/neurips_steered_backlog_drain.yaml tests/test_provider_role_routing.py tests/test_loader_validation.py
git commit -m "Add provider role routing for reusable workflows"
```

Expected: commit succeeds.
