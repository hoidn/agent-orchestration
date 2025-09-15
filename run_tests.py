#!/usr/bin/env python3
"""Test runner for the orchestrator"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from orchestrator.workflow.loader import WorkflowLoader, ValidationError


def test_valid_workflow():
    """Test loading a valid workflow"""
    loader = WorkflowLoader()
    workflow_path = project_root / "workflows/examples/test_strict_validation.yaml"

    try:
        workflow = loader.load(workflow_path)
        print(f"✅ Valid workflow loaded: {workflow.name}")
        print(f"   Version: {workflow.version}")
        print(f"   Steps: {len(workflow.steps)}")
        return True
    except ValidationError as e:
        print(f"❌ Unexpected validation error: {e}")
        return False


def test_invalid_workflow():
    """Test that invalid workflow is rejected (AT-10)"""
    loader = WorkflowLoader()
    workflow_path = project_root / "workflows/examples/test_provider_command_exclusivity.yaml"

    try:
        workflow = loader.load(workflow_path)
        print(f"❌ Invalid workflow was not rejected!")
        return False
    except ValidationError as e:
        print(f"✅ Invalid workflow correctly rejected: {e}")
        return True


def test_unknown_field_rejection():
    """Test that unknown fields are rejected (AT-7)"""
    import tempfile
    import yaml

    loader = WorkflowLoader()

    # Create a workflow with an unknown field
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            'version': '1.1',
            'unknown_field_xyz': 'should fail',  # Unknown field
            'steps': [
                {'name': 'test', 'command': ['echo', 'test']}
            ]
        }, f)
        temp_path = Path(f.name)

    try:
        workflow = loader.load(temp_path)
        print(f"❌ Workflow with unknown field was not rejected!")
        temp_path.unlink()
        return False
    except ValidationError as e:
        print(f"✅ Unknown field correctly rejected: {e}")
        temp_path.unlink()
        return True


def test_version_gating():
    """Test version gating for inject feature (AT-28)"""
    import tempfile
    import yaml

    loader = WorkflowLoader()

    # Test 1: inject with v1.1 should fail
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            'version': '1.1',
            'steps': [{
                'name': 'test',
                'command': ['echo', 'test'],
                'depends_on': {
                    'required': ['file.txt'],
                    'inject': True  # Should fail with v1.1
                }
            }]
        }, f)
        temp_path = Path(f.name)

    try:
        workflow = loader.load(temp_path)
        print(f"❌ inject with v1.1 was not rejected!")
        temp_path.unlink()
        return False
    except ValidationError as e:
        print(f"✅ inject correctly requires v1.1.1: {e}")
        temp_path.unlink()

    # Test 2: inject with v1.1.1 should succeed
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            'version': '1.1.1',
            'steps': [{
                'name': 'test',
                'command': ['echo', 'test'],
                'depends_on': {
                    'required': ['file.txt'],
                    'inject': True  # Should work with v1.1.1
                }
            }]
        }, f)
        temp_path = Path(f.name)

    try:
        workflow = loader.load(temp_path)
        print(f"✅ inject works with v1.1.1")
        temp_path.unlink()
        return True
    except ValidationError as e:
        print(f"❌ inject failed with v1.1.1: {e}")
        temp_path.unlink()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Running Orchestrator Loader Tests")
    print("=" * 60)

    tests = [
        ("Valid workflow loading", test_valid_workflow),
        ("Invalid workflow rejection (AT-10)", test_invalid_workflow),
        ("Unknown field rejection (AT-7)", test_unknown_field_rejection),
        ("Version gating (AT-28)", test_version_gating),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n{name}:")
        results.append(test_func())

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("✅ All tests passed!")
        return 0
    else:
        print(f"❌ {total - passed} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())