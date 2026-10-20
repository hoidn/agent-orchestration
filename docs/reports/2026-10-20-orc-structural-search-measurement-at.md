# ORC Structural Search Measurement Calibration: Interrupted Terra-Only AT

**Status:** historical execution record; stopped incomplete at the approved cap.
RPI passed both frozen calibration batches. PRR committed neither batch after
two native-agent control incidents. Combined calibration remains **OPEN, not
qualified**; this is not a measured PRR rubric failure. No B, B2, C or ORC
quality-comparison call followed.

The [measurement plan](../plans/2026-10-19-orc-structural-search-measurement-plan.md)
owns the remaining gates. Its code-first prerequisite was integrated in main
at `a92eeeea` before execution. The owner's existing conditional authorization
allowed A′ subject to no Claude; the accepted AT amendment planned four calls,
cap ten, using only `gpt-5.6-terra` at high effort. All ten observed native
sessions used that model and effort. No Claude or Fable session ran in AT.

## Frozen Inputs And Denominator

AT consumes the sole predeclared A′ alternative, the reference-free rubric.
It does not select A3. Runtime I_A2 remained clean at
`49cd27e6d3c059092e38fcf9836aa4bc50ae8b52`. Git freeze `997374d8` records
[judge-calibration-at.json](../../experiments/compare/criteria/judge-calibration-at.json),
SHA-256 `2963e39670c32962ac226fa4f8646029de5815f29d03eb1c0cea5bf66362de60`.
The original A/A2/F2 artifacts and seeds remain unchanged.

Each task has two nine-clone batches: four blind controls and the exact five
fillers from the corresponding A batch, with fresh clone IDs and no disclosed
reference. One Terra judge gives **four declared judge×batch pairs**, of which
only two completed. The two missing PRR pairs are not removed from the denominator.
No hidden tests were executed.

The unchanged rules require every pair to satisfy P1 (upstream − stub ≥ 4),
P2 (stub < partial < upstream), P3 (upstream − mutant ≥ 2), and each control's
cross-batch spread to be at most two. Both tasks must pass.

## Observed Calibration

Totals range from zero to eight; cells show batch 0 / batch 1.

| Task | Upstream | Stub | Partial | Mutant | P1/P2/P3 | Maximum spread | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RPI | 8 / 6 | 0 / 0 | 5 / 5 | 4 / 2 | All pass | 2 | Pass |
| PRR | Unavailable | Unavailable | Unavailable | Unavailable | Unmeasured | Unmeasured | Incomplete |

The [RPI result](/home/ollie/sc-pools/resume-projection-integrity/AT/records/results.json)
comes from the frozen harness join. All eighteen reasons were read;
[reason audit](/home/ollie/sc-evidence/AT/resume-projection-integrity-reason-audit.json)
retains the result hash and observations. Both mutant judgments identify the
unconditional return in `audit_scope`; scope/layering credit differs. The second
upstream judgment alleges persistence beyond the root failure envelope and
scores six instead of eight. These diagnoses were not independently validated
as part of this calibration; they do not alter the predeclared decision.

RPI's run is `20261020T173518Z-q3mlyj`. PRR's sole run is
`20261020T175209Z-66dgq7`; it has zero committed provider effects and no joined
ratings. The frozen close command exited one because both PRR batches must
finish in that run. No successful combined readout was fabricated.
The separate [interrupted readout](/home/ollie/sc-evidence/AT/interrupted-readout.json),
SHA-256 `a51789b3ce7b0abdc357b09a4c7526ac968c7de0c6e89ef43c1dc14a6a3fb56d`,
records the incomplete denominator and accounting.

## Execution Incidents

The first operator interruption happened after both RPI batches completed:
its effect-identity parser omitted the runtime's `/ else /` segment. A separately
hashed, independently reviewed [mechanical correction](/home/ollie/sc-evidence/AT/operator-correction.json)
fixed that interpretation without changing frozen scripts, runtime or scores.
RPI was not rerun. Its missing completion event was explicitly reconstructed
from terminal-memo filesystem time and hash; the subprocess return code remains
unknown, rather than being reported as zero.

The first PRR attempt launched three native Terra children despite the three
disabled multiagent feature flags. The coordinator stopped the process tree at
17:53:19 UTC before a judgment committed. A proposed external wrapper added
`-c agents.enabled=false`. Provider-free checks showed that configuration
removed collaboration instructions from `debug prompt-input`; a scripted
shim/guard/wrapper check preserved input, status, model restrictions and nested
PATH behavior. Independent review accepted a same-run, pending-only recovery.

