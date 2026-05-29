# Agent-Orchestration Documentation Hub

This index provides a comprehensive map of the repo documentation so you can quickly find the right contract, guide, or example.

Normative behavior lives in `specs/`.  
Informative guidance and mental models live in `docs/`.

## Clarifications ⚠️

These are the highest-impact terminology and contract confusions.

| Topic | Common Confusion | Correct Model | Reference |
| --- | --- | --- | --- |
| `depends_on` vs `consumes` | "They are redundant." | `depends_on` declares file dependencies and optional prompt injection; `consumes` is v1.2+ artifact producer/consumer lineage with typed preflight/freshness semantics. | [Dependencies](../specs/dependencies.md), [DSL](../specs/dsl.md) |
| Queue lifecycle | "Orchestrator auto-moves queue items." | Queue item movement is workflow-authored; orchestrator does not auto-move individual task files. | [Queues and Wait-For](../specs/queue.md) |
| Orchestration vs DSL | "DSL is the entire system." | DSL is the authored contract language; orchestration is DSL + runtime + queue conventions + operations policy. | [Orchestration Start Here](orchestration_start_here.md) |
| Rollback/checkpoint workflow safety | "Every workflow needs the same live-checkout git rules." | Only workflows with DSL-level git rollback/checkpoint behavior need special coexistence rules; author them explicitly, prefer recorded refs over ancestry shortcuts like `HEAD^`, and consider a dedicated run checkout. | [Orchestration Start Here](orchestration_start_here.md), [Workflow Drafting Guide](workflow_drafting_guide.md) |
| Docs vs specs precedence | "Any docs page is authoritative." | `specs/` are normative. `docs/` are explanatory. | [Master Spec](../specs/index.md) |
| Workflow authoring surfaces | "Workflow inputs, prompt files, dependencies, and artifacts are all the same kind of input." | Keep four surfaces separate: workflow boundary (`inputs`/`outputs`), runtime dependencies (`depends_on`/`consumes`), provider prompt sources (`input_file`/`asset_file`/`asset_depends_on`), and artifact storage or lineage (`artifacts`, `expected_outputs`, `output_bundle`, `publishes`). | [Workflow Drafting Guide](workflow_drafting_guide.md), [DSL](../specs/dsl.md), [Providers](../specs/providers.md) |
| Semantic authority | "Reports, pointer files, debug YAML, and typed state can all decide workflow meaning." | Structured state, artifact values, contracts, snapshots, and semantic IR are authority. Reports, pointer files, rendered plans, and debug YAML are views or representations unless a specific contract says otherwise. | [Workflow Language Design Principles](design/workflow_language_design_principles.md), [Workflow Drafting Guide](workflow_drafting_guide.md) |
| Inline command glue | "Python and shell commands should either be banned entirely or accepted as normal workflow authoring." | Command steps are allowed for external tools and certified adapters. Hidden workflow semantics in inline Python/shell, ad hoc JSON rewrites, pointer-as-state, or report parsing are migration debt and need typed procedures, certified command adapters, or runtime-native effects. | [Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md), [Workflow Drafting Guide](workflow_drafting_guide.md) |
| Adjudicated provider output | "The best candidate's stdout becomes the step output." | `adjudicated_provider` scores output-valid candidates, promotes only declared deterministic outputs, and suppresses candidate/evaluator stdout from normal step output state. | [Workflow Drafting Guide](workflow_drafting_guide.md), [DSL](../specs/dsl.md), [Step IO](../specs/io.md) |
| Managed provider jobs | "Managed training jobs should be encoded as manual guard and recovery command steps." | `managed_jobs` is a v2.13 provider-step modifier. Workflow YAML declares policy, watch roots, backend, poll budget, and managed outcome routes; runtime-owned guard, shim, audit, recovery, and resumable state replace hand-authored recovery glue. | [Workflow Drafting Guide](workflow_drafting_guide.md), [DSL](../specs/dsl.md), [Providers](../specs/providers.md), [Managed Provider Jobs Demo](../workflows/examples/managed_provider_jobs_demo.yaml) |

---

## Quick Start

### [README](../README.md) - Project Overview
**Description:** High-level project entrypoint with setup, CLI quickstart, version snapshot, and common commands.  
**Keywords:** setup, install, quickstart, cli  
**Use this when:** You are onboarding or need to run the orchestrator quickly.

