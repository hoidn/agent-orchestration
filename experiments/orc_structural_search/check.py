"""Offline episode admission against its controller-staged parent snapshot."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from experiments.orc_structural_search.acceptance import judge_child
from experiments.orc_structural_search.config import load_config

# Only driver-owned top-level files are omitted. Arbitrary extra content must reach scope validation.
WORKSPACE_FILES = frozenset({".git", "EPISODE.md", "HYPOTHESIS.txt", ".orchestrate"})


def stage_parent(source: Path, destination: Path) -> None:
    """Stage an advisory check's parent outside the mutable repository and its Git history."""
    from experiments.orc_structural_search.candidates import snapshot
    snapshot(source, {}, destination)
    for path in destination.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    destination.chmod(0o555)


def check_workspace(workspace: Path, metadata: Path) -> dict:
    workspace, metadata = workspace.resolve(), metadata.resolve()
    settings = json.loads(metadata.read_text())
    config = load_config(metadata.parent / settings["config"])
    with tempfile.TemporaryDirectory() as temporary:
        parent, child = Path(temporary) / "parent", Path(temporary) / "child"
        shutil.copytree(metadata.parent / settings["parent"], parent, copy_function=shutil.copyfile)
        for directory in [parent, *(path for path in parent.rglob("*") if path.is_dir())]:
            directory.chmod(0o755)
        shutil.copytree(workspace, child, ignore=lambda directory, names: (
            list(WORKSPACE_FILES.intersection(names)) if Path(directory) == workspace else []))
        hypothesis = workspace / "HYPOTHESIS.txt"
        if settings.get("site") and hypothesis.is_file():
            shutil.copyfile(hypothesis, child / hypothesis.name)
        result = judge_child(parent, child, config, runtime=metadata.parent / "py", site=settings.get("site"),
                             parent_candidate_id=settings.get("parent_candidate_id"))
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
