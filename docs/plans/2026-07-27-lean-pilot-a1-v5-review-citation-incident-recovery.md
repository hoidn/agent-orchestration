# Lean-Pilot a1-v5 Review-Citation Incident Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by
> task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the non-summarizable a1-v5 incident, make the existing
strict citation contract usable for empty and non-text payloads, and complete
the same exploratory controlled-task pilot under one fresh lock and
denominator.

**Architecture:** Keep citation ingestion unchanged and fail-closed. Derive
provider-visible locator eligibility from the same digest-verified package
bytes that ingestion validates, then expose one metadata row per citable
payload. Preserve a1-v5 byte-for-byte and bind it from an auxiliary operations
incident artifact in a fresh successor root; no a1-v5 attempt, package, review,
session, label map, or outcome enters the successor evidence.

**Tech Stack:** Python 3.11, canonical JSON, pytest, Git, tmux, Codex provider
CLI.

---

## Governing authority and execution assumption

This slice is subordinate to:

- `docs/superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md`;
- `docs/superpowers/plans/2026-07-26-orc-effectiveness-lean-pilot.md`;
- `docs/plans/2026-07-27-orc-effectiveness-lean-pilot-task7-readiness-amendment.md`.

The readiness amendment's “Bounded controller and stop semantics” requires a
separately locked pilot after a post-`VALID` apparatus defect. The owner's
standing direction to finish the active plan continuously is applied here as
authorization for that fresh exact-method successor. It does not authorize
same-lock repair, reviewer relaunch, evidence reuse, unblinding, a fifth
experiment record kind, a new treatment, or prospective work.

The a1-v5 root remains immutable. Its observed state is:

- one valid smoke and exactly three valid live blocks;
- three terminal reviewer transports and two accepted `review_result.v1`
  records;
- the third transport rejected during ingestion with
  `review_citation_location_invalid` because `:1-2` addressed a verified
  zero-byte payload;
- no `review-bindings.json`, `unblinding-bindings.json`, pilot summary, or
  report.

The validator behavior is correct. The apparatus defect is that the structured
reviewer prompt advertised line locators without publishing each verified
payload's line count or whether line locators were eligible.

## Prelaunch source-lineage correction

The first provider-free successor preparation at `a1-v6` exposed two further
defects before either launch review completed:

1. its proposed runtime commit `2f6be134` descended from the accepted
   `a2099be6` runtime through sixteen unrelated Q3/L5 paths in addition to the
   four reviewed citation-repair paths; reachable changes included prompt
   composition used by the treatments; and
2. the treatment child environment did not contain a controlled
   `PYTHONPATH`, so the installed editable-package finder resolved
   `orchestrator` from the live shared checkout rather than the detached
   runtime clone.

The prepared `a1-v6` root is therefore frozen as
`SUPERSEDED_PRELAUNCH_SOURCE_AND_IMPORT_LINEAGE_MISMATCH`. It consumed no
attempt: `evidence/` and `controller-tmp/` are empty; `work/`, `evaluation/`,
and `packages/` are absent; and no controller, Codex, or provider process was
started. Its lock, preflight, capture self-test, clean-test logs, and operations
files remain byte-for-byte provenance only. It is outside the smoke/live
denominator, supplies no evidence or session to a successor, and must not be
launched or rewritten.

The corrected successor is `a1-v7`, with a new pilot ID, seed, smoke ID, five
live IDs, lock, and all fresh roots. Its source revision has sole parent
`a2099be6` and contains only:

- the reviewed citation-repair plan, production module, and two tests;
- the generic treatment-runtime import strengthening and its tests;
- the governing design/plan wording required by that strengthening.

The new lock contains an explicit `apparatus.treatment_runtime` object with
exactly `import_root`, `revision_identity`, and `tree_identity`: the canonical
preparation repository root, `commit:<full runtime commit>`, and
`git-tree:<exact tree>`. Preparation and every block preflight require that
root to be the same canonical local repository as `archive.repository_root`,
detached, clean including ignored files, free of object alternates and
linked-worktree/common-dir indirection, and at the exact bound commit/tree.
Each digest-bound treatment launcher supplies `PYTHONPATH` as the single
`{treatment_runtime_root}` placeholder and
`PYTHONDONTWRITEBYTECODE=1`; the controller substitutes the placeholder only
from the verified binding. Top-level and nested Workflow Lisp Python
invocations use bytecode-disabled safe-path mode. No CWD, package location,
editable install, ambient path, provider-isolation feature, or changed
`run_block` signature participates.

## File structure

