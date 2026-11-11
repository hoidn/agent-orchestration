# Round 4 skeptic review: REVISE; numerical C4 counterexample, failed evidence integrity

**Uncalibrated exploration. Overall eligibility=false.** Calibration was owner-waived, not passed. Family/evaluator qualification and operational relevance remain unestablished. This review makes no universal-impossibility, model-quality, or engineering-effort claim.

The recorded measurements refute the exact C4 dispatch-saving margin: an independently implemented conventional baseline achieves zero unapproved dispatches, matching Orc on each seed. However, my checkpoint-inspection action changed recorded SQLite shared-memory files. The unchanged runner's integrity verifier now returns false. I therefore vote **REVISE**, not an acceptance-eligible COUNTEREXAMPLE. The smallest repair is fresh evidence for the unchanged candidates, with SQLite inspection confined to copies. This is an evidence repair, not permission to retune the claim or oracle.

## Exact bounded claim and evidence identity

The claim string is copied verbatim from the immutable source claim.json:

> In the four-case synthetic implementation-drift configure suite with public seeds 11,23,47, the typed-Python/generated-.orc debugger incurs at least one fewer unapproved repair-tool dispatch summed over helper_drift_partial and config_drift_completed for every seed than the strongest equal-budget baseline, while both arms pass all five checks on every case and Orc adds no total I/O, effective repairs, disruption, or escalation.

Proposal: `artifacts/implementation-drift-20261023T102317Z/round-4/builder/manifest.json`.
Challenge: `artifacts/implementation-drift-20261023T102317Z/round-4/skeptic-20261023T104603Z/manifest.json`.
Evidence: `artifacts/evidence/dda36d7986b04999a409d45cf8cd49fb/report.json`.

Evidence digest: `9fce118eebf69a7af80359d30dfec19383e61d9747b370d44a1f5e40de54ccb7`.
Runner SHA-256: `861a5e077faf5dcb713cf85d3ea351e4036c71442c43278907474d1eb0bfc01d`.

I read the retained runner source; its bytes match both report.runner_sha256 and the current recorder. The new [reviewed runner copy](official-audit-003/runner-reviewed.py) preserves that identity. The [predeclaration check](predeclaration-check.json) confirms exact byte equality with the earlier declaration, while retaining its disclosed lack of an independently trusted timestamp.

The criterion remains baseline-minus-Orc >=1, separately for each seed, summed over only the two primary cases. All five checks apply to all nine cases; total_io, effective_repairs, disruptions and escalations require per-case noninferiority. Extra cases, wall time, source length, or attractive diagnostics cannot replace the dispatch margin.

## Serious review-integrity failure: S13-REVIEW-INTEGRITY

The supplied evidence.valid was true. My first audit successfully passed the canonical digest, all 2,073 recorded artifact hashes, all 39 source hashes and runner identity before failing its SQLite inspection: immutable=1 ignored WAL contents, leaving no checkpoints table visible in a base database.

In parallel I ran the frozen `skeptic_controls.py` against the official evidence. Although it uses SQLite `mode=ro`, opening the databases updates WAL shared-memory state. That action changed **15 recorded `.sqlite-shm` files**. I should have run it against copies. [review-error.json](review-error.json) lists every affected path and its recorded/current digest. No restoration, evidence rewrite, source change, or metric change was attempted. The first failed audit source is retained in `official-audit-001/failed-review_audit.py`.

The final [audit](official-audit-003/audit.json) confirms the remaining **2,058/2,073 artifacts** still match, including every result, trace, source, database and WAL file. It copied DB/WAL pairs before querying checkpoints and verified that this final inspection caused no further recorded-file changes. This cannot make the original evidence intact again. The exact runner [verification result](integrity-verification.json) is **false**. A second audit output (`official-audit-002`) had a variable-shadowing error in its changed-file metadata; it is superseded by audit-003 and retained. Neither audit correction changed experimental code or recorded data.

S13 is a blocking reviewer error, not an experimental-arm loss or evidence of an Orc advantage. The original numerical records remain useful for interpretation but cannot pass this protocol's integrity gate.

## Numerical finding: S01-PARITY

| Public seed | Orc primary unapproved | LangGraph + SHA primary unapproved | Saving | Required |
|---|---:|---:|---:|---:|
| 11 | 0 | 0 | 0 | >=1 |
| 23 | 0 | 0 | 0 | >=1 |
| 47 | 0 | 0 | 0 | >=1 |

All 54 recorded main executions pass all five checks: **270 true checks**. I rescored every trace, independently recounted service dispatches against original software maps, compared each result with the report, read 414 raw suite/case/command/check logs, and checked all 27 causal pairs. Journals, outages, software changes, external interventions, final truth and all non-time metrics match. Terminal status/evidence/reason also match. Every noninferiority criterion holds. The baseline's zero is the metric's lower bound; no finite-search inference is needed to refute this particular saving on these cases.

