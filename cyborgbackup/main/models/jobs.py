# Python
from io import StringIO
import json
import logging
import os
import re
import sys
import traceback
import subprocess
import tempfile
from collections import OrderedDict

# Django
from django.conf import settings
from django.db import models, connection
from django.core.exceptions import NON_FIELD_ERRORS
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now
from django.utils.encoding import smart_text
from django.apps import apps
from django.contrib.contenttypes.models import ContentType

from django_celery_results.models import TaskResult

# REST Framework
from rest_framework.exceptions import ParseError

# Django-Polymorphic
from polymorphic.models import PolymorphicModel

from celery.task.control import inspect

# CyBorgBackup
from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.base import * # noqa
from cyborgbackup.main.models.events import JobEvent
from cyborgbackup.main.utils.common import (
    copy_model_by_class, copy_m2m_relationships,
    get_type_for_model, parse_yaml_or_json
)
from cyborgbackup.main.utils.encryption import encrypt_dict, decrypt_field
from cyborgbackup.main.constants import ACTIVE_STATES, CAN_CANCEL
from cyborgbackup.main.utils.string import UriCleaner, REPLACE_STR
from cyborgbackup.main.consumers import emit_channel_notification
from cyborgbackup.main.fields import JSONField, AskForField


__all__ = ['Job', 'StdoutMaxBytesExceeded']

logger = logging.getLogger('cyborgbackup.main.models.jobs')

# NOTE: ACTIVE_STATES moved to constants because it is used by parent modules


class JobTypeStringMixin(object):
    @classmethod
    def _underscore_to_camel(cls, word):
        return ''.join(x.capitalize() or '_' for x in word.split('_'))

    @classmethod
    def _camel_to_underscore(cls, word):
        return re.sub('(?!^)([A-Z]+)', r'_\1', word).lower()

    @classmethod
    def _model_type(cls, job_type):
        # Django >= 1.9
        #app = apps.get_app_config('main')
        model_str = cls._underscore_to_camel(job_type)
        try:
            return apps.get_model('main', model_str)
        except LookupError:
            print("Lookup model error")
            return None

    @classmethod
    def get_instance_by_type(cls, job_type, job_id):
        model = cls._model_type(job_type)
        if not model:
            return None
        return model.objects.get(id=job_id)

    def model_to_str(self):
        return self._camel_to_underscore(self.__class__.__name__)


class JobDeprecatedStdout(models.Model):

    class Meta:
        managed = False
        db_table = 'main_job'

    result_stdout_text = models.TextField(
        null=True,
        editable=False,
    )


class StdoutMaxBytesExceeded(Exception):

    def __init__(self, total, supported):
        self.total = total
        self.supported = supported


class TaskManagerJobMixin(models.Model):
    class Meta:
        abstract = True

    def get_jobs_fail_chain(self):
        return []


