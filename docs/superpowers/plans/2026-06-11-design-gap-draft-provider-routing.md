# Design Gap Draft Provider Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Lisp frontend design-delta drain route design-gap architecture drafting to either Codex or Claude Code, with the Claude model and effort configurable at launch time.

**Architecture:** Keep provider templates local to the callee workflow, because reusable-call provider namespaces are private to the imported workflow. Add a Claude Code provider equivalent to the existing Codex provider in the design-gap architect callee, expose provider/model/effort inputs there, and pass those inputs through from the parent drain. Preserve current Codex defaults so existing runs and scripts are unchanged unless callers opt in.

**Tech Stack:** Orchestrator DSL v2.14 YAML workflows, provider template substitution, reusable `call` input passing, `python -m orchestrator run --dry-run`, focused pytest validation where available.

---

## Context

The gap drafting provider is currently hardcoded in:

- `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`

Current shape:

```yaml
providers:
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--model", "${model}", "--config", "reasoning_effort=${effort}"]
    input_mode: "stdin"
    defaults:
      model: "${context.workflow_model}"
      effort: "${context.workflow_effort}"

steps:
  - name: DraftDesignGapArchitecture
    id: draft_design_gap_architecture
    provider: codex
```

The parent drain already exposes implementation provider routing, but not design-gap draft routing:

- `workflows/examples/lisp_frontend_design_delta_drain.yaml`

Changing `implementation_execute_provider` or `implementation_review_provider` does not affect `DraftDesignGapArchitecture`.

The repo already uses the Claude Code agentic CLI provider shape in several workflows:

```yaml
claude_opus:
  command: ["claude", "-p", "${PROMPT}", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]
  input_mode: "argv"
  defaults:
    model: "opus"
    effort: "high"
```

This plan should introduce the same parameterized shape for design-gap drafting, with default model `claude-fable-5`.

## Current-Run Note

Provider selection is resolved when the provider step launches. If an existing run is already inside `DraftDesignGapArchitecture`, editing the workflow will not safely switch that already-started child process. To use Claude Fable for that draft, launch a new run or resume/recover from a state before `DraftDesignGapArchitecture` starts. If the current run has already produced and accepted a draft bundle, leave that evidence intact and apply this routing to the next design-gap drafting step.

## Files

- Modify: `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
  - Add design-gap draft provider/model/effort inputs.
  - Add a parameterized Claude Code provider alias.
  - Add a lightweight preflight guard for provider/model compatibility.
  - Change `DraftDesignGapArchitecture` to use the selected provider and step-level provider params.
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
  - Add parent inputs for design-gap draft provider/model/effort.
  - Pass those inputs through the `call: design_gap_architect` sites.
- Modify if present and stale: `workflows/README.md`
  - Only if workflow catalog text needs to mention design-gap draft provider routing.
- Test/verify: focused dry-runs and YAML validation through `python -m orchestrator run`.

## Task 1: Add Callee-Level Provider Inputs And Claude Provider

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`

- [ ] **Step 1: Add provider routing inputs**

Add inputs after `architecture_index_root`:

```yaml
  design_gap_draft_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude"]
    default: "codex"
  design_gap_draft_model:
    kind: scalar
    type: string
    default: "gpt-5.4"
  design_gap_draft_effort:
    kind: scalar
    type: string
    default: "high"
```

Rationale: provider alias and model are separate. The model value is passed via `provider_params`, so Codex and Claude can both be parameterized.

- [ ] **Step 2: Add a Claude Code provider alias**

Add under `providers:` alongside `codex`:

```yaml
  claude:
    command: ["claude", "-p", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]
    input_mode: "stdin"
    defaults:
      model: "claude-fable-5"
      effort: "high"
```

