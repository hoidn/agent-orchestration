# Design Template

Use this template for design documents that introduce, change, or clarify
system behavior, architecture, public contracts, migration policy, or
operational behavior. Keep it short for small changes. Delete sections that do
not apply, or mark them `N/A` with one sentence explaining why.

Do not use this as the default structure for a bounded design-gap architecture
or `implementation_architecture.md` file. A gap architecture is narrower: it
applies an accepted design to one selected missing slice. Use
[`design_gap_implementation_architecture_template.md`](design_gap_implementation_architecture_template.md)
for that case.

The purpose is to make decisions, contracts, risks, and verification clear
enough that implementation and review do not have to infer missing architecture.

## Metadata

- **Title:**
- **Status:** draft | proposed | accepted | implemented | deferred | superseded
- **Kind:** feature | architecture decision | clarification | migration | operational design | finding
- **Owner:**
- **Reviewers:**
- **Created:**
- **Last material update:**
- **Related docs / issues / plans:**
- **Implementation target:**

## Summary

State what is being designed, why it matters, the recommended direction, and
what changes for users, callers, maintainers, or operators.

Aim for one to three paragraphs.

## Context And Authority

Identify the source of truth for this design.

- Existing behavior, docs, specs, code paths, tests, or external constraints.
- Prior decisions this document accepts, narrows, replaces, or supersedes.
- Ambiguity this design resolves.
- Implementation behavior this design relies on, with code paths or tests when relevant.

## Problem

Describe the problem without assuming the solution.

- Current limitation, inconsistency, failure mode, or opportunity.
- Who or what is affected.
- Why this needs a design-level decision rather than a local patch.
- Consequence of not addressing it.

## Goals And Non-Goals

List the outcomes this design must achieve.

Good goals are concrete and reviewable.

List what this design intentionally does not solve, including tempting nearby
features, deferred work, and behavior this design must not introduce.

## Decision

State the decision directly.

- Chosen approach.
- Main alternatives considered.
- Why this approach is preferred.
- Tradeoffs accepted.
- Decisions intentionally left open.

This section should be understandable without reading the whole document.

## Design Details

Describe the design in enough detail that an implementation plan does not need
to invent architecture.

Cover only the relevant pieces:

- Components or modules involved.
- Ownership boundaries.
- Control flow and data flow.
- State, persistence, generated output, or runtime behavior.
- User-facing, API-facing, operator-facing, or developer-facing behavior.
- Important edge cases.

Use diagrams, examples, pseudocode, or tables when they clarify the design.

## Contracts And Interfaces

Describe any contract this design creates, changes, or relies on.

Examples include APIs, CLI behavior, configuration, file formats, schemas,
events, generated artifacts, logs, metrics, traces, or user-visible behavior.

For changed contracts, state:

- Old behavior.
- New behavior.
- Compatibility impact.
- Validation and error behavior.

If there is no contract impact, say so explicitly.

## Dependencies And Sequencing

Identify what must be true before this design can be implemented safely.

- Required prior decisions or implementation work.
- Required migration, cleanup, data, test infrastructure, or review.
- Work that can proceed independently.
- Work that must wait for this design.
- Work this design blocks or unblocks.

## Invariants And Failure Modes

List the rules that must remain true after implementation.

Examples:

- A validator remains the single source of truth.
- A fallback path must not mask an error.
- Generated artifacts preserve source provenance.
- Runtime behavior does not depend on test-only fixtures.
- A retry or migration does not duplicate side effects.

Describe expected failure cases and required behavior:

- Invalid inputs or stale data.
- Partial failures or ordering problems.
- Permission or dependency failures.
- Compatibility failures.
- Recovery behavior.
- Stable diagnostics, logs, source maps, or user-facing messages when relevant.

## Security, Operations, And Performance

State material impact on security, privacy, permissions, operations, and
performance.

Cover only what applies:

- New authority, credentials, capabilities, or data access.
- Sensitive data handled, stored, logged, displayed, or transmitted.
- Deployment, rollout, rollback, monitoring, alerting, or runbook impact.
- Latency, throughput, memory, storage, network, build, startup, or runtime cost.

If there is no meaningful impact, say why.

