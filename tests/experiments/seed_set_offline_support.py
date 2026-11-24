"""The scripted `claude` for offline seed-set runs: it stands in for the candidate agent, the reviewer and the judges
behind the comparison harness's real shims, sandbox and model guard. No provider is called.

It reads its plan from $SEED_SET_STUB_PLAN (a read-only file the sandbox declaration admits):
`{"tasks": {id: {"marker", "patch", "visible", "fix": {model: first fixing attempt or null}}}, "usage_limit": {...}}`.
`--version` prints `VERSION`. Every call records a Claude session row answered by the model it was invoked with (what
the scan audits), prints stream-json lines as the metered template's CLI does (its result event reports `USAGE`
and `REPORTED_USD`), then writes its result to the file the prompt's last `- path:` line names:

- a judge (the prompt lists pool clones): one rating per clone in the listed order, S8 for a clone with changes
  and S0 for an unchanged one;
- an implementer (the prompt holds a task's marker): counts its attempt in the tree's ignored `.orchestrate/`
  (which a clone reset keeps); from the plan's first fixing attempt for this model on, applies the reference
  patch in its working directory when it still applies and runs the visible check there (inside the sandbox),
  logging that command as a Bash tool use in its session; reports a `Change`;
- a reviewer (any other prompt): APPROVE when its working tree has changes, else REQUEST_CHANGES.

With `"usage_limit": {"task": id, "model": m, "reset": epoch}` (an implementer call on that task by that model) or
`{"judge": m, "reset": epoch}` (a judge call by that model), the call answers as the vendor does at a usage limit
(the shape of experiments/long_horizon_tasks/fixtures/token-usage-limit-NonZeroAgentExitCodeError.json: a rejected
`rate_limit_event`, a `<synthetic>` session row, a result event with `api_error: usage_limit_reached`) and exits 1.
A test lifts the limit by rewriting the plan in place (the sandbox binds the same file). With
`"paid_usage": {"judge": m}` a judge call by that model first prints the CLI's paid-extra-usage `rate_limit_event`
(experiments/long_horizon_tasks/fixtures/token-paid-extra-usage-normal-end.json), then answers normally. With
`"auth_error": {"task": id, "model": m}` that implementer call ends as a login that expired mid-run does (an error
result naming the OAuth failure, status 401) and exits 1. With
`"sleep": seconds`
every call waits that long before it answers. With `"stderr_warning": text` every call that succeeds also prints
`text` on stderr (a CLI warning beside a successful call). With `"conftest_sleep": {"seconds": N, "pids": dir}` an
implementer call appends to the `conftest.py` of its tree code that, whenever pytest loads it in a host-side check
(its HOME is the check's `seed-set-host-*` box), records its pid as a file in `dir` and sleeps N seconds; optional
`"task"` and `"model"` keys limit it to that task's calls by that model, and `"node"` to a pytest run whose command
line names that node (one hidden test that hangs, fix round 3).
"""

import sys

VERSION = "2.1.311-stand-in (Claude Code)"
# Each call's metered usage (the result event's modelUsage) and the cost the CLI reports: below the table's price,
# so the guard's figure is the table's (Haiku USD 0.0036 a call, Sonnet USD 0.067).
USAGE = {"inputTokens": 1000, "outputTokens": 2000, "cacheReadInputTokens": 50000, "cacheCreationInputTokens": 10000}
REPORTED_USD = 0.001
# criterion.json's spend terms for tests (rulings R4, R5; review3 X3: the largest ordinary-rate call each per-call
# worst case must cover at the table's highest tier); a test that launches the stand-in names its own CLI pin
SPEND_TERMS = {"ceiling_usd": {"smoke": 20.0, "redraw": 40.0, "calibration": 100.0},
               "per_call_usd": {"claude-haiku-5-5": 0.25, "claude-sonnet-5-5": 1.0},
               "largest_call_usd": {"claude-haiku-5-5": 0.01, "claude-sonnet-5-5": 0.1},
               "cli": {"path": "/stand-in/bin/claude", "version": VERSION}}


def stand_in_login(config, expires_in_sec=30 * 86400):
    """A hand-made login file in the Claude config directory `config`: an expiry (`claudeAiOauth.expiresAt`, epoch
    milliseconds) `expires_in_sec` from now and stand-in token values, never a real token."""
    import json
    import time
    from pathlib import Path
    path = Path(config) / ".credentials.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"claudeAiOauth": {"accessToken": "stand-in-access", "refreshToken": "stand-in-refresh",
                                                  "expiresAt": int((time.time() + expires_in_sec) * 1000)}}))
    return path


def stand_in_terms(fakebin, **change):
    """SPEND_TERMS pinned to the stand-in `claude` in `fakebin` (the path the sandbox declaration resolves)."""
    from pathlib import Path
    return {**SPEND_TERMS, "cli": {"path": str(Path(fakebin, "claude").resolve()), "version": VERSION}, **change}

