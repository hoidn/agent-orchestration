"""Host-side commands that run candidate code: the visible check and the hidden tests (plan Step 2).

They run outside the sandbox, so they must never reach a real provider. `guarded` runs a command with fresh copies
of the Thread M no-provider stubs first on PATH (any `claude` or `codex` it starts by name exits 97 and is
logged), HOME, CLAUDE_CONFIG_DIR and CODEX_HOME at an empty directory (no credentials to find), and every
provider credential and COMPARE_/SEED_SET_ variable removed. It returns the process and the stubs' log lines; a
caller fails its check loudly on any logged line. A real CLI started by absolute path finds no credentials.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the study's checkout: its modules run from here
STUBS = ROOT / "experiments" / "thread_m" / "no_provider"
CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_FILE",
               "OPENAI_API_KEY", "CODEX_API_KEY")


def guarded(argv, cwd=None, timeout=None):
    """(completed process, provider attempts) of `argv` run behind fresh no-provider stubs and an empty home."""
    with tempfile.TemporaryDirectory(prefix="seed-set-host-") as directory:
        box = Path(directory)
        shutil.copytree(STUBS, box / "guard" / "no_provider")  # they log to box/guard/no-provider.log
        (box / "home").mkdir()
        env = {key: value for key, value in os.environ.items()
               if key not in CREDENTIALS and not key.startswith(("COMPARE_", "SEED_SET_", "ANTHROPIC_"))}
        env |= {"PATH": f"{box / 'guard' / 'no_provider'}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                "HOME": str(box / "home"), "CLAUDE_CONFIG_DIR": str(box / "home" / ".claude"),
                "CODEX_HOME": str(box / "home" / ".codex"), "PYTHONDONTWRITEBYTECODE": "1"}
        done = subprocess.run(argv, cwd=cwd or ROOT, env=env, capture_output=True, text=True, timeout=timeout)
        log = box / "guard" / "no-provider.log"
        return done, log.read_text().splitlines() if log.is_file() else []


def visible_check(task, patch, runtime):
    """evaluation.check_first_attempt run behind the guard; a logged provider attempt fails the check."""
    done, attempts = guarded([sys.executable, "-m", "experiments.orc_structural_search.evaluation", "check",
                              "--task", str(task), "--patch", str(patch), "--runtime", str(runtime)])
    if attempts:
        print(f"PROVIDER ATTEMPT in the visible check of {patch}: {attempts}", file=sys.stderr)
        return {"passed": False, "failing": ["the candidate's code attempted a provider call"], "excerpt": "",
                "provider_attempts": attempts}
    if done.returncode:
        raise SystemExit(f"visible check of {patch} failed to run: {done.stderr[-2000:]}")
    return json.loads(done.stdout)


def summarize(pool, criterion):
    """summarize.py (which runs the hidden tests) behind the guard; refuses on a provider attempt."""
    done, attempts = guarded([sys.executable, "-m", "experiments.compare.summarize", "--pool", str(pool),
                              "--criterion", str(criterion)])
    if attempts:
        raise SystemExit(f"PROVIDER ATTEMPT in the hidden tests of {pool}: {attempts}")
    if done.returncode:
        raise SystemExit(f"summarize refused {pool}: {(done.stderr or done.stdout).strip()[-2000:]}")
    return json.loads((Path(pool) / "records" / "results.json").read_text())
