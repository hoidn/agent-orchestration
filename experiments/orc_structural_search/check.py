"""Offline episode admission against its local immutable parent commit."""

import argparse
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from experiments.orc_structural_search.acceptance import judge_child
from experiments.orc_structural_search.config import load_config

# Only driver-owned top-level files are omitted. Arbitrary extra content must reach scope validation.
WORKSPACE_FILES = frozenset({".git", "EPISODE.md", "HYPOTHESIS.txt", ".orchestrate"})


def check_workspace(workspace: Path, metadata: Path) -> dict:
    workspace, metadata = workspace.resolve(), metadata.resolve()
    settings = json.loads(metadata.read_text())
    config = load_config(metadata.parent / settings["config"])
    with tempfile.TemporaryDirectory() as temporary:
        parent, child = Path(temporary) / "parent", Path(temporary) / "child"
        parent.mkdir()
        archive = subprocess.run(["git", "archive", settings["base"]], cwd=workspace,
                                 check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(parent, filter="data")
        shutil.copytree(workspace, child, ignore=lambda directory, names: (
            list(WORKSPACE_FILES.intersection(names)) if Path(directory) == workspace else []))
        hypothesis = workspace / "HYPOTHESIS.txt"
        if settings.get("site") and hypothesis.is_file():
            shutil.copyfile(hypothesis, child / hypothesis.name)
        result = judge_child(parent, child, config, runtime=metadata.parent / "py", site=settings.get("site"),
                             parent_candidate_id=settings.get("parent_candidate_id"))
        if "diagnostics" in result:
            result["diagnostics_schema_version"] = "workflow_lisp_compile_diagnostics.v1"
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    result = check_workspace(Path.cwd(), args.metadata)
    print(json.dumps(result))
    raise SystemExit(0 if result["outcome"] == "accepted" else 2 if result["outcome"] == "incident" else 1)


if __name__ == "__main__":
    main()
