# The REPL feature run

`orchestrator repl` was designed and built by the orchestrator itself on
2026-10-12: Fable drafted the plan, Codex (Sol 6.1) reviewed it, Fable revised
it, and Codex executed it in the worktree on branch `feature/orc-repl`. The
brief is `inputs.json`; the provider bindings are `providers.json`.

The workflow that ran was an earlier shape of
[`workflows/examples/design_review_execute.orc`](../../workflows/examples/design_review_execute.orc),
which flattened the plan into JSON lists of strings. That shape is retired:
the reference example now keeps the design as a markdown file and passes its
typed path. To run the same brief today:

```bash
python -m orchestrator run workflows/examples/design_review_execute.orc \
  --provider-externs-file workflows/examples/inputs/design_review_execute/providers.json \
  --input-file experiments/orc_repl_feature/inputs.json
```

The runs `20261013T012339Z-9azbib` and `20261013T014512Z-5875dy` in the
`feature/orc-repl` worktree were built from the retired sources at commit
`8a03c635`; attaching the REPL to them needs that revision checked out.
