"""Domain exception hierarchy for GreenPrint.

Every failure surfaced to a route is a `GreenPrintError` subtype so the
API layer can map domain failures to stable JSON error contracts without
inspecting third-party exception types.
"""


class GreenPrintError(Exception):
    """Base class for all GreenPrint domain errors."""

    status_code = 500
    public_message = "An internal error occurred while processing your footprint."


class ValidationError(GreenPrintError):
    """The caller supplied a malformed or unsafe request payload."""

    status_code = 400
    public_message = "The request payload is invalid."

    def __init__(self, message: str):
        super().__init__(message)
        self.public_message = message


class EstimationError(GreenPrintError):
    """Activity interpretation or emission estimation failed."""

    status_code = 502
    public_message = "Could not estimate emissions for the described activity."


class TranslationError(GreenPrintError):
    """The full-response translation pipeline failed."""

    status_code = 502
    public_message = "Could not translate the response to the requested language."


class LedgerError(GreenPrintError):
    """Reading from or writing to the footprint ledger failed."""

    status_code = 502
    public_message = "Could not access the footprint history ledger."
