You are the receiver in a bounded two-member provider group. Treat the
trusted checkout as read-only. Do not inspect, create, edit, or delete
repository files. The only permitted mutation is the runtime-bound output
bundle.

For the initial turn, use one shell invocation to become ready and then poll
the rendered synchronization marker:

`{{PYTHON}} -m orchestrator peer-ready && while [ ! -f {{SYNC_MARKER_SHELL}} ]; do sleep 0.05; done`

Keep that shell tool active until the complete command succeeds. Marker
appearance means the sender's ordinary `peer-send` command returned success
after the runtime durably offered its message. Then end the initial turn
naturally with one brief acknowledgement. Do not write the output bundle and
do not call `peer-ack` or `peer-finish` during the initial turn.

A runtime-framed message will arrive as the queued next turn. Verify that its
content is exactly the Unicode and newline-bearing value represented by
{{MESSAGE_JSON}}. Read the exact value after `message_id:` and acknowledge it
with:

`{{PYTHON}} -m orchestrator peer-ack <message_id>`

Replace `<message_id>` with the received value and wait for success. Then
write the exact message content as a direct JSON string to
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH` with:

`{{PYTHON}} -c 'import json, os; from pathlib import Path; Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({{MESSAGE_JSON}}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")'`

After the bundle exists, use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-finish`

Wait for success, then end the turn naturally with one brief acknowledgement
and invoke no more tools. Do not send a peer message or type the client close
command yourself; the runtime queues its declared natural close. Never use
Escape, interruption, cancellation, resume, steering, or directive commands.
