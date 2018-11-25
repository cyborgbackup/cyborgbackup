# Python
import re
import stat
import os
import cgi
import dateutil
import dateutil.relativedelta
import datetime
import time
import socket
import sys
import logging
import requests
import tzcron
import pytz
import collections
import json
from base64 import b64encode
from collections import OrderedDict, Iterable
import six

# Django
from django.conf import settings as dsettings
from django.core.exceptions import FieldError, ObjectDoesNotExist
from django.db.models import Q, Count, F, Max
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils.encoding import smart_text
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _

# Django REST Framework
from rest_framework.exceptions import PermissionDenied, ParseError
from rest_framework.parsers import FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler
from rest_framework import status

# CyBorgBackup
from cyborgbackup.api.filters import V1CredentialFilterBackend
from cyborgbackup.api.generics import *
from cyborgbackup.main.models import *
from cyborgbackup.main.utils.common import * # noqa
from cyborgbackup.main.utils.encryption import decrypt_field, encrypt_value
from cyborgbackup.main.utils.filters import SmartFilter
from cyborgbackup.main.utils.common import filter_insights_api_response
from cyborgbackup.main.utils.callbacks import CallbackQueueDispatcher
from cyborgbackup.api.renderers import * # noqa
from cyborgbackup.api.serializers import * # noqa
from cyborgbackup.main.constants import ACTIVE_STATES
#from cyborgbackup.api.exceptions import ActiveJobConflict
from cyborgbackup.api.permissions import *

import ansiconv
from wsgiref.util import FileWrapper

logger = logging.getLogger('cyborgbackup.api.views')

def api_exception_handler(exc, context):
    '''
    Override default API exception handler to catch IntegrityError exceptions.
    '''
    if isinstance(exc, IntegrityError):
        exc = ParseError(exc.args[0])
    if isinstance(exc, FieldError):
        exc = ParseError(exc.args[0])
    return exception_handler(exc, context)

class JobDeletionMixin(object):
    '''
    Special handling when deleting a running job object.
    '''
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        try:
            if obj.job_node.workflow_job.status in ACTIVE_STATES:
                raise PermissionDenied(detail=_('Cannot delete job resource when associated workflow job is running.'))
        except self.model.job_node.RelatedObjectDoesNotExist:
            pass
        # Still allow deletion of new status, because these can be manually created
        if obj.status in ACTIVE_STATES and obj.status != 'new':
            raise PermissionDenied(detail=_("Cannot delete running job resource."))
        elif not obj.event_processing_finished:
            # Prohibit deletion if job events are still coming in
            if obj.finished and now() < obj.finished + dateutil.relativedelta.relativedelta(minutes=1):
                # less than 1 minute has passed since job finished and events are not in
                return Response({"error": _("Job has not finished processing events.")},
                                status=status.HTTP_400_BAD_REQUEST)
            else:
                # if it has been > 1 minute, events are probably lost
                logger.warning('Allowing deletion of {} through the API without all events '
                               'processed.'.format(obj.log_format))
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class ApiRootView(APIView):

    permission_classes = (AllowAny,)
    view_name = _('REST API')
    versioning_class = None
    swagger_topic = 'Versioning'

    def get(self, request, format=None):
        ''' List supported API versions '''

        v1 = reverse('api:api_v1_root_view', kwargs={'version': 'v1'})
        data = dict(
            description=_('CyBorgBackup API Rest'),
            current_version=v1,
            available_versions=dict(v1=v1),
        )
        return Response(data)

class ApiVersionRootView(APIView):

    permission_classes = (AllowAny,)
    swagger_topic = 'Versioning'

    def get(self, request, format=None):
        ''' List top level resources '''
        data = OrderedDict()
        data['ping'] = reverse('api:api_v1_ping_view', request=request)
        data['config'] = reverse('api:api_v1_config_view', request=request)
        data['me'] = reverse('api:user_me_list', request=request)
        data['users'] = reverse('api:user_list', request=request)
        data['jobs'] = reverse('api:job_list', request=request)
        data['job_events'] = reverse('api:job_event_list', request=request)
        data['settings'] = reverse('api:setting_list', request=request)
        data['clients'] = reverse('api:client_list', request=request)
        data['schedules'] = reverse('api:schedule_list', request=request)
        data['repositories'] = reverse('api:repository_list', request=request)
        data['policies'] = reverse('api:policy_list', request=request)
        data['catalogs'] = reverse('api:catalog_list', request=request)
        return Response(data)

