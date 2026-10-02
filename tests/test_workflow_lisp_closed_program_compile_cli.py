from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import orchestrator
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp import syntax
import pytest


TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION


PROGRAM = """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"TARGET\")
  (defmodule grt/entry)
  (export run)
  (defrecord Candidate (title String) (score Int))
  (defproc revise-candidate
    ((candidate Candidate))
    -> Candidate
    :effects ((uses-command probe_revise))
    :lowering inline
    (command-result probe_revise
      :argv (\"python\" \"probe_revise.py\" candidate.title \"tidy\" \"fb\")
      :returns Candidate))
  (defworkflow run () -> Candidate
    (let* ((first (revise-candidate (record Candidate :title \"seed\" :score 0)))
           (second (revise-candidate first)))
      second)))
"""


def _write_workspace(root: Path, *, target: str | None = None) -> dict[str, Path]:
    source_root = root / "src"
    source = source_root / "grt" / "entry.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        PROGRAM.replace("TARGET", target or TARGET)
    )
    (root / "probe_revise.py").write_text("print('unused during compilation')\n")
    providers = root / "providers.json"
    providers.write_text('{"reviewer":"provider:review"}')
    prompts = root / "prompts.json"
    prompts.write_text('{"prompt":"asset_file:review.md"}')
    commands = root / "commands.json"
    commands.write_text(json.dumps({
        "probe_revise": {
            "kind": "external_tool",
            "stable_command": ["python", "probe_revise.py"],
            "closure": ["probe_revise.py"],
        }
    }))
    return {
        "workspace": root,
        "source_root": source_root,
        "source": source,
        "providers": providers,
        "prompts": prompts,
        "commands": commands,
    }


def _compile(files: dict[str, Path], *, package_root: Path | None = None, extra: tuple[str, ...] = ()):
    argv = [
        sys.executable, "-m", "orchestrator", "compile", str(files["source"]),
        "--source-root", str(files["source_root"]),
        "--provider-externs-file", str(files["providers"]),
        "--prompt-externs-file", str(files["prompts"]),
        "--command-boundaries-file", str(files["commands"]),
        *extra,
    ]
    if "imports" in files:
        argv += ["--imported-workflow-bundles-file", str(files["imports"])]
    env = {
        **os.environ,
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": str(package_root or Path(orchestrator.__file__).parents[1]),
    }
    return subprocess.run(
        argv, cwd=files["workspace"], env=env, capture_output=True, text=True, check=False
    )


def _build_state(files: dict[str, Path], *, package_root: Path | None = None):
    completed = _compile(files, package_root=package_root)
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    artifact = Path(summary["build_root"]) / "closed_program.json"
    return summary, ClosedProgram.from_artifact(artifact.read_text()), artifact.read_bytes()


def _write_import_workspace(root: Path, producer_target: str) -> dict[str, Path]:
    files = _write_workspace(root)
    source = root / "src" / "consumer" / "entry.orc"
    source.parent.mkdir(parents=True)
    source.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer/entry)
  (export run)
  (defworkflow run () -> Int (call selected-run)))
""")
    producer = root / "src" / "producer" / "entry.orc"
    producer.parent.mkdir(parents=True)
    producer.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{producer_target}")
  (defmodule producer/entry)
  (export selected-run)
  (defworkflow selected-run () -> Int 7))
""")
    imports = root / "imports.json"
    imports.write_text(json.dumps({
        "selected-run": {"kind": "compiled", "path": "src/producer/entry.orc"}
    }))
    files.update({"source": source, "imports": imports})
    return files


def _write_transitive_import_workspace(
    root: Path,
    *,
    selected_entry: str = "selected-run",
) -> dict[str, Path]:
    files = _write_workspace(root)
    source = root / "src" / "consumer" / "entry.orc"
    source.parent.mkdir(parents=True)
    source.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer/entry)
  (export run)
  (defworkflow run () -> Int (call selected-run)))
""")
    producer = root / "src" / "producer" / "entry.orc"
    producer.parent.mkdir(parents=True)
    producer.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule producer/entry)
  (import producer/helper :only (increment))
  (export selected-run alternate-run)
  (defworkflow selected-run () -> Int (increment 6))
  (defworkflow alternate-run () -> Int (increment 8)))
""")
    helper = root / "src" / "producer" / "helper.orc"
    helper.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule producer/helper)
  (export increment)
  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1)))
""")
    old_producer = root / "src" / "unused" / "entry.orc"
    old_producer.parent.mkdir(parents=True)
    old_producer.write_text("""(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule unused/entry)
  (export run)
  (defworkflow run () -> Int 9))
""")
    imports = files["imports"] = root / "imports.json"
    imports.write_text(json.dumps({
        "selected-run": {
            "kind": "compiled",
            "path": "src/producer/entry.orc",
            "entry_workflow": selected_entry,
        },
        "unused-run": {
            "kind": "compiled",
            "path": "src/unused/entry.orc",
            "entry_workflow": "run",
        },
    }))
    files.update({
        "source": source,
        "producer": producer,
        "helper": helper,
        "unused_producer": old_producer,
    })
    return files


def _write_injected_source_graph(root: Path) -> dict[str, Path]:
    source_root = root / "src"
    source_root.mkdir(parents=True)
    helper = source_root / "helper.orc"
    helper.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule helper)
  (export ReviewFindings ReviewFindingsJsonPath fetch)
  (defpath ReviewFindingsJsonPath :kind relpath :under "artifacts" :must-exist true)
  (defrecord ReviewFindings (schema_version String) (items_path String))
  (defproc fetch ((items ReviewFindingsJsonPath)) -> ReviewFindings
    :effects ((uses-command validate_review_findings_v1))
    :lowering inline
    (command-result validate_review_findings_v1
      :adapter validate_review_findings_v1
      :inputs ((items_path items))
      :returns ReviewFindings)))
""")
    source = source_root / "entry.orc"
    source.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule entry)
  (import helper :only (ReviewFindings ReviewFindingsJsonPath fetch))
  (export run)
  (defworkflow run ((items ReviewFindingsJsonPath)) -> ReviewFindings (fetch items)))
