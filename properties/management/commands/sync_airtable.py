from __future__ import annotations

import os
import re
import hashlib
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

import requests
from decouple import config
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.utils.text import slugify

from pyairtable import Table

from properties.location_utils import extract_location

from properties.models import (
    Property,
    PropertyConfiguration,
    PropertyImage,
    PropertyAmenity,
    PropertyProgress,
    PropertyProgressImage,
)

log = logging.getLogger(__name__)

# ---------------------------- Helpers ---------------------------------

def env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v if v is not None else default


def to_decimal(v: Any) -> Optional[Decimal]:
    if v in (None, "", [], {}):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def to_date(v: Any) -> Optional[datetime.date]:
    if v in (None, "", [], {}):
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def first_attachment(attachments: Any) -> Optional[Dict[str, Any]]:
    if not attachments:
        return None
    return attachments[0] if isinstance(attachments, list) else None


def iter_records(table: Table, *, max_records=None, **options):
    out, count = [], 0
    try:
        for chunk in table.iterate(max_records=max_records, **options):
            if isinstance(chunk, list):
                for rec in chunk:
                    if isinstance(rec, dict):
                        out.append(rec); count += 1
                        if max_records and count >= max_records: return out
            elif isinstance(chunk, dict):
                out.append(chunk); count += 1
                if max_records and count >= max_records: return out
    except Exception as e:
        log.warning("iterate() failed (%s); falling back to all()", e)
        out = table.all(max_records=max_records, **options)
    return out

# ---------------------------- Command ---------------------------------

