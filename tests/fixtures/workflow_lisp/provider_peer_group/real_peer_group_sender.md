You are the sender in a bounded three-member provider group. Treat the
checkout as read-only. Do not inspect, create, edit, or delete repository
files. The only permitted file mutations are the runtime-bound output bundle
and the rendered synchronization marker, both outside the checkout.

Use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-ready`

Wait for success. Then use one shell invocation to send the exact test message
and create the synchronization marker only after `peer-send` succeeds:

`{{PYTHON}} -m orchestrator peer-send receiver {{MESSAGE_SHELL}} && touch {{SYNC_MARKER_SHELL}}`

Wait for the combined command to succeed. Write the direct JSON string
`"sender-complete"` to the path in `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. One
exact way is:

`{{PYTHON}} -c 'import json, os; from pathlib import Path; Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("sender-complete"), encoding="utf-8")'`

After the bundle exists, use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-finish`

Wait for success, then end the turn naturally with one brief acknowledgement
and invoke no more tools. Do not type the client close command yourself; the
runtime queues its declared natural close. Never use Escape, interruption,
cancellation, resume, steering, or directive commands.
