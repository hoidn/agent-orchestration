# Roadmap Phase 0: Records And Baseline Plan

**Status: Plan, executed 2026-11-11.** Implements Phase 0 of the
[current roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-0-records-and-baseline).
It changes documents and housekeeping only: no runtime, language or spec
behavior, and no provider spend.

**Goal:** make the roadmap's evidence durable, close superseded records, and
fix a test baseline that later phases are gated against.

**Headline exit test:** one page states the next work (the roadmap, linked
from the index), and a second run of the launch recipe reproduces the same
failing test ids.

## Global constraints

- No provider or model calls.
- Pathspec commits only; no assistant attribution in commit messages.
- Other sessions work in this checkout. Do not touch their worktrees,
  uncommitted changes or evidence roots. A file that already carries an
  uncommitted change from another session is committed from a blob built on
  `HEAD`, so that only this plan's change enters the commit.
- Nothing is deleted before it has been looked at; every deletion is listed
  in the ledger below.
- Disk is tight (about 40 GB free). Check `df` before the full suite.

## Tasks

### Task 1: Durable records

- Copy the audit working notes (core, roadmaps, research, authoring) to
  `docs/reports/2026-11-11-project-audit/` and the five roadmap reviews to
  `docs/reports/2026-11-11-roadmap-review/`, each directory with a short
  `README.md` stating its role: captured working notes, not a contract;
  scratch paths inside them are not durable.
- Write `docs/reports/2026-11-11-what-the-experiments-established.md`: one row
  per experiment that spent provider calls, with its question, spend, result,
  evidence link and limits, and a short list of what is and is not
  established. Include the adversarial DAQ study and the resume
  retrospective's source ledgers.
- Record the adversarial DAQ study (`experiments/adversarial_daq/`, untracked,
  idle since 2026-10-23): commit its source and result documents, honoring its
  own `.gitignore`; exclude environments, run state and bulky artifacts and
  list what was excluded.
- **Check:** every link in the new pages resolves; the roadmap's Basis
  paragraph links the three new records.

### Task 2: Dispositions

Add a dated closure or status note at the top of each record named in the
roadmap's Dispositions table, stating what the roadmap decided and pointing
to it. No other text in those records changes, except the delivery plan's
stale Phase 4 text, which gets a correction note beside it.

- Close: substrate maintenance track; LSP P-series; LSP L6; OMP-I2.
- Keep with a note: evaluated-execution delivery plan; evolution follow-on
  roadmap (axis lifecycle kept, workstream ledger closed, authoring baseline
  trial moved to the roadmap's Phase 1 authoring check).
- Park: checked evaluation of generated source.
- Drop or archive: confined provider children, provider-phase isolation,
  typed program gates C2, MLEvolve architecture, private-runtime C2–C6,
  write-once W4.
- Backlog: archive note in its README; the token-usage item points to
  roadmap Phase 2.
- Dynamic branch: tag `archive/dynamic-core-2026-11-11` on
  `feat/orc-dynamic-core-cutover`; no push, no change to its checkout.
- **Check:** run every test module that reads a file under `docs/`; no test
  outside the baseline list fails.

### Task 3: Housekeeping

- Delete the leftover temp directories in the repo root (`tmp*` made by
  `mkdtemp`, and `orc-observe-*`) that are untracked, older than 30 days and
  not the working directory or open file of any process. Never the tracked or
  ignored `tmp/` directory itself.
- List every worktree with: branch, merged into `main` or not, clean or not,
  last modification, size, and whether a process uses it. Remove only those
  that are merged, clean, idle for more than 30 days, unused by any process,
  and hold no ignored content other than caches. Leave all others and record
  why.
- **Check:** `git worktree list` and the root listing match the ledger.

### Task 4: Test baseline

- Launch recipe: a dedicated worktree pinned to one commit;
  `PYTHONPATH=<worktree> pytest -q -n 16 --dist=worksteal --basetemp=<short path>`,
  started directly from an existing session, not from a new tmux session.
- Run it twice. Record the failing test ids of each run.
- Classify each failing id by mechanism, reusing the mechanisms of the
  [simplification record](2026-10-15-orc-simplification-roadmap-extension.md),
  and name the roadmap item that owns it.
- Write `docs/reports/2026-11-11-test-baseline.md` with the recipe, the
  commit, the counts, the list, and any id that differs between the runs.
- **Check:** the two runs' failing ids are equal, or every difference is
  listed with its cause.

### Task 5: Close

- Add index rows for the new records; set the roadmap's Phase 0 state.
- Fill the ledger below.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-11 | Owner approved roadmap revision 2; Phase 0 started. No provider spend is planned or authorized in this phase. |
| 2026-11-11 | Task 1 done: audit notes, roadmap reviews, the experiments page and the adversarial DAQ record are committed and indexed (`aaa2ea51`, `95afde32`, `506e4d47`). |
| 2026-11-11 | Task 2 done: 16 records carry a dated disposition note (`80c69892`, `a2835f42`); index, status matrix and design README aligned (`e69c224b`, `d72304f1`); the two dynamic branches are tagged `archive/dynamic-core-2026-11-11` and `archive/dynamic-2026-11-11`, nothing pushed. |
| 2026-11-11 | Task 3 done: 390 leftover temp directories removed (about 16 KB of content; none held evidence); 29 `tmp_*`/`tmp-*` root directories removed on the owner's instruction; 18 merged, clean, idle worktrees removed and 9 stale entries pruned; about 7 GB freed. Incident: removing `.worktrees/omp-i1-prerequisites` broke the base environment's editable install for a few minutes; the worktree was re-created at the same commit. |
| 2026-11-11 | Task 4 done: see the [test baseline report](../reports/2026-11-11-test-baseline.md). The two runs share seven failing ids (three fixed since, four an artifact of the worktree recipe); four further ids appeared in one run only and are recorded as load-sensitive. |
| 2026-11-11 | Phase 0 closed. Exit test: the roadmap is the single page that states the next work, and the failing ids are reproduced or explained. |
