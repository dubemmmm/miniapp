"""
Management command to validate Airtable data quality and report errors.
Usage: python manage.py validate_airtable_data
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from django.core.management.base import BaseCommand
from decouple import config
from pyairtable import Table

from properties.models import Property


class DataValidationReport:
    """Stores validation errors and warnings"""
    
    def __init__(self):
        self.errors = defaultdict(list)  # Critical issues
        self.warnings = defaultdict(list)  # Non-critical issues
        self.info = defaultdict(list)  # Informational messages
        
    def add_error(self, category: str, message: str, record_id: str = None, record_name: str = None):
        self.errors[category].append({
            'message': message,
            'record_id': record_id,
            'record_name': record_name
        })
    
    def add_warning(self, category: str, message: str, record_id: str = None, record_name: str = None):
        self.warnings[category].append({
            'message': message,
            'record_id': record_id,
            'record_name': record_name
        })
    
    def add_info(self, category: str, message: str):
        self.info[category].append(message)
    
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


class Command(BaseCommand):
    help = "Validate Airtable data quality and report errors/warnings"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--show-warnings',
            action='store_true',
            help='Show warnings in addition to errors'
        )
        parser.add_argument(
            '--show-info',
            action='store_true',
            help='Show informational messages'
        )
        parser.add_argument(
            '--category',
            type=str,
            help='Only check specific category: properties, configurations, images, amenities, relationships'
        )
    
    def handle(self, *args, **options):
        self.show_warnings = options['show_warnings']
        self.show_info = options['show_info']
        category_filter = options.get('category')
        
        # Initialize Airtable connection
        pat = config("AIRTABLE_TOKEN")
        base_id = config("AIRTABLE_BASE_ID")
        
        if not pat or not base_id:
            self.stderr.write(self.style.ERROR("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set"))
            return
        
        tbl_props = config("AIRTABLE_TABLE_PROPERTIES", "Property")
        tbl_cfgs = config("AIRTABLE_TABLE_CONFIGS", "Configuration")
        tbl_imgs = config("AIRTABLE_TABLE_IMAGES", "Images")
        tbl_amen = config("AIRTABLE_TABLE_AMENITIES", "Amenities")
        
        props_t = Table(pat, base_id, tbl_props)
        cfgs_t = Table(pat, base_id, tbl_cfgs)
        imgs_t = Table(pat, base_id, tbl_imgs)
        amen_t = Table(pat, base_id, tbl_amen)
        
        self.stdout.write(self.style.SUCCESS("🔍 Starting Airtable data validation...\n"))
        
        # Fetch all data
        self.stdout.write("📥 Fetching data from Airtable...")
        prop_records = list(props_t.all())
        cfg_records = list(cfgs_t.all())
        img_records = list(imgs_t.all())
        amen_records = list(amen_t.all())
        
        self.stdout.write(f"   Properties: {len(prop_records)}")
        self.stdout.write(f"   Configurations: {len(cfg_records)}")
        self.stdout.write(f"   Images: {len(img_records)}")
        self.stdout.write(f"   Amenities: {len(amen_records)}\n")
        
        report = DataValidationReport()
        
        # Run validations based on category filter
        categories_to_check = [category_filter] if category_filter else [
            'properties', 'configurations', 'images', 'amenities', 'relationships'
        ]
        
        if 'properties' in categories_to_check:
            self.validate_properties(prop_records, report)
        
        if 'configurations' in categories_to_check:
            self.validate_configurations(cfg_records, prop_records, report)
        
        if 'images' in categories_to_check:
            self.validate_images(img_records, prop_records, report)
        
        if 'amenities' in categories_to_check:
            self.validate_amenities(amen_records, prop_records, report)
        
        if 'relationships' in categories_to_check:
            self.validate_relationships(prop_records, cfg_records, img_records, amen_records, report)
        
        # Display report
        self.display_report(report)
    
    # ==================== PROPERTY VALIDATIONS ====================
    
    def validate_properties(self, records: List[Dict], report: DataValidationReport):
        self.stdout.write("🏢 Validating Properties...")
        
        seen_names = {}
        seen_slugs = {}
        
        for rec in records:
            rid = rec.get('id')
            fields = rec.get('fields', {})
            name = fields.get('Name', '').strip()
            
            # 1. Check for missing required fields
            if not name:
                report.add_error('properties', 
                    f"Missing property name", rid, "Unnamed Property")
            
            # 2. Check for duplicate names
            if name:
                if name.lower() in seen_names:
                    report.add_warning('properties',
                        f"Duplicate property name: '{name}'", rid, name)
                    report.add_warning('properties',
                        f"Duplicate property name: '{name}'", 
                        seen_names[name.lower()], name)
                seen_names[name.lower()] = rid
            
            # 3. Check slug issues
            slug = fields.get('Slug (Final)') or fields.get('Slug', '')
            if slug:
                if slug in seen_slugs:
                    report.add_error('properties',
                        f"Duplicate slug: '{slug}' - This will cause URL conflicts!", 
                        rid, name)
                seen_slugs[slug] = rid
            else:
                report.add_warning('properties',
                    f"Missing slug - will be auto-generated", rid, name)
            
            # 4. Check address
            address = fields.get('Address', '').strip()
            if not address:
                report.add_warning('properties',
                    f"Missing address", rid, name)
            elif len(address) < 10:
                report.add_warning('properties',
                    f"Address seems too short: '{address}'", rid, name)
            
            # 5. Check description
            description = fields.get('Description', '').strip()
            if not description:
                report.add_warning('properties',
                    f"Missing description", rid, name)
            elif len(description) < 50:
                report.add_warning('properties',
                    f"Description too short ({len(description)} chars) - consider adding more detail", 
                    rid, name)
            
            # 6. Validate coordinates
            lat = fields.get('Latitude')
            lon = fields.get('Longitude')
            
            if lat and not self.is_valid_latitude(lat):
                report.add_error('properties',
                    f"Invalid latitude: {lat} (must be between -90 and 90)", rid, name)
            
            if lon and not self.is_valid_longitude(lon):
                report.add_error('properties',
                    f"Invalid longitude: {lon} (must be between -180 and 180)", rid, name)
            
            if (lat and not lon) or (lon and not lat):
                report.add_warning('properties',
                    f"Incomplete coordinates - both latitude and longitude needed", rid, name)
            
            # 7. Check contact info
            contact_name = fields.get('Contact Name', '').strip()
            contact_phone = fields.get('Contact Phone', '').strip()
            
            if not contact_name and not contact_phone:
                report.add_warning('properties',
                    f"Missing contact information", rid, name)
            
            if contact_phone and not self.is_valid_phone(contact_phone):
                report.add_warning('properties',
                    f"Phone number format looks incorrect: '{contact_phone}'", rid, name)
            
            # 8. Check luxury status
            luxury = fields.get('Luxury Status', '').strip()
            if luxury and luxury not in ['luxurious', 'non_luxurious', 'Luxurious', 'Non-Luxurious']:
                report.add_warning('properties',
                    f"Unexpected luxury status value: '{luxury}'", rid, name)
            
            # 9. Check file attachments
            brochure = fields.get('Brochure')
            if not brochure:
                report.add_warning('properties',
                    f"Missing brochure PDF", rid, name)
            
            thumbnail = fields.get('Thumbnail') or fields.get('Thumbnails')
            if not thumbnail:
                report.add_warning('properties',
                    f"Missing thumbnail image", rid, name)
            
            # 10. Check completion date format
            completion_date = fields.get('Completion Date')
            if completion_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', str(completion_date)):
                report.add_warning('properties',
                    f"Completion date format incorrect: '{completion_date}' (should be YYYY-MM-DD)", 
                    rid, name)
    
    # ==================== CONFIGURATION VALIDATIONS ====================
    
    def validate_configurations(self, records: List[Dict], prop_records: List[Dict], 
                               report: DataValidationReport):
        self.stdout.write("🏗️  Validating Configurations...")
        
        prop_ids = {r.get('id') for r in prop_records}
        config_by_property = defaultdict(list)
        
        for rec in records:
            rid = rec.get('id')
            fields = rec.get('fields', {})
            
            # 1. Check for linked property
            linked_props = fields.get('Property', [])
            if not linked_props:
                report.add_error('configurations',
                    f"Configuration not linked to any property", rid)
                continue
            
            prop_id = linked_props[0]
            
            # 2. Check if linked property exists
            if prop_id not in prop_ids:
                report.add_error('configurations',
                    f"Linked to non-existent property: {prop_id}", rid)
                continue
            
            config_type = fields.get('Type', '').strip()
            
            # 3. Check for missing type
            if not config_type:
                report.add_error('configurations',
                    f"Missing configuration type", rid)
            
            # Track for duplicate checking
            config_by_property[prop_id].append({
                'id': rid,
                'type': config_type,
                'bedrooms': fields.get('Bedrooms'),
                'bathrooms': fields.get('Bathrooms'),
                'sqft': fields.get('Square Footage'),
                'price': fields.get('Price')
            })
            
            # 4. Validate bedrooms
            bedrooms = fields.get('Bedrooms')
            if bedrooms is None:
                report.add_warning('configurations',
                    f"Missing bedrooms count for '{config_type}'", rid)
            elif not isinstance(bedrooms, (int, float)) or bedrooms < 0:
                report.add_error('configurations',
                    f"Invalid bedrooms value: {bedrooms}", rid)
            elif bedrooms > 10:
                report.add_warning('configurations',
                    f"Unusually high bedroom count: {bedrooms} - please verify", rid)
            
            # 5. Validate bathrooms
            bathrooms = fields.get('Bathrooms')
            if bathrooms is None:
                report.add_warning('configurations',
                    f"Missing bathrooms count for '{config_type}'", rid)
            elif not isinstance(bathrooms, (int, float)) or bathrooms < 0:
                report.add_error('configurations',
                    f"Invalid bathrooms value: {bathrooms}", rid)
            
            # 6. Validate square footage
            sqft = fields.get('Square Footage')
            if not sqft:
                report.add_warning('configurations',
                    f"Missing square footage for '{config_type}'", rid)
            elif not isinstance(sqft, (int, float)) or sqft <= 0:
                report.add_error('configurations',
                    f"Invalid square footage: {sqft}", rid)
            elif sqft < 100:
                report.add_warning('configurations',
                    f"Very small square footage: {sqft} sqft - please verify", rid)
            elif sqft > 10000:
                report.add_warning('configurations',
                    f"Very large square footage: {sqft} sqft - please verify", rid)
            
            # 7. Validate price
            price = fields.get('Price')
            if not price:
                report.add_warning('configurations',
                    f"Missing price for '{config_type}'", rid)
            elif not isinstance(price, (int, float, Decimal)) or price < 0:
                report.add_error('configurations',
                    f"Invalid price value: {price}", rid)
            elif price < 1000:
                report.add_warning('configurations',
                    f"Suspiciously low price: ${price} - please verify", rid)
            
            # 8. Check logical consistency
            if bedrooms and bathrooms and bedrooms < bathrooms:
                report.add_warning('configurations',
                    f"More bathrooms ({bathrooms}) than bedrooms ({bedrooms}) - unusual but verify", 
                    rid)
        
        # 9. Check for duplicate configurations within same property
        for prop_id, configs in config_by_property.items():
            seen_types = {}
            for cfg in configs:
                cfg_type = cfg['type'].lower() if cfg['type'] else ''
                if cfg_type in seen_types:
                    report.add_error('configurations',
                        f"Duplicate configuration type '{cfg['type']}' for same property",
                        cfg['id'])
                seen_types[cfg_type] = cfg['id']
    
    # ==================== IMAGE VALIDATIONS ====================
    
    def validate_images(self, records: List[Dict], prop_records: List[Dict], 
                       report: DataValidationReport):
        self.stdout.write("🖼️  Validating Images...")
        
        prop_ids = {r.get('id') for r in prop_records}
        images_by_property = defaultdict(list)
        
        for rec in records:
            rid = rec.get('id')
            fields = rec.get('fields', {})
            
            # 1. Check for linked property
            linked_props = fields.get('Property', [])
            if not linked_props:
                report.add_error('images',
                    f"Image not linked to any property", rid)
                continue
            
            prop_id = linked_props[0]
            
            # 2. Check if linked property exists
            if prop_id not in prop_ids:
                report.add_error('images',
                    f"Linked to non-existent property: {prop_id}", rid)
                continue
            
            # 3. Check for image attachment
            image_attachments = fields.get('Image', [])
            if not image_attachments:
                report.add_error('images',
                    f"Image record has no actual image file attached", rid)
            else:
                # Validate image URLs
                for idx, img in enumerate(image_attachments):
                    url = img.get('url', '')
                    if not url:
                        report.add_error('images',
                            f"Image attachment {idx+1} has no URL", rid)
                    elif not url.startswith('https://'):
                        report.add_warning('images',
                            f"Image URL doesn't use HTTPS: {url[:50]}...", rid)
            
            # 4. Check alt text
            alt_text = fields.get('Alt Text', '').strip()
            if not alt_text:
                report.add_warning('images',
                    f"Missing alt text (important for accessibility)", rid)
            
            # 5. Check order
            order = fields.get('Order')
            if order is None:
                report.add_warning('images',
                    f"Missing order value - images may display randomly", rid)
            elif not isinstance(order, (int, float)):
                report.add_error('images',
                    f"Invalid order value: {order}", rid)
            
            images_by_property[prop_id].append({
                'id': rid,
                'order': order if order is not None else 999
            })
        
        # 6. Check for duplicate orders within same property
        for prop_id, images in images_by_property.items():
            orders = [img['order'] for img in images]
            if len(orders) != len(set(orders)):
                report.add_warning('images',
                    f"Property has duplicate image order values - images may not display as expected")
        
        # 7. Check properties with no images
        props_with_images = set(images_by_property.keys())
        props_without_images = prop_ids - props_with_images
        
        if props_without_images:
            for prop_id in props_without_images:
                prop_name = self.get_property_name(prop_records, prop_id)
                report.add_warning('images',
                    f"Property '{prop_name}' has no images", prop_id, prop_name)
    
    # ==================== AMENITY VALIDATIONS ====================
    
    def validate_amenities(self, records: List[Dict], prop_records: List[Dict], 
                          report: DataValidationReport):
        self.stdout.write("✨ Validating Amenities...")
        
        prop_ids = {r.get('id') for r in prop_records}
        amenities_by_property = defaultdict(list)
        
        for rec in records:
            rid = rec.get('id')
            fields = rec.get('fields', {})
            
            # 1. Check for linked property
            linked_props = fields.get('Property', [])
            if not linked_props:
                report.add_error('amenities',
                    f"Amenity not linked to any property", rid)
                continue
            
            prop_id = linked_props[0]
            
            # 2. Check if linked property exists
            if prop_id not in prop_ids:
                report.add_error('amenities',
                    f"Linked to non-existent property: {prop_id}", rid)
                continue
            
            # 3. Check amenity name/text
            amenity_text = fields.get('Amenities') or fields.get('Name', '')
            if not amenity_text or not amenity_text.strip():
                report.add_error('amenities',
                    f"Empty amenity name", rid)
                continue
            
            # 4. Parse comma-separated amenities
            amenity_names = [a.strip() for a in amenity_text.split(',') if a.strip()]
            
            if not amenity_names:
                report.add_error('amenities',
                    f"No valid amenity names found", rid)
            
            for name in amenity_names:
                # 5. Check for very long names (DB limit is 100)
                if len(name) > 100:
                    report.add_warning('amenities',
                        f"Amenity name too long ({len(name)} chars): '{name[:50]}...' - will be truncated", 
                        rid)
                
                # 6. Check for suspicious patterns
                if name.lower() in ['n/a', 'na', 'none', 'nil', 'null', 'test']:
                    report.add_warning('amenities',
                        f"Suspicious amenity name: '{name}' - should this be removed?", rid)
                
                amenities_by_property[prop_id].append(name.lower())
        
        # 7. Check for duplicate amenities within same property
        for prop_id, amenity_list in amenities_by_property.items():
            duplicates = [a for a in set(amenity_list) if amenity_list.count(a) > 1]
            if duplicates:
                prop_name = self.get_property_name(prop_records, prop_id)
                report.add_warning('amenities',
                    f"Property '{prop_name}' has duplicate amenities: {', '.join(duplicates)}",
                    prop_id, prop_name)
        
        # 8. Check properties with very few amenities
        for prop_id, amenity_list in amenities_by_property.items():
            if len(amenity_list) < 2:
                prop_name = self.get_property_name(prop_records, prop_id)
                report.add_warning('amenities',
                    f"Property '{prop_name}' has very few amenities ({len(amenity_list)}) - consider adding more",
                    prop_id, prop_name)
    
    # ==================== RELATIONSHIP VALIDATIONS ====================
    
    def validate_relationships(self, prop_records: List[Dict], cfg_records: List[Dict],
                              img_records: List[Dict], amen_records: List[Dict],
                              report: DataValidationReport):
        self.stdout.write("🔗 Validating Relationships...")
        
        prop_ids = {r.get('id') for r in prop_records}
        
        # Count child records per property
        configs_by_prop = defaultdict(int)
        images_by_prop = defaultdict(int)
        amenities_by_prop = defaultdict(int)
        
        for cfg in cfg_records:
            linked = cfg.get('fields', {}).get('Property', [])
            if linked:
                configs_by_prop[linked[0]] += 1
        
        for img in img_records:
            linked = img.get('fields', {}).get('Property', [])
            if linked:
                images_by_prop[linked[0]] += 1
        
        for amen in amen_records:
            linked = amen.get('fields', {}).get('Property', [])
            if linked:
                amenities_by_prop[linked[0]] += 1
        
        # Check each property
        for prop in prop_records:
            prop_id = prop.get('id')
            prop_name = prop.get('fields', {}).get('Name', 'Unnamed')
            is_active = prop.get('fields', {}).get('Is Active', True)
            
            # Only warn about missing data for active properties
            if is_active:
                # Check for properties with no configurations
                if configs_by_prop[prop_id] == 0:
                    report.add_warning('relationships',
                        f"Active property '{prop_name}' has no configurations",
                        prop_id, prop_name)
                
                # Check for properties with no images
                if images_by_prop[prop_id] == 0:
                    report.add_warning('relationships',
                        f"Active property '{prop_name}' has no images",
                        prop_id, prop_name)
                
                # Check for properties with no amenities
                if amenities_by_prop[prop_id] == 0:
                    report.add_warning('relationships',
                        f"Active property '{prop_name}' has no amenities",
                        prop_id, prop_name)
                
                # Check for suspiciously low counts
                if images_by_prop[prop_id] > 0 and images_by_prop[prop_id] < 3:
                    report.add_warning('relationships',
                        f"Property '{prop_name}' has only {images_by_prop[prop_id]} image(s) - consider adding more",
                        prop_id, prop_name)
    
    # ==================== HELPER METHODS ====================
    
    def is_valid_latitude(self, lat) -> bool:
        try:
            val = float(lat)
            return -90 <= val <= 90
        except (TypeError, ValueError):
            return False
    
    def is_valid_longitude(self, lon) -> bool:
        try:
            val = float(lon)
            return -180 <= val <= 180
        except (TypeError, ValueError):
            return False
    
    def is_valid_phone(self, phone: str) -> bool:
        # Basic phone validation - adjust for your region
        digits = re.sub(r'[^\d]', '', phone)
        return len(digits) >= 10
    
    def get_property_name(self, prop_records: List[Dict], prop_id: str) -> str:
        for prop in prop_records:
            if prop.get('id') == prop_id:
                return prop.get('fields', {}).get('Name', 'Unknown')
        return 'Unknown'
    
    # ==================== REPORT DISPLAY ====================
    
    def display_report(self, report: DataValidationReport):
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS("📊 VALIDATION REPORT"))
        self.stdout.write("="*80 + "\n")
        
        # Display errors
        if report.has_errors():
            self.stdout.write(self.style.ERROR(f"❌ ERRORS FOUND: {sum(len(v) for v in report.errors.values())}"))
            self.stdout.write(self.style.ERROR("These issues should be fixed before syncing:\n"))
            
            for category, errors in sorted(report.errors.items()):
                self.stdout.write(self.style.ERROR(f"\n  [{category.upper()}] - {len(errors)} error(s)"))
                for err in errors[:10]:  # Show first 10
                    record_info = f" (ID: {err['record_id'][:10]}...)" if err['record_id'] else ""
                    name_info = f" [{err['record_name']}]" if err['record_name'] else ""
                    self.stdout.write(f"    • {err['message']}{name_info}{record_info}")
                if len(errors) > 10:
                    self.stdout.write(f"    ... and {len(errors) - 10} more")
        else:
            self.stdout.write(self.style.SUCCESS("✅ No critical errors found!"))
        
        # Display warnings
        if self.show_warnings:
            self.stdout.write("\n")
            if report.has_warnings():
                self.stdout.write(self.style.WARNING(f"⚠️  WARNINGS: {sum(len(v) for v in report.warnings.values())}"))
                self.stdout.write(self.style.WARNING("These are non-critical but should be reviewed:\n"))
                
                for category, warnings in sorted(report.warnings.items()):
                    self.stdout.write(self.style.WARNING(f"\n  [{category.upper()}] - {len(warnings)} warning(s)"))
                    for warn in warnings[:10]:
                        record_info = f" (ID: {warn['record_id'][:10]}...)" if warn['record_id'] else ""
                        name_info = f" [{warn['record_name']}]" if warn['record_name'] else ""
                        self.stdout.write(f"    • {warn['message']}{name_info}{record_info}")
                    if len(warnings) > 10:
                        self.stdout.write(f"    ... and {len(warnings) - 10} more")
            else:
                self.stdout.write(self.style.SUCCESS("✅ No warnings found!"))
        
        # Summary
        self.stdout.write("\n" + "="*80)
        total_errors = sum(len(v) for v in report.errors.values())
        total_warnings = sum(len(v) for v in report.warnings.values())
        
        if total_errors > 0:
            self.stdout.write(self.style.ERROR(f"❌ Validation failed: {total_errors} error(s), {total_warnings} warning(s)"))
            self.stdout.write(self.style.ERROR("Please fix critical errors before syncing."))
        elif total_warnings > 0:
            self.stdout.write(self.style.WARNING(f"⚠️  Validation passed with warnings: {total_warnings} warning(s)"))
            self.stdout.write(self.style.WARNING("Consider reviewing warnings before syncing."))
        else:
            self.stdout.write(self.style.SUCCESS("✅ Validation passed! Data looks good."))
        
        self.stdout.write("="*80 + "\n")