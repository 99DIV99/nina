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
    def send_otp(self, phone: str, code: str, *, purpose: str = "", business: str = "") -> bool:
        """Deliver the OTP `code` to `phone`. `purpose` (booking/signup) selects the
        message pattern; `business` is the booking pattern's name variable. True on
        accepted."""


class ConsoleProvider(SmsProvider):
    """No-op sender: records the code so the flow is testable without a gateway."""

    def send_otp(self, phone: str, code: str, *, purpose: str = "", business: str = "") -> bool:
        logger.info("otp_console", extra={"target": phone, "code": code})
        # Visible in container logs during the HTTP-first bring-up.
        print(f"[OTP] {phone} ({purpose} @ {business}) -> {code}")  # noqa: T201
        return True


class IranPayamakProvider(SmsProvider):
    """IranPayamak / FarazSMS — pattern (OTP) send (https://api.iranpayamak.com).

    Contract reverse-engineered from the live API (/ws/v1/sms/pattern): requires
    `code` (the panel pattern code), `recipient`, `line_number` (validated against
    the account), `number_format`, plus the pattern variable carrying the OTP.
    """

    BASE = "https://api.iranpayamak.com"

    @staticmethod
    def _pattern_for(purpose: str) -> str:
        """The approved pattern code for this OTP purpose (booking vs signup),
        falling back to the generic pattern when a per-purpose one isn't set."""
        per_purpose = {
            "booking": getattr(settings, "IRANPAYAMAK_PATTERN_BOOKING", ""),
            "signup": getattr(settings, "IRANPAYAMAK_PATTERN_SIGNUP", ""),
            "login": getattr(settings, "IRANPAYAMAK_PATTERN_LOGIN", ""),
        }
        return per_purpose.get(purpose) or getattr(settings, "IRANPAYAMAK_PATTERN_CODE", "")

    def send_otp(
        self, phone: str, code: str, *, purpose: str = "", business: str = "", timeout: int = 10
    ) -> bool:
        api_key = getattr(settings, "IRANPAYAMAK_API_KEY", "")
        pattern_code = self._pattern_for(purpose)
        line_number = getattr(settings, "IRANPAYAMAK_LINE_NUMBER", "")
        if not (api_key and pattern_code and line_number):
            logger.error("otp_iranpayamak_unconfigured")
            return False

        # Pattern variables — names must match the %placeholders% in the panel.
        # Booking carries %business_name% + %code%; signup is %code% only.
        variables = {getattr(settings, "IRANPAYAMAK_VAR_CODE", "code"): code}
        if business:
            max_len = getattr(settings, "IRANPAYAMAK_BUSINESS_MAX_LEN", 40)
            var = getattr(settings, "IRANPAYAMAK_VAR_BUSINESS", "business_name")
            variables[var] = business[:max_len]
        body = {
            "code": pattern_code,
            "recipient": phone,
            "line_number": line_number,
            "number_format": "english",
            # Pattern variables go in a single top-level "attributes" object
            # (confirmed live: a flat list under "input_data" 500s with
            # 'Undefined array key "attributes"').
            "attributes": variables,
        }
        req = urllib.request.Request(
            f"{self.BASE}/ws/v1/sms/pattern",
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
                    logger.error("otp_iranpayamak_rejected", extra={"method": str(payload)[:300]})
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