### [Orchestration Start Here](orchestration_start_here.md)
**Description:** Conceptual foundation for the system and glossary of orchestration/workflow/runtime terminology, with a relationship diagram and a reminder that live-checkout git-safety rules are repo-local policy only for workflows with DSL-level git rollback/checkpoint behavior.
**Keywords:** concepts, glossary, orchestration, dsl, runtime, git
**Use this when:** You need a clean mental model before authoring workflows or debugging behavior.

### [Runtime Execution Lifecycle](runtime_execution_lifecycle.md)
**Description:** Step-by-step runtime timeline from workflow load/validation through step execution, contract enforcement, and termination.  
**Keywords:** runtime, execution, state, lifecycle, control-flow  
**Use this when:** You need to understand what the engine actually does during `run`/`resume`.

### [Workflow Monitoring](workflow_monitoring.md)
**Description:** Operational runbook for `orchestrator monitor`, including multi-workspace email notification setup, headless SMTP configuration, dry-run checks, and interpreting completed, failed, crashed, or stalled workflow emails.  
**Keywords:** monitor, email, notifications, headless, stalled, crashed  
**Use this when:** You want email alerts for workflow completion or failures across one or more repositories.

### [Workflow Drafting Guide](workflow_drafting_guide.md)
**Description:** Authoring guidance for writing robust workflows, including prompt/runtime/flow contract separation, deterministic handoff patterns, managed-provider job conventions, and special-case guidance for workflows with DSL-level git rollback/checkpoint behavior.
**Keywords:** authoring, prompts, contracts, deterministic-handoff, managed-jobs, gates, git
**Use this when:** You are writing or refactoring workflow YAML and prompt patterns.

### [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md)
**Description:** Lisp-first authoring guidance for `.orc` workflows, focused on typed procedures, structured results, semantic authority, and avoiding YAML-shaped Lisp.
**Keywords:** lisp-frontend, orc, workflow-authoring, typed-results, structured-state
**Use this when:** Drafting or reviewing high-level Workflow Lisp workflows, or migrating YAML workflows toward `.orc`.

### [Work Definition Model](work_definition_model.md)
**Description:** Plain model separating semantic invariants, procedural work instructions, bounded work items, workflow mechanics, and run evidence.
**Keywords:** work-definition, semantics, work-instructions, workflow-mechanics, evidence
**Use this when:** Deciding whether content belongs in specs/design docs, body-of-work instructions, work items, workflow YAML, or run artifacts.

### [Workflow Lisp Autonomous Drain Work Instructions](plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md)
**Description:** Procedural prescriptions for the active Workflow Lisp autonomous drain body of work, including objective, source material, work order, constraints, documentation expectations, completion target, and out-of-scope boundaries.
**Keywords:** lisp-frontend, autonomous-drain, work-instructions, full-design, procedural-prescriptions
**Use this when:** Preparing or reviewing Workflow Lisp drain work that needs the upfront procedure separated from semantic specs and workflow mechanics.

### [Local Workflow Steering](steering.md)
**Description:** Local steering constraints for the DSL v2.14 materialization and variant-output backlog drain, including the released v2.14 runtime surface and current Phase 2 workflow-translation gate.
**Keywords:** steering, backlog-drain, dsl-v214, roadmap-gate
**Use this when:** Launching or reviewing the local NeurIPS-style workflow for DSL v2.14 materialization and variants.

### [Prompt Index](../prompts/README.md)
**Description:** Curated catalog of canonical prompt files, with recent workflow prompt families and superseded near-duplicates called out explicitly.
**Keywords:** prompts, catalog, canonical, review, plan, implementation
**Use this when:** You want to reuse or adapt an existing prompt instead of inventing one from scratch.

### [Design Template](templates/design_template.md)
**Description:** General design-document template for behavior changes, architecture decisions, migrations, operational designs, and boundary/spec clarifications.
**Keywords:** design, template, architecture, contracts, invariants, verification, migration
**Use this when:** Drafting or reviewing a design that needs explicit authority, contracts, dependencies, failure modes, usage/integration checks, documentation impact, and implementation handoff.

### [Workflow Language Design Principles](design/workflow_language_design_principles.md)
**Description:** Cross-frontend design principles for semantic authority, typed transitions, report/pointer boundaries, validation-before-commit, variant proof, effects, source maps, and future frontend requirements.
**Keywords:** workflow-language, semantics, authority, typed-transitions, frontend, lisp, ir
**Use this when:** Deciding whether a DSL feature, Lisp frontend form, macro, or workflow abstraction strengthens core semantics or merely shortens brittle authoring syntax.

