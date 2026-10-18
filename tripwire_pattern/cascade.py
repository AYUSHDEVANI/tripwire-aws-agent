"""
Tripwire Decision Cascade
Coordinates Strands Decider 2B, deterministic policy checks, and Bedrock LLM judge into a 4-lane routing cascade.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

from tripwire_pattern.schemas import (
    DecisionCategory,
    DeciderLabel,
    TripwireDecision,
)
from tripwire_pattern.decider_client import DeciderClient
from tripwire_pattern.policy import PolicyEngine
from tripwire_pattern.judge import BedrockJudge
from tripwire_pattern.authorization import PendingActionManager

logger = logging.getLogger("tripwire.cascade")


class DecisionCascade:
    """
    Main decision engine implementing the Tripwire 4-lane decision cascade:
      - ALLOW: High confidence (>= 0.85) + grounded + deterministic policies pass.
      - ASK: Moderate confidence (0.60 - 0.85) or requires confirmation.
      - ESCALATE: Low confidence (< 0.60) or unsure -> invokes Bedrock LLM Judge.
      - BLOCK: Ungrounded, injection, unauthorized, or hard policy failure.
    """

    def __init__(
        self,
        allow_threshold: Optional[float] = None,
        ask_threshold: Optional[float] = None,
        decider_client: Optional[DeciderClient] = None,
        policy_engine: Optional[PolicyEngine] = None,
        judge: Optional[BedrockJudge] = None,
        action_manager: Optional[PendingActionManager] = None,
    ):
        self.allow_threshold = float(allow_threshold or os.getenv("CASCADE_ALLOW_THRESHOLD", "0.85"))
        self.ask_threshold = float(ask_threshold or os.getenv("CASCADE_ASK_THRESHOLD", "0.60"))

        self.decider = decider_client or DeciderClient()
        self.policy = policy_engine or PolicyEngine()
        self.judge = judge or BedrockJudge()
        self.action_manager = action_manager or PendingActionManager()

    def evaluate_tool_call(
        self,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: str = "",
        caller_role: str = "operator",
        confirmation_token: Optional[str] = None,
    ) -> TripwireDecision:
        """
        Evaluate a proposed tool call through the complete decision cascade.
        """
        start_time = time.perf_counter()

        # Step 0: Check if a valid, unexpired confirmation token is provided (from previous ASK lane)
        if confirmation_token:
            is_valid = self.action_manager.verify_and_consume(
                token_id=confirmation_token,
                tool_name=tool_name,
                tool_args=tool_args,
            )
            if is_valid:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                return TripwireDecision(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    category=DecisionCategory.ALLOW,
                    confidence=1.0,
                    rationale="Action permitted via verified one-time human confirmation token.",
                    evidence=["Verified confirmation token", "Parameters matched original intent"],
                    policy_passed=True,
                    requires_confirmation=False,
                    escalated=False,
                    executed=False,  # Handler will mark True after tool execution
                    latency_ms=round(latency_ms, 2),
                )
            else:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                return TripwireDecision(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    category=DecisionCategory.BLOCK,
                    confidence=1.0,
                    rationale="Invalid, expired, or replayed confirmation token.",
                    evidence=["Token verification failed", "Replay defense triggered"],
                    policy_passed=False,
                    requires_confirmation=False,
                    escalated=False,
                    executed=False,
                    latency_ms=round(latency_ms, 2),
                )

        # Step 1: Deterministic Policy Check (Hard invariant)
        policy_res = self.policy.evaluate(
            tool_name=tool_name,
            tool_args=tool_args,
            user_message=user_message,
            caller_role=caller_role,
        )

        if not policy_res.passed:
            # Hard policy failure overrides any model score!
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return TripwireDecision(
                tool_name=tool_name,
                tool_args=tool_args,
                category=DecisionCategory.BLOCK,
                confidence=1.0,
                rationale=f"Hard policy violation: {'; '.join(policy_res.violations)}",
                evidence=policy_res.violations,
                policy_passed=False,
                requires_confirmation=False,
                escalated=False,
                executed=False,
                latency_ms=round(latency_ms, 2),
            )

        # Step 2: Strands Decider 2B Evaluation
        decider_res = self.decider.evaluate(
            user_message=user_message,
            tool_name=tool_name,
            tool_args=tool_args,
            context=context,
        )

        # Step 3: Cascade Routing
        # Case A: Decider says ungrounded -> Block Lane
        if decider_res.label == DeciderLabel.UNGROUNDED:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return TripwireDecision(
                tool_name=tool_name,
                tool_args=tool_args,
                category=DecisionCategory.BLOCK,
                confidence=decider_res.confidence,
                decider_label=decider_res.label,
                rationale="Strands Decider 2B classified tool call as ungrounded or adversarial.",
                evidence=[
                    f"Decider label: {decider_res.label.value}",
                    f"Confidence: {decider_res.confidence:.2f}",
                ],
                policy_passed=True,
                requires_confirmation=False,
                escalated=False,
                executed=False,
                latency_ms=round(latency_ms, 2),
            )

        # Case B: Grounded with high confidence (>= allow_threshold)
        if decider_res.label == DeciderLabel.GROUNDED and decider_res.confidence >= self.allow_threshold:
            if policy_res.requires_confirmation:
                # Sensitive action (e.g. production mutation) still needs confirmation
                pending = self.action_manager.create_pending_action(
                    user_message=user_message,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    question=f"Please confirm execution of '{tool_name}' on production instance.",
                )
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                return TripwireDecision(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    category=DecisionCategory.ASK,
                    confidence=decider_res.confidence,
                    decider_label=decider_res.label,
                    rationale="High confidence grounded action on sensitive resource requires operator confirmation.",
                    evidence=["Policy requires explicit confirmation for target resource"],
                    policy_passed=True,
                    requires_confirmation=True,
                    escalated=False,
                    executed=False,
                    clarification_prompt=pending.question,
                    pending_token=pending.token,
                    latency_ms=round(latency_ms, 2),
                )

            # Standard Allow Lane
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return TripwireDecision(
                tool_name=tool_name,
                tool_args=tool_args,
                category=DecisionCategory.ALLOW,
                confidence=decider_res.confidence,
                decider_label=decider_res.label,
                rationale="Tool arguments are grounded in user request with high confidence.",
                evidence=[
                    f"Decider label: {decider_res.label.value}",
                    f"Confidence: {decider_res.confidence:.2f} >= {self.allow_threshold}",
                    "Deterministic policies verified",
                ],
                policy_passed=True,
                requires_confirmation=False,
                escalated=False,
                executed=False,
                latency_ms=round(latency_ms, 2),
            )

        # Case C: Moderate confidence (ask_threshold <= confidence < allow_threshold)
        if self.ask_threshold <= decider_res.confidence < self.allow_threshold:
            clarification_q = self._generate_clarification_question(user_message, tool_name, tool_args)
            pending = self.action_manager.create_pending_action(
                user_message=user_message,
                tool_name=tool_name,
                tool_args=tool_args,
                question=clarification_q,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return TripwireDecision(
                tool_name=tool_name,
                tool_args=tool_args,
                category=DecisionCategory.ASK,
                confidence=decider_res.confidence,
                decider_label=decider_res.label,
                rationale="Moderate confidence or ambiguity detected. Asking user for clarification.",
                evidence=[
                    f"Confidence: {decider_res.confidence:.2f} in range [{self.ask_threshold}, {self.allow_threshold})",
                ],
                policy_passed=True,
                requires_confirmation=True,
                escalated=False,
                executed=False,
                clarification_prompt=clarification_q,
                pending_token=pending.token,
                latency_ms=round(latency_ms, 2),
            )

        # Case D: Low confidence (< ask_threshold) or Decider unsure -> Escalation Lane
        logger.info("Confidence %.2f below ask threshold. Escalating to Bedrock LLM Judge.", decider_res.confidence)
        judge_eval = self.judge.judge(
            user_message=user_message,
            tool_name=tool_name,
            tool_args=tool_args,
            context=context,
            decider_rationale=f"Decider label={decider_res.label.value}, conf={decider_res.confidence:.2f}",
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if judge_eval.recommended_category == DecisionCategory.ALLOW:
            return TripwireDecision(
                tool_name=tool_name,
                tool_args=tool_args,
                category=DecisionCategory.ALLOW,
                confidence=judge_eval.confidence,
                decider_label=decider_res.label,
                rationale=f"Escalation resolved by Bedrock LLM Judge: {judge_eval.rationale}",
                evidence=judge_eval.evidence + [f"Judge assessment: {judge_eval.risk_assessment}"],
                policy_passed=True,
                requires_confirmation=False,
                escalated=True,
                executed=False,
                latency_ms=round(latency_ms, 2),
            )
        elif judge_eval.recommended_category == DecisionCategory.ASK:
            pending = self.action_manager.create_pending_action(
                user_message=user_message,
                tool_name=tool_name,
                tool_args=tool_args,
                question=judge_eval.rationale,
            )
            return TripwireDecision(
                tool_name=tool_name,
                tool_args=tool_args,
                category=DecisionCategory.ASK,
                confidence=judge_eval.confidence,
                decider_label=decider_res.label,
                rationale=f"Bedrock Judge recommended user clarification: {judge_eval.rationale}",
                evidence=judge_eval.evidence,
                policy_passed=True,
                requires_confirmation=True,
                escalated=True,
                executed=False,
                clarification_prompt=judge_eval.rationale,
                pending_token=pending.token,
                latency_ms=round(latency_ms, 2),
            )
        else:
            # Judge says BLOCK or Judge failed closed
            return TripwireDecision(
                tool_name=tool_name,
                tool_args=tool_args,
                category=DecisionCategory.BLOCK,
                confidence=judge_eval.confidence,
                decider_label=decider_res.label,
                rationale=f"Bedrock Judge rejected tool call: {judge_eval.rationale}",
                evidence=judge_eval.evidence,
                policy_passed=True,
                requires_confirmation=False,
                escalated=True,
                executed=False,
                latency_ms=round(latency_ms, 2),
            )

    def _generate_clarification_question(
        self,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> str:
        """Construct a specific clarification question for the user."""
        instance_id = tool_args.get("instance_id")
        user_lower = user_message.lower()
        if "web" in user_lower and "staging" in user_lower:
            return "Multiple staging web servers exist (i-staging-web-001 [stopped], i-staging-web-002 [running]). Which instance should be used?"
        if instance_id:
            return f"You requested '{user_message}'. Did you mean to run '{tool_name}' on instance '{instance_id}'?"
        return f"Please clarify the specific target instance and parameters for '{tool_name}'."
