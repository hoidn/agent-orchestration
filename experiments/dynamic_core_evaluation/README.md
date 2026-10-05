# Dynamic-core evaluation — historical DC-2 spike

This README preserves the earlier source-assembly/compiled-leaf experiment.
Its active bridge, fixtures and test drivers have been retired from the
candidate; the excerpts and commands below apply only to the frozen historical
checkout, not the current native runtime.

Current authoring starts with the [drafting guide](../../docs/lisp_workflow_drafting_guide.md).
The isolated target-3.0 candidate uses the real
[std/dynamic/improve library](../../orchestrator/workflow_lisp/stdlib_modules/std/dynamic/improve.orc),
[complete improve consumer](../../tests/fixtures/workflow_lisp/dynamic/improve.orc)
and [complete search consumer](../../tests/fixtures/workflow_lisp/dynamic/search.orc).
Their [public CLI smoke](../../tests/test_workflow_dynamic_improve.py) and
[local search checks](../../tests/test_workflow_dynamic_search.py) stage the
required module layout, probes and command manifests. A fixture path alone is
not a standalone launch. The [readiness plan](../../docs/plans/2026-10-02-workflow-lisp-dynamic-core-readiness-plan.md)
owns branch qualification; no adopted/default target, application migration,
resume or live-provider qualification follows from these examples.

Historical reproduction is pinned to immutable commit
`3a7f8efd464d69f9c652cb9fea8b350c1248edc6`, which contains all four experiment
owners, six fixtures and seven original test modules. It happens to equal the
stable evaluation branch's pre-cutover value; reproduce the commit, not a
moving branch. The retained typed comparator is separately pinned to
`4b69ee00d4c6204dd816b4caa02b9fee1dae25e8`; that revision does not contain this
spike. The individual replacement map pins original test bytes at
`26bc796fba0b493d3f94ce7f935a9796030758d4`, a partially cut-over tree, not the
runnable historical checkout.