- Modify `orchestrator/experiments/_pilot_review_support.py`: derive immutable
  citation-surface metadata from verified package payloads and include it in
  the live reviewer inspection contract.
- Modify `tests/experiments/test_lean_pilot_review.py`: cover provider-visible
  metadata for empty, multiline UTF-8, and non-UTF-8 payloads.
- Modify `tests/experiments/test_lean_pilot_evaluation.py`: make exact-path
  acceptance and line-locator rejection for empty payloads explicit.
- Create only in the fresh external successor root:
  `operations/predecessor-incident.a1-v5.json`, plus the same established
  source-map, provenance, preflight, launch, capture, and evidence surfaces
  already used by a1-v5.

No public API, schema, record kind, retry mechanism, prompt framework, or
production module above 500 physical lines is added.

### Task 1: Reproduce the missing reviewer guidance and preserve strict ingestion

- [ ] **Step 1: Add the failing structured-guidance test**

Extend the live-review test package with:

- a zero-byte text payload;
- a two-line UTF-8 payload ending in a newline; and
- a non-UTF-8 payload.

Assert that each verified citable path has exactly one provider-visible
metadata row containing:

```json
{
  "path": "relative/package/path",
  "utf8": true,
  "line_count": 0,
  "locator_eligibility": "EXACT_PATH_ONLY"
}
```

For a nonempty UTF-8 payload, require
`locator_eligibility="EXACT_PATH_OR_LINE_LOCATION"` and the exact
`splitlines()` count. For non-UTF-8 bytes require `utf8=false`,
`line_count=null`, and `EXACT_PATH_ONLY`. Require path order to match the
sorted citable-file order.

- [ ] **Step 2: Run RED**

Run:

```bash
pytest -q \
  tests/experiments/test_lean_pilot_review.py::test_live_reviewer_runs_two_exact_bounded_slots_and_publishes_results
```

Expected: fail because `citation_contract` has no per-payload locator metadata.

- [ ] **Step 3: Add explicit ingestion controls**

Add focused tests proving:

- exact `empty.txt` remains admissible;
- `empty.txt:1`, `empty.txt:1-1`, and `empty.txt:1-2` each fail with
  `review_citation_location_invalid`;
- a locator on non-UTF-8 bytes remains rejected.

These are contract-preservation tests. If an assertion already follows from a
broader parameterized test, keep one explicit empty-payload regression test
rather than duplicating the whole ingestion fixture.

- [ ] **Step 4: Verify the controls before implementation**

Run the new ingestion selectors. Exact-path behavior must pass under the
current validator and every invalid locator must fail closed.

### Task 2: Publish verified locator metadata

- [ ] **Step 1: Implement the minimal derivation**

While `_package_contract` verifies each manifest row, derive the row from the
already loaded `payload` bytes:

```python
try:
    line_count: int | None = len(payload.decode("utf-8").splitlines())
except UnicodeDecodeError:
    line_count = None
```

Publish a sorted tuple of rows with:

- `path`;
- `utf8`;
- `line_count`;
- `locator_eligibility`.

`EXACT_PATH_OR_LINE_LOCATION` is permitted only when `line_count > 0`.
Everything else is `EXACT_PATH_ONLY`.

- [ ] **Step 2: Add the rows and rule to the structured inspection contract**

Retain `citable_files`, `navigation_only_files`, `allowed_forms`,
`line_numbering`, and `exact_path_precedence`. Add:

- the one-to-one metadata rows; and
- a structured rule stating that `PATH` is always valid for a citable payload,
  while `PATH:LINE` and `PATH:START-END` require
  `EXACT_PATH_OR_LINE_LOCATION` and bounds within `line_count`.

Do not normalize provider output or change `_validate_citation`.

- [ ] **Step 3: Run GREEN and adjacent selectors**

Run:

```bash
pytest -q \
  tests/experiments/test_lean_pilot_review.py \
  tests/experiments/test_lean_pilot_evaluation.py \
  tests/experiments/test_lean_pilot_controller.py \
  tests/experiments/test_lean_pilot_controller_state.py
```

Then run:

```bash
pytest --collect-only -q tests/experiments
pytest -q tests/experiments
```

- [ ] **Step 4: Verify structural limits**

Recursively count `orchestrator/experiments/**/*.py`; every module must remain
at or below 500 physical lines. Run the exact facade/module-layout selectors
from the governing plan.

- [ ] **Step 5: Commit only the incident fix**

Preserve every unrelated staged, modified, and untracked path. Stage and commit
exactly:

