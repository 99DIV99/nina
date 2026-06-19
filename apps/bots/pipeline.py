"""
Conversational booking pipeline (B7): understand intent -> check REAL
availability (reuses Phase B4) -> create a PENDING appointment -> surface it in
the panel review queue. Transcript is logged per tenant.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apps.bots import tools
from apps.bots.models import Conversation, Message
from apps.bots.nlu import get_nlu


def _reply(conversation: Conversation, text: str) -> dict:
    Message.objects.create(conversation=conversation, role=Message.Role.BOT, text=text)
    conversation.save(update_fields=["state", "updated_at"])
    return {"reply": text, "state": conversation.state, "conversation_id": conversation.id}


def handle_message(bot, conversation: Conversation, text: str) -> dict:
    Message.objects.create(conversation=conversation, role=Message.Role.USER, text=text)
    state = conversation.state or {}
    intent = get_nlu().parse(text, state=state)

    if intent.name == "greet":
        return _reply(conversation, bot.greeting + " Say 'services' to see what I can book.")

    if intent.name == "list_services":
        services = tools.list_services(bot)
        if not services:
            return _reply(conversation, "Sorry, there are no bookable services right now.")
        listing = "; ".join(f"#{s['id']} {s['name']} ({s['duration_minutes']}m)" for s in services)
        return _reply(conversation, f"Here is what I can book: {listing}. Reply 'service #<id>'.")

    if intent.name == "choose_service":
        state["service_id"] = intent.entities["service_id"]
        conversation.state = state
        return _reply(conversation, "Great. What date and time? Use YYYY-MM-DD HH:MM.")

    if intent.name == "pick_time":
        state["date"] = intent.entities["date"]
        state["time"] = intent.entities["time"]
        conversation.state = state
        return _reply(conversation, "Thanks. What's your email so I can confirm?")

    if intent.name == "provide_contact":
        state["email"] = intent.entities["email"]
        conversation.state = state
        return _reply(conversation, "Got it. Reply 'book' to request this slot.")

    if intent.name == "book":
        missing = [k for k in ("service_id", "date", "time", "email") if k not in state]
        if missing:
            return _reply(conversation, f"I still need: {', '.join(missing)}.")
        service_id = state["service_id"]
        avail = tools.check_availability(
            bot, service_id=service_id, day=datetime.fromisoformat(state["date"]).date()
        )
        target = f"{state['date']}T{state['time']}"
        match = next((s for s in avail if s["start"].startswith(target)), None)
        if match is None:
            return _reply(conversation, "That slot isn't available. Try another time.")
        start_at = datetime.fromisoformat(match["start"])
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=ZoneInfo("UTC"))
        try:
            result = tools.create_pending_booking(
                bot,
                service_id=service_id,
                staff_id=match["staff_id"],
                start_at=start_at,
                customer_name=state.get("name", "Guest"),
                customer_email=state["email"],
            )
        except Exception as exc:  # noqa: BLE001
            return _reply(conversation, f"I couldn't hold that slot: {exc}")
        state["appointment_id"] = result["appointment_id"]
        conversation.state = state
        return _reply(
            conversation,
            "Done! I've requested that slot; the business will confirm shortly.",
        )

    return _reply(conversation, "I can help you book. Say 'services' to start.")
