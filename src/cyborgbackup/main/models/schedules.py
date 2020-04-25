import logging

from django.db import models

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.base import PrimordialModel
from cyborgbackup.main.models.policies import Policy

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

    def updated_related_policies(self):
        refPolicies = Policy.objects.filter(schedule__pk=self.pk)
        if refPolicies.exists():
            for pol in refPolicies:
                pol.save()

    def save(self, *args, **kwargs):
        self.updated_related_policies()
        # If update_fields has been specified, add our field names to it,
        # if it hasn't been specified, then we're just doing a normal save.
        super(Schedule, self).save(*args, **kwargs)
