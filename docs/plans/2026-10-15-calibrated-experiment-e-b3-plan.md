# E-B3 Plan: Maintained Workflows Against A Single Call On Rung 1

Status: **IN PROGRESS, judge-primary amendment below governs scoring**. Live state is recorded in `agent-orchestration-compare-evidence/eb3/execution-status.json`. Original pre-batch protocol: **APPROVED** (review `review_design_eb3.md`, findings F1–F7 applied; dispositions in
`revision_design_eb3.md`). Runtime and R48 package are built; S1 passed 116 tests, the upstream anchor passed 164/164, and S2 passed with four Opus sessions including its native subagent. The historical pre-batch criterion is:
[`experiments/compare/criteria/eb3.json`](../../experiments/compare/criteria/eb3.json). Design notes and fact checks:
`agent-orchestration-compare-evidence/eb3/design_eb3.md`.

## Addendum 2026-10-15: judge-primary amendment (supersedes the hidden-primary criterion for scoring)

**Status:** reviewed by independent Opus (`primary-amendment-review.md`); required E1-E5 corrections applied before freeze and queue continuation.

**Why.** The coordinator recorded this mid-batch owner reply at 2026-10-15T22:44:49Z: "don't use hidden tests, or only use them as secondary
criterion. they are imo too brittle and hard to design correctly" (`$E/owner-primary-amendment-request.json`). At that stage the queue was paused with SIGSTOP: four runs were live and continued, and five were pending. No pool or judge existed, and no hidden result or score had been read.

**What changes.**
- The new criterion is [`eb3-judge-primary.json`](../../experiments/compare/criteria/eb3-judge-primary.json).
- [`eb3.json`](../../experiments/compare/criteria/eb3.json) (sha256 `6208b5c0…`, commit `f7f91591`) and `$E/start.json`
  stay unchanged as the historical pre-batch freeze.
- **Primary measure:** the existing blind 0–8 rubric of `score.orc`, scored by the same two judges (Opus and
  `gpt-6-sol`) with the same prompts.
- **Primary entries:**
  - `design_review_execute.minus_control >= 0.9`, meaning at least 1 point;
  - `reviewed_change.paired_gain_mean >= 0.5`, with `paired_gain_runs_negative <= 0`, as in E-A;
  - run floors of 3, unchanged.
- **Hidden acceptance** is still computed by the existing `summarize`, but only as description. It has no threshold,
  gates no validity and ranks nothing.
- **The owner selected the existing blind rubric** (`owner-rubric-choice.json`); the numerical thresholds are coordinator choices fixed before scoring.
- **Unchanged:** runtime, code, prompts, task, models, arms, the nine runs, exclusions, the Fable halt and the model
  policy.
- **Judge self-preference** is now a limit on the primary measure itself. The report gives each judge's arm means and
  gains, and the agreement, beside the verdict (`judge_reporting`).

**Commands.** Use these in place of steps 6 and 10's `C`. Steps 8, 9 and 11 are otherwise unchanged.

```bash
source /home/ollie/Documents/agent-orchestration-compare-evidence/eb3/operation-env.sh
source "$E/monitor-functions.sh"     # run_state, started, tick, stop_launches, batch_done
C=$PWD/experiments/compare/criteria/eb3-judge-primary.json OLD=$PWD/experiments/compare/criteria/eb3.json
# A. after the independent Opus review: pathspec-commit the new criterion and this addendum, then
test "$(sha256sum < $OLD | cut -c1-64)" = 6208b5c05b8f80a286df96cbbe84822c9b9e020ba92e956f5e104516e2451588 &&
test "$(sha256sum < $E/start.json | cut -c1-64)" = 50d7f5e22443a8387b145c5a8a3b53c1a8f8e69cecede7d484a712c5a40634fc &&
test ! -e $P && git ls-files --error-unmatch "$C" docs/plans/2026-10-15-calibrated-experiment-e-b3-plan.md >/dev/null &&
git diff --quiet HEAD -- "$C" docs/plans/2026-10-15-calibrated-experiment-e-b3-plan.md &&
$PY -c '
import hashlib, json, subprocess, sys, time
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
pid = open(sys.argv[3]).read().strip()
commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", sys.argv[1]], text=True).strip()
plan_commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", "docs/plans/2026-10-15-calibrated-experiment-e-b3-plan.md"], text=True).strip()
assert commit and plan_commit
print(json.dumps({"recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "criterion": sys.argv[1], "criterion_sha256": h(sys.argv[1]),
  "criterion_commit": commit, "plan_commit": plan_commit,
  "amends_sha256": h(sys.argv[2]), "owner_request_sha256": h(sys.argv[4]),
  "queue_pid": pid, "queue_state": subprocess.check_output(["ps", "-o", "stat=", "-p", pid], text=True).strip()}, indent=1))' \
  $C $OLD $E/paused-queue.pid $E/owner-primary-amendment-request.json > $E/amendment-start.json
# B. continue the paused queue (it launches only the pending runs)
test -s $E/amendment-start.json && ps -o stat= -p "$(cat $E/paused-queue.pid)" | grep -q '^T' && tick &&
kill -CONT "$(cat $E/paused-queue.pid)"
```

Persist the new criterion for later shells:
```bash
cat > "$E/amendment-env.sh" <<'EOF'
C=/home/ollie/Documents/agent-orchestration-compare/experiments/compare/criteria/eb3-judge-primary.json
EOF
source "$E/amendment-env.sh"
# After sourcing operation-env.sh in any later shell, source amendment-env.sh too.
test "$C" = "$PWD/experiments/compare/criteria/eb3-judge-primary.json"
# After pool and before either judge launch:
$PY -c 'import json,sys; m=json.load(open(sys.argv[1])); a=json.load(open(sys.argv[2])); assert m["criterion_sha256"]==a["criterion_sha256"]' "$P/records/mapping.json" "$E/amendment-start.json"
```

