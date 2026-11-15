"""Compile (and optionally run) small probe programs through the public CLI; print one row per probe.

    PYTHONPATH=$PWD python experiments/authoring_revisions/probe.py <spec.py> <workdir> [name-prefix]

Run from the repository root with `experiments/thread_m/no_provider` first on `PATH`; <workdir> is a scratch
directory outside the repository. The spec defines PROBES = [(name, returns, body, extra_defs, run_inputs|None)]. Each probe becomes
<workdir>/<name>.orc at target 2.40 with one entry `run ((n Int) (model String) (t Int))`. Commands are the
stand-in `emit.py` (writes its JSON argument as the result, logs the call). No provider is called: a probe
that names a provider is compiled only.
"""
import json, re, runpy, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule {name})
  (export run)
  (defrecord Pair (a Int) (b List[String]))
  (defrecord Role (model String) (effort String))
  (defunion Verdict (MET (evidence List[String])) (NOT_MET (reasons List[String])))
  (defpath DocPath :kind relpath :under "docs" :must-exist true)
  (defprompt ask (:fills (q :text)) -> Pair "Answer {{q}}.")
{extra}
  (defworkflow run ((n Int) (model String) (t Int)) -> {returns}
    {body}))
'''
EMIT = '''import json, os, sys
from pathlib import Path
with open("calls.log", "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(sys.argv[1])
'''


def E(value, returns="Int"):
    return f"(command-result emit :argv (\"python\" \"emit.py\" {json.dumps(json.dumps(value))}) :returns {returns})"


def cli(work, *args):
    return subprocess.run([sys.executable, "-m", "orchestrator", *args], cwd=work, capture_output=True, text=True)


def one(work, name, returns, body, extra="", run_inputs=None):
    (work / f"{name}.orc").write_text(PRE.format(name=name, returns=returns, body=body, extra=extra))
    flags = ["--provider-externs-file", "providers.json", "--command-boundaries-file", "commands.json"]
    done = cli(work, "compile", f"{name}.orc", *flags)
    out = done.stdout + done.stderr
    found = re.search(r"\[([a-z_0-9]+)\] (.*)", out)
    if done.returncode == 0:
        row = [name, "accepted", "", ""]
    else:
        row = [name, "REFUSED", found.group(1) if found else "?", (found.group(2) if found else out.strip()[-400:])[:200]]
    if done.returncode == 0 and run_inputs is not None:
        (work / "calls.log").unlink(missing_ok=True)
        ran = cli(work, "run", f"{name}.orc", "--quiet", *flags, *[a for kv in run_inputs for a in ("--input", kv)])
        calls = (work / "calls.log").read_text().splitlines() if (work / "calls.log").exists() else []
        tail = "" if ran.returncode == 0 else " err=" + (ran.stdout + ran.stderr).strip()[-300:].replace("\n", " / ")
        row.append(f"exit={ran.returncode} out={ran.stdout.strip()[-160:]} calls={len(calls)}:{calls[-3:]}{tail}")
    return row


def main():
    spec, work = runpy.run_path(sys.argv[1], init_globals={"E": E}), Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    (work / "emit.py").write_text(EMIT)
    (work / "commands.json").write_text(json.dumps({"emit": {"stable_command": ["python", "emit.py"], "closure": ["emit.py"]}}))
    (work / "providers.json").write_text(json.dumps({"providers.a": "claude_unrestricted_workspace", "providers.b": "claude_unrestricted_workspace"}))
    for probe in spec["PROBES"]:
        if probe[0].startswith(sys.argv[3] if len(sys.argv) > 3 else ""):
            print(" | ".join(one(work, *probe)))
    shutil.rmtree(work / ".orchestrate", ignore_errors=True)


main()
