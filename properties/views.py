from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, UpdateView
from django.utils.decorators import method_decorator
from django.db.models import Q, Min, Max, Avg, Count, F, DecimalField, ExpressionWrapper, Prefetch
from django.core.paginator import Paginator
from itertools import combinations
import statistics
from collections import Counter
from django.contrib import messages
from .models import (
    SharedPropertyList,
    UserProfile,
    Property,
    PropertyConfiguration,
    PropertyImage,
    PropertyAmenity,
    PropertyFavorite,
    PropertyProgress,
)
from .location_utils import (
    extract_location, LOCATION_CHOICES, TRACKED_LOCATION_SLUGS,
    location_slug, location_from_slug, pair_slug, parse_pair_slug,
)
from .markets import (
    MARKETS, MARKET_MIN_PROJECTS, market_from_slug, market_properties, qualifying_markets,
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
    # Order in the prefetch queryset so the per-property loop can iterate the
    # cached set without an extra .order_by() query (avoids an N+1).
    Prefetch('progress_updates', queryset=PropertyProgress.objects.order_by('-update_date')),
    'progress_updates__images',
)

# Sanity bounds (naira per square metre) used to exclude data-entry errors from
# any publicly displayed price-per-sqm figure. Despite the model field being
# named `square_footage`, the synced Airtable values are actually square
# metres (verified against real listing prices — see memory).
PUBLIC_PSQM_MIN = 50_000
PUBLIC_PSQM_MAX = 20_000_000
# Same idea for a single unit's total price — excludes data-entry errors
# (extra zeros etc.) from any publicly displayed min/max price figure.
PUBLIC_PRICE_MAX = 50_000_000_000
# Floor-area sanity bounds (sqm) for any public average size; the synced data
# contains obvious entry errors (e.g. 170,000,000).
PUBLIC_SQM_MIN = 15
PUBLIC_SQM_MAX = 3_000
# A section is only shown when at least this many data points sit behind it.
MIN_SAMPLE = 3
PUBLIC_LISTING_PREVIEW = 8  # extra projects shown to visitors on a neighbourhood page


def _trim_trailing_zeros(formatted):
    """'498.00' -> '498', '3.50' -> '3.5', '3.51' -> '3.51'."""
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')
    return formatted


def _format_naira_compact(value):
    """₦2,340,000,000 -> '₦2.34B', ₦1,950,000 -> '₦1.95M', ₦498,000,000 -> '₦498M'. None passes through."""
    if value is None:
        return None
    value = float(value)
    if value >= 1_000_000_000:
        return f"₦{_trim_trailing_zeros(f'{value / 1_000_000_000:.2f}')}B"
    if value >= 1_000_000:
        return f"₦{_trim_trailing_zeros(f'{value / 1_000_000:.2f}')}M"
    if value >= 1_000:
        return f"₦{value / 1_000:.0f}K"
    return f"₦{value:,.0f}"


def _market_stats(props_qs):
    """Aggregate public stats for a set of properties (an area or a sub-market).
    Shared by the homepage, neighbourhood pages and comparisons so the numbers
    can never disagree between pages. Applies the same PUBLIC_PSQM_MIN/MAX and
    PUBLIC_PRICE_MAX outlier guards as the rest of the public site.
    """
    prop_ids = props_qs.values('pk')
    count = props_qs.count()

    psqm_configs = PropertyConfiguration.objects.filter(
        property_id__in=prop_ids,
        square_footage__gt=0,
        price__isnull=False,
        price__gt=0,
    ).annotate(
        psqm=ExpressionWrapper(
            F('price') / F('square_footage'),
            output_field=DecimalField(max_digits=20, decimal_places=2),
        )
    ).filter(psqm__gte=PUBLIC_PSQM_MIN, psqm__lte=PUBLIC_PSQM_MAX)
    psqm_stats = psqm_configs.aggregate(avg_psqm=Avg('psqm'), sample_size=Count('id'))

    price_stats = PropertyConfiguration.objects.filter(
        property_id__in=prop_ids,
        price__isnull=False,
        price__gt=0,
        price__lt=PUBLIC_PRICE_MAX,
    ).aggregate(min_price=Min('price'), max_price=Max('price'))
    unit_count = PropertyConfiguration.objects.filter(property_id__in=prop_ids).count()

    return {
        'count': count,
        'avg_psqm': psqm_stats['avg_psqm'],
        'avg_psqm_display': _format_naira_compact(psqm_stats['avg_psqm']),
        'sample_size': psqm_stats['sample_size'],
        'unit_count': unit_count,
        'min_price_display': _format_naira_compact(price_stats['min_price']),
        'max_price_display': _format_naira_compact(price_stats['max_price']),
    }


def _district_stats(location_value):
    """Stats for one broad area, by Property.location value."""
    return _market_stats(Property.objects.filter(is_active=True, location=location_value))


def _property_card_data(prop):
    """Per-property card fields shared by the homepage's 'Recently added'
    cards and the neighbourhood detail page's listing grid. Expects `prop`'s
    `configurations` and `progress_updates` (filtered to is_latest) to already
    be prefetched by the caller.
    """
    # Starting price needs only a price; price per sqm additionally needs a floor area.
    priced = [c for c in prop.configurations.all() if c.price and 0 < c.price <= PUBLIC_PRICE_MAX]
    cheapest = min(priced, key=lambda c: c.price) if priced else None
    psqm = None
    if cheapest and cheapest.square_footage:
        candidate = cheapest.price / cheapest.square_footage
        if PUBLIC_PSQM_MIN <= candidate <= PUBLIC_PSQM_MAX:
            psqm = candidate
    latest_progress = next(iter(prop.progress_updates.all()), None)
    return {
        'property': prop,
        'starting_price_display': _format_naira_compact(cheapest.price) if cheapest else None,
        'psqm_display': _format_naira_compact(psqm),
        'stage_label': latest_progress.get_stage_display() if latest_progress else None,
        'is_new': (timezone.now() - prop.created_at).days <= 21,
    }


