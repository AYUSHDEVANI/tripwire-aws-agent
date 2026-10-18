# Tripwire Reusable Decision Pattern

Tripwire is a drop-in, zero-trust safety pattern for AI agents built with the **Strands Agents SDK**. It intercepts proposed tool calls at the execution boundary and passes them through a calibrated decision cascade powered by **Strands Decider 2B** and **Amazon Bedrock**.

---

## Architecture Overview

```
Agent Proposed Tool Call
          ↓
Tripwire InterventionHandler (before_tool_call)
          ↓
[1] Deterministic Safety Policies (Environment, Target, RBAC)
          ↓
[2] Strands Decider 2B (Typed Grounding Question in ~15ms)
          ↓
[3] Confidence Cascade Routing
     ├── ALLOW (Conf >= 0.85 & Grounded & Policy Pass) → Proceed to execute tool
     ├── ASK   (0.60 <= Conf < 0.85 or Sensitive)      → Guide agent to clarify with user
     ├── ESCALATE (Conf < 0.60 or Unsure)              → Bedrock LLM Judge
     └── BLOCK (Ungrounded / Injection / Policy Fail)  → Deny tool execution
          ↓
[4] Redacted JSONL Audit Logging
```

---

## 3-Line Integration into Any Strands Agent

```python
from strands import Agent
from tripwire_pattern import TripwireInterventionHandler, DecisionCascade

# 1. Initialize the decision cascade
tripwire_handler = TripwireInterventionHandler(
    cascade=DecisionCascade(allow_threshold=0.85, ask_threshold=0.60),
    caller_role="operator"
)

# 2. Attach Tripwire to your Strands Agent
agent = Agent(
    model="anthropic.claude-3-haiku-20240307-v1:0",
    tools=[start_instance, stop_instance, list_instances],
    interventions=[tripwire_handler],
)

# 3. All tool calls are now protected before execution!
response = agent("Start i-staging-web-001 in staging")
```

---

## Typed Question & Wire Format

Tripwire uses the official Strands Decider System One choice schema (`POST /v1/systemone`):

- **Question**: `"Are all arguments of this tool call supported by the user's request?"`
- **Options**:
  - `grounded`: The tool arguments match what the user explicitly requested.
  - `ungrounded`: The tool arguments contain hallucinated, unauthorized, or contradictory resources.
  - `unsure`: The request is ambiguous, incomplete, or requires user clarification.

---

## Threshold Tuning Guide

| Parameter | Default | Guidance |
| :--- | :--- | :--- |
| `allow_threshold` | `0.85` | Lowering to `0.80` increases automation; raising to `0.90` increases safety for high-risk tools. |
| `ask_threshold` | `0.60` | Decisions between `ask_threshold` and `allow_threshold` prompt the user for clarification. |
| `strict_destructive`| `True` | Destructive operations (`delete_bucket`, etc.) always block by default. |

---

## Security Invariants

1. **Execution Boundary Enforcement**: Protected functions are never invoked if Decider or the Cascade denies, asks, or escalates.
2. **Deterministic Override**: Hard policy violations (e.g. attempting to operate on production when staging was requested) instantly reject regardless of model confidence.
3. **Fail-Closed**: If Decider or Bedrock times out or disconnects, the tool call is denied.
4. **Replay-Proof Confirmations**: User confirmation tokens are single-use, parameter-bound, and expire in 120 seconds.
