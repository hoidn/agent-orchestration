"""Readout-only list-price equivalents from frozen criterion rates and native receipts."""
import math
from collections.abc import Mapping
from datetime import date

from experiments.orc_structural_search.records import UNAVAILABLE

FIELDS = ('input', 'output', 'cache_read', 'cache_write')


def number(value, *, positive=False):
    try:
        return (type(value) in (int, float) and math.isfinite(value) and
                (value > 0 if positive else value >= 0))
    except OverflowError:
        return False


def validate(table):
    """Reject malformed price tables; never guess model aliases or missing cache rates."""
    if not isinstance(table, Mapping):
        raise ValueError('criterion price_table required')
    if table.get('currency') != 'USD' or not number(table.get('tokens_per_unit'), positive=True):
        raise ValueError('price_table requires USD and a positive finite tokens_per_unit')
    if not isinstance(table.get('source'), str) or not table['source'].strip():
        raise ValueError('price_table source required')
    validate_date(table.get('date'))
    if not isinstance(table.get('models'), Mapping) or not table['models']:
        raise ValueError('price_table models required')
    for model, rates in table['models'].items():
        if not isinstance(model, str) or not model.strip() or not valid_rates(rates):
            raise ValueError('each price_table model needs four finite nonnegative rates')
    return table


def validate_date(value):
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('invalid date')
    except (TypeError, ValueError) as error:
        raise ValueError('price_table date must be YYYY-MM-DD') from error


def valid_rates(rates):
    return isinstance(rates, Mapping) and all(number(rates.get(key)) for key in FIELDS)


def usage_cost(usage, table):
    if not isinstance(usage, Mapping):
        return UNAVAILABLE
    if not valid_usage(usage):
        return UNAVAILABLE
    rates = table['models'].get(usage['model'])
    tokens = usage.get('charge_tokens')
    if rates is None or not isinstance(tokens, Mapping):
        return UNAVAILABLE
    if not all(type(tokens.get(key)) is int and tokens[key] >= 0 for key in FIELDS):
        return UNAVAILABLE
    try:
        value = sum(tokens[key] * rates[key] / table['tokens_per_unit'] for key in FIELDS)
        return value if math.isfinite(value) else UNAVAILABLE
    except OverflowError:
        return UNAVAILABLE


def valid_usage(usage):
    model, proof = usage.get('model'), usage.get('provenance')
    return (isinstance(model, str) and bool(model.strip()) and isinstance(proof, Mapping)
            and proof.get('complete_native_transcript') is True)


def call_cost(call, table):
    if not isinstance(call, Mapping) or call.get('status') != 'complete':
        return UNAVAILABLE
    if call.get('provider') not in ('claude', 'codex'):
        return UNAVAILABLE
    usage = call.get('usage')
    if not isinstance(usage, list) or not usage:
        return UNAVAILABLE
    values = [usage_cost(row, table) for row in usage]
    return UNAVAILABLE if UNAVAILABLE in values else sum(values)


def cost(row, table):
    """Incomplete receipt coverage, duplicate calls or unknown usage leave cost unavailable."""
    validate(table)
    receipts = row.get('receipt_usage')
    if not complete_coverage(row.get('provider_calls'), receipts):
        return UNAVAILABLE
    values = [call_cost(call, table) for call in receipts]
    if UNAVAILABLE in values:
        return UNAVAILABLE
    value = sum(values)
    return value if math.isfinite(value) else UNAVAILABLE


def complete_coverage(calls, receipts):
    if type(calls) is not int or calls < 0 or not isinstance(receipts, list) or len(receipts) != calls:
        return False
    identities = [call.get('call_id') for call in receipts if isinstance(call, Mapping)]
    if len(identities) != calls or any(not isinstance(key, str) or not key for key in identities):
        return False
    return len(set(identities)) == calls
