import json, os, sys, time
from pathlib import Path
prompt = sys.stdin.buffer.read()
with Path("requests.jsonl").open("a", encoding="utf-8") as out:
    out.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(),
        "prompt": prompt.decode("utf-8"), "env": {key: os.environ.get(key)
        for key in ("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY")}}) + "\n")
mode = os.environ.get("PROVIDER_SHIM_MODE", "success")
if mode != "empty":
    sys.stdout.buffer.write(b"complete stdout\n"); sys.stdout.buffer.flush()
    sys.stderr.buffer.write(b"complete stderr\n"); sys.stderr.buffer.flush()
if mode == "timeout": time.sleep(10)
if mode == "nonzero": sys.exit(9)
result = os.environ.get("PROVIDER_SHIM_RESULT", '{"ok":true,"extra":7}').encode()
if "PROVIDER_SHIM_RESULTS" in os.environ:
    index = len(Path("requests.jsonl").read_text().splitlines()) - 1
    result = json.loads(os.environ["PROVIDER_SHIM_RESULTS"])[index].encode()
if mode == "stdout-only": sys.stdout.buffer.write(result); sys.exit(0)
target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
if mode == "wrong-path": target = Path("other-result.json")
if mode == "invalid": result = b'{"ok":"not-bool"}'
if mode == "chdir":
    os.makedirs("candidates/alpha", exist_ok=True); os.chdir("candidates/alpha")
    target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(result)
