# Live Git-Mutating Workflow Docs

Goal: document how to avoid human/workflow git-state collisions for workflows that stage, commit, reset, or otherwise treat the checkout as part of their runtime state.

Scope:
- `agent-orchestration` docs: add a narrow authoring/runtime note that this is a special-case concern for git-mutating workflows, not a universal workflow rule.
- `PtychoPINN` docs: add concrete operator conventions for the current backlog and `lines_256` loops, and make them discoverable from the main docs index.

Planned edits:
1. Update `docs/orchestration_start_here.md` and `docs/workflow_drafting_guide.md` in `agent-orchestration` with a special-case note for workflows that mutate git state.
2. Update `docs/index.md` in `agent-orchestration` so the note is discoverable from the docs hub.
3. Update `docs/workflows/orchestration_start_here.md` in `PtychoPINN` with repo-local live-run coexistence rules.
4. Update `docs/workflows/agent_orchestration_backlog_loop.md` and `docs/studies/lines_256_arch_improvement_loop.md` in `PtychoPINN` with concrete operator guidance for live git-mutating runs.
5. Update `docs/index.md` and `docs/studies/index.md` in `PtychoPINN` so readers can find the convention without repo archaeology.

Verification:
- `git diff --check` on all touched docs in both repos
- `rg` confirmation that the new coexistence guidance is reachable from each repo index
