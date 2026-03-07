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
| Docs vs specs precedence | "Any docs page is authoritative." | `specs/` are normative. `docs/` are explanatory. | [Master Spec](../specs/index.md) |

---

## Quick Start

### [README](../README.md) - Project Overview
**Description:** High-level project entrypoint with setup, CLI quickstart, version snapshot, and common commands.  
**Keywords:** setup, install, quickstart, cli  
**Use this when:** You are onboarding or need to run the orchestrator quickly.

### [Orchestration Start Here](orchestration_start_here.md)
**Description:** Conceptual foundation for the system and glossary of orchestration/workflow/runtime terminology, with a relationship diagram.  
**Keywords:** concepts, glossary, orchestration, dsl, runtime  
**Use this when:** You need a clean mental model before authoring workflows or debugging behavior.

### [Runtime Execution Lifecycle](runtime_execution_lifecycle.md)
**Description:** Step-by-step runtime timeline from workflow load/validation through step execution, contract enforcement, and termination.  
**Keywords:** runtime, execution, state, lifecycle, control-flow  
**Use this when:** You need to understand what the engine actually does during `run`/`resume`.

### [Workflow Drafting Guide](workflow_drafting_guide.md)
**Description:** Authoring guidance for writing robust workflows, including prompt/runtime/flow contract separation and deterministic handoff patterns.  
**Keywords:** authoring, prompts, contracts, deterministic-handoff, gates  
**Use this when:** You are writing or refactoring workflow YAML and prompt patterns.

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

4. [Workflow Index](../workflows/README.md) plus one or two runnable examples under [workflows/examples/](../workflows/examples/)
   Why: use examples to copy the current house style for loops, gates, artifact contracts, and prompt layout instead of inventing patterns from scratch.

Minimum rule of thumb: if you have only read `docs/index.md`, you can find the docs; if you have read the four items above, you can usually write an effective workflow without extra repo archaeology.

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
**Keywords:** providers, prompt-composition, argv, stdin, placeholders  
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
**Description:** DSL evolution from v1.1 through v1.4, migration guidance, and planned feature gating notes.  
**Keywords:** versioning, migration, v1.2, v1.3, v1.4  
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
**Keywords:** workflows, catalog, index, examples, runbooks
**Use this when:** You need to find the right workflow file before reading or running it.

### [v0 Artifact-Contract Prototype Runbook](../workflows/examples/README_v0_artifact_contract.md)
**Description:** Runbook for deterministic file-based handoff prototypes, including verification commands and known limits.  
**Keywords:** runbook, artifact-contracts, deterministic-handoff, prototype  
**Use this when:** Running or extending backlog/plan execute-review-fix prototypes.

### [Workflow Examples Directory](../workflows/examples/)
**Description:** Concrete YAML workflows covering retries, conditionals, loops, prompt auditing, capture modes, and dataflow contracts.  
**Keywords:** examples, yaml, retries, loops, dataflow  
**Use this when:** You want a working template instead of starting from a blank workflow.

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

*Last updated: March 2026*  
*Style: detailed catalog with descriptions, keywords, and task-oriented navigation*