class Command(BaseCommand):
    help = (
        "Sync Airtable (properties/configurations/images/amenities) to Postgres "
        "with perfect mirroring. Files (brochure/thumbnail/images) are downloaded "
        "and written via Django storage."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Max records per table (for testing)")
        parser.add_argument("--dry-run", action="store_true", help="Don't write DB/files; just show actions")
        parser.add_argument("--no-files", action="store_true", help="Skip downloading brochure/thumbnail/images")
        parser.add_argument(
            "--only",
            type=str,
            default="properties,configurations,images,amenities,progress",
            help="Comma list of domains to sync",
        )
        parser.add_argument(
            "--prune-missing",
            action="store_true",
            help="Delete DB rows (per domain) that are no longer present in Airtable",
        )
        parser.add_argument(
            "--limit-properties",
            type=int,
            default=None,
            help="Only sync N properties and their related records",
        )

    # ---------------------------- handle ---------------------------------

    def handle(self, *args, **opts):
        pat = config("AIRTABLE_TOKEN")
        base_id = config("AIRTABLE_BASE_ID")
        if not pat or not base_id:
            raise CommandError("AIRTABLE_PAT and AIRTABLE_BASE_ID must be set in environment")

        tbl_props = config("AIRTABLE_TABLE_PROPERTIES", "Property")
        tbl_cfgs = config("AIRTABLE_TABLE_CONFIGURATIONS", "Configuration")
        tbl_imgs = config("AIRTABLE_TABLE_IMAGES", "Images")
        tbl_amen = config("AIRTABLE_TABLE_AMENITIES", "Amenities")
        tbl_progress = config("AIRTABLE_TABLE_PROGRESS", "Property Progress")

        only: List[str] = [s.strip().lower() for s in opts["only"].split(",") if s.strip()]
        limit: Optional[int] = opts["limit"]
        dry_run: bool = opts["dry_run"]
        no_files: bool = opts["no_files"]
        prune_missing: bool = opts["prune_missing"]
        limit_properties: Optional[int] = opts["limit_properties"]

        self.stdout.write("Starting Airtable sync...")
        self.stdout.write(
            f"Base: {base_id} | Only: {only} | Limit: {limit or '∞'} | Dry-run: {dry_run} | Files: {'OFF' if no_files else 'ON'}"
        )

        props_t = Table(pat, base_id, tbl_props)
        cfgs_t = Table(pat, base_id, tbl_cfgs)
        imgs_t = Table(pat, base_id, tbl_imgs)
        amen_t = Table(pat, base_id, tbl_amen)
        progress_t = Table(pat, base_id, tbl_progress)

        # ----------------- Fetch all data first (so we can map links) -----------------
        prop_map: Dict[str, Dict[str, Any]] = {}
        if "properties" in only:
            self.stdout.write("Fetching properties ...")
            prop_records = iter_records(props_t, max_records=limit)
            if limit_properties:
                prop_records = prop_records[:limit_properties]
            self.stdout.write(f"Fetched {len(prop_records)} property records")
            prop_map = self._shape_properties(prop_records, download_files=not no_files)
            self.stdout.write(f"Prepared {len(prop_map)} properties")

        # track the set of property Airtable IDs we are syncing (for selective pruning)
        synced_prop_ids: Set[str] = set(prop_map.keys())

        cfg_data: List[Dict[str, Any]] = []
        if "configurations" in only:
            # If we're syncing configurations but not properties, build a minimal prop_map from DB
            if not prop_map:
                self.stdout.write("Building property map from database for configurations sync...")
                db_props = Property.objects.filter(airtable_id__isnull=False)
                for prop in db_props:
                    prop_map[prop.airtable_id] = {"name": prop.name, "slug": prop.slug}
                self.stdout.write(f"Found {len(prop_map)} properties in database")

            self.stdout.write("Fetching configurations ...")
            cfg_records = iter_records(cfgs_t, max_records=limit)
            self.stdout.write(f"Fetched {len(cfg_records)} configuration records")
            cfg_data = self._shape_configurations(cfg_records, prop_map)
            self.stdout.write(f"Prepared {len(cfg_data)} configurations")

        img_data: List[Dict[str, Any]] = []
        if "images" in only:
            # If we're syncing images but not properties, build a minimal prop_map from DB
            if not prop_map:
                self.stdout.write("Building property map from database for images sync...")
                db_props = Property.objects.filter(airtable_id__isnull=False)
                for prop in db_props:
                    prop_map[prop.airtable_id] = {"name": prop.name, "slug": prop.slug}
                self.stdout.write(f"Found {len(prop_map)} properties in database")

            self.stdout.write("Fetching images ...")
            img_records = iter_records(imgs_t, max_records=limit)
            self.stdout.write(f"Fetched {len(img_records)} image records")
            img_data = self._shape_images(img_records, prop_map)
            self.stdout.write(f"Prepared {len(img_data)} images")

        amen_data: List[Dict[str, Any]] = []
        if "amenities" in only:
            # If we're syncing amenities but not properties, build a minimal prop_map from DB
            if not prop_map:
                self.stdout.write("Building property map from database for amenities sync...")
                db_props = Property.objects.filter(airtable_id__isnull=False)
                for prop in db_props:
                    prop_map[prop.airtable_id] = {"name": prop.name, "slug": prop.slug}
                self.stdout.write(f"Found {len(prop_map)} properties in database")

            self.stdout.write("Fetching amenities ...")
            amen_records = iter_records(amen_t, max_records=limit)
            self.stdout.write(f"Fetched {len(amen_records)} amenity records")
            amen_data = self._shape_amenities(amen_records, prop_map)
            self.stdout.write(f"Prepared {len(amen_data)} amenities")

        progress_data: List[Dict[str, Any]] = []
        if "progress" in only:
            # If we're syncing progress but not properties, build a minimal prop_map from DB
            if not prop_map:
                self.stdout.write("Building property map from database for progress sync...")
                db_props = Property.objects.filter(airtable_id__isnull=False)
                for prop in db_props:
                    prop_map[prop.airtable_id] = {"name": prop.name, "slug": prop.slug}
                self.stdout.write(f"Found {len(prop_map)} properties in database")

            self.stdout.write("Fetching progress updates ...")
            progress_records = iter_records(progress_t, max_records=limit)
            self.stdout.write(f"Fetched {len(progress_records)} progress records")
            progress_data = self._shape_progress(progress_records, prop_map)
            self.stdout.write(f"Prepared {len(progress_data)} progress updates")

        if dry_run:
            self._preview(prop_map, cfg_data, img_data, amen_data)
            if prune_missing and synced_prop_ids:
                self._preview_prune(prop_map, cfg_data, img_data, amen_data)
            self.stdout.write(self.style.SUCCESS("Dry run complete — no writes performed."))
            return

        # ----------------- Sync to DB (single transaction) -----------------
        with transaction.atomic():
            if "properties" in only:
                self._sync_properties(prop_map, dry_run=dry_run, no_files=no_files)

            if "configurations" in only:
                self._sync_configurations(cfg_data, dry_run=dry_run)

            if "images" in only:
                self._sync_images(img_data, dry_run=dry_run, no_files=no_files)

            if "amenities" in only:
                self._sync_amenities(amen_data, dry_run=dry_run)

            if "progress" in only:
                self._sync_progress(progress_data, dry_run=dry_run, no_files=no_files)

            if prune_missing and not dry_run:
                # hard-delete rows that are no longer present in Airtable (perfect mirroring)
                if synced_prop_ids:
                    self._prune_missing_properties(synced_prop_ids)
                if "configurations" in only:
                    self._prune_missing_configurations(synced_prop_ids, {c["airtable_id"] for c in cfg_data})
                if "images" in only:
                    self._prune_missing_images(synced_prop_ids, {i["airtable_id"] for i in img_data})
                if "amenities" in only:
                    self._prune_missing_amenities(synced_prop_ids, {a["airtable_id"] for a in amen_data})
                if "progress" in only:
                    self._prune_missing_progress(synced_prop_ids, {p["airtable_id"] for p in progress_data})

        self.stdout.write(self.style.SUCCESS("✅ Airtable sync finished"))

    # --------------------------- Shapers ---------------------------------

    def _shape_properties(self, records: List[Dict[str, Any]], download_files: bool = False) -> Dict[str, Dict[str, Any]]:
        """Shape properties and (optionally) download files immediately while Airtable URLs are fresh."""
        out: Dict[str, Dict[str, Any]] = {}

        sess = None
        headers = None
        if download_files:
            sess = requests.Session()
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

        for rec in records:
            rid = rec.get("id")
            f = rec.get("fields", {})
            if not rid:
                continue

            name = f.get("Name") or f"Unnamed Property {rid}"
            slug_final = f.get("Slug (Final)") or f.get("Slug") or slugify(name)

            brochure_att = first_attachment(f.get("Brochure"))
            thumbnail_att = first_attachment(f.get("Thumbnail") or f.get("Thumbnails"))
            brochure_url = brochure_att.get("url") if brochure_att else None
            thumbnail_url = thumbnail_att.get("url") if thumbnail_att else None

            brochure_data = None
            thumbnail_data = None

            if download_files and sess is not None:
                if brochure_url:
                    try:
                        r = sess.get(brochure_url, timeout=60, headers=headers)
                        if r.status_code == 200 and r.content and len(r.content) > 100:
                            brochure_data = r.content
                            self.stdout.write(f"  📎 Downloaded brochure for {name} ({len(r.content)} bytes)")
                        else:
                            self.stdout.write(f"  ⚠️ Brochure download issue for {name}: status={r.status_code}")
                    except Exception as e:
                        self.stdout.write(f"  ⚠️ Brochure download error for {name}: {e}")

                if thumbnail_url:
                    try:
                        r = sess.get(thumbnail_url, timeout=60, headers=headers)
                        if r.status_code == 200 and r.content and len(r.content) > 100:
                            thumbnail_data = r.content
                            self.stdout.write(f"  🖼️ Downloaded thumbnail for {name} ({len(r.content)} bytes)")
                        else:
                            self.stdout.write(f"  ⚠️ Thumbnail download issue for {name}: status={r.status_code}")
                    except Exception as e:
                        self.stdout.write(f"  ⚠️ Thumbnail download error for {name}: {e}")

            out[rid] = {
                "airtable_id": rid,
                "name": name,
                "slug": slug_final,
                "address": f.get("Address") or "",
                "location": (f.get("Location") or "").strip(),
                "description": f.get("Description") or "",
                "latitude": to_decimal(f.get("Latitude")),
                "longitude": to_decimal(f.get("Longitude")),
                "contact_name": f.get("Contact Name") or "",
                "contact_phone": f.get("Contact Phone") or "",
                "luxury_status": (f.get("Luxury Status") or "non_luxurious").strip(),
                "is_active": bool(f.get("Is Active")),
                "completion_date": to_date(f.get("Completion Date")),
                # File bytes (if downloaded now)
                "brochure_data": brochure_data,
                "thumbnail_data": thumbnail_data,
            }

        return out

    def _shape_configurations(self, records: List[Dict[str, Any]], prop_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for rec in records:
            rid = rec.get("id")
            f = rec.get("fields", {})
            linked = f.get("Property") or []
            if not rid or not linked:
                continue
            prop_id = linked[0]
            if prop_id not in prop_map:
                continue
            out.append({
                "airtable_id": rid,
                "property_id": prop_id,
                "type": f.get("Type") or "",
                "bedrooms": int(f.get("Bedrooms") or 0),
                "bathrooms": int(f.get("Bathrooms") or 1),
                "square_footage": int(f.get("Square Footage") or 0),
                "price": to_decimal(f.get("Price")),
                "is_available": bool(f.get("Is Available")),
            })
        return out

    def _shape_images(self, records: List[Dict[str, Any]], prop_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for rec in records:
            rid = rec.get("id")
            f = rec.get("fields", {})
            linked = f.get("Property") or []
            if not rid or not linked:
                continue
            prop_id = linked[0]
            if prop_id not in prop_map:
                continue
            attachments = f.get("Image") or []
            alt_text = f.get("Alt Text") or ""
            base_order = int(f.get("Order") or 0)

            if isinstance(attachments, list):
                for idx, att in enumerate(attachments):
                    if isinstance(att, dict) and att.get("url"):
                        unique_id = f"{rid}_{idx}" if len(attachments) > 1 else rid
                        out.append({
                            "airtable_id": unique_id,
                            "property_id": prop_id,
                            "image_url": att.get("url"),
                            "alt_text": f"{alt_text} (Image {idx+1})" if alt_text and len(attachments) > 1 else alt_text,
                            "order": base_order + idx,
                            "attachment_index": idx,
                            "original_record_id": rid,
                        })
        return out

    def _shape_amenities(self, records: List[Dict[str, Any]], prop_map: Dict[str, Dict[str, Any]]):
        out: List[Dict[str, Any]] = []
        for rec in records:
            rid = rec.get("id")
            f = rec.get("fields", {})
            linked = f.get("Property") or []
            if not rid or not linked:
                continue
            prop_id = linked[0]
            if prop_id not in prop_map:
                continue

            raw = (f.get("Amenities") or f.get("Name") or "")
            names = [n.strip() for n in raw.split(",") if n.strip()]
            for nm in names:
                name_100 = nm[:100]
                slug = re.sub(r"[^a-z0-9]+", "_", nm.lower()).strip("_")
                candidate = f"{rid}_{slug}"
                if len(candidate) > 50:
                    digest = hashlib.sha1(nm.encode("utf-8")).hexdigest()[:10]
                    candidate = f"{rid}_{digest}"

                out.append({
                    "airtable_id": candidate,
                    "property_id": prop_id,
                    "name": name_100,
                })
        return out

    def _shape_progress(self, records: List[Dict[str, Any]], prop_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Shape progress update records from Airtable"""
        out: List[Dict[str, Any]] = []
        for rec in records:
            rid = rec.get("id")
            f = rec.get("fields", {})
            linked = f.get("Property") or []
            if not rid or not linked:
                continue
            prop_id = linked[0]
            if prop_id not in prop_map:
                continue

            # Get stage (map Airtable values to our choices)
            stage_raw = (f.get("Stage") or "").lower().strip()
            stage_map = {
                "foundation": "foundation",
                "structure": "structure",
                "roofing": "roofing",
                "exterior": "exterior",
                "exterior finishing": "exterior",
                "interior": "interior",
                "interior finishing": "interior",
                "landscaping": "landscaping",
                "final touches": "final_touches",
                "final": "final_touches",
                "completed": "completed",
                "complete": "completed",
            }
            stage = stage_map.get(stage_raw, "foundation")

            # Get progress percentage
            # Debug: Print available fields for first record
            if not out:
                self.stdout.write(f"DEBUG: Available fields in progress record: {list(f.keys())}")

            raw_pct = f.get("Progress Status")
            try:
                progress_pct = int(float(raw_pct)) if raw_pct not in (None, "") else 0
            except (TypeError, ValueError):
                progress_pct = 0
            progress_pct = max(0, min(100, progress_pct))  # Clamp to 0-100

            # Get update date
            update_date_str = f.get("Update Date") or f.get("Date")
            update_date = to_date(update_date_str) if update_date_str else timezone.now().date()

            # Get images
            images = f.get("Images") or f.get("Photos") or []
            images_data = []
            if isinstance(images, list):
                for img in images:
                    if isinstance(img, dict) and img.get("url"):
                        images_data.append({
                            "url": img.get("url"),
                            "filename": img.get("filename", ""),
                            "size": img.get("size", 0),
                            "type": img.get("type", ""),
                        })

            # Check both auto-calculated and manual "Is Latest" fields
            # Prefer the auto-calculated one if it exists
            is_latest = bool(
                f.get("Is Latest (Auto)") or
                f.get("Is Latest") or
                f.get("Latest")
            )

            out.append({
                "airtable_id": rid,
                "property_id": prop_id,
                "stage": stage,
                "progress_percentage": progress_pct,
                "update_date": update_date,
                "description": f.get("Description") or f.get("Notes") or "",
                "uploaded_by": f.get("Uploaded By") or f.get("Updated By") or "",
                "is_latest": is_latest,
                "images_data": images_data,
            })
        return out

    # --------------------------- Syncers ---------------------------------

    def _sync_properties(self, prop_map: Dict[str, Dict[str, Any]], *, dry_run: bool, no_files: bool):
        self.stdout.write(f"Syncing {len(prop_map)} properties ...")
        for rid, p in prop_map.items():
            fields = {
                "name": p["name"],
                "slug": p["slug"],
                "address": p["address"],
                # Airtable's Location single-select is authoritative. Any value it
                # sends is trusted (so new locations work without a code change);
                # only fall back to guessing from the address when it's left blank.
                "location": p["location"] or extract_location(p["address"]),
                "description": p["description"],
                "latitude": p["latitude"],
                "longitude": p["longitude"],
                "contact_name": p["contact_name"],
                "contact_phone": p["contact_phone"],
                "is_active": p["is_active"],
                "luxury_status": p["luxury_status"] if p["luxury_status"] in {c[0] for c in Property.LUXURY_CHOICES} else "non_luxurious",
                "completion_date": p["completion_date"],
            }

            if dry_run:
                self.stdout.write(f"🔍 Would upsert property: {fields['name']}")
                if not no_files:
                    if p.get("brochure_data"):
                        self.stdout.write(f"  → Would save brochure ({len(p['brochure_data'])} bytes)")
                    if p.get("thumbnail_data"):
                        self.stdout.write(f"  → Would save thumbnail ({len(p['thumbnail_data'])} bytes)")
                continue

            try:
                obj, created = Property.objects.get_or_create(airtable_id=rid, defaults=fields)
                if not created:
                    changed = False
                    for k, v in fields.items():
                        if getattr(obj, k) != v:
                            setattr(obj, k, v)
                            changed = True
                    if changed:
                        obj.last_synced_at = timezone.now()
                        obj.save()
                        self.stdout.write(f"🔄 Updated property: {obj.name}")
                    else:
                        self.stdout.write(f"✅ No changes: {obj.name}")
                else:
                    obj.last_synced_at = timezone.now()
                    obj.save()
                    self.stdout.write(f"✅ Created property: {obj.name}")

                if not no_files:
                    try:
                        if p.get("brochure_data"):
                            fname = f"brochure_{obj.slug}.pdf"
                            if obj.brochure:
                                obj.brochure.delete(save=False)
                            obj.brochure.save(fname, ContentFile(p["brochure_data"]), save=False)
                            self.stdout.write("  📎 Saved brochure to storage")

                        if p.get("thumbnail_data"):
                            fname = f"thumbnail_{obj.slug}.jpg"
                            if obj.thumbnail:
                                obj.thumbnail.delete(save=False)
                            obj.thumbnail.save(fname, ContentFile(p["thumbnail_data"]), save=False)
                            self.stdout.write("  🖼️ Saved thumbnail to storage")

                        if p.get("brochure_data") or p.get("thumbnail_data"):
                            obj.save()
                    except Exception as file_err:
                        self.stderr.write(f"  ⚠️ File save error for {obj.name}: {file_err}")

            except Exception as e:
                self.stderr.write(f"❌ Property sync error ({p.get('name')}): {e}")

    def _sync_configurations(self, cfgs: List[Dict[str, Any]], *, dry_run: bool):
        self.stdout.write(f"Syncing {len(cfgs)} configurations ...")
        for c in cfgs:
            prop = self._get_property_by_airtable_id(c["property_id"])  # type: ignore
            if not prop:
                self.stderr.write(f"❌ Missing property {c['property_id']} for configuration {c['airtable_id']}")
                continue
            fields = {
                "property": prop,
                "type": c["type"],
                "bedrooms": c["bedrooms"],
                "bathrooms": c["bathrooms"],
                "square_footage": c["square_footage"],
                "price": c["price"],
                "is_available": c["is_available"],
            }
            if dry_run:
                self.stdout.write(f"🔍 Would upsert config: {prop.name} - {c['type']}")
                continue
            try:
                obj, created = PropertyConfiguration.objects.get_or_create(
                    airtable_id=c["airtable_id"], defaults=fields
                )
                if not created:
                    changed = False
                    for k, v in fields.items():
                        if k == "property":
                            continue
                        if getattr(obj, k) != v:
                            setattr(obj, k, v)
                            changed = True
                    if changed:
                        obj.last_synced_at = timezone.now()
                        obj.save()
                        self.stdout.write(f"🔄 Updated config: {prop.name} - {obj.type}")
                    else:
                        self.stdout.write(f"✅ No changes: {prop.name} - {obj.type}")
                else:
                    obj.last_synced_at = timezone.now()
                    obj.save()
                    self.stdout.write(f"✅ Created config: {prop.name} - {obj.type}")
            except IntegrityError:
                # unique_together on (property, type); fallback to update by that pair
                obj = PropertyConfiguration.objects.filter(property=prop, type=c["type"]).first()
                if obj:
                    obj.bedrooms = c["bedrooms"]
                    obj.bathrooms = c["bathrooms"]
                    obj.square_footage = c["square_footage"]
                    obj.price = c["price"]
                    obj.is_available = c["is_available"]
                    obj.last_synced_at = timezone.now()
                    obj.save()
                    self.stdout.write(f"🔄 Updated existing (unique) config: {prop.name} - {obj.type}")
                else:
                    self.stderr.write(f"❌ Failed to upsert config for {prop.name} - {c['type']}")

    def _sync_images(self, imgs: List[Dict[str, Any]], *, dry_run: bool, no_files: bool):
        import hashlib as _hash

        self.stdout.write(f"Syncing {len(imgs)} images ...")
        sess = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

        for im in imgs:
            prop = self._get_property_by_airtable_id(im["property_id"])
            if not prop:
                self.stderr.write(f"❌ Missing property {im['property_id']} for image {im['airtable_id']}")
                continue

            url = im.get("image_url")
            url_hash = _hash.sha256(url.encode()).hexdigest() if url else ""

            defaults = {
                "property": prop,
                "alt_text": im["alt_text"],
                "order": im["order"],
                "attachment_index": im["attachment_index"],
                "original_record_id": im["original_record_id"],
                "image_url_hash": url_hash,
            }

            if dry_run:
                self.stdout.write(f"🔍 Would upsert image meta: {prop.name} (order {im['order']})")
                if url:
                    self.stdout.write(f"  → URL hash: {url_hash[:16]}...")
                continue

            obj, created = PropertyImage.objects.get_or_create(airtable_id=im["airtable_id"], defaults=defaults)

            if not created:
                changed = False
                for k in ("alt_text", "order", "attachment_index", "original_record_id", "image_url_hash"):
                    if getattr(obj, k) != defaults[k]:
                        setattr(obj, k, defaults[k])
                        changed = True
                if changed:
                    obj.last_synced_at = timezone.now()
                    obj.save()
                    self.stdout.write(f"🔄 Updated image meta: {prop.name} (order {obj.order})")

            needs_download = created or not obj.image or obj.image_url_hash != url_hash

            if not no_files and needs_download:
                if not url:
                    self.stderr.write(f"⚠️ No image URL for {prop.name} (order {im['order']})")
                else:
                    try:
                        self.stdout.write(f"⬇️  Downloading image for {prop.name} (order {im['order']})...")
                        r = sess.get(url, timeout=60, headers=headers)
                        if r.status_code == 200 and r.content and len(r.content) > 100:
                            fname = f"image_{prop.slug}_{im['order'] or 0}.jpg"
                            if obj.image:
                                obj.image.delete(save=False)
                            obj.image.save(fname, ContentFile(r.content), save=False)
                            obj.image_url_hash = url_hash
                            obj.last_synced_at = timezone.now()
                            obj.save()
                            self.stdout.write(
                                f"🖼️ Saved image: {prop.name} (order {obj.order}) - {len(r.content)} bytes"
                            )
                        else:
                            self.stderr.write(
                                f"⚠️ Image download issue for {prop.name} (order {im['order']}): "
                                f"status={r.status_code}, size={len(r.content) if r.content else 0}"
                            )
                    except Exception as e:
                        self.stderr.write(f"⚠️ Image download failed for {prop.name} (order {im['order']}): {e}")
            elif not no_files and not needs_download:
                self.stdout.write(f"✅ Image unchanged: {prop.name} (order {obj.order}) - skipping download")

    def _sync_amenities(self, ams: List[Dict[str, Any]], *, dry_run: bool):
        self.stdout.write(f"Syncing {len(ams)} amenities ...")
        for a in ams:
            prop = self._get_property_by_airtable_id(a["property_id"])  # type: ignore
            if not prop:
                self.stderr.write(f"❌ Missing property {a['property_id']} for amenity {a['airtable_id']}")
                continue
            if dry_run:
                self.stdout.write(f"🔍 Would upsert amenity: {prop.name} - {a['name']}")
                continue
            obj, created = PropertyAmenity.objects.get_or_create(
                airtable_id=a["airtable_id"], property=prop, defaults={"name": a["name"]}
            )
            if created:
                obj.last_synced_at = timezone.now()
                obj.save()
                self.stdout.write(f"✅ Created amenity: {prop.name} - {obj.name}")
            else:
                if obj.name != a["name"]:
                    obj.name = a["name"]
                    obj.last_synced_at = timezone.now()
                    obj.save()
                    self.stdout.write(f"🔄 Updated amenity: {prop.name} - {obj.name}")

    def _sync_progress(self, progress_updates: List[Dict[str, Any]], *, dry_run: bool, no_files: bool):
        import hashlib as _hash

        self.stdout.write(f"Syncing {len(progress_updates)} progress updates ...")
        sess = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

        for prog in progress_updates:
            prop = self._get_property_by_airtable_id(prog["property_id"])
            if not prop:
                self.stderr.write(f"❌ Missing property {prog['property_id']} for progress {prog['airtable_id']}")
                continue

            fields = {
                "property": prop,
                "stage": prog["stage"],
                "progress_percentage": prog["progress_percentage"],
                "update_date": prog["update_date"],
                "description": prog["description"],
                "uploaded_by": prog["uploaded_by"],
                "is_latest": prog["is_latest"],
                "images_data": prog["images_data"],
            }

            if dry_run:
                self.stdout.write(
                    f"🔍 Would upsert progress: {prop.name} - {prog['stage']} ({prog['progress_percentage']}%)"
                )
                continue

            try:
                obj, created = PropertyProgress.objects.get_or_create(
                    airtable_id=prog["airtable_id"],
                    defaults=fields
                )

                if not created:
                    changed = False
                    for k, v in fields.items():
                        if k == "property":
                            continue
                        if getattr(obj, k) != v:
                            setattr(obj, k, v)
                            changed = True
                    if changed:
                        obj.last_synced_at = timezone.now()
                        obj.save()
                        self.stdout.write(
                            f"🔄 Updated progress: {prop.name} - {obj.get_stage_display()} ({obj.progress_percentage}%)"
                        )
                    else:
                        self.stdout.write(f"✅ No changes: {prop.name} - {obj.get_stage_display()}")
                else:
                    obj.last_synced_at = timezone.now()
                    obj.save()
                    self.stdout.write(
                        f"✅ Created progress: {prop.name} - {obj.get_stage_display()} ({obj.progress_percentage}%)"
                    )

                # Download and sync progress images
                if not no_files and prog["images_data"]:
                    self._sync_progress_images(obj, prog["images_data"], sess, headers, dry_run)

            except Exception as e:
                self.stderr.write(f"❌ Progress sync error ({prop.name}): {e}")

    def _sync_progress_images(self, progress_obj, images_data: List[Dict], sess, headers, dry_run: bool):
        """Download and sync images for a progress update"""
        import hashlib as _hash

        for idx, img_data in enumerate(images_data):
            url = img_data.get("url")
            if not url:
                continue

            url_hash = _hash.sha256(url.encode()).hexdigest()
            unique_id = f"{progress_obj.airtable_id}_{idx}"

            defaults = {
                "progress_update": progress_obj,
                "order": idx,
                "caption": img_data.get("filename", ""),
                "attachment_index": idx,
                "image_url_hash": url_hash,
            }

            obj, created = PropertyProgressImage.objects.get_or_create(
                airtable_id=unique_id,
                defaults=defaults
            )

            needs_download = created or not obj.image or obj.image_url_hash != url_hash

            if needs_download:
                try:
                    self.stdout.write(
                        f"⬇️  Downloading progress image for {progress_obj.property.name} ({idx + 1}/{len(images_data)})..."
                    )
                    r = sess.get(url, timeout=60, headers=headers)
                    if r.status_code == 200 and r.content and len(r.content) > 100:
                        fname = f"progress_{progress_obj.property.slug}_{progress_obj.id}_{idx}.jpg"
                        if obj.image:
                            obj.image.delete(save=False)
                        obj.image.save(fname, ContentFile(r.content), save=False)
                        obj.image_url_hash = url_hash
                        obj.last_synced_at = timezone.now()
                        obj.save()
                        self.stdout.write(
                            f"🖼️ Saved progress image: {progress_obj.property.name} ({idx + 1}) - {len(r.content)} bytes"
                        )
                    else:
                        self.stderr.write(
                            f"⚠️ Progress image download issue: status={r.status_code}, size={len(r.content) if r.content else 0}"
                        )
                except Exception as e:
                    self.stderr.write(f"⚠️ Progress image download failed: {e}")
            else:
                self.stdout.write(f"✅ Progress image unchanged ({idx + 1}) - skipping download")

    # ------------------------ Pruning (perfect mirroring) ---------------

    def _prune_missing_properties(self, airtable_ids: Set[str]):
        qs = Property.objects.exclude(airtable_id__in=airtable_ids)
        count = qs.count()
        if count:
            self.stdout.write(self.style.WARNING(f"🗑️ Deleting {count} properties missing from Airtable"))
            qs.delete()
        else:
            self.stdout.write("No properties to prune.")

    def _prune_missing_configurations(self, scoped_prop_ids: Set[str], present_cfg_ids: Set[str]):
        qs = PropertyConfiguration.objects.filter(property__airtable_id__in=scoped_prop_ids).exclude(
            airtable_id__in=present_cfg_ids
        )
        count = qs.count()
        if count:
            self.stdout.write(self.style.WARNING(f"🗑️ Deleting {count} configurations missing from Airtable"))
            qs.delete()
        else:
            self.stdout.write("No configurations to prune.")

    def _prune_missing_images(self, scoped_prop_ids: Set[str], present_img_ids: Set[str]):
        qs = PropertyImage.objects.filter(property__airtable_id__in=scoped_prop_ids).exclude(
            airtable_id__in=present_img_ids
        )
        count = qs.count()
        if count:
            self.stdout.write(self.style.WARNING(f"🗑️ Deleting {count} images missing from Airtable"))
            qs.delete()
        else:
            self.stdout.write("No images to prune.")

    def _prune_missing_amenities(self, scoped_prop_ids: Set[str], present_am_ids: Set[str]):
        qs = PropertyAmenity.objects.filter(property__airtable_id__in=scoped_prop_ids).exclude(
            airtable_id__in=present_am_ids
        )
        count = qs.count()
        if count:
            self.stdout.write(self.style.WARNING(f"🗑️ Deleting {count} amenities missing from Airtable"))
            qs.delete()
        else:
            self.stdout.write("No amenities to prune.")

    def _prune_missing_progress(self, scoped_prop_ids: Set[str], present_progress_ids: Set[str]):
        qs = PropertyProgress.objects.filter(property__airtable_id__in=scoped_prop_ids).exclude(
            airtable_id__in=present_progress_ids
        )
        count = qs.count()
        if count:
            self.stdout.write(self.style.WARNING(f"🗑️ Deleting {count} progress updates missing from Airtable"))
            qs.delete()
        else:
            self.stdout.write("No progress updates to prune.")

    # ------------------------ Utilities & Preview -----------------------

    def _get_property_by_airtable_id(self, rid: str) -> Optional[Property]:
        try:
            return Property.objects.get(airtable_id=rid)
        except Property.DoesNotExist:
            return None

    def _preview(self, prop_map, cfg_data, img_data, amen_data):
        self.stdout.write(f"🔎 Would upsert {len(prop_map)} properties:")
        for p in list(prop_map.values())[:10]:
            self.stdout.write(f"  - {p['name']} (slug: {p['slug']})")

        cfgs = [c for c in cfg_data if c['property_id'] in prop_map]
        self.stdout.write(f"🔎 Would upsert {len(cfgs)} configurations:")
        for c in cfgs[:10]:
            pname = prop_map[c['property_id']]['name']
            self.stdout.write(
                f"  - {pname}: {c['type']} | {c['bedrooms']} BR / {c['bathrooms']} BA | price={c['price']}"
            )

        imgs = [i for i in img_data if i['property_id'] in prop_map]
        self.stdout.write(f"🔎 Would upsert {len(imgs)} images:")
        for i in imgs[:10]:
            pname = prop_map[i['property_id']]['name']
            url = i['image_url']
            self.stdout.write(f"  - {pname}: order={i['order']} url={(url[:60] + '...') if url else '—'}")

        ams = [a for a in amen_data if a['property_id'] in prop_map]
        self.stdout.write(f"🔎 Would upsert {len(ams)} amenities:")
        for a in ams[:10]:
            pname = prop_map[a['property_id']]['name']
            self.stdout.write(f"  - {pname}: {a['name']}")

    def _preview_prune(self, prop_map, cfg_data, img_data, amen_data):
        # Property prune
        self.stdout.write("\n🧹 PRUNE (dry-run):")
        all_prop_ids = set(prop_map.keys())
        prop_delete_count = Property.objects.exclude(airtable_id__in=all_prop_ids).count()
        self.stdout.write(f"  Properties to delete: {prop_delete_count}")

        # Configurations prune (scoped to synced properties)
        cfg_ids = {c['airtable_id'] for c in cfg_data}
        cfg_delete_count = (
            PropertyConfiguration.objects.filter(property__airtable_id__in=all_prop_ids)
            .exclude(airtable_id__in=cfg_ids)
            .count()
        )
        self.stdout.write(f"  Configurations to delete: {cfg_delete_count}")

        # Images prune (scoped)
        img_ids = {i['airtable_id'] for i in img_data}
        img_delete_count = (
            PropertyImage.objects.filter(property__airtable_id__in=all_prop_ids)
            .exclude(airtable_id__in=img_ids)
            .count()
        )
        self.stdout.write(f"  Images to delete: {img_delete_count}")

        # Amenities prune (scoped)
        am_ids = {a['airtable_id'] for a in amen_data}
        am_delete_count = (
            PropertyAmenity.objects.filter(property__airtable_id__in=all_prop_ids)
            .exclude(airtable_id__in=am_ids)
            .count()
        )
        self.stdout.write(f"  Amenities to delete: {am_delete_count}")
