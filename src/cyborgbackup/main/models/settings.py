# Python
import json

# Django
from django.db import models

# CyBorgBackup
from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.base import CreatedModifiedModel
from cyborgbackup.main.utils.encryption import encrypt_field, decrypt_field

__all__ = ['Setting']


class Setting(CreatedModifiedModel):

    SETTING_TYPE_CHOICES = [
        ('boolean', 'Boolean'),            # Job was started manually by a user.
        ('integer', 'Integer'),        # Job was started via relaunch.
        ('string', 'String'),        # Job was started via host callback.
        ('privatekey', 'Scheduled'),      # Job was started from a schedule.
        ('password', 'Dependency'),    # Job was started as a dependency of another job.
        ('workflow', 'Workflow'),        # Job was started from a workflow job.
    ]

    key = models.CharField(
        max_length=255,
    )
    value = models.TextField(
        null=True,
    )
    setting_type = models.CharField(
        max_length=20,
        choices=SETTING_TYPE_CHOICES,
        default='manual',
        editable=False,
    )

    group = models.TextField(
        null=True,
        editable=False
    )

    order = models.IntegerField(
        default=0,
        editable=False
    )

    def get_absolute_url(self, request=None):
        return reverse('api:setting_detail', kwargs={'pk': self.pk}, request=request)

    def get_ui_url(self):
        return None

    def __unicode__(self):
        try:
            json_value = json.dumps(self.value)
        except ValueError:
            # In the rare case the DB value is invalid JSON.
            json_value = u'<Invalid JSON>'
        if self.user:
            return u'{} ({}) = {}'.format(self.key, self.user, json_value)
        else:
            return u'{} = {}'.format(self.key, json_value)

    def is_setting_encrypted(self):
        if self.setting_type in ['password', 'privatekey']:
            return True
        else:
            return False

    def save(self, *args, **kwargs):
        encrypted = self.is_setting_encrypted()
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
        super(Setting, self).save(*args, **kwargs)

    @classmethod
    def get_cache_key(self, key):
        return key

    @classmethod
    def get_cache_id_key(self, key):
        return '{}_ID'.format(key)

    @classmethod
    def get_value(self, name):
        objs = self.objects.filter(key=name)
        if len(objs) == 1:
            setting = objs[0]
            return decrypt_field(setting, 'value')
        else:
            return None
