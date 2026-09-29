# MLEvolve-inspired ORC/Python comparison implementation plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` to execute and review this plan. This is an executable feasibility investigation, not a production MLEvolve port or a language-change project.

**Goal:** Develop comparable `.orc` and idiomatic Python search controllers and identify supported advantages, disadvantages, and unresolved gaps using executable evidence.

**Architecture:** Each language independently owns the complete search policy, state, acceptance decisions, repair routing, fusion, and stopping. Both use the same stateless proposal fixture and numerical evaluator. The `.orc` implementation must not call a Python search controller, selector, journal updater, or resume coordinator.

**Tech stack:** Current Workflow Lisp compiler/runtime; Python standard library; existing pytest. No new dependencies, paid model calls, or GPU workloads.

**Review:** The independent Sol-6 plan review approved this bounded feasibility investigation, requiring stateless leaves with no hidden decisions and separate attribution of controller, transport and runtime costs.

**Outcome:** Investigation complete. Python direct/subprocess specimens execute and agree; the full ORC specimen is retained as a reproducible compiler rejection (361 expression nodes against a 256-node limit). No full ORC runtime parity, timing or recovery result is claimed. Independent specification and quality reviews approved the scoped findings; see the [report](../reports/2026-09-29-mlevolve-orc-python-comparison.md).

## Scope and assumptions

- The user requests side-by-side implementations inspired by MLEvolve, not a behavior-preserving port. Compare the same policy first, then distinguish language ergonomics from algorithm choice.
- The user explicitly selected sequential versions first. Both executable controllers use the same sequential schedule. Concurrency is a documented boundary only; do not implement a concurrent arm.
- This substitutes scripted proposals for LLM responses. Numerical evaluation is real; no ML quality, MLE-bench, model cost, or GPU throughput conclusions follow.
- Use two candidate branches and bounded experience history. Retrieval embeddings and UCT are not required by this policy and receive no Python compatibility layer.
- What this makes harder: scaling to many branches, semantic retrieval over large histories, arbitrary dynamic parallel scheduling, and exact MLEvolve behavior. Report these boundaries rather than obscuring them with adapters.
- Work in `.worktrees/mlevolve-orc-python` on `investigate/mlevolve-orc-python`, based on `fc5f2a2e`. Existing changes in the main workspace are outside scope. Baseline: 96 selected expression, command-contract and rich-loop-resume tests passed.

## Governing references

Read `docs/index.md`, `docs/capability_status_matrix.md`, `docs/lisp_workflow_drafting_guide.md`, and the relevant frontend/command/result/state contracts. Target 2.29+ carries rich loop values; do not generalize the older 2.18 list limits. Use existing explicit bindings when effect placement requires them. `docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md` records known composition/recovery risks, not an implemented replacement runtime.

## Common experiment contract

The candidate is integer coefficients `(a, b)` for `a*x + b*x*x`. A stateless evaluator computes floating-point squared error against `2*x + 3*x*x` on a fixed, documented evaluation set. It also rejects out-of-domain coefficients with an explicit invalid result. The scripted proposal leaf exposes improve/repair/fuse operations from explicit arguments; it never selects the operation, ranks candidates, owns controller state or persists search decisions. If history is passed, it must actually affect the requested proposal; otherwise disclose that learning is limited to controller-owned incumbents, failure state and stagnation rather than semantic retrieval.

The common controller:

1. Evaluates two distinct seeds, initially `(1, 0)` and `(0, 1)`.
2. Alternates branch improvement. Strictly better valid scores replace the incumbent; ties retain it. Unsuccessful attempts increment that branch's stagnation counter.
3. After an invalid candidate, prioritizes one repair of that candidate on the same branch in the next iteration. Each evaluation, including repair, consumes the same budget.
4. Fuses the two incumbent branches when both have stagnated. Fusion uses both candidates and is selected in the controller.
5. Stops on a valid zero-error solution or budget exhaustion. `.orc` uses Float ordering, not Float equality, and a literal safety bound on its loop.
6. Retains attempt history. The initial structured command handoff was rejected by the current compiler; the paired boundary therefore passes scalar coefficients and history length, which is sufficient for this scripted proposal fixture. History remains controller-owned, and semantic history retrieval is not claimed.

Freeze concrete tie-breaking, failure and budget behavior in the experiment README before implementation. Adapt domain details only if both arms change together. Keep the number of branches intentionally fixed; do not build a search framework.

## Task 1: Implement and verify the paired specimen

Expected files, with consolidation preferred:

- `experiments/mlevolve_pair/search.orc`: all ORC policy and state.
- `experiments/mlevolve_pair/search.py`: all Python policy and state, ordinary functions/dataclasses as needed.
- `experiments/mlevolve_pair/leaves.py`: shared stateless proposal fixture, evaluator, and command transport only.
- `experiments/mlevolve_pair/commands.json`: explicit external-tool contracts.
- `experiments/mlevolve_pair/compare.py`: orchestration of the comparison, evidence collection, isolated output workspaces, failure probes, timing and source-size accounting. No search decisions.
- `experiments/mlevolve_pair/README.md`: frozen contract and reproducible commands.
- `tests/experiments/test_mlevolve_pair.py`: small behavioral/integration tests of the comparison.

- [x] Write the behavioral check before implementation: expected search route, both branches, invalid-result repair, stagnation, fusion, strict acceptance and evaluation budget.
- [x] Implement the independent Python controller and domain leaves, including strict candidate/evaluation validation.
- [x] Attempt the full `.orc` controller through public compile/run commands. Compact and explicit control-flow forms were tried; final compilation rejects an oversized pure expression. Full ORC execution remains unavailable, not silently substituted.
- [x] Assert equal ordered traces, final incumbent and budget accounting between direct/subprocess Python at budgets 3, 7 and 12. ORC parity cannot be asserted after compilation fails.
- [x] Run isolated malformed/missing-result probes: malformed output is rejected; an absent fresh bundle can reuse the prior iteration's output. Full-controller interruption/resume could not be exercised; existing smaller rich-loop resume tests passed. No runtime repair or restart workaround was added.
- [x] Record Python direct/subprocess timings and authored code/configuration separately from leaves/harness. Record compile-rejection latency separately from execution; no ORC execution or durable-storage measurement is available. Shared JSON format does not imply identical bundle-freshness semantics.
- [x] Assess concurrency as a documented boundary only, following the user's sequential-first choice. No concurrent arm or hidden Python scheduler in ORC.
- [x] Collect six tests and pass the narrow module; independently repeat through tmux. Public runtime probes and the full-controller compile rejection supply integration evidence. No full-suite run is needed for these isolated experiment files.
- [x] Obtain specification review, address findings, then obtain quality review. Both approved; primary also read code, evidence and verification outputs.

## Task 2: Integrate evidence and report

- [x] Primary agent reads all new code, resulting diff and fresh verification output.
- [x] Write the report with revision, policy, boundaries, commands, results, authored costs, errors and limits. Link specimens and evidence, and route it from `docs/index.md`.
- [x] Compare Python minimal execution against ORC runtime features fairly: validation is present; Python durability is omitted and its equivalent implementation cost unmeasured. Existing runtime source is excluded from authored counts.
- [x] Describe where each approach helps and give a scoped recommendation. The compiler failure is retained without a hidden Python selector or runtime modification.
- [x] Leave the isolated worktree and evidence reviewable. No unrelated refactors, production runtime fixes, repository-wide suite, commits or publishing were performed.
