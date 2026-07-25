You are the receiver in a bounded three-member provider group. Treat the
checkout as read-only. Do not inspect, create, edit, or delete repository
files. The only permitted file mutation is the runtime-bound output bundle.

For the initial turn, use one shell invocation to become ready and then poll
the rendered synchronization marker:

`{{PYTHON}} -m orchestrator peer-ready && while [ ! -f {{SYNC_MARKER_SHELL}} ]; do sleep 0.05; done`

Keep that one shell tool active until the complete command succeeds. Marker
appearance means the sender's `peer-send` returned success after the runtime
durably offered the queued message. Then end the initial turn naturally with
one brief acknowledgement. Do not write the output bundle and do not call
`peer-ack` or `peer-finish` during the initial turn.

A runtime-framed peer message will arrive as a queued next turn. In that turn,
read the exact values after `message_id:` and after the first blank line. Use
the shell to acknowledge the exact message id:

`{{PYTHON}} -m orchestrator peer-ack <message_id>`

Replace `<message_id>` with the received value and wait for success. Then
write the exact message content, without rewriting it, as a direct JSON string
to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. Use the received content as the final
argument here:

`{{PYTHON}} -c 'import json, os, sys; from pathlib import Path; Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(sys.argv[1], ensure_ascii=False), encoding="utf-8")' '<exact_message_content>'`

After the bundle exists, use the shell to run exactly:

`{{PYTHON}} -m orchestrator peer-finish`

Wait for success, then end the turn naturally with one brief acknowledgement
and invoke no more tools. Do not type the client close command yourself; the
runtime queues its declared natural close. Never use Escape, interruption,
cancellation, resume, steering, or directive commands, and do not send a peer
message.
