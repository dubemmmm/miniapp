"""
CRM Celery tasks:
  - send_visitor_confirmation      — transactional email to visitor
  - send_agent_notification        — internal alert to assigned agent
  - send_admin_escalation_email    — escalation to all admins
  - sweep_overdue_leads            — periodic: mark leads + followups overdue
  - sweep_escalations              — periodic: escalate stale overdue leads
  - compute_response_scores        — periodic: recompute agent response_score
"""
import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_lead(lead_id):
    from crm.models import Lead
    return Lead.objects.select_related('related_property').get(id=lead_id)


def _get_current_agent(lead):
    """Return the agent User for the lead's current assignment, or None."""
    assignment = lead.assignments.filter(is_current=True).first()
    if assignment and assignment.agent:
        return assignment.agent
    return None


def _site_url():
    return getattr(settings, 'SITE_URL', 'http://localhost:8000')


# ---------------------------------------------------------------------------
# Visitor confirmation email
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def send_visitor_confirmation(self, lead_id):
    from crm.models import EmailLog, ActivityLog
    from crm.email_service import send_transactional_email, render_template

    lead = _get_lead(lead_id)
    agent_user = _get_current_agent(lead)

    idempotency_key = f"{lead_id}:visitor_confirmation:{lead.email}"
    email_log, created = EmailLog.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'lead': lead,
            'recipient_email': lead.email,
            'recipient_type': EmailLog.RecipientType.VISITOR,
            'template_name': 'visitor_confirmation',
            'subject': f"Your enquiry for {lead.property_title_snapshot} has been received",
            'status': EmailLog.Status.PENDING,
        }
    )

    # Idempotency guard
    if not created and email_log.status == EmailLog.Status.SENT:
        logger.info("Visitor confirmation already sent for lead %s — skipping", lead_id)
        return

    # Build context
    if agent_user:
        profile = getattr(agent_user, 'profile', None)
        agent_name = agent_user.get_full_name() or agent_user.username
        agent_phone = getattr(profile, 'phone', '') if profile else ''
        agent_whatsapp = getattr(profile, 'whatsapp_number', '') if profile else ''
        agent_email = agent_user.email
    else:
        agent_name = 'Our team'
        agent_phone = ''
        agent_whatsapp = ''
        agent_email = settings.DEFAULT_FROM_EMAIL

    context = {
        'first_name': lead.first_name,
        'property_title': lead.property_title_snapshot,
        'property_location': lead.property_location_snapshot,
        'property_link': lead.property_url_snapshot,
        'agent_name': agent_name,
        'agent_phone': agent_phone or 'To be provided',
        'agent_whatsapp': agent_whatsapp or 'N/A',
        'agent_email': agent_email,
        'unsubscribe_link': f"{_site_url()}/crm/unsubscribe/{lead_id}/",
        'privacy_policy_link': f"{_site_url()}/privacy/",
    }

    body = render_template('visitor_confirmation', context)
    # Extract subject from first line of template (line starting with "Subject:")
    lines = body.splitlines()
    subject = email_log.subject
    body_lines = []
    for i, line in enumerate(lines):
        if line.startswith('Subject:'):
            subject = line.replace('Subject:', '').strip()
        elif i > 0 or not line.startswith('Subject:'):
            body_lines.append(line)
    body_text = '\n'.join(body_lines).strip()

    success, provider_id, error = send_transactional_email(
        recipient_email=lead.email,
        subject=subject,
        body_text=body_text,
    )

    if success:
        email_log.status = EmailLog.Status.SENT
        email_log.provider_message_id = provider_id or ''
        email_log.sent_at = timezone.now()
        email_log.save(update_fields=['status', 'provider_message_id', 'sent_at', 'updated_at'])

        ActivityLog.objects.create(
            lead=lead,
            actor=None,
            event_type=ActivityLog.EventType.EMAIL_SENT,
            contact_method=ActivityLog.ContactMethod.EMAIL,
            note=f"Visitor confirmation email sent to {lead.email}",
        )
    else:
        email_log.status = EmailLog.Status.FAILED
        email_log.retry_count += 1
        email_log.last_error = error or 'Unknown error'
        email_log.save(update_fields=['status', 'retry_count', 'last_error', 'updated_at'])
        logger.error("Failed to send visitor confirmation for lead %s: %s", lead_id, error)
        raise Exception(f"SendGrid error: {error}")


