# Evaluated OMP Result Delivery Correction

> Use `superpowers:subagent-driven-development`. Preserve unrelated work; no commits or real-provider experiments in this correction.

**Goal:** Make the evaluated provider path honor the existing OMP parent-materialization contract before continuing the native-session experiment.

**Authority:** [Providers](../../specs/providers.md), especially the `omp_json_stdout` exception; [result delivery](../design/provider_result_delivery.md); [delivery closeout](../reports/2026-10-13-provider-result-delivery-closeout.md). The user requested that the prompt-routing review be addressed before the previously authorized native-session campaign.

**Finding:** `launch_provider` captures a successful OMP response, then `provider_result` requires `result.json`. No evaluated caller materializes the normalized OMP result. The flat executor already does. A local fake-executor reproduction returns `provider_result_missing` for successful normalized JSON. The existing OMP delivery test exercises preparation refusal only.

**Approach:** In the evaluated launch owner, use the prepared invocation's actual OMP metadata mode to recognize its structured transport. After successful execution, write its normalized result bytes exclusively through the pinned attempt-file owner. Preserve the captured raw stdout as evidence. Leave schema/type/artifact validation to `provider_result`. Ordinary providers still must write their own file; no generic stdout fallback. Preserve every prompt-rendering byte and delivery digest.

**Tradeoff:** Result-file creation has two owners selected by the existing transport: OMP's parent and ordinary providers. Tests must keep that distinction explicit. This does not qualify a real OMP binary or native-session continuation.

## Scope

- `orchestrator/workflow/evaluated/providers.py`: transport-specific materialization after success, using existing descriptor-relative exclusive creation and existing failure diagnostics.
- `tests/test_workflow_evaluated_provider_delivery.py` (or a focused companion if needed): success, invalid result, nonzero/transport error, missing normalized result, planted file/symlink, and ordinary-provider stdout-only rejection. Include an integration check through the evaluated public run path with a fake provider transport, without a model call.
- `docs/reports/2026-10-13-provider-prompt-review.md`: disposition of the user's four recommendations, local evidence, remaining schema-display work, and this correction.
- Correct directly misleading OMP statements in `docs/design/provider_result_delivery.md` without changing its selected rendering or the flat-route contract.

## Steps

- [x] Independent reviewer checks the bounded plan against the existing OMP contract and result ownership.
- [x] Implementer writes and observes a failing regression, then makes the minimal correction. Reuse normalized transport output; never parse raw stdout as a substitute.
- [x] Run collection and narrow tests for changed modules, including ordinary stdout-only rejection and a public evaluated integration case.
- [x] Independent review checks contract compliance, exclusive creation, failure behavior, evidence retention and replay stability.
- [x] Coordinator inspects the diff and runs relevant affected modules under tmux with `pytest -q -n 16 --dist=worksteal` after narrow checks. No full repository suite unless findings require it.
- [x] Record observations and remaining work in the report. Resume the direct native-session plan only after this requested review is addressed.

## Review Disposition Already Verified

- New ordinary evaluated calls already use action-first `file/1`; flat and older committed rows retain `legacy` bytes for replay.
- `file/1` already suppresses irrelevant relpath guidance; chess prompts no longer duplicate transport instructions.
- Final assistant text is a live OMP transport, so global deletion is incorrect.
- Records/unions still expose internal field names and JSON pointers. A nested JSON presentation would need a new rendering version while preserving existing constraints and guidance. The user selected that follow-on change without blocking the direct CLI campaign.
- The native-session experiment invokes CLIs directly and does not use this renderer.

Fresh pre-change verification: 180 renderer/provider-delivery tests and 3 public replay tests pass. Logs: `/tmp/provider-delivery-review-20261013-mmkr0md6/`.

Correction complete: independent contract/code review PASS; 243 affected tests pass. See the [review report](../reports/2026-10-13-provider-prompt-review.md) for exact commands, negative-case evidence and the separately selected JSON presentation work. No real OMP call was made.
