# Shared `std/phase` Owner-Lane Self-Hosting Regression Reopen

Status: implementation architecture
Design gap id: `workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-regression-reopen`

## Scope

Restore builtin `std/phase` self-hosting so its exported review/fix types and
helpers resolve through the ordinary linked stdlib route.

The concrete failure is local type resolution for `std/phase` definitions such
as `ReviewLoopResult`. The fix belongs in stdlib module graph/type-environment
construction or in the `std/phase.orc` declarations themselves.

## Implementation Shape

Compile `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` as a normal
builtin module with its local and qualified-local type references available
before downstream modules consume it. Downstream Design Delta modules should
continue to import `std/phase`; they should not copy review-loop types or add
family-local aliases to bypass the shared issue.

Do not repair this by adding compiler-name special cases, report parsing,
pointer reads, command glue, or compatibility-bundle rereads.

## Out Of Scope

- redesigning `review-revise-loop` behavior;
- changing `std/drain`, `std/resource`, selector, gap-drafter, work-item, or
  finalization semantics;
- retiring unrelated compatibility intrinsics;
- replacing provider validators;
- inventories, conformance summaries, parity manifests, closeout artifacts, or
  bridge/publication validation; and
- broad build-artifact checks.

## Acceptance

Focused `std/phase` tests compile and validate the builtin module, including
local and qualified-local references to its exported types. The Design Delta
parent compile may be run as a downstream regression check after the shared
module passes, but it is not a substitute for the owner-lane stdlib test.
