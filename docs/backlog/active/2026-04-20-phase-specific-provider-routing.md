# Phase-Specific Provider Routing For Reusable Stacks

Active backlog item.

## Problem

Reusable design-plan-implementation stacks currently bake provider names inside imported library workflows. In practice, several stacks use `provider: codex` for every judgment-heavy step even when an operator wants different providers for different phase roles, such as Codex for design drafting/revision and Claude for review, planning, and implementation.

Because imported workflows keep private provider namespaces, a caller-level provider definition cannot reliably override provider choice inside the callee. The current EasySpin run used a PATH shim that intercepts the `codex` command and dispatches selected prompt shapes to different CLIs. That is useful for recovery, but it is not a principled workflow contract.

## Desired Outcome

Workflow authors can choose providers per phase role without editing prompt text, using PATH shims, or forking whole workflow stacks for every provider combination.

## Scope

- Major-project tranche stack:
  - roadmap draft/review/revise
  - big-design draft/review/revise
  - plan draft/review/revise
  - implementation execute/review/fix
- Generic backlog item stack if the same mechanism applies cleanly.
- Provider templates and workflow inputs/context needed to select providers by role.
- Tests or smoke checks proving imported workflows receive the intended provider role choices.

## Non-Goals

- Do not make prompt wording decide provider routing.
- Do not require runtime inspection of prompt text.
- Do not add a broad provider plugin framework before a small role-based convention is proven.
- Do not break existing workflows that assume one provider for every step.

## Candidate Design Direction

Add a small role-based provider convention for reusable stacks. For example, library workflows may expose context or inputs such as `design_author_provider`, `design_review_provider`, `plan_provider`, `implementation_provider`, and `implementation_review_provider`, with defaults preserving current behavior. The stack should pass those values into imported phases, and each phase should use explicit provider names or a documented provider-role mapping rather than relying on a single hard-coded `codex` provider.

If the DSL cannot currently express provider names from inputs/context, document the limitation and choose the smallest runtime or workflow-authoring extension needed. Avoid solving unrelated provider-session or model-selection problems in this item.

## Acceptance Criteria

- A major-project tranche workflow can run with Codex for big-design draft/revise and Claude for all other provider steps without PATH shims.
- Imported workflow boundaries make provider role propagation explicit and testable.
- Existing all-Codex/default-provider workflows remain valid.
- At least one mocked-provider runtime smoke proves that the expected provider command is invoked for design drafting/revision and a different expected provider command is invoked for review/planning/implementation.
- Documentation explains the convention and warns that prompt-text routing shims are only an operational workaround, not workflow design.
