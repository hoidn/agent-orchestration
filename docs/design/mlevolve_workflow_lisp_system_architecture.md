# MLEvolve Workflow Lisp System Architecture

Status: draft design
Kind: system architecture / workflow-library design
Created: 2026-06-09
Updated: 2026-06-09
Scope: Workflow Lisp architecture for an MLEvolve-style autonomous ML engineering search workflow, including typed orchestration, Monte Carlo Graph Search approximation, provider roles, certified adapters, state authority, and migration path from candidate sketches.

Authority:

- Normative DSL/runtime behavior lives in `specs/`.
- Workflow Lisp authoring guidance lives in `docs/lisp_workflow_drafting_guide.md`.
- Command adapter policy lives in `docs/design/workflow_command_adapter_contract.md`.
- Runtime foundation prerequisites live in `docs/design/workflow_lisp_runtime_migration_foundation.md`.
- This document is a design target and implementation architecture. It is not a normative runtime spec.
- This document does not promote any MLEvolve `.orc` workflow to production authority until compile, shared validation, dry-run or smoke, adapter fixtures, and runtime evidence pass.

Related docs:

- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/state.md`

Source candidate sketches:

- `tmp/mle/mle1/mlevolve_modular_mcgs_solution/`
- `tmp/mle/mle2/mlevolve_orc_solution_self_contained/`
- `tmp/mle/mle3/mlevolve_orc_solution/`
- `tmp/mle/mle4/mlevolve_approx_solution/`

## 1. Purpose

This document defines a recommended system architecture for implementing an MLEvolve-style autonomous ML engineering workflow in Workflow Lisp.

The design is based on review of four candidate solution sketches. The recommended path is to use candidate 4 as the practical executable base, borrow candidate 2's modular search-library structure as the long-term architecture, and defer candidate 1's more ambitious higher-order generic MCGS abstraction until compile-time procedure hooks and imported `.orc` libraries are less fragile.

The goal is not to clone upstream MLEvolve line-for-line. The goal is to express the behavior that matters for `agent-orchestration`:

- typed task/config/search state;
- provider-generated candidate code and plans;
- deterministic scheduling and queue transitions;
- sandboxed execution and validation;
- metric parsing and best-solution tracking;
- branch reuse, fusion, evolution, and aggregation;
- memory retrieval and update;
- structured terminal outcomes; and
- durable artifacts, reports, and resume-compatible state.

## 2. Executive Decision

Build the first implementation as a candidate-4-shaped Workflow Lisp workflow with certified adapters:

```text
workflows/examples/mlevolve_approx.orc
  -> typed setup / preview / coldstart / memory initialization
  -> scheduler tick
  -> provider candidate generation
  -> provider code review
  -> deterministic enqueue / execute / validate / commit adapters
  -> finalization
```

Treat the scheduler, executor, validator, memory indexer, and finalizer as certified command adapters in the first tranche. They may own deterministic algorithmic mechanics, but they must not hide workflow authority behind prose, stdout, pointer files, or unvalidated JSON.

After the concrete workflow compiles and dry-runs, split the architecture toward the candidate-2 module shape:

```text
workflows/library/search/mcgs.orc
  generic MCGS types, graph operators, and reusable search contracts

workflows/library/ml/mlevolve_types.orc
  ML task, candidate, metric, memory, execution, and result types

workflows/library/ml/mle_engineering.orc
  ML-specific provider roles and adapter calls

workflows/examples/mlevolve_approx.orc
  small entrypoint wiring task inputs, MCGS config, and ML engineering layer