Rationale: this is the Claude Code equivalent of the Codex agentic CLI provider, not the plain API completion form. Use stdin mode because design-gap drafting prompts include large injected context and can exceed OS argv limits if `${PROMPT}` is passed as a command-line argument. It can edit/write the required output bundle when the prompt instructs it to write `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

- [ ] **Step 3: Add provider/model compatibility preflight**

Add a command step before `DraftDesignGapArchitecture`:

```yaml
  - name: ValidateDesignGapDraftProviderRouting
    id: validate_design_gap_draft_provider_routing
    command:
      - python
      - -c
      - |
        import json
        import pathlib
        import sys

        provider = sys.argv[1]
        model = sys.argv[2]
        effort = sys.argv[3]
        output_path = pathlib.Path(sys.argv[4])

        errors = []
        if provider == "claude" and not (
            model.startswith("claude-")
            or model in {"fable", "opus", "sonnet", "haiku"}
        ):
            errors.append(f"provider=claude requires a Claude model, got {model!r}")
        if provider == "codex" and not (
            model.startswith("gpt-")
            or "codex" in model
        ):
            errors.append(f"provider=codex requires a Codex/OpenAI model, got {model!r}")
        codex_efforts = {"low", "medium", "high", "xhigh"}
        claude_efforts = {"low", "medium", "high", "xhigh", "max"}
        allowed_efforts = claude_efforts if provider == "claude" else codex_efforts
        if effort not in allowed_efforts:
            errors.append(
                f"unsupported effort {effort!r} for provider={provider}; "
                f"allowed={sorted(allowed_efforts)}"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": provider,
            "model": model,
            "effort": effort,
            "routing_status": "INVALID" if errors else "VALID",
            "errors": errors,
        }
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if errors:
            raise SystemExit("; ".join(errors))
      - ${inputs.design_gap_draft_provider}
      - ${inputs.design_gap_draft_model}
      - ${inputs.design_gap_draft_effort}
      - ${inputs.state_root}/draft-provider-routing.json
    output_bundle:
      path: ${inputs.state_root}/draft-provider-routing.json
      fields:
        - name: routing_status
          json_pointer: /routing_status
          type: enum
          allowed: ["VALID", "INVALID"]
        - name: provider
          json_pointer: /provider
          type: string
        - name: model
          json_pointer: /model
          type: string
        - name: effort
          json_pointer: /effort
          type: string
```

Rationale: a single `design_gap_draft_model` input is flexible, but it can accidentally pair `provider=claude` with the default Codex model. The preflight guard fails before launching the expensive provider and gives a clear diagnostic.

- [ ] **Step 4: Route `DraftDesignGapArchitecture` through the selected provider**

Change:

```yaml
    provider: codex
```

to:

```yaml
    provider: ${inputs.design_gap_draft_provider}
    provider_params:
      model: ${inputs.design_gap_draft_model}
      effort: ${inputs.design_gap_draft_effort}
```

Rationale: this preserves runtime-selected provider routing and makes both Codex and Claude model/effort launch-configurable.

- [ ] **Step 5: Prepare temporary local validation fixtures**

Create temporary state fixtures outside tracked docs:

```bash
mkdir -p state/tmp-design-gap-architect-provider-routing
printf '%s\n' '{"ledger_version":1,"events":[]}' \
  > state/tmp-design-gap-architect-provider-routing/progress_ledger.json
printf '%s\n' '{"selection_status":"DRAFT_DESIGN_GAP","design_gap_id":"provider-routing-smoke"}' \
  > state/tmp-design-gap-architect-provider-routing/selection-bundle.json
```

Rationale: the callee requires real paths for `progress_ledger_path` and `selection_bundle_path`. Use temporary state files so dry-runs and the negative guard smoke are reproducible without depending on an active run's artifacts.

- [ ] **Step 6: Run a callee dry-run with the default Codex route**

Run:

```bash
python -m orchestrator run workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml \
  --dry-run \
  --input state_root=state/tmp-design-gap-architect-provider-routing \
  --input steering_path=docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/work_instructions.md \
  --input target_design_path=docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input command_adapter_contract_path=docs/design/workflow_command_adapter_contract.md \
  --input progress_ledger_path=state/tmp-design-gap-architect-provider-routing/progress_ledger.json \
  --input selection_bundle_path=state/tmp-design-gap-architect-provider-routing/selection-bundle.json
```

Expected: dry-run succeeds. Existing default behavior remains Codex.

- [ ] **Step 7: Run a callee dry-run with the Claude route**

Run the same command with:

```bash
  --input design_gap_draft_provider=claude \
  --input design_gap_draft_model=claude-fable-5 \
  --input design_gap_draft_effort=high
