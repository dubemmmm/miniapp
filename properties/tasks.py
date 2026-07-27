# properties/tasks.py
from celery import shared_task
from django.core import management

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_sync_airtable_incremental(self):
    # runs the management command in --incremental mode: only pulls records changed
    # since the last watermark per domain (see properties/models.py SyncState)
    management.call_command("sync_airtable", incremental=True, verbosity=1)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_sync_airtable_full(self):
    # full pull + prune-missing: catches anything the incremental job could miss
    # (e.g. a misconfigured "Last Modified" watch field) and reconciles deletions
    management.call_command("sync_airtable", prune_missing=True, verbosity=1)
