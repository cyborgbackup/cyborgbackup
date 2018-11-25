import datetime
import logging

from django.conf import settings
from django.db import models
from django.utils.dateparse import parse_datetime
from django.utils.timezone import utc
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import force_text

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.fields import JSONField
from cyborgbackup.main.models.base import CreatedModifiedModel, PrimordialModel

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

    def save(self, *args, **kwargs):
        #encrypted = settings_registry.is_setting_encrypted(self.key)
        encrypted = False
        # If update_fields has been specified, add our field names to it,
        # if it hasn't been specified, then we're just doing a normal save.
        update_fields = kwargs.get('update_fields', [])
        # When first saving to the database, don't store any encrypted field
        # value, but instead save it until after the instance is created.
        # Otherwise, store encrypted value to the database.
        if encrypted:
                self.value = encrypt_field(self, 'value')
                if 'value' not in update_fields:
                    update_fields.append('value')
        super(Schedule, self).save(*args, **kwargs)

    @classmethod
    def get_cache_key(self, key):
        return key

    @classmethod
    def get_cache_id_key(self, key):
        return '{}_ID'.format(key)
