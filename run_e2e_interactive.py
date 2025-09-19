#!/usr/bin/env python3
"""Interactive E2E test runner that shows real-time agent I/O."""

import os
import sys
import json
import tempfile
import subprocess
import threading
import time
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


def run_interactive_test():
    """Run an interactive E2E test with real-time output."""

    print_colored("\n" + "="*80, 'cyan', bold=True)
    print_colored("   🚀 INTERACTIVE E2E TEST WITH REAL-TIME AGENT I/O", 'cyan', bold=True)
    print_colored("="*80 + "\n", 'cyan', bold=True)

    # Get paths
    project_root = Path(__file__).parent
    mock_agent = project_root / "mock_llm_agent.py"
    orchestrate = project_root / "orchestrate"

    # Make mock agent executable
    if mock_agent.exists():
        os.chmod(mock_agent, 0o755)

    # Create temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "workflows").mkdir()
        (workspace / "prompts").mkdir()
        (workspace / "artifacts" / "agent").mkdir(parents=True)
        (workspace / "lib").mkdir()

        # Create some dependency files for injection
        print_colored("\n📁 Creating test files...", 'yellow')

        (workspace / "lib" / "config.yaml").write_text("""
model: gpt-4
temperature: 0.7
max_tokens: 1000
""")

        (workspace / "lib" / "instructions.md").write_text("""
# System Instructions

You are a helpful AI assistant.
Follow these guidelines:
1. Be concise
2. Be accurate
3. Be helpful
""")

        # Create prompt file
        prompt_content = """Please analyze the dependencies provided and generate a summary.

Focus on:
- Configuration settings
- System instructions
- Any patterns you notice

Respond with a structured analysis."""

        prompt_path = workspace / "prompts" / "analyze.md"
        prompt_path.write_text(prompt_content)

        print_colored(f"  ✓ Created prompt: {prompt_path.name}", 'green')
        print_colored(f"  ✓ Created dependencies: lib/config.yaml, lib/instructions.md", 'green')

        # Create workflow with dependency injection
        workflow_content = f"""
version: "1.1.1"
name: interactive_e2e_demo

providers:
  mock_llm:
    command: ["python", "{mock_agent}", "-p", "${{PROMPT}}", "--model", "${{model}}", "--verbose"]
    input_mode: argv
    defaults:
      model: "gpt-4-mock"

steps:
  - name: AnalyzeWithInjection
    provider: mock_llm
    input_file: prompts/analyze.md
    output_file: artifacts/agent/analysis.txt
    output_capture: text
    depends_on:
      required:
        - lib/*.yaml
        - lib/*.md
      inject:
        mode: content
        instruction: "Review these dependencies:"
        position: prepend

  - name: SimpleEcho
    command: echo "Step 2 - Processing complete"
    output_capture: text
"""

        workflow_path = workspace / "workflows" / "interactive.yaml"
        workflow_path.write_text(workflow_content)

        print_colored(f"  ✓ Created workflow: {workflow_path.name}\n", 'green')

        # Prepare orchestrator command
        cmd = [
            "python", str(orchestrate),
            "run", str(workflow_path),
            "--debug"  # Enable debug to see more details
        ]

        print_colored("🎬 Starting orchestrator with command:", 'magenta', bold=True)
        print_colored(f"   {' '.join(cmd)}\n", 'white')

        # Set up environment
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"  # Ensure unbuffered output

        # Run orchestrator with real-time output streaming
        process = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env
        )

        # Create output queues
        stdout_queue = Queue()
        stderr_queue = Queue()

        # Start threads to read output
        stdout_thread = threading.Thread(
            target=stream_output,
            args=(process.stdout, "[ORCH OUT]", 'blue', stdout_queue)
        )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, "[ORCH LOG]", 'yellow', stderr_queue)
        )

        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()

        # Collect output for analysis
        all_stderr = []
        run_id = None

        # Wait for process to complete
        while process.poll() is None:
            time.sleep(0.1)

            # Collect stderr for run_id extraction
            try:
                while True:
                    line = stderr_queue.get_nowait()
                    all_stderr.append(line)
                    if "Created new run:" in line:
                        run_id = line.split("Created new run:")[-1].strip()
            except Empty:
                pass

        # Wait for threads to finish
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        return_code = process.returncode

        print_colored("\n" + "="*80, 'cyan')

        if return_code == 0:
            print_colored("✅ ORCHESTRATOR COMPLETED SUCCESSFULLY", 'green', bold=True)
        else:
            print_colored(f"❌ ORCHESTRATOR FAILED (exit code: {return_code})", 'red', bold=True)

        # Show results
        if run_id:
            print_colored(f"\n📊 Run ID: {run_id}", 'magenta')

            # Check for prompt audit files (these show the actual prompts sent)
            logs_dir = workspace / ".orchestrate" / "runs" / run_id / "logs"
            if logs_dir.exists():
                print_colored("\n📝 ACTUAL PROMPTS SENT TO AGENT:", 'cyan', bold=True)

                prompt_files = list(logs_dir.glob("*.prompt.txt"))
                for pf in prompt_files:
                    print_colored(f"\n   File: {pf.name}", 'green')
                    print_colored("   " + "-"*40, 'white')
                    content = pf.read_text()
                    for line in content.splitlines()[:30]:  # Show first 30 lines
                        print_colored(f"   {line}", 'white')
                    if content.count('\n') > 30:
                        print_colored(f"   ... ({content.count('\n') - 30} more lines)", 'white')

            # Check for artifacts
            artifact_dir = workspace / "artifacts" / "agent"
            if artifact_dir.exists():
                print_colored("\n📦 GENERATED ARTIFACTS:", 'cyan', bold=True)

                for artifact in artifact_dir.glob("*"):
                    if artifact.is_file():
                        print_colored(f"\n   File: {artifact.name}", 'green')
                        print_colored("   " + "-"*40, 'white')
                        content = artifact.read_text()
                        for line in content.splitlines()[:20]:
                            print_colored(f"   {line}", 'white')

            # Check state
            state_file = workspace / ".orchestrate" / "runs" / run_id / "state.json"
            if state_file.exists():
                state = json.loads(state_file.read_text())
                print_colored("\n📈 FINAL STATE:", 'cyan', bold=True)
                print_colored(f"   Status: {state.get('status', 'unknown')}", 'green')
                print_colored(f"   Steps completed: {len(state.get('steps', {}))}", 'green')

                # Show step results
                for step_name, step_data in state.get('steps', {}).items():
                    exit_code = step_data.get('exit_code', 'N/A')
                    status_color = 'green' if exit_code == 0 else 'red'
                    print_colored(f"   - {step_name}: exit_code={exit_code}", status_color)

        print_colored("\n" + "="*80 + "\n", 'cyan')


def main():
    """Main entry point."""
    print_colored("\nThis test will show real-time agent I/O interaction.", 'white')
    print_colored("The mock agent will display what it receives and generates.\n", 'white')

    try:
        run_interactive_test()
    except KeyboardInterrupt:
        print_colored("\n\n⚠️  Test interrupted by user", 'yellow')
        sys.exit(1)
    except Exception as e:
        print_colored(f"\n\n❌ Error: {e}", 'red', bold=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()