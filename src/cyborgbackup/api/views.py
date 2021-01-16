# Python
import re
import cgi
import dateutil
import dateutil.relativedelta
import datetime
import logging
import tzcron
import pytz
import pymongo
from base64 import b64encode
from collections import OrderedDict

# Django
from django.conf import settings as dsettings
from django.core.exceptions import FieldError
from django.db import IntegrityError, transaction
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils.translation import ugettext_lazy as _

# Django REST Framework
from rest_framework.exceptions import PermissionDenied, ParseError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler
from rest_framework import status, renderers

# CyBorgBackup
from rest_framework_simplejwt.views import TokenObtainPairView

from cyborgbackup.api.generics import (APIView, GenericAPIView, ListAPIView,
                                       ListCreateAPIView, SubListAPIView, RetrieveAPIView,
                                       RetrieveUpdateAPIView, RetrieveUpdateDestroyAPIView,
                                       get_view_name)
from cyborgbackup.main.models import reverse
from cyborgbackup.main.models.events import JobEvent
from cyborgbackup.main.models.catalogs import Catalog
from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.schedules import Schedule
from cyborgbackup.main.models.repositories import Repository
from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.models.users import User
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.utils.common import get_module_provider, camelcase_to_underscore, get_cyborgbackup_version
from cyborgbackup.main.utils.callbacks import CallbackQueueDispatcher
from cyborgbackup.main.utils.encryption import Keypair
from cyborgbackup.main.modules import Querier
from cyborgbackup.api.renderers import (BrowsableAPIRenderer, PlainTextRenderer,
                                        DownloadTextRenderer, AnsiDownloadRenderer, AnsiTextRenderer)
from cyborgbackup.api.serializers import (EmptySerializer, UserSerializer,
                                          JobSerializer, JobStdoutSerializer, JobCancelSerializer,
                                          JobRelaunchSerializer, JobListSerializer, JobEventSerializer,
                                          SettingSerializer, SettingListSerializer,
                                          ClientSerializer, ClientListSerializer, ScheduleSerializer,
                                          ScheduleListSerializer, RepositorySerializer, RepositoryListSerializer,
                                          PolicySerializer, PolicyLaunchSerializer, PolicyModuleSerializer,
                                          PolicyCalendarSerializer, PolicyVMModuleSerializer,
                                          CatalogSerializer, CatalogListSerializer, StatsSerializer,
                                          CyborgTokenObtainPairSerializer, RestoreLaunchSerializer)
from cyborgbackup.main.constants import ACTIVE_STATES
from cyborgbackup.api.permissions import UserPermission

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
        data['restore'] = reverse('api:restore_launch', request=request)
        data['catalogs'] = reverse('api:catalog_list', request=request)
        data['stats'] = reverse('api:stats', request=request)
        data['escatalogs'] = reverse('api:escatalog_list', request=request)
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
            # beat_schedule=dsettings.CELERY_BEAT_SCHEDULE,
            version=get_cyborgbackup_version(),
        )

        return Response(data)


class AuthView(APIView):
    ''' List enabled single-sign-on endpoints '''

    authentication_classes = []
    permission_classes = (AllowAny,)
    swagger_topic = 'System Configuration'

    def get(self, request):
        data = OrderedDict()
        err_backend, err_message = request.session.get('social_auth_error', (None, None))
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
        # admin_only_edit_fields = ('username', 'is_active')

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
                        return Response({'range': {'start': start, 'end': end, 'absolute_end': absolute_end},
                                         'content': b64encode(content.encode('utf-8'))})
                    elif content_format == 'html':
                        return Response({'range': {'start': start, 'end': end, 'absolute_end': absolute_end},
                                         'content': body})
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
                return super(JobStdout, self).retrieve(request, *args, **kwargs)
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
        return Response(data)

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.can_start:
            result = obj.signal_start(**request.data)
            if not result:
                return Response(request.data, status=status.HTTP_400_BAD_REQUEST)
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
            self.get_object()
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
        serializer = self.serializer_class(data=modified_data, context=context, instance=obj)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        jobs = Job.objects.filter(client=obj.client_id)
        if jobs.exists():
            for job in jobs:
                if job.status in ['waiting', 'pending', 'running']:
                    return Response({'detail': 'Backup job already running for this client.'},
                                    status=status.HTTP_400_BAD_REQUEST)

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
    parent_model = None  # Subclasses must define this attribute.
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


class SettingGetPublicSsh(ListAPIView):

    model = Setting
    serializer_class = EmptySerializer

    def list(self, request, *args, **kwargs):
        set = Setting.get_value(name='cyborgbackup_ssh_key')
        if set:
            return Response(Keypair.get_publickey(set))
        else:
            return Response([])


