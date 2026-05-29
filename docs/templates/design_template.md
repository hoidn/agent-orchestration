# Design Template

Use this template for design documents that introduce, change, or clarify
system behavior.

The goal is not to create a long document. The goal is to make the important
decisions explicit enough that implementation, review, testing, and future
maintenance do not have to infer architecture or invent missing contracts.

For small changes, keep the document short. Delete sections that truly do not
apply, or mark them `N/A` with one sentence explaining why. Do not keep empty
boilerplate.

## Metadata

- **Title:**
- **Status:** draft | proposed | accepted | implemented | deferred | superseded
- **Kind:** feature design | architecture decision | boundary/spec clarification | migration design | operational design | investigation/finding
- **Owner:**
- **Reviewers:**
- **Created:**
- **Last material update:**
- **Parent / related docs:**
- **Extends / replaces:**
- **Implementation target:** repo area, package, service, component, or workflow
- **Tracking issue / plan:**

## Summary

Briefly state:

- What is being designed.
- Why it matters.
- The decision or direction.
- What changes for users, callers, maintainers, or operators.

Aim for one to three paragraphs.

## Context And Authority

Explain the source of truth for this design.

Include:

- Existing behavior, documents, code paths, tests, production behavior, or external constraints this design depends on.
- Which prior docs or decisions this document accepts as authoritative.
- Which prior docs or assumptions this document changes, narrows, or supersedes.
- Any ambiguity this design resolves.

If this design depends on observed implementation behavior, identify the
relevant code paths or tests.

If this design depends on product, policy, legal, security, customer, or
operational requirements, identify those requirements.

## Problem

Describe the problem without assuming the proposed solution.

Include:

- The current limitation, inconsistency, failure mode, or opportunity.
- Who or what is affected.
- Why the problem needs a design-level decision rather than a local patch.
- What happens if this is not addressed.

## Goals

List the outcomes this design must achieve.

Good goals are concrete and reviewable.

Examples:

- Preserve a public API contract.
- Remove duplicated behavior.
- Make an invariant explicit and testable.
- Support a new workflow without changing existing callers.
- Improve debuggability, rollback safety, or operational reliability.

## Non-Goals

List things this design intentionally does not solve.

Include:

- Nearby problems deferred to later work.
- Features that may be tempting but are out of scope.
- Behaviors this design must not introduce.
- Areas where this document is not authoritative.

Non-goals should prevent scope creep and incorrect implementation assumptions.

## Decision Summary

State the proposed decision directly.

Include:

- The chosen approach.
- The main alternatives considered.
- Why the chosen approach is preferred.
- Any tradeoffs accepted.
- Any decision that remains intentionally open.

This section should be understandable without reading the entire document.

## Design Details

Describe the design in enough detail that an implementation plan does not need
to invent architecture.

Cover the relevant pieces:

- Components or modules involved.
- Ownership boundaries.
- Control flow.
- Data flow.
- State changes.
- Persistence or storage behavior.
- Build, generation, compilation, runtime, or deployment behavior.
- User-facing, API-facing, operator-facing, or developer-facing behavior.

Use diagrams, examples, pseudocode, or tables where they clarify the design.

Avoid describing only the happy path. Include the edge cases that define the
design.

## Public Contracts And Interfaces

Describe any contract this design creates, changes, or relies on.

Include relevant details for:

- APIs.
- CLI behavior.
- Configuration.
- File formats.
- Database schemas.
- Events or messages.
- Generated artifacts.
- Environment variables.
- Logs, metrics, traces, or debug output.
- User-visible behavior.
- Compatibility promises.

For each changed contract, specify:

- Old behavior.
- New behavior.
- Compatibility impact.
- Migration behavior.
- Validation rules.
- Error behavior.

If there is no contract impact, say so explicitly.

## Dependencies And Sequencing

Identify what must already be true before this design can be implemented safely.

Include:

- Required prior decisions.
- Required prior implementation work.
- Required migrations or cleanup.
- Required test infrastructure.
- Required data availability.
- Required security, policy, or operational review.
- Work that can proceed independently.
- Work that must not proceed until this design is accepted.

Also identify what this design blocks or unblocks.

## Invariants

List the rules that must remain true after implementation.

Examples:

- A value must never cross a particular boundary.
- A fallback path must not mask an error.
- Generated artifacts must preserve source provenance.
- A validator must remain the single source of truth.
- Runtime behavior must not depend on test-only fixtures.
- A migration must be idempotent.
- A retry must not duplicate side effects.

Invariants should be testable or reviewable.

## Failure Modes And Error Handling

Describe how the system behaves when things go wrong.

Include:

- Expected failure cases.
- Invalid inputs.
- Partial failures.
- Race conditions or ordering problems.
- Backward/forward compatibility failures.
- Dependency failures.
- Permission or capability failures.
- Data corruption or stale-data risks.
- Recovery behavior.
- Whether failures are compile-time, startup-time, runtime, deploy-time, or operator-visible.

Specify required diagnostics where relevant:

- Stable error classes or codes.
- User-facing messages.
- Developer-facing messages.
- Log/trace requirements.
- Source-map, provenance, or debug-location requirements.
- Conditions that must not silently fall back.

## Security, Privacy, And Permissions

State the security and privacy impact.

Include:

- New authority, permissions, credentials, or capabilities.
- Changes to data access.
- Sensitive data handled, stored, logged, displayed, or transmitted.
- Isolation boundaries.
- Tenant, user, workspace, account, or environment boundaries.
- Abuse cases.
- Auditability.
- Least-privilege considerations.
- Any required security review.