""")
    return {"workspace": root, "source_root": source_root, "source": source, "helper": helper}


def _write_injected_import_workspace(root: Path) -> dict[str, Path]:
    files = _write_transitive_import_workspace(root)
    helper = files["helper"]
    helper.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule producer/helper)
  (export ReviewFindings ReviewFindingsJsonPath fetch)
  (defpath ReviewFindingsJsonPath :kind relpath :under "artifacts" :must-exist true)
  (defrecord ReviewFindings (schema_version String) (items_path String))
  (defproc fetch ((items ReviewFindingsJsonPath)) -> ReviewFindings
    :effects ((uses-command validate_review_findings_v1))
    :lowering inline
    (command-result validate_review_findings_v1
      :adapter validate_review_findings_v1
      :inputs ((items_path items))
      :returns ReviewFindings)))
""")
    files["producer"].write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule producer/entry)
  (import producer/helper :only (ReviewFindings ReviewFindingsJsonPath fetch))
  (export selected-run alternate-run)
  (defworkflow selected-run ((items ReviewFindingsJsonPath)) -> Int
    (let* ((findings (fetch items))) 7))
  (defworkflow alternate-run ((items ReviewFindingsJsonPath)) -> Int
    (let* ((findings (fetch items))) 8)))
""")
    files["source"].write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer/entry)
  (export run)
  (defpath ConsumerItems :kind relpath :under "artifacts" :must-exist true)
  (defworkflow run ((items ConsumerItems)) -> Int (call selected-run :items items)))
""")
    return files


def _write_specialized_callee_workspace(root: Path) -> dict[str, Path]:
    files = _write_workspace(root)
    source = files["source_root"] / "cp" / "if_in_hook.orc"
    source.parent.mkdir(parents=True)
    fixture = Path(__file__).parent / "fixtures" / "workflow_lisp" / "closed_program" / "if_in_hook.orc"
    source.write_text(fixture.read_text().replace("TARGET", TARGET))
    (root / "probe.py").write_text(
        "import json\n"
        "import sys\n\n"
        "print(json.dumps({'n': int(sys.argv[-1])}))\n"
    )
    files["commands"].write_text(json.dumps({
        "fetch": {
            "kind": "external_tool",
            "stable_command": ["python", "probe.py"],
            "closure": ["probe.py"],
        }
    }))
    files["source"] = source
    return files


def test_compile_writes_the_closed_program_and_its_manifest(tmp_path: Path) -> None:
    files = _write_workspace(tmp_path)

    completed = _compile(files)

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    build_root = Path(summary["build_root"])
    program = ClosedProgram.from_artifact((build_root / "closed_program.json").read_text())
    manifest = json.loads((build_root / "manifest.json").read_text())
    assert summary == {
        "artifact_paths": {"closed_program": str(build_root / "closed_program.json")},
        "build_key": build_root.name,
        "build_root": str(build_root),
        "entry_workflow": "grt/entry::run",
        "program_digest": program.digest,
        "sites": len(program.sites),
    }
    assert manifest["schema_version"] == "closed-program-build/1"
    assert manifest["artifact_paths"] == {
        "closed_program": f"build/{build_root.name}/closed_program.json"
    }
    assert manifest["program_digest"] == program.digest
    assert manifest["build_key"] == build_root.name
    assert program.tree["entry"] == "workflow:grt/entry::run"
    assert program.sites


def test_compile_machine_output_reports_only_closed_program_identity(tmp_path: Path) -> None:
    files = _write_workspace(tmp_path)

    completed = _compile(files, extra=("--diagnostics-json",))

    assert completed.returncode == 0, completed.stderr
    machine = json.loads(completed.stdout)
    assert set(machine) == {"status", "program_digest", "build_key"}
    assert machine["status"] == "accepted"
    build = json.loads(
        (tmp_path / ".orchestrate" / "build" / machine["build_key"] / "manifest.json").read_text()
    )
    assert machine["program_digest"] == build["program_digest"]


@pytest.mark.parametrize("entry", ["run", "grt/entry::run"])
def test_compile_accepts_raw_and_canonical_entry_names(
    tmp_path: Path, entry: str
) -> None:
    files = _write_workspace(tmp_path)

    completed = _compile(files, extra=("--entry-workflow", entry))

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["entry_workflow"] == "grt/entry::run"


@pytest.mark.parametrize(
    "flag",
    [
        "--emit-executable-ir",
        "--emit-core-ast",
        "--emit-runtime-plan",
        "--emit-semantic-ir",
        "--emit-source-map",
        "--emit-debug-yaml",
    ],
)
def test_compile_rejects_each_flat_emit_flag_at_evaluated_target(
    tmp_path: Path, flag: str
) -> None:
    files = _write_workspace(tmp_path)

    completed = _compile(files, extra=(flag, "--diagnostics-json"))

    assert completed.returncode == 2
    diagnostic = json.loads(completed.stdout)["diagnostics"][0]
    assert diagnostic["code"] == "workflow_lisp_cli_input_unsupported"
    assert flag in diagnostic["message"]


def test_compile_missing_source_keeps_the_frontend_missing_diagnostic(tmp_path: Path) -> None:
    files = _write_workspace(tmp_path)
    files["source"] = tmp_path / "src" / "missing.orc"

    completed = _compile(files, extra=("--diagnostics-json",))

    assert completed.returncode == 2
    diagnostic = json.loads(completed.stdout)["diagnostics"][0]
    assert diagnostic["code"] == "workflow_lisp_cli_input_missing"
    assert diagnostic["path"] == str(files["source"])


