#!/usr/bin/env python3
"""Run a REAL agent test with live output streaming."""

import os
import sys
import json
import tempfile
import subprocess
import threading
import time
import shutil
from pathlib import Path
from queue import Queue, Empty


def print_colored(text, color='reset', bold=False):
    """Print colored text to stderr."""
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'reset': '\033[0m',
        'bold': '\033[1m'
    }
    prefix = ''
    if bold:
        prefix += colors['bold']
    if color in colors:
        prefix += colors[color]
    print(f"{prefix}{text}{colors['reset']}", file=sys.stderr)
    sys.stderr.flush()


def stream_output(pipe, prefix, color, output_queue):
    """Stream output from a pipe with colored prefix."""
    for line in iter(pipe.readline, ''):
        if line:
            line = line.rstrip()
            print_colored(f"{prefix} {line}", color)
            output_queue.put(line)
    pipe.close()


def run_claude_test():
    """Run a test with REAL Claude agent."""

    print_colored("\n" + "="*80, 'cyan', bold=True)
    print_colored("   🤖 REAL CLAUDE AGENT TEST - LIVE I/O", 'cyan', bold=True)
    print_colored("="*80 + "\n", 'cyan', bold=True)

    # Check if Claude is available
    if not shutil.which("claude"):
        print_colored("❌ Claude CLI not found. Please install it first:", 'red', bold=True)
        print_colored("   npm install -g @anthropic-ai/claude-cli", 'yellow')
        return False

    project_root = Path(__file__).parent
    orchestrate = project_root / "orchestrate"

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "workflows").mkdir()
        (workspace / "prompts").mkdir()
        (workspace / "artifacts" / "architect").mkdir(parents=True)
        (workspace / "src").mkdir()

        # Create a real code file to analyze
        print_colored("📁 Creating test files...", 'yellow')

        code_file = workspace / "src" / "example.py"
        code_file.write_text("""
def calculate_fibonacci(n):
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

def main():
    for i in range(10):
        print(f"fib({i}) = {calculate_fibonacci(i)}")

if __name__ == "__main__":
    main()
""")

        # Create a REAL prompt for Claude
        prompt_content = """Analyze this Python code and provide:
1. A brief description of what it does
2. Performance analysis (time complexity)
3. One specific optimization suggestion with code

Please be concise but specific."""

        prompt_path = workspace / "prompts" / "analyze_code.md"
        prompt_path.write_text(prompt_content)

        print_colored(f"  ✓ Created code file: src/example.py", 'green')
        print_colored(f"  ✓ Created prompt: prompts/analyze_code.md", 'green')

        # Create workflow
        workflow_content = f"""
version: "1.1.1"
name: real_claude_test

providers:
  claude:
    command: ["claude", "-p", "${{PROMPT}}"]
    input_mode: argv

steps:
  - name: AnalyzeCode
    provider: claude
    input_file: prompts/analyze_code.md
    output_file: artifacts/architect/analysis.md
    output_capture: text
    depends_on:
      required:
        - src/example.py
      inject:
        mode: content
        instruction: "Here is the code to analyze:"
        position: append
"""

        workflow_path = workspace / "workflows" / "claude_real.yaml"
        workflow_path.write_text(workflow_content)

        print_colored(f"  ✓ Created workflow: {workflow_path.name}\n", 'green')

        # Run orchestrator
        cmd = [
            "python", str(orchestrate),
            "run", str(workflow_path),
            "--debug"  # This enables prompt audit logs
        ]

        print_colored("🎬 EXECUTING WORKFLOW WITH REAL CLAUDE:", 'magenta', bold=True)
        print_colored(f"   {' '.join(cmd)}\n", 'white')

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env
        )

        # Stream output
        stdout_queue = Queue()
        stderr_queue = Queue()

        stdout_thread = threading.Thread(
            target=stream_output,
            args=(process.stdout, "[STDOUT]", 'blue', stdout_queue)
        )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, "[ORCHEST]", 'yellow', stderr_queue)
        )

        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()

        all_stderr = []
        run_id = None

        while process.poll() is None:
            time.sleep(0.1)
            try:
                while True:
                    line = stderr_queue.get_nowait()
                    all_stderr.append(line)
                    if "Created new run:" in line:
                        run_id = line.split("Created new run:")[-1].strip()
            except Empty:
                pass

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        return_code = process.returncode

        print_colored("\n" + "="*80, 'cyan')

        if return_code == 0:
            print_colored("✅ WORKFLOW COMPLETED SUCCESSFULLY", 'green', bold=True)
        else:
            print_colored(f"❌ WORKFLOW FAILED (exit code: {return_code})", 'red', bold=True)

        # Show the ACTUAL prompt sent to Claude
        if run_id:
            logs_dir = workspace / ".orchestrate" / "runs" / run_id / "logs"

            print_colored("\n📤 ACTUAL PROMPT SENT TO CLAUDE:", 'cyan', bold=True)
            print_colored("="*80, 'cyan')

            prompt_file = logs_dir / "AnalyzeCode.prompt.txt"
            if prompt_file.exists():
                prompt_content = prompt_file.read_text()
                for line in prompt_content.splitlines():
                    print_colored(line, 'white')

            print_colored("\n📥 CLAUDE'S RESPONSE:", 'cyan', bold=True)
            print_colored("="*80, 'cyan')

            # Show Claude's response
            artifact_file = workspace / "artifacts" / "architect" / "analysis.md"
            if artifact_file.exists():
                response = artifact_file.read_text()
                for line in response.splitlines():
                    print_colored(line, 'green')

            # Also check stdout log
            stdout_file = logs_dir / "AnalyzeCode.stdout"
            if stdout_file.exists() and not artifact_file.exists():
                response = stdout_file.read_text()
                for line in response.splitlines():
                    print_colored(line, 'green')

        print_colored("\n" + "="*80 + "\n", 'cyan')
        return return_code == 0


