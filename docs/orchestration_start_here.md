# Orchestration Start Here

This document is the conceptual entry point for `agent-orchestration`.
It explains how orchestration, workflow DSL authoring, and runtime execution fit together.

Normative behavior lives in `specs/`. This file is explanatory.

## Read Order

1. `docs/orchestration_start_here.md` (this file)
2. `docs/runtime_execution_lifecycle.md` (what happens at runtime)
3. [Workflow Lisp guide](lisp_workflow_drafting_guide.md) (direct `.orc` authoring)
   or [typed Python guide](python_workflow_drafting_guide.md) (serial generation into `.orc`)
4. `specs/index.md` (normative contracts)

## One-Screen Model

```text
Design time (authoring)                              Runtime (execution)
-----------------------------------------------------------------------------
Typed Python -> generated Workflow Lisp (.orc) --+
Write Workflow Lisp (.orc) ---------------------+--> Parse and typecheck source
Write provider prompt files -----------------------> Elaborate to typed surface AST
Define typed values/contracts ---------------------> Compile to a checked closed program
Configure queue conventions in workflow -----------> Evaluate effects against the memo / enforce contracts
Use runbook/CLI flags -----------------------------> Emit memo, derived state.json and reports
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
- Historical flat execution model, retired 2026-10-13; an evaluated run executes the checked closed program (`closed_program.json`) instead.

`compatibility projection`
- The derived `state.json`/report view (`steps.*`, `current_step`) an evaluated run rebuilds from its memo; never authority.

`step`
- One effect site in a workflow program (`command`, `provider`, `run_ref`, or an agent allocation or turn), identified under its call frames.

`step execution`
- One runtime invocation of one step in one run.

`queue`
- Filesystem-backed work-item conventions (`inbox/`, `processed/`, `failed/`) used by explicit workflow steps.

`policy`
- Rules and conventions for execution, e.g. retry strategy, gating strictness, queue lifecycle, and run operations.

`runbook`
- Human operations guidance for launch/monitor/resume/recovery; does not define executable logic by itself.

`authoring`
- Editing Workflow Lisp `.orc` directly or generating it from typed Python,
  plus prompt files, extern manifests and related contracts before a run.
  Python imports and tracing run during generation; runtime execution consumes
  the checked `.orc` program, never Python callbacks.

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
                           | Closed-program compile    |
                           | AST -> checked program    |
                           +-----------+---------------+
                                       |
                                       v
                           +---------------------------+
                           | Orchestrator Runtime      |
                           | evaluates the program     |
                           +-----------+---------------+
                                       |
                   +-------------------+-------------------+
                   |                                       |
                   v                                       v
        +-------------------------+            +-------------------------+
        | Command step            |            | Provider step           |
        | shell execution         |            | prompt + provider CLI   |
        +------------+------------+            +------------+------------+
                     |                                      ^
                     v                                      |
        +-------------------------+            +------------+------------+
        | state.json + run logs   |<-----------| prompt files + injection |
        | report/derived views    |            | composition               |
        +------------+------------+            +-------------------------+
                     ^
                     |
        +------------+------------+
        | queue item conventions  |
        | (workflow-authored ops) |
        +-------------------------+
```

## What Belongs Where

Change Workflow Lisp source or the typed Python source that generates it when
you need to change:

- typed branch, loop and call control
- input, result and path contracts
- explicit provider/command effects and prompt bindings

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
  source. `resume`, including `--force-restart`, refuses a retired execution
  profile first with `workflow_execution_profile_retired`, before source
  checks or mutation; a fresh `run` of a non-`.orc` path fails closed with
  `.orc required`. Legacy state remains viewable only
  through state-only report/dashboard observability.

Confusion: "Execution runs the authored source tree directly."
- Correction: execution runs the checked closed program compiled from the
  source (`closed_program.json`, digest-pinned in `run.json`); `state.json`
  and reports are derived views rebuilt from the memo. The flat route's
  executable IR and debug YAML renderer are retired.

Confusion: "Informative docs are normative."
- Correction: `specs/` are normative; docs are guidance.

## Companion Docs

- Runtime sequence details: `docs/runtime_execution_lifecycle.md`
- Workflow authoring guidance: [Workflow Lisp](lisp_workflow_drafting_guide.md)
  or [typed Python](python_workflow_drafting_guide.md)
- Historical YAML translation reference: `docs/workflow_drafting_guide.md`
- DSL reference (normative): `specs/dsl.md`
- State schema (normative): `specs/state.md`
- Provider/prompt contract (normative): `specs/providers.md`
- Queue conventions (normative): `specs/queue.md`
- CLI behavior (normative): `specs/cli.md`
