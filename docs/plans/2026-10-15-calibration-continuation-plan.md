# Calibration Continuation Plan (Task 8, rung 1 third sample)

Freeze requires an independent review, the committed criterion and its hash recorded in `start.json` before the
first launch. No continuation run has been launched.

Criterion: [`experiments/compare/criteria/calibration-continuation.json`](../../experiments/compare/criteria/calibration-continuation.json).
Base criterion: [`calibration.json`](../../experiments/compare/criteria/calibration.json) at `9faa4c01…` (after
`amends_4`, R55). Neither the base criterion, the Task 8 report, the task packages, E-B nor E-B2 is edited.

## What This Is

The owner said "after integrating in main, continue the calibration", after R55 removed the hidden-acceptance
condition. Under R55, rung 1 (mean 1.0 blockers) is borderline and needs a third single call and review. Rung 2 (2.5)
already meets the rule on its two recorded patches.

The continuation is **post-data**. It is written after every Task 8 rung and after E-B2 were run and read. It reuses
recorded samples and must never be reported as a fresh preregistered experiment. Task 8's frozen outcome (no rung
qualified under `3149bc36…`) and E-B2's rung-3 choice stand.

Approach: run one `direct_task` and one `review_once` on rung 1 under the exact Task 8 runtime (`2b9efd81`). Then
apply the ordered stop rule over rungs 1–2.

What this makes harder later:
- The third sample is taken on a later day than samples 1–2, and provider-side model drift cannot be ruled out.
- A fresh ladder would give a cleaner claim. The owner chose reuse (R56). That does not prevent a fresh ladder
  later, but it adds a second calibration outcome that readers must tell apart from Task 8's outcome.

## Freeze

1. **R56, the owner's choice.** On 2026-10-15T19:53:11Z, before the first launch (`$E/owner-choice.json`), the owner
   answered "Completar las muestras existentes". The question was whether to continue by completing the existing
   samples, meaning a third rung-1 sample and, if rung 1 does not qualify, rung 2 on its existing mean of 2.5, or to
   start a fresh calibration. This answer supersedes the coordinator's earlier provisional interpretation. Its text
   is in the criterion's `ruling`. It is separate from `amends_4`, which stays as written.
2. **Review.** A focused Opus review, by a reviewer other than the author, of the criterion and this plan.
3. **Freeze.** Commit the criterion. Then, before the first run, write `$E/start.json` with the criterion's sha256,
   R56 and a timestamp.

## Outcome Rule

| sample 3 (rung 1) | result |
| --- | --- |
| completed, review blockers ≥ 1 (or an empty patch, R47) | rung 1 qualifies (mean ≥ 1); stop |
| review blockers 0 (APPROVE, NEEDS_HUMAN, empty findings) | rung 1 fails (mean 0.67); rung 2 qualifies on its recorded 2.5; stop |
| `direct_task` fails other than by infrastructure, or the review fails twice other than by infrastructure | rung 1 fails; rung 2; stop |
| a second contaminated rung-1 run | rung 1 rejected; rung 2; stop |

No rung-2, rung-3 or rung-4 run happens in any branch. Infrastructure stops are resumed (R3), never relaunched.

**Halt without a result** (report to the owner) in any of these cases:
- any line of `frozen-inputs.sha256` fails;
- a runtime, package, `compare_base`, CLI or stale-install path check differs from Task 8;
- a generated command's `--dry-run` fails;
- the budget gate forbids the next call.

## Commands

Run from this repository's root. Every long step runs in tmux. Every check is an explicit `&&` chain, whose exit status is the first
failed assertion's. Each launch is the last link of its chain, so a failed assertion halts it. Do not use `set -e`
here: bash ignores it inside any command on the left of `&&`.

