# Tripwire Technical Architecture

Tripwire provides a zero-trust execution boundary and decision cascade for AI agents interacting with cloud infrastructure.

---

## 1. Core End-to-End Logical Architecture

```mermaid
flowchart TD
    User([User Request / Instruction]) --> Agent[Strands Main Agent on Amazon Bedrock]
    Agent --> Propose[Propose Tool Call & Arguments]
    
    subgraph TripwireExecutionBoundary [Tripwire Execution Boundary]
        Handler[Tripwire InterventionHandler<br/>before_tool_call]
        Policy[Deterministic Policy Engine<br/>Environment & Destructive Guards]
        Decider[Strands Decider 2B<br/>Typed Question / POST /v1/systemone]
        Router{Confidence & Safety<br/>Cascade Router}
        
        Propose --> Handler
        Handler --> Policy
        Policy -->|Policies Pass| Decider
        Policy -->|Hard Violation| BlockLane
        Decider --> Router
        
        Router -->|Conf >= 0.85 & Grounded| AllowLane[ALLOW Lane]
        Router -->|0.60 <= Conf < 0.85| AskLane[ASK Lane]
        Router -->|Conf < 0.60 or Unsure| EscalateLane[ESCALATE Lane]
        Router -->|Ungrounded / Injected| BlockLane[BLOCK Lane]
        
        EscalateLane --> Judge[Amazon Bedrock LLM Judge<br/>Claude 3 Haiku Arbiter]
        Judge -->|Valid & Safe| AllowLane
        Judge -->|Ambiguous| AskLane
        Judge -->|Risky or Error| BlockLane
    end
    
    AllowLane --> Execute[Execute Protected Tool Function]
    AskLane --> Clarify[Generate Pending Token & Prompt Clarification]
    BlockLane --> Reject[Deny Tool Execution & Fail Closed]
    
    Execute --> Audit[Structured JSONL Audit Event<br/>Secrets Redacted & Latencies Recorded]
    Clarify --> Audit
    Reject --> Audit
    
    Audit --> Dashboard[Streamlit SecOps Dashboard]
    Audit --> Telemetry([SIEM / CloudWatch Telemetry])
```

---

## 2. Decision Cascade State Machine

```mermaid
stateDiagram-v2
    [*] --> Intercepted : Agent triggers before_tool_call
    
    state Intercepted {
        [*] --> PolicyCheck
        PolicyCheck --> DeciderEval : Deterministic Policies Pass
        PolicyCheck --> Denied : Hard Policy Violation (Destructive, Env Confusion)
        
        DeciderEval --> HighConfidenceGrounded : Confidence >= 0.85 & Grounded
        DeciderEval --> ModerateConfidence : 0.60 <= Confidence < 0.85
        DeciderEval --> LowConfidenceOrUnsure : Confidence < 0.60 or Unsure
        DeciderEval --> UngroundedOrInjected : Decider Label = ungrounded
        
        LowConfidenceOrUnsure --> BedrockJudge : Escalate to Bedrock
        BedrockJudge --> HighConfidenceGrounded : Judge ALLOW
        BedrockJudge --> ModerateConfidence : Judge ASK
        BedrockJudge --> Denied : Judge BLOCK or Timeout
    }
    
    HighConfidenceGrounded --> Allowed : Proceed
    ModerateConfidence --> Asked : Guide with Clarification Token
    UngroundedOrInjected --> Denied : Deny Tool Execution
    
    Allowed --> Execution : Protected Cloud Function Runs
    Asked --> Suspended : Wait for User Confirmation Token
    Denied --> Aborted : Zero Tool Execution (Fail Closed)
    
    Execution --> [*] : Audit Logged
    Suspended --> [*] : Audit Logged
    Aborted --> [*] : Audit Logged
```

---

## 3. Component Breakdown

| Component | Responsibility | Performance |
| :--- | :--- | :--- |
| **Strands Agent** | Natural language reasoning, planning, and proposing AWS operations using Amazon Bedrock. | Model-dependent (~1-2s) |
| **InterventionHandler** | Strands SDK hook (`before_tool_call`) that enforces guardrails at the tool invocation boundary before any protected code executes. | < 0.5 ms |
| **PolicyEngine** | Deterministic security invariant enforcement: environment segregation (staging vs production), RBAC scopes, and destructive operation blocks. | < 0.2 ms |
| **DeciderClient** | Communicates with Strands Decider 2B (`POST /v1/systemone`) answering the typed question: *"Are all arguments of this tool call supported by the user's request?"* | ~12 - 15 ms |
| **DecisionCascade** | 4-lane decision router using calibrated confidence thresholds (Allow: >=0.85, Ask: 0.60-0.85, Escalate: <0.60, Block: ungrounded). | < 0.1 ms |
| **BedrockJudge** | Secondary LLM arbiter invoked exclusively for ambiguous edge cases or low-confidence decisions. | ~120 - 150 ms |
| **AuditLogger** | Thread-safe, JSONL structured audit trail with automated secret and credential redaction. | < 0.5 ms |
| **SecOps Dashboard** | Dark-mode Streamlit operations dashboard featuring real-time telemetry, interactive playground, and benchmark results. | Interactive UI |

---

## 4. Reusable Decision Pattern (`tripwire_pattern/`)

The core decision engine is completely decoupled from the agent implementation and dashboard. Any Strands agent can adopt Tripwire in three lines of code:

```python
from strands import Agent
from tripwire_pattern import TripwireInterventionHandler, DecisionCascade

handler = TripwireInterventionHandler(
    cascade=DecisionCascade(allow_threshold=0.85, ask_threshold=0.60)
)
agent = Agent(tools=[start_instance, stop_instance], interventions=[handler])
```
