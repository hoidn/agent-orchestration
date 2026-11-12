# Tutorial: Your First Pipeline

**Status: current guide.** You build one small pipeline from an empty
directory with the installed `orchestrator` command: wrap a shell script as a
step, run it, read a failure, fix it and continue the same run. No model is
called. Every output below was produced by running the commands shown; your
run ids and paths will differ.

## Install and start

You need Python 3.11 or later and a POSIX shell.

```bash
git clone https://github.com/hoidn/agent-orchestration.git
python3 -m venv orc-env && . orc-env/bin/activate
pip install ./agent-orchestration
mkdir first-pipeline && cd first-pipeline
```

Every command below runs in `first-pipeline`.

## A script, and the commands that wrap it

The pipeline grows a text file until it has a target number of words. Start
from a script you might already have:

<!-- file: count_words.sh -->
```sh
#!/bin/sh
# Prints the number of words in a file.
wc -w < "$1"
```

A **workflow** is a typed program made of **steps**. A **command** is a
step that runs a program in this directory: it hands its result to the
workflow by writing it as JSON to the file named in the environment variable
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. This wrapper runs any script, passes its
error output on, and hands over the number the script printed:

<!-- file: as_command.py -->
```python
"""Run a script and give its output, a number, to the workflow."""
import json, os, subprocess, sys
from pathlib import Path

done = subprocess.run(sys.argv[1:], capture_output=True, text=True)
sys.stderr.write(done.stderr)
if done.returncode != 0:
    sys.exit(done.returncode)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(done.stdout)))
```

The second command appends the text of `filler.txt` to the file and returns
how many times it has padded:

<!-- file: pad.py -->
```python
"""Append the text of filler.txt to a file; give the workflow the new number of pads."""
import json, os, sys
from pathlib import Path

filler = open("filler.txt").read()
with open(sys.argv[1], "a") as f:
    f.write(" " + filler)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(sys.argv[2]) + 1))
```

The command manifest, `commands.json`, names each command. `stable_command`
is the fixed start of its command line; the workflow may add arguments after
it. `closure` lists the files the command's behavior depends on: a run
records their contents, so it can tell later whether a script changed. Data
files such as the text being grown are not part of it.

<!-- file: commands.json -->
```json
{
  "count": {"stable_command": ["python", "as_command.py"], "closure": ["as_command.py", "count_words.sh"]},
  "pad": {"stable_command": ["python", "pad.py"], "closure": ["pad.py"]}
}
```

## The workflow

<!-- file: grow.orc -->
```lisp
(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule grow)
  (export run)
  (defrecord Outcome (reached Bool) (pads Int))
  (defworkflow run ((file String) (target Int)) -> Outcome
    (loop/recur :max 5 :state 0
      :on-exhausted (record Outcome :reached false :pads pads)
      (fn (pads)
        (let* ((words (command-result count
                        :argv ("python" "as_command.py" "sh" "count_words.sh" file) :returns Int)))
          (if (>= words target)
            (done (record Outcome :reached true :pads pads))
            (let* ((padded (command-result pad :argv ("python" "pad.py" file pads) :returns Int)))
              (continue padded))))))))
```

`run` takes two typed inputs and returns an `Outcome` record. `loop/recur`
runs its function at most `:max` times. The function receives the loop's
state, here `pads`, the number of pads so far, which starts at `:state`. Each round runs the `count` command, then
either stops with `done` or runs `pad` and starts the next round with
`continue`. If five rounds pass without `done`, the loop's value is
`:on-exhausted`, which can use the last state. `:returns` gives the type the
command's JSON must have.

## Compile

<!-- run -->
```console
$ orchestrator compile grow.orc
using commands.json beside grow.orc
{
  "artifact_paths": {
    "closed_program": "/home/you/first-pipeline/.orchestrate/build/06ba4f273d09d95c/closed_program.json"
  },
  "build_key": "06ba4f273d09d95c",
  "build_root": "/home/you/first-pipeline/.orchestrate/build/06ba4f273d09d95c",
  "entry_workflow": "grow::run",
  "program_digest": "sha256:4a0843feb3d2f7b4b542d1d259176f8f14d727897afdf3974d07976156bd315a",
  "sites": 2
}
```

