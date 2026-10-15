# The REPL feature run

`orchestrator repl` was designed and built by the orchestrator itself on
2026-10-12: Fable drafted the plan, Codex (Sol 6.1) reviewed it, Fable revised
it, and Codex executed it in the worktree on branch `feature/orc-repl`. The
brief is `inputs.json`; the provider bindings are `providers.json`.

That 2026-10-12 run used Fable. `planner_model` now defaults to `claude-opus-5-5`, because experiments no longer use
Fable models (owner, 2026-10-15).

`repl_feature.orc` is the variation of
[`workflows/examples/design_review_execute.orc`](../../workflows/examples/design_review_execute.orc)
whose prompts name the documents, code and contracts this feature touches. It
compiles with the command in its header and runs with:

```bash
python -m orchestrator run experiments/orc_repl_feature/repl_feature.orc \
  --provider-externs-file experiments/orc_repl_feature/providers.json \
  --input-file experiments/orc_repl_feature/inputs.json
```

The runs `20261013T012339Z-9azbib` and `20261013T014512Z-5875dy` in the
`feature/orc-repl` worktree were built from an earlier shape of this file that
flattened the plan into JSON lists (commit `8a03c635`); attaching the REPL to
them needs that revision checked out.
