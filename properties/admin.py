from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Property, PropertyConfiguration, PropertyImage, PropertyAmenity,
    SharedPropertyList, UserProfile, AirtableSyncLog, EmployeeInvitation,
    PropertyProgress, PropertyProgressImage
)


class PropertyConfigurationInline(admin.TabularInline):
    model = PropertyConfiguration
    extra = 0
    readonly_fields = ['airtable_id', 'last_synced_at']

class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 0
    readonly_fields = ['airtable_id', 'image_preview', 'last_synced_at']
    fields = ['image', 'image_preview', 'alt_text', 'order', 'airtable_id']

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 100px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'

class PropertyAmenityInline(admin.TabularInline):
    model = PropertyAmenity
    extra = 0
    readonly_fields = ['airtable_id', 'last_synced_at']

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'luxury_status', 
        'is_active', 
        'get_configuration_count',
        'get_image_count',
        'airtable_id', 
        'last_synced_at',
        'completion_date'
    ]
    list_filter = ['luxury_status', 'is_active', 'last_synced_at', 'created_at']
    search_fields = ['name', 'address', 'airtable_id', 'slug']
    readonly_fields = [
        'airtable_id', 
        'last_synced_at', 
        'created_at', 
        'updated_at',
        'get_primary_image_preview',
        'get_min_price',
        'get_max_bedrooms'
    ]
    prepopulated_fields = {'slug': ('name',)}
    inlines = [PropertyConfigurationInline, PropertyImageInline, PropertyAmenityInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'address', 'description')
        }),
        ('Location', {
            'fields': ('latitude', 'longitude'),
            'classes': ('wide',)
        }),
        ('Contact Information', {
            'fields': ('contact_name', 'contact_phone')
        }),
        ('Media', {
            'fields': ('brochure', 'thumbnail', 'get_primary_image_preview')
        }),
        ('Status & Classification', {
            'fields': ('is_active', 'luxury_status')
        }),
        ('Property Stats', {
            'fields': ('get_min_price', 'get_max_bedrooms'),
            'classes': ('collapse',)
        }),
        ('Sync Information', {
            'fields': ('airtable_id', 'last_synced_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_configuration_count(self, obj):
        return obj.configurations.count()
    get_configuration_count.short_description = 'Configs'

    def get_image_count(self, obj):
        return obj.images.count()
    get_image_count.short_description = 'Images'

    def get_primary_image_preview(self, obj):
        primary_image = obj.get_primary_image()
        if primary_image and primary_image.image:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 200px;" />',
                primary_image.image.url
            )
        return "No primary image"
    get_primary_image_preview.short_description = 'Primary Image Preview'

@admin.register(PropertyConfiguration)
class PropertyConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        'property', 
        'type', 
        'bedrooms', 
        'bathrooms', 
        'square_footage', 
        'price', 
        'is_available',
        'airtable_id'
    ]
    list_filter = ['is_available', 'bedrooms', 'bathrooms', 'last_synced_at']
    search_fields = ['property__name', 'type', 'airtable_id']
    readonly_fields = ['airtable_id', 'last_synced_at', 'created_at', 'updated_at']
    list_select_related = ['property']

    fieldsets = (
        ('Property Link', {
            'fields': ('property',)
        }),
        ('Configuration Details', {
            'fields': ('type', 'bedrooms', 'bathrooms', 'square_footage', 'price', 'is_available')
        }),
        ('Sync Information', {
            'fields': ('airtable_id', 'last_synced_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = [
        'property', 
        'alt_text', 
        'image_preview', 
        'order', 
        'airtable_id',
        'last_synced_at'
    ]
    list_filter = ['order', 'last_synced_at', 'created_at']
    search_fields = ['property__name', 'alt_text', 'airtable_id']
    readonly_fields = [
        'airtable_id', 
        'attachment_index',
        'original_record_id',
        'last_synced_at', 
        'created_at', 
        'updated_at',
        'image_preview_large'
    ]
    list_select_related = ['property']
    ordering = ['property', 'order']

    fieldsets = (
        ('Property Link', {
            'fields': ('property',)
        }),
        ('Image Details', {
            'fields': ('image', 'image_preview_large', 'alt_text', 'order')
        }),
        ('Airtable Sync Details', {
            'fields': ('airtable_id', 'attachment_index', 'original_record_id'),
            'classes': ('collapse',)
        }),
        ('Sync Information', {
            'fields': ('last_synced_at',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 100px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'

    def image_preview_large(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 200px; max-width: 300px;" />',
                obj.image.url
            )
        return "No image"
    image_preview_large.short_description = 'Large Preview'

@admin.register(PropertyAmenity)
class PropertyAmenityAdmin(admin.ModelAdmin):
    list_display = [
        'property', 
        'name', 
        'description',
        'icon',
        'airtable_id',
        'last_synced_at'
    ]
    list_filter = ['name', 'last_synced_at', 'created_at']
    search_fields = ['property__name', 'name', 'airtable_id']
    readonly_fields = ['airtable_id', 'last_synced_at', 'created_at', 'updated_at']
    list_select_related = ['property']

    fieldsets = (
        ('Property Link', {
            'fields': ('property',)
        }),
        ('Amenity Details', {
            'fields': ('name', 'description', 'icon')
        }),
        ('Sync Information', {
            'fields': ('airtable_id', 'last_synced_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


# If you have the AirtableSyncLog model, add this admin too
try:
    from .models import AirtableSyncLog
    
    @admin.register(AirtableSyncLog)
    class AirtableSyncLogAdmin(admin.ModelAdmin):
        list_display = [
            'sync_type', 
            'status', 
            'started_at', 
            'duration_display', 
            'total_records_processed', 
            'errors_count',
            'dry_run'
        ]
        list_filter = ['sync_type', 'status', 'dry_run', 'started_at']
        readonly_fields = [
            'started_at', 
            'completed_at',
            'duration_display', 
            'total_records_processed',
            'properties_processed',
            'configurations_processed',
            'images_processed',
            'amenities_processed'
        ]
        search_fields = ['notes']
        
        fieldsets = (
            ('Sync Details', {
                'fields': ('sync_type', 'status', 'dry_run', 'files_downloaded')
            }),
            ('Timing', {
                'fields': ('started_at', 'completed_at', 'duration_display')
            }),
            ('Statistics', {
                'fields': (
                    'total_records_processed',
                    'properties_processed',
                    'configurations_processed', 
                    'images_processed',
                    'amenities_processed'
                )
            }),
            ('Errors', {
                'fields': ('errors_count', 'error_details'),
                'classes': ('collapse',)
            }),
            ('Notes', {
                'fields': ('notes',),
                'classes': ('collapse',)
            })
        )

        def duration_display(self, obj):
            duration = obj.duration()
            if duration:
                total_seconds = int(duration.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                if hours:
                    return f"{hours}h {minutes}m {seconds}s"
                elif minutes:
                    return f"{minutes}m {seconds}s"
                else:
                    return f"{seconds}s"
            return "In progress..."
        duration_display.short_description = 'Duration'

        def total_records_processed(self, obj):
            return obj.total_records_processed()
        total_records_processed.short_description = 'Total Records'

except ImportError:
    # AirtableSyncLog model doesn't exist yet
    pass


@admin.register(SharedPropertyList)
class SharedPropertyListAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at", "expires_at", "is_active", "view_count")
    list_filter = ("is_active", "created_at", "expires_at")
    search_fields = ("name", "token", "created_by__username")
    filter_horizontal = ("properties",)
    readonly_fields = ("token", "created_at", "view_count")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "is_employee", "can_share_properties", "created_at")
    list_filter = ("role", "is_employee", "can_share_properties")
    search_fields = ("user__username", "user__first_name", "user__last_name", "phone")
    readonly_fields = ("created_at",)


@admin.register(EmployeeInvitation)
class EmployeeInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "status_badge",
        "use_count_display",
        "created_by",
        "used_by",
        "created_at",
        "expires_at"
    )
    list_filter = ("is_used", "created_at", "expires_at")
    search_fields = ("code", "created_by__username", "used_by__username", "notes")
    readonly_fields = ("code", "created_at", "used_by", "used_at", "use_count")

    fieldsets = (
        ("Invitation Code", {
            "fields": ("code",)
        }),
        ("Usage", {
            "fields": ("max_uses", "use_count", "is_used", "used_by", "used_at")
        }),
        ("Validity", {
            "fields": ("created_by", "created_at", "expires_at")
        }),
        ("Notes", {
            "fields": ("notes",),
            "classes": ("collapse",)
        })
    )

    actions = ["generate_invitation_codes"]

    def save_model(self, request, obj, form, change):
        """Auto-generate code if creating new invitation"""
        if not change:  # Only when creating new
            if not obj.code:
                obj.code = EmployeeInvitation.generate_code()
            if not obj.created_by:
                obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def status_badge(self, obj):
        if obj.is_valid():
            color = "green"
            status = "Active"
        elif obj.is_used or obj.use_count >= obj.max_uses:
            color = "red"
            status = "Used"
        elif obj.expires_at and timezone.now() > obj.expires_at:
            color = "orange"
            status = "Expired"
        else:
            color = "gray"
            status = "Inactive"

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            status
        )
    status_badge.short_description = "Status"

    def use_count_display(self, obj):
        return f"{obj.use_count} / {obj.max_uses}"
    use_count_display.short_description = "Uses"

    def generate_invitation_codes(self, request, queryset):
        """Admin action to generate new invitation codes"""
        from .models import EmployeeInvitation

        # Generate 5 new codes
        count = 5
        created_codes = []

        for _ in range(count):
            code = EmployeeInvitation.generate_code()
            invitation = EmployeeInvitation.objects.create(
                code=code,
                created_by=request.user,
                max_uses=1
            )
            created_codes.append(invitation.code)

        self.message_user(
            request,
            f"Successfully generated {count} invitation codes: {', '.join(created_codes)}"
        )

    generate_invitation_codes.short_description = "Generate 5 new invitation codes"


class PropertyProgressImageInline(admin.TabularInline):
    model = PropertyProgressImage
    extra = 0
    readonly_fields = ['airtable_id', 'image_preview', 'last_synced_at', 'image_url_hash']
    fields = ['image', 'image_preview', 'caption', 'order', 'airtable_id']

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 100px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(PropertyProgress)
class PropertyProgressAdmin(admin.ModelAdmin):
    list_display = [
        'property',
        'stage',
        'progress_percentage',
        'update_date',
        'is_latest',
        'uploaded_by',
        'image_count',
        'airtable_id',
        'last_synced_at'
    ]
    list_filter = ['stage', 'is_latest', 'update_date', 'last_synced_at']
    search_fields = ['property__name', 'description', 'uploaded_by', 'airtable_id']
    readonly_fields = [
        'airtable_id',
        'last_synced_at',
        'created_at',
        'updated_at',
        'image_count'
    ]
    list_select_related = ['property']
    date_hierarchy = 'update_date'
    inlines = [PropertyProgressImageInline]

    fieldsets = (
        ('Property Link', {
            'fields': ('property',)
        }),
        ('Progress Details', {
            'fields': ('stage', 'progress_percentage', 'update_date', 'is_latest')
        }),
        ('Description & Uploader', {
            'fields': ('description', 'uploaded_by')
        }),
        ('Images Data (from Airtable)', {
            'fields': ('images_data',),
            'classes': ('collapse',)
        }),
        ('Sync Information', {
            'fields': ('airtable_id', 'last_synced_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def image_count(self, obj):
        return obj.images.count()
    image_count.short_description = 'Images'


@admin.register(PropertyProgressImage)
class PropertyProgressImageAdmin(admin.ModelAdmin):
    list_display = [
        'progress_update',
        'image_preview',
        'caption',
        'order',
        'airtable_id',
        'last_synced_at'
    ]
    list_filter = ['order', 'last_synced_at', 'created_at']
    search_fields = ['progress_update__property__name', 'caption', 'airtable_id']
    readonly_fields = [
        'airtable_id',
        'attachment_index',
        'image_url_hash',
        'last_synced_at',
        'created_at',
        'updated_at',
        'image_preview_large'
    ]
    list_select_related = ['progress_update', 'progress_update__property']
    ordering = ['progress_update', 'order']

    fieldsets = (
        ('Progress Update Link', {
            'fields': ('progress_update',)
        }),
        ('Image Details', {
            'fields': ('image', 'image_preview_large', 'caption', 'order')
        }),
        ('Airtable Sync Details', {
            'fields': ('airtable_id', 'attachment_index', 'image_url_hash'),
            'classes': ('collapse',)
        }),
        ('Sync Information', {
            'fields': ('last_synced_at',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 100px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'

    def image_preview_large(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 200px; max-width: 300px;" />',
                obj.image.url
            )
        return "No image"
    image_preview_large.short_description = 'Large Preview'