### [Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md)
**Description:** Design guidance for separating legitimate command steps and certified command adapters from hidden semantic inline Python/shell glue.
**Keywords:** command-adapter, inline-glue, workflow-language, semantic-authority, adapters, lints
**Use this when:** Auditing workflow command steps, extracting inline Python or shell, deciding whether a script should be a certified adapter, or planning runtime-native promotion.

### [Workflow Lisp MVP Comparison](workflow_lisp_mvp_comparison.md)
**Description:** README-style side-by-side comparison of the Workflow Lisp MVP `.orc` implementation-attempt slice against the equivalent v2.14 YAML slice, focused on whether the frontend removes real brittleness.
**Keywords:** lisp-frontend, mvp, comparison, yaml, orc, readability
**Use this when:** You want the quickest concrete answer to whether the Lisp frontend is an actual authoring improvement.

### [Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md)
**Description:** Accepted baseline and umbrella contract for a typed procedural Lisp frontend that lowers to shared core workflow AST, validation, semantic IR, executable IR, and the existing runtime rather than YAML text.
**Keywords:** lisp-frontend, workflow-language, core-ast, semantic-ir, macros, defworkflow
**Use this when:** Reviewing the parent Workflow Lisp language contract or checking whether a scoped frontend delta preserves the baseline design.

### [Workflow Lisp Frontend MVP Specification](design/workflow_lisp_frontend_mvp_specification.md)
**Description:** Narrow MVP tranche for proving the Lisp frontend with typed records/unions, `provider-result`, `command-result`, `match`, source-span diagnostics, and one real v2.14 phase translation before adding user macros or the full procedural library.
**Keywords:** lisp-frontend, mvp, workflow-language, core-ast, typed-unions, match
**Use this when:** Planning the first implementable Lisp frontend tranche or deciding which parts of the full frontend specification are intentionally deferred.

### [Workflow Lisp Procedure References And Partial Application](design/workflow_lisp_proc_refs_partial_application.md)
**Description:** Accepted design delta and active implementation target for compile-time `ProcRef` and `bind-proc` partial application without runtime procedure values.
**Keywords:** lisp-frontend, procref, defproc, partial-application, higher-order
**Use this when:** Implementing, reviewing, or planning the focused ProcRef / partial-application extension to the Workflow Lisp frontend.

### [Workflow Lisp Local ProcRef Bindings](design/workflow_lisp_let_proc_local_proc_refs.md)
**Description:** Proposed follow-on design delta for `let-proc`, a compile-time lexical procedure-binding form that closure-converts to generated `defproc` plus existing `ProcRef` semantics.
**Keywords:** lisp-frontend, let-proc, procref, lexical-procedure, compile-time
**Use this when:** Reviewing local procedure authoring ergonomics without runtime closures or a second lowering path.

### [Workflow Lisp Runtime Closures Boundary](design/workflow_lisp_runtime_closures_boundary.md)
**Description:** Deferred runtime-semantics boundary for principled closures, including sealed closure families, checked dynamic invocation, typed captures, capabilities, source maps, and replay/resume constraints.
**Keywords:** lisp-frontend, closures, runtime-callable, executable-ir, replay, resume
**Use this when:** Evaluating future runtime closure pressure without weakening `ProcRef` or `let-proc`.

### [Lisp ProcRef Partial Application Work Instructions](plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md)
**Description:** Procedural instructions for the focused ProcRef / `bind-proc` implementation tranche, separating the active delta target from the parent frontend baseline.
**Keywords:** lisp-frontend, procref, work-instructions, proc-ref-drain, procedural-prescriptions
**Use this when:** Launching or reviewing the focused ProcRef drain workflow.

### [Workflow Lisp Refactoring Backlog](plans/2026-05-23-workflow-lisp-refactoring-backlog.md)
**Description:** Refactoring backlog for reducing maintenance cost in `orchestrator/workflow_lisp/` while preserving the current compiler architecture, diagnostics, provenance, type safety, effect visibility, and lowering behavior.
**Keywords:** lisp-frontend, refactoring, compiler, typecheck, lowering, diagnostics
**Use this when:** Planning cleanup of the Workflow Lisp frontend implementation without mixing it with missing full-design feature work.

### [Dashboard Observability Summary GUI](design/dashboard_observability_summary_gui.md)
**Description:** Design note for the dashboard summary-hub page that renders provider/phase summaries from `RUN_ROOT/summaries/index.json` and links detailed call-frame summaries through safe run-file routes.
**Keywords:** dashboard, observability, summaries, gui, summary-hub
**Use this when:** Reviewing or extending the read-only GUI for generated workflow summaries.

