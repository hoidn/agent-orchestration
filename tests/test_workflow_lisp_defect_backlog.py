"""The compiler and runtime defect backlog: every reproduction, and the list of known defects.

Source: `docs/plans/2026-11-13-compiler-and-runtime-defect-backlog-plan.md` (its Defect Table and
Reproductions). A row is one program with the outcome wanted for it. A row that does not give that
outcome today is in `KNOWN` with today's signature, read from a run:

    ("crash", class, "file.py:qualified.name")
                                              `compiler_defect`: the class of its cause and the innermost
                                              function under `orchestrator/` in the cause's traceback that
                                              is not a raising helper (`crash_signature`)
    ("traceback", class, "file.py:qualified.name")
                                              the exception left the build uncaught (exit 1 on the command line)
    ("refused", code, ...)                    the diagnostic codes
    ("builds",)                               the public build wrote a closed program
    ("value", value, command labels...)       the result of the public `run` and its command log
    ("digests", n)                            n distinct program digests among the row's two spellings
    ("ran", exit code, launches, leaks, code...)
                                              a provider row: requests the stand-in received, how many of
                                              them carried the text of a file outside the workspace, and
                                              the diagnostic codes a failed run prints

Rules, each enforced here:
- a known row must still give exactly its signature. A fix makes its row fail. The fixer then (1)
  deletes the row's entry from `KNOWN`, and only that; (2) states the wanted outcome where the row
  has none, never as the signature it was known by; (3) removes the row's `AMENDED` entry if it has
  one. `KNOWN_AT_T0` and `WANTED_AT_T0` are not touched;
- `KNOWN` only shrinks: its ids are in `KNOWN_AT_T0`, which also freezes each signature. A known row's
  signature differs from the frozen one only through `AMENDED` (the new signature and a reason naming
  the date of the plan's ledger row). An amendment is for the same defect under a moved key: another
  function of a crash or traceback of the same class, a traceback that became a coded crash, another
  code of a refusal. A row that moved to a different wrong outcome is not amended;
- no row is deleted: every id is in `WANTED_AT_T0`. Deleting one is an `AMENDED` entry too. A new
  defect is added to `KNOWN`, `KNOWN_AT_T0` and `WANTED_AT_T0`, with a ledger row;
- a wanted outcome changes only by a decision recorded in the plan's ledger: it may be made stricter
  freely (an outcome stated where there was none, a value where there was `builds`); any other change
  needs an `AMENDED_WANTED` entry with a dated reason, for known rows, controls and pins;
- a known row that builds, commits or gives a value where a refusal is wanted, and every row of
  `PAIRED`, names a control row, not in `KNOWN`, that exercises the guard it gets past (`CONTROLS`);
  every key of `PAIRED` and `CONTROLS` is a row.

A row whose wanted outcome is `None` is owned by another decision (the one-target cut, or a fix that
chooses a code): only today's outcome is recorded.

No program, listed only (plan row id):

    | Row  | Why there is no row here                                                          |
    | ---- | --------------------------------------------------------------------------------- |
    | A1   | missing prompt `input_file`: branch `fix/missing-prompt-file` carries its tests   |
    | E16  | bare `[Errno 2]` for a missing prompt file: the same branch                       |
    | D14  | empty `(list)` in a `match` arm: not reproduced, no program                       |
    | D18  | provider extern used as a value in reached code: not re-run, no program           |
    | E3   | the `variant_ref_unproved` message: a message is not asserted                     |
    | E14  | `TimestampNs` documented as a type: closed by the documentation, no program       |
    | E17  | dead prompt identity code: a `grep`, not a program                                |
    | E21  | a pure operand renames the effects beside it: not re-run, no program              |
    | E22  | local names are part of the program digest: a property the cut decides            |

Rows D21, D21-continue, D22 and E27 are the roadmap's tenth batch; the plan's Defect Table does not hold them yet. Rows
B7-*, D23, D24 and D25 (the eleventh batch, found by the call-site fix) and D25-plain to D29 (found by the
bound-value review) are in the Defect Table.
Rows D5-binder-hidden, D5-binder-hidden-match, D5-if-whole and D5-if-whole-return, found by the review of
TD2, D5-if-match and D20-map-argument, found by its re-review, D4-subject-match and D4-subject-loop, found by the
differential corpus of TD1, and D4-subject-argument and D20-let-proc-subject, found by its second re-review, are
not in it either. Rows D10-input-pure, D10-field, D10-field-pure, D10-literal-let, D10-literal-let-pure and D10-rebound-*
(the twelfth batch, found by the TD6 review and its fix round) are in the Defect Table.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from tests import test_workflow_evaluated_prompt_source_unreadable as prompt_file_fixture
from tests import test_workflow_evaluated_providers as provider_fixture
from tests import test_workflow_lisp_run_ref_workflow_program as run_ref_fixture
from tests.agent_session_shims import closed_path
from tests.workflow_lisp_closed_program_helpers import build_outcome

REPO = Path(__file__).resolve().parents[1]
BUILDS = ("builds",)


def refused(*codes: str) -> tuple:
    return ("refused", *codes)


def value(result, *log: str) -> tuple:
    return ("value", result, *log)


def crash(error: str, where: str) -> tuple:
    return ("crash", error, where)


# ---------------------------------------------------------------------------------------------
# The known defects. Signatures were read from runs on `main`, never typed from the plan.

ELABORATE = "workflow_lisp/wcc/elaborate.py"
NO_ELABORATION = crash("TypeError", f"{ELABORATE}:_elaborate_expr_to_value")
OPERAND = crash("TypeError", f"{ELABORATE}:_body_to_prefix_and_value")
BINDER_OUT_OF_SCOPE = crash("KeyError", f"{ELABORATE}:_infer_expr_type")
NO_NARROWING = crash("TypeError", f"{ELABORATE}:_infer_expr_type")
CAPTURED_COMMAND = crash("ValueError", "workflow_lisp/closed/command_templates.py:CommandScopeContext.bind")
CAPTURED_PROVIDER_INPUT = crash("TypeError", "workflow/evaluated/provider_io.py:ProviderIOContext.bind")
CAPTURE_REQUESTS = "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>."
LAUNCHED_WITH_OUTSIDE_TEXT = ("ran", 0, 1, 1)

KNOWN: dict[str, tuple] = {
    "A2-C": BUILDS, "A2-G": BUILDS, "A2-M": BUILDS,
    "A4-abs": LAUNCHED_WITH_OUTSIDE_TEXT, "A4-dotdot": LAUNCHED_WITH_OUTSIDE_TEXT,
    "A4-symlink": LAUNCHED_WITH_OUTSIDE_TEXT,
    "B2-let": value(2), "B2-arm": value(2), "B3": value(100), "B3-print": value(1), "B4": value(10),
    "B5": value(6), "B5-ref": value(6),
    "C1": value(7, "libw"),
    "D5-binder-hidden": NO_NARROWING, "D5-binder-hidden-match": NO_NARROWING,
    "D5-if-whole": NO_NARROWING, "D5-if-whole-return": NO_NARROWING, "D5-if-match": NO_NARROWING,
    "D20-map-argument": NO_NARROWING,
    "D4-subject-match": NO_ELABORATION, "D4-subject-loop": NO_ELABORATION,
    "D4-subject-argument": OPERAND, "D20-let-proc-subject": OPERAND,
    "D6": crash("CheckedFormError", "contracts/closed_program/check.py:_Checker._field_type"),
    "D7": BINDER_OUT_OF_SCOPE, "D7-hoisted": BINDER_OUT_OF_SCOPE, "D8": BINDER_OUT_OF_SCOPE,
    "D12-entry": crash("CanonicalNameError", "workflow_lisp/closed/names.py:canonical_type_descriptor.<locals>.build"),
    "D12-literal": NO_ELABORATION,
    "D12-name": BINDER_OUT_OF_SCOPE,
    "D13": crash("CheckedFormError", "contracts/closed_program/check.py:_Checker._value"),
    "D22": crash("AttributeError", "workflow_lisp/typecheck_structural_values.py:typecheck_structural_value_expr"),
    "D24": crash("ValueError", "workflow_lisp/closed/names.py:Renamer.ref"),
    "D25": crash("KeyError", "workflow_lisp/compiler.py:_compile_stage3_graph"),
    "D10-input-pure": crash("KeyError", "workflow_lisp/compiler.py:_compile_stage3_graph"),
    "D10-field": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-field-pure": crash("ValueError", "workflow_lisp/closed/command_templates.py:CommandScopeContext.bind"),
    "D10-literal-let": crash("ValueError", "workflow_lisp/closed/names.py:Renamer.ref"),
    "D10-literal-let-pure": crash("KeyError", "workflow_lisp/compiler.py:_compile_stage3_graph"),
    "D10-rebound-loop": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-continue": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-fn": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-let": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-let-in-loop": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-arm": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-macro": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-parameter": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-two-roles": crash("ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D25-plain": crash("KeyError", "workflow_lisp/compiler.py:_compile_stage3_graph"),
    "D26": crash("ValueError", "workflow_lisp/closed/names.py:Renamer.ref"),
    "D27": crash("CheckedFormError", "contracts/closed_program/check.py:_Checker._check_effect_node"),
    "D28": crash("ValueError", CAPTURE_REQUESTS + "visit_reference_owner"), "D29": CAPTURED_COMMAND,
    "B7-free-eff": crash("ValueError", CAPTURE_REQUESTS + "register_request"), "B7-free-pure": CAPTURED_COMMAND,
    "B7-free-arg": crash("ValueError", CAPTURE_REQUESTS + "register_request"),
    "B7-same-written": refused("procedure_lowering_unresolved"), "B7-same-ref": refused("procedure_lowering_unresolved"),
    "B7-macro-if": crash("ValueError", CAPTURE_REQUESTS + "visit_reference_owner"),
    "B7-macro-let": crash("ValueError", CAPTURE_REQUESTS + "visit_reference_owner"),
    "B7-macro-match": crash("ValueError", CAPTURE_REQUESTS + "visit_reference_owner"),
    "B7-macro-loop": crash("ValueError", CAPTURE_REQUESTS + "visit_reference_owner"),
    "B7-macro-or": crash("ValueError", CAPTURE_REQUESTS + "visit_reference_owner"),
    "B7-macro-defun": crash("ValueError", CAPTURE_REQUESTS + "visit_reference_owner"),
    "B7-macro-if-pure": value(303),
    "B7-macro-not-pure": value(404),
    "B7-macro-and-pure": value(1010),
    "B7-macro-record-call-pure": value(505),
    "B7-macro-record-map-pure": value(2424),
    "E1-and": refused("variant_ref_unproved"), "E1-or": refused("variant_ref_unproved"),
    "E2": refused("variant_ref_unproved"),
    "E4": refused("variant_tag_union_mismatch"),
    "E6": refused("name_unknown"),
    "E7": refused("procedure_call_unknown"),
    "E8": refused("procedure_lowering_unresolved"),
    "E9": refused("procedure_call_unknown"), "E9-local": refused("procedure_call_unknown"),
    "E11": refused("workflow_signature_mismatch"),
    "E12": BUILDS,
    "E13": ("digests", 1),
    "E23-local": refused("name_unknown"), "E23-input": refused("name_unknown"),
    "E24": refused("path_join_under_type_invalid"),
    "E26": refused("procedure_call_unknown"),
    "E27": ("ran", 2, 0, 0, "resume_preflight_failed"),
}

# Frozen at T0, spelled out and never edited: the signature each known row had when it was entered. A row
# added later for a new defect is entered here too, with a row in the plan's ledger.
KNOWN_AT_T0: dict[str, tuple] = {
    "A2-C": ("builds",),
    "A2-G": ("builds",),
    "A2-M": ("builds",),
    "A3-path": ("ran", 1, 1, 0, "provider_result_invalid"),
    "A3-string": ("ran", 1, 1, 0, "provider_result_invalid"),
    "A4-abs": ("ran", 0, 1, 1),
    "A4-dotdot": ("ran", 0, 1, 1),
    "A4-symlink": ("ran", 0, 1, 1),
    "B1": ("ran", 0, 1, 0),
    "B2-arm": ("value", 2),
    "B2-let": ("value", 2),
    "B3": ("value", 100),
    "B3-print": ("value", 1),
    "B4": ("value", 10),
    "B5": ("value", 6),
    "B5-ref": ("value", 6),
    "B7-chain": ("value", 104104),
    "B7-deep": ("value", 105105),
    "B7-int": ("value", 404),
    "B7-let": ("value", 103103),
    "B7-ref": ("value", 103103),
    "B7-same-written": ("refused", "procedure_lowering_unresolved"),
    "B7-same-ref": ("refused", "procedure_lowering_unresolved"),
    "B7-macro-if": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.visit_reference_owner"),
    "B7-macro-let": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.visit_reference_owner"),
    "B7-macro-match": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.visit_reference_owner"),
    "B7-macro-loop": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.visit_reference_owner"),
    "B7-macro-or": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.visit_reference_owner"),
    "B7-macro-defun": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.visit_reference_owner"),
    "B7-macro-if-pure": ("value", 303),
    "B7-macro-not-pure": ("value", 404),
    "B7-macro-and-pure": ("value", 1010),
    "B7-macro-record-call-pure": ("value", 505),
    "B7-macro-record-map-pure": ("value", 2424),
    "C1": ("value", 7, "libw"),
    "D1": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_body_to_prefix_and_value"),
    "D2": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_body_to_prefix_and_value"),
    "D3": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_body_to_prefix_and_value"),
    "D4-loop": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_elaborate_expr_to_value"),
    "D4-map-bound": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_elaborate_expr_to_value"),
    "D4-map-value": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_elaborate_expr_to_value"),
    "D5": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D5-binder-hidden": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D5-binder-hidden-match": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D5-if-whole": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D5-if-whole-return": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D5-if-match": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D20-map-argument": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D4-subject-match": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_elaborate_expr_to_value"),
    "D4-subject-loop": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_elaborate_expr_to_value"),
    "D4-subject-argument": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_body_to_prefix_and_value"),
    "D20-let-proc-subject": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_body_to_prefix_and_value"),
    "D6": ("crash", "CheckedFormError", "contracts/closed_program/check.py:_Checker._field_type"),
    "D7": ("crash", "KeyError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D7-hoisted": ("crash", "KeyError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D8": ("crash", "KeyError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D9-fn": ("traceback", "RuntimeError", "workflow_lisp/loop_state.py:_typecheck_loop_state_seed"),
    "D9-map": ("traceback", "RuntimeError", "workflow_lisp/loop_state.py:_typecheck_loop_state_seed"),
    "D9-name": ("traceback", "RuntimeError", "workflow_lisp/loop_state.py:_typecheck_loop_state_seed"),
    "D9-ref": ("traceback", "RuntimeError", "workflow_lisp/loop_state.py:_typecheck_loop_state_seed"),
    "D10": ("crash", "ValueError", "workflow_lisp/closed/command_templates.py:CommandScopeContext.bind"),
    "D10-R1": ("crash", "ValueError", "workflow_lisp/closed/command_templates.py:CommandScopeContext.bind"),
    "D11": ("crash", "TypeError", "workflow/evaluated/provider_io.py:ProviderIOContext.bind"),
    "D11-R1": ("crash", "TypeError", "workflow/evaluated/provider_io.py:ProviderIOContext.bind"),
    "D11-R2": ("crash", "TypeError", "workflow/evaluated/provider_io.py:ProviderIOContext.bind"),
    "D11-R5": ("crash", "TypeError", "workflow/evaluated/provider_io.py:ProviderIOContext.bind"),
    "D12-entry": ("crash", "CanonicalNameError", "workflow_lisp/closed/names.py:canonical_type_descriptor.<locals>.build"),
    "D12-literal": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_elaborate_expr_to_value"),
    "D12-name": ("crash", "KeyError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type"),
    "D13": ("crash", "CheckedFormError", "contracts/closed_program/check.py:_Checker._value"),
    "D19": ("crash", "SiteAssignmentError", "contracts/closed_program/sites.py:_SiteWalker._value_has_effect"),
    "D20": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_body_to_prefix_and_value"),
    "D21": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_replace_halts_with_jump"),
    "D21-continue": ("crash", "TypeError", "workflow_lisp/wcc/elaborate.py:_replace_halts_with_jump"),
    "D22": ("traceback", "AttributeError", "workflow_lisp/typecheck_structural_values.py:typecheck_structural_value_expr"),
    "D23": ("crash", "ValueError", "workflow_lisp/wcc/elaborate.py:_procedure_edges_by_site"),
    "D23-macro": ("crash", "ValueError", "workflow_lisp/wcc/elaborate.py:_procedure_edges_by_site"),
    "D24": ("crash", "ValueError", "workflow_lisp/closed/names.py:Renamer.ref"),
    "D25": ("crash", "KeyError", "workflow_lisp/compiler.py:_compile_stage3_graph"),
    "D10-input-pure": ("crash", "KeyError", "workflow_lisp/compiler.py:_compile_stage3_graph"),
    "D10-field": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-field-pure": ("crash", "ValueError", "workflow_lisp/closed/command_templates.py:CommandScopeContext.bind"),
    "D10-literal-let": ("crash", "ValueError", "workflow_lisp/closed/names.py:Renamer.ref"),
    "D10-literal-let-pure": ("crash", "KeyError", "workflow_lisp/compiler.py:_compile_stage3_graph"),
    "D10-rebound-loop": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-continue": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-fn": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-let": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-let-in-loop": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-arm": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-macro": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-parameter": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D10-rebound-two-roles": ("crash", "ValueError", "workflow_lisp/closed/names.py:_capture_index_mapping"),
    "D25-plain": ("crash", "KeyError", "workflow_lisp/compiler.py:_compile_stage3_graph"),
    "D26": ("crash", "ValueError", "workflow_lisp/closed/names.py:Renamer.ref"),
    "D27": ("crash", "CheckedFormError", "contracts/closed_program/check.py:_Checker._check_effect_node"),
    "D28": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.visit_reference_owner"),
    "D29": ("crash", "ValueError", "workflow_lisp/closed/command_templates.py:CommandScopeContext.bind"),
    "B7-free-eff": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.register_request"),
    "B7-free-pure": ("crash", "ValueError", "workflow_lisp/closed/command_templates.py:CommandScopeContext.bind"),
    "B7-free-arg": ("crash", "ValueError", "workflow_lisp/closed/build.py:Builder._prepare_computed_capture_requests.<locals>.register_request"),
    "E1-and": ("refused", "variant_ref_unproved"),
    "E1-or": ("refused", "variant_ref_unproved"),
    "E2": ("refused", "variant_ref_unproved"),
    "E4": ("refused", "variant_tag_union_mismatch"),
    "E6": ("refused", "name_unknown"),
    "E7": ("refused", "procedure_call_unknown"),
    "E8": ("refused", "procedure_lowering_unresolved"),
    "E9": ("refused", "procedure_call_unknown"),
    "E9-local": ("refused", "procedure_call_unknown"),
    "E11": ("refused", "workflow_signature_mismatch"),
    "E12": ("builds",),
    "E13": ("digests", 1),
    "E23-input": ("refused", "name_unknown"),
    "E23-local": ("refused", "name_unknown"),
    "E24": ("refused", "path_join_under_type_invalid"),
    "E26": ("refused", "procedure_call_unknown"),
    "E27": ("ran", 2, 0, 0, "resume_preflight_failed"),
}

# Every row and its wanted outcome, frozen at T0 and never edited: a row is never deleted silently and a
# wanted outcome is never loosened silently. A new row is entered here too.
WANTED_AT_T0: dict[str, tuple | None] = {
    "A2-C": ("refused", "run_ref_placement_invalid"),
    "A2-G": ("refused", "run_ref_placement_invalid"),
    "A2-M": ("refused", "run_ref_placement_invalid"),
    "A2-named": ("refused", "run_ref_placement_invalid"),
    "A2-path": ("builds",),
    "A3-path": ("ran", 1, 0, 0, "duplicate_artifact_name"),
    "A3-string": ("ran", 1, 0, 0, "duplicate_artifact_name"),
    "A3-two-names": ("ran", 0, 1, 0),
    "A4-abs": None,
    "A4-asset-abs": ("ran", 1, 0, 0, "asset_file_read_failed"),
    "A4-asset-dotdot": ("ran", 1, 0, 0, "asset_file_read_failed"),
    "A4-asset-symlink": ("ran", 1, 0, 0, "asset_file_read_failed"),
    "A4-dotdot": None,
    "A4-symlink": None,
    "B1": ("ran", 1, 0, 0, "prompt_output_position_destination_collision"),
    "B1-two-paths": ("ran", 0, 1, 0),
    "B2-arm": None,
    "B2-let": None,
    "B2-no-reference": ("refused", "procedure_call_unknown"),
    "B3": None,
    "B3-print": None,
    "B4": None,
    "B4-no-caller-binding": ("refused", "procedure_call_unknown"),
    "B5": None,
    "B5-ref": None,
    "B6": ("value", True, "strb"),
    "B7-chain": ("value", 204104),
    "B7-deep": ("value", 205105),
    "B7-int": ("value", 1004),
    "B7-let": ("value", 203103),
    "B7-ref": ("value", 203103),
    "B7-same-macro": ("value", 104104),
    "B7-same-written": ("value", 104104),
    "B7-same-ref": ("value", 103103),
    "B7-macro-if": ("value", 110103),
    "B7-macro-let": ("value", 110104),
    "B7-macro-match": ("value", 110104),
    "B7-macro-loop": ("value", 110104),
    "B7-macro-or": ("value", 110103),
    "B7-macro-defun": ("value", 117105),
    "B7-macro-if-pure": ("value", 1003),
    "B7-macro-not-pure": ("value", 1004),
    "B7-macro-and-pure": ("value", 410),
    "B7-macro-record-call-pure": ("value", 1705),
    "B7-macro-record-map-pure": ("value", 3024),
    "B7-written": ("value", 204104),
    "C1": ("refused", "procedure_effect_ceiling_exceeded"),
    "C1-local": ("refused", "procedure_effect_ceiling_exceeded"),
    "D1": ("value", 1005),
    "D2": ("refused", "effect_not_permitted"),
    "D3": ("refused", "effect_not_permitted"),
    "D4-cond": ("value", 0),
    "D4-if": ("value", 0),
    "D4-loop": ("value", 0),
    "D4-map": ("value", 2, "m", "m"),
    "D4-map-bound": ("value", 2, "m", "m"),
    "D4-map-value": ("value", [1, 1], "m", "m"),
    "D5": ("value", 3),
    "D5-arm-binder": ("value", 3),
    "D5-if": ("value", 3),
    "D5-binder-hidden": ("value", 8),
    "D5-binder-hidden-match": ("value", 33),
    "D5-if-whole": ("value", 3),
    "D5-if-whole-return": ("builds",),
    "D5-if-match": ("value", 3),
    "D20-map-argument": ("value", 2),
    "D4-subject-match": ("value", 3),
    "D4-subject-loop": ("value", 0),
    "D4-subject-argument": ("value", 3),
    "D20-let-proc-subject": ("value", 2),
    "D5-other-variant": ("refused", "variant_ref_wrong_variant"),
    "D6": ("value", 4),
    "D7": ("value", 2, "step", "step", "check"),
    "D7-bound": ("value", 2, "step", "step", "check"),
    "D7-hoisted": ("value", 2, "step", "step", "check"),
    "D8": ("value", 1),
    "D9-fn": ("value", 5),
    "D9-map": ("value", 2, "m", "m"),
    "D9-name": ("value", 5),
    "D9-ref": ("value", 5),
    "D9-scalar-state": ("value", 5),
    "D10": ("value", 2),
    "D10-R1": ("value", 2),
    "D11": ("value", 2, "step", "step"),
    "D11-R1": ("value", 3, "add"),
    "D11-R2": ("value", 2, "add", "add"),
    "D11-R3": ("value", 2, "add", "add"),
    "D11-R4": ("value", 2, "add", "add"),
    "D11-R5": ("value", 2, "add", "add"),
    "D12-declared": ("builds",),
    "D12-entry": None,
    "D12-literal": None,
    "D12-name": None,
    "D13": ("refused", "pure_expr_overflow"),
    "D13-folded": ("refused", "pure_expr_overflow"),
    "D15": ("builds",),
    "D16": ("refused", "proc_ref_literal_required"),
    "D17-effect": ("value", 2, "m", "m"),
    "D17-pure": ("value", 2),
    "D19": None,
    "D19-done": ("value", 1, "e"),
    "D20": None,
    "D20-bound": ("value", 1, "e1"),
    "D21": None,
    "D21-continue": None,
    "D22": None,
    "D23": ("value", 34),
    "D23-macro": ("value", 705),
    "D24": None,
    "D25": None,
    "D10-input-pure": ("value", 2),
    "D10-field": ("value", 3, "add"),
    "D10-field-pure": ("value", 2),
    "D10-literal-let": ("value", 3, "add"),
    "D10-literal-let-pure": ("value", 11),
    "D10-rebound-loop": ("value", 2, "add"),
    "D10-rebound-continue": ("value", 2, "add"),
    "D10-rebound-fn": ("value", 2, "add"),
    "D10-rebound-let": ("value", 2, "add"),
    "D10-rebound-let-in-loop": ("value", 2, "add"),
    "D10-rebound-arm": ("value", 2, "add"),
    "D10-rebound-macro": ("value", 2, "add"),
    "D10-rebound-parameter": ("value", 2, "add"),
    "D10-rebound-two-roles": ("value", 13, "add", "add"),
    "D10-rebound-renamed": ("value", 2, "add"),
    "D10-rebound-unreferenced": ("value", 7),
    "D10-rebound-unread-binding": ("value", 7),
    "D10-rebound-ignored-argument": ("value", 7),
    "D25-plain": None,
    "D26": None,
    "D27": None,
    "D28": None,
    "D29": None,
    "B7-free-eff": ('value', 111105),
    "B7-free-pure": ('value', 1105),
    "B7-free-arg": ('value', 111105),
    "E1-and": None,
    "E1-or": None,
    "E2": None,
    "E2-parallel": ("builds",),
    "E2-pure": ("builds",),
    "E4": None,
    "E5-cond": ("value", 1),
    "E5-if": ("value", 1),
    "E5-match": ("value", 1),
    "E6": ("value", 2),
    "E6-uncalled": ("builds",),
    "E7": ("value", 2, "g", "g"),
    "E8": ("value", 3),
    "E9": ("value", 1),
    "E9-local": ("value", 5),
    "E9-direct": ("builds",),
    "E9-effect-callee": ("builds",),
    "E9-effect-caller": ("builds",),
    "E10": ("value", 6),
    "E11": None,
    "E12": None,
    "E13": None,
    "E15-missing": ("ran", 1, 0, 0, "asset_file_read_failed"),
    "E18-in-place": ("refused", "list_map_binder_invalid"),
    "E18-macro": ("refused", "list_map_binder_invalid"),
    "E18-other-binder": ("value", 2),
    "E19": ("value", 4),
    "E20": ("value", 1),
    "E23-bound": ("value", 2),
    "E23-input": ("value", 2),
    "E23-local": ("value", 2),
    "E24": ("value", {"p": "artifacts/work/x.json"}),
    "E24-imported": ("value", {"p": "artifacts/work/x.json"}),
    "E24-qualified": ("value", {"p": "artifacts/work/x.json"}),
    "E25": ("builds",),
    "E26": None,
    "E27": ("ran", 0, 2, 0),
    "E27-plain-resume": ("ran", 0, 2, 0),
}

# The one way a frozen fact changes: an entry `row id: (new value, reason)` whose reason names the date of the
# row in the plan's ledger that records the change.
#
# `AMENDED`, for signatures and rows:
# - a known row whose signature moved while its defect stayed: the new signature, which `KNOWN` then holds.
#   An amendment may change the function of a crash or a traceback (same exception class; a traceback may
#   become a coded crash of its class) or the code of a refusal, and nothing else: a refusal that became a
#   crash, or a crash of another class, is a different defect and is not amended;
# - a deleted row: `None`.
# An entry whose row is fixed (no longer in `KNOWN`) is removed.
#
# `AMENDED_WANTED`, for wanted outcomes: the new wanted outcome of a row, known, control or pin. Stating an
# outcome where none was stated, or a value where only `builds` was, needs no entry; any other change does.
TYPECHECK_BOUNDARY = "2026-11-13, Task TP1: a typecheck failure is reported as compiler_defect, not a traceback"
AMENDED: dict[str, tuple[tuple | None, str]] = {
    "D9-ref": (None, "2026-11-13, coordinator ruling: D9-ref's remaining outcome is E9, entered as E9-local"),
    "D22": (KNOWN["D22"], TYPECHECK_BOUNDARY),
}
AMENDED_WANTED: dict[str, tuple[tuple | None, str]] = {}

# Rows the plan names as needing a control whatever their signature.
PAIRED = frozenset({"A2-C", "A2-G", "A2-M", "A3-path", "A3-string", "A4-abs", "A4-dotdot", "A4-symlink", "B1",
                    "B2-let", "B2-arm", "B4", "C1", "D5", "D9-name", "D9-fn", "D9-map",
                    "D11-R1", "D11-R2", "D11-R5"})

# Known row -> the control rows that exercise the guard it gets past (or, for a crash, the nearest
# spelling that works). A control is never in `KNOWN`.
CONTROLS: dict[str, tuple[str, ...]] = {
    "A2-C": ("A2-named", "A2-path"), "A2-G": ("A2-named", "A2-path"), "A2-M": ("A2-named", "A2-path"),
    "A3-path": ("A3-two-names",), "A3-string": ("A3-two-names",),
    "A4-abs": ("A4-asset-abs",), "A4-dotdot": ("A4-asset-dotdot",), "A4-symlink": ("A4-asset-symlink",),
    "B1": ("B1-two-paths",),
    "B2-let": ("B2-no-reference",), "B2-arm": ("B2-no-reference",),
    "B4": ("B4-no-caller-binding",),
    "C1": ("C1-local",),
    "D4-loop": ("D4-if", "D4-cond"), "D4-map-value": ("D4-map",), "D4-map-bound": ("D4-map",),
    "D7": ("D7-bound",), "D7-hoisted": ("D7-bound",),
    "D5": ("D5-if", "D5-arm-binder", "D5-other-variant"),
    "D9-name": ("D9-scalar-state",), "D9-fn": ("D9-scalar-state",),
    "D9-map": ("D9-scalar-state",),
    "D11-R1": ("D11-R3", "D11-R4"), "D11-R2": ("D11-R3", "D11-R4"), "D11-R5": ("D11-R3", "D11-R4"),
    "D12-entry": ("D12-declared",), "D12-literal": ("D12-declared",), "D12-name": ("D12-declared",),
    "D13": ("D13-folded",),
    "D19": ("D19-done",), "D20": ("D20-bound",),
    "E2": ("E2-parallel", "E2-pure"),
    "E6": ("E6-uncalled",),
    "E9": ("E9-direct", "E9-effect-callee", "E9-effect-caller"),
    "E23-local": ("E23-bound",), "E23-input": ("E23-bound",),
    "E24": ("E24-imported", "E24-qualified"),
    "E27": ("E27-plain-resume",),
}


# ---------------------------------------------------------------------------------------------
# Programs: the body of one module `m` at target 2.40, entry `run`.

def E(label: str, result, type_: str) -> str:
    return f'(command-result c :argv ("python" "c.py" "{label}" "{result}") :returns {type_})'


U = "(defunion U (A (n Int)) (B (why String)))"
SHAPE = "(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"
INC = "(defproc increment ((value Int)) -> Int (+ value 1))"
DBL = "(defproc dbl ((value Int)) -> Int (* value 2))"
AP = "(defproc apply1 ((f ProcRef[Int -> Int]) (v Int)) -> Int (f v))"
STEP = f"(defproc step ((n Int)) -> Int {E('step', 1, 'Int')})"
CHK = f"(defproc check ((n Int)) -> Bool {E('check', 'true', 'Bool')})"
ADD = "(defproc add ((n Int) (x Int)) -> Int (+ n x))"
ADDE = f"(defproc add ((n Int) (x Int)) -> Int {E('add', 3, 'Int')})"
EACH = ("(defproc each ((f ProcRef[Int -> Int]) (xs List[Int])) -> Int\n"
        "    (list/length (list/map-effect ((x xs)) :max 2 (f x))))")
U_IS_A_3 = ('u={"variant":"A","n":3}',)

COMMAND = '''import os, sys
from pathlib import Path
with open("log.txt", "a", encoding="utf-8") as log:
    log.write(sys.argv[1] + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(sys.argv[2], encoding="utf-8")
'''


def module(run: str, *definitions: str, name: str = "m", head: str = "(export run)") -> str:
    forms = "\n  ".join((*definitions, f"(defworkflow run {run})"))
    return f'(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n  (defmodule {name}) {head}\n  {forms})\n'


@dataclass(frozen=True)
class Row:
    """One program. `source` is the text of `m.orc`, or files by path with the entry file first."""

    wanted: tuple | None
    source: str | dict[str, str]
    inputs: tuple[str, ...] = ()
    entry: str = "m::run"
    versus: str | None = None  # a second spelling: the outcome is the number of distinct digests


def row(wanted: tuple | None, run: str, *definitions: str, inputs: tuple[str, ...] = ()) -> Row:
    return Row(wanted, module(run, *definitions), inputs)


MM_B4 = "(defmacro mm (x) (let* ((f (proc-ref increment))) (f x)))"
WITH_BUMP = "(defmacro with-bump (k body) (let-proc ((bump ((x Int)) -> Int (+ x k))) body))"
LIB_W = f"(defworkflow lib-w ((n Int)) -> Int {E('libw', 7, 'Int')})"
C1_P = "(defproc p ((n Int)) -> Int :effects ((calls-workflow lib-w)) (call lib-w :n n))"
D3_VIA = ("(defproc via-cont ((f ProcRef[Int -> Int]) (xs List[Int])) -> Int\n"
          "    (loop/recur :max 3 :state 0 :on-exhausted 0\n"
          "      (fn (s) (if (= s 0) (continue (list/length (list/map-effect ((x xs)) :max 2 (f x)))) (done s)))))")
D4_MAP = f"(list/map-effect ((x (list 1 2))) :max (match u ((A a) a.n) ((B b) 1)) {E('m', 1, 'Int')})"
D7_LOOP = ("(loop/recur :max 2 :state tmp :on-exhausted s (fn (s) (if (check s) (done s) "
           "(continue (loop/recur :max 1 :state (+ s tmp) :on-exhausted u (fn (u) (done (step u))))))))")
D7_RUNS = ("step", "step", "check")
# The state starts at 5 and `:on-exhausted` is 0: a fix that exhausts the loop instead of finishing it shows.
D9_STATE = "(loop/recur ((s (loop-state (i Int 5)))) :max 1 :on-exhausted 0 (done s.i))"
D9_FN = "(loop/recur :max 1 :state (loop-state (i Int 5)) :on-exhausted 0 (fn (s) (done s.i)))"
D9_MAP = f"(list/length (list/map-effect ((x (list 1 2))) :max 2 {E('m', 1, 'Int')}))"


def d9(body: str, call: str = "(h n)") -> str:
    return f"((n Int)) -> Int (let-proc ((h ((v Int)) -> Int {body})) {call})"


D11_VIA = ("(defproc via ((f ProcRef[Int -> Int]) (xs List[Int])) -> Int\n"
           "    (list/length (list/map-effect ((x xs)) :max 2 (f x))))")
ROLE = "(let* ((role (bind-proc (proc-ref add) :n 1))) BODY)"
ROLE_STEP = ROLE.replace("BODY", "(let-proc ((step ((x Int)) -> Int (role x))) BODY)")
MAP_12 = "(list/length (list/map-effect ((x (list 1 2))) :max 2 CALL))"
D12 = ("(defrecord Box (n Int))", "(defworkflow helper ((b Box)) -> Box b)",
       "(defworkflow invoke ((runner WorkflowRef[Box -> Box])) -> Box (record Box :n 1))")
D17_EFFECT = ("(defproc total ((n Int) (xs List[Int])) -> Int\n"
              f"    (list/length (list/map-effect ((x xs)) :max 2 {E('m', 1, 'Int')})))")
D17_PURE = "(defproc total ((n Int) (xs List[Int])) -> Int (list/length (list/map ((x xs)) (+ x n))))"
D17_RUN = "() -> Int (let* ((r (bind-proc (proc-ref total) :n 1))) (r (list 1 2)))"
D19_VALUE = f"(if (> n 0) (if (> n 0) {E('e', 1, 'Int')} 0) 0)"
D19 = "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) (EXIT VALUE)))"
D20_MK = "(defproc mkshape ((r Int)) -> Shape (variant Shape CIRCLE :r r))"
D20_SUBJECT = f"(mkshape (if (> n 0) {E('e1', 1, 'Int')} {E('e2', 2, 'Int')}))"
D20_ARMS = "((CIRCLE c) c.r) ((SQUARE s) 0)"
B7_BOX = ("(defrecord Box (n Int))", "(defworkflow c1 ((input Box)) -> Box (record Box :n (+ input.n 100)))",
          "(defworkflow c2 ((input Box)) -> Box (record Box :n (+ input.n 200)))",
          "(defproc foo ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box (call runner :input input))")
B7_INC1 = "(defproc inc1 ((hook ProcRef[Box -> Box]) (input Box)) -> Box (hook (record Box :n (+ input.n 1))))"
B7_AP = "(defproc ap ((hook ProcRef[Box -> Box]) (input Box)) -> Box (hook input))"
B7_CH = "(defmacro ch (w v) (inc1 (bind-proc (proc-ref foo) :runner (workflow-ref w)) v))"
B7_RUN = ("((n Int)) -> Int (let* ((input (record Box :n n)) (a (CALL c1 input)) (b (CALL c2 input))) "
          "(+ a.n (* 1000 b.n)))")
B7_WRITTEN = "(inc1 (bind-proc (proc-ref foo) :runner (workflow-ref W)) input)"
B7_HELPER = "(defproc helper ((fixed Int) (y Int)) -> Int (+ fixed y))"
B7_APPLYI = "(defproc applyi ((hook ProcRef[Int -> Int]) (x Int)) -> Int (hook x))"
B7_BF = "(defmacro bf (k x) (applyi (bind-proc (proc-ref helper) :fixed (+ k 0)) x))"
ROLE_OVER = ("(let* (VALUE (role (bind-proc (proc-ref add) :n READ))) "
             "(let-proc ((step ((x Int)) -> Int (role x))) (step 1)))")
ADDN = f"(defproc add ((n Int) (x Int)) -> Int (let* ((z {E('add', 0, 'Int')})) (+ (+ n x) z)))"
REBOUND = "(let* ((role (bind-proc (proc-ref add) :n k))) BODY)"
REBOUND_STEP = "(let-proc ((step ((x Int)) -> Int (role x))) USE)"
REBINDERS = {
    "loop": "(loop/recur ((k 100)) :max 1 :on-exhausted 0 (done LOCAL))",
    "continue": "(loop/recur ((k 0)) :max 2 :on-exhausted 0 (if (> k 0) (done k) (continue LOCAL)))",
    "fn": "(loop/recur :max 1 :state 100 :on-exhausted 0 (fn (k) (done LOCAL)))",
    "let": "(let* ((k 100)) LOCAL)",
    "let-in-loop": "(loop/recur ((s 0)) :max 1 :on-exhausted 0 (let* ((k 100)) (done LOCAL)))",
    "arm": "(match (variant U A :n 100) ((A k) LOCAL) ((B b) 0))",
    "macro": "(bind-as k LOCAL)",
}
BIND_AS = "(defmacro bind-as (nm body) (let* ((nm 100)) body))"
IGNORE = "(defproc ignore ((f ProcRef[Int -> Int]) (v Int)) -> Int v)"


def rebound(wanted: tuple, body: str) -> Row:
    return row(wanted, "((k Int)) -> Int " + REBOUND.replace("BODY", body), ADDN, U, BIND_AS, IGNORE, inputs=("k=1",))
B7_FWK = "(defproc fwk ((k Int) (y Int)) -> Int (let* ((r (call c1 :input (record Box :n (+ y k))))) r.n))"
B7_U = "(defunion U (A (n Int)) (B (n Int)))"
B7_DBL = "(defun dbl ((x Int)) -> Int (* x 2))"
B7_BH = "(defproc bh ((f Bool) (y Int)) -> Int (if f (+ 1 y) (+ 7 y)))"
B7_BOXH = "(defproc boxh ((b Box) (y Int)) -> Int (+ b.n y))"
B7_WRAPH = "(defproc wraph ((w Wrap) (y Int)) -> Int (+ w.box.n (+ (* 10 (list/length w.xs)) y)))"
B7_PURE_TWICE = "((n Int)) -> Int (+ (bm 1 n) (* 100 (bm 7 n)))"
B7_TWICE = "((n Int)) -> Int (+ (bv 1 n) (* 1000 (bv 7 n)))"
B7_FWI = "(defproc fwi ((k Int) (input Box)) -> Box (call c1 :input (record Box :n (+ input.n k))))"
B7_FREE_RUN = "((n Int)) -> Int (let* ((input (record Box :n n)) (a FIRST) (c SECOND)) (+ a.n (* 1000 c.n)))"
LOOP_LOCAL_ADDING = "(let-proc ((h ((v Int)) -> Int (loop/recur ((s v)) :max 1 :on-exhausted s (done (+ s ADDEND))))) (h x))"
D23_LOCAL = "((v Int)) -> Int (loop/recur ((s v)) :max 1 :on-exhausted s (done BODY))"
D23_BOTH = ("(defproc both ((n Int)) -> Int (let-proc ((f " + D23_LOCAL.replace("BODY", "(+ s 1)") + ")\n"
            "    (g " + D23_LOCAL.replace("BODY", "(* s 10)") + ")) (+ (f n) (g n))))")
D23_MACRO = ("(defmacro with-loop (x k) (let-proc ((h " + D23_LOCAL.replace("(s v)", "(s k)").replace("BODY", "s")
             + ")) (h x)))")
E2_COMMAND = '(command-result c :argv ("python" "c.py" "m" u.n) :returns Int)'
E4_PICK = ("(defproc pick :forall (T) ((x T))\n"
           "    :where ((T has-union-variant OK (n Int)) (T has-union-variant BAD (why String)))\n"
           "    -> Int (if (= x.variant OK) 1 0))")
E9_H = "(defproc h ((v Int)) -> Int (loop/recur ((s v)) :max 1 :on-exhausted 0 (done s)))"
E9_RUN = "((n Int)) -> Int (apply1 (proc-ref h) n)"
E18_MM = "(defmacro mm (x) (let* ((v (list x x))) (list/length (list/map ((BINDER v)) (+ BINDER 1)))))"
E23_BIND = "(apply1 (bind-proc (proc-ref add) :n NAME) 1)"
E24_VALUE = {"p": "artifacts/work/x.json"}
E24_LIB = ('(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n  (defmodule m/lib) (export P Box mk)\n'
           '  (defpath P :kind relpath :under "artifacts/work" :must-exist false)\n  (defrecord Box (p P))\n'
           '  (defproc mk () -> Box (record Box :p (path/join-under P "x.json"))))\n')


def c1(*definitions: str, head: str) -> dict[str, str]:
    lib = module("() -> Int 1", LIB_W, name="lib", head="(export lib-w run)")
    return {"m.orc": module("() -> Int (p 1)", *definitions, C1_P, head=head), "lib.orc": lib}


def e24(imports: str, lib: str = E24_LIB) -> Row:
    direct = module("() -> Box (mk)", name="m/direct", head=f"(import m/lib :only ({imports})) (export run)")
    return Row(value(E24_VALUE), {"m/direct.orc": direct, "m/lib.orc": lib}, entry="m/direct::run")


ROWS: dict[str, Row] = {
    # Class B: a silent wrong value or wrong callee. B2 to B5 are the one-target cut's.
    "B2-let": row(None, "() -> Int (let* ((g (proc-ref increment))) (let* ((g 5)) (g 1)))", INC),
    "B2-arm": row(None, "((u U)) -> Int (let* ((g (proc-ref increment))) (match u ((A g) (g 1)) ((B b) 0)))",
                  U, INC, inputs=U_IS_A_3),
    "B2-no-reference": row(refused("procedure_call_unknown"), "() -> Int (let* ((g 5)) (g 1))"),
    "B3": row(None, "() -> Int (let-proc ((f ((x Int)) -> Int (+ x 1))) (f 1))",
              "(defun f ((n Int)) -> Int (* n 100))"),
    "B3-print": row(None, "() -> Int (let-proc ((print ((x Int)) -> Int (+ x 100))) (print 1))"),
    "B4": row(None, "() -> Int (let* ((f (proc-ref dbl))) (+ 0 (mm 5)))", INC, DBL, MM_B4),
    "B4-no-caller-binding": row(refused("procedure_call_unknown"), "() -> Int (+ 0 (mm 5))", INC, DBL, MM_B4),
    "B5": row(None, "((n Int)) -> Int (with-bump 5 (bump n))", WITH_BUMP, inputs=("n=1",)),
    "B5-ref": row(None, "((n Int)) -> Int (with-bump 5 (apply1 (proc-ref bump) n))", AP, WITH_BUMP, inputs=("n=1",)),
    # Not fixed: specification 8.10 states that a `Bool` result accepts the strings.
    "B6": row(value(True, "strb"), "() -> Bool " + E("strb", r'\"TRUE\"', "Bool")),
    # Eleventh batch: a value bound by `bind-proc` is identified by its position and, made of stable kinds only,
    # its content, so two expansions of one template that bind different such values get two specializations.
    "B7-chain": row(value(204104), B7_RUN.replace("CALL", "ch"), *B7_BOX, B7_INC1, B7_CH, inputs=("n=3",)),
    "B7-ref": row(value(203103), B7_RUN.replace("CALL", "ba"), *B7_BOX, B7_AP,
                  "(defmacro ba (w v) (ap (bind-proc (proc-ref foo) :runner (workflow-ref w)) v))", inputs=("n=3",)),
    "B7-deep": row(value(205105), B7_RUN.replace("CALL", "cd"), *B7_BOX, B7_INC1,
                   "(defmacro cd (w v) (inc1 (bind-proc (proc-ref inc1) :hook "
                   "(bind-proc (proc-ref foo) :runner (workflow-ref w))) v))", inputs=("n=3",)),
    "B7-let": row(value(203103), B7_RUN.replace("CALL", "lb"), *B7_BOX, B7_AP,
                  "(defmacro lb (w v) (let* ((g (bind-proc (proc-ref foo) :runner (workflow-ref w)))) (ap g v)))",
                  inputs=("n=3",)),
    "B7-written": row(value(204104), B7_RUN.replace("(CALL c1 input)", B7_WRITTEN.replace("W", "c1"))
                      .replace("(CALL c2 input)", B7_WRITTEN.replace("W", "c2")), *B7_BOX, B7_INC1, inputs=("n=3",)),
    "B7-same-macro": row(value(104104), B7_RUN.replace("c2", "c1").replace("CALL", "ch"), *B7_BOX, B7_INC1, B7_CH,
                         inputs=("n=3",)),
    "B7-int": row(value(1004), "((n Int)) -> Int (+ (bf 1 n) (* 100 (bf 7 n)))", B7_HELPER, B7_APPLYI, B7_BF,
                  inputs=("n=3",)),
    "B7-same-written": row(value(104104), B7_RUN.replace("(CALL c1 input)", B7_WRITTEN.replace("W", "c1"))
                           .replace("(CALL c2 input)", B7_WRITTEN.replace("W", "c1")), *B7_BOX, B7_INC1, inputs=("n=3",)),
    # Bound to `ap` directly, not through `inc1`: the same refusal (bound-value re-review, `Q-wfref-same`).
    "B7-same-ref": row(value(103103), B7_RUN.replace("(CALL c1 input)", "(ap (bind-proc (proc-ref foo) :runner "
                       "(workflow-ref c1)) input)").replace("(CALL c2 input)", "(ap (bind-proc (proc-ref foo) :runner "
                       "(workflow-ref c1)) input)"), *B7_BOX, B7_AP, inputs=("n=3",)),
    # A bound value of another kind than the stable ones keeps the position identity alone, so two expansions of
    # one template share one specialization (bound-value re-review: conditional normalization hoists these kinds).
    "B7-macro-if": row(value(110103), B7_TWICE, *B7_BOX, B7_FWK, B7_APPLYI, B7_U, B7_DBL,
                    "(defmacro bv (k x) (applyi (bind-proc (proc-ref fwk) :k (if (> k 2) k 0)) x))", inputs=("n=3",)),
    "B7-macro-let": row(value(110104), B7_TWICE, *B7_BOX, B7_FWK, B7_APPLYI, B7_U, B7_DBL,
                    "(defmacro bv (k x) (applyi (bind-proc (proc-ref fwk) :k (let* ((z k)) (+ z 0))) x))", inputs=("n=3",)),
    "B7-macro-match": row(value(110104), B7_TWICE, *B7_BOX, B7_FWK, B7_APPLYI, B7_U, B7_DBL,
                    "(defmacro bv (k x) (applyi (bind-proc (proc-ref fwk) :k (match (variant U A :n k) ((A a) a.n) ((B b) 0))) x))", inputs=("n=3",)),
    "B7-macro-loop": row(value(110104), B7_TWICE, *B7_BOX, B7_FWK, B7_APPLYI, B7_U, B7_DBL,
                    "(defmacro bv (k x) (applyi (bind-proc (proc-ref fwk) :k (loop/recur ((s k)) :max 1 :on-exhausted s (done (+ s 0)))) x))", inputs=("n=3",)),
    "B7-macro-or": row(value(110103), B7_TWICE, *B7_BOX, B7_FWK, B7_APPLYI, B7_U, B7_DBL,
                    "(defmacro bv (k x) (applyi (bind-proc (proc-ref fwk) :k (if (or (> k 2) (> 0 1)) k 0)) x))", inputs=("n=3",)),
    "B7-macro-defun": row(value(117105), B7_TWICE, *B7_BOX, B7_FWK, B7_APPLYI, B7_U, B7_DBL,
                    "(defmacro bv (k x) (applyi (bind-proc (proc-ref fwk) :k (dbl k)) x))", inputs=("n=3",)),
    "B7-macro-if-pure": row(value(1003), "((n Int)) -> Int (+ (bf 1 n) (* 100 (bf 7 n)))", B7_HELPER, B7_APPLYI,
                            "(defmacro bf (k x) (applyi (bind-proc (proc-ref helper) :fixed (if (> k 2) k 0)) x))",
                            inputs=("n=3",)),
    # The same family, pure: a bound `not`, `and`, or a record holding a call or a `list/map` (bound-value
    # re-review, round 2). Two expansions share one specialization and both use the first expansion's value.
    "B7-macro-not-pure": row(value(1004), B7_PURE_TWICE, B7_BH, B7_APPLYI,
               "(defmacro bm (k x) (applyi (bind-proc (proc-ref bh) :f (not (> k 2))) x))", inputs=("n=3",)),
    "B7-macro-and-pure": row(value(410), B7_PURE_TWICE, B7_BH, B7_APPLYI,
               "(defmacro bm (k x) (applyi (bind-proc (proc-ref bh) :f (and (> k 2) (> 9 1))) x))", inputs=("n=3",)),
    "B7-macro-record-call-pure": row(value(1705), B7_PURE_TWICE, "(defrecord Box (n Int))", B7_BOXH, B7_DBL,
               B7_APPLYI, "(defmacro bm (k x) (applyi (bind-proc (proc-ref boxh) :b (record Box :n (dbl k))) x))",
               inputs=("n=3",)),
    "B7-macro-record-map-pure": row(value(3024), B7_PURE_TWICE, "(defrecord Box (n Int))",
               "(defrecord Wrap (box Box) (xs List[Int]))", B7_WRAPH, B7_APPLYI,
               "(defmacro bm (k x) (applyi (bind-proc (proc-ref wraph) :w (record Wrap :box (record Box :n k) "
               ":xs (list/map ((i (list 1 2))) (+ i k)))) x))", inputs=("n=3",)),
    # A bound value that reads a local keeps the position identity alone, so two expansions of a template whose
    # bound value still reads a local after substitution share one specialization: the build stops.
    "B7-free-eff": row(value(111105), B7_FREE_RUN.replace("FIRST", "(lk 1 input)").replace("SECOND", "(lk 7 input)"),
                       *B7_BOX, B7_FWI, B7_AP, "(defmacro lk (k v) (let* ((b k) (hook (bind-proc (proc-ref fwi) "
                       ":k (+ b 1)))) (ap hook v)))", inputs=("n=3",)),
    "B7-free-pure": row(value(1105), "((n Int)) -> Int (+ (lkp 1 n) (* 100 (lkp 7 n)))", B7_HELPER, B7_APPLYI,
                        "(defmacro lkp (k x) (let* ((b k) (hook (bind-proc (proc-ref helper) :fixed (+ b 1)))) "
                        "(applyi hook x)))", inputs=("n=3",)),
    "B7-free-arg": row(value(111105), B7_FREE_RUN.replace("FIRST", "(let* ((b 1)) (bk b input))")
                       .replace("SECOND", "(let* ((b 7)) (bk b input))"), *B7_BOX, B7_FWI, B7_AP,
                       "(defmacro bk (k v) (let* ((hook (bind-proc (proc-ref fwi) :k (+ k 1)))) (ap hook v)))",
                       inputs=("n=3",)),

    # Class C: the declared effects ceiling over an imported workflow.
    "C1": Row(refused("procedure_effect_ceiling_exceeded"),
              c1(head="(import lib :only (lib-w)) (export run)")),
    "C1-local": Row(refused("procedure_effect_ceiling_exceeded"), module("() -> Int (p 1)", LIB_W, C1_P)),

    # Class D: a crash on source the language admits.
    "D1": row(value(1005), "() -> Int (let* ((c 1000)) (+ c (let* ((c 5)) "
              "(match (variant Shape SQUARE :side 2) ((CIRCLE k) k.r) ((SQUARE s) c)))))", SHAPE),
    "D2": row(refused("effect_not_permitted"),
              "((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) "
              f"(continue (+ (if (> n 0) {E('e', 1, 'Int')} 0) 9))))", inputs=("n=1",)),
    "D3": row(refused("effect_not_permitted"), "() -> Int (via-cont (proc-ref step) (list 1 2))", STEP, D3_VIA),
    # `:on-exhausted` is 9 and the loop finishes with 0: a fix that exhausts instead of finishing shows.
    "D4-loop": row(value(0), "((u U)) -> Int (loop/recur ((s 0)) :max (match u ((A a) a.n) ((B b) 1)) "
                   ":on-exhausted 9 (done s))", U, inputs=U_IS_A_3),
    "D4-if": row(value(0), "((n Int)) -> Int (loop/recur ((s 0)) :max (if (> n 0) 1 2) :on-exhausted 9 (done s))",
                 inputs=("n=1",)),
    "D4-cond": row(value(0), "((n Int)) -> Int (loop/recur ((s 0)) :max (cond ((> n 0) 1) (true 2)) "
                   ":on-exhausted 9 (done s))", inputs=("n=1",)),
    # A serial map's `:max (match …)` crashes where the map is a value of its own (the workflow's result, a
    # `let*` binding) and builds where the map is an operand, here of `list/length`: the control.
    "D4-map-value": row(value([1, 1], "m", "m"), f"((u U)) -> List[Int] {D4_MAP}", U, inputs=U_IS_A_3),
    "D4-map-bound": row(value(2, "m", "m"), f"((u U)) -> Int (let* ((ys {D4_MAP})) (list/length ys))",
                        U, inputs=U_IS_A_3),
    "D4-map": row(value(2, "m", "m"), f"((u U)) -> Int (list/length {D4_MAP})", U, inputs=U_IS_A_3),
    "D5": row(value(3), "((u U)) -> Int (match u ((A a) u.n) ((B b) 0))", U, inputs=U_IS_A_3),
    "D5-other-variant": row(refused("variant_ref_wrong_variant"),
                            '((u U)) -> String (match u ((A a) u.why) ((B b) "x"))', U),
    "D5-arm-binder": row(value(3), "((u U)) -> Int (match u ((A u) u.n) ((B b) 0))", U, inputs=U_IS_A_3),
    "D5-if": row(value(3), "((u U)) -> Int (if (= u.variant A) u.n 0)", U, inputs=U_IS_A_3),
    # Found by the review of TD2: a read of the subject where a binding in the arm hides the arm's binder, and a
    # name a discriminant test proves used whole. The E1 placement test of a defect inside a `continue` value uses
    # D5-binder-hidden's shape as its vehicle: a fix of this row needs another one there.
    "D5-binder-hidden": row(value(8), "((u U)) -> Int (match u ((A a) (let* ((a 5)) (+ a u.n))) ((B b) 0))",
                            U, inputs=U_IS_A_3),
    "D5-binder-hidden-match": row(value(33), "((u U) (v U)) -> Int (match u ((A a) (match v ((A a) "
                                  "(+ u.n (* 10 a.n))) ((B b) 0))) ((B b) 0))", U, inputs=(*U_IS_A_3, 'v={"variant":"A","n":3}')),
    "D5-if-whole": row(value(3), "((u U)) -> Int (if (= u.variant A) (f u) 0)", U,
                       "(defproc f ((x U)) -> Int (match x ((A a) a.n) ((B b) 0)))", inputs=U_IS_A_3),
    "D5-if-whole-return": row(BUILDS, "((u U)) -> U (if (= u.variant A) u u)", U),
    # Found by the re-review of TD1, beside the rows above and with their key, but other defects: a `match` on a
    # name a discriminant test proves; a map in a `match` subject's argument, whose result element type the
    # subject carried as written lacks.
    "D5-if-match": row(value(3), "((u U)) -> Int (if (= u.variant A) (match u ((A a) a.n) ((B b) 0)) 0)", U,
                       inputs=U_IS_A_3),
    "D20-map-argument": row(value(2), "((n Int)) -> Int (match (mkshape (list/length (list/map ((x (list 1 2))) x))) "
                            f"{D20_ARMS})", SHAPE, D20_MK, inputs=("n=1",)),
    # Found while widening the differential corpus of TD1: a pure `match` or a loop as a `match` subject, with
    # D12-literal's key. An `if` there builds.
    "D4-subject-match": row(value(3), "((u U)) -> Int (match (match u ((A a) (variant Shape CIRCLE :r a.n)) "
                            f"((B b) (variant Shape SQUARE :side 1))) {D20_ARMS})", U, SHAPE, inputs=U_IS_A_3),
    "D4-subject-loop": row(value(0), "() -> Int (match (loop/recur ((s 0)) :max 2 :on-exhausted (variant Shape SQUARE "
                           f":side 1) (done (variant Shape CIRCLE :r s))) {D20_ARMS})", SHAPE),
    # Found by the second re-review of TD1, crashing on `main` before the branch: a pure `match` in a call argument
    # of a `match` subject (not D4-subject-match, the `match` as the whole subject), and a `let-proc` subject whose
    # body is a call with an `if` argument calling the local.
    "D4-subject-argument": row(value(3), f"((u U)) -> Int (match (mkshape (match u ((A a) a.n) ((B b) 3))) {D20_ARMS})",
                               U, SHAPE, D20_MK, inputs=U_IS_A_3),
    "D20-let-proc-subject": row(value(2), "((n Int)) -> Int (match (let-proc ((f ((k Int)) -> Int (+ k 1))) "
                                f"(mkshape (if (> n 0) (f n) 2))) {D20_ARMS})", SHAPE, D20_MK, inputs=("n=1",)),
    # 4: the inner `u` is `A 1`, the workflow's is `A 3`. A fix of the crash alone returns a wrong value.
    "D6": row(value(4), "((u U)) -> Int (+ (let* ((u (variant U A :n 1))) (if (= u.variant A) u.n 0)) "
              "(if (= u.variant A) u.n 0))", U, inputs=U_IS_A_3),
    "D7": row(value(2, *D7_RUNS), f"() -> Int (let* ((tmp (step 3))) (+ tmp (let* ((tmp (step 1))) {D7_LOOP})))",
              STEP, CHK),
    # The inner `let*` bound first builds; hoisted into the outer binding list, as the plan words it, it crashes.
    "D7-bound": row(value(2, *D7_RUNS),
                    f"() -> Int (let* ((tmp (step 3)) (r (let* ((tmp (step 1))) {D7_LOOP}))) (+ tmp r))", STEP, CHK),
    "D7-hoisted": row(value(2, *D7_RUNS),
                      f"() -> Int (let* ((tmp0 (step 3)) (tmp (step 1))) (+ tmp0 {D7_LOOP}))", STEP, CHK),
    # Task 0b of the staged-authoring plan removes D8, E7 and E8.
    "D8": row(value(1), "((u U)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (= (list/length "
              "(list/map ((v (list u u))) (match v ((A a) a.n) ((B b) 0)))) 2) (done 1) (continue (+ s 1))))",
              U, inputs=U_IS_A_3),
    "D9-name": row(value(5), d9(D9_STATE), inputs=("n=1",)),
    "D9-fn": row(value(5), d9(D9_FN), inputs=("n=1",)),
    "D9-map": row(value(2, "m", "m"), d9(D9_MAP), inputs=("n=1",)),
    "D9-scalar-state": row(value(5), d9("(loop/recur ((s 5)) :max 1 :on-exhausted 0 (done s))"), inputs=("n=1",)),
    "D10": row(value(2), "() -> Int (let* ((p (proc-ref increment))) "
               "(let-proc ((f ((x Int)) -> Int (p x))) (f 1)))", INC),
    "D10-R1": row(value(2), "() -> Int " + ROLE_STEP.replace("BODY", "(step 1)"), ADD),
    "D11": row(value(2, "step", "step"), "() -> Int (let* ((g (proc-ref step))) "
               "(let-proc ((h ((n Int)) -> Int (g n))) (via (proc-ref h) (list 1 2))))", STEP, D11_VIA),
    "D11-R1": row(value(3, "add"), "() -> Int " + ROLE_STEP.replace("BODY", "(step 1)"), ADDE),
    "D11-R2": row(value(2, "add", "add"),
                  "() -> Int " + ROLE_STEP.replace("BODY", MAP_12.replace("CALL", "(step x)")), ADDE),
    "D11-R5": row(value(2, "add", "add"),
                  "() -> Int " + ROLE_STEP.replace("BODY", "(each (proc-ref step) (list 1 2))"), ADDE, EACH),
    "D11-R3": row(value(2, "add", "add"),
                  "() -> Int " + ROLE.replace("BODY", MAP_12.replace("CALL", "(role x)")), ADDE),
    "D11-R4": row(value(2, "add", "add"), "() -> Int " + ROLE.replace("BODY", "(each role (list 1 2))"), ADDE, EACH),
    "D12-entry": Row(None, module("() -> Int 1", *D12, head="(export run invoke)"), entry="m::invoke"),
    "D12-literal": row(None, "() -> Box (call invoke :runner (workflow-ref helper))", *D12),
    "D12-name": row(None, "() -> Box (call invoke :runner helper)", *D12),
    "D12-declared": row(BUILDS, "() -> Int 1", *D12),
    "D13": row(refused("pure_expr_overflow"), "() -> Int 9223372036854775808"),
    "D13-folded": row(refused("pure_expr_overflow"), "() -> Int (+ 9223372036854775807 1)"),
    # Regression pins: closed, or not reproduced in the planner's shape.
    "D15": row(BUILDS, "() -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (done (list/length "
               f'(list/map-effect ((r (list "a" "b"))) :max 2 :parallel 2 :workspace r {E("p", 1, "Int")}))))'),
    "D16": row(refused("proc_ref_literal_required"), "((n Int)) -> Int (let* ((g (if (> n 0) "
               "(proc-ref increment) (proc-ref increment)))) (g 1))", INC),
    "D17-effect": row(value(2, "m", "m"), D17_RUN, D17_EFFECT),
    "D17-pure": row(value(2), D17_RUN, D17_PURE),
    "D19": row(refused("effect_not_permitted"), D19.replace("EXIT", "continue").replace("VALUE", D19_VALUE), inputs=("n=1",)),
    "D19-done": row(value(1, "e"), D19.replace("EXIT", "done").replace("VALUE", D19_VALUE), inputs=("n=1",)),
    "D20": row(value(1, "e1"), f"((n Int)) -> Int (match {D20_SUBJECT} {D20_ARMS})", SHAPE, D20_MK, inputs=("n=1",)),
    "D20-bound": row(value(1, "e1"), f"((n Int)) -> Int (let* ((shape {D20_SUBJECT})) (match shape {D20_ARMS}))",
                     SHAPE, D20_MK, inputs=("n=1",)),
    # Tenth batch: `done` where the loop body's value is not the control form itself; specification 13.1
    # refuses it.
    "D21": row(refused("loop_recur_contract_invalid"), "() -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (let* ((x (done 1))) x))"),
    # The `continue` spelling, which a mutant of the seed set reached (mutant generator Task T5).
    "D21-continue": row(refused("loop_recur_contract_invalid"), "() -> Int (loop/recur ((s 0)) :max 2 :on-exhausted s (let* ((x (continue (+ s 1)))) (done 1)))"),
    "D22": row(None, "() -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (list (done 1)))"),
    # Eleventh batch: an inlined pure procedure gave every node of its body the site of its call, so two calls in
    # that body to different lifted locals shared one site and one target, chosen in hash-seed order.
    # Found by the call-site review; not collisions: they crash in a single use too.
    "D24": row(None, "((n Int)) -> Int (let* ((x n) (r (record R :k 1))) "
               + LOOP_LOCAL_ADDING.replace("ADDEND", "r.k") + ")", "(defrecord R (k Int))", inputs=("n=3",)),
    "D25": row(None, "((n Int)) -> Int (both n 1)", "(defproc both ((x Int) (k Int)) -> Int (let* ((kk (+ k 0))) "
               + LOOP_LOCAL_ADDING.replace("ADDEND", "kk") + "))", inputs=("n=3",)),
    # Twelfth batch (TD6 fix round 1), each a role called from a local step: over a workflow input with a pure
    # `add` (D10's shape with `:n k`); over a field read; over a `let*` name bound to a literal. The copied role is
    # the spelling `main` crashes on when written by hand inside the local. D10-rebound-*: the role reads `k`, bound
    # again between the role and the local (each binder kind; a parameter of the local; one of two roles). A copy
    # would read the inner binder, so the local keeps its capture parameters and crashes as on `main`; wanted is
    # the value the lexical binding gives, the one the renamed spelling runs to. Controls: renamed; the local never
    # referenced, referenced only by a `let*` nothing reads, or by an argument its callee ignores: `main` builds
    # each (7) with the same digest.
    "D10-input-pure": row(value(2), "((k Int)) -> Int " + ROLE_OVER.replace("VALUE ", "").replace("READ", "k"), ADD,
                          inputs=("k=1",)),
    "D10-field": row(value(3, "add"), "((k Int)) -> Int " + ROLE_OVER.replace("VALUE", "(r (record R :k k))")
                     .replace("READ", "r.k"), ADDE, "(defrecord R (k Int))", inputs=("k=1",)),
    "D10-field-pure": row(value(2), "((k Int)) -> Int " + ROLE_OVER.replace("VALUE", "(r (record R :k k))")
                          .replace("READ", "r.k"), ADD, "(defrecord R (k Int))", inputs=("k=1",)),
    "D10-literal-let": row(value(3, "add"), "() -> Int " + ROLE_OVER.replace("VALUE", "(v 10)").replace("READ", "v"),
                           ADDE),
    "D10-literal-let-pure": row(value(11), "() -> Int " + ROLE_OVER.replace("VALUE", "(v 10)").replace("READ", "v"),
                                ADD),
    "D10-rebound-loop": rebound(value(2, "add"), REBINDERS["loop"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(step 1)"))),
    "D10-rebound-continue": rebound(value(2, "add"), REBINDERS["continue"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(step 1)"))),
    "D10-rebound-fn": rebound(value(2, "add"), REBINDERS["fn"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(step 1)"))),
    "D10-rebound-let": rebound(value(2, "add"), REBINDERS["let"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(step 1)"))),
    "D10-rebound-let-in-loop": rebound(value(2, "add"), REBINDERS["let-in-loop"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(step 1)"))),
    "D10-rebound-arm": rebound(value(2, "add"), REBINDERS["arm"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(step 1)"))),
    "D10-rebound-macro": rebound(value(2, "add"), REBINDERS["macro"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(step 1)"))),
    "D10-rebound-parameter": rebound(value(2, "add"), "(let-proc ((step ((k Int)) -> Int (role k))) (step 1))"),
    "D10-rebound-two-roles": row(value(13, "add", "add"), "((k Int)) -> Int (let* ((v 10) (r1 (bind-proc (proc-ref add) :n k)) "
                                 "(r2 (bind-proc (proc-ref add) :n v))) (let* ((v 0)) (let-proc ((step ((x Int)) -> Int "
                                 "(+ (r1 x) (r2 x)))) (step 1))))", ADDN, inputs=("k=1",)),
    "D10-rebound-renamed": rebound(value(2, "add"), REBINDERS["loop"].replace("((k 100))", "((q 100))")
                                   .replace("LOCAL", REBOUND_STEP.replace("USE", "(step 1)"))),
    "D10-rebound-unreferenced": rebound(value(7), REBINDERS["loop"].replace("LOCAL", REBOUND_STEP.replace("USE", "7"))),
    "D10-rebound-unread-binding": rebound(value(7), REBINDERS["let"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(let* ((f (proc-ref step))) 7)"))),
    "D10-rebound-ignored-argument": rebound(value(7), REBINDERS["let"].replace(
        "LOCAL", REBOUND_STEP.replace("USE", "(ignore (proc-ref step) 7)"))),
    "D25-plain": row(value(4), "((n Int)) -> Int (pan 1 n)",
                     "(defproc pan ((k Int) (x Int)) -> Int (let-proc ((h ((v Int)) -> Int (+ v k))) (h x)))",
                     inputs=("n=3",)),
    # Found by the bound-value review; each crashes on `main` too, in a single use (D28 binds in two scopes).
    "D26": row(value(104), B7_FREE_RUN.replace("(c SECOND)) (+ a.n (* 1000 c.n))", ") a.n").replace(
               "FIRST", "(ap (bind-proc (proc-ref fw) :b (record Box :n 1)) input)"), *B7_BOX, B7_AP,
               "(defproc fw ((b Box) (input Box)) -> Box (call c1 :input (record Box :n (+ input.n b.n))))",
               inputs=("n=3",)),
    "D28": row(value(110104), B7_FREE_RUN.replace("FIRST", "(let* ((b 1) (hook (bind-proc (proc-ref fwi) :k b))) (ap hook input))")
               .replace("SECOND", "(let* ((b 7) (hook (bind-proc (proc-ref fwi) :k b))) (ap hook input))"),
               *B7_BOX, B7_FWI, B7_AP, inputs=("n=3",)),
    "D29": row(value([7]), "() -> List[Int] (list/map ((b (list 1))) (let* ((hook (bind-proc (proc-ref add-leading) "
               ":leading (+ b 1)))) (hook 5)))",
               "(defproc add-leading ((leading Int) (value Int)) -> Int (+ leading value))"),
    "D23": row(value(34), "((n Int)) -> Int (both n)", D23_BOTH, inputs=("n=3",)),
    "D23-macro": row(value(705), "((n Int)) -> Int (both n)", D23_MACRO,
                     "(defproc both ((n Int)) -> Int (+ (with-loop n 5) (* 100 (with-loop n 7))))", inputs=("n=3",)),

    # Class E: a refusal of good source, a misleading code, an accepted form with no effect.
    # No wanted outcome for E1 and E2: the frontend specification 12.2 lists these reads (under a test combined
    # with `and` or `or`; in the body of a serial `list/map-effect`) as refused with `variant_ref_unproved`.
    # Whether they are defects or the rule is a design question for the dropped task TE1, not for this module.
    "E1-and": row(None, "((u U) (r Bool)) -> Int (if (and (= u.variant A) r) u.n 0)", U),
    "E1-or": row(None, "((u U) (r Bool)) -> Int (if (or (!= u.variant A) r) 0 u.n)", U),
    "E2": row(None, "((u U)) -> List[Int] (if (= u.variant A) "
              f"(list/map-effect ((y (list 1 2))) :max 2 {E2_COMMAND}) (list 0))", U),
    "E2-parallel": row(BUILDS, "((u U)) -> List[Int] (if (= u.variant A) "
                       f'(list/map-effect ((y (list "a"))) :max 2 :parallel 1 :workspace y {E2_COMMAND}) (list 0))', U),
    "E2-pure": row(BUILDS, "((u U)) -> List[Int] (if (= u.variant A) (list/map ((y (list 1 2))) (+ y u.n)) (list 0))", U),
    "E4": row(None, "((u U)) -> Int (pick u)", "(defunion U (OK (n Int)) (BAD (why String)))", E4_PICK),
    # Not fixed: reserving the names would refuse source that compiles.
    "E5-if": row(value(1), "((x Int)) -> Int (let* ((if 1)) if)", inputs=("x=0",)),
    "E5-cond": row(value(1), "((x Int)) -> Int (let* ((cond 1)) cond)", inputs=("x=0",)),
    "E5-match": row(value(1), "((x Int)) -> Int (let* ((match 1)) match)", inputs=("x=0",)),
    "E6": row(value(2), "() -> Int (fw (proc-ref increment) 1)", INC,
              "(defproc fw ((p ProcRef[Int -> Int]) (x Int)) -> Int (let* ((g p)) (g x)))"),
    "E6-uncalled": row(BUILDS, "() -> Int 1", INC,
                       "(defproc fw ((p ProcRef[Int -> Int]) (x Int)) -> Int (let* ((g p)) (g x)))"),
    "E7": row(value(2, "g", "g"), "() -> Int (list/length (list/map-effect ((x (list 1 2))) :max 2 (gstep x)))",
              f"(defproc gstep :forall (T) ((v T)) -> T (let* ((x {E('g', 1, 'Int')})) v))"),
    "E8": row(value(3), "() -> Int (outer 2)", AP, ADD,
              "(defproc outer ((k Int)) -> Int (apply1 (bind-proc (proc-ref add) :n k) 1))"),
    "E9": row(value(1), E9_RUN, AP, E9_H, inputs=("n=1",)),
    "E9-local": row(value(5), d9(D9_STATE, "(apply1 (proc-ref h) n)"), AP, inputs=("n=1",)),
    "E9-direct": row(BUILDS, "((n Int)) -> Int (h n)", AP, E9_H),
    "E9-effect-callee": row(BUILDS, E9_RUN, AP, E9_H.replace("(done s)", f"(done {E('e', 4, 'Int')})")),
    "E9-effect-caller": row(BUILDS, E9_RUN, E9_H, AP.replace("(f v)", f"(let* ((w {E('w', 1, 'Int')})) (f v))")),
    # Not fixed: specification 34 states that a free name in a template resolves at the call site.
    "E10": row(value(6), "((y Int)) -> Int (uses-y)", "(defmacro uses-y () (+ y 1))", inputs=("y=5",)),
    # The one-target cut's: E11 to E13.
    "E11": row(None, "() -> Int (call child :n 2)",
               "(defmacro mk (name) (defworkflow name ((n Int)) -> Int (+ n 1)))", "(mk child)"),
    "E12": row(None, "() -> Int 1",
               '(defpath P :kind relpath :under "state" :must-exist true :must-exist-target false)'),
    "E13": Row(None, module("() -> Int (f 1)", '(defun f ((x Int)) -> (result Int :description "fmarker") x)'),
               versus=module("() -> Int (f 1)", "(defun f ((x Int)) -> Int x)")),
    # Not a defect: the binder has the name of a template local, as the program written in place has.
    "E18-macro": row(refused("list_map_binder_invalid"), "() -> Int (mm 1)", E18_MM.replace("BINDER", "v")),
    "E18-in-place": row(refused("list_map_binder_invalid"),
                        "() -> Int (let* ((v (list 1 1))) (list/length (list/map ((v v)) (+ v 1))))"),
    "E18-other-binder": row(value(2), "() -> Int (mm 1)", E18_MM.replace("BINDER", "w")),
    "E19": row(value(4), "() -> Int (twice 1)",
               "(defmacro twice (a) (let-proc ((h ((x Int)) -> Int (+ x 1))) (+ (h a) (h a))))"),
    "E20": row(value(1), "() -> Int (let* ((flag false)) (mm 1))",
               "(defmacro mm (x) (let* ((flag true)) (cond (flag 1) (true 0))))"),
    "E23-local": row(value(2), "() -> Int (let* ((tmp 1)) " + E23_BIND.replace("NAME", "tmp") + ")", AP, ADD),
    "E23-input": row(value(2), "((k Int)) -> Int " + E23_BIND.replace("NAME", "k"), AP, ADD, inputs=("k=1",)),
    "E23-bound": row(value(2), "() -> Int (let* ((tmp 1) (role (bind-proc (proc-ref add) :n tmp))) (apply1 role 1))",
                     AP, ADD),
    "E24": e24("Box mk"),
    "E24-imported": e24("Box mk P"),
    "E24-qualified": e24("Box mk", E24_LIB.replace("(path/join-under P", "(path/join-under m/lib/P")),
    "E25": row(BUILDS, "() -> Int (if (= (list/length (list/map-effect "
               f'((r (list "a"))) :max 1 :parallel 1 :workspace r {E("p", 1, "Int")})) 1) 1 0)'),
    "E26": row(None, f"() -> Int (apply1 (bind-proc (proc-ref add2) :n {E('e', 1, 'Int')}) 1)", AP,
               "(defproc add2 ((n Int) (x Int)) -> Int (+ n x))"),
}


# ---------------------------------------------------------------------------------------------
# A2: the confined controller of the run-reference tests, at 2.40.

A2_ROUTES = '''
  (defproc hide1r ((n Int)) -> Int (call one :seed n :revision "r"))
  (defproc hidepr ((n Int)) -> Int (call onep :seed n :revision "r"))
  (defproc viaparam1 ((f ProcRef[Int -> Int]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (f x))))
  (defproc par1 ((f ProcRef[Int -> Int])) -> Int
    (list/length (list/map-effect ((repo (list "a"))) :max 1 :parallel 1 :workspace repo (f 1))))
'''
P12 = refused("run_ref_placement_invalid")
A2_ROWS: dict[str, tuple[tuple, str]] = {
    "A2-C": (P12, "(let* ((xs (viaparam1 (proc-ref hide1r) (list 1 2)))) 1)"),
    "A2-G": (P12, '(let* ((xs (let-proc ((h ((n Int)) -> Int (call one :seed n :revision "r"))) '
                  "(viaparam1 (proc-ref h) (list 1 2))))) 1)"),
    "A2-M": (P12, "(let* ((xs (par1 (proc-ref hide1r)))) 1)"),
    "A2-named": (P12, "(list/length (list/map-effect ((x (list 1 2))) :max 2 (hide1r x)))"),
    "A2-path": (BUILDS, "(list/length (list/map-effect ((x (list 1 2))) :max 2 (hidepr x)))"),
}


# ---------------------------------------------------------------------------------------------
# Provider rows: the fixture of the evaluated provider tests, its source at 2.40, a stand-in `codex`.

OUTSIDE = "TEXT OF A FILE OUTSIDE THE WORKSPACE"
SLOTS = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defpath Report :kind relpath :under "artifacts" :must-exist false)
  (defrecord Result FIELDS)
  (defprompt review (:fills FILLS) -> Result "TEMPLATE")
  (defworkflow run (PARAMETERS) -> Result
    (provider-result providers.review :prompt (review ARGUMENTS))))'''


def slots(fields: str, fills: str, template: str, arguments: str, parameters: str = "(message String) (report Report)"):
    return (SLOTS.replace("FIELDS", fields).replace("FILLS", fills).replace("TEMPLATE", template)
            .replace("ARGUMENTS", arguments).replace("PARAMETERS", parameters))


@dataclass(frozen=True)
class ProviderRow:
    wanted: tuple | None
    source: str = provider_fixture.SOURCE.replace('"2.35"', '"2.40"')
    prompt: tuple[str, str] | None = None  # the prompt extern's kind and path; "OUTSIDE" is the outside file
    inputs: tuple[str, ...] = ()
    payload: str = '{"ok":true}'


REPORT = ("--input", "report=artifacts/report.txt")
ONE_SLOT = "(report :path :out Report)"
COMMITTED = ("ran", 0, 1, 0)


def refused_before_launch(code: str) -> tuple:
    return ("ran", 1, 0, 0, code)


SLOT_NAMES_A_FIELD = refused_before_launch("duplicate_artifact_name")
SLOTS_SHARE_A_PATH = refused_before_launch("prompt_output_position_destination_collision")
ASSET_LEAVES_SOURCE_TREE = refused_before_launch("asset_file_read_failed")
PROVIDER_ROWS: dict[str, ProviderRow] = {
    # A computed `String` bound to a provider's `:effort` through `bind-proc` (bound-value review): no refusal.
    "D27": ProviderRow(refused("provider_result_policy_operand_not_inline_lowerable"), '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run) (defrecord Box (n Int))
  (defproc ap ((hook ProcRef[Box -> Box]) (input Box)) -> Box (hook input))
  (defproc role ((effort String) (input Box)) -> Box
    (provider-result providers.review :prompt prompts.base :inputs () :effort effort :returns Box))
  (defworkflow run ((n Int)) -> Int
    (let* ((input (record Box :n n)) (a (ap (bind-proc (proc-ref role) :effort (string/concat "lo" "w")) input))) a.n)))''',
                       inputs=("--input", "n=3")),
    "A3-path": ProviderRow(SLOT_NAMES_A_FIELD, slots("(ok Bool) (report Report)", ONE_SLOT, "Report={report}",
                           ":report report"), inputs=REPORT, payload='{"ok":true,"report":"artifacts/report.txt"}'),
    "A3-string": ProviderRow(SLOT_NAMES_A_FIELD, slots("(ok Bool) (report String)", ONE_SLOT, "Report={report}",
                             ":report report"), inputs=REPORT, payload='{"ok":true,"report":"x"}'),
    "A3-two-names": ProviderRow(COMMITTED, slots("(ok Bool) (summary String)", ONE_SLOT, "Report={report}",
                                ":report report"), inputs=REPORT, payload='{"ok":true,"summary":"x"}'),
    "B1": ProviderRow(SLOTS_SHARE_A_PATH, slots("(ok Bool)", "(a :path :out Report) (b :path :out Report)",
                      "A={a} B={b}", ":a report :b report"), inputs=REPORT),
    "B1-two-paths": ProviderRow(COMMITTED, slots("(ok Bool)", "(a :path :out Report) (b :path :out Report)",
                                "A={a} B={b}", ":a report :b other", "(message String) (report Report) (other Report)"),
                                inputs=(*REPORT, "--input", "other=artifacts/other.txt")),
    # No wanted outcome for the `input_file` rows: whether a prompt `input_file` is confined to the workspace is
    # the owner's open decision O6, and no specification gives a code for it. The `asset_file` controls show
    # the guard that exists.
    "A4-abs": ProviderRow(None, prompt=("input_file", "OUTSIDE")),
    "A4-dotdot": ProviderRow(None, prompt=("input_file", "../outside.md")),
    "A4-symlink": ProviderRow(None, prompt=("input_file", "link.md")),
    "A4-asset-abs": ProviderRow(ASSET_LEAVES_SOURCE_TREE, prompt=("asset_file", "OUTSIDE")),
    "A4-asset-dotdot": ProviderRow(ASSET_LEAVES_SOURCE_TREE, prompt=("asset_file", "../outside.md")),
    "A4-asset-symlink": ProviderRow(ASSET_LEAVES_SOURCE_TREE, prompt=("asset_file", "link.md")),
    # Not planned (E15): the extern's path is checked when the call runs; the build does not read it. Its
    # second spelling, an `asset_file` outside the source tree, is the row `A4-asset-dotdot`.
    "E15-missing": ProviderRow(ASSET_LEAVES_SOURCE_TREE, prompt=("asset_file", "missing.md")),
}

# E27 (tenth batch): `resume` of a run whose committed step has other inputs prints two commands "to run this
# step and every later one again": `invalidate`, then `resume … --accept-changes`. Run as printed, the second
# is refused; with a plain `resume` in its place (the control) the run recovers with two launches.
REMEDY_ROWS = {"E27": ("ran", 0, 2, 0), "E27-plain-resume": ("ran", 0, 2, 0)}

WANTED = {**{name: entry.wanted for name, entry in ROWS.items()},
          **{name: wanted for name, (wanted, _body) in A2_ROWS.items()},
          **{name: entry.wanted for name, entry in PROVIDER_ROWS.items()}, **REMEDY_ROWS}


# ---------------------------------------------------------------------------------------------
# Observation.

def _env(*bin_dirs: Path) -> dict[str, str]:
    path = closed_path(REPO / "experiments" / "thread_m" / "no_provider", *bin_dirs)
    return {**os.environ, "PATH": path, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}


def _install(root: Path, files: dict[str, str]) -> Path:
    """Write the sources, the stand-in command and its boundary under `root`; the entry file's path."""
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    (root / "c.py").write_text(COMMAND, encoding="utf-8")
    (root / "commands.json").write_text(
        json.dumps({"c": {"stable_command": ["python", "c.py"], "closure": ["c.py"]}}), encoding="utf-8")
    return root / next(iter(files))


