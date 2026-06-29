Read the listed steering, target design, baseline design, command-adapter
contract, progress ledger, typed design-gap subject record, architecture
targets, existing implementation architecture index, current implementation
architecture, generated work-item context, generated check commands, and
architecture review report from the checkout before acting.

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
Keep procedure out of the architecture file. Task order, command-order
checklists, workflow recovery procedure, and manifest/report refresh chores
do not belong in `implementation_architecture.md`.

Do not edit source code, backlog queues, run state, or unrelated docs.

The revised draft bundle must keep this shape:

```json
{
  "draft_status": "DRAFTED",
  "design_gap_id": "<request.subject.design_gap_id>",
  "architecture_path": "<request.targets.architecture_path>",
  "work_item_context_path": "<request.targets.work_item_context_path>",
  "check_commands_path": "<request.targets.check_commands_path>",
  "plan_target_path": "<request.targets.plan_target_path>",
  "summary": "short summary"
}
```
