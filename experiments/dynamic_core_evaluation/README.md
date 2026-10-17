# Dynamic-core evaluation

The spike and comparison that preceded native target 3.0. Both ran ordinary
functions and closures against the typed `std/improve` workflows and the
Python search reference from [`mlevolve_pair`](../mlevolve_pair/README.md),
using deterministic local commands and no model calls. Native 3.0 as it ships
is described in the
[drafting guide](../../docs/lisp_workflow_drafting_guide.md#2b-native-30-dynamic-composition)
and [versioning](../../specs/versioning.md#native-target-30); nothing here is
needed to use it.

Results: [dynamic-core evaluation report](../../docs/reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md).

## The spike

A small evaluator ran ordinary source (`define`, `fn`, immutable captures,
lists and records) and sent every effect to a compiled typed leaf workflow
through a bridge. With no imports, the caller or test driver assembled shared
source fragments, and caller-written normalizers mapped each leaf's `return__…`
result keys back into the caller's records.

Its tests compared outcomes, full leaf payloads and their order against the
typed improve workflows: approval, blocked and exhausted outcomes, failures at
the leaf boundary, and the public result schema. The search tests compared the
complete `SearchResult` and trace against the Python reference over a fixed
set of budgets. Four source edits (a new `Draft.origin` field, a feedback field
rename, independent rubric and goal context, a pure helper over
`Feedback.note`) and several failure and restart cases recorded when a bad
name, arity or missing field is caught and what a restart repeats.

Limits: every effect launched a fresh compiled leaf with its own state and
startup cost; the evaluator had no imports, macros, mutation, static effect
tracking or public launch route; a fresh run repeated completed effects.
Timings and paid-call costs were not measured, and the results make no claim
about net code deletion or production readiness.

### Reproduce the spike

The spike exists only at commit `3a7f8efd464d69f9c652cb9fea8b350c1248edc6`.
Check it out separately and set up the Python 3.11+ environment from that
revision's README:

```bash
historical_parent="$(mktemp -d)"
git worktree add --detach "$historical_parent/checkout" 3a7f8efd464d69f9c652cb9fea8b350c1248edc6
cd "$historical_parent/checkout"
```

From that checkout root, this driver assembles the improve fragment with a
caller, compiles the local review/revise leaves, writes and reads back the
program artifact, and runs both effects:

```bash
python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from tests.experiments.test_dynamic_core_utility_improve import _dynamic_run

with TemporaryDirectory(prefix="dynamic-core-improve-") as temporary:
    workspace = Path(temporary) / "run"
    outcome = _dynamic_run(workspace, seed="draft", limit=2, wrapped=True)
    assert "error" not in outcome, outcome.get("error")
    print(json.dumps({
        "artifact_digest_after_disk_readback": outcome["digest"],
        "evaluation_steps": outcome["steps"],
        "result": outcome["value"],
        "ordered_leaf_inputs": outcome["events"],
    }, indent=2))
PY
```

The printed event list holds the complete review and revision inputs in order.
`wrapped=True` exercises the captured review/revise callbacks.

The full test group is slow; run it in tmux from the same checkout:

```bash
pytest -q -n 16 --dist=worksteal \
  tests/experiments/test_dynamic_core_utility_core.py \
  tests/experiments/test_dynamic_core_utility_improve.py \
  tests/experiments/test_dynamic_core_utility_search.py \
  tests/experiments/test_dynamic_core_utility_edits.py
```

## Implemented W3 Comparison (Opt-In)

[`test_w3_dynamic_reevaluation.py`](test_w3_dynamic_reevaluation.py) runs typed
2.36 (local hooks with captures) and native 3.0 side by side through public
compile, run and resume: the improve consumer's outcomes, the search consumer
over nine scenarios and eight budgets, the four source edits, when unbound
names, arity errors and missing fields are caught, an operation-budget
restart, and process kills followed by typed resume versus a native fresh run.

The two runtimes agreed everywhere except two behaviors, which the module
keeps as failing checks:

- `limit=0`: native refuses with `invalid_limit`; 2.36 returns `EXHAUSTED`
  with the initial value. Neither runs a hook.
- A command result containing `valid: "false"`: native refuses it with
  `dynamic_command_result_invalid`; 2.36 reads it as `false` and continues.

Typed 2.36 local hooks capture context as native closures do, so context
capture is not an advantage unique to native 3.0.

### Reproduce the comparison

The module pins its runtimes: the native runtime and reused helper bytes must
equal `b0b05d504d4b1be7b1cbaebfadf47ffdc3e66012`, and the typed checkout must
be exactly `47e85a9c7e452bfd367275a15d5e97b928efa5ca` and clean. It refuses to
run against the current tree. Use the comparison checkout
`d87334f0365f46bfeb56bf7a0f753d1490df85c5`:

```bash
git worktree add --detach /var/tmp/orc-w3-frozen-packet d87334f0365f46bfeb56bf7a0f753d1490df85c5
git worktree add --detach /var/tmp/orc-w3-frozen-typed 47e85a9c7e452bfd367275a15d5e97b928efa5ca
cd /var/tmp/orc-w3-frozen-packet
export ORC_W3_REEVALUATION_TYPED_ROOT=/var/tmp/orc-w3-frozen-typed
python -m pytest --collect-only -q experiments/dynamic_core_evaluation/test_w3_dynamic_reevaluation.py
python -m pytest -q experiments/dynamic_core_evaluation/test_w3_dynamic_reevaluation.py -k 'RW_I01 or RW_S02'
```

For the full comparison, run this in tmux with the same environment variable:

```bash
python -m pytest -q -n 16 --dist=worksteal experiments/dynamic_core_evaluation/test_w3_dynamic_reevaluation.py
```

Default pytest discovery covers `tests/` only, so this module runs only when
named. It fails rather than skips when the typed checkout is missing, dirty or
mismatched, and its two discrepancy checks make a nonzero exit expected. Raw
observations go to `/tmp/orc-w3-dynamic-reevaluation-20261012/`.