In the frozen spike, the complete improve consumer assembles an ordinary
[improve fragment](https://github.com/hoidn/agent-orchestration/blob/3a7f8efd464d69f9c652cb9fea8b350c1248edc6/experiments/dynamic_core_evaluation/fixtures/improve.orc)
with caller-owned hooks and retains the compiled Improvement contract.
[Search](https://github.com/hoidn/agent-orchestration/blob/3a7f8efd464d69f9c652cb9fea8b350c1248edc6/experiments/dynamic_core_evaluation/fixtures/search.orc)
retains SearchResult; [composition](https://github.com/hoidn/agent-orchestration/blob/3a7f8efd464d69f9c652cb9fea8b350c1248edc6/experiments/dynamic_core_evaluation/fixtures/composition.orc)
is the smaller Value-result example. The driver writes and reads admitted
artifacts, checks their digest, and executes real local leaves through
LeafBridge and WorkflowExecutor. Its missing import support requires assembly;
these costs and wire normalizers are historical, not current authoring patterns.

## Context passed to hooks

In the existing typed helper, each hook receives the explicit `inputs I`
argument. The typed route already supports one `String` as `I` without a
context record:

```lisp
(review state.current inputs)
(revise state.current inputs r.feedback)
```

The dynamic excerpt is UE03 in the [paired source-edit cases](https://github.com/hoidn/agent-orchestration/blob/3a7f8efd464d69f9c652cb9fea8b350c1248edc6/tests/experiments/test_dynamic_core_utility_edits.py).
It gives review only the candidate; an ordinary closure captures the
independent goal and rubric, while the revise closure captures the goal it
uses:

```lisp
(define (review-for goal rubric)
  (fn (current)
    (let* ((wire (effect review (record
                 (draft__title (field current "title"))
                 (draft__score (field current "score"))
                 (goal goal)
                 (rubric rubric)))))
      (normalize-review wire))))

(define (revise-for goal)
  (fn (current feedback)
    (let* ((wire (effect revise (record
                 (draft__title (field current "title"))
                 (draft__score (field current "score"))
                 (goal goal)
                 (feedback__note (field feedback "note"))))))
      (record (title (field wire "return__title"))
              (score (field wire "return__score"))))))

(improve (record (title "draft") (score 0))
         (review-for "tidy" "clarity") (revise-for "tidy") 1)
```

This excerpt omits the caller-local `normalize-review` definition shown in the
tested source; that function reconstructs the active `Decision` payload from
the leaf's declared `return__…` result. UE03 also extends the compiled review
leaf's input contract with `rubric`; the baseline `utility_leaves` review
workflow accepts only `Draft` and `goal`, so this edited leaf contract is a
prerequisite for the independent rubric input.

Both dynamic effects still pass through the declared compiled leaf input contracts.
The frozen evidence credits the typed single-`String` context. Proposed W3
could also remove explicit capture forwarding from the typed helper; it is not
implemented, so closure capture is not counted as a unique gain here.

## Evidence for utility authoring

The focused utility tests compare actual outcomes, full leaf payloads and their
order against existing typed improve workflows. They cover approval, blocked
and exhausted outcomes, failures at the declared leaf boundary, source
assembly versus a caller-owned inline definition copy, and the public typed
result schema. The search tests compare the complete `SearchResult` value and
trace against the existing Python reference over the frozen evaluation
budgets.

The source-edit cases exercise a `Draft.origin` field through initialization,
review and revision; a feedback/evidence field rename through producer,
contract and consumer; independent rubric and goal context; and matching pure
helpers that extract `Feedback.note` to a `String`. The failure cases record
whether a bad name or arity is rejected before a leaf, whether a missing field
or VM budget failure happens after a completed review, and what survives a
restart. A fresh dynamic run repeats completed effects and retains their leaf
run files. A typed public resume after a committed iteration continues without
replaying the hooks. Receipts and exact source pairs are written under the
pytest temporary directory by the tests; timings and paid-call costs are not
measured.

Ordinary source also supports bounded utility operations such as list append,
list length and updates to existing record keys. These checks keep collections
as ordinary lists and records rather than inventing a homogeneous internal
schema.

## Reproduce the frozen full improve consumer

Use a separate checkout at the immutable historical revision, with the Python
3.11+ development environment from that revision's README:

```bash
historical_parent="$(mktemp -d)"
git worktree add --detach "$historical_parent/checkout" 3a7f8efd464d69f9c652cb9fea8b350c1248edc6
cd "$historical_parent/checkout"
```

From that checkout root, run this historical test-owned driver. It assembles
the shared definition fragment with a real caller, compiles the existing local
review/revise workflows, writes and reads the admitted artifact, and executes
both effects. It makes no paid model calls and adds no runtime framework.

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

The printed event list contains the complete review and revision input records,
including their order. `wrapped=True` exercises the captured review/revise
callbacks. The helper verifies that the deserialized artifact has the same
digest before passing it to the evaluator.

## Historical limits

Every effect still launches a fresh compiled legacy leaf with its existing
state, contract validation and startup cost. Caller-authored normalizers map
the leaf's `return__…` wire keys into the caller's record shape; the bridge
validates and exposes the declared result unchanged. Source assembly is
performed by the caller or test driver; the dynamic language has no imports,
macros, mutation or public launch route. The evaluator has no static effect
tracking or resumable continuation, so a fresh run repeats earlier effects.
This evidence does not claim net deletion, lower total complexity or
production readiness; those remain separate decisions in the
[evaluation plan](../../docs/plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md).

Run the focused checks from the frozen checkout root in a tmux session, as required
by `AGENTS.md` for this slow pytest group:

```bash
pytest -q -n 16 --dist=worksteal \
  tests/experiments/test_dynamic_core_utility_core.py \
  tests/experiments/test_dynamic_core_utility_improve.py \
  tests/experiments/test_dynamic_core_utility_search.py \
  tests/experiments/test_dynamic_core_utility_edits.py
```
