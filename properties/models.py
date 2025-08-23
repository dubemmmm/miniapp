from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string

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
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    address = models.TextField()
    description = models.TextField()
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
    created_at = models.DateTimeField(auto_now_add=True,)
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
    created_at = models.DateTimeField(auto_now_add=True,)
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
    image = models.ImageField(upload_to=property_image_path)
    alt_text = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    
    # Additional Airtable sync fields
    attachment_index = models.PositiveIntegerField(default=0, 
                                                   help_text="Index of attachment within Airtable record")
    original_record_id = models.CharField(max_length=50, blank=True,
                                          help_text="Original Airtable record ID before splitting")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, )
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

class UserProfile(models.Model):
    """Extended user profile for employee management"""
    ROLE_CHOICES = (
        ('admin', 'Administrator'),
        ('agent', 'Real Estate Agent'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    phone = models.CharField(max_length=20, blank=True)
    is_employee = models.BooleanField(default=False)
    can_share_properties = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_role_display()}"