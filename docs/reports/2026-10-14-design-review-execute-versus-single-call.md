# E-B: Design-Review-Execute Against One Call On A Feature One Call Does Not Finish

Status: not evaluated: the task did not qualify. The criterion was committed before any E-B run, including the
qualification runs. No treatment run and no batch control run was made.

## Question And Criterion

The question is whether `workflows/examples/design_review_execute.orc` delivers more of the hidden
acceptance tests than one `gpt-6.1-sol` call with the same task text and time limit. The task is
the Workflow Lisp REPL: base `47e85a9c`, with 16 hidden node ids from `fe49c1c4`. In the treatment,
`claude-fable-5-1` plans and revises, and `gpt-6.1-sol` reviews and executes.

- Criterion: [`experiments/compare/criteria/eb.json`](../../experiments/compare/criteria/eb.json).
- SHA-256: `d5b8737829fba1bc33bcfa3d81b63d239dc01fe3bc172c5c5604f3c3d76e009c` (amendment 1; the first version, `de57fba1…`, is cited in its `amends` field).
- Each version was committed before the runs it governs. E-B made no scoring run, so no run bound it.
- Runs, pooling and summarizing use the frozen runtime at `1a77e0af`.
- Two qualification runs made at `aac25b7d` were discarded for a harness defect (R35).
- Package SHA-256: `585e057e3828b7eb7a9208ccb5188925949357737c03e156013096ceabcb5f61`.

## Qualification

The criterion requires that two single calls, made with the control's binding (`gpt-6.1-sol`, effort high,
`:timeout-sec 14400`), each pass at most 7 of the 16 hidden node ids. Both runs exceeded that.

| run | outcome | wall clock | calls | patch | hidden acceptance | scan hits | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qualification run-1 | completed | 2394 s | 1 | 17 files, 1854 added lines | 16/16 | 27 | cleared |
| qualification run-2 | completed | 1656 s | 1 | 22 files, 1716 added lines | 14/16 | 55 | cleared |
| anchor `upstream-repl` | | | | 1786 added lines | 16/16 | | |
| anchor `stub-repl` | | | | | 0/16 | | |

- Run-2 fails `test_completed_root_loop_captures_done_result_not_seed_halt[False]` (`memo_inconsistent`:
  replay failed before a lexical scope was available) and its `[True]` variant (the `state` binding is
  missing). The node-by-node rerun is recorded in the evidence directory (`eb/qualification/run-2-failing-nodes.txt`).
- Every scan hit was the `claude-tmux-sockets` pattern. In each case the agent read the tmux skill and used
  sockets under `/tmp/claude-tmux-sockets`. Inside the sandbox that path is the run's own private `/tmp`:
  the agent's first `ls` there found no such directory.
- Neither agent named the main checkout, a sibling worktree, the frozen runtime, another run or another
  session's transcript.
- Hidden acceptance was measured on the qualification pool, built without running any judge, with the
  interpreter the criterion names. Evidence: `records/qualification.json` in the pool, copied to the
  evidence directory with the run records.

## Runs

Two earlier qualification runs, at `aac25b7d`, were discarded before any measurement was used. Both
completed. Their pytest runs executed inside a tmux server on the shared socket
`/tmp/claude-tmux-sockets/repl.sock`, which another session's REPL provider run had started on
2026-10-13. That server's global environment carried `PYTHONPATH` at the main checkout, which holds the
solution. Run-2 also saw run-1's processes. The harness was then fixed (R35: every agent CLI runs under
bubblewrap with a private `/tmp`, `/dev/shm` and process list), and the criterion was amended before the
reruns. No treatment run was made.

## Hidden Acceptance, Scores And Anchors

Nothing was scored by judges. The anchors' hidden fractions are in the qualification table above.

## Contamination Scan

See Qualification. Both verdicts are `cleared`, with reasons recorded in each run's `record.json`.

## Cost

- Four `gpt-6.1-sol` single calls of 28 to 40 minutes each: two discarded and two qualification runs.
- No Anthropic calls.
- No scoring.

## Verdict

**Not evaluated.** With its public-interface appendix, the task text lets one `gpt-6.1-sol` call deliver
the REPL's first release, so the task does not belong to the class E-B targets. The frozen fallback was a
census candidate; it was not run (R39). The census candidates are changes of about 100 to 250 lines, much
smaller than this feature, which one call finished. The next E-B uses a task chosen by the
difficulty-calibration rule the owner set on 2026-10-14 (the design's "Difficulty calibration for
follow-on experiments"): the single call passes below half of the hidden acceptance, and the expected
number of review blockers on single-call patches is at least one. Both are measured before any
treatment run.

Amended 2026-10-15 (ruling R55, `amends_4` of the calibration criterion): the owner removed the
hidden-acceptance condition; the paragraph above records the rule as of 2026-10-14. The current rule
is in the [design](../design/orc_effectiveness_comparison_harness.md) ("Difficulty calibration for
follow-on experiments").

## Limits

- **Two runs.** The two qualification runs are a small sample of the single call. Both landed far above
  the bar: 14 and 16 of 16, against at most 7.
- **The appendix.** The hidden tests needed the public interface named, and the appendix names forms,
  output lines, codes and exit statuses. This makes the task better specified than the feature brief the
  original workflow received.
- **Public solution.** The solution is public and present on this machine. The scan covers what the
  agent typed and printed, plus its sessions. It does not prevent reads of home or the network (R35).

## Reproduce

```bash
RT=/home/ollie/compare-runtime    # git worktree add --detach $RT 1a77e0af
PY=/home/ollie/miniconda3/bin/python
H=$RT/experiments/compare
W=/home/ollie/compare-work-eb2
cd /home/ollie
for k in 1 2; do
  PYTHONPATH=$RT $PY $H/prepare.py run --task $H/tasks/eb-repl --arm direct_task --root $W --runtime $RT \
    --set model=gpt-6.1-sol --set effort=high
done
# run each records/direct_task/run-<k>/command.sh, then collect, scan (--hash fe49c1c4) and adjudicate
PYTHONPATH=$RT $PY $H/prepare.py pool --task $H/tasks/eb-repl --criterion <criteria/eb.json> \
  --out $W/qual-pool --judge claude-opus-5-5 --judge gpt-6-sol=$H/providers/score_codex.json \
  $W/records/direct_task/run-1 $W/records/direct_task/run-2
# hidden acceptance: summarize.hidden_fraction(clone, $H/tasks/eb-repl, $PY) for each clone
```
