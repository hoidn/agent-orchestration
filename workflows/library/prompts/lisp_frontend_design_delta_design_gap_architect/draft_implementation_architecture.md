Read the steering, target design, command-adapter contract, typed design-gap
subject record, and architecture targets before acting. The baseline design path
is available as the accepted baseline design contract.
When the subject record includes selected docs or `attempt_history_summary`, use
that context to avoid redrafting stale or already-blocked assumptions.

Draft a single implementation-architecture document for exactly the selected
target-design gap. The baseline design is the accepted baseline design contract
and not the active work queue. This is an implementation architecture, not a
replacement product design/spec. Keep the scope bounded to the selected gap. Do
not draft multiple alternative architectures, do not cover multiple design gaps,
and do not broaden the scope beyond the selected gap.

If the selected gap changes a file that is used outside the selected gap's
files, describe the rule those outside uses should follow too.

Use `docs/templates/design_gap_implementation_architecture_template.md` as the
structure guide when helpful. Do not use the general
`docs/templates/design_template.md` as the default shape for this output; that
template is for system/spec-level designs, not bounded gap architectures.
Keep procedure out of the architecture file. Describe ownership, constraints,
allowed and forbidden implementation shapes, source surfaces, and acceptance
conditions. Do not include task order, command-order checklists, or recovery
procedure. Every acceptance condition and check command must be traceable to
the target design or to behavior whose consumer you verified is live in the
current checkout; classify any failing pre-existing check as a live contract
to satisfy or a stale artifact to exclude before including it.

Stay consistent with existing architecture in the checkout. Reuse established
module names, data types, and ownership boundaries unless the selected gap
requires changing them.

Treat `workflow_command_adapter_contract.md` as authoritative whenever the
architecture proposes scripts, command steps, legacy adapters, or
runtime-native promotion.

List `docs/design/workflow_command_adapter_contract.md` in the generated
work-item context's authoritative inputs when the slice may touch scripts,
command steps, adapters, or runtime-native effects.

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
  "design_gap_id": "<request.subject.design_gap_id>",
  "architecture_path": "<request.targets.architecture_path>",
  "work_item_context_path": "<request.targets.work_item_context_path>",
  "check_commands_path": "<request.targets.check_commands_path>",
  "plan_target_path": "<request.targets.plan_target_path>",
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
