"""
Tripwire Authorization & Pending Action Manager
Manages caller roles, permission scopes, and replay-resistant pending action tokens for human confirmation.
"""

import time
import uuid
from typing import Any, Dict, Optional
from tripwire_pattern.schemas import PendingAction

# Default TTL for pending confirmation tokens in seconds (2 minutes)
DEFAULT_TOKEN_TTL_SECONDS = 120.0


class PendingActionManager:
    """
    Tracks pending operations requiring clarification or human confirmation.
    Provides strict replay prevention, parameter binding, and expiration checks.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TOKEN_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._pending_tokens: Dict[str, PendingAction] = {}

    def create_pending_action(
        self,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        question: str,
    ) -> PendingAction:
        """Create and store a pending action awaiting user confirmation."""
        token_id = str(uuid.uuid4())
        now = time.time()
        pending = PendingAction(
            token=token_id,
            user_message=user_message,
            tool_name=tool_name,
            tool_args=tool_args,
            question=question,
            created_at=now,
            expires_at=now + self.ttl_seconds,
            used=False,
        )
        self._pending_tokens[token_id] = pending
        return pending

    def verify_and_consume(
        self,
        token_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> bool:
        """
        Verify that a pending action token is valid, unexpired, matches the exact tool & arguments,
        and marks it consumed to prevent replay.
        """
        pending = self._pending_tokens.get(token_id)
        if not pending:
            return False

        now = time.time()
        # Check expiration
        if now > pending.expires_at:
            del self._pending_tokens[token_id]
            return False

        # Check single-use / replay
        if pending.used:
            return False

        # Check parameter binding: cannot approve a modified action with old token!
        if pending.tool_name != tool_name or pending.tool_args != tool_args:
            return False

        # Mark consumed
        pending.used = True
        return True

    def get_pending(self, token_id: str) -> Optional[PendingAction]:
        return self._pending_tokens.get(token_id)

    def clean_expired(self) -> None:
        """Remove expired tokens."""
        now = time.time()
        expired = [k for k, v in self._pending_tokens.items() if now > v.expires_at or v.used]
        for k in expired:
            del self._pending_tokens[k]
