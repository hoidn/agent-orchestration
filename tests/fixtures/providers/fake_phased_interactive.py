"""Local Codex-shaped terminal stand-in; submissions use the public private client."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def event(kind, **fields):
    descriptor = os.open("phased-events.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, (json.dumps({"event": kind, "pid": os.getpid(), **fields}) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


prompt = sys.argv[-1]
frame = json.loads(prompt.splitlines()[0])
assert frame["protocol_schema_version"] == "provider_phased_protocol_frame.v1"
assert frame["phase"] == "task"
bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
mode = os.environ.get("ORC_FAKE_PHASED_MODE", "success")
event("start", argv=sys.argv[1:-1], bundle=str(bundle))
event("task", frame=frame, digest=hashlib.sha256(prompt.encode()).hexdigest())
turns = 0
for line in sys.stdin:
    if line.strip() == "/exit":
        event("natural_exit", returncode=0)
        raise SystemExit(0)
    try:
        frame = json.loads(line)
    except ValueError:
        continue
    if not isinstance(frame, dict) or frame.get("phase") not in {"initial_materialization", "retry_materialization"}:
        continue
    turns += 1
    assert frame["protocol_schema_version"] == "provider_phased_protocol_frame.v1"
    assert frame["submission_ordinal"] == turns
    assert frame["phase"] == ("initial_materialization" if turns == 1 else "retry_materialization")
    output = Path("outputs/report.md")
    assert not output.exists() and not bundle.exists(), "every correction must recreate the complete candidate"
    event("turn", phase=frame["phase"], ordinal=turns, diagnostics=frame.get("diagnostics", []), candidates_absent=True)
    bad = mode == "always-invalid" or turns == 1 and mode.endswith("-once")
    missing_output = bad and mode in {"missing-output-once", "both-invalid-once", "always-invalid"}
    bad_result = bad and mode in {"bad-result-once", "both-invalid-once", "always-invalid"}
    if not missing_output:
        output.write_bytes("salida ñ\r\n".encode())
    bundle.write_text(json.dumps({"approved": "invalid" if bad_result else True}) + "\n")
    event("candidates", ordinal=turns, output=output.exists(), result=True)
    if os.environ.get("ORC_FAKE_HOLD_BEFORE_SUBMIT"):
        signal.pause()
    event("submit_request", ordinal=turns)
    result = subprocess.run([sys.executable, "-m", "orchestrator", "provider-materialization-submit"],
        capture_output=True, text=True, timeout=65, check=False)
    assert result.stdout, result.stderr
    receipt = json.loads(result.stdout)
    event("submit", receipt=receipt, returncode=result.returncode)
    assert receipt["submission_ordinal"] == turns
    if receipt["status"] == "failed":
        assert result.returncode == 2
        raise SystemExit(2)
    assert result.returncode == 0
raise AssertionError("provider stdin closed without graceful close")
