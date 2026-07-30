# Orchestration Start Here

This document is the conceptual entry point for `agent-orchestration`.
It explains how orchestration, workflow DSL authoring, and runtime execution fit together.

Normative behavior lives in `specs/`. This file is explanatory.

## Read Order

1. `docs/orchestration_start_here.md` (this file)
2. `docs/runtime_execution_lifecycle.md` (what happens at runtime)
3. `docs/lisp_workflow_drafting_guide.md` (how to author `.orc` workflows)
4. `specs/index.md` (normative contracts)

## One-Screen Model

```text
Design time (authoring)                              Runtime (execution)
-----------------------------------------------------------------------------
Write Workflow Lisp (.orc) ------------------------> Parse and typecheck source
Write provider prompt files -----------------------> Elaborate to typed surface AST
Define typed values/contracts ---------------------> Lower to executable IR + compatibility projection
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
- One executable `.orc` program defining typed steps, control flow, and
  contracts.

`DSL`
- The normative Core workflow contract (`steps`, routing, artifacts,
  publications, consumes, and related runtime semantics) targeted by the
  Workflow Lisp compiler. It is not a separately authored YAML frontend.

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
- Editing Workflow Lisp `.orc`, prompt files, extern manifests, and related
  contracts before a run.

`runtime`
- Executing a workflow (`run`/`resume`) and producing state/log artifacts under `.orchestrate/runs/<run_id>/`.

## Relationship Diagram

```text
                 +-------------------------------------------+
                 | Workflow Lisp .orc                        |
                 | (typed composition and contracts)         |
                 +----------------------+--------------------+
                                        |
                                        v
                           +---------------------------+
                           | Compile + Elaborate       |
                           | source -> typed AST       |
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

Change Workflow Lisp source when you need to change:
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
- Correction: routing belongs in typed workflow control flow and its lowered
  Core graph.

Confusion: "Queue lifecycle is automatic."
- Correction: queue file lifecycle is workflow-authored; orchestrator does not auto-move items.

Confusion: "The runtime can still execute a YAML/YML workflow if the file is
present."
- Correction: fresh `run` accepts only a case-insensitive `.orc` suffix and
  rejects every other source with `.orc required` before state creation.
  Reports and dashboards may render persisted legacy state without parsing its
  source. `resume` loads the selected persisted state, then every recorded
  non-`.orc` suffix fails closed with `.orc required`, regardless of run
  terminality or force-restart selection. Legacy state remains viewable only
  through state-only report/dashboard observability.

Confusion: "Execution runs the authored source tree directly."
- Correction: execution runs validated executable IR. Persisted/reporting
  compatibility surfaces are reconstructed through the projection layer.
  `expanded.debug.yaml` is a JSON-rendered debug view despite its historical
  filename.

Confusion: "Informative docs are normative."
- Correction: `specs/` are normative; docs are guidance.

## Companion Docs

- Runtime sequence details: `docs/runtime_execution_lifecycle.md`
- Workflow authoring guidance: `docs/lisp_workflow_drafting_guide.md`
- Historical YAML translation reference: `docs/workflow_drafting_guide.md`
- DSL reference (normative): `specs/dsl.md`
- State schema (normative): `specs/state.md`
- Provider/prompt contract (normative): `specs/providers.md`
- Queue conventions (normative): `specs/queue.md`
- CLI behavior (normative): `specs/cli.md`