```bash
git add \
  docs/plans/2026-07-27-lean-pilot-a1-v5-review-citation-incident-recovery.md \
  orchestrator/experiments/_pilot_review_support.py \
  tests/experiments/test_lean_pilot_evaluation.py \
  tests/experiments/test_lean_pilot_review.py
git commit --only \
  docs/plans/2026-07-27-lean-pilot-a1-v5-review-citation-incident-recovery.md \
  orchestrator/experiments/_pilot_review_support.py \
  tests/experiments/test_lean_pilot_evaluation.py \
  tests/experiments/test_lean_pilot_review.py \
  -m "Harden empty-payload review citation guidance"
```

### Task 3: Obtain ordered independent reviews

- [ ] **Step 1: Specification review**

One fresh reviewer checks:

- one metadata row per digest-verified citable payload;
- exact parity with ingestion's UTF-8 `splitlines()` semantics;
- empty and non-text payloads remain exact-path-only;
- no validator weakening, normalization, or retry;
- no public API, schema, record kind, or family-specific behavior.

- [ ] **Step 2: Quality review**

After specification approval, a second fresh reviewer checks:

- derivation occurs once at the verified package boundary;
- no payload reread or duplicate validation;
- stable canonical ordering;
- production-module line limits;
- focused and full experiment-suite evidence.

Repair any concrete issue with the same implementer, then repeat the applicable
review. Commit every repair with `git commit --only` over the same four scoped
paths from Task 2 Step 5, rerun the affected tests, and re-review the resulting
commit. Before Task 4, record one final reviewed commit and tree, and require:

```bash
test -z "$(git diff -- \
  docs/plans/2026-07-27-lean-pilot-a1-v5-review-citation-incident-recovery.md \
  orchestrator/experiments/_pilot_review_support.py \
  tests/experiments/test_lean_pilot_evaluation.py \
  tests/experiments/test_lean_pilot_review.py)"
git diff --cached --quiet -- \
  docs/plans/2026-07-27-lean-pilot-a1-v5-review-citation-incident-recovery.md \
  orchestrator/experiments/_pilot_review_support.py \
  tests/experiments/test_lean_pilot_evaluation.py \
  tests/experiments/test_lean_pilot_review.py
fix_commit="$(git rev-parse HEAD)"
fix_tree="$(git rev-parse HEAD^{tree})"
```

The detached runtime and every subsequent provenance record bind this final
reviewed `fix_commit` and `fix_tree`, not an earlier implementation commit.

### Task 3A: Pin treatment imports and reconstruct the exact source lineage

- [ ] **Step 1: Add RED contract and behavior tests**

Cover the closed `apparatus.treatment_runtime` object, exact full commit/tree
formats, canonical non-root import path, equality with
`archive.repository_root`, required launcher-supplied `PYTHONPATH` placeholder
and `PYTHONDONTWRITEBYTECODE` value, and rejection when either key is
credential-backed.
In prepare/runner tests require failure before `STARTED` for a missing binding,
relative/root/symlink import root, wrong commit or tree, attached branch, dirty
tracked/untracked/ignored content, object alternates, a missing/literal/list
runtime path, a bytecode value other than `"1"`, or ambient editable-install
fallback. Reject top-level or nested Workflow Lisp Python commands when `-B`
or `-P` is absent, and forbid `-I`. A positive child probe must resolve a
sentinel module only from the locked clone even when a hostile ambient/editable
copy exists.

- [ ] **Step 2: Implement the strict generic binding**

Keep the four record kinds and existing `run_block` signature. Add no
provider-isolation dependency. `prepare` derives the binding only from its
already explicit `repository-root` and `full-revision` arguments and records
the exact tree. Put Git/root verification in a small existing-responsibility
private module so `_runner_preflight.py` remains below 500 physical lines.
Keep `HOME` and `TMPDIR` controller-owned. Require each locked launcher to
supply the exact runtime-root placeholder and bytecode value, add safe-path and
bytecode-disabled Python flags as the exact `-B -P` prefix, require the nested
Workflow Lisp command's exact `<resolved-python> -B -P -m orchestrator`
prefix, reject either missing flag, and forbid `-I`.

- [ ] **Step 3: Build one isolated reviewed source revision**

Use an ordinary `--no-hardlinks` clone, never a worktree. Detach at
`a2099be6`, apply only the two citation-fix commits and the scoped
runtime-import/doc changes, and commit them on that lineage. Require the
result's sole ancestry delta from `a2099be6` to equal the explicit reviewed
path allowlist, the three citation code/test blobs to equal `2f6be134`, and all
other predecessor blobs to remain equal. Record full commit/tree and per-path
digests; do not treat a restricted Git pathspec as proof of the full delta.

