"""Calibrated quality/cost comparisons; recompute the complete tolerant frontier."""
from experiments.orc_structural_search.pricing import number
from experiments.orc_structural_search.records import UNAVAILABLE


def tolerances(tau_q, tau_c):
    if not number(tau_q) or not number(tau_c):
        raise ValueError('dominance tolerances must be finite nonnegative numbers')


def dominates(a, b, tau_q, tau_c):
    tolerances(tau_q, tau_c)
    q_a, q_b, c_a, c_b = a['quality'], b['quality'], a['cost'], b['cost']
    return (q_a >= q_b - tau_q and c_a <= c_b * (1 + tau_c) and
            (q_a > q_b + tau_q or c_a < c_b * (1 - tau_c)))


def frontier(rows, tau_q, tau_c):
    tolerances(tau_q, tau_c)
    eligible = [row for row in rows if row['above_floor'] and number(row['quality']) and number(row['cost'])]
    return sorted(a['candidate_id'] for a in eligible
                  if not any(dominates(b, a, tau_q, tau_c) for b in eligible if a is not b))
