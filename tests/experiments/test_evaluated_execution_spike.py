"""Spike of evaluated execution: the closed program, its sites and effect identity.

Throwaway (decision 4 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md,
Tasks 8 and 9). Contract: docs/design/workflow_lisp_evaluated_execution.md sections 4 and 6.

Every effect is a command-backed procedure running the probe of the totality matrix,
which appends `<command> <n>` to `probe.log`, or a stand-in provider. Programs live in
`fixtures/evaluated_execution_spike/` or are cells of the totality matrix.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from experiments.evaluated_execution_spike.closed import build_closed_program
from experiments.evaluated_execution_spike.frontend import typecheck_program
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_generic_unions_runtime import _write_sources
from tests.workflow_lisp_totality_matrix_sources import COMMANDS, PROBE, program

FIXTURES = Path(__file__).parent / "fixtures" / "evaluated_execution_spike"
BOUNDARIES = {name: ExternalToolBinding(name=name, stable_command=("python", "probe.py")) for name in COMMANDS}
PROVIDERS = {"providers.review": "codex"}
PROMPTS = {"prompts.review": "review.md"}


def fixture(name: str) -> dict[str, str]:
    return {f"spk/{name}.orc": (FIXTURES / f"{name}.orc").read_text(encoding="utf-8")}


def matrix(form: str, position: str) -> dict[str, str]:
    return program(form, position, "probe.py")


def install(root: Path, sources: dict[str, str]) -> Path:
    """Write the sources, the probe and the prompt under `root`; return the entry module's path."""

    _write_sources(root, sources)
    (root / "probe.py").write_text(PROBE, encoding="utf-8")
    (root / "review.md").write_text("Review the draft.\n", encoding="utf-8")
    return root / next(iter(sources))


def entry_workflow(sources: dict[str, str]) -> str:
    return next(iter(sources)).removesuffix(".orc") + "::run"


def build(root: Path, sources: dict[str, str], **options):
    entry = install(root, sources)
    typed = typecheck_program(
        entry,
        entry_workflow=entry_workflow(sources),
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        provider_externs=PROVIDERS,
        prompt_externs=PROMPTS,
    )
    return build_closed_program(typed, **options)


def with_blank_lines(text: str) -> str:
    """Two blank lines and a comment before every definition."""

    return text.replace("\n  (def", "\n\n\n  ;; moved down\n  (def")


# Task 8: sites -------------------------------------------------------------


def test_three_call_sites_of_one_procedure_are_three_sites(tmp_path: Path) -> None:
    closed = build(tmp_path, fixture("three_call_sites"))

    callee = "spk/three_call_sites::fetch"
    assert closed.sites == tuple(
        f"spk/three_call_sites::run / {binder}={callee} / #1" for binder in ("a", "b", "c")
    )


def test_one_procedure_in_three_arms_of_a_match_in_a_loop_is_three_sites(tmp_path: Path) -> None:
    closed = build(tmp_path, fixture("arms_in_loop"))

    callee = "spk/arms_in_loop::fetch"
    assert closed.sites == tuple(
        f"spk/arms_in_loop::run / loop:state[*] / got / {arm} / #1={callee} / #1"
        for arm in ("FIRST", "SECOND", "THIRD")
    )


def test_a_specialized_hook_is_named_by_its_base_and_its_canonical_arguments(tmp_path: Path) -> None:
    closed = build(tmp_path, fixture("if_in_hook"))

    improve = (
        "std/improve::improve[B=spk/if_in_hook::Note, F=spk/if_in_hook::Note, I=spk/if_in_hook::Brief, "
        "S=spk/if_in_hook::Candidate, review=spk/if_in_hook::review, revise=spk/if_in_hook::revise]"
    )
    prefix = f"spk/if_in_hook::run / result={improve} / loop:state[*]"
    assert closed.sites == (
        f"{prefix} / decision=spk/if_in_hook::review / b=spk/if_in_hook::fetch / #1",
        f"{prefix} / REVISE / next=spk/if_in_hook::revise / b=spk/if_in_hook::fetch / #1",
    )


@pytest.mark.parametrize("name", ["three_call_sites", "arms_in_loop", "if_in_hook", "loop_in_loop"])
def test_blank_lines_and_comments_change_no_site_and_not_the_program_digest(tmp_path: Path, name: str) -> None:
    sources = fixture(name)
    edited = {path: with_blank_lines(text) for path, text in sources.items()}

    original, spaced = build(tmp_path / "a", sources), build(tmp_path / "b", edited)

    assert edited != sources
    assert (spaced.sites, spaced.digest) == (original.sites, original.digest)


@pytest.mark.parametrize("name", ["three_call_sites", "if_in_hook", "loop_in_loop"])
def test_moving_the_program_changes_no_site_and_not_the_program_digest(tmp_path: Path, name: str) -> None:
    here = build(tmp_path / "here", fixture(name))
    there = build(tmp_path / "elsewhere" / "deeper", fixture(name))

    assert (there.sites, there.digest) == (here.sites, here.digest)


def test_no_site_and_no_part_of_the_digested_program_holds_a_path_a_position_or_a_type_text(
    tmp_path: Path,
) -> None:
    from experiments.evaluated_execution_spike.closed import strip_provenance

    closed = build(tmp_path, fixture("if_in_hook"))
    digested = json.dumps(strip_provenance(closed.tree))

    for text in (*closed.sites, digested):
        assert str(tmp_path) not in text
        assert "stdlib_modules" not in text
        assert re.search(r"TypeRef|SourceSpan|line=|\.orc:\d+", text) is None
    assert str(tmp_path) in closed.artifact()  # provenance is kept, outside the digest


def test_the_closed_program_holds_no_surface_object_and_is_canonical_json(tmp_path: Path) -> None:
    closed = build(tmp_path, matrix("pure-match", "loop-state-field"))

    reparsed = json.loads(closed.artifact())

    assert reparsed == closed.tree
    assert '"opaque' not in closed.artifact() and "Expr" not in closed.artifact()


def test_moving_the_package_changes_no_site_and_not_the_program_digest(tmp_path: Path) -> None:
    """The orchestrator package, `std/improve` included, and the spike, copied to another root."""

    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    package = tmp_path / "package"
    for part in ("orchestrator", "experiments/evaluated_execution_spike"):
        shutil.copytree(repo / part, package / part, ignore=shutil.ignore_patterns("__pycache__"))
    entry = install(tmp_path / "program", fixture("if_in_hook"))
    script = (
        "import json, sys; from pathlib import Path\n"
        "from experiments.evaluated_execution_spike.closed import build_closed_program\n"
        "from experiments.evaluated_execution_spike.frontend import typecheck_program\n"
        "from orchestrator.workflow_lisp.workflows import ExternalToolBinding\n"
        "entry = Path(sys.argv[1])\n"
        "typed = typecheck_program(entry, entry_workflow='spk/if_in_hook::run', source_roots=(entry.parents[1],),\n"
        "    command_boundaries={'fetch': ExternalToolBinding(name='fetch', stable_command=('python', 'probe.py'))})\n"
        "closed = build_closed_program(typed)\n"
        "print(json.dumps([closed.sites, closed.digest]))\n"
    )
    moved = subprocess.run(
        [sys.executable, "-c", script, str(entry)],
        cwd=package, env={"PYTHONPATH": str(package), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=True,
    )
    here = build(tmp_path / "here", fixture("if_in_hook"))

    assert json.loads(moved.stdout.splitlines()[-1]) == [list(here.sites), here.digest]
