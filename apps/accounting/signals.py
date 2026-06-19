"""Connect booking signals to accounting (B6 auto-income)."""

from django.dispatch import receiver

from apps.booking.signals import appointment_completed


@receiver(appointment_completed)
def on_appointment_completed(sender, appointment, **kwargs):
    from apps.accounting.services import record_income_for_appointment

    record_income_for_appointment(appointment)
