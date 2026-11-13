Run roots written before the `declaration` input part stops carrying source positions (Phase 3b, T2).
**Recorded once; never regenerated at test time**: they exist to prove that runs recorded under the old rule,
by the real runtime that preceded the change, still resume.

Recorded on 2026-11-13 at target **2.40** with the package at `c3bdd14d` (the build before T2; no code change
since `4bc14b7d`, the base the Phase 3b plan names), by `scaffolds/record_fixtures.py`,
`scaffolds/assemble_fixtures.sh` and `scaffolds/clean_phased_reservations.py` of the unmerged branch
`proof/phase-3b` (commit `3662a26b`). The one change to the scaffold: its three sources declare
`(:target-dsl "2.40")` (the provider source, the agent source, the phased `main.orc`; Lane D stage 4, ruling
R4 and Task 3d of `docs/plans/2026-11-12-lane-d-stage-4-one-target-plan.md`). The command, in an export of
`c3bdd14d` (`orchestrator/`, `tests/*.py`, `tests/fixtures/{phased_239,providers,provider_delivery_pre_change}`):

    PATH=experiments/thread_m/no_provider:$PATH PYTHONPATH=<export> \
      python scaffolds/record_fixtures.py OUT          # holding flock /tmp/orc-declaration-pre-change.lock
    python scaffolds/clean_phased_reservations.py /tmp/orc-declaration-pre-change/phased_{committed,pending}
    sh scaffolds/assemble_fixtures.sh OUT tests/fixtures/declaration_pre_change

then the two revoked `/tmp/orc-peer-*` namespaces the phased cases created were removed. The first recording
(2026-11-12, targets 2.38 and 2.39, same build and scaffold) is kept in history:
`git show ae36901d:tests/fixtures/declaration_pre_change`.

Every provider was a local stand-in on a closed `PATH`; no model was called. Each case ran in
`/tmp/orc-declaration-pre-change/<case>` with `--run-ref-root /tmp/orc-declaration-pre-change/run-ref`: the
stored program's position records hold that path and the old rule digests them, so the path is part of the
evidence. Commands are spelled by path (`./t.py`), so no run pins an interpreter of the recording host.

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

The run wrote its files `0600`; git keeps no such mode, so a test restores it after copying (the
phased receipt check requires it).

`tests/test_workflow_evaluated_edit_resume_baseline.py` pins what the base does with each.