# ---------------------------------------------------------------------------
# Agent notification email
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def send_agent_notification(self, lead_id):
    from crm.models import EmailLog, ActivityLog
    from crm.email_service import send_transactional_email, render_template

    lead = _get_lead(lead_id)
    agent_user = _get_current_agent(lead)

    # If no agent (FALLBACK), notify all admin users instead
    recipients = []
    if agent_user:
        recipients = [agent_user]
    else:
        recipients = list(
            User.objects.filter(
                is_active=True, profile__role='admin'
            ).select_related('profile')
        )

    for recipient in recipients:
        if not recipient.email:
            logger.warning("Skipping agent notification for user %s — no email address", recipient.username)
            continue
        idempotency_key = f"{lead_id}:agent_notification:{recipient.email}"
        email_log, created = EmailLog.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                'lead': lead,
                'recipient_email': recipient.email,
                'recipient_type': EmailLog.RecipientType.AGENT if agent_user else EmailLog.RecipientType.ADMIN,
                'template_name': 'agent_notification',
                'subject': f"New lead assigned to you — {lead.property_title_snapshot}",
                'status': EmailLog.Status.PENDING,
            }
        )

        if not created and email_log.status == EmailLog.Status.SENT:
            continue

        context = {
            'agent_name': recipient.get_full_name() or recipient.username,
            'property_title': lead.property_title_snapshot,
            'property_location': lead.property_location_snapshot,
            'visitor_first_name': lead.first_name,
            'visitor_last_name': lead.last_name,
            'visitor_email': lead.email,
            'visitor_phone': lead.phone or 'Not provided',
            'visitor_message': lead.message,
            'submission_datetime': lead.created_at.strftime('%d %b %Y, %H:%M UTC'),
            'sla_deadline': lead.sla_deadline.strftime('%d %b %Y, %H:%M UTC'),
            'lead_id': str(lead.id)[:8].upper(),
            'crm_lead_url': f"{_site_url()}/crm/leads/{lead.id}/",
        }

        body = render_template('agent_notification', context)
        lines = body.splitlines()
        subject = email_log.subject
        body_lines = []
        for i, line in enumerate(lines):
            if line.startswith('Subject:'):
                subject = line.replace('Subject:', '').strip()
            else:
                body_lines.append(line)
        body_text = '\n'.join(body_lines).strip()

        success, provider_id, error = send_transactional_email(
            recipient_email=recipient.email,
            subject=subject,
            body_text=body_text,
        )

        if success:
            email_log.status = EmailLog.Status.SENT
            email_log.provider_message_id = provider_id or ''
            email_log.sent_at = timezone.now()
            email_log.save(update_fields=['status', 'provider_message_id', 'sent_at', 'updated_at'])
        else:
            email_log.status = EmailLog.Status.FAILED
            email_log.retry_count += 1
            email_log.last_error = error or 'Unknown error'
            email_log.save(update_fields=['status', 'retry_count', 'last_error', 'updated_at'])
            logger.error("Failed to send agent notification for lead %s: %s", lead_id, error)
            raise Exception(f"SendGrid error: {error}")


