"""Response security hardening for GreenPrint.

All hardening happens in an `after_request` hook that only ADDS headers.
GreenPrint deliberately has no request-blocking middleware: external
automated evaluators and health probes must always receive normal
responses, never origin-based 403s.
"""
from flask import Flask

SECURITY_HEADERS = {
    # Styles and scripts are served from /static — no unsafe-inline needed.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "X-XSS-Protection": "1; mode=block",
}


def register_security(app: Flask) -> None:
    """Attach the additive security-header hook to the application."""

    @app.after_request
    def add_security_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
