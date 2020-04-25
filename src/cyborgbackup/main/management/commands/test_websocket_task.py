from django.core.management.base import BaseCommand
from django.core.management import call_command
from crum import impersonate
from django.contrib.auth import get_user_model
from cyborgbackup.main import consumers


class Command(BaseCommand):
    """Create preloaded data, intended for new installs
    """
    help = 'Creates a preload tower data iff there is none.'

    def handle(self, *args, **kwargs):
        consumers.emit_channel_notification("jobs-status_changed", {
            "job_id": 38631,
            "status": "successful",
            "job_name": "Backup Job Backup mail from Knet",
            "group_name": "jobs"
	}) 
        consumers.emit_channel_notification("jobs-status_changed", {
            "job_id": 38631,
            "status": "failed",
            "job_name": "Backup Job Backup mail from Knet",
            "group_name": "jobs"
	}) 
        consumers.emit_channel_notification("jobs-status_changed", {
            "job_id": 38631,
            "status": "running",
            "job_name": "Backup Job Backup mail from Knet",
            "group_name": "jobs"
	}) 
