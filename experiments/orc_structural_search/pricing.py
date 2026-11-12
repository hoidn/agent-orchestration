"""Readout-only list-price equivalents from frozen criterion rates and native receipts."""
import math
from collections.abc import Mapping

from experiments.orc_structural_search.records import UNAVAILABLE
from orchestrator.providers.pricing import (  # noqa: F401  (re-exported for readers of this module)
    FIELDS, number, usage_cost, valid_rates, valid_tokens, valid_usage, validate, validate_date,
)


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