## Evidence And Implementation Boundaries

Explain how reviewers can tell that the implementation follows this design
rather than a helper path, fixture path, test-only path, or accidental fallback.

Include:

- Default code path that must provide the behavior.
- Helper, fixture, mock, generated, adapter, shim, or fallback paths that must
  not be mistaken for the implementation.
- Tests or review checks that prove the intended path is used.
- Artifacts that are evidence-only rather than source-of-truth.

Use this section especially for generated files, fixtures, adapters, mocks,
compatibility shims, fallbacks, and phased migrations.

## Compatibility And Migration

Describe how existing users, callers, data, docs, or workflows move from old
behavior to new behavior.

- Backward compatibility.
- Old/new coexistence.
- Migration, backfill, cutover, rollback, and deprecation.
- Versioning implications.
- Compatibility tests.

If there is no compatibility impact, say so explicitly.

## Verification Strategy

Describe how correctness will be proven.

Include the checks that matter for this design:

- Unit tests for local behavior.
- Integration tests across real module, service, storage, API, CLI, runtime, or workflow boundaries.
- Declarative acceptance / integration scenarios that specify expected behavior at the public contract level.
- End-to-end tests when the full deployed or user-facing path needs coverage.
- Regression, golden/oracle, migration, failure-mode, performance, security, or observability checks when relevant.
- Negative tests for behavior that must be rejected, blocked, impossible, or visibly diagnosed.

For each major goal or invariant, identify at least one test, scenario, or
review check that proves it.

## Declarative Acceptance / Integration Scenarios

For designs that change behavior across boundaries, include at least one
scenario written at the same abstraction level as the design contract.

A good scenario should specify:

- Initial state, fixtures, inputs, configuration, or existing data.
- Public entrypoint used by the caller, operator, workflow, API, CLI, file, event, or system boundary.
- Expected observable result.
- Required diagnostics, emitted artifacts, state changes, logs, metrics, or outputs.
- Important invariants that must hold.
- Negative or forbidden behavior that must not occur.
- Which dependencies are real, stubbed, simulated, or fixture-backed.
- Why the scenario proves the intended integration path rather than a helper path, mock path, or test-only shortcut.

Avoid asserting private implementation details unless those details are part of
the design contract.

## Success Criteria

Define the bar for accepting the implementation.

Include:

- Required behavior.
- Required tests.
- Required docs or examples.
- Required migration, compatibility, operational, or metric evidence.
- Required review signoff.
- Declarative acceptance / integration scenarios for the primary behavior.
- Negative acceptance scenarios for behavior that must be rejected, blocked, impossible, or visibly diagnosed.
- Evidence that acceptance scenarios exercise the intended integration path rather than a helper, fixture-only, mock-only, or fallback path.

## Stop / Revise Criteria

Define when the design should be reconsidered.

Examples:

- Implementation requires violating an invariant.
- The design cannot be tested without relying on fixture-only behavior.
- Migration or rollout proves unsafe.
- Performance is worse than the stated threshold.
- Scope expands beyond the accepted goals.
- A dependency proves unavailable or materially different from assumed.

## Documentation Impact

List docs that must be created, updated, deprecated, or removed.

Include user docs, developer docs, API docs, runbooks, migration guides,
architecture docs, examples, templates, or tests-as-documentation when relevant.

If no docs are affected, say why.

## Implementation Handoff

Provide enough direction for an implementation plan.

- Suggested phases.
- Files, modules, services, workflows, or packages likely to change.
- Interfaces to add, remove, or modify.
- Validation or test order.
- Known tricky areas.
- Safe first step.
- Review checkpoints.
- Work that should remain out of scope.

Do not over-prescribe code structure unless that structure is part of the
design decision.

## Open Questions

List unresolved questions with owner, impact, deadline or blocking status, and
whether implementation may proceed before resolution.

Do not hide major design uncertainty here. If an open question affects the core
decision, the design may still be draft rather than accepted.

## Appendix

Optional supporting material: examples, diagrams, comparisons, experiment notes,
prior incidents, glossary, and links to related issues, PRs, tests, or docs.

Keep appendices clearly separate from normative design requirements.
