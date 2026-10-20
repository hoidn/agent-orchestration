"""Readout-only list-price equivalents from frozen criterion rates and native receipts."""
import math
from collections.abc import Mapping
from datetime import date

from experiments.orc_structural_search.records import UNAVAILABLE

FIELDS = ('input', 'output', 'cache_read', 'cache_write')


def number(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value) and
            (value > 0 if positive else value >= 0))


def validate(table):
    """Reject malformed price tables; never guess model aliases or missing cache rates."""
    if not isinstance(table, Mapping):
        raise ValueError('criterion price_table required')
    if table.get('currency') != 'USD' or not number(table.get('tokens_per_unit'), positive=True):
        raise ValueError('price_table requires USD and a positive finite tokens_per_unit')
    if not isinstance(table.get('source'), str) or not table['source'].strip():
        raise ValueError('price_table source required')
    try:
        if date.fromisoformat(table['date']).isoformat() != table['date']:
            raise ValueError('invalid date')
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('price_table date must be YYYY-MM-DD') from error
    if not isinstance(table.get('models'), Mapping) or not table['models']:
        raise ValueError('price_table models required')
    for model, rates in table['models'].items():
        if not isinstance(model, str) or not model.strip() or not valid_rates(rates):
            raise ValueError('each price_table model needs four finite nonnegative rates')
    return table


def valid_rates(rates):
    return isinstance(rates, Mapping) and all(number(rates.get(key)) for key in FIELDS)


def usage_cost(usage, table):
    if not isinstance(usage, Mapping):
        return UNAVAILABLE
    rates = table['models'].get(usage.get('model'))
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


def call_cost(call, table):
    if not isinstance(call, Mapping) or call.get('status') != 'complete':
        return UNAVAILABLE
    usage = call.get('usage')
    if not isinstance(usage, list) or not usage:
        return UNAVAILABLE
    values = [usage_cost(row, table) for row in usage]
    return UNAVAILABLE if UNAVAILABLE in values else sum(values)


def cost(row, table):
    """Incomplete receipt coverage, duplicate calls or unknown usage leave cost unavailable."""
    validate(table)
    calls, receipts = row.get('provider_calls'), row.get('receipt_usage')
    if type(calls) is not int or calls < 0 or not isinstance(receipts, list) or len(receipts) != calls:
        return UNAVAILABLE
    identities = [call.get('call_id') for call in receipts if isinstance(call, Mapping)]
    if len(identities) != calls or any(not isinstance(key, str) or not key for key in identities):
        return UNAVAILABLE
    if len(set(identities)) != calls:
        return UNAVAILABLE
    values = [call_cost(call, table) for call in receipts]
    if UNAVAILABLE in values:
        return UNAVAILABLE
    value = sum(values)
    return value if math.isfinite(value) else UNAVAILABLE
