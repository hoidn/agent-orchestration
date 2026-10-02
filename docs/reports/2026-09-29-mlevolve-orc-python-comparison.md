# MLEvolve-inspired search in ORC and Python

**Historical checkpoint:** The findings and development status below describe
baseline `fc5f2a2e1426d74da4cdb79a97a494e685300141`, not the current checkout.
For maintained source, reproduction commands and current limits, use the
[specimen README](../../experiments/mlevolve_pair/README.md) and
[drafting guide §2A](../lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today).

Result: Python executes the bounded policy; the full ORC specimen is blocked by the current frontend. Its explicit control-flow form generates a 361-node pure expression against a 256-node limit. This is a reproducible feasibility result, not a proof that every ORC formulation is impossible. The runtime was not modified to admit the specimen.

Purpose: compare independent `.orc` and Python implementations of the same search policy, without assuming an exact MLEvolve port and without placing a Python controller underneath `.orc`.

Follow-up: [ORC language limitations and possible solutions](2026-09-29-orc-language-limitations-and-solutions.md) separates the observed restrictions and defects from proposed authoring, compiler and runtime remedies.

Repository baseline: `fc5f2a2e1426d74da4cdb79a97a494e685300141`. Upstream inspected: [MLEvolve at `9c5c8a3`](https://github.com/InternScience/MLEvolve/tree/9c5c8a3b23f0361708b59a401452dddc00f97189). Governing local contracts are routed by `docs/index.md`; the [comparison plan](../plans/2026-09-29-mlevolve-orc-python-comparison.md) owns the experiment scope.

## What is being compared

The comparison keeps multi-branch exploration, strict incumbent selection, repair after an invalid candidate, stagnation-triggered cross-branch fusion, and an evaluation budget. It replaces MLEvolve's exact UCT/time schedule with a deterministic two-branch policy implemented independently in each language.

Scripted proposals stand in for model responses. The numerical evaluator executes a small polynomial prediction problem with a known target. The generator's script deliberately supplies useful proposals; a successful score is evidence that control and evaluation compose, not that either language discovers better ML models. No model calls, GPU workloads, MLE-bench tasks or model-cost measurements are included.

The shared Python leaves have a domain boundary: given an explicit proposal request, produce a candidate; given a candidate, evaluate it. They may validate domain inputs and encode a result bundle. They may not select a branch, choose a search operation, update incumbents, maintain a search journal, enforce the controller's budget, decide termination, or restore the controller. Those decisions belong to `search.orc` and, independently, `search.py`.

## Relationship to MLEvolve and justified language boundaries

The inspected upstream [search coordinator](https://github.com/InternScience/MLEvolve/blob/9c5c8a3b23f0361708b59a401452dddc00f97189/engine/agent_search.py) selects drafting, debugging, improvement and stagnation-related evolution/fusion, and maintains branch and incumbent state. Its [selection implementation](https://github.com/InternScience/MLEvolve/blob/9c5c8a3b23f0361708b59a401452dddc00f97189/engine/node_selection.py) combines UCT traversal, time-dependent exploration and weighted top-k exploitation. Those are application policies; preserving their Python modules under an ORC wrapper would not investigate an ORC implementation of the search.

| Responsibility | Coherent ORC design | Coherent Python design | Evidence in this specimen |
| --- | --- | --- | --- |
| Select branch/action, accept a result, repair, fuse, stop | Ordinary typed state and control flow in ORC | Ordinary state and control flow in Python | Independent sequential controllers; fixed two-branch policy |
| Ask a model for a plan or code change | Native provider effects when their contract fits | Model API calls | Scripted stateless responses only; no live provider comparison |
| Run candidate training and compute metrics | A command effect invoking the experiment environment | Direct library calls or the same command protocol | Small numerical evaluator only |
| Keep controller history | ORC loop state and runtime persistence | In-memory history in this specimen | Typed trial records and parent lineage |
| Retrieve similar past experiments | Omit unless the chosen algorithm needs it; then a separately justified retrieval computation | Same optional numerical/library computation | Not implemented or measured |
| Dynamic MCGS graph, UCT, time-based stochastic selection | Requires a separate expressibility and cost investigation | Native collections, numerical functions and sampling | Deliberately replaced; no claim of equivalent search quality |

The toy sum-of-squares calculation could itself use integer arithmetic; Python is not intrinsically required for that calculation. Here it supplies a controlled external-experiment fixture. For a real ML workload, the numerical/ML environment provides the substantive reason for that boundary; a candidate can be a code/artifact path rather than a large record. This does not justify retaining the original Python scheduler, search journal, action selector or agent hierarchy. The scripted Python proposal leaf stands in for model output, not a recommendation to route native ORC provider calls through Python. No original MLEvolve module is needed by these specimens.

## Comparisons and attribution

Three execution modes were attempted with the same policy and leaves:

1. Python with ordinary direct leaf function calls.
2. The same Python controller using subprocess calls and the same JSON request/result-bundle format.
3. ORC using command effects through its compiler and runtime. The full controller fails compilation before executing a leaf; only the smaller capability probes run successfully.

Mode 1 versus 2 exposes the cost of process and JSON boundaries. Mode 2 versus 3 would compare more similar transports, but the compile failure prevents that timing comparison. Python does not implement checkpoints or public resume. ORC's existing machinery for those services is an integration benefit, not measured recovery superiority for this search. Neither Python timing measures the cost of real LLM calls or training.

Freshness semantics differ: the Python harness gives each call a new bundle filename and checks its presence; ORC manages its own bundle paths. The payload format and subprocess boundary are comparable, but result freshness is not an identical protocol. The missing-result probe below makes this distinction consequential. Graph/controller memory usage, leaf-process memory, and durable storage for the full ORC search were not measured.

Concurrency is a separate capability question. Selecting two candidates from one frozen state and evaluating them concurrently is not the same search policy as selecting the second candidate after observing the first result. Measurements from those schedules must not be mixed.

## Feasibility checks before the paired run

A minimal public-runtime probe successfully carried command-produced records with `Float` scores through comparison, `record-update`, `list/append`, two loop iterations and final return. Its result retained both trial records and the lower score. Thus the experiment need not move list history or incumbent comparison into Python merely to make those components compose.

The probe also found an authoring restriction: a Float literal in an expression such as `:best 999.0` is rejected with `frontend_parse_error`; float literals are currently accepted in public `defworkflow` parameter defaults. A typed score input/default or a score produced by evaluation supplies the required value. This is an ergonomics cost, not evidence that Float comparison is unavailable.

A second probe passed the entire computed loop-state record as one command `:argv` argument. Stage 3 rejected that form with `workflow_return_not_exportable` (command arguments must resolve to admitted literals or workflow inputs). The typed adapter's record-valued `:inputs` were also rejected with `command_adapter_input_not_projectable`. The final boundary therefore uses scalar coefficients and history length; internal state still retains all trial records. Python's ordinary dictionary argument has no comparable transport declaration. Semantic retrieval over the full trial list is not implemented by either specimen.

## Python reference behavior

The primary agent collected and ran the initial behavioral tests successfully. Independent direct runs produced the following reference outcomes. These are Python results; no ORC equality claim follows from them.

| Evaluation budget | Evaluations used | Termination | Best `(a,b)` | SSE |
| --- | ---: | --- | --- | ---: |
| 2 | 2 | Budget exhausted | `(0,1)` | 176 |
| 3 | 3 | Budget exhausted before repair | `(0,1)` | 176 |
| 4 | 4 | Budget exhausted after repair | `(0,1)` | 176 |
| 7 | 7 | Budget exhausted | `(0,3)` | 40 |
| 12 | 10 | Target reached by fusion | `(2,3)` | 0 |

The ten-evaluation route is `seed A`, `seed B`, `improve A` (invalid), `repair A`, `improve B`, `improve A`, `improve B`, `improve A`, `improve B`, `fuse`. Branch A's repair improves its own incumbent without necessarily beating branch B's global best; both local and global acceptance must remain distinct.

## Recorded measurements

The retained [evidence.json](../../experiments/mlevolve_pair/evidence.json) contains full Python traces and the public ORC compile diagnostic. Reproduce with:

```bash
python -m experiments.mlevolve_pair.compare --output /tmp/mlevolve-pair-evidence.json
```

| Budget | Direct Python, ms | Python subprocess leaves, ms | Full results and traces equal? |
| ---: | ---: | ---: | --- |
| 3 | 0.044 | 142.0 | Yes |
| 7 | 0.061 | 383.8 | Yes |
| 12 | 0.079 | 567.9 | Yes; solved after 10 evaluations |

These are individual local observations, not medians or stable performance estimates. Direct timing excludes the parent interpreter's startup; subprocess timing includes child startup, JSON and bundle-file I/O. The default case launches 18 leaves: two seed evaluations and eight proposal/evaluation pairs. The evaluator itself is tiny, so process overhead dominates. This says nothing about the cost ratio for real training or model calls. The ORC compile rejection took 2.84 s including process startup; that is not an execution-time measurement.

Physical source lines, including blank lines: Python controller **128**, attempted ORC controller **239**, ORC command declarations **51**, shared leaves/validation **86**, harness plus behavioral tests **277**. The Python subprocess adapter lives in the harness. These are descriptive counts, not a claim of equivalent delivered features: Python omits persistence, and the ORC attempt is blocked. Probe code and the existing runtime are outside these controller counts.

## Full ORC controller: compile failure

The retained [search.orc](../../experiments/mlevolve_pair/search.orc) contains the whole controller. Branches select repair, improvement or fusion; each invokes proposal and evaluation commands, computes strict acceptance, updates history and incumbents, and continues the loop. There is no Python controller underneath it.

Several authoring forms were tried before accepting the limitation:

| Form | Observed boundary |
| --- | --- |
| Compact shared proposal/evaluation body, effectful helper directly inside `continue` | WCC `ProcedureCallExpr` exception |
| Helper call bound before `continue`; compact body subsequently inlined into loop | `pure_expr_payload_too_large` in selected scalar expressions |
| Explicit operation/branch cases in a helper | WCC `ValueError: pure boolean conditions require WCC pure-projection lowering` |
| Explicit cases in the loop, whole conditional bound to `next-state` | `workflow_return_not_exportable`: unsupported `let*` binding `LetStarExpr` |
| Explicit cases with `continue` at every terminal branch | Passed those placement issues; reached the expression-size limit in the first repair-state update |

The final form also uses `state.evaluations` as the proposal's history length: every evaluation adds exactly one trial. This avoids placing `list/length` directly in a command argument, another rejected expression position. It does not change the policy.

Reproduce from the worktree root:

```bash
python -m orchestrator run experiments/mlevolve_pair/search.orc \
  --command-boundaries-file experiments/mlevolve_pair/commands.json \
  --state-dir /tmp/mlevolve-direct-branches --quiet
```

Fresh CLI exit: **2**. Diagnostic: `pure_expr_payload_too_large` at the `record-update` in repair branch A. To inspect the otherwise hidden count, a temporary observational wrapper printed the metadata passed to `orchestrator.workflow.pure_expr._raise`: `{'node_count': 361, 'max_nodes': 256}`. It preserved the original exception and limit. No runtime source was edited.

Consequences: there is no full ORC search trace, winner, execution timing or committed-boundary recovery result to compare. The authored ORC line count describes a blocked implementation attempt, not a functioning equivalent. Baseline rich-loop public-resume checks passed as part of 96 narrow existing tests, but those smaller checks do not establish recovery of this controller.

## Result validation: a passing check and a failure

The retained [malformed-result workflow](../../experiments/mlevolve_pair/probes/malformed_result.orc) asks for an `Int` field and receives a string. A fresh public CLI run exited 1, with run status `failed`, step exit code 2, and `contract_violation` / `invalid_integer` at JSON pointer `/ordinal`. The diagnostic includes the originating ORC source location. State: `/tmp/mlevolve-malformed-probe-state/20260929T205037Z-j0poa4/state.json`.

```bash
python -m orchestrator run experiments/mlevolve_pair/probes/malformed_result.orc \
  --command-boundaries-file experiments/mlevolve_pair/probes/commands.json \
  --state-dir /tmp/mlevolve-malformed-probe-state --quiet
```

This is a concrete benefit of deriving boundary validation and diagnostics from declarations. Python can also validate small result records simply; the paired controller validates strict Bool/Float evaluation fields and rejects nonfinite scores. Neither language's structural check proves that an experiment metric is meaningful.

The retained [missing-bundle workflow](../../experiments/mlevolve_pair/probes/missing_bundle.orc) invokes the same command in two loop iterations. Its [leaf](../../experiments/mlevolve_pair/probes/missing_bundle.py) writes `{"ordinal": 0}` on the first call and deliberately exits successfully without producing any bundle on the second call.

Run from the repository root:

```bash
python -m orchestrator run experiments/mlevolve_pair/probes/missing_bundle.orc \
  --command-boundaries-file experiments/mlevolve_pair/probes/commands.json \
  --state-dir /tmp/mlevolve-retained-probe-state --quiet
```

Fresh observed result on the baseline: CLI exit 0, run status `completed`, `return__round: 2`, and `return__history: [{"ordinal": 0}, {"ordinal": 0}]`. The runtime consumed the previous iteration's bundle as the second result. A repeat after adding the malformed-output mode confirmed the same behavior; full state: `/tmp/mlevolve-retained-probe-state/20260929T205124Z-426g7y/state.json`.

This demonstrates a missing-freshness check on this repeated command boundary, not a failure of every contract or resume path. A structurally valid result does not establish that the current invocation produced it. The investigation does not repair the runtime or insert a cleanup wrapper to conceal the finding. Consequently stronger result delivery is not an unconditional ORC advantage in the current checkout.

## Interpretation limits

The two-branch specimen does not establish behavior with a large archive, embedding retrieval, arbitrary generated code, heterogeneous model APIs, GPU allocation, adaptive asynchronous scheduling, or exact MLEvolve search. It is also not a safety boundary for generated training code.

The code size of this workflow must not include the entire existing ORC runtime, nor exclude its authored configuration. Python must not be credited with equivalent durability or validation merely because its minimal loop is shorter. Conversely, an ORC contract does not prove metric correctness or search effectiveness.

## Concurrency boundary

The current language has no ordinary parallel command-map equivalent to Python's `ThreadPoolExecutor`. `list/map-effect` erases to an ordered bounded loop using normal call/checkpoint machinery. The existing behavioral check `tests/test_workflow_lisp_list_traversal.py::test_frontend_effect_map_runtime_commits_exact_calls_in_source_order` passed all four parametrizations during this investigation; it proves ordered calls/results, not a new timing benchmark.

`trial` supports concurrency across static `run-ref` arms, with pinned sources, trial workspace/evaluation machinery and its own restrictions. [Its normative contract](../../specs/dsl.md) explicitly excludes a general parallel block or dynamic arm builder. Provider peer groups and supervision implement provider protocols, not a pool of numerical command evaluations. None is an appropriate substitute just to make the comparison look symmetric.

An application-specific Python scheduler hidden under the ORC workflow would defeat the controller comparison. If concurrent evaluation is a required property, the clean choices are a general runtime capability with its own design and evidence, a separately justified execution service whose caller still owns selection, or a Python controller. The present sequential specimen cannot establish which investment is worthwhile.

## Recommendation

For an executable MLEvolve-inspired search now, prefer a Python controller. The tested ORC formulations do not yet deliver the same bounded sequential policy, even after removing UCT, semantic retrieval and concurrency. This is a frontend feasibility cost, not a reason to hide those decisions inside a Python command and describe the wrapper as an ORC implementation.

| Question | What the evidence supports |
| --- | --- |
| Does ORC improve the search algorithm or model quality? | No demonstrated advantage. The algorithm, proposals and evaluations determine those outcomes; this fixture does not benchmark model quality. |
| Does ORC remove search-policy code? | No. The explicit state, acceptance, repair, stagnation and fusion decisions still need to be authored. Compact composition hit compiler limits. |
| Does ORC help with contracts and diagnostics? | Yes, the isolated malformed-result probe demonstrates automatic type checking and source attribution. Small Python validators also cover these simple records. |
| Does ORC help with persistence and operations? | It supplies existing checkpoint/resume and run-observation machinery. Python here omits that machinery. The full controller cannot use it yet, and the stale-bundle probe limits claims about reliable result delivery. |
| Is ORC faster or cheaper? | Unmeasured for this controller because it does not compile. Python direct/subprocess measurements isolate transport overhead only. |
| Which is easier to change in this experiment? | Python: ordinary values compose without the observed expression-position and expansion limits. The ORC attempt needed scalar boundary declarations and explicit duplicated branches, and still failed. |

A coherent future ORC version would own the entire search policy and use native provider calls for proposals, with numerical execution at a well-defined command boundary. Its case would be strongest when reuse of the existing operational runtime matters more than unrestricted policy composition. Before adopting that design, the full sequential specimen should compile, match Python's trace/budget behavior, reject absent fresh results, and pass an actual interruption/resume check. These are acceptance conditions for future work, not additional runtime changes made by this investigation.

## Verification and delivery

The primary agent's final run collected **6 tests**, then passed all **6 in 0.81 s**. An independent harness invocation reproduced Python trace equality at budgets 3/7/12 and ORC's `pure_expr_payload_too_large` rejection. Its JSON is `/tmp/mlevolve-pair-final-evidence.json`; the retained specimen evidence remains the separate observation tabulated above. Independent specification and quality review approved the investigation, with another six-test pass. `git diff --check` was clean. The public malformed/missing-bundle runs are documented above; no full ORC search run or recovery success is asserted.

The changes remain uncommitted in `.worktrees/mlevolve-orc-python`, branch `investigate/mlevolve-orc-python`. Production runtime code and the main working tree's existing edits were not changed.