`compile` checks the program; `sites` counts the places that run a step.
It found `commands.json` because the file sits beside `grow.orc`
(`--command-boundaries-file` names another one). `run` compiles too, so this
step is optional.

## Run it, and read a failure

<!-- file: notes.txt -->
```text
one two three
```

<!-- run: exit 1 -->
```console
$ orchestrator run grow.orc --input file=notes.txt --input target=5
using commands.json beside grow.orc
run     20261112T060138Z-bq9zwh  /home/you/first-pipeline/.orchestrate/runs/20261112T060138Z-bq9zwh
start   workflow:grow::run / loop:pads[1] / words  attempt 1
commit  workflow:grow::run / loop:pads[1] / words  attempt 1
start   workflow:grow::run / loop:pads[1] / else / padded  attempt 1
failed  workflow:grow::run / loop:pads[1] / else / padded  attempt 1  [command_exit_nonzero]
        stderr: /home/you/first-pipeline/.orchestrate/runs/20261112T060138Z-bq9zwh/effects/916a1013837e190c3975e6c21d5f0d0af43ec4d55213789a8060cdbaa725a650/attempt-1/stderr.txt
        | Traceback (most recent call last):
        |   File "/home/you/first-pipeline/pad.py", line 5, in <module>
        |     filler = open("filler.txt").read()
        |              ~~~~^^^^^^^^^^^^^^
        | FileNotFoundError: [Errno 2] No such file or directory: 'filler.txt'
[command_exit_nonzero] evaluated command failed with exit code 1
resume  orchestrator resume 20261112T060138Z-bq9zwh
```

A **run** is one execution, recorded under `.orchestrate/runs/<run id>`. The
first line gives its id and directory. Each step has an **identity**, its
place in the program: the workflow, the loop round, the branch and the name
it is bound to. `start` and `commit` lines show its **attempts**; a committed
step's result is recorded, and the run never runs it again. Here the count of
round 1 committed and the pad failed. The `failed` block names the error code,
the file that holds the step's error output and its last lines: `filler.txt`
does not exist. The `resume` line is the command that continues this run;
the command exits 1.

## Fix the cause and resume

<!-- file: filler.txt -->
```text
more
```

<!-- run: printed -->
```console
$ orchestrator resume <run id>
run     20261112T060138Z-bq9zwh  /home/you/first-pipeline/.orchestrate/runs/20261112T060138Z-bq9zwh
start   workflow:grow::run / loop:pads[1] / else / padded  attempt 2
[effect_rerun] workflow:grow::run / loop:pads[1] / else / padded attempts=[1]
commit  workflow:grow::run / loop:pads[1] / else / padded  attempt 2
start   workflow:grow::run / loop:pads[2] / words  attempt 1
commit  workflow:grow::run / loop:pads[2] / words  attempt 1
start   workflow:grow::run / loop:pads[2] / else / padded  attempt 1
commit  workflow:grow::run / loop:pads[2] / else / padded  attempt 1
start   workflow:grow::run / loop:pads[3] / words  attempt 1
commit  workflow:grow::run / loop:pads[3] / words  attempt 1
{"pads":2,"reached":true}
```

The `[effect_rerun]` line notes that the failed step runs again. The committed count of
round 1 did not run again; the pad ran as attempt 2. The last line, on
standard output, is the result as JSON, and the command exits 0.

## Look at a finished run

<!-- run -->
```console
$ orchestrator report | head -n 9
# Workflow Status

## Run
- run_id: `20261112T060138Z-bq9zwh`
- status: `completed`
- workflow_file: `grow.orc`
- started_at: `2026-11-12T06:01:38.710578+00:00`
- updated_at: `2026-11-12T06:01:39.455474+00:00`
- memo_offset: `12760`
```

`report` shows the latest run (`--run-id` picks another). After these lines
come its inputs, its outputs and, under "Steps", each step with its attempt
and result.

## When the loop runs out

<!-- run -->
```console
$ orchestrator run grow.orc --input file=notes.txt --input target=100 --quiet
{"pads":5,"reached":false}
```

The target is never reached in five rounds, so the run returns the
`:on-exhausted` value. `--quiet` prints only the result (and, on a failure,
the failure and the `resume` line).

