This is a bounded turn-boundary delivery check launched from a trusted
checkout. Treat the checkout as strictly read-only: do not inspect, create,
edit, or delete any repository file. The only permitted file mutation is the
explicit output-bundle path supplied through
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, which is outside the checkout.

For the initial turn, use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-ready`

Wait for that command to succeed. Then end the initial turn naturally with
one brief acknowledgement. Do not write the output bundle and do not call
`peer-ack` or `peer-finish` during the initial turn.

A runtime-framed message will arrive as a queued next turn. In that queued
turn, read the exact value after `message_id:` and use the shell to run:

`{{PYTHON}} -m orchestrator peer-ack <message_id>`

Replace `<message_id>` with the exact received value and wait for success.
Then write the direct JSON string value {{EXPECTED_VALUE_JSON}} to the path
in `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. One exact way to do that is:

`{{PYTHON}} -c 'import json, os; from pathlib import Path; Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({{EXPECTED_VALUE_JSON}}), encoding="utf-8")'`

After the bundle exists, use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-finish`

Wait for that command to succeed, then end the turn naturally with one brief
acknowledgement and invoke no more tools. Do not type the client close
command yourself; the runtime queues its declared natural close. Never use
Escape, interruption, cancellation, a resume command, a directive, or
`peer-send`.