class ApiV1RootView(ApiVersionRootView):
    view_name = _('Version 1')

class ApiV1PingView(APIView):
    """A simple view that reports very basic information about this
    instance, which is acceptable to be public information.
    """
    permission_classes = (AllowAny,)
    authentication_classes = ()
    view_name = _('Ping')
    swagger_topic = 'System Configuration'

    def get(self, request, format=None):
        """Return some basic information about this instance

        Everything returned here should be considered public / insecure, as
        this requires no auth and is intended for use by the installer process.
        """
        response = {
            'version': get_cyborgbackup_version(),
        }

        response['ping'] = "pong"
        return Response(response)

class ApiV1ConfigView(APIView):

    permission_classes = (IsAuthenticated,)
    view_name = _('Configuration')
    swagger_topic = 'System Configuration'

    def check_permissions(self, request):
        super(ApiV1ConfigView, self).check_permissions(request)
        if not request.user.is_superuser and request.method.lower() not in {'options', 'head', 'get'}:
            self.permission_denied(request)  # Raises PermissionDenied exception.

    def get(self, request, format=None):
        '''Return various sitewide configuration settings'''

        data = dict(
            time_zone=dsettings.TIME_ZONE,
            debug=dsettings.DEBUG,
            sql_debug=dsettings.SQL_DEBUG,
            allowed_hosts=dsettings.ALLOWED_HOSTS,
            beat_schedule=dsettings.CELERY_BEAT_SCHEDULE,
            version=get_cyborgbackup_version(),
        )

        return Response(data)

class AuthView(APIView):
    ''' List enabled single-sign-on endpoints '''

    authentication_classes = []
    permission_classes = (AllowAny,)
    swagger_topic = 'System Configuration'

    def get(self, request):
        from rest_framework.reverse import reverse
        data = OrderedDict()
        err_backend, err_message = request.session.get('social_auth_error', (None, None))
        auth_backends = load_backends(settings.AUTHENTICATION_BACKENDS, force_load=True).items()
        # Return auth backends in consistent order: Google, GitHub, SAML.
        auth_backends.sort(key=lambda x: 'g' if x[0] == 'google-oauth2' else x[0])
        for name, backend in auth_backends:
            if (not feature_exists('enterprise_auth') and
                    not feature_enabled('ldap')) or \
                (not feature_enabled('enterprise_auth') and
                 name in ['saml', 'radius']):
                    continue
            login_url = reverse('social:begin', args=(name,))
            complete_url = request.build_absolute_uri(reverse('social:complete', args=(name,)))
            backend_data = {
                'login_url': login_url,
                'complete_url': complete_url,
            }
            if err_backend == name and err_message:
                backend_data['error'] = err_message
            data[name] = backend_data
        return Response(data)

class UserList(ListCreateAPIView):

    model = User
    serializer_class = UserSerializer
    permission_classes = (UserPermission,)

    def post(self, request, *args, **kwargs):
        ret = super(UserList, self).post(request, *args, **kwargs)
        return ret


class UserMeList(ListAPIView):

    model = User
    serializer_class = UserSerializer
    view_name = _('Me')

    def get_queryset(self):
        return self.model.objects.filter(pk=self.request.user.pk)

class UserDetail(RetrieveUpdateDestroyAPIView):

    model = User
    serializer_class = UserSerializer

    def update_filter(self, request, *args, **kwargs):
        ''' make sure non-read-only fields that can only be edited by admins, are only edited by admins '''
        obj = self.get_object()

        su_only_edit_fields = ('is_superuser')
        admin_only_edit_fields = ('username', 'is_active')

        fields_to_check = ()
        if not request.user.is_superuser:
            fields_to_check += su_only_edit_fields

        bad_changes = {}
        for field in fields_to_check:
            left = getattr(obj, field, None)
            right = request.data.get(field, None)
            if left is not None and right is not None and left != right:
                bad_changes[field] = (left, right)
        if bad_changes:
            raise PermissionDenied(_('Cannot change %s.') % ', '.join(bad_changes.keys()))

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        return super(UserDetail, self).destroy(request, *args, **kwargs)