def _foundation_properties():
    """Active developments whose latest recorded stage is 'foundation' — the
    earliest construction stage we track, i.e. what we treat as a new launch."""
    return Property.objects.filter(
        is_active=True,
        progress_updates__is_latest=True,
        progress_updates__stage='foundation',
    ).distinct()


def _even_rows(items, per_row=4):
    """Trim a card list so it fills whole rows at desktop (per_row) and at
    tablet/mobile (2 per row); with fewer than per_row cards, keep pairs."""
    n = len(items)
    n -= n % per_row if n >= per_row else n % 2
    return items[:n]


def _prefer_classified(qs, limit):
    """First `limit` properties from qs (newest first), preferring ones with a
    real neighbourhood tag; only backfill from 'Others' if there aren't enough."""
    picked = list(qs.exclude(location='Others').order_by('-created_at')[:limit])
    if len(picked) < limit:
        have_ids = [p.id for p in picked]
        picked += list(
            qs.filter(location='Others').exclude(id__in=have_ids)
            .order_by('-created_at')[:limit - len(picked)]
        )
    return picked


def _card_queryset(qs):
    """Public cards need a photo, plus the configs/progress the card helper reads."""
    return (
        qs.exclude(thumbnail='').exclude(thumbnail__isnull=True)
        .prefetch_related(
            'configurations',
            Prefetch('progress_updates', queryset=PropertyProgress.objects.filter(is_latest=True)),
        )
    )


BED_ORDER = ['1', '2', '3', '4', '5+']


def _bed_bucket(bedrooms):
    if bedrooms is None or bedrooms < 1:
        return None
    return '5+' if bedrooms >= 5 else str(bedrooms)


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _market_insights(props_qs):
    """Everything on a market page beyond the headline stats: availability,
    typical prices, sizes, unit mix and the completion pipeline. Each block is
    None (or empty) when fewer than MIN_SAMPLE data points sit behind it, so
    the template can hide it rather than show a number that means nothing."""
    prop_ids = props_qs.values('pk')
    cfgs = list(
        PropertyConfiguration.objects.filter(property_id__in=prop_ids)
        .values('bedrooms', 'square_footage', 'price', 'is_available')
    )

    def valid_price(c):
        return bool(c['price']) and 0 < c['price'] < PUBLIC_PRICE_MAX

    def valid_size(c):
        return bool(c['square_footage']) and PUBLIC_SQM_MIN <= c['square_footage'] <= PUBLIC_SQM_MAX

    prices = sorted(float(c['price']) for c in cfgs if valid_price(c))
    sizes = [float(c['square_footage']) for c in cfgs if valid_size(c)]

    typical = None
    if len(prices) >= MIN_SAMPLE:
        quartiles = statistics.quantiles(prices, n=4) if len(prices) >= 4 else [prices[0], None, prices[-1]]
        typical = {
            'n': len(prices),
            'median': _format_naira_compact(statistics.median(prices)),
            'low': _format_naira_compact(quartiles[0]),
            'high': _format_naira_compact(quartiles[2]),
        }
    avg_size = {'n': len(sizes), 'value': round(statistics.mean(sizes))} if len(sizes) >= MIN_SAMPLE else None

    groups = {}
    for c in cfgs:
        bucket = _bed_bucket(c['bedrooms'])
        if bucket:
            groups.setdefault(bucket, []).append(c)
    with_beds = sum(len(g) for g in groups.values())
    unit_mix = []
    for bucket in BED_ORDER:
        group = groups.get(bucket)
        if not group:
            continue
        gp = sorted(float(c['price']) for c in group if valid_price(c))
        gs = [float(c['square_footage']) for c in group if valid_size(c)]
        unit_mix.append({
            'label': f"{bucket} bedroom",
            'units': len(group),
            'share': round(len(group) / with_beds * 100) if with_beds else 0,
            'median_price': _format_naira_compact(statistics.median(gp)) if len(gp) >= MIN_SAMPLE else None,
            'price_n': len(gp),
            'avg_size': round(statistics.mean(gs)) if len(gs) >= MIN_SAMPLE else None,
            'size_n': len(gs),
        })
    top_mix = max(unit_mix, key=lambda r: r['units']) if unit_mix else None

    dates = list(props_qs.values_list('completion_date', flat=True))
    dated = [d for d in dates if d]
    year_counts = Counter(d.year for d in dated)
    this_year = timezone.localdate().year
    pipeline = [{'year': y, 'count': n, 'past': y < this_year} for y, n in sorted(year_counts.items())]
    stage_order = [c[0] for c in PropertyProgress._meta.get_field('stage').choices]
    stage_labels = dict(PropertyProgress._meta.get_field('stage').choices)
    stage_counts = dict(
        PropertyProgress.objects.filter(property_id__in=prop_ids, is_latest=True)
        .values_list('stage').annotate(n=Count('id'))
    )
    stages = [{'label': stage_labels[k], 'count': stage_counts[k], 'key': k}
              for k in stage_order if stage_counts.get(k)]

    return {
        'total_units': len(cfgs),
        'available_units': sum(1 for c in cfgs if c['is_available']),
        'typical': typical,
        'avg_size': avg_size,
        'unit_mix': unit_mix,
        'top_mix': top_mix,
        'pipeline': pipeline,
        'pipeline_max': max((p['count'] for p in pipeline), default=0),
        'dated_count': len(dated),
        'undated_count': len(dates) - len(dated),
        'stages': stages,
        'foundation_count': stage_counts.get('foundation', 0),
    }


