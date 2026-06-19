"""
NLU interface (B7). The pipeline depends on this protocol, not a concrete model,
so a rule-based parser (default, dependency-free) or an LLM adapter (e.g. Claude
tool use with the scoped tools in tools.py) can be swapped in via settings.

An LLM adapter MUST be constrained to the tools in apps.bots.tools and the
current tenant -- it never gets a free-form database capability.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Intent:
    name: str  # greet | list_services | choose_service | pick_time | provide_contact | book | fallback
    entities: dict = field(default_factory=dict)


class RuleBasedNLU:
    """Tiny deterministic parser; good enough for the web widget happy path and
    fully testable. Replace with an LLM adapter for natural conversation."""

    def parse(self, text: str, *, state: dict) -> Intent:
        t = (text or "").strip().lower()
        if not t:
            return Intent("fallback")
        if any(w in t for w in ("hi", "hello", "hey")):
            return Intent("greet")

        # A specific service selection ("service #5") must win over the generic
        # "show me your services" listing intent.
        m = re.search(r"service\s*#?(\d+)", t)
        if m:
            return Intent("choose_service", {"service_id": int(m.group(1))})

        if "service" in t or "what do you" in t or "menu" in t:
            return Intent("list_services")

        m = re.search(r"(\d{4}-\d{2}-\d{2})[ t](\d{2}:\d{2})", t)
        if m:
            return Intent("pick_time", {"date": m.group(1), "time": m.group(2)})

        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text or "")
        if m:
            return Intent("provide_contact", {"email": m.group(0)})

        if "book" in t or "confirm" in t or "yes" in t:
            return Intent("book")
        return Intent("fallback")


def get_nlu():
    return RuleBasedNLU()
