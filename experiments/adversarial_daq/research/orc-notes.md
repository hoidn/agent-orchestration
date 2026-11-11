# Orc source audit

Source read and compiler exercised at
[`bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2`](https://github.com/hoidn/agent-orchestration/tree/bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2),
commit date 2026-10-23 01:48 UTC (October 22 Pacific). The downloaded source is
under `research/agent-orchestration-main/` in this workspace. Search-engine
snapshots of the README contained retired example paths; current source governs.

The Python API is a typed symbolic authoring layer that generates ordinary
`.orc`, then goes through the same compiler/runtime. It is not Python executing
arbitrary user control flow with magically inferred correctness. The documented
serial subset uses records, enums, variants, typed paths, lazy `when`, exhaustive
`match`, and explicit bounded-loop state. Use `py build`, `py check`, and `py run`.
[Python guide](https://github.com/hoidn/agent-orchestration/blob/bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2/docs/python_workflow_drafting_guide.md).

The maintained authoring route is evaluated `.orc` at targets 2.35–2.40. This
controller uses 2.39, typed records/results and `loop/recur`. `std/improve` is a
good review/revise helper, but its exhausted result may contain an unreviewed
last revision; this controller instead finishes each complete paired experiment
and both votes before deciding whether another round is allowed. Fresh calls
with full structured history keep the two adversaries independent without native
conversation-session dependencies.
[Library guide](https://github.com/hoidn/agent-orchestration/blob/bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2/docs/lisp_library_reference.md),
[drafting guide](https://github.com/hoidn/agent-orchestration/blob/bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2/docs/lisp_workflow_drafting_guide.md).

Compile-time checking can reject known ill-typed graph composition before
dispatch. Future provider JSON is validated at runtime, before a typed result
is committed/consumed. `must-exist` paths establish an existence contract; they
do not infer calibration validity, run identity, causality or scientific truth.
Those facts require explicit provenance and predicates. A prefix match and
mtime order alone are weak semantic evidence. Do not credit domain-specific
guard code exclusively to Orc.

Command boundaries declare a stable command and closure. Declared implementation
bytes are checked at execution/commit and on resume; closure is not a sandbox,
universal dependency discovery or rollback. Uncommitted commands may rerun;
`must_not_repeat` can make uncertain retries refuse, but does not solve arbitrary
external exactly-once effects. Evaluated commands have no automatic runtime
timeout at this pin, so the runner bounds its child processes explicitly.
[Command contract](https://github.com/hoidn/agent-orchestration/blob/bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2/docs/design/workflow_command_adapter_contract.md),
[CLI contract](https://github.com/hoidn/agent-orchestration/blob/bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2/specs/cli.md).

A concrete authoring limitation was encountered during this implementation:
returning a `Round` record whose nested records were populated directly from
bound provider values produced `workflow_return_not_exportable`. Explicit nested
record constructors compile. The workaround remains visible in
`adversarial.orc`; count it when judging ergonomics. Evidence is the actual pinned
compiler diagnostic and `procedure_specialization.py::_record_expr_value_at_path`,
not a claim that every nested-record composition fails.

The default `claude` provider invokes its installed CLI and preserves that CLI's
ordinary permission behavior. Both roles use that provider for model parity;
they are distinct prompts/fresh calls, not a claim of independent model families.
The built-in `codex` provider at this pin includes
`--dangerously-bypass-approvals-and-sandbox`; do not silently switch to it on a
credentialed host. Provider selection is an execution-environment concern,
separate from workflow typing.
[Registry source](https://github.com/hoidn/agent-orchestration/blob/bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2/orchestrator/providers/registry.py).

The proposed advantage is consequently a hypothesis about enforceable declared
contracts, explicit dependency/recovery semantics, auditability or measured
engineering burden. It is not established by compiling this controller.
