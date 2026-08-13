# F1 Configuration Ownership

Diagnose and remove the change amplification caused by configuration ownership
being spread across the product. Implement one coherent public configuration
surface while preserving the behavior exercised by the frozen checks.

The completed product must:

- resolve simulation, training, inference, and runtime-execution configuration
  through declared public entry points;
- give file mappings and command-line patches a strict, documented precedence;
- apply torch execution configuration transactionally, without leaving partial
  or ambient state after a rejected update;
- reject unknown or ill-typed input rather than silently accepting it through a
  tolerant compatibility path;
- isolate retired configuration state from modern entry points;
- validate mappings at the boundary and derive public input fields from one
  authority;
- preserve source provenance across a fresh-process round trip; and
- migrate production consumers across both backends, command-line entry points,
  workflow components, and study scripts to the public surface.

Produce working product code and tests, the fixed
`scripts/es_f1_config_resolution_adapter.py`,
`es_f1_candidate_evidence.json`, and
`tests/test_es_f1_config_ownership.py`. Also produce a configuration decision
record and a migration guide at safe product-relative paths declared in the
candidate evidence. The evidence declares public resolution symbols and
clause-scoped evidence paths; it does not declare evaluator observations,
provenance findings, verdicts, or quantitative implementation measurements.

The exact runner, environment, pre-edit checks, separate candidate-owned check,
output schemas, hard clauses, and claim limits are frozen by the visible task
assets. Every required invocation must pass. Checks run from fresh external
scratch directories against an exact disposable product copy, whose bytes must
remain unchanged by verification. Do not assume the process working directory
is the product root.

The adapter is a path-materialization seam, not a prescribed product
architecture. It receives evaluator-owned file mappings and command-line
patches bound by digest and returns only safe paths to resolved records. The
evaluator independently derives precedence, transactional behavior, strictness,
consumer closure, provenance, cross-surface coherence, bypass classification,
and pass/fail state.

The candidate evidence also declares the four fixed evaluation hooks defined by
its schema. Each hook accepts one JSON object and returns one JSON object; hooks
expose product behavior and test seams only, never observations or verdicts.
The evaluator invokes and audits the described product targets independently.

Request paths are relative to the directory containing `request.json`; result
paths are relative to the directory containing `result.json`. Do not assume a
module name, class hierarchy, record nesting, file count, or internal
representation. The study is task-specific and makes only the claim limits in
the visible contract.
