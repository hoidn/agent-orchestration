"""Calls proxy proof from complete native identities and explicit recorded CLI effort."""
import re
import json
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
    if not identity_status(receipt) or receipt.get('provider') not in ('claude', 'codex'):
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


def identity_status(receipt):
    status, reason = receipt.get('status'), receipt.get('reason')
    return ((status == 'complete' and reason is None) or
            (status == 'unavailable' and reason == 'missing_or_invalid_model_counters'))


def require_campaign_models(row, allowed):
    """Every counted C1 call needs native model identity; declared argv is not actual-model proof."""
    receipts = row.get('receipt_usage')
    if not pricing.complete_coverage(row.get('provider_calls'), receipts) or not actual_coverage(row, receipts):
        raise ValueError(f"C1 actual model identity: incomplete native call coverage at {row.get('records_dir')}")
    for receipt in receipts:
        usage = receipt.get('usage')
        if receipt.get('provider') != 'codex' or not isinstance(usage, list) or not usage:
            raise ValueError('C1 actual model identity: non-Codex or missing native usage')
        for item in usage:
            if not native_identity(item) or item['model'] not in allowed or \
                    item['provenance'].get('model_source') != 'turn_context.model':
                raise ValueError('C1 actual model identity: forbidden, unknown or argv-only model')


def require_campaign_scan(row, allowed):
    """Enforce C1's narrower policy on the canonical scan before any quality ingestion."""
    from experiments.compare import scan, sandbox
    records = Path(row['records_dir'])
    path = records / ('scan.json' if row['kind'] == 'judge' else 'record.json')
    document = json.loads(path.read_text())
    metadata = json.loads((records / 'record.json').read_text())
    tree, since = Path(metadata['tree']), metadata['created_at']
    home = sandbox.session_home(metadata)
    claude = scan.claude_sessions(tree, home)
    hits = list(scan.model_hits(claude, None))
    codex = list(scan.codex_sessions(tree, since, home))
    hits += list(scan.model_hits(codex, 'gpt-5.6-terra'))
    if row.get('provider_calls') == 0 and codex:
        hits.append({'file': str(codex[0]), 'line': 0, 'pattern': scan.FORBIDDEN_MODEL,
                     'text': 'C1 uncounted native session cannot establish zero calls'})
    try:
        require_campaign_models(row, allowed)
    except ValueError as error:
        hits.append({'file': str(records), 'line': 0, 'pattern': scan.FORBIDDEN_MODEL, 'text': str(error)})
    current = document if row['kind'] == 'judge' else document['scan']
    if hits:
        current['hits'] += [hit for hit in hits if hit not in current['hits']]
        current['verdict'] = None
        path.write_text(json.dumps(document) + '\n')
        raise ValueError(f"C1 actual model identity: canonical scan refuses model policy: {hits[0]['text']}")
    if current['hits'] and (current.get('verdict') or {}).get('verdict') != 'cleared':
        raise ValueError('C1 unadjudicated contamination at generation barrier')


def campaign_proxy_comparable(rows, pools, models):
    """Freeze positive native identity and explicit effort proof at this checkpoint."""
    from experiments.orc_structural_search import metering
    work = [r for r in rows if r['kind'] in ('episode', 'evaluation')] + metering._judge_work(pools)
    pairs = set()
    try:
        for row in work:
            require_campaign_models(row, models)
            if row['provider_calls']:
                observed = observed_pairs(row)
                if observed is None:
                    return False
                pairs.update(observed)
    except ValueError:
        return False
    return bool(pairs) and all(effort in models[model] for model, effort in pairs)
