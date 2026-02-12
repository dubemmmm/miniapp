"""
Utility helpers for the CRM app.
"""
from datetime import datetime, timedelta, time
from django.utils import timezone


def compute_sla_deadline(start_dt, sla_config):
    """
    Compute the SLA deadline from start_dt, respecting business hours.

    If start_dt falls outside business hours or on a non-business day,
    the SLA clock starts at the next business day's opening time.
    Then `sla_config.first_contact_hours` business hours are added.

    Returns a timezone-aware datetime.
    """
    business_days = sla_config.business_days or [1, 2, 3, 4, 5]
    bh_start = sla_config.business_hours_start  # time object
    bh_end = sla_config.business_hours_end      # time object
    hours_needed = sla_config.first_contact_hours

    # Ensure start_dt is timezone-aware (UTC)
    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt)

    current = start_dt

    # If outside business hours, advance to the next business day open
    current = _advance_to_business_hours(current, business_days, bh_start, bh_end)

    # Now add business hours
    remaining = hours_needed
    while remaining > 0:
        end_of_day = current.replace(
            hour=bh_end.hour, minute=bh_end.minute, second=0, microsecond=0
        )
        hours_left_today = (end_of_day - current).total_seconds() / 3600

        if hours_left_today >= remaining:
            current = current + timedelta(hours=remaining)
            remaining = 0
        else:
            remaining -= hours_left_today
            # Jump to next business day open
            next_day = current + timedelta(days=1)
            next_day = next_day.replace(
                hour=bh_start.hour, minute=bh_start.minute, second=0, microsecond=0
            )
            current = _advance_to_business_hours(next_day, business_days, bh_start, bh_end)

    return current


def _advance_to_business_hours(dt, business_days, bh_start, bh_end):
    """Advance dt to the nearest business-hours open moment."""
    bh_start_time = time(bh_start.hour, bh_start.minute)
    bh_end_time = time(bh_end.hour, bh_end.minute)

    for _ in range(14):  # Safety cap: max 2 weeks forward
        # ISO weekday: 1=Mon, 7=Sun
        if dt.isoweekday() in business_days:
            current_time = dt.time().replace(second=0, microsecond=0)
            if bh_start_time <= current_time < bh_end_time:
                return dt
            elif current_time < bh_start_time:
                return dt.replace(
                    hour=bh_start.hour, minute=bh_start.minute, second=0, microsecond=0
                )
        # Move to next day at bh_start
        dt = (dt + timedelta(days=1)).replace(
            hour=bh_start.hour, minute=bh_start.minute, second=0, microsecond=0
        )
    return dt


def get_client_ip(request):
    """Extract the real client IP, respecting X-Forwarded-For."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')
