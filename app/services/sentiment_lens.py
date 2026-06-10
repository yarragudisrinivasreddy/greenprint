"""SentimentLens — Cloud Natural Language analysis of user reflections.

Product role: users often add a note to their tracking ("felt guilty
about the flight", "proud of cycling week"). SentimentLens reads the
motivational tone so the InsightComposer can choose between celebratory
and encouraging coaching language — the same data, a more human nudge.
"""
from google.cloud import language_v2

from app.logging_config import get_logger

logger = get_logger(__name__)


class SentimentLens:
    """Cloud Natural Language sentiment scoring of free-text notes."""

    def __init__(self):
        self._client = None

    @property
    def client(self) -> language_v2.LanguageServiceClient:
        """Lazy Cloud NL client — created once per process."""
        if self._client is None:
            self._client = language_v2.LanguageServiceClient()
        return self._client

    def gauge_motivation(self, text: str) -> dict:
        """Score sentiment of a user's note; neutral fallback on failure."""
        if not text or not text.strip():
            return {"score": 0.0, "tone": "neutral"}
        try:
            document = language_v2.Document(
                content=text, type_=language_v2.Document.Type.PLAIN_TEXT
            )
            sentiment = self.client.analyze_sentiment(
                request={"document": document}
            ).document_sentiment
            score = round(sentiment.score, 2)
        except Exception as exc:
            logger.warning("Sentiment analysis unavailable: %s", exc)
            score = 0.0
        if score > 0.25:
            tone = "celebratory"
        elif score < -0.25:
            tone = "encouraging"
        else:
            tone = "neutral"
        return {"score": score, "tone": tone}

    def is_healthy(self) -> bool:
        try:
            return self.client is not None
        except Exception:
            return False
