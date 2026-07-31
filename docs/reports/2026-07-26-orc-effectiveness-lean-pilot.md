# Lean Pilot Evidence Summary

- Record kind: `pilot_summary.v1`
- Summary ID: `summary-a1-lean-pilot-2026-07-27-r5`
- Pilot lock digest: `sha256:b8d69ba2f3d2b2e7bc6d9181d776db0b7abacd2035f851cd44be613dac6d8503`
- Status: `EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED`
- Valid blocks: 3
- Excluded attempts: 0

## Valid Block Outcomes

- `b-b5e157fc7ffaca68` (`sha256:f7be072ad77d13cf13a312f6a8e76ee11b84e934fdf6450d078874f8b73d032e`)
  - DIRECT_VS_ORC: A_WIN (A_ONLY; quality=NOT_APPLICABLE)
  - COORDINATOR_VS_ORC: A_WIN (A_ONLY; quality=NOT_APPLICABLE)
- `b-ed345c592d9b1d50` (`sha256:217efb31a549087e292d4c3d0b94ba292dd3043729d1cacdc002660e04238119`)
  - DIRECT_VS_ORC: A_WIN (A_ONLY; quality=NOT_APPLICABLE)
  - COORDINATOR_VS_ORC: TIE_NONVIABLE (NEITHER; quality=TIE; review digests=sha256:3636ac7e8e3a0c3c1bf0f1317e0ecfef3f8837c985e5043474c949aa4885b5d5, sha256:05f024ce729bdd8bd6e9ec44971e08b9aa20fcaf41e2edceaf2b9c03049962ec)
- `b-5970f312e6698e50` (`sha256:e5c3c5d8fca11860d48864cc1f4164d7b80df26cba62751754899f659b8f72c2`)
  - DIRECT_VS_ORC: A_WIN (BOTH; quality=A; review digests=sha256:881cf86d2fdcdef1a158fedceaf3211e82de0a3616c1f7080d48c5fe5443b2d9, sha256:b10b517fdf63f330666fe96798733c3f1551987033fe9a86f2f43f5139cb07b4)
  - COORDINATOR_VS_ORC: B_WIN (B_ONLY; quality=NOT_APPLICABLE)

## Excluded Attempts

- None.

## Comparison Counts

- DIRECT_VS_ORC: A=3, B=0, ties=0, indeterminate=0, nonviable ties=0
- COORDINATOR_VS_ORC: A=1, B=1, ties=0, indeterminate=0, nonviable ties=1

## Treatment Statistics

- DIRECT: viable=3, nonviable=0, provider calls=[1, 1, 1]
  - Lifecycle outcomes: BLOCKED=0, CHECK_FAILURE=0, COMPLETED=3, EXHAUSTED=0, LAUNCH_FAILURE=0, NONZERO_EXIT=0, PROTOCOL_FAILURE=0, TIMEOUT=0
  - Failure classes: BLOCKED=0, CHECK_FAILURE=0, EXHAUSTED=0, LAUNCH_FAILURE=0, NONZERO_EXIT=0, PROTOCOL_FAILURE=0, TIMEOUT=0
- COORDINATOR: viable=1, nonviable=2, provider calls=[5, 1, 1]
  - Lifecycle outcomes: BLOCKED=0, CHECK_FAILURE=0, COMPLETED=1, EXHAUSTED=0, LAUNCH_FAILURE=0, NONZERO_EXIT=0, PROTOCOL_FAILURE=2, TIMEOUT=0
  - Failure classes: BLOCKED=0, CHECK_FAILURE=0, EXHAUSTED=0, LAUNCH_FAILURE=0, NONZERO_EXIT=0, PROTOCOL_FAILURE=2, TIMEOUT=0
- ORC: viable=1, nonviable=2, provider calls=[1, 1, 7]
  - Lifecycle outcomes: BLOCKED=0, CHECK_FAILURE=0, COMPLETED=1, EXHAUSTED=0, LAUNCH_FAILURE=0, NONZERO_EXIT=0, PROTOCOL_FAILURE=2, TIMEOUT=0
  - Failure classes: BLOCKED=0, CHECK_FAILURE=0, EXHAUSTED=0, LAUNCH_FAILURE=0, NONZERO_EXIT=0, PROTOCOL_FAILURE=2, TIMEOUT=0