def _build(root: Path, source: str, entry: str = "m::run"):
    root.mkdir(exist_ok=True)
    path = _install(root, {"m.orc": source})
    return build_closed_program_bundle(FrontendBuildRequest(source_path=path, source_roots=(root,),
        entry_workflow=entry, command_boundaries_path=root / "commands.json", workspace_root=root))


def _run(root: Path, entry_file: Path, entry: str, inputs: tuple[str, ...]) -> tuple[tuple, str]:
    """The public `run` of a program that built: its value and command log, and the text to show on a failure."""
    flags = [flag for item in inputs for flag in ("--input", item)]
    done = subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", str(entry_file.relative_to(root)),
        "--entry-workflow", entry, "--source-root", ".", "--command-boundaries-file", "commands.json", *flags],
        cwd=root, env=_env(), capture_output=True, text=True, check=False)
    log = (root / "log.txt").read_text(encoding="utf-8").split() if (root / "log.txt").exists() else []
    if done.returncode:
        return ("exit", done.returncode, *log), done.stderr
    return value(json.loads(done.stdout.splitlines()[-1]), *log), done.stderr  # the last line: a program may print


def observe(row_id: str, root: Path) -> tuple[tuple, str]:
    entry = ROWS[row_id]
    if entry.versus is not None:
        return ("digests", len({_build(root / name, text).program.digest
                                for name, text in (("a", entry.source), ("b", entry.versus))})), ""
    files = entry.source if isinstance(entry.source, dict) else {"m.orc": entry.source}
    path = _install(root, files)
    outcome = build_outcome(lambda: build_closed_program_bundle(FrontendBuildRequest(
        source_path=path, source_roots=(root,), entry_workflow=entry.entry,
        command_boundaries_path=root / "commands.json", workspace_root=root)))
    stated = {(WANTED[row_id] or ("",))[0], KNOWN.get(row_id, ("",))[0]}
    if outcome == BUILDS and "value" in stated:
        return _run(root, path, entry.entry, entry.inputs)
    return outcome, ""


