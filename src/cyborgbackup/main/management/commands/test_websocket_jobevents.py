from django.core.management.base import BaseCommand

from cyborgbackup.main import consumers


class Command(BaseCommand):
    """Create preloaded data, intended for new installs
    """
    help = 'Creates a preload tower data iff there is none.'

    def handle(self, *args, **kwargs):
        i = 6
        while i < 200:
            consumers.emit_channel_notification("job_events-4", {"id": 16139540,
                                                                 "type": "job_event",
                                                                 "url": "/api/v1/job_events/16139540/",
                                                                 "related": {"job": "/api/v1/jobs/38631/"},
                                                                 "summary_fields": {
                                                                     "job": {
                                                                         "id": 4,
                                                                         "name": "Backup Job Backup Mail from Knet knet.milkywan.cloud",
                                                                         "status": "running",
                                                                         "failed": False,
                                                                         "elapsed": "0.000"
                                                                     }
                                                                 },
                                                                 "created": "2020-04-11T17:50:38.159331+00:00",
                                                                 "modified": "2020-04-11T17:50:38.159340+00:00",
                                                                 "job": 4,
                                                                 "event": "verbose",
                                                                 "counter": i,
                                                                 "event_display":
                                                                     "Verbose",
                                                                 "event_data": {},
                                                                 "event_level": 0,
                                                                 "failed": False,
                                                                 "changed": False,
                                                                 "uuid": "",
                                                                 "task": "",
                                                                 "stdout": "Merging into master chunks insddex {}...".format(
                                                                     i),
                                                                 "start_line": 8,
                                                                 "end_line": 9,
                                                                 "verbosity": 0,
                                                                 "event_name": "verbose",
                                                                 "group_name": "job_events"
                                                                 })
            i = i + 1
