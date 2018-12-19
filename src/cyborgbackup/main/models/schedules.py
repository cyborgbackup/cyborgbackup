import logging

from django.db import models

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.base import PrimordialModel

analytics_logger = logging.getLogger('cyborgbackup.models.schedule')

__all__ = ['Schedule']


class CyborgBackupScheduleState(models.Model):
    schedule_last_run = models.DateTimeField(auto_now_add=True)


class Schedule(PrimordialModel):
    name = models.CharField(
        max_length=1024,
    )

    crontab = models.CharField(
        max_length=1024,
    )

    enabled = models.BooleanField(
        default=True
    )

    def get_absolute_url(self, request=None):
        return reverse('api:schedule_detail', kwargs={'pk': self.pk}, request=request)

    def get_ui_url(self):
        return "/#/schedules/{}".format(self.pk)

    @classmethod
    def get_cache_key(self, key):
        return key

    @classmethod
    def get_cache_id_key(self, key):
        return '{}_ID'.format(key)
