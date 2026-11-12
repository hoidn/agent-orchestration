"""List-price equivalents of provider token usage.

The packaged `price_table.json` holds `currency`, `tokens_per_unit`, `source`, `date` and four rates
(`input`, `output`, `cache_read`, `cache_write`) per model, and optionally a `long_context` tier: the
four rates that apply above `above_input_tokens` prompt tokens. It is a frozen copy of the vendors'
public price pages on its date, not billed spend. A model without rates prices as None, never as zero.
`priced` uses the ordinary rates; `cap_cost` (the spend cap's figure) the highest tier.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import date
from importlib import resources

FIELDS = ('input', 'output', 'cache_read', 'cache_write')
UNAVAILABLE = 'unavailable'


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
        if 'long_context' in rates and not valid_tier(rates['long_context']):
            raise ValueError(f'{model}: long_context needs a positive above_input_tokens and four rates')
    return table


def valid_tier(tier):
    return (isinstance(tier, Mapping) and type(tier.get('above_input_tokens')) is int
            and tier['above_input_tokens'] > 0 and all(number(tier.get(key)) for key in FIELDS))


def validate_date(value):
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('invalid date')
    except (TypeError, ValueError) as error:
        raise ValueError('price_table date must be YYYY-MM-DD') from error


def valid_rates(rates):
    return isinstance(rates, Mapping) and all(number(rates[key]) for key in FIELDS if key in rates)


def valid_tokens(tokens):
    return all(type(tokens.get(key)) is int and tokens[key] >= 0 for key in FIELDS)


def valid_usage(usage):
    model, proof = usage.get('model'), usage.get('provenance')
    return (isinstance(model, str) and bool(model.strip()) and
            model.lower() not in ('unknown', 'unavailable', 'auto', 'default') and isinstance(proof, Mapping)
            and proof.get('complete_native_transcript') is True)


def usage_cost(usage, table):
    """Cost of one receipt row (`model`, `charge_tokens`, complete `provenance`), or UNAVAILABLE."""
    if not isinstance(usage, Mapping) or not valid_usage(usage):
        return UNAVAILABLE
    rates = table['models'].get(usage['model'])
    tokens = usage.get('charge_tokens')
    if rates is None or not isinstance(tokens, Mapping):
        return UNAVAILABLE
    if not all(key in rates for key in FIELDS) or not valid_tokens(tokens):
        return UNAVAILABLE
    try:
        value = sum(tokens[key] * rates[key] / table['tokens_per_unit'] for key in FIELDS)
        return value if math.isfinite(value) else UNAVAILABLE
    except OverflowError:
        return UNAVAILABLE


def prices_model(table: Mapping, model) -> bool:
    """Whether the table has all four rates for `model`."""
    rates = table['models'].get(model) if isinstance(model, str) else None
    return isinstance(rates, Mapping) and all(key in rates for key in FIELDS)


def _highest_tier(table: Mapping) -> Mapping:
    models = {model: {**rates, **{key: rates['long_context'][key] for key in FIELDS}} if 'long_context' in rates
              else rates for model, rates in table['models'].items()}
    return {**table, 'models': models}


def cap_cost(usage, table: Mapping) -> float | None:
    """The cap's figure for one `usage.json`: the larger of the CLI's reported cost and the highest-tier price.

    None (unmetered) unless the usage is `reported` and `complete` with priced rows.
    """
    if not isinstance(usage, Mapping) or usage.get('status') != 'reported' or usage.get('complete') is not True:
        return None
    rows = usage.get('rows')
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        return None
    value = priced(rows, _highest_tier(table))
    reported = usage.get('reported_cost_usd')
    return None if value is None else max(value, reported) if number(reported) else value


def priced(rows: list[dict], table: Mapping) -> float | None:
    """Sum of `tokens x rate / tokens_per_unit` over usage rows; None if any row's model has no rates."""
    value = 0.0
    for row in rows:
        cost = usage_cost({'model': row.get('model'), 'charge_tokens': row.get('tokens'),
                           'provenance': {'complete_native_transcript': True}}, table)
        if cost == UNAVAILABLE:
            return None
        value += cost
    return value


def load_price_table(path=None) -> dict:
    """The packaged price table, or the one at `path`, validated.

    Raises OSError when `path` cannot be read and ValueError when it is not a valid table.
    """
    if path is None:
        text = resources.files(__package__).joinpath('price_table.json').read_text(encoding='utf-8')
    else:
        with open(path, encoding='utf-8') as stream:
            text = stream.read()
    try:
        return validate(json.loads(text))
    except RecursionError as error:
        raise ValueError('price_table nesting too deep') from error
