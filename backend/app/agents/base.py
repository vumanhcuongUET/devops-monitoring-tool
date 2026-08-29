"""
Base Agent Class

Abstract base class for all specialized AI agents.
Defines the interface and common functionality.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)


class AgentResponse:
    """Standardized agent response structure."""

    def __init__(
        self,
        agent_name: str,
        insights: dict[str, Any],
        confidence: float = 0.8,
        recommendations: list | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.agent_name = agent_name
        self.insights = insights
        self.confidence = confidence  # 0.0 to 1.0
        self.recommendations = recommendations or []
        self.error = error
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert response to dictionary."""
        return {
            "agent": self.agent_name,
            "insights": self.insights,
            "confidence": self.confidence,
            "recommendations": self.recommendations,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    def is_successful(self) -> bool:
        """Check if agent analysis was successful."""
        return self.error is None


class BaseAgent(ABC):
    """
    Abstract base class for specialized AI agents.

    All agents must inherit from this class and implement:
    - get_prompt_template(): Return the system prompt
    - analyze(): Analyze context and return AgentResponse
    """

    def __init__(
        self,
        name: str,
        model: str = "claude-sonnet-4-20250514",
        timeout: int = 30,
    ):
        self.name = name
        self.model = model
        self.timeout = timeout
        self.client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._prompt_cache: str | None = None

    @abstractmethod
    def get_prompt_template(self) -> str:
        """
        Return the system prompt for this agent.

        This defines the agent's expertise, behavior, and output format.
        Should be a clear, specific prompt that guides the model's behavior.
        """

    @abstractmethod
    async def analyze(self, context: dict[str, Any]) -> AgentResponse:
        """
        Analyze context and return insights.

        Args:
            context: Dictionary containing relevant data for analysis
                    (logs, metrics, k8s state, etc.)

        Returns:
            AgentResponse with insights, confidence, and recommendations
        """

    async def _query_claude(
        self,
        user_message: str,
        max_tokens: int = 1024,
    ) -> str:
        """
        Query Claude API with the agent's system prompt.

        Args:
            user_message: The user query or data to analyze
            max_tokens: Maximum tokens in response

        Returns:
            Claude's response as text
        """
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=self.get_prompt_template(),
                messages=[
                    {
                        "role": "user",
                        "content": user_message,
                    }
                ],
                timeout=self.timeout,
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Error querying Claude for agent {self.name}: {e}")
            raise

    def _validate_context(self, context: dict[str, Any], required_keys: list) -> bool:
        """
        Validate that context contains required keys.

        Args:
            context: The context dictionary
            required_keys: List of required key names

        Returns:
            True if all required keys are present
        """
        missing_keys = [key for key in required_keys if key not in context]
        if missing_keys:
            logger.warning(
                f"Agent {self.name} missing required context keys: {missing_keys}"
            )
            return False
        return True

    def _calculate_confidence(
        self,
        data_quality: float = 1.0,
        data_volume: int = 100,
        model_uncertainty: float = 0.0,
    ) -> float:
        """
        Calculate confidence score for the analysis.

        Args:
            data_quality: Quality of input data (0.0 to 1.0)
            data_volume: Amount of data (higher = more confidence)
            model_uncertainty: Uncertainty in model response (0.0 to 1.0)

        Returns:
            Confidence score (0.0 to 1.0)
        """
        # Base confidence from data quality
        confidence = data_quality

        # Increase with data volume (diminishing returns)
        volume_factor = min(data_volume / 1000, 0.2)
        confidence += volume_factor

        # Decrease with model uncertainty
        confidence -= model_uncertainty

        # Clamp to [0, 1]
        return max(0.0, min(1.0, confidence))

    def _extract_recommendations(self, response: str) -> list:
        """
        Extract structured recommendations from response text.

        Looks for patterns like:
        - "RECOMMENDATION: ..."
        - "Action: ..."
        - "Suggestion: ..."

        Args:
            response: The model's response text

        Returns:
            List of recommendation strings
        """
        recommendations = []
        lines = response.split("\n")

        for line in lines:
            line = line.strip()
            for prefix in ["RECOMMENDATION:", "ACTION:", "SUGGESTION:", "📌"]:
                if line.startswith(prefix):
                    recommendations.append(line[len(prefix) :].strip())

        return recommendations

    async def health_check(self) -> dict[str, Any]:
        """
        Check agent health and readiness.

        Returns:
            Health status dictionary
        """
        return {
            "agent": self.name,
            "model": self.model,
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }
