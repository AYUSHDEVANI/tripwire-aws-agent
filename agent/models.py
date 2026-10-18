"""
Agent State and Messaging Models
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from tripwire_pattern.schemas import TripwireDecision


class AgentRunRequest(BaseModel):
    user_message: str
    caller_role: str = "operator"
    confirmation_token: Optional[str] = None
    context: Optional[str] = None


class AgentRunResponse(BaseModel):
    user_message: str
    reply_text: str
    intercepted: bool = False
    decision: Optional[TripwireDecision] = None
    tool_executed: bool = False
    tool_result: Optional[Any] = None
    latency_ms: float = 0.0
