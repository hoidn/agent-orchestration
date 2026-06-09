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

These paths are local working evidence, not durable implementation evidence.
Before using this document as an implementation handoff, preserve the reviewed
candidates under a committed fixture path, a report artifact, or a recorded
commit/ref.

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

After the concrete workflow compiles, shared-validates, and has a fixture smoke
path, split the architecture toward the candidate-2 module shape:

```text
workflows/library/search/mcgs/types.orc
workflows/library/search/mcgs/contracts.orc
workflows/library/search/mcgs/loop.orc
  generic MCGS types, graph operators, and reusable search contracts

workflows/library/ml/mlevolve/types.orc
workflows/library/ml/mlevolve/provider_roles.orc
workflows/library/ml/mlevolve/adapter_contracts.orc
workflows/library/ml/mlevolve/review.orc
workflows/library/ml/mlevolve/memory.orc
  ML task, candidate, metric, memory, execution, provider, review, and adapter contracts

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

### 3.1 Candidate Evidence Required

The candidate ranking is advisory until backed by durable evidence. Record this
table before implementation work starts:

| Candidate | Source ref | Parser status | Compile/typecheck status | Adapter coverage | Prompt coverage | Runtime evidence | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Candidate 1 | TBD | TBD | TBD | TBD | TBD | TBD | generic callback reference |
| Candidate 2 | TBD | TBD | TBD | TBD | TBD | TBD | long-term module reference |
| Candidate 3 | TBD | TBD | TBD | TBD | TBD | TBD | reference only |
| Candidate 4 | TBD | TBD | TBD | TBD | TBD | TBD | first implementation base |

Temporary `tmp/` paths are not sufficient evidence for future review. The
evidence must include enough information to reproduce why candidate 4 is the
first runnable base and why candidate 2 is the preferred module shape.

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

### 4.1 MLEvolve Mechanism Traceability

This workflow is an MLEvolve-style architecture, not a line-for-line upstream
clone. The intended fidelity boundary is:

| MLEvolve mechanism | Workflow Lisp expression |
| --- | --- |
| Progressive Monte Carlo Graph Search | `SchedulerTick`, `SearchLoopState`, `CandidateNode`, `ReferenceEdge`, `NodeSnapshot`, and typed expansion requests. |
| Retrospective memory | coldstart guidance, memory layer state, memory retrieval context, memory update deltas, and memory ledger artifacts. |
| Hierarchical planning and adaptive code generation | provider roles for draft, debug, improve, evolve, fuse, aggregate, and typed generation modes. |
| Execution and metric feedback | sandboxed execution adapter, typed `EvaluationResult`, typed metric direction/value, and validation/leakage reports. |
| Branch reuse and fusion | explicit parent/reference edges and node-set snapshots, not report-parsed branch names. |

The scheduler may compute exploration/exploitation policy in an adapter, but
the selected action, rationale, and downstream request must be typed workflow
values.

## 5. Goals

- Express the MLEvolve loop as typed Workflow Lisp composition, not as one Python script.
- Keep terminal workflow outcomes in typed unions.
- Keep per-step provider decisions separate from terminal workflow status.
- Represent search state, pending work, candidate nodes, metrics, memory context, and blockers as typed records/unions.
- Use refined path types for task inputs, candidate code, plans, reports, snapshots, queues, memory ledgers, submissions, and generated bundles.
- Prefer typed state deltas over adapters committing opaque whole-state mutations.
- Use provider-result steps for draft, debug, improve, evolution, fusion, aggregation, and code-review roles.
- Use certified command adapters for deterministic setup, scheduling, queue updates, execution, validation, memory indexing, and finalization.
- Keep benchmark execution and sandboxing out of provider prompts.
- Preserve artifact lineage for plans, code, execution reports, validation reports, reviews, submissions, memory context, journals, and snapshots.
- Make stdout/debug reports views; typed bundles and runtime state are authority.
- Make effectful provider, command, state, and artifact effects visible in source maps and Semantic IR.
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

`execute_parse_validate_commit_batch` is acceptable only as a first-tranche
fixture/adapter boundary with a typed transition bundle. Promotion-grade work
should split execution, metric parsing, leakage validation, and state commit
unless the combined adapter has explicit idempotency, replay, state-schema, and
negative-test evidence.

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
prompts/mlevolve/
tests/workflow_lisp/examples/test_mlevolve_approx.py
```

