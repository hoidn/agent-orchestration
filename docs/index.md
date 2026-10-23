# Agent-Orchestration Documentation Hub

Start here to choose the contract, guide, capability owner or work plan for a
task. Normative runtime behavior lives in [specs/](../specs/index.md); accepted
component designs explain the language and architecture. This index routes to
those owners and does not independently select work or qualify a capability.

Read role labels separately from implementation status: **current contract/guide**
owns present rules or instructions, **plan** owns only its stated selection and
gates, and **historical/captured evidence** records past decisions or results.
A date or directory does not decide the role. See the
[role conventions](documentation_conventions.md#current-guidance-and-historical-records);
use the capability matrix to determine what is implemented and qualified.

<a id="quick-start"></a>
<a id="workflow-author-fast-path"></a>
<a id="finding-information"></a>
<a id="by-task"></a>
<a id="by-audience"></a>
<a id="testing-and-validation"></a>
<a id="workflow-runbooks-and-examples"></a>

## Fast Triage

| Need | Start here | Scope |
| --- | --- | --- |
| Understand the system | [Architecture overview](architecture_overview.md) and [orchestration model](orchestration_start_here.md) | Concepts, authority and component boundaries |
| Check available behavior | [Capability matrix](capability_status_matrix.md) | Implemented, partial, library, designed, future and historical surfaces; implementation does not imply public qualification |
| Author a workflow | [Workflow Lisp drafting guide](lisp_workflow_drafting_guide.md) or [typed Python guide](python_workflow_drafting_guide.md) | Direct `.orc` authoring or serial Python generation into the same compiler/runtime; prerequisites and admitted shapes at each destination |
| Choose a reusable helper | [Library reference](lisp_library_reference.md) | Typed inputs, outputs, composition and examples |
| Copy a complete example | [Workflow catalog](../workflows/README.md#which-example-should-i-copy) | Route readiness and copy safety; a compile check alone is not live-provider qualification |
| Compile, run, resume or invalidate | [Lifecycle](runtime_execution_lifecycle.md) and [CLI contract](../specs/cli.md) | Evaluated execution is the sole current workflow runtime; old profiles remain read-only |
| Inspect or monitor a run | [Monitoring](workflow_monitoring.md), [observability](../specs/observability.md) and [dashboard design](design/dashboard_observability_summary_gui.md) | Reports and dashboards are views, not execution authority |
| Change the language/compiler | [Design index](design/README.md), [frontend baseline](design/workflow_lisp_frontend_specification.md) and [evaluated execution](design/workflow_lisp_evaluated_execution.md) | Retained types/imports and checked closed-program execution |
| Use editor tooling | [LSP setup](workflow_lisp_language_server_setup.md) and [tooling contract](design/workflow_lisp_language_server.md) | Evaluated semantic/LSP qualification F2 remains OPEN_NOT_WAIVED; L6 remains unselected |
| Use phased provider delivery | [2.39 recipe](lisp_workflow_drafting_guide.md#authoring-phased-contract-delivery-target-239), [accepted contract](design/workflow_lisp_phased_contract_delivery.md#target-239-evaluated-migration) and [migration plan](plans/2026-10-16-phased-execution-239-plan.md) | Bounded deterministic lifecycle; explicitly capable interactive provider required; paid live-provider qualification unselected |
| Use agent instances | [Agent Sessions](lisp_workflow_drafting_guide.md#agent-sessions-target-238) | Bounded target-2.38 native session turns; qualification and remaining comparisons have separate owners |
| Run a confined child | [Command-only recipe](lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only) and [confinement contract](design/workflow_lisp_run_ref_expression_environments.md) | Command-only `:network :none` is implemented; private transport does not open public confined providers |
| Evaluate parallel work | [Evaluated execution](design/workflow_lisp_evaluated_execution.md) and [capability matrix](capability_status_matrix.md) | Target 2.37 has bounded qualification; parallel source is not generally copy-safe |
| Select implementation work | [Delivery plan](plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md), [evolution roadmap](plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md), [substrate track](plans/2026-07-26-substrate-maintenance-track.md) and [simplification execution record](plans/2026-10-15-orc-simplification-roadmap-extension.md) | Current selection, dependencies and remaining gates; the extension records completed selected lanes, explicit deferrals and verification limits, with existing gates preserved |
| Review proposals and backlog | [Work definition model](work_definition_model.md) and [backlog inventory](backlog/README.md) | File residence in `active/` does not establish selection or completion |
| Choose review/revision/search patterns | [Workflow design lessons](orc_workflow_design_lessons.md) and [comparison harness](../experiments/compare/README.md) | Separate executable recipes, task calibration and measured quality; historical results do not establish general utility |
| Work with provider prompts | [Prompt catalog](../prompts/README.md), [providers](../specs/providers.md) and [dependencies](../specs/dependencies.md) | Manual reuse, typed imports and executable consumers have distinct prerequisites |
| Verify a change | [Testing guide](../tests/README.md), [acceptance](../specs/acceptance/index.md) and [verification manifest](workflow_lisp_g6_verification_gate.json) | Use current selectors and scoped evidence |
| Maintain documentation | [Documentation conventions](documentation_conventions.md) | Current contracts, active plans, evidence preservation and historical scope |

## Clarifications ⚠️

- [CLI admission](../specs/cli.md#executable-support-boundary) and
  [executor retirement](design/workflow_lisp_executor_retirement.md) govern
  execution and the selected 2.35 source/import/tooling floor. Historical
  YAML/flat contracts and frozen source do not supply current analysis,
  execution or recovery permission.
- Targets 2.35–2.39 share the evaluated runtime. Target 2.39 adds [procedure authoring](lisp_workflow_drafting_guide.md#procedure-contracts-at-target-239), finite source admission and [bounded phased delivery](lisp_workflow_drafting_guide.md#authoring-phased-contract-delivery-target-239); imported 2.35–2.38 definitions retain their original contracts.
- The 2.35 source floor covers transitive source and typed-program imports,
  REPL loading and LSP analysis. Historical report/dashboard data readers do
  not reopen those source doors; evaluated LSP F2 remains OPEN_NOT_WAIVED.
- Validated typed values, closed artifacts and memo records own current runtime
  meaning. Reports, stdout, debug projections and pointer files are views unless
  their owning contract explicitly says otherwise.
- Implementation, executable admission, live qualification and research utility
  are separate claims. Follow the capability owner and its evidence rather than
  inferring one from another.
- Plans own selection and remaining work; reports preserve captured results.
  Neither an old imperative nor an index entry selects a new workflow run.

## Reading Paths

Use these paths when you know the kind of work you are doing but not yet which
document owns the answer.

### When Changing Specs

- Start with [Master Spec](../specs/index.md).
- Read the relevant normative spec, usually [DSL](../specs/dsl.md),
  [Step IO](../specs/io.md), [State](../specs/state.md),
  [Providers](../specs/providers.md), or [Dependencies](../specs/dependencies.md).
- Check [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) for
  current author-facing explanation and examples; use the historical YAML
  guide only when interpreting retired source.
- If docs and specs disagree, specs win; update explanatory docs afterward.

### When Writing Or Revising Design Docs

- Start with [Design Template](templates/design_template.md).
- Read [Workflow Language Design Principles](design/workflow_language_design_principles.md).
- Read the closest existing design document before adding a new one.
- If the design changes discoverability, update this index.
- If the design introduces runtime or validation obligations, add or plan the
  corresponding `specs/` update.

### When Working On Workflow Lisp

- Start with [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md).
- Check the parent [Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md).
- Use [evaluated execution](design/workflow_lisp_evaluated_execution.md) for
  the checked closed program, evaluator, effect identity and memo authority.
  The frontend specification owns retained types, macros and typed imports.
- Semantic IR, Executable IR, Stdlib Lowering and State Layout document
  historical flat execution and retained data contracts. They do not admit
  excluded evaluated effects such as views or resource transitions; check
  the capability matrix before using those surfaces.
- For a historical promotion decision, read the frozen
  [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md);
  use route readiness and direct owner tests for current claims.

### When Auditing Historical YAML-To-`.orc` Migrations

- Start with [Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md).
- Read [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) and
  [Workflow Language Design Principles](design/workflow_language_design_principles.md).
- Check the relevant runtime specs and preserved reports for the behavior that
  was promoted.
- Treat compile, validation, and dry-run as current regression evidence, not a
  request to regenerate the retired manifest/report gate.

### When Authoring Workflows

- Choose [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) for
  direct `.orc` source or [Typed Python Workflows](python_workflow_drafting_guide.md)
  for typed serial source generation. Both use the same compiler and runtime.
- Use [Workflow Lisp Library Reference](lisp_library_reference.md) to choose a
  reusable helper or complete candidate generation/evaluation/selection example.
- Read [Designing `.orc` Workflows That Beat A Single Call](orc_workflow_design_lessons.md)
  before choosing a review, revise, or select pattern.
- Check the [Capability Status Matrix](capability_status_matrix.md) and the
  route-readiness registry before selecting a form or copy-safe `.orc` example.
- Check [DSL](../specs/dsl.md), [Step IO](../specs/io.md), and
  [Providers](../specs/providers.md) for normative behavior.
- Use [Prompt Index](../prompts/README.md) when provider prompts are involved.
- Use [Workflow Drafting Guide](workflow_drafting_guide.md) only to interpret
  or translate historical YAML/YML source; the retired frontend cannot execute it.

### When Reviewing Plans Or Backlog Drains

- Start with [Work Definition Model](work_definition_model.md).
- Read the relevant work instructions under `docs/plans/`.
- For generated gap designs, use
  [Design Gap Architecture Template](templates/design_gap_implementation_architecture_template.md).
- Check the active design, backlog item, run evidence, and any generated
  summaries before changing status labels.

---

<a id="informative-guides-docs"></a>
<a id="normative-spec-modules-specs"></a>

## Document Catalog

These links retain the detailed catalog's destinations and section anchors.
Use the routes above for a new task; consult each destination's scope before
reusing instructions. Plans can contain active obligations as well as history.

| Document | Role |
| --- | --- |
| <a id="readme---project-overview"></a>[README](../README.md) | Guide or reference; prerequisites and limits at destination |
| <a id="orchestration-start-here"></a>[Orchestration Start Here](orchestration_start_here.md) | Guide or reference; prerequisites and limits at destination |
| <a id="runtime-execution-lifecycle"></a>[Runtime Execution Lifecycle](runtime_execution_lifecycle.md) | Guide or reference; prerequisites and limits at destination |
| <a id="workflow-monitoring"></a>[Workflow Monitoring](workflow_monitoring.md) | Guide or reference; prerequisites and limits at destination |
| <a id="workflow-drafting-guide"></a>[Workflow Drafting Guide](workflow_drafting_guide.md) | Historical YAML interpretation; current authoring uses the Lisp or Python guide |
| <a id="workflow-lisp-drafting-guide"></a>[Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) | Guide or reference; prerequisites and limits at destination |
| [Typed Python Workflows](python_workflow_drafting_guide.md) | Current guide; provider-free build/check/run recipe and serial frontend limits |
| <a id="workflow-lisp-library-reference"></a>[Workflow Lisp Library Reference](lisp_library_reference.md) | Guide or reference; prerequisites and limits at destination |
| <a id="work-definition-model"></a>[Work Definition Model](work_definition_model.md) | Guide or reference; prerequisites and limits at destination |
| <a id="procedure-first-roadmap-execution-sequence"></a>[Procedure-First Roadmap Execution Sequence](plans/2026-07-09-procedure-first-roadmap-execution-sequence.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-language-quality-and-domain-semantics-roadmap"></a>[Workflow Lisp Language Quality And Domain Semantics Roadmap](plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md) | Plan or decision record; check current selection |
| <a id="substrate-maintenance-and-persistence-parsimony-track"></a>[Substrate Maintenance And Persistence Parsimony Track](plans/2026-07-26-substrate-maintenance-track.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-pure-result-replay"></a>[Workflow Lisp Pure-Result Replay](design/workflow_lisp_pure_result_replay.md) | Historical design; current owner linked at destination |
| <a id="pure-result-replay-feasibility-component-plan"></a>[Pure-Result Replay Feasibility Component Plan](plans/2026-07-30-pure-result-replay-feasibility-component-plan.md) | Plan or decision record; check current selection |
| <a id="pure-result-replay-activation-component-plan"></a>[Pure-Result Replay Activation Component Plan](plans/2026-07-30-pure-result-replay-activation-component-plan.md) | Plan or decision record; check current selection |
| <a id="mc-common-helper-consolidation-component-plan"></a>[MC Common-Helper Consolidation Component Plan](plans/2026-07-30-mc-common-helper-consolidation-component-plan.md) | Plan or decision record; check current selection |
| <a id="m0-green-baseline-implementation-plan"></a>[M0 Green Baseline Implementation Plan](plans/2026-07-29-m0-green-baseline-component-plan.md) | Plan or decision record; check current selection |
| <a id="m1-estate-shrink-implementation-plan"></a>[M1 Estate Shrink Implementation Plan](plans/2026-07-29-m1-estate-shrink-component-plan.md) | Plan or decision record; check current selection |
| <a id="provider-at-least-once-recovery-component-plan"></a>[Provider At-Least-Once Recovery Component Plan](plans/2026-07-30-provider-at-least-once-recovery-component-plan.md) | Plan or decision record; check current selection |
| <a id="provider-attempt-allocator-simplification-component-plan"></a>[Provider Attempt Allocator Simplification Component Plan](plans/2026-07-30-provider-attempt-allocator-simplification-component-plan.md) | Plan or decision record; check current selection |
| <a id="adjudication-rerun-recovery-component-plan"></a>[Adjudication Rerun Recovery Component Plan](plans/2026-07-30-adjudication-rerun-recovery-component-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-compiler-session-state-implementation-plan"></a>[Workflow Lisp Compiler Session State Implementation Plan](plans/2026-07-27-workflow-lisp-compiler-session-state-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="orc-effectiveness-lean-pilot-design"></a>[`.orc` Effectiveness Lean Pilot Design](superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md) | Historical study design; preserve original conditions |
| <a id="lean-pilot-forensics-and-post-e2-study-inputs"></a>[Lean Pilot Forensics And Post-E2 Study Inputs](reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md) | Captured evidence; not a behavioral contract |
| <a id="orc-effectiveness-comparison-harness"></a>[Orc Effectiveness Comparison Harness](design/orc_effectiveness_comparison_harness.md) | Component contract or target; check admitted scope |
| <a id="task-difficulty-calibration"></a>[Task-Difficulty Calibration](reports/2026-10-14-task-difficulty-calibration.md) | Captured evidence; not a behavioral contract |
| <a id="calibration-continuation-rung-1s-third-sample"></a>[Calibration Continuation: Rung 1's Third Sample](reports/2026-10-15-calibration-continuation.md) | Captured evidence; not a behavioral contract |
| <a id="e-b2-historical-not-calibration-qualified"></a>[E-B2: Historical Workflow Comparison And Calibration Limits](reports/2026-10-15-calibrated-orc-versus-single-call.md) | Captured evidence; not a behavioral contract |
| <a id="e-b3-orc-versus-single-call-rung1"></a>[E-B3: Workflows Versus A Single Call On Calibration Rung 1 (claims not evaluated)](reports/2026-10-16-eb3-orc-versus-single-call-rung1.md) | Captured evidence; not a behavioral contract |
| <a id="effectiveness-harness-and-experiments-plan"></a>[Effectiveness Harness And Experiments Plan](plans/2026-10-14-effectiveness-harness-and-experiments-plan.md) | Plan or decision record; check current selection |
| <a id="orc-research-charter"></a>[ORC Research Charter](plans/2026-09-08-orc-research-charter.md) | Plan or decision record; check current selection |
| <a id="orc-structural-search-roadmap"></a>[ORC Structural Search Roadmap (R3 Implementation Sequence)](plans/2026-10-18-orc-structural-search-roadmap.md) | Plan/decision record; Phases 0–1 have measure-free readouts, Phase 2 remains unselected; natural task difficulty is not qualified, Luna low/high preparation selected with new budget pending; B/B2/C remain separately gated |
| [ORC Structural Search Phase 0 Offline Apparatus Implementation Plan](plans/2026-10-18-orc-structural-search-phase0-offline-plan.md) | Implementation plan; executed (offline, scripted providers) |
| [ORC Structural Search Live Phase 0 Gates And Phase 1 Implementation Plan](plans/2026-10-18-orc-structural-search-live-phase1-plan.md) | Implementation plan; live Phase 0 gates and Phase 1; run ([report](reports/2026-10-18-orc-structural-search-phase1.md)) |
| [ORC Structural Search Phase 2 (I2 And Adaptive Search) Implementation Plan](plans/2026-10-18-orc-structural-search-phase2-plan.md) | Implementation plan; mode 2, I2 episodes and validation split built offline (scripted providers); not selected by the Phase 1 decision; live runs need a new owner selection and budget approval |
| [ORC Structural Search Three-Arm Compile-Only Readout Implementation Plan](plans/2026-10-19-orc-structural-search-three-arm-readout-plan.md) | Implementation plan; executed 2026-10-19 (I1, I2, I3; measure-free, judge stage not run under the calibration rule; [report section](reports/2026-10-18-orc-structural-search-phase1.md#three-arm-readout)) |
| [ORC Structural Search Stage C1: Cumulative Whole-Program Campaign Pilot Implementation Plan](plans/2026-10-19-orc-structural-search-cumulative-pilot-plan.md) | Implementation plan; offline Tasks 1–7 implemented and verified; live Tasks 8–13 retain separate owner gates; the [natural task-difficulty plan](plans/2026-10-22-simple-evaluation-calibration-plan.md) owns the selected weak/strong pilot; artificial-control checks do not establish task difficulty |
| [ORC Structural Search: The `module` Condition (Rewrite, Compile, Repair)](plans/2026-10-19-orc-structural-search-module-rewrite-plan.md) | Maintained module decision and live-selection gates; revised apparatus delivered offline, with fresh evidence in the active implementation plan; no live study or budget selected |
| [ORC Structural Search `module` Condition Implementation Plan](plans/2026-10-19-orc-structural-search-module-condition-implementation-plan.md) | Offline delivery/verification record including reviewed main-integration policy-set/five-class and cache-write corrections; scripted providers only, no live arm |
| [ORC Structural Search Measurement Calibration Implementation Plan](plans/2026-10-19-orc-structural-search-measurement-plan.md) | Measurement selection and coordination ledger; A/AT/AS are historical evaluator checks; TD2 did not qualify task difficulty; fresh Luna low/high packet is frozen and verified offline, with new spend pending; B/B2/C and campaigns retain separate gates |
| [Simple Evaluation Implementation Plan](plans/2026-10-22-simple-evaluation-plan.md) | Offline evaluator delivery and verification: independent rubric components and three-control mean separation; historical AT failure unchanged; artificial-control checks do not qualify task difficulty |
| [Natural Task-Difficulty Calibration](plans/2026-10-22-simple-evaluation-calibration-plan.md) | Current plan: fresh Luna low versus Luna high, same tasks and blind rubric; review-environment and exact-effort fixes integrated and verified; fresh packet frozen and checked offline; new budget pending; prior 16 starts exhausted |
| [Natural Task-Difficulty Pilot: Isolation Incident](reports/2026-10-22-natural-task-difficulty-calibration.md) | Captured evidence: two interrupted Luna roots and four forbidden Claude/Fable probes; six starts count against the original ten-session cap; no accepted quality observations |
| [Natural Task-Difficulty Recovery: RPI Gap Fails, PRR Judge Excluded](reports/2026-10-22-natural-task-difficulty-recovery.md) | Captured TD2 evidence: RPI gap −1.5 with environment uncertainty; PRR judge excluded for sandbox-induced deletions; all 16 authorized starts spent, no two-task qualification; proper environment fix verified offline |
| [ORC Structural Search Measurement Calibration: Step A](reports/2026-10-19-orc-structural-search-measurement-calibration.md) | Captured calibration evidence; A failed the frozen RPI spread rule, PRR passed; 8 calls with complete receipts; no ORC benefit claim |
| [ORC Structural Search Measurement Calibration: Interrupted Terra-Only AT](reports/2026-10-20-orc-structural-search-measurement-at.md) | Captured interrupted calibration evidence; RPI passed both frozen batches, PRR committed none after two native-agent control incidents; four CLI plus six native child sessions exhausted cap10, all Terra high; combined calibration OPEN and total cost unavailable; no ORC benefit claim |
| [ORC Structural Search Measurement Calibration: Completed Terra-Only AT](reports/2026-10-20-orc-structural-search-measurement-at-completion.md) | Captured final evidence; all four pairs complete, RPI passes and PRR fails P2 in one batch; 12/20 sessions, all Terra high; two continuation sessions without new children; observed list-price cost ≥USD4.3461492, complete total unavailable; no ORC benefit claim |
| <a id="orc-structural-search-phase1"></a>[ORC Structural Search Phase 1: Catalog And Unguided I1 Sampling On Family (a)](reports/2026-10-18-orc-structural-search-phase1.md) | Captured evidence; not a behavioral contract |
| [Source-Site Inspection Feasibility And Manifest Implementation Plan](plans/2026-10-18-source-site-inspection-feasibility-plan.md) | Implementation plan; executed (offline, scripted providers) |
| <a id="workflow-lisp-source-site-inspection"></a>[Workflow Lisp Source-Site Inspection](design/workflow_lisp_source_site_inspection.md) | Component contract or target; Partial: implemented offline (scripted providers); unselected for live use; not copy-safe |
| <a id="orc-structural-search-driver"></a>[ORC Structural Search Driver](design/orc_structural_search_driver.md) | Component contract or target; Partial apparatus implemented offline; mode-2 helpers historical and fresh adaptive launch unsupported; live Phase 1 measure-free; measurement plan owns final Terra-only AT failure (PRR P2), with gate 2 FAIL_NOT_QUALIFIED and gate 3 unmeasured; no live Phase 2/module selection; not copy-safe |
| <a id="orc-structural-search-cumulative-campaigns"></a>[ORC Structural Search Cumulative Campaigns](design/orc_structural_search_cumulative_campaigns.md) | Component contract or target; Partial: Stage C1 implemented offline; no live campaign or accepted measure; criterion-selected calibration follows the harness contract; Stage C2 fragment evidence remains unselected |
| <a id="orc-programmability-composition-and-improvement"></a>[ORC Programmability, Composition, And Improvement](design/orc_reuse_introspection_search_experiment.md) | Component contract or target; check admitted scope |
| <a id="orc-session-patterns-and-research-inputs"></a>[ORC Session Patterns And Research Inputs](reports/2026-09-08-orc-session-patterns.md) | Captured evidence; not a behavioral contract |
| <a id="workflow-lisp-evolution-follow-on-roadmap"></a>[Workflow Lisp Evolution Follow-On Roadmap](plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md) | Plan or decision record; check current selection |
| <a id="e0-canonical-direct-control-component-plan"></a>[E0 Canonical Direct-Control Component Plan](plans/2026-07-31-workflow-lisp-e0-direct-control-component-plan.md) | Plan or decision record; check current selection |
| <a id="e1-run-ref-component-plan"></a>[E1 `run-ref` Component Plan](plans/2026-07-31-workflow-lisp-e1-run-ref-component-plan.md) | Plan or decision record; check current selection |
| <a id="e2-trial-component-plan"></a>[E2 `trial` Component Plan](plans/2026-08-01-workflow-lisp-e2-trial-component-plan.md) | Plan or decision record; check current selection |
| <a id="es-first-effectiveness-study-component-plan"></a>[ES First Effectiveness Study Component Plan](plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md) | Plan or decision record; check current selection |
| <a id="es-task-5-study-controller-execution-plan"></a>[ES Task 5 Study Controller Execution Plan](plans/2026-08-03-es-task5-study-controller-execution-plan.md) | Plan or decision record; check current selection |
| <a id="es-f1-large-scope-pre-run-refreeze-plan"></a>[ES F1 Large-Scope Pre-Run Refreeze Plan](plans/2026-08-03-es-f1-large-scope-refreeze-execution-plan.md) | Plan or decision record; check current selection |
| <a id="lsp-frontend-prerequisites-p-series-roadmap"></a>[LSP Frontend Prerequisites P-Series Roadmap](plans/2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-recursion-rec-series-roadmap"></a>[Workflow Lisp Recursion REC-Series Roadmap](plans/2026-08-01-workflow-lisp-recursion-rec-series-roadmap.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-language-server-l6-utility-roadmap"></a>[Workflow Lisp Language Server L6 Utility Roadmap](plans/2026-07-31-workflow-lisp-language-server-l6-utility-roadmap.md) | Plan or decision record; check current selection |
| [OMP Providers And Native Continuation](design/omp_provider_and_native_continuation.md) | Current retained contract; upgrade procedure in the runbook |
| [Workflow Lisp Provider Call Policy](design/workflow_lisp_provider_call_policy.md) | Current component contract; provider choice, defaults and registry binding |
| <a id="omp-integration-design-and-roadmap-extension"></a>[OMP Integration Design And Roadmap Extension](plans/2026-08-14-omp-integration-design-and-roadmap.md) | Historical delivery record; current contract linked above |
| <a id="omp-pin-upgrade-runbook"></a>[OMP Pin Upgrade Runbook](omp_upgrade_runbook.md) | Guide or reference; prerequisites and limits at destination |
| <a id="procedure-first-reuse-contract"></a>[Procedure-First Reuse Contract](design/workflow_lisp_procedure_first_reuse_contract.md) | Component contract or target; check admitted scope |
| <a id="procedure-migration-identity-compatibility"></a>[Procedure-Migration Identity Compatibility](design/workflow_lisp_procedure_migration_identity_compatibility.md) | Durable identity contract; migration machinery/evidence historical |
| <a id="procedure-migration-identity-compatibility-prerequisites-plan"></a>[Procedure-Migration Identity Compatibility Prerequisites Plan](plans/2026-07-13-procedure-migration-identity-compatibility-plan.md) | Plan or decision record; check current selection |
| <a id="tracked-plan-procedure-first-pilot"></a>[Tracked-Plan Procedure-First Pilot](plans/2026-07-13-procedure-first-pilot-plan.md) | Plan or decision record; check current selection |
| <a id="procedure-identity-store-match-scoped-counts-plan"></a>[Procedure Identity Store Match-Scoped Counts Plan](plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md) | Plan or decision record; check current selection |
| <a id="resume-projection-integrity-hardening-design-and-planning-plan"></a>[Resume Projection Integrity Hardening Design And Planning Plan](plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md) | Plan or decision record; check current selection |
| <a id="resume-projection-integrity-hardening-design"></a>[Resume Projection Integrity Hardening Design](design/resume_projection_integrity_hardening.md) | Historical design; current owner linked at destination |
| <a id="resume-projection-integrity-hardening-implementation-plan"></a>[Resume Projection Integrity Hardening Implementation Plan](plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="procedure-first-migration-waves-implementation-plan"></a>[Procedure-First Migration Waves Implementation Plan](plans/2026-07-13-procedure-first-migration-waves-plan.md) | Plan or decision record; check current selection |
| <a id="user-facing-yaml-retirement-program"></a>[User-Facing YAML Retirement Program](plans/2026-07-07-yaml-retirement-program.md) | Plan or decision record; check current selection |
| <a id="yaml-retirement-task-2-commit-lineage-restart-design"></a>[YAML-Retirement Task 2 Commit-Lineage Restart Design](plans/2026-07-22-yaml-retirement-task-2-commit-lineage-restart-design.md) | Plan or decision record; check current selection |
| <a id="yaml-retirement-task-2-commit-lineage-restart-implementation-plan"></a>[YAML-Retirement Task 2 Commit-Lineage Restart Implementation Plan](plans/2026-07-22-yaml-retirement-task-2-commit-lineage-restart-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="yaml-to-workflow-lisp-gap-list"></a>[YAML-to-Workflow-Lisp Gap List](workflow_yaml_orc_gap_list.md) | Guide or reference; prerequisites and limits at destination |
| <a id="workflow-lisp-provider-prompt-dependencies"></a>[Workflow Lisp Provider Prompt Dependencies](design/workflow_lisp_provider_prompt_dependencies.md) | Current component contract; delivery history linked by owner |
| <a id="yaml-deprecation-surface-design"></a>[YAML Deprecation Surface Design](plans/2026-07-17-yaml-deprecation-surface-design.md) | Plan or decision record; check current selection |
| <a id="tracked-design-phase-identity-retirement-plan"></a>[Tracked-Design Phase Identity-Retirement Plan](plans/2026-07-16-tracked-design-phase-identity-retirement-plan.md) | Plan or decision record; check current selection |
| <a id="stack-implementation-phase-identity-retirement-plan"></a>[Stack Implementation Phase Identity-Retirement Plan](plans/2026-07-16-design-plan-impl-implementation-phase-identity-retirement-plan.md) | Plan or decision record; check current selection |
| <a id="same-file-build-checks-identity-retirement-decision"></a>[Same-File Build-Checks Identity-Retirement Decision](plans/2026-07-16-same-file-build-checks-identity-retirement-plan.md) | Plan or decision record; check current selection |
| <a id="design-delta-exported-workflow-retention-decision"></a>[Design Delta Exported-Workflow Retention Decision](plans/2026-07-16-design-delta-exported-workflow-retention-plan.md) | Plan or decision record; check current selection |
| <a id="design-delta-finalizer-projection-checkpoint-retention-decision"></a>[Design Delta Finalizer-Projection Checkpoint-Retention Decision](plans/2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md) | Plan or decision record; check current selection |
| <a id="design-delta-blocked-recovery-lowering-retention-decision"></a>[Design Delta Blocked-Recovery Lowering-Retention Decision](plans/2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md) | Plan or decision record; check current selection |
| <a id="design-delta-phase-orchestration-retention-decision"></a>[Design Delta Phase-Orchestration Retention Decision](plans/2026-07-16-design-delta-phase-orchestration-retention-plan.md) | Plan or decision record; check current selection |
| <a id="design-delta-completed-finalization-lowering-retention-decision"></a>[Design Delta Completed-Finalization Lowering-Retention Decision](plans/2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md) | Plan or decision record; check current selection |
| <a id="design-delta-drain-builder-checkpoint-retention-decision"></a>[Design Delta Drain-Builder Checkpoint-Retention Decision](plans/2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md) | Plan or decision record; check current selection |
| <a id="procedure-first-reuse-inventory"></a>[Procedure-First Reuse Inventory](plans/2026-07-13-procedure-first-reuse-inventory.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-autonomous-drain-work-instructions"></a>[Workflow Lisp Autonomous Drain Work Instructions](plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md) | Plan or decision record; check current selection |
| <a id="local-workflow-steering"></a>[Local Workflow Steering](steering.md) | Optional local input; empty content selects no work |
| <a id="verified-iteration-drain"></a>[Verified-Iteration Drain](design/verified_iteration_drain.md) | Component contract or target; check admitted scope |
| <a id="prompt-index"></a>[Prompt Index](../prompts/README.md) | Guide or reference; prerequisites and limits at destination |
| <a id="design-template"></a>[Design Template](templates/design_template.md) | Guide or reference; prerequisites and limits at destination |
| <a id="design-gap-architecture-template"></a>[Design Gap Architecture Template](templates/design_gap_implementation_architecture_template.md) | Guide or reference; prerequisites and limits at destination |
| <a id="workflow-language-design-principles"></a>[Workflow Language Design Principles](design/workflow_language_design_principles.md) | Component contract or target; check admitted scope |
| <a id="workflow-command-adapter-contract"></a>[Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-mvp-comparison"></a>[Workflow Lisp MVP Comparison](workflow_lisp_mvp_comparison.md) | Guide or reference; prerequisites and limits at destination |
| <a id="workflow-lisp-unified-design-for-unimplemented-surfaces"></a>[Workflow Lisp Unified Design for Unimplemented Surfaces](design/workflow_lisp_unified_frontend_design.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-repl-introspection"></a>[Workflow Lisp REPL Introspection](design/workflow_lisp_repl_introspection.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-repl"></a>[Workflow Lisp REPL](design/workflow_lisp_repl.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-frontend-specification"></a>[Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-refactor-architecture"></a>[Workflow Lisp Refactor Architecture](design/workflow_lisp_refactor_architecture.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-semantic-workflow-ir"></a>[Workflow Lisp Semantic Workflow IR](design/workflow_lisp_semantic_workflow_ir.md) | Retained typed-analysis and historical-reader contract |
| <a id="workflow-lisp-executable-ir"></a>[Workflow Lisp Executable IR](design/workflow_lisp_executable_ir.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-macro-surface-contract"></a>[Workflow Lisp Macro Surface Contract](design/workflow_lisp_macro_surface_contract.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-frontend-mvp-specification"></a>[Workflow Lisp Frontend MVP Specification](design/workflow_lisp_frontend_mvp_specification.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-procedure-references-and-partial-application"></a>[Workflow Lisp Procedure References And Partial Application](design/workflow_lisp_proc_refs_partial_application.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-local-procref-bindings"></a>[Workflow Lisp Local ProcRef Bindings](design/workflow_lisp_let_proc_local_proc_refs.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-provider-prompt-queue"></a>[Workflow Lisp Provider Prompt Queue](design/workflow_lisp_provider_prompt_queue.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-provider-live-binding"></a>[Workflow Lisp Provider Live Binding](design/workflow_lisp_provider_live_binding.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-provider-peer-messaging"></a>[Workflow Lisp Provider Peer Messaging](design/workflow_lisp_provider_peer_messaging.md) | Historical design; current owner linked at destination |
| <a id="provider-peer-messaging-v11-implementation-plan"></a>[Provider Peer Messaging v1.1 Implementation Plan](plans/2026-07-24-provider-peer-messaging-v1.1-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-pure-list-traversal"></a>[Workflow Lisp Pure List Traversal](design/workflow_lisp_pure_list_traversal.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-pure-list-traversal-implementation-plan"></a>[Workflow Lisp Pure List Traversal Implementation Plan](plans/2026-07-25-workflow-lisp-pure-list-traversal-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-transportable-value-type"></a>[Workflow Lisp Transportable `Value` Type](design/workflow_lisp_transportable_value_type.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-prompt-calculus"></a>[Workflow Lisp Prompt Calculus](design/workflow_lisp_prompt_calculus.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-phased-contract-delivery"></a>[Workflow Lisp Phased Contract Delivery](design/workflow_lisp_phased_contract_delivery.md#target-239-evaluated-migration) | Accepted target-2.39 contract; [migration plan](plans/2026-10-16-phased-execution-239-plan.md) owns implementation/evidence; retained target-2.23 sections are historical |
| <a id="workflow-lisp-phased-contract-delivery-implementation-plan"></a>[Workflow Lisp Phased Contract Delivery Implementation Plan](plans/2026-07-27-workflow-lisp-phased-contract-delivery-implementation-plan.md) | Historical target-2.23 Q5 plan; preserved delivery evidence |
| [Phased Execution At Target 2.39 Implementation Plan](plans/2026-10-16-phased-execution-239-plan.md) | Current selected migration plan; implementation evidence, review and verification obligations |
| <a id="workflow-lisp-prompt-output-positions-implementation-plan"></a>[Workflow Lisp Prompt Output Positions Implementation Plan](plans/2026-07-26-workflow-lisp-prompt-output-positions-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-prompt-identity-diagnostics"></a>[Workflow Lisp Prompt Identity Diagnostics](design/workflow_lisp_prompt_identity_diagnostics.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-judgment-views"></a>[Workflow Lisp Judgment Views](design/workflow_lisp_judgment_views.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-judgment-views-implementation-plan"></a>[Workflow Lisp Judgment Views Implementation Plan](plans/2026-07-29-workflow-lisp-judgment-views-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-prompt-identity-diagnostics-implementation-plan"></a>[Workflow Lisp Prompt Identity Diagnostics Implementation Plan](plans/2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-language-server"></a>[Workflow Lisp Language Server](design/workflow_lisp_language_server.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-lsp-diagnostic-lifecycle-and-compile-progress"></a>[Workflow Lisp LSP Diagnostic Lifecycle And Compile Progress](design/workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-l4-diagnostic-lifecycle-and-compile-progress-implementation-plan"></a>[Workflow Lisp L4 Diagnostic Lifecycle And Compile Progress Implementation Plan](plans/2026-07-28-workflow-lisp-language-server-l4-diagnostic-lifecycle-progress-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-lsp-authored-reference-navigation"></a>[Workflow Lisp LSP Authored Reference Navigation](design/workflow_lisp_lsp_authored_reference_navigation.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-l5-authored-reference-navigation-implementation-plan"></a>[Workflow Lisp L5 Authored Reference Navigation Implementation Plan](plans/2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-language-server-setup"></a>[Workflow Lisp Language Server Setup](workflow_lisp_language_server_setup.md) | Guide or reference; prerequisites and limits at destination |
| <a id="workflow-lisp-language-server-implementation-plan"></a>[Workflow Lisp Language Server Implementation Plan](plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-language-server-l1-implementation-plan"></a>[Workflow Lisp Language Server L1 Implementation Plan](plans/2026-07-26-workflow-lisp-language-server-l1-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-language-server-l2-implementation-plan"></a>[Workflow Lisp Language Server L2 Implementation Plan](plans/2026-07-27-workflow-lisp-language-server-l2-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-language-server-l3-per-source-entry-selection-implementation-plan"></a>[Workflow Lisp Language Server L3 Per-Source Entry Selection Implementation Plan](plans/2026-07-28-workflow-lisp-language-server-l3-per-source-entry-selection-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-parametric-type-system"></a>[Workflow Lisp Parametric Type System](design/workflow_lisp_parametric_type_system.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-compile-time-parametric-specialization"></a>[Workflow Lisp Compile-Time Parametric Specialization](design/workflow_lisp_compile_time_parametric_specialization.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-structural-parametric-constraints"></a>[Workflow Lisp Structural Parametric Constraints](design/workflow_lisp_structural_parametric_constraints.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-reviewrevise-stdlib-parametric-integration"></a>[Workflow Lisp Review/Revise Stdlib Parametric Integration](design/workflow_lisp_review_revise_stdlib_parametric_integration.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-runtime-closures-boundary"></a>[Workflow Lisp Runtime Closures Boundary](design/workflow_lisp_runtime_closures_boundary.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-run-ref-confined-child-environments"></a>[Workflow Lisp Run-Ref Confined Child Environments](design/workflow_lisp_run_ref_expression_environments.md) | Component contract or target; check admitted scope |
| <a id="lisp-procref-partial-application-work-instructions"></a>[Lisp ProcRef Partial Application Work Instructions](plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-refactoring-backlog"></a>[Workflow Lisp Refactoring Backlog](plans/2026-05-23-workflow-lisp-refactoring-backlog.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-refactoring-and-retirement-plan-set"></a>[Workflow Lisp Refactoring And Retirement Plan Set](plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md) | Plan or decision record; check current selection |
| <a id="workflow-lisp-key-migration-parity-architecture"></a>[Workflow Lisp Key Migration Parity Architecture](design/workflow_lisp_key_migration_parity_architecture.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-runtime-migration-foundation"></a>[Workflow Lisp Runtime Migration Foundation](design/workflow_lisp_runtime_migration_foundation.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-post-foundation-composition-and-stdlib-migration"></a>[Workflow Lisp Post-Foundation Composition And Stdlib Migration](design/workflow_lisp_post_foundation_composition_stdlib_migration.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-generic-core-expression-surface-and-adapter-retirement"></a>[Workflow Lisp Generic Core, Expression Surface, And Adapter Retirement](design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-private-runtime-state-and-consumer-value-flow"></a>[Workflow Lisp Private Runtime State And Consumer Value Flow](design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-runtime-native-drain-authoring"></a>[Workflow Lisp Runtime-Native Drain Authoring](design/workflow_lisp_runtime_native_drain_authoring.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-shared-owner-lane-prerequisites"></a>[Workflow Lisp Shared Owner-Lane Prerequisites](design/workflow_lisp_shared_owner_lane_prerequisites.md) | Component contract or target; check admitted scope |
| <a id="workflow-lisp-consumer-side-rendering"></a>[Workflow Lisp Consumer-Side Rendering](design/workflow_lisp_consumer_side_rendering.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-lexical-execution-checkpoints"></a>[Workflow Lisp Lexical Execution Checkpoints](design/workflow_lisp_lexical_execution_checkpoints.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-core-calculus-and-compiler-middle-end"></a>[Workflow Lisp Core Calculus And Compiler Middle-End](design/workflow_lisp_core_calculus_middle_end.md) | Component contract or target; check admitted scope |
| <a id="lisp-migrate-key-workflows-execution-plan"></a>[Lisp Migrate Key Workflows Execution Plan](plans/2026-05-29-lisp-migrate-key-workflows-execution-plan.md) | Plan or decision record; check current selection |
| <a id="lisp-migrate-key-workflows-execution-summary"></a>[Lisp Migrate Key Workflows Execution Summary](plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md) | Plan or decision record; check current selection |
| <a id="dashboard-observability-summary-gui"></a>[Dashboard Observability Summary GUI](design/dashboard_observability_summary_gui.md) | Component contract or target; check admitted scope |
| <a id="dsl-v214-variant-surface-decision"></a>[DSL v2.14 Variant Surface Decision](design/dsl_v214_variant_surface_decision.md) | Historical design; current owner linked at destination |
| <a id="dsl-v214-materialization-and-variant-draft"></a>[DSL v2.14 Materialization And Variant Draft](design/dsl_v214_materialization_variants_draft.md) | Historical design; current owner linked at destination |
| <a id="dsl-v214-pointer-authority"></a>[DSL v2.14 Pointer Authority](design/dsl_v214_pointer_authority.md) | Historical design; current owner linked at destination |
| <a id="dsl-v214-yaml-ergonomics-and-loc-reduction"></a>[DSL v2.14 YAML Ergonomics And LOC Reduction](design/dsl_v214_yaml_ergonomics.md) | Historical design; current owner linked at destination |
| <a id="minimal-neurips-v214-behavior-matrix"></a>[Minimal NeurIPS v2.14 Behavior Matrix](design/neurips_v214_behavior_matrix.md) | Historical design; current owner linked at destination |
| <a id="workflow-lisp-g6-verification-gate"></a>[Workflow Lisp G6 Verification Gate](workflow_lisp_g6_verification_gate.json) | Scoped machine-readable registry or verification input |
| <a id="slide-decks"></a>[Slide Decks](slides/README.md) | Historical presentation |
| <a id="master-spec"></a>[Master Spec](../specs/index.md) | Normative contract within its stated profile/version scope |
| <a id="orchestration-start-here-1"></a>[Orchestration Start Here](orchestration_start_here.md) | Guide or reference; prerequisites and limits at destination |
| <a id="runtime-execution-lifecycle-1"></a>[Runtime Execution Lifecycle](runtime_execution_lifecycle.md) | Guide or reference; prerequisites and limits at destination |
| <a id="workflow-drafting-guide-1"></a>[Workflow Drafting Guide](workflow_drafting_guide.md) | Historical YAML interpretation; current authoring uses the Lisp or Python guide |
| <a id="local-workflow-steering-1"></a>[Local Workflow Steering](steering.md) | Optional local input; empty content selects no work |
| <a id="master-spec-index"></a>[Master Spec Index](../specs/index.md) | Normative contract within its stated profile/version scope |
| <a id="workflow-dsl-and-control-flow"></a>[Workflow DSL and Control Flow](../specs/dsl.md) | Normative contract within its stated profile/version scope |
| <a id="variable-model-and-substitution"></a>[Variable Model and Substitution](../specs/variables.md) | Normative contract within its stated profile/version scope |
| <a id="dependencies-and-injection"></a>[Dependencies and Injection](../specs/dependencies.md) | Normative contract within its stated profile/version scope |
| <a id="providers-and-prompt-delivery"></a>[Providers and Prompt Delivery](../specs/providers.md) | Normative contract within its stated profile/version scope |
| <a id="step-io-and-output-capture"></a>[Step IO and Output Capture](../specs/io.md) | Normative contract within its stated profile/version scope |
| <a id="run-identity-and-state"></a>[Run Identity and State](../specs/state.md) | Normative contract within its stated profile/version scope |
| <a id="queues-and-wait-for"></a>[Queues and Wait-For](../specs/queue.md) | Normative contract within its stated profile/version scope |
| <a id="cli-contract"></a>[CLI Contract](../specs/cli.md) | Normative contract within its stated profile/version scope |
| <a id="observability-and-status-json"></a>[Observability and Status JSON](../specs/observability.md) | Normative contract within its stated profile/version scope |
| <a id="security-and-path-safety"></a>[Security and Path Safety](../specs/security.md) | Normative contract within its stated profile/version scope |
| <a id="versioning-and-migration"></a>[Versioning and Migration](../specs/versioning.md) | Normative contract within its stated profile/version scope |
| <a id="acceptance-tests"></a>[Acceptance Tests](../specs/acceptance/index.md) | Normative contract within its stated profile/version scope |
| <a id="prompt-management-and-qa-patterns"></a>[Prompt Management and QA Patterns](../specs/examples/patterns.md) | Historical YAML example; not runnable guidance |
| <a id="file-dependencies-example"></a>[File Dependencies Example](../specs/examples/file-dependencies.md) | Historical YAML example; not runnable guidance |
| <a id="injection-modes-example"></a>[Injection Modes Example](../specs/examples/injection-modes.md) | Historical YAML example; not runnable guidance |
| <a id="multi-agent-inbox-example"></a>[Multi-Agent Inbox Example](../specs/examples/multi-agent-inbox.md) | Historical YAML example; not runnable guidance |
| <a id="debugging-example"></a>[Debugging Example](../specs/examples/debugging.md) | Historical YAML example; not runnable guidance |
| <a id="workflow-index"></a>[Workflow Index](../workflows/README.md) | Workflow catalog/source; check registry and executable admission |
| <a id="generic-run-watchdog-historical-source"></a>[Generic Run Watchdog Historical Source](../workflows/library/generic_run_watchdog/watchdog.orc) | Workflow catalog/source; check registry and executable admission |
| <a id="workflow-examples-directory"></a>[Workflow Examples Directory](../workflows/examples/) | Workflow catalog/source; check registry and executable admission |
| <a id="augustoctober-durable-documentation-consistency-pass"></a>[August–October Durable Documentation Consistency Pass](plans/2026-10-01-durable-documentation-consistency-pass.md) | Plan or decision record; check current selection |
| <a id="project-consistency-quality-pass--2026-09-08"></a>[Project Consistency Quality Pass — 2026-09-08](reports/2026-09-08-project-consistency-quality-pass.md) | Captured evidence; not a behavioral contract |
| <a id="e2e-testing-guide"></a>[E2E Testing Guide](../tests/README.md) | Guide or reference; prerequisites and limits at destination |
| <a id="acceptance-criteria"></a>[Acceptance Criteria](../specs/acceptance/index.md) | Normative contract within its stated profile/version scope |
| <a id="active-backlog-items"></a>[Active Backlog Items](backlog/active/) | Proposal inventory; directory name does not select work |
| <a id="plans-and-adr-style-notes"></a>[Plans and ADR-Style Notes](plans/) | Plan or decision record; check current selection |
| <a id="adjudicated-provider-step-design"></a>[Adjudicated Provider Step Design](plans/2026-04-20-adjudicated-provider-step-design.md) | Plan or decision record; check current selection |
| <a id="adjudicated-provider-step-implementation-plan"></a>[Adjudicated Provider Step Implementation Plan](plans/2026-04-20-adjudicated-provider-step-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="major-project-implementation-escalation-ladder-design"></a>[Major-Project Implementation Escalation Ladder Design](plans/2026-04-26-major-project-implementation-escalation-ladder-design.md) | Plan or decision record; check current selection |
| <a id="major-project-implementation-escalation-ladder-implementation-plan"></a>[Major-Project Implementation Escalation Ladder Implementation Plan](plans/2026-04-26-major-project-implementation-escalation-ladder-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="major-project-escalation-ladder-routing-revision-plan"></a>[Major-Project Escalation Ladder Routing Revision Plan](plans/2026-04-26-major-project-escalation-ladder-routing-revision-plan.md) | Plan or decision record; check current selection |
| <a id="repeat-until-exhaustion-escalation-implementation-plan"></a>[Repeat-Until Exhaustion Escalation Implementation Plan](plans/2026-04-27-repeat-until-exhaustion-escalation-design-implementation-plan.md) | Plan or decision record; check current selection |
| <a id="roadmap-revision-soft-review-implementation-plan"></a>[Roadmap Revision Soft Review Implementation Plan](plans/2026-04-27-roadmap-revision-soft-review-implementation-plan.md) | Plan or decision record; check current selection |

<a id="informative-spec-examples-specsexamples"></a>
<a id="backlog-and-design-history"></a>

## Historical Records

[Reports](reports/), [closed plans and decision records](plans/),
[extracted design history](reports/documentation-history/), the
[historical YAML guide](workflow_drafting_guide.md), [YAML estate](workflow_yaml_estate_triage.md)
and [orientation map](../MIND_MAP.md) preserve provenance. Their captured
commands, status and results do not override current contracts or select work.
Frozen inputs, fixture documents and generated run evidence remain unchanged.
