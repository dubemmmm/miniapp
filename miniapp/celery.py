import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'miniapp.settings')

# Create a Celery instance and configure it
app = Celery('miniapp')

# Load configuration from Django settings.py (under the 'CELERY' namespace)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # Existing Airtable sync
    "run-sync-airtable-daily": {
        "task": "properties.tasks.run_sync_airtable",
        "schedule": crontab(hour=0, minute=0),  # daily at midnight UTC
    },
    # CRM: mark overdue leads every 30 minutes
    "crm-sweep-overdue-leads": {
        "task": "crm.tasks.sweep_overdue_leads",
        "schedule": crontab(minute="*/30"),
    },
    # CRM: escalate stale overdue leads every hour
    "crm-sweep-escalations": {
        "task": "crm.tasks.sweep_escalations",
        "schedule": crontab(minute=0),  # top of every hour
    },
    # CRM: recompute agent response scores daily at 02:00 UTC
    "crm-compute-response-scores": {
        "task": "crm.tasks.compute_response_scores",
        "schedule": crontab(hour=2, minute=0),
    },
}