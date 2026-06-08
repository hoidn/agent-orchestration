# Architecture Overview

Status: informative conceptual front door
Normative authority: `specs/`
Fuller model: [Orchestration Start Here](orchestration_start_here.md)

`agent-orchestration` is a deterministic workflow runtime plus authoring
frontends for agent-driven work. It treats workflows as typed contracts over
state, artifacts, provider calls, command calls, and control flow.

## One-Screen Model

```text
authored workflow
  YAML DSL or Workflow Lisp .orc
        |
        v
loader / frontend / validation
        |
        v
typed workflow state, output contracts, artifact lineage, source maps
        |
        v
runtime execution
        |
        v
run state, logs, artifacts, reports, and resume evidence
```

## What Is Authoritative?

Normative runtime behavior lives in `specs/`, especially:

- [DSL](../specs/dsl.md)
- [Step IO](../specs/io.md)
- [Providers](../specs/providers.md)
- [State](../specs/state.md)
- [Dependencies](../specs/dependencies.md)

Within a run, structured state, output bundles, typed variants, validated
artifacts, snapshots, and source-mapped executable nodes are the semantic
authority. They decide routing, resume, publication, and terminal status.

## What Is A View?

Reports, markdown summaries, rendered debug YAML, stdout, prompt audits, pointer
files, and dashboards are views unless a specific contract makes one of them the
artifact value. A useful view may explain a decision, but workflow control should
come from validated state and contracts.

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
- migration candidates can be compared against YAML primaries mechanically.

## Why Workflow Lisp?

Workflow Lisp (`.orc`) is an authoring frontend for reusable typed composition.
It should make high-level workflows easier to write without changing runtime
authority. The frontend lowers through shared validation, semantic IR, executable
IR, source maps, and the existing runtime.

Use Workflow Lisp when the required forms are supported and the workflow does
not depend on behavior still only proven in YAML. Use YAML when exact runtime
behavior, compatibility fixtures, or unsupported surfaces are required.

## Next Reading

- [Documentation Hub](index.md): choose the right spec, guide, or design doc.
- [Capability Status Matrix](capability_status_matrix.md): check whether a
  surface is implemented, partial, library-provided, designed, future, or legacy.
- [Workflow Drafting Guide](workflow_drafting_guide.md): author YAML workflows.
- [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md): author `.orc`
  workflows.
- [Design Documentation Index](design/README.md): route to architecture and
  migration designs.
- [Documentation Conventions](documentation_conventions.md): keep future docs
  explicit about status, authority, examples, and trust boundaries.