`prepare.py run` only builds the candidate, the records and `command.sh`. The dry run is the generated command itself
with the orchestrator's `--dry-run` appended, which `orchestrate run` accepts at `2b9efd81`. Under the same
environment, entry, source root, providers file and `inputs.json`, it compiles the closed program and binds the
inputs. It then returns 0 before any run state exists, with no memo and no provider call. Its only write is the
git-ignored `.orchestrate/build/` cache, which the real run reuses.

```bash
RTC=2b9efd81305d687ce3f8b03ade334d221ba38eb3
RT=/home/ollie/calib-continuation-runtime W=/home/ollie/calib-continuation-work P=$W/rung1-pool
PY=/home/ollie/miniconda3/bin/python H=$RT/experiments/compare T=$H/tasks/cf1-generic-unions
EV=/home/ollie/Documents/agent-orchestration-compare-evidence/calibration E=$EV/continuation
C=$PWD/experiments/compare/criteria/calibration-continuation.json
SOL=1798fc7034d38dc5938472a7cff883b8381703e4
```

**0. Reused inputs unchanged** (rerun before the report):

```bash
sha256sum -c $E/frozen-inputs.sha256
```

**1. Runtime and environment.** Task 8's runtime and work roots were removed at closeout. Coordinator preflight
created `$RT` at `$RTC` on 2026-10-15 (`$E/runtime-preflight.json`). Validate that runtime; never recreate it.
Record the environment and assert it:

```bash
STALE=/home/ollie/Documents/agent-orchestration/.worktrees/omp-i1-prerequisites
test "$(git -C $RT rev-parse HEAD)" = $RTC &&
git -C /home/ollie/Documents/agent-orchestration worktree list --porcelain | grep -qx "worktree $RT" &&
test -z "$(git -C $RT status --porcelain)" &&
test "$(cd $T && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum)" \
  = "23681b729c512c7589cc9a6f0a12e7be102d7928d8f7967d2e6ca87a20dcd728  -" &&
test "$(codex --version)" = "codex-cli 0.162.1" &&
command -v bwrap &&
test "$(cd / && env -u PYTHONPATH $PY -c 'import orchestrator; print(orchestrator.__file__)')" \
  = $STALE/orchestrator/__init__.py &&
test "$(cd / && PYTHONPATH=$RT $PY -P -c 'import orchestrator; print(orchestrator.__file__)')" \
  = $RT/orchestrator/__init__.py &&
{ date -Is; $PY --version; codex --version; git -C $STALE rev-parse HEAD
  echo "stale worktree porcelain lines: $(git -C $STALE status --porcelain | wc -l)"; } > $E/env.txt &&
echo ENV-OK
```

No new smoke is run. Rung 1's own `direct_task` and `review_once` runs completed at exactly `2b9efd81` with codex-cli
0.162.1, so they show the mechanics work at this commit (R52 amendment). If any check above differs, halt.

**2. Budget.** R8, as amended, lets designed runs continue past the weekly limit on credits. It allows no run beyond
the design, and the report states the credit balance before and after. On top of R8, this plan adds a conservative
guard that is not R8 text: `used_percent < 95`, or credits available with a balance of at least 1245.01, which is
Task 8's whole credit spend.

`budget_ok` reads the rate-limit metadata only and appends it to `$E/codex-usage.txt`. It exits non-zero when
`rate_limits` is null, in which case re-read later and do not launch, and when the guard fails. Call it before every
launch, and once more after the last continuation run for the after balance.

```bash
budget_ok() { $PY -c '
import glob, json, os, sys, time
f = max(glob.glob(os.path.expanduser("~/.codex/sessions/*/*/*/rollout-*.jsonl")), key=os.path.getmtime)
last = None
for line in open(f):
    p = json.loads(line).get("payload")
    if isinstance(p, dict) and p.get("rate_limits"):
        last = p["rate_limits"]
print(json.dumps({"read_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "file": os.path.basename(f), "rate_limits": last}))
c = (last or {}).get("credits") or {}
sys.exit(0 if last and (last["primary"]["used_percent"] < 95
                        or (c.get("has_credits") and float(c.get("balance") or 0) >= 1245.01)) else 1)' | tee -a $E/codex-usage.txt
  return ${PIPESTATUS[0]}; }
```

