import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class LeadSource(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = 'NEW', 'New'
        CONTACTED = 'CONTACTED', 'Contacted'
        VIEWING_SCHEDULED = 'VIEWING_SCHEDULED', 'Viewing Scheduled'
        NEGOTIATION = 'NEGOTIATION', 'Negotiation'
        WON = 'WON', 'Won'
        LOST = 'LOST', 'Lost'
        UNRESPONSIVE = 'UNRESPONSIVE', 'Unresponsive'

    class FollowUpStatus(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Not Started'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        OVERDUE = 'OVERDUE', 'Overdue'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Property context (FK + denormalized snapshot)
    # Named 'related_property' to avoid collision with Python's built-in 'property' decorator.
    related_property = models.ForeignKey(
        'properties.Property',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='leads'
    )
    property_title_snapshot = models.CharField(max_length=200, blank=True)
    property_location_snapshot = models.CharField(max_length=300, blank=True)
    property_url_snapshot = models.URLField(blank=True)

    # Visitor details
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    message = models.TextField()

    # Status
    lead_status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.NEW
    )
    followup_status = models.CharField(
        max_length=20, choices=FollowUpStatus.choices, default=FollowUpStatus.NOT_STARTED
    )

    # Source / UTM
    source = models.ForeignKey(
        LeadSource, on_delete=models.SET_NULL, null=True, blank=True
    )
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_term = models.CharField(max_length=100, blank=True)

    # Spam / dedup
    ip_address_hash = models.CharField(max_length=64, blank=True)
    is_duplicate = models.BooleanField(default=False)
    duplicate_of = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='duplicates'
    )

    # SLA
    sla_deadline = models.DateTimeField()
    consent_given = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'related_property']),
            models.Index(fields=['lead_status']),
            models.Index(fields=['followup_status']),
            models.Index(fields=['sla_deadline']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} — {self.property_title_snapshot}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_overdue(self):
        return (
            self.followup_status == self.FollowUpStatus.OVERDUE
            or (
                self.sla_deadline < timezone.now()
                and self.followup_status in [
                    self.FollowUpStatus.NOT_STARTED,
                    self.FollowUpStatus.IN_PROGRESS,
                ]
            )
        )


class LeadAssignment(models.Model):
    class Reason(models.TextChoices):
        SCORE_BASED = 'SCORE_BASED', 'Score Based'
        ROUND_ROBIN = 'ROUND_ROBIN', 'Round Robin'
        MANUAL = 'MANUAL', 'Manual'
        FALLBACK = 'FALLBACK', 'Fallback (No Agents)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='assignments')
    agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lead_assignments'
    )
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assignments_made'
    )
    assignment_reason = models.CharField(
        max_length=20, choices=Reason.choices, default=Reason.SCORE_BASED
    )
    score_snapshot = models.JSONField(default=dict, blank=True)
    is_current = models.BooleanField(default=True)
    admin_note = models.TextField(blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    unassigned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['lead', 'is_current']),
            models.Index(fields=['agent', 'is_current']),
        ]

    def __str__(self):
        agent_name = self.agent.get_full_name() if self.agent else 'Unassigned'
        return f"{self.lead} → {agent_name} ({'current' if self.is_current else 'past'})"