That recovery also launched three native Terra children. The coordinator
stopped it at 18:03:04 UTC. Its actual native transcript retained collaboration
instructions and tools. The offline prompt check had not established effective
prevention on the executed route. The earlier approval is retained as historical
evidence and expressly superseded by the
[incident review](/home/ollie/sc-evidence/AT/native-agent-incident2-independent-review.json).

The generated shell scripts and parent launcher have valid PATH quoting.
However, the shim records argv before the guard/wrapper, and no final backend
argv or process environment was retained. Therefore the evidence does not
establish whether the wrapper was omitted or the CLI execution path ignored
the setting. The [postmortem](/home/ollie/sc-evidence/AT/native-agent-recovery-postmortem.json)
preserves that uncertainty. Effective native-agent prevention remains unqualified.

## Budget, Consumption And Hygiene

| Execution | CLI dispatches | Native children | Completed judge batches |
| --- | --- | --- | --- |
| RPI | 2 | 0 | 2 |
| PRR initial attempt | 1 | 3 | 0 |
| PRR recovery | 1 | 3 | 0 |
| Total | 4 | 6 | 2 |

The six children had no further descendants. Counting all ten provider sessions
exhausts cap ten; the shim's four call directories alone undercount consumption.
There is no remaining recovery allowance.

| Consumption evidence | Frozen list-price equivalent USD | Coverage |
| --- | --- | --- |
| Completed RPI | 1.8673224 | Two complete native receipts |
| Interrupted PRR roots and children | At least 0.7393364 | Eight last recorded cumulative totals; final consumption unavailable |
| AT total | At least 2.6066588 | Full total unavailable |

Each native PRR session is counted once. Its parent counters are not added again
from the standard parent-only shim receipts. Frozen `metering.receipts` and
`pricing.cost` provide the completed RPI accounting; the interrupted-session
supplement retains raw counters and applies the same frozen rates descriptively.
Parse-complete native JSONL is not proof of completed execution or complete
consumption. These are list-price equivalents, not billed spend.

Both pools passed final integrity checks: all 36 clones match their recorded
patches. Both automated scans report zero hits; manual action audits nevertheless
found the native delegation. All recorded actions were reviewed: no candidate
edits, test execution, protected solution reads or unrelated-session reads were
observed. The 220 historical file hashes and the AT criterion, original scripts
and frozen runtime remain intact. Native action provenance is retained under
[/home/ollie/sc-evidence/AT](/home/ollie/sc-evidence/AT).

## Verification And Consequence

The shared guard now explicitly requests `agents.enabled=false`. Its checks
passed: 83 focused tests, 83 collected tests, the affected public-CLI integration
selector after commit (one passed), and 318 broader comparison/evaluation tests
under `pytest -q -n 16 --dist=worksteal`. The earlier integration attempt used a
fixture cloned from the previous committed HEAD; it was not weakened.
These checks verify argument/configuration mechanics and scripted behavior;
they do not qualify effective live blocking.

The [AT preparation verification](/home/ollie/sc-evidence/preparation/AT-verification/verification.json)
separately records 44 focused passes and a broad run with 1423 passes/two
dirty-runtime refusals; both affected selectors passed after committing the
documentation edit. That broad run is not relabeled as all-green.

Gate 2 remains open because PRR is incomplete; gate 3 was not measured.
Completed RPI receipts are available, but complete AT consumption is unavailable.
B/B2/C and a live cumulative campaign remain unrun. Further recovery requires
verified enforcement on the actual executed route, accounting/cap coverage for
all dispatches, and a concrete new owner-budget decision. No additional rubric
revision or A3 is selected.

One judge supplies no cross-provider agreement evidence, and these controls
include no structurally different known-correct implementation. Reference
removal and judge-panel reduction also changed together. Neither RPI's pass
nor this interrupted calibration establishes ORC improvement, a quality
frontier, cost-effectiveness or causation by removing the reference.

## Subsequent Offline Diagnosis

After the stop, a [public run/resume trace](/home/ollie/sc-evidence/AT/offline-public-dispatch-trace.json)
reproduced the frozen runtime's dispatch with an inert backend. Both routes
reached the external wrapper, placing `agents.enabled=false` before `exec`
and the provider's effort override after it. A separate
[native exec parser probe](/home/ollie/sc-evidence/AT/offline-exec-config-scope.json),
with network egress disabled and credential files masked, demonstrated that
Codex 0.163.0 discards the top-level configuration when `exec` supplies its
own `--config`. The same invalid boolean was ignored in the former position
and rejected in the latter. This reproduces a concrete failure mechanism;
it does not recover the missing historical process argv.

The maintained guard now places its settings inside the `exec` configuration
scope. Frozen runtime, wrapper, operators, pools and completed judgments remain
unchanged. These offline checks made no remote model requests and do not
qualify live native-agent prevention. The ten-session accounting, incomplete
calibration and remaining gates are unchanged.