### [DSL v2.14 Variant Surface Decision](design/dsl_v214_variant_surface_decision.md)
**Description:** Durable Phase 1 design note selecting `variant_output` over an `output_bundle.variants` extension for tagged-union output validation while keeping `select_variant_output` separate.
**Keywords:** dsl-v214, variant-output, output-bundle, tagged-union, decision
**Use this when:** You need the authoritative contract-surface decision before Phase 1 runtime implementation or doc alignment.

### [DSL v2.14 Materialization And Variant Draft](design/dsl_v214_materialization_variants_draft.md)
**Description:** Phase 0 reference that inventories the legacy materialization and tagged-union patterns frozen before the public v2.14 runtime release.
**Keywords:** dsl-v214, phase-0, materialization, variant-output, oracle
**Use this when:** You need the current-behavior characterization that future v2.14 implementation work is meant to preserve or intentionally replace.

### [DSL v2.14 Pointer Authority](design/dsl_v214_pointer_authority.md)
**Description:** Phase 1 design note that inventories current pointer surfaces and fixes one authority rule for published relpath artifacts versus compatibility-only pointer shims.
**Keywords:** dsl-v214, pointer-authority, relpath, publishes, compatibility
**Use this when:** You need the authoritative pointer model before Phase 1 runtime implementation or workflow migration decisions.

### [DSL v2.14 YAML Ergonomics And LOC Reduction](design/dsl_v214_yaml_ergonomics.md)
**Description:** Phase 2 follow-up design note for making v2.14 workflows shorter than the legacy stack by keeping JSON bundles native, adding shared variant fields, adding batch materialization, and enforcing LOC regression checks.
**Keywords:** dsl-v214, yaml-ergonomics, loc, variant-output, materialize-artifacts
**Use this when:** Reviewing why the first v2.14 workflow translation increased YAML size or planning the compact v2.14 authoring correction.

### [Minimal NeurIPS v2.14 Behavior Matrix](design/neurips_v214_behavior_matrix.md)
**Description:** Scenario matrix for the primitive and minimal-NeurIPS Phase 0 oracle fixtures, including preserved observations and normalized-away volatile fields.
**Keywords:** neurips, oracle, behavior-matrix, phase-0, fixtures
**Use this when:** Reviewing what the new oracle suites are expected to lock down.

### [Workflow Prompt Map](workflow_prompt_map.md)
**Description:** Exhaustive generated map of workflow provider prompt sources, including `input_file`, `asset_file`, and `asset_depends_on` resolution and missing-file status.  
**Keywords:** workflows, prompts, input_file, asset_file, prompt-assets  
**Use this when:** You need to find which prompt files a workflow step uses or audit missing/stale prompt references.

### [Slide Decks](slides/README.md)
**Description:** Source-controlled teaching slides for workflow and DSL concepts, including the Ralph workflow YAML semantics and prompt-injection example.
**Keywords:** slides, teaching, yaml, prompt-injection, ralph
**Use this when:** You want a short presentation-style explanation of a workflow concept.

### [Master Spec](../specs/index.md)
**Description:** Normative root of the external contract, including module map, versioning boundaries, and acceptance scope.  
**Keywords:** normative, contract, spec, versioning, conformance  
**Use this when:** You need authoritative behavior definitions.

## Workflow Author Fast Path

If your immediate goal is to write or revise a workflow, use this read order:

1. [Workflow Drafting Guide](workflow_drafting_guide.md)
   Why: start with authoring conventions, handoff patterns, and the prompt/runtime/flow contract split so you do not write syntactically valid but operationally weak workflows.

2. [Workflow DSL and Control Flow](../specs/dsl.md)
   Why: this is the authoritative schema and control-flow contract for top-level keys, step fields, version gates, `for_each`, `consumes`, `publishes`, and routing.

3. [Variable Model and Substitution](../specs/variables.md), [Dependencies and Injection](../specs/dependencies.md), and [Providers and Prompt Delivery](../specs/providers.md)
   Why: these three specs cover the authoring details that most often cause broken workflows: substitution rules, dependency injection behavior, and what providers actually receive.

4. [Prompt Index](../prompts/README.md), [Workflow Index](../workflows/README.md), [Workflow Prompt Map](workflow_prompt_map.md), plus one or two runnable examples under [workflows/examples/](../workflows/examples/)
   Why: use the prompt catalog, exhaustive prompt map, and workflow examples to copy the current house style for review prompts, loop contracts, gates, artifact contracts, and prompt layout instead of inventing patterns from scratch.