Adapter scripts must live under an accepted command-adapter convention before
implementation. Current repo conventions include `orchestrator/workflow_lisp/adapters/`
for frontend adapter helpers and `scripts/` for standalone command utilities.
Do not introduce a new top-level `adapters/` tree unless the command-adapter
contract and workflow catalog accept it.

The `.orc` module path must match the file path. For example:

```lisp
(defmodule examples/mlevolve_approx)
```

should live at:

```text
workflows/examples/mlevolve_approx.orc
```

### 8.2 Long-Term Layout

After the first workflow compiles, shared-validates, and fixture-smokes:

```text
workflows/library/search/mcgs/types.orc
workflows/library/search/mcgs/contracts.orc
workflows/library/search/mcgs/loop.orc
workflows/library/search/mcgs/policy_adapters.orc
workflows/library/ml/mlevolve/types.orc
workflows/library/ml/mlevolve/provider_roles.orc
workflows/library/ml/mlevolve/adapter_contracts.orc
workflows/library/ml/mlevolve/review.orc
workflows/library/ml/mlevolve/memory.orc
workflows/library/prompts/mlevolve/
workflows/examples/mlevolve_approx.orc
registered mlevolve command adapters under the accepted adapter convention
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
           RUN_EXHAUSTED:
             done
           RUN_BLOCKED:
             done
       COMPLETED/TIMED_OUT/EXHAUSTED/BLOCKED:
         done
  -> finalize
```

The scheduler tick is a typed event, not a gate string. It must carry enough data for downstream steps to run without parsing reports.

### 9.1 Authoring Skeleton

The target authoring shape should feel like typed orchestration rather than a
manual state-file script:

```lisp
(defworkflow run-mlevolve-approx
  ((inputs MleTaskInputs)
   (mle-cfg MleConfig)
   (mcgs-cfg McgsConfig))
  -> MleSearchOutput
  :effects ((uses-provider providers.mlevolve.draft
                           providers.mlevolve.debug
                           providers.mlevolve.review)
            (runs-command adapters.mlevolve.scheduler
                          adapters.mlevolve.execute
                          adapters.mlevolve.finalize)
            (updates-state SearchLoopState)
            (writes SearchSnapshotPath ExecutionReportPath SubmissionPath))
  (let* ((setup (mle/setup-run inputs mle-cfg))
         (preview (mle/build-preview setup))
         (memory (mle/init-memory setup preview))
         (initial (mcgs/init-search-state inputs mcgs-cfg memory)))
    (loop/recur
      :max mcgs-cfg.max-steps
      :state initial
      (fn (state)
        (let ((tick (mcgs/scheduler-tick state)))
          (match tick
            ((EXPAND_SELECTED selected)
              (continue (mle/expand-and-enqueue state selected.request)))
            ((EXECUTE_PENDING_BATCH pending)
              (continue (mle/execute-and-commit state pending.batch)))
            ((RUN_COMPLETE completed)
              (done (mle/finalize-completed completed)))
            ((RUN_TIMEOUT timed-out)
              (done (mle/finalize-timeout timed-out)))
            ((RUN_EXHAUSTED exhausted)
              (done (mle/finalize-exhausted exhausted)))
            ((RUN_BLOCKED blocked)
              (done (mle/finalize-blocked blocked)))))))))
```

This skeleton is an authoring target, not proof that every shown helper already
exists. Implementation must use the current accepted `.orc` import, effect,
and stdlib surfaces.

## 10. Data Contracts

The first implementation should define concrete `.orc` contracts before writing
provider prompts or adapters.

### 10.1 Refined Path Families

Use path contracts instead of plain strings for durable file/state surfaces:

