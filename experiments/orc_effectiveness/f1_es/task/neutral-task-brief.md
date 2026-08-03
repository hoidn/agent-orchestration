# F1 Reloadable-Generator Extension Boundary

Diagnose the change amplification involved in adding a reloadable PyTorch CDI
architecture. Design and implement the smallest coherent package-local
extension boundary that reduces cross-cutting edits while preserving current
construction, training, checkpoint and bundle reload, inference, public
configuration, and supported artifact behavior. Demonstrate it with one
migrated representative architecture and one small witness architecture.
Document ownership, schema evolution, compatibility, rejected alternatives,
and limitations.

Produce working product code and tests, an architecture decision record, a
concise extension-author guide, a versioned candidate-evidence record, and the
fixed solution-neutral lifecycle adapter. The evidence record declares safe
product-relative paths for the architecture decision record and author guide.
The other output paths, visible checks, lifecycle schemas, hard-contract
clauses, and claim limits are frozen by `visible-task-contract.json`.
The exact Python runner, environment, invocation order, ten pre-edit selectors,
and candidate-owned selector are frozen by `visible-check-manifest.json`; both
required invocations must exit successfully.

The evaluator runs each required invocation from its own fresh empty external
scratch working directory, outside the disposable exact-extract product copy.
Selectors and project imports still resolve against that product copy; relative
test and library outputs instead land in the invocation scratch directory and
are discarded. The product copy must retain the same exact digest before and
after every invocation. Do not assume that the process working directory is the
product root.

The lifecycle adapter is a benchmark seam, not a prescribed internal product
architecture. Its only lifecycle-result responsibility is to materialize four
artifacts: checkpoint and bundle outputs for the representative and witness
architectures. It receives an evaluator-owned base configuration and CDI
fixture whose paths and bytes are digest-bound by the request. It does not
author lifecycle observations, process identities, structural values, or
pass/fail claims.

The evaluator verifies the candidate-evidence, input, operation, and result
bindings, then independently loads and tamper-checks all four artifacts. Every
lifecycle, construction-identity, structural-roundtrip, fresh-process, and
inference assertion is evaluator-derived through approved public APIs rather
than accepted from adapter-authored claims.

Every request path is relative to the evaluator-owned directory containing
`request.json`, and every result artifact path is relative to the
evaluator-owned directory containing `result.json`. The adapter must resolve
those paths against the corresponding record root, never against its current
working directory or an assumed candidate-workspace root.

Do not assume a descriptor name, registry layout, payload nesting, class name,
file count, or other particular internal representation. Existing physics,
loss, scaling, and data ownership remain outside the new extension boundary.
The study is task-specific and makes only the claim limits in the visible
contract.
