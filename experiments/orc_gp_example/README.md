# Offline genetic programming over ORC workflow programs (a toy)

A small, runnable (mu+lambda) genetic-programming loop whose individuals are ORC workflow programs. It shows
the whole loop end to end: genotype, typed construction, the ordinary compiler as the validity filter,
execution through the public `python -m orchestrator run`, fitness from the whole run, selection, mutation,
crossover, generations and structural diversity. It runs offline in about two minutes and never calls a paid
provider: a scripted agent stands in for `claude` and `codex`.

It is a toy. The scripted world has fixed rules (below) that make program structure matter, so the search has
something to find. The fitness numbers say nothing about real agents.

## Run it

```bash
PYTHONPATH=$PWD python -m experiments.orc_gp_example.evolve --out /tmp/orc-gp
```

Run it from the repository root. Defaults: `--population 6 --generations 4 --seed 0`. The command prints one row
per generation and writes `<out>/results.json` plus one workspace per evaluated program under
`<out>/runs/<digest>/`, holding the rendered `individual.orc`, the boundary files and the run's `state/`.
`--ill-typed-rate P` turns on a deliberately ill-typed mutation operator. The compiler rejects the programs it
makes, and the loop counts them as rejected instead of crashing.

Table columns: `best` and `mean` fitness of the population, `skel` the number of distinct structural
skeletons in the population, `ok`/`rej` the offspring the compiler accepted or rejected (in generation 0,
the initial population), `hits` the offspring whose rendered source had already been evaluated.

## What each piece is in GP terms

| GP concept | Here |
| --- | --- |
| Genotype | An ordered list of stages (`grammar.py`): `plan(model)`, `implement(model)`, `check_and_repair(rounds, diagnoser)` and `review_and_revise(rounds, reviewer)`. Each genotype has at least one `implement` and at most six stages. Models: `claude-sonnet-5-5`, `claude-opus-5-5` and `gpt-6-sol`. |
| Typed construction / closure | `grammar.render` turns every genotype into a target-2.39 module. Its entry is `run ((task String)) -> Outcome`, built from `provider-result`, `command-result check`, `let*`, `if`, `match` and `loop/recur`, and it ends with a final check. Rendering is total over the grammar, but `python -P -m orchestrator compile` still runs on every individual and its verdict is recorded. |
| Phenotype / evaluation | Each new rendered source runs once through `python -P -m orchestrator run ... --state-dir state` in its own plain-directory workspace. `scripted_agent.py` is on `PATH` as `claude` and `codex`, and serves as the `check` command. |
| Fitness | Computed from the whole run's memo: `10 * success - 0.5 * cost`. Success needs a completed `DONE` terminal and a passing final check. Cost prices every committed provider call by model: sonnet 1, gpt-6-sol 3, opus 5 toy units. If the terminal or the final check is missing, fitness is `None` (ranked last), never 0. |
| Selection | (mu+lambda) with mu = lambda = population. Parents are picked by size-2 tournaments. The next population is the best mu of parents plus children, with duplicates merged. The scheme is elitist, so the best fitness never drops. |
| Mutation | Insert, delete or replace a stage, change a model, or change rounds. A child must differ from its parent and stay valid. |
| Crossover | One-point crossover on the stage lists: a prefix of one parent followed by a suffix of the other. |
| Diversity | The number of distinct `skeleton_hash` values (from `experiments/orc_structural_search/records.py`) of the rendered sources. The hash masks literals such as models and rounds, so it counts structures. |
| Reproducibility | The seed is fixed. Fitness is cached by rendered-source digest, so a repeated individual is a cache hit, not a replicate. |

The search starts from a seed program, `implement(claude-sonnet-5-5)`, plus random genotypes.

## The toy world (`scripted_agent.py`)

- An implementation leaves 2 defects with sonnet and 1 with opus or gpt-6-sol. It leaves none when its prompt
  carries a strong planner's `GUARD-EDGE-CASE` step, and only opus and gpt-6-sol write that step.
- In `check_and_repair`, a strong diagnoser names a root cause and the repair then removes every defect.
  Otherwise each round removes one.
- In `review_and_revise`, the reviewer asks for changes only when defects remain and its model family differs
  from the implementer's. Each revision removes one defect.
- The check passes when something was implemented and no defect remains.

Several different structures succeed at different costs, for example `plan(gpt-6-sol) implement(sonnet)`
or `implement(sonnet) check_and_repair(1, gpt-6-sol)`. The search has to trade success against calls.

## How this differs from the real structural search

`experiments/orc_structural_search` searches authored `.orc` source, not a grammar genotype. In it:

- An LLM mutator rewrites a whole file (I1), or makes one-site edits as a transaction (I2).
- Children run against live agents on real task repositories, behind the comparison-harness shims.
- Outcomes are judged by blind judges and metered from provider receipts.

This example replaces all of that with a fixed grammar, random variation operators, a scripted world and a
price table. It is a teaching aid for the GP loop, not a proxy for that search.

Test: `tests/experiments/test_orc_gp_example.py`.