```lisp
(defpath TaskDescriptionPath :kind relpath :under "inputs" :must-exist true)
(defpath DatasetManifestPath :kind relpath :under "inputs" :must-exist true)
(defpath CandidateCodePath :kind relpath :under "artifacts/mlevolve/code" :must-exist true)
(defpath CandidatePlanPath :kind relpath :under "artifacts/mlevolve/plans" :must-exist true)
(defpath ExecutionReportPath :kind relpath :under "artifacts/mlevolve/execution" :must-exist true)
(defpath ValidationReportPath :kind relpath :under "artifacts/mlevolve/validation" :must-exist true)
(defpath SearchSnapshotPath :kind relpath :under "state/mlevolve/search" :must-exist true)
(defpath PendingQueuePath :kind relpath :under "state/mlevolve/queue" :must-exist true)
(defpath MemoryLedgerPath :kind relpath :under "state/mlevolve/memory" :must-exist true)
(defpath SubmissionPath :kind relpath :under "artifacts/mlevolve/submissions" :must-exist true)
```

These path contracts are semantic constraints. Pointer files, reports, and
materialized prompt views remain representations unless a specific contract
promotes them.

### 10.2 Minimum Search Records

Minimum supporting records:

```text
MetricValue(direction, value, parsed)
SearchBudget(max_steps, time_limit_sec, completed_steps, elapsed_sec)
NodeRef(node_id, branch_id, stage, health, metric)
ReferenceEdge(source_node, target_node, relation)
CandidateNode(node, parent, references, plan, code, generation_report, provenance)
ExecutionResult(node, report, validation_report, metric, health)
MemoryContext(items, context_view, retrieval_report, ledger)
ExecutionBatch(queue, parallel_width, selected_nodes)
SchedulerRationale(policy, reason, selected_node, exploration_score, exploitation_score)
```

Private typed list/map/record values should be used for node sets, top-k
snapshots, memory contexts, queues, and execution batches once the runtime
foundation supports them. Do not collapse these values into ad hoc pointer
files or markdown reports.

### 10.3 Terminal Status

Minimum terminal status union:

```text
SearchLoopStatus =
  ACTIVE(state)
  COMPLETED(summary, best_solution, top_k_submissions, journal, memory_ledger)
  TIMED_OUT(summary, best_solution, journal, memory_ledger)
  EXHAUSTED(summary, best_solution, journal, memory_ledger)
  BLOCKED(summary, blocker, journal)
```

`EXHAUSTED` is distinct from `TIMED_OUT`: it means the bounded search budget was
consumed without another active route. If implementation intentionally
normalizes exhaustion to `COMPLETED` or `BLOCKED`, that normalization must be a
typed field and a recorded parity decision.

Minimum scheduler tick union:

```text
SchedulerTick =
  EXPAND_SELECTED(request, rationale, scheduler_report)
  EXECUTE_PENDING_BATCH(batch, rationale, scheduler_report)
  RUN_COMPLETE(summary, best_solution, top_k_submissions, journal, memory_ledger)
  RUN_TIMEOUT(summary, best_solution, journal, memory_ledger)
  RUN_EXHAUSTED(summary, best_solution, journal, memory_ledger)
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

`REVIEW_REVISED(candidate)` is a one-shot review/repair policy: the reviewer may
emit a revised candidate that is validated and then enqueued without another
review pass. If MLEvolve uses bounded review/fix, replace this union with the
stdlib `review-revise-loop` route and typed `ReviewLoopResult` instead of
inventing a second loop.

### 10.4 Blocker Scope

Distinguish node-level blockers from run-level blockers:

```text
NodeBlocker =
  NODE_GENERATION_BLOCKED(blocker, node_or_request, report)
  NODE_REVIEW_BLOCKED(blocker, node, review_report)
  NODE_EXECUTION_BLOCKED(blocker, node, execution_report)

