# MLEvolve-inspired paired search

A small scripted specimen comparing search controllers written in Python and
in Workflow Lisp. Each searches two integer coefficients of `a*x + b*x*x`
against the fixed target `2*x + 3*x*x` at `x = [-2, -1, 1, 2]`; the score is
the sum of squared errors. Coefficients outside `[-5, 5]` return an invalid
evaluation and can never be accepted. Proposals come from a deterministic
fixture, not a model.

## Search policy

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

The proposal fixture's first A improvement is deliberately out of bounds,
repair yields `(2, 0)`, later A improvements plateau at `(2, 0)`, B
improvements plateau at `(0, 3)`, and fusion combines A's `a` with B's `b`.
Both controllers keep the typed trial list, but the proposal leaf receives its
length (`history_size` / evaluation count) because the typed command adapter
accepts only scalar and path inputs. The fixture uses that length to inject the
invalid candidate once; it never chooses the operation or branch. The two seed
candidates are fixed and valid by construction.

## Files

| File | Contents |
| --- | --- |
| `search.py` | Python controller |
| `leaves.py` | Shared evaluation and proposal leaves, callable directly or as subprocesses |
| `search.orc`, `commands.json` | Workflow Lisp controller at target 2.33 and its command manifest |
| `search_compact.orc`, `commands_compact.json` | Shorter target-2.33 controller and its manifest (module `mlevolve_pair/search_compact`) |
| `compare.py` | Runs the comparison and writes the evidence JSON |

The compiler refuses both `.orc` controllers at their declared target 2.33
(`search.orc` with `workflow_boundary_type_invalid` for a loop inside a branch,
`search_compact.orc` with `workflow_return_not_exportable`), so only the Python
controller executes here. A runnable Workflow Lisp version of the same search
is the [native 3.0 search consumer](../../tests/fixtures/workflow_lisp/dynamic/search.orc),
which uses these leaves and `commands_compact.json`; see
[Iterative search](../../docs/lisp_library_reference.md#iterative-search).

## Reproduce

From the repository root:

```bash
python -m experiments.mlevolve_pair.compare --output /tmp/mlevolve-pair-evidence.json
```

This runs the Python controller with direct and subprocess leaves over several
budgets, then attempts the public compile and run of `search.orc` and records
the refusal. The output also lists source line counts and the stated limits.

## Limits

Python has no durable recovery in this specimen, so recovery was not compared.
The comparison is sequential; concurrency was not measured. The scripted
leaves say nothing about live model quality, model cost, GPU throughput or
production-provider behavior.

Results: [comparison report](../../docs/reports/2026-09-29-mlevolve-orc-python-comparison.md).