def _default_overview(label, stats, ins):
    """Factual paragraph from the numbers. Deliberately says nothing about an
    area's character: that is editorial copy and belongs in the admin."""
    parts = [
        f"{label} has {_plural(stats['count'], 'off-plan development')} tracked on this platform, "
        f"with {_plural(ins['total_units'], 'unit')} on record ({ins['available_units']} currently marked available)."
    ]
    if stats['avg_psqm_display']:
        parts.append(f"Verified prices average {stats['avg_psqm_display']} per square metre across {_plural(stats['sample_size'], 'unit price')}.")
    if ins['typical']:
        parts.append(f"The median priced unit is {ins['typical']['median']}.")
    return ' '.join(parts)


def _default_commentary(label, stats, ins, citywide, total_developments):
    """'What the numbers say': plain statements, each computed from the data."""
    points = []
    if stats['avg_psqm'] and citywide['avg_psqm']:
        pct = round((float(stats['avg_psqm']) / float(citywide['avg_psqm']) - 1) * 100)
        if pct == 0:
            points.append(f"At {stats['avg_psqm_display']} per sqm, {label} sits in line with the tracked citywide average of {citywide['avg_psqm_display']}.")
        else:
            points.append(
                f"At {stats['avg_psqm_display']} per sqm, {label} sits {abs(pct)}% {'above' if pct > 0 else 'below'} "
                f"the tracked citywide average of {citywide['avg_psqm_display']}."
            )
    if total_developments:
        share = round(stats['count'] / total_developments * 100)
        points.append(f"{label} accounts for {share}% of the {total_developments} developments we track.")
    if ins['typical']:
        points.append(
            f"The middle half of priced units cost between {ins['typical']['low']} and {ins['typical']['high']}, "
            f"with a median of {ins['typical']['median']}."
        )
    if stats['count'] and ins['foundation_count']:
        pct = round(ins['foundation_count'] / stats['count'] * 100)
        points.append(
            f"{_plural(ins['foundation_count'], 'project')} ({pct}%) are at foundation stage, the earliest stage we track."
        )
    if ins['pipeline']:
        peak = max(ins['pipeline'], key=lambda p: p['count'])
        points.append(f"Most stated completion dates fall in {peak['year']} ({_plural(peak['count'], 'project')}).")
    if stats['sample_size'] and stats['sample_size'] < 10:
        points.append(f"The average price rests on only {_plural(stats['sample_size'], 'verified price')}, so treat it as indicative.")
    return points


def _default_faqs(label, stats, ins):
    faqs = []
    if stats['avg_psqm_display']:
        faqs.append((f"What is the average price per square metre in {label}?",
                     f"{stats['avg_psqm_display']}, based on {_plural(stats['sample_size'], 'verified unit price')} with a recorded floor area."))
    else:
        faqs.append((f"What is the average price per square metre in {label}?",
                     f"We do not yet have enough verified prices in {label} to publish an average."))
    faqs.append((f"How many off-plan projects are tracked in {label}?",
                 f"{_plural(stats['count'], 'active development')} and {_plural(ins['total_units'], 'unit')}, "
                 f"of which {ins['available_units']} are currently marked available."))
    if ins['typical']:
        faqs.append((f"What do off-plan units in {label} typically cost?",
                     f"The median priced unit is {ins['typical']['median']}, and the middle half of priced units cost between "
                     f"{ins['typical']['low']} and {ins['typical']['high']} ({_plural(ins['typical']['n'], 'priced unit')})."))
    size_bits = []
    if ins['top_mix']:
        size_bits.append(f"The most common unit type is the {ins['top_mix']['label']} ({ins['top_mix']['share']}% of units).")
    if ins['avg_size']:
        size_bits.append(f"Average floor area is {ins['avg_size']['value']} sqm across {_plural(ins['avg_size']['n'], 'unit')} with a recorded size.")
    if size_bits:
        faqs.append((f"What sizes and unit types are available in {label}?", ' '.join(size_bits)))
    if ins['pipeline']:
        top = sorted(ins['pipeline'], key=lambda p: -p['count'])[:3]
        years = ', '.join(f"{p['year']} ({p['count']})" for p in sorted(top, key=lambda p: p['year']))
        faqs.append((f"When are projects in {label} due for completion?",
                     f"Of {_plural(ins['dated_count'], 'project')} with a stated completion date, the largest groups fall in {years}. "
                     f"{ins['undated_count']} have no date recorded yet."))
    return faqs


def _nearby_rows(market, this_avg):
    """Price comparison with each nearby market that has enough projects."""
    rows = []
    for slug in market.nearby:
        other = market_from_slug(slug)
        if not other:
            continue
        qs = market_properties(other)
        n = qs.count()
        if n < MARKET_MIN_PROJECTS:
            continue
        st = _market_stats(qs)
        delta = None
        if this_avg and st['avg_psqm']:
            delta = round((float(st['avg_psqm']) / float(this_avg) - 1) * 100)
        rows.append({
            'market': other,
            'count': n,
            'avg': st['avg_psqm_display'],
            'sample': st['sample_size'],
            'delta': delta,
            'compare_slug': pair_slug(market.slug, other.slug) if market.kind == 'area' and other.kind == 'area' else None,
        })
    return rows


