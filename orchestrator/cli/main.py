"""Main CLI entry point for orchestrator."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .commands import run_workflow


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the orchestrator CLI."""
    parser = argparse.ArgumentParser(
        prog='orchestrate',
        description='Multi-Agent Orchestration System'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run a workflow')
    run_parser.add_argument(
        'workflow',
        type=str,
        help='Path to workflow YAML file'
    )
    run_parser.add_argument(
        '--context',
        action='append',
        metavar='KEY=VALUE',
        help='Context variables (can be specified multiple times)'
    )
    run_parser.add_argument(
        '--context-file',
        type=str,
        help='Path to JSON file containing context variables'
    )
    run_parser.add_argument(
        '--clean-processed',
        action='store_true',
        help='Empty processed directory before run'
    )
    run_parser.add_argument(
        '--archive-processed',
        type=str,
        metavar='DEST',
        help='Archive processed directory to destination on success'
    )
    run_parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    run_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate without execution'
    )
    run_parser.add_argument(
        '--backup-state',
        action='store_true',
        help='Backup state before each step'
    )
    run_parser.add_argument(
        '--state-dir',
        type=str,
        help='Override default state directory'
    )
    run_parser.add_argument(
        '--on-error',
        choices=['stop', 'continue'],
        default='stop',
        help='Error handling strategy'
    )
    run_parser.add_argument(
        '--max-retries',
        type=int,
        default=0,
        help='Maximum retry attempts'
    )
    run_parser.add_argument(
        '--retry-delay',
        type=int,
        default=1000,
        help='Retry delay in milliseconds'
    )
    run_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress non-error output'
    )
    run_parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    run_parser.add_argument(
        '--log-level',
        choices=['debug', 'info', 'warn', 'error'],
        default='info',
        help='Set log level'
    )

    # Resume command (minimal for now)
    resume_parser = subparsers.add_parser('resume', help='Resume a workflow run')
    resume_parser.add_argument(
        'run_id',
        type=str,
        help='Run ID to resume'
    )
    resume_parser.add_argument(
        '--repair',
        action='store_true',
        help='Attempt state recovery from backup'
    )
    resume_parser.add_argument(
        '--force-restart',
        action='store_true',
        help='Ignore existing state and start new run'
    )
    resume_parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging and state backups'
    )
    resume_parser.add_argument(
        '--backup-state',
        action='store_true',
        help='Backup state before each step'
    )

    return parser


def main(args: Optional[list] = None) -> int:
    """Main entry point for the CLI."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        return 1

    if parsed_args.command == 'run':
        return run_workflow(parsed_args)
    elif parsed_args.command == 'resume':
        from orchestrator.cli.commands import resume_workflow
        return resume_workflow(**vars(parsed_args))
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())