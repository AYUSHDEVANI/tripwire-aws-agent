"""
Unit tests for 4-lane decision cascade and confidence thresholds.
"""

import pytest
from tripwire_pattern.cascade import DecisionCascade
from tripwire_pattern.schemas import DecisionCategory, DeciderLabel


def test_cascade_allow_lane():
    cascade = DecisionCascade(allow_threshold=0.85, ask_threshold=0.60)
    decision = cascade.evaluate_tool_call(
        user_message="Start i-staging-web-001 in staging",
        tool_name="start_instance",
        tool_args={"instance_id": "i-staging-web-001"},
    )
    assert decision.category == DecisionCategory.ALLOW
    assert decision.confidence >= 0.85
    assert decision.policy_passed is True


def test_cascade_ask_lane_ambiguous():
    cascade = DecisionCascade(allow_threshold=0.85, ask_threshold=0.60)
    decision = cascade.evaluate_tool_call(
        user_message="Start the web server",
        tool_name="start_instance",
        tool_args={"instance_id": "i-staging-web-001"},
    )
    # Ambiguous target routes to ASK (or Escalation that resolves to ASK)
    assert decision.category == DecisionCategory.ASK
    assert decision.requires_confirmation is True
    assert decision.pending_token is not None


def test_cascade_block_lane_destructive():
    cascade = DecisionCascade()
    decision = cascade.evaluate_tool_call(
        user_message="Delete bucket company-staging-artifacts",
        tool_name="delete_bucket",
        tool_args={"bucket_name": "company-staging-artifacts"},
    )
    assert decision.category == DecisionCategory.BLOCK
    assert decision.policy_passed is False


def test_cascade_block_lane_hallucination():
    cascade = DecisionCascade()
    decision = cascade.evaluate_tool_call(
        user_message="Please restart web-2 in staging",
        tool_name="start_instance",
        tool_args={"instance_id": "i-production-web-001"},
    )
    # Tool targets production when user asked for staging -> BLOCK
    assert decision.category == DecisionCategory.BLOCK


def test_cascade_one_time_confirmation_token():
    cascade = DecisionCascade()
    # 1. Trigger ASK lane to get a pending token
    ask_decision = cascade.evaluate_tool_call(
        user_message="Start the web server",
        tool_name="start_instance",
        tool_args={"instance_id": "i-staging-web-001"},
    )
    assert ask_decision.category == DecisionCategory.ASK
    token = ask_decision.pending_token
    assert token is not None

    # 2. Resubmit with the valid confirmation token -> ALLOW!
    confirmed_decision = cascade.evaluate_tool_call(
        user_message="Confirm start i-staging-web-001",
        tool_name="start_instance",
        tool_args={"instance_id": "i-staging-web-001"},
        confirmation_token=token,
    )
    assert confirmed_decision.category == DecisionCategory.ALLOW

    # 3. Replay attack: try using the exact same token again -> BLOCK!
    replay_decision = cascade.evaluate_tool_call(
        user_message="Confirm start i-staging-web-001",
        tool_name="start_instance",
        tool_args={"instance_id": "i-staging-web-001"},
        confirmation_token=token,
    )
    assert replay_decision.category == DecisionCategory.BLOCK
    assert "Invalid, expired, or replayed" in replay_decision.rationale