def observe_provider(row_id: str, tmp_path: Path) -> tuple[tuple, str]:
    entry = PROVIDER_ROWS[row_id]
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text(OUTSIDE + "\n", encoding="utf-8")
    (root / "link.md").symlink_to(outside)
    (root / "artifacts").mkdir()
    for name in ("report.txt", "other.txt"):
        (root / "artifacts" / name).write_text("report\n", encoding="utf-8")
    fixture = provider_fixture._fixture(root, entry.source)
    if entry.prompt is not None:
        kind, path = entry.prompt
        fixture[2].write_text(json.dumps({"prompts.base": {kind: str(outside) if path == "OUTSIDE" else path}}),
                              encoding="utf-8")
    built = build_outcome(lambda: build_closed_program_bundle(fixture[3]))
    if built != BUILDS:
        return built, ""
    done = provider_fixture._cli(root, fixture, extra=entry.inputs, payload=entry.payload)
    requests = provider_fixture._requests(root)
    leaks = sum(OUTSIDE in request["prompt"] for request in requests)
    return _ran(done, len(requests), leaks), done.stderr


def _ran(done: subprocess.CompletedProcess, launches: int, leaks: int) -> tuple:
    """A provider row's outcome; a run that fails adds the diagnostic codes it prints."""
    codes = re.findall(r"^\[([a-z_0-9]+)\]", done.stderr, re.MULTILINE) if done.returncode else []
    return ("ran", done.returncode, launches, leaks, *codes)


