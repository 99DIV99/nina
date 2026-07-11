"""Panel booking API (B4). All writes are gated by booking.manage / staff.manage."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers, status, viewsets
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
    AppointmentPaymentSerializer,
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
from apps.common.api_schema import ErrorResponseSerializer
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


@extend_schema_view(
    list=extend_schema(
        summary="List appointments (filterable)",
        parameters=[
            OpenApiParameter("status", str, description="Filter by status."),
            OpenApiParameter("staff", int, description="Filter by staff id."),
            OpenApiParameter(
                "date_from", OpenApiTypes.DATE, description="Only on/after this date."
            ),
            OpenApiParameter("date_to", OpenApiTypes.DATE, description="Only on/before this date."),
        ],
    ),
    create=extend_schema(
        summary="Create an appointment (panel)",
        request=AppointmentCreateSerializer,
        responses={201: AppointmentSerializer, 400: ErrorResponseSerializer},
    ),
)
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

    @extend_schema(
        summary="Confirm an appointment",
        request=None,
        responses={200: AppointmentSerializer},
    )
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        appt = self.get_object()
        from apps.booking.models import AppointmentStatus

        appt.status = AppointmentStatus.CONFIRMED
        appt.save(update_fields=["status", "updated_at"])
        return Response(AppointmentSerializer(appt).data)

    @extend_schema(
        summary="Cancel an appointment",
        request=None,
        responses={200: AppointmentSerializer, 400: ErrorResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition(booking_services.cancel)

    @extend_schema(
        summary="Mark an appointment complete (posts income)",
        request=None,
        responses={200: AppointmentSerializer, 400: ErrorResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._transition(booking_services.complete)

    @extend_schema(
        summary="Mark an appointment as a no-show",
        request=None,
        responses={200: AppointmentSerializer, 400: ErrorResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        return self._transition(booking_services.mark_no_show)

    @extend_schema(
        summary="Reschedule an appointment",
        request=RescheduleSerializer,
        responses={200: AppointmentSerializer, 400: ErrorResponseSerializer},
    )
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

    @extend_schema(
        summary="Get or record appointment payment details",
        request=AppointmentPaymentSerializer,
        responses={200: AppointmentPaymentSerializer, 400: ErrorResponseSerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def payment(self, request, pk=None):
        appointment = self.get_object()
        if request.method == "GET":
            return Response(AppointmentPaymentSerializer(appointment).data)
        serializer = AppointmentPaymentSerializer(appointment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # The completion signal handles the opposite order (paid first, then
        # completed). This handles completing first, then recording payment.
        from apps.accounting.services import record_income_for_appointment

        record_income_for_appointment(appointment)
        return Response(serializer.data)

    def _transition(self, fn):
        appt = self.get_object()
        try:
            appt = fn(appt)
        except DomainError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}}, status=exc.status_code
            )
        return Response(AppointmentSerializer(appt).data)


class StaffSlotsSerializer(serializers.Serializer):
    staff = StaffSerializer()
    slots = serializers.ListField(
        child=inline_serializer(
            "AvailabilitySlot",
            {
                "start": serializers.DateTimeField(),
                "end": serializers.DateTimeField(),
                "staff_id": serializers.IntegerField(),
            },
        )
    )


class AvailabilityResponseSerializer(serializers.Serializer):
    """Bookable slots per qualified staff member for a service over a date range."""

    service = serializers.IntegerField()
    availability = StaffSlotsSerializer(many=True)


@extend_schema(
    summary="Bookable slots for a service (panel)",
    parameters=[AvailabilityQuerySerializer],
    responses={200: AvailabilityResponseSerializer},
)
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