| Case, each arm/seed | I/O | Attempts / effective / rejected | Disruption / escalation |
|---|---:|---|---|
| clean | 2 | 0 / 0 / 0 | 0 / 0 |
| helper_drift_partial | 4 | 1 / 1 / 0 | 10 / 1 |
| config_drift_completed | 4 | 1 / 1 / 0 | 1 / 0 |
| irrecoverable | 9 | 3 / 0 / 0 | 0 / 1 |
| skeptic_helper_drift_completed | 4 | 1 / 1 / 0 | 1 / 0 |
| skeptic_config_drift_partial | 4 | 1 / 1 / 0 | 10 / 1 |
| skeptic_drift_pending_reads | 6 | 1 / 1 / 0 | 1 / 0 |
| skeptic_overlapping_incomplete | 12 | 0 / 0 / 0 | 0 / 1 |
| skeptic_completion_at_dispatch | 5 | 1 / 0 / 1 | 0 / 0 |

Each arm totals 150 I/O, 123 observations, 27 repair attempts, 15 effective repairs, three rejected actions, 69 synthetic disruption units, 15 deliberately injected process losses, 30 downtime ticks, and twelve appropriate escalations. Unsafe effects, duplicate audit keys, and unapproved dispatches are zero. Every escalation's final missing-participant list and generation match recorded truth. No main DUT exception, timeout, false recovery or unnecessary escalation appears. Fifteen nonzero Orc subprocess exits are expected `effect_input_diverged` refusals followed by successful reconciliation; they are preserved, not hidden as ordinary exits. The separate 15 losses per arm are applied-effect/lost-receipt injections, not unexpected crashes.

## Baseline strength, controls and attribution

The frozen baseline executes LangGraph 1.2.16 functional tasks/entrypoint with SQLite checkpointer 3.1.2, synchronous durability, typed interrupts, strict Pydantic 2.10.3 boundaries, GNU sha256sum 9.4 and durable pre-dispatch intent files. Completed tasks reuse results; uncertain uncommitted tasks reacquire observations rather than treating intent as successful effect. Copied checkpoint inspections confirm real tables in 27 databases. Actual mypy 2.4.0 strict checking passes ([receipt](mypy-receipt.json)); disclosed skips mean this is not whole-program static verification. The separate boundary controls reject a known count-field type error, malformed string/bool integers, extra fields, unknown decisions and mismatched permits. Immediate deterministic authorization does not test stale human approvals.

Orc executes the actual Python API/generated .orc through the pinned 0.2.0 source at bb9cb30d, TARGET 2.39. Python is 3.13.9. Both arms share domain policy, transport, service deployment, actuator allowlist and read-only reconciliation. Both see the same six-file closure and current deployment bytes. Budgets are equal: 24 I/O, three actual repair attempts, twelve ordinary rounds, eight reconciliation reads within the same I/O cap, one restart, 25 seconds per case and 120 per suite. Both inner arms are deterministic, with zero live/recorded model outputs, prompts, tokens or delegation. Package inventory matches the frozen report; nothing was installed.

The five added cases use the documented noncolliding CASES interface. Swapping helper/config drift prevents file-name-to-outcome shortcuts. Pending work must finish before fresh growth proves recovery. Overlapping faults abstain without speculative repair. Completion at dispatch is rejected by the shared action-time guard. No frozen oracle or original case was changed.

I also rescored all 70 traces and read 560 logs in the unchanged challenge development matrix, including all sixteen ablation executions ([local audit](local-ablation-audit-001/audit.json)). There is exactly one failed execution: omitted-closure Orc `helper_drift_partial` performs **four actual attempts**, so bounded=false. All other checks remain true. S12-REPLAY-BUDGET therefore remains a concrete limitation of this workflow's replay accounting, not a main full-closure failure.

| Seed-11 variant, primary cases | I/O | Unapproved / rejected |
|---|---:|---|
| Full checks, either arm | 8 | 0 / 0 |
| Orc deployment closure omitted | 14 | 4 / 4 |
| Baseline SHA disabled | 12 | 2 / 2 |
| No drift, Orc | 15 | 0 / 2 |
| No drift, LangGraph | 13 | 0 / 0 |

My strongest attempted dismissal—that the actuator allowlist makes byte checks useless—fails: removing checks wastes changed-code service entries even when effects are blocked. **I concede useful byte-drift detection in both implementations**, including Orc's integrated dependency diagnostic. Read-only reconciliation supplies the recovery decision; a refusal alone proves neither restored acquisition nor justified escalation. These controls separate content validation, replay and domain policy. They supply no model-quality or measured ergonomics advantage.

Eight additional causal controls and eight copied-trace mutations passed: stale epoch, pending/completion races, unapproved reset, missing/wrong action-time snapshots, missing/changed software maps, false growth, unhealthy truth, unbound evidence and empty explanation. The earlier S10 action-time oracle defect is not reproduced in this scorer. Recorder honesty and escalation semantics remain trust boundaries: diagnostic_useful means current linkage plus nonempty text, not expert causal diagnosis.

## Relevance, costs and remaining objections

