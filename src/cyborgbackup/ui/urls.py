import os
import base64
import socket
import prometheus_client
from prometheus_client import multiprocess
from django.conf.urls import url
from django.views.generic.base import TemplateView
from django.contrib.staticfiles import views
from django.http import HttpResponse
from django.urls import re_path

from cyborgbackup.main.utils.tasks import catalog_is_running, celery_worker_is_running
from cyborgbackup.main.models import Job, Policy, Repository, Schedule, Client
from cyborgbackup.main.models.settings import Setting
from cyborgbackup import get_version

app_name = 'ui'

METRICS_CYBORG_INFO = prometheus_client.Gauge(
    'cyborgbackup_info',
    'CyBorgBackup Instance',
    ['instance', 'version']
)

METRICS_CYBORG_JOBS_STATUS = prometheus_client.Gauge(
    'cyborgbackup_jobs_status',
    'CyBorgBackup Job Status',
    ['instance', 'status']
)

METRICS_CYBORG_POLICIES_ENABLED = prometheus_client.Gauge(
    'cyborgbackup_policies_enabled',
    'CyBorgBackup Policies Enabled',
    ['instance', 'enabled']
)

METRICS_CYBORG_POLICIES_TYPE = prometheus_client.Gauge(
    'cyborgbackup_policies_type',
    'CyBorgBackup Policies Type',
    ['instance', 'policy_type']
)

METRICS_CYBORG_POLICIES_CLIENTS = prometheus_client.Gauge(
    'cyborgbackup_policies_clients',
    'CyBorgBackup Policies Clients',
    ['instance', 'policy_type']
)

METRICS_CYBORG_CLIENTS_ENABLED = prometheus_client.Gauge(
    'cyborgbackup_clients_enabled',
    'CyBorgBackup Clients Enabled',
    ['instance', 'enabled']
)

METRICS_CYBORG_SCHEDULES_ENABLED = prometheus_client.Gauge(
    'cyborgbackup_schedules_enabled',
    'CyBorgBackup Schedules Enabled',
    ['instance', 'enabled']
)

METRICS_CYBORG_REPOSITORIES_SIZE = prometheus_client.Gauge(
    'cyborgbackup_repositories_size',
    'CyBorgBackup Repositories Sizing',
    ['instance', 'repository_name', 'stat']
)

METRICS_CYBORG_BACKUPS_SIZE = prometheus_client.Gauge(
    'cyborgbackup_backups_size',
    'CyBorgBackup Backup Sizing',
    ['instance', 'archive_name', 'stat']
)

METRICS_CYBORG_JOBS_DURATIONS = prometheus_client.Gauge(
    'cyborgbackup_jobs_duration',
    'CyBorgBackup Job Duration',
    ['instance', 'archive_name', 'client', 'policy_type']
)

class IndexView(TemplateView):

    template_name = 'ui/index.html'

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        context['celery'] = celery_worker_is_running()
        context['catalog'] = catalog_is_running()
        context['jobs'] = Job.objects.filter().count()
        context['policies'] = len(Policy.objects.filter())
        context['clients'] = len(Client.objects.filter())
        context['schedules'] = len(Schedule.objects.filter())
        context['repositories'] = len(Repository.objects.filter())
        return context


def _get_metrics():
    instance = socket.gethostname()
    METRICS_CYBORG_INFO.labels(instance, get_version()).set(1)

    for job_state in Job.ALL_STATUS_CHOICES:
        METRICS_CYBORG_JOBS_STATUS.labels(instance, job_state[0]).set(
            Job.objects.filter(status=job_state[0]).count()
        )

    for policy_state in (True, False):
        METRICS_CYBORG_POLICIES_ENABLED.labels(instance, policy_state).set(
            Policy.objects.filter(enabled=policy_state).count()
        )

    for policy_type in Policy.POLICY_TYPE_CHOICES:
        METRICS_CYBORG_POLICIES_TYPE.labels(instance, policy_type[0]).set(
            Policy.objects.filter(policy_type=policy_type[0]).count()
        )

    for policy in Policy.objects.filter():
        METRICS_CYBORG_POLICIES_CLIENTS.labels(instance, policy.name).set(policy.clients.all().count())

    for client_state in (True, False):
        METRICS_CYBORG_CLIENTS_ENABLED.labels(instance, client_state).set(
            Client.objects.filter(enabled=client_state).count()
        )

    for schedule_state in (True, False):
        METRICS_CYBORG_SCHEDULES_ENABLED.labels(instance, client_state).set(
            Schedule.objects.filter(enabled=schedule_state).count()
        )

    for repository in Repository.objects.all():
        METRICS_CYBORG_REPOSITORIES_SIZE.labels(instance, repository.name, 'compressed').set(
            repository.compressed_size
        )
        METRICS_CYBORG_REPOSITORIES_SIZE.labels(instance, repository.name, 'deduplicated').set(
            repository.deduplicated_size
        )
        METRICS_CYBORG_REPOSITORIES_SIZE.labels(instance, repository.name, 'original').set(
            repository.original_size
        )

    for job in Job.objects.exclude(archive_name=''):
        METRICS_CYBORG_BACKUPS_SIZE.labels(instance, job.archive_name, 'compressed').set(job.compressed_size)
        METRICS_CYBORG_BACKUPS_SIZE.labels(instance, job.archive_name, 'deduplicated').set(job.deduplicated_size)
        METRICS_CYBORG_BACKUPS_SIZE.labels(instance, job.archive_name, 'original').set(job.original_size)

        METRICS_CYBORG_JOBS_DURATIONS.labels(
            instance,
            job.archive_name,
            job.client.hostname,
            job.policy.policy_type
        ).set(job.elapsed)

    if "prometheus_multiproc_dir" in os.environ:
        registry = prometheus_client.CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = prometheus_client.REGISTRY
    return prometheus_client.generate_latest(registry)


def MetricsPrometheus(request):
    metrics_enabled = Setting.objects.get(key='cyborgbackup_metrics_enabled')
    if metrics_enabled and metrics_enabled.value == 'True':
        metrics_auth = Setting.objects.get(key='cyborgbackup_metrics_auth')
        if metrics_auth and metrics_auth.value == 'True':
            if 'HTTP_AUTHORIZATION' in request.META:
                auth = request.META['HTTP_AUTHORIZATION'].split()
                if len(auth) == 2:
                    if auth[0].lower() == "basic":
                        uname, passwd = base64.b64decode(auth[1]).split(b':')
                        metrics_user = Setting.objects.get(key='cyborgbackup_metrics_auth_username')
                        metrics_pass = Setting.objects.get(key='cyborgbackup_metrics_auth_password')
                        if uname.decode('utf-8') == metrics_user.value and passwd.decode('utf-8') == metrics_pass.value:
                            return HttpResponse(
                                _get_metrics(), content_type=prometheus_client.CONTENT_TYPE_LATEST
                            )
            response = HttpResponse()
            response.status_code = 401
            response['WWW-Authenticate'] = 'Basic realm="CyBorgBackup Metrics"'
            return response
        else:
            return HttpResponse(
                _get_metrics(), content_type=prometheus_client.CONTENT_TYPE_LATEST
            )
    else:
        return HttpResponse("You didn't say the magic word !")


index = IndexView.as_view()

urlpatterns = [
    url(r'^$', index, name='index'),
    url(r'^metrics$', MetricsPrometheus),
    re_path(r'^(?P<path>.*)$', views.serve),
]
