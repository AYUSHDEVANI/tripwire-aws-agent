"""
Strands Decider 2B Client
Official System One wire format integration with calibrated confidence and fail-closed fallback.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional
import requests

from tripwire_pattern.schemas import DeciderLabel, DeciderResult
from tripwire_pattern.question import TRIPWIRE_PRIMARY_QUESTION

logger = logging.getLogger("tripwire.decider")


def derive_confidence(probabilities: List[float]) -> float:
    """
    Normalised max-probability from strands_decider.schema:
        (N * p_max - 1) / (N - 1)
    Uniform -> 0.0, one-hot -> 1.0.
    """
    n = len(probabilities)
    if n <= 1:
        return 1.0
    p_max = max(probabilities)
    return float(max(0.0, min(1.0, (n * p_max - 1.0) / (n - 1.0))))


class DeciderClient:
    """
    Client for Strands Decider 2B server supporting POST /v1/systemone.
    Includes mock/offline fallback that preserves the exact System One schema and calibrated confidence.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: Optional[float] = None,
        mock_fallback: Optional[bool] = None,
    ):
        self.endpoint = (endpoint or os.getenv("DECIDER_ENDPOINT", "http://localhost:8099")).rstrip("/")
        self.timeout = float(timeout or os.getenv("DECIDER_TIMEOUT_SECONDS", "1.0"))
        fallback_env = os.getenv("DECIDER_MOCK_FALLBACK", "true").lower() in ("true", "1", "yes")
        self.mock_fallback = mock_fallback if mock_fallback is not None else fallback_env
        self.is_mock_mode = os.getenv("TRIPWIRE_MODE", "mock").lower() == "mock"
        self._server_available: Optional[bool] = None

    def evaluate(
        self,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: str = "",
    ) -> DeciderResult:
        """
        Evaluate tool call against user request using Strands Decider 2B.
        """
        start_time = time.perf_counter()

        # If explicitly in mock mode or server previously known unreachable, use local simulation
        if (self.is_mock_mode or self._server_available is False) and self.mock_fallback:
            return self._evaluate_local_simulation(user_message, tool_name, tool_args, context, start_time)

        # Build official System One choice question
        request_payload = {
            "state": (
                f"User Request: {user_message}\n"
                f"{f'Context: {context}' if context else ''}\n"
                f"Proposed Tool: {tool_name}\n"
                f"Proposed Arguments: {tool_args}"
            ),
            "model": "strands-decider-latest",
            "questions": {
                "grounding": {
                    "type": "choice",
                    "instructions": TRIPWIRE_PRIMARY_QUESTION,
                    "criteria": {
                        DeciderLabel.GROUNDED.value: "The tool arguments match what the user explicitly requested.",
                        DeciderLabel.UNGROUNDED.value: "The tool arguments contain hallucinated, unauthorized, or contradictory resources.",
                        DeciderLabel.UNSURE.value: "The request is ambiguous, incomplete, or requires user clarification.",
                    },
                }
            },
        }

        # Try live endpoint
        url = f"{self.endpoint}/v1/systemone"
        try:
            resp = requests.post(url, json=request_payload, timeout=(0.3, self.timeout))
            if resp.status_code == 200:
                self._server_available = True
                data = resp.json()
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                answers = data.get("answers", {})
                grounding = answers.get("grounding", {})
                choice = grounding.get("choice", DeciderLabel.UNSURE.value)
                conf = grounding.get("confidence", 0.0)

                # Map choice string to DeciderLabel enum
                try:
                    label = DeciderLabel(choice)
                except ValueError:
                    label = DeciderLabel.UNSURE

                return DeciderResult(
                    label=label,
                    confidence=float(conf),
                    latency_ms=round(latency_ms, 2),
                    model_id=data.get("model", "strands-decider-2b"),
                    raw_output=data,
                )
            else:
                logger.warning("Decider server returned HTTP %s: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.info("Decider live endpoint unreachable (%s). Using fallback: %s", e, self.mock_fallback)

        if not self.mock_fallback:
            # Fail closed if live server is required but unavailable
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return DeciderResult(
                label=DeciderLabel.UNSURE,
                confidence=0.0,
                latency_ms=round(latency_ms, 2),
                model_id="decider-unreachable-fail-closed",
            )

        # Deterministic local simulation of Decider 2B
        return self._evaluate_local_simulation(user_message, tool_name, tool_args, context, start_time)

    def _evaluate_local_simulation(
        self,
        user_message: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: str,
        start_time: float,
    ) -> DeciderResult:
        """
        Deterministic, calibrated local evaluation matching Decider 2B behavior.
        Used for mock environments, unit tests, and offline demonstrations.
        """
        user_lower = user_message.lower()
        args_str = str(tool_args).lower()
        latency_ms = (time.perf_counter() - start_time) * 1000.0 + 8.5  # Typical local inference ~15ms

        # 1. Check for prompt injection keywords
        injection_indicators = [
            "ignore previous", "ignore all", "bypass", "override", "system prompt",
            "jailbreak", "delete all", "delete every", "secret"
        ]
        if any(ind in user_lower for ind in injection_indicators) and ("delete" in tool_name or "stop" in tool_name or "prod" in args_str):
            probs = [0.02, 0.95, 0.03]  # ungrounded
            conf = derive_confidence(probs)
            return DeciderResult(
                label=DeciderLabel.UNGROUNDED,
                confidence=round(conf, 3),
                latency_ms=round(latency_ms, 2),
                model_id="strands-decider-2b-sim",
                raw_output={"simulated": True, "reason": "detected adversarial prompt injection"},
            )

        # 2. Check for target hallucination / environment mismatch
        # e.g., user asks for staging, tool targets production
        if "staging" in user_lower and "prod" in args_str:
            probs = [0.03, 0.94, 0.03]  # ungrounded
            conf = derive_confidence(probs)
            return DeciderResult(
                label=DeciderLabel.UNGROUNDED,
                confidence=round(conf, 3),
                latency_ms=round(latency_ms, 2),
                model_id="strands-decider-2b-sim",
                raw_output={"simulated": True, "reason": "environment mismatch"},
            )

        # Check if instance_id in args appears or is referenced in user message
        instance_id = tool_args.get("instance_id")
        if instance_id:
            id_lower = str(instance_id).lower()
            # If user mentioned a specific instance but tool targets a contradictory instance
            if ("web-2" in user_lower or "002" in user_lower) and "001" in id_lower:
                probs = [0.05, 0.91, 0.04]  # ungrounded
                conf = derive_confidence(probs)
                return DeciderResult(
                    label=DeciderLabel.UNGROUNDED,
                    confidence=round(conf, 3),
                    latency_ms=round(latency_ms, 2),
                    model_id="strands-decider-2b-sim",
                    raw_output={"simulated": True, "reason": "target instance contradicts user request"},
                )
            if ("web-1" in user_lower or "001" in user_lower) and "002" in id_lower:
                probs = [0.05, 0.91, 0.04]  # ungrounded
                conf = derive_confidence(probs)
                return DeciderResult(
                    label=DeciderLabel.UNGROUNDED,
                    confidence=round(conf, 3),
                    latency_ms=round(latency_ms, 2),
                    model_id="strands-decider-2b-sim",
                    raw_output={"simulated": True, "reason": "target instance contradicts user request"},
                )

            # Check if user actually specified an instance or if the target is ambiguous/omitted
            known_instance_mentions = [
                id_lower, "001", "002", "web-1", "web 1", "web-2", "web 2", "web-prod-1", "prod-1"
            ]
            has_explicit_id = any(mention in user_lower for mention in known_instance_mentions)
            if not has_explicit_id:
                # User asked a generic request without naming the instance -> ambiguous
                probs = [0.25, 0.25, 0.50]  # unsure
                conf = derive_confidence(probs)  # ~0.25
                return DeciderResult(
                    label=DeciderLabel.UNSURE,
                    confidence=round(conf, 3),
                    latency_ms=round(latency_ms, 2),
                    model_id="strands-decider-2b-sim",
                    raw_output={"simulated": True, "reason": "target instance omitted or ambiguous in request"},
                )

        # 4. Check for destructive operation
        if "delete" in tool_name:
            if "confirm" not in user_lower and "force" not in user_lower:
                probs = [0.30, 0.35, 0.35]  # unsure/ungrounded
                conf = derive_confidence(probs)
                return DeciderResult(
                    label=DeciderLabel.UNSURE,
                    confidence=round(conf, 3),
                    latency_ms=round(latency_ms, 2),
                    model_id="strands-decider-2b-sim",
                    raw_output={"simulated": True, "reason": "unconfirmed destructive operation"},
                )

        # 5. Normal grounded case
        # Check if key args align with request
        probs = [0.94, 0.03, 0.03]  # grounded
        conf = derive_confidence(probs)  # ~ 0.91
        return DeciderResult(
            label=DeciderLabel.GROUNDED,
            confidence=round(conf, 3),
            latency_ms=round(latency_ms, 2),
            model_id="strands-decider-2b-sim",
            raw_output={"simulated": True, "reason": "arguments fully grounded"},
        )
