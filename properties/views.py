from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, UpdateView
from django.utils.decorators import method_decorator
from django.db.models import Q, Min, Max
from django.contrib import messages
from .models import (
    SharedPropertyList,
    UserProfile,
    Property,
    PropertyConfiguration,
    PropertyImage,
    PropertyAmenity,
    PropertyFavorite,
)
from django.utils import timezone
from django.db.models.functions import ExtractMonth, ExtractYear
from datetime import timedelta
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import login, logout
from datetime import datetime, timedelta
from .forms import ExternalUserRegistrationForm, EmployeeRegistrationForm
import json
import logging
from django.urls import reverse, reverse_lazy
from io import BytesIO
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.conf import settings
from django.core.files.storage import default_storage
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from PIL import Image as PILImage
from calendar import month_name
import os
import requests
from decimal import Decimal
import requests
logger = logging.getLogger(__name__)
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Q
from decimal import Decimal, InvalidOperation
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

PROPERTY_PREFETCHES = (
    'images',
    'configurations',
    'amenities',
    'progress_updates',
    'progress_updates__images',
)


def get_user_initials(user):
    if not user.is_authenticated:
        return "NA"
    initials = ''.join(part[0].upper() for part in [user.first_name, user.last_name] if part)
    if initials:
        return initials[:2]
    return (user.username[:2] if user.username else "NA").upper()


def format_date_as_quarter(date_obj):
    """Convert a date object to quarter format (e.g., 'Q1 2028')"""
    if not date_obj:
        return None

    month = date_obj.month
    year = date_obj.year

    if month <= 3:
        quarter = 1
    elif month <= 6:
        quarter = 2
    elif month <= 9:
        quarter = 3
    else:
        quarter = 4

    return f"Q{quarter} {year}"


def extract_location(address):
    """Extract key location from address string"""
    if not address:
        return 'Others'

    location_keywords = {
        'Ikoyi': ['ikoyi'],
        'Lekki': ['lekki', 'ajah', 'osapa', 'chevron', 'oniru', 'ikate', 'agungi'],
        'Banana Island': ['banana island'],
        'Victoria Island': ['victoria island', 'vi ', ' vi,', 'v.i'],
    }

    address_lower = address.lower()
    for main_location, variations in location_keywords.items():
        for variation in variations:
            if variation in address_lower:
                return main_location
    return 'Others'


def build_property_payload(
    request,
    properties_queryset,
    favorite_ids=None,
    config_queryset=None,
    completion_dates_queryset=None
):
    """Serialize properties and build filter metadata for the frontend."""
    favorite_ids = favorite_ids or set()
    properties_list = list(properties_queryset)
    property_ids = [prop.id for prop in properties_list]

    if config_queryset is None:
        config_queryset = PropertyConfiguration.objects.filter(
            property_id__in=property_ids,
            is_available=True
        )

    if completion_dates_queryset is not None:
        completion_dates = [date for date in completion_dates_queryset if date]
    else:
        completion_dates = [prop.completion_date for prop in properties_list if prop.completion_date]

    quarter_year_options = []
    seen_quarters = set()
    for date in completion_dates:
        year = date.year
        month = date.month
        quarter = (month - 1) // 3 + 1
        label = f"Q{quarter} {year}"
        if label not in seen_quarters:
            seen_quarters.add(label)
            quarter_year_options.append(label)
    quarter_year_options.sort(key=lambda x: (int(x.split()[1]), int(x[1])))

    aggregates = {
        'price_range': config_queryset.aggregate(min_price=Min('price'), max_price=Max('price')) or {},
        'bedroom_range': config_queryset.aggregate(min_bedrooms=Min('bedrooms'), max_bedrooms=Max('bedrooms')) or {},
        'bathroom_range': config_queryset.aggregate(min_bathrooms=Min('bathrooms'), max_bathrooms=Max('bathrooms')) or {},
        'square_footage_range': config_queryset.aggregate(
            min_square_footage=Min('square_footage'),
            max_square_footage=Max('square_footage')
        ) or {},
    }

    filter_ranges = {
        'luxury_choices': Property.luxury_status.field.choices,
        **aggregates,
        'quarter_year_options': quarter_year_options,
    }

    def safe_float(value, default=0):
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    filter_ranges_json = {
        'min_price': safe_float(aggregates['price_range'].get('min_price')),
        'max_price': safe_float(aggregates['price_range'].get('max_price'), 10000000),
        'min_sqft': safe_float(aggregates['square_footage_range'].get('min_square_footage')),
        'max_sqft': safe_float(aggregates['square_footage_range'].get('max_square_footage'), 10000),
        'quarter_year_options': quarter_year_options,
    }

    properties_data = []
    for prop in properties_list:
        images = [
            {
                'image': request.build_absolute_uri(img.image.url),
                'alt_text': img.alt_text or ''
            }
            for img in prop.images.all() if img.image
        ]

        configurations = [
            {
                'type': config.type,
                'bedrooms': config.bedrooms,
                'bathrooms': float(config.bathrooms),
                'square_footage': config.square_footage,
                'price': float(config.price) if config.price else 0,
                'is_available': config.is_available
            }
            for config in prop.configurations.all()
        ]

        amenities = [
            {
                'name': amenity.name,
                'description': amenity.description or '',
                'icon': amenity.icon or '✨'
            }
            for amenity in prop.amenities.all()
        ]

        progress = [
            {
                'stage': update.get_stage_display(),
                'progress_percentage': update.progress_percentage,
                'update_date': update.update_date.strftime('%Y-%m-%d'),
                'description': update.description or '',
                'images': [
                    {
                        'image': request.build_absolute_uri(img.image.url),
                        'caption': img.caption or ''
                    }
                    for img in update.images.all() if img.image
                ]
            }
            for update in prop.progress_updates.all().order_by('-update_date')
        ]

        properties_data.append({
            'id': prop.id,
            'name': prop.name,
            'address': prop.address,
            'location': extract_location(prop.address),
            'description': prop.description or '',
            'thumbnail': request.build_absolute_uri(prop.thumbnail.url) if prop.thumbnail else '',
            'latitude': float(prop.latitude) if prop.latitude else 0,
            'longitude': float(prop.longitude) if prop.longitude else 0,
            'contact_name': prop.contact_name or '',
            'contact_phone': prop.contact_phone or '',
            'luxury_status': prop.luxury_status,
            'completion_date': prop.completion_date.strftime('%Y-%m-%d') if prop.completion_date else '',
            'is_active': prop.is_active,
            'images': images,
            'configurations': configurations,
            'amenities': amenities,
            'progress': progress,
            'is_favorite': prop.id in favorite_ids,
        })

    return properties_data, filter_ranges, filter_ranges_json