```

Do not start from the fully generic ProcRef-heavy designs. They are architecturally attractive, but they depend on surfaces that are still more fragile than the direct candidate-4 shape.

## 3. Candidate Disposition

| Candidate | Use | Reason |
| --- | --- | --- |
| Candidate 1 | Inspiration for generic MCGS callbacks | Good abstraction, but too dependent on higher-order ProcRefs and mostly stub adapters. |
| Candidate 2 | Long-term module architecture | Cleanest separation of generic MCGS, ML types, ML engineering, prompts, and example entrypoint. Not runnable enough as the first base. |
| Candidate 3 | Reference only | Honest boundary notes, but monolithic, parser-broken, and less complete than candidate 4. |
| Candidate 4 | First implementation base | Closest to runnable, has concrete adapters, current-ish `.orc` shape, and explicit MLEvolve role coverage. |

The practical ranking is:

```text
candidate 4 -> candidate 2 -> candidate 1 -> candidate 3
```

The architecture ranking is:

```text
candidate 2 -> candidate 1 -> candidate 4 -> candidate 3
```

The implementation should choose practical convergence first and preserve a path to the cleaner architecture.

## 4. Problem

MLEvolve-style workflows are difficult to express safely because they mix several concerns:

- stochastic or heuristic search policy;
- provider-generated plans and code;
- benchmark execution and metric extraction;
- branch graph state and queue state;
- memory retrieval and update;
- code review and repair;
- final submission assembly; and
- long-running resumable state.

If this is implemented as ordinary Python, composition is easy locally but workflow authority becomes opaque. The runtime cannot easily see typed state transitions, provider effects, artifact lineage, branch proof, terminal outcomes, or resume boundaries.

If this is implemented as overly pure `.orc`, the workflow becomes brittle. Detailed UCT-like selection, stagnation heuristics, execution sandboxing, metric parsing, leakage checks, and filesystem mutations are better handled by certified adapters with explicit typed contracts.

The architecture must therefore split responsibilities carefully:

```text
Workflow Lisp owns orchestration authority.
Certified adapters own deterministic mechanics.
Provider steps own candidate generation and review decisions.
Runtime contracts own validation, artifacts, paths, state, and resume.
Reports remain views.
```

## 5. Goals

- Express the MLEvolve loop as typed Workflow Lisp composition, not as one Python script.
- Keep terminal workflow outcomes in typed unions.
- Keep per-step provider decisions separate from terminal workflow status.
- Represent search state, pending work, candidate nodes, metrics, memory context, and blockers as typed records/unions.
- Use provider-result steps for draft, debug, improve, evolution, fusion, aggregation, and code-review roles.
- Use certified command adapters for deterministic setup, scheduling, queue updates, execution, validation, memory indexing, and finalization.
- Keep benchmark execution and sandboxing out of provider prompts.
- Preserve artifact lineage for plans, code, execution reports, validation reports, reviews, submissions, memory context, journals, and snapshots.
- Make stdout/debug reports views; typed bundles and runtime state are authority.
- Allow an incremental path from a direct workflow to reusable MCGS library modules.

## 6. Non-Goals

- Do not vendor or reimplement upstream MLEvolve internals in this document.
- Do not require runtime closures or dynamic procedure values.
- Do not require generic ProcRef-based MCGS before the direct workflow is proven.
- Do not encode full scheduler heuristics in `.orc` control flow in the first tranche.
- Do not make Python adapters arbitrary hidden workflow programs.
- Do not parse markdown reports for semantic state.
- Do not treat generated code execution as safe without a sandbox contract.
- Do not treat compile success as production readiness.
- Do not promote this workflow to a canonical example until it has focused fixtures and at least one dry-run or smoke path.

## 7. Architecture Overview

The architecture has six lanes:

```text
authored .orc control plane
  -> typed search/domain contracts
  -> provider roles
  -> certified deterministic adapters
  -> runtime state/artifacts
  -> reports and dashboards as views
