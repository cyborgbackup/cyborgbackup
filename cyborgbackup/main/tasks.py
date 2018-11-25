# Python
from collections import OrderedDict, namedtuple
from io import StringIO
import functools
import importlib
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import time
import traceback
import six
from six.moves import xrange
from urllib.parse import urlparse
from distutils.version import LooseVersion as Version
import yaml
import fcntl
try:
    import psutil
except Exception:
    psutil = None

from contextlib import contextmanager

# Celery
from celery import Task, shared_task, Celery
from celery.signals import celeryd_init, worker_process_init, worker_shutdown, worker_ready, celeryd_after_setup

# Django
from django.conf import settings
from django.db import transaction, DatabaseError, IntegrityError
from django.db.models.fields.related import ForeignKey
from django.utils.timezone import now, timedelta
from django.utils.encoding import smart_str
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django_pglocks import advisory_lock as django_pglocks_advisory_lock
from django.db import connection
from rest_framework.authtoken.models import Token

# Django-CRUM
from crum import impersonate

# CyBorgBackup
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.models.repositories import Repository
from cyborgbackup.main.models.events import JobEvent
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.models.catalogs import Catalog
from cyborgbackup.main.models.users import User
from cyborgbackup.main.models.schedules import CyborgBackupScheduleState
from cyborgbackup.main.constants import ACTIVE_STATES
from cyborgbackup.main.expect import run
from cyborgbackup.main.consumers import emit_channel_notification
from cyborgbackup.main.utils.common import OutputEventFilter, get_type_for_model, get_ssh_version, get_module_provider, load_module_provider
from cyborgbackup.main.utils.encryption import decrypt_field
from cyborgbackup.main.utils.callbacks import CallbackQueueDispatcher

__all__ = ['RunJob', 'handle_work_error', 'handle_work_success', 'advisory_lock', 'CallbackQueueDispatcher',
           'CyBorgBackupTaskError', 'task_set_logger_pre_run', 'cyborgbackup_periodic_scheduler',
           'LogErrorsTask', 'send_notifications', 'run_administrative_checks', 'purge_old_stdout_files']

OPENSSH_KEY_ERROR = u'''\
It looks like you're trying to use a private key in OpenSSH format, which \
isn't supported by the installed version of OpenSSH on this instance. \
Try upgrading OpenSSH or providing your private key in an different format. \
'''

logger = logging.getLogger('cyborgbackup.main.tasks')

@contextmanager
def advisory_lock(*args, **kwargs):
    if connection.vendor == 'postgresql':
        with django_pglocks_advisory_lock(*args, **kwargs) as internal_lock:
            yield internal_lock
    else:
        yield True


class _CyBorgBackupTaskError():
    def build_exception(self, task, message=None):
        if message is None:
            message = "Execution error running {}".format(task.log_format)
        e = Exception(message)
        e.task = task
        e.is_awx_task_error = True
        return e

    def TaskCancel(self, task, rc):
        """Canceled flag caused run_pexpect to kill the job run"""
        message = "{} was canceled (rc={})".format(task.log_format, rc)
        e = self.build_exception(task, message)
        e.rc = rc
        e.awx_task_error_type = "TaskCancel"
        return e

    def TaskError(self, task, rc):
        """Userspace error (non-zero exit code) in run_pexpect subprocess"""
        message = "{} encountered an error (rc={}), please see task stdout for details.".format(task.log_format, rc)
        e = self.build_exception(task, message)
        e.rc = rc
        e.awx_task_error_type = "TaskError"
        return e


CyBorgBackupTaskError = _CyBorgBackupTaskError()


class LogErrorsTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if getattr(exc, 'is_cyborgbackup_task_error', False):
            logger.warning(six.text_type("{}").format(exc))
        elif isinstance(self, BaseTask):
            logger.exception(six.text_type(
                '{!s} {!s} execution encountered exception.')
                             .format(get_type_for_model(self.model), args[0]))
        else:
            logger.exception(six.text_type('Task {} encountered exception.').format(self.name), exc_info=exc)
        super(LogErrorsTask, self).on_failure(exc, task_id, args, kwargs, einfo)


@shared_task(queue='cyborgbackup', base=LogErrorsTask)
def send_notifications(notification_list, job_id=None):
    if not isinstance(notification_list, list):
        raise TypeError("notification_list should be of type list")
    if job_id is not None:
        job_actual = Job.objects.get(id=job_id)

    notifications = Notification.objects.filter(id__in=notification_list)
    if job_id is not None:
        job_actual.notifications.add(*notifications)

    for notification in notifications:
        try:
            sent = notification.notification_template.send(notification.subject, notification.body)
            notification.status = "successful"
            notification.notifications_sent = sent
        except Exception as e:
            logger.error(six.text_type("Send Notification Failed {}").format(e))
            notification.status = "failed"
            notification.error = smart_str(e)
        finally:
            notification.save()

