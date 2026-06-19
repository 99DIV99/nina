"""Request-scoped context: request id + resolved tenant for logs/tracing."""

import logging
import uuid

from django.db import connection
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("nina.request")


class RequestContextMiddleware(MiddlewareMixin):
    """
    Runs AFTER TenantMainMiddleware, so `connection.schema_name` is already set.
    Attaches a request id and the active schema name for observability. It does
    NOT make any authorization decision -- isolation is enforced by the schema
    switch itself.
    """

    def process_request(self, request):
        request.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.tenant_schema = getattr(connection, "schema_name", "public")

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", None)
        if request_id:
            response["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "tenant": getattr(request, "tenant_schema", None),
                "path": request.path,
                "method": request.method,
                "user_id": getattr(getattr(request, "user", None), "id", None),
            },
        )
        return response
