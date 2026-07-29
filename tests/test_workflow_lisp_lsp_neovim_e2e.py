"""Repository-real Neovim evidence for the shipped LSP lifecycle."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
INVALID_SOURCE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "modules"
    / "invalid"
    / "path_mismatch"
    / "neurips"
    / "bad.orc"
)


WorkspaceEntry = tuple[str, bytes | str | None]


def _workspace_entries(root: Path) -> dict[str, WorkspaceEntry]:
    entries: dict[str, WorkspaceEntry] = {}

    def visit(directory: Path) -> None:
        with os.scandir(directory) as children:
            ordered_children = sorted(children, key=lambda child: child.name)
        for child in ordered_children:
            path = Path(child.path)
            relative_path = path.relative_to(root).as_posix()
            if child.is_symlink():
                entries[relative_path] = ("symlink", os.readlink(path))
            elif child.is_dir(follow_symlinks=False):
                entries[relative_path] = ("directory", None)
                visit(path)
            elif child.is_file(follow_symlinks=False):
                entries[relative_path] = ("regular_file", path.read_bytes())
            else:
                raise AssertionError(
                    f"unsupported workspace entry type: {relative_path}"
                )

    visit(root)
    return entries


def test_workspace_entry_snapshot_records_topology_without_following_symlinks(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "regular.txt").write_bytes(b"regular")
    (workspace / "empty").mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "unobserved.txt").write_bytes(b"outside")
    (workspace / "linked-file").symlink_to("regular.txt")
    (workspace / "linked-directory").symlink_to(external, target_is_directory=True)

    assert _workspace_entries(workspace) == {
        "empty": ("directory", None),
        "linked-directory": ("symlink", str(external)),
        "linked-file": ("symlink", "regular.txt"),
        "regular.txt": ("regular_file", b"regular"),
    }


def test_neovim_observes_current_diagnostics_and_one_save_progress_interval(
    tmp_path: Path,
) -> None:
    nvim = shutil.which("nvim")
    assert nvim is not None, "the L4 acceptance gate requires installed nvim"

    workspace = (tmp_path / "workspace").resolve()
    source_path = workspace / "neurips" / "bad.orc"
    source_path.parent.mkdir(parents=True)
    shutil.copy2(INVALID_SOURCE, source_path)
    initial_text = source_path.read_text(encoding="utf-8")
    saved_text = initial_text.replace(
        "  (defmodule other/place)\n",
        "  (defmodule neurips/bad)\n",
    )
    assert saved_text != initial_text
    before_entries = _workspace_entries(workspace)

    result_path = (tmp_path / "neovim-result.json").resolve()
    script_path = (tmp_path / "neovim-l4.lua").resolve()
    script_path.write_text(
        r"""
local result_path = assert(vim.env.ORC_NEOVIM_RESULT)
local source_path = assert(vim.env.ORC_NEOVIM_SOURCE)
local workspace = assert(vim.env.ORC_NEOVIM_WORKSPACE)
local python = assert(vim.env.ORC_NEOVIM_PYTHON)

local result = {
  create_events = {},
  progress_events = {},
  publish_events = {},
  sequence = {},
}

local function record(kind, payload)
  table.insert(result.sequence, {
    kind = kind,
    payload = vim.deepcopy(payload),
  })
end

local default_publish =
  assert(vim.lsp.handlers["textDocument/publishDiagnostics"])
local default_create =
  assert(vim.lsp.handlers["window/workDoneProgress/create"])
local default_progress = assert(vim.lsp.handlers["$/progress"])

local function wait_for(label, predicate)
  if not vim.wait(30000, predicate, 10) then
    error("timed out waiting for " .. label)
  end
end

local function write_result()
  vim.fn.writefile({ vim.json.encode(result) }, result_path)
end