```

### 7.1 Authored Workflow Lisp Control Plane

The top-level `.orc` workflow owns visible orchestration:

1. create run workspace and initial state;
2. build dataset preview and optional coldstart guidance;
3. initialize or retrieve memory;
4. initialize search state;
5. loop for bounded steps or time;
6. ask scheduler for the next typed tick;
7. expand selected nodes or execute pending batches;
8. update typed status;
9. finalize completed, timed-out, blocked, or exhausted runs.

The control plane should be readable without understanding scheduler internals.

### 7.2 Typed Domain Contracts

The workflow should define or import typed records/unions for:

- task request and config;
- metric direction and parsed metric value;
- blocker classification;
- node references and node-set snapshots;
- run bundle, search state, journal, snapshot, queue, and memory state;
- expansion requests;
- candidate generation results;
- code review results;
- scheduler ticks;
- search loop status; and
- final outputs.

The candidate-4 type shape is a good first approximation. Candidate 2's type-module split is the preferred later organization.

### 7.3 Provider Roles

Provider roles should be explicit and typed:

| Role | Input authority | Output authority |
| --- | --- | --- |
| Draft | task, dataset, preview, coldstart, memory, mode | `CandidateGenerationResult` |
| Debug | parent node, failure report, task context, memory | `CandidateGenerationResult` |
| Improve | parent node, selection report, memory | `CandidateGenerationResult` |
| Evolve | parent node, stagnation report, memory | `CandidateGenerationResult` |
| Fuse | node set, stagnation report, memory | `CandidateGenerationResult` |
| Aggregate | top-k snapshot, source nodes, memory | `CandidateGenerationResult` |
| Code review | candidate plan/code/report, task context | `CodeReviewResult` |

Provider prompts may produce markdown reports, but those reports are views. Provider semantic output must be structured and validated.

### 7.4 Certified Deterministic Adapters

Adapters are allowed when they are stable command boundaries with typed inputs and outputs.

Initial certified adapters:

- `setup_run`: allocate workspace, root node, journal, snapshot, and run report.
- `build_data_preview`: produce preview and sample-submission report.
- `build_coldstart_guidance`: produce coldstart state.
- `init_global_memory_layer`: produce memory layer state.
- `initialize_search_state`: create journal, snapshot, pending queue, and active state.
- `scheduler_tick`: choose the next typed scheduler action.
- `choose_generation_mode`: choose planner/codegen mode.
- `retrieve_memory_context`: build memory context for provider generation.
- `enqueue_reviewed_candidate`: add accepted/revised candidates to pending execution.
- `commit_generation_blocker`: commit provider generation blockers.
- `commit_review_blocker`: commit review blockers.
- `execute_parse_validate_commit_batch`: run candidate code, parse metrics, validate outputs, update best/top-k state.
- `finalize_run`: produce terminal summary and submission bundle.

Each adapter must have:

```text
typed input signature
typed output signature
declared artifact writes
declared state writes
path-safety expectations
stable error taxonomy
fixture tests
negative tests
source-map ownership
```

### 7.5 Runtime State And Artifacts

The runtime owns validation and publication of structured output. Adapters and providers may create files, but workflow state is committed only after runtime contract validation.

Authority layers:

```text
typed .orc value
  -> executable contract
  -> structured provider/command bundle
  -> runtime validation
  -> state.json and artifact ledger
  -> reports and dashboards
```

Reports, markdown summaries, prompt traces, stdout, pointer files, and debug YAML are views unless a specific contract promotes them.

### 7.6 Search Policy

The first implementation should keep detailed search policy inside `scheduler_tick` as a certified adapter. That adapter may compute:

- initial draft fanout;
- pending execution batches;
- debug versus improve decisions;
- top-k exploitation;
- exploration decay;
- stagnation detection;
- evolution/fusion/aggregation triggers;
- branch diversity pressure; and
- timeout/completion/block routing.

The adapter returns a typed `SchedulerTick`. The workflow decides only how to route that tick.

Later, when generic MCGS library support is stable, split reusable search policy into `workflows/library/search/mcgs.orc` and keep only low-level numeric or graph-update mechanics in certified adapters.

## 8. Target Module Layout

### 8.1 First Tranche Layout

Use a direct, practical layout:

```text
workflows/examples/mlevolve_approx.orc
adapters/mlevolve/
prompts/mlevolve/
tests/workflow_lisp/examples/test_mlevolve_approx.py
```

The `.orc` module path must match the file path. For example:

```lisp
(defmodule examples/mlevolve_approx)
```

should live at:

```text
workflows/examples/mlevolve_approx.orc
```

### 8.2 Long-Term Layout

After the first workflow compiles and dry-runs:

```text
workflows/library/search/mcgs.orc
workflows/library/ml/mlevolve_types.orc
workflows/library/ml/mle_engineering.orc
workflows/library/prompts/mlevolve/
workflows/examples/mlevolve_approx.orc
adapters/mlevolve/
```

The entrypoint should shrink toward:

```lisp
(defworkflow run-mlevolve-approx ((inputs MleTaskInputs)
                                  (mle_cfg MleConfig)
                                  (mcgs_cfg McgsConfig)) -> MleSearchOutput
  ...)
```

## 9. Control Flow

The direct workflow should follow this shape:

```text
setup run
  -> build preview
  -> build coldstart
  -> initialize memory
  -> initialize search state
  -> loop/recur
       ACTIVE:
         scheduler_tick
           EXPAND_SELECTED:
             choose_generation_mode
             retrieve_memory_context
             provider generate candidate
             provider review code
             enqueue or commit blocker
           EXECUTE_PENDING_BATCH:
             execute/parse/validate/commit batch
           RUN_COMPLETE:
             done
           RUN_TIMEOUT:
             done
           RUN_BLOCKED:
             done
       COMPLETED/TIMED_OUT/BLOCKED:
         done
  -> finalize
