# T26 HEAD vs HEAD^ Workflow Behavior Simulation

## Inputs And Exclusions

Simulation target: EasySpin `T26-full-chili-slow-motion-solver-expansion`, starting before T26 design and ending when original T26 completes, fails, blocks, or is superseded.

Compared revisions:

- Old behavior: `HEAD^` = `3358b47cba21087f59752d7ca6be988b08b5728b`
- New behavior: `HEAD` = `14fa0b68b89c4cc045d8d1eb060e522049d40967`

Included evidence:

- Agent-orchestration workflow and prompt files at `HEAD^` and `HEAD`.
- EasySpin T26 manifest entry and tranche brief.
- EasySpin actual T26 terminal implementation review and execution report.
- EasySpin failed run state for `20260422T224455Z-avq8uu`.

Excluded evidence:

- The deleted old simulation report.
- T26-generated design, plan, docs, implementation files, tests, catalogs, and reports as starting-state inputs. They are used only as historical evidence for likely difficulty and terminal failure mode.

## Compared Versions

`HEAD^` major-project tranche stack:

- imports `tracked_big_design_phase.yaml`
- imports `tracked_plan_phase.yaml`
- imports `design_plan_impl_implementation_phase.yaml`
- design decisions: `APPROVE`, `REVISE`, `BLOCK`
- plan decisions: `APPROVE`, `REVISE`
- implementation decisions: `APPROVE`, `REVISE`
- implementation loop cap: 40

`HEAD` major-project tranche stack:

- imports `tracked_big_design_phase.yaml`
- imports `major_project_tranche_plan_phase.yaml`
- imports `major_project_tranche_implementation_phase.yaml`
- imports `major_project_roadmap_revision_phase.yaml` through the drain iteration workflow
- design decisions: `APPROVE`, `REVISE`, `ESCALATE_ROADMAP_REVISION`, `BLOCK`
- plan decisions: `APPROVE`, `REVISE`, `ESCALATE_REDESIGN`, `BLOCK`
- implementation decisions: `APPROVE`, `REVISE`, `ESCALATE_REPLAN`, `BLOCK`
- implementation loop cap: 40
- soft escalation threshold: 10 cumulative implementation review iterations since last approved design
- selected tranche stack transition cap: 120

## Scenario Setup

Target case: T26 oversized tranche.

Starting state:

- T26 manifest status is `pending`.
- T26 has `design_depth: big` and `completion_gate: implementation_approved`.
- T26 prerequisites include T38, T37, T36, T34, T33, T32, T31, T21, T22, T23, T13, T14, and T16.
- T26 brief asks for full reviewed public `chili` parity, solver correctness, convergence, basis limits, sparse/dense representation, output containers, public CUDA FP64 or reviewed CUDA blockers, FP32 promotions where justified, docs, examples, capability records, performance notes, representative scale cases, memory/chunking evidence, and no silent CPU fallback or precision downgrade.
- The brief says unsafe or infeasible in-scope MATLAB numeric modes must remain open for explicit roadmap recharter, not be treated as tranche closure.

Hard case: a difficult but local tranche where repeated revisions are shrinking real local defects and the approved design/plan remain credible.

Small case: a routine major-project tranche that should approve before threshold crossing.

## Evidence Ledger