class SettingGenerateSsh(ListCreateAPIView):

    model = Setting
    serializer_class = EmptySerializer

    def list(self, request, *args, **kwargs):
        set = Setting.objects.get(key='cyborgbackup_ssh_key')
        if set.value != '':
            return Response([], status=status.HTTP_200_OK)
        else:
            return Response([], status=status.HTTP_204_NO_CONTENT)

    def create(self, request, *args, **kwargs):
        data = request.data
        set = Setting.objects.get(key='cyborgbackup_ssh_key')
        logger.debug(data)
        if set:
            if (set.value != '' and 'force' in data.keys()) \
                    or (set.value == ''):
                sshpass = Setting.objects.get(key='cyborgbackup_ssh_password')
                password = None
                if sshpass and sshpass.value != '':
                    password = sshpass.value
                kp = Keypair(passphrase=password, size=data['size'], type=data['type'])
                kp.generate()
                set.value = kp.privatekey
                set.save()
                sshpass.value = kp.passphrase
                sshpass.save()
                return Response({
                    'pubkey': kp.public_key
                }, status=status.HTTP_201_CREATED)
            else:
                return Response(OrderedDict(), status=status.HTTP_409_CONFLICT)
        else:
            return Response(OrderedDict(), status=status.HTTP_409_CONFLICT)


class ClientList(ListCreateAPIView):

    model = Client
    serializer_class = ClientListSerializer

    @property
    def allowed_methods(self):
        methods = super(ClientList, self).allowed_methods
        return methods


class ClientDetail(RetrieveUpdateDestroyAPIView):

    model = Client
    serializer_class = ClientSerializer

    def patch(self, request, *args, **kwargs):
        obj = self.get_object()
        logger.debug(request.data)

        serializer = self.serializer_class(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        policies = Policy.objects.all()
        if policies.exists() and 'policies' in request.data.keys():
            for pol in policies:
                if pol.id in request.data['policies'] and len([x for x in pol.clients.all() if x.id == obj.id]) == 0:
                    logger.debug('Add client to policy {}'.format(pol.name))
                    pol.clients
                if len([x for x in pol.clients.all() if x.id == obj.id]) > 0 and pol.id not in request.data['policies']:
                    logger.debug('Remove client from policy {}'.format(pol.name))

        return super(ClientDetail, self).patch(request, *args, **kwargs)


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


class PolicyModule(ListCreateAPIView):

    model = Policy
    serializer_class = PolicyModuleSerializer

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


class RestoreLaunch(ListCreateAPIView):

    model = Job
    serializer_class = RestoreLaunchSerializer

    def list(self, request, *args, **kwargs):
        data = []
        return Response(data)

    def create(self, request, *args, **kwargs):
        result = None
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        obj = serializer.validated_data
        jobs = Job.objects.filter(archive_name=obj['archive_name'])
        if jobs.exists():
            job = jobs[0]
            client = job.client

            jobs_client = Job.objects.filter(client=client.pk)
            if jobs_client.exists():
                for job_client in jobs_client:
                    if job_client.status in ['waiting', 'pending', 'running']:
                        return Response({'detail': 'Backup job already running for this client.'},
                                        status=status.HTTP_400_BAD_REQUEST)

            extra_vars = {
                'item': serializer.validated_data['item'],
                'dest': serializer.validated_data['destination'],
                'dry_run': serializer.validated_data['dry_run'],
                'dest_folder': serializer.validated_data['dest_folder']
            }

            new_job = job.policy.create_restore_job(source_job=job, extra_vars=extra_vars)

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


class MongoCatalog(ListAPIView):

    model = Catalog
    serializer_class = CatalogSerializer

    def list(self, request, *args, **kwargs):
        logger.debug(request.data)
        data = []
        archive_name = request.GET.get('archive_name', None)
        path = request.GET.get('path__regexp', None)
        db = pymongo.MongoClient().local
        if path:
            obj = db.catalog.find({'$and':[{'archive_name': archive_name}, {'path':{'$regex':'^{}$'.format(path)}}]}, { "_id": 0, "archive_name": 1, "path": 1, "type": 1, "size": 1, "healthy": 1, "mtime": 1, "owner": 1, "group": 1, "mode": 1})
            data = list(obj)
            return Response({'count': len(data), 'results': data})
        else:
            obj = db.catalog.count({'archive_name': archive_name})
            return Response({'count': obj, 'results': []})


class Stats(ListAPIView):

    model = Job
    serializer_class = StatsSerializer

    def list(self, request, *args, **kwargs):
        data = []
        now = datetime.datetime.now(pytz.utc)
        last_30_days = now - datetime.timedelta(days=30)
        jobs = Job.objects.filter(job_type='job', started__gte=last_30_days).order_by('started')
        if jobs.exists():
            for job in jobs:
                stats_dates = [stat['date'] for stat in data]
                if job.started.date() not in stats_dates:
                    data.append({'date': job.started.date(), 'size': 0, 'dedup': 0, 'success': 0, 'failed': 0})
                for stat in data:
                    if stat['date'] == job.started.date():
                        stat['size'] += job.original_size
                        stat['dedup'] += job.deduplicated_size
                        if job.status == 'successful':
                            stat['success'] += 1
                        if job.status == 'failed':
                            stat['failed'] += 1
        return Response(data)


class CyborgTokenObtainPairView(TokenObtainPairView):
    serializer_class = CyborgTokenObtainPairSerializer
