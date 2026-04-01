# `depends_on.inject` In Imported `2.x` Workflows Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the authored contract so imported `2.x` workflows used through `call` may declare `depends_on.inject`, and make mixed `asset_depends_on` plus workspace dependency injection compose provider prompts in the spec-defined order.

**Architecture:** Keep the change narrow and sequence it in contract order. First, add imported-workflow validation coverage and replace the loader's exact-version gate with the normal `>= 1.1.1` check. Next, fix provider prompt composition so source-relative asset blocks are added before workspace dependency injection runs. Then prove the full imported-call path with runtime coverage and one dedicated runnable example that exercises the mixed prompt surfaces without relying on external providers.

**Tech Stack:** Python loader/runtime code, YAML reusable workflows, prompt-composition helpers, pytest integration coverage, orchestrator CLI smoke checks with `--debug`.

---

## Global Guardrails

- Land tranches in order; later tranches assume earlier validation and runtime behavior already exist.
- Write the failing regression first in each tranche before changing implementation code.
- Keep the slice narrow: no prompt-subsystem rewrite, no `call` runtime redesign, and no state-schema churn.
- Prefer extending existing test modules: `tests/test_loader_validation.py`, `tests/test_prompt_contract_injection.py`, `tests/test_subworkflow_calls.py`, and `tests/test_workflow_examples_v0.py`.
- If implementation adds or renames a test module instead of extending an existing one, run `pytest --collect-only` on that module before claiming coverage.
- Use `inject: true` or explicit `position: prepend` in mixed prompt-order tests and smokes; append-only cases do not distinguish the broken and fixed stage order.

## Compatibility And Migration Boundary

- No `state.json` migration is expected. The state schema stays unchanged.
- This is a contract-restoration change, not a new authored surface: workflows at `version: "1.1.1"` and above remain the only valid `depends_on.inject` users, but imported `2.x` callees stop being rejected incorrectly.
- The reusable-call same-version rule stays unchanged. Caller and callee must still declare the same DSL version in the first `call` tranche.
- `depends_on` remains WORKSPACE-relative everywhere, including inside imported workflows.
- `asset_depends_on` remains workflow-source-relative and provider-only.
- Injection still affects only the composed provider prompt. No new caller-visible artifact, state field, or exported call output is introduced.
- Migration is manual only where authors were carrying workarounds. Existing pointer-file or prompt-glue workarounds may be removed later, but this slice should not require any automatic migration code.

## Explicit Non-Goals

- Import-local semantics for plain `depends_on`.
- A broader prompt-source naming cleanup (`input_file` vs `asset_file`) or prompt-composer refactor.
- Any widening of the `call` boundary so injected dependency lists or prompt text become exported artifacts.
- A new merged formatting scheme for mixed `asset_depends_on` plus `depends_on.inject`; existing asset-block and dependency-injection renderers stay in place.
- Temporary authoring restrictions that forbid `asset_depends_on` plus `depends_on.inject` on the same provider step.
- Reworking unrelated workflow examples or prompt families outside the targeted imported-injection coverage.

