"""Consistent error envelope for the whole API (B10: error envelope)."""

from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """Wrap DRF errors in `{ "error": { code, message, details } }`."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    code = getattr(exc, "default_code", "error")

    def first_message(node) -> str:
        """Pull the most useful human-readable message out of a DRF error detail."""
        if isinstance(node, str):
            return node
        if isinstance(node, list):
            return first_message(node[0]) if node else "Request failed."
        if isinstance(node, dict):
            if "detail" in node:
                return str(node["detail"])
            for value in node.values():  # first field's first error
                return first_message(value)
        return "Request failed."

    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        message = str(detail["detail"])
        details = None
    else:
        # Surface the specific reason (e.g. "Invalid credentials.") instead of a
        # generic "Validation failed."; keep the full structure under `details`.
        message = first_message(detail)
        details = detail if isinstance(detail, dict) else None

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
