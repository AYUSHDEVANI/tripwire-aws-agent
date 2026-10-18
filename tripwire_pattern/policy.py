"""
Tripwire Deterministic Policy Engine
Enforces environment boundaries, destructive operation controls, and input validation independently of AI models.
"""

import os
from typing import Any, Dict, List, Optional
from tripwire_pattern.schemas import PolicyResult

# Known mock resources for environment validation
KNOWN_MOCK_INSTANCES = {
    "i-staging-web-001": {"env": "staging", "state": "stopped", "name": "web-1"},
    "i-staging-web-002": {"env": "staging", "state": "running", "name": "web-2"},
    "i-production-web-001": {"env": "production", "state": "running", "name": "web-prod-1"},
}

# Operations classified as destructive
DESTRUCTIVE_TOOLS = {
    "delete_bucket",
    "terminate_instance",
    "delete_database",
    "purge_queue",
}

# Mutation tools
MUTATING_TOOLS = {
    "start_instance",
    "stop_instance",
    "reboot_instance",
    "modify_instance_attribute",
}

# Read-only tools
READ_ONLY_TOOLS = {
    "list_instances",
    "describe_instance",
    "get_instance_status",
}


class PolicyEngine:
    def __init__(
        self,
        allow_prod_mutations: Optional[bool] = None,
        strict_destructive: Optional[bool] = None,
        custom_tools: Optional[set[str]] = None,
    ):
        prod_env = os.getenv("TRIPWIRE_ALLOW_PROD_MUTATIONS", "false").lower() in ("true", "1", "yes")
        destr_env = os.getenv("CASCADE_STRICT_DESTRUCTIVE", "true").lower() in ("true", "1", "yes")
        self.allow_prod_mutations = allow_prod_mutations if allow_prod_mutations is not None else prod_env
        self.strict_destructive = strict_destructive if strict_destructive is not None else destr_env
        self.custom_tools = custom_tools or set()

    def evaluate(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_message: str,
        caller_role: str = "operator",
    ) -> PolicyResult:
        """
        Evaluate deterministic safety policies.
        Returns PolicyResult indicating whether policy passed and any violations.
        """
        violations: List[str] = []
        requires_confirmation = False
        is_destructive = tool_name in DESTRUCTIVE_TOOLS
        target_env = "staging"

        # 1. Unknown or malformed tool check
        all_supported_tools = DESTRUCTIVE_TOOLS | MUTATING_TOOLS | READ_ONLY_TOOLS | self.custom_tools
        if tool_name not in all_supported_tools:
            violations.append(f"Tool '{tool_name}' is not in the authorized AWS tool registry.")
            return PolicyResult(
                passed=False,
                violations=violations,
                caller_role=caller_role,
            )

        # 2. Destructive Operations Policy
        if is_destructive:
            if self.strict_destructive:
                violations.append(
                    f"Destructive operation '{tool_name}' is blocked by default safety policy. "
                    "Manual elevation and two-person authorization required."
                )
            else:
                requires_confirmation = True

        # 3. Environment Segregation & Target Inspection
        instance_id = tool_args.get("instance_id")
        if instance_id:
            instance_info = KNOWN_MOCK_INSTANCES.get(instance_id)
            if instance_info:
                target_env = instance_info["env"]
            elif "prod" in str(instance_id).lower():
                target_env = "production"
            elif "staging" in str(instance_id).lower():
                target_env = "staging"
            else:
                violations.append(f"Target instance identifier '{instance_id}' is ungrounded or unknown.")

            # Check if user requested staging but target is production
            user_lower = user_message.lower()
            if "staging" in user_lower and target_env == "production":
                violations.append(
                    f"Environment confusion: User specified 'staging' but tool call targets production resource '{instance_id}'."
                )

            # Check production mutation policy
            if target_env == "production" and tool_name in (MUTATING_TOOLS | DESTRUCTIVE_TOOLS):
                if not self.allow_prod_mutations and caller_role != "admin":
                    violations.append(
                        f"Mutations on production resources ({instance_id}) are prohibited for role '{caller_role}'."
                    )
                else:
                    requires_confirmation = True

        # 4. Caller RBAC Policy
        if caller_role == "viewer" and tool_name not in READ_ONLY_TOOLS:
            violations.append(f"Role 'viewer' is not authorized to execute mutating tool '{tool_name}'.")

        # 5. Argument Format & Malformed Inputs
        if tool_name in (MUTATING_TOOLS | {"describe_instance"}):
            if not instance_id or not isinstance(instance_id, str):
                violations.append(f"Tool '{tool_name}' requires a valid string 'instance_id' parameter.")

        passed = len(violations) == 0
        return PolicyResult(
            passed=passed,
            violations=violations,
            requires_confirmation=requires_confirmation,
            is_destructive=is_destructive,
            caller_role=caller_role,
            target_environment=target_env,
        )
