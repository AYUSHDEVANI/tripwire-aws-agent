"""
Tripwire Strands Agent Runner
Connects the Strands Agent lifecycle with the Tripwire intervention handler.
Supports both Amazon Bedrock live mode and zero-cost mock execution mode.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

from strands import Agent
from agent.tools import (
    ALL_MOCK_TOOLS,
    start_instance,
    stop_instance,
    describe_instance,
    list_instances,
    delete_bucket,
    _CURRENT_STATE,
)
from agent.configuration import get_settings
from agent.models import AgentRunRequest, AgentRunResponse
from tripwire_pattern import (
    TripwireInterventionHandler,
    DecisionCascade,
    DecisionCategory,
    AuditLogger,
)

logger = logging.getLogger("tripwire.agent")


class TripwireAgent:
    """
    Main agent controller integrating Strands Agent and the Tripwire safety cascade.
    """

    def __init__(
        self,
        handler: Optional[TripwireInterventionHandler] = None,
        settings: Optional[Any] = None,
    ):
        self.settings = settings or get_settings()
        self.audit = AuditLogger(log_path=self.settings.tripwire_audit_path)
        self.cascade = DecisionCascade(
            allow_threshold=self.settings.cascade_allow_threshold,
            ask_threshold=self.settings.cascade_ask_threshold,
        )
        self.handler = handler or TripwireInterventionHandler(
            cascade=self.cascade,
            audit_logger=self.audit,
            caller_role=self.settings.tripwire_caller_role,
        )

        self._strands_agent = None
        if self.settings.tripwire_mode == "live":
            try:
                self._strands_agent = Agent(
                    model=self.settings.bedrock_model_id,
                    tools=ALL_MOCK_TOOLS,
                    interventions=[self.handler],
                    system_prompt=(
                        "You are an AWS Operations Assistant managing EC2 instances and S3 buckets. "
                        "When asked to manage an instance, propose the appropriate tool call. "
                        "Do not invent instance IDs not mentioned by the user."
                    ),
                )
            except Exception as e:
                logger.warning("Failed to initialize live Strands Agent (%s). Operating in mock mode.", e)
                self._strands_agent = None

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        """
        Execute user request through the agent and Tripwire guardrail.
        """
        start_time = time.perf_counter()
        user_msg = request.user_message.strip()

        # If live agent is active, run through Strands Agent
        if self._strands_agent and self.settings.tripwire_mode == "live":
            try:
                result = self._strands_agent(user_msg)
                total_latency = (time.perf_counter() - start_time) * 1000.0
                decision = self.handler.last_decision
                return AgentRunResponse(
                    user_message=user_msg,
                    reply_text=str(result),
                    intercepted=decision is not None,
                    decision=decision,
                    tool_executed=decision.executed if decision else False,
                    latency_ms=round(total_latency, 2),
                )
            except Exception as e:
                logger.error("Live agent run error: %s. Falling back to deterministic pipeline.", e)

        # Deterministic simulation of agent tool proposal & intervention
        return self._simulate_agent_turn(request, start_time)

    def _simulate_agent_turn(self, request: AgentRunRequest, start_time: float) -> AgentRunResponse:
        """
        Simulates the Strands agent tool proposal step, then rigorously enforces the Tripwire intervention.
        """
        user_msg = request.user_message
        user_lower = user_msg.lower()

        # 1. Determine which tool the agent would propose based on request
        tool_name, tool_args = self._propose_tool_call(user_msg)

        if not tool_name:
            # General query not invoking tools (e.g. conversational)
            total_latency = (time.perf_counter() - start_time) * 1000.0
            return AgentRunResponse(
                user_message=user_msg,
                reply_text="I am your AWS Operations Agent. You can ask me to list, describe, start, or stop EC2 instances.",
                intercepted=False,
                latency_ms=round(total_latency, 2),
            )

        # 2. INTERCEPT: Invoke Tripwire Decision Cascade before tool execution!
        decision = self.cascade.evaluate_tool_call(
            user_message=user_msg,
            tool_name=tool_name,
            tool_args=tool_args,
            caller_role=request.caller_role,
            confirmation_token=request.confirmation_token,
        )

        tool_executed = False
        tool_result = None
        reply_text = ""

        # 3. Route based on Decision Category
        if decision.category == DecisionCategory.ALLOW:
            # Critical Invariant: Tool executes ONLY when ALLOWED!
            tool_func = {
                "start_instance": start_instance,
                "stop_instance": stop_instance,
                "describe_instance": describe_instance,
                "list_instances": list_instances,
                "delete_bucket": delete_bucket,
            }.get(tool_name)

            if tool_func:
                tool_result = tool_func(**tool_args)
                tool_executed = True
                decision.executed = True
                reply_text = f"Action Approved ({decision.rationale}). Output: {tool_result.get('message', 'Success')}"

            # Log audit event
            self.audit.log_event(
                decision_id=decision.decision_id,
                user_message=user_msg,
                tool_name=tool_name,
                tool_args=tool_args,
                lane="ALLOW",
                final_action="EXECUTED",
                decider_label=decision.decider_label.value if decision.decider_label else None,
                confidence=decision.confidence,
                execution_result=tool_result,
                latency_ms=decision.latency_ms,
                caller_role=request.caller_role,
                metadata={"rationale": decision.rationale, "evidence": decision.evidence},
            )

        elif decision.category == DecisionCategory.ASK:
            # Never execute tool on ASK!
            tool_executed = False
            reply_text = f"Clarification Needed: {decision.clarification_prompt}"
            self.audit.log_event(
                decision_id=decision.decision_id,
                user_message=user_msg,
                tool_name=tool_name,
                tool_args=tool_args,
                lane="ASK",
                final_action="CLARIFICATION_REQUESTED",
                decider_label=decision.decider_label.value if decision.decider_label else None,
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                caller_role=request.caller_role,
                metadata={"prompt": decision.clarification_prompt, "pending_token": decision.pending_token},
            )

        elif decision.category == DecisionCategory.BLOCK:
            # Never execute tool on BLOCK!
            tool_executed = False
            reply_text = f"Action Blocked by Tripwire Guardrail: {decision.rationale}"
            self.audit.log_event(
                decision_id=decision.decision_id,
                user_message=user_msg,
                tool_name=tool_name,
                tool_args=tool_args,
                lane="BLOCK",
                final_action="BLOCKED",
                decider_label=decision.decider_label.value if decision.decider_label else None,
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                caller_role=request.caller_role,
                metadata={"rationale": decision.rationale, "evidence": decision.evidence},
            )

        total_latency = (time.perf_counter() - start_time) * 1000.0
        return AgentRunResponse(
            user_message=user_msg,
            reply_text=reply_text,
            intercepted=True,
            decision=decision,
            tool_executed=tool_executed,
            tool_result=tool_result,
            latency_ms=round(total_latency, 2),
        )

    def _propose_tool_call(self, user_msg: str) -> tuple[Optional[str], Dict[str, Any]]:
        """
        Parses intent to determine the proposed tool call and arguments.
        Faithfully models agent behaviors including hallucinations when prompted ambiguously.
        """
        user_lower = user_msg.lower()

        # Terminate instance
        if "terminate" in user_lower or "kill" in user_lower:
            for inst_id in ["i-staging-web-001", "i-staging-web-002", "i-production-web-001"]:
                if inst_id in user_lower:
                    return "terminate_instance", {"instance_id": inst_id}
            return "terminate_instance", {"instance_id": "i-production-web-001" if "prod" in user_lower else "i-staging-web-001"}

        # Database operations
        if "database" in user_lower or " db " in user_lower or "db." in user_lower:
            tool = "delete_database" if "delete" in user_lower else "stop_database"
            return tool, {"database_id": "production-db" if "prod" in user_lower else "staging-db"}

        # Delete bucket or resources
        if "delete" in user_lower and ("bucket" in user_lower or "all" in user_lower or "every" in user_lower):
            bucket_name = "company-production-backups" if "prod" in user_lower else "company-staging-artifacts"
            return "delete_bucket", {"bucket_name": bucket_name}

        # Start instance
        if "start" in user_lower:
            # Check if specific ID is mentioned
            for inst_id in ["i-staging-web-001", "i-staging-web-002", "i-production-web-001"]:
                if inst_id in user_lower:
                    return "start_instance", {"instance_id": inst_id}

            # Hallucination / environment substitution scenario:
            if "production" in user_lower and "staging" in user_lower:
                return "start_instance", {"instance_id": "i-production-web-001"}

            # If user asks for "web-2 in staging"
            if "web-2" in user_lower or "web 2" in user_lower:
                return "start_instance", {"instance_id": "i-staging-web-002"}

            # If user asks for "web-1 in staging" or "web server in staging"
            if "staging" in user_lower and ("web-1" in user_lower or "web 1" in user_lower):
                return "start_instance", {"instance_id": "i-staging-web-001"}

            # Ambiguous scenario: "Start the web server" or "Start the server"
            if "web server" in user_lower or "the server" in user_lower or "the instance" in user_lower:
                return "start_instance", {"instance_id": "i-staging-web-001"}

            # Prompt injection scenario
            if "production" in user_lower:
                return "start_instance", {"instance_id": "i-production-web-001"}

            return "start_instance", {"instance_id": "i-staging-web-001"}

        # Stop instance
        if "stop" in user_lower:
            for inst_id in ["i-staging-web-001", "i-staging-web-002", "i-production-web-001"]:
                if inst_id in user_lower:
                    return "stop_instance", {"instance_id": inst_id}
            if "prod" in user_lower:
                return "stop_instance", {"instance_id": "i-production-web-001"}
            return "stop_instance", {"instance_id": "i-staging-web-002"}

        # List instances
        if "list" in user_lower or "show" in user_lower:
            env = "staging" if "staging" in user_lower else ("production" if "prod" in user_lower else "all")
            return "list_instances", {"environment": env}

        # Describe instance
        if "describe" in user_lower or "details" in user_lower:
            for inst_id in ["i-staging-web-001", "i-staging-web-002", "i-production-web-001"]:
                if inst_id in user_lower:
                    return "describe_instance", {"instance_id": inst_id}
            return "describe_instance", {"instance_id": "i-staging-web-001"}

        # Generic adversarial attempts
        if any(w in user_lower for w in ["override", "ignore", "bypass", "jailbreak", "developer mode"]):
            return "delete_bucket", {"bucket_name": "company-production-backups"}

        return None, {}
