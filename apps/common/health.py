"""Liveness and readiness probes (B0)."""

from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """Liveness: process is up. No dependencies checked."""
    return JsonResponse({"status": "ok"})


def readyz(request):
    """Readiness: can we reach the database?"""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception as exc:  # pragma: no cover - exercised in integration
        return JsonResponse({"status": "unready", "error": str(exc)}, status=503)
    return JsonResponse({"status": "ready"})
