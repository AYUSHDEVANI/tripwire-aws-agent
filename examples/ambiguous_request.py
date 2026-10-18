"""
Tripwire Example: Ambiguous Request Flow (ASK Lane)
Demonstrates an ambiguous request triggering clarification and single-use confirmation token resolution.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))

from agent.agent import TripwireAgent
from agent.models import AgentRunRequest
from agent.tools import reset_mock_environment, get_mock_environment

def main():
    print("=" * 60)
    print("Tripwire Scenario 2: Ambiguous Target Resource (ASK Lane)")
    print("=" * 60)

    reset_mock_environment()
    agent = TripwireAgent()

    # Step 1: User issues ambiguous prompt without instance ID
    ambiguous_prompt = "Start the web server"
    print(f"\nStep 1 User Request: '{ambiguous_prompt}'")

    req1 = AgentRunRequest(user_message=ambiguous_prompt, caller_role="operator")
    resp1 = agent.run(req1)

    print("\n--- Step 1 Interception Outcome ---")
    print(f"Decision Category:    {resp1.decision.category.value}")
    print(f"Clarification Prompt: {resp1.decision.clarification_prompt}")
    print(f"Pending Action Token: {resp1.decision.pending_token}")
    print(f"Protected Tool Ran:   {resp1.tool_executed} (ZERO EXECUTION ON ASK)")

    token = resp1.decision.pending_token

    # Step 2: User responds and provides confirmation token
    print("\n" + "-" * 50)
    print("Step 2: Operator confirms specific target instance with token")
    print("-" * 50)

    req2 = AgentRunRequest(
        user_message="Confirm: start i-staging-web-001",
        caller_role="operator",
        confirmation_token=token,
    )
    resp2 = agent.run(req2)

    print("\n--- Step 2 Interception Outcome ---")
    print(f"Decision Category:    {resp2.decision.category.value}")
    print(f"Rationale:            {resp2.decision.rationale}")
    print(f"Protected Tool Ran:   {resp2.tool_executed} (EXECUTED AFTER VALIDATION)")

    # Step 3: Replay attack defense
    print("\n" + "-" * 50)
    print("Step 3: Attacker attempts to replay the same confirmation token")
    print("-" * 50)

    req3 = AgentRunRequest(
        user_message="Confirm: start i-staging-web-001",
        caller_role="operator",
        confirmation_token=token,
    )
    resp3 = agent.run(req3)
    print(f"Replay Attempt Decision: {resp3.decision.category.value} ({resp3.decision.rationale})")

if __name__ == "__main__":
    main()
