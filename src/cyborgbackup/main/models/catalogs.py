import datetime
import logging
import gzip
import base64
import json

from django.conf import settings
from django.db import models
from django.utils.dateparse import parse_datetime
from django.utils.timezone import utc
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import force_text

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.fields import JSONField
from cyborgbackup.main.models.base import CreatedModifiedModel, PrimordialModel
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.utils.common import could_be_script, copy_model_by_class, copy_m2m_relationships
from cyborgbackup.main.consumers import emit_channel_notification

analytics_logger = logging.getLogger('cyborgbackup.models.Catalog')

__all__ = ['Catalog']

class Catalog(PrimordialModel):

    archive_name = models.CharField(
        max_length=1024,
    )

    mode = models.CharField(
        max_length=10
    )

    path = models.CharField(
        max_length=2048,
    )

    owner = models.CharField(
        max_length=1024
    )

    group = models.CharField(
        max_length=1024
    )

    type = models.CharField(
        max_length=1
    )

    healthy = models.BooleanField()

    size = models.PositiveIntegerField()

    mtime = models.DateTimeField()

    job = models.ForeignKey(
        'Job',
        related_name='catalogs',
        on_delete=models.CASCADE,
        null=False,
        editable=True,
    )

    def get_absolute_url(self, request=None):
        return reverse('api:catalog_detail', kwargs={'pk': self.pk}, request=request)

    def get_ui_url(self):
        return "/#/catalogs/{}".format(self.pk)

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
        super(Catalog, self).save(*args, **kwargs)

    @classmethod
    def create_from_data(self, **kwargs):
        pk = None
        for key in ('archive_name',):
            if key in kwargs:
                pk = key
        if pk is None:
            return

        archive_name = kwargs['archive_name']
        job = kwargs['job']
        catalog_data = kwargs['catalog']
        catalogs_entries_raw = gzip.decompress(base64.b64decode(catalog_data))
        catalog_entries = json.loads(catalogs_entries_raw.decode('utf-8'))
        created = []
        for entry in catalog_entries:
            entry.update({'archive_name': archive_name, 'job_id': job})
            created.append(self.objects.create(**entry))
        analytics_logger.info('Catalog data saved.', extra=dict(python_objects=dict(created=len(created))))
        return len(created)

    @classmethod
    def get_cache_key(self, key):
        return key

    @classmethod
    def get_cache_id_key(self, key):
        return '{}_ID'.format(key)
