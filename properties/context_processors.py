from django.conf import settings

from .models import DeveloperLogo


def developer_logos(request):
    """Makes the active, logo-having DeveloperLogo rows available to every
    template as `developer_logos`, so the footer partial (included on many
    separate public views) doesn't need each view to remember to pass it."""
    return {
        'developer_logos': DeveloperLogo.objects.filter(
            is_active=True
        ).exclude(logo='').exclude(logo__isnull=True)
    }


def tracking(request):
    """GA4 / Meta Pixel IDs for partials/tracking_head.html. Empty (tags off)
    in DEBUG and for staff, so local work and the team's own browsing stay out
    of the numbers. Signed-in clients get a GA4 user_id (their numeric id, no
    personal data) so their sessions join up across devices."""
    off = {'ga4_measurement_id': '', 'meta_pixel_id': '', 'tracking_user_id': ''}
    if settings.DEBUG:
        return off
    user = getattr(request, 'user', None)
    user_id = ''
    if user is not None and user.is_authenticated:
        profile = getattr(user, 'profile', None)
        if user.is_staff or (profile is not None and profile.is_employee):
            return off
        user_id = str(user.pk)
    return {
        'ga4_measurement_id': settings.GA4_MEASUREMENT_ID,
        'meta_pixel_id': settings.META_PIXEL_ID,
        'tracking_user_id': user_id,
    }
