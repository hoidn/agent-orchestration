"""Size of the closed program over the shipped workflows, in the tree form and the table form (item F).

Run from the repository root:
  PYTHONPATH=$PWD PYTHONDONTWRITEBYTECODE=1 python experiments/evaluated_execution_spike/census.py <scratch dir>

The workflows are copied to the scratch directory. Externs come from the checked-in
manifests (`*providers*.json`, `*prompts*.json`, `*commands*.json`) where one names
them; otherwise a provider is `codex`, a prompt an empty file created in the copy, and
a plain command the leading literal words of its `:argv`. A certified adapter with no
manifest entry cannot be synthesized; the workflow is reported as not built.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from orchestrator.workflow_lisp.build_manifest_io import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.workflows import ExternalToolBinding

from .closed import build_closed_program
from .frontend import typecheck_program
from .table import to_table

CORPUS = ("workflows/examples", "workflows/library", "workflows/experiments", "experiments/orc_vs_single_call",
          "experiments/mlevolve_pair")


def count_nodes(node: Any) -> int:
    if isinstance(node, dict):
        return 1 + sum(count_nodes(v) for v in node.values())
    if isinstance(node, list):
        return sum(count_nodes(v) for v in node)
    return 0


def _manifests(repo: Path) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {"providers": {}, "prompts": {}, "commands": {}}
    for kind in merged:
        for path in sorted(repo.glob(f"**/*{kind}*.json")):
            if ".tmp" in path.parts or "tests" in path.parts:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                for key, value in data.items():
                    merged[kind].setdefault(key, value)
    return merged


def _externs(text: str, entry: Path, manifests: dict[str, dict[str, Any]]) -> tuple[dict, dict, dict]:
    providers = {n: manifests["providers"].get(n, "codex") for n in re.findall(r"\bproviders\.[\w.-]+", text)}
    prompts = {}
    for name in re.findall(r"\bprompts\.[\w.-]+", text):
        path = manifests["prompts"].get(name) or f"synthesized/{name}.md"
        path = path if isinstance(path, str) else next(iter(path.values()))
        target = entry.parent / path
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Stand-in prompt.\n", encoding="utf-8")
        prompts[name] = path
    commands: dict[str, Any] = {}
    for match in re.finditer(r"\(command-result\s+([\w.-]+)(.*?)(?=\(command-result|\Z)", text, re.S):
        name, rest = match.group(1), match.group(2)
        adapter = re.match(r"\s*:adapter\s+([\w.-]+)", rest)
        key = adapter.group(1) if adapter else name
        if key in manifests["commands"]:
            commands[key] = _parse_command_boundaries_manifest({key: manifests["commands"][key]}, manifest_path=None)[key]
        elif not adapter:
            argv = re.search(r":argv\s*\(((?:\s*\"[^\"]*\")+)", rest)
            words = re.findall(r"\"([^\"]*)\"", argv.group(1)) if argv else ["true"]
            commands[key] = ExternalToolBinding(name=key, stable_command=tuple(words))
    return providers, prompts, commands


def measure(entry: Path, root: Path, workflow: str, manifests: dict) -> dict[str, Any]:
    text = entry.read_text(encoding="utf-8")
    providers, prompts, commands = _externs(text, entry, manifests)
    started = time.monotonic()
    library = [p for p in (root / "workflows" / "library", *[a / "workflows" / "library" for a in root.parents])
               if p.is_dir()][:1]
    typed = typecheck_program(entry, entry_workflow=workflow, source_roots=(root, *library),
                              command_boundaries=commands, provider_externs=providers, prompt_externs=prompts)
    closed = build_closed_program(typed)
    seconds = time.monotonic() - started
    table = to_table(closed)
    return {"nodes": count_nodes(closed.tree), "bytes": len(closed.artifact().encode()), "seconds": round(seconds, 2),
            "sites": len(closed.sites), "table_nodes": count_nodes(table.tree),
            "table_bytes": len(table.artifact().encode()), "table_sites": len(table.sites),
            "definitions": len(table.tree["definitions"])}


def census(repo: Path, scratch: Path) -> list[dict[str, Any]]:
    manifests = _manifests(repo)
    rows = []
    for corpus in CORPUS:
        shutil.copytree(repo / corpus, scratch / corpus, dirs_exist_ok=True)
        for entry in sorted((scratch / corpus).rglob("*.orc")):
            text = entry.read_text(encoding="utf-8")
            module = re.search(r"\(defmodule\s+([^)\s]+)\)", text)
            if module is None:
                continue
            root = entry.parents[len(module.group(1).split("/")) - 1]
            exported = re.search(r"\(export\s+([^)]*)\)", text)
            workflows = [w for w in (exported.group(1).split() if exported else [])
                         if re.search(rf"\(defworkflow\s+{re.escape(w)}\s", text)]
            for workflow in workflows:
                row = {"file": entry.relative_to(scratch).as_posix(), "workflow": workflow}
                try:
                    row.update(measure(entry, root, f"{module.group(1)}::{workflow}", manifests))
                except BaseException as exc:  # a measurement records why a workflow was not built
                    row["not_built"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
                rows.append(row)
    return rows


if __name__ == "__main__":
    scratch = Path(sys.argv[1])
    scratch.mkdir(parents=True, exist_ok=True)
    print(json.dumps(census(Path.cwd(), scratch), indent=1))