### Tranche 1: Loader Regression And Gate Fix

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_subworkflow_calls.py`

**Work:**
- Extend the existing negative loader coverage in `tests/test_loader_validation.py` so it continues to prove `version: "1.1"` rejects `depends_on.inject`.
- Add a new imported-workflow regression in `tests/test_subworkflow_calls.py` that loads a `2.7` caller plus `2.7` callee where the callee provider step uses plain `depends_on.inject: true`.
- Make the new imported-workflow test fail for the current reason: `Import '<alias>': Step '<name>': depends_on.inject requires version '1.1.1'`.
- Replace the exact string equality check in `orchestrator/loader.py` with the standard `self._version_at_least(version, "1.1.1")` gate.
- Keep the fix scoped to validation. Do not touch dependency resolution semantics, prompt composition, or `call` exports in this tranche.

**Verification:**
```bash
pytest tests/test_loader_validation.py -k "inject_requires_1_1_1" -v
pytest tests/test_subworkflow_calls.py -k "depends_on_inject" -v
```

**Checkpoint:** Do not start prompt-composition work until the imported `2.7` callee validates and the `1.1` negative gate still fails.

### Tranche 2: Prompt-Composition Order Regression And Runtime Fix

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Reference: `orchestrator/workflow/prompting.py`
- Modify: `tests/test_prompt_contract_injection.py`

**Work:**
- Add a focused mixed-surface regression in `tests/test_prompt_contract_injection.py` for a `2.5+` provider step that combines:
  - a base prompt source,
  - `asset_depends_on`,
  - workspace `depends_on.inject: true` or explicit `position: prepend`.
- Make that test assert the final observable prompt order that only the fixed stage order can produce:
  - workspace dependency block first,
  - source-asset blocks second,
  - base prompt after the asset blocks,
  - output contract suffix still last.
- Reorder provider prompt composition in `orchestrator/workflow/executor.py` so `apply_asset_depends_on_prompt_injection(...)` runs on the base prompt before dependency injection mutates that prompt.
- Preserve current behavior for dependency resolution, missing-required validation, injection modes, instructions, truncation bookkeeping, prompt-audit emission, consumes injection, and output-contract suffixing.
- Keep `orchestrator/workflow/prompting.py` changes minimal; only touch it if a small helper/interface adjustment is needed to support the executor reorder cleanly.

**Verification:**
```bash
pytest tests/test_prompt_contract_injection.py -k "asset_depends_on and depends_on_inject" -v
```

**Checkpoint:** The generic mixed prompt-order regression must pass before adding imported-call runtime proof or smoke artifacts.

### Tranche 3: Imported-Call Runtime Coverage And Dedicated Smoke Example

**Files:**
- Modify: `tests/test_subworkflow_calls.py`
- Create: `workflows/examples/depends_on_inject_imported_v2_call.yaml`
- Create: `workflows/library/depends_on_inject_imported_review.yaml`
- Create: `workflows/library/prompts/depends_on_inject_imported_review.md`
- Create: `workflows/library/rubrics/depends_on_inject_imported_review.md`
- Modify: `tests/test_workflow_examples_v0.py`
- Modify: `workflows/README.md`

**Work:**
- Add an imported-call runtime regression in `tests/test_subworkflow_calls.py` that executes a callee provider step with both `asset_depends_on` and workspace `depends_on.inject: true`, captures the composed prompt, and proves the fixed order survives the `call` boundary.
- Keep that runtime assertion distinct from the loader regression:
  - the callee must actually execute,
  - the assertion must distinguish fixed vs broken order,
  - the test should not depend on append-only positioning.
- Add a dedicated runnable example pair:
  - caller workflow under `workflows/examples/` that writes a workspace runtime manifest, then `call`s the library workflow,
  - callee workflow under `workflows/library/` that uses workflow-source prompt assets plus `depends_on.inject`.
- Make the example self-contained and local-provider-safe:
  - use a provider command that can run without network/secrets,
  - emit the required decision artifact locally,
  - rely on `--debug` prompt audit (or a deterministic captured prompt file if simpler) as the smoke evidence surface.
- Extend `tests/test_workflow_examples_v0.py` so the new example validates and runs under mocked provider execution, and assert the imported callee prompt order there as well if that keeps the example coverage readable.
- Update `workflows/README.md` so the new example and library workflow are discoverable from the workflow catalog.

**Verification:**
```bash
pytest tests/test_subworkflow_calls.py -k "depends_on_inject and asset_depends_on" -v
pytest tests/test_workflow_examples_v0.py -k "depends_on_inject_imported_v2_call" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/depends_on_inject_imported_v2_call.yaml \
  --state-dir /tmp/depends-on-inject-imported-v2-call-smoke \
  --debug
sed -n '1,160p' /tmp/depends-on-inject-imported-v2-call-smoke/logs/ReviewImportedInjection.prompt.txt
```

**Checkpoint:** Do not close the implementation until the non-dry-run smoke produces observable prompt evidence showing the dependency block reached the imported callee before the asset block, and the asset block still precedes the base prompt.

### Tranche 4: Doc Alignment And Final Narrow Integration Gate

**Files:**
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `specs/versioning.md`
- Reference: `specs/providers.md`
- Reference: `specs/dsl.md`

**Work:**
- Correct the informative provider prompt-composition order in `docs/workflow_drafting_guide.md` so it matches the actual contract:
  - base prompt source,
  - `asset_depends_on`,
  - workspace `depends_on.inject`,
  - consumed artifacts,
  - output contract.
- Clarify the `specs/versioning.md` wording for `depends_on.inject` so it reads as `1.1.1 or higher`, not an exact-version special case.
- Leave `specs/providers.md` and `specs/dsl.md` unchanged unless implementation reveals a real ambiguity that the current wording does not already cover.
- Record the example smoke command and the prompt-audit evidence path in the final implementation report so the verification is reproducible.

**Verification:**
```bash
pytest tests/test_loader_validation.py tests/test_prompt_contract_injection.py tests/test_subworkflow_calls.py tests/test_workflow_examples_v0.py -k "depends_on_inject or asset_depends_on" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/depends_on_inject_imported_v2_call.yaml \
  --state-dir /tmp/depends-on-inject-imported-v2-call-final \
  --debug
```

**Checkpoint:** The slice is complete only when validation, generic prompt composition, imported-call runtime coverage, example coverage, and the non-dry-run smoke all pass together.

## Final Integration Gate

Run this from the repo root after all tranches pass independently:

```bash
pytest tests/test_loader_validation.py tests/test_prompt_contract_injection.py tests/test_subworkflow_calls.py tests/test_workflow_examples_v0.py -k "depends_on_inject or asset_depends_on" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/depends_on_inject_imported_v2_call.yaml \
  --state-dir /tmp/depends-on-inject-imported-v2-call-final \
  --debug
sed -n '1,160p' /tmp/depends-on-inject-imported-v2-call-final/logs/ReviewImportedInjection.prompt.txt
```

Completion criteria:

- imported `2.x` callees with `depends_on.inject` load successfully
- the `1.1` negative gate still fails
- mixed `asset_depends_on` plus `depends_on.inject` provider prompts compose in spec order
- the imported-call runtime regression proves the fixed behavior through `call`
- the runnable example and prompt-audit evidence show the same order without `--dry-run`
- docs no longer imply the old stage order or exact-version loader gate
