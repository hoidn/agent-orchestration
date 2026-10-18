"""I2 sites: the source-site manifest of a candidate, site selection, the site brief and the derived receipt.

Design: docs/design/orc_structural_search_driver.md (Proposal Interfaces I2, Edit Validation And Transactions);
manifest contract: docs/design/workflow_lisp_source_site_inspection.md §3. The manifest is built by the runtime's
own copy of this module in a subprocess (`site_manifest`; `python -P -m experiments.orc_structural_search.sites`
with PYTHONPATH=<runtime>, cwd=<runtime>), so the driver never imports another orchestrator than the one that
evaluates the candidate. `main` compiles in process and prints the manifest JSON as its last stdout line.

The receipt is derived from the child's final files, never written by the agent (`derive_receipt`): the
replacement is the child's subform at the parent site's index path, the supporting declarations are the child's
top-level definitions the parent lacks, the hypothesis is the first line of an optional HYPOTHESIS.txt in the
child root. `candidates.validate_one_site` judges it.
"""

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from experiments.orc_structural_search.candidates import (
    Receipt, _owner_form, _parse_site, _site_path, _split_forms, _subform, _top_level_forms)
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.records import UNAVAILABLE
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_text

HYPOTHESIS = "HYPOTHESIS.txt"
STDERR_TAIL_CHARS = 4000


def site_manifest(root: Path, config: ExperimentConfig, *, runtime: Path) -> dict:
    """The manifest of the candidate at `root` over its mutable `.orc` files, built by the runtime's helper.

    Raises RuntimeError with the helper's stderr tail when it exits nonzero.
    """
    command = [sys.executable, "-P", "-m", "experiments.orc_structural_search.sites", "--root", str(root),
               "--entry-workflow", config.entry_workflow, "--source-root", config.source_root,
               "--provider-externs-file", config.providers_file]
    if config.command_boundaries_file is not None:
        command += ["--command-boundaries-file", config.command_boundaries_file]
    command += ["--files", *[name for name in config.mutable_files if name.endswith(".orc")]]
    result = subprocess.run(command, cwd=runtime, env={**os.environ, "PYTHONPATH": str(runtime)},
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"site manifest of {root} failed (exit {result.returncode}): "
                           f"{result.stderr[-STDERR_TAIL_CHARS:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def main(argv: Sequence[str] | None = None) -> None:
    """Compile the candidate in process and print its manifest over `--files` (paths relative to `--root`)."""
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle
    from orchestrator.workflow_lisp.reader import SourceReadTrace
    from orchestrator.workflow_lisp.source_sites import build_manifest

    parser = argparse.ArgumentParser(prog="python -m experiments.orc_structural_search.sites")
    for flag in ("--root", "--entry-workflow", "--source-root", "--provider-externs-file"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--command-boundaries-file")
    parser.add_argument("--files", nargs="+", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    source_root = root / args.source_root
    boundaries = args.command_boundaries_file and root / args.command_boundaries_file
    result = prepare_closed_program_bundle(FrontendBuildRequest(
        source_path=(source_root / args.entry_workflow.split("::")[0]).with_suffix(".orc"), source_roots=(source_root,),
        entry_workflow=args.entry_workflow, provider_externs_path=root / args.provider_externs_file,
        command_boundaries_path=boundaries or None, workspace_root=root), source_read_trace=SourceReadTrace())
    print(json.dumps(build_manifest(result, root=root, files=[Path(name) for name in args.files]), sort_keys=True))


def eligible_sites(manifest: Mapping, config: ExperimentConfig) -> list[dict]:
    """Eligible records whose owner is a mutable definition in a mutable file, sorted by site id."""
    return sorted((dict(record) for record in manifest["sites"].values()
                   if record["eligibility"] == "eligible"
                   and record["owner"]["name"].rpartition("::")[2] in config.mutable_definitions
                   and record["span"]["start"]["path"] in config.mutable_files),
                  key=lambda record: record["site_id"])


def select_site(sites: Sequence[Mapping], rng: random.Random) -> dict:
    return dict(rng.choice(sites))


def site_brief(site: Mapping) -> str:
    """The site's record and the I2 rule, as the brief's "Site" section text."""
    start, end = site["span"]["start"], site["span"]["end"]
    bindings = "\n".join(f"- {binding['name']}: {binding['type']}" for binding in site["bindings"]) or "- (none)"
    return "\n".join([
        f"Site: {site['site_id']}",
        f"Kind: {site['kind']}, {start['path']} lines {start['line']}-{end['line']}"
        f" (the form starting at line {start['line']}, column {start['column']})",
        f"Result type: {site['result_type']['rendered']}",
        "Bindings in scope:", bindings,
        f"Dependencies: {json.dumps(site['dependencies'], sort_keys=True)}",
        f"Owner effect restriction: {site['effects']['restriction']}",
        "",
        "Replace exactly that form with one expression of the same result type. Any helper you need goes in as a"
        " new top-level definition with a fresh name. Nothing else changes: no other form, definition or file."
        f" Optionally write a one-line {HYPOTHESIS} saying why the replacement should do better.",
    ])


def _forms_and_text(path: Path) -> tuple[tuple, str] | None:
    """(top-level forms, LF-normalized text their offsets index), or None when the file is missing or unreadable."""
    try:
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        return _top_level_forms(read_sexpr_text(text, source_path=str(path))), text
    except (FileNotFoundError, UnicodeDecodeError, LispFrontendCompileError):
        return None  # the receipt stays empty; validate_one_site reports the child


def _slice(text: str, node) -> str:
    return text[node.span.start.offset:node.span.end.offset]


def derive_receipt(parent: Path, child: Path, site: Mapping, config: ExperimentConfig, *,
                   parent_candidate_id: str) -> Receipt:
    """The I2 receipt of `child` against the parent's `site`, read from the child's files (see module doc)."""
    owner_name, file_name, line, column = _parse_site(site["site_id"])
    parent_bytes = (parent / file_name).read_bytes()
    parent_forms = _forms_and_text(parent / file_name)[0]
    path = _site_path(_owner_form(parent_forms, owner_name), line, column)
    replacement, helpers = "", ()
    child_read = _forms_and_text(child / file_name)
    if child_read is not None:
        child_forms, text = child_read
        child_owner = _owner_form(child_forms, owner_name)
        node = _subform(child_owner, path) if child_owner is not None and path is not None else None
        replacement = _slice(text, node) if node is not None else ""
        present = _split_forms(parent_forms)[1].keys()
        helpers = tuple(_slice(text, form) for key, form in _split_forms(child_forms)[1].items()
                        if key not in present)
    return Receipt(parent_candidate_id=parent_candidate_id, site_id=site["site_id"],
                   expected_file_digest="sha256:" + hashlib.sha256(parent_bytes).hexdigest(),
                   replacement_expression=replacement, supporting_declarations=helpers,
                   condition=config.condition, hypothesis=_hypothesis(child / HYPOTHESIS))


def _hypothesis(path: Path) -> str:
    """The first line of the optional hypothesis file, else "unavailable"."""
    lines = path.read_text().splitlines() if path.is_file() else []
    return lines[0].strip() if lines and lines[0].strip() else UNAVAILABLE


def slot_type(manifest: Mapping, owner: str, path: str, line: int, column: int) -> str | None:
    """The canonical result type of the site `<owner>@<path>:<line>:<column>`, or None (no site, or no type)."""
    result_type = manifest["sites"].get(f"{owner}@{path}:{line}:{column}", {}).get("result_type")
    return result_type["canonical"] if isinstance(result_type, Mapping) else None


if __name__ == "__main__":
    main()
