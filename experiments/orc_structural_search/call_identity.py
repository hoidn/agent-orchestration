"""Calls proxy proof from complete native identities and explicit recorded CLI effort."""
import re
from pathlib import Path

from experiments.orc_structural_search import pricing


def cli_effort(records, receipt):
    """Use only explicit flags the house CLI emits; no compiled-policy or default inference."""
    try:
        args = (Path(records) / 'calls' / receipt['call_id'] / 'argv.nul').read_bytes().decode().split('\0')
    except (OSError, TypeError, UnicodeError):
        return None
    if receipt['provider'] == 'claude':
        values = option_values(args, '--effort')
    else:
        configs = option_values(args, '--config') + option_values(args, '-c')
        values = [value.split('=', 1)[1].strip('"') for value in configs
                  if value.startswith('model_reasoning_effort=')]
    return values[0] if len(values) == 1 else None


def option_values(args, option):
    separate = [args[index + 1] for index, arg in enumerate(args[:-1]) if arg == option]
    return separate + [arg.split('=', 1)[1] for arg in args if arg.startswith(option + '=')]


def observed_pairs(row):
    receipts = row.get('receipt_usage')
    if not pricing.complete_coverage(row.get('provider_calls'), receipts) or not receipts:
        return None
    if not actual_coverage(row, receipts):
        return None
    pairs = set()
    for receipt in receipts:
        observed = receipt_pairs(row, receipt)
        if observed is None:
            return None
        pairs.update(observed)
    return pairs


def receipt_pairs(row, receipt):
    if receipt.get('provider') not in ('claude', 'codex'):
        return None
    effort, usage = cli_effort(row.get('records_dir'), receipt), receipt.get('usage')
    if not effort or not isinstance(usage, list) or not usage:
        return None
    if not all(native_identity(item) for item in usage):
        return None
    if len({item['provenance']['session_sha256'] for item in usage}) != 1:
        return None
    return {(item['model'], effort) for item in usage}


def native_identity(usage):
    if not isinstance(usage, dict) or not pricing.valid_usage(usage):
        return False
    digest = usage['provenance'].get('session_sha256')
    return isinstance(digest, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None


def actual_coverage(row, receipts):
    try:
        records = Path(row['records_dir'])
        calls = {path.name for path in (records / 'calls').iterdir() if path.is_dir()}
        return calls == {receipt['call_id'] for receipt in receipts}
    except (KeyError, TypeError, OSError):
        return False
