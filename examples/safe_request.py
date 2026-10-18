"""
Tripwire Example: Safe Grounded Request
Demonstrates an authorized, fully grounded request flowing through the ALLOW lane and executing.
"""

import os
import sys

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath("."))

from agent.agent import TripwireAgent
from agent.models import AgentRunRequest
from agent.tools import reset_mock_environment, get_mock_environment

def main():
    print("=" * 60)
    print("Tripwire Scenario 1: Safe Grounded AWS Operation")
    print("=" * 60)

    reset_mock_environment()
    agent = TripwireAgent()

    user_prompt = "Start i-staging-web-001 in staging"
    print(f"\nUser Request: '{user_prompt}'")

    request = AgentRunRequest(user_message=user_prompt, caller_role="operator")
    response = agent.run(request)

    print("\n--- Tripwire Interception Outcome ---")
    print(f"Decision Category:    {response.decision.category.value}")
    print(f"Decider Confidence:   {response.decision.confidence}")
    print(f"Rationale:            {response.decision.rationale}")
    print(f"Evidence:             {response.decision.evidence}")
    print(f"Protected Tool Ran:   {response.tool_executed}")
    print(f"Total Latency:        {response.latency_ms} ms")

    # Verify cloud state
    env_state = get_mock_environment()
    inst = env_state["instances"]["i-staging-web-001"]
    print(f"\nTarget Instance State in AWS: {inst['state']} (Successfully transitioned to 'running')")

if __name__ == "__main__":
    main()
