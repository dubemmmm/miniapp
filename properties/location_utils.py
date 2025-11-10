"""
Utility functions for location privacy and coordinate fuzzing
"""
import hashlib
import math
import random
from decimal import Decimal


def fuzz_coordinates(latitude, longitude, user_id=None, property_id=None, radius_meters=400):
    """
    Generate fuzzy coordinates offset from actual location within a radius.
    Uses consistent seeding based on user_id and property_id to ensure
    same user always sees same fuzzy location for same property.

    Args:
        latitude: Actual latitude (Decimal or float)
        longitude: Actual longitude (Decimal or float)
        user_id: User ID for consistent fuzzing (optional)
        property_id: Property ID for consistent fuzzing
        radius_meters: Fuzzing radius in meters (default 400m)

    Returns:
        tuple: (fuzzy_latitude, fuzzy_longitude) as Decimals
    """
    # Convert to float for calculations
    lat = float(latitude)
    lon = float(longitude)

    # Create consistent seed from user_id and property_id
    if user_id and property_id:
        seed_string = f"{user_id}_{property_id}_location_fuzz"
        seed_hash = hashlib.sha256(seed_string.encode()).hexdigest()
        seed = int(seed_hash[:8], 16)  # Use first 8 hex chars as seed
        random.seed(seed)

    # Generate random offset within radius
    # Using polar coordinates for uniform distribution
    angle = random.uniform(0, 2 * math.pi)
    distance = random.uniform(radius_meters * 0.5, radius_meters)  # 50-100% of radius

    # Convert distance to degrees (approximate)
    # 1 degree latitude ≈ 111km
    # 1 degree longitude ≈ 111km * cos(latitude)
    lat_offset = (distance / 111000) * math.sin(angle)
    lon_offset = (distance / (111000 * math.cos(math.radians(lat)))) * math.cos(angle)

    fuzzy_lat = lat + lat_offset
    fuzzy_lon = lon + lon_offset

    # Reset random seed to avoid affecting other random operations
    random.seed()

    # Return as Decimal with same precision
    return (
        Decimal(str(round(fuzzy_lat, 10))),
        Decimal(str(round(fuzzy_lon, 10)))
    )


def get_fuzzy_radius_meters(radius_meters=400):
    """
    Return the fuzzing radius in meters for displaying circle overlay.

    Args:
        radius_meters: The fuzzing radius used

    Returns:
        int: Radius in meters
    """
    return radius_meters


def obscure_address(address, level='partial'):
    """
    Obscure full address to show only general area.

    Args:
        address: Full address string
        level: 'partial' (show area/neighborhood) or 'minimal' (show only city)

    Returns:
        str: Obscured address
    """
    if not address:
        return "Location available after inquiry"

    # Split address by common delimiters
    parts = address.replace(',', ' ').split()

    if level == 'minimal':
        # Return only last 1-2 parts (usually city/state)
        return ' '.join(parts[-2:]) if len(parts) >= 2 else parts[-1]

    elif level == 'partial':
        # Return last 3-4 parts (neighborhood, city, state)
        if len(parts) >= 4:
            return ' '.join(parts[-4:])
        elif len(parts) >= 2:
            return ' '.join(parts[-3:])
        else:
            return address

    return address


def can_view_exact_location(user, property_obj):
    """
    Check if user has permission to view exact location of property.

    Args:
        user: Django User object
        property_obj: Property object

    Returns:
        bool: True if user can see exact location
    """
    if not user.is_authenticated:
        return False

    try:
        profile = user.profile

        # Employees always see exact location
        if profile.is_employee:
            return True

        # Check if user has unlocked this property
        if hasattr(profile, 'unlocked_properties'):
            return profile.unlocked_properties.filter(id=property_obj.id).exists()

    except AttributeError:
        pass

    return False


def get_property_location_data(property_obj, user):
    """
    Get location data for property based on user permissions.
    Returns either exact or fuzzy coordinates.

    Args:
        property_obj: Property object
        user: Django User object

    Returns:
        dict: Location data with coordinates, address, and metadata
    """
    # Check if user can see exact location
    show_exact = can_view_exact_location(user, property_obj)

    if show_exact:
        return {
            'latitude': float(property_obj.latitude) if property_obj.latitude else None,
            'longitude': float(property_obj.longitude) if property_obj.longitude else None,
            'address': property_obj.address,
            'is_exact': True,
            'fuzzy_radius': 0
        }
    else:
        # Generate fuzzy location
        user_id = user.id if user.is_authenticated else 0

        if property_obj.latitude and property_obj.longitude:
            fuzzy_lat, fuzzy_lon = fuzz_coordinates(
                property_obj.latitude,
                property_obj.longitude,
                user_id=user_id,
                property_id=property_obj.id,
                radius_meters=400
            )

            return {
                'latitude': float(fuzzy_lat),
                'longitude': float(fuzzy_lon),
                'address': obscure_address(property_obj.address, level='partial'),
                'is_exact': False,
                'fuzzy_radius': 400
            }
        else:
            return {
                'latitude': None,
                'longitude': None,
                'address': obscure_address(property_obj.address, level='minimal'),
                'is_exact': False,
                'fuzzy_radius': 0
            }