class StdoutANSIFilter(object):

    def __init__(self, fileobj):
        self.fileobj = fileobj
        self.extra_data = ''
        if hasattr(fileobj, 'close'):
            self.close = fileobj.close

    def read(self, size=-1):
        data = self.extra_data
        while size > 0 and len(data) < size:
            line = self.fileobj.readline(size)
            if not line:
                break
            # Remove ANSI escape sequences used to embed event data.
            line = re.sub(r'\x1b\[K(?:[A-Za-z0-9+/=]+\x1b\[\d+D)+\x1b\[K', '', line)
            # Remove ANSI color escape sequences.
            line = re.sub(r'\x1b[^m]*m', '', line)
            data += line
        if size > 0 and len(data) > size:
            self.extra_data = data[size:]
            data = data[:size]
        else:
            self.extra_data = ''
        return data

class JobList(ListCreateAPIView):

    model = Job
    #metadata_class = JobTypeMetadata
    serializer_class = JobListSerializer

    @property
    def allowed_methods(self):
        methods = super(JobList, self).allowed_methods
        return methods

    # NOTE: Remove in 3.3, switch ListCreateAPIView to ListAPIView
    def post(self, request, *args, **kwargs):
        return super(JobList, self).post(request, *args, **kwargs)

class JobDetail(JobDeletionMixin, RetrieveUpdateDestroyAPIView):

    model = Job
    #metadata_class = JobTypeMetadata
    serializer_class = JobSerializer

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        # Only allow changes (PUT/PATCH) when job status is "new".
        if obj.status != 'new':
            return self.http_method_not_allowed(request, *args, **kwargs)
        return super(JobDetail, self).update(request, *args, **kwargs)


class StdoutMaxBytesExceeded(Exception):

    def __init__(self, total, supported):
        self.total = total
        self.supported = supported

class JobStdout(RetrieveAPIView):

    model = Job
    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    serializer_class = JobStdoutSerializer
    renderer_classes = [BrowsableAPIRenderer, renderers.StaticHTMLRenderer,
                        PlainTextRenderer, AnsiTextRenderer,
                        renderers.JSONRenderer, DownloadTextRenderer, AnsiDownloadRenderer]
    filter_backends = ()

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        try:
            target_format = request.accepted_renderer.format
            if target_format in ('html', 'api', 'json'):
                content_format = request.query_params.get('content_format', 'html')
                content_encoding = request.query_params.get('content_encoding', None)
                start_line = request.query_params.get('start_line', 0)
                end_line = request.query_params.get('end_line', None)
                dark_val = request.query_params.get('dark', '')
                dark = bool(dark_val and dark_val[0].lower() in ('1', 't', 'y'))
                content_only = bool(target_format in ('api', 'json'))
                dark_bg = (content_only and dark) or (not content_only and (dark or not dark_val))
                content, start, end, absolute_end = job.result_stdout_raw_limited(start_line, end_line)

                # Remove any ANSI escape sequences containing job event data.
                content = re.sub(r'\x1b\[K(?:[A-Za-z0-9+/=]+\x1b\[\d+D)+\x1b\[K', '', content)

                body = ansiconv.to_html(cgi.escape(content))

                context = {
                    'title': get_view_name(self.__class__),
                    'body': mark_safe(body),
                    'dark': dark_bg,
                    'content_only': content_only,
                }
                data = render_to_string('api/stdout.html', context).strip()

                if target_format == 'api':
                    return Response(mark_safe(data))
                if target_format == 'json':
                    if content_encoding == 'base64' and content_format == 'ansi':
                        return Response({'range': {'start': start, 'end': end, 'absolute_end': absolute_end}, 'content': b64encode(content.encode('utf-8'))})
                    elif content_format == 'html':
                        return Response({'range': {'start': start, 'end': end, 'absolute_end': absolute_end}, 'content': body})
                return Response(data)
            elif target_format == 'txt':
                return Response(job.result_stdout)
            elif target_format == 'ansi':
                return Response(job.result_stdout_raw)
            elif target_format in {'txt_download', 'ansi_download'}:
                filename = '{type}_{pk}{suffix}.txt'.format(
                    type=camelcase_to_underscore(job.__class__.__name__),
                    pk=job.id,
                    suffix='.ansi' if target_format == 'ansi_download' else ''
                )
                content_fd = job.result_stdout_raw_handle(enforce_max_bytes=False)
                if target_format == 'txt_download':
                    content_fd = StdoutANSIFilter(content_fd)
                response = HttpResponse(FileWrapper(content_fd), content_type='text/plain')
                response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
                return response
            else:
                return super(UnifiedJobStdout, self).retrieve(request, *args, **kwargs)
        except StdoutMaxBytesExceeded as e:
            response_message = _(
                "Standard Output too large to display ({text_size} bytes), "
                "only download supported for sizes over {supported_size} bytes.").format(
                    text_size=e.total, supported_size=e.supported
                )
            if request.accepted_renderer.format == 'json':
                return Response({'range': {'start': 0, 'end': 1, 'absolute_end': 1}, 'content': response_message})
            else:
                return Response(response_message)