The painful candidate task is resuming a debugger after a repair applied without a receipt, detecting a deployment change, then distinguishing genuine acquisition recovery from current incompleteness. **Incident frequency and operator time saved are unknown.** Supplied primary evidence establishes related mechanisms, not this combined operational incident or its approved recovery.

The supplied 2026-10-22/23 snapshot of [LCLS2 control at 04d36d15](https://github.com/slac-lcls/lcls2/blob/04d36d15c222ec6dbc10b833bf0c3ef5059a5c34/psdaq/psdaq/control/control.py) documents configure phases, correlation and existing state guards; [DaqLCLS2 at 4a3f2504](https://github.com/pcdshub/pcdsdaq/blob/4a3f2504b4d6f1860457ecfc40aaaf28115a777f/pcdsdaq/daq/lcls2.py) supplies validation and asynchronous completion/status handling. [SLAC AMI THAG005](https://proceedings.jacow.org/icalepcs2025/pdf/THAG005.pdf) already supplies mypy compatibility checking and monitoring. Those tools are not executed here, and no advantage over their controls/status features is inferred. These are supplied provenance citations, not newly fetched evidence. All work used local synthetic tools.

S02-RELEVANCE remains blocking: an independent DAQ expert must determine incident correspondence, frequency if known, trustworthy observation/deployment mirrors, atomic-permit feasibility, actual costs and approved targeted repair/escalation. The software-hash comparator is appropriate for this experiment; no file-production DAG requires a Snakemake imitation. [Orc's pinned command contract](https://github.com/hoidn/agent-orchestration/blob/bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2/docs/design/workflow_command_adapter_contract.md) covers declared bytes, not automatic dependency discovery, sandboxing, rollback or physical truth.

S06-LEAKAGE remains blocking: every case, seed and oracle is public development material; none was independently withheld. Runtime resource packaging excludes evaluator modules but is cooperative discipline, not concealment. Three deterministic seeds vary generation/event increments, not incident families. Observed savings [0,0] are not a confidence interval or statistical reliability estimate. No qualification receipt exists.

S03/S04 remain bounded to intact-disk SIGKILL and the tested fresh/action-time evidence. S05 scientific experiment/run/detector/config/calibration lineage and partial XTC/SMD completion are outside scope; epoch and byte hashes cannot establish them. Arbitrary byte-check/service-use TOCTOU, delayed approvals, host power loss and exactly-once effects are untested. S07 attribution is shared policy plus conventional content checking. S08/S10 scorer controls pass locally; physical qualification remains absent. S09 costs include all attempts, rejected actions and glue. S11 now has official measurements and this REVIEW, but the opponent's ANSWER and final integrity gate remain pending; S13 prevents a valid acceptance.

Official per-case wall min/median/max is Orc **3402/4717/4899 ms**, baseline **755/1338/1412 ms**. These include startup/compiler/checkpoint/validation/restart costs and are secondary observations, not replacement acceptance criteria or facility latencies. Source inventories retain 117 baseline lines, 133 Orc-specific workflow/wrapper/adapter lines plus command manifest, 118 shared Python lines, and 432 evaluator lines, excluding declared auxiliary audit/control code and JSON. Both arms maintain schemas, wrappers, dependency inventories and recovery policy; LangGraph adds intents/checkpoint/interrupt glue, Orc adds explicit closure/program contracts and refusal handling. No authoring hours, migration cost or long-term maintenance outcome was measured. Numerical parity cannot refute a future precisely measured ergonomics claim.

## Verdict and smallest decisive next step

Typed judgments: **REVISE; fair=true; relevant=false; reproduced=false; eligibility=false**. Fair describes the equal local experimental comparison. Relevant is false for qualified LCLS-II usefulness. Reproduced is false for acceptance of the supplied digest after its recorded-artifact integrity failure; substantive trace rescore and conventional numerical parity are separately demonstrated.

Preserve C1–C3 retractions, C4's exact failed margin and S12. Obtain a fresh mechanical execution of the **same frozen proposal/challenge**, same seeds/cases/oracle/pins and budgets. Inspect SQLite only after copying DB/WAL files; verify the fresh recorder digest before and after both role reviews. The builder must answer the zero-dispatch construction and integrity blocker. For any operational-advantage claim, also resolve S02 and S06; a calibration waiver supplies neither determination.

One-command reproduction of this read-only evidence audit, using a NEW destination under artifacts:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python artifacts/implementation-drift-20261023T102317Z/round-4/skeptic-review-20261023T110019Z/review_audit.py artifacts/evidence/dda36d7986b04999a409d45cf8cd49fb artifacts/NEW-review-audit
```

It reports the existing 15 SHM mismatches, audits all main traces/logs, runs causal/mutation controls, and queries only database copies. It does not claim the current evidence passes integrity. For a fresh full numerical comparison, the challenge dossier's `skeptic_reproduce.py NEW-DESTINATION --ablations` command executes actual libraries and retains the expected omitted-closure bound failure. Neither local reproduction can replace the runtime's current evidence digest.
