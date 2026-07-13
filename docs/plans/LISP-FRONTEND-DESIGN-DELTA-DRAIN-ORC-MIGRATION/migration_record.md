# Lisp Frontend Design Delta Drain .orc Migration Record

Workflow family: Lisp frontend design delta drain
Primary `.orc`: `workflows/library/lisp_frontend_design_delta/drain.orc`
Compatibility YAML twin: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
Status: `primary-flipped; promotion evidence recorded; Gate P3 satisfied; promoted parity target retired`
Created: 2026-06-09
Plan: `docs/plans/2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md`

## Authority

The `.orc` workflow is now the primary launch and routing surface for this
family. The route-readiness registry labels it `wcc_default` /
`promotion_eligible` with preferred-current-guidance copy safety, and the
retained historical promotion report records that the former migration target
was eligible for the primary surface. The YAML twin remains in place only as
compatibility/reference evidence until the Stage 6 archive gate.

The promotion handoff now has strict promotable parity plus fresh ordinary
compile, input-complete CLI dry-run, and parent-smoke evidence. This record did
not satisfy Gate P3 by itself; the later independent joint proof recorded in
the governing drain plan verified all four conditions and satisfied Gate P3.
Phase 3 Task 3.1 subsequently re-homed the focused parent-drain smoke with
reviewed parity evidence, and Task 3.2 retired the promoted parity target while
preserving its historical promotion report. The current selector is drain
Phase 3 Task 3.4: Phase-3 verification. Task 3.3 retired the ordered
certification bundle. Task 3.4 evidence is recorded and pending independent
review and closure; Phase 4, Stage 5 typed result guidance, and Stage 6 YAML
archive remain later work.

The remaining sections preserve the June migration inventory and baseline as
dated provenance. They do not override the current registry, retired
parity-target state, or catalog routing above.

## Historical YAML Baseline (2026-06-09)

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

## Historical Inventory Status (2026-06-09)

| Evidence area | Status | Evidence |
| --- | --- | --- |
| Workflow-family inventory | complete for first pass | `inventory.md` |
| Reproducible baseline characterization | complete for first pass | `baseline_evidence.md` |
| Runtime foundation readiness gate | complete for first pass | `foundation_readiness_gate.md` |
| Command adapter classification | complete for first pass | `inventory.md` |
| Domain type module | complete for first pass | `workflows/library/lisp_frontend_design_delta/types.orc`; `test_design_delta_domain_types_import_from_two_candidate_modules` |
| `.orc` import/layout feasibility | complete for first pass | `feasibility_probe.md`; `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` |
| Plan phase `.orc` candidate | compile candidate complete for first pass; runtime/parity paths open | `workflows/library/lisp_frontend_design_delta/plan_phase.orc`; `test_design_delta_plan_phase_candidate_compiles_with_stdlib_review_loop` |
| Implementation phase `.orc` candidate | leaf execute-attempt and completed-review candidate complete for first pass; full phase composition/output parity open | `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`; `test_design_delta_implementation_phase_candidate_compiles_with_variant_and_review_loop` |
| Selector `.orc` candidate | provider-decision candidate complete for first pass; bundle publication/output parity open | `workflows/library/lisp_frontend_design_delta/selector.orc`; `test_design_delta_selector_candidate_compiles_as_provider_decision` |
| Design-gap architect `.orc` candidate | behavior-preserving draft/validate leaves complete for first pass; review/revise and path parity open | `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc`; `test_design_delta_architect_candidate_compiles_draft_and_validation_leaves` |
| Work-item `.orc` candidate | terminal/recovery classifier leaves complete for first pass; full orchestration and run-state recording open | `workflows/library/lisp_frontend_design_delta/work_item.orc`; `test_design_delta_work_item_candidate_compiles_terminal_and_recovery_leaves` |
| Parent drain `.orc` candidate | blocked before implementation; readiness blockers recorded | `parent_drain_readiness_blockers.md` |
| Resume/recovery parity | not started | none |
| Migration parity target manifest | not started | none |
| `--require-non-regressive` | not started | none |
| `--require-promotable` | not started | none |

## Historical Promotion Checklist

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

## Historical Accepted Differences (2026-06-09)

None yet.

## Historical Open Migration Risks (2026-06-09)

- Parent drain recovery is not equivalent to the simple design-doc review/revise
  `.orc` workflow; it needs typed recovery routing and resource-state mutation.
- The first plan-phase `.orc` candidate avoids raw public `state/` path inputs
  by modeling work-item context and ledger context as artifact inputs. The
  parent/private context layer must bridge the YAML `state/` compatibility
  inputs before parity evidence can claim public-boundary equivalence.
- The first implementation-phase `.orc` candidate is intentionally split into
  leaf workflows. The current frontend/shared-validation path cannot place the
  stdlib review/revise loop inside the `COMPLETED` arm of an implementation
  attempt `match`; nested structured `repeat_until` and `match` steps fail
  shared validation when generated below that branch. Full phase composition
  and exact YAML output parity remain open until that composition gap is fixed
  or a certified adapter boundary is accepted.
- The first selector `.orc` candidate models the provider selection decision
  with typed artifact inputs. It does not yet expose the YAML selector's raw
  `state/` manifest, ledger, run-state, or `selection_bundle_path` public
  boundary. Selection-bundle publication still needs a typed projection,
  certified adapter, or private context bridge before parity can claim
  equivalence.
- The first design-gap architect `.orc` candidate is behavior-preserving for
  the current YAML draft/validate shape. It does not incorporate the accepted
  architecture review/revise loop from `docs/design/lisp_frontend_review_fix_loops.md`.
  Target derivation, architecture-index construction, and work-item bundle
  publication still need StateLayout/private context or certified-adapter
  bridges before public-boundary parity can be claimed.
- The first work-item `.orc` candidate migrates only terminal classification
  and blocked-recovery classification leaves. Full work-item orchestration
  remains open because `ResolveWorkItemInputs`, implementation-phase
  composition, recovery-route selection, terminal recording, and run-state
  mutation still require typed projections, resource-transition ownership, or
  certified adapters.
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

## Historical Next Checkpoint (2026-06-09)

Proceed to the plan phase `.orc` candidate. Do not translate the parent drain
until selector, gap architect, work item, plan phase, implementation phase,
and recovery routing candidates have focused evidence.
