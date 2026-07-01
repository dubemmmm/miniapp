from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from .location_utils import LOCATION_CHOICES, extract_location

def property_image_path(instance, filename):
    """Generate upload path for property images"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return f"property_images/{instance.property.slug}/{filename}"
def brochure_path(instance, filename):
    """Generate upload path for brochures"""
    ext = filename.split('.')[-1]
    filename = f"brochure.{ext}"
    return f"brochures/{instance.slug}/{filename}"

def property_thumbnail_path(instance, filename):
    """Generate upload path for Property thumbnail"""
    return f"property_thumbnails/{instance.slug}/{filename}"

# Create your models here.
class Property(models.Model):
    LUXURY_CHOICES = (
        ('luxurious', 'Luxurious'),
        ('non_luxurious', 'Non-Luxurious'),
    )
    
    # Airtable tracking
    airtable_id = models.CharField(max_length=50, unique=True, blank=True, null=True, 
                                   help_text="Airtable record ID for sync purposes")
    
    # Core fields
    name = models.CharField(max_length=200, default=0)
    slug = models.SlugField(unique=True, blank=True)
    address = models.TextField(default='lekki')
    location = models.CharField(
        max_length=50,
        choices=LOCATION_CHOICES,
        blank=True,
        db_index=True,
        help_text="Location group used for filtering. Leave blank to auto-derive from the address."
    )
    description = models.TextField(default='house')
    latitude = models.DecimalField(
        max_digits=20,
        decimal_places=15,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
        null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=20, 
        decimal_places=15,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        null=True, blank=True
    )
    contact_name = models.CharField(max_length=100, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    brochure = models.FileField(upload_to=brochure_path, blank=True, null=True)
    thumbnail = models.ImageField(upload_to=property_thumbnail_path, blank=True, null=True)
    
    # Status fields
    is_active = models.BooleanField(default=True)
    luxury_status = models.CharField(
        max_length=20,
        choices=LUXURY_CHOICES,
        default='non_luxurious',
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True,
                                          help_text="Last time this was synced from Airtable")
    completion_date = models.DateField(null=True, blank=True, db_index=True)  # New field

    class Meta:
        verbose_name_plural = "Properties"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['airtable_id']),
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
            models.Index(fields=['luxury_status']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        # Auto-derive location from the address only when it hasn't been set
        # manually, so an explicit choice is never overwritten.
        if not self.location:
            self.location = extract_location(self.address)
        super().save(*args, **kwargs)

    def get_min_price(self):
        """Get minimum price from configurations"""
        configs = self.configurations.filter(price__isnull=False)
        if configs:
            return min(config.price for config in configs if config.price)
        return None

    def get_max_bedrooms(self):
        """Get maximum bedrooms from configurations"""
        configs = self.configurations.all()
        if configs:
            return max(config.bedrooms for config in configs)
        return 0

    def get_primary_image(self):
        """Get the first image (order 0) or first available image"""
        return self.images.order_by('order').first()

    def get_available_configurations(self):
        """Get only available configurations"""
        return self.configurations.filter(is_available=True)
    
class PropertyConfiguration(models.Model):
    # Airtable tracking
    airtable_id = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                   help_text="Airtable record ID for sync purposes")
    
    # Relationships
    property = models.ForeignKey(
        Property, 
        on_delete=models.CASCADE, 
        related_name='configurations'
    )
    
    # Core fields
    type = models.CharField(max_length=100)  # e.g., "Studio", "1BR", "2BR"
    bedrooms = models.PositiveIntegerField(default=0)
    bathrooms = models.PositiveIntegerField(default=1)
    square_footage = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.property.name} - {self.type}"

    class Meta:
        ordering = ['bedrooms', 'price']
        indexes = [
            models.Index(fields=['airtable_id']),
            models.Index(fields=['property', 'is_available']),
            models.Index(fields=['bedrooms']),
            models.Index(fields=['price']),
        ]
        # Ensure unique combinations
        unique_together = [['property', 'type']]
        
class PropertyImage(models.Model):
    # Airtable tracking
    airtable_id = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                   help_text="Airtable record ID for sync purposes")
    
    # Relationships
    property = models.ForeignKey(
        Property, 
        on_delete=models.CASCADE, 
        related_name='images'
    )
    
    # Core fields
    image = models.ImageField(upload_to=property_image_path, null=False, blank=False)
    alt_text = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    
    # Additional Airtable sync fields
    attachment_index = models.PositiveIntegerField(default=0, 
                                                   help_text="Index of attachment within Airtable record")
    original_record_id = models.CharField(max_length=50, blank=True,
                                          help_text="Original Airtable record ID before splitting")
    image_url_hash = models.CharField(max_length=64, blank=True, 
                                      help_text="SHA256 hash of image URL to detect changes")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order']
        indexes = [
            models.Index(fields=['airtable_id']),
            models.Index(fields=['property', 'order']),
            models.Index(fields=['original_record_id']),
        ]

    def __str__(self):
        return f"{self.property.name} - Image {self.order}"
    
class PropertyAmenity(models.Model):
    # Airtable tracking
    airtable_id = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                   help_text="Airtable record ID for sync purposes")
    
    # Relationships
    property = models.ForeignKey(
        Property, 
        on_delete=models.CASCADE, 
        related_name='amenities'
    )
    
    # Core fields
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, help_text="Optional amenity description")
    icon = models.CharField(max_length=50, blank=True, help_text="Icon class or name")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Property Amenities"
        indexes = [
            models.Index(fields=['airtable_id']),
            models.Index(fields=['property']),
            models.Index(fields=['name']),
        ]
        # Ensure unique combinations
        unique_together = [['property', 'name']]

    def __str__(self):
        return f"{self.property.name} - {self.name}"


# Additional model for tracking sync status
class AirtableSyncLog(models.Model):
    SYNC_TYPES = (
        ('full', 'Full Sync'),
        ('properties', 'Properties Only'),
        ('configurations', 'Configurations Only'),
        ('images', 'Images Only'),
        ('amenities', 'Amenities Only'),
    )
    
    STATUS_CHOICES = (
        ('started', 'Started'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success'),
    )
    
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPES, default='full')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='started')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    properties_processed = models.PositiveIntegerField(default=0)
    configurations_processed = models.PositiveIntegerField(default=0)
    images_processed = models.PositiveIntegerField(default=0)
    amenities_processed = models.PositiveIntegerField(default=0)
    
    # Error tracking
    errors_count = models.PositiveIntegerField(default=0)
    error_details = models.JSONField(default=list, blank=True)
    
    # Additional info
    notes = models.TextField(blank=True)
    dry_run = models.BooleanField(default=False)
    files_downloaded = models.BooleanField(default=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['sync_type']),
            models.Index(fields=['started_at']),
        ]

    def __str__(self):
        return f"{self.sync_type.title()} Sync - {self.status} ({self.started_at.strftime('%Y-%m-%d %H:%M')})"

    def duration(self):
        """Get sync duration"""
        if self.completed_at:
            return self.completed_at - self.started_at
        return None

    def total_records_processed(self):
        """Get total records processed across all types"""
        return (self.properties_processed + self.configurations_processed + 
                self.images_processed + self.amenities_processed)


class SharedPropertyList(models.Model):
    """Model for sharing selected properties with temporary links"""
    name = models.CharField(max_length=200, help_text="Name for this shared list")
    token = models.CharField(max_length=50, unique=True, blank=True)
    properties = models.ManyToManyField(Property, related_name='shared_lists')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_lists')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    view_count = models.PositiveIntegerField(default=0)
    airtable_ids = models.JSONField(default=list, help_text="List of Airtable record IDs for the properties")
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.token:
            self.token = get_random_string(32)
        super().save(*args, **kwargs)
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return self.is_active and not self.is_expired()
    
    def __str__(self):
        return f"{self.name} - {self.token[:8]}..."


class PropertyFavorite(models.Model):
    """Store per-user favourite properties."""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='favourite_properties'
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='favourited_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'property')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['property']),
        ]

    def __str__(self):
        return f"{self.user.username} ❤ {self.property.name}"


class UserProfile(models.Model):
    """Extended user profile for employee management"""
    ROLE_CHOICES = (
        ('admin', 'Administrator'),
        ('agent', 'Real Estate Agent'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)
    is_employee = models.BooleanField(default=False)
    can_share_properties = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Location privacy - track which properties external users have unlocked
    unlocked_properties = models.ManyToManyField(
        Property,
        blank=True,
        related_name='unlocked_by_users',
        help_text="Properties for which this user can see exact location"
    )

    # CRM agent fields
    is_available = models.BooleanField(
        default=True,
        help_text="Agent can toggle offline to pause lead assignment"
    )
    on_leave_until = models.DateField(
        null=True, blank=True,
        help_text="If set and today <= this date, agent is excluded from assignment"
    )
    whatsapp_number = models.CharField(max_length=20, blank=True)
    coverage_locations = models.TextField(
        blank=True,
        help_text="Comma-separated list of cities/areas this agent covers"
    )
    property_specialties = models.TextField(
        blank=True,
        help_text="Comma-separated list of property categories this agent specialises in"
    )
    response_score = models.FloatField(
        default=1.0,
        help_text="0.0–1.0 ratio of leads contacted within SLA (last 30 days). Recomputed daily."
    )
    current_open_leads = models.PositiveIntegerField(
        default=0,
        help_text="Denormalized count of currently open leads assigned to this agent"
    )
    current_overdue_leads = models.PositiveIntegerField(
        default=0,
        help_text="Denormalized count of overdue leads assigned to this agent"
    )
    last_assigned_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Timestamp of most recent lead assignment (used for tie-breaking)"
    )
    total_leads_assigned = models.PositiveIntegerField(default=0)
    total_leads_won = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_role_display()}"

    @property
    def is_eligible_for_assignment(self):
        """True when the agent can receive new lead assignments."""
        from django.utils import timezone
        today = timezone.now().date()
        if self.role != 'agent':
            return False
        if not self.user.is_active:
            return False
        if not self.is_available:
            return False
        if self.on_leave_until and self.on_leave_until >= today:
            return False
        return True

    def unlock_property(self, property_obj):
        """Grant user access to exact location of a property"""
        if not self.is_employee:  # Employees don't need to unlock
            self.unlocked_properties.add(property_obj)

    def has_unlocked_property(self, property_obj):
        """Check if user has unlocked a specific property"""
        if self.is_employee:
            return True
        return self.unlocked_properties.filter(id=property_obj.id).exists()


class EmployeeInvitation(models.Model):
    """Invitation codes for employee registration"""
    code = models.CharField(max_length=20, unique=True, db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_invitations',
        help_text="Admin who created this invitation"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Optional expiration date")
    is_used = models.BooleanField(default=False)
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_invitation',
        help_text="Employee who used this code"
    )
    used_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.IntegerField(default=1, help_text="Number of times this code can be used")
    use_count = models.IntegerField(default=0)
    notes = models.TextField(blank=True, help_text="Internal notes about this invitation")

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Employee Invitation'
        verbose_name_plural = 'Employee Invitations'

    def __str__(self):
        status = "Used" if self.is_used else "Active"
        return f"{self.code} - {status}"

    def is_valid(self):
        """Check if invitation code is still valid"""
        # Check if already used (for single-use codes)
        if self.max_uses == 1 and self.is_used:
            return False

        # Check if max uses reached
        if self.use_count >= self.max_uses:
            return False

        # Check if expired
        if self.expires_at and timezone.now() > self.expires_at:
            return False

        return True

    def mark_as_used(self, user):
        """Mark invitation as used by a specific user"""
        self.use_count += 1
        if self.use_count >= self.max_uses:
            self.is_used = True
        self.used_by = user
        self.used_at = timezone.now()
        self.save()


class ClientInvitation(models.Model):
    """Invitation codes for client/external user registration"""
    code = models.CharField(max_length=20, unique=True, db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_client_invitations',
        help_text="Admin who created this invitation"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Optional expiration date")
    is_used = models.BooleanField(default=False)
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_client_invitation',
        help_text="Client who used this code"
    )
    used_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.IntegerField(default=1, help_text="Number of times this code can be used")
    use_count = models.IntegerField(default=0)
    notes = models.TextField(blank=True, help_text="Internal notes about this invitation")

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Client Invitation'
        verbose_name_plural = 'Client Invitations'

    def __str__(self):
        status = "Used" if self.is_used else "Active"
        return f"{self.code} - {status}"

    def is_valid(self):
        """Check if invitation code is still valid"""
        # Check if already used (for single-use codes)
        if self.max_uses == 1 and self.is_used:
            return False

        # Check if max uses reached
        if self.use_count >= self.max_uses:
            return False

        # Check if expired
        if self.expires_at and timezone.now() > self.expires_at:
            return False

        return True

    def mark_as_used(self, user):
        """Mark invitation as used by a specific user"""
        self.use_count += 1
        if self.use_count >= self.max_uses:
            self.is_used = True
        self.used_by = user
        self.used_at = timezone.now()
        self.save()

    @staticmethod
    def generate_code():
        """Generate a unique random invitation code"""
        while True:
            code = get_random_string(12, allowed_chars='ABCDEFGHJKLMNPQRSTUVWXYZ23456789').upper()
            if not EmployeeInvitation.objects.filter(code=code).exists():
                return code


def progress_image_path(instance, filename):
    """Generate upload path for progress update images"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return f"progress_images/{instance.progress_update.property.slug}/{filename}"