- [ ] **Step 4: Run verification and ordered reviews**

Run the exact RED/GREEN selectors, the treatment-parity and provider-free
integration smoke, all `tests/experiments` with
`pytest -q -n 16 --dist=worksteal`, and the recursive 500-line gate from the
clean clone. First obtain a contract/specification review of the runtime
binding and fail-closed cases. After approval, obtain a code-quality and
source-lineage review of the final commit/tree. Only then prepare `a1-v7`.

### Task 4: Freeze a fresh exact-method successor

The path/identity literals below that name `a1-v6`, revision `r4`, or its tmux
session are superseded by this correction and must be executed as `a1-v7`,
revision `r5`, and a fresh `a1-v7` session. Preserve `a1-v6`; do not reuse or
rename it. Add
`operations/superseded-prelaunch.a1-v6.json` beside the existing bound a1-v5
incident artifact in a1-v7. Both are auxiliary operations provenance, not
experiment records or evidence inputs.

- [ ] **Step 1: Preserve and bind a1-v5**

The immutable predecessor root is:

```text
/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v5
```

The fresh successor root and layout are:

```text
/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v6/
  apparatus/
  controller-runtime-<fix-commit-short>/
  controller-tmp/
  evidence/
  operations/
    apparatus-source-map.a1-v6.json
    calibration-revalidation.txt
    capture-controller-exit-<fix-commit-short>.sh
    launch-controller-direct-<fix-commit-short>.sh
    predecessor-incident.a1-v5.json
    prelaunch-preflight.json
    runtime-provenance.json
    run-clean-xdist-tests.sh
  pilot-lock.json
```

`work/`, `evaluation/`, and `packages/` must be absent before execution.

Do not write inside a1-v5. In the fresh successor root, create
`operations/predecessor-incident.a1-v5.json` as an auxiliary operations
provenance artifact, not an experiment record. Bind at minimum:

- a1-v5 lock, source map, runtime commit/tree/provenance, controller wrapper,
  log, and numeric exit sidecar;
- the exact valid smoke/live prefix and unused reserve IDs;
- all package-preparation completions and package manifests;
- the three reviewer launch intents and terminal transports;
- the two accepted review results;
- failed block/reviewer/session identity and exact error code/detail;
- absence of review bindings, unblinding bindings, summary, and report.

State that no predecessor evidence or session is reusable, no label-map
content was read, and no same-lock action is authorized.

The operations binding is exact and deliberately outside the experiment
contract:

1. `runtime-provenance.json` contains the incident path and SHA-256 under
   `inputs.predecessor_incident`;
2. the launch wrapper verifies exact SHA-256 values for both the incident and
   runtime provenance before preflight or execution;
3. `prelaunch-preflight.json` repeats both digests and records the predecessor
   disposition check as passed;
4. the capture wrapper verifies the launch-wrapper and preflight digests.

The incident artifact is excluded from `pilot_lock.v1`,
`apparatus.asset_manifest`, treatment staging, candidate packages, review
inputs, unblinding inputs, and successor synthesis. It is not an outcome input;
its only successor-facing claims are provenance, consumed-session exclusion,
and the prohibition on predecessor reuse.

- [ ] **Step 2: Revalidate unchanged calibration**

The metadata repair changes only the live structured inspection contract.
Rubric, stable reviewer identities, execution policy, output schema, and
package evidence bytes remain unchanged. Revalidate the complete calibration
seal under the current validators and record that limited basis. Do not claim
that calibration proved the new metadata; the new focused tests and reviews
prove it.

- [ ] **Step 3: Prepare fresh identities and roots**

Create a new randomization seed, smoke ID, five ordered live IDs, pilot ID,
control root, evidence root, work root, evaluation root, package root, and
clean ordinary detached clone at the reviewed fix commit. All IDs and roots
must be disjoint from a1-v4 and a1-v5. Do not create a Git worktree.

Create the clean clone as an ordinary standalone clone with no object
alternates:

```bash
base=/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v6
fix_commit="$(git rev-parse HEAD)"
fix_short="$(git rev-parse --short=8 HEAD)"
clean="$base/controller-runtime-$fix_short"
git clone --no-hardlinks /home/ollie/Documents/agent-orchestration "$clean"
git -C "$clean" checkout --detach "$fix_commit"
test ! -e "$clean/.git/objects/info/alternates"
test -z "$(git -C "$clean" status --porcelain=v1 --untracked-files=all)"
```

