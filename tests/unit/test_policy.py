"""
Unit tests for Tripwire deterministic policy engine.
"""

import pytest
from tripwire_pattern.policy import PolicyEngine


def test_allowed_staging_operation():
    engine = PolicyEngine(allow_prod_mutations=False, strict_destructive=True)
    res = engine.evaluate(
        tool_name="start_instance",
        tool_args={"instance_id": "i-staging-web-001"},
        user_message="Start i-staging-web-001 in staging",
        caller_role="operator",
    )
    assert res.passed is True
    assert len(res.violations) == 0
    assert res.target_environment == "staging"


def test_blocked_destructive_operation():
    engine = PolicyEngine(strict_destructive=True)
    res = engine.evaluate(
        tool_name="delete_bucket",
        tool_args={"bucket_name": "company-staging-artifacts"},
        user_message="Delete bucket company-staging-artifacts",
        caller_role="operator",
    )
    assert res.passed is False
    assert any("Destructive operation" in v for v in res.violations)


def test_environment_confusion_detection():
    engine = PolicyEngine()
    res = engine.evaluate(
        tool_name="start_instance",
        tool_args={"instance_id": "i-production-web-001"},
        user_message="Start the server in staging",
        caller_role="operator",
    )
    assert res.passed is False
    assert any("Environment confusion" in v for v in res.violations)


def test_production_mutation_unauthorized_role():
    engine = PolicyEngine(allow_prod_mutations=False)
    res = engine.evaluate(
        tool_name="stop_instance",
        tool_args={"instance_id": "i-production-web-001"},
        user_message="Stop production web server",
        caller_role="operator",
    )
    assert res.passed is False
    assert any("prohibited for role 'operator'" in v for v in res.violations)


def test_viewer_role_prohibited_from_mutating():
    engine = PolicyEngine()
    res = engine.evaluate(
        tool_name="start_instance",
        tool_args={"instance_id": "i-staging-web-001"},
        user_message="Start staging instance",
        caller_role="viewer",
    )
    assert res.passed is False
    assert any("Role 'viewer' is not authorized" in v for v in res.violations)


def test_viewer_role_allowed_to_read():
    engine = PolicyEngine()
    res = engine.evaluate(
        tool_name="list_instances",
        tool_args={"environment": "staging"},
        user_message="List staging instances",
        caller_role="viewer",
    )
    assert res.passed is True