| ID | Type | Evidence | Use In Simulation |
| --- | --- | --- | --- |
| E1 | specified | EasySpin manifest entry for T26: pending, big design, implementation-approved gate, broad prerequisite list | Starting state and route selection |
| E2 | specified | T26 brief objective and scope: full reviewed public `chili` parity plus explicit recharter for infeasible in-scope modes | Scope preservation rule |
| E3 | observed | Actual T26 design and plan both reached approval in the historical run | Estimate that initial design/plan may approve before implementation evidence exists |
| E4 | observed | Actual final T26 implementation review decision was `REVISE` with high finding: full-scope denominator still unimplemented, preview-only route still blocked | Estimate terminal implementation evidence |
| E5 | observed | Actual execution report says preview cleanup landed, but solver-family completion, runtime-row promotion, parity/workflow closure, and docs migration remained current-scope work | Distinguish local progress from tranche closure |
| E6 | observed | Actual fresh gate: `write_t26_chili_reports.py --check` exited 1 with workflow/parity/benchmarks blocked and `closes_t26_denominator=False` | Validate non-closing failure mode |
| E7 | observed | Actual run `20260422T224455Z-avq8uu` status is `failed` | Validate old-workflow terminal outcome |
| E8 | specified | `HEAD^` implementation review allows only `APPROVE` or `REVISE` and maxes at 40 iterations | Old workflow routing |
| E9 | specified | `HEAD` implementation review allows `ESCALATE_REPLAN` and consumes `implementation_iteration_context` | New implementation escalation behavior |
| E10 | specified | `HEAD` plan review allows `ESCALATE_REDESIGN` and consumes active upstream escalation context | New plan escalation behavior |
| E11 | specified | `HEAD` design review allows `ESCALATE_ROADMAP_REVISION` and emits `roadmap_change_request.json` | New design-to-roadmap behavior |
| E12 | specified | `HEAD` drain iteration handles `ESCALATE_ROADMAP_REVISION` by calling roadmap revision and promoting approved roadmap/manifest candidates | New terminal route |
| E13 | specified | `HEAD` design prompt says to use `ESCALATE_ROADMAP_REVISION` when current-tranche redesign is insufficient and a split/reorder/prerequisite/ownership change is needed | Scope-preserving redesign behavior |
| E14 | specified | `HEAD` plan prompt rejects deferring material design requirements without authority/rationale/handoff criteria | Prevents silent plan narrowing |
| E15 | specified | `HEAD` implementation prompt says unfinished current-scope work blocks approval and threshold crossing requires locus assessment | Prevents silent implementation narrowing |

## Deterministic Workflow Delta

At `HEAD^`, once design and plan approve, T26 can only loop in implementation until `APPROVE` or iteration failure. The workflow has no typed route to say "the plan is wrong," "the design is wrong," or "the roadmap tranche should be split."

At `HEAD`, the same implementation evidence can produce a deterministic upward route:

1. implementation review writes `ESCALATE_REPLAN`
2. selected tranche stack activates implementation escalation context
3. plan phase consumes upstream escalation context
4. plan review can write `ESCALATE_REDESIGN`
5. selected tranche stack activates plan escalation context
6. big-design phase consumes upstream escalation context
7. design review can write `ESCALATE_ROADMAP_REVISION`
8. selected tranche stack finalizes item outcome as `ESCALATE_ROADMAP_REVISION`
9. drain iteration calls roadmap revision
10. approved roadmap revision promotes updated roadmap and manifest, then drain status is `CONTINUE`

This deterministic route is bounded by `max_transitions: 120`, phase loop caps, and terminal decisions.

Known deterministic caveat: `HEAD` writes `phase_iteration_index` as `0` in the implementation iteration context command. This simulation relies on `cumulative_review_iterations_since_design_approval`, not the local loop index.

## Simulated Event Log

### Target Case: T26 Oversized Tranche, HEAD^

| Event | Phase/Step | Consumed Inputs | Decision/Output | Produced State | Next Route | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| O1 | Select tranche | Manifest with T26 pending and prerequisites complete | T26 selected | Item state roots created | Big design | High, deterministic after selection assumptions |
| O2 | Draft/review design | T26 brief, project roadmap, manifest | `REVISE` then `APPROVE` | Full-scope T26 design | Plan | Medium; provider judgment, supported by actual approval |
| O3 | Draft/review plan | Approved full-scope design | `REVISE` then `APPROVE` | Broad one-tranche plan | Implementation | Medium; provider judgment, supported by actual approval |
| O4 | Execute implementation | Design and plan | Partial scaffold and preview evidence | Execution report says work remains | Implementation review | Medium; inferred from actual terminal artifacts |
| O5 | Review cycles 1-39 | Design, plan, execution report | Repeated `REVISE` | Review reports and revised execution reports | Fix implementation | Medium; exact count simulated, route deterministic |
| O6 | Review cycle 40 | Same | `REVISE`; no escalation option exists | Implementation loop cannot approve | Workflow failure / skipped-after-implementation path | High route confidence; exact runtime failure shape depends on executor |

Terminal `HEAD^` outcome: original T26 fails late after exhausting implementation review/fix capacity. Required work remains in a failure report, not in structured successor roadmap scope.

### Target Case: T26 Oversized Tranche, HEAD

