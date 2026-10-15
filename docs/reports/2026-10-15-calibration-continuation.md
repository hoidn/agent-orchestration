# Calibration Continuation: Rung 1's Third Sample

Status: complete. Rung 1 qualifies. Sample 3's hidden fraction was measured after the upstream anchor passed
164/164, and the results are archived with their output manifest.

This is a **post-data continuation that the owner approved**, not a fresh preregistered experiment. It was written
after every Task 8 rung and after E-B2 had been run and read. It does not rewrite either of them:
- the [Task 8 report](2026-10-14-task-difficulty-calibration.md) keeps its frozen outcome (no rung qualified under
  `3149bc36…`);
- E-B2's choice of rung 3 and its [results](2026-10-15-calibrated-orc-versus-single-call.md) stand.

## Question And Criterion

R55 qualifies a rung on review blockers alone. Under it, rung 1 (`cf1-generic-unions`, mean 1.0 over two patches)
was borderline and needed a third single call and review. The owner was asked, before any launch, whether to complete
the existing samples or calibrate afresh. The answer was "Completar las muestras existentes" (ruling R56,
2026-10-15T19:53:11Z).

- **Criterion:** [`calibration-continuation.json`](../../experiments/compare/criteria/calibration-continuation.json),
  frozen at `f0cc6974`, SHA-256 `c6cfb85a9b21268fcffb32209fa45974ca139743c3cc1cdb0444d04e7c37efc9`. The hash was
  recorded in `start.json` before the first launch. Everything else comes from the base
  [`calibration.json`](../../experiments/compare/criteria/calibration.json) (`amends_4`).
- **Rule:**
  - rung 1 qualifies if its mean over three patches is at least 1;
  - otherwise rung 2 qualifies on its recorded mean of 2.5;
  - nothing beyond rung 2 runs.
- **Runtime:** `2b9efd81`, the same commit as rung 1's original runs. The package hash is `23681b72…`, and the
  seeded base is `19f76c85…`.

## Result

| sample | run | single call's hidden acceptance | review | blockers |
| --- | --- | --- | --- | --- |
| 1 | Task 8 `direct_task/run-1` | 149/164 (0.91) | Task 8 `review_once/run-1`, REQUEST_CHANGES | 1 |
| 2 | Task 8 `direct_task/run-2` | 148/164 (0.90) | Task 8 `review_once/run-2`, REQUEST_CHANGES | 1 |
| 3 | continuation `direct_task/run-1` (`20261015T195817Z-rhqkgj`) | 154/164 (0.94) | continuation `review_once/run-1` (`20261015T203735Z-mmzi94`), REQUEST_CHANGES | 1 |

- **Mean review blockers: 1.0, so rung 1 qualifies.** The stop rule ends here. No rung-2, rung-3 or rung-4 call was
  made, and no treatment arm ran.
- **Anchors in the continuation pool:** upstream 164/164 (1.00) and stub 1/164 (0.01). The upstream anchor passes
  every node, so sample 3's hidden fraction is valid. It is description only, as the criterion requires.
- **Wall clock:** the single call took 2248 s and the review 192 s. Each was one shim call.

Sample 3's review finding, verbatim:
- Applying Box[Node] where Node has next Optional[Node] raises RecursionError during stage 1 compilation;
  generic_unions.validate_applied_payloads and its nested reference predicates traverse the record cycle without a
  visited set.

Rung 1's three findings, including the two in the Task 8 report, all name a concrete input that goes wrong. This one
and sample 1's are both unbounded recursion over a recursive generic type.

## What Was Checked

- The owner's choice and the frozen criterion hash were both recorded before the first launch.
- All 31 reused input hashes (Task 8 runs, reviews, summaries and criteria) were verified, and the old evidence was
  not modified.
- Runtime: commit `2b9efd81` with no changes, package hash, `codex-cli 0.162.1`, `bwrap`, and both `orchestrator`
  import paths.
- The single call's `inputs.json` is byte-identical to samples 1–2, and its `compare_base` matches.
- The review is paired with its patch: `applied.path` is the continuation run's `final.diff`, SHA-256 `6831d4f0…`.
  The review's intent, account and replies match Task 8's, and `candidate_changed` is false.
- Each generated command passed `--dry-run` with no run root and no provider call before it was launched.
- **Scans:**
  - `direct_task` had 27 hits, all cleared after inspection: 21 were tmux skill text or the agent's own private
    `/tmp` sockets; 5 were traceback paths from the stale editable install (see Limits); 1 was a baseline evidence
    path that pytest printed, and that path is present at the seeded base.
  - `review_once` had 0 hits.
  - No hit names the solution, another run, the pool, another session's transcript or the network.
- No judge ran. The pool holds judge configurations only because `prepare.py pool` requires them. `verify-pool`
  confirms that all 3 clones match their recorded patches.

## Cost

- **Provider invocations:** one `gpt-6.1-sol` single call and one `gpt-6-sol` review.
- **Codex:** the weekly window read 59% before the single call and 64% before the review and after it. The credit
  balance stayed at 28549.41. These readings cover the whole account while other sessions were running, so the change
  is not this continuation's own cost.
- **Authoring and review:** Opus subagents designed, reviewed and wrote up the continuation. That usage is outside
  the experiment-call accounting above.

## Limits

- **Post-data and small.** The rule was written knowing that rung 1 needed one review with at least one blocker, and
  that rung 2 would otherwise qualify. Every rung-1 review so far has blocked. `k = 3`, and the reviewer's variance
  is unmeasured.
- **Time and model drift.** Samples 1–2 ran on 2026-10-14 and sample 3 on 2026-10-15. The runtime and CLI were the
  same, but the provider's model may have changed.
- **"Single call" means one CLI invocation.** Each arm made one shim provider invocation. Inside it, Codex delegated
  internally: 4 Codex sessions ran under the single call's tree and 3 under the review's. So a single call is not
  necessarily one model agent.
- **Stale editable install.**
  - Without `PYTHONPATH`, `orchestrator` resolves to `.worktrees/omp-i1-prerequisites`. That is the same import path
    as in Task 8, but its HEAD during Task 8 was never recorded. Its current HEAD, `fc6a9b1b`, is recorded.
  - The single call hit it once: `python /tmp/probe_improve.py` imported it, and it rejected DSL 2.33. The agent then
    reran with `PYTHONPATH=.`.
  - The solution `1798fc70` is not an ancestor of `fc6a9b1b`.
- **Contamination is detected, not prevented**, for home, transcripts and the network.

## Reproduce

- **Commands:** the [continuation plan](../plans/2026-10-15-calibration-continuation-plan.md). Mechanics come from
  the frozen criterion.
- **Evidence:** `agent-orchestration-compare-evidence/calibration/continuation/`, beside the repository. It holds:
  - the owner's choice, `start.json` and the reviews of the design;
  - `frozen-inputs.sha256`;
  - the archived runs with their state and transcript indices, and the scan adjudication;
  - environment and runtime metadata, and `codex-usage.txt`;
  - the pool records and `hidden-<clone>.json`, in `pool/`;
  - `rung-1-continuation.json`, the result;
  - `continuation-outputs.sha256`, covering 67 files.
