"""Reusable drf-spectacular building blocks.

Most of our endpoints are hand-written ``APIView``s with no ``serializer_class``,
so by default the Swagger UI can only show the path + docstring — no request body,
query parameters, or response shape. These serializers (plus ``@extend_schema`` on
each view) give spectacular the shapes it needs to render real, parameterised docs.
"""

from rest_framework import serializers


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Stable machine-readable error code.")
    message = serializers.CharField(help_text="Human-readable explanation.")


class ErrorResponseSerializer(serializers.Serializer):
    """The uniform error envelope every endpoint returns on failure."""

    error = ErrorDetailSerializer()


class TokenPairSerializer(serializers.Serializer):
    """JWT pair issued on a successful login / signup."""

    access = serializers.CharField(help_text="Short-lived access token (Bearer).")
    refresh = serializers.CharField(help_text="Long-lived refresh token.")
