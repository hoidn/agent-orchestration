Read the listed steering, full design, MVP design, command-adapter contract,
progress ledger, selector bundle, architecture target contract, existing
implementation architecture index, current implementation architecture,
generated work-item context, generated check commands, and architecture review
report from the checkout before acting.

Revise the implementation architecture for exactly the selected Lisp frontend
design gap to address the review findings.

Update the same target files that the draft step produced:

- implementation architecture Markdown;
- work-item context Markdown;
- check-command JSON list;
- draft bundle JSON.

Keep the scope bounded to the selected gap. Preserve coherence with prior
implementation architecture documents and do not redefine shared concepts unless
the review report requires a clearly justified correction.

Do not edit source code, backlog queues, run state, or unrelated docs.

The revised draft bundle must keep this shape:

```json
{
  "draft_status": "DRAFTED",
  "design_gap_id": "parser-syntax",
  "architecture_path": "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md",
  "work_item_context_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md",
  "check_commands_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json",
  "plan_target_path": "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md",
  "summary": "short summary"
}
```
