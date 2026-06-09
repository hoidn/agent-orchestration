# Design Delta Drain YAML Baseline Evidence

Status: characterization evidence
Created: 2026-06-09
Migration record: `migration_record.md`

## Baseline Run

- Repo commit used for this characterization pass: `6be15841aa04a85ac2973be14c9d2b323626c4ea`
- Run id: `20260609T003338Z-iroxpc`
- Workflow: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Final persisted state: `completed`
- Drain status: `DONE`
- Completed repeat iterations: `0` through `9`
- Run state output: `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json`
- Drain summary output: `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json`
- Target design: `docs/design/workflow_lisp_runtime_migration_foundation.md`
- Baseline design: `docs/design/workflow_lisp_frontend_specification.md`
- Evidence mode: real-provider run
- Provider aliases: `implementation_execute_provider=codex`, `implementation_review_provider=codex`

The exact original shell command used to launch this historical run is not
stored in the run state. The stable evidence commands for this baseline are:

```bash
python -m orchestrator report --run-id 20260609T003338Z-iroxpc
python -m json.tool state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json
python -m json.tool artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json
sha256sum state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json
```

To reproduce the baseline shape, launch the YAML primary with the same target
and baseline design paths, the same `LISP-FRONTEND-AUTONOMOUS-DRAIN` state and
artifact roots, and the same `codex` provider aliases. Promotion evidence must
use freshly generated run ids and a parity target manifest rather than relying
on this historical run alone.

## Primary Output Checksums

```text
6bcc6ded05aad360034f80e5c290a4821507882ce53217ad01ae301c2a505c82  state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json
3be576e27ca97867b1b0592e8b54f50324daec746d1bc233f4eb3bfbf4df692d  artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json
```

## Representative Artifact Checksums

These checksums are representative characterization evidence, not a complete
promotion manifest. Promotion must compute full evidence from a parity target.

```text
fb34ff2deaac80107c79a5e954a084e14c58cb33b54e1eb01c652bf87a24bf5c  artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gap-work-item/implementation-phase/execution_report.md
60a75baba8f4d3ac55692ec6fe01f876ce40de6b64e8d19478b6d55acad6adbd  artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract-summary.json
4bcb8b601ba25c7f2c93d2c10964c731ffa555a71f01eb82ff5d9e7fb26dd8e5  artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/execution_report.md
d9594bf6d5d58db36344527dd6212ac7a8682282bce16cdac026a9e1b6204c73  artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan-summary.json
306f62142c0e82982320368fa64a904a260e19c792b350ba3b918502ad56da7c  artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/execution_report.md
7690f75d3bf8c9927897999277a3e3354ad32320ec5c918a86977c4313bcb10d  artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/generic-collection-types-summary.json
f9c9346bbd9ff5a59d180cc548f3413a2bc37ad220710175a144a0e01e260f06  artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/generic-collection-types/execution_report.md
```

## Full Evidence Command Template

For a promotion-grade baseline, generate a checksum manifest from the selected
run root and public output/artifact families:

```bash
find state/LISP-FRONTEND-AUTONOMOUS-DRAIN artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN \
  -type f -print0 | sort -z | xargs -0 sha256sum
```

## Accepted Differences

None recorded. Any future `.orc` candidate differences must be explicit in the
parity target manifest and accepted by the gate; compile or dry-run success is
not enough.
