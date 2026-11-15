"""dev-check command boundary: run the task's agent-visible checks, write a CheckReport.

Reads ``dev-check.json`` (``{"argv": [...], "timeout_sec": N}``) from the
working directory, runs ``argv`` there with that timeout, and writes
``{"passed": bool, "failing": [str], "excerpt": str}`` (excerpt: last 4,000
characters of combined output) to ``$ORCHESTRATOR_OUTPUT_BUNDLE_PATH``.
A missing ``dev-check.json`` fails closed.

Check-withheld form: with ``"withheld": true`` the test files are not in the tree. The directory named by
``$SEED_SET_WITHHELD`` (outside the candidate's sandbox; the runner sets it) holds them at their relative
paths. The check copies them in, runs ``argv`` in its own process group, and in every case (failure,
timeout, SIGTERM) restores each overwritten file and removes each file and directory it created, so the
tree is as before. Without that directory it fails closed. Only a SIGKILL of this process can leave
the files behind.
"""

import contextlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

EXCERPT_CHARS = 4000


@contextlib.contextmanager
def placed(tree, source):
    """Copy every file under `source` into `tree`; on exit restore the tree exactly."""
    saved, made = {}, []
    try:
        for file in sorted(p for p in source.rglob("*") if p.is_file()):
            dest = tree / file.relative_to(source)
            for directory in reversed(dest.parents):
                if not directory.exists():
                    directory.mkdir()
                    made.append(directory)
            saved[dest] = dest.read_bytes() if dest.exists() else None
            dest.write_bytes(file.read_bytes())
        yield
    finally:
        for dest, data in saved.items():
            if data is None:
                dest.unlink(missing_ok=True)
            else:
                dest.write_bytes(data)
        for directory in reversed(made):
            shutil.rmtree(directory, ignore_errors=True)


def run(argv, timeout, cwd, env=None):
    """(returncode or None on timeout, combined output); the whole process group is killed on timeout."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out.decode(errors="replace")
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return None, out.decode(errors="replace")
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def report(argv, timeout, code, output):
    if code is None:
        return {"passed": False, "failing": [f"timeout after {timeout}s"], "excerpt": output[-EXCERPT_CHARS:]}
    failing = [] if code == 0 else [f"{' '.join(argv)} exited {code}"]
    return {"passed": code == 0, "failing": failing, "excerpt": output[-EXCERPT_CHARS:]}


def check(tree=Path("."), withheld=None) -> dict:
    # ponytail: runs checks in the working clone; fresh-checkout application deferred
    config_path = tree / "dev-check.json"
    if not config_path.exists():
        return {"passed": False, "failing": ["dev-check.json missing"], "excerpt": ""}
    config = json.loads(config_path.read_text())
    argv, timeout = config["argv"], config["timeout_sec"]
    if not config.get("withheld"):
        try:
            proc = subprocess.run(argv, cwd=tree, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            output = "".join(
                stream.decode(errors="replace") if isinstance(stream, bytes) else (stream or "")
                for stream in (exc.stdout, exc.stderr))
            return report(argv, timeout, None, output)
        return report(argv, timeout, proc.returncode, proc.stdout + proc.stderr)
    source = Path(withheld or os.environ.get("SEED_SET_WITHHELD", ""))
    if not str(source) or str(source) == "." or not source.is_dir():
        return {"passed": False, "failing": ["withheld check source unavailable"], "excerpt": ""}
    # the placed tests' bytecode goes outside the tree (none is left for the agent to read) and is reused, so a
    # test whose subprocess imports the package under a short timeout is not slowed past it
    with tempfile.TemporaryDirectory(prefix="dev-check-pycache-") as cache, placed(tree, source):
        env = {key: value for key, value in os.environ.items()
               if key not in ("SEED_SET_WITHHELD", "PYTHONDONTWRITEBYTECODE")} | {"PYTHONPYCACHEPREFIX": cache}
        code, output = run(argv, timeout, tree, env)
    return report(argv, timeout, code, output)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # unwinds `placed`, so the tree is restored
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(check()))