If there is no meaningful impact, say why.

## Operational Impact

Describe how this design affects operating the system.

Include, where relevant:

- Deployment behavior.
- Rollout strategy.
- Rollback strategy.
- Feature flags.
- Migrations.
- Backfills.
- Monitoring.
- Alerting.
- SLOs or reliability expectations.
- Capacity or performance impact.
- Failure recovery.
- On-call or support burden.
- Runbook changes.

For non-operational changes, mark this section `N/A` with a brief explanation.

## Performance And Resource Impact

Describe expected effects on:

- Latency.
- Throughput.
- Memory.
- Storage.
- Network usage.
- Build time.
- Startup time.
- Runtime cost.
- Developer workflow cost.

Include expected scale assumptions.

If performance is not a concern, explain why.

## Evidence And Implementation Boundaries

Identify how reviewers can tell that the implementation follows this design
rather than a helper path, fixture path, test-only path, or accidental fallback.

Include:

- Production/default code path that must provide the behavior.
- Helper, fixture, mock, generated, or fallback paths that must not be mistaken for the implementation.
- Review checks that distinguish intended behavior from incidental behavior.
- Tests that prove the intended path is used.
- Any code paths that must remain impossible, disabled, or rejected.
- Any artifacts that are evidence-only rather than source-of-truth.

This section is especially important when the design involves generated files,
test fixtures, adapters, mocks, compatibility shims, fallbacks, or phased
migrations.

## Compatibility And Migration

Describe how existing users, callers, data, docs, or workflows move from old
behavior to new behavior.

Include:

- Whether the change is backward compatible.
- Whether old and new behavior coexist.
- Migration steps.
- Data migration or backfill requirements.
- Deprecation plan.
- Cutover plan.
- Rollback plan.
- Versioning implications.
- How compatibility is tested.

If this is a new feature with no compatibility impact, say so explicitly.

## Alternatives Considered

List serious alternatives and why they were not chosen.

For each alternative, include:

- Description.
- Benefits.
- Drawbacks.
- Reason rejected or deferred.

This section should capture real tradeoffs, not strawmen.

## Verification Strategy

Describe how correctness will be proven.

Include, where relevant:

- Unit tests for local behavior.
- Integration tests across real module, service, storage, API, CLI, runtime, or workflow boundaries.
- End-to-end integration scenarios that exercise the intended path from entrypoint to observable result.
- Acceptance tests that demonstrate success criteria from the perspective of a user, caller, operator, or maintainer.
- Realistic inputs, workflows, examples, commands, requests, files, or scenarios.
- Regression tests for previously broken or risky behavior.
- Golden/oracle tests for behavior that must remain equivalent across implementations.
- Property tests or fuzz tests for broad input spaces.
- Typechecking, static validation, schema validation, or compile-time checks.
- Migration, backfill, downgrade, or rollback tests.
- Failure-mode tests for invalid inputs, partial failures, stale data, permission failures, dependency failures, and race conditions.
- Performance, scale, or resource tests.
- Security, privacy, or permissions tests.
- Manual review checks.
- Observability checks using logs, metrics, traces, dashboards, alerts, or runbooks.

Also include negative tests: cases that must be rejected, blocked, impossible,
or visibly diagnosed.

For each major goal or invariant, identify at least one test or review check
that proves it.

## Success Criteria

Define the bar for accepting the implementation.

Include:

- Required behavior.
- Required tests.
- Acceptance tests for the primary user, caller, operator, or maintainer workflows.
- At least one realistic integration or end-to-end scenario demonstrating the intended behavior.
- Negative acceptance tests proving forbidden behavior is rejected or impossible.
- Required metrics.
- Required documentation.
- Required migration evidence.
- Required review signoff.
- Required operational readiness.
- Required compatibility evidence.

Success criteria should be specific enough that a reviewer can say yes or no.

## Stop / Revise Criteria

Define when the design should be reconsidered.

Examples:

- The implementation requires violating an invariant.
- The design cannot be tested without excessive fixture-only behavior.
- The migration requires unsafe downtime.
- Performance is worse than the stated threshold.
- The design preserves the old complexity instead of reducing it.
- The design requires expanding scope beyond the accepted goals.
- A dependency proves unavailable or materially different from assumed.

This section prevents sunk-cost implementation.

## Documentation Impact

List docs that must be created or updated.

Include:

- User documentation.
- Developer documentation.
- API docs.
- Runbooks.
- Migration guides.
- Architecture docs.
- Examples.
- Templates.
- Tests-as-documentation.
- Deprecated docs to update or remove.

If no docs are affected, explain why.

## Implementation Handoff

Provide enough direction for an implementation plan.

Include:

- Suggested implementation phases.
- Files, modules, services, or packages likely to change.
- Interfaces to add, remove, or modify.
- Validation or test order.
- Known tricky areas.
- Safe first step.
- Review checkpoints.
- Work that should remain out of scope.

Do not over-prescribe code structure unless that structure is part of the design
decision.

## Open Questions

List unresolved questions.

For each question, include:

- Owner.
- Impact.
- Deadline or blocking status.
- Whether implementation may proceed before resolution.

Do not hide major design uncertainty in this section. If an open question
affects the core decision, the design may still be draft rather than accepted.

## Appendix

Optional supporting material:

- Examples.
- Extended diagrams.
- Reference snippets.
- Detailed comparison tables.
- Experiment notes.
- Prior incidents.
- Glossary.
- Links to related issues, PRs, tests, or docs.

Keep appendices clearly separate from normative design requirements.