# ---------------------------------------------------------------------------
# Admin escalation email
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=60, autoretry_for=(Exception,))
def send_admin_escalation_email(self, lead_id):
    from crm.models import EmailLog, ActivityLog, SLAConfig
    from crm.email_service import send_transactional_email, render_template

    lead = _get_lead(lead_id)
    agent_user = _get_current_agent(lead)
    sla_config = SLAConfig.get()

    admins = list(User.objects.filter(is_active=True, profile__role='admin').select_related('profile'))
    if not admins:
        logger.warning("No admin users found to escalate lead %s", lead_id)
        return

    for admin in admins:
        idempotency_key = f"{lead_id}:admin_escalation:{admin.email}:{timezone.now().strftime('%Y-%m-%d')}"
        email_log, created = EmailLog.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                'lead': lead,
                'recipient_email': admin.email,
                'recipient_type': EmailLog.RecipientType.ADMIN,
                'template_name': 'admin_escalation',
                'subject': f"[ESCALATION] Overdue lead — {lead.property_title_snapshot}",
                'status': EmailLog.Status.PENDING,
            }
        )
        if not created and email_log.status == EmailLog.Status.SENT:
            continue

        context = {
            'visitor_name': lead.full_name,
            'visitor_email': lead.email,
            'property_title': lead.property_title_snapshot,
            'agent_name': agent_user.get_full_name() if agent_user else 'Unassigned',
            'sla_deadline': lead.sla_deadline.strftime('%d %b %Y, %H:%M UTC'),
            'overdue_since': lead.sla_deadline.strftime('%d %b %Y, %H:%M UTC'),
            'overdue_hours': sla_config.escalation_overdue_hours,
            'crm_lead_url': f"{_site_url()}/crm/leads/{lead.id}/",
        }

        body = render_template('admin_escalation', context)
        lines = body.splitlines()
        subject = email_log.subject
        body_lines = []
        for line in lines:
            if line.startswith('Subject:'):
                subject = line.replace('Subject:', '').strip()
            else:
                body_lines.append(line)
        body_text = '\n'.join(body_lines).strip()

        success, provider_id, error = send_transactional_email(
            recipient_email=admin.email,
            subject=subject,
            body_text=body_text,
        )

        if success:
            email_log.status = EmailLog.Status.SENT
            email_log.provider_message_id = provider_id or ''
            email_log.sent_at = timezone.now()
            email_log.save(update_fields=['status', 'provider_message_id', 'sent_at', 'updated_at'])
        else:
            email_log.status = EmailLog.Status.FAILED
            email_log.retry_count += 1
            email_log.last_error = error or ''
            email_log.save(update_fields=['status', 'retry_count', 'last_error', 'updated_at'])
            raise Exception(f"SendGrid error: {error}")


# ---------------------------------------------------------------------------
# Periodic: sweep overdue leads
# ---------------------------------------------------------------------------

@shared_task
def sweep_overdue_leads():
    """
    Run every 30 minutes via Celery Beat.
    Marks leads and follow-ups as OVERDUE when they've passed their deadline
    without a qualifying contact event.
    """
    from crm.models import Lead, FollowUp, ActivityLog

    now = timezone.now()

    # --- Overdue leads ---
    # A lead is overdue if: sla_deadline < now AND followup_status in (NOT_STARTED, IN_PROGRESS)
    # AND no CALL_LOGGED / EMAIL_SENT / WHATSAPP_LOGGED ActivityLog after the deadline.
    contact_events = {
        ActivityLog.EventType.CALL_LOGGED,
        ActivityLog.EventType.EMAIL_SENT,
        ActivityLog.EventType.WHATSAPP_LOGGED,
    }

    candidate_leads = Lead.objects.filter(
        sla_deadline__lt=now,
        followup_status__in=[Lead.FollowUpStatus.NOT_STARTED, Lead.FollowUpStatus.IN_PROGRESS],
    ).prefetch_related('activity_logs')

    overdue_count = 0
    for lead in candidate_leads:
        # Check if a contact event was logged after sla_deadline
        contacted = lead.activity_logs.filter(
            event_type__in=contact_events,
            created_at__gte=lead.sla_deadline,
        ).exists()

        if not contacted:
            lead.followup_status = Lead.FollowUpStatus.OVERDUE
            lead.save(update_fields=['followup_status', 'updated_at'])

            # Append-only ActivityLog
            try:
                ActivityLog.objects.create(
                    lead=lead,
                    actor=None,
                    event_type=ActivityLog.EventType.OVERDUE_FLAGGED,
                    note=f"SLA deadline {lead.sla_deadline:%d %b %Y %H:%M} UTC passed without contact.",
                )
            except Exception:
                pass  # Log write failure shouldn't block the sweep

            # Update agent's overdue counter
            current_assignment = lead.assignments.filter(is_current=True).first()
            if current_assignment and current_assignment.agent:
                try:
                    profile = current_assignment.agent.profile
                    from django.db.models import F
                    from properties.models import UserProfile
                    UserProfile.objects.filter(pk=profile.pk).update(
                        current_overdue_leads=F('current_overdue_leads') + 1
                    )
                except Exception:
                    pass

            overdue_count += 1

    # --- Overdue follow-ups ---
    FollowUp.objects.filter(
        due_at__lt=now,
        status__in=[FollowUp.Status.NOT_STARTED, FollowUp.Status.IN_PROGRESS],
    ).update(status=FollowUp.Status.OVERDUE)

    logger.info("sweep_overdue_leads: %d leads marked overdue", overdue_count)