Steps 8–9 continue with `$C` from above. Step 10 builds the pool with `--criterion $C`, so both judges bind the new
sha256, and runs `summarize --criterion $C` once. After `summarize`, read in this order:
1. the criterion's `validity` list, which has no hidden gate;
2. the measures and the verdict;
3. the per-judge values and the agreement;
4. hidden acceptance, as description, with any upstream-anchor shortfall stated as a caveat.

The report names both criteria and the stage at which the amendment was made.

---

**No E-B3 call** (S2 probe, run or judge) happens before both of these:
- the model guard is reviewed and committed;
- this plan is committed with a pathspec commit, and the commit is recorded in `$E/plan-commit.txt`.

Governing documents:
- the [harness design](../design/orc_effectiveness_comparison_harness.md);
- the harness [README](../../experiments/compare/README.md);
- the effectiveness plan's Task 9 and its rulings ([plan](2026-10-14-effectiveness-harness-and-experiments-plan.md));
- the [calibration continuation](../reports/2026-10-15-calibration-continuation.md);
- the [model guard plan](2026-10-15-experiment-model-guard-plan.md).

E-B2's [criterion](../../experiments/compare/criteria/eb2.json) and
[report](../reports/2026-10-15-calibrated-orc-versus-single-call.md) are the form this plan follows. They, the
calibration criteria and every archived evidence file stay unchanged.

## What This Is

The owner said "continue the experiments" after two things: the post-data continuation qualified rung 1
(`cf1-generic-unions`, review blockers 1, 1, 1), and the owner had asked that no experiment use Fable. E-B3 runs the
E-B2 design on rung 1:
- the same three arms, bindings, judges and measures;
- three runs per arm, exactly nine designed runs;
- no replacement and no `best_of_n`.

It is a prospective experiment on a task whose qualification was post-data, and it is reported as exploratory.

Decisions and who made them:
- **Owner:** no Fable model in any experiment call; planner `claude-opus-5-5`; "continue the experiments".
- **Coordinator:**
  - continue E-B2's design with nine runs, no replacement, and infrastructure resumes only;
  - the one-node threshold (`coordinator-threshold-note.json`; an optional owner question is still unanswered, and
    an answer before freeze would replace the choice; it is not a freeze precondition);
  - runtime Option A;
  - the R48 package as a new directory.

Approach:
1. Freeze a runtime: E-B2's `e8882086`, plus the reviewed model guard's harness files byte for byte, plus a rung-1
   package variant whose only change is the R48 upstream anchor.
2. Prove the guard on real CLIs with one bounded probe, after this plan is committed.
3. Run nine runs, then pool, judge and summarize once.

What this makes harder later:
- The runtime commit sits on a side branch from `e8882086`, kept reachable by a tag. The result describes that
  orchestrator, not current `main` (v0.2.0).
- A second rung-1 package directory (`cf1-generic-unions-r48`) exists beside the calibration package, and readers must
  tell them apart. The criterion names both.
- If the control lands near calibration (about 0.92), DRE's expected headroom is about 0.08. A one-node threshold is
  inside single-call noise, and the criterion says so.

## Pending (parent supplies; nothing below runs until its prerequisites exist)

| item | needed for | status |
| --- | --- | --- |
| `G`: reviewed, committed guard (subagent pin `CLAUDE_CODE_SUBAGENT_MODEL=claude-opus-5-5`, `_FORCE=1`, atomic guard install; reviewed separately, 116 harness tests passing) | step 1 | `60775825`, approved and integrated in main |
| `RTC` and the R48 `package_sha256` | steps 2, 6 | runtime `6f43fae173b5b09374665fb17ae7a7c120514dee`; package `5e2ef0a4aa54b1c9938b57ffc65d18f9099311af9c66567c4092402c605f0f80` |
| upstream anchor 164/164 | step 3 | passed, `anchor-upstream-r48.json` |
| S1 at `$RT` | step 4 | 116 passed, `EXIT=0` |
| plan pathspec commit, recorded in `$E/plan-commit.txt` | step 5 (S2) | `da9bf8ef`, before S2 |
| S2 real-CLI probe | step 6 | passed, `s2-probe-check.json`; five shim calls, four Opus sessions |
| Opus re-review of this revision, then the criterion freeze | step 6 | `review_design_eb3_r1.md` APPROVED; required R1/R2 corrections applied |
| optional owner threshold answer | none; it replaces the coordinator's choice only if it arrives before freeze | unanswered |

## Runtime (Option A, decided)

Fact base, checked on 2026-10-15 (the commands are in `design_eb3.md`):
- From `e8882086` to `ee0d9cfa`, `experiments/compare` changes only in `criteria/`. The arms' workflows, provider
  templates, controls, `score.orc` and the harness test modules are identical.
- The harness is standard-library Python and bash. It reaches the orchestrator only through `command.sh` and the run
  state files.
- The orchestrator changes by 120 files and about 16k lines up to `main`.
- `2b9efd81` (calibration) and `e8882086` differ only in `summarize.py`.

Branch `eb3-runtime` from `e8882086`:
- commit 1: the guard's harness files, byte-identical to `G`;
- commit 2: the package variant.

E-B2's smoke, batch, judges and summarize at `e8882086`, and rung 1's calibration `direct_task` runs at `2b9efd81`, stand
as mechanics evidence for the unchanged orchestrator path.

The guard branch's other changes are not backported:
- Opus defaults in `workflows/examples/*.orc`, `experiments/agent_chess` and `experiments/orc_repl_feature`;
- docs and the README;
- `tests/test_workflow_lisp_design_review_execute_agents_example.py`.