| Event | Phase/Step | Consumed Inputs | Decision/Output | Produced State | Next Route | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| N1 | Select tranche | Manifest with T26 pending and prerequisites complete | T26 selected | Item state roots, inactive upstream context | Big design | High, deterministic after selection assumptions |
| N2 | Draft/review design | T26 brief, project roadmap, manifest, inactive upstream context | `REVISE` then `APPROVE` | Full-scope design; inactive design escalation context | Plan | Medium; actual history shows approval likely before implementation evidence |
| N3 | Draft/review plan | Approved design, inactive upstream context | `REVISE` then `APPROVE` | Broad plan attempting full T26 in one tranche | Implementation | Medium; actual history shows approval likely |
| N4 | Execute implementation attempt 1 | Design and plan | Partial scaffold/preview evidence | Execution report with non-closing preview route | Implementation review loop | Medium; inferred from actual execution report |
| N5 | Implementation reviews 1-9 | Design, plan, execution report, iteration context below threshold | `REVISE` | Local fixes continue; review reports identify concrete gaps | Fix implementation | Medium; provider judgment, threshold not crossed |
| N6 | Implementation review 10 | Same plus threshold-crossed context | `ESCALATE_REPLAN` | Active implementation escalation context: plan lacks executable route from preview numerics to public denominator closure | Plan | Medium-high; prompt requires locus assessment and actual evidence shows structural non-closure |
| N7 | Plan review with escalation context | Design, plan, upstream implementation escalation context | `ESCALATE_REDESIGN` | Active plan escalation context | Big design | Medium-high; plan-only repair would not preserve full denominator credibly |
| N8 | Redesign review with plan escalation context | T26 brief, roadmap, manifest, prior implementation evidence, upstream plan escalation context | `ESCALATE_ROADMAP_REVISION` | Active design escalation context and `roadmap_change_request.json` asking to supersede/split T26 | Roadmap revision | Medium; key judgment point |
| N9 | Roadmap revision | Project brief, current roadmap, current manifest, roadmap change request | `APPROVE` after revision if successor scope is explicit | Updated roadmap and manifest candidates with original T26 superseded and successor tranches carrying omitted work | Promote candidates; continue drain | Medium; depends on revision quality and manifest validation |

Terminal `HEAD` outcome: original T26 is superseded through roadmap revision after one threshold-sized implementation attempt. It does not approve, and it does not silently narrow. Remaining work is preserved in successor tranche scope.

### Hard But Local Tranche, HEAD

| Event | Phase/Step | Consumed Inputs | Decision/Output | Rationale | Confidence |
| --- | --- | --- | --- | --- | --- |
| H1 | Implementation reviews before threshold | Design, plan, execution reports | `REVISE` | Local defects remain, but fixes are reducing the failure surface | Medium |
| H2 | Implementation review after threshold | Same plus threshold-crossed context | `REVISE` with escalation assessment | Continued local implementation remains credible because the plan/design are still executable | Medium |
| H3 | Later review | Updated execution report | `APPROVE` | No current-scope blockers remain | Low-medium; scenario is representative, not T26-specific evidence |

This scenario checks that `HEAD` does not force escalation solely because the threshold crossed.

### Small Routine Tranche, HEAD

| Event | Phase/Step | Consumed Inputs | Decision/Output | Rationale | Confidence |
| --- | --- | --- | --- | --- | --- |
| S1 | Design/plan | Brief and prior context | `APPROVE` after normal review | Scope is bounded | Medium |
| S2 | Implementation review | Execution report before threshold | `APPROVE` | No current-scope blockers | Medium |

Escalation artifacts remain inactive. Process overhead is extra state, not extra workflow churn.

## Decision Rationale

Why `HEAD^` fails late:

- E8 gives implementation only `APPROVE` or `REVISE`.
- E4-E6 show the realistic terminal implementation evidence is "current-scope denominator still unimplemented," not "ready to approve."
- With no upward route, repeated `REVISE` is the only available non-approval decision until loop exhaustion.

Why `HEAD` escalates at implementation review 10:

- E9 introduces `ESCALATE_REPLAN`.
- E15 says threshold crossing requires explicit locus assessment.
- E4-E6 show remaining work is not merely a stale report or invalid gate; public route promotion and parity closure remain structurally missing.
- The likely high-quality decision is `ESCALATE_REPLAN`, because local fixes are no longer the right locus.