Minimum rule of thumb: if you have only read `docs/index.md`, you can find the docs; if you have read the four items above, you can usually write an effective workflow without extra repo archaeology.

For new DSL surfaces, macro systems, frontend languages, or reusable workflow
families, also read [Workflow Language Design Principles](design/workflow_language_design_principles.md)
before drafting the feature. It defines the semantic authority model that keeps
new authoring surfaces from becoming shorter versions of brittle YAML.

If the workflow uses inline Python/shell or helper scripts for state, routing,
resource movement, provider-output normalization, or report parsing, also read
[Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md)
before adding or preserving the command boundary.

## Informative Guides (`docs/`)

### [Orchestration Start Here](orchestration_start_here.md)
**Description:** Concept model with terms and boundaries between authoring-time decisions and runtime semantics.  
**Keywords:** terminology, model, boundaries, authoring, runtime  
**Use this when:** Clarifying how queue/policy/runbook/workflow/DSL/step terms relate.

### [Runtime Execution Lifecycle](runtime_execution_lifecycle.md)
**Description:** Runtime sequence details for `when`, preflight, execution, output validation, publish/consume updates, and next-step resolution.  
**Keywords:** runtime-order, step-state, retries, timeout, consume-publish  
**Use this when:** Diagnosing run behavior and state transitions.

### [Workflow Drafting Guide](workflow_drafting_guide.md)
**Description:** Workflow authoring patterns focused on deterministic handoff and high-signal control-flow gates.  
**Keywords:** drafting, dsl-authoring, output-contracts, loop-patterns  
**Use this when:** Designing new loops (execute/review/fix), gates, and prompt contracts.

### [Local Workflow Steering](steering.md)
**Description:** Current local steering for the DSL v2.14 backlog-drain run, including selectable and deferred roadmap phases.  
**Keywords:** steering, local-run, roadmap-gate, dsl-v214  
**Use this when:** Running or auditing the local NeurIPS-style backlog workflow.

## Normative Spec Modules (`specs/`)

### [Master Spec Index](../specs/index.md)
**Description:** Entrypoint and authoritative map of all normative modules.  
**Keywords:** master-spec, scope, map, precedence  
**Use this when:** Navigating specs or confirming precedence rules.

### [Workflow DSL and Control Flow](../specs/dsl.md)
**Description:** Full workflow schema and control-flow semantics, including version-gated fields and mutual exclusivity rules.  
**Keywords:** dsl, schema, steps, goto, for_each, artifacts  
**Use this when:** Authoring workflow YAML or validating field-level behavior.

### [Variable Model and Substitution](../specs/variables.md)
**Description:** Variable namespaces, substitution locations, escapes, and undefined-variable failure semantics.  
**Keywords:** variables, substitution, namespaces, escaping  
**Use this when:** Debugging unexpected path/command/provider substitutions.

### [Dependencies and Injection](../specs/dependencies.md)
**Description:** `depends_on` dependency resolution plus v1.1.1 injection semantics, ordering, and truncation behavior.  
**Keywords:** depends_on, injection, required, optional, glob  
**Use this when:** Defining file prerequisites or prompt dependency injection behavior.

### [Providers and Prompt Delivery](../specs/providers.md)
**Description:** Provider template contracts, prompt composition order, placeholder substitution, and provider runtime semantics.  
**Keywords:** providers, prompt-composition, argv, stdin, placeholders, managed-jobs
**Use this when:** Creating provider templates or debugging what providers actually receive.

### [Step IO and Output Capture](../specs/io.md)
**Description:** Capture modes (`text|lines|json`), limits, tee behavior, and deterministic output contract enforcement behavior.  
**Keywords:** output-capture, stdout, json, expected_outputs, output_bundle  
**Use this when:** Choosing step output strictness and debugging capture/parse failures.

### [Run Identity and State](../specs/state.md)
**Description:** `run_id`, `state.json` schema, step status model, and artifact lineage state fields.  
**Keywords:** state-json, run-id, schema, artifact_versions  
**Use this when:** Interpreting run state, resume behavior, or state integrity logic.

### [Queues and Wait-For](../specs/queue.md)
**Description:** Queue directory conventions and `wait_for` behavior, including timeout and polling state fields.  
**Keywords:** queue, wait_for, inbox, processed, failed  
**Use this when:** Authoring filesystem queue flows and blocking wait steps.