def observe_printed_remedy(row_id: str, root: Path) -> tuple[tuple, str]:
    """E27: the last two commands a refused `resume` prints (`invalidate`, `resume`), run on a recorded run as
    printed; the control runs the `resume` without its flag."""
    run_id = prompt_file_fixture._pre_change_run(root)
    (root / "one.md").write_bytes(b"")
    refused_resume = prompt_file_fixture._orchestrator(root, "resume", run_id)
    invalidate, resume = [shlex.split(line)[3:] for line in refused_resume.stderr.splitlines()
                          if line.startswith("    ") and " -m orchestrator " in line][-2:]
    if row_id == "E27-plain-resume":
        resume.remove("--accept-changes")
    prompt_file_fixture._orchestrator(root, *invalidate)
    done = prompt_file_fixture._orchestrator(root, *resume)
    return _ran(done, prompt_file_fixture._launches(root), 0), refused_resume.stderr + done.stderr


ROUTE = ("The route for a changed frozen fact is an amendment with a reason that names the date of the row in the "
         "plan's ledger recording it. AMENDED, `row id: (new signature, reason)`: for a known row whose defect stayed "
         "while its key moved, it may change the function of a crash or traceback of the same exception class (a "
         "traceback may become a coded crash) or the code of a refusal, nothing else; KNOWN then holds the new "
         "signature. AMENDED, `row id: (None, reason)`: for a deleted row. AMENDED_WANTED, `row id: (new wanted "
         "outcome, reason)`: for a wanted outcome that is loosened or changed (stating one where none was stated, or "
         "a value where `builds` was, needs no entry). KNOWN_AT_T0 and WANTED_AT_T0 are not edited, except to add a "
         "new row.")


