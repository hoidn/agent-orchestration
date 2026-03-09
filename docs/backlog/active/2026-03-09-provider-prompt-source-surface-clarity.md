# Backlog Item: Provider Prompt Source Surface Clarity

- Status: active
- Created on: 2026-03-09
- Plan: `docs/plans/2026-03-09-provider-prompt-source-surface-clarity-implementation-plan.md`

## Scope
Resolve the recurring abstraction confusion where provider-step prompt source fields such as `input_file` are mistaken for workflow business inputs. Clarify the contract split between workflow-boundary `inputs`, runtime data dependencies, and provider prompt sources; clean up examples/docs to reflect that split; and, if docs alone are insufficient, evaluate a compatibility-preserving naming improvement or advisory lint in a follow-up.
