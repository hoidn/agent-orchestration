Read `AGENTS.md` and `docs/index.md` first if they exist in the current repo.

You are coordinating one direct-vs-workflow demo trial for this repository.

Your job is to:
- provision equivalent fresh workspaces for the direct arm and workflow arm
- launch the trial using the repo's existing coordinator tooling
- inspect the archived outputs
- summarize the result precisely, including any operational gaps

Use the existing scripts and workflow definitions in this repo rather than inventing a new process.

## Inputs You Need

You need these runtime inputs before starting:
- path to the task seed repository
- path to the task markdown file
- path to an empty experiment root directory

Optional:
- explicit seed commit or commitish
- explicit workflow YAML path
- explicit direct-arm prompt override

## Required Process

1. Verify the seed repo and task file exist.
2. Verify the experiment root is empty or does not exist yet.
3. Run the built-in coordinator:

```bash
python scripts/demo/run_trial.py \
  --seed-repo <seed-repo> \
  --experiment-root <experiment-root> \
  --task-file <task-file>
```

4. If the trial runner exits non-zero, do not assume failure details. Read the archived outputs and evaluator results first.
5. Inspect these files after the run:
- `<experiment-root>/trial-metadata.json`
- `<experiment-root>/archive/direct-command.json`
- `<experiment-root>/archive/workflow-command.json`
- `<experiment-root>/archive/direct-run-metadata.json`
- `<experiment-root>/archive/workflow-run-metadata.json`
- `<experiment-root>/archive/trial-result.json`
6. Report:
- start commit
- direct-arm command
- workflow-arm command
- direct-arm exit code
- workflow-arm exit code
- evaluator verdict for each arm, if present
- notable failure categories, if present
- the location of the archived result file

## Constraints

- Do not modify the seed repo just to make provisioning easier.
- Do not manually perform the direct run and workflow run if the built-in runner can do it.
- Do not patch prompts or workflow files during the trial unless the user explicitly asks for experiment-definition changes.
- Do not claim the runs were parallel. The current built-in runner provisions parallel directories but executes the two arms serially.
- Do not claim a seed was evaluated if the runner did not dispatch an evaluator for it.

## If Evaluator Output Is Missing

If `trial-result.json` shows `null` evaluation results for one or both arms:
- state that the run completed without evaluator integration for that seed
- report command exit codes and archived metadata anyway
- call out that evaluator dispatch is currently seed-specific and incomplete

## Expected Final Summary

Your final summary should be concrete and operational. Include:
- what command you ran
- where the experiment root is
- whether provisioning succeeded
- whether the direct and workflow executions succeeded
- whether evaluator results were produced
- the most important limitation still present in the coordination path

The most likely current limitation is that the built-in runner is serial and only has mocked-subprocess coverage for its orchestration path unless a real local trial was just run.
