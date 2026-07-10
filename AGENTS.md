# AGENTS.md

Read `docs/index.md` before making changes.

Documentation routing:
- Start at `docs/index.md` for current docs/spec routing.
- Use `docs/capability_status_matrix.md` to check whether a surface is implemented, partial, library-provided, designed, future, or legacy before copying it.
- Use `docs/design/README.md` to choose the relevant design doc; `MIND_MAP.md` is a secondary orientation map, not the agent entry point.

Repo expectations:
- Read `docs/index.md` before deciding what docs or specs govern the task.
- Use the `tmux` skill when launching long-running commands.
- After narrow selectors, run broad, slow, or full pytest suites with
  `pytest -q -n 16 --dist=worksteal`; keep long runs in tmux.
- When executing plans, use Subagent-Driven execution without asking for confirmation
- When launching workflows for EasySpin, `/home/ollie/Documents/PtychoPINN`, or its paper repo `/home/ollie/Documents/ptychopinnpaper2`, run the workflow process in the `ptycho311` environment, including tmux-launched workflows.
- For tmux-launched EasySpin, PtychoPINN, or paper workflows, prefer sourcing conda, activating `ptycho311`, and then invoking `python -m orchestrator` directly so tmux shows live output; if you use `conda run`, include `--no-capture-output`.
- Write plans under `docs/plans/` before large edits.
- Keep changes scoped to the task; avoid unrelated refactors.
- Run commands from the repo root so imports, relative paths, and fixture layout stay stable.
- Treat fresh command output as required verification evidence.
- Prefer the narrowest relevant `pytest` selectors first.
- If you add or rename tests, run `pytest --collect-only` on those modules.
- Changes to workflows, prompts, artifact contracts, provisioning, or demo trial mechanics should rerun at least one orchestrator/demo smoke check in addition to unit tests.
- For DSL, frontend, runtime, or reusable workflow changes, include an end-to-end usage or integration check, or state why isolated checks are enough.
- Do not add or keep tests that assert literal prompt text or prompt phrasing. Prefer behavioral, contract, artifact-lineage, or dataflow assertions that stay valid when prompts are revised.

Do not assume success from inspection alone when runnable checks are available.
Do not weaken verification just to make a failure disappear.
Do not create worktrees, especially not when executing plans or implementing features
When a workflow run has already passed an approval/review gate and later fails downstream, prefer `orchestrator resume <run_id>` over launching a fresh run unless you intentionally want to redo the earlier gated stages.

Development rules:
1. When interacting with the user ask, don't assume. If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements. When running unattended, pick the most reasonable interpretation, proceed, and record the assumption rather than blocking.
2. Implement the most direct, maintainable solution. Solve simple problems simply and harder problems with careful design. Do not add speculative abstractions for needs that don't exist yet. Before implementing a solution, state your approach in 1–2 sentences and explicitly list what this approach makes harder down the line
3. Stay in scope, but maintain the ecosystem. Do not make unprompted cosmetic changes to unrelated code. However, if modifying adjacent code is genuinely necessary to abstract common logic, update a shared interface/type signature, or prevent a regression, that is in scope. Ensure your local changes do not silently break adjacent systems.
4. Flag uncertainty explicitly. If you're unsure about something, see point 1 above. If it makes sense to do so, conduct a small, localised and low-risk experiment and bring the hypothesis and results to me to discuss. Confidence without certainty causes more damage than admitting a gap.
5. When interacting with the user developing designs don't hesitate to suggest a better way, or one that has long lasting impact over a tactical change. (as a few examples)
