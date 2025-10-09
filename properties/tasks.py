# properties/tasks.py
from celery import shared_task
from django.core import management

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_sync_airtable(self):
    # runs the management command named by the filename: "sync_airtable"
    management.call_command("sync_airtable", verbosity=1)