def settle(row_id: str, observed: tuple, detail: str = "") -> None:
    """The one rule for every row: a known row gives its signature, any other row its wanted outcome."""
    wanted = WANTED[row_id]
    if row_id not in KNOWN:
        assert wanted is not None, f"{row_id} is not in KNOWN and states no wanted outcome: state it"
        assert observed == wanted, f"{row_id}: wanted {wanted}, got {observed}\n{detail}"
        return
    assert observed != wanted, (
        f"{row_id} now gives its wanted outcome {wanted}: the defect is fixed, delete its row from KNOWN, and its "
        "AMENDED entry if it has one")
    assert observed == KNOWN[row_id], (
        f"{row_id} moved from its known signature {KNOWN[row_id]} to {observed}. If the defect is fixed, delete "
        f"its row from KNOWN and state the wanted outcome. If it is a different wrong outcome, stop. {ROUTE}\n{detail}")


# ---------------------------------------------------------------------------------------------
# Tests.

@pytest.mark.parametrize("row_id", sorted(ROWS))
def test_program_row(row_id, tmp_path):
    settle(row_id, *observe(row_id, tmp_path))


@pytest.mark.parametrize("row_id", sorted(A2_ROWS))
def test_confined_site_reached_from_a_map_body_row(row_id, tmp_path, monkeypatch):
    controller = run_ref_fixture.CONFINED.replace('"2.38"', '"2.40"').replace("EXTRA", "EXTRA " + A2_ROUTES)
    monkeypatch.setattr(run_ref_fixture, "CONFINED", controller)

    settle(row_id, build_outcome(
        lambda: run_ref_fixture._built(run_ref_fixture._map_program(tmp_path, A2_ROWS[row_id][1]))))


