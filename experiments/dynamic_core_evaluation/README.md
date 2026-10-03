# Dynamic-core evaluation

This remains an isolated experiment, not a public `.orc` target or a production
adoption. The current evidence executes complete improve and compact-search
consumers through admitted dynamic artifacts and the existing compiled leaf
runtime. The driver writes each artifact to disk, reads it back, checks its
digest, then calls real deterministic local command leaves through
`LeafBridge` and `WorkflowExecutor`.

The full improve consumer assembles the ordinary [`improve` definition
fragment](fixtures/improve.orc) with caller-owned hooks and keeps the compiled
result contract `Improvement[Draft Feedback Blocker]`. The compact search
consumer uses [`search.orc`](fixtures/search.orc), declares `SearchResult`, and
reuses the existing compact controller command adapters. The smaller
[`composition.orc`](fixtures/composition.orc) remains a `Value`-result example
for single-pass closure composition; it is not the result schema used by those
full-consumer checks. Shared definitions have to be assembled into caller
source because this bounded reader has no ORC import support.

## Context passed to hooks

In the existing typed helper, each hook receives the explicit `inputs I`
argument. The typed route already supports one `String` as `I` without a
context record:

```lisp
(review state.current inputs)
(revise state.current inputs r.feedback)
```

The dynamic excerpt is UE03 in the [paired source-edit cases](../../tests/experiments/test_dynamic_core_utility_edits.py).
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
The current evidence credits the typed single-`String` context. Proposed W3
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

## Run the full improve consumer

From the repository or worktree root, run this test-owned driver. It assembles
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

## Limits

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

Run the focused checks from the repository root in a tmux session, as required
by `AGENTS.md` for this slow pytest group:

```bash
pytest -q -n 16 --dist=worksteal \
  tests/experiments/test_dynamic_core_utility_core.py \
  tests/experiments/test_dynamic_core_utility_improve.py \
  tests/experiments/test_dynamic_core_utility_search.py \
  tests/experiments/test_dynamic_core_utility_edits.py
```
