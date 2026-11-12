#!/usr/bin/env python3
"""Build the environment of one authoring-check arm.

Usage: build_env.py before|after OUT_DIR [--commit COMMIT]

Exports `orchestrator/`, `pyproject.toml` and `LICENSE.md` at COMMIT with
`git archive`, installs them non-editable into OUT_DIR/venv (a virtual
environment that sees this interpreter's packages, so no network is needed),
checks that the installed package is the one imported, and writes the arm's
document to OUT_DIR/GUIDE.md and the arm's facts to OUT_DIR/env.json.

- before: COMMIT defaults to the Phase 1 base (the parent of the first Phase 1
  code commit); the document is the Workflow Lisp drafting guide.
- after: COMMIT is required (the phase tip); the document is the tutorial.

OUT_DIR must not exist and must lie outside the checkout. Calls no model.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

KIT = Path(__file__).resolve().parent
REPO = KIT.parents[1]
PHASE1_BASE = "22dfb97389ea7dba4c2424f187ff084e492ffdfb"
ARMS = {"before": ("docs/lisp_workflow_drafting_guide.md", PHASE1_BASE),
        "after": ("docs/tutorial_first_pipeline.md", None)}
PACKAGE = ("orchestrator", "pyproject.toml", "LICENSE.md")


def _git(*argv: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *argv], capture_output=True, check=True).stdout


def checkout_root() -> Path:
    """The main checkout (worktrees share its git directory)."""
    common = _git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()
    return Path(common).parent


def build(arm: str, out: Path, commit: str) -> dict:
    document, _default = ARMS[arm]
    sha = _git("rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    guide = _git("show", f"{sha}:{document}")
    src = out / "src"
    src.mkdir(parents=True)
    archive = _git("archive", "--format=tar", sha, *PACKAGE)
    subprocess.run(["tar", "-x", "-C", str(src)], input=archive, check=True)
    venv = out / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], check=True)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "--quiet", "--no-index", "--no-deps",
                    "--no-build-isolation", str(src)], check=True, env=env, cwd=out)
    located = subprocess.run([str(venv / "bin" / "python"), "-c", "import orchestrator; print(orchestrator.__file__)"],
                             capture_output=True, text=True, check=True, env=env, cwd=out).stdout.strip()
    if not Path(located).resolve().is_relative_to(venv.resolve()):
        raise SystemExit(f"build_env: orchestrator imports from {located}, not from {venv}")
    if not (venv / "bin" / "orchestrator").is_file():
        raise SystemExit(f"build_env: no orchestrator script in {venv / 'bin'}")
    (out / "GUIDE.md").write_bytes(guide)
    facts = {"arm": arm, "commit": sha, "document": document, "base_python": sys.executable,
             "orchestrator_module": located}
    (out / "env.json").write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return facts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arm", choices=sorted(ARMS))
    parser.add_argument("out", type=Path)
    parser.add_argument("--commit")
    args = parser.parse_args(argv)
    commit = args.commit or ARMS[args.arm][1]
    if commit is None:
        parser.error(f"arm {args.arm} needs --commit")
    out = args.out.resolve()
    if out.exists():
        parser.error(f"{out} already exists")
    if out.is_relative_to(checkout_root()):
        parser.error(f"{out} is inside the checkout {checkout_root()}")
    print(json.dumps(build(args.arm, out, commit), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
