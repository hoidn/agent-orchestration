"""The scripted `claude` for offline seed-set runs: it stands in for the candidate agent, the reviewer and the judges
behind the comparison harness's real shims, sandbox and model guard. No provider is called.

It reads its plan from $SEED_SET_STUB_PLAN (a read-only file the sandbox declaration admits):
`{"tasks": {id: {"marker", "patch", "visible", "fix": {model: first fixing attempt or null}}}}`. Every call records
a Claude session row answered by the model it was invoked with (what the scan audits), then writes its result to
the file the prompt's last `- path:` line names:

- a judge (the prompt lists pool clones): one rating per clone in the listed order, S8 for a clone with changes
  and S0 for an unchanged one;
- an implementer (the prompt holds a task's marker): counts its attempt in the tree's ignored `.orchestrate/`
  (which a clone reset keeps); from the plan's first fixing attempt for this model on, applies the reference
  patch in its working directory when it still applies and runs the visible check there (inside the sandbox),
  logging that command as a Bash tool use in its session; reports a `Change`;
- a reviewer (any other prompt): APPROVE when its working tree has changes, else REQUEST_CHANGES.
"""

import sys

STUB = f"""#!{sys.executable} -I
import json, os, re, subprocess, sys
from pathlib import Path
prompt = sys.stdin.read()
model = sys.argv[sys.argv.index("--model") + 1]
plan = json.loads(Path(os.environ["SEED_SET_STUB_PLAN"]).read_text())
slug = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())
session = Path(os.environ["HOME"]) / ".claude" / "projects" / slug / f"{{os.getpid()}}.jsonl"
session.parent.mkdir(parents=True, exist_ok=True)
session.write_text(json.dumps({{"type": "assistant", "message": {{"model": model}}}}) + "\\n")

def changed(repo):
    status = subprocess.run(["git", "-C", repo, "diff", "--quiet", "HEAD"]).returncode
    if status not in (0, 1):
        sys.exit(f"git diff failed in {{repo}}")
    return status == 1

clones = list(dict.fromkeys(re.findall(r"(/[^\\s\\"'\\[\\],]+/clones/[0-9a-f]{{8}})", prompt)))
entry = next((entry for entry in plan["tasks"].values() if entry["marker"] in prompt), None)
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
        print(f"visible check exit {{check.returncode}}")
        with session.open("a") as log:  # the transcript row the self-check detector reads
            log.write(json.dumps({{"type": "assistant", "message": {{"model": model, "content": [{{
                "type": "tool_use", "name": "Bash", "input": {{"command": " ".join(entry["visible"])}}}}]}}}}) + "\\n")
    result = {{"summary": f"attempt {{attempt}}", "account": "applied the reference fix" if fixes else "none"}}
Path(re.findall(r"^- path: (.+)$", prompt, re.M)[-1]).write_text(json.dumps(result))
"""
