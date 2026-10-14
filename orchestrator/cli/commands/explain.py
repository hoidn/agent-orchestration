"""Workflow Lisp explain command."""

from __future__ import annotations

import logging
from argparse import Namespace

logger = logging.getLogger(__name__)


def explain_workflow(args: Namespace) -> int:
    """Refuse the retired flat-compilation views."""

    logger.error(
        "[workflow_explain_retired] flat compilation views are retired; "
        "use a separately retained complete release/environment for those views, "
        "or compile --diagnostics-json to check a current workflow"
    )
    return 2
