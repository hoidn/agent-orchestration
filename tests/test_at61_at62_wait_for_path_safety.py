from orchestrator.fsq.wait import WaitFor, WaitForConfig


class TestAT61WaitForPathSafety:
    def test_at61_absolute_path_rejected(self, tmp_path):
        result = WaitFor(WaitForConfig(glob_pattern="/etc/passwd", workspace=str(tmp_path))).execute()
        assert result.exit_code == 2
        assert result.files == []
        assert result.error["type"] == "path_safety_error"
        assert result.error["context"]["glob_pattern"] == "/etc/passwd"

    def test_at61_parent_escape_rejected(self, tmp_path):
        result = WaitFor(WaitForConfig(glob_pattern="../outside/*.txt", workspace=str(tmp_path))).execute()
        assert result.exit_code == 2
        assert result.files == []
        assert result.error["type"] == "path_safety_error"
        assert result.error["context"]["glob_pattern"] == "../outside/*.txt"

    def test_at61_nested_parent_escape_rejected(self, tmp_path):
        result = WaitFor(WaitForConfig(glob_pattern="subdir/../../outside/*.txt", workspace=str(tmp_path))).execute()
        assert result.exit_code == 2
        assert result.files == []
        assert result.error["type"] == "path_safety_error"


class TestAT62WaitForSymlinkEscape:
    def test_at62_symlink_escape_excluded(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("private")
        (workspace / "linked.txt").symlink_to(outside)
        result = WaitFor(WaitForConfig(glob_pattern="*.txt", workspace=str(workspace),
            timeout_sec=1, poll_ms=10)).execute()
        assert result.exit_code == 124
        assert result.files == []
        assert result.timed_out is True
        assert outside.read_text() == "private"

    def test_at62_relative_paths_returned(self, tmp_path):
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "one.txt").write_text("one")
        (tmp_path / "nested" / "two.txt").write_text("two")
        result = WaitFor(WaitForConfig(glob_pattern="nested/*.txt", workspace=str(tmp_path), min_count=2, timeout_sec=1)).execute()
        assert result.exit_code == 0
        assert sorted(result.files) == ["nested/one.txt", "nested/two.txt"]

    def test_at62_symlink_within_workspace_allowed(self, tmp_path):
        (tmp_path / "target.txt").write_text("target")
        (tmp_path / "linked.txt").symlink_to(tmp_path / "target.txt")
        result = WaitFor(WaitForConfig(glob_pattern="*.txt", workspace=str(tmp_path), min_count=2)).execute()
        assert result.exit_code == 0
        assert sorted(result.files) == ["linked.txt", "target.txt"]