def run_codex_test():
    """Run a test with REAL Codex agent."""

    print_colored("\n" + "="*80, 'cyan', bold=True)
    print_colored("   🤖 REAL CODEX AGENT TEST - LIVE I/O", 'cyan', bold=True)
    print_colored("="*80 + "\n", 'cyan', bold=True)

    # Check if Codex is available
    if not shutil.which("codex"):
        print_colored("❌ Codex CLI not found. Please install it first:", 'red', bold=True)
        print_colored("   Instructions at: https://github.com/anthropics/codex", 'yellow')
        return False

    project_root = Path(__file__).parent
    orchestrate = project_root / "orchestrate"

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "workflows").mkdir()
        (workspace / "prompts").mkdir()
        (workspace / "artifacts" / "engineer").mkdir(parents=True)

        # Create prompt for Codex
        prompt_content = """Write a Python function that:
1. Takes a list of numbers
2. Returns the top 3 most frequent numbers
3. Include a simple test case

Be concise and use modern Python."""

        prompt_path = workspace / "prompts" / "generate_code.md"
        prompt_path.write_text(prompt_content)

        print_colored(f"  ✓ Created prompt: prompts/generate_code.md", 'green')

        # Create workflow (stdin mode for Codex)
        workflow_content = f"""
version: "1.1"
name: real_codex_test

providers:
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"]
    input_mode: stdin

steps:
  - name: GenerateCode
    provider: codex
    input_file: prompts/generate_code.md
    output_file: artifacts/engineer/solution.py
    output_capture: text
"""

        workflow_path = workspace / "workflows" / "codex_real.yaml"
        workflow_path.write_text(workflow_content)

        print_colored(f"  ✓ Created workflow: {workflow_path.name}\n", 'green')

        # Run orchestrator
        cmd = [
            "python", str(orchestrate),
            "run", str(workflow_path),
            "--debug"
        ]

        print_colored("🎬 EXECUTING WORKFLOW WITH REAL CODEX:", 'magenta', bold=True)
        print_colored(f"   {' '.join(cmd)}\n", 'white')
        print_colored("📤 PROMPT BEING SENT (via stdin):", 'cyan', bold=True)
        print_colored("-"*40, 'cyan')
        for line in prompt_content.splitlines():
            print_colored(f"  {line}", 'white')
        print_colored("-"*40 + "\n", 'cyan')

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env
        )

        # Stream output
        stdout_queue = Queue()
        stderr_queue = Queue()

        stdout_thread = threading.Thread(
            target=stream_output,
            args=(process.stdout, "[STDOUT]", 'blue', stdout_queue)
        )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, "[ORCHEST]", 'yellow', stderr_queue)
        )

        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()

        all_stderr = []
        run_id = None

        while process.poll() is None:
            time.sleep(0.1)
            try:
                while True:
                    line = stderr_queue.get_nowait()
                    all_stderr.append(line)
                    if "Created new run:" in line:
                        run_id = line.split("Created new run:")[-1].strip()
            except Empty:
                pass

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        return_code = process.returncode

        print_colored("\n" + "="*80, 'cyan')

        if return_code == 0:
            print_colored("✅ WORKFLOW COMPLETED SUCCESSFULLY", 'green', bold=True)
        else:
            print_colored(f"❌ WORKFLOW FAILED (exit code: {return_code})", 'red', bold=True)

        # Show Codex's response
        if run_id:
            print_colored("\n📥 CODEX'S GENERATED CODE:", 'cyan', bold=True)
            print_colored("="*80, 'cyan')

            artifact_file = workspace / "artifacts" / "engineer" / "solution.py"
            if artifact_file.exists():
                response = artifact_file.read_text()
                for line in response.splitlines():
                    print_colored(line, 'green')

        print_colored("\n" + "="*80 + "\n", 'cyan')
        return return_code == 0


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Run REAL agent E2E test with live output')
    parser.add_argument(
        '--agent',
        choices=['claude', 'codex'],
        default='claude',
        help='Which agent to test (default: claude)'
    )

    args = parser.parse_args()

    if args.agent == 'claude':
        success = run_claude_test()
    else:
        success = run_codex_test()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()