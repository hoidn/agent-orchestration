# Workflow Lisp Native Transportable Returns: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_native_transportable_returns.md](../../design/workflow_lisp_native_transportable_returns.md).

## Implementation Handoff

The safe first implementation step is to add declarative RED tests for a
root-valued `Bool` across frontend typechecking, contract derivation, prompt
metadata, runtime validation, source attribution, and workflow-call binding.
Then introduce the shared transportability/result-contract model before
widening individual effect or workflow guards.

Suggested native-return phases:

1. shared result type and contract model;
2. provider/command root lowering and prompt shape;
3. workflow/procedure/call binding across classic and WCC routes;
4. source maps, runtime plans, state, resume, dashboard, and adjudication;
5. compatibility and end-to-end evidence; and
6. normative and authoring documentation.

Suggested guidance phases:

1. `ReturnSpec` and field metadata syntax;
2. compile-time metadata/example validation;
3. schema/import/specialization/flattening propagation;
4. executable guidance schema and prompt rendering;
5. runtime-neutrality and end-to-end evidence; and
6. documentation and capability promotion.

Plans must name exact owning modules after the current migration sequence and
must use narrow tests before integration, smoke, parity, and broader gates.
