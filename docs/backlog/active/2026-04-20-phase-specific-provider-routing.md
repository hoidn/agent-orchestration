# KISS Provider Role Routing For Reusable Stacks

Active backlog item.

Plan: `docs/plans/2026-05-01-kiss-provider-role-routing-implementation-plan.md`

## Problem

Reusable design-plan-implementation stacks currently bake provider names inside imported library workflows. In practice, several stacks use `provider: codex` for every judgment-heavy step even when an operator wants different providers for different phase roles, such as Codex for design drafting/revision and Claude for review, planning, and implementation.

Because imported workflows keep private provider namespaces, a caller-level provider definition cannot reliably override provider choice inside the callee. The current EasySpin run used a PATH shim that intercepts the `codex` command and dispatches selected prompt shapes to different CLIs. That is useful for recovery, but it is not a principled workflow contract.

## Desired Outcome

Workflow authors can choose providers for specific reusable-stack roles, such as `ExecuteImplementation`, without editing prompt text, using PATH shims, or forking whole workflow stacks for every provider combination.

## Scope

- Add the smallest DSL/runtime support needed for provider names to be resolved from workflow data, for example `provider: "${context.implementation_execute_provider}"`, with deterministic validation before provider launch.
- Define role-specific provider settings in reusable library workflows, starting with:
  - `implementation_execute_provider`
  - `implementation_review_provider`
  - `implementation_fix_provider`
- Keep provider templates local to the callee workflow scope. The callee should define the supported aliases, such as `codex` and `claude_opus`.
- Pass role values through imported workflow calls where the top-level stack needs to override defaults.
- Apply first to the NeurIPS/generic backlog implementation phase and then to the major-project tranche stack if the same convention remains clean.
- Add tests or smoke checks proving imported workflows receive the intended provider role choices.

## Non-Goals

- Do not make prompt wording decide provider routing.
- Do not require runtime inspection of prompt text.
- Do not add a broad provider plugin framework before this role-based convention is proven.
- Do not add arbitrary provider maps or implicit caller/callee provider namespace merging.
- Do not make model inheritance part of the first fix beyond ordinary provider template defaults and `provider_params`.
- Do not break existing workflows that assume one provider for every step.

## Candidate Design Direction

Add a small role-based provider convention for reusable stacks. Library workflows expose context or inputs with defaults preserving current behavior:

```yaml
context:
  implementation_execute_provider: codex
  implementation_review_provider: codex
  implementation_fix_provider: codex

providers:
  codex: ...
  claude_opus: ...

steps:
  - name: ExecuteImplementation
    provider: "${context.implementation_execute_provider}"

  - name: ReviewImplementation
    provider: "${context.implementation_review_provider}"

  - name: FixImplementation
    provider: "${context.implementation_fix_provider}"
```

The caller passes role values through `call.with` only when it wants a different assignment:

```yaml
with:
  implementation_execute_provider: claude_opus
  implementation_review_provider: codex
  implementation_fix_provider: codex
```

If the DSL cannot currently express provider names from inputs/context, implement that narrow substitution and validation path. Avoid solving unrelated provider-session, model-selection, provider-map, or plugin problems in this item.

## Acceptance Criteria

- A workflow can run `ExecuteImplementation` with `claude_opus` while review/fix steps still use `codex`, without PATH shims.
- Imported workflow boundaries make provider role propagation explicit and testable.
- Existing all-Codex/default-provider workflows remain valid.
- Invalid provider role values fail before provider launch with a clear contract error.
- At least one mocked-provider runtime smoke proves that the expected provider command is invoked for `ExecuteImplementation` and a different expected provider command can be invoked for review/fix.
- Documentation explains the convention and warns that prompt-text routing shims are only an operational workaround, not workflow design.