## Review Diagnostics

- Agreement count: 6
- Disagreement count: 0
- Adjudication count: 0
- Guess accuracy: 0/1
- `b-b5e157fc7ffaca68`: package `b-b5e157fc7ffaca68` (`sha256:9adb41ae367863ed0de0c8b70fa305c7c4c38feb9826a003974cbbe14f451c1b`); initial reviews agree=True; disposition=NOT_APPLICABLE
  - Initial review `b-b5e157fc7ffaca68-calibration-reviewer-01` by `calibration-reviewer-01`: `sha256:bc9fffc90fbf4550095c029fb3df92387176ed8a46420f9cca841ade198a7373` at `b-b5e157fc7ffaca68/reviews/calibration-reviewer-01/review-result.json`
  - Initial review `b-b5e157fc7ffaca68-calibration-reviewer-02` by `calibration-reviewer-02`: `sha256:8a98bf76eea48320cb22fa1f1c8ddceac1a134e72fc1fc69c728e655ad757bc7` at `b-b5e157fc7ffaca68/reviews/calibration-reviewer-02/review-result.json`
- `b-ed345c592d9b1d50`: package `b-ed345c592d9b1d50` (`sha256:34f02396191dec3cae701bb674512d20de12a7f9c11c05949f8c58e828ad5e46`); initial reviews agree=True; disposition=NOT_APPLICABLE
  - Initial review `b-ed345c592d9b1d50-calibration-reviewer-01` by `calibration-reviewer-01`: `sha256:3636ac7e8e3a0c3c1bf0f1317e0ecfef3f8837c985e5043474c949aa4885b5d5` at `b-ed345c592d9b1d50/reviews/calibration-reviewer-01/review-result.json`
  - Initial review `b-ed345c592d9b1d50-calibration-reviewer-02` by `calibration-reviewer-02`: `sha256:05f024ce729bdd8bd6e9ec44971e08b9aa20fcaf41e2edceaf2b9c03049962ec` at `b-ed345c592d9b1d50/reviews/calibration-reviewer-02/review-result.json`
- `b-5970f312e6698e50`: package `b-5970f312e6698e50` (`sha256:142320b4bf4f20e4015520583c535efcf22e8713552c152a25719c1473377cde`); initial reviews agree=True; disposition=NOT_APPLICABLE
  - Initial review `b-5970f312e6698e50-calibration-reviewer-01` by `calibration-reviewer-01`: `sha256:881cf86d2fdcdef1a158fedceaf3211e82de0a3616c1f7080d48c5fe5443b2d9` at `b-5970f312e6698e50/reviews/calibration-reviewer-01/review-result.json`
  - Initial review `b-5970f312e6698e50-calibration-reviewer-02` by `calibration-reviewer-02`: `sha256:b10b517fdf63f330666fe96798733c3f1551987033fe9a86f2f43f5139cb07b4` at `b-5970f312e6698e50/reviews/calibration-reviewer-02/review-result.json`
- Guess confusion:
  - DIRECT -> DIRECT: 0
  - DIRECT -> COORDINATOR: 0
  - DIRECT -> ORC: 0
  - DIRECT -> UNKNOWN: 6
  - COORDINATOR -> DIRECT: 0
  - COORDINATOR -> COORDINATOR: 0
  - COORDINATOR -> ORC: 0
  - COORDINATOR -> UNKNOWN: 6
  - ORC -> DIRECT: 0
  - ORC -> COORDINATOR: 0
  - ORC -> ORC: 0
  - ORC -> UNKNOWN: 6

## Hard-Contract Findings

- `b-b5e157fc7ffaca68` / ORC: PROTOCOL_FAILURE -> TREATMENT_OUTCOME_RETAINED
  - Evidence: `b-b5e157fc7ffaca68/arm-c8249bc890b6327e/stdout.txt`
  - Evidence: `b-b5e157fc7ffaca68/arm-c8249bc890b6327e/stderr.txt`
  - Evidence: `b-b5e157fc7ffaca68/arm-c8249bc890b6327e/raw-result.json`
  - Evidence: `b-b5e157fc7ffaca68/arm-c8249bc890b6327e/environment.json`
  - Evidence: `b-b5e157fc7ffaca68/arm-c8249bc890b6327e/check-stdout.txt`
  - Evidence: `b-b5e157fc7ffaca68/arm-c8249bc890b6327e/check-stderr.txt`
