#!/usr/bin/env python3
"""Mock LLM Agent for E2E testing - simulates a real LLM agent with visible I/O."""

import sys
import time
import json
import argparse
from datetime import datetime


def print_banner(title, char="="):
    """Print a visible banner."""
    width = 80
    print(char * width, file=sys.stderr)
    print(f"  {title}".ljust(width), file=sys.stderr)
    print(char * width, file=sys.stderr)
    sys.stderr.flush()


def mock_llm_agent():
    """Mock LLM agent that shows what it receives and generates."""

    parser = argparse.ArgumentParser(description='Mock LLM Agent')
    parser.add_argument('-p', '--prompt', help='Prompt (for argv mode)')
    parser.add_argument('--model', default='mock-model', help='Model name')
    parser.add_argument('--mode', default='auto', choices=['argv', 'stdin', 'auto'],
                       help='Input mode')
    parser.add_argument('--verbose', action='store_true', help='Verbose output to stderr')

    args = parser.parse_args()

    # Show agent startup
    if args.verbose:
        print_banner("🤖 MOCK LLM AGENT STARTED")
        print(f"  Mode: {args.mode}", file=sys.stderr)
        print(f"  Model: {args.model}", file=sys.stderr)
        print(f"  Time: {datetime.now().isoformat()}", file=sys.stderr)
        print("", file=sys.stderr)
        sys.stderr.flush()

    # Get the prompt
    prompt = None

    if args.prompt:
        # argv mode
        prompt = args.prompt
        if args.verbose:
            print_banner("📥 RECEIVED PROMPT (via argv)", "-")
            print(f"  Length: {len(prompt)} chars", file=sys.stderr)
            print("  Content:", file=sys.stderr)
            for line in prompt.splitlines():
                print(f"    {line}", file=sys.stderr)
            print("", file=sys.stderr)
            sys.stderr.flush()

    elif args.mode in ['stdin', 'auto']:
        # stdin mode
        if args.verbose:
            print_banner("⏳ READING PROMPT (via stdin)", "-")
            sys.stderr.flush()

        prompt = sys.stdin.read()

        if args.verbose:
            print_banner("📥 RECEIVED PROMPT (via stdin)", "-")
            print(f"  Length: {len(prompt)} chars", file=sys.stderr)
            print("  Content:", file=sys.stderr)
            for line in prompt.splitlines()[:20]:  # Show first 20 lines
                print(f"    {line}", file=sys.stderr)
            if prompt.count('\n') > 20:
                print(f"    ... ({prompt.count('\n') - 20} more lines)", file=sys.stderr)
            print("", file=sys.stderr)
            sys.stderr.flush()

    if not prompt:
        print("ERROR: No prompt received", file=sys.stderr)
        sys.exit(1)

    # Simulate processing time
    if args.verbose:
        print_banner("🔄 PROCESSING", "-")
        print("  Simulating LLM inference...", file=sys.stderr)
        sys.stderr.flush()

    time.sleep(0.5)  # Simulate thinking

    # Generate response based on prompt content
    response = generate_response(prompt, args.model)

    if args.verbose:
        print_banner("📤 GENERATING RESPONSE", "-")
        print(f"  Length: {len(response)} chars", file=sys.stderr)
        print("  Preview:", file=sys.stderr)
        for line in response.splitlines()[:10]:
            print(f"    {line}", file=sys.stderr)
        print("", file=sys.stderr)
        sys.stderr.flush()

    # Output the response to stdout (this is what the orchestrator captures)
    print(response)
    sys.stdout.flush()

    if args.verbose:
        print_banner("✅ MOCK LLM AGENT COMPLETED")
        sys.stderr.flush()

    sys.exit(0)


def generate_response(prompt: str, model: str) -> str:
    """Generate a mock response based on the prompt."""

    prompt_lower = prompt.lower()

    # Check for specific patterns in the prompt
    if "hello" in prompt_lower or "hi" in prompt_lower:
        return "Hello! I'm a mock LLM agent. I received your greeting and I'm responding appropriately."

    elif "list" in prompt_lower and "files" in prompt_lower:
        return """Here are the files I found:
- README.md
- main.py
- config.yaml
- tests/test_main.py
- docs/guide.md"""

    elif "count" in prompt_lower:
        return "1, 2, 3, 4, 5"

    elif "json" in prompt_lower:
        return json.dumps({
            "status": "success",
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "message": "This is a mock JSON response",
            "data": {
                "items": ["item1", "item2", "item3"],
                "count": 3
            }
        }, indent=2)

    elif "code" in prompt_lower or "function" in prompt_lower:
        return """def process_data(input_data):
    \"\"\"Process the input data and return results.\"\"\"
    result = []
    for item in input_data:
        if validate(item):
            result.append(transform(item))
    return result

print("Code generated successfully")"""

    elif "error" in prompt_lower or "fail" in prompt_lower:
        print("ERROR: Simulated error condition", file=sys.stderr)
        sys.exit(1)

    # Check for dependency injection markers
    if "# Dependencies" in prompt or "## Dependencies" in prompt:
        return f"""I can see you've provided dependencies in your prompt.

Prompt structure detected:
- Main prompt content: {len(prompt.splitlines())} lines
- Contains dependency injection: Yes
- Model: {model}

Here's my analysis of your request:
{prompt[:200]}...

Generated response: Task completed successfully with all dependencies considered."""

    # Default response
    return f"""Mock LLM Response
================

I received your prompt with {len(prompt)} characters and {len(prompt.splitlines())} lines.

Model: {model}
Timestamp: {datetime.now().isoformat()}

Your prompt mentioned these key topics:
{extract_topics(prompt)}

Here's my generated response:
This is a mock response that simulates what a real LLM would return.
The actual content would depend on the specific prompt, but I'm
demonstrating that I received and processed your input successfully.

Task completed."""


def extract_topics(prompt: str) -> str:
    """Extract potential topics from prompt."""
    # Simple keyword extraction
    keywords = []
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}

    words = prompt.lower().split()[:50]  # First 50 words
    for word in words:
        word = word.strip('.,!?;:')
        if len(word) > 4 and word not in common_words:
            keywords.append(word)

    if keywords:
        return "- " + "\n- ".join(keywords[:5])
    return "- General query"


if __name__ == "__main__":
    mock_llm_agent()