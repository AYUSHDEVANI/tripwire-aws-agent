"""
Tripwire Configuration Settings
Uses Pydantic Settings to validate environment configuration.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class TripwireSettings(BaseSettings):
    # Operating Mode
    tripwire_mode: str = "mock"  # "mock" or "live"

    # AWS & Bedrock
    aws_region: str = "us-east-1"
    aws_profile: Optional[str] = None
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_judge_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"

    # Strands Decider 2B
    decider_endpoint: str = "http://localhost:8099"
    decider_timeout_seconds: float = 2.0
    decider_mock_fallback: bool = True

    # Decision Cascade
    cascade_allow_threshold: float = 0.85
    cascade_ask_threshold: float = 0.60
    cascade_strict_destructive: bool = True

    # Security & RBAC
    tripwire_caller_role: str = "operator"
    tripwire_allow_prod_mutations: bool = False

    # Audit & Observability
    tripwire_audit_path: str = "./data/audit.jsonl"
    tripwire_log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> TripwireSettings:
    """Load and validate settings."""
    return TripwireSettings()