```

Expected: validation accepts the provider alias and substitutes `${model}` / `${effort}` without unresolved placeholders.

- [ ] **Step 8: Run a negative smoke for mismatched provider/model**

Run a real callee invocation with a mismatched model and a short timeout. This should fail in the preflight command before the provider step launches:

```bash
python -m orchestrator run workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml \
  --input state_root=state/tmp-design-gap-architect-provider-routing \
  --input steering_path=docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/work_instructions.md \
  --input target_design_path=docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input command_adapter_contract_path=docs/design/workflow_command_adapter_contract.md \
  --input progress_ledger_path=state/tmp-design-gap-architect-provider-routing/progress_ledger.json \
  --input selection_bundle_path=state/tmp-design-gap-architect-provider-routing/selection-bundle.json \
  --input design_gap_draft_provider=claude \
  --input design_gap_draft_model=gpt-5.4 \
  --input design_gap_draft_effort=high
```

Expected: the workflow fails at `ValidateDesignGapDraftProviderRouting` with a clear provider/model mismatch. It must not launch Claude. If it reaches `DraftDesignGapArchitecture`, stop and fix the preflight ordering.

- [ ] **Step 9: Remove temporary local fixtures if they are not useful**

```bash
rm -rf state/tmp-design-gap-architect-provider-routing
```

Do not remove active run state.

- [ ] **Step 10: Commit Task 1**

```bash
git add workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml
git commit -m "feat: add design gap draft provider routing"
```

## Task 2: Expose Routing From The Parent Drain

**Files:**
- Modify: `workflows/examples/lisp_frontend_design_delta_drain.yaml`

- [ ] **Step 1: Add parent inputs**

Add near the existing implementation provider inputs:

```yaml
  design_gap_draft_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude"]
    default: "codex"
  design_gap_draft_model:
    kind: scalar
    type: string
    default: "gpt-5.4"
  design_gap_draft_effort:
    kind: scalar
    type: string
    default: "high"
```

Rationale: defaults preserve current Codex behavior. A caller can switch to Claude Fable with three explicit inputs.

- [ ] **Step 2: Pass inputs into the normal design-gap architect call**

In the `DRAFT_DESIGN_GAP` branch, update `call: design_gap_architect` `with:`:

```yaml
                      design_gap_draft_provider:
                        ref: inputs.design_gap_draft_provider
                      design_gap_draft_model:
                        ref: inputs.design_gap_draft_model
                      design_gap_draft_effort:
                        ref: inputs.design_gap_draft_effort
```

- [ ] **Step 3: Pass inputs into any additional design-gap architect calls**

Search:

```bash
rg -n "call: design_gap_architect|design_gap_architect_state_root" workflows/examples/lisp_frontend_design_delta_drain.yaml
```

If a second call path exists for done-review or recovery-generated gap drafting, pass the same three inputs there too. Do not leave one design-gap drafting path hardcoded unless it is intentionally separate and documented.

- [ ] **Step 4: Run parent dry-run with current defaults**

Run the same drain dry-run command used for the active target, but with `--dry-run`. For the current local setup:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/work_instructions.md \
  --input target_design_path=docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input progress_ledger_path=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain \
  --input run_state_target_path=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN \
  --input architecture_index_root=docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps
```

Expected: same result as before the change. Existing default behavior remains Codex.

- [ ] **Step 5: Run parent dry-run with Claude Fable routing**

Add:

```bash
  --input design_gap_draft_provider=claude \
  --input design_gap_draft_model=claude-fable-5 \
  --input design_gap_draft_effort=high
```

Expected: dry-run succeeds and validates the new parent inputs and callee call bindings.

- [ ] **Step 6: Commit Task 2**

```bash
git add workflows/examples/lisp_frontend_design_delta_drain.yaml
git commit -m "feat: expose design gap draft provider routing"
```

## Task 3: Add Focused Regression Coverage If Existing Test Harness Supports It

**Files:**
- Inspect: `tests/test_loader_validation.py`
- Inspect: `tests/test_provider_execution.py`
- Create or modify only if there is an existing low-friction workflow loading test pattern.