RunBlocker =
  RUN_SETUP_BLOCKED(blocker, report)
  RUN_SANDBOX_UNAVAILABLE(blocker, report)
  RUN_PROVIDER_UNAVAILABLE(blocker, report)
  RUN_UNRECOVERABLE(blocker, summary)
```

A blocked node may leave `SearchLoopStatus` as `ACTIVE`; a run blocker produces
terminal `BLOCKED`. Missing sandbox resources, invalid task contracts, provider
transport failure, or exhausted recovery attempts can block the run. Malformed
candidate code, failed execution, or review rejection should usually block only
that branch unless scheduler policy says no safe work remains.

### 10.5 Typed State Deltas

Adapters should return typed deltas wherever practical instead of committing
opaque whole-state mutations:

```text
SearchStateDelta =
  ENQUEUE_CANDIDATE(candidate, journal_entry)
  COMMIT_EXECUTION_RESULT(node, result, metric, journal_entry)
  MARK_NODE_BLOCKED(blocker, journal_entry)
  UPDATE_MEMORY(memory_delta, journal_entry)
  FINALIZE_RUN(summary, submission_bundle, journal_entry)
```

The adapter may compute the deterministic mechanics. Workflow/runtime authority
begins only after the structured delta bundle validates and the declared
state/artifact transition is committed.

### 10.6 Generic Search Contracts

The first MLEvolve workflow may be monomorphic, but reusable search types should
be introduced early when they do not require runtime closures:

```text
SearchNode[PayloadT]
SearchState[NodeT MemoryT]
SearchProblem[TaskT CandidateT MetricT MemoryT]
ExpansionRequest[CandidateT MemoryT]
```

These type parameters are compile-time only. They must specialize before Core,
Semantic IR, Executable IR, and runtime-visible contracts.

These types should eventually move into reusable search and ML modules.

## 11. Adapter Boundary Rules

Compute adapters may own deterministic calculation:

- leakage checks;
- scheduler heuristics;
- generation-mode selection;
- memory retrieval queries;
- metric parsing from benchmark-owned output; and
- graph/search scoring.

Commit-capable adapters may own deterministic state transitions only when the
transition is declared and validated:

- run setup;
- graph snapshot updates;
- queue writes;
- journal appends;
- memory ledger updates;
- execution-result commits;
- final submission assembly.

Commit-capable adapters must emit a typed transition bundle describing:

- input state identity and schema version;
- output state identity and schema version;
- declared artifacts written;
- queue, journal, snapshot, and memory mutations;
- idempotency key;
- replay behavior on resume;
- stable error code; and
- source-map owner.

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
Adapter stdout, logs, markdown reports, and undeclared files are not commit
authority.

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
- Add a compile/shared-validation dry-run path.
- Add a separate fixture smoke path that does not execute arbitrary user code.

Acceptance:

- Compile succeeds.
- Shared validation succeeds.
- Dry-run resolves prompt externs, adapter references, contracts, and lowering
  without requiring provider or command execution.
- Fixture smoke succeeds with fake providers and fixture-mode adapters.

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

- Extract ML types into `workflows/library/ml/mlevolve/types.orc`.
- Extract provider roles, adapter contracts, review, and memory helpers into
  `workflows/library/ml/mlevolve/`.
- Keep direct top-level entrypoint small.

Acceptance:

- Imports compile.
- Source maps preserve ownership.
- Direct workflow and split workflow have equivalent dry-run behavior.

### Phase 4: Reusable MCGS Library

- Extract generic graph-search records and scheduler-facing contracts.
- Keep numeric graph policy in adapters where appropriate.
- Introduce ProcRef or compile-time hooks only where current frontend support is proven.
- Keep generic types compile-time-only and monomorphized before runtime-visible contracts.

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
- `EXHAUSTED` is explicit or deliberately normalized through a typed field.
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
| Step budget exhausted | Return `RUN_EXHAUSTED`, or a documented typed normalization. |
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

Minimum real-execution sandbox checks:

- generated code cannot read secrets or environment values outside the allowlist;
- generated code cannot write outside candidate workspace and output roots;
- network access is disabled or explicitly policy-controlled;
- symlink traversal is rejected;
- timeout kills child process trees;
- resource limits are enforced;
- dataset inputs are read-only;
- invalid or leakage-risk submissions cannot update `best_solution`; and
- logs redact provider tokens, secrets, and private environment variables.

## 16. Verification Strategy

Minimum checks:

- compile the `.orc` with a module-path-correct file;
- run shared validation;
- run adapter fixture tests;
- run provider-output fixture tests with fake providers;
- dry-run the top-level workflow;
- smoke-run a safe fixture task without executing arbitrary code;
- verify state/artifact lineage for generated plans, code, reviews, execution reports, validation reports, and final summaries.
- verify effect summaries and source maps expose provider, command, state, and artifact effects.
- verify typed adapter deltas or transition bundles are validated before commit.

Negative checks:

- malformed provider candidate output fails;
- malformed review output fails;
- adapter stdout without output bundle does not become state;
- wrong-path adapter/provider bundle fails;
- unsafe relpaths fail path validation;
- invalid metric parse does not update best solution;
- leakage-risk candidate cannot become best solution;
- timeout returns `TIMED_OUT`;
- exhausted budget returns `EXHAUSTED` or a documented typed normalization;
- blocked setup returns typed `BLOCKED`.
- real execution adapter cannot run without sandbox policy evidence.

## 17. Declarative Acceptance Scenarios

### 17.1 Compile / Shared-Validation Gate

Initial state:

- a fixture task description under `inputs/`;
- a fixture dataset manifest under `inputs/`;
- provider externs and prompt externs that resolve;
- registered certified adapter references.

Entrypoint:

```bash
python -m orchestrator run workflows/examples/mlevolve_approx.orc \
  --entry-workflow run-mlevolve-approx \
  --dry-run
