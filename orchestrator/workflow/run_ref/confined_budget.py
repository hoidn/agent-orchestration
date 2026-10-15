"""Fixed Linux wall clock for the confined visit's durable ledger accounting."""
from pathlib import Path
import time

from .runtime import RunRefRuntimeError


def boot_id():
    try:
        value = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if not value:
            raise ValueError('empty boot id')
        return value
    except (OSError, ValueError) as exc:
        raise RunRefRuntimeError('run_ref_environment_unavailable', 'budget_boot_identity_unavailable') from exc


def boottime_ns():
    try:
        return time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError) as exc:
        raise RunRefRuntimeError('run_ref_environment_unavailable', 'budget_clock_unavailable') from exc


def remaining_ns(state, *, now=None, boot=None):
    charged = state['charged_ns']
    active = state['active']
    if active is not None:
        if active['boot_id'] != (boot_id() if boot is None else boot):
            raise RunRefRuntimeError('run_ref_environment_changed', 'budget_clock_epoch_changed')
        now = boottime_ns() if now is None else now
        if now < active['since_ns']:
            raise RunRefRuntimeError('run_ref_evidence_invalid', 'budget_clock_went_backwards')
        charged += now - active['since_ns']
    return state['limit_ns'] - charged


class VisitBudget:
    """In-memory projection of acknowledged openings/closures, never a second authority."""

    def __init__(self, state, emit):
        self.state, self.emit = state, emit

    @property
    def charged_ns(self):
        return self.state['limit_ns'] - remaining_ns(self.state)

    @property
    def remaining(self):
        return remaining_ns(self.state) / 1_000_000_000

    def close(self):
        active = self.state['active']
        if active is not None:
            remaining_ns(self.state)  # validate boot/clock before proposing closure
            now = boottime_ns()
            ack = self.emit('budget_close', dict(opening_sequence=active['opening_sequence'],
                            boot_id=active['boot_id'], until_ns=now))
            self.state = dict(self.state, charged_ns=self.state['charged_ns'] + now - active['since_ns'],
                              active=None, closure_digest=ack.authority_digest)
        return self.state
