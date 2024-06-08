# Python
import datetime
import logging
from collections import OrderedDict

import dateutil
import pytz
import tzcron
from rest_framework import status
# Django REST Framework
from rest_framework.response import Response

from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.utils.common import get_module_provider
# CyBorgBackup
from .generics import ListAPIView, RetrieveAPIView, RetrieveUpdateDestroyAPIView, ListCreateAPIView
from ..serializers.jobs import JobSerializer
from ..serializers.policies import PolicySerializer, PolicyLaunchSerializer, PolicyModuleSerializer, \
    PolicyCalendarSerializer, PolicyVMModuleSerializer
from ...main.modules import Querier

logger = logging.getLogger('cyborgbackups.api.views.policies')


class PolicyList(ListCreateAPIView):
    model = Policy
    serializer_class = PolicySerializer
    tags = ['Policy']


class PolicyDetail(RetrieveUpdateDestroyAPIView):
    model = Policy
    serializer_class = PolicySerializer
    tags = ['Policy']


class PolicyVMModule(ListAPIView):
    model = Policy
    serializer_class = PolicyVMModuleSerializer
    tags = ['Policy']

    def list(self, request, *args, **kwargs):
        data = get_module_provider()
        return Response(data)


class PolicyModule(ListCreateAPIView):
    model = Policy
    serializer_class = PolicyModuleSerializer
    tags = ['Policy']

    def callModule(self, request, args, kwargs):
        module = kwargs['module']
        client_id = kwargs['client']
        data = {}
        if module == 'vm':
            data = get_module_provider()
        else:
            client = Client.objects.get(pk=client_id)
            if client:
                q = Querier()
                params = {**request.query_params.dict(), **request.data}
                data = q.querier(module, client, params)
                if data == -1:
                    return Response({}, status=status.HTTP_204_NO_CONTENT)
        return Response(data)

    def list(self, request, *args, **kwargs):
        return self.callModule(request, args, kwargs)

    def post(self, request, *args, **kwargs):
        return self.callModule(request, args, kwargs)


class PolicyCalendar(ListAPIView):
    model = Policy
    serializer_class = PolicyCalendarSerializer
    tags = ['Policy']

    def list(self, request, *args, **kwargs):
        obj = self.get_object()
        now = datetime.datetime.now(pytz.utc)
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year = now.year
        if start_month.month == 12:
            year += 1
        relative_month = dateutil.relativedelta.relativedelta(months=1)
        end_month = datetime.datetime(year, (start_month + relative_month).month, 1) - datetime.timedelta(days=1)
        end_month = end_month.replace(hour=23, minute=59, second=50, tzinfo=pytz.utc)
        schedule = tzcron.Schedule(obj.schedule.crontab, pytz.utc, start_month, end_month)
        return Response([s.isoformat() for s in schedule])


class PolicyLaunch(RetrieveAPIView):
    model = Policy
    serializer_class = PolicyLaunchSerializer
    tags = ['Policy']

    def update_raw_data(self, data):
        obj = self.get_object()
        extra_vars = data.pop('extra_vars', None) or {}
        if obj:
            data['extra_vars'] = extra_vars
        return data

    def post(self, request, *args, **kwargs):
        obj = self.get_object()

        serializer = self.serializer_class(data=request.data, context={'job': obj})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        for client in obj.clients.all():
            jobs = Job.objects.filter(client=client.pk, repository=obj.repository.pk)
            if jobs.exists():
                for job in jobs:
                    if job.status in ['waiting', 'pending', 'running']:
                        return Response({'detail': 'Backup job already running for theses clients.'},
                                        status=status.HTTP_400_BAD_REQUEST)

        new_job = obj.create_job(**serializer.validated_data)
        result = new_job.signal_start()

        if not result:
            data = OrderedDict()
            new_job.delete()
            return Response(data, status=status.HTTP_400_BAD_REQUEST)
        else:
            data = OrderedDict()
            data['job'] = new_job.id
            data.update(JobSerializer(new_job, context=self.get_serializer_context()).to_representation(new_job))
            return Response(data, status=status.HTTP_201_CREATED)

    def sanitize_for_response(self, data):
        """
        Model objects cannot be serialized by DRF,
        this replaces objects with their ids for inclusion in response
        """

        def display_value(val):
            if hasattr(val, 'id'):
                return val.id
            else:
                return val

        sanitized_data = {}
        for field_name, value in data.items():
            if isinstance(value, (set, list)):
                sanitized_data[field_name] = []
                for sub_value in value:
                    sanitized_data[field_name].append(display_value(sub_value))
            else:
                sanitized_data[field_name] = display_value(value)

        return sanitized_data
