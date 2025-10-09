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
    "run-sync-airtable-daily": {
        "task": "properties.tasks.run_sync_airtable",  # adjust to your app name
        "schedule": crontab(hour=0, minute=0),  # every day at midnight UTC
    },
}