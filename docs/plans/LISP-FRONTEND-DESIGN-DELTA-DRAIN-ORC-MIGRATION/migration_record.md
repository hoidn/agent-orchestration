# Lisp Frontend Design Delta Drain .orc Migration Record

Workflow family: Lisp frontend design delta drain
YAML source of truth: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
Candidate `.orc`: not created yet
Status: `inventory`
Created: 2026-06-09
Plan: `docs/plans/2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md`

## Authority

YAML remains authoritative for this workflow family. The `.orc` candidate may
become primary only after migration parity tooling computes that it is
non-regressive and `--require-promotable` succeeds.

Compile, shared validation, and dry-run are required evidence, but they are not
sufficient promotion evidence by themselves.

## Current Baseline

Representative completed YAML run:

- Run: `20260609T003338Z-iroxpc`
- Workflow: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Status: `completed`
- Drain status: `DONE`
- Completed repeat iterations: `0` through `9`
- Run state: `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json`
- Drain summary: `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json`
- Target design: `docs/design/workflow_lisp_runtime_migration_foundation.md`
- Baseline design: `docs/design/workflow_lisp_frontend_specification.md`
- Implementation execute provider: `codex`
- Implementation review provider: `codex`

Baseline evidence checked during inventory:

- `python -m json.tool state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json`
- `python -m json.tool artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json`
- `python -m orchestrator report --run-id 20260609T003338Z-iroxpc`
- `baseline_evidence.md`

## Migration Status

| Evidence area | Status | Evidence |
| --- | --- | --- |
| Workflow-family inventory | complete for first pass | `inventory.md` |
| Reproducible baseline characterization | complete for first pass | `baseline_evidence.md` |
| Runtime foundation readiness gate | complete for first pass | `foundation_readiness_gate.md` |
| Command adapter classification | complete for first pass | `inventory.md` |
| Domain type module | complete for first pass | `workflows/library/lisp_frontend_design_delta/types.orc`; `test_design_delta_domain_types_import_from_two_candidate_modules` |
| `.orc` import/layout feasibility | complete for first pass | `feasibility_probe.md`; `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` |
| Plan phase `.orc` candidate | compile candidate complete for first pass; runtime/parity paths open | `workflows/library/lisp_frontend_design_delta/plan_phase.orc`; `test_design_delta_plan_phase_candidate_compiles_with_stdlib_review_loop` |
| Implementation phase `.orc` candidate | not started | none |
| Selector `.orc` candidate | not started | none |
| Design-gap architect `.orc` candidate | not started | none |
| Work-item `.orc` candidate | not started | none |
| Parent drain `.orc` candidate | not started | none |
| Resume/recovery parity | not started | none |
| Migration parity target manifest | not started | none |
| `--require-non-regressive` | not started | none |
| `--require-promotable` | not started | none |

## Required Evidence Before Promotion

- `.orc` family parses, typechecks, lowers, and passes shared validation.
- Fake-provider tests cover normal completion, done, blocked, plan revise,
  implementation revise, implementation blocked, prerequisite recovery,
  recovered-gap retry, and exhaustion.
- Command helpers that remain are certified adapters or tracked migration debt.
- Reports, pointer files, prompt prose, stdout, and debug YAML are not routing
  authority.
- Source maps and Semantic IR explain generated paths and hidden runtime
  bindings.
- Resume/reuse tests cover the parent drain, nested review loops, implementation
  review/fix loop, blocked recovery, and recovered-gap retry.
- `migration-parity` computes `non_regressive=true`.
- `migration-parity --require-promotable` succeeds.
- The user explicitly accepts promotion from YAML primary to `.orc` primary.

## Accepted Differences

None yet.

## Open Migration Risks

- Parent drain recovery is not equivalent to the simple design-doc review/revise
  `.orc` workflow; it needs typed recovery routing and resource-state mutation.
- The first plan-phase `.orc` candidate avoids raw public `state/` path inputs
  by modeling work-item context and ledger context as artifact inputs. The
  parent/private context layer must bridge the YAML `state/` compatibility
  inputs before parity evidence can claim public-boundary equivalence.
- Provider `variant_output.path` target binding must be reliable before
  provider-heavy implementation attempts are promotion evidence.
- Several scripts mutate run state and cannot be converted to pure helpers
  without a resource-transition design.
- The YAML family uses many pointer files as compatibility representations; the
  `.orc` candidate must not preserve them as semantic authority.
- `PublishUpdatedExecutionReport` includes copy-recovery behavior that may be
  incompatible with the authority model unless certified as compatibility-only.
- Stage 3 currently rejects nested union payloads at workflow boundaries, so
  exported recovery and drain results must stay first-order until that frontend
  limitation is closed or intentionally accepted.
- Required lints currently reject low-level state paths on high-level workflow
  boundaries, so full recovery-state payloads must remain internal/private or
  certified-adapter surfaces until the StateLayout/private contract gate passes.
- Exported workflows must return records or unions, so bare enum decisions need
  record wrappers with decision and evidence fields.
- Resume parity must exercise stale prerequisite/recovery edges, not just
  ordinary happy-path resume.

## Next Checkpoint

Proceed to the plan phase `.orc` candidate. Do not translate the parent drain
until selector, gap architect, work item, plan phase, implementation phase,
and recovery routing candidates have focused evidence.
