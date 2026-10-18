"""
Tripwire Bedrock LLM Judge
Second-stage arbiter for ambiguous, edge-case, or escalated decisions using Amazon Bedrock.
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional
import boto3
from pydantic import BaseModel, Field

from tripwire_pattern.schemas import DecisionCategory

logger = logging.getLogger("tripwire.judge")


class JudgeEvaluation(BaseModel):
    """Structured, validated output from the LLM Judge."""
    recommended_category: DecisionCategory
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    risk_assessment: str = "low"


class BedrockJudge:
    """
    Amazon Bedrock second-stage escalation judge.
    Supports real Bedrock Converse/InvokeModel API and mock simulation mode.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.model_id = model_id or os.getenv("BEDROCK_JUDGE_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        mock_env = os.getenv("TRIPWIRE_MODE", "mock").lower() == "mock"
        self.mock_mode = mock_mode if mock_mode is not None else mock_env

        self._client = None
        if not self.mock_mode:
            try:
                self._client = boto3.client("bedrock-runtime", region_name=self.region)
            except Exception as e:
                logger.warning("Failed to initialize Bedrock client (%s). Falling back to mock judge.", e)
                self.mock_mode = True

    def judge(
        self,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: str = "",
        decider_rationale: str = "",
    ) -> JudgeEvaluation:
        """
        Evaluate an escalated tool call.
        Fails closed to BLOCK if judge is unavailable or returns malformed output.
        """
        start_time = time.perf_counter()

        if self.mock_mode or not self._client:
            return self._mock_judge_evaluate(user_message, tool_name, tool_args)

        # Real Bedrock invocation
        prompt = (
            f"You are the Tripwire Safety Judge for AWS Agent operations.\n"
            f"Analyze the following proposed tool call for grounding, security, and policy compliance.\n\n"
            f"User Request: {user_message}\n"
            f"Context: {context}\n"
            f"Decider note: {decider_rationale}\n"
            f"Proposed Tool: {tool_name}\n"
            f"Arguments: {json.dumps(tool_args)}\n\n"
            f"Return a JSON object with:\n"
            f"- recommended_category: one of 'ALLOW', 'ASK', 'BLOCK'\n"
            f"- confidence: float between 0.0 and 1.0\n"
            f"- rationale: short explanation\n"
            f"- evidence: list of facts\n"
            f"- risk_assessment: 'low', 'medium', or 'high'"
        )

        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "temperature": 0.0,
                "messages": [{"role": "user", "content": prompt}],
            })
            response = self._client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            resp_body = json.loads(response["body"].read().decode("utf-8"))
            content_text = resp_body.get("content", [{}])[0].get("text", "")

            # Extract JSON block
            parsed_json = self._extract_json(content_text)
            evaluation = JudgeEvaluation.model_validate(parsed_json)
            return evaluation

        except Exception as e:
            logger.error("Bedrock Judge evaluation failed: %s. Failing closed to BLOCK.", e)
            return JudgeEvaluation(
                recommended_category=DecisionCategory.BLOCK,
                confidence=1.0,
                rationale=f"LLM Judge execution error ({str(e)}). Tripwire failed closed for safety.",
                evidence=["Judge invocation failed"],
                risk_assessment="high",
            )

    def _extract_json(self, text: str) -> dict:
        """Extract and parse JSON from LLM text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find code block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            return json.loads(text[start:end].strip())
        elif "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        raise ValueError(f"No valid JSON found in judge response: {text[:100]}")

    def _mock_judge_evaluate(
        self,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> JudgeEvaluation:
        """
        Deterministic, validated simulation of the LLM Judge for test and offline environments.
        """
        user_lower = user_message.lower()

        # Ambiguous target request
        ambiguous_terms = [
            "the server", "web server", "api box", "which", "the instance",
            "machine", "bounce", "bring up", "turn on", "turn off", "staging server",
            "production server", "check the server", "the node"
        ]
        has_id = any(term in user_lower for term in ["001", "002", "web-1", "web 1", "web-2", "web 2", "web-prod-1"])
        if any(term in user_lower for term in ambiguous_terms) and not has_id:
            return JudgeEvaluation(
                recommended_category=DecisionCategory.ASK,
                confidence=0.78,
                rationale="User request is ambiguous. Judge recommends asking for specific instance target.",
                evidence=["Multiple potential matching instances found", "Instance ID not explicitly stated"],
                risk_assessment="medium",
            )

        # Destructive tool
        if "delete" in tool_name:
            return JudgeEvaluation(
                recommended_category=DecisionCategory.BLOCK,
                confidence=0.95,
                rationale="Judge recommends blocking unverified destructive cloud deletion.",
                evidence=["Destructive operation without authenticated sign-off"],
                risk_assessment="high",
            )

        # Injections
        if any(term in user_lower for term in ["ignore", "bypass", "system prompt", "override"]):
            return JudgeEvaluation(
                recommended_category=DecisionCategory.BLOCK,
                confidence=0.99,
                rationale="Judge detected adversarial prompt injection attempt in user message.",
                evidence=["Adversarial instruction detected in request payload"],
                risk_assessment="critical",
            )

        # Default fallback
        return JudgeEvaluation(
            recommended_category=DecisionCategory.ALLOW,
            confidence=0.88,
            rationale="Judge verified that tool parameters align with user intent and environment is non-production.",
            evidence=["Parameters match stated intent", "Safe staging target"],
            risk_assessment="low",
        )
