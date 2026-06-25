"""
SMS provider abstraction. The OTP engine is provider-agnostic; concrete senders
plug in here and are selected by settings.SMS_PROVIDER.

- console  : logs the code (default) — the full OTP flow works with no credentials
             and no real SMS, ideal for dev / the HTTP-first bring-up.
- iranpayamak: real delivery via IranPayamak/FarazSMS "Send Simple SMS"
             (POST /ws/v1/sms/simple, Api-Key header).
"""

from __future__ import annotations

import json
import logging
import urllib.request
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger("nina.otp")


class SmsProvider(ABC):
    @abstractmethod
    def send_otp(self, phone: str, code: str) -> bool:
        """Deliver the OTP `code` to `phone`. Return True on accepted-for-delivery."""


class ConsoleProvider(SmsProvider):
    """No-op sender: records the code so the flow is testable without a gateway."""

    def send_otp(self, phone: str, code: str) -> bool:
        logger.info("otp_console", extra={"target": phone, "code": code})
        # Visible in container logs during the HTTP-first bring-up.
        print(f"[OTP] {phone} -> {code}")  # noqa: T201
        return True


class IranPayamakProvider(SmsProvider):
    """IranPayamak / FarazSMS — Send Simple SMS (https://api.iranpayamak.com)."""

    BASE = "https://api.iranpayamak.com"

    def send_otp(self, phone: str, code: str, *, timeout: int = 10) -> bool:
        api_key = getattr(settings, "IRANPAYAMAK_API_KEY", "")
        line_number = getattr(settings, "IRANPAYAMAK_LINE_NUMBER", "")
        if not api_key or not line_number:
            logger.error("otp_iranpayamak_unconfigured")
            return False

        template = getattr(settings, "OTP_SMS_TEMPLATE", "Your verification code: {code}")
        body = {
            "text": template.format(code=code),
            "line_number": line_number,
            "recipients": [phone],
            "number_format": "english",
            "schedule": None,
        }
        req = urllib.request.Request(
            f"{self.BASE}/ws/v1/sms/simple",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Api-Key": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                payload = json.loads(resp.read().decode("utf-8") or "{}")
                ok = 200 <= resp.status < 300 and payload.get("status") == "success"
                if not ok:
                    logger.error("otp_iranpayamak_rejected", extra={"method": str(payload)[:200]})
                return ok
        except Exception as exc:  # noqa: BLE001
            logger.error("otp_iranpayamak_failed", extra={"method": str(exc)[:200]})
            return False


_PROVIDERS = {
    "console": ConsoleProvider,
    "iranpayamak": IranPayamakProvider,
}


def get_provider() -> SmsProvider:
    name = getattr(settings, "SMS_PROVIDER", "console")
    return _PROVIDERS.get(name, ConsoleProvider)()
