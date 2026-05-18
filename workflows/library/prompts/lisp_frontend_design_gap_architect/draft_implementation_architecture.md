Read the injected steering, full design, MVP design, progress ledger, and
selector bundle before acting.

Draft exactly one implementation architecture for the selected Lisp frontend
design gap. Keep the scope bounded to the selected gap.

Write:

- an implementation architecture Markdown file at the target architecture path;
- a work-item context Markdown file at the target context path;
- a JSON list of deterministic check commands at the target check-commands
  path;
- the draft bundle JSON at the output-contract path.

Do not edit source code, backlog queues, run state, or unrelated docs.

Use this bundle shape:

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

If the gap cannot be safely architected:

```json
{
  "draft_status": "BLOCKED",
  "reason": "short reason"
}
```
