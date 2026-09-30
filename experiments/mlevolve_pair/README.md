# MLEvolve-inspired paired search

This is a small, scripted comparison of two independent search controllers.
Both search the same integer model `a*x + b*x*x` against `2*x + 3*x*x` at
`x = [-2, -1, 1, 2]`; the score is the sum of squared errors. Coefficients
outside `[-5, 5]` return an invalid evaluation and can never be accepted.

Each controller evaluates seeds A `(1, 0)` and B `(0, 1)` first. It then
alternates A/B improvements, replacing a branch incumbent only on a valid,
strictly lower score. A tie or invalid proposal leaves the incumbent in place
and increments that branch's stall count. An invalid proposal schedules one
repair of that same candidate and branch before switching branches. A repair
that is still invalid is not retried. An accepted improvement resets that
branch's stall count. When both counts reach two, the controller asks the
shared proposal fixture to fuse the current A and B incumbents and evaluates
that candidate. Search stops when its best evaluation is valid and at or below
the target score, or when the evaluation budget is exhausted; seeds, repairs,
and fusion all count. The default budget is 12, valid budgets are
integers from 2 through 16, and the ORC loop has a fixed safety bound of 16.
Fusion is attempted at most once; if it does not solve the task, both stall
counts reset and alternation continues until the score or budget stop. Budgets
outside `[2, 16]` return `invalid_budget` with zero evaluations.

At startup, a valid seed outranks an invalid seed; if both are invalid, A is
kept as a fallback.

The proposal fixture is deterministic: its first A improvement is deliberately
out of bounds, repair yields `(2, 0)`, later A improvements plateau at `(2, 0)`,
B improvements plateau at `(0, 3)`, and fusion combines A's `a` with B's `b`.
Both controllers retain the typed trial list, but the proposal leaf receives its
length (`history_size` / evaluation count) because the current typed command
adapter accepts only scalar and path inputs. The fixture uses that length to
inject the invalid candidate once; it never chooses the operation or branch.
The two seed candidates are fixed and valid by fixture construction.

`search.orc` records the authored ORC policy, but this specimen does not claim
that the policy executed: the current compiler rejects the controller. It
first met the 256-node limit of a pure expression; since bound values are
shared in a payload it meets a loop inside a branch
(`workflow_boundary_type_invalid`). `compare.py` runs the Python controller with
direct and subprocess leaves, then attempts the ORC compile and public run.
From the repository root, reproduce the comparison and write its evidence with:

```bash
python -m experiments.mlevolve_pair.compare --output experiments/mlevolve_pair/evidence.json
```

The compact controller is in `search_compact.orc`. Its module path is
`mlevolve_pair/search_compact`, so its certified adapter manifest is
`commands_compact.json` (the `owner_module` metadata matches that module).
Run it with the same public command, substituting that source and manifest:

```bash
python -m orchestrator run experiments/mlevolve_pair/search_compact.orc \
  --entry-workflow run-search --source-root experiments \
  --command-boundaries-file experiments/mlevolve_pair/commands_compact.json \
  --dry-run
```

The broader findings are in the
[comparison report](../../docs/reports/2026-09-29-mlevolve-orc-python-comparison.md).
Python has no matching durable recovery implementation in this specimen, so
recovery advantage was not measured.
These scripted leaves validate the numerical and workflow boundaries, but
provide no evidence about live model quality, model cost, GPU throughput, or
production-provider behavior.