- `b-ed345c592d9b1d50` / COORDINATOR: PROTOCOL_FAILURE -> TREATMENT_OUTCOME_RETAINED
  - Evidence: `b-ed345c592d9b1d50/arm-672e32482a646dce/stdout.txt`
  - Evidence: `b-ed345c592d9b1d50/arm-672e32482a646dce/stderr.txt`
  - Evidence: `b-ed345c592d9b1d50/arm-672e32482a646dce/raw-result.json`
  - Evidence: `b-ed345c592d9b1d50/arm-672e32482a646dce/environment.json`
  - Evidence: `b-ed345c592d9b1d50/arm-672e32482a646dce/check-stdout.txt`
  - Evidence: `b-ed345c592d9b1d50/arm-672e32482a646dce/check-stderr.txt`
- `b-ed345c592d9b1d50` / ORC: PROTOCOL_FAILURE -> TREATMENT_OUTCOME_RETAINED
  - Evidence: `b-ed345c592d9b1d50/arm-049be278ee1735c0/stdout.txt`
  - Evidence: `b-ed345c592d9b1d50/arm-049be278ee1735c0/stderr.txt`
  - Evidence: `b-ed345c592d9b1d50/arm-049be278ee1735c0/raw-result.json`
  - Evidence: `b-ed345c592d9b1d50/arm-049be278ee1735c0/environment.json`
  - Evidence: `b-ed345c592d9b1d50/arm-049be278ee1735c0/check-stdout.txt`
  - Evidence: `b-ed345c592d9b1d50/arm-049be278ee1735c0/check-stderr.txt`
- `b-5970f312e6698e50` / COORDINATOR: PROTOCOL_FAILURE -> TREATMENT_OUTCOME_RETAINED
  - Evidence: `b-5970f312e6698e50/arm-6f1bb7bab50582e3/stdout.txt`
  - Evidence: `b-5970f312e6698e50/arm-6f1bb7bab50582e3/stderr.txt`
  - Evidence: `b-5970f312e6698e50/arm-6f1bb7bab50582e3/raw-result.json`
  - Evidence: `b-5970f312e6698e50/arm-6f1bb7bab50582e3/environment.json`
  - Evidence: `b-5970f312e6698e50/arm-6f1bb7bab50582e3/check-stdout.txt`
  - Evidence: `b-5970f312e6698e50/arm-6f1bb7bab50582e3/check-stderr.txt`

## Exact Metrics

- Median elapsed_milliseconds / DIRECT: 569897/1
- Median cost_microunits / DIRECT: UNKNOWN
- Median input_tokens / DIRECT: UNKNOWN
- Median output_tokens / DIRECT: UNKNOWN
- Median elapsed_milliseconds / COORDINATOR: 227180/1
- Median cost_microunits / COORDINATOR: UNKNOWN
- Median input_tokens / COORDINATOR: UNKNOWN
- Median output_tokens / COORDINATOR: UNKNOWN
- Median elapsed_milliseconds / ORC: 235971/1
- Median cost_microunits / ORC: UNKNOWN
- Median input_tokens / ORC: UNKNOWN
- Median output_tokens / ORC: UNKNOWN
- Ratio elapsed_milliseconds / ORC:DIRECT: 235971/569897
- Ratio elapsed_milliseconds / ORC:COORDINATOR: 235971/227180
- Ratio cost_microunits / ORC:DIRECT: UNKNOWN
- Ratio cost_microunits / ORC:COORDINATOR: UNKNOWN
- Ratio input_tokens / ORC:DIRECT: UNKNOWN
- Ratio input_tokens / ORC:COORDINATOR: UNKNOWN
- Ratio output_tokens / ORC:DIRECT: UNKNOWN
- Ratio output_tokens / ORC:COORDINATOR: UNKNOWN

This report is exploratory controlled-task evidence only.
