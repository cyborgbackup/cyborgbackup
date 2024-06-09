import base64
import gzip
import json
import logging

import pymongo
from django.conf import settings
from django.db import models

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
    def create_from_data(cls, **kwargs):
        pk = None
        for key in ('archive_name',):
            if key in kwargs:
                pk = key
        if pk is None:
            return

        catalog_data = kwargs['catalog']
        catalogs_entries_raw = gzip.decompress(base64.b64decode(catalog_data))
        catalog_entries = json.loads(catalogs_entries_raw.decode('utf-8'))

        db = pymongo.MongoClient(settings.MONGODB_URL).local
        db.catalog.insert_many(catalog_entries)
        if 'archive_name_text_path_text' not in db.catalog.index_information().keys():
            db.catalog.create_index([
                ('archive_name', pymongo.TEXT),
                ('path', pymongo.TEXT)
            ], name='archive_name_text_path_text', default_language='english')
        if 'archive_name_1' not in db.catalog.index_information().keys():
            db.catalog.create_index('archive_name', name='archive_name_1', default_language='english')

        logger.info('Catalog data saved.', extra=dict(python_objects=dict(created=len(catalog_entries))))
        return len(catalog_entries)

    @classmethod
    def get_cache_key(cls, key):
        return key

    @classmethod
    def get_cache_id_key(cls, key):
        return '{}_ID'.format(key)

    def __str__(self):
        return 'catalog'
