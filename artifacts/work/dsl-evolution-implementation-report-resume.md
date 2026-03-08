## Completed In This Pass

- Closed the remaining Task 13 gap from review by turning `repeat_until` bodies into statement-layer execution surfaces instead of raw primitive-only nested steps.
  - loader validation now accepts direct nested `call`, `match`, and `if/else` bodies inside `repeat_until`
  - repeat-until bodies are lowered with loop-local structured-ref rewriting so body-local refs stay on `self.steps.*` and outer lexical refs stay on `parent.steps.*`
  - the repeat-until executor now runs lowered branch/case markers, join nodes, and nested calls with iteration-scoped runtime ids
  - nested call frames inside `repeat_until` now key off the iteration runtime step id, so repeated iterations persist distinct call frames and `resume` reuses the unfinished one instead of collapsing iterations together
- Restored the shipped docs/example contract to the approved design boundary.
  - updated the DSL and drafting docs to allow direct nested `call` / `match` / `if/else` in `repeat_until` while still rejecting `goto`, nested `for_each`, and nested `repeat_until`
  - upgraded `workflows/examples/repeat_until_demo.yaml` to exercise nested `call` + `match`
  - added `workflows/examples/library/repeat_until_review_loop.yaml` as the imported reusable loop-body workflow used by the demo
- Added direct coverage for the previously-missed boundary.
  - loader acceptance for nested `call` + `match`
  - runtime coverage for stable lowered ids plus iteration-scoped call-frame lineage
  - resume coverage for nested calls inside `repeat_until`
  - updated example smoke coverage

## Completed Plan Tasks

- Task 13: Add post-test `repeat_until` as its own loop tranche
  - completed the approved structured-loop composition boundary by supporting statement-layer body execution with nested reusable `call` and structured `match`
  - kept loop-frame outputs explicit on the authored `repeat_until` node and preserved the `self.outputs.*` condition boundary
  - preserved stable authored-id ancestry across lowered loop-body nodes and iteration-qualified runtime identities
  - verified resume-safe iteration bookkeeping and nested call-frame reuse for unfinished loop-body work
  - refreshed the example/docs surfaces so the shipped contract matches the implemented tranche

## Remaining Required Plan Tasks

- None.

## Verification

- `pytest --collect-only tests/test_loader_validation.py tests/test_structured_control_flow.py tests/test_resume_command.py tests/test_workflow_examples_v0.py -q`
  - collected `148` tests
- `pytest tests/test_loader_validation.py tests/test_structured_control_flow.py tests/test_resume_command.py -k repeat_until -v`
  - `10 passed`, `118 deselected`
- `pytest tests/test_workflow_examples_v0.py -k repeat_until -v`
  - `1 passed`, `19 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --dry-run`
  - loader/validation completed successfully
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --state-dir /tmp/dsl-evolution-repeat-until-demo-clean`
  - created run `20260308T043709Z-9cndcx`
  - inspected `/tmp/dsl-evolution-repeat-until-demo-clean/20260308T043709Z-9cndcx/state.json`
  - persisted run `status` was `completed`
  - persisted `steps.ReviewLoop.artifacts` was `{"review_decision": "APPROVE"}`

## Residual Risks

- The first `repeat_until` composition tranche now supports direct nested `call`, `match`, and `if/else` bodies. Nested `for_each`, nested `repeat_until`, and `goto` inside loop bodies remain intentionally rejected.
- Coverage now proves the direct composition boundary and nested-call resume path. It does not separately claim support for deeper second-level structured nesting inside a loop-body branch/case beyond that documented first-tranche surface.
- The real CLI smoke was run from the repo root as required. Because the example writes into workspace-local `state/review-loop`, repeated local operator runs can reuse prior counters/history unless that workspace state is cleaned between runs; the durable proof point recorded above is the fresh run state under `/tmp/dsl-evolution-repeat-until-demo-clean`.