```

The scheduler tick is a typed event, not a gate string. It must carry enough data for downstream steps to run without parsing reports.

## 10. Data Contracts

Minimum terminal status union:

```text
SearchLoopStatus =
  ACTIVE(state)
  COMPLETED(summary, best_solution, top_k_submissions, journal, memory_ledger)
  TIMED_OUT(summary, best_solution, journal, memory_ledger)
  BLOCKED(summary, blocker, journal)
```

Minimum scheduler tick union:

```text
SchedulerTick =
  EXPAND_SELECTED(request, scheduler_report)
  EXECUTE_PENDING_BATCH(queue, parallel_width, scheduler_report)
  RUN_COMPLETE(summary, best_solution, top_k_submissions, journal, memory_ledger)
  RUN_TIMEOUT(summary, best_solution, journal, memory_ledger)
  RUN_BLOCKED(summary, blocker, journal)
```

Minimum candidate generation union:

```text
CandidateGenerationResult =
  CANDIDATE_READY(candidate)
  GENERATION_BLOCKED(blocker, report)
```

Minimum review union:

```text
CodeReviewResult =
  REVIEW_ACCEPTED(candidate, review_report)
  REVIEW_REVISED(candidate, review_report)
  REVIEW_BLOCKED(blocker, review_report)
```

These types should eventually move into a reusable ML module.

## 11. Adapter Boundary Rules

Adapters may own:

- deterministic filesystem setup;
- benchmark execution;
- metric parsing from benchmark-owned output;
- leakage checks;
- graph snapshot updates;
- queue writes;
- journal appends;
- scheduler heuristics;
- memory indexing;
- final submission assembly.

Adapters may not own:

- hidden provider decisions;
- terminal workflow status outside typed output contracts;
- report parsing as semantic state;
- unvalidated stdout JSON as canonical state;
- undeclared artifact writes;
- undeclared queue transitions;
- prompt-only routing decisions;
- caller-selected output bundle paths.

The adapter contract is valid only when the runtime validates the adapter's structured result before committing state.

## 12. Runtime Foundation Dependencies

This design depends on several runtime surfaces being reliable:

- command structured-output conformance;
- provider structured-output target binding;
- private frontend-lowered typed value transport;
- generated path allocation ownership;
- prompt extern source semantics; and
- source-map visibility for generated paths and adapter calls.

If these are not yet complete, the first implementation should use the narrowest current supported path and explicitly mark any workaround as compatibility debt.

The workflow must not treat adapter stdout, prompt reports, or materialized value views as semantic authority merely because a runtime feature is missing.

## 13. Phased Implementation

### Phase 0: Package Normalization

- Move candidate-4 `.orc` to a module-path-correct location.
- Remove generated artifacts such as `__pycache__`.
- Rename module to match file path.
- Add provider prompt extern bindings.
- Add minimal README and example input.

Acceptance:

- `.orc` parses and reaches the next real compiler/runtime limitation.
- No package-path mismatch remains.

### Phase 1: Direct Candidate-4 Workflow

- Make the direct workflow compile and typecheck.
- Convert adapter outputs to the current expected structured bundle or variant format.
- Add focused adapter fixture tests.
- Add a dry-run or smoke path that does not execute arbitrary user code.

Acceptance:

- Compile succeeds.
- Shared validation succeeds.
- Dry-run or smoke succeeds with fixture providers/adapters.

### Phase 2: Certified Adapter Hardening

- Write explicit adapter contracts.
- Add positive and negative tests for each adapter class.
- Ensure adapters use declared output bundle paths.
- Ensure execution adapter has a sandbox policy before real code execution.

Acceptance:

- Runtime validates adapter output bundles.
- Missing/invalid adapter output fails closed.
- Queue and journal changes are traceable.

### Phase 3: Search/ML Module Split

- Extract ML types into `workflows/library/ml/mlevolve_types.orc`.
- Extract ML orchestration helpers into `workflows/library/ml/mle_engineering.orc`.
- Keep direct top-level entrypoint small.

Acceptance:

- Imports compile.
- Source maps preserve ownership.
- Direct workflow and split workflow have equivalent dry-run behavior.

### Phase 4: Reusable MCGS Library

- Extract generic graph-search records and scheduler-facing contracts.
- Keep numeric graph policy in adapters where appropriate.
- Introduce ProcRef or compile-time hooks only where current frontend support is proven.

Acceptance:

- Generic MCGS module can be reused by a non-ML fixture.
- ML specialization compiles without runtime procedure values.

## 14. Invariants And Failure Modes

Invariants:

- Provider decisions are structured values, not report text.
- Command adapter results are structured values, not stdout authority.
- Terminal outcomes are typed `SearchLoopStatus` variants.
- `BLOCKED` is explicit and carries a typed blocker.
- `TIMED_OUT` is terminal non-success, not hidden loop failure.
- Code execution is never performed by provider prompt alone.
- Search state snapshots and journals are artifacts/state with declared contracts.
- Queue movement is adapter-owned only when declared and tested.
- Generated code artifacts are treated as untrusted until sandbox execution validates them.

Expected failure behavior:

| Failure | Required behavior |
| --- | --- |
| Provider emits malformed candidate | Provider/output contract failure or `GENERATION_BLOCKED` if explicitly modeled. |
| Review blocks candidate | Commit typed blocker and terminal or active status as workflow dictates. |
| Scheduler cannot select work | Return `RUN_BLOCKED` or `RUN_COMPLETE`, not an empty report. |
| Execution fails | Produce execution report and route debug or blocked state through typed scheduler state. |
| Metric parse fails | Produce validation failure/report and keep candidate out of best solution. |
| Leakage check fails | Mark candidate invalid/leakage risk and keep evidence. |
| Adapter writes wrong path | Runtime output-contract failure. |
| Sandbox unavailable | Typed `Blocker` with retryability and stable class. |

## 15. Security And Operations

Generated ML code is untrusted. A production implementation must define:

- execution sandbox;
- filesystem access policy;
- network policy;
- timeout policy;
- resource limits;
- dataset isolation;
- secret redaction;
- artifact retention policy; and
- log/report redaction policy.

Until that exists, the execution adapter may operate only in fixture or annotation-scanning mode.

Provider prompts should not receive credentials, private environment variables, or unrestricted workspace context. Prompt inputs should be typed artifacts and explicit task context.

## 16. Verification Strategy

Minimum checks:

- compile the `.orc` with a module-path-correct file;
- run shared validation;
- run adapter fixture tests;
- run provider-output fixture tests with fake providers;
- dry-run the top-level workflow;
- smoke-run a safe fixture task without executing arbitrary code;
- verify state/artifact lineage for generated plans, code, reviews, execution reports, validation reports, and final summaries.

Negative checks:

- malformed provider candidate output fails;
- malformed review output fails;
- adapter stdout without output bundle does not become state;
- wrong-path adapter/provider bundle fails;
- unsafe relpaths fail path validation;
- invalid metric parse does not update best solution;
- leakage-risk candidate cannot become best solution;
- timeout returns `TIMED_OUT`;
- blocked setup returns typed `BLOCKED`.

## 17. Declarative Acceptance Scenario

Initial state:

- a fixture task description under `inputs/`;
- a fixture dataset manifest under `inputs/`;
- fake providers that emit deterministic structured candidate/review bundles;
- adapters configured in fixture/safe mode.

Entrypoint:

```bash
python -m orchestrator run workflows/examples/mlevolve_approx.orc \
  --entry-workflow mlevolve-run \
  --dry-run
