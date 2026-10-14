from orchestrator.exec import CaptureMode, StepExecutor


class TestCommandOutputCaptureConversion:
    def test_at1_at2_at45_at52_command_text_mode(self, tmp_path):
        result = StepExecutor(tmp_path).execute_command("text", ["printf", "test text output\n"],
            output_capture=CaptureMode("text"))
        assert result.exit_code == 0
        assert result.capture_result.mode is CaptureMode.TEXT
        assert result.to_state_dict()["output"] == "test text output\n"

    def test_at1_at2_at45_at52_command_lines_mode(self, tmp_path):
        result = StepExecutor(tmp_path).execute_command("lines", ["printf", "line1\nline2\nline3\n"],
            output_capture=CaptureMode("lines"))
        assert result.exit_code == 0
        assert result.capture_result.mode is CaptureMode.LINES
        assert result.to_state_dict()["lines"] == ["line1", "line2", "line3"]
        assert "output" not in result.to_state_dict()

    def test_at1_at2_at45_at52_command_json_mode(self, tmp_path):
        result = StepExecutor(tmp_path).execute_command("json", ["printf", '{"key":"value","number":42}'],
            output_capture=CaptureMode("json"))
        assert result.exit_code == 0
        assert result.capture_result.mode is CaptureMode.JSON
        assert result.to_state_dict()["json"] == {"key": "value", "number": 42}
        assert "output" not in result.to_state_dict()

    def test_at1_at2_at45_at52_command_default_text_mode(self, tmp_path):
        result = StepExecutor(tmp_path).execute_command("default", ["printf", "default text output\n"])
        assert result.exit_code == 0
        assert result.capture_result.mode is CaptureMode.TEXT
        assert result.to_state_dict()["output"] == "default text output\n"
