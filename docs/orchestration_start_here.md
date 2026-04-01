# Orchestration Start Here

This document is the conceptual entry point for `agent-orchestration`.
It explains how orchestration, workflow DSL authoring, and runtime execution fit together.

Normative behavior lives in `specs/`. This file is explanatory.

## Read Order

1. `docs/orchestration_start_here.md` (this file)
2. `docs/runtime_execution_lifecycle.md` (what happens at runtime)
3. `docs/workflow_drafting_guide.md` (how to author workflows)
4. `specs/index.md` (normative contracts)

## One-Screen Model

```text
Design time (authoring)                              Runtime (execution)
-----------------------------------------------------------------------------
Write workflow YAML (DSL) -------------------------> Parse raw mapping
Write provider prompt files -----------------------> Elaborate to typed surface AST
Define artifact contracts -------------------------> Lower to executable IR + compatibility projection
Configure queue conventions in workflow -----------> Execute IR nodes / enforce contracts
Use runbook/CLI flags -----------------------------> Emit state/logs/reports through compatibility surfaces
```

Short version:
- DSL authoring defines intended behavior.
- Runtime execution applies that behavior step by step.
- Orchestration is the full system around both.

## Glossary

`orchestration`
- The full coordination system: workflow graph + runtime engine + queue conventions + operational policy.

`workflow`
- One executable YAML definition of steps, control flow, and contracts.

`DSL`
- The YAML schema used to express workflows (`steps`, `on.goto`, `artifacts`, `publishes`, `consumes`, etc.).

`surface AST`
- The immutable authored-shape in-memory model produced after validation/elaboration.

`executable IR`
- The immutable execution-shape in-memory model consumed by runtime collaborators.

`compatibility projection`
- The mapping from executable node ids back to persisted/reporting surfaces such as `steps.*`, `current_step.index`, `finalization.*`, and report ordering.

`step`
- One node in a workflow graph (`command`, `provider`, `wait_for`, or loop-nested step).

`step execution`
- One runtime invocation of one step in one run.

`queue`
- Filesystem-backed work-item conventions (`inbox/`, `processed/`, `failed/`) used by explicit workflow steps.

`policy`
- Rules and conventions for execution, e.g. retry strategy, gating strictness, queue lifecycle, and run operations.

`runbook`
- Human operations guidance for launch/monitor/resume/recovery; does not define executable logic by itself.

`authoring`
- Editing workflow YAML, prompt files, and related contracts before a run.

`runtime`
- Executing a workflow (`run`/`resume`) and producing state/log artifacts under `.orchestrate/runs/<run_id>/`.

## Relationship Diagram

```text
                 +-------------------------------------------+
                 | Workflow DSL YAML                         |
                 | (graph, routing, contracts)               |
                 +----------------------+--------------------+
                                        |
                                        v
                           +---------------------------+
                           | Parse + Elaborate         |
                           | raw -> typed surface AST  |
                           +-----------+---------------+
                                       |
                                       v
                           +---------------------------+
                           | Lowering                  |
                           | AST -> IR + projection    |
                           +-----------+---------------+
                                       |
                                       v
                           +---------------------------+
                           | Orchestrator Runtime      |
                           | executes IR nodes         |
                           +-----------+---------------+
                                       |
                   +-------------------+-------------------+
                   |                                       |
                   v                                       v
        +-------------------------+            +-------------------------+
        | Command / wait_for step |            | Provider step           |
        | shell/poll execution    |            | prompt + provider CLI   |
        +------------+------------+            +------------+------------+
                     |                                      ^
                     v                                      |
        +-------------------------+            +------------+------------+
        | state.json + run logs   |<-----------| prompt files + injection |
        | report/projection views |            | composition               |
        +------------+------------+            +-------------------------+
                     ^
                     |
        +------------+------------+
        | queue item conventions  |
        | (workflow-authored ops) |
        +-------------------------+
```

## What Belongs Where

Change workflow DSL when you need to change:
- control flow (`goto`, gates, retries, loops)
- artifact lineage semantics (`artifacts`, `publishes`, `consumes`)
- deterministic output/consume contract behavior

Change prompt files when you need to change:
- provider step instructions
- scope/format guidance for provider outputs

Change runtime invocation or runbooks when you need to change:
- CLI flags (`--debug`, `--on-error`, summary mode, etc.)
- operational procedures (launch, monitoring, recovery)
- repo-local operator conventions for special workflows that also mutate git state during a run

Change specs when you need to change:
- normative contract semantics (DSL/state/CLI behavior itself)

## Frequent Confusions

Confusion: "Runbook controls execution semantics."
- Correction: workflow DSL controls executable semantics; runbook explains usage.

Confusion: "Every workflow needs the same git-safety rules."
- Correction: most workflows do not treat git history or checkout state as runtime data. Special coexistence rules are repo-local operational policy only for workflows with DSL-level git rollback/checkpoint behavior, such as candidate-commit loops that record a base ref and later reset/restore against it.

Confusion: "Prompt text can define routing."
- Correction: routing belongs in DSL `on.*.goto` and gate steps.

Confusion: "Queue lifecycle is automatic."
- Correction: queue file lifecycle is workflow-authored; orchestrator does not auto-move items.

Confusion: "Execution still runs the raw lowered dict graph."
- Correction: raw YAML exists only long enough to parse; execution runs the lowered executable IR, and persisted/reporting compatibility surfaces are reconstructed through the projection layer.

Confusion: "Informative docs are normative."
- Correction: `specs/` are normative; docs are guidance.

## Companion Docs

- Runtime sequence details: `docs/runtime_execution_lifecycle.md`
- Workflow authoring guidance: `docs/workflow_drafting_guide.md`
- DSL reference (normative): `specs/dsl.md`
- State schema (normative): `specs/state.md`
- Provider/prompt contract (normative): `specs/providers.md`
- Queue conventions (normative): `specs/queue.md`
- CLI behavior (normative): `specs/cli.md`
