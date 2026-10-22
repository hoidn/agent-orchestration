"""Source-free admission of typed serial host requests."""
from collections.abc import Mapping

from orchestrator.workflow.type_descriptor import is_transportable_type_descriptor

_STRING = {"kind": "primitive", "name": "String"}
_INT = {"kind": "primitive", "name": "Int"}


def check_request_input(checker, node, env, **walk):
    if checker.tree['target'] != '2.40':
        checker.fail('effect_class', 'host input requires target 2.40', node)
    required = {'k', 'class', 'result', 'answer', 'repeat', 'show'}
    if not required <= set(node) or set(node) - required - {'site', '@', 'question', 'prompt', 'timeout_sec'}:
        checker.fail('effect_shape', 'host request has missing or unexpected fields', node)
    if ('question' in node) == ('prompt' in node):
        checker.fail('effect_shape', 'host request requires exactly one question or prompt', node)
    if node['repeat'] != 'rerun':
        checker.fail('effect_repeat', 'host input repeat must be rerun', node)
    answer = node['answer']
    checker._validate_descriptor(answer, node=node)
    if not (answer == _STRING or answer.get('kind') in {'enum', 'union'}) or not is_transportable_type_descriptor(answer, allow_nested_structures=True):
        checker.fail('effect_result', 'host answer must be String, enum or closed transportable union', node)
    expected = {'kind': 'union', 'name': f"std/host::HostReply[{answer['name']}]", 'variants': [
        {'name': 'ANSWERED', 'fields': [{'name': 'value', 'type': answer}, {'name': 'by', 'type': _STRING}]},
        {'name': 'CANCELLED', 'fields': [{'name': 'by', 'type': _STRING}]},
        {'name': 'EXPIRED', 'fields': []}]}
    if not checker._same(node['result'], expected):
        checker.fail('effect_result', 'host result must be the canonical instantiated std/host::HostReply', node)
    if 'question' in node:
        checker._require_type(checker._value(node['question'], env, allow_effect=False, **walk), _STRING, 'effect_shape', node)
    else:
        prompt = node['prompt']
        if not isinstance(prompt, Mapping) or set(prompt) != {'template', 'fills'} or not isinstance(prompt['template'], str) or not isinstance(prompt['fills'], list):
            checker.fail('effect_shape', 'host question prompt is malformed', node)
        checker._check_provider_prompt_fills(prompt, node=node, env=env, **walk)
    if 'timeout_sec' in node:
        value = node['timeout_sec']
        checker._require_type(checker._value(value, env, allow_effect=False, **walk), _INT, 'effect_shape', node)
        if value.get('k') == 'lit' and (type(value['v']) is not int or value['v'] <= 0):
            checker.fail('effect_shape', 'host timeout must be positive', node)
    if not isinstance(node['show'], list):
        checker.fail('effect_shape', 'host shown evidence must be an ordered array', node)
    for value in node['show']:
        actual = checker._value(value, env, allow_effect=False, **walk)
        if actual.get('kind') != 'path':
            checker.fail('effect_shape', 'host evidence requires typed file paths', node)
