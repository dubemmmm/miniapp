from django.contrib import admin
from django.utils.html import format_html
from crm.models import (
    ActivityLog, EmailLog, FollowUp, Lead, LeadAssignment,
    LeadSource, SLAConfig,
)


@admin.register(LeadSource)
class LeadSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        'short_id', 'full_name', 'email', 'property_title_snapshot',
        'current_agent', 'lead_status_badge', 'followup_status_badge',
        'is_overdue_display', 'created_at',
    )
    list_filter = ('lead_status', 'followup_status', 'is_duplicate', 'created_at')
    search_fields = ('email', 'first_name', 'last_name', 'property_title_snapshot')
    readonly_fields = ('id', 'created_at', 'updated_at', 'ip_address_hash', 'duplicate_of')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Visitor', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'message', 'consent_given')
        }),
        ('Property Snapshot', {
            'fields': (
                'related_property', 'property_title_snapshot',
                'property_location_snapshot', 'property_url_snapshot'
            )
        }),
        ('Status', {
            'fields': ('lead_status', 'followup_status', 'sla_deadline', 'closed_at')
        }),
        ('Source / UTM', {
            'classes': ('collapse',),
            'fields': ('source', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_term')
        }),
        ('Deduplication', {
            'classes': ('collapse',),
            'fields': ('is_duplicate', 'duplicate_of', 'ip_address_hash')
        }),
        ('Metadata', {
            'classes': ('collapse',),
            'fields': ('id', 'created_at', 'updated_at')
        }),
    )

    def short_id(self, obj):
        return str(obj.id)[:8].upper()
    short_id.short_description = 'ID'

    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Visitor'

    def current_agent(self, obj):
        assignment = obj.assignments.filter(is_current=True).select_related('agent').first()
        if assignment and assignment.agent:
            return assignment.agent.get_full_name() or assignment.agent.username
        return '—'
    current_agent.short_description = 'Agent'

    STATUS_COLOURS = {
        'NEW': '#3B82F6',
        'CONTACTED': '#8B5CF6',
        'VIEWING_SCHEDULED': '#F59E0B',
        'NEGOTIATION': '#F97316',
        'WON': '#10B981',
        'LOST': '#6B7280',
        'UNRESPONSIVE': '#EF4444',
    }

    def lead_status_badge(self, obj):
        colour = self.STATUS_COLOURS.get(obj.lead_status, '#6B7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_lead_status_display()
        )
    lead_status_badge.short_description = 'Status'

    FOLLOWUP_COLOURS = {
        'NOT_STARTED': '#6B7280',
        'IN_PROGRESS': '#3B82F6',
        'COMPLETED': '#10B981',
        'OVERDUE': '#EF4444',
    }

    def followup_status_badge(self, obj):
        colour = self.FOLLOWUP_COLOURS.get(obj.followup_status, '#6B7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_followup_status_display()
        )
    followup_status_badge.short_description = 'Follow-up'

    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color:#EF4444;font-weight:bold">⚠ Overdue</span>')
        return '—'
    is_overdue_display.short_description = 'SLA'


@admin.register(LeadAssignment)
class LeadAssignmentAdmin(admin.ModelAdmin):
    list_display = ('lead', 'agent', 'assignment_reason', 'is_current', 'assigned_at')
    list_filter = ('assignment_reason', 'is_current')
    readonly_fields = ('id', 'assigned_at', 'score_snapshot')
    search_fields = ('lead__email', 'lead__first_name', 'lead__last_name')
    ordering = ('-assigned_at',)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('lead', 'event_type', 'actor', 'contact_method', 'created_at')
    list_filter = ('event_type', 'contact_method', 'created_at')
    readonly_fields = (
        'id', 'lead', 'actor', 'event_type', 'contact_method',
        'old_value', 'new_value', 'note', 'is_private', 'created_at'
    )
    search_fields = ('lead__email',)
    ordering = ('-created_at',)

    # Append-only: no add, change, or delete in admin
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('lead', 'agent', 'followup_type', 'due_at', 'status')
    list_filter = ('status', 'followup_type')
    search_fields = ('lead__email',)
    ordering = ('due_at',)


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = (
        'template_name', 'recipient_email', 'recipient_type',
        'status_badge', 'retry_count', 'sent_at', 'created_at'
    )
    list_filter = ('status', 'recipient_type', 'template_name')
    readonly_fields = (
        'id', 'idempotency_key', 'provider_message_id', 'created_at', 'updated_at'
    )
    search_fields = ('recipient_email',)
    ordering = ('-created_at',)

    EMAIL_STATUS_COLOURS = {
        'PENDING': '#F59E0B',
        'SENT': '#10B981',
        'FAILED': '#EF4444',
        'BOUNCED': '#F97316',
        'DELIVERED': '#3B82F6',
    }

    def status_badge(self, obj):
        colour = self.EMAIL_STATUS_COLOURS.get(obj.status, '#6B7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(SLAConfig)
class SLAConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'first_contact_hours', 'escalation_overdue_hours', 'updated_at')
    readonly_fields = ('updated_at',)

    fieldsets = (
        ('SLA Timings', {
            'fields': ('first_contact_hours', 'escalation_overdue_hours', 'dedup_window_hours')
        }),
        ('Business Hours', {
            'fields': ('business_hours_start', 'business_hours_end', 'business_days')
        }),
        ('Assignment Weights', {
            'description': 'Weights used in the Weighted Least-Load scoring algorithm.',
            'fields': ('w1_open_leads', 'w2_overdue_leads', 'w3_response_score',
                       'w4_location_match', 'w5_specialty_match')
        }),
        ('Audit', {
            'fields': ('updated_at', 'updated_by')
        }),
    )

    def has_add_permission(self, request):
        return not SLAConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