# ---------------------------------------------------------------------------
# Periodic: sweep escalations
# ---------------------------------------------------------------------------

@shared_task
def sweep_escalations():
    """
    Run every hour via Celery Beat.
    Escalates leads that are overdue AND have passed the escalation threshold
    without an admin having been notified today.
    """
    from crm.models import Lead, ActivityLog, SLAConfig

    sla_config = SLAConfig.get()
    now = timezone.now()
    from datetime import timedelta
    escalation_cutoff = now - timedelta(hours=sla_config.escalation_overdue_hours)

    overdue_leads = Lead.objects.filter(
        followup_status=Lead.FollowUpStatus.OVERDUE,
        sla_deadline__lt=escalation_cutoff,
    )

    for lead in overdue_leads:
        # Don't escalate if we already escalated within the last 24 hours
        already_escalated = lead.activity_logs.filter(
            event_type=ActivityLog.EventType.ESCALATED,
            created_at__gte=now - timedelta(hours=24),
        ).exists()

        if not already_escalated:
            try:
                ActivityLog.objects.create(
                    lead=lead,
                    actor=None,
                    event_type=ActivityLog.EventType.ESCALATED,
                    note=f"Lead overdue for >{sla_config.escalation_overdue_hours}h. Admin notified.",
                )
            except Exception:
                pass
            send_admin_escalation_email.delay(str(lead.id))

    logger.info("sweep_escalations: processed %d overdue leads", overdue_leads.count())


# ---------------------------------------------------------------------------
# Periodic: compute agent response scores
# ---------------------------------------------------------------------------

@shared_task
def compute_response_scores():
    """
    Run daily at 02:00 UTC via Celery Beat.
    response_score = (leads contacted within SLA in last 30 days) / (total leads assigned in last 30 days)
    """
    from crm.models import Lead, ActivityLog
    from properties.models import UserProfile
    from datetime import timedelta
    from django.db.models import Q, Min, F

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    contact_events = [
        ActivityLog.EventType.CALL_LOGGED,
        ActivityLog.EventType.EMAIL_SENT,
        ActivityLog.EventType.WHATSAPP_LOGGED,
    ]

    agents = UserProfile.objects.filter(role='agent', user__is_active=True).select_related('user')

    for agent_profile in agents:
        # Leads assigned to this agent in the last 30 days, annotated with each lead's
        # earliest contact timestamp (if any) — computed in the DB, not fetched and
        # looped over in Python, so this is 2 aggregate queries per agent regardless
        # of how many leads they have.
        assigned_leads = Lead.objects.filter(
            assignments__agent=agent_profile.user,
            assignments__is_current=True,
            created_at__gte=thirty_days_ago,
        ).annotate(
            first_contact_at=Min(
                'activity_logs__created_at',
                filter=Q(activity_logs__event_type__in=contact_events),
            )
        )
        total = assigned_leads.count()

        if total == 0:
            # No leads → keep existing score to avoid penalising new/inactive agents
            continue

        contacted_within_sla = assigned_leads.filter(
            first_contact_at__isnull=False,
            first_contact_at__lte=F('sla_deadline'),
        ).count()

        score = round(contacted_within_sla / total, 4)
        UserProfile.objects.filter(pk=agent_profile.pk).update(response_score=score)

    logger.info("compute_response_scores: updated scores for %d agents", agents.count())