Why plan escalates to redesign instead of approving a quick repair:

- E10 allows `ESCALATE_REDESIGN`.
- E14 rejects plans that defer material design requirements without authority and rejects overbroad plans that collapse separable responsibilities into hard-to-review units.
- T26's remaining work spans solver substrate, public runtime promotion, parity/release closure, and performance evidence. A plan-only repair would be a second attempt to package the same overbroad denominator unless the design boundary changes.

Why design escalates to roadmap revision instead of approving a narrowed redesign:

- E2 says infeasible in-scope modes require explicit roadmap recharter, not closure.
- E13 says `ESCALATE_ROADMAP_REVISION` is appropriate when local redesign alone is insufficient and split/reorder/prerequisite insertion is needed.
- A narrowed local architecture that omits public runtime promotion or parity closure would silently drop required work unless successor scope is created.
- Therefore the simulated design decision is `ESCALATE_ROADMAP_REVISION`, not `APPROVE`.

Why roadmap revision approves:

- The simulated `roadmap_change_request.json` asks for a split/supersession, not local closure.
- Approval is conditional on updated roadmap and manifest preserving omitted work as successor tranches.
- If the candidate roadmap/manifest failed to preserve omitted work, the correct simulated decision would be `REVISE` or `BLOCK`, not approval.

## Comparison

| Dimension | HEAD^ | HEAD |
| --- | --- | --- |
| Terminal result for original T26 | Late implementation failure | Superseded by roadmap revision |
| First non-local correction point | None | Implementation review 10 |
| Scope preservation | Failure report only | Required work carried into successor roadmap scope |
| Risk of silent narrowing | High after failure, because no structured recharter path exists | Lower, because design review can force roadmap revision |
| Process burden | Lower until failure; high wasted implementation churn | Higher artifact/routing burden; less wasted implementation churn |
| Deterministic auditability | No escalation context | Explicit upstream escalation contexts, request artifact, and manifest update |
| Regression risk | Fewer moving parts | More moving parts and provider JSON obligations |

## Assumptions And Falsifiers

Assumptions:

- T26 prerequisites are treated as complete for selection.
- Initial T26 design and plan approval remain likely because the actual run approved them before implementation evidence accumulated.
- T26 implementation difficulty remains similar under blank-slate rerun.
- Reviewers follow the new prompt semantics at `HEAD`.
- Roadmap revision candidate preserves omitted work explicitly.

Falsifiers:

- If initial design review at `HEAD` immediately returns `ESCALATE_ROADMAP_REVISION`, the terminal outcome is still roadmap revision, but the implementation attempt does not occur.
- If plan review at `HEAD` immediately returns `ESCALATE_REDESIGN`, escalation happens earlier than simulated.
- If implementation genuinely closes public `chili` parity before threshold crossing, `HEAD` approves and this target-case simulation is wrong.
- If implementation evidence after threshold is still clearly shrinking local defects, review should remain `REVISE` with escalation assessment.
- If roadmap revision omits public runtime promotion or parity/release closure successor scope, roadmap review should return `REVISE` or `BLOCK`.
- If provider output fails to produce valid escalation JSON, runtime may fail before the intended route.

## Regression Risks

1. Provider-written escalation context JSON may be malformed or too vague.
2. Extra phase-local prompts could create checklist gravity and longer reports.
3. Over-eager reviewers may escalate difficult but converging work.
4. Roadmap revision promotion must validate manifest candidates before copying them into place.
5. The implementation iteration context currently sets `phase_iteration_index` to `0`; cumulative count is the reliable threshold signal.
6. Any redesign that narrows T26 without successor roadmap scope would violate the brief and should be rejected.

## Recommendation

Decision: `ADOPT_NARROWLY`

Adopt the `HEAD` behavior for major-project workflows. It improves the T26 failure mode by converting a late implementation-loop failure into a structured roadmap-revision outcome while preserving the omitted work in successor scope.

Do not broaden the escalation ladder to shared generic design-plan-implementation workflows without a separate simulation. Also add or keep behavioral tests for malformed escalation context, repeated escalation state hygiene, roadmap revision promotion, and hard-but-local tranches that should continue revising after threshold crossing.
