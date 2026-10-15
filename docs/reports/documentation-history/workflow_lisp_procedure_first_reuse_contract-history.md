# Workflow Lisp Procedure First Reuse Contract: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_procedure_first_reuse_contract.md](../../design/workflow_lisp_procedure_first_reuse_contract.md).

## Feasibility Evidence

The design is grounded by three distinct cases rather than by a compile-only
prototype:

- `std/drain.orc::backlog-drain-proc` demonstrates generic, effectful,
  ProcRef-composed inline procedure behavior on the promoted Design Delta
  route.
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc::tracked-plan-phase`
  is an ordinary non-drain internal workflow with typed results and provider
  effects beneath a retained public stack wrapper. It is a positive migration
  candidate, subject to the full migration test.
- `workflows/library/lisp_frontend_design_delta/drain.orc::drain` is a negative
  case: it owns the promoted external run/resume and terminal publication
  contract and therefore remains a workflow even if its internal helpers move
  to procedures.

These examples prove that the boundary classification is meaningful. They do
not claim that every effect family or inventory row is already migratable.
