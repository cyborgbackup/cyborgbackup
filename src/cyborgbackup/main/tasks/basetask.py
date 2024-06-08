import json
import logging
import os
import shutil
import stat
import tempfile
import time
import traceback
from collections import OrderedDict

from celery import Task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction, DatabaseError

from cyborgbackup.main.exceptions import JobException, JobHookException
from cyborgbackup.main.expect import run
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.tasks.builders.helpers import build_passwords, build_cwd, build_env
from cyborgbackup.main.tasks.errors import _CyBorgBackupTaskError
from cyborgbackup.main.tasks.helpers import with_path_cleanup
from cyborgbackup.main.utils.callbacks import CallbackQueueDispatcher
from cyborgbackup.main.utils.common import get_type_for_model, OutputEventFilter
from cyborgbackup.main.utils.encryption import decrypt_field

logger = logging.getLogger('cyborgbackup.main.tasks.bastask')

CyBorgBackupTaskError = _CyBorgBackupTaskError()


class LogErrorsTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if getattr(exc, 'is_cyborgbackup_task_error', False):
            logger.warning(str("{}").format(exc))
        elif isinstance(self, BaseTask):
            logger.exception(str(
                '{!s} {!s} execution encountered exception.')
                             .format(get_type_for_model(self.model), args[0]))
        else:
            logger.exception(str('Task {} encountered exception.').format(self.name), exc_info=exc)
        super(LogErrorsTask, self).on_failure(exc, task_id, args, kwargs, einfo)


class BaseTask(LogErrorsTask):
    name = None
    model = None
    event_model = None
    event_data_key = None
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
                        if field in ('result_traceback',):
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
        """
        Return absolute path relative to this file.
        """
        return os.path.abspath(os.path.join(os.path.dirname(__file__), *args))

    def build_private_data(self, instance, **kwargs):
        """
        Return SSH private key data (only if stored in DB as ssh_key_data).
        Return structure is a dict of the form:
        """
        private_data = {'credentials': {}}
        for sets in Setting.objects.filter(key__contains='ssh_key'):
            # If we were sent SSH credentials, decrypt them and send them
            # back (they will be written to a temporary file).
            private_data['credentials'][sets] = decrypt_field(sets, 'value') or ''

        return private_data

    def build_private_data_dir(self, instance, **kwargs):
        """
        Create a temporary directory for job-related files.
        """
        path = tempfile.mkdtemp(prefix='cyborgbackup_%s_' % instance.pk, dir='/var/tmp/cyborgbackup')
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.cleanup_paths.append(path)
        return path

    def build_private_data_files(self, instance, **kwargs):
        """
        Creates temporary files containing the private data.
        Returns a dictionary i.e.,

        {
            'credentials': {
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
                <cyborgbackup.main.models.Credential>: '/path/to/decrypted/data',
            }
        }
        """
        private_data = self.build_private_data(instance, **kwargs)
        private_data_files = {'credentials': {}}
        if private_data is not None:
            listpaths = []
            for sets, data in private_data.get('credentials', {}).items():
                # OpenSSH formatted keys must have a trailing newline to be
                # accepted by ssh-add.
                if 'OPENSSH PRIVATE KEY' in data and not data.endswith('\n'):
                    data += '\n'
                # For credentials used with ssh-add, write to a named pipe which
                # will be read then closed, instead of leaving the SSH key on disk.
                if sets:
                    name = 'credential_{}'.format(sets.key)
                    path = os.path.join(kwargs['private_data_dir'], name)
                    run.open_fifo_write(path, data)
                    listpaths.append(path)
            if len(listpaths) > 1:
                private_data_files['credentials']['ssh'] = listpaths
            elif len(listpaths) == 1:
                private_data_files['credentials']['ssh'] = listpaths[0]

        return private_data_files

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
        """
        Return a dictionary where keys are strings or regular expressions for
        prompts, and values are password lookup keys (keys that are returned
        from build_passwords).
        """
        return OrderedDict()

    def get_stdout_handle(self, instance):
        """
        Return an virtual file object for capturing stdout and events.
        """
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
        """
        Hook for any steps to run before the job/task starts
        """

    def post_run_hook(self, instance, status, **kwargs):
        """
        Hook for any steps to run before job/task is marked as complete.
        """

    def final_run_hook(self, instance, status, **kwargs):
        """
        Hook for any steps to run after job/task is marked as complete.
        """

    @with_path_cleanup
    def run(self, pk, isolated_host=None, **kwargs):
        """
        Run the job/task and capture its output.
        """
        instance = self.update_model(pk, status='running', start_args='')

        instance.websocket_emit_status("running")
        status, rc, tb = 'error', None, ''
        stdout_handle = None
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
            kwargs['passwords'] = build_passwords()
            args = self.build_args(instance, **kwargs)
            safe_args = self.build_safe_args(instance, **kwargs)
            output_replacements = self.build_output_replacements(instance, **kwargs)
            cwd = build_cwd(instance, **kwargs)
            env = build_env(instance, **kwargs)
            instance = self.update_model(instance.pk, job_args=' '.join(args), job_cwd=cwd, job_env=json.dumps(env))

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
        except JobException:
            if status != 'canceled':
                tb = traceback.format_exc()
                if settings.DEBUG:
                    logger.exception('%s Exception occurred while running task', instance.log_format)
        finally:
            try:
                shutil.rmtree(kwargs['private_data_dir'])
            except Exception:
                logger.exception('Error flushing Private Data dir')
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
        except JobHookException:
            logger.exception(str('{} Post run hook errored.').format(instance.log_format))
        instance = self.update_model(pk)
        if instance.cancel_flag:
            status = 'canceled'

        instance = self.update_model(pk, status=status, result_traceback=tb,
                                     output_replacements=output_replacements,
                                     emitted_events=event_ct,
                                     **extra_update_fields)
        try:
            self.final_run_hook(instance, status, **kwargs)
        except JobHookException:
            logger.exception(str('{} Final run hook errored.').format(instance.log_format))
        instance.websocket_emit_status(status)
        if status != 'successful' and not hasattr(settings, 'CELERY_UNIT_TEST'):
            # Raising an exception will mark the job as 'failed' in celery
            # and will stop a task chain from continuing to execute
            if status == 'canceled':
                raise CyBorgBackupTaskError.TaskCancel(instance, rc)
            else:
                raise CyBorgBackupTaskError.TaskError(instance, rc)

    def get_ssh_key_path(self, instance, **kwargs):
        """
        If using an SSH key, return the path for use by ssh-agent.
        """
        private_data_files = kwargs.get('private_data_files', {})
        if 'ssh' in private_data_files.get('credentials', {}):
            return private_data_files['credentials']['ssh']

        return ''
