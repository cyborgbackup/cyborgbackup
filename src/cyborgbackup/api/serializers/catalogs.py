# Python
import logging

# Django REST Framework
from rest_framework import serializers

from cyborgbackup.main.models.catalogs import Catalog
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.validators import vars_validate_or_raise
# CyBorgBackup
from .base import BaseSerializer, DynamicFieldsSerializerMixin

logger = logging.getLogger('cyborgbackup.api.serializers.catalogs')


class RestoreLaunchSerializer(BaseSerializer):
    defaults = serializers.SerializerMethodField()
    archive_name = serializers.CharField(required=True, write_only=True)
    destination = serializers.CharField(required=True, write_only=True)
    dest_folder = serializers.CharField(required=True, write_only=True)
    dry_run = serializers.BooleanField(required=False, initial=False, write_only=True)
    item = serializers.CharField(required=False, write_only=True)
    verbosity = serializers.IntegerField(required=False, initial=0, min_value=0, max_value=4, write_only=True)

    class Meta:
        model = Job
        fields = ('defaults', 'archive_name', 'destination', 'dest_folder', 'dry_run', 'item', 'verbosity')

    def get_defaults(self, obj):
        defaults_dict = {'verbosity': 0, 'archive_name': '', 'destination': '',
                         'dest_folder': '', 'dry_run': False, 'item': ''}
        return defaults_dict

    def get_job_template_data(self, obj):
        return dict(name=obj.name, id=obj.id, description=obj.description)

    def validate_extra_vars(self, value):
        return vars_validate_or_raise(value)


class CatalogSerializer(BaseSerializer):
    class Meta:
        model = Catalog
        fields = ('id', 'url', 'archive_name', 'path', 'job', 'mode', 'mtime', 'owner', 'group', 'size', 'healthy')

    def get_related(self, obj):
        res = super(CatalogSerializer, self).get_related(obj)
        if obj.job:
            res['job'] = self.reverse('api:job_detail', kwargs={'pk': obj.job.pk})
        return res

    def to_representation(self, obj):
        ret = super(CatalogSerializer, self).to_representation(obj)
        if obj is not None and 'job' in ret and not obj.job:
            ret['job'] = None
        return ret


class CatalogListSerializer(DynamicFieldsSerializerMixin, CatalogSerializer):
    class Meta:
        model = Catalog
        fields = ('id', 'url', 'archive_name', 'path', 'job', 'mode', 'mtime', 'owner', 'group', 'size', 'healthy')