- [ ] **Step 1: Check for existing workflow load/dry-run tests**

Run:

```bash
rg -n "lisp_frontend_design_delta_drain.yaml|run\\(.*--dry-run|provider_params|Load" tests/test_loader_validation.py tests/test_provider_execution.py tests
```

- [ ] **Step 2: Add a minimal regression if pattern is obvious**

Preferred assertion:

- loading `workflows/examples/lisp_frontend_design_delta_drain.yaml` succeeds;
- `design_gap_draft_provider=claude`, `design_gap_draft_model=claude-fable-5`, and `design_gap_draft_effort=high` pass validation;
- the child provider params preserve `${model}` and `${effort}` substitution through reusable call binding.

Do not add a brittle test that asserts prompt text.

- [ ] **Step 3: Run the focused test**

Run:

```bash
pytest <selected-test-module-or-test-name> -q
```

Expected: PASS.

- [ ] **Step 4: If no suitable harness exists, document why dry-run coverage is sufficient**

Record in the final response that workflow dry-runs validated the behavior and no new unit test was added because the existing regression harness does not expose a narrow reusable-call provider-binding assertion.

- [ ] **Step 5: Commit Task 3 if tests changed**

```bash
git add tests/<changed-test-file>
git commit -m "test: cover design gap draft provider routing"
```

## Task 4: Optional Docs/Catalog Update

**Files:**
- Modify if needed: `workflows/README.md`

- [ ] **Step 1: Check whether catalog text needs an update**

Run:

```bash
rg -n "lisp_frontend_design_delta_drain.yaml|lisp_frontend_design_delta_design_gap_architect" workflows/README.md
```

- [ ] **Step 2: Update only if useful**

If the catalog currently describes provider routing in this workflow family, add that design-gap drafting can be routed via `design_gap_draft_provider` with model/effort inputs. If it is only a short catalog row, leave it alone.

- [ ] **Step 3: Run markdown/diff checks**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 4: Commit docs if changed**

```bash
git add workflows/README.md
git commit -m "docs: note design gap draft provider routing"
```

## Task 5: Launch Or Resume With Claude Fable

**Files:**
- No code files.

- [ ] **Step 1: Decide whether to resume or launch**

If the active run has already launched `DraftDesignGapArchitecture`, do not expect workflow YAML edits to affect that in-flight child process. Prefer one of:

- launch a fresh drain when the goal is to test Claude Fable drafting from the beginning;
- resume/recover only if the run is before the drafting step;
- leave the current draft untouched and use Claude Fable for the next design-gap drafting step.

- [ ] **Step 2: Launch with Claude Fable inputs**

Use the current target setup plus:

```bash
  --input design_gap_draft_provider=claude \
  --input design_gap_draft_model=claude-fable-5 \
  --input design_gap_draft_effort=high
```

- [ ] **Step 3: Monitor provider behavior**

Use tmux and watchdog as usual. Confirm:

- the provider command is `claude -p ... --model claude-fable-5 --effort high --permission-mode bypassPermissions`;
- `DraftDesignGapArchitecture` writes the declared `draft-bundle.json`;
- `ValidateDesignGapArchitecture` consumes and validates the bundle;
- wrong or missing bundles fail closed rather than being inferred from stdout.

- [ ] **Step 4: Record verification**

In the final handoff, include:

- dry-run command and result;
- live run id if launched;
- whether the design-gap drafting step used `claude-fable-5`;
- whether validation accepted the resulting bundle.

## Final Verification

Run before claiming completion:

```bash
git diff --check
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run <current-inputs>
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run <current-inputs> \
  --input design_gap_draft_provider=claude \
  --input design_gap_draft_model=claude-fable-5 \
  --input design_gap_draft_effort=high
```

If tests were added:

```bash
pytest <selected-test-module-or-test-name> -q
```

## Rollback

If Claude routing breaks validation, revert only the routing additions:

- restore `DraftDesignGapArchitecture.provider: codex`;
- remove parent pass-through inputs;
- keep unrelated workflow/run-state files untouched.

Do not reset active run state unless explicitly requested.