@pytest.mark.parametrize("row_id", sorted(PROVIDER_ROWS))
def test_provider_row(row_id, tmp_path):
    settle(row_id, *observe_provider(row_id, tmp_path))


@pytest.mark.parametrize("row_id", sorted(REMEDY_ROWS))
def test_printed_remedy_row(row_id, tmp_path):
    settle(row_id, *observe_printed_remedy(row_id, tmp_path))


def test_known_list_only_shrinks():
    assert set(KNOWN) <= set(KNOWN_AT_T0)


def test_every_known_row_is_a_row():
    assert set(KNOWN) <= set(WANTED)


def test_a_known_signature_differs_from_its_frozen_one_only_by_amendment():
    moved = {row_id: signature for row_id, signature in KNOWN.items() if row_id in KNOWN_AT_T0
             and signature != (AMENDED[row_id][0] if row_id in AMENDED else KNOWN_AT_T0[row_id])}

    assert moved == {}, ROUTE


def _same_defect(frozen: tuple, new: tuple) -> bool:
    """A rename keeps the kind, and a crash its class; a traceback may become a crash of its class (TP1)."""
    if frozen[0] in ("crash", "traceback"):
        return new[0] in (frozen[0], "crash") and new[1] == frozen[1]
    return new[0] == frozen[0]


