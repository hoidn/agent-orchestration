# ORC Structural Search Measurement Calibration: Completed Terra-Only AT

**Status:** historical execution evidence; AT completed all four declared
judge×batch pairs and **FAIL_NOT_QUALIFIED**. RPI passes; PRR fails strict P2
ordering in one batch. This is known-control judge calibration, with no ORC
benefit, quality frontier or cost-effectiveness claim. The
[measurement plan](../plans/2026-10-19-orc-structural-search-measurement-plan.md)
owns remaining decisions and gates; this report selects no further execution.

The [interrupted report](2026-10-20-orc-structural-search-measurement-at.md)
preserves the original cap 10 stop and two native-agent incidents. The owner
subsequently approved up to ten additional sessions, overall cap 20. The
continuation completed only the two pending PRR batches in the original run;
completed RPI observations were preserved. This is the same sole predeclared
A′ alternative, with no further rubric revision or A3.

## Frozen Result

The authoritative [combined readout](/home/ollie/sc-evidence/AT/combined-readout.json)
has SHA-256 `d7209bbb1a74cb6f14e9bb4db7e8fdfdd2a388467395297a10d58be8972c66d0`.
Its values come from the frozen harness clone-ID joins. Runtime
I_A2 remains `49cd27e6d3c059092e38fcf9836aa4bc50ae8b52`; git criterion freeze
`997374d8` and criterion SHA-256
`2963e39670c32962ac226fa4f8646029de5815f29d03eb1c0cea5bf66362de60`
are unchanged. Original F2, operator scripts, masks and pool inputs remain intact.

One `gpt-5.6-terra` high-effort judge scored two batches per task, four declared
pairs in total. Each batch has four blind controls and five fillers, with no
disclosed reference. Scores range from zero to eight.

| Task | Batch | Upstream | Stub | Partial | Mutant | P1 | P2 | P3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RPI | 0 | 8 | 0 | 5 | 4 | Pass | Pass | Pass |
| RPI | 1 | 6 | 0 | 5 | 2 | Pass | Pass | Pass |
| PRR | 0 | 6 | 0 | 0 | 4 | Pass | **Fail** | Pass |
| PRR | 1 | 5 | 0 | 2 | 3 | Pass | Pass | Pass |

P1 requires upstream − stub ≥ 4; P2 requires stub < partial < upstream;
P3 requires upstream − mutant ≥ 2. Frozen `error_rate = 0` permits no failing pair.
PRR's P2 failing fraction is 1/2; the first partial ties the stub at zero.
All P1/P3 pairs pass. Each task's maximum cross-batch anchor spread is2,
within the unchanged limit 2. No pairs are missing and no judge is excluded.
Both tasks must pass, so the combined scientific result fails.

RPI run `20261020T173518Z-q3mlyj` is unchanged. PRR run
`20261020T175209Z-66dgq7` now has both batches committed. The two interrupted
attempts remain in its history; neither produced a completed judgment to rescore.

## Qualified Continuation

[Continuation packet v2](/home/ollie/sc-evidence/AT/budget20-continuation-packet-v2.json),
SHA-256 `b625327686b4c123ae1ad7bd30422c4f27a38df183ae306abab44caa4c89212c`,
binds the adapter, selfchecks, v7 proof, exact installed CLI and external v2
wrapper. The wrapper places native-agent settings inside `exec` configuration
scope. It preserves the frozen runtime and original operators.

[Native qualification v7](/home/ollie/sc-evidence/AT/offline-native-catalog-qualification-verdict-v7.json)
passed with zero remote model calls. Actual native exec requests against an
inert local Responses provider showed the enabled collaboration catalog and
working `list_agents` handler; disabling agents removed that namespace, and
an exact fabricated `collaboration.spawn_agent` call was locally refused.
Four local requests used the production model/effort/guard argv. A private,
credential-free CODEX_HOME selected the isolated transport. This qualifies
native registration/refusal for the pinned installed CLI and exact wrapper;
it supplies no general prevention promise for direct API or absolute-binary bypass.

The [independent review](/home/ollie/sc-evidence/AT/budget20-continuation-independent-review.json)
accepted this exact pending-only packet. Its fresh checks passed nine selfcheck
groups, manifest preflight, all 12 bound-file hashes, 243 protected hashes,
v7 positive/negative controls and 121 unchanged mask roots. The public dry-run
exited 0 with no new calls and preserved the existing PRR memo. Root independently rechecked the saved
native proof and reran preflight before launch.

The continuation exited 0 after 373.75 seconds, with no watchdog stop, new native
children or extra native roots. Only two new Terra-high sessions ran; actual
metadata and final lineage were audited. The prior incident reviews remain
historical evidence and do not become successful prevention evidence retroactively.

## Budget And Cost Coverage

| Execution | CLI sessions | Native children | Completed batches |
| --- | --- | --- | --- |
| Original RPI | 2 | 0 | 2 |
| Interrupted PRR attempts | 2 | 6 | 0 |
| Qualified PRR continuation | 2 | 0 | 2 |
| Total | 6 | 6 | 4 |

All 12 sessions used Terra high, within overall cap 20. The eight unused sessions
are mechanical-recovery allowance. There are no pending effects to recover;
the allowance does not transfer to rescoring, A3, B/B2/C or another campaign.

| Consumption evidence | Frozen list-price equivalent USD | Coverage |
| --- | --- | --- |
| Completed RPI | 1.8673224 | Two complete native receipts |
| Completed PRR continuation | 1.7394904 | Two complete native receipts, call IDs 3/4 |
| Interrupted PRR roots and children | ≥0.7393364 | Last observed cumulative totals only |
| All AT | **≥ 4.3461492** | Complete total unavailable |

[Completed PRR metering](/home/ollie/sc-evidence/AT/budget20-completed-PRR-metering.json)
joins only the two continuation native sessions through frozen
`metering.receipts` and `pricing.cost`. Historical interrupted sessions are
retained once, without adding their parent-only shim counters again. The frozen
2026-10-19 price table gives standard short-context list-price equivalents,
not billed spend. Missing final interrupted consumption keeps the full AT cost
unavailable; the lower bound cannot establish cost-effectiveness.

## Hygiene, Gates And Limits

Final pool verification checked all 36 clones. Automated scans had zero hits;
all 243 protected file hashes remain intact, including criterion, original operators
and RPI evidence. The frozen runtime retains its exact commit and clean tree. The coordinator's
[manual audit](/home/ollie/sc-evidence/AT/budget20-manual-audit.json)
cleared 46 structured continuation actions and read 18 PRR rating reasons.
No candidate edits, unit/hidden-test execution, protected solution reads or
unrelated-session reads were observed. The reasons were not independently
validated as technical diagnoses. No Claude or Fable session ran.

Gate 2 is **FAIL_NOT_QUALIFIED**; gate 3 remains unmeasured. Complete receipts
exist for the four completed judge batches, but complete AT consumption remains
unavailable. B/B2/C and live cumulative campaigns remain unrun and separately
gated. A′ is complete and failed; no rescoring or A3 is selected. Any new
measurement design needs a separate owner decision. The continuing no-Claude
restriction and the owner's policy against hidden tests as the primary measure
remain in force.

One judge supplies no cross-provider agreement evidence. There is no
structurally different known-correct control. Reference removal and panel
reduction changed together, preventing causal attribution. Calibration failure
rejects this frozen measure; it establishes no conclusion about ORC benefit.
