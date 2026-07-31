# Lean Pilot A1-v7 Final Evidence Review

- **Review date:** 2026-07-31
- **Reviewer:** independent delegated final-evidence reviewer
  `/root/mc_final_spec_review_r2`
- **Verdict:** `LEAN_PILOT_FINAL_EVIDENCE_APPROVED`
- **Scope:** the immutable `a1-v7` lock, exact smoke/live denominator,
  calibration and blinding bindings, deterministic summary and Markdown view,
  retained treatment failures, usage handling, and claim limits

## Exact bindings

| Role | Path | SHA-256 |
| --- | --- | --- |
| Pilot lock | `/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v7/pilot-lock.json` | `b8d69ba2f3d2b2e7bc6d9181d776db0b7abacd2035f851cd44be613dac6d8503` |
| Sealed review bindings | `/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v7/evidence/review-bindings.json` | `2defb62dc0fc3f9187bc930d73a15265610b71c57ae4198b938b6c781b66f367` |
| Sealed unblinding bindings | `/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v7/evidence/unblinding-bindings.json` | `1c1f46273fd6ab6d779e7001f9b27fd60d3ff816ec817859fa2ff0955e525cf4` |
| Authoritative summary | `/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v7/summary-2026-07-31/pilot-summary.json` | `153263159d6516d032be83bd8f53954be0ba05b39af58be23d1abdca34085e89` |
| Deterministic Markdown view | `docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md` | `f5a0884fc14ee399d3753644180c380387d6a78b60315e2c445daffc1baffc3c` |

## Findings

The reviewer independently verified that the lock binds one smoke
(`b-8fbf73c9d6aa1278`) followed by the exact three-block valid live prefix
(`b-b5e157fc7ffaca68`, `b-ed345c592d9b1d50`, and
`b-5970f312e6698e50`). The review and unblinding bindings are complete and in
the required order. Deterministic regeneration produced the exact summary and
Markdown digests above.

The summary truthfully retains four treatment-specific `PROTOCOL_FAILURE`
outcomes. `DIRECT` was viable in 3/3 blocks and won all three `DIRECT_VS_ORC`
comparisons. `ORC` was viable in 1/3 blocks. The
`COORDINATOR_VS_ORC` comparison contains one coordinator win, one ORC win, and
one nonviable tie. All input-token, output-token, and cost values remain
`UNKNOWN`. The six blinded reviewer results agree; no adjudication occurred.

The evidence supports only the declared `exploratory_controlled_task` claim.
It does not establish general `.orc`, Workflow Lisp, or orchestration
effectiveness; does not establish strict provider isolation; and does not
authorize a prospective benchmark or product change. The preserved `a1-v5`
incident and superseded prelaunch `a1-v6` supplied provenance only. No pilot
attempt was resumed, rerun, or imported into the `a1-v7` denominator.

## Verdict

`LEAN_PILOT_FINAL_EVIDENCE_APPROVED`

The reviewed evidence may proceed to its owner-decision handoff without a
second review. A second review is required only after a concrete evidence
violation and material repair.
