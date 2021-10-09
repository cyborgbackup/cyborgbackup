from django.core.management.base import BaseCommand

from cyborgbackup.main import consumers


class Command(BaseCommand):
    """Create preloaded data, intended for new installs
    """
    help = 'Creates a preload tower data iff there is none.'

    def handle(self, *args, **kwargs):
        data = [
            {
                "job_id": 38631,
                "status": "running",
                "job_name": "Backup Job Backup mail from Knet",
                "group_name": "jobs"
            },
            {
                "job_id": 38631,
                "status": "successful",
                "job_name": "Backup Job Backup mail from Knet",
                "group_name": "jobs"
            },
            {
                "job_id": 38631,
                "status": "failed",
                "job_name": "Backup Job Backup mail from Knet",
                "group_name": "jobs"
            }
        ]

        for msg in data:
            consumers.emit_channel_notification('jobs-status_changed', msg)