### [CLI Contract](../specs/cli.md)
**Description:** Normative commands, flags, safety constraints, and runtime observability CLI controls.  
**Keywords:** cli, run, resume, report, safety, flags  
**Use this when:** Implementing or validating CLI behavior and operational commands.

### [Observability and Status JSON](../specs/observability.md)
**Description:** Debug logging expectations, prompt audit behavior, error context shape, and status JSON conventions.  
**Keywords:** observability, debug, logging, status-json, prompt-audit  
**Use this when:** Adding diagnostics or interpreting runtime visibility artifacts.

### [Security and Path Safety](../specs/security.md)
**Description:** Path safety rules, secret handling, masking guarantees, and environment precedence semantics.  
**Keywords:** security, secrets, masking, path-safety, workspace  
**Use this when:** Reviewing security boundaries and safe path handling.

### [Versioning and Migration](../specs/versioning.md)
**Description:** DSL evolution from v1.1 through current v2.x gates, migration guidance, and planned feature gating notes.
**Keywords:** versioning, migration, v2.13, managed-jobs, provider-session, adjudicated-provider
**Use this when:** Migrating workflows between DSL versions.

### [Acceptance Tests](../specs/acceptance/index.md)
**Description:** Normative acceptance criteria and conformance checklist across all spec modules.  
**Keywords:** acceptance, conformance, validation, test-matrix  
**Use this when:** Verifying implementation correctness against spec obligations.

## Informative Spec Examples (`specs/examples/`)

### [Prompt Management and QA Patterns](../specs/examples/patterns.md)
**Description:** Reusable authoring patterns for prompts, queue coordination, and deterministic QA gating.  
**Keywords:** patterns, prompt-management, qa-gating, workflows  
**Use this when:** Looking for practical multi-step workflow patterns.

### [File Dependencies Example](../specs/examples/file-dependencies.md)
**Description:** Example workflow showing dependency resolution patterns with variables and loops.  
**Keywords:** dependencies, loops, variables, required-optional  
**Use this when:** Building workflows with dynamic file prerequisites.

### [Injection Modes Example](../specs/examples/injection-modes.md)
**Description:** Side-by-side examples of `inject: true`, `list`, `content`, `append`, and no-injection modes.  
**Keywords:** injection, list-mode, content-mode, prompt-assembly  
**Use this when:** Selecting an injection mode for provider steps.

### [Multi-Agent Inbox Example](../specs/examples/multi-agent-inbox.md)
**Description:** End-to-end queue-oriented coordination flow using inbox tasks, loops, and provider steps.  
**Keywords:** multi-agent, inbox, for_each, queue-lifecycle  
**Use this when:** Designing agent queue workflows with explicit task movement.

### [Debugging Example](../specs/examples/debugging.md)
**Description:** Minimal example for diagnosing failed runs via logs and `state.json`.  
**Keywords:** debugging, failures, logs, resume  
**Use this when:** Building quick failure-diagnosis workflow snippets.

## Workflow Runbooks and Examples

### [Workflow Index](../workflows/README.md)
**Description:** Catalog of workflows under `workflows/`, with short purpose summaries and quick pointers for choosing an example.
**Keywords:** workflows, catalog, index, examples, runbooks, managed-jobs
**Use this when:** You need to find the right workflow file before reading or running it.

### [Generic Run Watchdog](../workflows/examples/generic_run_watchdog.yaml)
**Description:** v2.14 reusable watchdog that probes any orchestrator run by `run_id`, emits generic evidence for running/completed/failed/stalled states, and invokes a repair provider only when recovery is needed.
**Keywords:** workflows, watchdog, run-monitoring, repair, resume, v2.14
**Use this when:** You need a scheduled check that can diagnose a crashed, failed, or stalled workflow run and drive a principled repair plus resume/relaunch action.

### [Lisp Frontend Autonomous Drain](../workflows/examples/lisp_frontend_autonomous_drain.yaml)
**Description:** v2.14 local drain for Lisp frontend MVP/full-design work. The selector can choose an active backlog item or identify an unimplemented design gap, draft an implementation architecture, and route the normalized work item through the plan/implementation stack without roadmap phase gating.
**Keywords:** workflows, lisp-frontend, autonomous-drain, design-gap, backlog, v2.14
**Use this when:** Running Lisp frontend implementation work from either explicit backlog items or design gaps discovered from the frontend specifications.