def test_malformed_target_peek_keeps_duplicate_export_diagnostic_precedence(
    tmp_path: Path,
) -> None:
    files = _write_workspace(tmp_path)
    files["source"].write_bytes(
        f'(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")\n'.encode()
        + b"\xff"
    )
    completed = _compile(
        files,
        extra=(
            "--emit-core-ast", "duplicate.json",
            "--emit-core-ast", "duplicate.json",
            "--diagnostics-json",
        ),
    )
    assert completed.returncode == 2
    diagnostic = json.loads(completed.stdout)["diagnostics"][0]
    assert diagnostic["code"] == "artifact_export_requested_multiple_times"


def test_compile_requires_closures_at_the_command_manifest_and_keeps_234_compatibility(
    tmp_path: Path,
) -> None:
    files = _write_workspace(tmp_path)
    command_manifest = json.loads(files["commands"].read_text())
    command_manifest["probe_revise"].pop("closure")
    files["commands"].write_text(json.dumps(command_manifest))

    completed = _compile(files, extra=("--diagnostics-json",))

    assert completed.returncode == 2
    diagnostic = json.loads(completed.stdout)["diagnostics"][0]
    assert diagnostic["code"] == "command_boundary_closure_missing"
    assert diagnostic["path"] == str(files["commands"])

    legacy = _write_workspace(tmp_path / "legacy", target="2.34")
    legacy_manifest = json.loads(legacy["commands"].read_text())
    legacy_manifest["probe_revise"].pop("closure")
    legacy["commands"].write_text(json.dumps(legacy_manifest))
    legacy_completed = _compile(legacy)
    assert legacy_completed.returncode == 0, legacy_completed.stderr


@pytest.mark.parametrize("entry", [None, "run", "entry::run"])
def test_moduleless_compile_preserves_explicit_entry_selection(
    tmp_path: Path, entry: str | None
) -> None:
    files = _write_workspace(tmp_path)
    files["source"] = tmp_path / "src" / "standalone.orc"
    files["source"].write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defworkflow run () -> Int 7))