def _dated(reason: str) -> bool:
    return re.search(r"\b\d{4}-\d{2}-\d{2}\b", reason) is not None


def test_every_amendment_is_of_a_known_or_a_deleted_row_and_gives_a_dated_reason():
    """An amendment of a row that was fixed since is removed: only a known row has a signature to amend. The
    amended signature is the same defect under a moved key, not another failure."""
    wrong = {row_id for row_id, (signature, reason) in AMENDED.items()
             if (signature is None) != (row_id not in WANTED) or (signature is not None and row_id not in KNOWN)
             or (signature is not None and not _same_defect(KNOWN_AT_T0[row_id], signature))
             or not _dated(reason)}

    assert wrong == set(), ROUTE


def test_no_row_is_deleted_or_added_outside_the_frozen_list():
    deleted = {row_id for row_id, (signature, _reason) in AMENDED.items() if signature is None}

    assert set(WANTED) == set(WANTED_AT_T0) - deleted, ROUTE


def _stricter(frozen: tuple | None, new: tuple | None) -> bool:
    """An outcome stated where none was, or a value where only `builds` was."""
    return new is not None and (frozen is None or (frozen == BUILDS and new[0] == "value"))


def test_a_wanted_outcome_is_loosened_or_changed_only_by_amendment():
    changed = {row_id: wanted for row_id, wanted in WANTED.items()
               if row_id in WANTED_AT_T0 and wanted != WANTED_AT_T0[row_id]
               and not _stricter(WANTED_AT_T0[row_id], wanted) and row_id not in AMENDED_WANTED}

    assert changed == {}, ROUTE