def property_favorite_prefetch(prefetch):
    """Prefix property prefetches for use from PropertyFavorite.property."""
    if isinstance(prefetch, Prefetch):
        return Prefetch(
            f'property__{prefetch.prefetch_through}',
            queryset=prefetch.queryset,
            to_attr=prefetch.to_attr,
        )
    return f'property__{prefetch}'


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
            for update in prop.progress_updates.all()
        ]

        properties_data.append({
            'id': prop.id,
            'name': prop.name,
            'address': prop.address,
            'location': prop.location or extract_location(prop.address),
            'description': prop.description or '',
            'thumbnail': request.build_absolute_uri(prop.thumbnail.url) if prop.thumbnail else '',
            'brochure': request.build_absolute_uri(prop.brochure.url) if prop.brochure else '',
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

            # Mark the invitation code as used
            if hasattr(form, 'invitation'):
                form.invitation.mark_as_used(user)
                logger.info(f"Invitation code {form.invitation.code} used by {user.username}")

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
    """Custom logout view that redirects to the public landing page"""
    logout(request)
    return redirect('home')


@login_required
def properties_api(request):
    """API endpoint to get all properties as JSON for the map.
    Login-required: only used by the (authenticated) map dashboard."""
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
@login_required
def property_detail_api(request, property_id):
    """API endpoint to get a single property's details as JSON.
    Login-required (security review). NOTE: this disables the property-detail
    modal on the public /shared/<token>/ page for anonymous viewers — the
    shared list still renders server-side, but shared_properties.js:~394's
    fetch will redirect to login. Re-enable anonymous access by rendering the
    detail server-side in shared_properties.html if shared links must work."""
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
            
            config_data = [['Type', 'Bedrooms', 'Bathrooms', 'Sq. M.', 'Price', 'Available']]
            
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
                config_headers = ['Type', 'Bed', 'Bath', 'Sq.M', 'Price']
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
        can_share_properties = profile.can_share_properties

    except UserProfile.DoesNotExist:
        # Create profile if it doesn't exist (should not happen with new registration)
        profile = UserProfile.objects.create(
            user=request.user,
            is_employee=False,
            can_share_properties=False,
            role=None
        )
        is_internal_user = False
        can_share_properties = False
        logger.info(f"Created missing UserProfile for user: {request.user.username}")

    context = {
        'is_internal_user': is_internal_user,
        'can_share_properties': can_share_properties,
        'n8n_chat_url': settings.N8N_CHAT_WEBHOOK_URL,
        'user_initials': get_user_initials(request.user),
        'user_full_name': request.user.get_full_name() or request.user.username,
        'carto_api_key': settings.CARTO_API_KEY,
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

    shared_lists = list(SharedPropertyList.objects.filter(created_by=request.user))
    total_views = sum(sl.view_count or 0 for sl in shared_lists)
    active_count = sum(1 for sl in shared_lists if sl.is_valid)

    return render(request, 'manage_shared_lists.html', {
        'shared_lists': shared_lists,
        'total_views': total_views,
        'active_count': active_count,
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
        *PROPERTY_PREFETCHES
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

    # Full property payload (configs, amenities, images, etc.) for the client-side
    # Compare table — mirrors temp_view/favorites_view so anonymous shared-link
    # viewers get everything up front instead of hitting the login-required
    # property_detail_api.
    properties_data, _, _ = build_property_payload(request, properties)

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
        'properties_json': json.dumps(properties_data),
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
        *(property_favorite_prefetch(pref) for pref in PROPERTY_PREFETCHES)
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

    try:
        is_internal_user = request.user.profile.is_employee
        can_share_properties = request.user.profile.can_share_properties
    except UserProfile.DoesNotExist:
        is_internal_user = False
        can_share_properties = False

    context = {
        'properties_json': json.dumps(properties_data),
        'filter_ranges_json': json.dumps(filter_ranges_json),
        'filter_ranges': filter_ranges,
        'search_query': '',
        'is_favorites_page': True,
        'is_internal_user': is_internal_user,
        'can_share_properties': can_share_properties,
        'user_initials': get_user_initials(request.user),
        'user_full_name': request.user.get_full_name() or request.user.username,
        'n8n_chat_url': settings.N8N_CHAT_WEBHOOK_URL,
    }
    return render(request, 'favorites.html', context)


def public_homepage_view(request):
    """Public, unauthenticated market-intelligence homepage — now the site root.

    Already-authenticated users (agents, clients) land on their portfolio
    instead, so moving the gated view off "/" doesn't strand anyone who has
    it bookmarked as their app entry point.

    Every number here is computed from real data, not fixtures — see
    PUBLIC_PSQM_MIN/MAX above for the outlier guard applied to any
    price-per-square-metre figure before it's shown publicly.
    """
    if request.user.is_authenticated:
        return redirect('temp')

    active_properties = Property.objects.filter(is_active=True)

    valid_configs = PropertyConfiguration.objects.filter(
        property__is_active=True,
        square_footage__gt=0,
        price__isnull=False,
        price__gt=0,
    ).annotate(
        psqm=ExpressionWrapper(
            F('price') / F('square_footage'),
            output_field=DecimalField(max_digits=20, decimal_places=2),
        )
    ).filter(psqm__gte=PUBLIC_PSQM_MIN, psqm__lte=PUBLIC_PSQM_MAX)

    citywide = valid_configs.aggregate(avg_psqm=Avg('psqm'), sample_size=Count('id'))

    districts = []
    for loc_value, loc_label in LOCATION_CHOICES:
        if loc_value == 'Others':
            continue
        stats = _district_stats(loc_value)
        if stats['count'] == 0:
            continue
        rep_property = (
            active_properties.filter(location=loc_value)
            .exclude(thumbnail='').exclude(thumbnail__isnull=True)
            .order_by('-created_at')
            .first()
        )
        districts.append({
            'label': loc_label,
            'value': loc_value,
            'slug': location_slug(loc_value),
            'count': stats['count'],
            'avg_psqm': stats['avg_psqm'],
            'avg_psqm_display': stats['avg_psqm_display'],
            'sample_size': stats['sample_size'],
            'image_url': rep_property.thumbnail.url if rep_property and rep_property.thumbnail else None,
        })
    districts.sort(key=lambda d: d['count'], reverse=True)
    max_district_psqm = max((d['avg_psqm'] for d in districts if d['avg_psqm']), default=None)

    # A real (not fabricated) editorial line for the trends area: whichever
    # district has the highest avg psqm among those with a reliable sample.
    priciest_district = None
    reliable = [d for d in districts if d['sample_size'] and d['sample_size'] >= 3 and d['avg_psqm']]
    if reliable:
        priciest_district = max(
            reliable,
            key=lambda d: d['avg_psqm'],
        )

    # A real property image for the hero. Prefer a hand-picked flagship listing
    # (genuinely strong photography); fall back to the highest-value active
    # listing with a thumbnail if that one's ever renamed or deactivated —
    # excluding the same price outliers kept out of the public psqm figures.
    hero_property = (
        active_properties.filter(name__iexact="Metropolitan Towers")
        .exclude(thumbnail='').exclude(thumbnail__isnull=True)
        .first()
        or active_properties
        .exclude(thumbnail='').exclude(thumbnail__isnull=True)
        .annotate(max_config_price=Max('configurations__price'))
        .filter(max_config_price__isnull=False, max_config_price__lt=PUBLIC_PRICE_MAX)
        .order_by('-max_config_price')
        .first()
    )

    # Prefer properties with a real neighbourhood tag so these rows aren't
    # dominated by unclassified listings (see _prefer_classified).
    recent = _even_rows([_property_card_data(p) for p in _prefer_classified(_card_queryset(active_properties), 8)])

    # "New launches": developments at foundation stage — the earliest point we track.
    launches = _even_rows([_property_card_data(p) for p in _prefer_classified(_card_queryset(_foundation_properties()), 4)])
    launch_count = _foundation_properties().count()

    # Popular-looking entry points into the comparison tool: every pair among
    # the top districts by supply (canonical, sorted URLs).
    comparison_pairs = [
        {'a': a, 'b': b, 'slug': pair_slug(a['slug'], b['slug'])}
        for a, b in combinations(districts[:4], 2)
    ][:6]

    context = {
        'total_developments': active_properties.count(),
        'district_count': active_properties.exclude(location='').exclude(location='Others').values('location').distinct().count(),
        'citywide_avg_psqm_display': _format_naira_compact(citywide['avg_psqm']),
        'citywide_sample_size': citywide['sample_size'],
        'districts': districts[:5],
        'max_district_psqm': max_district_psqm,
        'priciest_district': priciest_district,
        'total_units': PropertyConfiguration.objects.filter(property__is_active=True).count(),
        'recent': recent,
        'launches': launches,
        'launch_count': launch_count,
        'comparison_pairs': comparison_pairs,
        'hero_property': hero_property,
        'data_updated_at': timezone.now(),
    }
    return render(request, 'public_home.html', context)


def _faq_jsonld(faqs):
    """schema.org FAQPage JSON-LD built from the same Q&As the page displays."""
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    }
    return json.dumps(data, ensure_ascii=False).replace('</', '<\\/')


def neighbourhood_detail_view(request, location_slug):
    """Public market page (an area like Ikoyi, or a sub-market like Banana
    Island). Public, no login required, same as property_detail_view below.

    Every figure is computed from tracked data. Editorial copy (overview,
    commentary, extra FAQs, guide) comes from NeighbourhoodProfile when an
    editor has written it; otherwise the page shows generated, factual text.
    """
    from .models import NeighbourhoodProfile

    market = market_from_slug(location_slug)
    if market is None:
        raise Http404("Unknown neighbourhood")

    props = market_properties(market)
    stats = _market_stats(props)
    limited = stats['count'] < MARKET_MIN_PROJECTS
    ins = _market_insights(props)
    citywide = _market_stats(Property.objects.filter(is_active=True))

    profile = NeighbourhoodProfile.objects.filter(market_slug=market.slug).first()
    editorial_overview = profile.overview.strip() if profile else ''
    overview = editorial_overview or _default_overview(market.label, stats, ins)
    editorial_commentary = profile.commentary.strip() if profile else ''
    faqs = _default_faqs(market.label, stats, ins)
    if profile:
        faqs += [(f.question, f.answer) for f in profile.faqs.all()]
    guide = None
    if profile and profile.guide_file:
        # The file URL is deliberately not put in the page: the download link is
        # returned by the guide form endpoint once the visitor has left their details.
        guide = {'title': profile.guide_title or f"{market.label} off-plan market guide"}

    rep_property = (
        _card_queryset(props).order_by('-created_at').first()
    )

    selected = [
        _property_card_data(p)
        for p in _card_queryset(props).filter(configurations__price__gt=0).distinct().order_by('-created_at')[:8]
    ]
    selected = _even_rows(selected)

    properties_qs = (
        _card_queryset(props).annotate(min_config_price=Min('configurations__price'))
    )
    sort = request.GET.get('sort', 'newest')
    if sort == 'price_asc':
        properties_qs = properties_qs.order_by(F('min_config_price').asc(nulls_last=True))
    elif sort == 'price_desc':
        properties_qs = properties_qs.order_by(F('min_config_price').desc(nulls_last=True))
    else:
        sort = 'newest'
        properties_qs = properties_qs.order_by('-created_at')

    if request.user.is_authenticated:
        paginator = Paginator(properties_qs, 24)
        page_obj = paginator.get_page(request.GET.get('page'))
        listings = [_property_card_data(prop) for prop in page_obj]
        gated_remaining = 0
    else:
        # Visitors get a short preview (not repeating the selected projects);
        # the full inventory and sorting sit behind sign-up.
        page_obj = None
        shown_ids = [c['property'].id for c in selected]
        rest = properties_qs.exclude(id__in=shown_ids).order_by('-created_at')
        listings = _even_rows([_property_card_data(prop) for prop in rest[:PUBLIC_LISTING_PREVIEW]])
        gated_remaining = max(rest.count() - len(listings), 0)

    label = market.label
    context = {
        'market': market,
        'limited': limited,
        'location_label': label,
        'location_slug': market.slug,
        'stats': stats,
        'insights': ins,
        'overview': overview,
        'overview_is_editorial': bool(editorial_overview),
        'editorial_commentary': editorial_commentary,
        'commentary_points': _default_commentary(label, stats, ins, citywide, citywide['count']),
        'faqs': faqs,
        'faq_jsonld': _faq_jsonld(faqs),
        'guide': guide,
        'selected': selected,
        'nearby': _nearby_rows(market, stats['avg_psqm']),
        'page_obj': page_obj,
        'listings': listings,
        'gated_remaining': gated_remaining,
        'sort': sort,
        'data_updated_at': timezone.now(),
        'compare_links': [
            {'label': dict(LOCATION_CHOICES)[v], 'slug': pair_slug(market.slug, other)}
            for other, v in TRACKED_LOCATION_SLUGS.items() if other != market.slug
        ] if market.kind == 'area' else [],
        'image_url': rep_property.thumbnail.url if rep_property and rep_property.thumbnail else None,
        'meta_title': f"{label} Off-Plan Property Market: {_plural(stats['count'], 'development')}"
                      + (f", {stats['avg_psqm_display']} avg/sqm" if stats['avg_psqm_display'] else "")
                      + " | CW Intelligence",
        'meta_description': f"Track {_plural(stats['count'], 'active off-plan development')} in {label}, Lagos: "
                             f"average price per square metre, typical unit prices, completion pipeline and verified listing data.",
    }
    return render(request, 'neighbourhood_detail.html', context)


def request_access_view(request):
    """Public page: ask for a client account. Submits to the CRM as a lead; an
    adviser then issues an invitation code (see register_view)."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'request_access.html', {
        'markets': qualifying_markets(),
        'meta_title': 'Request Private Access | CW Intelligence',
        'meta_description': 'Ask for a CW Real Estate client account to browse the full off-plan inventory, unit-level pricing and curated shortlists.',
    })


def neighbourhood_index_view(request):
    """Public index of every market with enough tracked projects."""
    areas, subs = [], []
    for m in MARKETS:
        qs = market_properties(m)
        if qs.count() < MARKET_MIN_PROJECTS:
            continue
        stats = _market_stats(qs)
        rep = _card_queryset(qs).order_by('-created_at').first()
        item = {
            'market': m,
            'stats': stats,
            'image_url': rep.thumbnail.url if rep and rep.thumbnail else None,
            'parent_label': market_from_slug(m.parent).label if m.parent else '',
        }
        (areas if m.kind == 'area' else subs).append(item)
    return render(request, 'neighbourhoods_index.html', {
        'areas': areas,
        'subs': subs,
        'data_updated_at': timezone.now(),
    })


def _comparison_side(slug):
    """Everything one side of a neighbourhood comparison needs."""
    value = TRACKED_LOCATION_SLUGS[slug]
    stats = _district_stats(value)
    latest = _prefer_classified(
        _card_queryset(Property.objects.filter(is_active=True, location=value)), 3,
    )
    return {
        'slug': slug,
        'label': dict(LOCATION_CHOICES)[value],
        'stats': stats,
        'launches': _foundation_properties().filter(location=value).count(),
        'latest': [_property_card_data(p) for p in latest],
        'image_url': latest[0].thumbnail.url if latest and latest[0].thumbnail else None,
    }


def compare_neighbourhoods_view(request, pair=None):
    """Public neighbourhood-vs-neighbourhood comparison. Every figure comes from
    the same _district_stats used on the homepage and district pages, so the
    numbers can never disagree between pages. Public, no login required."""
    if pair is None:
        a, b = request.GET.get('a'), request.GET.get('b')
        if a in TRACKED_LOCATION_SLUGS and b in TRACKED_LOCATION_SLUGS and a != b:
            return redirect('compare_neighbourhoods', pair=pair_slug(a, b))
        options = [{'slug': s, 'label': dict(LOCATION_CHOICES)[v]} for s, v in TRACKED_LOCATION_SLUGS.items()]
        pairs = []
        for x, y in combinations(options, 2):
            sx, sy = _district_stats(TRACKED_LOCATION_SLUGS[x['slug']]), _district_stats(TRACKED_LOCATION_SLUGS[y['slug']])
            pairs.append({'a': x, 'b': y, 'a_psqm': sx['avg_psqm_display'], 'b_psqm': sy['avg_psqm_display'],
                          'slug': pair_slug(x['slug'], y['slug'])})
        return render(request, 'compare_neighbourhoods.html', {
            'chooser': True,
            'options': options,
            'pairs': pairs,
            'data_updated_at': timezone.now(),
            'meta_title': 'Compare Lagos Off-Plan Neighbourhoods | CW Intelligence',
            'meta_description': 'Compare off-plan price per square metre, supply and new launches between Lagos neighbourhoods, side by side.',
        })

    parsed = parse_pair_slug(pair)
    if not parsed:
        raise Http404("Unknown comparison")
    slug_a, slug_b = parsed
    if slug_a not in TRACKED_LOCATION_SLUGS or slug_b not in TRACKED_LOCATION_SLUGS or slug_a == slug_b:
        raise Http404("Unknown comparison")
    canonical = pair_slug(slug_a, slug_b)
    if canonical != pair:
        return redirect('compare_neighbourhoods', pair=canonical, permanent=True)

    a, b = _comparison_side(slug_a), _comparison_side(slug_b)
    sa, sb = a['stats'], b['stats']

    def range_text(st):
        return f"{st['min_price_display']} to {st['max_price_display']}" if st['min_price_display'] else 'N/A'

    rows = [
        {'label': 'Active developments', 'a': sa['count'], 'b': sb['count']},
        {'label': 'Avg price per sqm', 'a': sa['avg_psqm_display'] or 'N/A', 'b': sb['avg_psqm_display'] or 'N/A', 'bars': True},
        {'label': 'Verified prices behind that average', 'a': sa['sample_size'], 'b': sb['sample_size']},
        {'label': 'Units tracked', 'a': sa['unit_count'], 'b': sb['unit_count']},
        {'label': 'Unit price range (lowest to highest)', 'a': range_text(sa), 'b': range_text(sb)},
        {'label': 'At foundation stage (new launches)', 'a': a['launches'], 'b': b['launches']},
    ]

    # Plain-language takeaways, derived only from the numbers above.
    takeaways = []
    if sa['avg_psqm'] and sb['avg_psqm']:
        hi, lo = (a, b) if sa['avg_psqm'] >= sb['avg_psqm'] else (b, a)
        pct = round((float(hi['stats']['avg_psqm']) / float(lo['stats']['avg_psqm']) - 1) * 100)
        takeaways.append(
            f"{hi['label']} averages {hi['stats']['avg_psqm_display']} per sqm, {pct}% higher than "
            f"{lo['label']} at {lo['stats']['avg_psqm_display']}."
        )
    if sa['count'] != sb['count']:
        more, fewer = (a, b) if sa['count'] > sb['count'] else (b, a)
        takeaways.append(
            f"{more['label']} has more tracked supply: {more['stats']['count']} developments "
            f"against {fewer['stats']['count']} in {fewer['label']}."
        )
    thin = [x for x in (a, b) if x['stats']['sample_size'] < 10]
    caveat = None
    if thin:
        names = ' and '.join(x['label'] for x in thin)
        caveat = (f"{names}'s average rests on fewer than 10 verified prices, so treat it as indicative, "
                  "not definitive.")

    max_psqm = max((x['stats']['avg_psqm'] for x in (a, b) if x['stats']['avg_psqm']), default=None)
    verdict = takeaways[0] if takeaways else f"{a['label']} and {b['label']}, side by side."
    return render(request, 'compare_neighbourhoods.html', {
        'chooser': False,
        'a': a, 'b': b, 'sides': [a, b], 'rows': rows, 'takeaways': takeaways, 'caveat': caveat, 'max_psqm': max_psqm,
        'options': [{'slug': s, 'label': dict(LOCATION_CHOICES)[v]} for s, v in TRACKED_LOCATION_SLUGS.items()],
        'other_pairs': [
            {'label': f"{a['label']} vs {dict(LOCATION_CHOICES)[TRACKED_LOCATION_SLUGS[o]]}", 'slug': pair_slug(slug_a, o)}
            for o in TRACKED_LOCATION_SLUGS if o not in (slug_a, slug_b)
        ] + [
            {'label': f"{b['label']} vs {dict(LOCATION_CHOICES)[TRACKED_LOCATION_SLUGS[o]]}", 'slug': pair_slug(slug_b, o)}
            for o in TRACKED_LOCATION_SLUGS if o not in (slug_a, slug_b)
        ],
        'data_updated_at': timezone.now(),
        'meta_title': f"{a['label']} vs {b['label']}: Lagos Off-Plan Prices Compared | CW Intelligence",
        'meta_description': verdict,
    })


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

    try:
        is_internal_user = request.user.profile.is_employee
        can_share_properties = request.user.profile.can_share_properties
    except UserProfile.DoesNotExist:
        is_internal_user = False
        can_share_properties = False

    context = {
        'properties_json': json.dumps(properties_data),
        'filter_ranges_json': json.dumps(filter_ranges_json),
        'filter_ranges': filter_ranges,
        'search_query': filters['search'],
        'is_favorites_page': False,
        'is_internal_user': is_internal_user,
        'can_share_properties': can_share_properties,
        'user_initials': get_user_initials(request.user),
        'user_full_name': request.user.get_full_name() or request.user.username,
        'n8n_chat_url': settings.N8N_CHAT_WEBHOOK_URL,
    }
    template_name = 'temp2.html' if request.resolver_match.url_name == 'temp2' else 'temp.html'
    return render(request, template_name, context)


@login_required
def reports_view(request):
    """Reports / Blog section — placeholder 'coming soon' page for now."""
    return render(request, 'coming_soon.html', {'page_title': 'Reports'})


@require_POST
def validate_invitation_code(request):
    """API endpoint to validate client invitation codes"""
    import json as json_module
    from .models import ClientInvitation

    try:
        data = json_module.loads(request.body)
        code = data.get('code', '').strip()

        if not code:
            return JsonResponse({'valid': False, 'error': 'Invitation code is required'})

        try:
            invitation = ClientInvitation.objects.get(code=code)
        except ClientInvitation.DoesNotExist:
            return JsonResponse({'valid': False, 'error': 'Invalid invitation code'})

        if not invitation.is_valid():
            return JsonResponse({'valid': False, 'error': 'This invitation code has expired or has been fully used'})

        # Store the invitation code in session for the OAuth flow
        request.session['pending_invitation_code'] = code
        # Explicitly save the session to ensure it persists across OAuth redirect
        request.session.modified = True
        request.session.save()

        logger.info(f"Stored invitation code {code} in session for OAuth flow")

        return JsonResponse({'valid': True})

    except Exception as e:
        logger.error(f"Error validating invitation code: {str(e)}")
        return JsonResponse({'valid': False, 'error': 'An error occurred. Please try again.'})


def google_oauth_with_invitation(request):
    """
    Custom view to handle Google OAuth initiation with invitation code.
    This ensures the invitation code is properly stored in session before OAuth redirect.
    """
    from django.shortcuts import redirect
    from .models import ClientInvitation

    invitation_code = request.GET.get('invitation_code', '').strip()

    if not invitation_code:
        messages.error(request, 'Invitation code is required for registration.')
        return redirect('register')

    try:
        invitation = ClientInvitation.objects.get(code=invitation_code)
    except ClientInvitation.DoesNotExist:
        messages.error(request, 'Invalid invitation code.')
        return redirect('register')

    if not invitation.is_valid():
        messages.error(request, 'This invitation code has expired or has been fully used.')
        return redirect('register')

    # Store invitation code in session
    request.session['pending_invitation_code'] = invitation_code
    request.session['is_employee_signup'] = False

    # Force session save
    request.session.modified = True
    request.session.save()

    logger.info(f"Stored invitation code {invitation_code} in session for Google OAuth")
    logger.info(f"Session key after save: {request.session.session_key}")
    logger.info(f"Session data: {dict(request.session.items())}")

    # Redirect to Google OAuth
    from allauth.socialaccount.providers.google.views import oauth2_login
    return oauth2_login(request)


def property_detail_view(request, property_pk):
    """
    HTML property detail page with enquiry form.
    Public — no login required (visitors need to be able to submit enquiries).
    """
    from crm.forms import EnquiryForm

    prop = get_object_or_404(Property, pk=property_pk, is_active=True)
    images = prop.images.order_by('order')
    configurations = prop.configurations.filter(is_available=True)
    amenities = prop.amenities.all()
    progress = prop.progress_updates.filter(is_latest=True).first()

    form = EnquiryForm()

    is_completed = bool(prop.completion_date and prop.completion_date <= timezone.localdate())
    min_price = prop.get_min_price()

    # Prefilled WhatsApp enquiry deep link (same message format as the listing cards).
    whatsapp_url = ''
    if prop.contact_phone:
        import urllib.parse
        loc = prop.address.split(',')[0].strip() if prop.address else ''
        price_str = f"₦{min_price:,.0f}" if min_price else "Price on Request"
        greeting = prop.contact_name or 'there'
        wa_msg = (
            f"Hi {greeting}, I'm interested in {prop.name}"
            f"{f' in {loc}' if loc else ''} listed at {price_str}. "
            f"Please send me more details. {request.build_absolute_uri()}"
        )
        wa_digits = ''.join(c for c in prop.contact_phone if c.isdigit())
        if wa_digits.startswith('0'):
            wa_digits = '234' + wa_digits[1:]
        whatsapp_url = f"https://wa.me/{wa_digits}?text={urllib.parse.quote(wa_msg)}"

    context = {
        'property': prop,
        'images': images,
        'configurations': configurations,
        'amenities': amenities,
        'progress': progress,
        'form': form,
        'enquiry_url': f'/crm/enquire/{prop.pk}/',
        'min_price': min_price,
        'is_completed': is_completed,
        'whatsapp_url': whatsapp_url,
        'is_favorite': PropertyFavorite.objects.filter(
            user=request.user, property=prop
        ).exists() if request.user.is_authenticated else False,
    }
    return render(request, 'property_detail.html', context)


@require_POST
def chat_proxy(request):
    """Same-origin proxy to the n8n chat webhook.

    The browser posts here instead of hitting n8n directly, which avoids the
    cross-origin CORS preflight that n8n's webhook node rejects, and keeps the
    webhook URL out of page source. CSRF-protected; the widgets send the token.
    """
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        payload = {}

    message = (payload.get('message') or '').strip()
    if not message:
        return JsonResponse({'error': 'Message is required.'}, status=400)

    webhook_url = getattr(settings, 'N8N_CHAT_WEBHOOK_URL', '')
    if not webhook_url:
        return JsonResponse(
            {'output': 'Chat service is unavailable right now. Please try again later.'},
            status=503,
        )

    try:
        resp = requests.post(
            webhook_url,
            json={
                'chatId': payload.get('chatId') or '',
                'message': message,
                'route': payload.get('route') or 'general',
            },
            timeout=25,
        )
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            data = {'output': resp.text}
        # n8n's "Respond to Webhook" often wraps the reply in a single-item list.
        if isinstance(data, list):
            data = data[0] if data else {}
        return JsonResponse(data, safe=False)
    except requests.RequestException as exc:
        logger.error('Chat webhook proxy failed: %s', exc)
        return JsonResponse(
            {'output': 'Sorry, something went wrong. Please try again later.'},
            status=502,
        )
