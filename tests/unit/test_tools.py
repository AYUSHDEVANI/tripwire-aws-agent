"""
Unit tests for mock AWS tools and state transitions.
"""

import pytest
from agent.tools import (
    reset_mock_environment,
    get_mock_environment,
    list_instances,
    describe_instance,
    start_instance,
    stop_instance,
    delete_bucket,
)


def setup_function():
    reset_mock_environment()


def test_list_instances():
    res = list_instances(environment="all")
    assert res["status"] == "success"
    assert res["count"] == 3
    assert res["mode"] == "simulated"

    staging_res = list_instances(environment="staging")
    assert staging_res["count"] == 2


def test_describe_instance():
    res = describe_instance(instance_id="i-staging-web-001")
    assert res["status"] == "success"
    assert res["instance"]["environment"] == "staging"
    assert res["instance"]["state"] == "stopped"

    err_res = describe_instance(instance_id="i-non-existent")
    assert err_res["status"] == "error"
    assert err_res["error_code"] == "InstanceNotFound"


def test_start_instance_state_transition():
    # Initially stopped
    assert get_mock_environment()["instances"]["i-staging-web-001"]["state"] == "stopped"

    res = start_instance(instance_id="i-staging-web-001")
    assert res["status"] == "success"
    assert res["current_state"] == "running"
    assert get_mock_environment()["instances"]["i-staging-web-001"]["state"] == "running"

    # No-op when already running
    noop_res = start_instance(instance_id="i-staging-web-001")
    assert noop_res["status"] == "no_op"


def test_stop_instance_state_transition():
    # Initially running
    assert get_mock_environment()["instances"]["i-staging-web-002"]["state"] == "running"

    res = stop_instance(instance_id="i-staging-web-002")
    assert res["status"] == "success"
    assert res["current_state"] == "stopped"
    assert get_mock_environment()["instances"]["i-staging-web-002"]["state"] == "stopped"


def test_delete_bucket():
    res = delete_bucket(bucket_name="company-staging-artifacts")
    assert res["status"] == "success"
    assert "company-staging-artifacts" not in get_mock_environment()["buckets"]

    err_res = delete_bucket(bucket_name="non-existent-bucket")
    assert err_res["status"] == "error"
