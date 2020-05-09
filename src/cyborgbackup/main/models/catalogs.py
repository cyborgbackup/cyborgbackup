import logging
import gzip
import base64
import json

from django.db import models
from elasticsearch import Elasticsearch

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.base import PrimordialModel

logger = logging.getLogger('cyborgbackup.models.Catalog')

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
        # es = Elasticsearch([{'host': 'localhost', 'port': 9200}])
        for entry in catalog_entries:
            entry.update({'archive_name': archive_name, 'job_id': job})
            created.append(self.objects.create(**entry))
            # es.index(index='catalog', doc_type='entry', body={
            #     'path': entry['path'],
            #     'job': entry['job_id'],
            #     'archive_name': entry['archive_name'],
            #     'mode': entry['mode'],
            #     'owner': entry['user'],
            #     'group': entry['group'],
            #     'type': entry['type'],
            #     'size': entry['size'],
            #     'healthy': entry['healthy'],
            #     'mtime': entry['mtime']
            # });
        logger.info('Catalog data saved.', extra=dict(python_objects=dict(created=len(created))))
        return len(created)

    @classmethod
    def get_cache_key(self, key):
        return key

    @classmethod
    def get_cache_id_key(self, key):
        return '{}_ID'.format(key)

    def __str__(self):
        return 'catalog'