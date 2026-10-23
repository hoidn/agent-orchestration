# Natural task-difficulty calibration: interrupted pilot

Role: captured experiment evidence. This report does not authorize more calls.
The [selected plan](../plans/2026-10-22-simple-evaluation-calibration-plan.md)
owns prospective selection and recovery; the incident is not a task-quality result.

## Outcome

The pilot is **INVALID_MODEL_POLICY / INCOMPLETE**. Neither task has a valid
weak/strong comparison. No quality scores were accepted and no hidden tests ran.

The owner corrected calibration to mean a noticeable quality gap between fresh,
natural outputs of weaker and stronger agents, without deliberate defects.
The frozen design was two Luna-high and two Terra-high direct attempts for each
of `resume-projection-integrity` (RPI) and `pure-result-replay` (PRR), followed by
one blind Terra-high judging session per task. The existing four independent
components total 0–8; each task requires `mean(Terra) - mean(Luna) >= 2`.
All four natural observations are required. No synthetic controls or references
enter the pool. Ten sessions were planned, capped at ten including nested calls.

## Observed execution

| Role | Planned sessions | Observed starts | Accepted observations |
| --- | ---: | ---: | ---: |
| Luna high, direct generation | 4 | 2 | 0 |
| Terra high, direct generation | 4 | 0 | 0 |
| Terra high, blind judging | 2 | 0 | 0 |
| Forbidden Claude/Fable probes | 0 | 4 | 0 |

Both Luna attempts were working on RPI. One started the repository's broad local
pytest suite in an interactive tmux shell. Legacy design-delta workflow tests
mocked `ProviderExecutor` but still executed readiness probes through raw
`subprocess.run(["claude", ...])`. All four native API-request records name
`claude-fable-5-1`; two contain Fable assistant responses and two were interrupted
without responses. This was real provider activity, not simulated test metadata.

The operator stopped both original attempts when it observed forbidden assistant
metadata. Neither generation run has a terminal result. A subsequent process
check found no remaining process with a working directory under the experiment
work root. There were no observed Codex native children, additional attributed
Codex roots or Claude sidechains.

The independent inventory counts at least **six** starts, not the two reported
by the original operator counter. That counter omitted Claude CLI roots and
only detected Claude after an assistant response. Incomplete evidence and absent
responses do not make those calls free or remove them from the budget.

## Cause and correction

A zero-provider command-resolution check reproduced the guard bypass: with the
same guarded inherited PATH, plain Bash and noninteractive login Bash resolve
the guarded Claude binary; interactive Bash and interactive login Bash resolve
`~/.local/bin/claude` instead. Codex continued to resolve through its guard in
that check. This reproduces a bypass consistent with the tmux route; retained
incident evidence does not establish the exact historical PATH transition.

The reviewed correction hides Claude installation/auth/config paths inside the
experiment sandbox when the binding explicitly forbids Claude and removes its
credential environment. This prevents the observed direct CLI route even if PATH
changes. Recovery must also count every scoped Claude CLI start, including calls
without an assistant response. Offline verification passed 202 affected tests with
`-q -n 16 --dist=worksteal` in tmux and
four public CLI smoke checks, using fake providers. The original runtime and
criterion remain unchanged. The correction is integrated in `bda0f693`; the
[authorized recovery](../plans/2026-10-22-simple-evaluation-calibration-plan.md#recovery-td2-budget-approved)
uses a new snapshot and packet. The owner subsequently authorized ten new
sessions within a total cap of sixteen, including these six incident starts; TD2
is running and has no quality verdict yet.

## Evidence and limits

- Frozen runtime: `b067d37ce1bdf96f7281c1e0265384727cbb24e5`.
- Criterion SHA256: `d92fccd9ff6a661bfc11032e47688906b83268c6b0fc80e995083be7c5c59b24`.
- Generation packet SHA256: `e3dc89e7036fde367fbca217470de9e23698347866375fb76085df5bee7d784b`.
- Operator SHA256: `64744665d3d480510a4f6e3c65893fd0c003bc3e5ee8b93ba4ece79ebd619c83`.
- External evidence root: `/home/ollie/sc-evidence/TD-20261022`.
- Independent `incident-inventory.json` SHA256:
  `691ff43b28987bd950fae97aec8a10c2e4c51da24c0c67249de79b9f157f8e69`.
- `interactive-shell-resolution-summary.json` joins the zero-call resolution
  checks to their raw source; native transcript identities, receipt counters,
  run paths and hashes are preserved in the incident inventory.

All 364 protected historical files retained their hashes. The original criterion,
operator, aborted runs and native evidence remain unchanged. The total cost is
unavailable: Luna has no frozen price, both Luna runs were interrupted, and two
Claude requests have no response usage. Claude's two available telemetry costs
sum to USD 1.3196; that is neither a complete total nor a frozen-table estimate.

The earlier AS exercise used artificial controls and cannot establish task
difficulty. This interrupted natural pilot establishes neither a difficulty gap
nor ORC benefit. A fresh complete repetition needs ten sessions; after the six
observed starts, it exceeds the original cap and requires a new recorded budget.
