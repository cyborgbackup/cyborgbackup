# Python
import cgi
import logging
import re
from base64 import b64encode
from wsgiref.util import FileWrapper

import ansiconv
import dateutil
# Django
from django.db import transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
# Django REST Framework
from rest_framework import status, renderers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.settings import api_settings

from cyborgbackup.main.constants import ACTIVE_STATES
from cyborgbackup.main.models.jobs import Job, JobEvent
from cyborgbackup.main.utils.common import camelcase_to_underscore
# CyBorgBackup
from .generics import RetrieveUpdateDestroyAPIView, ListCreateAPIView, RetrieveAPIView, GenericAPIView, ListAPIView, \
    SubListAPIView
from ..helpers import get_view_name
from ..renderers import BrowsableAPIRenderer, PlainTextRenderer, AnsiTextRenderer, DownloadTextRenderer, \
    AnsiDownloadRenderer
from ..serializers.base import EmptySerializer
from ..serializers.jobs import JobSerializer, JobEventSerializer, JobListSerializer, JobCancelSerializer, \
    JobStdoutSerializer, JobRelaunchSerializer

logger = logging.getLogger('cyborgbackups.api.views.jobs')


class JobDeletionMixin(object):
    """
    Special handling when deleting a running job object.
    """

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
        if 0 < size < len(data):
            self.extra_data = data[size:]
            data = data[:size]
        else:
            self.extra_data = ''
        return data


class JobList(ListCreateAPIView):
    model = Job
    serializer_class = JobListSerializer
    tags = ['Job']

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
    tags = ['Job']

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
    tags = ['Job']

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
    tags = ['Job']

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
    tags = ['Job']

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
    tags = ['Job']

    def update_raw_data(self, data):
        data = super(JobRelaunch, self).update_raw_data(data)
        try:
            self.get_object()
        except PermissionDenied:
            return data
        return data

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
    tags = ['Job']


class JobEventDetail(RetrieveAPIView):
    model = JobEvent
    serializer_class = JobEventSerializer
    tags = ['Job']


class BaseJobEventsList(SubListAPIView):
    model = JobEvent
    serializer_class = JobEventSerializer
    parent_model = None  # Subclasses must define this attribute.
    relationship = 'job_events'
    view_name = _('Job Events List')
    search_fields = ('stdout',)
    tags = ['Job']

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
