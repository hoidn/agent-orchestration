# Backlog Item: Restore Injected Design Template Asset

- Status: active
- Created on: 2026-04-14
- Plan: none yet

## Scope
Revisit the temporary `docs/templates/design_template.md` design-template arrangement and restore the preferred workflow-bundled prompt-asset version when it will not disrupt active runs.

The current docs-template placement was chosen so already-running workflows can pick up the template through existing prompt text without requiring a workflow restart. The longer-term shape should make reusable workflows carry their own design template as a source-relative asset, using `asset_depends_on`, so copied workflow stacks do not depend on a separately maintained docs file being present in the target checkout.

## Required Work
- Confirm there are no active workflows that need the docs-template workaround to affect future design steps without restart.
- Decide whether `docs/templates/design_template.md` should remain as a human-facing copy, become a pointer to the workflow asset, or be removed after the injected asset is restored.
- Restore a workflow-bundled template under `workflows/library/prompts/common/design_template.md` or an equivalent prompt-asset path.
- Wire `DraftDesign` and `DraftBigDesign` to inject the template with `asset_depends_on`.
- Keep the design drafting prompts concise: they should tell the agent to use the injected template and omit irrelevant optional sections.
- Sync the workflow asset, YAML, and prompt wording to downstream workflow copies that are expected to run from their own checkout.
- Regenerate or check `docs/workflow_prompt_map.md` so the injected asset appears in the prompt map.

## Non-Goals
- Do not require active workflows to restart just to see the design template.
- Do not make the design template a mandatory rigid schema for every small change.
- Do not duplicate substantive design instructions in YAML and prompt prose.
- Do not add prompt-phrasing tests.

## Success Criteria
- Reusable design workflows carry the design template with the workflow source tree.
- `docs/workflow_prompt_map.md` lists the injected design template asset for the relevant design-drafting steps.
- Downstream copies can be validated with orchestrator dry-runs after the sync.
- Any remaining docs-template file has a clear role and does not silently drift from the injected asset.