class PropertyProgress(models.Model):
    """Track construction/development progress for properties"""
    STAGE_CHOICES = (
        ('foundation', 'Foundation'),
        ('structure', 'Structure'),
        ('roofing', 'Roofing'),
        ('exterior', 'Exterior Finishing'),
        ('interior', 'Interior Finishing'),
        ('landscaping', 'Landscaping'),
        ('final_touches', 'Final Touches'),
        ('completed', 'Completed'),
    )

    # Airtable tracking
    airtable_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text="Airtable record ID for sync purposes"
    )

    # Relationships
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='progress_updates'
    )

    # Core fields
    stage = models.CharField(
        max_length=20,
        choices=STAGE_CHOICES,
        help_text="Current construction stage"
    )
    progress_percentage = models.PositiveIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0,
        help_text="Overall completion percentage (0-100)"
    )
    update_date = models.DateField(
        default=timezone.now,
        help_text="Date of this progress update"
    )
    description = models.TextField(
        blank=True,
        help_text="Details about this progress update"
    )
    uploaded_by = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name or email of person who added this update"
    )
    is_latest = models.BooleanField(
        default=False,
        help_text="Mark if this is the most recent update for the property"
    )

    # Multiple images support - stored as JSON array of image URLs from Airtable
    images_data = models.JSONField(
        default=list,
        blank=True,
        help_text="List of image attachment data from Airtable"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this was synced from Airtable"
    )

    class Meta:
        ordering = ['-update_date', '-created_at']
        verbose_name = 'Property Progress Update'
        verbose_name_plural = 'Property Progress Updates'
        indexes = [
            models.Index(fields=['airtable_id']),
            models.Index(fields=['property', '-update_date']),
            models.Index(fields=['stage']),
            models.Index(fields=['is_latest']),
        ]

    def __str__(self):
        return f"{self.property.name} - {self.get_stage_display()} ({self.progress_percentage}%)"

    def save(self, *args, **kwargs):
        # If this is marked as latest, unmark other updates for this property
        if self.is_latest:
            PropertyProgress.objects.filter(
                property=self.property,
                is_latest=True
            ).exclude(id=self.id).update(is_latest=False)
        super().save(*args, **kwargs)


class PropertyProgressImage(models.Model):
    """Individual images for progress updates (downloaded from Airtable)"""
    # Airtable tracking
    airtable_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text="Unique ID for this image (progress_update_id + index)"
    )

    # Relationships
    progress_update = models.ForeignKey(
        PropertyProgress,
        on_delete=models.CASCADE,
        related_name='images'
    )

    # Core fields
    image = models.ImageField(
        upload_to=progress_image_path,
        null=True,
        blank=True
    )
    order = models.PositiveIntegerField(default=0)
    caption = models.CharField(max_length=200, blank=True)

    # Airtable sync fields
    attachment_index = models.PositiveIntegerField(
        default=0,
        help_text="Index of attachment within Airtable record"
    )
    image_url_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA256 hash of image URL to detect changes"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order', 'attachment_index']
        indexes = [
            models.Index(fields=['airtable_id']),
            models.Index(fields=['progress_update', 'order']),
        ]

    def __str__(self):
        return f"{self.progress_update.property.name} - Progress Image {self.order}"