""")
    args = ("--diagnostics-json",) if entry is None else (
        "--entry-workflow", entry
    )
    if entry is None:
        completed = _compile(files, extra=args)
        assert completed.returncode == 2
        diagnostic = json.loads(completed.stdout)["diagnostics"][0]
        assert diagnostic["code"] == "entry_workflow_required"
        assert diagnostic["path"] == str(files["source"])
        return

    completed = _compile(files, extra=args)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["entry_workflow"] == "entry::run"


@pytest.mark.parametrize(
    "producer_target",
    ["2.34", syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION],
)
def test_compiled_import_manifest_selects_old_and_evaluated_producers(
    tmp_path: Path, producer_target: str
) -> None:
    files = _write_import_workspace(tmp_path, producer_target)

    completed = _compile(files)

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    program = ClosedProgram.from_artifact(
        (Path(summary["build_root"]) / "closed_program.json").read_text()
    )
    assert program.tree["entry"] == "workflow:consumer/entry::run"
    assert "workflow:producer/entry::selected-run" in program.tree["definitions"]

    producer = files["source_root"] / "producer" / "entry.orc"
    producer.write_text("; producer-only comment\n\n" + producer.read_text())
    rebuilt = _compile(files)
    assert rebuilt.returncode == 0, rebuilt.stderr
    rebuilt_summary = json.loads(rebuilt.stdout)
    rebuilt_program = ClosedProgram.from_artifact(
        (Path(rebuilt_summary["build_root"]) / "closed_program.json").read_text()
    )
    assert rebuilt_summary["build_key"] != summary["build_key"]
    assert rebuilt_program.digest == program.digest
    assert rebuilt_program.sites == program.sites
    assert tuple(rebuilt_program.tree["definitions"]) == tuple(program.tree["definitions"])


def test_build_key_is_portable_and_raw_source_bytes_stay_out_of_program_digest(
    tmp_path: Path,
) -> None:
    first_files = _write_workspace(tmp_path / "here")
    first_summary, first_program, first_artifact = _build_state(first_files)
    second_files = _write_workspace(tmp_path / "elsewhere" / "deeper")
    second_summary, second_program, second_artifact = _build_state(second_files)

    assert (first_summary["build_key"], first_program.digest) == (
        second_summary["build_key"], second_program.digest
    )
    assert first_artifact != second_artifact

    original = first_files["source"].read_text()
    first_files["source"].write_text("; source-only comment\n\n" + original)
    edited_summary, edited_program, _artifact = _build_state(first_files)
    assert edited_summary["build_key"] != first_summary["build_key"]
    assert edited_program.digest == first_program.digest
    assert edited_program.sites == first_program.sites
    assert tuple(edited_program.tree["definitions"]) == tuple(first_program.tree["definitions"])


def test_package_copy_preserves_closed_program_identity(tmp_path: Path) -> None:
    files = _write_workspace(tmp_path / "workspace")
    original_summary, original_program, _artifact = _build_state(files)
    package_parent = tmp_path / "copied-package"
    package_parent.mkdir()
    shutil.copytree(Path(orchestrator.__file__).parents[1] / "orchestrator", package_parent / "orchestrator")

    copied_summary, copied_program, _artifact = _build_state(
        files, package_root=package_parent
    )

    assert (copied_summary["build_key"], copied_program.digest) == (
        original_summary["build_key"], original_program.digest
    )


def test_imported_specialized_callee_identity_survives_source_and_package_relocation(
    tmp_path: Path,
) -> None:
    original_files = _write_specialized_callee_workspace(tmp_path / "original")
    command = json.loads(original_files["commands"].read_text())["fetch"]
    assert (original_files["workspace"] / "probe.py").is_file()
    assert command["closure"] == ["probe.py"]
    original_summary, original_program, _artifact = _build_state(original_files)

    moved_files = _write_specialized_callee_workspace(tmp_path / "elsewhere" / "deeper")
    moved_summary, moved_program, _artifact = _build_state(moved_files)

    copied_package_root = tmp_path / "copied-package"
    copied_package_root.mkdir()
    shutil.copytree(
        Path(orchestrator.__file__).parents[1] / "orchestrator",
        copied_package_root / "orchestrator",
    )
    copied_summary, copied_program, _artifact = _build_state(
        original_files, package_root=copied_package_root
    )

    expected_identity = (original_summary["build_key"], original_program.digest)
    assert (moved_summary["build_key"], moved_program.digest) == expected_identity
    assert (copied_summary["build_key"], copied_program.digest) == expected_identity
    assert moved_program.sites == original_program.sites == copied_program.sites
    assert tuple(moved_program.tree["definitions"]) == tuple(original_program.tree["definitions"])
    assert tuple(copied_program.tree["definitions"]) == tuple(original_program.tree["definitions"])


def test_canonical_configuration_controls_digest_and_key(tmp_path: Path) -> None:
    files = _write_workspace(tmp_path)
    summary, program, _artifact = _build_state(files)
    command_manifest = json.loads(files["commands"].read_text())
    command_manifest["probe_revise"]["closure"].append("./probe_revise.py")
    files["commands"].write_text(json.dumps(command_manifest, indent=4))
    normalized_summary, normalized_program, _artifact = _build_state(files)
    assert (normalized_summary["build_key"], normalized_program.digest) == (
        summary["build_key"], program.digest
    )

    reordered = {"probe_revise": dict(reversed(list(command_manifest["probe_revise"].items())))}
    files["commands"].write_text(json.dumps(reordered, separators=(",", ":")))
    reordered_summary, reordered_program, _artifact = _build_state(files)
    assert (reordered_summary["build_key"], reordered_program.digest) == (
        summary["build_key"], program.digest
    )

    command_manifest["probe_revise"]["closure"] = ["other.py"]
    files["commands"].write_text(json.dumps(command_manifest))
    changed_closure_summary, changed_closure, _artifact = _build_state(files)
    assert changed_closure_summary["build_key"] != summary["build_key"]
    assert changed_closure.digest != program.digest

    command_manifest["probe_revise"]["closure"] = ["other.py"]
    command_manifest["probe_revise"]["stable_command"] = ["python", "other.py"]
    source = files["source"].read_text()
    files["source"].write_text(source.replace('("python" "probe_revise.py"', '("python" "other.py"'))
    files["commands"].write_text(json.dumps(command_manifest))
    changed_command_summary, changed_command, _artifact = _build_state(files)
    assert changed_command_summary["build_key"] != summary["build_key"]
    assert changed_command.digest != program.digest

    command_manifest["probe_revise"]["closure"] = ["probe_revise.py"]
    command_manifest["probe_revise"]["stable_command"] = ["python", "probe_revise.py"]
    files["source"].write_text(source)
    files["commands"].write_text(json.dumps(command_manifest))
    files["workspace"].joinpath("probe_revise.py").write_text("print('changed bytes')\n")
    closure_bytes_summary, closure_bytes, _artifact = _build_state(files)
    assert (closure_bytes_summary["build_key"], closure_bytes.digest) == (
        summary["build_key"], program.digest
    )


def test_unused_command_provider_and_prompt_rows_are_part_of_identity(tmp_path: Path) -> None:
    files = _write_workspace(tmp_path)
    baseline, program, _artifact = _build_state(files)

    providers = json.loads(files["providers"].read_text())
    providers["unused_provider"] = "provider:unused"
    files["providers"].write_text(json.dumps(providers))
    provider_summary, provider_program, _artifact = _build_state(files)
    assert provider_summary["build_key"] != baseline["build_key"]
    assert provider_program.digest != program.digest

    prompts = json.loads(files["prompts"].read_text())
    prompts["unused_prompt"] = "asset_file:unused.md"
    files["prompts"].write_text(json.dumps(prompts))
    prompt_summary, prompt_program, _artifact = _build_state(files)
    assert prompt_summary["build_key"] != provider_summary["build_key"]
    assert prompt_program.digest != provider_program.digest

    commands = json.loads(files["commands"].read_text())
    commands["unused_boundary"] = {
        "kind": "external_tool",
        "stable_command": ["python", "unused.py"],
        "closure": ["unused.py"],
    }
    (files["workspace"] / "unused.py").write_text("print('unused boundary fixture')\n")
    assert (files["workspace"] / "unused.py").is_file()
    assert commands["unused_boundary"]["closure"] == ["unused.py"]
    files["commands"].write_text(json.dumps(commands))
    command_summary, command_program, _artifact = _build_state(files)
    assert command_summary["build_key"] != prompt_summary["build_key"]
    assert command_program.digest != prompt_program.digest

    commands["unused_boundary"].update({
        "kind": "certified_adapter",
        "input_contract": {"type": "object"},
        "output_type_name": "Int",
        "effects": ["structured_result"],
        "path_safety": {"kind": "workspace_relpath"},
        "source_map_behavior": "step",
        "fixture_ids": ["unused_ok"],
        "negative_fixture_ids": ["unused_bad"],
        "behavior_class": "structured_result",
        "input_signature": [
            {"name": "n", "type_name": "Int", "required": True, "transport_key": "n"}
        ],
        "artifact_contracts": ["unused_contract"],
        "state_writes": [],
        "error_codes": ["unused_error"],
        "owner_module": "unused/module",
        "replacement_path": None,
        "invocation_protocol": "json_object_positional_arg",
    })
    files["commands"].write_text(json.dumps(commands))
    kind_summary, kind_program, _artifact = _build_state(files)
    assert kind_summary["build_key"] != command_summary["build_key"]
    assert kind_program.digest != command_program.digest


@pytest.mark.parametrize("shape", ["specialized_import", "path_run_ref", "let_proc", "bound_capture"])
def test_source_only_comments_preserve_specialized_closed_programs(
    tmp_path: Path, shape: str
) -> None:
    files = _write_workspace(tmp_path)
    source = files["source"]
    target = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
    if shape == "specialized_import":
        helper = files["source_root"] / "lib" / "generic.orc"
        helper.parent.mkdir(parents=True)
        helper.write_text(f'''(workflow-lisp (:language "0.1")
  (:target-dsl "{target}")
  (defmodule lib/generic) (export identity)
  (defproc identity :forall (T) ((value T)) -> T :effects () :lowering inline value))''')
        source.write_text(f'''(workflow-lisp (:language "0.1")
  (:target-dsl "{target}")
  (defmodule grt/entry) (import lib/generic :as generic :only (identity))
  (export run)
  (defworkflow run () -> Int (generic.identity 7)))''')
    elif shape == "path_run_ref":
        source.write_text(f'''(workflow-lisp (:language "0.1")
  (:target-dsl "{target}")
  (defmodule grt/entry) (export run)
  (defworkflow run () -> Int
    (let* ((child (run-ref
      :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
      :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
      :policy (:environment :deterministic-effect-free :setup ())))) 0)))''')
    elif shape == "let_proc":
        source.write_text(f'''(workflow-lisp (:language "0.1")
  (:target-dsl "{target}")
  (defmodule grt/entry) (export run)
  (defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int
    :effects () :lowering inline (hook value))
  (defworkflow run ((input Int)) -> Int
    (let* ((fixed 7))
      (let-proc (local ((value Int)) -> Int :captures (fixed) (+ value fixed))
        (apply-int (proc-ref local) input)))))''')
    else:
        source.write_text(f'''(workflow-lisp (:language "0.1")
  (:target-dsl "{target}")
  (defmodule grt/entry) (export run)
  (defproc helper ((fixed Int) (x Int)) -> Int :effects () :lowering inline (+ fixed x))
  (defproc invoke ((runner ProcRef[Int -> Int]) (x Int)) -> Int
    :effects () :lowering inline (runner x))
  (defworkflow run ((x Int)) -> Int
    (invoke (bind-proc (proc-ref helper) :fixed x) x)))''')

    original_summary, original_program, _artifact = _build_state(files)
    original_source = source.read_text()
    source.write_text("; a source-only comment\n\n" + original_source)
    edited_summary, edited_program, _artifact = _build_state(files)

    assert edited_summary["build_key"] != original_summary["build_key"]
    assert edited_program.digest == original_program.digest
    assert edited_program.sites == original_program.sites
    assert tuple(edited_program.tree["definitions"]) == tuple(original_program.tree["definitions"])


def _build_request(files: dict[str, Path]) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=files["source"],
        source_roots=(files["source_root"],),
        provider_externs_path=files["providers"],
        prompt_externs_path=files["prompts"],
        imported_workflow_bundles_path=files.get("imports"),
        command_boundaries_path=files["commands"],
        workspace_root=files["workspace"],
    )


def _plain_json(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    return value


def _independent_build_key(recipe: dict[str, object]) -> str:
    encoded = json.dumps(
        _plain_json(recipe),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def test_imported_snapshot_configuration_and_source_contribute_to_build_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.workflow_lisp.closed import artifact as artifact_module

    def clear_configuration(files: dict[str, Path]) -> None:
        for name in ("commands", "providers", "prompts"):
            files[name].write_text("{}")

    raw_files = _write_transitive_import_workspace(tmp_path / "raw")
    clear_configuration(raw_files)
    recipes: list[dict[str, object]] = []
    original_key = artifact_module.closed_build_key

    def record_recipe(**kwargs):
        recipes.append(_plain_json(kwargs))
        return original_key(**kwargs)

    monkeypatch.setattr(artifact_module, "closed_build_key", record_recipe)
    raw_result = artifact_module.build_closed_program_bundle(_build_request(raw_files))
    raw_recipe = recipes[-1]
    assert raw_result.build_key == _independent_build_key(raw_recipe)
    assert set(raw_recipe["imported_programs"]) == {"selected-run", "unused-run"}
    producer = raw_recipe["imported_programs"]["selected-run"]
    assert producer["entry_workflow"] == "producer/entry::selected-run"
    assert set(producer["source_file_digests"]) == {
        "producer/entry",
        "producer/helper",
    }
    assert producer["source_file_digests"]["producer/entry"] == hashlib.sha256(
        raw_files["producer"].read_bytes()
    ).hexdigest()
    assert producer["source_file_digests"]["producer/helper"] == hashlib.sha256(
        raw_files["helper"].read_bytes()
    ).hexdigest()
    empty_configuration = {"commands": {}, "providers": {}, "prompts": {}}
    assert producer["configuration"] == empty_configuration
    assert producer["source_module_configurations"] == {
        "producer/helper": empty_configuration,
    }

    canonical_files = _write_transitive_import_workspace(
        tmp_path / "relocated" / "deeper",
        selected_entry="producer/entry::selected-run",
    )
    clear_configuration(canonical_files)
    canonical_result = artifact_module.build_closed_program_bundle(
        _build_request(canonical_files)
    )
    assert (canonical_result.build_key, canonical_result.program.digest) == (
        raw_result.build_key,
        raw_result.program.digest,
    )

    changed_entry_files = _write_transitive_import_workspace(
        tmp_path / "changed-entry",
        selected_entry="alternate-run",
    )
    clear_configuration(changed_entry_files)
    changed_entry = artifact_module.build_closed_program_bundle(
        _build_request(changed_entry_files)
    )
    assert changed_entry.build_key != raw_result.build_key
    assert changed_entry.program.digest != raw_result.program.digest

    raw_files["helper"].write_text(
        "; producer helper comment\n\n" + raw_files["helper"].read_text()
    )
    comment_result = artifact_module.build_closed_program_bundle(
        _build_request(raw_files)
    )
    assert comment_result.build_key != raw_result.build_key
    assert comment_result.program.digest == raw_result.program.digest
    assert comment_result.program.sites == raw_result.program.sites
    assert tuple(comment_result.program.tree["definitions"]) == tuple(
        raw_result.program.tree["definitions"]
    )

    semantic_helper = raw_files["helper"].read_text().replace(
        "(+ value 1)", "(+ value 2)"
    )
    raw_files["helper"].write_text(semantic_helper)
    semantic_result = artifact_module.build_closed_program_bundle(
        _build_request(raw_files)
    )
    assert semantic_result.build_key != comment_result.build_key
    assert semantic_result.program.digest != comment_result.program.digest
    assert semantic_result.program.sites == comment_result.program.sites
    assert tuple(semantic_result.program.tree["definitions"]) == tuple(
        comment_result.program.tree["definitions"]
    )

    unused_source = raw_files["unused_producer"].read_text()
    raw_files["unused_producer"].write_text(unused_source.replace("-> Int 9", "-> Int 10"))
    unused_producer = artifact_module.build_closed_program_bundle(
        _build_request(raw_files)
    )
    assert unused_producer.build_key != semantic_result.build_key

    commands = json.loads(raw_files["commands"].read_text())
    commands["unused_imported_scope"] = {
        "kind": "external_tool",
        "stable_command": ["python", "unused_imported_scope.py"],
        "closure": ["unused_imported_scope.py"],
    }
    (raw_files["workspace"] / "unused_imported_scope.py").write_text(
        "print('declared but unused')\n"
    )
    raw_files["commands"].write_text(json.dumps(commands))
    unused_configuration = artifact_module.build_closed_program_bundle(
        _build_request(raw_files)
    )
    assert unused_configuration.build_key != unused_producer.build_key
    assert unused_configuration.program.digest != unused_producer.program.digest
    expected_unused_command = {
        "kind": "external_tool",
        "name": "unused_imported_scope",
        "stable_command": ["python", "unused_imported_scope.py"],
        "must_not_repeat": False,
        "closure": [{"base": "workspace", "path": "unused_imported_scope.py"}],
        "retirement_class": None,
        "retirement_label": None,
        "replacement_surface": None,
        "bridge_owner": None,
        "expiry_condition": None,
        "evidence_refs": [],
        "retirement_status": None,
    }
    expected_configuration = {
        "commands": {"unused_imported_scope": expected_unused_command},
        "providers": {},
        "prompts": {},
    }
    final_producer = recipes[-1]["imported_programs"]["selected-run"]
    assert final_producer["source_module_configurations"] == {
        "producer/helper": expected_configuration,
    }


def test_fourth_manifest_build_keeps_old_and_evaluated_producer_bodies(
    tmp_path: Path,
) -> None:
    files = _write_transitive_import_workspace(tmp_path)
    source = files["source"].read_text()
    files["source"].write_text(source.replace(
        "(defworkflow run () -> Int (call selected-run))",
        """(defworkflow run () -> Int
    (let* ((current (call selected-run))
           (legacy (call unused-run)))
      (+ current legacy)))""",
    ))

    summary, program, artifact = _build_state(files)

    assert summary["build_key"] == Path(summary["build_root"]).name
    restored = ClosedProgram.from_artifact(artifact.decode("utf-8"))
    assert (restored.tree, restored.sites, restored.digest) == (
        program.tree,
        program.sites,
        program.digest,
    )
    definitions = program.tree["definitions"]
    evaluated = definitions["workflow:producer/entry::selected-run"]
    legacy = definitions["workflow:unused/entry::run"]
    assert evaluated["key"][:3] == ["producer/entry", "workflow", "selected-run"]
    assert legacy["key"][:3] == ["unused/entry", "workflow", "run"]

    # The new producer is compiled from its typed 2.35 source and its inline
    # helper is retained as executable body data after the CLI build/readback.
    body = evaluated["body"]
    first = body
    assert first["k"] == "let" and first["value"]["k"] == "lit"
    assert first["value"]["v"] == 6
    second = first["body"]
    assert second["k"] == "let" and second["value"]["k"] == "name"
    assert second["value"]["n"] == first["name"]
    third = second["body"]
    assert third["k"] == "let" and third["value"]["k"] == "op"
    assert third["value"]["payload"]["expr"]["operator"] == "+"
    assert [argument["k"] for argument in third["value"]["args"]] == ["name", "lit"]
    assert third["value"]["args"][0]["n"] == second["name"]
    assert third["value"]["args"][1]["v"] == 1
    assert third["body"]["k"] == "halt"
    assert third["body"]["value"]["n"] == third["name"]
    assert not [node for node in _closed_ast_nodes(body) if node.get("k") == "call"]

    # The source-produced old 2.34 bundle keeps its original literal body.
    assert legacy["body"]["k"] == "halt"
    assert legacy["body"]["value"]["k"] == "lit"
    assert legacy["body"]["value"]["v"] == 9

    # Both imports are actually selected by the consumer, in authored order.
    entry = program.tree["body"]
    current, previous = entry, entry["body"]
    assert current["k"] == previous["k"] == "let"
    assert current["name"] == "current" and previous["name"] == "legacy"
    assert current["value"]["callee"] == "workflow:producer/entry::selected-run"
    assert previous["value"]["callee"] == "workflow:unused/entry::run"
    total = previous["body"]
    assert total["k"] == "let" and total["value"]["k"] == "op"
    assert total["value"]["payload"]["expr"]["operator"] == "+"
    assert [argument["n"] for argument in total["value"]["args"]] == [
        current["name"], previous["name"]
    ]


def _closed_ast_nodes(value):
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    return tuple(_ast_nodes(value))


def test_imported_producer_key_uses_the_consumed_source_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.workflow_lisp.closed import artifact as artifact_module

    files = _write_transitive_import_workspace(tmp_path)
    original_helper = files["helper"].read_bytes()
    original_compile = artifact_module.compile_typed_program
    changed = False

    def compile_then_edit(*args, **kwargs):
        nonlocal changed
        typed = original_compile(*args, **kwargs)
        if typed.entry_module == "producer/entry" and not changed:
            files["helper"].write_bytes(original_helper + b"\n; after retained producer compile\n")
            changed = True
        return typed

    monkeypatch.setattr(artifact_module, "compile_typed_program", compile_then_edit)
    first = artifact_module.build_closed_program_bundle(_build_request(files))
    monkeypatch.setattr(artifact_module, "compile_typed_program", original_compile)
    second = artifact_module.build_closed_program_bundle(_build_request(files))

    assert changed
    assert first.build_key != second.build_key
    assert first.program.digest == second.program.digest


def test_injected_nonentry_configuration_changes_root_build_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace
    from unittest.mock import patch

    from orchestrator.workflow_lisp import compiler
    from orchestrator.workflow_lisp.closed import artifact as artifact_module

    files = _write_injected_source_graph(tmp_path)
    request = FrontendBuildRequest(
        source_path=files["source"],
        source_roots=(files["source_root"],),
        workspace_root=files["workspace"],
    )
    recipes: list[dict[str, object]] = []
    original_key = artifact_module.closed_build_key

    def record_recipe(**kwargs):
        recipes.append(_plain_json(kwargs))
        return original_key(**kwargs)

    monkeypatch.setattr(artifact_module, "closed_build_key", record_recipe)
    first = artifact_module.build_closed_program_bundle(request)
    name = "validate_review_findings_v1"
    registry = dict(compiler.STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME)
    registry[name] = replace(registry[name], closure=("adapters",))
    with patch.object(compiler, "STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME", registry):
        second = artifact_module.build_closed_program_bundle(request)

    first_scope = recipes[0]["source_module_configurations"]["helper"]
    second_scope = recipes[1]["source_module_configurations"]["helper"]
    assert recipes[0]["command_boundary_manifest"] == {}
    assert "validate_review_findings_v1" in first_scope["commands"]
    assert first_scope["commands"] != second_scope["commands"]
    assert first.build_key != second.build_key
    assert first.program.digest != second.program.digest


def test_unused_injected_configuration_does_not_change_build_identity(
    tmp_path: Path,
) -> None:
    from dataclasses import replace
    from unittest.mock import patch

    from orchestrator.workflow_lisp import compiler
    from orchestrator.workflow_lisp.closed import artifact as artifact_module

    files = _write_workspace(tmp_path)
    request = _build_request(files)
    first = artifact_module.build_closed_program_bundle(request)
    name = "validate_review_findings_v1"
    registry = dict(compiler.STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME)
    registry[name] = replace(registry[name], closure=("adapters",))
    with patch.object(compiler, "STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME", registry):
        second = artifact_module.build_closed_program_bundle(request)

    assert (second.build_key, second.program.digest) == (
        first.build_key,
        first.program.digest,
    )


def test_injected_nonentry_configuration_changes_imported_producer_contribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace
    from unittest.mock import patch

    from orchestrator.workflow_lisp import compiler
    from orchestrator.workflow_lisp.closed import artifact as artifact_module

    files = _write_injected_import_workspace(tmp_path)
    request = _build_request(files)
    recipes: list[dict[str, object]] = []
    original_key = artifact_module.closed_build_key

    def record_recipe(**kwargs):
        recipes.append(_plain_json(kwargs))
        return original_key(**kwargs)

    monkeypatch.setattr(artifact_module, "closed_build_key", record_recipe)
    first = artifact_module.build_closed_program_bundle(request)
    name = "validate_review_findings_v1"
    registry = dict(compiler.STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME)
    registry[name] = replace(registry[name], closure=("adapters",))
    with patch.object(compiler, "STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME", registry):
        second = artifact_module.build_closed_program_bundle(request)

    first_producer = recipes[0]["imported_programs"]["selected-run"]
    second_producer = recipes[1]["imported_programs"]["selected-run"]
    first_scope = first_producer["source_module_configurations"]["producer/helper"]
    second_scope = second_producer["source_module_configurations"]["producer/helper"]
    assert "validate_review_findings_v1" in first_scope["commands"]
    assert first_scope["commands"] != second_scope["commands"]
    assert first.build_key != second.build_key
    assert first.program.digest != second.program.digest


def test_recursive_imported_snapshot_contributions_include_leaf_module_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.workflow_lisp.closed import artifact as artifact_module
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program

    files = _write_workspace(tmp_path)
    source_root = files["source_root"]
    leaf_path = source_root / "leaf" / "entry.orc"
    leaf_path.parent.mkdir()
    leaf_path.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule leaf/entry)
  (export leaf-run)
  (defworkflow leaf-run () -> Int 3))
""")
    middle_path = source_root / "middle" / "entry.orc"
    middle_path.parent.mkdir()
    middle_path.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule middle/entry)
  (export selected-run)
  (defworkflow selected-run () -> Int (call leaf-run)))
