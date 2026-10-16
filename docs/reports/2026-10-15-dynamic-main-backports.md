# Selected main backports into the dynamic branch — 2026-10-15

Status: completed and integrated into `feat/orc-dynamic-core-cutover`, preserving the reviewed local documentation overlay. The full suite remains red as recorded below. This report records execution of the [reviewed plan](../plans/2026-10-15-dynamic-main-backports-plan.md); it does not select native adoption or change the default profile.

## Source pins and delivered scope

- Dynamic base: `1ecde6e4566cf38a9d9f642e4e5c74e45d71b368`.
- Main inspection pin: `6005b5c1f105057a41a5a57882e5df90abf44118`.
- Product and consumer changes: `df65b7033dde242b357e575ba1285f644057ab5c`; documentation: `e08f44b89f90d235657ef4ef92c520b5f1c58da8`. Post-suite test-only corrections: `f760232d` (structural relpath guidance assertion) and `e438a3f87ce5e284d31bea416f6a4d60a6a9b3fa` (renderer guard import; final tested code/test pin); no product code changed after the full campaign.
- Target: `feat/orc-dynamic-core-cutover`, `/var/tmp/agent-orchestration-orc-dynamic-core`. Integration branch: `integrate/dynamic-main-backports-20261015`.
- Evidence root: `/tmp/orc-dynamic-main-sync-20261015-yenoqng0`. Receipts preserve actual commands, code pins, hashes, outputs and limitations.

| Package | Commits | Result |
| --- | --- | --- |
| Nested result summaries | `724dc507` | Preserve resolved typed environments through direct, inline and private control summaries. |
| Invalidation preflight | `f01d1722` | Historical/headerless or unsupported-profile roots refuse before lock allocation; evaluated authority remains validated under lock and native no-write refusal remains. |
| Provider delivery | `0deca59f`, `48f5ff22` | Replay selects retained legacy/file1/file2 rendering; current transport metadata selects OMP delivery; authoritative result validation remains shared. |
| REPL inspection | `c4ea0128`, `66ef35cc` | Module declarations, immutable authored source and non-evaluating queries; typed result-file lookup and explicit native observed-kind/no-provenance limits. |
| Shared owners | `d2d7897c`, `4bfeb493`, `2865c978`, `39b3bb95` | Prepared provider IO, checked artifact contracts and runtime prompt helpers moved without duplicate implementations. |
| Current consumers/reference | `df65b703`, `e08f44b8` | Canonical serial best-of-n targets 2.35; frozen 2.28 comparisons remain; complete library examples and profile-specific guidance added. |

No whole-main merge, unrelated main WIP, native agents/parallel/child/recovery, stdout streaming, default/adoption change or historical experiment rewrite was included. The OMP/file2 correction came only from the plan's frozen 51-file packet with patch SHA `9e0838b57c8fd04c29f658564e98225f769529f42f02f7fd223bb0d63fa148e8`.

## Verification

Provider-facing checks used local deterministic shims or mocks; no paid/live providers were invoked. Python was the existing 3.13.9 base environment. Final broad campaigns and paired controls ran in private tmux sessions with `-q -n 16 --dist=worksteal` and ordinary bytecode caching. The initial affected baseline used `-B` and disabled pytest caching; its normal-cache repeat passed all 1050 selected tests. Both baseline receipts are retained, and neither waives later failures.

