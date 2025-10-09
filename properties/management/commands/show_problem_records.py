"""
Management command to show detailed info about problem records
Usage: python manage.py show_problem_records
"""
from django.core.management.base import BaseCommand
from decouple import config
from pyairtable import Table
from collections import defaultdict


class Command(BaseCommand):
    help = "Show detailed information about problem records from Airtable validation"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--record-id',
            type=str,
            help='Show specific record by ID'
        )
    
    def handle(self, *args, **options):
        pat = config("AIRTABLE_TOKEN")
        base_id = config("AIRTABLE_BASE_ID")
        
        if not pat or not base_id:
            self.stderr.write(self.style.ERROR("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set"))
            return
        
        tbl_props = config("AIRTABLE_TABLE_PROPERTIES", "Property")
        tbl_cfgs = config("AIRTABLE_TABLE_CONFIGS", "Configuration")
        tbl_imgs = config("AIRTABLE_TABLE_IMAGES", "Images")
        
        props_t = Table(pat, base_id, tbl_props)
        cfgs_t = Table(pat, base_id, tbl_cfgs)
        imgs_t = Table(pat, base_id, tbl_imgs)
        
        specific_record = options.get('record_id')
        
        if specific_record:
            self.show_specific_record(specific_record, props_t, cfgs_t, imgs_t)
            return
        
        self.stdout.write(self.style.SUCCESS("🔍 Finding Problem Records...\n"))
        
        # Fetch all data
        prop_records = list(props_t.all())
        cfg_records = list(cfgs_t.all())
        img_records = list(imgs_t.all())
        
        # Create property lookup
        prop_lookup = {p['id']: p.get('fields', {}).get('Name', 'Unnamed') for p in prop_records}
        
        self.stdout.write("="*80)
        self.stdout.write(self.style.ERROR("❌ CRITICAL ERRORS"))
        self.stdout.write("="*80 + "\n")
        
        # 1. Find configurations with missing type
        self.stdout.write(self.style.WARNING("1️⃣  Configurations with Missing Type:"))
        missing_type_count = 0
        for cfg in cfg_records:
            cfg_type = cfg.get('fields', {}).get('Type', '').strip()
            if not cfg_type:
                missing_type_count += 1
                self.show_configuration_detail(cfg, prop_lookup)
        
        if missing_type_count == 0:
            self.stdout.write(self.style.SUCCESS("   ✅ No issues found!"))
        self.stdout.write("")
        
        # 2. Find duplicate configuration types
        self.stdout.write(self.style.WARNING("2️⃣  Duplicate Configuration Types:"))
        config_by_property = defaultdict(list)
        for cfg in cfg_records:
            linked = cfg.get('fields', {}).get('Property', [])
            if linked:
                prop_id = linked[0]
                cfg_type = cfg.get('fields', {}).get('Type', '').strip().lower()
                if cfg_type:
                    config_by_property[prop_id].append({
                        'id': cfg['id'],
                        'type': cfg.get('fields', {}).get('Type', ''),
                        'bedrooms': cfg.get('fields', {}).get('Bedrooms'),
                        'bathrooms': cfg.get('fields', {}).get('Bathrooms'),
                        'sqft': cfg.get('fields', {}).get('Square Footage'),
                        'price': cfg.get('fields', {}).get('Price'),
                    })
        
        duplicate_count = 0
        for prop_id, configs in config_by_property.items():
            types_seen = {}
            for cfg in configs:
                cfg_type_lower = cfg['type'].lower()
                if cfg_type_lower in types_seen:
                    duplicate_count += 1
                    prop_name = prop_lookup.get(prop_id, 'Unknown Property')
                    self.stdout.write(self.style.ERROR(f"\n   🏢 Property: {prop_name}"))
                    self.stdout.write(f"   📋 Duplicate Type: '{cfg['type']}'")
                    self.stdout.write(f"   🔑 Record ID: {cfg['id']}")
                    self.stdout.write(f"   🛏️  Details: {cfg['bedrooms']} bed / {cfg['bathrooms']} bath / {cfg['sqft']} sqft / ${cfg['price']}")
                    self.stdout.write(self.style.WARNING(f"   💡 Previous Record ID: {types_seen[cfg_type_lower]}"))
                    self.stdout.write(f"   ⚠️  Action: Delete one or rename to make unique (e.g., '{cfg['type']} - Unit A')")
                    self.stdout.write("")
                else:
                    types_seen[cfg_type_lower] = cfg['id']
        
        if duplicate_count == 0:
            self.stdout.write(self.style.SUCCESS("   ✅ No duplicate types found!"))
        self.stdout.write("")
        
        # 3. Find images with no file
        self.stdout.write(self.style.WARNING("3️⃣  Images with No File Attached:"))
        missing_image_count = 0
        for img in img_records:
            attachments = img.get('fields', {}).get('Image', [])
            if not attachments:
                missing_image_count += 1
                self.show_image_detail(img, prop_lookup)
        
        if missing_image_count == 0:
            self.stdout.write(self.style.SUCCESS("   ✅ No issues found!"))
        self.stdout.write("")
        
        # Summary
        self.stdout.write("="*80)
        total_errors = missing_type_count + duplicate_count + missing_image_count
        if total_errors > 0:
            self.stdout.write(self.style.ERROR(f"Total Critical Issues: {total_errors}"))
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("📝 How to fix in Airtable:"))
            self.stdout.write("   1. Open your Airtable base")
            self.stdout.write("   2. Go to the Configuration or Images table")
            self.stdout.write("   3. Add a Formula field named 'Record ID' with formula: RECORD_ID()")
            self.stdout.write("   4. Search for the Record IDs shown above")
            self.stdout.write("   5. Fix the issues, then delete the Record ID field")
        else:
            self.stdout.write(self.style.SUCCESS("🎉 No critical errors found!"))
        self.stdout.write("="*80)
    
    def show_configuration_detail(self, cfg, prop_lookup):
        cfg_id = cfg['id']
        fields = cfg.get('fields', {})
        linked = fields.get('Property', [])
        prop_name = prop_lookup.get(linked[0], 'Unknown') if linked else 'No Property Linked'
        
        self.stdout.write("")
        self.stdout.write(f"   🏢 Property: {prop_name}")
        self.stdout.write(self.style.ERROR(f"   🔑 Record ID: {cfg_id}"))
        self.stdout.write(f"   📋 Type: (MISSING)")
        self.stdout.write(f"   🛏️  Bedrooms: {fields.get('Bedrooms', 'N/A')}")
        self.stdout.write(f"   🚿 Bathrooms: {fields.get('Bathrooms', 'N/A')}")
        self.stdout.write(f"   📐 Square Footage: {fields.get('Square Footage', 'N/A')}")
        self.stdout.write(f"   💰 Price: ${fields.get('Price', 'N/A')}")
        self.stdout.write(f"   ✅ Available: {fields.get('Is Available', True)}")
        self.stdout.write(self.style.WARNING(f"   ⚠️  Action: Add a Type (e.g., '1 Bedroom', '2 Bedroom', 'Studio')"))
    
    def show_image_detail(self, img, prop_lookup):
        img_id = img['id']
        fields = img.get('fields', {})
        linked = fields.get('Property', [])
        prop_name = prop_lookup.get(linked[0], 'Unknown') if linked else 'No Property Linked'
        
        self.stdout.write("")
        self.stdout.write(f"   🏢 Property: {prop_name}")
        self.stdout.write(self.style.ERROR(f"   🔑 Record ID: {img_id}"))
        self.stdout.write(f"   📝 Alt Text: {fields.get('Alt Text', '(None)')}")
        self.stdout.write(f"   🔢 Order: {fields.get('Order', '(None)')}")
        self.stdout.write(self.style.ERROR(f"   📎 Image: (NO FILE ATTACHED)"))
        self.stdout.write(self.style.WARNING(f"   ⚠️  Action: Attach an image file or delete this record"))
    
    def show_specific_record(self, record_id, props_t, cfgs_t, imgs_t):
        """Show details for a specific record ID"""
        self.stdout.write(f"Looking for record: {record_id}\n")
        
        # Try properties
        try:
            prop = props_t.get(record_id)
            self.stdout.write(self.style.SUCCESS("Found in PROPERTIES table:"))
            self.stdout.write(f"  Name: {prop['fields'].get('Name')}")
            self.stdout.write(f"  Address: {prop['fields'].get('Address')}")
            self.stdout.write(f"  Slug: {prop['fields'].get('Slug (Final)') or prop['fields'].get('Slug')}")
            return
        except:
            pass
        
        # Try configurations
        try:
            cfg = cfgs_t.get(record_id)
            self.stdout.write(self.style.SUCCESS("Found in CONFIGURATIONS table:"))
            fields = cfg['fields']
            linked = fields.get('Property', [])
            if linked:
                prop = props_t.get(linked[0])
                self.stdout.write(f"  Property: {prop['fields'].get('Name')}")
            self.stdout.write(f"  Type: {fields.get('Type', '(MISSING)')}")
            self.stdout.write(f"  Bedrooms: {fields.get('Bedrooms')}")
            self.stdout.write(f"  Bathrooms: {fields.get('Bathrooms')}")
            self.stdout.write(f"  Square Footage: {fields.get('Square Footage')}")
            self.stdout.write(f"  Price: ${fields.get('Price')}")
            return
        except:
            pass
        
        # Try images
        try:
            img = imgs_t.get(record_id)
            self.stdout.write(self.style.SUCCESS("Found in IMAGES table:"))
            fields = img['fields']
            linked = fields.get('Property', [])
            if linked:
                prop = props_t.get(linked[0])
                self.stdout.write(f"  Property: {prop['fields'].get('Name')}")
            self.stdout.write(f"  Alt Text: {fields.get('Alt Text')}")
            self.stdout.write(f"  Order: {fields.get('Order')}")
            self.stdout.write(f"  Image: {len(fields.get('Image', []))} attachment(s)")
            return
        except:
            pass
        
        self.stderr.write(self.style.ERROR(f"Record {record_id} not found in any table"))