""")
    consumer = source_root / "consumer" / "entry.orc"
    consumer.parent.mkdir()
    consumer.write_text(f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer/entry)
  (export run)
  (defworkflow run () -> Int (call selected-run)))
""")
    imports = tmp_path / "imports.json"
    imports.write_text(json.dumps({
        "selected-run": {"kind": "compiled", "path": "src/middle/entry.orc"}
    }))
    files.update({"source": consumer, "imports": imports})
    for name in ("commands", "providers", "prompts"):
        files[name].write_text("{}")

    def compile_leaf() -> object:
        return compile_typed_program(
            leaf_path,
            entry_workflow="leaf-run",
            source_roots=(source_root,),
            command_boundaries={},
            workspace_root=tmp_path,
        )

    def compile_middle(leaf: object) -> object:
        return compile_typed_program(
            middle_path,
            entry_workflow="selected-run",
            source_roots=(source_root,),
            command_boundaries={},
            imported_programs={"leaf-run": leaf},
            workspace_root=tmp_path,
        )

    leaf = compile_leaf()
    middle = compile_middle(leaf)
    recipes: list[dict[str, object]] = []
    original_key = artifact_module.closed_build_key

    def record_recipe(**kwargs):
        recipes.append(_plain_json(kwargs))
        return original_key(**kwargs)

    def retain_middle(_request, **_kwargs):
        return {}, {"selected-run": middle}

    monkeypatch.setattr(artifact_module, "closed_build_key", record_recipe)
    monkeypatch.setattr(artifact_module, "_load_closed_imports", retain_middle)
    first = artifact_module.build_closed_program_bundle(_build_request(files))
    middle_recipe = recipes[-1]["imported_programs"]["selected-run"]
    expected_leaf = {
        "entry_workflow": "leaf/entry::leaf-run",
        "target": TARGET,
        "source_file_digests": _plain_json(leaf.source_file_digests),
        "configuration": {"commands": {}, "providers": {}, "prompts": {}},
        "source_module_configurations": {},
        "imported_programs": {},
    }
    assert middle_recipe["entry_workflow"] == "middle/entry::selected-run"
    assert middle_recipe["imported_programs"] == {"leaf-run": expected_leaf}
    assert first.build_key == _independent_build_key(recipes[-1])

    changed_leaf_source = leaf_path.read_text().replace("-> Int 3", "-> Int 4")
    leaf_path.write_text(changed_leaf_source)
    changed_leaf = compile_leaf()
    middle = compile_middle(changed_leaf)
    second = artifact_module.build_closed_program_bundle(_build_request(files))
    assert second.build_key != first.build_key
    assert second.program.digest != first.program.digest
    assert recipes[-1]["imported_programs"]["selected-run"]["imported_programs"][
        "leaf-run"
    ]["source_file_digests"] == _plain_json(changed_leaf.source_file_digests)


