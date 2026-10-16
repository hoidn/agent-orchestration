# Provider Prompt Routing Review

Review requested before the native-session CLI experiment. Baseline: `fc497229`.
This report distinguishes existing fixes from remaining work; no real provider
was invoked for this review.

## Disposition Of The Recommendations

| Recommendation / claim | Observation at review baseline | Disposition |
| --- | --- | --- |
| Render the selected delivery action instead of asking the agent to choose | New ordinary evaluated attempts already select `file/1`, with the write action first and one concrete path occurrence | Implemented by [provider result delivery](../design/provider_result_delivery.md); verified locally |
| Final assistant text is a dead branch everywhere | OMP strips the output-path binding and its flat executor materializes normalized assistant text | Incorrect globally; retain the supported transport and historical replay bytes |
| Omit irrelevant relpath guidance | `file/1` walks nested types and emits the note only for contracts containing relpath | Implemented; legacy and flat output-position rendering remain unchanged |
| Remove application-level transport paragraphs | Both chess prompt assets already omit those paragraphs | Implemented |
| Show nested JSON instead of internal field aliases plus JSON pointers | Record/union rendering exposes both; the compiler and validator have separate uses for them internally | Implemented as versioned `file/2`; [rendering report](2026-10-13-provider-json-rendering.md). Internal contract fields remain intact |
| Every renderer change breaks existing runs | Delivery rendering is now recorded in provider input parts; historical commits select their recorded renderer | Resolved for delivery rendering; future changes need a new version, not an in-place edit of `file/1` |
| Prompt tests should stop asserting phrasing | Current delivery tests inspect schema, selection, paths and dataflow; a stored pre-change prompt additionally protects replay identity | Keep the replay fixture: its byte equality is a persistence contract, not a preference for prose |
| Agents need queue-specific injection rules | The agent design gives each turn its current typed contract; prompt-queue is superseded for first delivery | No new queue injection mechanism is needed |

The baseline `file/1` contract for a `String` result is:

```text
## Output Contract
Write the JSON value specified below to the file on the `- path:` line, with a file-writing or shell tool, before you finish. The environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH names the same file. Returning the value in your reply does not deliver it.
- path: attempt/result.json
  format: JSON value
  type: string
```

The comparison establishes differences in instructions, not a measured causal
reduction in model mistakes. The [delivery closeout](2026-10-13-provider-result-delivery-closeout.md)
records the small real smoke and the outstanding measurement limit.

## Confirmed OMP Integration Gap

The evaluated path selected `legacy` for OMP but did not implement its
parent-materialization exception. `effect_execution.perform_external` called
`launch_provider`, then `runtime._validate_attempt_outcome` called
`provider_result`, which read `result.json`. No intermediate step created that
file from OMP's normalized result. A local fake-executor reproduction returned
valid normalized JSON and exit zero, retained stdout, and then failed with
`provider_result_missing`.

The existing OMP delivery test exercised preparation refusal, so its passing
result did not establish successful OMP result delivery. The [correction plan](../plans/2026-10-13-evaluated-omp-result-delivery-fix.md)
uses the actual prepared transport mode, exclusive creation through the pinned
attempt-file owner, and the existing result validator. Ordinary providers keep
their file-delivery requirement; arbitrary stdout is not a fallback.

Correction status: implemented and independently reviewed (contract PASS,
quality PASS). The prepared OMP metadata mode selects parent materialization;
only successful, nonempty normalized output can be written. Empty or absent
normalized output fails with `provider_result_missing`, even when a valid
result file was planted. Existing files and symlinks are preserved and cause a
recorded failure. Raw stdout and stderr remain evidence. No renderer bytes or
delivery digests were changed by this correction.

## Presentation Follow-On

The user selected nested JSON presentation as follow-on work, explicitly
without blocking the direct CLI campaign. `file/2` now preserves optional
fields, unions, container types, path constraints and authored guidance while
showing their actual nesting. Internal aliases and pointers remain in the
compiled contract and disappear from the provider-facing display. The native CLI
probe already supplies JSON schemas directly and never uses the pointer-based
prompt renderer; its evidence remains distinct from the public `.orc`
integration checks of the new display.

OMP still receives `legacy` wording, and the logical-workspace prompt preface
still contains a file-writing instruction. A dedicated text-delivery rendering
would need to select the correct instruction in both places. The chess task
prose also still describes its position as “one text value” although the result
is now `MoveOutcome`; whether this causes model confusion is unmeasured. These
observations are not claims that every prompt family has been simplified.

## Verification

Fresh baseline checks:

- `python -m pytest -q tests/test_prompt_contract.py tests/test_prompt_contract_recursive_schema.py tests/test_workflow_evaluated_provider_delivery.py`: **180 passed in 16.98s**.
- Three public replay tests in `test_workflow_evaluated_resume_replay.py`: **3 passed in 10.72s**, covering old commits without a delivery part, rejection of unknown renderings, and the checked-in pre-change run.
- Independent read-only review confirmed the OMP caller chain, supported text transport, current selector behavior, and the correction plan.

Post-correction verification:

- The changed provider-delivery module collects **18 tests**. New regressions were observed failing before the fix, including acceptance of a planted file when normalized output was absent.
- Coordinator command `python -m pytest -q -n 16 --dist=worksteal tests/test_prompt_contract.py tests/test_prompt_contract_recursive_schema.py tests/test_workflow_evaluated_provider_delivery.py tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_provider_reads.py tests/test_workflow_evaluated_prompts.py tests/test_workflow_evaluated_resume_replay.py`: **243 passed in 17.97s**.
- Independent reviewer reran the provider-delivery module: **18 passed**. A further public CLI check with a fake OMP transport and planted result leaf returned exit 1, `evaluated_execution_failed`, and no commits; the memo remained readable.
- Public integration checks use a fake transport at the provider boundary. No real OMP binary or account was exercised, and no improved model-compliance rate is claimed.

Local logs and rendered specimens: `/tmp/provider-delivery-review-20261013-mmkr0md6/`.

The native-session probe invokes provider CLIs directly and does not use this
renderer. It has now launched under the existing authorization; the
[live report](2026-10-13-native-session-cli-live.md) records observations and
stop reasons. This review does not qualify native-session continuation,
exclusivity, or recovery.
