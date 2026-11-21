"""
Client activity logging for the staff activity page (/crm/activity/).
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# A client flicking back and forth to the same listing is one view, not twenty.
VIEW_DEDUP_MINUTES = 30


def log_activity(user, event, related_property=None, detail=''):
    """Record one thing a signed-in client did. Staff and anonymous visitors
    are ignored. Never raises: analytics must not be able to break a page."""
    from crm.models import ClientActivity

    try:
        if user is None or not user.is_authenticated or user.is_staff:
            return
        profile = getattr(user, 'profile', None)
        if profile is not None and profile.is_employee:
            return
        if event == ClientActivity.Event.PROPERTY_VIEW and related_property is not None:
            recent = timezone.now() - timedelta(minutes=VIEW_DEDUP_MINUTES)
            if ClientActivity.objects.filter(
                user=user, event=event, related_property=related_property, created_at__gte=recent,
            ).exists():
                return
        ClientActivity.objects.create(
            user=user, event=event, related_property=related_property, detail=(detail or '')[:200],
        )
    except Exception:
        logger.warning("Could not record client activity %s", event, exc_info=True)