**3. Prepare, dry-run and launch the third single call.** `dry_run_ok` runs the generated command with
`--dry-run`. It then asserts that no run root and no call record exist.

```bash
dry_run_ok() {
  local cwd
  bash -n $1/command.sh &&
  bash -c "$(cat $1/command.sh) --dry-run" &&
  cwd=$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["cwd"])' $1/record.json) &&
  { test ! -e $cwd/.orchestrate/runs || test -z "$(ls -A $cwd/.orchestrate/runs)"; } &&
  { test ! -e $1/calls || test -z "$(ls -A $1/calls)"; }; }
PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm direct_task --root $W --runtime $RT \
  --set model=gpt-6.1-sol --set effort=high
R=$W/records/direct_task/run-1     # run-2 for a contamination replacement
cmp $R/inputs.json $EV/runs/ladder/direct_task-run-1/inputs.json &&
test "$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["compare_base"])' $R/record.json)" \
  = 19f76c85a4fda1840ca75accaad4459d95d75e26 &&
dry_run_ok $R && budget_ok && tmux new-session -d -s calcont-dt1 "bash $R/command.sh > $R/run.log 2>&1"
# after an infrastructure stop only: tmux new-session -d -s calcont-dt1r "bash $R/resume.sh <run_id> >> $R/run.log 2>&1"
```

**4. Collect, scan, adjudicate.**

```bash
PYTHONPATH=$RT $PY $H/prepare.py collect --run $R
PYTHONPATH=$RT $PY $H/prepare.py scan --run $R --hash $SOL
PYTHONPATH=$RT $PY $H/prepare.py scan --run $R --verdict cleared --reason "<what the hits are>"   # only with hits
```

The harness's patterns already cover every surviving copy of earlier material. The Task 8 evidence and every sibling
checkout lie under the main-checkout prefix, and old transcripts are under `.codex/sessions` or `.claude/projects`.
Old records paths match the `records/<arm>/run-<k>` layout. The old runtime and work roots no longer exist.

A contaminated run is replaced once, by preparing the same arm again: it becomes `run-2` in `$W`. A run that failed
other than by infrastructure ends rung 1, so go to step 7. An empty `collected/final.diff` (`test -s` fails) gets no
review and counts 1 blocker.

**5. Review the third patch.** The pairing assertion enforces the base `run_membership` rule: `applied.path` is
`$R`'s `final.diff`, and `applied.sha256` is that file's hash.

```bash
PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm review_once --root $W --runtime $RT --apply $R/collected/final.diff
V=$W/records/review_once/run-1     # run-2 for a rerun or a contamination replacement
$PY -c 'import json,sys; a,b=(json.load(open(p)) for p in sys.argv[1:]); assert all(a[k]==b[k] for k in ("intent","account","replies"))' \
  $V/inputs.json $EV/runs/ladder/review_once-run-1/inputs.json &&
$PY -c 'import hashlib,json,sys; a=json.load(open(sys.argv[1]))["applied"]; assert a["path"]==sys.argv[2] and a["sha256"]==hashlib.sha256(open(sys.argv[2],"rb").read()).hexdigest()' \
  $V/record.json $R/collected/final.diff &&
dry_run_ok $V && budget_ok && tmux new-session -d -s calcont-rv1 "bash $V/command.sh > $V/run.log 2>&1"
PYTHONPATH=$RT $PY $H/prepare.py collect --run $V        # prints variant, blockers, findings, applied.path, candidate_changed
PYTHONPATH=$RT $PY $H/prepare.py scan --run $V --hash $SOL
PYTHONPATH=$RT $PY $H/prepare.py scan --run $V --verdict cleared --reason "<what the hits are>"   # only with hits
```

