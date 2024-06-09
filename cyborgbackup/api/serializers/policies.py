# Python
import logging

# Django REST Framework
from rest_framework import serializers

from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.validators import vars_validate_or_raise
# CyBorgBackup
from .base import BaseSerializer, EmptySerializer

logger = logging.getLogger('cyborgbackup.api.serializers.policies')


class PolicySerializer(BaseSerializer):
    class Meta:
        model = Policy
        fields = ('*', 'id', 'uuid', 'url', 'name', 'extra_vars',
                  'clients', 'repository', 'schedule', 'policy_type', 'keep_hourly',
                  'keep_yearly', 'keep_daily', 'keep_weekly', 'keep_monthly',
                  'vmprovider', 'next_run', 'mode_pull', 'enabled', 'created', 'modified',
                  'prehook', 'posthook')

    def get_related(self, obj):
        res = super(PolicySerializer, self).get_related(obj)
        res['launch'] = self.reverse('api:policy_launch', kwargs={'pk': obj.pk})
        res['calendar'] = self.reverse('api:policy_calendar', kwargs={'pk': obj.pk})
        if obj.schedule:
            res['schedule'] = self.reverse('api:schedule_detail', kwargs={'pk': obj.schedule.pk})
        if obj.repository:
            res['repository'] = self.reverse('api:repository_detail', kwargs={'pk': obj.repository.pk})
        return res

    def to_representation(self, obj):
        ret = super(PolicySerializer, self).to_representation(obj)
        if obj is not None and 'schedule' in ret and not obj.schedule:
            ret['schedule'] = None
        if obj is not None and 'repository' in ret and not obj.repository:
            ret['repository'] = None
        return ret


class PolicyListSerializer(PolicySerializer):
    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(PolicyListSerializer, self).get_field_names(declared_fields, info)
        # Meta multiple inheritance and -field_name options don't seem to be
        # taking effect above, so remove the undesired fields here.
        return tuple(x for x in field_names)

    def get_types(self):
        return ['policy']


class PolicyLaunchSerializer(BaseSerializer):
    defaults = serializers.SerializerMethodField()
    extra_vars = serializers.JSONField(required=False, write_only=True)
    verbosity = serializers.IntegerField(required=False, initial=0, min_value=0, max_value=4, write_only=True)

    class Meta:
        model = Policy
        fields = ('defaults', 'extra_vars', 'verbosity')

    def get_defaults(self, obj):
        defaults_dict = {'verbosity': 0, 'extra_vars': obj.extra_vars}
        return defaults_dict

    def get_job_template_data(self, obj):
        return dict(name=obj.name, id=obj.id, description=obj.description)

    def validate_extra_vars(self, value):
        return vars_validate_or_raise(value)


class PolicyCalendarSerializer(EmptySerializer):
    events = serializers.ListField(child=serializers.DateTimeField())


class PolicyVMModuleSerializer(EmptySerializer):
    modules = serializers.SerializerMethodField()


class PolicyModuleSerializer(EmptySerializer):
    modules = serializers.SerializerMethodField()