units = {"B": 1, "kB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12}
def parseSize(size):
    number, unit = [string.strip() for string in size.split()]
    return int(float(number)*units[unit])

@shared_task(bind=True, base=LogErrorsTask)
def compute_borg_size(self):
    logger.debug('Compute Borg Size Report')
    jobs = Job.objects.filter(original_size=0, deduplicated_size=0, compressed_size=0, status='successful', job_type='job').order_by('-finished')
    if jobs.exists():
        for job in jobs:
            events = JobEvent.objects.filter(job_id=job.pk).order_by('-counter')
            for event in events:
                prg = re.compile("This archive:\s*([0-9\.]*\s*.B)\s*([0-9\.]*\s*.B)\s*([0-9\.]*\s*.B)\s*")
                m = prg.match(event.stdout)
                if m:
                    job.original_size = parseSize(m.group(1))
                    job.compressed_size = parseSize(m.group(2))
                    job.deduplicated_size = parseSize(m.group(3))
                    job.save()
                    break
    repos = Repository.objects.filter(original_size=0, deduplicated_size=0, compressed_size=0, ready=True)
    if repos.exists():
        for repo in repos:
            jobs = Job.objects.filter(policy__repository_id=repo.pk, status='successful', job_type='job').order_by('-finished')
            if jobs.exists():
                last_running_job = jobs.first()
                events = JobEvent.objects.filter(job_id=last_running_job.pk).order_by('-counter')
                for event in events:
                    prg = re.compile("All archives:\s*([0-9\.]*\s*.B)\s*([0-9\.]*\s*.B)\s*([0-9\.]*\s*.B)\s*")
                    m = prg.match(event.stdout)
                    if m:
                        repo.original_size = parseSize(m.group(1))
                        repo.compressed_size = parseSize(m.group(2))
                        repo.deduplicated_size = parseSize(m.group(3))
                        repo.save()
                        break

@shared_task(bind=True, base=LogErrorsTask)
def prune_catalog(self):
    logger.debug('Prune deleted archive in Catalog')
    jobs = Job.objects.filter(status='successful', job_type='prune', pruned=False).order_by('-finished')
    if jobs.exists():
        for job in jobs:
            events = JobEvent.objects.filter(job_id=job.pk).order_by('-counter')
            for event in events:
                prg = re.compile("Pruning\sarchive:\s([^\s]*)\s.*")
                m = prg.match(event.stdout)
                if m:
                    Catalog.objects.filter(archive_name=m.group(1)).delete()
            job.pruned=True
            job.save()

@shared_task(bind=True, base=LogErrorsTask)
def borg_restore_test(self):
    logger.debug('Borg Restore Test')
    try:
        setting = Setting.objects.get(key='cyborgbackup_auto_restore_test')
        restore_test = setting.value
    except Exception as e:
        restore_test = False
    if restore_test == 'True':
        logger.debug('Launch Random Job Restore')

@shared_task(bind=True, base=LogErrorsTask)
def borg_repository_integrity(self):
    logger.debug('Borg Repository Integrity')
    try:
        setting = Setting.objects.get(key='cyborgbackup_check_repository')
        check_repository = setting.value
    except Exception as e:
        check_repository = False
    if check_repository == 'True':
        logger.debug('Launch Borg Repository Integrity')

@shared_task(bind=True, base=LogErrorsTask)
def purge_old_stdout_files(self):
    nowtime = time.time()
    for f in os.listdir(settings.JOBOUTPUT_ROOT):
        if os.path.getctime(os.path.join(settings.JOBOUTPUT_ROOT, f)) < nowtime - settings.LOCAL_STDOUT_EXPIRE_TIME:
            os.unlink(os.path.join(settings.JOBOUTPUT_ROOT, f))
            logger.info(six.text_type("Removing {}").format(os.path.join(settings.JOBOUTPUT_ROOT, f)))

@shared_task(bind=True, base=LogErrorsTask)
def cyborgbackup_periodic_scheduler(self):
    run_now = now()
    state = CyborgBackupScheduleState.objects.get_or_create(pk=1)[0]
    last_run = state.schedule_last_run
    logger.debug("Last scheduler run was: %s", last_run)
    state.schedule_last_run = run_now
    state.save()

    old_policies = Policy.objects.enabled().before(last_run)
    for policy in old_policies:
        policy.save()
    policies = Policy.objects.enabled().between(last_run, run_now)
    for policy in policies:
        policy.save() # To update next_run timestamp.
        try:
            new_job = policy.create_job('scheduled')
            new_job.launch_type = 'scheduled'
            can_start = new_job.signal_start()
        except Exception:
            logger.exception('Error spawning scheduled job.')
            continue
        if not can_start:
            new_job.status = 'failed'
            new_job.job_explanation = "Scheduled job could not start because it was not in the right state or required manual credentials"
            new_job.save(update_fields=['status', 'job_explanation'])
            new_job.websocket_emit_status("failed")
        emit_channel_notification('schedules-changed', dict(id=policy.id, group_name="jobs"))
    state.save()

@shared_task(bind=True, queue='cyborgbackup', base=LogErrorsTask)
def handle_work_success(self, result, task_actual):
    try:
        instance = Job.get_instance_by_type(task_actual['type'], task_actual['id'])
    except ObjectDoesNotExist:
        logger.warning('Missing {} `{}` in success callback.'.format(task_actual['type'], task_actual['id']))
        return
    if not instance:
        return

    from cyborgbackup.main.utils.tasks import run_job_complete
    run_job_complete.delay(instance.id)

@shared_task(queue='cyborgbackup', base=LogErrorsTask)
def handle_work_error(task_id, *args, **kwargs):
    subtasks = kwargs.get('subtasks', None)
    logger.debug('Executing error task id %s, subtasks: %s' % (task_id, str(subtasks)))
    first_instance = None
    first_instance_type = ''
    if subtasks is not None:
        for each_task in subtasks:
            try:
                instance = Job.get_instance_by_type(each_task['type'], each_task['id'])
                if not instance:
                    # Unknown task type
                    logger.warn("Unknown task type: {}".format(each_task['type']))
                    continue
            except ObjectDoesNotExist:
                logger.warning('Missing {} `{}` in error callback.'.format(each_task['type'], each_task['id']))
                continue

            if first_instance is None:
                first_instance = instance
                first_instance_type = each_task['type']

            if instance.celery_task_id != task_id and not instance.cancel_flag:
                instance.status = 'failed'
                instance.failed = True
                if not instance.job_explanation:
                    instance.job_explanation = 'Previous Task Failed: {"job_type": "%s", "job_name": "%s", "job_id": "%s"}' % \
                                               (first_instance_type, first_instance.name, first_instance.id)
                instance.save()
                instance.websocket_emit_status("failed")

    # We only send 1 job complete message since all the job completion message
    # handling does is trigger the scheduler. If we extend the functionality of
    # what the job complete message handler does then we may want to send a
    # completion event for each job here.
    if first_instance:
        from cyborgbackup.main.utils.tasks import run_job_complete
        run_job_complete.delay(first_instance.id)
        pass

def with_path_cleanup(f):
    @functools.wraps(f)
    def _wrapped(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        finally:
            for p in self.cleanup_paths:
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    elif os.path.exists(p):
                        os.remove(p)
                except OSError:
                    logger.exception(six.text_type("Failed to remove tmp file: {}").format(p))
            self.cleanup_paths = []
    return _wrapped


class BaseTask(LogErrorsTask):
    name = None
    model = None
    event_model = None
    abstract = True
    cleanup_paths = []
    proot_show_paths = []

    def update_model(self, pk, _attempt=0, **updates):
        """Reload the model instance from the database and update the
        given fields.
        """
        output_replacements = updates.pop('output_replacements', None) or []

        try:
            with transaction.atomic():
                # Retrieve the model instance.
                instance = self.model.objects.get(pk=pk)

                # Update the appropriate fields and save the model
                # instance, then return the new instance.
                if updates:
                    update_fields = ['modified']
                    for field, value in updates.items():
                        if field in ('result_traceback'):
                            for srch, repl in output_replacements:
                                value = value.replace(srch, repl)
                        setattr(instance, field, value)
                        update_fields.append(field)
                        if field == 'status':
                            update_fields.append('failed')
                    instance.save(update_fields=update_fields)
                return instance
        except DatabaseError as e:
            # Log out the error to the debug logger.
            logger.debug('Database error updating %s, retrying in 5 '
                         'seconds (retry #%d): %s',
                         self.model._meta.object_name, _attempt + 1, e)

            # Attempt to retry the update, assuming we haven't already
            # tried too many times.
            if _attempt < 5:
                time.sleep(5)
                return self.update_model(
                    pk,
                    _attempt=_attempt + 1,
                    output_replacements=output_replacements,
                    **updates
                )
            else:
                logger.error('Failed to update %s after %d retries.',
                             self.model._meta.object_name, _attempt)

    def get_path_to(self, *args):
        '''
        Return absolute path relative to this file.
        '''
        return os.path.abspath(os.path.join(os.path.dirname(__file__), *args))

    def build_private_data(self, instance, **kwargs):
        '''
        Return SSH private key data (only if stored in DB as ssh_key_data).
        Return structure is a dict of the form:
        '''
        private_data = {'credentials': {}}
        for settings in Setting.objects.filter(key__contains='ssh_key'):
            # If we were sent SSH credentials, decrypt them and send them
            # back (they will be written to a temporary file).
            private_data['credentials'][settings] = decrypt_field(settings, 'value') or ''

        return private_data

    def build_private_data_dir(self, instance, **kwargs):
        '''
        Create a temporary directory for job-related files.
        '''
        path = tempfile.mkdtemp(prefix='cyborgbackup_%s_' % instance.pk, dir='/tmp/')
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.cleanup_paths.append(path)
        return path

    def build_private_data_files(self, instance, **kwargs):
        '''
        Creates temporary files containing the private data.
        Returns a dictionary i.e.,

        {
            'credentials': {
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
            }
        }
        '''
        private_data = self.build_private_data(instance, **kwargs)
        private_data_files = {'credentials': {}}
        if private_data is not None:
            ssh_ver = get_ssh_version()
            ssh_too_old = True if ssh_ver == "unknown" else Version(ssh_ver) < Version("6.0")
            openssh_keys_supported = ssh_ver != "unknown" and Version(ssh_ver) >= Version("6.5")
            for settings, data in private_data.get('credentials', {}).items():
                # Bail out now if a private key was provided in OpenSSH format
                # and we're running an earlier version (<6.5).
                if 'OPENSSH PRIVATE KEY' in data and not openssh_keys_supported:
                    raise RuntimeError(OPENSSH_KEY_ERROR)
            listpaths = []
            for settings, data in private_data.get('credentials', {}).items():
                # OpenSSH formatted keys must have a trailing newline to be
                # accepted by ssh-add.
                if 'OPENSSH PRIVATE KEY' in data and not data.endswith('\n'):
                    data += '\n'
                # For credentials used with ssh-add, write to a named pipe which
                # will be read then closed, instead of leaving the SSH key on disk.
                if settings and not ssh_too_old:
                    name = 'credential_{}'.format(settings.key)
                    path = os.path.join(kwargs['private_data_dir'], name)
                    run.open_fifo_write(path, data)
                    listpaths.append(path)
            if len(listpaths) > 1:
                private_data_files['credentials']['ssh'] = listpaths
            elif len(listpaths) == 1:
                private_data_files['credentials']['ssh'] = listpaths[0]

        return private_data_files

    def build_extra_vars_file(self, vars, **kwargs):
        handle, path = tempfile.mkstemp(dir=kwargs.get('private_data_dir', None))
        f = os.fdopen(handle, 'w')
        f.write(json.dumps(vars))
        f.close()
        os.chmod(path, stat.S_IRUSR)
        return path

    def build_env(self, instance, **kwargs):
        '''
        Build environment dictionary
        '''
        env = {}
        for attr in dir(settings):
            if attr == attr.upper() and attr.startswith('CYBORGBACKUP_'):
                env[attr] = str(getattr(settings, attr))

        if 'private_data_dir' in kwargs.keys():
            env['PRIVATE_DATA_DIR'] = kwargs['private_data_dir']
        return env

    def build_args(self, instance, **kwargs):
        raise NotImplementedError

    def build_safe_args(self, instance, **kwargs):
        return self.build_args(instance, **kwargs)

    def build_cwd(self, instance, **kwargs):
        raise NotImplementedError

    def build_output_replacements(self, instance, **kwargs):
        return []

    def get_idle_timeout(self):
        return None

    def get_instance_timeout(self, instance):
        global_timeout_setting_name = instance._global_timeout_setting()
        if global_timeout_setting_name:
            global_timeout = getattr(settings, global_timeout_setting_name, 0)
            job_timeout = global_timeout
        else:
            job_timeout = 0
        return job_timeout

    def get_password_prompts(self, **kwargs):
        '''
        Return a dictionary where keys are strings or regular expressions for
        prompts, and values are password lookup keys (keys that are returned
        from build_passwords).
        '''
        return OrderedDict()

    def get_stdout_handle(self, instance):
        '''
        Return an virtual file object for capturing stdout and events.
        '''
        dispatcher = CallbackQueueDispatcher()

        def event_callback(event_data):
            event_data.setdefault(self.event_data_key, instance.id)
            if 'uuid' in event_data:
                cache_event = cache.get('ev-{}'.format(event_data['uuid']), None)
                if cache_event is not None:
                    event_data.update(cache_event)
            dispatcher.dispatch(event_data)

        return OutputEventFilter(event_callback)

    def pre_run_hook(self, instance, **kwargs):
        '''
        Hook for any steps to run before the job/task starts
        '''

    def post_run_hook(self, instance, status, **kwargs):
        '''
        Hook for any steps to run before job/task is marked as complete.
        '''

    def final_run_hook(self, instance, status, **kwargs):
        '''
        Hook for any steps to run after job/task is marked as complete.
        '''

    @with_path_cleanup
    def run(self, pk, isolated_host=None, **kwargs):
        '''
        Run the job/task and capture its output.
        '''
        instance = self.update_model(pk, status='running', start_args='')

        instance.websocket_emit_status("running")
        status, rc, tb = 'error', None, ''
        output_replacements = []
        extra_update_fields = {}
        event_ct = 0
        try:
            kwargs['isolated'] = isolated_host is not None
            self.pre_run_hook(instance, **kwargs)
            if instance.cancel_flag:
                instance = self.update_model(instance.pk, status='canceled')
            if instance.status != 'running':
                if hasattr(settings, 'CELERY_UNIT_TEST'):
                    return
                else:
                    # Stop the task chain and prevent starting the job if it has
                    # already been canceled.
                    instance = self.update_model(pk)
                    status = instance.status
                    raise RuntimeError('not starting %s task' % instance.status)

            kwargs['private_data_dir'] = self.build_private_data_dir(instance, **kwargs)
            # May have to serialize the value
            kwargs['private_data_files'] = self.build_private_data_files(instance, **kwargs)
            kwargs['passwords'] = self.build_passwords(instance, **kwargs)
            args = self.build_args(instance, **kwargs)
            safe_args = self.build_safe_args(instance, **kwargs)
            output_replacements = self.build_output_replacements(instance, **kwargs)
            cwd = self.build_cwd(instance, **kwargs)
            env = self.build_env(instance, **kwargs)
            instance = self.update_model(instance.pk, job_args=' '.join(args), job_cwd=cwd, job_env=json.dumps(env))

            #safe_env = build_safe_env(env)

            stdout_handle = self.get_stdout_handle(instance)
            # If there is an SSH key path defined, wrap args with ssh-agent.
            ssh_key_path = self.get_ssh_key_path(instance, **kwargs)
            # If we're executing on an isolated host, don't bother adding the
            # key to the agent in this environment
            if ssh_key_path:
                ssh_auth_sock = os.path.join(kwargs['private_data_dir'], 'ssh_auth.sock')
                args = run.wrap_args_with_ssh_agent(args, ssh_key_path, ssh_auth_sock)
                safe_args = run.wrap_args_with_ssh_agent(safe_args, ssh_key_path, ssh_auth_sock)

            expect_passwords = {}
            for k, v in self.get_password_prompts(**kwargs).items():
                expect_passwords[k] = kwargs['passwords'].get(v, '') or ''
            _kw = dict(
                expect_passwords=expect_passwords,
                cancelled_callback=lambda: self.update_model(instance.pk).cancel_flag,
                job_timeout=self.get_instance_timeout(instance),
                idle_timeout=self.get_idle_timeout(),
                extra_update_fields=extra_update_fields,
                pexpect_timeout=getattr(settings, 'PEXPECT_TIMEOUT', 5),
            )
            status, rc = run.run_pexpect(
                args, cwd, env, stdout_handle, **_kw
            )
        except Exception:
            if status != 'canceled':
                tb = traceback.format_exc()
                if settings.DEBUG:
                    logger.exception('%s Exception occurred while running task', instance.log_format)
        finally:
            try:
                stdout_handle.flush()
                stdout_handle.close()
                event_ct = getattr(stdout_handle, '_event_ct', 0)
                logger.info('%s finished running, producing %s events.',
                            instance.log_format, event_ct)
            except Exception:
                logger.exception('Error flushing job stdout and saving event count.')

        try:
            self.post_run_hook(instance, status, **kwargs)
        except Exception:
            logger.exception(six.text_type('{} Post run hook errored.').format(instance.log_format))
        instance = self.update_model(pk)
        if instance.cancel_flag:
            status = 'canceled'

        instance = self.update_model(pk, status=status, result_traceback=tb,
                                     output_replacements=output_replacements,
                                     emitted_events=event_ct,
                                     **extra_update_fields)
        try:
            self.final_run_hook(instance, status, **kwargs)
        except Exception:
            logger.exception(six.text_type('{} Final run hook errored.').format(instance.log_format))
        instance.websocket_emit_status(status)
        if status != 'successful' and not hasattr(settings, 'CELERY_UNIT_TEST'):
            # Raising an exception will mark the job as 'failed' in celery
            # and will stop a task chain from continuing to execute
            if status == 'canceled':
                raise CyBorgBackupTaskError.TaskCancel(instance, rc)
            else:
                raise CyBorgBackupTaskError.TaskError(instance, rc)

    def get_ssh_key_path(self, instance, **kwargs):
        '''
        If using an SSH key, return the path for use by ssh-agent.
        '''
        private_data_files = kwargs.get('private_data_files', {})
        if 'ssh' in private_data_files.get('credentials', {}):
            return private_data_files['credentials']['ssh']

        return ''


class RunJob(BaseTask):
    '''
    Celery task to run a job.
    '''

    name = 'cyborgbackup.main.tasks.run_job'
    model = Job
    event_model = JobEvent
    event_data_key = 'job_id'

    def build_passwords(self, job, **kwargs):
        '''
        Build a dictionary of passwords for SSH private key, SSH user, sudo/su.
        '''
        passwords = {}
        for setting in Setting.objects.filter(key__contains='ssh_key'):
            set = Setting.objects.get(key=setting.key.replace('ssh_key', 'ssh_password'))
            passwords['credential_{}'.format(setting.key)] = decrypt_field(set, 'value')
        return passwords

    def build_extra_vars_file(self, vars, **kwargs):
        handle, path = tempfile.mkstemp(dir=kwargs.get('private_data_dir', None))
        f = os.fdopen(handle, 'w')
        f.write("# CyBorgBackup Extra Vars #\n")
        f.write(json.dumps(vars))
        f.close()
        os.chmod(path, stat.S_IRUSR)
        return path

    def build_args(self, job, **kwargs):
        '''
        Build command line argument list for running the task,
        optionally using ssh-agent for public/private key authentication.
        '''
        creds = None

        if creds:
            ssh_username = kwargs.get('username', creds.username)
        env = self.build_env(job, **kwargs)
        if job.job_type == 'check':
            agentUsers = User.objects.filter(is_agent=True)
            if not agentUsers.exists():
                agentUser = User()
                agentUser.email = 'cyborg@agent.local'
                agentUser.is_superuser = True
                agentUser.is_agent = True
                agentUser.save()
            else:
                agentUser = agentUsers.first()
            if job.client_id and job.policy.policy_type != 'vm':
                try:
                    setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
                    client_user = setting_client_user.value
                except Exception as e:
                    client_user = 'root'
                handle, path = tempfile.mkstemp()
                f = os.fdopen(handle, 'w')
                token, created = Token.objects.get_or_create(user=agentUser)
                base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'prepare_client')
                with open(base_script) as fs:
                    script = fs.read()
                f.write(script)
                f.close()
                handle_env, path_env = tempfile.mkstemp()
                f = os.fdopen(handle_env, 'w')
                for key,var in env.items():
                    f.write('export {}="{}"\n'.format(key, var))
                f.close()
                os.chmod(path, stat.S_IEXEC | stat.S_IREAD )
                args= ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= ['{}@{}'.format(client_user, job.client.hostname)]
                args+= ['\"', 'mkdir', env['PRIVATE_DATA_DIR'], '\"', '&&']
                args+= ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= [path, path_env, '{}@{}:{}/'.format(client_user, job.client.hostname, env['PRIVATE_DATA_DIR'])]
                args+= [ '&&' ]
                args+= ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= ['{}@{}'.format(client_user, job.client.hostname)]
                args+= ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
                args+= ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
                args+= [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)), '; exicode=$?;', 'rm', '-rf', env['PRIVATE_DATA_DIR'], '; exit $exitcode\"']
            if job.client_id and job.policy.policy_type == 'vm':
                try:
                    setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
                    client_user = setting_client_user.value
                except Exception as e:
                    client_user = 'root'
                handle, path_prepare = tempfile.mkstemp()
                f = os.fdopen(handle, 'w')
                base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'prepare_hypervisor')
                with open(base_script) as fs:
                    script = fs.read()
                f.write(script)
                f.close()
                handle, path_backup_script = tempfile.mkstemp()
                f = os.fdopen(handle, 'w')
                provider = load_module_provider(job.policy.vmprovider)
                hypervisor_hostname = provider.get_client(job.client.hostname)
                f.write(provider.get_script())
                f.close()
                env.update({'CYBORGBACKUP_BACKUP_SCRIPT': os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_backup_script))})
                handle_env, path_env = tempfile.mkstemp()
                f = os.fdopen(handle_env, 'w')
                for key,var in env.items():
                    f.write('export {}="{}"\n'.format(key, var))
                f.close()
                os.chmod(path_prepare, stat.S_IEXEC | stat.S_IREAD )
                args= ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= ['{}@{}'.format(client_user, hypervisor_hostname)]
                args+= ['\"', 'mkdir', env['PRIVATE_DATA_DIR'], '\"', '&&']
                args+= ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= [path_prepare, path_env, path_backup_script, '{}@{}:{}/'.format(client_user, hypervisor_hostname, env['PRIVATE_DATA_DIR'])]
                args+= [ '&&' ]
                args+= ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= ['{}@{}'.format(client_user, hypervisor_hostname)]
                args+= ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
                args+= ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
                args+= [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_prepare)), '; exicode=$?;', 'rm', '-rf', env['PRIVATE_DATA_DIR'], '; exit $exitcode\"']
            if job.repository_id:
                handle, path = tempfile.mkstemp()
                f = os.fdopen(handle, 'w')
                token, created = Token.objects.get_or_create(user=agentUser)
                base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'prepare_repository')
                with open(base_script) as fs:
                    script = fs.read()
                f.write(script)
                f.close()
                os.chmod(path, stat.S_IEXEC | stat.S_IREAD)
                handle_env, path_env = tempfile.mkstemp()
                f = os.fdopen(handle_env, 'w')
                for key,var in env.items():
                    if key == 'CYBORG_BORG_REPOSITORY' and ':' in var:
                        var = var.split(':')[1]
                    f.write('export {}="{}"\n'.format(key, var))
                f.close()
                repository_conn = job.policy.repository.path.split(':')[0]
                args= ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= [repository_conn]
                args+= ['\"', 'mkdir', env['PRIVATE_DATA_DIR'], '\"', '&&']
                args+= ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= [path, path_env, '{}:{}/'.format(repository_conn, env['PRIVATE_DATA_DIR'])]
                args+= [ '&&' ]
                args+= ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= [repository_conn]
                args+= ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
                args+= ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
                args+= [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)), '; exicode=$?;', 'rm', '-rf', env['PRIVATE_DATA_DIR'], '; exit $exitcode\"']
        elif job.job_type == 'catalog':
            agentUsers = User.objects.filter(is_agent=True)
            if not agentUsers.exists():
                agentUser = User()
                agentUser.email = 'cyborg@agent.local'
                agentUser.is_superuser = True
                agentUser.is_agent = True
                agentUser.save()
            else:
                agentUser = agentUsers.first()
            if job.client_id:
                handle, path = tempfile.mkstemp()
                f = os.fdopen(handle, 'w')
                token, created = Token.objects.get_or_create(user=agentUser)
                master_jobs = Job.objects.filter(dependent_jobs=job.pk)
                master_job = None
                if master_jobs.exists():
                    master_job = master_jobs.first()
                if not master_job:
                    master_jobs = Job.objects.filter(dependent_jobs=job.old_pk)
                    if master_jobs.exists():
                        master_job = master_jobs.first()
                if not master_job:
                    raise Exception("Unable to get master job")
                job_events = JobEvent.objects.filter(
                    job=master_job.pk,
                    stdout__contains="Archive name: {}".format(
                        master_job.policy.policy_type
                    )
                )
                archive_name = None
                if job_events.exists():
                    job_stdout = job_events.first().stdout
                    archive_name = job_stdout.split(':')[1].strip()
                if not archive_name:
                    raise Exception("Latest backup haven't archive name in the report")
                base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'fill_catalog')
                with open(base_script) as fs:
                    script = fs.read()
                f.write(script)
                f.close()
                os.chmod(path, stat.S_IEXEC | stat.S_IREAD )
                handle_env, path_env = tempfile.mkstemp()
                f = os.fdopen(handle_env, 'w')
                for key,var in env.items():
                    f.write('export {}="{}"\n'.format(key, var))
                f.close()
                repository_conn = job.policy.repository.path.split(':')[0]
                args= ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= [repository_conn]
                args+= ['\"', 'mkdir', env['PRIVATE_DATA_DIR'], '\"', '&&']
                args+= ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= [path, path_env, '{}:{}/'.format(repository_conn, env['PRIVATE_DATA_DIR'])]
                args+= [ '&&' ]
                args+= ['ssh', '-Ao', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                args+= [repository_conn]
                args+= ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
                args+= ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
                args+= [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)), '; exicode=$?;', 'rm', '-rf', env['PRIVATE_DATA_DIR'], '; exit $exitcode\"']
        elif job.job_type == 'prune':
            if job.client_id:
                prefix = '{}-{}-'.format(job.policy.policy_type, job.client.hostname)
                args = ['borg', 'prune', '-v', '--list']
                args+= ['--prefix', prefix]
                if job.policy.keep_hourly and job.policy.keep_hourly > 0:
                    args+= ['--keep-hourly={}'.format(job.policy.keep_hourly)]
                if job.policy.keep_daily and job.policy.keep_daily > 0:
                    args+= ['--keep-daily={}'.format(job.policy.keep_daily)]
                if job.policy.keep_weekly and job.policy.keep_weekly > 0:
                    args+= ['--keep-weekly={}'.format(job.policy.keep_weekly)]
                if job.policy.keep_monthly and job.policy.keep_monthly > 0:
                    args+= ['--keep-monthly={}'.format(job.policy.keep_monthly)]
                if job.policy.keep_yearly and job.policy.keep_yearly > 0:
                    args+= ['--keep-monthly={}'.format(job.policy.keep_yearly)]
        else:
            (client, client_user, args) = self.build_borg_cmd(job)
            handle_env, path_env = tempfile.mkstemp()
            f = os.fdopen(handle_env, 'w')
            for key,var in env.items():
                f.write('export {}="{}"\n'.format(key, var))
            f.close()
            new_args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            new_args+= ['{}@{}'.format(client_user, client)]
            new_args+= ['\"', 'mkdir', env['PRIVATE_DATA_DIR'], '\"', '&&']
            new_args+= ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            new_args+= [path_env, '{}@{}:{}/'.format(client_user, client, env['PRIVATE_DATA_DIR'])]
            new_args+= [ '&&' ]
            new_args+= ['ssh', '-Ao', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            new_args+= ['{}@{}'.format(client_user, client)]
            new_args+= ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            new_args+= ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            new_args+= [' '.join(args), '; exicode=$?;', 'rm', '-rf', env['PRIVATE_DATA_DIR'], '; exit $exitcode\"']
            args = new_args
        return args

########
# Backup host => backupHost
# Client => client
# Repository => /backup
########
# rootfs        Backup all / filesystem
# vm            Backup Virtual Machine disk using snapshot
# mysql         Backup MySQL Database
# postgresql    Backup PostgreSQL
# piped         Backup using pipe program
# config        Backup only /etc
# mail          Backup only mail directory
########
# rootfs
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX && cd /tmp/sshfs_XXX && borg create /backup::archive . && fusermount -u /tmp/sshfs"
# config
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /etc"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX && cd /tmp/sshfs_XXX && borg create /backup::archive ./etc && fusermount -u /tmp/sshfs
# mail
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /var/lib/mail"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX && cd /tmp/sshfs_XXX && borg create /backup::archive ./var/lib/mail && fusermount -u /tmp/sshfs
# mysql
#   pull => ssh root@client "mysqldump | borg create borg@backupHost:/backup::archive -"
#   push => ssh borg@backupHost "ssh root@client "mysqldump" | borg create /backup::archive -"
# pgsql
#   pull => ssh root@client "pg_dumpall|pg_dump | borg create borg@backupHost:/backup::archive -"
#   push => ssh borg@backupHost "ssh root@client "pg_dumpall|pg_dump" | borg create /backup::archive -"
########

    def build_borg_cmd(self, job):
        policy_type = job.policy.policy_type
        jobDate = job.created
        jobDateString = jobDate.strftime("%Y-%m-%d_%H-%M")
        excludedDirs = []
        args = []
        piped = ''
        client = job.client.hostname
        client_hostname = client
        try:
            setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
            client_user = setting_client_user.value
        except Exception as e:
            client_user = 'root'
        args += ['borg']
        args += ['create']
        repositoryPath = ''
        if not job.policy.mode_pull:
            repositoryPath = job.policy.repository.path
        args += ['--debug', '-v', '--stats']
        archive_client_name = job.client.hostname
        if policy_type == 'rootfs':
            path = '/'
            excludedDirs = ['/media', '/dev', '/proc', '/sys', '/var/run', '/run', '/lost+found', '/mnt', '/var/lib/lxcfs', '/tmp']
        if policy_type == 'config':
            path = '/etc'
        if policy_type == 'mail':
            path = '/var/lib/mail /var/mail'
        if policy_type in ('mysql', 'postgresql', 'piped'):
            path = '-'
            if policy_type == 'mysql':
                piped += 'mysqldump'
            if policy_type == 'postgresql':
                piped += 'pg_dumpall'
            if policy_type == 'piped':
                piped += 'dd if=/dev/sda'
            if not job.policy.mode_pull:
                args = [piped, '|']+args
        if policy_type == 'vm':
            path = '-'
            provider = load_module_provider(job.policy.vmprovider)
            client = provider.get_client(job.client.hostname)
            client_hostname = client
            piped_list = ['/var/cache/cyborgbackup/borg_backup_vm']
            piped = ' '.join(piped_list)
            if not job.policy.mode_pull:
                 args = [piped, '|']+args
        if client_user != 'root':
            args = ['sudo']+args
        args += ['{}::{}-{}-{}'.format(repositoryPath, policy_type, archive_client_name, jobDateString)]
        if job.policy.mode_pull and policy_type in ('rootfs', 'config', 'mail'):
            path = '.'+path
        args += [path]
        if len(excludedDirs) > 0:
            keyword = '--exclude '
            if job.policy.mode_pull:
                keyword += '.'
            args += (keyword + (' '+keyword).join(excludedDirs)).split(' ')
        if job.policy.mode_pull:
            (clientUri, repository_path) = job.policy.repository.path.split(':')
            client = clientUri.split('@')[1]
            client_user = clientUri.split('@')[0]
            if policy_type in ('rootfs', 'config', 'mail'):
                sshFsDirectory = '/tmp/sshfs_{}_{}'.format(client_hostname, jobDateString)
                pullCmd = ['mkdir', sshFsDirectory]
                pullCmd += ['&&', 'sshfs', 'root@{}:{}'.format(client_hostname, path[1::]), sshFsDirectory]
                pullCmd += ['&&', 'cd', sshFsDirectory]
                pullCmd += ['&&']+args
                args = pullCmd
            if policy_type in ('mysql', 'postgresql', 'piped', 'vm'):
                pullCmd = ['ssh', '{}@{}'.format(client_user, client_hostname)]
                if client_user != 'root':
                    piped = 'sudo '+piped
                pullCmd += ["'"+piped+"'|"+' '.join(args)]
                args = pullCmd
            if policy_type == 'vm':
                pass

        return (client, client_user, args)

    def build_safe_args(self, job, **kwargs):
        return self.build_args(job, display=True, **kwargs)

    def build_env(self, job, **kwargs):
        env = super(RunJob, self).build_env(job, **kwargs)
        agentUsers = User.objects.filter(is_agent=True)
        if not agentUsers.exists():
            agentUser = User()
            agentUser.email = 'cyborg@agent.local'
            agentUser.is_superuser = True
            agentUser.is_agent = True
            agentUser.save()
        else:
            agentUser = agentUsers.first()
            token, created = Token.objects.get_or_create(user=agentUser)
        if token and (job.job_type == 'check' or job.job_type == 'catalog'):
            env['CYBORG_AGENT_TOKEN'] = str(token)
            try:
                set = Setting.objects.get(key='cyborgbackup_url')
                base_url = set.value
            except Exception as e:
                base_url = 'http://web:8000'
            if job.job_type == 'check':
                if job.client_id:
                    env['CYBORG_URL'] = '{}/api/v1/clients/{}/'.format(base_url, job.client_id)
                if job.repository_id:
                    env['CYBORG_URL'] = '{}/api/v1/repositories/{}/'.format(base_url, job.repository_id)
            if job.job_type == 'catalog':
                env['CYBORG_URL'] = '{}/api/v1/catalogs/'.format(base_url)
            if job.repository_id or job.job_type == 'catalog':
                env['CYBORG_BORG_PASSPHRASE'] = job.policy.repository.repository_key
                if job.job_type == 'catalog':
                    env['CYBORG_BORG_REPOSITORY'] = job.policy.repository.path.split(':')[1]
                else:
                    env['CYBORG_BORG_REPOSITORY'] = job.policy.repository.path
            if job.job_type == 'catalog':
                master_jobs = Job.objects.filter(dependent_jobs=job.pk)
                if master_jobs.exists():
                    master_job = master_jobs.first()
                job_events = JobEvent.objects.filter(
                    job=master_job.pk,
                    stdout__contains="Archive name: {}".format(
                        master_job.policy.policy_type
                    )
                )
                if job_events.exists():
                    job_stdout = job_events.first().stdout
                    archive_name = job_stdout.split(':')[1].strip()
                env['CYBORG_JOB_ARCHIVE_NAME'] = archive_name
                env['CYBORG_JOB_ID'] = str(master_job.pk)
        else:
            env['BORG_PASSPHRASE'] = job.policy.repository.repository_key
            env['BORG_REPO'] = job.policy.repository.path
        env['BORG_RSH'] = 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
        return env

    def build_cwd(self, job, **kwargs):
        cwd = '/tmp/'
        return cwd

    def get_idle_timeout(self):
        return getattr(settings, 'JOB_RUN_IDLE_TIMEOUT', None)

    def get_password_prompts(self, **kwargs):
        d = super(RunJob, self).get_password_prompts(**kwargs)
        for k, v in kwargs['passwords'].items():
            d[re.compile(r'Enter passphrase for .*'+k+':\s*?$', re.M)] = k
            d[re.compile(r'Enter passphrase for .*'+k, re.M)] = k
        d[re.compile(r'Bad passphrase, try again for .*:\s*?$', re.M)] = ''
        return d


Celery('cyborgbackup').register_task(RunJob())
