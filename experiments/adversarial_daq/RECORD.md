# Adversarial DAQ Study: Record

**Status: Historical record (finished 2026-10-23), not a contract.** This page
records what the adversarial DAQ study compared, what it found, and what of its
directory is committed. The study's own
[launch record](docs/plans/2026-10-23-adversarial-daq-launch.md) owns the run
facts and figures below; [`README.md`](README.md) and
[`docs/protocol.md`](docs/protocol.md) own the package and its protocol. The
package pins its own runtime (`bb9cb30d`, target 2.39) and is not a source of
current ORC examples. A separate file is used so the 67 supplied files, whose
hashes the run verified, stay unchanged.

## What it compared and found

- **Question:** a builder and a skeptic, both `gpt-6.1-sol` high, searched for
  a scoped advantage of an ORC workflow over a strong existing-tool baseline
  for synthetic LCLS-II DAQ debugging, for at most four rounds and sixteen
  controller provider calls. Calibration was waived by the owner, not passed.
- **Spend:** all 16 provider sites committed; 18 started attempts, one failing
  before inference (CLI argument) and one paid capacity failure.
- **Result:** `INCONCLUSIVE` (budget exhausted without evidence-backed
  agreement), per [`final-verification.json`](artifacts/launch/final-verification.json).
  Claims C1–C4 were each refuted by an executable baseline at parity: actual
  LangGraph in rounds 1, 2 and 4, strict Python/Pydantic in round 3. Inner arms
  used no model calls. Recorded case wall time was higher for ORC every round
  (round 1: 137.4 s ORC against 39.6 s LangGraph), which includes compilation
  and process startup.
- **Limits:** synthetic simulator, no DAQ expert, agent-authored oracle;
  round 2's scorer checked pre-advance state; round 4's official evidence
  failed its integrity check because a reviewer's read-only SQLite open
  changed 15 `.sqlite-shm` files (the builder reproduced its 54 cases from
  frozen sources with the same zero saving).

## Committed result documents

Besides the files the directory's `.gitignore` lets through, these small
result documents under the ignored `artifacts/` tree are committed:

- `artifacts/launch/final-report.json`, `final-verification.json`,
  `capacity-failure-report.json`;
- the four official evidence reports, `artifacts/evidence/<id>/report.json`
  for rounds 1–4 (`ba4a285b…`, `c5f2edc9…`, `f2be2f42…`, `dda36d79…`);
- each round's skeptic `review.md` and builder `report.md` (eight files) named
  in the launch record.

## Not committed

Present on disk on 2026-11-11, left in place, not committed:

- `.venv/` (119 MB): the package environment.
- `.orchestrate/` (13 MB): runtime run state.
- `research/agent-orchestration-main/` (142 MB): an extracted copy of the
  pinned runtime source; `research/upstream-commit.json` records its commit.
- `artifacts/` (836 MB, about 37,000 files) apart from the result documents
  above: per-round working trees, trial copies, SQLite checkpoints, smoke runs,
  provider temp state, the 17 non-official evidence reports, and
  `artifacts/launch/live-resume.log` (11 MB live stream).
- `__pycache__/` and `.pytest_cache/` directories.

No credentials were found in the committed files; the provider credential
directory named in `artifacts/launch/deployment.json` was outside this tree.