### [Lisp Frontend ProcRef Delta Drain](../workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml)
**Description:** Focused successor drain for the ProcRef / `bind-proc` delta. It uses the ProcRef design as the active target, passes the completed frontend specification as baseline context, and writes to a separate ProcRef state/plan namespace.
**Keywords:** workflows, lisp-frontend, procref, bind-proc, autonomous-drain, design-delta, v2.14
**Use this when:** Running the scoped ProcRef / partial-application implementation tranche without reopening the completed full frontend drain.

### [Managed Provider Jobs Demo](../workflows/examples/managed_provider_jobs_demo.yaml)
**Description:** Minimal v2.13 workflow showing `managed_jobs` on a provider step, a local managed training launch, runtime-owned audit/recovery state, and managed outcome routing to review/fix steps.
**Keywords:** managed-jobs, provider, v2.13, audit, recovery, shim
**Use this when:** You need a copyable starting point for provider-launched training or batch jobs that should be recovered without relaunching the provider.

### [v0 Artifact-Contract Prototype Runbook](../workflows/examples/README_v0_artifact_contract.md)
**Description:** Runbook for deterministic file-based handoff prototypes, including verification commands and known limits.  
**Keywords:** runbook, artifact-contracts, deterministic-handoff, prototype  
**Use this when:** Running or extending backlog/plan execute-review-fix prototypes.

### [Workflow Examples Directory](../workflows/examples/)
**Description:** Concrete YAML workflows covering retries, conditionals, loops, prompt auditing, capture modes, and dataflow contracts.  
**Keywords:** examples, yaml, retries, loops, dataflow  
**Use this when:** You want a working template instead of starting from a blank workflow.

### [NeurIPS Hybrid ResNet Plan/Implementation Workflow](../workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml)
**Description:** Input-required call-based workflow that loops over roadmap tranche selection from a supplied design and roadmap, then runs plan drafting/review and implementation/review for each selected tranche.
**Keywords:** workflows, call, roadmap, design, tranche-selection, plan-review, implementation-review
**Use this when:** You need a local reusable template for adaptive roadmap draining while keeping roadmap, design, selected tranche context, and progress ledger context explicit in planning provider steps.

### [PtychoPINN Backlog Plan Slice Loop (Downstream Reference)](../workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml)
**Description:** Informative snapshot of a real downstream workflow copied from `PtychoPINN/workflows/agent_orchestration/backlog_plan_slice_impl_review_loop.yaml` at source commit `370f641fdf84` (copied March 3, 2026).  
**Keywords:** downstream, ptychopinn, backlog, execute-review-loop, reference  
**Use this when:** You want a non-trivial real-world workflow example that demonstrates producer/consumer dataflow and looped review gates.

## Testing and Validation

### [E2E Testing Guide](../tests/README.md)
**Description:** Canonical testing guidance for this repo, including targeted pytest usage, collection checks for new tests, and workflow/demo smoke commands.  
**Keywords:** testing, e2e, pytest, verification, smoke-checks  
**Use this when:** Choosing verification commands for workflow, runtime, prompt, and demo changes before merge.

### [Acceptance Criteria](../specs/acceptance/index.md)
**Description:** Canonical acceptance checklist mapped to DSL/runtime/CLI/security contracts.  
**Keywords:** acceptance, normative-tests, obligations  
**Use this when:** Confirming whether a behavior change should be accepted or rejected.

## Backlog and Design History

### [Active Backlog Items](backlog/active/)
**Description:** Active backlog documents with scope/status and linked implementation plans.  
**Keywords:** backlog, active, scope, status  
**Use this when:** Checking what high-priority documentation-driven work is currently in flight.

### [Plans and ADR-Style Notes](plans/)
**Description:** Implementation plans and historical design notes used to track rationale and execution details.  
**Keywords:** plans, adr, history, rationale  
**Use this when:** You need design context behind existing behavior, not normative contracts.

### [Adjudicated Provider Step Design](plans/2026-04-20-adjudicated-provider-step-design.md)
**Description:** ADR for DSL `2.11` adjudicated provider steps, including candidate isolation, evaluator evidence, selection, ledgers, promotion, state, and resume contracts.
**Keywords:** adjudicated-provider, evaluator, candidates, promotion, score-ledger
**Use this when:** You need the design rationale behind the v2.11 adjudicated provider runtime and its V1 constraints.

