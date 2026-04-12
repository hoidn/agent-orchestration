import subprocess
from pathlib import Path

from scripts.workflow_prompt_map import collect_prompt_refs, render_markdown, workflow_files


def test_collect_prompt_refs_resolves_input_and_asset_paths(tmp_path: Path):
    repo = tmp_path
    workflow_dir = repo / "workflows" / "library"
    workflow_dir.mkdir(parents=True)
    (repo / "prompts" / "workflows").mkdir(parents=True)
    (workflow_dir / "prompts").mkdir()
    (workflow_dir / "rubrics").mkdir()
    (repo / "prompts" / "workflows" / "review.md").write_text(
        "review\n", encoding="utf-8"
    )
    (workflow_dir / "prompts" / "draft.md").write_text(
        "draft\n", encoding="utf-8"
    )
    (workflow_dir / "rubrics" / "rubric.md").write_text(
        "rubric\n", encoding="utf-8"
    )
    workflow = workflow_dir / "example.yaml"
    workflow.write_text(
        """
version: "2.7"
steps:
  - name: Draft
    provider: codex
    asset_file: prompts/draft.md
    asset_depends_on:
      - rubrics/rubric.md
  - name: Review
    provider: codex
    input_file: prompts/workflows/review.md
""",
        encoding="utf-8",
    )

    refs = collect_prompt_refs(repo, [workflow])

    assert [(ref.step_path, ref.field, ref.authored_path, ref.exists) for ref in refs] == [
        ("Draft", "asset_file", "prompts/draft.md", True),
        ("Draft", "asset_depends_on", "rubrics/rubric.md", True),
        ("Review", "input_file", "prompts/workflows/review.md", True),
    ]
    assert refs[0].resolved_path == workflow_dir / "prompts" / "draft.md"
    assert refs[1].resolved_path == workflow_dir / "rubrics" / "rubric.md"
    assert refs[2].resolved_path == repo / "prompts" / "workflows" / "review.md"


def test_collect_prompt_refs_walks_nested_control_flow(tmp_path: Path):
    repo = tmp_path
    workflow_dir = repo / "workflows" / "examples"
    prompt_dir = repo / "prompts"
    workflow_dir.mkdir(parents=True)
    prompt_dir.mkdir()
    for name in ["loop.md", "then.md", "else.md", "case.md", "for_each.md"]:
        (prompt_dir / name).write_text(name, encoding="utf-8")
    workflow = workflow_dir / "nested.yaml"
    workflow.write_text(
        """
version: "2.7"
steps:
  - name: Loop
    repeat_until:
      steps:
        - name: LoopPrompt
          provider: codex
          input_file: prompts/loop.md
  - name: Branch
    if:
      compare: {left: 1, op: eq, right: 1}
    then:
      steps:
        - name: ThenPrompt
          provider: codex
          input_file: prompts/then.md
    else:
      steps:
        - name: ElsePrompt
          provider: codex
          input_file: prompts/else.md
  - name: Route
    match:
      ref: inputs.decision
      cases:
        APPROVE:
          steps:
            - name: CasePrompt
              provider: codex
              input_file: prompts/case.md
  - name: Items
    for_each:
      items: [one]
      steps:
        - name: ForEachPrompt
          provider: codex
          input_file: prompts/for_each.md
""",
        encoding="utf-8",
    )

    refs = collect_prompt_refs(repo, [workflow])

    assert [ref.step_path for ref in refs] == [
        "Loop > LoopPrompt",
        "Branch > then > ThenPrompt",
        "Branch > else > ElsePrompt",
        "Route > case APPROVE > CasePrompt",
        "Items > ForEachPrompt",
    ]


def test_render_markdown_includes_missing_status(tmp_path: Path):
    repo = tmp_path
    workflow_dir = repo / "workflows" / "examples"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "missing.yaml"
    workflow.write_text(
        """
version: "1.1"
steps:
  - name: MissingPrompt
    provider: codex
    input_file: prompts/missing.md
""",
        encoding="utf-8",
    )

    refs = collect_prompt_refs(repo, [workflow])
    markdown = render_markdown(repo, refs)

    assert "`workflows/examples/missing.yaml`" in markdown
    assert "`prompts/missing.md`" in markdown
    assert "| no |" in markdown


def test_workflow_files_prefers_git_tracked_files(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    workflow_dir = tmp_path / "workflows" / "examples"
    workflow_dir.mkdir(parents=True)
    tracked = workflow_dir / "tracked.yaml"
    untracked = workflow_dir / "untracked.yaml"
    tracked.write_text('version: "1.1"\nsteps: []\n', encoding="utf-8")
    untracked.write_text('version: "1.1"\nsteps: []\n', encoding="utf-8")
    subprocess.run(
        ["git", "add", tracked.relative_to(tmp_path).as_posix()],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert workflow_files(tmp_path) == [tracked]
