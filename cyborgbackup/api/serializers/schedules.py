# Python
import logging

from cyborgbackup.main.models.schedules import Schedule
# CyBorgBackup
from .base import BaseSerializer

logger = logging.getLogger('cyborgbackup.api.serializers.schedules')


class ScheduleSerializer(BaseSerializer):
    """Read-only serializer for activity stream."""

    class Meta:
        model = Schedule
        fields = ('id', 'uuid', 'url', 'name', 'crontab', 'enabled', 'created', 'modified')

    def update(self, obj, validated_data):
        obj = super(ScheduleSerializer, self).update(obj, validated_data)
        return obj

    def validate(self, attrs):
        return attrs


class ScheduleListSerializer(ScheduleSerializer):
    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(ScheduleListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names)

    def get_types(self):
        return ['schedule']
