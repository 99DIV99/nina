"""Panel booking API (B4). All writes are gated by booking.manage / staff.manage."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorization import (
    P_BOOKING_MANAGE,
    P_BOOKING_VIEW,
    P_CUSTOMER_MANAGE,
    P_CUSTOMER_VIEW,
    P_SERVICE_MANAGE,
    P_STAFF_MANAGE,
)
from apps.accounts.permissions import HasPermission, IsTenantMember
from apps.booking import services as booking_services
from apps.booking.availability import generate_slots
from apps.booking.models import Appointment, BusinessHours, Customer, Service, StaffMember, TimeOff
from apps.booking.serializers import (
    AppointmentCreateSerializer,
    AppointmentSerializer,
    AvailabilityQuerySerializer,
    BusinessHoursSerializer,
    CustomerSerializer,
    RescheduleSerializer,
    ServiceSerializer,
    StaffSerializer,
    TimeOffSerializer,
)
from apps.business.models import BusinessProfile
from apps.common.exceptions import DomainError


class _PermViewSet(viewsets.ModelViewSet):
    """ViewSet whose required permission depends on read vs write."""

    permission_classes = [HasPermission]
    view_permission = P_BOOKING_VIEW
    manage_permission = P_BOOKING_MANAGE

    @property
    def required_permission(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return self.view_permission
        return self.manage_permission


class ServiceViewSet(_PermViewSet):
    queryset = Service.objects.all().prefetch_related("staff")
    serializer_class = ServiceSerializer
    view_permission = P_BOOKING_VIEW
    manage_permission = P_SERVICE_MANAGE


class StaffViewSet(_PermViewSet):
    queryset = StaffMember.objects.all()
    serializer_class = StaffSerializer
    view_permission = P_BOOKING_VIEW
    manage_permission = P_STAFF_MANAGE


class CustomerViewSet(_PermViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    view_permission = P_CUSTOMER_VIEW
    manage_permission = P_CUSTOMER_MANAGE


class BusinessHoursViewSet(_PermViewSet):
    queryset = BusinessHours.objects.select_related("staff")
    serializer_class = BusinessHoursSerializer
    manage_permission = P_STAFF_MANAGE


class TimeOffViewSet(_PermViewSet):
    queryset = TimeOff.objects.select_related("staff")
    serializer_class = TimeOffSerializer
    manage_permission = P_STAFF_MANAGE


class AppointmentViewSet(_PermViewSet):
    queryset = Appointment.objects.select_related("service", "staff", "customer")
    serializer_class = AppointmentSerializer
    view_permission = P_BOOKING_VIEW
    manage_permission = P_BOOKING_MANAGE

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("staff"):
            qs = qs.filter(staff_id=params["staff"])
        if params.get("date_from"):
            qs = qs.filter(start_at__date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(start_at__date__lte=params["date_to"])
        return qs

    def create(self, request, *args, **kwargs):
        ser = AppointmentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        profile = BusinessProfile.get_solo()
        try:
            appt = booking_services.create_appointment(
                service=data["service"],
                staff=data["staff"],
                start_at=data["start_at"],
                customer=data.get("customer"),
                source="panel",
                price=data.get("price"),
                notes=data.get("notes", ""),
                enforce_availability=not data.get("override_availability", False),
                lead_minutes=profile.booking_lead_minutes,
                max_advance_days=profile.max_advance_days,
            )
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        return Response(AppointmentSerializer(appt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        appt = self.get_object()
        from apps.booking.models import AppointmentStatus

        appt.status = AppointmentStatus.CONFIRMED
        appt.save(update_fields=["status", "updated_at"])
        return Response(AppointmentSerializer(appt).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition(booking_services.cancel)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._transition(booking_services.complete)

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        return self._transition(booking_services.mark_no_show)

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        appt = self.get_object()
        ser = RescheduleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        profile = BusinessProfile.get_solo()
        try:
            appt = booking_services.reschedule(
                appt,
                new_start=ser.validated_data["start_at"],
                enforce_availability=not ser.validated_data.get("override_availability", False),
                lead_minutes=profile.booking_lead_minutes,
                max_advance_days=profile.max_advance_days,
            )
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        return Response(AppointmentSerializer(appt).data)

    def _transition(self, fn):
        appt = self.get_object()
        try:
            appt = fn(appt)
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        return Response(AppointmentSerializer(appt).data)


class AvailabilityView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        ser = AvailabilityQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        return Response(_availability_payload(ser.validated_data))


def _availability_payload(data: dict) -> dict:
    service = Service.objects.filter(pk=data["service"], is_active=True).first()
    if service is None:
        raise DomainError("Unknown service.", code="service_not_found", status_code=404)
    profile = BusinessProfile.get_solo()
    staff_qs = service.staff.filter(is_active=True)
    if data.get("staff"):
        staff_qs = staff_qs.filter(pk=data["staff"])

    result = []
    for staff in staff_qs:
        slots = generate_slots(
            service=service,
            staff=staff,
            range_start=data["date_from"],
            range_end=data["date_to"],
            lead_minutes=profile.booking_lead_minutes,
            max_advance_days=profile.max_advance_days,
        )
        result.append({"staff": StaffSerializer(staff).data, "slots": [s.as_dict() for s in slots]})
    return {"service": service.id, "availability": result}