The review's rerun and its contamination replacement are the same command: prepare `review_once` again with the same
`--apply`, which creates `run-2` in `$W`.
- **Infrastructure stop:** resume the review; do not rerun it.
- **Other failure:** rerun once.
- **Contamination:** replace it once. That replacement uses up rung 1's one allowed contamination replacement.

**6. Hidden fraction (descriptive).** Build the pool only after the review is adjudicated, so that no clone carrying the
upstream anchor exists while an agent runs. No judge is run, and `score-*.sh` is never executed.

```bash
PYTHONPATH=$RT $PY $H/prepare.py pool --task $T --criterion $C --out $P \
  --judge claude-opus-5-5 --judge gpt-6-sol=$H/providers/score_codex.json $W/records/direct_task/run-*
sed -e "s#/home/ollie/calib-runtime#$RT#g" -e "s#/home/ollie/calib-work/ladder/rung1-pool#$P#" \
  $EV/runs/hidden-rung1.py > $E/hidden.py && diff $EV/runs/hidden-rung1.py $E/hidden.py   # paths only
for cid in $($PY -c 'import json,sys; print(*json.load(open(sys.argv[1]))["clones"])' $P/records/mapping.json); do
  tmux new-session -d -s calcont-h-$cid "$PY $E/hidden.py $cid > $E/hidden-$cid.log 2>&1; echo EXIT=\$? >> $E/hidden-$cid.log"
done
```

The fraction is void unless the upstream anchor passes 164/164.

**7. Evidence and result.** Copy into `$E` only, never into Task 8's directories or the package:
- every `$W/records/<arm>/run-<k>` as `runs/<arm>-run-<k>`, with its `state_root` as `state`;
- `$P/records` as `pool/`.

```bash
mkdir -p $E/runs $E/pool
for X in $W/records/*/run-*; do
  D=$E/runs/$(basename $(dirname $X))-$(basename $X); cp -a $X $D
  cp -a "$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["state_root"])' $X/record.json)" $D/state
done
test ! -d $P/records || cp -a $P/records/. $E/pool/
(cd $E && sha256sum runs/*/record.json runs/*/inputs.json $(ls runs/*/collected/final.diff pool/mapping.json \
  pool/hidden-*.json 2>/dev/null) > continuation-outputs.sha256)
budget_ok || true    # the after reading, for credits before and after
```

Write `$E/rung-1-continuation.json`. It holds:
- samples 1–2, by evidence path and hash;
- each continuation run, by its evidence copy, its full `$W` records path (its identity) and its hashes in
  `continuation-outputs.sha256`;
- the mean and the verdict;
- rung 2's recorded mean, if rung 1 fails.

Then rerun step 0 and `sha256sum -c continuation-outputs.sha256` (from `$E`). Write the report as
`docs/reports/<date>-calibration-continuation.md`, labelled post-data and citing R56 as the owner's choice. Keep
`$RT` and `$W` until the report is reviewed. To delete the pool, first `chmod u+r $P/clones`.

## Limits

- **Samples are not exchangeable in time.** Samples 1–2 ran on 2026-10-14 and sample 3 runs later, with the same
  pinned runtime and CLI but possibly a changed provider model.
- **The rule is known.** Under the rule, rung 1 qualifies if and only if one review returns at least one blocker.
  Otherwise rung 2 qualifies on recorded data. All eight Task 8 reviews returned `REQUEST_CHANGES`.
- **Stale editable install.** Only the import path is known to equal Task 8's (`.worktrees/omp-i1-prerequisites`).
  - That worktree is now at `fc6a9b1b` with one untracked entry, and its Task 8 HEAD was never recorded.
  - The executor is pinned by `PYTHONPATH=$RT -P`, and the shims strip `PYTHONPATH` from agents, so exposure is
    limited to agent-side imports outside the candidate.
  - `env.txt` records the worktree's HEAD and porcelain count.
  - The shared install is not altered.
- **`k = 3` at most**, and the reviewer's variance is unmeasured.
