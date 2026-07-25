You are the sender in a bounded two-member provider group. Treat the trusted
checkout as read-only. Do not inspect, create, edit, or delete repository
files. The only permitted mutations are the runtime-bound output bundle and
the rendered synchronization marker, both outside the checkout.

Use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-ready`

Wait for success. Then use one shell invocation to send the exact test
message and create the synchronization marker only after `peer-send`
succeeds:

`{{PYTHON}} -m orchestrator peer-send receiver {{MESSAGE_SHELL}} && touch {{SYNC_MARKER_SHELL}}`

Wait for the combined command to succeed. Write the direct JSON string
{{SENDER_VALUE_JSON}} to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` with:

`{{PYTHON}} -c 'import json, os; from pathlib import Path; Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({{SENDER_VALUE_JSON}}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")'`

After the bundle exists, use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-finish`

Wait for success, then end the turn naturally with one brief acknowledgement
and invoke no more tools. Do not acknowledge a peer message or type the
client close command yourself; the runtime queues its declared natural close.
Never use Escape, interruption, cancellation, resume, steering, or directive
commands.
