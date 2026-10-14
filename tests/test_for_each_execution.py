"""
Test suite for for-each loop execution.
Tests AT-3 and AT-13: Dynamic for-each with pointer resolution.
"""

import pytest

from orchestrator.workflow.pointers import PointerResolver


class TestPointerResolution:
    """Test pointer resolution for items_from."""

    def test_at3_items_from_lines(self):
        """AT-3: items_from with steps.X.lines pointer."""
        state = {
            'steps': {
                'ListFiles': {
                    'exit_code': 0,
                    'lines': ['file1.txt', 'file2.txt', 'file3.txt']
                }
            }
        }

        resolver = PointerResolver(state)
        result = resolver.resolve('steps.ListFiles.lines')

        assert result == ['file1.txt', 'file2.txt', 'file3.txt']

    def test_at13_items_from_json_nested(self):
        """AT-13: items_from with nested JSON path."""
        state = {
            'steps': {
                'ParseData': {
                    'exit_code': 0,
                    'json': {
                        'results': {
                            'files': ['a.json', 'b.json', 'c.json']
                        },
                        'count': 3
                    }
                }
            }
        }

        resolver = PointerResolver(state)

        # Test nested path resolution
        result = resolver.resolve('steps.ParseData.json.results.files')
        assert result == ['a.json', 'b.json', 'c.json']

        # Test single-level JSON access
        result = resolver.resolve('steps.ParseData.json.count')
        assert result == 3

    def test_invalid_pointer_syntax(self):
        """Test invalid pointer syntax is rejected."""
        resolver = PointerResolver({})

        with pytest.raises(ValueError, match="Invalid pointer syntax"):
            resolver.resolve('invalid.pointer')

        with pytest.raises(ValueError, match="Invalid pointer syntax"):
            resolver.resolve('steps')

    def test_missing_step_in_pointer(self):
        """Test pointer to non-existent step."""
        resolver = PointerResolver({'steps': {}})

        with pytest.raises(ValueError, match="Step 'Missing' not found"):
            resolver.resolve('steps.Missing.lines')

    def test_missing_output_type(self):
        """Test pointer to missing output type."""
        state = {
            'steps': {
                'Test': {
                    'exit_code': 0,
                    'text': 'some output'
                }
            }
        }

        resolver = PointerResolver(state)

        with pytest.raises(ValueError, match="does not have 'lines' output"):
            resolver.resolve('steps.Test.lines')

        with pytest.raises(ValueError, match="does not have 'json' output"):
            resolver.resolve('steps.Test.json')

    def test_invalid_json_path_navigation(self):
        """Test invalid JSON path navigation."""
        state = {
            'steps': {
                'Test': {
                    'exit_code': 0,
                    'json': {
                        'value': 'not_an_object'
                    }
                }
            }
        }

        resolver = PointerResolver(state)

        with pytest.raises(ValueError, match="is not an object"):
            resolver.resolve('steps.Test.json.value.nested')

        with pytest.raises(ValueError, match="missing key"):
            resolver.resolve('steps.Test.json.nonexistent')

    def test_safe_resolution(self):
        """Test safe resolution with error handling."""
        state = {
            'steps': {
                'Test': {
                    'lines': ['a', 'b']
                }
            }
        }

        resolver = PointerResolver(state)

        # Successful resolution
        success, value, error = resolver.resolve_safe('steps.Test.lines')
        assert success is True
        assert value == ['a', 'b']
        assert error is None

        # Failed resolution
        success, value, error = resolver.resolve_safe('steps.Missing.lines')
        assert success is False
        assert value is None
        assert "not found" in error