STUB = f"""#!{sys.executable} -I
import json, os, re, subprocess, sys, time
from pathlib import Path
if sys.argv[1:] == ["--version"]:
    print({VERSION!r})
    sys.exit(0)
prompt = sys.stdin.read()
model = sys.argv[sys.argv.index("--model") + 1]
plan = json.loads(Path(os.environ["SEED_SET_STUB_PLAN"]).read_text())
slug = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())
session = Path(os.environ["HOME"]) / ".claude" / "projects" / slug / f"{{os.getpid()}}.jsonl"
session.parent.mkdir(parents=True, exist_ok=True)
session.write_text(json.dumps({{"type": "assistant", "message": {{"model": model}}}}) + "\\n")
if os.environ.get("SEED_SET_WITHHELD"):  # the sandbox clears it: an agent must never see the withheld tests' path
    with session.open("a") as log:
        log.write(json.dumps({{"type": "assistant", "message": {{"model": model, "withheld_seen": True}}}}) + "\\n")

def emit(event):
    print(json.dumps(event), flush=True)

def ended(**result):
    emit({{"type": "result", "subtype": "success", "is_error": False, "result": "done",
           "total_cost_usd": {REPORTED_USD!r}, "modelUsage": {{model: {USAGE!r}}}, **result}})

def usage_limited(limit):
    emit({{"type": "rate_limit_event", "rate_limit_info": {{"status": "rejected", "resetsAt": limit["reset"],
           "rateLimitType": "five_hour", "isUsingOverage": False}}}})
    with session.open("a") as log:
        log.write(json.dumps({{"type": "assistant", "message": {{"model": "<synthetic>", "content": [
            {{"type": "text", "text": "You've hit your session limit"}}]}}}}) + "\\n")
    ended(is_error=True, api_error_status=429, api_error="usage_limit_reached", result="You've hit your session limit")
    sys.exit(1)

def changed(repo):
    status = subprocess.run(["git", "-C", repo, "diff", "--quiet", "HEAD"]).returncode
    if status not in (0, 1):
        sys.exit(f"git diff failed in {{repo}}")
    return status == 1

clones = list(dict.fromkeys(re.findall(r"(/[^\\s\\"'\\[\\],]+/clones/[0-9a-f]{{8}})", prompt)))
key, entry = next(((key, entry) for key, entry in plan["tasks"].items() if entry["marker"] in prompt), (None, None))
limit = plan.get("usage_limit") or {{}}
if (clones and limit.get("judge") == model) or (key is not None and (limit.get("task"), limit.get("model")) == (
        key, model)):
    usage_limited(limit)
auth = plan.get("auth_error") or {{}}
if key is not None and (auth.get("task"), auth.get("model")) == (key, model):
    ended(is_error=True, api_error_status=401,
          result="Failed to authenticate: OAuth session expired and could not be refreshed")
    sys.exit(1)
if clones and (plan.get("paid_usage") or {{}}).get("judge") == model:
    emit({{"type": "rate_limit_event", "rate_limit_info": {{"status": "rejected", "rateLimitType": "five_hour",
           "overageStatus": "allowed", "isUsingOverage": True, "overageInUse": True}}}})
time.sleep(plan.get("sleep", 0))  # a call that is still running when a test kills its launcher
slow = plan.get("conftest_sleep")
if slow and entry is not None and (slow.get("task", key), slow.get("model", model)) == (key, model):
    with open("conftest.py", "a") as conftest:  # candidate code that sleeps in a host-side check (re-review N2)
        conftest.write("\\nimport os, sys, time\\nif 'seed-set-host-' in os.environ.get('HOME', '') and "
                       "%r in ' '.join(sys.argv):\\n    open(os.path.join(%r, str(os.getpid())), 'w').close()\\n"
                       "    time.sleep(%d)\\n" % (slow.get("node", ""), slow["pids"], slow["seconds"]))
if clones:
    result = [{{"clone": c, "quality": "S8" if changed(c) else "S0", "reason": "scripted"}} for c in clones]
elif entry is None:
    result = ({{"variant": "APPROVE", "notes": []}} if changed(".")
              else {{"variant": "REQUEST_CHANGES", "findings": ["nothing is implemented"]}})
else:
    counter = Path(".orchestrate/stub-attempts")
    attempt = (int(counter.read_text()) if counter.exists() else 0) + 1
    counter.write_text(str(attempt))
    first = entry["fix"][model]
    fixes = first is not None and attempt >= first and subprocess.run(
        ["git", "apply", "--check", "-"], input=entry["patch"], text=True, capture_output=True).returncode == 0
    if fixes:
        subprocess.run(["git", "apply", "--binary", "-"], input=entry["patch"], text=True, check=True)
        check = subprocess.run(entry["visible"], capture_output=True, text=True)
        emit({{"type": "system", "subtype": "stand-in", "text": f"visible check exit {{check.returncode}}"}})
        with session.open("a") as log:  # the transcript row the self-check detector reads
            log.write(json.dumps({{"type": "assistant", "message": {{"model": model, "content": [{{
                "type": "tool_use", "name": "Bash", "input": {{"command": " ".join(entry["visible"])}}}}]}}}}) + "\\n")
    result = {{"summary": f"attempt {{attempt}}", "account": "applied the reference fix" if fixes else "none"}}
Path(re.findall(r"^- path: (.+)$", prompt, re.M)[-1]).write_text(json.dumps(result))
if plan.get("stderr_warning"):
    print(plan["stderr_warning"], file=sys.stderr, flush=True)
ended()
"""


