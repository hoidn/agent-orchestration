# Shareable upstream hunks ported into the dynamic branch — 2026-10-17

Status: executed from the [reviewed plan](../plans/2026-10-17-dynamic-shared-upstream-port-plan.md);
integration into `feat/orc-dynamic-core-cutover` is recorded in the last section. This
report selects no native adoption, default-profile change, target change, main merge or push.

## Pins and selection

- Dynamic base: `74fae634`. Upstream inspection pin: main `90ae778c`; merge-base `93a33ae2`.
- Integration branch: `integrate/dynamic-shared-port-20261017`. Product commits
  `0f7f4a65`, `6da91155`, `9bac22fe`, `51ec4905`; documentation and test closeout
  `77707c8a` (spec precision from the integrated review) and the architecture-test
  companion hunk; the integrated tip is recorded in the integration section.
- Evidence root: `/var/tmp/orc-dynamic-evidence/shared-port-20261017/` (hunk inventories,
  patches, baseline, control and per-task receipts/reviews). Branch backup bundle and the
  target's overlay patch are under `/var/tmp/orc-dynamic-evidence/`.
- Selection was made per hunk from three read-only inventories over 45 shared modules
  (providers/contracts, evaluated seam/CLI/readers, closed-program contracts). The
  closed-program group yielded no shareable hunk; typed-only features (2.37–2.39), all
  retirement deletions and behavior-free refactors were excluded with reasons in the plan.

| Package | Upstream hunks | Commit | Result |
| --- | --- | --- | --- |
| Owned-group provider teardown | `3693acbd` executor/control + tests + one `specs/providers.md` hunk | `0f7f4a65` | Bounded group quiescence, SIGKILL fallback, bounded I/O joins; a zero exit with a surviving owned group is a failure (D-C). Diff identical to main line for line; no `3e07b8cd` content. |
| Streaming rule (D-B) | `ce8a41d7` runtime/evaluated/resume hunks; `perform_provider` adapted; native CLI/runtime threading; `specs/cli.md` wording | `6da91155`, `51ec4905` | Provider output streams by default on typed 2.35/2.36 and native 3.0; `--quiet` silences; `--stream-output` accepted and inert. Real-process evidence on both routes, stdout and stderr. |
| Reply-excerpt blanking | `acfc3708` + the `providers.py` hunk of `aba32230`; main's public test | `9bac22fe` | Missing-result failures name the blanked head of the reply; the branch assertion that only reflected the missing excerpt now matches main. |
| `_parse_output_value` delegation | `3693acbd` hunk in `output_contract.py` | `9bac22fe` | Deduplication only; body identical to main; behavior-neutral on the branch. |

Decisions recorded unattended (plan D-A to D-D) stand as executed; the owner may reverse any at review.

## Verification

Environment: `/home/ollie/miniconda3/bin/python` 3.13.9, `PYTHONPATH` set to the worktree,
`-p no:cacheprovider`; broad runs in tmux with `-q -n 16 --dist=worksteal`. No live or paid
providers; local shims only.

| Check | Result | Receipt |
| --- | --- | --- |
| Baseline, 54 modules at `74fae634`, idle machine | 2205 passed, 0 failed, 129.9 s | `baseline/` |
| Main control, teardown test modules at `90ae778c` | 194 passed | `main-control/` |
| Task 1 narrow / paired executor consumers (10 modules) | 194 passed; 618/618 on HEAD and control | `task1/` |
| Task 2 red→green / five-module selector / real processes | 3 failed→5 passed; 331 vs 326 on base; typed 2.35 and native 3.0 CLI runs | `task2/` |
| Task 2 revision (stderr marker) | red 2 failed → 179 passed over four native modules | `task2/receipt.md` Revision |
| Task 3 red→green / six-module selector | 4 failed→6 passed; 199 passed | `task3/` |
| Affected campaign, 65 modules at `51ec4905`, under external load | 6 failed, 2960 passed; all six are 20 s deadline/transport waits; paired serial reruns pass 2/2 on HEAD and 1/2–2/2 on the unmodified control | `task4/attribution.md` |
| Public smoke, real processes | 9 passed; consumers `-k 'best_of_n or public or smoke'` 14 passed | `task4/smoke.log` |
| Full non-e2e control at `74fae634` | 448 failed, 23703 passed, 14 errors, 7 skipped, 172 xfailed, 1875 s under external load | `task5/full-control.log` |
| Full non-e2e at `77707c8a` (product code identical to `51ec4905`) | 420 failed, 23766 passed, 14 errors, 7 skipped, 172 xfailed, 944 s; paired by node: 430 common, 29 control-only (load-sensitive), 1 HEAD-only | `task5/attribution.md`, `task5/pairing.txt` |
| HEAD-only node, deterministic | `test_common_helper_architecture.py::test_status_helpers_have_one_common_owner`: main updated this test in `3693acbd` when `_execute_session_invocation` became a delegating wrapper; the companion hunk was missing from the inventory and is ported in `32d0e6b2`; module 7 passed | `task5/helper-architecture-test.log` |
| Per-task distinct reviews and integrated review | Tasks 1–3 PASS (minor only); integrated review PASS (three minor, two inherited from main) | `task*/review.md`, `task5/integrated-review.md` |

A first full run on `51ec4905` aborted near 90 % when the disk filled with pytest base
temporaries (31 GB); it was discarded, the temporaries deleted and the run repeated on the
final product tip (`task5/disk-incident.md`).

The six affected-campaign failures and the full-suite failure counts reflect machine load
from concurrent sessions; the paired control runs are the attribution evidence, not the
2026-10-15 inventory. The baseline's 0-failure idle result is not reproducible under that load.

## Findings for the owner

- **Upstream contradiction:** main's `specs/cli.md` says `--quiet` applies to `run` and
  `resume`, but main's resume parser has no `--quiet`. The branch states the accurate rule;
  the fix belongs upstream (`task2/upstream-contradiction-resume-quiet.md`).
- **Minor follow-ups, not applied:** `_reply_excerpt` reads the whole `stdout.txt` before
  truncating (same on main; bound it once `WorkspaceFiles.read(max_bytes)` is ported);
  run-ref child runs keep `stream_output=False` on both main and the branch, which the spec
  sentence "run and resume stream" does not say; `tests/test_workflow_dynamic_readers.py`
  watcher tests flake under load on the base commit as well.
- **Deferred shareable work** is listed in the plan's Excluded section; nothing was
  silently dropped.

## Integration

Rehearsal on a disposable worktree at `74fae634` with the target's byte-verified overlay
(21 dirty docs, one untracked plan): `git stash push --include-untracked`
(OID `d9a48898`), `git merge --ff-only` to `51ec4905`, `git stash apply --index`: no
conflicts; the overlay's `specs/providers.md` and `workflow_lisp_dynamic_core_proposal.md`
hunks do not overlap the ported ones. The rehearsal was rebuilt on the final tip
(`34f5cbcf`, stash `cedb9192`) with the same result and a 12-test public smoke.

Target integration, performed as rehearsed on 2026-10-17: the target at `74fae634` with its
21 dirty docs and one untracked plan was stashed as
`dynamic-shared-port-original-preserved-20261017` (OID `5f029dad`), fast-forwarded to
`34f5cbcf`, and the stash re-applied with `--index`. Verified: HEAD equals the integration
tip; status, every dirty file's bytes and the overlay patch equal the rehearsal; original
main's HEAD, index and worktree are unchanged. The stash and backups are kept; nothing was
reset, cleaned or pushed. This paragraph lands through one further docs-only fast-forward,
which needs no stash because the report is not among the target's dirty files.
