# Python
import logging

# Django
from django.utils.translation import gettext_lazy as _
# Django REST Framework
from rest_framework import serializers

from cyborgbackup.main.models.users import User
# CyBorgBackup
from .base import BaseSerializer

logger = logging.getLogger('cyborgbackup.api.serializers.stats')


class UserSerializer(BaseSerializer):
    password = serializers.CharField(required=False, default='', write_only=True,
                                     help_text=_('Write-only field used to change the password.'))
    show_capabilities = ['edit', 'delete']

    class Meta:
        model = User
        fields = ('*', '-name', '-description', '-modified', '-username',
                  'first_name', 'last_name', 'email', 'is_superuser', 'password',
                  '-created_by', '-modified_by', 'notify_backup_daily',
                  'notify_backup_weekly', 'notify_backup_monthly',
                  'notify_backup_success', 'notify_backup_failed',
                  'notify_backup_summary')

    def to_representation(self, obj):
        ret = super(UserSerializer, self).to_representation(obj)
        ret.pop('password', None)
        return ret

    def get_validation_exclusions(self, obj=None):
        ret = super(UserSerializer, self).get_validation_exclusions(obj)
        ret.append('password')
        return ret

    def validate_password(self, value):
        if not self.instance and value in (None, ''):
            raise serializers.ValidationError(_('Password required for new User.'))
        return value

    def _update_password(self, obj, new_password):
        # For now we're not raising an error, just not saving password for
        # users managed by LDAP who already have an unusable password set.
        if new_password:
            obj.set_password(new_password)
            obj.save(update_fields=['password'])
        elif not obj.password:
            obj.set_unusable_password()
            obj.save(update_fields=['password'])

    def create(self, validated_data):
        new_password = validated_data.pop('password', None)
        obj = super(UserSerializer, self).create(validated_data)
        self._update_password(obj, new_password)
        return obj

    def update(self, obj, validated_data):
        new_password = validated_data.pop('password', None)
        obj = super(UserSerializer, self).update(obj, validated_data)
        self._update_password(obj, new_password)
        return obj
