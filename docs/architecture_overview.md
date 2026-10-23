# Architecture Overview

Status: informative conceptual front door
Normative authority: `specs/`
Fuller model: [Orchestration Start Here](orchestration_start_here.md)

`agent-orchestration` is a deterministic workflow runtime with Workflow Lisp
and typed Python authoring for agent-driven work. It treats workflows as typed
contracts over state, artifacts, provider calls, command calls, and control flow.

## One-Screen Model

```text
Workflow Lisp source (.orc) <- typed Python source generation
        |
        v
typed frontend / checked closed-program validation
        |
        v
checked program, typed contracts, effect sites and source provenance
        |
        v
evaluated runtime and effect memo
        |
        v
run header, checked artifact, memo, attempt evidence and derived views
```

## What Is Authoritative?

Normative runtime behavior lives in `specs/`, especially:

- [DSL](../specs/dsl.md)
- [Step IO](../specs/io.md)
- [Providers](../specs/providers.md)
- [State](../specs/state.md)
- [Dependencies](../specs/dependencies.md)

Within an evaluated run, the immutable header and checked program, validated
input/result values and append-only memo own execution, reuse and terminal
status. Effect sites and activation paths identify effects; source spans explain
them. Historical state/snapshot formats retain only their explicit read contract.

## What Is A View?

Reports, markdown summaries, stdout, prompt audits, pointer files, and
dashboards are views unless a specific contract makes one of them the artifact
value. `expanded.debug.yaml` is an intentionally historical filename for a
JSON-rendered debug projection; it is also a view and is never parsed as authored
source. A useful view may explain a decision, but workflow control should come
from validated state and contracts.

## Why Files?

The runtime intentionally exposes durable filesystem artifacts:

- runs can be resumed or inspected after process death;
- provider and command outputs have stable evidence paths;
- workflow steps can consume validated artifacts instead of transient process
  memory;
- downstream tools can inspect the same state the runtime uses.

Files are storage and evidence. They should not become unvalidated hidden state
or ad hoc pointers that replace structured workflow values.

## Why Types?

Typed outputs, variants, and contracts prevent common workflow mistakes:

- a review decision is distinct from a report;
- a tagged outcome must prove its variant before variant-specific values are
  consumed;
- command and provider outputs are validated before canonical state is exposed;
- migration results can be compared against preserved historical baselines
  mechanically.

## Why Workflow Lisp?

Workflow Lisp (`.orc`) is an authoring frontend for reusable typed composition.
It provides typed modules, procedures, bounded control and visible effects.
Shared typed elaboration, specialization and scope/proof analysis construct a
checked closed program, which the evaluated runtime executes against its memo.
Resume re-evaluates from the entry and reuses validated committed effects.

Public compilation and execution use admitted evaluated targets: 2.35/2.36,
bounded 2.37 parallel-map support, and bounded 2.38 Agent Sessions and command-only
confined run references. Target 2.39 adds inferred procedure effects with
optional restrictions and compiler-owned lowering, using the same runtime.
Source compilation, imports and editor analysis require targets 2.35–2.39;
historical data readers do not admit older source. Public confined providers
remain gated. The
[evaluated design](design/workflow_lisp_evaluated_execution.md) owns that model;
the [flat-route retrospective](reports/2026-10-13-flat-route-retirement-retrospective.md)
records the retired predecessor. The [capability matrix](capability_status_matrix.md)
owns current availability, copy-safety and remaining gates for each surface.

The [Python frontend](design/python_workflow_frontend.md) generates inspectable
ordinary `.orc` for a serial subset, using the same compiler and runtime.
Its imports and tracing execute trusted Python; the build worker is not a
sandbox. Retained snapshots let ordinary resume work without importing Python.
If neither frontend supports the required form, record a capability gap rather
than creating a lower-level or YAML workaround. Historical YAML/YML sources
remain translation and evidence inputs, not executable workflows.

## Next Reading

- [Documentation Hub](index.md): choose the right spec, guide, or design doc.
- [Capability Status Matrix](capability_status_matrix.md): check whether a
  surface is implemented, partial, library-provided, designed, future, or legacy.
- [Workflow Drafting Guide](workflow_drafting_guide.md): translate or audit
  historical YAML workflows.
- [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md): author `.orc`
  workflows.
- [Typed Python Workflows](python_workflow_drafting_guide.md): generate `.orc`
  and run a provider-free serial example.
- [Design Documentation Index](design/README.md): route to architecture and
  migration designs.
- [Documentation Conventions](documentation_conventions.md): keep future docs
  explicit about status, authority, examples, and trust boundaries.
