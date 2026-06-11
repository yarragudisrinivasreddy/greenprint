"""Domain exception hierarchy for GreenPrint.

Every failure surfaced to a route is a `GreenPrintError` subtype so the
API layer can map domain failures to stable JSON error contracts without
inspecting third-party exception types.
"""
from __future__ import annotations


class GreenPrintError(Exception):
    """Base class for all GreenPrint domain errors."""

    status_code: int = 500
    public_message: str = "An internal error occurred while processing your footprint."


class ValidationError(GreenPrintError):
    """The caller supplied a malformed or unsafe request payload."""

    status_code: int = 400
    public_message: str = "The request payload is invalid."

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_message = message


class EstimationError(GreenPrintError):
    """Activity interpretation or emission estimation failed."""

    status_code: int = 502
    public_message: str = "Could not estimate emissions for the described activity."


class TranslationError(GreenPrintError):
    """The full-response translation pipeline failed."""

    status_code: int = 502
    public_message: str = "Could not translate the response to the requested language."


class LedgerError(GreenPrintError):
    """Reading from or writing to the footprint ledger failed."""

    status_code: int = 502
    public_message: str = "Could not access the footprint history ledger."