| Check | Result | Receipt |
| --- | --- | --- |
| Nested summaries | 72 passed | `task1/receipt.json` |
| Invalidation | 17 narrow and 151 affected passed; interruption/state controls passed | `task2/` |
| Versioned delivery | 179 narrow and 290 affected passed | `task3a/receipt.json` |
| OMP/file2 integration | 470 passed, 4 environment/live-provider skips | `task3b/receipt.json` |
| Typed inspection | 421 affected passed; restored four-provider public smoke passed | `task4a/receipt.json` |
| Native inspection | 98 passed | `task4b/receipt.json` |
| Prepared IO owners | 148 narrow, 175 affected passed | `task5a/receipt.json` |
| Checked artifact owners | 413 contract and 129 runtime passed | `task5b/receipt.json` |
| Runtime prompt helpers | 55 narrow, 158 affected passed | `task5c/receipt.json` |
| Best-of-n | 4 focused passed; 26 adjacent passed; both historical caller regressions passed | `task6a/receipt.md` |
| Documentation examples | 9 actual compile/dry-run/run commands and 6 public smokes passed | `task6b/final-receipt.json` |
| New module collection | 129 tests collected in 9 modules | `task7/collection.json` |
| Integrated affected, 139 modules | 4517 passed, 8 watcher deadline failures, 4 skipped; exit 1 | `task7/affected.json` |
| Full non-e2e at `e08f44b8` | 23885 passed, 280 failed, 7 skipped, 172 xfailed; exit 1, 1116.98s | `task7/full.json` |
| Post-suite test corrections | 31 shape tests and 34 renderer/owner tests passed; distinct review approved | `task7/wording-test.json`, `task5c/final-correction/receipt.json` |
| Paired 295-node failure/control campaign | Final: 269 failed, 26 passed; base: 270 failed, 25 passed; no final-only failed nodes | `task7/failure-review/` |
| Public smoke pytest selectors | 39 passed, exit 0, 58.38s at `e438a3f8` | `task7/public-pytest.json` |
| Public subprocess smoke | 16 CLI invocations, 64 assertions passed across 2.35/2.36/3.0 | `task7/runs/public-smoke-20261016T004451-ae28c795dc/receipt.json` |
| Rehearsed dirty-overlay smoke | Same three profiles, 16 processes, 64 assertions passed | `rehearsal-smoke.json` |

The full command is `python -m pytest -q -n 16 --dist=worksteal -m 'not e2e' --ignore=tests/e2e`. The clean pinned base already returned 290 failed, 23581 passed, 7 skipped and 172 xfailed. The baseline inventory in `evidence/base-failures/` records every node and trace; it is not a blanket waiver. The final full run had four newly failing nodes: one stale renderer monkeypatch (corrected and retested), two directory-admission checks, and one 15-second run-reference marker wait. The latter three passed in both paired runs; the run-reference case also passed in the affected campaign. Their relevant isolation/test/helper files are byte-identical between base and integration. A private ancestor-mutation experiment reproduced both admission refusals on both pins; it demonstrates the existing race-sensitive checks, not the exact changed field or ancestor during each full-run failure.

The 295-node union contains every affected/full failed selector plus the 31 compiler/watcher/spike controls. The paired campaign produced 269 common failures and none unique to final; the sole base-only failure was watcher discovery `[None]`. Of the common failures, 258 had identical diagnostics after only checkout/temp-root normalization. Eight further differences were inspected: two identical bwrap prerequisite refusals, four missing nanoBragg source errors and two historical checkout-path bindings with different truncated presentation. Three observed identity differences were investigated without normalizing hashes: a four-process matrix of base/final code against the same two source roots produced byte-identical DesignDelta and all three WCC structural projections for each source root. Changing the source root alone reproduced the observed checkpoint hash change. The source-path-sensitive specialization mechanism predates this backport. The controls cover the measured projections and observed suffixes, not a separate cross-root runtime execution or a repair of the ten golden failures.

The 269 paired common failures comprise 110 missing ES hook fixtures, 58 noncanonical interpreter paths, 68 explicit bwrap digest refusals, 8 installed Codex pins, 2 feasibility bwrap bindings, 2 hard-clause fixture failures, 4 missing nanoBragg sources, 5 historical checkout-bound evidence failures, 10 compiler golden failures and 2 observer/child-call assertions following a BoundaryProofError whose underlying diagnostic is not printed. Those last two are not claimed to have a proven bwrap cause. Watcher deadlines appeared in the broad campaigns but no watcher failed only on final in the paired controls. They remain failures, and prerequisite refusals do not validate behavior behind the refused prerequisite. Node-by-node traces, original and paired outcomes, and limits are retained in `task7/failure-review/`; raw projection evidence is in `task7/identity-attribution/`.