class JobStart(GenericAPIView):

    model = Job
    obj_permission_type = 'start'
    serializer_class = EmptySerializer
    deprecated = True

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        data = dict(
            can_start=obj.can_start,
        )
        #if obj.can_start:
        #    data['ask_variables_on_launch'] = obj.ask_variables_on_launch
        return Response(data)

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.can_start:
            result = obj.signal_start(**request.data)
            if not result:
                return Response(data, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(status=status.HTTP_202_ACCEPTED)
        else:
            return self.http_method_not_allowed(request, *args, **kwargs)

class JobCancel(RetrieveAPIView):

    model = Job
    obj_permission_type = 'cancel'
    serializer_class = JobCancelSerializer

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.can_cancel:
            obj.cancel()
            return Response(status=status.HTTP_202_ACCEPTED)
        else:
            return self.http_method_not_allowed(request, *args, **kwargs)

class JobRelaunch(RetrieveAPIView):

    model = Job
    obj_permission_type = 'start'
    serializer_class = JobRelaunchSerializer

    def update_raw_data(self, data):
        data = super(JobRelaunch, self).update_raw_data(data)
        try:
            obj = self.get_object()
        except PermissionDenied:
            return data
        return data

    @csrf_exempt
    @transaction.non_atomic_requests
    def dispatch(self, *args, **kwargs):
        return super(JobRelaunch, self).dispatch(*args, **kwargs)

    def check_object_permissions(self, request, obj):
        return super(JobRelaunch, self).check_object_permissions(request, obj)

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        context = self.get_serializer_context()

        modified_data = request.data.copy()
        #modified_data.setdefault('credential_passwords', {})
        #for password in obj.passwords_needed_to_start:
        #    if password in modified_data:
        #        modified_data['credential_passwords'][password] = modified_data[password]

        # Note: is_valid() may modify request.data
        # It will remove any key/value pair who's key is not in the 'passwords_needed_to_start' list
        serializer = self.serializer_class(data=modified_data, context=context, instance=obj)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        jobs = Job.objects.filter(client=obj.client_id)
        if jobs.exists():
            for job in jobs:
                if job.status in ['waiting', 'pending', 'running']:
                    return Response({'detail': 'Backup job already running for this client.'}, status=status.HTTP_400_BAD_REQUEST)

        copy_kwargs = {}

        new_job = obj.copy_job(**copy_kwargs)
        result = new_job.signal_start()
        if not result:
            data = dict(msg=_('Error starting job!'))
            new_job.delete()
            return Response(data, status=status.HTTP_400_BAD_REQUEST)
        else:
            data = JobSerializer(new_job, context=context).data
            # Add job key to match what old relaunch returned.
            data['job'] = new_job.id
            headers = {'Location': new_job.get_absolute_url(request=request)}
            return Response(data, status=status.HTTP_201_CREATED, headers=headers)

class JobEventList(ListAPIView):

    model = JobEvent
    serializer_class = JobEventSerializer

class JobEventDetail(RetrieveAPIView):

    model = JobEvent
    serializer_class = JobEventSerializer

class BaseJobEventsList(SubListAPIView):

    model = JobEvent
    serializer_class = JobEventSerializer
    parent_model = None # Subclasses must define this attribute.
    relationship = 'job_events'
    view_name = _('Job Events List')
    search_fields = ('stdout',)

    def finalize_response(self, request, response, *args, **kwargs):
        response['X-UI-Max-Events'] = 4000
        return super(BaseJobEventsList, self).finalize_response(request, response, *args, **kwargs)

class JobJobEventsList(BaseJobEventsList):

    parent_model = Job

    def get_queryset(self):
        job = self.get_parent_object()
        self.check_parent_access(job)
        qs = job.job_events
        #qs = qs.select_related('host')
        return qs.all()

class SettingList(ListAPIView):

    model = Setting
    serializer_class = SettingListSerializer

    @property
    def allowed_methods(self):
        methods = super(SettingList, self).allowed_methods
        return methods


class SettingDetail(RetrieveUpdateAPIView):

    model = Setting
    serializer_class = SettingSerializer


class ClientList(ListCreateAPIView):

    model = Client
    serializer_class = ClientListSerializer

    @property
    def allowed_methods(self):
        methods = super(ClientList, self).allowed_methods
        return methods

    def post(self, request, *args, **kwargs):
        return super(ClientList, self).post(request, *args, **kwargs)


class ClientDetail(RetrieveUpdateDestroyAPIView):

    model = Client
    serializer_class = ClientSerializer


class ScheduleList(ListCreateAPIView):

    model = Schedule
    serializer_class = ScheduleListSerializer

    @property
    def allowed_methods(self):
        methods = super(ScheduleList, self).allowed_methods
        return methods


class ScheduleDetail(RetrieveUpdateDestroyAPIView):

    model = Schedule
    serializer_class = ScheduleSerializer


class RepositoryList(ListCreateAPIView):

    model = Repository
    serializer_class = RepositoryListSerializer

    @property
    def allowed_methods(self):
        methods = super(RepositoryList, self).allowed_methods
        return methods


class RepositoryDetail(RetrieveUpdateDestroyAPIView):

    model = Repository
    serializer_class = RepositorySerializer


class PolicyList(ListCreateAPIView):

    model = Policy
    serializer_class = PolicySerializer


class PolicyDetail(RetrieveUpdateDestroyAPIView):

    model = Policy
    serializer_class = PolicySerializer


class PolicyVMModule(ListAPIView):

    model = Policy
    serializer_class = PolicyVMModuleSerializer

    def list(self, request, *args, **kwargs):
        data = get_module_provider()
        return Response(data)


class PolicyCalendar(ListAPIView):

    model = Policy
    serializer_class = PolicyCalendarSerializer

    def list(self, request, *args, **kwargs):
        data = OrderedDict()
        obj = self.get_object()
        now = datetime.datetime.now(pytz.utc)
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_month = datetime.datetime(now.year, (start_month + dateutil.relativedelta.relativedelta(months=1)).month, 1) - datetime.timedelta(days=1)
        end_month = end_month.replace(hour=23, minute=59, second=50, tzinfo=pytz.utc)
        schedule = tzcron.Schedule(obj.schedule.crontab, pytz.utc, start_month, end_month)
        return Response([s.isoformat() for s in schedule])


class PolicyLaunch(RetrieveAPIView):

    model = Policy
    serializer_class = PolicyLaunchSerializer

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
            jobs = Job.objects.filter(client=client.pk)
            if jobs.exists():
                for job in jobs:
                    if job.status in ['waiting', 'pending', 'running']:
                        return Response({'detail': 'Backup job already running for theses clients.'}, status=status.HTTP_400_BAD_REQUEST)

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
        '''
        Model objects cannot be serialized by DRF,
        this replaces objects with their ids for inclusion in response
        '''

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

class CatalogList(ListCreateAPIView):

    model = Catalog
    serializer_class = CatalogListSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        if set(data.keys()).intersection(['archive_name', 'job', 'event', 'catalog']):
            callback = CallbackQueueDispatcher()
            callback.dispatch(data)
            return Response(OrderedDict(), status=status.HTTP_201_CREATED)

        return Response(OrderedDict(), status=status.HTTP_400_BAD_REQUEST)


class CatalogDetail(RetrieveUpdateDestroyAPIView):

    model = Catalog
    serializer_class = CatalogSerializer
