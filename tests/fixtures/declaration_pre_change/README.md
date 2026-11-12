Run roots written before the `declaration` input part stops carrying source positions (Phase 3b, T2).
**Never regenerate them**: they exist to prove that runs recorded under the old rule still resume.

Recorded on 2026-11-12 with the package at `c3bdd14d` (no code change since `4bc14b7d`, the base the
Phase 3b plan names), by `scaffolds/record_fixtures.py` and `scaffolds/assemble_fixtures.sh` on the
unmerged branch `proof/phase-3b` (commit `3662a26b`). Every provider was a local stand-in on a closed
`PATH`; no model was called. Each case ran in `/tmp/orc-declaration-pre-change/<case>` with
`--run-ref-root /tmp/orc-declaration-pre-change/run-ref`: the stored program's position records hold that
path and the old rule digests them, so the path is part of the evidence. Commands are spelled by path
(`./t.py`), so no run pins an interpreter of the recording host.

Each directory holds the workspace sources and `runs/<run id>/` (copy it to `.orchestrate/runs/`). Not kept:
call logs, build caches, locks, display-only `provider-observation/`, and the native stores of the completed
agent run, which a completed run never reads.

| Case | What it is | Relocates |
| --- | --- | --- |
| `provider_committed` | `s1` command, `p` provider (stand-in `codex_shim.py`), `s3` command; completed | yes |
| `agent_turns_committed` | the four-turn, two-agent run of `test_clean_run_commits_four_turns_on_two_native_sessions`; completed | yes |
| `agent_turn_pending` | the same, killed after turn `b1`'s native turn completed and its receipt said so, before `committed`; holds both native stores | **no**: the allocation's pinned configuration binds the launch cwd, so it resumes only in `/tmp/orc-declaration-pre-change/agent_turn_pending` |
| `phased_committed` | the `phased_239` workflow, killed after the phased provider's `committed` row, before `settled` | yes |
| `phased_pending` | the same, killed with the attempt's receipt `prepared` and no `committed` row | **no**: the receipt names a transport reservation under `/tmp` by device and inode; without it the base refuses `provider_phased_cleanup_failed` |

`tests/test_workflow_evaluated_edit_resume_baseline.py` pins what the base does with each.