Owner extraction preserved moved function ASTs, compatibility object identities, the explicit typed target set `{2.35, 2.36}`, runtime prompt/input/evidence hashes and selected pre/post artifact probes. Those artifact probes used pure 2.35/2.36/3.0 programs; they do not claim that compiler package fingerprints remain unchanged for every source or run-reference program.

## Reviewed adaptations and evidence limits

- `sites` moved during 5a because prepared IO bind checks need its source-free traversal. Only three package exports became lazy to avoid the concrete eager frontend cycle. The later owner move retained source configuration projectors and all branch-specific native behavior.
- Existing target/schema consumers in `wcc/route.py`, `family_profiles.py` and `lowering/phase_scope.py` received import-only adaptations. An upstream-only `run_header.py` was not invented.
- Best-of-n's historical spike and flat/closed comparison harnesses also needed the frozen 2.28 source. Review reproduced both failures and verified the narrow fixes without changing their assertions.
- The Task6a adjacent selector ran serially and its tmux wrapper retained the 26-passed summary but not the exit code. It is not claimed as a captured parallel success; the integrated 16-worker campaign covers those modules with an explicit exit receipt.
- An external smoke initially assumed typed compile's human JSON carried `status`, and redundantly redeclared a local prompt return. The script now uses the existing machine JSON option and the prompt's declared return. The failed run receipt is retained; the final assertions were not weakened.
- The integrated suite found one stale test monkeypatch import after the helper extraction. It was reproduced, then changed to the actual runtime owner while retaining all assertions and the no-second-render guard; re-exporting its dependency from the old wrapper would have made that guard ineffective. Public function aliases retain object identity. The full suite was not repeated for this test-only correction; the complete module, owner controls and final failed-selector campaign provide the updated evidence.
- The relpath shape test now checks that exactly one non-metadata comment precedes its field, retaining constraint/enum checks without asserting human prompt wording. It passed before and after the adjustment.
- Independent code reviews approved each package and their interactions. A distinct Astra review approved the specifications/library guidance and the dirty documentation integration. No prompt wording assertions, blanket xfails, deleted tests or relaxed timeouts were used to hide failures.

## Preservation and integration

The original target was fast-forwarded to `0ce17f75be1b7d826f7c8a1f94e9abad30e2f5a5`; only this completion report and its plan checkboxes follow as documentation closeout. `original-integration.json` records the actual stash/merge/apply and exact manifest verification; `integration-closeout.json` records the final branch tip. This task never wrote main. Its original HEAD, index, 34 dirty tracked files' bytes/modes and untracked inventory remained unchanged; an external one-line edit to `AGENTS.md` appeared at 01:07 UTC and was preserved separately in `main-external-change.json` and `main-observed-external-change/`. Final checks compare against that observed state rather than claiming main received no concurrent edits. The target snapshot contains 21 dirty tracked documents, one untracked plan and an empty index.

The disposable rehearsal reproduced that state exactly before applying the integration. Its only textual conflict combined the user's two existing capability rows with the two new rows. Review then corrected one stale overlay paragraph saying REPL inspection was unavailable; the exact before/after is retained in `rehearsal-overlay-semantic-correction.json`. All other authored changes and the untracked plan remain intact, and the index remains empty. Both inputs, modes and reviewed output are retained in the snapshot/patch receipts. Rehearsal link checks and the three-profile smoke passed.

Backups: `integration-target-snapshot/`, the reviewed `rehearsal-expected-ready/` and final `rehearsal-expected-final/` manifests, and original named stash `dynamic-backports-original-preserved-20261015` (`dbe66d55a072d9c0d70e0f7a8cadbc77f30e9a70`). The rehearsal stash is `ea866214e35b85ef7d5652a0b1b2658c6ea5bbe5`. No stash is dropped and no original worktree is reset or cleaned.
