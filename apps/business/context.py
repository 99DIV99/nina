"""
The bootstrap/context payload (B3).

This is an OUTBOUND RENDERING HINT only. It grants nothing. Authorization stays
per-request and server-side: the frontend may use `experience`/`enabledModules`
to decide what to render, but every data call is independently authorized.
"""
from apps.accounts.authorization import current_membership, effective_permissions
from apps.business.models import DEFAULT_VOCABULARY, BusinessProfile


def build_context(request) -> dict:
    business = request.tenant  # public-schema Business, set by TenantMainMiddleware
    profile = BusinessProfile.get_solo()
    membership = current_membership(request)

    base_vocab = DEFAULT_VOCABULARY.get(business.experience, DEFAULT_VOCABULARY["general"])
    vocabulary = {**base_vocab, **(profile.vocabulary or {})}

    return {
        "business": {
            "name": business.name,
            "type": business.business_type,
            "plan": business.plan,
            "is_active": business.is_active,
        },
        "experience": business.experience,
        "enabledModules": business.enabled_modules(),
        "branding": {
            "displayName": profile.display_name or business.name,
            "logoUrl": profile.logo_url,
            "primaryColor": profile.primary_color,
            "accentColor": profile.accent_color,
        },
        "vocabulary": vocabulary,
        "policies": {
            "timezone": profile.timezone,
            "bookingLeadMinutes": profile.booking_lead_minutes,
            "maxAdvanceDays": profile.max_advance_days,
            "cancellationWindowHours": profile.cancellation_window_hours,
        },
        "user": {
            "id": request.user.id,
            "email": request.user.email,
            "role": membership.role if membership else None,
            "permissions": sorted(effective_permissions(request)),
        },
    }