def hanging_harness(root, pids):
    """A checkout at `root` (for `host.ROOT`) whose `experiments.compare.summarize` records its pid as a file in
    `pids` and hangs: a summary harness that itself hangs (fix round 3). Returns `root`."""
    from pathlib import Path
    package = Path(root) / "experiments" / "compare"
    package.mkdir(parents=True)
    for init in (package.parent / "__init__.py", package / "__init__.py"):
        init.write_text("")
    (package / "summarize.py").write_text(
        f"import os, time\nopen(os.path.join({str(pids)!r}, str(os.getpid())), 'w').close()\ntime.sleep(300)\n")
    return Path(root)


def manifest_rows(sizes, smoke=True):
    """tasks.jsonl rows in the builder's format for a synthetic ladder: `sizes` maps tier to its number of tasks.
    T1 to T4 rows carry a check-withheld twin (`withheld_id` `<tier>w-<k>`), T5 rows are withheld only, T0 rows are
    variants of the T1 rows (the same commits), the first four of each tier are probe tasks, and an extra T2 row
    is the smoke task."""
    rows = []
    for tier, count in sizes.items():
        for k in range(count):
            commit = f"{'T1' if tier == 'T0' else tier}{k:02d}".ljust(40, "0")
            rows.append({"id": f"{tier}-{k:02d}", "tier": tier, "form": "withheld" if tier == "T5" else "in_tree",
                         "withheld_id": f"{tier}w-{k:02d}" if tier in ("T1", "T2", "T3", "T4") else None,
                         "probe": k < 4, "set": "ladder", "commit": commit})
    if smoke:
        rows.append({"id": "smoke", "tier": "T2", "form": "in_tree", "withheld_id": "smoke-withheld", "probe": False,
                     "set": "smoke", "commit": "s" * 40})
    return rows


def committed_runtime(root, rows):
    """A runtime git checkout at `root` holding this checkout's programs and rubric and the task list `rows` at
    experiments/seed_set/tasks.jsonl, committed: what the freeze reads. Returns the task list's path."""
    import json
    import shutil
    import subprocess
    from pathlib import Path

    from experiments.seed_set import layout, rules
    checkout = Path(__file__).resolve().parents[2]
    shutil.copytree(checkout / layout.PROGRAMS, root / layout.PROGRAMS, ignore=shutil.ignore_patterns("__pycache__"))
    (root / rules.RUBRIC_FILE).parent.mkdir(parents=True)
    (root / rules.RUBRIC_FILE).write_bytes((checkout / rules.RUBRIC_FILE).read_bytes())
    (root / rules.PRICE_TABLE).parent.mkdir(parents=True)
    (root / rules.PRICE_TABLE).write_bytes((checkout / rules.PRICE_TABLE).read_bytes())
    tasks = root / "experiments" / "seed_set" / "tasks.jsonl"
    tasks.write_text("".join(json.dumps(row) + "\n" for row in rows))
    stable_anchors(tasks, root=root)
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "rt"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return tasks


def write_frozen_criterion(study, **extra):
    """criterion.json beside the judge criterion, naming the sha256 values the freeze requires (plan Step 1f) and,
    unless `extra` names others, the test spend terms."""
    import json

    from experiments.seed_set import rules
    study.frozen.write_text(json.dumps({"sha256": rules.required_hashes(study), "spend": SPEND_TERMS, **extra}))


def stable_anchors(tasks, unstable=(), scoring_path="current", root=None):
    """anchor_stability.json beside `tasks` (a task list): a stable entry at the current hash for every package the
    study can use, except the `unstable` ids, measured under `scoring_path` ("current": the scoring path of the files
    under `root`, this checkout by default; None: an entry without the field)."""
    import json

    from experiments.seed_set import anchors, build_tasks
    rows = [json.loads(line) for line in tasks.read_text().splitlines()]
    path = {"current": {"scoring_path": anchors.scoring_path_hash(root or build_tasks.ROOT)}, None: {}}.get(
        scoring_path, {"scoring_path": scoring_path})
    entries = {pid: {"sha256": build_tasks.package_hash(tasks.parent / "tasks" / pid), "stable": pid not in unstable,
                     **path} for pid in anchors.packages(rows)}
    (tasks.parent / anchors.FILE).write_text(json.dumps(entries))
