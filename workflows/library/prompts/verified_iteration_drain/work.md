You are executing one iteration of an autonomous drain toward the consumed
target design.

Read the consumed work order, the target design, the ledger, any notes in the
blocked-notes directory, and the previous review findings or failing check
log when the work order names them.

Pick the most valuable piece of unfinished work toward the target design —
including undoing or replacing an earlier approach when the ledger shows it
is not converging. If the previous check log shows failing checks, restoring
them to green is the mandatory first task. The target design's non-goals and
the check commands are the scope boundary; there is no file-list fence.

Make verified progress: run the check commands from the work order yourself
and commit only work that passes. Stage files by explicit path; never use
`git add -A`, `git add .`, or `git commit -a`. Keep commit messages plain.

If something genuinely requires the user — credentials, environment, or an
intention only they can resolve — write a short `BLOCKED-<topic>.md` note in
the blocked-notes directory and continue with other actionable work.

Before finishing, write:
- the verdict file named by `worker_verdict_path`: `CONTINUE` (more work
  remains), `DONE` (the target design's acceptance criteria hold in the
  current checkout), or `BLOCKED_ON_USER` (nothing actionable remains
  without user input);
- one line to the file named by `worker_note_path` describing what you did
  or learned this iteration.
