from copy import deepcopy

import pytest

from orchestrator.workflow_lisp.closed.check import _Checker, CheckedFormError
from orchestrator.workflow_lisp.closed.names import key_type_descriptor, _normalize_closed_value
from tests.test_workflow_lisp_closed_program_check import _tree


INT = {"kind": "primitive", "name": "Int"}
STRING = {"kind": "primitive", "name": "String"}


def record(name, child=STRING):
    return {"kind": "record", "name": name, "fields": [{"name": "item", "type": child}]}


def union(name, child=STRING, tags=("A", "B")):
    return {"kind": "union", "name": name, "variants": [
        {"name": tag, "fields": [{"name": "item", "type": child}]} for tag in tags]}


def case(owner, tag="A"):
    return {"kind": "variant_case", "union_name": owner["name"], "variant": tag,
            "fields": next(row["fields"] for row in owner["variants"] if row["name"] == tag)}


def path(name, root="state", exists=False):
    return {"kind": "path", "name": name, "under": root, "must_exist_target": exists}


def checker(*descriptors):
    tree = _tree()
    def register(descriptor):
        kind = descriptor["kind"]
        if kind in {"record", "union", "enum", "path"}:
            tree["types"][descriptor["name"]] = descriptor
        if kind in {"record", "variant_case"}:
            for row in descriptor["fields"]:
                register(row["type"])
        elif kind == "union":
            for variant in descriptor["variants"]:
                for row in variant["fields"]:
                    register(row["type"])
        elif kind in {"list", "optional"}:
            register(descriptor["item"])
        elif kind == "map":
            register(descriptor["key"])
            register(descriptor["value"])
    for descriptor in descriptors:
        register(descriptor)
    result = _Checker(tree)
    result.types = tree["types"]
    result._validate_type_table()
    return result


@pytest.mark.parametrize("wrapper", [lambda x: x, lambda x: record("entry::Wrapper", x),
    lambda x: {"kind": "optional", "item": x}, lambda x: {"kind": "list", "item": x},
    lambda x: {"kind": "map", "key": STRING, "value": x}])
@pytest.mark.parametrize("key_domain", [False, True])
def test_shared_relation_conserves_case_proof_recursively(wrapper, key_domain):
    owner = union("entry::Inner")
    actual, target = wrapper(owner), wrapper(case(owner))
    check = checker(owner, actual, target)
    project = lambda d: key_type_descriptor(d, run_ref_signatures={}) if key_domain else d
    assert not check._shared_compatible(project(target), project(actual), key_domain=key_domain)
    assert check._shared_compatible(project(actual), project(target), key_domain=key_domain)
    assert check._shared_compatible(project(target), project(target), key_domain=key_domain)


@pytest.mark.parametrize("key_domain", [False, True])
@pytest.mark.parametrize("actual,target,compatible", [
    (record("entry::Payload"), record("helper::Payload"), True),
    (record("entry::Payload", INT), record("helper::Payload"), False),
    (record("entry::Different"), record("helper::Payload"), False),
    (union("entry::Choice"), union("helper::Choice"), True),
    (union("entry::Choice", INT), union("helper::Choice"), False),
    ({"kind": "enum", "name": "entry::Status", "allowed": ["a", "b"]},
     {"kind": "enum", "name": "helper::Status", "allowed": ["a", "b"]}, True),
    ({"kind": "enum", "name": "entry::Status", "allowed": ["a", "b"]},
     {"kind": "enum", "name": "helper::Status", "allowed": ["b", "a"]}, False),
])
def test_shared_source_nominals_compare_contracts_without_erasure(actual, target, compatible, key_domain):
    check = checker(actual, target)
    if key_domain:
        actual, target = [key_type_descriptor(d, run_ref_signatures={}) for d in (actual, target)]
    assert check._shared_compatible(target, actual, key_domain=key_domain) is compatible
    assert actual != target


def test_direct_path_assignment_does_not_weaken_recursive_paths():
    actual, target = path("entry::Report", exists=True), path("Path.state-root")
    check = checker(actual, target)
    assert check._shared_assignable(actual, target, key_domain=False)
    assert not check._shared_compatible(record("entry::Box", target), record("helper::Box", actual), key_domain=False)
    assert not check._shared_compatible({"kind": "list", "item": target}, {"kind": "list", "item": actual}, key_domain=False)