def test_build_key_uses_the_compiler_retained_source_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.workflow_lisp.closed import artifact as artifact_module

    files = _write_workspace(tmp_path)
    original_compile = artifact_module.compile_typed_program
    mutated = False

    def compile_then_edit(*args, **kwargs):
        nonlocal mutated
        typed = original_compile(*args, **kwargs)
        if not mutated:
            files["source"].write_bytes(files["source"].read_bytes() + b"\n; after compile\n")
            mutated = True
        return typed

    monkeypatch.setattr(artifact_module, "compile_typed_program", compile_then_edit)
    first = artifact_module.build_closed_program_bundle(_build_request(files))
    monkeypatch.setattr(artifact_module, "compile_typed_program", original_compile)
    second = artifact_module.build_closed_program_bundle(_build_request(files))

    assert first.build_key != second.build_key
    assert first.program.digest == second.program.digest


@pytest.mark.parametrize("producer_target", ["2.34", syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION])
def test_imported_producer_peek_and_compile_share_a_separate_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, producer_target: str
) -> None:
    from orchestrator.workflow_lisp.closed import artifact as artifact_module
    from orchestrator.workflow_lisp.reader import SourceReadTrace

    files = _write_import_workspace(tmp_path, producer_target)
    producer = files["source_root"] / "producer" / "entry.orc"
    consumer_trace = SourceReadTrace()
    producer_traces: list[SourceReadTrace] = []
    trace_class = artifact_module.SourceReadTrace

    def make_producer_trace() -> SourceReadTrace:
        trace = trace_class()
        producer_traces.append(trace)
        return trace

    original_peek = artifact_module.entry_target_dsl_version
    changed = False

    def peek_then_edit(path: Path, *, source_read_trace: SourceReadTrace | None = None):
        nonlocal changed
        version = original_peek(path, source_read_trace=source_read_trace)
        if path.resolve() == producer.resolve() and not changed:
            producer.write_text("; producer changed after target peek\n\n" + producer.read_text())
            changed = True
        return version

    monkeypatch.setattr(artifact_module, "SourceReadTrace", make_producer_trace)
    monkeypatch.setattr(artifact_module, "entry_target_dsl_version", peek_then_edit)

    with pytest.raises(RuntimeError, match="changed during one compiler read trace"):
        artifact_module.build_closed_program_bundle(
            _build_request(files), source_read_trace=consumer_trace
        )

    assert changed
    assert len(producer_traces) == 1
    assert producer_traces[0] is not consumer_trace
    assert producer_traces[0].revision_conflict_paths == (producer.resolve(),)
    assert all(record.canonical_path != files["source"].resolve() for record in producer_traces[0].records)
    assert not (files["workspace"] / ".orchestrate" / "build").exists()


