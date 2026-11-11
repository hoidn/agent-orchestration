# Verification record

Verified on 2026-10-23 UTC, macOS arm64, Python 3.14.6.

| Check | Observed result |
|---|---|
| Pinned upstream tarball comparison | 4,288 regular source files compared; zero differences |
| `bash run.sh compile` | Success with the actual pinned compiler, target 2.39 |
| `bash run.sh dry-run` | Exit 0; typed inputs and bindings accepted |
| `bash run.sh test` | **32 passed in 39.53 seconds** |
| `bash -n run.sh` | Exit 0 |
| Independent follow-up review | No remaining blocker in evidence-integrity, malformed-root, and overflow fixes |

Coverage includes paired seeds and asymmetric results, incomplete reports,
path escape/collision refusal, source mutation, malformed manifest roots,
nonfinite aggregate rejection, evidence/report/source/log/manifest tampering,
explicit model environment forwarding, refusal of arbitrary environment names,
trial timeouts, public CLI compilation, positive and negative consensus,
disagreement with history propagation, budget exhaustion, missing expert input,
false eligibility, stale digests, mismatched claims, malformed provider output,
invalid budgets, known static type mismatch before dispatch, completed replay,
and failed-review resume reusing committed trials.

Provider outputs in these tests are deterministic substitutes. The synthetic
suite deliberately gives the two arms different results to test evidence
accounting; it is not a DAQ model or a scientific result. No live adversarial
debate, inner-agent performance study or facility operation was completed.

An early test-harness shebang contained the workspace path's space, causing PATH
fallback to the installed unauthenticated provider CLI. It failed before a model
response. The harness now uses `/usr/bin/env python3` with an explicit test PATH;
the final suite uses only the fixture executable.

Shell invocations on this host emitted an existing `LC_ALL=C.UTF-8` locale
warning; commands completed with the exits listed above.

The current compiler rejected a bound nested-record return during development;
explicit constructors fixed it without changing upstream. This observed
limitation is documented in the Orc audit rather than hidden from the skeptic.

The integrity check detects ordinary artifact drift through acceptance. It does
not make directories immutable or defend against malicious same-user code.
Completed-run resume reuses committed effects; it is not a fresh empirical
evaluation or an ongoing integrity monitor.
