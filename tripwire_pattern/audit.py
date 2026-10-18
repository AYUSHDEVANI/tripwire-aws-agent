"""
Tripwire Audit Logger
Provides structured JSONL audit trail with automated secret redaction.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from tripwire_pattern.schemas import AuditEvent

# Sensitive patterns to redact
REDACTION_PATTERNS = [
    (re.compile(r"(?i)\b(akia[0-9a-z]{16})\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)\b(asia[0-9a-z]{16})\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)(aws_secret_access_key\s*[:=]\s*['\"]?)([0-9a-zA-Z/+]{40})(['\"]?)"), r"\1[REDACTED_AWS_SECRET]\3"),
    (re.compile(r"(?i)(bearer\s+[a-zA-Z0-9_\-\.]{20,})"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)(password\s*[:=]\s*['\"]?)([^'\";\s]+)(['\"]?)"), r"\1[REDACTED_PASSWORD]\3"),
    (re.compile(r"(?i)(token\s*[:=]\s*['\"]?)([a-zA-Z0-9_\-\.]{16,})(['\"]?)"), r"\1[REDACTED_TOKEN]\3"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"]?)([a-zA-Z0-9_\-]{16,})(['\"]?)"), r"\1[REDACTED_API_KEY]\3"),
]


def redact_sensitive_string(text: str) -> str:
    """Scrub sensitive credentials, tokens, and keys from string."""
    if not isinstance(text, str):
        return text
    scrubbed = text
    for pattern, replacement in REDACTION_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


def sanitize_payload(obj: Any) -> Any:
    """Recursively sanitize dicts, lists, and primitives."""
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            if any(term in k.lower() for term in ["secret", "password", "token", "key", "authorization"]):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_payload(v)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    elif isinstance(obj, str):
        return redact_sensitive_string(obj)
    return obj


class AuditLogger:
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path or os.getenv("TRIPWIRE_AUDIT_PATH", "./data/audit.jsonl")
        # Ensure target directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)

    def log_event(
        self,
        decision_id: str,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        lane: str,
        final_action: str,
        decider_label: Optional[str] = None,
        confidence: Optional[float] = None,
        execution_result: Optional[Any] = None,
        latency_ms: float = 0.0,
        caller_role: str = "operator",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Create and persist a sanitized audit event."""
        sanitized_args = sanitize_payload(tool_args)
        sanitized_msg = redact_sensitive_string(user_message)
        sanitized_res = sanitize_payload(execution_result) if execution_result is not None else None

        event = AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision_id=decision_id,
            user_message=sanitized_msg,
            tool_name=tool_name,
            tool_args=sanitized_args,
            decider_label=decider_label,
            confidence=confidence,
            lane=lane,
            final_action=final_action,
            execution_result=sanitized_res,
            latency_ms=round(latency_ms, 2),
            caller_role=caller_role,
            metadata=metadata or {},
        )

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

        return event

    def read_all_events(self) -> List[Dict[str, Any]]:
        """Read all audit events from the JSONL log."""
        if not os.path.exists(self.log_path):
            return []
        events = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events

    def clear(self) -> None:
        """Clear audit log (for tests)."""
        if os.path.exists(self.log_path):
            os.remove(self.log_path)
