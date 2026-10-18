"""
Tripwire Strands Intervention Handler
Hooks into Strands Agent tool lifecycle to enforce guardrail decisions at the execution boundary.
"""

import logging
from typing import Any, Dict, Optional

from strands.interventions.handler import InterventionHandler
from strands.interventions.actions import Proceed, Deny, Guide, Confirm
from strands.hooks.events import BeforeToolCallEvent

from tripwire_pattern.schemas import DecisionCategory, TripwireDecision
from tripwire_pattern.cascade import DecisionCascade
from tripwire_pattern.audit import AuditLogger

logger = logging.getLogger("tripwire.handler")


class TripwireInterventionHandler(InterventionHandler):
    """
    Strands InterventionHandler protecting AWS tool calls.
    Enforces the Tripwire Decision Cascade before any tool code executes.
    """

    def __init__(
        self,
        cascade: Optional[DecisionCascade] = None,
        audit_logger: Optional[AuditLogger] = None,
        caller_role: str = "operator",
    ):
        super().__init__()
        self.cascade = cascade or DecisionCascade()
        self.audit = audit_logger or AuditLogger()
        self.caller_role = caller_role
        self.last_decision: Optional[TripwireDecision] = None

    @property
    def name(self) -> str:
        return "TripwireInterventionHandler"

    def before_tool_call(
        self,
        event: BeforeToolCallEvent,
        **kwargs: Any,
    ) -> Proceed | Deny | Guide | Confirm:
        """
        Intercept tool call before execution.
        """
        tool_use = event.tool_use
        tool_name = tool_use.get("name", "unknown_tool")
        tool_args = tool_use.get("input", {})

        # Extract user message from invocation state or event context
        user_message = ""
        inv_state = getattr(event, "invocation_state", {}) or {}
        if isinstance(inv_state, dict):
            user_message = inv_state.get("user_message", "")
            if not user_message and "messages" in inv_state:
                # Get last user message from message history
                msgs = inv_state.get("messages", [])
                for m in reversed(msgs):
                    if isinstance(m, dict) and m.get("role") == "user":
                        user_message = m.get("content", "")
                        break
                    elif hasattr(m, "content"):
                        user_message = str(m.content)
                        break

        # Fallback if user_message not found in invocation state
        if not user_message:
            user_message = f"Execute tool {tool_name} with arguments {tool_args}"

        # Evaluate through Decision Cascade
        decision = self.cascade.evaluate_tool_call(
            user_message=user_message,
            tool_name=tool_name,
            tool_args=tool_args,
            caller_role=self.caller_role,
        )
        self.last_decision = decision

        # Route according to decision lane
        if decision.category == DecisionCategory.ALLOW:
            # Audit log allow (execution marked true when proceed completes)
            self.audit.log_event(
                decision_id=decision.decision_id,
                user_message=user_message,
                tool_name=tool_name,
                tool_args=tool_args,
                lane="ALLOW",
                final_action="EXECUTED",
                decider_label=decision.decider_label.value if decision.decider_label else None,
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                caller_role=self.caller_role,
                metadata={"rationale": decision.rationale, "evidence": decision.evidence},
            )
            decision.executed = True
            return Proceed(reason=decision.rationale)

        elif decision.category == DecisionCategory.ASK:
            self.audit.log_event(
                decision_id=decision.decision_id,
                user_message=user_message,
                tool_name=tool_name,
                tool_args=tool_args,
                lane="ASK",
                final_action="CLARIFICATION_REQUESTED",
                decider_label=decision.decider_label.value if decision.decider_label else None,
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                caller_role=self.caller_role,
                metadata={"prompt": decision.clarification_prompt, "pending_token": decision.pending_token},
            )
            prompt = decision.clarification_prompt or "Clarification required before executing tool."
            # Cancel tool execution for this turn and guide agent to clarify with user
            event.cancel_tool = prompt
            return Guide(feedback=prompt, reason=decision.rationale)

        elif decision.category == DecisionCategory.BLOCK:
            self.audit.log_event(
                decision_id=decision.decision_id,
                user_message=user_message,
                tool_name=tool_name,
                tool_args=tool_args,
                lane="BLOCK",
                final_action="BLOCKED",
                decider_label=decision.decider_label.value if decision.decider_label else None,
                confidence=decision.confidence,
                latency_ms=decision.latency_ms,
                caller_role=self.caller_role,
                metadata={"rationale": decision.rationale, "evidence": decision.evidence},
            )
            # Explicitly cancel tool execution
            event.cancel_tool = True
            return Deny(reason=decision.rationale)

        else:
            # Escalation that resolved to ask or block is handled above; default fail closed
            event.cancel_tool = True
            return Deny(reason="Safety cascade failed closed.")

    def evaluate_direct(
        self,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        confirmation_token: Optional[str] = None,
    ) -> TripwireDecision:
        """
        Direct programmatic evaluation helper (used by API, benchmark, and playground).
        """
        decision = self.cascade.evaluate_tool_call(
            user_message=user_message,
            tool_name=tool_name,
            tool_args=tool_args,
            caller_role=self.caller_role,
            confirmation_token=confirmation_token,
        )
        self.last_decision = decision
        return decision
