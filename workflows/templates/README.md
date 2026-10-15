# Workflow Templates

New workflow families start from a registry-approved Workflow Lisp `.orc`
example and adapt typed procedures and contracts; do not create another
YAML/YML template here.

## Template Routes

| Purpose | Starting point | Status |
| --- | --- | --- |
| New template | [Plan, review and execute](../examples/plan_review_execute.orc) | Current evaluated 2.35 example; use the provider manifest and compile command in its header. Live execution requires the configured providers. |
| Review/revise template | [`std/improve` proposal example](../examples/improve_experiment_proposal.orc) | Current bounded 2.36 example; use its manifests and the workspace-owned `scripts/launch_experiment.py`, which is not supplied by the example. |

For a review/revise loop, use the [std/improve reference](../../docs/lisp_library_reference.md#review-and-revise-with-stdimprove)
and its manifest/workspace prerequisites. The former
[`review_revise_design_docs.orc`](../../tests/fixtures/workflow_lisp/retired_examples/review_revise_design_docs.orc)
template is historical; its old executable entry is retired.
