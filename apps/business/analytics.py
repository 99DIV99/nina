"""Public-page analytics: cookieless, PII-free view capture.

A "visitor" is identified by a SALTED hash of IP + User-Agent + the calendar day.
The day component makes the hash rotate daily (so it can't track anyone across
days); SECRET_KEY salts it (so it's irreversible / not guessable). We store only
the hash — never the IP or UA — which lets us count unique visitors per day
without holding any personal data.
"""

import hashlib
from datetime import date

from django.conf import settings

from apps.business.models import PageView


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def visitor_hash_for(request) -> str:
    ip = _client_ip(request)
    ua = request.META.get("HTTP_USER_AGENT", "")
    raw = f"{ip}|{ua}|{date.today().isoformat()}|{settings.SECRET_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def record_page_view(request, *, ref: str = "") -> None:
    PageView.objects.create(visitor_hash=visitor_hash_for(request), ref=(ref or "")[:40])