local ok, failure = xpcall(function()
  vim.cmd("edit " .. vim.fn.fnameescape(source_path))
  local bufnr = vim.api.nvim_get_current_buf()
  vim.bo[bufnr].filetype = "workflow-lisp"

  local capabilities = vim.lsp.protocol.make_client_capabilities()
  capabilities.window = capabilities.window or {}
  capabilities.window.workDoneProgress = true

  local client_id = assert(vim.lsp.start({
    name = "workflow-lisp-l4-acceptance",
    cmd = { python, "-m", "orchestrator.lsp" },
    root_dir = workspace,
    capabilities = capabilities,
    init_options = {
      source_roots = { workspace },
    },
    handlers = {
      ["textDocument/publishDiagnostics"] = function(err, params, ctx, config)
        table.insert(result.publish_events, vim.deepcopy(params))
        record("publish", params)
        return default_publish(err, params, ctx, config)
      end,
      ["window/workDoneProgress/create"] = function(err, params, ctx, config)
        table.insert(result.create_events, vim.deepcopy(params))
        record("create", params)
        return default_create(err, params, ctx, config)
      end,
      ["$/progress"] = function(err, params, ctx, config)
        table.insert(result.progress_events, vim.deepcopy(params))
        record("progress", params)
        return default_progress(err, params, ctx, config)
      end,
    },
  }, { bufnr = bufnr }))
  result.client_id = client_id

  wait_for("initial invalid-source diagnostic", function()
    if #vim.diagnostic.get(bufnr) ~= 1 then
      return false
    end
    for _, publication in ipairs(result.publish_events) do
      if #publication.diagnostics == 1 then
        return true
      end
    end
    return false
  end)
  wait_for("initial progress settlement", function()
    for _, event in ipairs(result.progress_events) do
      if event.value.kind == "end" then
        return true
      end
    end
    return false
  end)
  result.initial_view_count = #vim.diagnostic.get(bufnr)
  for _, publication in ipairs(result.publish_events) do
    if #publication.diagnostics == 1 then
      result.initial_publish = vim.deepcopy(publication)
      break
    end
  end

  result.create_events = {}
  result.progress_events = {}
  result.publish_events = {}
  result.sequence = {}
  vim.api.nvim_buf_set_lines(
    bufnr,
    3,
    4,
    false,
    { "  (defmodule neurips/bad)" }
  )
  wait_for("dirty diagnostic clear", function()
    if #vim.diagnostic.get(bufnr) ~= 0 then
      return false
    end
    for _, publication in ipairs(result.publish_events) do
      if #publication.diagnostics == 0 then
        return true
      end
    end
    return false
  end)
  result.dirty_view_count = #vim.diagnostic.get(bufnr)
  result.dirty_publish =
    vim.deepcopy(result.publish_events[#result.publish_events])

  result.create_events = {}
  result.progress_events = {}
  result.publish_events = {}
  result.sequence = {}
  vim.cmd("write")
  wait_for("saved-source progress and current diagnostic result", function()
    local ended = false
    for _, event in ipairs(result.progress_events) do
      if event.value.kind == "end" then
        ended = true
      end
    end
    return #result.create_events == 1
      and ended
      and #result.publish_events > 0
      and #vim.diagnostic.get(bufnr) == 0
  end)
  vim.wait(200)
  result.post_save_view_count = #vim.diagnostic.get(bufnr)
  result.post_save_publish =
    vim.deepcopy(result.publish_events[#result.publish_events])
  vim.lsp.status()
  result.final_progress_status = vim.lsp.status()

  vim.lsp.stop_client(client_id)
  wait_for("language-server shutdown", function()
    return vim.lsp.get_client_by_id(client_id) == nil
  end)
end, debug.traceback)

if not ok then
  result.error = failure
end
write_result()
if ok then
  vim.cmd("qa!")
else
  vim.cmd("cquit 1")
end
""".strip()
        + "\n",
        encoding="utf-8",
    )

    environment = dict(os.environ)
    environment.update(
        {
            "ORC_NEOVIM_RESULT": str(result_path),
            "ORC_NEOVIM_SOURCE": str(source_path),
            "ORC_NEOVIM_WORKSPACE": str(workspace),
            "ORC_NEOVIM_PYTHON": sys.executable,
            "PYTHONPATH": os.pathsep.join(
                (
                    str(REPO_ROOT),
                    environment.get("PYTHONPATH", ""),
                )
            ).rstrip(os.pathsep),
        }
    )
    completed = subprocess.run(
        (
            nvim,
            "--clean",
            "--headless",
            "-n",
            "-u",
            "NONE",
            "-c",
            "lua dofile(vim.env.ORC_NEOVIM_SCRIPT)",
        ),
        cwd=workspace,
        env={**environment, "ORC_NEOVIM_SCRIPT": str(script_path)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=45,
        check=False,
    )
    assert result_path.is_file(), (
        f"Neovim produced no result; stdout={completed.stdout!r}; "
        f"stderr={completed.stderr!r}"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert completed.returncode == 0, (
        f"Neovim failed: {result.get('error')!r}; "
        f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
    )
    assert "error" not in result

    initial_publish = result["initial_publish"]
    assert initial_publish["uri"] == source_path.as_uri()
    assert len(initial_publish["diagnostics"]) == 1
    initial_diagnostic = initial_publish["diagnostics"][0]
    assert initial_diagnostic["code"] == "module_path_mismatch"
    assert initial_diagnostic["range"] == {
        "start": {"line": 3, "character": 2},
        "end": {"line": 3, "character": 25},
    }
    assert initial_diagnostic["data"] == {
        "diagnostic_kind": "validation",
        "phase": "syntax",
        "validation_pass": "module",
        "authority_layer": "frontend",
        "raw_span": {
            "path": str(source_path),
            "start": {"line": 4, "column": 3, "offset": 60},
            "end": {"line": 4, "column": 26, "offset": 83},
        },
        "form_path": ["workflow-lisp", "defmodule", "other/place"],
        "notes": [],
        "expansion_frames": [],
        "compile_entry_uri": source_path.as_uri(),
        "accepted_generation": 1,
    }
    assert result["initial_view_count"] == 1
    assert result["dirty_publish"] == {
        "uri": source_path.as_uri(),
        "diagnostics": [],
    }
    assert result["dirty_view_count"] == 0

    creates = result["create_events"]
    progress = result["progress_events"]
    assert len(creates) == 1
    assert [event["value"]["kind"] for event in progress] == ["begin", "end"]
    token = creates[0]["token"]
    assert [event["token"] for event in progress] == [token, token]
    assert progress[0]["value"]["cancellable"] is False
    assert "percentage" not in progress[0]["value"]
    assert [event["kind"] for event in result["sequence"]] == [
        "create",
        "progress",
        "publish",
        "progress",
    ]
    assert result["post_save_publish"] == {
        "uri": source_path.as_uri(),
        "diagnostics": [],
    }
    assert result["post_save_view_count"] == 0
    assert result["final_progress_status"] == ""

    after_entries = _workspace_entries(workspace)
    expected_after_entries = dict(before_entries)
    expected_after_entries["neurips/bad.orc"] = (
        "regular_file",
        saved_text.encode("utf-8"),
    )
    assert after_entries == expected_after_entries
    assert not (workspace / ".orchestrate").exists()
