# F1 Reloadable-Generator Extension Boundary

Diagnose the change amplification involved in maintaining reloadable PyTorch
CDI architectures. Design and implement the smallest coherent package-local
extension boundary that reduces cross-cutting edits while preserving current
construction, training, checkpoint and bundle reload, inference, public
configuration, and supported artifact behavior.

The boundary must cover the frozen built-ins `cnn`, `ffno`, `fno`,
`fno_vanilla`, `hybrid`, `hybrid_resnet`,
`hybrid_resnet_convnext_bottleneck`, `hybrid_resnet_ffno_bottleneck`,
`hybrid_resnet_ffno_ptychoblock_encoder`,
`hybrid_resnet_ptychoblock_ffno_encoder`, `neuralop_uno`,
`spectral_resnet_bottleneck_linear_decoder`,
`spectral_resnet_bottleneck_net`, and `stable_hybrid`, in that order, plus one
candidate-declared architecture whose implementation is distinct from every
built-in. Each architecture crosses the same configuration, construction,
training and optimizer, checkpoint and bundle persistence, fresh reload,
inference, structural-identity, and round-trip reconstruction lifecycle.

Produce working product code and tests, an architecture decision record, a
concise extension-author guide, a versioned candidate-evidence record, and the
fixed solution-neutral lifecycle adapter. The evidence record declares the
ordered built-in rows, the separate candidate witness, structural fields and
safe product-relative document paths. The other output paths, visible checks,
lifecycle schemas, hard-contract clauses, and claim limits are frozen by
`visible-task-contract.json`.

The exact Python runner, environment, invocation order, nineteen pre-edit
selectors, and separate candidate-owned selector are frozen by
`visible-check-manifest.json`; both required invocations must exit
successfully.

The evaluator runs each required invocation from its own fresh empty external
scratch working directory, outside the disposable exact-extract product copy.
Selectors and project imports still resolve against that product copy;
relative test and library outputs instead land in the invocation scratch
directory and are discarded. The product copy must retain the same exact
digest before and after every invocation. Do not assume that the process
working directory is the product root.

The lifecycle adapter is a benchmark seam, not a prescribed internal product
architecture. Its lifecycle-result responsibility is limited to materializing
one checkpoint and one bundle path for each requested architecture. It
receives per-case evaluator-owned configuration and CDI inputs whose paths and
bytes are digest-bound by the request. It does not author lifecycle
observations, process identities, structural values, artifact-era support,
implementation identities, or pass/fail claims.

The evaluator verifies the candidate-evidence, input, operation, and result
bindings, then independently loads and tamper-checks all artifacts. Every
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
