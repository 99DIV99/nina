"""Minimal RFC 5545 .ics builder for booking confirmations (B5)."""

from datetime import datetime


def _fmt(dt: datetime) -> str:
    return (
        dt.astimezone(tz=None).strftime("%Y%m%dT%H%M%SZ")
        if dt.tzinfo
        else dt.strftime("%Y%m%dT%H%M%S")
    )


def build_ics(
    *,
    uid: str,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    location: str = "",
) -> bytes:
    import datetime as _dt
    from zoneinfo import ZoneInfo

    def z(dt):
        return dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")

    now = _dt.datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NINA//Booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        f"DTSTART:{z(start)}",
        f"DTEND:{z(end)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{location}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
