# Python
import logging

# Django
from django.utils.translation import gettext_lazy as _

# Django REST Framework
from rest_framework import serializers

# CyBorgBackup
from .base import BaseSerializer
from cyborgbackup.main.models.repositories import Repository

logger = logging.getLogger('cyborgbackup.api.serializers.repositories')


class RepositorySerializer(BaseSerializer):
    force_ready = serializers.BooleanField(required=False, default=False, write_only=True,
                                           help_text=_('Write-only field used to force ready on the object.'))

    class Meta:
        model = Repository
        fields = ('id', 'uuid', 'url', 'name', 'path', 'repository_key',
                  'original_size', 'compressed_size', 'deduplicated_size', 'ready',
                  'enabled', 'created', 'modified', 'force_ready')

    def update(self, obj, validated_data):
        obj = super(RepositorySerializer, self).update(obj, validated_data)
        if validated_data.get('force_ready', False):
            obj.ready = True
            obj.save()
        return obj

    def validate(self, attrs):
        return attrs


class RepositoryListSerializer(RepositorySerializer):
    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(RepositoryListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names)

    def get_types(self):
        return ['repository']