@pytest.mark.parametrize("producer_target", ["2.34", syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION])
def test_root_target_peek_and_selected_compile_share_a_fail_closed_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, producer_target: str
) -> None:
    from argparse import Namespace

    from orchestrator.cli.commands import compile as compile_module

    files = _write_workspace(tmp_path, target=producer_target)
    monkeypatch.chdir(files["workspace"])
    original_build = (
        compile_module.build_closed_program_bundle
        if producer_target == syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
        else compile_module.build_frontend_bundle
    )

    def mutate_after_peek(request, *, source_read_trace=None):
        files["source"].write_bytes(files["source"].read_bytes() + b"\n; concurrent edit\n")
        return original_build(request, source_read_trace=source_read_trace)

    target_builder_name = (
        "build_closed_program_bundle"
        if producer_target == syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
        else "build_frontend_bundle"
    )
    monkeypatch.setattr(compile_module, target_builder_name, mutate_after_peek)
    args = Namespace(
        workflow=str(files["source"]),
        source_root=[str(files["source_root"])],
        entry_workflow=None,
        provider_externs_file=str(files["providers"]),
        prompt_externs_file=str(files["prompts"]),
        imported_workflow_bundles_file=None,
        command_boundaries_file=str(files["commands"]),
        emit_executable_ir=[],
        emit_core_ast=[],
        emit_runtime_plan=[],
        emit_semantic_ir=[],
        emit_source_map=[],
        emit_debug_yaml=[],
        diagnostics_json=True,
    )

    with pytest.raises(RuntimeError, match="changed during one compiler read trace"):
        compile_module.compile_workflow(args)
    assert not (files["workspace"] / ".orchestrate" / "build").exists()
