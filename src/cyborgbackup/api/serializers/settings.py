# Python
import logging

# CyBorgBackup
from .base import BaseSerializer
from cyborgbackup.main.models.settings import Setting
from ..fields import VerbatimField

logger = logging.getLogger('cyborgbackup.api.serializers.settings')

class SettingSerializer(BaseSerializer):
    """Read-only serializer for activity stream."""

    value = VerbatimField(allow_null=True)

    class Meta:
        model = Setting
        fields = ('id', 'url', 'key', 'type', 'setting_type', 'value', 'group', 'order', 'created', 'modified')

    def update(self, obj, validated_data):
        validated_data.pop('key', None)
        obj = super(SettingSerializer, self).update(obj, validated_data)
        return obj

    def validate(self, attrs):
        attrs.pop('key', None)
        return attrs


class SettingListSerializer(SettingSerializer):

    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(SettingListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names)

    def get_types(self):
        if type(self) is SettingListSerializer:
            return ['setting']
        else:
            return super(SettingListSerializer, self).get_types()