# Create your views here.
@login_required
def landing_view(request):
    """Display and filter properties - Only accessible to employees"""
    # Check if user is employee
    is_employee = False
    can_sync_airtable = False
    try:
        profile = request.user.profile
        is_employee = profile.is_employee
        can_sync_airtable = is_employee

        # Redirect non-employees to dashboard
        if not is_employee:
            messages.info(request, 'Access restricted. Employees only.')
            return redirect('dashboard')

    except UserProfile.DoesNotExist:
        # Create profile if it doesn't exist (should not happen with new registration)
        profile = UserProfile.objects.create(
            user=request.user,
            is_employee=False,
            can_share_properties=False,
            role=None
        )
        logger.info(f"Created missing UserProfile for user: {request.user.username}")
        messages.info(request, 'Access restricted. Employees only.')
        return redirect('dashboard')
    properties = Property.objects.filter(is_active=True)
    
    # Initialize filters
    filters = {
        'search': request.GET.get('search', '').strip(),
        'luxury_status': request.GET.get('luxury_status', ''),
        'min_price': request.GET.get('min_price', ''),
        'max_price': request.GET.get('max_price', ''),
        'min_bedrooms': request.GET.get('min_bedrooms', ''),
        'max_bedrooms': request.GET.get('max_bedrooms', ''),
        'min_bathrooms': request.GET.get('min_bathrooms', ''),
        'max_bathrooms': request.GET.get('max_bathrooms', ''),
        'completion_quarter': request.GET.get('completion_quarter', ''),
        'completion_year': request.GET.get('completion_year', ''),
        'min_square_footage': request.GET.get('min_square_footage', ''),
        'max_square_footage': request.GET.get('max_square_footage', ''),
    }

    # Apply filters
    if filters['search']:
        properties =properties.filter(
            Q(name__icontains=filters['search']) |
            Q(address__icontains=filters['search']) |
            Q(description__icontains=filters['search'])
        )
    
    if filters['luxury_status']:
        properties = properties.filter(luxury_status=filters['luxury_status'])
    
    # Filter by configuration fields (price, bedrooms, bathrooms)
    if filters['min_price']:
        try:
            min_price = float(filters['min_price'])
            properties = properties.filter(configurations__price__gte=min_price, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['max_price']:
        try:
            max_price = float(filters['max_price'])
            properties = properties.filter(configurations__price__lte=max_price, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['min_bedrooms']:
        try:
            min_bedrooms = int(filters['min_bedrooms'])
            properties = properties.filter(configurations__bedrooms__gte=min_bedrooms, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['max_bedrooms']:
        try:
            max_bedrooms = int(filters['max_bedrooms'])
            properties = properties.filter(configurations__bedrooms__lte=max_bedrooms, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['min_bathrooms']:
        try:
            min_bathrooms = int(filters['min_bathrooms'])
            properties = properties.filter(configurations__bathrooms__gte=min_bathrooms, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['max_bathrooms']:
        try:
            max_bathrooms = int(filters['max_bathrooms'])
            properties = properties.filter(configurations__bathrooms__lte=max_bathrooms, configurations__is_available=True)
        except ValueError:
            pass
    
    # Filter by completion quarter and year
    if filters['completion_quarter'] and filters['completion_year']:
        try:
            quarter = int(filters['completion_quarter'])
            year = int(filters['completion_year'])

            # Map quarter to date range
            quarter_dates = {
                1: (1, 1, 3, 31),    # Q1: Jan 1 - Mar 31
                2: (4, 1, 6, 30),    # Q2: Apr 1 - Jun 30
                3: (7, 1, 9, 30),    # Q3: Jul 1 - Sep 30
                4: (10, 1, 12, 31),  # Q4: Oct 1 - Dec 31
            }

            if quarter in quarter_dates:
                start_month, start_day, end_month, end_day = quarter_dates[quarter]
                start_date = datetime(year, start_month, start_day).date()
                end_date = datetime(year, end_month, end_day).date()

                # Filter properties with completion date within the quarter
                properties = properties.filter(
                    completion_date__gte=start_date,
                    completion_date__lte=end_date
                )
        except (ValueError, TypeError):
            pass
        
    # square footage filters (based on configurations)
    if filters['min_square_footage']:
        try:
            min_sqft = int(filters['min_square_footage'])
            properties = properties.filter(
                configurations__square_footage__gte=min_sqft,
                configurations__is_available=True
            )
        except ValueError:
            pass

    if filters['max_square_footage']:
        try:
            max_sqft = int(filters['max_square_footage'])
            properties = properties.filter(
                configurations__square_footage__lte=max_sqft,
                configurations__is_available=True
            )
        except ValueError:
            pass

    properties = properties.distinct()

    # Get filter ranges for the template
    all_configs = PropertyConfiguration.objects.filter(is_available=True, property__is_active=True)

    aggregates = {
        'price_range': all_configs.aggregate(min_price=Min('price'), max_price=Max('price')) or {},
        'bedroom_range': all_configs.aggregate(min_bedrooms=Min('bedrooms'), max_bedrooms=Max('bedrooms')) or {},
        'bathroom_range': all_configs.aggregate(min_bathrooms=Min('bathrooms'), max_bathrooms=Max('bathrooms')) or {},
        'square_footage_range': all_configs.aggregate(
            min_square_footage=Min('square_footage'),
            max_square_footage=Max('square_footage')
        ) or {},
    }

    # Get unique completion quarters and years
    completion_dates = Property.objects.filter(
        is_active=True,
        completion_date__isnull=False
    ).values_list('completion_date', flat=True).distinct()

    quarter_year_options = []
    seen_quarters = set()
    for date in completion_dates:
        if date:
            year = date.year
            month = date.month
            quarter = (month - 1) // 3 + 1
            label = f"Q{quarter} {year}"
            if label not in seen_quarters:
                seen_quarters.add(label)
                quarter_year_options.append(label)
    quarter_year_options.sort(key=lambda x: (int(x.split()[1]), int(x[1])))

    filter_ranges = {
        'luxury_choices': Property.luxury_status.field.choices,
        **aggregates,
        'quarter_year_options': quarter_year_options,
    }

    context = {
        'properties': properties,
        'filters': filters,
        'filter_ranges': filter_ranges,
        'is_employee': is_employee,
        'is_internal_user': is_employee,
        'can_sync_airtable': can_sync_airtable,
        'search_query': filters['search'],
    }
    return render(request, 'landing.html', context)

@login_required
def home(request):
    return render(request, 'home.html')

def register_view(request):
    """Public registration view for external users (non-employees)"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    # Set session flag for OAuth adapter
    request.session['is_employee_signup'] = False

    if request.method == 'POST':
        form = ExternalUserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Account created successfully! Please log in.')
            logger.info(f"New external user registered: {user.username}")
            return redirect('login')
    else:
        form = ExternalUserRegistrationForm()

    return render(request, 'register.html', {'form': form, 'is_employee_signup': False})


def employee_register_view(request):
    """Public registration view for employee users (admin/agent)"""
    if request.user.is_authenticated:
        return redirect('temp')

    # Set session flag for OAuth adapter
    request.session['is_employee_signup'] = True

    if request.method == 'POST':
        form = EmployeeRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Employee account created successfully! Please log in.')
            logger.info(f"New employee registered: {user.username} - Role: {user.profile.role}")
            return redirect('login')
        else:
            # Log form errors for debugging
            logger.error(f"Employee registration form errors: {form.errors}")
    else:
        form = EmployeeRegistrationForm()

    return render(request, 'employee_register.html', {'form': form, 'is_employee_signup': True})


def custom_logout_view(request):
    """Custom logout view that redirects to login page"""
    logout(request)
    return redirect('login')


def properties_api(request):
    """API endpoint to get all properties as JSON for the map"""
    from .location_utils import get_property_location_data

    properties = Property.objects.filter(is_active=True).prefetch_related(
        'configurations', 'images', 'amenities', 'progress_updates__images'
    )

    properties_data = []
    for prop in properties:
        # Get location data based on user permissions
        location_data = get_property_location_data(prop, request.user)

        images = [request.build_absolute_uri(img.image.url) for img in prop.images.all()]
        thumbnail = request.build_absolute_uri(prop.thumbnail.url) if prop.thumbnail else None
        configurations = [
            {
                'type': config.type,
                'bedrooms': config.bedrooms,
                'bathrooms': config.bathrooms,
                'square_footage': config.square_footage,
                'price': f"₦{float(config.price):,.2f}" if config.price is not None else "TBD"
            }
            for config in prop.configurations.all()
        ]
        amenities = [amenity.name for amenity in prop.amenities.all()]

        # Include progress updates only if user has exact location access
        progress_updates = []
        if location_data['is_exact']:
            for update in prop.progress_updates.all().order_by('-update_date'):
                progress_images = [
                    request.build_absolute_uri(img.image.url)
                    for img in update.images.all()
                    if img.image
                ]
                progress_updates.append({
                    'id': update.id,
                    'stage': update.get_stage_display(),
                    'stage_code': update.stage,
                    'progress_percentage': update.progress_percentage,
                    'update_date': update.update_date.strftime('%Y-%m-%d'),
                    'description': update.description,
                    'uploaded_by': update.uploaded_by,
                    'is_latest': update.is_latest,
                    'images': progress_images
                })

        properties_data.append({
            'id': prop.id,
            'name': prop.name,
            'latitude': location_data['latitude'],
            'longitude': location_data['longitude'],
            'address': location_data['address'],
            'is_exact_location': location_data['is_exact'],
            'fuzzy_radius': location_data['fuzzy_radius'],
            'description': prop.description,
            'configurations': configurations,
            'amenities': amenities,
            'thumbnail': thumbnail,
            'images': images,
            'contact': f"{prop.contact_name} - {prop.contact_phone}" if location_data['is_exact'] else "Contact available after inquiry",
            'brochure': request.build_absolute_uri(prop.brochure.url) if prop.brochure else "",
            'luxury_status': prop.get_luxury_status_display(),
            'completion_date': format_date_as_quarter(prop.completion_date),
            'progress_updates': progress_updates

        })

    return JsonResponse(properties_data, safe=False)
def property_detail_api(request, property_id):
    """API endpoint to get a single property's details as JSON"""
    from .location_utils import get_property_location_data

    property = get_object_or_404(Property.objects.prefetch_related(
        'configurations', 'images', 'amenities', 'progress_updates__images'
    ), id=property_id, is_active=True)

    # Get location data based on user permissions
    location_data = get_property_location_data(property, request.user)

    images = [request.build_absolute_uri(img.image.url) for img in property.images.all()]
    thumbnail = request.build_absolute_uri(property.thumbnail.url) if property.thumbnail else None
    configurations = [
        {
            'type': config.type,
            'bedrooms': config.bedrooms,
            'bathrooms': config.bathrooms,
            'square_footage': config.square_footage,
            'price': f"₦{float(config.price):,.2f}" if config.price is not None else "TBD"
        }
        for config in property.configurations.all()
    ]
    amenities = [amenity.name for amenity in property.amenities.all()]

    # Include progress updates only if user has exact location access (employees or shared link users)
    progress_updates = []
    if location_data['is_exact']:
        for update in property.progress_updates.all().order_by('-update_date'):
            progress_images = [
                request.build_absolute_uri(img.image.url)
                for img in update.images.all()
                if img.image
            ]
            progress_updates.append({
                'id': update.id,
                'stage': update.get_stage_display(),
                'stage_code': update.stage,
                'progress_percentage': update.progress_percentage,
                'update_date': update.update_date.strftime('%Y-%m-%d'),
                'description': update.description,
                'uploaded_by': update.uploaded_by,
                'is_latest': update.is_latest,
                'images': progress_images
            })

    property_data = {
        'id': property.id,
        'name': property.name,
        'latitude': location_data['latitude'],
        'longitude': location_data['longitude'],
        'address': location_data['address'],
        'is_exact_location': location_data['is_exact'],
        'fuzzy_radius': location_data['fuzzy_radius'],
        'description': property.description,
        'configurations': configurations,
        'amenities': amenities,
        'thumbnail': thumbnail,
        'images': images,
        'contact': f"{property.contact_name} - {property.contact_phone}" if location_data['is_exact'] else "Contact available after inquiry",
        'brochure': request.build_absolute_uri(property.brochure.url) if property.brochure else "",
        'luxury_status': property.get_luxury_status_display(),
        'completion_date': format_date_as_quarter(property.completion_date),
        'progress_updates': progress_updates
    }

    return JsonResponse(property_data)

@login_required
def create_shared_list(request):
    """Create a shared property list with temporary link"""
    try:
        profile = request.user.profile
        if not profile.can_share_properties:
            logger.warning(f"User {request.user.username} attempted to create shared list without permission")
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except UserProfile.DoesNotExist:
        logger.warning(f"User {request.user.username} has no UserProfile")
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', 'Shared Properties').strip()
            property_ids = data.get('property_ids', [])
            duration_hours = int(data.get('duration_hours', 72))  # Default 3 days
            
            if not property_ids:
                logger.error("No property IDs provided in request")
                return JsonResponse({'error': 'No properties selected'}, status=400)
            
            # Get properties and their airtable_ids
            properties = Property.objects.filter(id__in=property_ids, is_active=True)
            if not properties.exists():
                logger.error(f"No valid properties found for IDs: {property_ids}")
                return JsonResponse({'error': 'No valid properties found'}, status=400)
            
            # Collect airtable_ids from properties
            airtable_ids = [prop.airtable_id for prop in properties if prop.airtable_id]
            
            # Create shared list
            expires_at = timezone.now() + timedelta(hours=duration_hours)
            shared_list = SharedPropertyList.objects.create(
                name=name,
                created_by=request.user,
                expires_at=expires_at,
                airtable_ids=airtable_ids
            )
            
            # Add properties to the ManyToManyField
            shared_list.properties.set(properties)
            
            # Generate shareable URL using reverse to ensure correct path
            try:
                share_path = reverse('shared_properties', kwargs={'token': shared_list.token})
                share_url = request.build_absolute_uri(share_path)
                logger.info(f"Generated share URL: {share_url}")
            except Exception as e:
                logger.error(f"Failed to generate share URL: {str(e)}")
                return JsonResponse({'error': f'Failed to generate share URL: {str(e)}'}, status=500)
            
            logger.info(f"Created shared list {shared_list.token} with {properties.count()} properties")
            
            return JsonResponse({
                'success': True,
                'share_url': share_url,
                'token': shared_list.token,
                'expires_at': shared_list.expires_at.isoformat(),
                'property_count': properties.count()
            })
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON data in request")
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except ValueError as e:
            logger.error(f"Invalid input: {str(e)}")
            return JsonResponse({'error': f'Invalid input: {str(e)}'}, status=400)
        except Exception as e:
            logger.error(f"Server error: {str(e)}")
            return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
    
    logger.warning(f"Invalid request method: {request.method}")
    return JsonResponse({'error': 'Invalid request method'}, status=405)


class PropertyPDFGenerator:
    """Utility class for generating property PDFs with professional styling"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='PropertyTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=20,
            textColor=colors.HexColor('#1f2937'),
            alignment=TA_CENTER
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=12,
            textColor=colors.HexColor('#374151'),
            borderWidth=1,
            borderColor=colors.HexColor('#e5e7eb'),
            borderPadding=8,
            backColor=colors.HexColor('#f9fafb')
        ))
        
        self.styles.add(ParagraphStyle(
            name='PropertyInfo',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            textColor=colors.HexColor('#4b5563')
        ))
    
    def _download_and_process_image(self, image_url, max_width=400, max_height=300):
        """Download and process image for PDF inclusion"""
        try:
            if image_url.startswith('/'):
                # Local file
                image_path = os.path.join(settings.MEDIA_ROOT, image_url.lstrip('/'))
                print('the image path is ', image_path)
                if os.path.exists(image_path):
                    img = PILImage.open(image_path)
                else:
                    return None
            else:
                # Remote URL
                print('the remote image url is ', image_url)
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                img = PILImage.open(BytesIO(response.content))
            
            # Resize image maintaining aspect ratio
            img.thumbnail((max_width, max_height), PILImage.Resampling.LANCZOS)
            
            # Save to temporary buffer
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)
            
            return Image(buffer, width=img.width, height=img.height)
        except Exception as e:
            print(f"Error processing image {image_url}: {e}")
            return None
    
    def generate_property_pdf(self, property_obj, request):
        """Generate PDF for a single property"""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=inch,
            bottomMargin=inch
        )
        
        story = []
        
        # Header with company info
        story.append(Paragraph("Real Estate Properties", self.styles['PropertyTitle']))
        story.append(Spacer(1, 0.2*inch))
        
        # Property name and luxury status
        title_text = property_obj.name
        if property_obj.luxury_status == 'luxurious':
            title_text += " ★ LUXURY PROPERTY"
        story.append(Paragraph(title_text, self.styles['Heading1']))
        story.append(Spacer(1, 0.2*inch))
        
        # Property images
        if property_obj.images.exists():
            story.append(Paragraph("Property Images", self.styles['SectionHeader']))
            
            # Add main image
            main_image = property_obj.get_primary_image()
            if main_image:
                image_url = request.build_absolute_uri(main_image.image.url)
                img = self._download_and_process_image(image_url)
                if img:
                    story.append(img)
                    story.append(Spacer(1, 0.1*inch))
        
        # Basic information table
        story.append(Paragraph("Property Information", self.styles['SectionHeader']))
        
        basic_info = [
            ['Property Name:', property_obj.name],
            ['Address:', property_obj.address],
            ['Luxury Status:', 'Luxurious' if property_obj.luxury_status == 'luxurious' else 'Standard'],
            ['Contact:', property_obj.contact_name or 'Available on request'],
            ['Phone:', property_obj.contact_phone or 'Available on request'],
        ]
        
        basic_table = Table(basic_info, colWidths=[2*inch, 4*inch])
        basic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(basic_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Description
        if property_obj.description:
            story.append(Paragraph("Description", self.styles['SectionHeader']))
            story.append(Paragraph(property_obj.description, self.styles['PropertyInfo']))
            story.append(Spacer(1, 0.2*inch))
        
        # Configurations
        if property_obj.configurations.exists():
            story.append(Paragraph("Available Configurations", self.styles['SectionHeader']))
            
            config_data = [['Type', 'Bedrooms', 'Bathrooms', 'Sq. Ft.', 'Price', 'Available']]
            
            for config in property_obj.configurations.all():
                price_str = f"₦{config.price:,.0f}" if config.price else "On Request"
                availability = "Yes" if config.is_available else "No"
                
                config_data.append([
                    config.type,
                    str(config.bedrooms),
                    str(config.bathrooms),
                    f"{config.square_footage:,}",
                    price_str,
                    availability
                ])
            
            config_table = Table(config_data, colWidths=[1.2*inch, 0.8*inch, 0.8*inch, 0.8*inch, 1.2*inch, 0.8*inch])
            config_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(config_table)
            story.append(Spacer(1, 0.2*inch))
        
        # Amenities
        if property_obj.amenities.exists():
            story.append(Paragraph("Amenities & Features", self.styles['SectionHeader']))
            
            amenities_text = ", ".join([amenity.name for amenity in property_obj.amenities.all()])
            story.append(Paragraph(amenities_text, self.styles['PropertyInfo']))
            story.append(Spacer(1, 0.2*inch))
        
        # Footer
        story.append(Spacer(1, 0.5*inch))
        story.append(Paragraph("Contact us for more information or to schedule a viewing.", 
                              self.styles['PropertyInfo']))
        
        # Generate PDF
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()
        
        return pdf
    
    def generate_comparison_pdf(self, properties, request):
        """Generate PDF comparing multiple properties"""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=inch,
            bottomMargin=inch
        )
        
        story = []
        
        # Header
        story.append(Paragraph("Property Comparison Report", self.styles['PropertyTitle']))
        story.append(Spacer(1, 0.3*inch))
        
        # Summary table
        story.append(Paragraph("Properties Overview", self.styles['SectionHeader']))
        
        # Basic comparison table
        headers = ['Property', 'Address', 'Luxury', 'Min Price', 'Max Bedrooms']
        comparison_data = [headers]
        
        for prop in properties:
            min_price = prop.get_min_price()
            price_str = f"₦{min_price:,.0f}" if min_price else "On Request"
            
            comparison_data.append([
                prop.name[:25] + ('...' if len(prop.name) > 25 else ''),
                prop.address[:30] + ('...' if len(prop.address) > 30 else ''),
                '★ Luxury' if prop.luxury_status == 'luxurious' else 'Standard',
                price_str,
                str(prop.get_max_bedrooms())
            ])
        
        comparison_table = Table(comparison_data, colWidths=[1.5*inch, 2*inch, 1*inch, 1.2*inch, 1*inch])
        comparison_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(comparison_table)
        story.append(PageBreak())
        
        # Detailed comparison for each property
        for i, prop in enumerate(properties):
            story.append(Paragraph(f"{i+1}. {prop.name}", self.styles['Heading2']))
            story.append(Spacer(1, 0.1*inch))
            
            # Property details
            details = [
                ['Address:', prop.address],
                ['Description:', prop.description[:200] + ('...' if len(prop.description) > 200 else '') if prop.description else 'Not provided'],
                ['Contact:', f"{prop.contact_name} - {prop.contact_phone}" if prop.contact_name and prop.contact_phone else 'Available on request'],
            ]
            
            details_table = Table(details, colWidths=[1.5*inch, 5*inch])
            details_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(details_table)
            story.append(Spacer(1, 0.15*inch))
            
            # Configurations
            if prop.configurations.exists():
                config_headers = ['Type', 'Bed', 'Bath', 'Sq.Ft', 'Price']
                config_data = [config_headers]
                
                for config in prop.configurations.all()[:5]:  # Limit to 5 configs
                    price_str = f"₦{config.price:,.0f}" if config.price else "On Request"
                    config_data.append([
                        config.type,
                        str(config.bedrooms),
                        str(config.bathrooms),
                        f"{config.square_footage:,}",
                        price_str
                    ])
                
                config_table = Table(config_data, colWidths=[1.3*inch, 0.6*inch, 0.6*inch, 0.8*inch, 1.2*inch])
                config_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4b5563')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(config_table)
            
            # Amenities
            if prop.amenities.exists():
                story.append(Spacer(1, 0.1*inch))
                amenities = ", ".join([a.name for a in prop.amenities.all()[:10]])  # Limit amenities
                if prop.amenities.count() > 10:
                    amenities += f" and {prop.amenities.count() - 10} more..."
                story.append(Paragraph(f"<b>Amenities:</b> {amenities}", self.styles['PropertyInfo']))
            
            if i < len(properties) - 1:  # Don't add page break after last property
                story.append(PageBreak())
        
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()
        
        return pdf

@login_required
@require_http_methods(["GET"])
def download_property_pdf(request, property_id):
    """Download PDF for a specific property"""
    property_obj = get_object_or_404(Property, id=property_id, is_active=True)
    print('i am here')
    
    # Check if user has access to this property
    if not request.user.profile.is_employee:
        # Check if property is in user's shared lists
        shared_lists = SharedPropertyList.objects.filter(
            created_by=request.user,
            is_active=True,
            expires_at__gt=timezone.now(),
            properties=property_obj
        )
        if not shared_lists.exists():
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Generate PDF
    generator = PropertyPDFGenerator()
    pdf_content = generator.generate_property_pdf(property_obj, request)
    
    # Create response
    response = HttpResponse(pdf_content, content_type='application/pdf')
    filename = f"{property_obj.slug}-details.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

# @login_required
@require_http_methods(["POST"])
def compare_properties(request):
    """Compare multiple properties and return comparison data"""
    try:
        data = json.loads(request.body)
        property_ids = data.get('property_ids', [])
        
        if len(property_ids) < 2:
            return JsonResponse({'error': 'At least 2 properties required for comparison'}, status=400)
        
        if len(property_ids) > 5:
            return JsonResponse({'error': 'Maximum 5 properties can be compared at once'}, status=400)
        
        # Get properties
        properties = Property.objects.filter(
            id__in=property_ids,
            is_active=True
        ).prefetch_related('configurations', 'amenities', 'images')
        
        if not request.user.profile.is_employee:
            # Filter by shared lists
            shared_lists = SharedPropertyList.objects.filter(
                created_by=request.user,
                is_active=True,
                expires_at__gt=timezone.now()
            )
            properties = properties.filter(shared_lists__in=shared_lists).distinct()
        
        if not properties.exists():
            return JsonResponse({'error': 'No accessible properties found'}, status=404)
        
        # Build comparison data
        comparison_data = []
        for prop in properties:
            # Convert Decimal prices to float to avoid JSON serialization issues
            configs = []
            for config in prop.configurations.all():
                config_data = {
                    'type': config.type,
                    'bedrooms': config.bedrooms,
                    'bathrooms': config.bathrooms,
                    'square_footage': config.square_footage,
                    'price': float(config.price) if config.price else None,  # Convert Decimal to float
                    'is_available': config.is_available
                }
                configs.append(config_data)
            
            amenities = list(prop.amenities.all().values_list('name', flat=True))
            
            # Handle images properly
            images = []
            for img in prop.images.all():
                images.append(request.build_absolute_uri(img.image.url))
            
            comparison_data.append({
                'id': prop.id,
                'name': prop.name,
                'slug': prop.slug,
                'address': prop.address,
                'description': prop.description,
                'luxury_status': prop.luxury_status,
                'contact_name': prop.contact_name,
                'contact_phone': prop.contact_phone,
                'min_price': float(prop.get_min_price()) if prop.get_min_price() else None,
                'max_bedrooms': prop.get_max_bedrooms(),
                'configurations': configs,
                'amenities': amenities,
                'images': images,
                'primary_image': request.build_absolute_uri(prop.get_primary_image().image.url) if prop.get_primary_image() else None
            })
        
        return JsonResponse({
            'success': True,
            'properties': comparison_data,
            'comparison_url': reverse('comparison_pdf', kwargs={'property_ids': ','.join(map(str, property_ids))})
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        # Add more detailed error logging
        import traceback
        print(f"Error in compare_properties: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
    
@login_required
def dashboard_view(request):
    """Map dashboard view - accessible to all authenticated users

    External users see fuzzy locations, employees see exact locations
    """
    try:
        profile = request.user.profile
        is_internal_user = profile.is_employee

    except UserProfile.DoesNotExist:
        # Create profile if it doesn't exist (should not happen with new registration)
        profile = UserProfile.objects.create(
            user=request.user,
            is_employee=False,
            can_share_properties=False,
            role=None
        )
        is_internal_user = False
        logger.info(f"Created missing UserProfile for user: {request.user.username}")

    context = {
        'is_internal_user': is_internal_user,
        'n8n_chat_url': settings.N8N_CHAT_WEBHOOK_URL,
        'user_initials': get_user_initials(request.user),
        'user_full_name': request.user.get_full_name() or request.user.username,
    }

    return render(request, 'dashboard.html', context)

@login_required
def manage_shared_lists(request):
    """Manage shared property lists"""
    try:
        profile = request.user.profile
        if not profile.can_share_properties:
            messages.error(request, 'Permission denied.')
            return redirect('temp')
    except UserProfile.DoesNotExist:
        messages.error(request, 'Permission denied.')
        return redirect('temp')

    shared_lists = SharedPropertyList.objects.filter(created_by=request.user)

    return render(request, 'manage_shared_lists.html', {
        'shared_lists': shared_lists
    })


@login_required
@require_POST
@csrf_protect
def delete_shared_list(request, list_id):
    """Delete a shared property list"""
    try:
        profile = request.user.profile
        if not profile.can_share_properties:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        shared_list = get_object_or_404(
            SharedPropertyList,
            id=list_id,
            created_by=request.user
        )

        list_name = shared_list.name
        shared_list.delete()

        logger.info(f"User {request.user.username} deleted shared list: {list_name}")

        return JsonResponse({
            'success': True,
            'message': f'Shared list "{list_name}" deleted successfully'
        })

    except Exception as e:
        logger.error(f"Error deleting shared list {list_id}: {str(e)}")
        return JsonResponse({'error': f'Failed to delete list: {str(e)}'}, status=500)


@login_required
@require_POST
@csrf_protect
def request_property_unlock(request, property_id):
    """
    Request to unlock exact location of a property.
    This can be triggered when user inquires about a property.
    """
    try:
        property_obj = get_object_or_404(Property, id=property_id, is_active=True)

        # Check if user already has access
        try:
            profile = request.user.profile

            if profile.is_employee:
                return JsonResponse({
                    'success': True,
                    'message': 'You already have access to exact locations',
                    'unlocked': True
                })

            # Check if already unlocked
            if profile.has_unlocked_property(property_obj):
                return JsonResponse({
                    'success': True,
                    'message': 'Location already unlocked',
                    'unlocked': True
                })

            # For now, automatically unlock on request
            # In production, you might want to:
            # - Send email to admin for approval
            # - Require user to fill out a form
            # - Require payment
            # - Check if user has verified identity
            profile.unlock_property(property_obj)

            logger.info(f"User {request.user.username} unlocked property: {property_obj.name}")

            return JsonResponse({
                'success': True,
                'message': f'Exact location for {property_obj.name} is now visible',
                'unlocked': True
            })

        except UserProfile.DoesNotExist:
            return JsonResponse({'error': 'User profile not found'}, status=404)

    except Exception as e:
        logger.error(f"Error unlocking property {property_id}: {str(e)}")
        return JsonResponse({'error': f'Failed to unlock property: {str(e)}'}, status=500)


@login_required
@require_POST
@csrf_protect
def toggle_shared_list(request, list_id):
    """Toggle active status of a shared property list"""
    try:
        profile = request.user.profile
        if not profile.can_share_properties:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        new_status = data.get('active', True)

        shared_list = get_object_or_404(
            SharedPropertyList,
            id=list_id,
            created_by=request.user
        )

        shared_list.is_active = new_status
        shared_list.save(update_fields=['is_active'])

        status_text = 'activated' if new_status else 'deactivated'
        logger.info(f"User {request.user.username} {status_text} shared list: {shared_list.name}")

        return JsonResponse({
            'success': True,
            'message': f'Shared list "{shared_list.name}" {status_text} successfully',
            'is_active': shared_list.is_active
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error toggling shared list {list_id}: {str(e)}")
        return JsonResponse({'error': f'Failed to toggle list: {str(e)}'}, status=500)
    
    
@login_required
@require_http_methods(["GET"])
def comparison_pdf(request, property_ids=None):
    """Generate PDF comparison of selected properties"""
    try:
        # Get property_ids from URL parameter or query parameter
        if not property_ids:
            property_ids = request.GET.get('property_ids', '')
        
        if not property_ids:
            return JsonResponse({'error': 'No property IDs provided'}, status=400)
        
        # Convert comma-separated string to list of integers
        try:
            property_id_list = [int(pid.strip()) for pid in property_ids.split(',') if pid.strip()]
        except ValueError:
            return JsonResponse({'error': 'Invalid property IDs format'}, status=400)
        
        if len(property_id_list) < 2:
            return JsonResponse({'error': 'At least 2 properties required for comparison'}, status=400)
        
        # Get properties
        properties = Property.objects.filter(
            id__in=property_id_list,
            is_active=True
        ).prefetch_related('configurations', 'amenities', 'images')
        
        if not request.user.profile.is_employee:
            # Filter by shared lists for non-employees
            shared_lists = SharedPropertyList.objects.filter(
                created_by=request.user,
                is_active=True,
                expires_at__gt=timezone.now()
            )
            properties = properties.filter(shared_lists__in=shared_lists).distinct()
        
        if not properties.exists():
            return JsonResponse({'error': 'No accessible properties found'}, status=404)
        
        # Generate PDF
        generator = PropertyPDFGenerator()
        pdf_content = generator.generate_comparison_pdf(properties, request)
        
        # Create response
        response = HttpResponse(pdf_content, content_type='application/pdf')
        filename = f"property-comparison-{property_ids.replace(',', '-')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        return JsonResponse({'error': f'PDF generation error: {str(e)}'}, status=500)
    

def shared_properties_view(request, token):
    """View shared properties via temporary link"""
    shared_list = get_object_or_404(SharedPropertyList, token=token)
    
    # if not shared_list.is_valid or shared_list.is_expired or not shared_list.is_active:
    #     return render(request, 'shared_expired.html', {'shared_list': shared_list})
    
    if not shared_list.is_valid():
        if shared_list.is_expired or shared_list.is_active:
            return render(request, 'shared_expired.html', {'shared_list': shared_list})
        else:
            raise Http404("Shared list not found or inactive")
    
    # Increment view count
    shared_list.view_count += 1
    shared_list.save(update_fields=['view_count'])
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    min_bedrooms = request.GET.get('min_bedrooms')
    max_bedrooms = request.GET.get('max_bedrooms')
    min_bathrooms = request.GET.get('min_bathrooms')
    max_bathrooms = request.GET.get('max_bathrooms')
    luxury_status = request.GET.get('luxury_status')
    completion_date = request.GET.get('completion_date')
    min_square_footage = request.GET.get('min_square_footage', '')
    max_square_footage = request.GET.get('max_square_footage', '')
    
    
    # Get properties from shared list
    properties = shared_list.properties.filter(is_active=True).prefetch_related(
        'configurations', 'images', 'amenities'
    )
    
    # Apply filters
    if search_query:
        properties = properties.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if luxury_status:
        properties = properties.filter(luxury_status=luxury_status)
    
    # Filter by price range
    if min_price:
        properties = properties.filter(configurations__price__gte=min_price).distinct()
    if max_price:
        properties = properties.filter(configurations__price__lte=max_price).distinct()
    
    # Filter by bedrooms
    if min_bedrooms:
        properties = properties.filter(configurations__bedrooms__gte=min_bedrooms).distinct()
    if max_bedrooms:
        properties = properties.filter(configurations__bedrooms__lte=max_bedrooms).distinct()
    
    # Filter by bathrooms
    if min_bathrooms:
        properties = properties.filter(configurations__bathrooms__gte=min_bathrooms).distinct()
    if max_bathrooms:
        properties = properties.filter(configurations__bathrooms__lte=max_bathrooms).distinct()
    
    # Filter by completion date
    if completion_date:
        properties = properties.filter(completion_date__lte=completion_date)
    
    if min_square_footage:
        try:
            properties = properties.filter(
                configurations__square_footage__gte=int(min_square_footage),
                configurations__is_available=True
            )
        except ValueError:
            pass
    if max_square_footage:
        try:
            properties = properties.filter(
                configurations__square_footage__lte=int(max_square_footage),
                configurations__is_available=True
            )
        except ValueError:
            pass
    
    properties = properties.distinct()
        
    # Get filter ranges
    all_shared_properties = shared_list.properties.filter(is_active=True)
    price_range = all_shared_properties.aggregate(
        min_price=Min('configurations__price'),
        max_price=Max('configurations__price')
    )
    bedroom_range = all_shared_properties.aggregate(
        min_bedrooms=Min('configurations__bedrooms'),
        max_bedrooms=Max('configurations__bedrooms')
    )
    bathroom_range = all_shared_properties.aggregate(
        min_bathrooms=Min('configurations__bathrooms'),
        max_bathrooms=Max('configurations__bathrooms')
    )
    square_footage_range = all_shared_properties.aggregate(
        min_square_footage=Min('configurations__square_footage'),
        max_square_footage=Max('configurations__square_footage')
    )
    
    context = {
        'properties': properties,
        'shared_list': shared_list,
        'is_shared_view': True,
        'search_query': search_query,
        'filters': {
            'min_price': min_price,
            'max_price': max_price,
            'min_bedrooms': min_bedrooms,
            'max_bedrooms': max_bedrooms,
            'min_bathrooms': min_bathrooms,
            'max_bathrooms': max_bathrooms,
            'luxury_status': luxury_status,
            'min_square_footage': min_square_footage,
            'max_square_footage': max_square_footage,
            'completion_date': completion_date,
        },
        'filter_ranges': {
            'price_range': price_range,
            'bedroom_range': bedroom_range,
            'bathroom_range': bathroom_range,
            'square_footage_range': square_footage_range,
        }
    }
    
    return render(request, 'shared_properties.html', context)


@login_required
@require_POST
def toggle_favorite(request, property_id):
    """Toggle the favourite status for a property on behalf of the current user."""
    property_obj = get_object_or_404(Property, pk=property_id, is_active=True)
    favorite, created = PropertyFavorite.objects.get_or_create(
        user=request.user,
        property=property_obj,
    )

    if created:
        is_favorite = True
    else:
        favorite.delete()
        is_favorite = False

    return JsonResponse({
        'success': True,
        'property_id': property_id,
        'is_favorite': is_favorite,
    })


@login_required
def favorites_view(request):
    """Display the current user's favourite properties."""
    favorite_entries = PropertyFavorite.objects.filter(user=request.user).select_related(
        'property'
    ).prefetch_related(
        *(f'property__{pref}' for pref in PROPERTY_PREFETCHES)
    ).order_by('-created_at')

    favorite_ids = [entry.property_id for entry in favorite_entries]
    properties = [entry.property for entry in favorite_entries]

    config_queryset = PropertyConfiguration.objects.filter(
        property_id__in=favorite_ids,
        is_available=True
    )

    properties_data, filter_ranges, filter_ranges_json = build_property_payload(
        request,
        properties,
        favorite_ids=set(favorite_ids),
        config_queryset=config_queryset,
    )

    context = {
        'properties_json': json.dumps(properties_data),
        'filter_ranges_json': json.dumps(filter_ranges_json),
        'filter_ranges': filter_ranges,
        'search_query': '',
        'is_favorites_page': True,
        'user_initials': get_user_initials(request.user),
        'user_full_name': request.user.get_full_name() or request.user.username,
        'n8n_chat_url': settings.N8N_CHAT_WEBHOOK_URL,
    }
    return render(request, 'favorites.html', context)


@login_required
def temp_view(request):
    """Display and filter properties"""
    properties = Property.objects.filter(is_active=True).prefetch_related(*PROPERTY_PREFETCHES)
    favorite_ids = set(
        PropertyFavorite.objects.filter(user=request.user).values_list('property_id', flat=True)
    )

    # Initialize filters
    filters = {
        'search': request.GET.get('search', '').strip(),
        'luxury_status': request.GET.get('luxury_status', ''),
        'min_price': request.GET.get('min_price', ''),
        'max_price': request.GET.get('max_price', ''),
        'min_bedrooms': request.GET.get('min_bedrooms', ''),
        'max_bedrooms': request.GET.get('max_bedrooms', ''),
        'min_bathrooms': request.GET.get('min_bathrooms', ''),
        'max_bathrooms': request.GET.get('max_bathrooms', ''),
        'completion_quarter': request.GET.get('completion_quarter', ''),
        'completion_year': request.GET.get('completion_year', ''),
        'min_square_footage': request.GET.get('min_square_footage', ''),
        'max_square_footage': request.GET.get('max_square_footage', ''),
    }

    # Apply filters
    if filters['search']:
        properties =properties.filter(
            Q(name__icontains=filters['search']) |
            Q(address__icontains=filters['search']) |
            Q(description__icontains=filters['search'])
        )
    
    if filters['luxury_status']:
        properties = properties.filter(luxury_status=filters['luxury_status'])
    
    # Filter by configuration fields (price, bedrooms, bathrooms)
    if filters['min_price']:
        try:
            min_price = float(filters['min_price'])
            properties = properties.filter(configurations__price__gte=min_price, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['max_price']:
        try:
            max_price = float(filters['max_price'])
            properties = properties.filter(configurations__price__lte=max_price, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['min_bedrooms']:
        try:
            min_bedrooms = int(filters['min_bedrooms'])
            properties = properties.filter(configurations__bedrooms__gte=min_bedrooms, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['max_bedrooms']:
        try:
            max_bedrooms = int(filters['max_bedrooms'])
            properties = properties.filter(configurations__bedrooms__lte=max_bedrooms, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['min_bathrooms']:
        try:
            min_bathrooms = int(filters['min_bathrooms'])
            properties = properties.filter(configurations__bathrooms__gte=min_bathrooms, configurations__is_available=True)
        except ValueError:
            pass
    
    if filters['max_bathrooms']:
        try:
            max_bathrooms = int(filters['max_bathrooms'])
            properties = properties.filter(configurations__bathrooms__lte=max_bathrooms, configurations__is_available=True)
        except ValueError:
            pass
    
    # Filter by completion quarter and year
    if filters['completion_quarter'] and filters['completion_year']:
        try:
            quarter = int(filters['completion_quarter'])
            year = int(filters['completion_year'])

            # Map quarter to date range
            quarter_dates = {
                1: (1, 1, 3, 31),    # Q1: Jan 1 - Mar 31
                2: (4, 1, 6, 30),    # Q2: Apr 1 - Jun 30
                3: (7, 1, 9, 30),    # Q3: Jul 1 - Sep 30
                4: (10, 1, 12, 31),  # Q4: Oct 1 - Dec 31
            }

            if quarter in quarter_dates:
                start_month, start_day, end_month, end_day = quarter_dates[quarter]
                start_date = datetime(year, start_month, start_day).date()
                end_date = datetime(year, end_month, end_day).date()

                # Filter properties with completion date within the quarter
                properties = properties.filter(
                    completion_date__gte=start_date,
                    completion_date__lte=end_date
                )
        except (ValueError, TypeError):
            pass
        
    # square footage filters (based on configurations)
    if filters['min_square_footage']:
        try:
            min_sqft = int(filters['min_square_footage'])
            properties = properties.filter(
                configurations__square_footage__gte=min_sqft,
                configurations__is_available=True
            )
        except ValueError:
            pass

    if filters['max_square_footage']:
        try:
            max_sqft = int(filters['max_square_footage'])
            properties = properties.filter(
                configurations__square_footage__lte=max_sqft,
                configurations__is_available=True
            )
        except ValueError:
            pass

    properties = properties.distinct()

    all_configs = PropertyConfiguration.objects.filter(is_available=True, property__is_active=True)
    completion_dates_qs = Property.objects.filter(
        is_active=True,
        completion_date__isnull=False
    ).values_list('completion_date', flat=True).distinct()

    properties_data, filter_ranges, filter_ranges_json = build_property_payload(
        request,
        properties,
        favorite_ids=favorite_ids,
        config_queryset=all_configs,
        completion_dates_queryset=completion_dates_qs,
    )
    context = {
        'properties_json': json.dumps(properties_data),
        'filter_ranges_json': json.dumps(filter_ranges_json),
        'filter_ranges': filter_ranges,
        'search_query': filters['search'],
        'is_favorites_page': False,
        'user_initials': get_user_initials(request.user),
        'user_full_name': request.user.get_full_name() or request.user.username,
        'n8n_chat_url': settings.N8N_CHAT_WEBHOOK_URL,
    }
    return render(request, 'temp.html', context)