def test_alpha_normalization_keeps_aligned_shared_targets():
    target = record("helper::Payload")
    value = {"k": "block", "body": {"k": "let", "name": "authored", "label": "label",
        "value": {"k": "inject", "type": union("entry::Choice"), "variant": "A", "fields": [["item", {"k": "lit", "v": "s", "type": STRING}]]},
        "body": {"k": "halt", "value": {"k": "field", "base": {"k": "name", "n": "authored"}, "path": ["item"], "shared": [target]}}}}
    normalized = _normalize_closed_value(value)
    assert normalized["body"]["body"]["value"]["shared"] == [target]


DECLARATIONS = '''
  (defenum Status A B)
  (defpath ReportPath :kind relpath :under "state" :must-exist true)
  (defrecord Payload (item-id FIELD_TYPE))
  (defrecord Box (item Payload))
  (defrecord PathBox (item ReportPath))
  (defunion Choice (A (item Payload)) (B (item Payload)))
  (defunion Pair :forall (L R) (ONLY (item Int)))'''


@pytest.fixture(params=["String", "Int"])
def source_types(tmp_path, request):
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from tests.workflow_lisp_closed_program_helpers import install
    helper = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule helper) (export Status ReportPath Payload Box PathBox Choice Pair)
      DECLARATIONS)'''.replace("DECLARATIONS", DECLARATIONS.replace("FIELD_TYPE", "String"))
    entry = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule entry) (import helper :as h) (export run)
      DECLARATIONS (defworkflow run () -> Int 0))'''.replace("DECLARATIONS", DECLARATIONS.replace("FIELD_TYPE", request.param))
    source = install(tmp_path, {"helper.orc": helper, "entry.orc": entry}, entry_path="entry.orc")
    return compile_typed_program(source, entry_workflow=None, source_roots=(tmp_path,), command_boundaries={})


@pytest.mark.parametrize("actual_name,target_name", [
    ("Payload", "h.Payload"), ("Box", "h.Box"), ("Status", "h.Status"),
    ("Choice", "h.Choice"), ("Optional[Payload]", "Optional[h.Payload]"),
    ("List[Payload]", "List[h.Payload]"), ("Map[String,Payload]", "Map[String,h.Payload]"),
    ("Payload", "h.Box"), ("ReportPath", "Path.state-root"),
    ("List[ReportPath]", "List[Path.state-root]"),
    ("h.Pair[Payload Int]", "h.Pair[h.Payload Int]"),
    ("h.Pair[Payload Int]", "h.Pair[h.Payload String]"),
    ("h.Pair[Payload Int]", "h.Pair[Int h.Payload]"),
    ("Pair[Payload Int]", "h.Pair[Payload Int]"),
])
@pytest.mark.parametrize("key_domain", [False, True])
def test_local_assignment_matches_unchanged_source_oracle(source_types, actual_name, target_name, key_domain):
    from orchestrator.workflow_lisp.closed.names import canonical_type_descriptor
    from orchestrator.workflow_lisp.parametric_constraints import constraint_field_type_satisfied
    env = source_types.type_env
    origin = source_types.entry.definition
    resolve = lambda name: env.resolve_type(name, span=origin.span, form_path=origin.form_path)
    actual_ref, target_ref = resolve(actual_name), resolve(target_name)
    actual, target = [canonical_type_descriptor(ref, typed=source_types) for ref in (actual_ref, target_ref)]
    # Phantom arguments do not occur in payloads, so register their complete facts too.
    payloads = [canonical_type_descriptor(resolve(name), typed=source_types) for name in ("Payload", "h.Payload")]
    check = checker(actual, target, *payloads)
    project = lambda d: key_type_descriptor(d, run_ref_signatures={}) if key_domain else d
    assert check._shared_assignable(project(actual), project(target), key_domain=key_domain) == constraint_field_type_satisfied(actual_ref, target_ref)


@pytest.mark.parametrize("key_domain", [False, True])
@pytest.mark.parametrize("target_tag,actual_tag,target_payload,expected", [
    ("A", "A", STRING, True), ("B", "A", STRING, False),
    ("A", "A", INT, False),
])
def test_cross_owner_cases_require_existing_tag_and_matching_payload(key_domain, target_tag, actual_tag, target_payload, expected):
    actual_owner, target_owner = union("entry::Inner"), union("helper::Inner", target_payload)
    actual, target = case(actual_owner, actual_tag), case(target_owner, target_tag)
    check = checker(actual_owner, target_owner)
    project = lambda d: key_type_descriptor(d, run_ref_signatures={}) if key_domain else d
    for descriptor in (actual, target):
        check._shared_validate_descriptor(project(descriptor), {}, key_domain=key_domain)
    assert check._shared_compatible(project(target), project(actual), key_domain=key_domain) is expected
    assert check._shared_compatible(project(target_owner), project(actual), key_domain=key_domain) is (target_payload == STRING)