class ActivityLog(models.Model):
    class EventType(models.TextChoices):
        LEAD_CREATED = 'LEAD_CREATED', 'Lead Created'
        STATUS_CHANGED = 'STATUS_CHANGED', 'Status Changed'
        AGENT_ASSIGNED = 'AGENT_ASSIGNED', 'Agent Assigned'
        AGENT_REASSIGNED = 'AGENT_REASSIGNED', 'Agent Reassigned'
        CALL_LOGGED = 'CALL_LOGGED', 'Call Logged'
        EMAIL_SENT = 'EMAIL_SENT', 'Email Sent'
        WHATSAPP_LOGGED = 'WHATSAPP_LOGGED', 'WhatsApp Logged'
        NOTE_ADDED = 'NOTE_ADDED', 'Note Added'
        FOLLOWUP_SCHEDULED = 'FOLLOWUP_SCHEDULED', 'Follow-Up Scheduled'
        FOLLOWUP_COMPLETED = 'FOLLOWUP_COMPLETED', 'Follow-Up Completed'
        OVERDUE_FLAGGED = 'OVERDUE_FLAGGED', 'Marked Overdue'
        ESCALATED = 'ESCALATED', 'Escalated to Admin'
        DUPLICATE_DETECTED = 'DUPLICATE_DETECTED', 'Duplicate Detected'

    class ContactMethod(models.TextChoices):
        EMAIL = 'EMAIL', 'Email'
        PHONE = 'PHONE', 'Phone'
        WHATSAPP = 'WHATSAPP', 'WhatsApp'
        IN_PERSON = 'IN_PERSON', 'In Person'
        OTHER = 'OTHER', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activity_logs')
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='crm_activities'
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    contact_method = models.CharField(
        max_length=20, choices=ContactMethod.choices, blank=True
    )
    old_value = models.CharField(max_length=100, blank=True)
    new_value = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lead', 'event_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.lead} — {self.get_event_type_display()} at {self.created_at:%Y-%m-%d %H:%M}"

    # Append-only: block updates and deletes at the manager level
    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("ActivityLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("ActivityLog entries cannot be deleted.")


class FollowUp(models.Model):
    class FollowUpType(models.TextChoices):
        CALL = 'CALL', 'Call'
        EMAIL = 'EMAIL', 'Email'
        WHATSAPP = 'WHATSAPP', 'WhatsApp'
        MEETING = 'MEETING', 'Meeting'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Not Started'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        OVERDUE = 'OVERDUE', 'Overdue'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='followups')
    agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='followups'
    )
    due_at = models.DateTimeField()
    followup_type = models.CharField(max_length=20, choices=FollowUpType.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_STARTED
    )
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_followups'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_at']
        indexes = [
            models.Index(fields=['lead', 'status']),
            models.Index(fields=['agent', 'due_at']),
        ]

    def __str__(self):
        return f"Follow-up for {self.lead} on {self.due_at:%Y-%m-%d}"


class EmailLog(models.Model):
    class RecipientType(models.TextChoices):
        VISITOR = 'VISITOR', 'Visitor'
        AGENT = 'AGENT', 'Agent'
        ADMIN = 'ADMIN', 'Admin'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SENT = 'SENT', 'Sent'
        FAILED = 'FAILED', 'Failed'
        BOUNCED = 'BOUNCED', 'Bounced'
        DELIVERED = 'DELIVERED', 'Delivered'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(
        Lead, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='email_logs'
    )
    recipient_email = models.EmailField()
    recipient_type = models.CharField(max_length=10, choices=RecipientType.choices)
    template_name = models.CharField(max_length=100)
    subject = models.CharField(max_length=300)
    provider_message_id = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    retry_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    # Idempotency key format: {lead_id}:{template_name}:{recipient_email}
    idempotency_key = models.CharField(max_length=400, unique=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lead', 'status']),
            models.Index(fields=['idempotency_key']),
        ]

    def __str__(self):
        return f"{self.template_name} → {self.recipient_email} [{self.status}]"


class SLAConfig(models.Model):
    """Singleton model — only one row should exist."""
    first_contact_hours = models.PositiveSmallIntegerField(
        default=2,
        help_text="Hours within which the agent must make first contact"
    )
    escalation_overdue_hours = models.PositiveSmallIntegerField(
        default=24,
        help_text="Hours after SLA deadline before admin is escalated"
    )
    dedup_window_hours = models.PositiveSmallIntegerField(
        default=6,
        help_text="Hours within which a re-submission of the same email+property is treated as a duplicate"
    )
    business_hours_start = models.TimeField(default='08:00')
    business_hours_end = models.TimeField(default='18:00')
    business_days = models.JSONField(
        default=list,
        help_text="ISO weekday numbers: 1=Mon, 7=Sun. Default [1,2,3,4,5]"
    )
    # Assignment weights (stored here for admin editability)
    w1_open_leads = models.FloatField(default=0.35, help_text="Weight for normalised open leads")
    w2_overdue_leads = models.FloatField(default=0.25, help_text="Weight for normalised overdue leads")
    w3_response_score = models.FloatField(default=0.20, help_text="Weight for agent response score")
    w4_location_match = models.FloatField(default=0.12, help_text="Weight for location match")
    w5_specialty_match = models.FloatField(default=0.08, help_text="Weight for specialty match")

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = 'SLA Configuration'
        verbose_name_plural = 'SLA Configuration'

    def __str__(self):
        return f"SLA Config (contact within {self.first_contact_hours}h)"

    def save(self, *args, **kwargs):
        self.pk = 1  # Enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        """Return the singleton config, creating defaults if it doesn't exist."""
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={'business_days': [1, 2, 3, 4, 5]}
        )
        return obj
