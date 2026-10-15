# Workflow Lisp Unified Design Work Instructions

Status: **Historical checkpoint; original body preserved.**

Historical procedure for the original unified delta, not current steering. V1/W3 are bounded implemented contracts; nested definitions, recursion and runtime closures remain separately gated/unselected under focused owners, not globally complete.

Current owner: [workflow_lisp_frontend_specification.md](../../design/workflow_lisp_frontend_specification.md).

Original proposal / historical checkpoint begins below. Its original status,
commands, measurements and tense are preserved; they do not override the current
scope notice.


Status: active target-delta instructions

Use `docs/design/workflow_lisp_unified_frontend_design.md` as the active target
design. Treat the current repository implementation, tests, shared workflow
validation, and accepted implemented `ProcRef` / `bind-proc` behavior as the
baseline.

Select and implement only the next useful increment needed to close a real gap
between the target design and the current implementation. Do not reinterpret
the target as a full replacement specification, and do not reopen already
implemented baseline behavior unless the target design explicitly requires it.
