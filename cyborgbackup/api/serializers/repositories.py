# Python
import logging

from cyborgbackup.main.models.repositories import Repository
# CyBorgBackup
from .base import BaseSerializer

logger = logging.getLogger('cyborgbackup.api.serializers.repositories')


class RepositorySerializer(BaseSerializer):
    """Read-only serializer for activity stream."""

    class Meta:
        model = Repository
        fields = ('id', 'uuid', 'url', 'name', 'path', 'repository_key',
                  'original_size', 'compressed_size', 'deduplicated_size', 'ready', 'enabled', 'created', 'modified')

    def update(self, obj, validated_data):
        obj = super(RepositorySerializer, self).update(obj, validated_data)
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
