"""
Unit tests for structured audit logger and secret redaction.
"""

import os
import tempfile
import pytest
from tripwire_pattern.audit import AuditLogger, redact_sensitive_string, sanitize_payload


def test_redact_sensitive_string():
    raw = "Here is my AKIAIOSFODNN7EXAMPLE and secret aws_secret_access_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'"
    cleaned = redact_sensitive_string(raw)
    assert "AKIA" not in cleaned
    assert "[REDACTED_AWS_KEY]" in cleaned
    assert "[REDACTED_AWS_SECRET]" in cleaned

    bearer = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    assert "Bearer [REDACTED_TOKEN]" in redact_sensitive_string(bearer)


def test_sanitize_payload_dict():
    payload = {
        "instance_id": "i-staging-web-001",
        "api_key": "secret1234567890abcdef",
        "nested": {"password": "mypassword123", "safe_val": 42},
    }
    sanitized = sanitize_payload(payload)
    assert sanitized["instance_id"] == "i-staging-web-001"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["safe_val"] == 42


def test_audit_logger_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test_audit.jsonl")
        logger = AuditLogger(log_path=log_path)

        event = logger.log_event(
            decision_id="test-uuid-1234",
            user_message="Start instance with token=sec1234567890abc",
            tool_name="start_instance",
            tool_args={"instance_id": "i-staging-web-001"},
            lane="ALLOW",
            final_action="EXECUTED",
            decider_label="grounded",
            confidence=0.92,
            latency_ms=12.5,
        )

        assert event.final_action == "EXECUTED"
        assert os.path.exists(log_path)

        events = logger.read_all_events()
        assert len(events) == 1
        assert events[0]["decision_id"] == "test-uuid-1234"
        assert events[0]["lane"] == "ALLOW"
        assert "[REDACTED_TOKEN]" in events[0]["user_message"]
