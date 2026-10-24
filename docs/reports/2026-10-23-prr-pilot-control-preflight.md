# PRR Pilot: Natural-Control Preflight

**Role:** Captured independent behavioral checks and a pre-spend stop; not a new quality score, model ranking or direct-versus-ORC result.

**Result:** The bounded review did not establish the hypothesized functional ordering of the preselected first LS11 Sol-high patch and first LS10 Luna-high patch. That fixed-pair evaluator selection stopped before any new provider call. The [pilot plan](../plans/2026-10-23-prr-direct-orc-pilot-plan.md) records the unexecuted protocol and bounded corrective work.

## What was checked

The reviewer reconstructed both original patches against the same seeded base, verified byte-identical patch round trips before and after testing, and confirmed that imports came from each disposable reconstruction. It used the exact frozen command-recovery task and public fixtures. Previous blind ratings supplied neither expected test results nor independent truth.

| Behavior | First Sol-high patch | First Luna-high patch |
| --- | --- | --- |
| Settled command recovery | Completed; expected outputs and execution counts | Completed; same expected outputs and counts |
| Missing, invalid and non-restorable checkpoint authority | All three rejected correctly | All three rejected correctly |
| Public profiled-union example | Completed with expected outputs | Completed with expected outputs |
| Frozen fixture's final pure-row assertion | Passed | Rejected a permitted full skipped row |

Both recovery runs produced `return__count=5`, `return__value="completed-4"` and `return__derived=8`, with execution counts `first=1` and `retry=2`. The retained diagnostics found no pure bundles, private versions, pure checkpoint records or pure restore bindings in either run.

The frozen fixture reported four passing cases for Sol and three passing cases plus one failure for Luna. Its `_pure_rows_are_shells` helper requires every recorded pure row to be an exact completed shell. Task item 3 instead explicitly keeps failed and skipped rows as full durable rows. Luna's differential row was an inactive-branch skip, not an improperly persisted successful pure value. The reported failure therefore does not establish the expected functional ordering.

One bounded continuation probe attempted to interrupt the public union before a second pure projection. Compilation produced only one relevant projection, so the intended interruption never occurred in either candidate. The probe's failed precondition is retained as a diagnostic limitation, not counted as a candidate failure or evidence about resumed replay. No further search for a favorable case or replacement control was performed.

## Consequence and limits

The evidence establishes several working behaviors in both patches and identifies a fixture mismatch. It does **not** establish equal overall quality, refute every historical judge diagnosis, or independently validate the historical score gap. LS11's recorded scores and score-based difficulty result remain unchanged; its separate evaluator prerequisite remains unmet.

No evaluator or pilot call was launched: **zero new provider starts; the historical total remains 76**. No synthetic implementation defect, hidden test, replacement solution or expanded control search was used. The maintained fixture and capped-call guard are the only corrective implementation selected; the frozen task and original observations remain immutable. A corrected fixture alone neither qualifies a new task package nor supplies the missing control ordering.

## Corrective verification

The maintained fixture now accepts valid full failed/skipped rows, including an unvisited inactive-branch skip, while retaining exact successful-shell, visit and forbidden-artifact checks. It also rejects an explicit contradiction between a full row's status and outcome. Separately, any explicitly capped comparison call now prohibits nested provider CLI launches; three declared outer calls remain possible under cap three, and the fourth is refused before its backend.

Focused fixture regression checks passed all 23 cases. The related comparison/guard/model-policy suite passed all 140 cases with `python -m pytest -q -n 16 --dist=worksteal`. The guard's focused 22-case proof includes actual tmux/interactive-shell routes and uncapped compatibility. All provider backends in these checks were scripted.

Separate reconstructed copies of both original patches passed all four public workflow cases with the corrected fixture overlay (`0a0fb44a2d08e6585171328affa349d5897eab79a9ff8cac59156eb6a93afa49`). The subsequent status/outcome refinement (`c80726127d70d09a5ed67f421bd67b56472a23376277a6fce1a15fbb243db71f`) passed the regression suite and was executed against those retained real workflow states. The workflow cases were not rerun after that refinement. These are correction diagnostics, not a new functional ranking or task qualification.

Verification logs are under `/home/ollie/sc-evidence/preparation/PRR-P1-preparation-verification/`; the separate workflow diagnostic is `/home/ollie/sc-evidence/preparation/PRR-P1-corrected-fixture-diagnostic/diagnostic-results.json`, SHA256 `ec2969c0c410bcf93ae12189e30225c35bb362de2e3dc50dfb723c04b6aa0931`.

## Evidence

Canonical independent review: `/home/ollie/sc-evidence/preparation/PRR-P1-control-verification/control-review.json`, SHA256 `994815035b531c457927c8082debe45ac2af3513a2c97292a4f1c11432953f80`. The coordinator independently verified all 43 referenced files. Its original command output, states, counters, reconstruction identities and limitations are retained there.

| Original artifact | SHA256 |
| --- | --- |
| First LS11 Sol-high raw patch | `b6551ae2ac1438025c2a9538dce2c41e0dcb003e7cba0e57eff6f0a60cc0f135` |
| First LS10 Luna-high raw patch | `a72fa25836c68775f26a172fdf5953580a1a4c89005ee0eaed75c3d7f8578aa4` |
| Frozen public command-recovery fixture | `925c2fd038648c0198aa91c0d5129698cb45cbbce496f945c8f2b707426de0ff` |

The [LS11 report](2026-10-23-luna-sol-high-command-recovery-calibration.md) owns the earlier blind scores. This follow-up owns only the independent checks and stop described above.
