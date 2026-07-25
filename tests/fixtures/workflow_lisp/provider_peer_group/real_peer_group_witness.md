You are the witness in a bounded three-member provider group. Treat the
checkout as read-only. Do not inspect, create, edit, or delete repository
files. The only permitted file mutation is the runtime-bound output bundle.

Use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-ready`

Wait for success. Write the direct JSON boolean `true` to the path in
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. One exact way is:

`{{PYTHON}} -c 'import json, os; from pathlib import Path; Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(True), encoding="utf-8")'`

After the bundle exists, use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-finish`

Wait for success, then end the turn naturally with one brief acknowledgement
and invoke no more tools. Do not type the client close command yourself; the
runtime queues its declared natural close. Never use Escape, interruption,
cancellation, resume, steering, directive, `peer-send`, or `peer-ack`.
