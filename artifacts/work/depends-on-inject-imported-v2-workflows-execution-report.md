## Completed In This Pass

- Restored loader validation so `depends_on.inject` is accepted for workflows at `version: "1.1.1"` and all later supported versions, including imported `2.7` callees.
- Reordered provider prompt composition so `asset_depends_on` expands the base prompt before workspace `depends_on.inject` runs.
- Added regression coverage for loader validation, mixed prompt composition, imported-call runtime behavior, and the new runnable example.
- Added a dedicated imported-call example plus library workflow assets, and aligned the workflow catalog/docs with the restored contract.
- Adjusted the example's local provider wiring so the real CLI smoke can emit the decision artifact without relying on unresolved output-contract placeholders in the prompt.

## Completed Plan Tasks

- Tranche 1: added imported-workflow loader coverage and replaced the exact `1.1.1` equality gate with the standard version-order check while preserving the `1.1` rejection.
- Tranche 2: added a mixed `asset_depends_on` + `depends_on.inject` prompt-order regression and fixed executor stage ordering.
- Tranche 3: added imported-call runtime coverage, created `workflows/examples/depends_on_inject_imported_v2_call.yaml`, created `workflows/library/depends_on_inject_imported_review.yaml` plus prompt/rubric assets, updated workflow example coverage, and updated the workflow catalog.
- Tranche 4: updated `docs/workflow_drafting_guide.md` and `specs/versioning.md` to match the implemented contract and captured final verification evidence.

## Remaining Required Plan Tasks

- None.

## Verification

- `pytest tests/test_loader_validation.py -k "inject_requires_1_1_1" -v` -> `1 passed, 96 deselected`
- `pytest tests/test_subworkflow_calls.py -k "depends_on_inject" -v` -> `1 passed, 22 deselected`
- `pytest tests/test_prompt_contract_injection.py -k "asset_depends_on and depends_on_inject" -v` -> `2 passed, 17 deselected`
- `pytest tests/test_subworkflow_calls.py -k "depends_on_inject and asset_depends_on" -v` -> `1 passed, 23 deselected`
- `pytest tests/test_workflow_examples_v0.py -k "depends_on_inject_imported_v2_call" -v` -> `1 passed, 25 deselected`
- `pytest tests/test_loader_validation.py tests/test_prompt_contract_injection.py tests/test_subworkflow_calls.py tests/test_workflow_examples_v0.py -k "depends_on_inject or asset_depends_on" -v` -> `5 passed, 161 deselected`
- Real CLI smoke in an isolated temp workspace copy of the new example/library files:
  `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/depends_on_inject_imported_v2_call.yaml --state-dir /tmp/depends-on-inject-imported-v2-call-final --debug`
  Result: run `20260311T015759Z-906jtm` completed successfully.
- Prompt-audit evidence:
  `/tmp/depends-on-inject-imported-v2-call-final/20260311T015759Z-906jtm/call_frames/root.run_imported_review__visit__1/logs/ReviewImportedInjection.prompt.txt`
  Verified order: workspace dependency block, then workflow-source rubric block, then base prompt, then output contract.

## Residual Risks

- The output-contract prompt block still renders authored `expected_outputs.path` text without resolving `${inputs.*}` placeholders. This change does not alter that broader prompt-contract behavior; the smoke example works by passing the resolved output path through `provider_params` instead.
- The smoke was isolated in `/tmp` because the CLI uses the current working directory as the workflow workspace. Running the example directly from the repo root would create temporary `state/` artifacts in the checkout.
