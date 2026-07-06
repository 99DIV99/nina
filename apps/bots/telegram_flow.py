"""
Button-based Telegram booking flow (B7).

A deterministic state machine that replaces the text-based NLU for Telegram.
Each step presents inline-keyboard buttons (no emojis); the user taps a button or
types short text (name, phone, OTP code).  The flow reuses the same availability
engine and booking service as the web widget, so correctness guarantees
(no double-booking, tenant isolation) are unchanged.

Flow order (when require_phone_otp is True — the default):
    MENU → SERVICE → DATE → TIME → NAME → PHONE → OTP → CONFIRM → DONE

When require_phone_otp is False, the OTP step is skipped but phone is still
collected:
    MENU → SERVICE → DATE → TIME → NAME → PHONE → CONFIRM → DONE
"""

from __future__ import annotations

import logging
from datetime import date as date_cls, datetime, timedelta
from zoneinfo import ZoneInfo

from apps.bots import tools
from apps.bots.models import Bot, Conversation
from apps.bots.telegram import (
    answer_callback_query,
    send_message,
    send_message_with_buttons,
)
from apps.booking.availability import generate_slots
from apps.booking.models import Service, StaffMember
from apps.business.models import BusinessProfile

logger = logging.getLogger("nina.bots.telegram_flow")

# Max days ahead the date buttons cover (Telegram inline keyboards allow up to
# 100 buttons per message, so 7 is comfortable in a 4×2 grid + Back).
DATE_WINDOW_DAYS = 7
# How many time-slot buttons to render max (Telegram limit is ~100).
MAX_TIME_BUTTONS = 30
# Time-slot buttons per row.
TIME_BUTTONS_PER_ROW = 3


# ---------------------------------------------------------------------------
# Keyboard helpers
# ---------------------------------------------------------------------------

def _btn(label: str, data: str) -> dict[str, str]:
    return {"text": label, "callback_data": data}


def _back_row(target: str = "menu") -> list[dict[str, str]]:
    return [_btn("Back", f"back:{target}")]


def _cancel_row() -> list[dict[str, str]]:
    return [_btn("Cancel", "cancel")]


# ---------------------------------------------------------------------------
# Step → handler map
# ---------------------------------------------------------------------------