@pytest.mark.parametrize("key_domain", [False, True])
def test_discriminants_keep_complete_tags_and_internal_family(key_domain):
    actual_owner, target_owner = union("entry::Choice"), union("helper::Choice")
    different_owner = union("third::Choice", tags=("A", "C"))
    discriminant = lambda owner: {"kind": "enum", "name": owner["name"] + ".variant", "allowed": [row["name"] for row in owner["variants"]]}
    actual, target, different = [discriminant(owner) for owner in (actual_owner, target_owner, different_owner)]
    declared = {"kind": "enum", "name": "plain::Choice.variant", "allowed": ["A", "B"]}
    check = checker(actual_owner, target_owner, different_owner, actual, target, different, declared)
    project = lambda d: key_type_descriptor(d, run_ref_signatures={}) if key_domain else d
    assert check._shared_compatible(project(target), project(actual), key_domain=key_domain)
    assert not check._shared_compatible(project(different), project(actual), key_domain=key_domain)
    assert not check._shared_compatible(project(declared), project(actual), key_domain=key_domain)
    assert not check._shared_compatible(project(actual), project(declared), key_domain=key_domain)


@pytest.mark.parametrize("key_domain", [False, True])
def test_shared_key_nominal_target_must_match_projected_catalog(key_domain):
    target = record("helper::Payload")
    check = checker(target)
    forged = deepcopy(target)
    forged["fields"][0]["type"] = INT
    project = lambda d: key_type_descriptor(d, run_ref_signatures={}) if key_domain else d
    with pytest.raises(CheckedFormError) as error:
        check._shared_validate_descriptor(project(forged), {}, key_domain=key_domain)
    assert error.value.rule == ("definition_key" if key_domain else "nominal_definition")


def test_generated_runtime_identity_is_stricter_than_full_signature_key_equality():
    from tests.test_workflow_lisp_closed_program_check import _run_ref_tree
    tree, _, config = _run_ref_tree()
    check = _Checker(tree)
    check.run()
    actual = config.result_descriptor["envelope"]
    other = deepcopy(actual)
    other["name"] = "RunRefResult$" + "a" * 16
    signatures = {**check.run_ref_signatures, other["name"]: check.run_ref_signatures[actual["name"]]}
    assert not check._shared_assignable(actual, other, key_domain=False)
    projected = [key_type_descriptor(d, run_ref_signatures=signatures) for d in (actual, other)]
    assert projected[0] == projected[1]
    assert projected[0]["kind"] == "run-ref-result"
    assert check._shared_assignable(*projected, key_domain=True)
    node = {"k": "field", "base": {"k": "lit", "v": 0, "type": INT},
            "path": ["result"], "shared": [actual]}
    normalized = _normalize_closed_value(node, run_ref_signatures=signatures)
    assert normalized["shared"] == [projected[0]]
    check._shared_validate_descriptor(projected[0], {}, key_domain=True)
    tampered = deepcopy(projected[0])
    tampered["signature"]["inputs"][0][1] = STRING
    with pytest.raises(CheckedFormError) as error:
        check._shared_validate_descriptor(tampered, {}, key_domain=True)
    assert error.value.rule == "definition_key"


@pytest.mark.parametrize("key_domain", [False, True])
def test_applied_owners_preserve_ordered_internal_discriminant_arguments(key_domain):
    owners = [union(name) for name in ("entry::Choice", "helper::Choice")]
    enums = [{"kind": "enum", "name": owner["name"] + ".variant", "allowed": ["A", "B"]} for owner in owners]
    applied = [union("shared::Pair[" + enum["name"] + " Int]", INT, tags=("ONLY",)) for enum in enums]
    check = checker(*owners, *enums, *applied)
    project = lambda d: key_type_descriptor(d, run_ref_signatures={}) if key_domain else d
    assert check._shared_compatible(project(applied[0]), project(applied[1]), key_domain=key_domain)
    wrong = union("shared::Pair[Int helper::Choice.variant]", INT, tags=("ONLY",))
    assert not check._shared_compatible(project(applied[0]), project(wrong), key_domain=key_domain)