E-B3 passes `planner_model` explicitly (asserted on `inputs.json`), and every other Claude call binds a literal or a
passed model. At `e8882086` DRE's `planner_model` default is still `claude-fable-5-1`. The `--set`, the input
assertion and the guard's refusal cover it.

## Package Variant (R48, decided: new directory)

The calibration anchor is `git diff c77e7ec0 1798fc70 -- . ':!tests' ':!docs/design' ':!artifacts'`: 98 files,
sha256 `4c045c27…`. Merges `df39415b` and `10b03f09` brought AGENTS.md, docs plans and reports, and
`experiments/orc_vs_single_call/` (including judge ratings) into the range. Pool does not strip anchors.

- **Rebuild:** `git diff c77e7ec0 1798fc70 -- orchestrator specs workflows`. It has 45 files and sha256
  `4f74faa3c17edb0d788dc9f5130d96df5055b41268153553a81aff6924b48101`, and it applies at the base.
- It keeps the main runtime repair `5a02cb0f`, which `task.txt` asks for ("the loop-exhaustion and
  checkpoint-restore repairs they depend on"). Its tests are among the 164.
- `experiments/compare/tasks/cf1-generic-unions-r48` is a copy of the calibration package with only
  `anchors/cf1-generic-unions-upstream.diff` replaced, so the anchor stems are unchanged. Neither package has `seed/`.
- The calibration package (`23681b72…`) is never edited.
- A filtered anchor below 164/164 stops the experiment for a design decision. The hidden set is never edited.

## Model Policy And Smoke

No call uses a Fable model: not arms, nested calls, in-process subagents, judges, or authoring and review subagents.
Codex runs only the pre-registered experiment calls and the S2 Codex probe. Authoring and review are Opus subagents.
The shared `~/.claude/settings.json` default is `claude-fable-5-1`, so any guard bypass would be a Fable call. Every
probe below therefore fails closed.

- **S0, reused:** the guard's own gate: separate review and 116 passing harness tests that run the real shim under
  real `bwrap` with stand-in CLIs. It stands for the runtime because the backported blobs are asserted identical to
  `G`, and the test modules are identical at `e8882086`.
- **S1, at the runtime:** the same harness modules run from `$RT` against `e8882086`'s orchestrator.
- **S2, bounded real-CLI probe** (after the plan commit). It covers what stand-ins cannot:
  - real argument pass-through;
  - a real Codex shell's `PATH`;
  - the CLI 2.1.301 subagent pin;
  - the real session format.

  It runs in this order:
  - **c, refusal.** Fable `--model` and `--fallback-model` refusals and one allowed control, against a recording
    stub `claude` placed before the real one. The real CLI is never reachable.
  - **a, Claude.** An Opus top-level call that makes one Agent-tool subagent call explicitly requesting
    `model: sonnet` (an allowed model, never Fable) and runs one fail-closed nested `claude -p`.
  - **b, Codex.** A Codex `gpt-6-sol` low-effort call that runs the same fail-closed nested `claude -p`.

  Expected: 5 shim calls; at least 4 Claude session files, at least one of them a subagent transcript; every Claude
  answer `claude-opus-5-5`. Not pooled and not measured.
- **No arm smoke.** The arms' orchestrator path is unchanged from E-B2. Every watchdog tick checks every started tree
  (step 8).

`$E/model_census.py` (step 3) is an evidence-only command, not a harness feature. It uses the standard library and
reuses `scan.claude_sessions` (recursive) and `scan.answering_model`. It writes metadata only: session counts, model
counts, session id, mtime and `cwd`, and never message text, prompts or tool inputs.
- **`census DIR...`:** answering-model counts per run tree or judge directory. It exits 3 on any Fable answer.
- **`sweep SINCE TREE...`:** `-tmp-*` project sessions written since `SINCE`. A session is attributed to a tree only
  when its `/tmp/<rel>` `cwd` exists under exactly one listed tree's `tmp/` and not on the host `/tmp`. It exits 3
  only on an attributed Fable session.
- **Limits:**
  - a `cwd` of exactly `/tmp`, or a `rel` that is shared or also exists on the host, stays unattributed;
  - host sessions default to Fable, so unattributed Fable sessions are expected and only counted;
  - a session started by an absolute CLI path or a reset `PATH` outside `/tmp` and outside a tree is invisible to
    scan, census and sweep.

## Commands

Run from this repository's root (`/home/ollie/Documents/agent-orchestration-compare`). Rules for every step:
- Every check is an `&&` chain, and each launch is its last link.
- Every long step runs in tmux on the private socket `/tmp/claude-tmux-sockets/claude.sock`. Output streams through
  `tee`, and the step ends with an `EXIT=` line.
- Nothing downstream starts before the `EXIT=` line it depends on.
- Never `pkill -f` a pattern from your own command line.
- Commit only with pathspecs and no assistant attribution.

```bash
MAIN=/home/ollie/Documents/agent-orchestration TM="tmux -S /tmp/claude-tmux-sockets/claude.sock"
E2=e88820864c894c96ec2023f85b95db7a9ef59d6d GB=ee0d9cfa4f18e0b1305a6fc2d0671981684e6af4
G=60775825ca0f4efaf5c0b8434efe410030f301ed                           # the reviewed guard commit
RT=/home/ollie/eb3-runtime W=/home/ollie/eb3-work P=/home/ollie/eb3-work/pool PR=/home/ollie/eb3-probe
PY=/home/ollie/miniconda3/bin/python H=$RT/experiments/compare T=$RT/experiments/compare/tasks/cf1-generic-unions-r48
O=$RT/experiments/compare/tasks/cf1-generic-unions C=$PWD/experiments/compare/criteria/eb3.json
E=/home/ollie/Documents/agent-orchestration-compare-evidence/eb3
EV=/home/ollie/Documents/agent-orchestration-compare-evidence/calibration
Q=/home/ollie/Documents/agent-orchestration-compare-evidence/queue.py
B=c77e7ec0b0626914f81b7d1bd6249491e6c59c89 SOL=1798fc7034d38dc5938472a7cff883b8381703e4
STALE=/home/ollie/Documents/agent-orchestration/.worktrees/omp-i1-prerequisites
waitexit() { until grep -q '^EXIT=' "$1" 2>/dev/null; do sleep 30; done; tail -1 "$1"; grep -qx 'EXIT=0' "$1"; }
```

Run `waitexit` from a coordinator wakeup loop, not a foreground sleep. It returns non-zero unless the step exited 0.

### 1. Runtime branch (after `G` exists)

```bash
git -C $MAIN merge-base --is-ancestor $GB $G &&
FILES=$(git -C $MAIN diff --name-only $GB $G -- experiments/compare tests/experiments \
          ':!experiments/compare/criteria' ':!experiments/compare/tasks') &&
echo "$FILES" > $E/backport-files.txt &&
BAD=$(for f in $FILES; do                          # pre-images identical at E2 and GB (or absent in both)
  test "$(git -C $MAIN rev-parse -q --verify $E2:$f)" = "$(git -C $MAIN rev-parse -q --verify $GB:$f)" || echo "$f"
done) && { test -z "$BAD" || { echo "PRE-IMAGE DIFFERS: $BAD"; false; }; } &&
git -C $MAIN worktree add -b eb3-runtime $RT $E2 &&
git -C $MAIN diff --binary $GB $G -- $FILES | git -C $RT apply --index &&
git -C $RT diff --cached --quiet $G -- $FILES &&     # index equals the reviewed guard blobs
git -C $RT commit -q -m "experiments: backport the reviewed model guard harness to the E-B3 runtime" -- $FILES &&
echo BACKPORT-OK
```

Any `PRE-IMAGE DIFFERS` line or a non-empty diff stops here.

### 2. Package variant and audit

```bash
cp -a $O $T &&
git -C $MAIN diff $B $SOL -- orchestrator specs workflows > $T/anchors/cf1-generic-unions-upstream.diff &&
test "$(sha256sum < $T/anchors/cf1-generic-unions-upstream.diff | cut -c1-64)" \
  = 4f74faa3c17edb0d788dc9f5130d96df5055b41268153553a81aff6924b48101 &&
test "$(grep -c '^diff --git' $T/anchors/cf1-generic-unions-upstream.diff)" = 45 &&
test "$(diff -rq $O $T)" = "Files $O/anchors/cf1-generic-unions-upstream.diff and $T/anchors/cf1-generic-unions-upstream.diff differ" &&
test "$(cd $O && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum)" \
  = "23681b729c512c7589cc9a6f0a12e7be102d7928d8f7967d2e6ca87a20dcd728  -" &&
git -C $RT add experiments/compare/tasks/cf1-generic-unions-r48 &&
git -C $RT commit -q -m "experiments: rung-1 package variant with the R48 upstream anchor" -- experiments/compare/tasks/cf1-generic-unions-r48 &&
RTC=$(git -C $RT rev-parse HEAD) && echo $RTC > $E/runtime-commit.txt &&
(cd $T && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum) | tee $E/package-sha256.txt
```

### 3. Evidence scripts, and the upstream anchor at 164/164 (about 7 minutes)

```bash
cat > $E/anchor_check.py <<'EOF'
"""R48 upstream anchor hidden check. usage: anchor_check.py H T CLONE OUT PY"""
import json, sys
from pathlib import Path
h, t, clone, out, py = sys.argv[1:]
sys.path.insert(0, h)
import summarize
nodes = [l.strip() for l in (Path(t) / "hidden_tests.txt").read_text().splitlines() if l.strip()]
failed = summarize.hidden_failures(Path(clone), Path(t), nodes, py)
Path(out).write_text(json.dumps({"nodes": len(nodes), "failed": failed}, indent=2) + "\n")
print(f"{len(nodes) - len(failed)}/{len(nodes)}")
EOF
cat > $E/model_census.py <<'EOF'
"""E-B3 evidence-only model census; metadata only (no message text, prompts or tool inputs).
usage: model_census.py H census DIR...        answering-model counts per run tree or judge directory; exit 3 on Fable
       model_census.py H sweep SINCE TREE...  -tmp-* project sessions written since SINCE (epoch s); exit 3 on an
                                              attributed Fable session"""
import json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import scan  # claude_sessions (recursive per tree slug) and answering_model (assistant message.model)
mode, rest, home = sys.argv[2], sys.argv[3:], Path.home()

def rows(path):
    for line in path.open(errors="replace"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            yield row

def models(path):
    return Counter(m for row in rows(path) for m in scan.answering_model(row))

def fable(counts):
    return sum(n for m, n in counts.items() if "fable" in m.lower())

if mode == "census":
    out = {}
    for d in rest:
        files = list(scan.claude_sessions(Path(d), home))
        out[d] = {"sessions": len(files), "models": dict(sum((models(f) for f in files), Counter()))}
    print(json.dumps(out, indent=1))
    sys.exit(3 if any(fable(v["models"]) for v in out.values()) else 0)
since, trees, found = float(rest[0]), [Path(t) for t in rest[1:]], []
for f in sorted((home / ".claude" / "projects").glob("-tmp-*/**/*.jsonl")):
    if f.stat().st_mtime < since:
        continue
    cwd = next((r["cwd"] for r in rows(f) if isinstance(r.get("cwd"), str)), None)
    rel = cwd[5:] if cwd and cwd.startswith("/tmp/") else ""
    owners = [str(t) for t in trees if rel and (t / "tmp" / rel).exists()]
    tree = owners[0] if len(owners) == 1 and not (Path("/tmp") / rel).exists() else None
    found.append({"session": f.stem, "mtime": f.stat().st_mtime, "cwd": cwd, "models": dict(models(f)),
                  "attributed_tree": tree})
print(json.dumps(found, indent=1))
sys.exit(3 if any(fable(s["models"]) and s["attributed_tree"] for s in found) else 0)
EOF
mkdir -p /home/ollie/eb3-anchor-check/clone && git -C $MAIN archive $B | tar -x -C /home/ollie/eb3-anchor-check/clone &&
(cd /home/ollie/eb3-anchor-check/clone && git apply $T/anchors/cf1-generic-unions-upstream.diff) &&
$TM new-session -d -s eb3-anchor bash -o pipefail -c "$PY -I $E/anchor_check.py $H $T /home/ollie/eb3-anchor-check/clone \
  $E/anchor-upstream-r48.json $PY 2>&1 | tee $E/anchor-upstream-r48.log; echo EXIT=\$? >> $E/anchor-upstream-r48.log"
# after EXIT:
waitexit $E/anchor-upstream-r48.log &&
$PY -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["nodes"]==164 and d["failed"]==[]' $E/anchor-upstream-r48.json &&
rm -rf /home/ollie/eb3-anchor-check
```

The clone is the base tree plus the anchor without `.git`. That is what pool builds for a seedless package, and
`hidden_failures` drops `.git` anyway. The binding gate is still the pool's per-batch anchor check. The clone holds the
solution's runtime files, so it is deleted before any agent runs.

### 4. Environment and S1

```bash
test "$(git -C $RT rev-parse HEAD)" = "$(cat $E/runtime-commit.txt)" && test -z "$(git -C $RT status --porcelain)" &&
test "$(codex --version)" = "codex-cli 0.162.1" && command -v bwrap &&
test "$(cd / && PYTHONPATH=$RT $PY -P -c 'import orchestrator; print(orchestrator.__file__)')" = $RT/orchestrator/__init__.py &&
! git -C $STALE merge-base --is-ancestor $SOL HEAD &&
( date -Is; $PY --version; codex --version; claude --version; git -C $STALE rev-parse HEAD
  cd / && env -u PYTHONPATH $PY -c 'import orchestrator; print(orchestrator.__file__)' ) > $E/env.txt &&
$TM new-session -d -s eb3-s1 bash -o pipefail -c "cd $RT && PYTHONPATH=$RT $PY -m pytest -q -n 16 --dist=worksteal \
  tests/experiments/test_compare_harness.py tests/experiments/test_compare_pool_summarize.py \
  tests/experiments/test_compare_review_once.py tests/test_workflow_evaluated_compare_score.py 2>&1 | tee $E/s1-harness.log; \
  echo EXIT=\$? >> $E/s1-harness.log"
waitexit $E/s1-harness.log
```

Codex must stay at `0.162.1` for every later step. The Claude CLI version is recorded at the start and at the end.

### 5. S2 real-CLI probe (only after `$E/plan-commit.txt` exists)

```bash
test -s $E/plan-commit.txt && git merge-base --is-ancestor "$(cat $E/plan-commit.txt)" HEAD &&
mkdir -p $PR/records $PR/tree/tmp $PR/stub && git init -q $PR/tree/cand-1 &&
git -C $PR/tree/cand-1 commit -q --allow-empty -m probe-base && PB=$(git -C $PR/tree/cand-1 rev-parse HEAD) &&
SINCE=$(date +%s) && echo $SINCE > $PR/since &&
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> %s/stub.log\nexit 99\n' $PR > $PR/stub/claude && chmod +x $PR/stub/claude
probe() { (cd $PR/tree/cand-1 && env PATH=$H/shim:$1:$PATH COMPARE_ROOT=$PR/records COMPARE_TREE=$PR/tree \
  COMPARE_BASE=$PB TMPDIR=$PR/tree/tmp "${@:2}"); }
# c: refusals against the recording stub (the stub comes before the real claude, so no real call is possible)
echo x | probe $PR/stub claude -p --model claude-fable-5-1; echo "c1 exit=$?" >> $PR/c.out
echo x | probe $PR/stub claude -p --model claude-opus-5-5 --fallback-model claude-fable-5-1; echo "c2 exit=$?" >> $PR/c.out
echo x | probe $PR/stub claude -p --model claude-opus-5-5; echo "c3 exit=$?" >> $PR/c.out
grep -qx 'c1 exit=2' $PR/c.out && grep -qx 'c2 exit=2' $PR/c.out && grep -qx 'c3 exit=99' $PR/c.out &&
test "$(wc -l < $PR/stub.log)" = 1 && grep -q -- '--model claude-opus-5-5' $PR/stub.log && echo C-OK
cat > $PR/nested.txt <<EOF
Run exactly this one shell command and include its full output in your reply:
test "\$(command -v claude)" = "$PR/tree/.model-guard/claude" && claude -p "Say OK only." || echo GUARD-MISSING
If the output contains GUARD-MISSING, run nothing else.
EOF
{ echo 'Do exactly these two things and nothing else.'
  echo '1. Use the Agent tool once, with model "sonnet", asking the subagent to reply with the single word OK.'
  echo '2. The shell step below.'; cat $PR/nested.txt
  echo 'Reply with the subagent'"'"'s reply and the command output.'; } > $PR/agent.txt
# a, then b (real calls; only after C-OK)
probe /nonexistent claude -p --model claude-opus-5-5 --effort low --permission-mode bypassPermissions < $PR/agent.txt > $PR/a.out 2>&1
probe /nonexistent codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check \
  --model gpt-6-sol --config model_reasoning_effort=low < $PR/nested.txt > $PR/b.out 2>&1
```

Pass, all of:
- `C-OK`, from refusals that never reached the real CLI;
- `$PR/a.out` and `$PR/b.out` contain an `OK` from the nested call and no `GUARD-MISSING`;
- `$PR/records/calls/` holds 5 calls;
- the census check:

  ```bash
  $PY -I $E/model_census.py $H census $PR/tree | tee $PR/census.json &&
  $PY -c 'import json,sys; d=json.load(open(sys.argv[1])); v=d[sys.argv[2]]; assert v["sessions"]>=4 and set(v["models"])=={"claude-opus-5-5"}' $PR/census.json $PR/tree
  ```

- With `_FORCE=1`, Claude Code removes the Agent tool's model selector; an explicit `model: sonnet` argument is therefore unavailable. The prompt requests Sonnet, and this expected refusal is recorded in `s2-probe-check.json` against the [vendor contract](https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model). The required evidence is at least one subagent transcript, meaning a `.jsonl` below the top level of the probe tree's project directory
  (`find ~/.claude/projects/-home-ollie-eb3-probe-tree* -mindepth 2 -name '*.jsonl'`), whose assistant rows answer
  `claude-opus-5-5`. If CLI 2.1.301 stores subagent transcripts elsewhere, locate the file read-only and record its
  path. The probe does not pass without the subagent's own answering model.

If the agent made no subagent call, probe a is inconclusive: rerun probe a once and record it. A second miss, or any
other failure, goes back to the guard implementer, and the experiment does not freeze. A non-Opus or Fable answer is
a guard defect.

Copy `$PR/*.out`, `$PR/stub.log`, `$PR/census.json`, `$PR/records` and the probe's session files into `$E/probe/`,
then delete `$PR`.

### 6. Freeze

1. Fill in the criterion: `guard_commit`, `runtime.commit`, `package_sha256`, and an owner threshold answer if one
   arrived. Never fill in a value that has not been produced.
2. An Opus reviewer distinct from the author re-reviews the revision. Apply accepted findings.
3. Commit `experiments/compare/criteria/eb3.json` with a pathspec commit, then tag the runtime and write `start.json`:

```bash
git -C $MAIN tag eb3-runtime-frozen "$(cat $E/runtime-commit.txt)" &&
$PY -c '
import hashlib, json, sys, time
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
read = lambda p: open(p).read().split()[0]
print(json.dumps({"recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "criterion_sha256": h(sys.argv[1]),
                  "criterion_commit": sys.argv[2], "plan_commit": read(sys.argv[3]), "runtime_commit": read(sys.argv[4]),
                  "package_sha256": read(sys.argv[5]),
                  "threshold": "coordinator one-node choice (coordinator-threshold-note.json) unless the criterion records an owner answer",
                  "script_sha256": {p: h(p) for p in sys.argv[6:]}}, indent=1))' \
  $C "$(git log -1 --format=%H -- $C)" $E/plan-commit.txt $E/runtime-commit.txt $E/package-sha256.txt \
  $Q $E/anchor_check.py $E/model_census.py > $E/start.json
```

No batch run starts before `start.json` exists.

### 7. Batch: exactly nine runs, at most four live

```bash
budget_ok() { $PY -c '
import glob, json, os, sys, time
f = max(glob.glob(os.path.expanduser("~/.codex/sessions/*/*/*/rollout-*.jsonl")), key=os.path.getmtime)
last = None
for line in open(f):
    p = json.loads(line).get("payload")
    if isinstance(p, dict) and p.get("rate_limits"): last = p["rate_limits"]
print(json.dumps({"read_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "file": os.path.basename(f), "rate_limits": last}))
c = (last or {}).get("credits") or {}
sys.exit(0 if last and c.get("has_credits") and float(c.get("balance") or 0) >= 5000 else 1)' | tee -a $E/codex-usage.txt
  return ${PIPESTATUS[0]}; }
dry_run_ok() { local cwd; bash -n $1/command.sh && bash -c "$(cat $1/command.sh) --dry-run" &&
  cwd=$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["cwd"])' $1/record.json) &&
  { test ! -e $cwd/.orchestrate/runs || test -z "$(ls -A $cwd/.orchestrate/runs)"; } &&
  { test ! -e $1/calls || test -z "$(ls -A $1/calls)"; }; }
test -s $E/start.json && test ! -e $W && test ! -e /home/ollie/eb3-anchor-check && test ! -e $PR &&
for k in 1 2 3; do
  PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm design_review_execute --root $W --runtime $RT \
    --set planner_model=claude-opus-5-5 --set reviewer_model=gpt-6.1-sol &&
  PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm direct_task --root $W --runtime $RT \
    --set model=gpt-6.1-sol --set effort=high &&
  PYTHONPATH=$RT $PY $H/prepare.py run --task $T --arm reviewed_change --root $W --runtime $RT || break
done
RUNS=$(for k in 1 2 3; do for a in design_review_execute direct_task reviewed_change; do printf '%s ' "$W/records/$a/run-$k"; done; done)
ok=1; for R in $RUNS; do dry_run_ok $R || { echo "DRY-RUN FAILED $R"; ok=0; }; done
for k in 1 2 3; do
  cmp $W/records/direct_task/run-$k/inputs.json $EV/runs/ladder/direct_task-run-1/inputs.json || ok=0
  $PY -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["planner_model"]=="claude-opus-5-5" and d["reviewer_model"]=="gpt-6.1-sol"' \
    $W/records/design_review_execute/run-$k/inputs.json || ok=0
  $PY -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["task"]==open(sys.argv[2]).read() and d["intent"]==open(sys.argv[3]).read()' \
    $W/records/reviewed_change/run-$k/inputs.json $T/task.txt $T/intent.txt || ok=0
done
test $ok = 1 && test "$(ls -d $W/records/*/run-* | wc -l)" = 9 && budget_ok && date +%s > $E/batch-since &&
$TM new-session -d -s eb3-batch bash -o pipefail -c "env -u PYTHONPATH $PY $Q 4 $RUNS 2>&1 | tee $W/queue.log; echo EXIT=\$? >> $W/queue.log"
```

The queue interleaves the arms, so no arm runs only early or only late.

### 8. Monitoring: coordinator wakeups every 20 minutes or less

One mechanism: a recurring coordinator wakeup (a `/loop` or cron wakeup at 20 minutes or less). It ends when
`batch_done` holds. Each tick does these things and nothing else:
- runs `tick`, which appends one line to `$E/watchdog.log`;
- applies the Fable halt rule;
- resumes infrastructure stops (R3).

```bash
run_state() { $PY -c '
import json, sys; from pathlib import Path; sys.path.insert(0, sys.argv[2]); import prepare
r = json.load(open(sys.argv[1] + "/record.json")); root = Path(r["state_root"])
for d in sorted(p for p in root.glob("*") if (p / "memo.jsonl").exists()):
    rows = prepare.read_memo(d / "memo.jsonl"); t = rows[-1] if rows and rows[-1]["record"] == "terminal" else {}
    print(sys.argv[1], d.name, t.get("outcome", "running"))' $1 $H; }
started() {   # run trees and judge directories whose first shim call exists
  for R in $RUNS; do test -n "$(ls -A $R/calls 2>/dev/null)" && $PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["tree"])' $R/record.json; done
  test -f $P/records/mapping.json && $PY -c '
import json, sys; from pathlib import Path
pool = Path(sys.argv[1])
for judge, info in json.load(open(pool / "records" / "mapping.json"))["judges"].items():
    calls = pool / "records" / "judges" / judge / "calls"
    if calls.is_dir() and any(calls.iterdir()):
        print(pool / "judges" / info["dir"])' $P; }
tick() { local s=0 trees t; trees=$(started)
  for t in $trees; do cmp -s $t/.model-guard/claude $H/shim/model-guard || { echo "GUARD-MISMATCH $t"; s=1; }; done
  test -z "$trees" || $PY -I $E/model_census.py $H census $trees > $E/census-latest.json || s=1
  $PY -I $E/model_census.py $H sweep "$(cat $E/batch-since)" $trees > $E/sweep-latest.json || s=1
  echo "$(date -Is) started=$(echo $trees | wc -w) $(for R in $RUNS; do run_state $R; done | awk '{print $NF}' | sort | uniq -c | tr -s ' \n' ' ') status=$s" >> $E/watchdog.log
  return $s; }
stop_launches() {   # pauses the queue, keeping its pane and live runs alive
  local pane q; pane=$($TM display-message -p -t eb3-batch '#{pane_pid}') &&
  q=$(ps -o pid=,comm= --ppid $pane | awk '$2 ~ /^python/ {print $1}') && test -n "$q" && kill -STOP $q && echo "$q" > $E/paused-queue.pid
  echo "$(date -Is) launches stopped: $1" >> $E/watchdog.log; }
batch_done() { grep -q '^EXIT=' $W/queue.log && ! $TM ls 2>/dev/null | grep -q '^eb3-r-' &&
  ! { for R in $RUNS; do run_state $R; done | grep -q ' running$'; }; }
```

- **Fable halt.** `tick` returns non-zero on a guard mismatch, a Fable answer in any started tree, or an attributed
  Fable sweep session. On that tick:
  1. call `stop_launches`, and start no resume;
  2. copy `census-latest.json` and `sweep-latest.json` to timestamped files;
  3. investigate and record the cause in `$E/rulings.md`.

  The affected run is excluded. Launches continue only if the recorded cause lies outside the frozen runtime and needs
  no runtime change. Continue the same queue with `kill -CONT "$(cat $E/paused-queue.pid)"`; it records finished live runs and launches only pending ones. Never restart `$Q`.
  Otherwise, halt without a result. Never retry a call that could reach Fable.
- **Resume rule (R3).** A run that stopped on provider infrastructure (rate limit, usage limit, auth, or a CLI crash
  before any agent output) is resumed in its own directory, only when:
  - fewer than four runs are live;
  - the last `tick` passed;
  - `budget_ok` passes.

  Resume command:
  `$TM new-session -d -s eb3-r-<arm>-<k> bash -o pipefail -c "bash $R/resume.sh <run_id> 2>&1 | tee -a $R/run.log; echo EXIT=\$? >> $R/run.log"`.
  Record the evidence for the classification in `$E/rulings.md`. Every other failure, timeouts included, stays
  failed. No run is relaunched, replaced or added.
- **Run ids.** At each tick, `for R in $RUNS; do run_state $R; done >> $E/run-ids.txt`.

### 9. Collect, scan, census, adjudicate (after `batch_done`)

```bash
batch_done && tick &&
for R in $RUNS; do PYTHONPATH=$RT $PY $H/prepare.py collect --run $R && PYTHONPATH=$RT $PY $H/prepare.py scan --run $R --hash $SOL || break; done
cp $E/census-latest.json $E/census-runs.json && cp $E/sweep-latest.json $E/sweep-runs.json
PYTHONPATH=$RT $PY $H/prepare.py scan --run $R --verdict cleared --reason "<what the hits are>"         # after reading them
PYTHONPATH=$RT $PY $H/prepare.py scan --run $R --verdict contaminated --reason "<what the agent read>"
```

For a Fable session attributed by the sweep, record a contaminated verdict on its run before pool, or on its judge before summarize, using `prepare.py scan --run R --verdict contaminated --reason "attributed Fable -tmp- session <id>"` (judge: `--pool P --judge J`). This applies even when the scan itself has zero hits.

A Fable-model hit cannot be cleared, and pool excludes that run. There is no replacement, so an excluded or failed run
leaves its arm's claim not evaluated.

### 10. Pool, judges, summarize: one at a time, each after the previous `EXIT=0`

```bash
PYTHONPATH=$RT $PY $H/prepare.py pool --task $T --criterion $C --out $P \
  --judge claude-opus-5-5 --judge gpt-6-sol=$H/providers/score_codex.json $RUNS &&
budget_ok && $TM new-session -d -s eb3-j1 bash -o pipefail -c "bash $P/records/score-claude-opus-5-5.sh 2>&1 | tee $E/judge-opus.log; echo EXIT=\$? >> $E/judge-opus.log"
waitexit $E/judge-opus.log && PYTHONPATH=$RT $PY $H/prepare.py verify-pool --pool $P &&
PYTHONPATH=$RT $PY $H/prepare.py scan --pool $P --judge claude-opus-5-5 --hash $SOL && tick    # adjudicate hits
budget_ok && $TM new-session -d -s eb3-j2 bash -o pipefail -c "bash $P/records/score-gpt-6-sol.sh 2>&1 | tee $E/judge-gpt.log; echo EXIT=\$? >> $E/judge-gpt.log"
waitexit $E/judge-gpt.log && PYTHONPATH=$RT $PY $H/prepare.py verify-pool --pool $P &&
PYTHONPATH=$RT $PY $H/prepare.py scan --pool $P --judge gpt-6-sol --hash $SOL && tick          # adjudicate hits
# Only after judge 2's verify-pool, scan, adjudication and tick above succeeded:
cp $E/census-latest.json $E/census-final.json && cp $E/sweep-latest.json $E/sweep-final.json &&
$TM new-session -d -s eb3-sum bash -o pipefail -c "PYTHONPATH=$RT $PY $H/summarize.py --pool $P --criterion $C --python $PY 2>&1 | tee $E/summarize.log; echo EXIT=\$? >> $E/summarize.log"
waitexit $E/summarize.log
```

- Pass the nine designed runs. Pool lists every excluded run with its reason.
- A judge stopped by a provider failure is resumed with `resume-<judge>.sh <run_id>` in tmux with an `EXIT=` line.
  It is never re-run.
- `summarize` runs once. With 164 nodes per clone over about 18 clones, it takes 2–3 hours.
- No patch, hidden fraction or judge score is read before it.
- Then read, in this order:
  1. the upstream anchor's `hidden` is 1.0 in every batch;
  2. the criterion's `validity` list, checked by the controller;
  3. the measures and the verdict.

### 11. Evidence, report, cleanup

- Copy each `$W/records/<arm>/run-<k>` as `$E/runs/<arm>-run-<k>`, with its state root as `state/` and its tree's
  session files and rollouts.
- Copy `$P/records` as `$E/pool/`.
- Write `$E/outputs.sha256`, as the continuation did.
- Call `budget_ok || true` to take the after reading.
- Report: `docs/reports/<date>-eb3-orc-versus-single-call-rung1.md`, with E-B2's sections plus:
  - links to the calibration and continuation reports, with rung 1's post-data qualification stated first;
  - the coordinator's threshold attribution;
  - the model-guard disclosure;
  - the census and sweep counts;
  - per-run node counts beside the calibration spread;
  - the limits below.
- After an independent Opus review of the report, update the README evidence row, the index and the design lessons.
  Nothing is promoted before the validity checks pass.
- Keep `$RT` and the `eb3-runtime-frozen` tag. Delete `$W` only after the evidence manifest verifies, running
  `chmod u+r $P/clones` first.

## Budget

- **Authorized calls:**
  - nine runs;
  - infrastructure resumes;
  - two judges;
  - S2: about three Opus calls (top-level, subagent, nested), one nested Opus call from Codex, and one short Codex
    call; the S2 refusals reach only a stub;
  - at most one recorded rerun of probe a.

  Nothing else.
- **Worst-case wall clock per run:** `design_review_execute` 7 h, `reviewed_change` 9 h, `direct_task` 4 h. E-B2's
  batch took about 3 h.
- **Codex:**
  - Weekly window about 64% used, and credits 28549.41.
  - E-B2's batch and judges moved the account-wide window by at most 27 points.
  - R8 as amended lets designed runs continue on credits. `budget_ok` is stricter than R8: it requires credits and a
    balance of at least 5000.
  - It is checked before the batch, each resume and each judge.

## Halt Without Result

Halt in any of these cases:
- a backport, package or anchor check fails;
- S1 or S2 fails;
- an environment check fails;
- a dry run fails;
- the Fable halt rule has no recorded cause outside the runtime;
- `budget_ok` forbids a launch;
- the upstream anchor is below 1.0 in any batch.

## Limits

- **Rung 1 qualified post-data (R56).** At the calibration control level, DRE's expected headroom is about 0.08. The
  fresh control may differ. `reviewed_change`'s paired headroom is uncalibrated. A one-node threshold is inside the
  single-call spread (range 6, SD 3.2), so a held claim is a directional observation, not significance or a
  population effect.
- **Three runs per arm on one task,** and the reviewer's and the judges' variance is unmeasured.
- **Calibration ran without the guard.** E-B3 runs with it, so nested `claude` calls answer with Opus instead of the
  shared default `claude-fable-5-1`, and in-process subagents are pinned to Opus.
  - The guard covers `PATH` lookups and the subagent environment only.
  - Absolute paths, a reset `PATH` or direct API calls are seen only by scan, census and sweep within their limits.
  - The guard audit found no Fable session attributed to rung 1's calibration runs, within its coverage.
- **Time and model drift between days.** The Claude CLI was not pinned in calibration.
- **Judge self-preference:** `gpt-6-sol` is `reviewed_change`'s reviewer, and `claude-opus-5-5` is DRE's planner.
- **Shared environment:** the stale editable install, shared home and transcripts, and the network are covered by
  detection only.
