import os
import logging
import requests
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.db import transaction
from django.core.files.base import ContentFile
from pyairtable import Table
from decouple import config
from django.core.cache import cache
from properties.models import Property, PropertyConfiguration, PropertyImage, PropertyAmenity
from django.utils import timezone
from datetime import datetime
import time
from properties.tasks import download_file_task, download_image_task
log = logging.getLogger(__name__)

def env(name, default=None):
    v = os.environ.get(name)
    return v if v is not None else default

def to_decimal(v):
    if v in (None, "", [], {}):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None
    
def to_date(v):
    if v in (None, "", [], {}):
        return None
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None

def first_attachment(attachments):
    if not attachments:
        return None
    return attachments[0]

def extract_records_from_response(table_data):
    records = []
    try:
        for item in table_data.iterate(max_records=100):  # Explicitly limit per page
            if isinstance(item, dict):
                records.append(item)
            elif isinstance(item, list):
                records.extend(item)
    except Exception as e:
        print(f"iterate() failed: {e}, falling back to all()")
        records = table_data.all(max_records=1000)  # Fallback with limit
    return records

class Command(BaseCommand):
    help = "Fetch data from Airtable and sync to Django models, deleting properties not in Airtable."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making changes to database (test mode).'
        )
        parser.add_argument(
            '--no-files',
            action='store_true',
            help='Skip downloading files (brochures, thumbnails, images).'
        )
        parser.add_argument(
            '--cache-only',
            action='store_true',
            help='Only cache data, don\'t sync to database.'
        )

    def handle(self, *args, **options):
        print("=" * 50)
        print("STARTING AIRTABLE DATA FETCH AND SYNC")
        print("=" * 50)

        dry_run = options.get('dry_run', False)
        no_files = options.get('no_files', False)
        cache_only = options.get('cache_only', False)

        if dry_run:
            print("🔍 DRY RUN MODE - No database changes will be made")
        if no_files:
            print("📁 FILE DOWNLOAD DISABLED")
        if cache_only:
            print("💾 CACHE ONLY MODE - Database sync disabled")

        #token = 'patFtmrCvhrJq4htC.c1a887af3fd1d826944534a68c822caf0bedc92b8a0a8246782280c18597d800' # For my own airtable account
        #token = 'patE38Xzz7fKDNsGL.2cd7f247fc218496d101af45a5627be6707ddb8d3762cc521117f5288c3b4438' # For CW airtable account
        #base_id = 'appkkHHDh5A21JhlK'
        #base_id = 'appLocaWHQNhMuYSH' # For CW airtable account
        
        token = config('AIRTABLE_TOKEN', default=None)
        base_id = config('AIRTABLE_BASE_ID', default=None)

        tbl_props = config('AIRTABLE_TABLE_PROPERTIES', default='Property')
        tbl_cfgs  = config('AIRTABLE_TABLE_CONFIGS',    default='Configuration')
        tbl_imgs  = config('AIRTABLE_TABLE_IMAGES',     default='Images')
        tbl_amen  = config('AIRTABLE_TABLE_AMENITIES',  default='Amenities')
        
        
        print('airtable is ', tbl_amen)

        print(f"Token: {'*' * (len(token) - 4) + token[-4:] if token else 'NOT SET'}")
        print(f"Base ID: {base_id}")
        print(f"Properties table: {tbl_props}")

        if not token or not base_id:
            self.stderr.write(self.style.ERROR("AIRTABLE_TOKEN and AIRTABLE_BASE_ID are required"))
            return

        try:
            props = Table(token, base_id, tbl_props)
            cfgs = Table(token, base_id, tbl_cfgs)
            imgs = Table(token, base_id, tbl_imgs)
            amens = Table(token, base_id, tbl_amen)

            print("\nStarting property fetch...")
            prop_map = self.fetch_properties(props)
            print(f"Properties fetched: {len(prop_map)}")

            print("Starting configuration fetch...")
            config_data = self.fetch_configurations(cfgs, prop_map)
            print(f"Configurations fetched: {len(config_data)}")

            print("Starting image fetch...")
            image_data = self.fetch_images(imgs, prop_map)
            print(f"Images fetched: {len(image_data)}")

            print("Starting amenity fetch...")
            amenity_data = self.fetch_amenities(amens, prop_map)
            print(f"Amenities fetched: {len(amenity_data)}")

            result = {
                'properties': list(prop_map.values()),
                'configurations': config_data,
                'images': image_data,
                'amenities': amenity_data
            }

            # Store in cache
            cache.set('airtable_data', result, timeout=3600)
            print('✅ Cache stored successfully')

            # Sync to database if not cache-only mode
            if not cache_only:
                print("\n" + "=" * 50)
                print("STARTING DATABASE SYNC")
                print("=" * 50)
                self.sync_to_database(result, dry_run=dry_run, no_files=no_files)

            self.stdout.write(self.style.SUCCESS("✅ Airtable data fetch and sync complete."))
            time.sleep(0.2)  # Respect 5 req/sec limit after each table fetch

        except Exception as e:
            print(f"❌ ERROR during fetch: {e}")
            import traceback
            traceback.print_exc()
            raise

    def sync_to_database(self, data, dry_run=False, no_files=False):
        """Sync fetched data to Django models and delete missing properties"""
        try:
            with transaction.atomic():
                # Collect all Airtable IDs from fetched properties
                airtable_ids = {prop['airtable_id'] for prop in data['properties']}
                
                print(f"🔄 Syncing {len(data['properties'])} properties...")
                self.sync_properties(data['properties'], dry_run=dry_run, no_files=no_files)
                
                print(f"🔄 Syncing {len(data['configurations'])} configurations...")
                self.sync_configurations(data['configurations'], dry_run=dry_run)
                
                print(f"🔄 Syncing {len(data['images'])} images...")
                self.sync_images(data['images'], dry_run=dry_run, no_files=no_files)
                
                print(f"🔄 Syncing {len(data['amenities'])} amenities...")
                self.sync_amenities(data['amenities'], dry_run=dry_run)

                # Delete properties missing from Airtable
                if not dry_run:
                    print("🔍 Checking for properties missing from Airtable...")
                    existing_properties = Property.objects.exclude(airtable_id__in=airtable_ids)
                    count = existing_properties.count()
                    if count > 0:
                        print(f"🗑️ Deleting {count} properties missing from Airtable...")
                        existing_properties.delete()
                        print(f"✅ Deleted {count} missing properties")

                if dry_run:
                    raise transaction.TransactionManagementError("🔍 Dry run - rolling back changes")

                print("✅ Database sync completed successfully!")

        except transaction.TransactionManagementError:
            if dry_run:
                print("🔍 Dry run completed - no actual changes made")
        except Exception as e:
            print(f"❌ Database sync error: {str(e)}")
            raise

    def sync_properties(self, properties_data, dry_run=False, no_files=False):
        """Sync properties to Django Property model"""
        for prop_data in properties_data:
            try:
                airtable_id = prop_data['airtable_id']
                
                # Map luxury status
                luxury_mapping = {
                    'Luxurious': 'luxurious',
                    'Non Luxurious': 'non_luxurious',
                    'luxurious': 'luxurious',
                    'non_luxurious': 'non_luxurious'
                }
                
                property_fields = {
                    'name': prop_data['name'],
                    'slug': prop_data['slug'],
                    'address': prop_data['address'],
                    'description': prop_data['description'],
                    'latitude': prop_data['latitude'],
                    'longitude': prop_data['longitude'],
                    'contact_name': prop_data['contact_name'],
                    'contact_phone': prop_data['contact_phone'],
                    'is_active': prop_data['is_active'],
                    'luxury_status': luxury_mapping.get(prop_data['luxury_status'], 'non_luxurious'),
                    'completion_date': prop_data['completion_date']
                }

                if dry_run:
                    print(f"🔍 Would sync property: {prop_data['name']}")
                    continue

                try:
                    property_obj = Property.objects.get(airtable_id=airtable_id)
                    changed = False
                    for field, value in property_fields.items():
                        if getattr(property_obj, field) != value:
                            setattr(property_obj, field, value)
                            changed = True
                    if changed:
                        property_obj.last_synced_at = timezone.now()
                        property_obj.save()
                        action = "🔄 Updated"
                    else:
                        action = "✅ No changes"
                except Property.DoesNotExist:
                    property_obj = Property(airtable_id=airtable_id, **property_fields)
                    property_obj.last_synced_at = timezone.now()
                    property_obj.save()
                    action = "✅ Created"

                print(f"{action} property: {property_obj.name}")

                # Download and save files
                if not no_files:
                    self.handle_property_files(property_obj, prop_data)

            except Exception as e:
                print(f"❌ Error syncing property {prop_data.get('name', 'Unknown')}: {str(e)}")
                continue

    def sync_configurations(self, configurations_data, dry_run=False):
        """Sync configurations to Django PropertyConfiguration model"""
        for config_data in configurations_data:
            try:
                if dry_run:
                    print(f"🔍 Would sync configuration: {config_data['type']}")
                    continue

                # Find the property
                property_obj = self.get_property_by_airtable_id(config_data['property_id'])
                if not property_obj:
                    print(f"❌ Property not found for configuration: {config_data['property_id']}")
                    continue

                config_fields = {
                    'type': config_data['type'],
                    'bedrooms': config_data['bedrooms'],
                    'bathrooms': config_data['bathrooms'],
                    'square_footage': config_data['square_footage'],
                    'price': config_data['price'],
                    'is_available': config_data['is_available']
                }

                try:
                    config_obj = PropertyConfiguration.objects.get(airtable_id=config_data['airtable_id'])
                    changed = False
                    for field, value in config_fields.items():
                        if getattr(config_obj, field) != value:
                            setattr(config_obj, field, value)
                            changed = True
                    if changed:
                        config_obj.last_synced_at = timezone.now()
                        config_obj.save()
                        action = "🔄 Updated"
                    else:
                        action = "✅ No changes"
                except PropertyConfiguration.DoesNotExist:
                    config_obj = PropertyConfiguration(
                        airtable_id=config_data['airtable_id'],
                        property=property_obj,
                        **config_fields
                    )
                    config_obj.last_synced_at = timezone.now()
                    config_obj.save()
                    action = "✅ Created"

                print(f"{action} configuration: {property_obj.name} - {config_data['type']}")

            except Exception as e:
                print(f"❌ Error syncing configuration: {str(e)}")
                continue

    def sync_images(self, images_data, dry_run=False, no_files=False):
        """Sync images to Django PropertyImage model"""
        for image_data in images_data:
            try:
                if dry_run:
                    print(f"🔍 Would sync image: {image_data['alt_text']}")
                    continue

                property_obj = self.get_property_by_airtable_id(image_data['property_id'])
                if not property_obj:
                    print(f"❌ Property not found for image: {image_data['property_id']}")
                    continue

                existing_image = PropertyImage.objects.filter(airtable_id=image_data['airtable_id']).first()

                if existing_image:
                    changed = False
                    if existing_image.alt_text != image_data['alt_text']:
                        existing_image.alt_text = image_data['alt_text']
                        changed = True
                    if existing_image.order != image_data['order']:
                        existing_image.order = image_data['order']
                        changed = True
                    file_changed = False
                    if not no_files and not existing_image.image and image_data.get('image_url'):
                        success = self.download_and_save_image(existing_image, image_data['image_url'])
                        if success:
                            file_changed = True

                    if changed or file_changed:
                        existing_image.last_synced_at = timezone.now()
                        existing_image.save()
                        action = "🔄 Updated"
                    else:
                        action = "✅ No changes"
                    print(f"{action} image for: {property_obj.name} (Order: {image_data['order']})")
                else:
                    image_fields = {
                        'airtable_id': image_data['airtable_id'],
                        'property': property_obj,
                        'alt_text': image_data['alt_text'],
                        'order': image_data['order'],
                        'attachment_index': image_data['attachment_index'],
                        'original_record_id': image_data['original_record_id']
                    }

                    image_obj = PropertyImage(**image_fields)
                    image_obj.last_synced_at = timezone.now()

                    if not no_files and image_data.get('image_url'):
                        success = self.download_and_save_image(image_obj, image_data['image_url'])
                        if success:
                            print(f"✅ Downloaded image for: {property_obj.name} (Order: {image_data['order']})")
                        else:
                            print(f"⚠️ Created image record but failed to download file for: {property_obj.name}")
                    else:
                        print(f"✅ Created image record for: {property_obj.name} (Order: {image_data['order']})")

                    image_obj.save()
                    print(f"✅ Created image for: {property_obj.name} (Order: {image_data['order']})")

            except Exception as e:
                print(f"❌ Error syncing image: {str(e)}")
                continue

    def sync_amenities(self, amenities_data, dry_run=False):
        """Sync amenities to Django PropertyAmenity model"""
        for amenity_data in amenities_data:
            try:
                if dry_run:
                    print(f"🔍 Would sync amenity: {amenity_data['name']}")
                    continue

                property_obj = self.get_property_by_airtable_id(amenity_data['property_id'])
                if not property_obj:
                    print(f"❌ Property not found for amenity: {amenity_data['property_id']}")
                    continue

                amenity_fields = {
                    'name': amenity_data['name']
                }

                amenity_obj, created = PropertyAmenity.objects.get_or_create(
                    airtable_id=amenity_data['airtable_id'],
                    property=property_obj,
                    defaults=amenity_fields
                )

                if created:
                    amenity_obj.last_synced_at = timezone.now()
                    amenity_obj.save()
                    action = "✅ Created"
                else:
                    changed = False
                    if amenity_obj.name != amenity_data['name']:
                        amenity_obj.name = amenity_data['name']
                        changed = True
                    if changed:
                        amenity_obj.last_synced_at = timezone.now()
                        amenity_obj.save()
                        action = "🔄 Updated"
                    else:
                        action = "✅ No changes"

                print(f"{action} amenity: {property_obj.name} - {amenity_data['name']}")

            except Exception as e:
                print(f"❌ Error syncing amenity: {str(e)}")
                continue

    def get_property_by_airtable_id(self, airtable_id):
        """Helper to get Property by Airtable ID"""
        try:
            return Property.objects.get(airtable_id=airtable_id)
        except Property.DoesNotExist:
            cached_data = cache.get('airtable_data', {})
            properties = cached_data.get('properties', [])
            for prop in properties:
                if prop['airtable_id'] == airtable_id:
                    try:
                        return Property.objects.get(slug=prop['slug'])
                    except Property.DoesNotExist:
                        return None
            return None

    def handle_property_files(self, property_obj, prop_data):
        if prop_data.get('brochure_url') and not property_obj.brochure:
            download_file_task.delay(property_obj, prop_data['brochure_url'], 'brochure', 'brochure')
        if prop_data.get('thumbnail_url') and not property_obj.thumbnail:
            download_file_task.delay(property_obj, prop_data['thumbnail_url'], 'thumbnail', 'thumbnail')

    def download_and_save_image(self, image_obj, image_url):
        if image_url:
            download_image_task.delay(image_obj, image_url)
            return True
        return False

    def download_file(self, url, timeout=30):
        """Download file from URL"""
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            print(f"⚠️ Download failed for {url}: {str(e)}")
            return None

    def fetch_properties(self, props_table):
        prop_map = {}
        seen_ids = set()
        processed_count = 0

        records = extract_records_from_response(props_table)
        print(f"Retrieved {len(records)} property records from Airtable")

        if not records:
            print("No property records found!")
            return {}

        for i in range(0, len(records), 100):  # Process 100 records at a time
            batch = records[i:i + 100]
            for rec in batch:
                try:
                    if not isinstance(rec, dict) or 'id' not in rec:
                        print(f"Skipping invalid record {i + (rec - batch[0] + 1)}: {type(rec)}")
                        continue

                    rid = rec["id"]
                    f = rec.get("fields", {})
                    seen_ids.add(rid)

                    print(f"\nProcessing property {processed_count + 1}/{len(records)}: {rid}")

                    name = f.get("Name") or f"Unnamed Property {rid}"
                    print(f"Property name: '{name}'")

                    slug_final = f.get("Slug (Final)") or f.get("Slug") or slugify(name)
                    address = f.get("Address") or ""
                    description = f.get("Description") or ""
                    lat = to_decimal(f.get("Latitude"))
                    lng = to_decimal(f.get("Longitude"))
                    contact_name = f.get("Contact Name") or ""
                    contact_phone = f.get("Contact Phone") or ""
                    luxury_status = f.get("Luxury Status") or "non_luxurious"
                    is_active = bool(f.get("Is Active"))
                    completion_date = to_date(f.get("Completion Date"))

                    brochure_att = first_attachment(f.get("Brochure"))
                    thumb_att = first_attachment(f.get("Thumbnail") or f.get("Thumbnails"))

                    prop_data = {
                        'airtable_id': rid,
                        'name': name,
                        'slug': slug_final,
                        'address': address,
                        'description': description,
                        'latitude': lat,
                        'longitude': lng,
                        'contact_name': contact_name,
                        'contact_phone': contact_phone,
                        'luxury_status': luxury_status,
                        'is_active': is_active,
                        'brochure_url': brochure_att.get("url") if brochure_att else None,
                        'thumbnail_url': thumb_att.get("url") if thumb_att else None,
                        'completion_date': completion_date
                    }

                    prop_map[rid] = prop_data
                    processed_count += 1

                except Exception as e:
                    print(f"Error processing property record {i + (rec - batch[0] + 1)}: {e}")
                    continue

                # Clear memory every 500 records
                if processed_count % 500 == 0:
                    import gc
                    gc.collect()
                    print(f"🗑️ Cleared memory after processing {processed_count} properties")

        print(f"Successfully processed {processed_count} properties")
        return prop_map

    def fetch_configurations(self, cfgs_table, prop_map):
        seen_ids = set()
        config_data = []

        records = extract_records_from_response(cfgs_table)
        print(f"Retrieved {len(records)} configuration records")

        for i in range(0, len(records), 100):  # Process 100 records at a time
            batch = records[i:i + 100]
            for rec in batch:
                try:
                    if not isinstance(rec, dict) or 'id' not in rec:
                        print(f"Skipping invalid configuration record: {rec}")
                        continue

                    rid = rec["id"]
                    f = rec.get("fields", {})
                    seen_ids.add(rid)

                    linked = f.get("Property") or []
                    if not linked:
                        print(f"Configuration {rid} has no linked property")
                        continue
                    prop_id = linked[0]
                    if prop_id not in prop_map:
                        print(f"Configuration {rid} links to unknown property {prop_id}")
                        continue

                    config = {
                        'airtable_id': rid,
                        'property_id': prop_id,
                        'type': f.get("Type") or "",
                        'bedrooms': int(f.get("Bedrooms") or 0),
                        'bathrooms': int(f.get("Bathrooms") or 1),
                        'square_footage': int(f.get("Square Footage") or 0),
                        'price': to_decimal(f.get("Price")),
                        'is_available': bool(f.get("Is Available"))
                    }

                    config_data.append(config)
                    print(f"Processed configuration for property {prop_id}")

                except Exception as e:
                    print(f"Error processing configuration {rid}: {e}")
                    continue

                # Clear memory every 500 records
                if len(config_data) % 500 == 0:
                    import gc
                    gc.collect()
                    print(f"🗑️ Cleared memory after processing {len(config_data)} configurations")

        return config_data

    def fetch_images(self, imgs_table, prop_map):
        seen_ids = set()
        image_data = []

        records = extract_records_from_response(imgs_table)
        print(f"Retrieved {len(records)} image records")

        for i in range(0, len(records), 100):  # Process 100 records at a time
            batch = records[i:i + 100]
            for rec in batch:
                try:
                    if not isinstance(rec, dict) or 'id' not in rec:
                        print(f"Skipping invalid image record: {rec}")
                        continue

                    rid = rec["id"]
                    f = rec.get("fields", {})
                    seen_ids.add(rid)

                    linked = f.get("Property") or []
                    if not linked:
                        print(f"Image {rid} has no linked property")
                        continue
                    prop_id = linked[0]
                    if prop_id not in prop_map:
                        print(f"Image {rid} links to unknown property {prop_id}")
                        continue

                    attachments = f.get("Image") or []
                    alt_text = f.get("Alt Text") or ""
                    order = int(f.get("Order") or 0)

                    print(f"Record {rid} has {len(attachments)} attachments")

                    if attachments and isinstance(attachments, list):
                        for j, attachment in enumerate(attachments):
                            if attachment and isinstance(attachment, dict) and attachment.get("url"):
                                unique_image_id = f"{rid}_{j}" if len(attachments) > 1 else rid
                                
                                image = {
                                    'airtable_id': unique_image_id,
                                    'property_id': prop_id,
                                    'image_url': attachment.get("url"),
                                    'alt_text': f"{alt_text} (Image {j+1})" if len(attachments) > 1 and alt_text else alt_text,
                                    'order': order + j,
                                    'attachment_index': j,
                                    'original_record_id': rid
                                }

                                image_data.append(image)
                                print(f"Added image {j+1}/{len(attachments)} for property {prop_id}: {attachment.get('url')}")

                except Exception as e:
                    print(f"Error processing image {rid}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

                # Clear memory every 500 records
                if len(image_data) % 500 == 0:
                    import gc
                    gc.collect()
                    print(f"🗑️ Cleared memory after processing {len(image_data)} images")

        print(f"Total images processed: {len(image_data)}")
        return image_data

    def fetch_amenities(self, amen_table, prop_map):
        seen_ids = set()
        amenity_data = []

        records = extract_records_from_response(amen_table)
        print(f"Retrieved {len(records)} amenity records")

        for i in range(0, len(records), 100):  # Process 100 records at a time
            batch = records[i:i + 100]
            for rec in batch:
                try:
                    if not isinstance(rec, dict) or 'id' not in rec:
                        print(f"Skipping invalid amenity record: {rec}")
                        continue

                    rid = rec["id"]
                    f = rec.get("fields", {})
                    seen_ids.add(rid)

                    linked = f.get("Property") or []
                    if not linked:
                        print(f"Amenity {rid} has no linked property")
                        continue
                    prop_id = linked[0]
                    if prop_id not in prop_map:
                        print(f"Amenity {rid} links to unknown property {prop_id}")
                        continue

                    amenities_text = f.get("Amenities") or f.get("Name") or ""
                    if not amenities_text:
                        print(f"Amenity {rid} has no name")
                        continue

                    amenity_names = [name.strip() for name in amenities_text.split(',') if name.strip()]
                    for amenity_name in amenity_names:
                        amenity_id = f"{rid}_{amenity_name.replace(' ', '_').lower()}"
                        amenity = {
                            'airtable_id': amenity_id,
                            'property_id': prop_id,
                            'name': amenity_name
                        }
                        amenity_data.append(amenity)
                        print(f"Processed amenity: {amenity_name} for property {prop_id}")

                except Exception as e:
                    print(f"Error processing amenity {rid}: {e}")
                    continue

                # Clear memory every 500 records
                if len(amenity_data) % 500 == 0:
                    import gc
                    gc.collect()
                    print(f"🗑️ Cleared memory after processing {len(amenity_data)} amenities")

        return amenity_data