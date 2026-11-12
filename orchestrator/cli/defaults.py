"""Manifest files beside the workflow source, used when their flag is absent.

Applied once in `main()` after parsing, so every command and the resume recipe
see an ordinary explicit value. `resume` never looks for defaults: it uses the
paths its run recorded.
"""

from __future__ import annotations

import argparse
from pathlib import Path

MANIFEST_DEFAULTS = {"command_boundaries_file": "commands.json",
                     "provider_externs_file": "providers.json",
                     "prompt_externs_file": "prompts.json"}


def apply_manifest_defaults(args: argparse.Namespace) -> list[str]:
    """Fill each absent manifest flag from the file of that name beside args.workflow; return the files used."""
    workflow = getattr(args, "workflow", None)
    if not workflow:
        return []
    used = []
    for attribute, name in MANIFEST_DEFAULTS.items():
        if not hasattr(args, attribute) or getattr(args, attribute):
            continue
        sibling = Path(workflow).parent / name
        if sibling.is_file():
            setattr(args, attribute, str(sibling))
            used.append(str(sibling))
    return used