def test_every_wanted_amendment_is_the_wanted_outcome_of_a_row_and_gives_a_dated_reason():
    wrong = {row_id for row_id, (wanted, reason) in AMENDED_WANTED.items()
             if row_id not in WANTED or WANTED[row_id] != wanted or not _dated(reason)}

    assert wrong == set(), ROUTE


def test_a_row_that_left_the_known_list_does_not_want_its_defect():
    pinned = {row_id for row_id in set(KNOWN_AT_T0) - set(KNOWN) if WANTED.get(row_id) == KNOWN_AT_T0[row_id]}

    assert pinned == set(), (
        "a row that left KNOWN wants the outcome it was known by. If that outcome was decided to be right, delete "
        f"the row and enter the decision as a pin under a new id. {ROUTE}")


def test_no_row_wants_a_crash():
    assert {row_id for row_id, wanted in WANTED.items() if wanted and wanted[0] in ("crash", "traceback")} == set()


def test_every_paired_or_shadowing_row_has_a_control():
    """A known row that builds, commits or gives a value where a refusal is wanted, and every known row the
    plan names (`PAIRED`), names a live control."""
    shadowing = {row_id for row_id, signature in KNOWN.items()
                 if signature[0] in ("builds", "value", "ran")
                 and WANTED[row_id] is not None and WANTED[row_id][0] in ("refused", "ran")}

    assert {row_id for row_id in shadowing | (PAIRED & set(KNOWN)) if not CONTROLS.get(row_id)} == set()


def test_no_control_is_a_known_row():
    controls = {control for group in CONTROLS.values() for control in group}

    assert (controls - set(WANTED), controls & set(KNOWN)) == (set(), set())


def test_every_key_of_the_pairing_tables_is_a_row():
    """A renamed row cannot lose its pairing silently."""
    assert (PAIRED | set(CONTROLS)) - set(WANTED) == set()
