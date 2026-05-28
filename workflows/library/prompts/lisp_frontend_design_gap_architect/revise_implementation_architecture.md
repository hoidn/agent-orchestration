Read the listed steering, target design, baseline design, command-adapter
contract, progress ledger, selector bundle, architecture target contract, existing
implementation architecture index, current implementation architecture,
generated work-item context, generated check commands, and architecture review
report from the checkout before acting.

Revise the implementation architecture for exactly the selected target-design
gap to address the review findings.

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
  "design_gap_id": "procref-static-surface-and-resolution",
  "architecture_path": "<architecture_path from architecture-targets.json>",
  "work_item_context_path": "<work_item_context_path from architecture-targets.json>",
  "check_commands_path": "<check_commands_path from architecture-targets.json>",
  "plan_target_path": "<plan_target_path from architecture-targets.json>",
  "summary": "short summary"
}
```
