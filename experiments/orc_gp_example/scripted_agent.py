"""The toy world: a scripted coding agent and the check it is judged by. No provider is called.

Installed by `evolve.py` three ways, and dispatches on the name it runs under:

* `claude` / `codex` on PATH (the `claude_unrestricted_workspace` / `codex_unrestricted_workspace` provider
  templates run those names): reads the prompt on stdin and `--model <name>` from argv, updates
  `world.json` in the working directory and writes its JSON result to `$ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
* `check.py` in the workspace (the `check` command boundary): writes a CheckReport
  `{"passed": bool, "failing": [str]}` to `$ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

The rules are deterministic and make program structure matter (a toy, not a model of real agents):

* implement: leaves 2 defects with the cheap model, 1 with a strong one, 0 when the prompt carries a
  strong planner's GUARD-EDGE-CASE step.
* plan: only a strong model (opus, gpt-6-sol) writes the GUARD-EDGE-CASE step.
* diagnose: only a strong model names a ROOT-CAUSE; a repair given one removes every defect, otherwise one.
* review: requests changes only when defects remain and the reviewer's family (claude/gpt) differs from the
  implementer's; each revision removes one defect.
* check: passes iff something was implemented and no defect remains.
"""

import json
import os
import re
import sys
from pathlib import Path

STRONG = {"claude-opus-5-5", "gpt-6-sol"}
UNPLANNED_DEFECTS = {"claude-sonnet-5-5": 2, "claude-opus-5-5": 1, "gpt-6-sol": 1}
WORLD = Path("world.json")


def family(model: str) -> str:
    return "gpt" if model.startswith("gpt") else "claude"


def act(stage: str, model: str, prompt: str, world: dict) -> dict:
    """Apply `stage` by `model` to `world` (mutated in place) and return the provider result."""

    if stage == "plan":
        return {"steps": ["write the change"] + (["GUARD-EDGE-CASE"] if model in STRONG else [])}
    if stage == "implement":
        defects = 0 if "GUARD-EDGE-CASE" in prompt else UNPLANNED_DEFECTS[model]
        world.update(implemented=True, defects=defects, implementer_family=family(model))
        return {"summary": f"implemented with {defects} defect(s)"}
    if stage == "diagnose":
        return {"findings": ["ROOT-CAUSE: unguarded edge case"] if model in STRONG else ["something is off"]}
    if stage in ("repair", "revise"):
        if world["implemented"]:
            world["defects"] = 0 if "ROOT-CAUSE" in prompt else max(0, world["defects"] - 1)
        return {"summary": f"{stage} left {world['defects']} defect(s)"}
    if stage == "review":
        if world["defects"] and family(model) != world["implementer_family"]:
            return {"variant": "REQUEST_CHANGES", "findings": ["the edge case is unguarded"]}
        return {"variant": "APPROVE", "notes": []}
    raise SystemExit(f"scripted agent: unknown stage {stage!r}")


def agent() -> dict:
    prompt = sys.stdin.read()
    model = sys.argv[sys.argv.index("--model") + 1]
    stage = re.search(r"STAGE:(\w+)", prompt)
    if stage is None:
        raise SystemExit("scripted agent: prompt carries no STAGE marker")
    world = json.loads(WORLD.read_text()) if WORLD.exists() else {"implemented": False, "defects": 0,
                                                                   "implementer_family": None}
    result = act(stage.group(1), model, prompt, world)
    WORLD.write_text(json.dumps(world))
    return result


def check() -> dict:
    world = json.loads(WORLD.read_text()) if WORLD.exists() else {"implemented": False, "defects": 0}
    failing = ([] if world["implemented"] else ["nothing implemented"]) + \
        [f"defect {n}" for n in range(1, world["defects"] + 1)]
    return {"passed": not failing, "failing": failing}


if __name__ == "__main__":
    result = check() if Path(sys.argv[0]).name == "check.py" else agent()
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(result))