```

Expected result:

- workflow compiles and validates;
- module path matches file path;
- prompt externs resolve;
- adapter references resolve to registered certified adapters;
- provider, command, state, and artifact effects are visible;
- no real provider command or generated-code execution is required.

### 17.2 Fixture Smoke Gate

Initial state:

- the same fixture task and dataset manifest;
- fake providers that emit deterministic structured candidate/review bundles;
- adapters configured in fixture/safe mode;
- execution adapter limited to fixture or annotation-scanning behavior.

Entrypoint:

```bash
python -m orchestrator run workflows/examples/mlevolve_approx.orc \
  --entry-workflow run-mlevolve-approx \
  --provider-externs-file workflows/examples/inputs/mlevolve/providers.fake.json \
  --prompt-externs-file workflows/examples/inputs/mlevolve/prompts.json
```

Expected result:

- setup creates typed run state;
- scheduler emits typed ticks with typed rationale;
- provider roles emit structured candidate/review results;
- adapters emit structured command results or typed deltas;
- final status is `COMPLETED`, `TIMED_OUT`, `EXHAUSTED`, or typed `BLOCKED`;
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
- Candidate sketch evidence is durable enough to audit without local `tmp/` paths.
- Compile/shared-validation dry-run succeeds without claiming runtime outputs.
- At least one safe fixture smoke path succeeds.
- Adapter contracts exist for setup, scheduler, execution/validation, queue update, memory, and finalization.
- Commit-capable adapters return typed transition bundles or typed deltas with idempotency and replay semantics.
- Provider roles emit structured results validated by runtime contracts.
- Refined path types, search records, search status, scheduler tick, generation result, review result, blocker scope, and state-delta contracts are typed and documented.
- Code review uses either the stdlib `review-revise-loop` route or a documented one-shot review/repair policy.
- Search state, memory context, top-k snapshots, node sets, queues, and execution batches use private typed values where supported rather than pointer/report workarounds.
- Effect summaries and source maps expose provider, command, state, and artifact effects.
- Reports, stdout, pointer files, and prompt text remain views.
- A follow-up module-split plan exists for candidate-2-style reusable library organization.
- Any remaining reliance on future Workflow Lisp features is explicitly listed as a prerequisite rather than hidden in example syntax.
