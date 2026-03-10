# v0 Artifact-Contract Prototype Runbook

This runbook documents the prototype workflows that use deterministic file-based output contracts.

## Workflows

- `workflows/examples/backlog_plan_execute_v0.yaml`
  - Pattern: backlog item selection -> plan draft -> plan execution -> optional review loop.
- `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml`
  - Pattern: execute -> review -> fix loop with explicit v1.2 artifact publish/consume guarantees.
- `workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml`
  - Pattern: flexible execution/fix steps + strict JSON assessment/review gates using `output_bundle`/`consume_bundle`.
- `workflows/examples/test_fix_loop_v0.yaml`
  - Pattern: run tests -> gate on failure count -> fix -> retry until pass/max cycles.
- `workflows/examples/unit_of_work_plus_test_fix_v0.yaml`
  - Pattern: perform unit-of-work -> run tests -> fix loop.
- `workflows/examples/dsl_review_first_fix_loop_provider_session.yaml`
  - Pattern: fresh provider-session review -> publish runtime-owned string handle -> gate on review output -> resume the same provider session for fixes.

## Deterministic Handoff Contract

- Each phase writes required artifacts to files under `state/` or `artifacts/`.
- Each producing step declares `expected_outputs` with explicit `name`.
- Downstream logic consumes values from `steps.<Step>.artifacts.<name>`.
- In `version: "1.2"` workflows, provider steps with `consumes` automatically inject a deterministic `Consumed Artifacts` prompt block (unless `inject_consumes: false`).
- In `version: "1.3"` workflows, deterministic values can be bundled:
  - `output_bundle` extracts typed artifacts from one JSON output file.
  - `consume_bundle` materializes resolved consumes into one JSON file for downstream command/provider use.
- In `version: "2.10"` provider-session workflows:
  - fresh session handles are typed scalar `string` artifacts published by the runtime, not by prompt-authored files
  - the reserved resume handle participates in lineage but is excluded from prompt injection and `consume_bundle`
- Recommended control policy:
  - Keep heavy execution/fix steps flexible (`output_capture: text`).
  - Keep assessment/review/gate steps strict (`output_capture: json`, `allow_parse_error: false`).
  - Drive `goto` decisions from strict published artifacts, not raw prose logs.

## Verification Commands

```bash
cd ~/Documents/agent-orchestration
pytest tests/test_loader_validation.py -k "expected_outputs or inject_output_contract" -v
pytest tests/test_output_contract.py -v
pytest tests/test_workflow_output_contract_integration.py -v
pytest tests/test_prompt_contract_injection.py -v
pytest tests/test_workflow_examples_v0.py -v
```

Runtime smoke proof:

```bash
cd ~/Documents/agent-orchestration
pytest tests/test_workflow_examples_v0.py -k runtime -v
```

Optional dry-run check:

```bash
cd ~/Documents/agent-orchestration
python -m orchestrator run workflows/examples/backlog_plan_execute_v0.yaml --dry-run
python -m orchestrator run workflows/examples/dsl_review_first_fix_loop_provider_session.yaml --dry-run
```

Runtime example with summaries enabled:

```bash
cd ~/Documents/agent-orchestration
python -m orchestrator run workflows/examples/backlog_plan_execute_v0.yaml --debug --step-summaries --summary-mode async --summary-provider claude_sonnet_summary
```

## Known Limitations (v0)

- Loop control uses existing `on.*.goto` and shell gates (no new control-flow DSL primitives yet).
- Exit-code taxonomy for contract failures is currently implementation-defined; consumers should gate on non-zero plus `error.type == "contract_violation"`.