class TelegramFlow:
    """Encapsulates the state machine for one inbound update.

    A fresh instance is created per webhook delivery.  It reads
    ``conversation.state``, decides the next action, mutates state, and persists
    it via ``conversation.save()`` at the end of each step.
    """

    def __init__(self, bot: Bot, conversation: Conversation, parsed: dict) -> None:
        self.bot = bot
        self.conv = conversation
        self.parsed = parsed
        self.token = bot.telegram_bot_token
        self.chat_id = parsed["chat_id"]
        self.state: dict = conversation.state or {}
        # Ensure step is always set.
        self.state.setdefault("step", "MENU")
        self.profile = BusinessProfile.get_solo()
        self.tz = self._tz()

    def _tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.profile.timezone or "UTC")
        except Exception:  # noqa: BLE001
            return ZoneInfo("UTC")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle(self) -> None:
        is_callback = "callback_data" in self.parsed
        step = self.state["step"]

        if is_callback:
            data = self.parsed["callback_data"]
            # Global commands take priority regardless of step.
            if data == "cancel":
                self._do_cancel()
                return
            if data == "book" or data == "back:menu":
                self._step_menu(force=True)
                return

            self._dispatch_callback(step, data)
        else:
            # Text input — only valid in NAME / PHONE / OTP steps.
            text = self.parsed.get("text", "").strip()
            self._dispatch_text(step, text)

    # ------------------------------------------------------------------
    # Callback dispatch (explicit if/elif — clearer than nested ternaries)
    # ------------------------------------------------------------------

    def _dispatch_callback(self, step: str, data: str) -> None:
        if step == "MENU":
            if data == "book":
                self._cb_service_list(data)
            else:
                self._step_menu(force=True)

        elif step == "SERVICE":
            if data.startswith("svc:"):
                self._cb_enter_date(int(data.split(":")[1]))
            elif data == "back:svc":
                self._cb_service_list(data)
            else:
                self._cb_service_list(data)

        elif step == "DATE":
            if data.startswith("day:"):
                self._cb_enter_time(int(data.split(":")[1]))
            elif data == "back:date":
                self._cb_enter_date(self.state.get("service_id", 0))
            else:
                self._step_menu(force=True)

        elif step == "TIME":
            if data.startswith("t:"):
                self._cb_pick_time(int(data.split(":")[1]))
            elif data == "back:date":
                self._cb_enter_time(self.state.get("day_offset", 0))
            else:
                self._step_menu(force=True)

        elif step == "OTP":
            if data == "resend":
                self._cb_resend_otp(data)
            else:
                self._step_menu(force=True)

        elif step == "CONFIRM":
            if data == "confirm":
                self._cb_confirm(data)
            else:
                self._do_cancel()

        elif step == "DONE":
            self._step_menu(force=True)

        # NAME / PHONE don't have valid callbacks (text-input steps).
        else:
            self._ack()
            self._send("Please type your response, or press Cancel.")

    # ------------------------------------------------------------------
    # Text dispatch
    # ------------------------------------------------------------------

    def _dispatch_text(self, step: str, text: str) -> None:
        if step == "NAME":
            self._text_name(text)
        elif step == "PHONE":
            self._text_phone(text)
        elif step == "OTP":
            self._text_otp(text)
        else:
            # Unexpected text in a button-only step — nudge the user.
            self._send("Please use the buttons below to continue.")

    # ------------------------------------------------------------------
    # Callback answer helper
    # ------------------------------------------------------------------

    def _ack(self) -> None:
        """Acknowledge the button press (removes the loading spinner)."""
        cq_id = self.parsed.get("callback_query_id")
        if cq_id:
            answer_callback_query(self.token, cq_id)

    # ------------------------------------------------------------------
    # Step: MENU
    # ------------------------------------------------------------------

    def _step_menu(self, *, force: bool = False) -> None:
        self._ack()
        self.state = {"step": "MENU"}
        self._persist()
        self._send_buttons(
            "Book now!",
            [[_btn("Book appointment", "book")]],
        )

    # ------------------------------------------------------------------
    # Step: SERVICE
    # ------------------------------------------------------------------

    def _cb_service_list(self, data: str) -> None:
        self._ack()
        services = tools.list_services(self.bot)
        if not services:
            self._send_buttons(
                "No bookable services right now.",
                [_back_row()],
            )
            return
        # One button per service, stacked vertically (names can be long).
        rows = [
            [_btn(f"#{s['id']} {s['name']} ({s['duration_minutes']}m)", f"svc:{s['id']}")]
            for s in services
        ]
        rows.append(_back_row())
        self.state["step"] = "SERVICE"
        self._persist()
        self._send_buttons("Select a service:", rows)

    # ------------------------------------------------------------------
    # Step: DATE
    # ------------------------------------------------------------------

    def _cb_enter_date(self, service_id: int) -> None:
        self._ack()
        service = self._get_service(service_id)
        if service is None:
            self._send_buttons("That service is no longer available.", [_back_row("svc")])
            return
        self.state["service_id"] = service_id
        self.state["service_name"] = service.name
        self.state["step"] = "DATE"
        self._persist()

        today = date_cls.today()
        rows: list[list[dict[str, str]]] = []
        col: list[dict[str, str]] = []
        for i in range(DATE_WINDOW_DAYS):
            day = today + timedelta(days=i)
            if i == 0:
                label = "Today"
            elif i == 1:
                label = "Tomorrow"
            else:
                label = day.strftime("%a %b %d")
            col.append(_btn(label, f"day:{i}"))
            if len(col) == 2:  # 2 per row → 4 rows for 7 days
                rows.append(col)
                col = []
        if col:
            rows.append(col)
        rows.append(_back_row("svc"))
        self._send_buttons("Select a date:", rows)

    # ------------------------------------------------------------------
    # Step: TIME
    # ------------------------------------------------------------------

    def _cb_enter_time(self, day_offset: int) -> None:
        self._ack()
        service_id = self.state.get("service_id")
        service = self._get_service(service_id) if service_id else None
        if service is None:
            self._step_menu(force=True)
            return

        today = date_cls.today()
        day = today + timedelta(days=day_offset)

        # Generate slots for this one day and cache them in conversation state
        # so the time-selection button press doesn't re-query.
        slots = self._generate_slots(service, day)
        self.state["day_offset"] = day_offset
        self.state["date"] = day.isoformat()
        self.state["slots"] = [
            {"staff_id": s.staff_id, "start": s.start.isoformat()} for s in slots[:MAX_TIME_BUTTONS]
        ]
        self.state["step"] = "TIME"
        self._persist()

        if not slots:
            self._send_buttons(
                f"No available times for {day.strftime('%a %b %d')}.",
                [_back_row("date")],
            )
            return

        rows: list[list[dict[str, str]]] = []
        col: list[dict[str, str]] = []
        for idx, s in enumerate(slots[:MAX_TIME_BUTTONS]):
            local = s.start.astimezone(self.tz)
            label = local.strftime("%H:%M")
            col.append(_btn(label, f"t:{idx}"))
            if len(col) == TIME_BUTTONS_PER_ROW:
                rows.append(col)
                col = []
        if col:
            rows.append(col)
        rows.append(_back_row("date"))
        self._send_buttons(
            f"Available times for {service.name} on {day.strftime('%a %b %d')}:",
            rows,
        )

    def _cb_pick_time(self, slot_idx: int) -> None:
        self._ack()
        slots = self.state.get("slots", [])
        if slot_idx < 0 or slot_idx >= len(slots):
            self._send("That time is no longer available. Please pick another.")
            return
        chosen = slots[slot_idx]
        self.state["slot"] = chosen
        self.state["step"] = "NAME"
        self._persist()
        self._send_buttons(
            "Enter your name:",
            [_cancel_row()],
        )

    # ------------------------------------------------------------------
    # Step: NAME (text input)
    # ------------------------------------------------------------------

    def _text_name(self, text: str) -> None:
        name = text[:200].strip()
        if not name:
            self._send("Name is required. Please type your name.")
            return
        self.state["name"] = name
        self.state["step"] = "PHONE"
        self._persist()
        self._send_buttons("Enter your phone number:", [_cancel_row()])

    # ------------------------------------------------------------------
    # Step: PHONE (text input)
    # ------------------------------------------------------------------

    def _text_phone(self, text: str) -> None:
        from apps.otp.services import normalize_phone

        phone = normalize_phone(text)
        if len(phone) < 7:
            self._send(
                "That doesn't look like a valid phone number. Please try again,"
                " or press Cancel."
            )
            return

        self.state["phone"] = phone

        if self.profile.require_phone_otp:
            # Send OTP and move to OTP verification step.
            from apps.otp.services import request_otp
            from apps.common.exceptions import DomainError

            business_name = self.profile.display_name or "the business"
            try:
                request_otp(phone, "booking", business=business_name)
            except DomainError as exc:
                self._send(f"Could not send verification code: {exc.message}")
                return
            self.state["step"] = "OTP"
            self._persist()
            self._send_buttons(
                f"A verification code was sent to {phone}. Enter it:",
                [[_btn("Resend", "resend")], _cancel_row()],
            )
        else:
            # OTP not required — go straight to confirm.
            self.state["otp_verified"] = True
            self.state["step"] = "CONFIRM"
            self._persist()
            self._show_confirm()

    # ------------------------------------------------------------------
    # Step: OTP (text input)
    # ------------------------------------------------------------------

    def _text_otp(self, text: str) -> None:
        from apps.otp.services import verify_otp
        from apps.common.exceptions import DomainError

        code = text.strip()
        phone = self.state.get("phone", "")
        try:
            verify_otp(phone, "booking", code)
        except DomainError:
            self._send("Incorrect code. Please try again, or press Resend.")
            return

        self.state["otp_verified"] = True
        self.state["step"] = "CONFIRM"
        self._persist()
        self._show_confirm()

    def _cb_resend_otp(self, data: str) -> None:
        self._ack()
        from apps.otp.services import request_otp
        from apps.common.exceptions import DomainError

        phone = self.state.get("phone", "")
        business_name = self.profile.display_name or "the business"
        try:
            request_otp(phone, "booking", business=business_name)
            self._send("A new code was sent.")
        except DomainError as exc:
            self._send(f"Could not resend: {exc.message}")

    # ------------------------------------------------------------------
    # Step: CONFIRM
    # ------------------------------------------------------------------

    def _show_confirm(self) -> None:
        slot = self.state.get("slot")
        if not slot:
            self._step_menu(force=True)
            return
        start_iso = slot["start"]
        start = datetime.fromisoformat(start_iso)
        local = start.astimezone(self.tz)
        date_str = local.strftime("%a %b %d, %H:%M")
        name = self.state.get("name", "Guest")
        phone = self.state.get("phone", "")
        service_name = self.state.get("service_name", "")
        summary = (
            f"Service: {service_name}\n"
            f"When: {date_str}\n"
            f"Name: {name}\n"
            f"Phone: {phone}"
        )
        self._send_buttons(
            f"Please confirm your booking:\n\n{summary}",
            [[_btn("Confirm", "confirm")], _cancel_row()],
        )

    def _cb_confirm(self, data: str) -> None:
        self._ack()
        slot = self.state.get("slot")
        if not slot:
            self._step_menu(force=True)
            return

        service_id = self.state.get("service_id")
        service = self._get_service(service_id) if service_id else None
        if service is None:
            self._send_buttons("Service unavailable.", [_back_row("svc")])
            return

        staff_id = slot.get("staff_id")
        staff = StaffMember.objects.filter(id=staff_id, is_active=True).first()
        if staff is None:
            self._send_buttons("Staff member unavailable.", [_back_row("svc")])
            return

        start_at = datetime.fromisoformat(slot["start"])
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=ZoneInfo("UTC"))

        phone = self.state.get("phone", "")
        name = self.state.get("name", "Guest")

        try:
            result = tools.create_pending_booking(
                self.bot,
                service_id=service.id,
                staff_id=staff.id,
                start_at=start_at,
                customer_name=name,
                customer_phone=phone,
            )
        except Exception as exc:  # noqa: BLE001
            self._send(f"Could not create the booking: {exc}")
            return

        self.state["appointment_id"] = result["appointment_id"]
        self.state["step"] = "DONE"
        self._persist()
        self._send_buttons(
            "Appointment requested. The business will confirm shortly.",
            [[_btn("Book another", "book")]],
        )

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def _do_cancel(self) -> None:
        self._ack()
        self._step_menu(force=True)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _get_service(self, service_id: int | None) -> Service | None:
        if service_id is None:
            return None
        return next((s for s in tools._allowed_services(self.bot) if s.id == service_id), None)

    def _generate_slots(self, service: Service, day: date_cls):
        """All bookable slots for a service across all qualified staff on a day."""
        staff_qs = service.staff.filter(is_active=True)
        out = []
        for staff in staff_qs:
            slots = generate_slots(
                service=service,
                staff=staff,
                range_start=day,
                range_end=day,
                lead_minutes=self.profile.booking_lead_minutes,
                max_advance_days=self.profile.max_advance_days,
            )
            out.extend(slots)
        out.sort(key=lambda s: s.start)
        return out

    def _persist(self) -> None:
        self.conv.state = self.state
        self.conv.save(update_fields=["state", "updated_at"])

    def _send(self, text: str) -> None:
        send_message(self.token, self.chat_id, text)

    def _send_buttons(self, text: str, keyboard: list[list[dict[str, str]]]) -> None:
        send_message_with_buttons(self.token, self.chat_id, text, keyboard)

# ---------------------------------------------------------------------------
# Public entry point (called by TelegramWebhookView)
# ---------------------------------------------------------------------------

def handle_update(bot: Bot, conversation: Conversation, parsed: dict, raw_payload: dict) -> None:
    """Route an inbound Telegram update through the button-based flow."""
    flow = TelegramFlow(bot, conversation, parsed)
    flow.handle()