## Change a script after its step committed

`notes.txt` now has line breaks, because `filler.txt` ends with one. Fix
`pad.py` so it strips them:

<!-- file: pad.py -->
```python
"""Append the text of filler.txt to a file; give the workflow the new number of pads."""
import json, os, sys
from pathlib import Path

filler = open("filler.txt").read().strip()
with open(sys.argv[1], "a") as f:
    f.write(" " + filler)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(sys.argv[2]) + 1))
```

Resuming the first run now refuses, because a committed step used the old
`pad.py`; it exits 2 and changes nothing. The first line is the error code
with its details; the lines after it say what to do:

<!-- run: exit 2 -->
```console
$ orchestrator resume <run id>
[effect_input_diverged] workflow:grow::run / loop:pads[1] / else / padded: effect input diverged (input parts changed: ['implementation_files']; dependency identities changed: False; previous sha256:944b4a0ab4faac62789e027c4eda240c5c64d41b90edd275c859800efffb7c90, current sha256:8daa183fb6611eba7aab5312f3e4dcc68e79c0ad87bc2aac245636e52fee662c)
step workflow:grow::run / loop:pads[1] / else / padded was committed with other inputs; changed: implementation_files; files: pad.py
to run this step and every later one again (workspace files are not rolled back):
    orchestrator invalidate 20261112T060138Z-bq9zwh 'workflow:grow::run / loop:pads[1] / else / padded'
    orchestrator resume 20261112T060138Z-bq9zwh
```

**Invalidate** tells the run to forget a committed step, so `resume` runs it
and every later step again:

<!-- run: printed -->
```console
$ orchestrator invalidate <run id> 'workflow:grow::run / loop:pads[1] / else / padded'
{"from_commit": 4618, "record": "invalidated", "time": 1794463301.6015902}
$ orchestrator resume <run id>
run     20261112T060138Z-bq9zwh  /home/you/first-pipeline/.orchestrate/runs/20261112T060138Z-bq9zwh
start   workflow:grow::run / loop:pads[1] / else / padded  attempt 3
commit  workflow:grow::run / loop:pads[1] / else / padded  attempt 3
start   workflow:grow::run / loop:pads[2] / words  attempt 2
commit  workflow:grow::run / loop:pads[2] / words  attempt 2
{"pads":1,"reached":true}
```

The loop stopped after one pad: `notes.txt` still holds every word the earlier
runs added.

## Two limits

- If a step fails because of a bug in its own script, fix the script and
  run the printed `resume` command: the failed step runs again with the
  fixed script. A step that was killed, or that changed its own script
  before it failed, is not retried with changed files until you add
  `--accept-changes` to the `resume` command, which the refusal prints.
- `invalidate` runs the step and every later one again, and does not roll
  back files in the workspace: what the earlier attempts wrote stays.

## A step that calls a model

Not part of the pipeline above: this needs a provider command line tool (here
`claude`) installed and signed in, and it spends model calls. A provider step
names a provider, a prompt and the result type; the runtime tells the model
where and in what shape to write the result.

```lisp
(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule summary)
  (export run)
  (defrecord Summary (title String) (sentences Int))
  (defworkflow run ((text String)) -> Summary
    (provider-result providers.writer :prompt prompts.summarize
      :inputs (text) :model "claude-haiku-5-5" :effort "low" :returns Summary)))
```

Save it as `summary.orc` in a new directory, with `providers.json` holding
`{"providers.writer": "claude_unrestricted_workspace"}` (a profile that runs
`claude -p` in that directory without permission prompts), `prompts.json`
holding `{"prompts.summarize": "summarize.md"}`, and the prompt in
`summarize.md`. Run it with
`orchestrator run summary.orc --input text="One. Two."`.

## Next

- [Workflow Lisp drafting guide](lisp_workflow_drafting_guide.md): the
  language, types, procedures and provider steps in full.
- [Edit a prompt and continue](runtime_execution_lifecycle.md#edit-a-prompt-and-continue):
  change a provider step's prompt in the middle of a run.
- [Typed Python workflows](python_workflow_drafting_guide.md): write the
  same kind of workflow in Python.
- [CLI contract](../specs/cli.md): every command, flag and printed line.
