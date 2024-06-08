# Python
import logging

# Django REST Framework
from rest_framework import serializers

from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.policies import Policy
# CyBorgBackup
from .base import BaseSerializer

logger = logging.getLogger('cyborgbackup.api.serializers.clients')


class ClientSerializer(BaseSerializer):
    can_be_updated = serializers.SerializerMethodField()
    show_capabilities = ['edit', 'delete']

    class Meta:
        model = Client
        fields = ('*', '-name', '-description', 'hostname', 'ip', 'bandwidth_limit', 'port',
                  'version', 'ready', 'hypervisor_ready', 'hypervisor_name', 'can_be_updated',
                  'mark_as_to_update', 'enabled', 'behind_firewall', 'uuid')

    def get_summary_fields(self, obj):
        summary_dict = super(ClientSerializer, self).get_summary_fields(obj)
        relPolicies = Policy.objects.filter(clients__id=obj.pk)
        if relPolicies.exists():
            summary_dict['policies'] = []
            for pol in relPolicies:
                summary_dict['policies'].append({'id': pol.id, 'name': pol.name})

        return summary_dict

    def get_can_be_updated(self, obj):
        return obj.can_be_updated()


class ClientListSerializer(ClientSerializer):
    class Meta:
        fields = ('*',)

    def get_field_names(self, declared_fields, info):
        field_names = super(ClientListSerializer, self).get_field_names(declared_fields, info)
        return tuple(x for x in field_names)

    def get_types(self):
        return ['client']
