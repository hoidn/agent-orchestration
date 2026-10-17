# `.orc` Workflows Versus A Single Agent Call

Materials of an experiment that compared two `.orc` workflows with a single
agent call on the same task: generate four candidates and select one, and
implement, review and revise. It is small: one real
defect of this repository as the task, six runs per configuration, and model
judges rating patches blind against a four-criterion rubric. Treat its numbers
as exploratory.

- Results: [experiment report](../../docs/reports/2026-09-28-orc-versus-single-call.md)
- Guidance drawn from it: [`docs/orc_workflow_design_lessons.md`](../../docs/orc_workflow_design_lessons.md)

| Path | Contents |
| --- | --- |
| `workflows/best_of_n.orc` | target 2.35; four implementers, one selector; Sonnet implements, `gpt-6-sol` selects |
| `workflows/reviewed_change.orc` | target 2.28; implement, review, revise; Sonnet implements, `gpt-6-sol` reviews |
| `workflows/*.providers.json` | provider bindings for each workflow |
| `task/` | the instructions given to the agents and the bug report package |
| `evaluation/rubric.md` | the four criteria the blind judges applied |
| `evaluation/results.json` | every rated patch, per judge and per criterion, and what each workflow selected |
| `evaluation/judge_ratings/` | the judges' ratings with their reasons, and the key from random id to patch |
| `harness/` | the agent CLI wrapper and the trial runners, with the paths of the machine the experiment ran on |

The patches themselves, the prompts and the agents' outputs are not tracked.
The `harness/` scripts carry the paths of the machine the experiment ran on;
adapt them before rerunning a trial.

## Run the maintained best-of-N workflow

[`best_of_n.orc`](workflows/best_of_n.orc) targets typed 2.35. Its
`best-of-n` entry maps candidates serially, with a maximum
of eight, then asks the judge to select one. The existing
[`best_of_n.providers.json`](workflows/best_of_n.providers.json) binds the
implementers to `claude_unrestricted_workspace` and the judge to
`codex_unrestricted_workspace`.

Start with a clean base repository and create one independent clone per
candidate under a temporary working root. From a shell with the project Python
environment active:

```bash
REPO=/absolute/path/to/agent-orchestration
BASE_REPO=/absolute/path/to/clean/base-repository
WORK=$(mktemp -d)
mkdir -p "$WORK/candidates"
for name in alpha beta gamma delta; do
  git clone --no-hardlinks "$BASE_REPO" "$WORK/candidates/$name"
done
cat > "$WORK/inputs.json" <<'JSON'
{
  "task": "Fix add in calc.py so that it returns the sum.",
  "intent": "add returns a + b",
  "repos": ["candidates/alpha", "candidates/beta", "candidates/gamma", "candidates/delta"]
}
JSON

cd "$WORK"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
SOURCE="$REPO/experiments/orc_vs_single_call/workflows/best_of_n.orc"
SOURCE_ROOT="$REPO/experiments/orc_vs_single_call/workflows"
PROVIDERS="$REPO/experiments/orc_vs_single_call/workflows/best_of_n.providers.json"
python -B -m orchestrator compile "$SOURCE" --entry-workflow best_of_n::best-of-n \
  --source-root "$SOURCE_ROOT" --provider-externs-file "$PROVIDERS"
python -B -m orchestrator run "$SOURCE" --entry-workflow best_of_n::best-of-n \
  --source-root "$SOURCE_ROOT" --provider-externs-file "$PROVIDERS" \
  --input-file "$WORK/inputs.json" --dry-run
python -B -m orchestrator run "$SOURCE" --entry-workflow best_of_n::best-of-n \
  --source-root "$SOURCE_ROOT" --provider-externs-file "$PROVIDERS" \
  --input-file "$WORK/inputs.json"
RUN_ID=$(python -c 'from pathlib import Path; print(next(Path(".orchestrate/runs").iterdir()).name)')
python -B -m orchestrator resume "$RUN_ID"
python -B -m orchestrator report --run-id "$RUN_ID" \
  --runs-root "$WORK/.orchestrate/runs" --format json
```

Each repository path must exist and point to a separate clone of the same
baseline. The `select-only` entry takes `intent`, ordered `repos`, and ordered
`accounts`; it calls only the judge.

To check `reviewed_change.orc` without calling providers, from the repository
root:

```bash
python -m orchestrator run experiments/orc_vs_single_call/workflows/reviewed_change.orc \
  --entry-workflow reviewed_change::reviewed-change \
  --source-root experiments/orc_vs_single_call/workflows \
  --provider-externs-file experiments/orc_vs_single_call/workflows/reviewed_change.providers.json \
  --input task="Fix add in calc.py" --input intent="add returns a + b" --input repo=. \
  --dry-run
```
