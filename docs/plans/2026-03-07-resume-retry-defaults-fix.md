# Resume Retry Defaults Fix

**Goal:** Prevent `orchestrate resume` from crashing provider steps when retry settings are omitted.

## Scope

- Keep the fix narrow to resume-time retry defaults and defensive retry-policy handling.
- Add regression coverage for both the CLI resume path and the retry helper.

## Plan

1. Add a failing resume-command test proving `resume_workflow()` must supply concrete retry defaults to `WorkflowExecutor`.
2. Add a failing retry-policy test proving `RetryPolicy` must tolerate `None` retry values without crashing.
3. Patch `resume_workflow()` to normalize retry defaults before constructing/executing the workflow.
4. Harden `RetryPolicy` against `None` values so similar call sites fail safe instead of crashing.
5. Run narrow pytest selectors plus collection checks for the touched test modules.