class Job(CommonModelNameNotUnique, JobTypeStringMixin, TaskManagerJobMixin):
    '''
    Concrete base class for job run by the task engine.
    '''

    # status inherits from related jobs. Thus, status must be able to be set to any status that a job status is settable to.
    JOB_STATUS_CHOICES = [
        ('new', 'New'),                  # Job has been created, but not started.
        ('pending', 'Pending'),          # Job has been queued, but is not yet running.
        ('waiting', 'Waiting'),          # Job is waiting on an update/dependency.
        ('running', 'Running'),          # Job is currently running.
        ('successful', 'Successful'),    # Job completed successfully.
        ('failed', 'Failed'),            # Job completed, but with failures.
        ('error', 'Error'),              # The job was unable to run.
        ('canceled', 'Canceled'),        # The job was canceled before completion.
    ]

    COMMON_STATUS_CHOICES = JOB_STATUS_CHOICES + [
        ('never updated', 'Never Updated'),     # A job has never been run using this template.
    ]

    DEPRECATED_STATUS_CHOICES = [
        # No longer used for Project / Inventory Source:
        ('updating', 'Updating'),            # Same as running.
    ]

    ALL_STATUS_CHOICES = OrderedDict(DEPRECATED_STATUS_CHOICES).items()

    LAUNCH_TYPE_CHOICES = [
        ('manual', 'Manual'),            # Job was started manually by a user.
        ('relaunch', 'Relaunch'),        # Job was started via relaunch.
        ('callback', 'Callback'),        # Job was started via host callback.
        ('scheduled', 'Scheduled'),      # Job was started from a schedule.
        ('dependency', 'Dependency'),    # Job was started as a dependency of another job.
        ('workflow', 'Workflow'),        # Job was started from a workflow job.
        ('sync', 'Sync'),                # Job was started from a project sync.
        ('scm', 'SCM Update')            # Job was created as an Inventory SCM sync.
    ]

    JOB_TYPE_CHOICES = [
        ('provision', 'Provision VM'),
        ('dns', 'Update DNS'),
        ('monit_observium', 'Monitoring Observium'),
        ('monit_status', 'Monitoring Status')
    ]

    VERBOSITY_CHOICES = [
        (0, '0 (Normal)'),
        (1, '1 (Verbose)'),
        (2, '2 (More Verbose)'),
        (3, '3 (Debug)'),
        (4, '4 (Connection Debug)'),
    ]

    PASSWORD_FIELDS = ('start_args',)

    # NOTE: Working around a django-polymorphic issue: https://github.com/django-polymorphic/django-polymorphic/issues/229
    base_manager_name = 'base_objects'

    class Meta:
        app_label = 'main'

    job_type = models.CharField(
        max_length=64,
        choices=JOB_TYPE_CHOICES,
        default='job',
    )
    policy = models.ForeignKey(
        'Policy',
        related_name='jobs',
        on_delete=models.CASCADE,
        null=True,
        editable=False,
    )
    client = models.ForeignKey(
        'Client',
        related_name='jobs_client',
        on_delete=models.CASCADE,
        null=True,
        editable=False,
    )
    repository = models.ForeignKey(
        'Repository',
        related_name='jobs_repository',
        on_delete=models.CASCADE,
        null=True,
        editable=False,
    )
    old_pk = models.PositiveIntegerField(
        null=True,
        default=None,
        editable=False,
    )
    verbosity = models.PositiveIntegerField(
        choices=VERBOSITY_CHOICES,
        blank=True,
        default=0,
    )
    extra_vars = models.TextField(
        blank=True,
        default='',
    )
    timeout = models.IntegerField(
        blank=True,
        default=0,
        help_text=_("The amount of time (in seconds) to run before the task is canceled."),
    )
    emitted_events = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    launch_type = models.CharField(
        max_length=20,
        choices=LAUNCH_TYPE_CHOICES,
        default='manual',
        editable=False,
    )
    cancel_flag = models.BooleanField(
        blank=True,
        default=False,
        editable=False,
    )
    status = models.CharField(
        max_length=20,
        choices=JOB_STATUS_CHOICES,
        default='new',
        editable=False,
    )
    failed = models.BooleanField(
        default=False,
        editable=False,
    )
    started = models.DateTimeField(
        null=True,
        default=None,
        editable=False,
        help_text=_("The date and time the job was queued for starting."),
    )
    finished = models.DateTimeField(
        null=True,
        default=None,
        editable=False,
        help_text=_("The date and time the job finished execution."),
    )
    elapsed = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        editable=False,
        help_text=_("Elapsed time in seconds that the job ran."),
    )
    job_args = prevent_search(models.TextField(
        blank=True,
        default='',
        editable=False,
    ))
    job_cwd = models.CharField(
        max_length=1024,
        blank=True,
        default='',
        editable=False,
    )
    job_env = prevent_search(JSONField(
        blank=True,
        default={},
        editable=False,
    ))
    job_explanation = models.TextField(
        blank=True,
        default='',
        editable=False,
        help_text=_("A status field to indicate the state of the job if it wasn't able to run and capture stdout"),
    )
    start_args = prevent_search(models.TextField(
        blank=True,
        default='',
        editable=False,
    ))
    result_traceback = models.TextField(
        blank=True,
        default='',
        editable=False,
    )
    celery_task_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        editable=False,
    )
    job_pool = models.IntegerField(
        blank=True,
        default=0,
    )
    dependent_jobs = models.ForeignKey(
        'self',
        related_name='%(class)s_blocked_jobs+',
        on_delete=models.CASCADE,
        null=True,
        editable=False,
    )
    hypervisor = models.CharField(
        max_length=1024,
        blank=True,
        default='',
    )
    original_size = models.BigIntegerField(
        default=0
    )

    compressed_size = models.BigIntegerField(
        default=0
    )

    deduplicated_size = models.BigIntegerField(
        default=0
    )

    pruned = models.BooleanField(
        default=False
    )

    extra_vars_dict = VarsDictProperty('extra_vars', True)

    def get_absolute_url(self, request=None):
        return reverse('api:job_detail', kwargs={'pk': self.pk}, request=request)

    def get_ui_url(self):
        return "/#/jobs/{}".format(self.pk)

    @classmethod
    def _get_task_class(cls):
        from cyborgbackup.main.tasks import RunJob
        return RunJob

    def _global_timeout_setting(self):
        return 'DEFAULT_JOB_TIMEOUT'

    def __unicode__(self):
        return u'%s-%s-%s' % (self.created, self.id, self.status)

    @property
    def log_format(self):
        return '{} {} ({})'.format(get_type_for_model(type(self)), self.id, self.status)

    def _get_parent_instance(self):
        return getattr(self, self._get_parent_field_name(), None)

    def _update_parent_instance_no_save(self, parent_instance, update_fields=[]):
        def parent_instance_set(key, val):
            setattr(parent_instance, key, val)
            if key not in update_fields:
                update_fields.append(key)

        if parent_instance:
            if self.status in ('pending', 'waiting', 'running'):
                if parent_instance.current_job != self:
                    parent_instance_set('current_job', self)
                # Update parent with all the 'good' states of it's child
                if parent_instance.status != self.status:
                    parent_instance_set('status', self.status)
            elif self.status in ('successful', 'failed', 'error', 'canceled'):
                if parent_instance.current_job == self:
                    parent_instance_set('current_job', None)
                parent_instance_set('last_job', self)
                parent_instance_set('last_job_failed', self.failed)

        return update_fields

    def _get_current_status(self):
        if  self.status:
            return self.status

    def _set_status_and_last_job_run(self, save=True):
        status = self._get_current_status()
        return self.update_fields(status=status, save=save)

    def save(self, *args, **kwargs):
        """Save the job, with current status, to the database.
        Ensure that all data is consistent before doing so.
        """
        # If update_fields has been specified, add our field names to it,
        # if it hasn't been specified, then we're just doing a normal save.
        update_fields = kwargs.get('update_fields', [])

        # Update status and last_updated fields.
        updated_fields = self._set_status_and_last_job_run(save=False)
        for field in updated_fields:
            if field not in update_fields:
                update_fields.append(field)

        # Get status before save...
        status_before = self.status or 'new'

        # If this job already exists in the database, retrieve a copy of
        # the job in its prior state.
        if self.pk:
            self_before = self.__class__.objects.get(pk=self.pk)
            if self_before.status != self.status:
                status_before = self_before.status

        # Sanity check: Is this a failure? Ensure that the failure value
        # matches the status.
        failed = bool(self.status in ('failed', 'error', 'canceled'))
        if self.failed != failed:
            self.failed = failed
            if 'failed' not in update_fields:
                update_fields.append('failed')

        # Sanity check: Has the job just started? If so, mark down its start
        # time.
        if self.status == 'running' and not self.started:
            self.started = now()
            if 'started' not in update_fields:
                update_fields.append('started')

        # Sanity check: Has the job just completed? If so, mark down its
        # completion time, and record its output to the database.
        if self.status in ('successful', 'failed', 'error', 'canceled') and not self.finished:
            # Record the `finished` time.
            self.finished = now()
            if 'finished' not in update_fields:
                update_fields.append('finished')

        # If we have a start and finished time, and haven't already calculated
        # out the time that elapsed, do so.
        if self.started and self.finished and not self.elapsed:
            td = self.finished - self.started
            elapsed = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / (10 ** 6 * 1.0)
        else:
            elapsed = 0.0
        if self.elapsed != elapsed:
            self.elapsed = str(elapsed)
            if 'elapsed' not in update_fields:
                update_fields.append('elapsed')

        # Okay; we're done. Perform the actual save.
        result = super(Job, self).save(*args, **kwargs)

        # If status changed, update the parent instance.
        #if self.status != status_before:
        #    self._update_parent_instance()

        # Done.
        return result

    def launch_prompts(self):
        '''
        Return dictionary of prompts job was launched with
        returns None if unknown
        '''
        JobLaunchConfig = self._meta.get_field('launch_config').related_model
        try:
            config = self.launch_config
            return config.prompts_dict()
        except JobLaunchConfig.DoesNotExist:
            return None

    def create_config_from_prompts(self, kwargs):
        '''
        Create a launch configuration entry for this job, given prompts
        returns None if it can not be created
        '''
        if self.job_template is None:
            return None
        JobLaunchConfig = self._meta.get_field('launch_config').related_model
        config = JobLaunchConfig(job=self)
        valid_fields = self.job_template.get_ask_mapping().keys()
        # Special cases allowed for workflows
        kwargs.pop('survey_passwords', None)
        for field_name, value in kwargs.items():
            if field_name not in valid_fields:
                raise Exception('Unrecognized launch config field {}.'.format(field_name))
            key = field_name
            setattr(config, key, value)
        config.save()

        return config

    @property
    def event_class(self):
        return JobEvent

    @property
    def result_stdout_text(self):
        related = JobDeprecatedStdout.objects.get(pk=self.pk)
        return related.result_stdout_text or ''

    @result_stdout_text.setter
    def result_stdout_text(self, value):
        related = JobDeprecatedStdout.objects.get(pk=self.pk)
        related.result_stdout_text = value
        related.save()

    @property
    def event_parent_key(self):
        tablename = self._meta.db_table
        return {
            'main_job': 'job_id',
        }[tablename]

    def get_event_queryset(self):
        return self.event_class.objects.filter(**{self.event_parent_key: self.id})

    @property
    def event_processing_finished(self):
        '''
        Returns True / False, whether all events from job have been saved
        '''
        if self.status in ACTIVE_STATES:
            return False  # tally of events is only available at end of run
        try:
            event_qs = self.get_event_queryset()
        except NotImplementedError:
            return True  # Model without events, such as WFJT
        return self.emitted_events == event_qs.count()

    def result_stdout_raw_handle(self, enforce_max_bytes=True):
        """
        This method returns a file-like object ready to be read which contains
        all stdout for the Job.

        If the size of the file is greater than 1048576, a StdoutMaxBytesExceeded exception
        will be raised.
        """
        max_supported = 1048576

        if enforce_max_bytes:
            # If enforce_max_bytes is True, we're not grabbing the whole file,
            # just the first <settings.STDOUT_MAX_BYTES_DISPLAY> bytes;
            # in this scenario, it's probably safe to use a StringIO.
            fd = StringIO()
        else:
            # If enforce_max_bytes = False, that means they're downloading
            # the entire file.  To avoid ballooning memory, let's write the
            # stdout content to a temporary disk location
            if not os.path.exists(settings.JOBOUTPUT_ROOT):
                os.makedirs(settings.JOBOUTPUT_ROOT)
            fd = tempfile.NamedTemporaryFile(
                prefix='{}-{}-'.format(self.model_to_str(), self.pk),
                suffix='.out',
                dir=settings.JOBOUTPUT_ROOT
            )

        # Note: the code in this block _intentionally_ does not use the
        # Django ORM because of the potential size (many MB+) of
        # `main_jobevent.stdout`; we *do not* want to generate queries
        # here that construct model objects by fetching large gobs of
        # data (and potentially ballooning memory usage); instead, we
        # just want to write concatenated values of a certain column
        # (`stdout`) directly to a file

        with connection.cursor() as cursor:

            if enforce_max_bytes:
                # detect the length of all stdout for this Job, and
                # if it exceeds settings.STDOUT_MAX_BYTES_DISPLAY bytes,
                # don't bother actually fetching the data
                total = self.get_event_queryset().aggregate(
                    total=models.Sum(models.Func(models.F('stdout'), function='LENGTH'))
                )['total']
                if total > max_supported:
                    raise StdoutMaxBytesExceeded(total, max_supported)

            cursor.copy_expert(
                "copy (select stdout from {} where {}={} order by start_line) to stdout".format(
                    self._meta.db_table + 'event',
                    self.event_parent_key,
                    self.id
                ),
                fd
            )

            if hasattr(fd, 'name'):
                # If we're dealing with a physical file, use `sed` to clean
                # up escaped line sequences
                fd.flush()
                subprocess.Popen("sed -i 's/\\\\r\\\\n/\\n/g' {}".format(fd.name), shell=True).wait()
                return open(fd.name, 'r')
            else:
                # If we're dealing with an in-memory string buffer, use
                # string.replace()
                fd = StringIO(fd.getvalue().replace('\\r\\n', '\n'))
                return fd

    def _escape_ascii(self, content):
        # Remove ANSI escape sequences used to embed event data.
        content = re.sub(r'\x1b\[K(?:[A-Za-z0-9+/=]+\x1b\[\d+D)+\x1b\[K', '', content)
        # Remove ANSI color escape sequences.
        content = re.sub(r'\x1b[^m]*m', '', content)
        return content

    def _result_stdout_raw(self, redact_sensitive=False, escape_ascii=False):
        content = self.result_stdout_raw_handle().read().decode('utf-8')
        if redact_sensitive:
            content = UriCleaner.remove_sensitive(content)
        if escape_ascii:
            content = self._escape_ascii(content)
        return content

    @property
    def result_stdout_raw(self):
        return self._result_stdout_raw()

    @property
    def result_stdout(self):
        return self._result_stdout_raw(escape_ascii=True)

    def _result_stdout_raw_limited(self, start_line=0, end_line=None, redact_sensitive=True, escape_ascii=False):
        return_buffer = StringIO()
        if end_line is not None:
            end_line = int(end_line)
        stdout_lines = self.result_stdout_raw_handle().readlines()
        absolute_end = len(stdout_lines)
        for line in stdout_lines[int(start_line):end_line]:
            return_buffer.write(line)
        if int(start_line) < 0:
            start_actual = len(stdout_lines) + int(start_line)
            end_actual = len(stdout_lines)
        else:
            start_actual = int(start_line)
            if end_line is not None:
                end_actual = min(int(end_line), len(stdout_lines))
            else:
                end_actual = len(stdout_lines)

        return_buffer = return_buffer.getvalue()
        if redact_sensitive:
            return_buffer = UriCleaner.remove_sensitive(return_buffer)
        if escape_ascii:
            return_buffer = self._escape_ascii(return_buffer)

        return return_buffer, start_actual, end_actual, absolute_end

    def result_stdout_raw_limited(self, start_line=0, end_line=None, redact_sensitive=False):
        return self._result_stdout_raw_limited(start_line, end_line, redact_sensitive)

    def result_stdout_limited(self, start_line=0, end_line=None, redact_sensitive=False):
        return self._result_stdout_raw_limited(start_line, end_line, redact_sensitive, escape_ascii=True)

    @property
    def celery_task(self):
        try:
            if self.celery_task_id:
                return TaskResult.objects.get(task_id=self.celery_task_id)
        except TaskResult.DoesNotExist:
            pass

    def get_passwords_needed_to_start(self):
        return []

    @property
    def can_start(self):
        return bool(self.status in ('new', 'waiting'))

    @property
    def can_update(self):
        return True

    def update(self, **kwargs):
        if self.can_update:
            job = self.create_job()
            job.signal_start(**kwargs)
            return job

    def create_job(self, **kwargs):
        '''
        Create a new job based on this job.
        '''
        eager_fields = kwargs.pop('_eager_fields', None)

        job_class = self.__class__
        fields = self._get_job_field_names()
        unallowed_fields = set(kwargs.keys()) - set(fields)
        if unallowed_fields:
            logger.warn('Fields {} are not allowed as overrides.'.format(unallowed_fields))
            map(kwargs.pop, unallowed_fields)

        job = copy_model_by_class(self, job_class, fields, kwargs)

        if eager_fields:
            for fd, val in eager_fields.items():
                setattr(job, fd, val)

        # Set the job back-link on the job
        parent_field_name = job_class._get_parent_field_name()
        setattr(job, parent_field_name, self)

        job.save()

        from cyborgbackup.main.signals import disable_activity_stream
        with disable_activity_stream():
            copy_m2m_relationships(self, job, fields, kwargs=kwargs)

        job.create_config_from_prompts(kwargs)

        return job

    @classmethod
    def _get_job_field_names(cls):
        return set(
            ['name', 'description', 'policy', 'client', 'repository', 'job_type']
        )

    def copy_job(self, limit=None):
        '''
        Returns saved object, including related fields.
        Create a copy of this unified job for the purpose of relaunch
        '''
        job_class = self.__class__
        parent_field_name = 'job'
        fields = job_class._get_job_field_names() | set([parent_field_name])

        create_data = {"launch_type": "relaunch"}
        if limit:
            create_data["limit"] = limit

        copy_job = copy_model_by_class(self, job_class, fields, {})
        for fd, val in create_data.items():
            setattr(copy_job, fd, val)
        copy_job.old_pk = self.pk
        copy_job.save()

        # Labels coppied here
        copy_m2m_relationships(self, copy_job, fields)
        return copy_job

    @classmethod
    def get_ask_mapping(cls):
        '''
        Creates dictionary that maps the unified job field (keys)
        to the field that enables prompting for the field (values)
        '''
        mapping = {}
        for field in cls._meta.fields:
            if isinstance(field, AskForField):
                mapping[field.allows_field] = field.name
        return mapping

    @property
    def task_impact(self):
        return 1

    def websocket_emit_data(self):
        ''' Return extra data that should be included when submitting data to the browser over the websocket connection '''
        websocket_data = dict(job_name=self.name)
        return websocket_data

    def _websocket_emit_status(self, status):
        try:
            status_data = dict(job_id=self.id, status=status)
            status_data.update(self.websocket_emit_data())
            status_data['group_name'] = 'jobs'
            emit_channel_notification('jobs-status_changed', status_data)

        except IOError:  # includes socket errors
            logger.exception('%s failed to emit channel msg about status change', self.log_format)

    def websocket_emit_status(self, status):
        connection.on_commit(lambda: self._websocket_emit_status(status))

    def notification_data(self):
        return dict(id=self.id,
                    name=self.name,
                    url=self.get_ui_url(),
                    created_by=smart_text(self.created_by),
                    started=self.started.isoformat() if self.started is not None else None,
                    finished=self.finished.isoformat() if self.finished is not None else None,
                    status=self.status,
                    traceback=self.result_traceback)

    def pre_start(self, **kwargs):
        if not self.can_start:
            self.job_explanation = u'%s is not in a startable state: %s, expecting one of %s' % (self._meta.verbose_name, self.status, str(('new', 'waiting')))
            self.save(update_fields=['job_explanation'])
            return (False, None)

        needed = self.get_passwords_needed_to_start()
        try:
            start_args = json.loads(decrypt_field(self, 'start_args'))
        except Exception:
            start_args = None

        if start_args in (None, ''):
            start_args = kwargs

        opts = dict([(field, start_args.get(field, '')) for field in needed])

        if not all(opts.values()):
            missing_fields = ', '.join([k for k, v in opts.items() if not v])
            self.job_explanation = u'Missing needed fields: %s.' % missing_fields
            self.save(update_fields=['job_explanation'])
            return (False, None)

        return (True, opts)

    def start_celery_task(self, opts, error_callback, success_callback, queue):
        if self.job_type != 'workflow':
            kwargs = {
                'link_error': error_callback,
                'link': success_callback,
                'queue': None,
                'task_id': None,
            }
            if not self.celery_task_id:
                raise RuntimeError("Expected celery_task_id to be set on model.")
            kwargs['task_id'] = self.celery_task_id
            task_class = self._get_task_class()
            args = [self.pk]
            kwargs['queue'] = 'celery'
            async_result = task_class().apply(args, opts, **kwargs)
        else:
            return None

    def start(self, error_callback, success_callback, **kwargs):
        '''
        Start the task running via Celery.
        '''
        (res, opts) = self.pre_start(**kwargs)
        if res:
            self.start_celery_task(opts, error_callback, success_callback)
        return res

    def signal_start(self, **kwargs):
        """Notify the task runner system to begin work on this task."""

        # Sanity check: Are we able to start the job? If not, do not attempt
        # to do so.
        if not self.can_start:
            return False

        # Sanity check: If we are running unit tests, then run synchronously.
        if getattr(settings, 'CELERY_UNIT_TEST', False):
            return self.start(None, None, **kwargs)

        # Save the pending status, and inform the SocketIO listener.
        self.update_fields(start_args=json.dumps(kwargs), status='pending')
        #self.websocket_emit_status("pending")

        from cyborgbackup.main.utils.tasks import run_job_launch
        connection.on_commit(lambda: run_job_launch.delay(self.id))

        # Each type of unified job has a different Task class; get the
        # appropirate one.
        # task_type = get_type_for_model(self)

        # Actually tell the task runner to run this task.
        # FIXME: This will deadlock the task runner
        #from awx.main.tasks import notify_task_runner
        #notify_task_runner.delay({'id': self.id, 'metadata': kwargs,
        #                          'task_type': task_type})

        # Done!
        return True

    @property
    def can_cancel(self):
        return bool(self.status in CAN_CANCEL)

    def _force_cancel(self):
        # Update the status to 'canceled' if we can detect that the job
        # really isn't running (i.e. celery has crashed or forcefully
        # killed the worker).
        task_statuses = ('STARTED', 'SUCCESS', 'FAILED', 'RETRY', 'REVOKED')
        try:
            taskmeta = self.celery_task
            print(self.celery_task)
            if not taskmeta or taskmeta.status not in task_statuses:
                return
            from celery import current_app
            i = current_app.control.inspect()
            for v in (i.active() or {}).values():
                if taskmeta.task_id in [x['id'] for x in v]:
                    return
            for v in (i.reserved() or {}).values():
                if taskmeta.task_id in [x['id'] for x in v]:
                    return
            for v in (i.revoked() or {}).values():
                if taskmeta.task_id in [x['id'] for x in v]:
                    return
            for v in (i.scheduled() or {}).values():
                if taskmeta.task_id in [x['id'] for x in v]:
                    return
            instance = self.__class__.objects.get(pk=self.pk)
            if instance.can_cancel:
                instance.status = 'canceled'
                update_fields = ['status']
                if not instance.job_explanation:
                    instance.job_explanation = 'Forced cancel'
                    update_fields.append('job_explanation')
                instance.save(update_fields=update_fields)
                self.websocket_emit_status("canceled")
        except Exception: # FIXME: Log this exception!
            if settings.DEBUG:
                raise

    def _build_job_explanation(self):
        if not self.job_explanation:
            return 'Previous Task Canceled: {"job_type": "%s", "job_name": "%s", "job_id": "%s"}' % \
                   (self.model_to_str(), self.name, self.id)
        return None

    #def get_jobs_fail_chain(self):
    #    return list(self.dependent_jobs.all())

    def cancel(self, job_explanation=None, is_chain=False):
        if self.can_cancel:
            #if not is_chain:
            #    map(lambda x: x.cancel(job_explanation=self._build_job_explanation(), is_chain=True), self.get_jobs_fail_chain())

            if not self.cancel_flag:
                self.cancel_flag = True
                self.start_args = ''  # blank field to remove encrypted passwords
                cancel_fields = ['cancel_flag', 'start_args']
                if self.status in ('pending', 'waiting', 'new'):
                    self.status = 'canceled'
                    cancel_fields.append('status')
                if job_explanation is not None:
                    self.job_explanation = job_explanation
                    cancel_fields.append('job_explanation')
                self.save(update_fields=cancel_fields)
                self.websocket_emit_status("canceled")
            if settings.BROKER_URL.startswith('amqp://'):
                self._force_cancel()
        return self.cancel_flag


    def dependent_jobs_finished(self):
        for j in self.__class__.objects.filter(dependent_jobs=self.pk):
            if j.status in ['new', 'pending', 'waiting', 'running']:
                return False
        return True