```

Expected result:

- workflow compiles and validates;
- setup creates typed run state;
- scheduler emits typed ticks;
- provider roles emit structured candidate/review results;
- adapters emit structured command results;
- final status is `COMPLETED`, `TIMED_OUT`, or typed `BLOCKED`;
- reports are linked as views;
- state and artifact ledger carry the authoritative result.

Forbidden result:

- markdown report parsing decides terminal state;
- adapter stdout becomes semantic state without bundle validation;
- generated code executes outside the sandbox policy;
- scheduler hidden state cannot be inspected through declared snapshots/journals;
- workflow success depends on a module path mismatch, source-root workaround, or test-only fixture path.

## 18. Success Criteria

- Candidate-4-derived direct workflow compiles from a canonical repo path.
- At least one safe fixture dry-run or smoke path succeeds.
- Adapter contracts exist for setup, scheduler, execution/validation, queue update, memory, and finalization.
- Provider roles emit structured results validated by runtime contracts.
- Search status, scheduler tick, generation result, and review result unions are typed and documented.
- Reports, stdout, pointer files, and prompt text remain views.
- A follow-up module-split plan exists for candidate-2-style reusable library organization.
- Any remaining reliance on future Workflow Lisp features is explicitly listed as a prerequisite rather than hidden in example syntax.
