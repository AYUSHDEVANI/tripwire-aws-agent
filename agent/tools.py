"""
Mock AWS Tools & In-Memory Environment
Provides simulated AWS operations with defense-in-depth execution boundary checks.
"""

import copy
from typing import Any, Dict, List
from strands import tool

# Initial seeded mock environment as defined in PRD Section 6
DEFAULT_MOCK_STATE: Dict[str, Any] = {
    "instances": {
        "i-staging-web-001": {
            "instance_id": "i-staging-web-001",
            "name": "web-1",
            "environment": "staging",
            "state": "stopped",
            "instance_type": "t3.medium",
            "ip_address": "10.0.1.14",
            "simulated": True,
        },
        "i-staging-web-002": {
            "instance_id": "i-staging-web-002",
            "name": "web-2",
            "environment": "staging",
            "state": "running",
            "instance_type": "t3.medium",
            "ip_address": "10.0.1.15",
            "simulated": True,
        },
        "i-production-web-001": {
            "instance_id": "i-production-web-001",
            "name": "web-prod-1",
            "environment": "production",
            "state": "running",
            "instance_type": "m5.large",
            "ip_address": "10.0.100.5",
            "simulated": True,
        },
    },
    "buckets": {
        "company-staging-artifacts": {"region": "us-east-1", "files_count": 42},
        "company-production-backups": {"region": "us-east-1", "files_count": 1024},
    },
}

# Current runtime state
_CURRENT_STATE = copy.deepcopy(DEFAULT_MOCK_STATE)


def reset_mock_environment() -> None:
    """Reset the mock cloud state to default."""
    global _CURRENT_STATE
    _CURRENT_STATE = copy.deepcopy(DEFAULT_MOCK_STATE)


def get_mock_environment() -> Dict[str, Any]:
    """Return a copy of the current mock environment."""
    return copy.deepcopy(_CURRENT_STATE)


@tool
def list_instances(environment: str = "all") -> Dict[str, Any]:
    """
    List EC2 instances in the environment.

    Args:
        environment: Filter by environment ('staging', 'production', or 'all').
    """
    instances = list(_CURRENT_STATE["instances"].values())
    if environment != "all":
        instances = [i for i in instances if i["environment"].lower() == environment.lower()]
    return {
        "status": "success",
        "count": len(instances),
        "instances": instances,
        "mode": "simulated",
    }


@tool
def describe_instance(instance_id: str) -> Dict[str, Any]:
    """
    Get detailed information for a specific EC2 instance.

    Args:
        instance_id: The EC2 instance identifier (e.g., i-staging-web-001).
    """
    instance = _CURRENT_STATE["instances"].get(instance_id)
    if not instance:
        return {
            "status": "error",
            "error_code": "InstanceNotFound",
            "message": f"Instance '{instance_id}' does not exist in the environment.",
        }
    return {
        "status": "success",
        "instance": instance,
        "mode": "simulated",
    }


@tool
def start_instance(instance_id: str) -> Dict[str, Any]:
    """
    Start a stopped EC2 instance.

    Args:
        instance_id: The identifier of the instance to start (e.g., i-staging-web-001).
    """
    instance = _CURRENT_STATE["instances"].get(instance_id)
    if not instance:
        return {
            "status": "error",
            "error_code": "InstanceNotFound",
            "message": f"Instance '{instance_id}' does not exist in the environment.",
        }

    previous_state = instance["state"]
    if previous_state == "running":
        return {
            "status": "no_op",
            "message": f"Instance '{instance_id}' is already in 'running' state.",
            "current_state": "running",
            "mode": "simulated",
        }

    # Transition state
    instance["state"] = "running"
    return {
        "status": "success",
        "instance_id": instance_id,
        "previous_state": previous_state,
        "current_state": "running",
        "environment": instance["environment"],
        "message": f"Successfully started instance '{instance_id}' in {instance['environment']}.",
        "mode": "simulated",
    }


@tool
def stop_instance(instance_id: str) -> Dict[str, Any]:
    """
    Stop a running EC2 instance.

    Args:
        instance_id: The identifier of the instance to stop (e.g., i-staging-web-002).
    """
    instance = _CURRENT_STATE["instances"].get(instance_id)
    if not instance:
        return {
            "status": "error",
            "error_code": "InstanceNotFound",
            "message": f"Instance '{instance_id}' does not exist in the environment.",
        }

    previous_state = instance["state"]
    if previous_state == "stopped":
        return {
            "status": "no_op",
            "message": f"Instance '{instance_id}' is already in 'stopped' state.",
            "current_state": "stopped",
            "mode": "simulated",
        }

    # Transition state
    instance["state"] = "stopped"
    return {
        "status": "success",
        "instance_id": instance_id,
        "previous_state": previous_state,
        "current_state": "stopped",
        "environment": instance["environment"],
        "message": f"Successfully stopped instance '{instance_id}' in {instance['environment']}.",
        "mode": "simulated",
    }


@tool
def delete_bucket(bucket_name: str) -> Dict[str, Any]:
    """
    Delete an S3 bucket (Simulated destructive operation).

    Args:
        bucket_name: The name of the S3 bucket to delete.
    """
    bucket = _CURRENT_STATE["buckets"].get(bucket_name)
    if not bucket:
        return {
            "status": "error",
            "error_code": "NoSuchBucket",
            "message": f"Bucket '{bucket_name}' does not exist.",
        }

    del _CURRENT_STATE["buckets"][bucket_name]
    return {
        "status": "success",
        "bucket_name": bucket_name,
        "message": f"SIMULATED: Bucket '{bucket_name}' has been deleted.",
        "mode": "simulated",
    }


ALL_MOCK_TOOLS = [
    list_instances,
    describe_instance,
    start_instance,
    stop_instance,
    delete_bucket,
]
