"""ResponseTranslator — full-response translation for GreenPrint.

Why this module exists: a multilingual assistant that only translates
the user's *input* still answers in English. GreenPrint translates the
ENTIRE structured response recursively, so a user who tracks in Hindi or
Telugu reads every label, tip and narrative in their own language.

Exclusions (never translated): machine-readable keys (factor_key,
unit, ...), unit symbols such as kgCO2e/kWh/km whose scientific meaning
is script-independent, and #hashtags whose platform function breaks in
non-Latin scripts.
"""
from google.cloud import translate_v3

from app.constants import (
    DEFAULT_LANGUAGE,
    NON_TRANSLATABLE_KEYS,
    PROTECTED_PREFIXES,
    SUPPORTED_LANGUAGES,
    UNIT_SYMBOLS,
)
from app.exceptions import TranslationError
from app.logging_config import get_logger

logger = get_logger(__name__)


class ResponseTranslator:
    """Cloud Translate v3 wrapper applying the recursive full-response pattern."""

    def __init__(self, config):
        self._config = config
        self._client = None

    @property
    def client(self) -> translate_v3.TranslationServiceClient:
        """Lazy Cloud Translate v3 client — created once per process."""
        if self._client is None:
            self._client = translate_v3.TranslationServiceClient()
        return self._client

    @property
    def _parent(self) -> str:
        return f"projects/{self._config.project_id}/locations/global"

    # ------------------------------------------------------------------
    def translate_response(self, payload: dict, target_language: str) -> dict:
        """Translate a full structured response; English passes through."""
        language = (target_language or DEFAULT_LANGUAGE).lower()
        if language == DEFAULT_LANGUAGE:
            return payload
        if language not in SUPPORTED_LANGUAGES:
            raise TranslationError(f"Unsupported language: {target_language}")
        try:
            return self.translate_json_values(payload, language)
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError("Translation service failed.") from exc

    def translate_json_values(self, obj, target_lang: str):
        """Recursively translate every translatable string value in `obj`."""
        if isinstance(obj, str):
            return self._translate_string(obj, target_lang)
        if isinstance(obj, dict):
            return {
                key: (value if key in NON_TRANSLATABLE_KEYS else self.translate_json_values(value, target_lang))
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [self.translate_json_values(item, target_lang) for item in obj]
        return obj  # Numbers, booleans, None pass through untouched.

    def _translate_string(self, text: str, target_lang: str) -> str:
        if not self.is_translatable(text):
            return text
        response = self.client.translate_text(
            request={
                "parent": self._parent,
                "contents": [text],
                "mime_type": "text/plain",
                "source_language_code": DEFAULT_LANGUAGE,
                "target_language_code": target_lang,
            }
        )
        return response.translations[0].translated_text

    @staticmethod
    def is_translatable(text: str) -> bool:
        """Decide whether a string carries prose meaning worth translating."""
        stripped = text.strip()
        if not stripped:
            return False
        if any(stripped.startswith(prefix) for prefix in PROTECTED_PREFIXES):
            return False  # Hashtags keep platform function only verbatim.
        if stripped in UNIT_SYMBOLS:
            return False
        return True

    def is_healthy(self) -> bool:
        try:
            return self.client is not None
        except Exception:
            return False