### [Adjudicated Provider Step Implementation Plan](plans/2026-04-20-adjudicated-provider-step-implementation-plan.md)
**Description:** Implementation plan for the v2.11 adjudicated provider first release, covering DSL validation, isolated candidate workspaces, same-trust-boundary scoring, ledgers, transactional promotion, resume reconciliation, observability, and docs/examples.
**Keywords:** implementation-plan, adjudicated-provider, v2.11, candidates, scoring, promotion, resume
**Use this when:** You need the accepted implementation task breakdown for the adjudicated provider runtime and its verification gates.

### [Major-Project Implementation Escalation Ladder Design](plans/2026-04-26-major-project-implementation-escalation-ladder-design.md)
**Description:** Design for soft implementation-iteration escalation context, upward phase rerouting (`replan`, `redesign`, `roadmap revision`), structured escalation artifacts, and manifest supersession handling in major-project tranche stacks.
**Keywords:** implementation-review, escalation, replan, redesign, roadmap-revision, repeat-until, major-project
**Use this when:** You need the rationale and exact workflow/prompt contract for stopping long implementation churn by escalating to the right upstream phase.

### [Major-Project Implementation Escalation Ladder Implementation Plan](plans/2026-04-26-major-project-implementation-escalation-ladder-implementation-plan.md)
**Description:** Implementation plan for the major-project escalation ladder, including local phase forks, deterministic escalation-state helpers, routing changes, manifest `superseded` handling, prompt assets, and verification.
**Keywords:** implementation-plan, escalation, major-project, workflow-routing, manifest, prompts
**Use this when:** You need the task breakdown and verification checklist for the major-project escalation ladder implementation.

### [Major-Project Escalation Ladder Routing Revision Plan](plans/2026-04-26-major-project-escalation-ladder-routing-revision-plan.md)
**Description:** Revision plan for adjacent-only phase escalation and DSL-valid drain-level roadmap-revision dispatch through a reusable one-iteration workflow.
**Keywords:** implementation-plan, escalation, adjacent-routing, roadmap-revision, drain-iteration, major-project
**Use this when:** You need to revise the major-project escalation ladder so implementation routes to plan, plan routes to design, and design routes to roadmap revision without nested repeat-loop control flow.

### [Repeat-Until Exhaustion Escalation Implementation Plan](plans/2026-04-27-repeat-until-exhaustion-escalation-design-implementation-plan.md)
**Description:** Implementation plan for DSL v2.12 `repeat_until.on_exhausted.outputs`, typed pipeline support, and major-project review-loop non-convergence escalation.
**Keywords:** implementation-plan, repeat-until, v2.12, exhaustion, escalation, major-project
**Use this when:** You need deterministic routing for bounded review loops that fail to converge without treating successful loop iterations as runtime crashes.

### [Roadmap Revision Soft Review Implementation Plan](plans/2026-04-27-roadmap-revision-soft-review-implementation-plan.md)
**Description:** Implementation plan for making major-project roadmap revision review advisory when roadmap revision is the top available authority, while still recording findings and promoting finalized roadmap and manifest candidates.
**Keywords:** implementation-plan, roadmap-revision, advisory-review, major-project, tranche-drain
**Use this when:** You need the rationale and verification path for top-authority roadmap revision phases that should record review findings without blocking the updated roadmap.

## Finding Information

### By Task
- **Understand terminology and boundaries:** [Orchestration Start Here](orchestration_start_here.md)
- **Understand runtime state transitions:** [Runtime Execution Lifecycle](runtime_execution_lifecycle.md)
- **Author or refactor workflows:** [Workflow Author Fast Path](#workflow-author-fast-path)
- **Clarify `depends_on` vs `consumes`:** [Dependencies](../specs/dependencies.md) + [DSL](../specs/dsl.md) + [Versioning](../specs/versioning.md)
- **Check queue ownership and wait behavior:** [Queue Spec](../specs/queue.md)
- **Debug a failed run:** [Observability](../specs/observability.md) + [State](../specs/state.md) + [Debugging Example](../specs/examples/debugging.md)
- **Validate conformance:** [Acceptance Index](../specs/acceptance/index.md) + [tests/README](../tests/README.md)

### By Audience
- **Workflow authors:** [Workflow Author Fast Path](#workflow-author-fast-path)
- **Runtime operators:** [CLI](../specs/cli.md), [Runtime Lifecycle](runtime_execution_lifecycle.md), [Observability](../specs/observability.md)
- **Spec/contract reviewers:** [Master Spec](../specs/index.md), [Acceptance](../specs/acceptance/index.md), [Versioning](../specs/versioning.md)

---

*Last updated: April 2026*
*Style: detailed catalog with descriptions, keywords, and task-oriented navigation*
