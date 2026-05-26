import hashlib
import json
import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from crm.assignment import assign_agent
from crm.forms import EnquiryForm
from crm.mixins import AdminOnlyMixin, CRMAccessMixin
from crm.models import (
    ActivityLog, EmailLog, FollowUp, Lead, LeadAssignment, SLAConfig,
)
from crm.utils import compute_sla_deadline, get_client_ip
from properties.models import Property, UserProfile

logger = logging.getLogger(__name__)


def _safe_enqueue(task, *args):
    """Best-effort Celery enqueue for fire-and-forget side effects.

    Email/notification tasks are dispatched from ``transaction.on_commit`` after
    the DB write is already committed. If the broker (Redis) is unreachable we
    must not let that turn a successful enquiry into a 500 — log a warning and
    move on. Run a Celery worker against a live broker to actually deliver these.
    """
    try:
        task.delay(*args)
    except Exception:
        logger.warning(
            "Could not enqueue Celery task %s (broker unavailable?); the DB "
            "change is committed but this async side effect was skipped.",
            getattr(task, 'name', repr(task)),
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Enquiry form submission (public endpoint)
# ---------------------------------------------------------------------------

def enquiry_submit(request, property_pk):
    """
    POST-only view. Handles the property enquiry form submission.
    Returns JSON so the frontend Fetch handler can respond in-page.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    prop = get_object_or_404(Property, pk=property_pk, is_active=True)

    form = EnquiryForm(request.POST)

    # Silent honeypot discard — return success so bots don't know
    if request.POST.get('website'):
        return JsonResponse({'success': True})

    # Basic rate limiting via session counter (lightweight, no extra package needed)
    rate_key = 'enquiry_rate'
    rate_window_key = 'enquiry_rate_window'
    now_ts = timezone.now().timestamp()
    window_start = request.session.get(rate_window_key, now_ts)
    rate_count = request.session.get(rate_key, 0)

    if now_ts - window_start > 600:  # 10-minute window
        request.session[rate_key] = 0
        request.session[rate_window_key] = now_ts
        rate_count = 0

    if rate_count >= 3:
        return JsonResponse(
            {'error': 'Too many submissions. Please wait a few minutes and try again.'},
            status=429
        )

    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)

    data = form.cleaned_data
    ip = get_client_ip(request)
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()

    sla_config = SLAConfig.get()
    dedup_hours = sla_config.dedup_window_hours

    # --- Deduplication check ---
    from datetime import timedelta
    dedup_cutoff = timezone.now() - timedelta(hours=dedup_hours)
    existing_lead = Lead.objects.filter(
        email=data['email'],
        related_property=prop,
        is_duplicate=False,
        created_at__gte=dedup_cutoff,
    ).first()

    if existing_lead:
        # Mark this submission as a duplicate and re-send confirmation
        Lead.objects.create(
            related_property=prop,
            property_title_snapshot=existing_lead.property_title_snapshot,
            property_location_snapshot=existing_lead.property_location_snapshot,
            property_url_snapshot=existing_lead.property_url_snapshot,
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email'],
            phone=data.get('phone', ''),
            message=data['message'],
            ip_address_hash=ip_hash,
            is_duplicate=True,
            duplicate_of=existing_lead,
            sla_deadline=existing_lead.sla_deadline,
            consent_given=data.get('consent', False),
            lead_status=Lead.Status.NEW,
            followup_status=Lead.FollowUpStatus.NOT_STARTED,
        )
        # Re-send confirmation using existing lead's agent
        from crm.tasks import send_visitor_confirmation
        transaction.on_commit(lambda: _safe_enqueue(send_visitor_confirmation, str(existing_lead.id)))
        _increment_rate(request)
        return JsonResponse({'success': True})

    # --- Create Lead + Assignment (atomic) ---
    sla_deadline = compute_sla_deadline(timezone.now(), sla_config)

    with transaction.atomic():
        # Build property URL snapshot
        try:
            prop_url = request.build_absolute_uri(f'/property/{prop.pk}/')
        except Exception:
            prop_url = ''

        lead = Lead.objects.create(
            related_property=prop,
            property_title_snapshot=prop.name,
            property_location_snapshot=prop.address,
            property_url_snapshot=prop_url,
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email'],
            phone=data.get('phone', ''),
            message=data['message'],
            ip_address_hash=ip_hash,
            sla_deadline=sla_deadline,
            consent_given=data.get('consent', False),
            lead_status=Lead.Status.NEW,
            followup_status=Lead.FollowUpStatus.NOT_STARTED,
            utm_source=request.session.get('utm_source', ''),
            utm_medium=request.session.get('utm_medium', ''),
            utm_campaign=request.session.get('utm_campaign', ''),
            utm_term=request.session.get('utm_term', ''),
        )

        ActivityLog.objects.create(
            lead=lead,
            actor=None,
            event_type=ActivityLog.EventType.LEAD_CREATED,
            note=f"Lead created from property detail page for {prop.name}",
        )

        # Assign agent (row-locked inside assign_agent)
        agent_profile, score_snapshot, reason = assign_agent(lead)

        agent_user = agent_profile.user if agent_profile else None

        LeadAssignment.objects.create(
            lead=lead,
            agent=agent_user,
            assigned_by=None,
            assignment_reason=reason,
            score_snapshot=score_snapshot,
            is_current=True,
        )

        if agent_profile:
            UserProfile.objects.filter(pk=agent_profile.pk).update(
                current_open_leads=agent_profile.current_open_leads + 1,
                total_leads_assigned=agent_profile.total_leads_assigned + 1,
                last_assigned_at=timezone.now(),
            )

        ActivityLog.objects.create(
            lead=lead,
            actor=None,
            event_type=ActivityLog.EventType.AGENT_ASSIGNED,
            new_value=agent_user.get_full_name() if agent_user else 'Unassigned',
            note=f"Agent assigned via {reason}",
        )

        # Enqueue emails after the transaction commits
        from crm.tasks import send_visitor_confirmation, send_agent_notification
        lead_id = str(lead.id)
        transaction.on_commit(lambda: _safe_enqueue(send_visitor_confirmation, lead_id))
        transaction.on_commit(lambda: _safe_enqueue(send_agent_notification, lead_id))

    _increment_rate(request)
    return JsonResponse({'success': True})


def _increment_rate(request):
    request.session['enquiry_rate'] = request.session.get('enquiry_rate', 0) + 1


# ---------------------------------------------------------------------------
# CRM: Leads List
# ---------------------------------------------------------------------------

class LeadsListView(CRMAccessMixin, TemplateView):
    template_name = 'crm/leads_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        profile = getattr(user, 'profile', None)

        qs = Lead.objects.select_related('related_property').prefetch_related('assignments__agent')

        # Agents only see their own leads
        if profile and profile.role == 'agent':
            qs = qs.filter(assignments__agent=user, assignments__is_current=True)

        # Filters
        params = self.request.GET
        if params.get('status'):
            qs = qs.filter(lead_status=params['status'])
        if params.get('followup_status'):
            qs = qs.filter(followup_status=params['followup_status'])
        if params.get('property_id'):
            qs = qs.filter(related_property_id=params['property_id'])
        if params.get('agent_id'):
            qs = qs.filter(assignments__agent_id=params['agent_id'], assignments__is_current=True)
        if params.get('date_from'):
            qs = qs.filter(created_at__date__gte=params['date_from'])
        if params.get('date_to'):
            qs = qs.filter(created_at__date__lte=params['date_to'])
        if params.get('overdue_only') == '1':
            qs = qs.filter(followup_status=Lead.FollowUpStatus.OVERDUE)

        qs = qs.distinct().order_by('-created_at')

        paginator = Paginator(qs, 25)
        page = self.request.GET.get('page', 1)
        leads_page = paginator.get_page(page)

        # Annotate each lead with current agent name
        for lead in leads_page:
            current = lead.assignments.filter(is_current=True).first()
            lead.current_agent = current.agent if current else None

        # KPI counts (unfiltered, scoped to what the user can see)
        base_qs = Lead.objects.all()
        if profile and profile.role == 'agent':
            base_qs = base_qs.filter(assignments__agent=user, assignments__is_current=True)
        ctx['new_count'] = base_qs.filter(lead_status=Lead.Status.NEW).count()
        ctx['overdue_count'] = base_qs.filter(followup_status=Lead.FollowUpStatus.OVERDUE).count()
        ctx['won_count'] = base_qs.filter(lead_status=Lead.Status.WON).count()

        ctx['leads'] = leads_page
        ctx['paginator'] = paginator
        ctx['properties'] = Property.objects.filter(is_active=True).values('id', 'name')
        ctx['agents'] = UserProfile.objects.filter(role='agent', user__is_active=True).select_related('user')
        ctx['lead_statuses'] = Lead.Status.choices
        ctx['followup_statuses'] = Lead.FollowUpStatus.choices
        ctx['params'] = params
        ctx['is_admin'] = profile and profile.role == 'admin'
        ctx['has_filters'] = any([
            params.get('search'), params.get('status'), params.get('followup_status'),
            params.get('agent_id'), params.get('date_from'), params.get('date_to'),
            params.get('overdue_only'),
        ])
        return ctx


# ---------------------------------------------------------------------------
# CRM: Lead Detail
# ---------------------------------------------------------------------------

class LeadDetailView(CRMAccessMixin, DetailView):
    model = Lead
    template_name = 'crm/lead_detail.html'
    context_object_name = 'lead'

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, 'profile', None)
        qs = Lead.objects.select_related('related_property')
        if profile and profile.role == 'agent':
            qs = qs.filter(assignments__agent=user, assignments__is_current=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lead = self.object
        profile = getattr(self.request.user, 'profile', None)

        ctx['assignments'] = lead.assignments.select_related('agent', 'assigned_by').order_by('-assigned_at')
        ctx['current_assignment'] = lead.assignments.filter(is_current=True).select_related('agent').first()
        ctx['activity_logs'] = lead.activity_logs.select_related('actor').order_by('-created_at')
        ctx['followups'] = lead.followups.select_related('agent').order_by('due_at')
        ctx['email_logs'] = lead.email_logs.order_by('-created_at')
        ctx['lead_statuses'] = Lead.Status.choices
        ctx['is_admin'] = profile and profile.role == 'admin'
        ctx['agents'] = UserProfile.objects.filter(
            role='agent', user__is_active=True, is_available=True
        ).select_related('user')
        ctx['contact_methods'] = ActivityLog.ContactMethod.choices
        ctx['followup_types'] = FollowUp.FollowUpType.choices
        return ctx


# ---------------------------------------------------------------------------
# CRM: AJAX — Update Lead Status
# ---------------------------------------------------------------------------

class UpdateLeadStatusView(CRMAccessMixin, View):
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk)
        profile = getattr(request.user, 'profile', None)

        # Agent can only update their own leads
        if profile and profile.role == 'agent':
            if not lead.assignments.filter(agent=request.user, is_current=True).exists():
                return JsonResponse({'error': 'Permission denied'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        new_status = body.get('status')
        if new_status not in dict(Lead.Status.choices):
            return JsonResponse({'error': 'Invalid status'}, status=400)

        old_status = lead.lead_status
        lead.lead_status = new_status

        # Mark closed_at for terminal statuses
        if new_status in (Lead.Status.WON, Lead.Status.LOST, Lead.Status.UNRESPONSIVE):
            lead.closed_at = timezone.now()
            lead.followup_status = Lead.FollowUpStatus.COMPLETED
            # Decrement agent's open leads counter
            assignment = lead.assignments.filter(is_current=True).first()
            if assignment and assignment.agent:
                UserProfile.objects.filter(user=assignment.agent).update(
                    current_open_leads=max(0, assignment.agent.profile.current_open_leads - 1)
                )
                if new_status == Lead.Status.WON:
                    UserProfile.objects.filter(user=assignment.agent).update(
                        total_leads_won=assignment.agent.profile.total_leads_won + 1
                    )

        lead.save()

        ActivityLog.objects.create(
            lead=lead,
            actor=request.user,
            event_type=ActivityLog.EventType.STATUS_CHANGED,
            old_value=old_status,
            new_value=new_status,
        )

        return JsonResponse({'success': True, 'new_status': new_status})


# ---------------------------------------------------------------------------
# CRM: AJAX — Reassign Lead
# ---------------------------------------------------------------------------

class ReassignLeadView(AdminOnlyMixin, View):
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        agent_user_id = body.get('agent_id')
        admin_note = body.get('note', '')

        if not agent_user_id:
            return JsonResponse({'error': 'agent_id required'}, status=400)

        new_agent = get_object_or_404(User, pk=agent_user_id, is_active=True)

        with transaction.atomic():
            # Supersede current assignment
            now = timezone.now()
            old_assignment = lead.assignments.filter(is_current=True).first()
            if old_assignment:
                # Adjust old agent's counters
                if old_assignment.agent:
                    UserProfile.objects.filter(user=old_assignment.agent).update(
                        current_open_leads=max(0, old_assignment.agent.profile.current_open_leads - 1)
                    )
                old_assignment.is_current = False
                old_assignment.unassigned_at = now
                old_assignment.save(update_fields=['is_current', 'unassigned_at'])

            LeadAssignment.objects.create(
                lead=lead,
                agent=new_agent,
                assigned_by=request.user,
                assignment_reason=LeadAssignment.Reason.MANUAL,
                score_snapshot={},
                is_current=True,
                admin_note=admin_note,
            )

            # Update new agent's counters
            UserProfile.objects.filter(user=new_agent).update(
                current_open_leads=new_agent.profile.current_open_leads + 1,
                total_leads_assigned=new_agent.profile.total_leads_assigned + 1,
                last_assigned_at=now,
            )

            ActivityLog.objects.create(
                lead=lead,
                actor=request.user,
                event_type=ActivityLog.EventType.AGENT_REASSIGNED,
                old_value=old_assignment.agent.get_full_name() if old_assignment and old_assignment.agent else 'Unassigned',
                new_value=new_agent.get_full_name(),
                note=admin_note,
            )

        # Notify new agent
        from crm.tasks import send_agent_notification
        transaction.on_commit(lambda: _safe_enqueue(send_agent_notification, str(lead.id)))

        return JsonResponse({'success': True})


# ---------------------------------------------------------------------------
# CRM: AJAX — Log Activity
# ---------------------------------------------------------------------------

class LogActivityView(CRMAccessMixin, View):
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk)
        profile = getattr(request.user, 'profile', None)

        # Agents can only log against their own leads
        if profile and profile.role == 'agent':
            if not lead.assignments.filter(agent=request.user, is_current=True).exists():
                return JsonResponse({'error': 'Permission denied'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        event_type = body.get('event_type')
        contact_method = body.get('contact_method', '')
        note = body.get('note', '')
        is_private = body.get('is_private', False)

        valid_events = [e[0] for e in ActivityLog.EventType.choices]
        if event_type not in valid_events:
            return JsonResponse({'error': 'Invalid event_type'}, status=400)

        ActivityLog.objects.create(
            lead=lead,
            actor=request.user,
            event_type=event_type,
            contact_method=contact_method,
            note=note,
            is_private=is_private,
        )

        # If a contact event, move followup_status forward if it was NOT_STARTED
        contact_events = {
            ActivityLog.EventType.CALL_LOGGED,
            ActivityLog.EventType.EMAIL_SENT,
            ActivityLog.EventType.WHATSAPP_LOGGED,
        }
        if event_type in contact_events and lead.followup_status == Lead.FollowUpStatus.NOT_STARTED:
            lead.followup_status = Lead.FollowUpStatus.IN_PROGRESS
            lead.save(update_fields=['followup_status', 'updated_at'])

        return JsonResponse({'success': True})


# ---------------------------------------------------------------------------
# CRM: AJAX — Add Follow-Up
# ---------------------------------------------------------------------------

class AddFollowUpView(CRMAccessMixin, View):
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        due_at_str = body.get('due_at')
        followup_type = body.get('followup_type', FollowUp.FollowUpType.CALL)
        notes = body.get('notes', '')

        if not due_at_str:
            return JsonResponse({'error': 'due_at is required'}, status=400)

        from django.utils.dateparse import parse_datetime
        due_at = parse_datetime(due_at_str)
        if not due_at:
            return JsonResponse({'error': 'Invalid due_at format. Use ISO 8601.'}, status=400)
        if timezone.is_naive(due_at):
            due_at = timezone.make_aware(due_at)

        # Default to the current agent for this lead
        assignment = lead.assignments.filter(is_current=True).first()
        agent_user = assignment.agent if assignment else None

        followup = FollowUp.objects.create(
            lead=lead,
            agent=agent_user,
            due_at=due_at,
            followup_type=followup_type,
            notes=notes,
            created_by=request.user,
        )

        ActivityLog.objects.create(
            lead=lead,
            actor=request.user,
            event_type=ActivityLog.EventType.FOLLOWUP_SCHEDULED,
            note=f"{followup.get_followup_type_display()} scheduled for {due_at.strftime('%d %b %Y %H:%M')} UTC",
        )

        return JsonResponse({'success': True, 'followup_id': str(followup.id)})


# ---------------------------------------------------------------------------
# CRM: Agent Workload View
# ---------------------------------------------------------------------------

class AgentWorkloadView(AdminOnlyMixin, TemplateView):
    template_name = 'crm/agent_workload.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        agents = UserProfile.objects.filter(
            role='agent', user__is_active=True
        ).select_related('user').order_by('-current_open_leads')

        ctx['agents'] = agents
        ctx['is_admin'] = True
        return ctx


# ---------------------------------------------------------------------------
# CRM: Admin Settings
# ---------------------------------------------------------------------------

class CRMSettingsView(AdminOnlyMixin, TemplateView):
    template_name = 'crm/settings.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sla = SLAConfig.get()
        ctx['sla_config'] = sla
        ctx['agents'] = UserProfile.objects.filter(
            role='agent'
        ).select_related('user').order_by('user__first_name')
        ctx['tab_list'] = [
            ('sla', 'SLA & Dedup'),
            ('weights', 'Assignment Weights'),
            ('agents', 'Agents'),
        ]
        ctx['weight_fields'] = [
            ('w1', 'w1 — Open leads (penalise load)', sla.w1_open_leads),
            ('w2', 'w2 — Overdue leads (penalise load)', sla.w2_overdue_leads),
            ('w3', 'w3 — Response score (reward quality)', sla.w3_response_score),
            ('w4', 'w4 — Location match (reward relevance)', sla.w4_location_match),
            ('w5', 'w5 — Specialty match (reward relevance)', sla.w5_specialty_match),
        ]
        ctx['is_admin'] = True
        return ctx

    def post(self, request, *args, **kwargs):
        sla_config = SLAConfig.get()
        section = request.POST.get('section')

        if section == 'sla':
            sla_config.first_contact_hours = int(request.POST.get('first_contact_hours', 2))
            sla_config.escalation_overdue_hours = int(request.POST.get('escalation_overdue_hours', 24))
            sla_config.dedup_window_hours = int(request.POST.get('dedup_window_hours', 6))
            sla_config.updated_by = request.user
            sla_config.save()

        elif section == 'weights':
            try:
                sla_config.w1_open_leads = float(request.POST.get('w1', 0.35))
                sla_config.w2_overdue_leads = float(request.POST.get('w2', 0.25))
                sla_config.w3_response_score = float(request.POST.get('w3', 0.20))
                sla_config.w4_location_match = float(request.POST.get('w4', 0.12))
                sla_config.w5_specialty_match = float(request.POST.get('w5', 0.08))
                sla_config.updated_by = request.user
                sla_config.save()
            except (ValueError, TypeError):
                pass

        return redirect('crm:settings')


# ---------------------------------------------------------------------------
# CRM: Toggle Agent Availability (agent self-service)
# ---------------------------------------------------------------------------

class ToggleAvailabilityView(CRMAccessMixin, View):
    def post(self, request):
        profile = getattr(request.user, 'profile', None)
        if not profile or profile.role != 'agent':
            return JsonResponse({'error': 'Permission denied'}, status=403)
        profile.is_available = not profile.is_available
        profile.save(update_fields=['is_available'])
        return JsonResponse({'success': True, 'is_available': profile.is_available})
