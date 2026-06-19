"""Consistent error envelope for the whole API (B10: error envelope)."""
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """Wrap DRF errors in `{ "error": { code, message, details } }`."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    code = getattr(exc, "default_code", "error")
    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        message = str(detail["detail"])
        details = None
    elif isinstance(detail, (list, str)):
        message = "Request failed."
        details = detail
    else:
        message = "Validation failed."
        details = detail

    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response


class DomainError(Exception):
    """Base class for booking/business domain errors surfaced to the API."""

    code = "domain_error"
    status_code = 400

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
