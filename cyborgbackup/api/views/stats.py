# Python
import datetime
import logging

import pytz
# Django REST Framework
from rest_framework.response import Response

from cyborgbackup.main.models.jobs import Job
# CyBorgBackup
from .generics import ListAPIView
from ..serializers.stats import StatsSerializer

logger = logging.getLogger('cyborgbackups.api.views.stats')


class Stats(ListAPIView):
    model = Job
    serializer_class = StatsSerializer
    tags = ['Stats']

    def list(self, request, *args, **kwargs):
        data = []
        now = datetime.datetime.now(pytz.utc)
        last_30_days = now - datetime.timedelta(days=30)
        jobs = Job.objects.filter(job_type='job', started__gte=last_30_days).order_by('started')
        if jobs.exists():
            for job in jobs:
                stats_dates = [stat['date'] for stat in data]
                if job.started.date() not in stats_dates:
                    data.append({'date': job.started.date(), 'size': 0, 'dedup': 0, 'success': 0, 'failed': 0})
                for stat in data:
                    if stat['date'] == job.started.date():
                        stat['size'] += job.original_size
                        stat['dedup'] += job.deduplicated_size
                        if job.status == 'successful':
                            stat['success'] += 1
                        if job.status == 'failed':
                            stat['failed'] += 1
        return Response(data)