- [ ] **Step 4: Regenerate and verify bindings**

Regenerate the source map, apparatus, lock, runtime provenance, provider-free
preflight, capture wrapper, and launch wrapper. The source map starts from the
accepted a1-v5 source-map contract, changes only successor identity/root fields
and source digests affected by the reviewed fix, and is saved at the exact
a1-v6 operations path above. Require the clean runtime root to be pristine and
all output locations absent before launch.

Prepare and validate from the detached clone:

```bash
calibration=/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/calibration/round-1
python=/home/ollie/miniconda3/bin/python
cd "$clean"
PYTHONDONTWRITEBYTECODE=1 "$python" -B scripts/experiments/lean_pilot.py prepare \
  --source-map "$base/operations/apparatus-source-map.a1-v6.json" \
  --repository-root "$clean" \
  --full-revision "$fix_commit" \
  --fresh-control-root "$base/apparatus" \
  --fresh-evidence-root "$base/evidence" \
  --calibration-seal "$calibration/calibration-seal.json" \
  --lock-output "$base/pilot-lock.json"
PYTHONDONTWRITEBYTECODE=1 "$python" -B scripts/experiments/lean_pilot.py \
  validate-lock \
  --lock "$base/pilot-lock.json"
```

The generated launch wrapper accepts exactly one of `--preflight-only` or
`--execute`; the capture wrapper accepts zero arguments for a live run and
invokes the launch wrapper exactly once with `--execute`. Freeze and record
literal SHA-256 values for the source map, lock, incident, provenance,
calibration revalidation, clean-test log/exit, launch wrapper, and preflight.
No placeholder remains when either launch reviewer starts.

Run the provider-free gates:

```bash
"$base/operations/launch-controller-direct-$fix_short.sh" --preflight-only
"$base/operations/capture-controller-exit-$fix_short.sh" --self-test
```

- [ ] **Step 5: Obtain two launch reviews**

One reviewer checks the frozen contract and predecessor disposition; a second
checks the exact hash-gated zero-argument tmux launch. Neither reviewer launches
the provider.

### Task 5: Execute and close the governing lean-pilot plan

- [ ] **Step 1: Run exactly one captured controller**

Launch one hash-gated controller in tmux. Do not restart it. Monitor the
persisted block/review state and provider process until it completes or a
genuine new incident occurs.

After both reviewers approve the literal capture-wrapper SHA-256, launch with
zero wrapper arguments and no redirection:

```bash
capture="$base/operations/capture-controller-exit-$fix_short.sh"
expected_capture_sha256="<literal reviewer-approved sha256>"
test "$(sha256sum "$capture" | cut -d ' ' -f 1)" = \
  "$expected_capture_sha256"
tmux new-session -d -s lean-pilot-a1-v6-live "$capture"
```

The placeholder above is a plan-time value only; replace it in the executed
outer gate with the reviewed literal digest. Do not pass `--execute` to the
capture wrapper.

- [ ] **Step 2: Enforce the locked denominator and review order**

Require one valid smoke, then the exact contiguous live prefix stopping at
three valid blocks or five IDs. Start no review before collection closes.
Require every live reviewer slot to have one fresh session and one immutable
transport. Seal all review bindings before unblinding.

- [ ] **Step 3: Generate fresh deterministic outputs**

On successful controller completion, generate `pilot_summary.v1` into a fresh
external summary root and
`docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md` into an absent path.
The structured JSON is authoritative and the Markdown is its deterministic
view.

- [ ] **Step 4: Obtain final evidence review**

One independent reviewer checks exact lock/denominator adherence, calibration,
blinding, treatment-failure accounting, disagreement handling, `UNKNOWN`
costs, deterministic regeneration, and task-specific claim limits. Use a
second reviewer only after a concrete violation and repair.

- [ ] **Step 5: Run final verification and reconcile status**

Run focused collection/tests, lock validation, a smoke/integration check, the
recursive module-size check, and full
`pytest -q -n 16 --dist=worksteal` in tmux. Reconcile the governing design,
plan, readiness amendment, docs routing, and report without promoting
provider-phase isolation or making a general ORC-effectiveness claim.

- [ ] **Step 6: Commit only scoped reviewed paths**

Do not commit external evidence or unrelated shared-tree changes. Record the
truthful terminal:

- `STOP_APPARATUS_NOT_VIABLE`;
- `STOP_INSUFFICIENT_VALID_BLOCKS`; or
- `EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED`.
