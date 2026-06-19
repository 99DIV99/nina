"""Domain signals so other modules (accounting, notifications) can react without
the booking engine knowing about them."""
import django.dispatch

appointment_created = django.dispatch.Signal()  # kwargs: appointment
appointment_completed = django.dispatch.Signal()  # kwargs: appointment
appointment_cancelled = django.dispatch.Signal()  # kwargs: appointment
appointment_rescheduled = django.dispatch.Signal()  # kwargs: appointment, old_start
