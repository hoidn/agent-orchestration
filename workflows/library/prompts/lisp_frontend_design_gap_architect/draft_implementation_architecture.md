Read the listed steering, target design, baseline design, command-adapter
contract, progress ledger, selector bundle, architecture target contract, and
existing implementation architecture index from the checkout before acting.

Draft a single implementation-architecture document for exactly the selected
target-design gap. The baseline design is a compatibility constraint, not the
active work queue. This is an implementation architecture, not a replacement
product design/spec. Keep the scope bounded to the selected gap. Do not draft
multiple alternative architectures, do not cover multiple design gaps, and do
not broaden the scope beyond the selected gap.

Preserve coherence with prior implementation architecture documents listed in
the architecture index:

- review the listed architecture documents before drafting;
- reuse established package/module names, data types, and ownership boundaries
  unless there is a stated reason not to;
- do not redefine shared concepts such as spans, diagnostics, Core Workflow
  AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or
  variant proof;
- declare the files/components owned by this slice and the shared components it
  intentionally does not own;
- if this slice must revise a prior decision, state the conflict and the reason
  explicitly.

Treat `workflow_command_adapter_contract.md` as authoritative whenever the
architecture proposes scripts, command steps, legacy adapters, or
runtime-native promotion.

List `docs/design/workflow_command_adapter_contract.md` in the generated
work-item context's authoritative inputs when the slice may touch scripts,
command steps, adapters, or runtime-native effects.

Include a section named `Relationship To Existing Implementation Architectures`
with:

- existing slices reviewed;
- decisions reused;
- new decisions in this slice;
- conflicts or revisions.

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
  "design_gap_id": "<design_gap_id from selection bundle>",
  "architecture_path": "<architecture_path from architecture-targets.json>",
  "work_item_context_path": "<work_item_context_path from architecture-targets.json>",
  "check_commands_path": "<check_commands_path from architecture-targets.json>",
  "plan_target_path": "<plan_target_path from architecture-targets.json>",
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
