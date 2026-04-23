"""Main CLI entry point for orchestrator."""

import argparse
import sys
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
        '--input',
        action='append',
        metavar='NAME=VALUE',
        help='Workflow signature inputs (can be specified multiple times)'
    )
    run_parser.add_argument(
        '--input-file',
        type=str,
        help='Path to JSON file containing workflow signature inputs'
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
        '--stream-output',
        action='store_true',
        help='Stream provider stdout/stderr live without enabling full debug mode'
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
        default=1,
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
    run_parser.add_argument(
        '--step-summaries',
        action='store_true',
        help='Enable per-step summaries (advisory only)'
    )
    run_parser.add_argument(
        '--summary-mode',
        choices=['async', 'sync'],
        help='Summary mode (default: async when summaries are enabled)'
    )
    run_parser.add_argument(
        '--summary-provider',
        type=str,
        default='claude_sonnet_summary',
        help='Provider template name for summaries'
    )
    run_parser.add_argument(
        '--summary-timeout-sec',
        type=int,
        default=120,
        help='Timeout for a single summary request'
    )
    run_parser.add_argument(
        '--summary-max-input-chars',
        type=int,
        default=12000,
        help='Maximum snapshot chars passed to summarizer'
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
        '--stream-output',
        action='store_true',
        help='Stream provider stdout/stderr live without enabling full debug mode'
    )
    resume_parser.add_argument(
        '--backup-state',
        action='store_true',
        help='Backup state before each step'
    )
    resume_parser.add_argument(
        '--state-dir',
        type=str,
        help='Override default state directory'
    )
    resume_parser.add_argument(
        '--max-retries',
        type=int,
        default=1,
        help='Maximum retry attempts'
    )
    resume_parser.add_argument(
        '--retry-delay',
        type=int,
        default=1000,
        help='Retry delay in milliseconds'
    )
    resume_parser.add_argument(
        '--summary-mode',
        choices=['async', 'sync'],
        help='Override summary mode for this resume run'
    )
    resume_parser.add_argument(
        '--summary-provider',
        type=str,
        help='Override summary provider for this resume run'
    )
    resume_parser.add_argument(
        '--summary-timeout-sec',
        type=int,
        help='Override summary timeout for this resume run'
    )
    resume_parser.add_argument(
        '--summary-max-input-chars',
        type=int,
        help='Override summary max input chars for this resume run'
    )

    report_parser = subparsers.add_parser('report', help='Render workflow run status')
    report_parser.add_argument(
        '--run-id',
        type=str,
        help='Run ID (defaults to latest run)'
    )
    report_parser.add_argument(
        '--runs-root',
        type=str,
        default='.orchestrate/runs',
        help='Runs root directory'
    )
    report_parser.add_argument(
        '--format',
        choices=['md', 'json'],
        default='md',
        help='Output format'
    )
    report_parser.add_argument(
        '--output',
        type=str,
        help='Optional output file path'
    )

    dashboard_parser = subparsers.add_parser('dashboard', help='Serve local workflow dashboard')
    dashboard_parser.add_argument(
        '--workspace',
        action='append',
        required=True,
        help='Workspace root to scan; can be specified multiple times'
    )
    dashboard_parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host interface to bind (default: 127.0.0.1)'
    )
    dashboard_parser.add_argument(
        '--port',
        type=int,
        default=8765,
        help='Port to bind (default: 8765)'
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
    elif parsed_args.command == 'report':
        from orchestrator.cli.commands import report_workflow
        return report_workflow(
            run_id=parsed_args.run_id,
            runs_root=parsed_args.runs_root,
            format=parsed_args.format,
            output=parsed_args.output,
        )
    elif parsed_args.command == 'dashboard':
        from orchestrator.cli.commands import dashboard_workflow
        return dashboard_workflow(
            workspace=parsed_args.workspace,
            host=parsed_args.host,
            port=parsed_args.port,
        )
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
