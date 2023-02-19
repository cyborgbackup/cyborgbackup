# Python
from collections import OrderedDict
import functools
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import time
import traceback
import datetime
import random
import six
import smtplib
import pymongo
from email.message import EmailMessage
from email.headerregistry import Address
try:
    import psutil
except Exception:
    psutil = None

from contextlib import contextmanager

# Celery
from celery import Task, shared_task, Celery

# Django
from django.conf import settings
from django.db import transaction, DatabaseError
from django.utils.timezone import now
from django.core import management
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django_pglocks import advisory_lock as django_pglocks_advisory_lock
from django.db import connection
from jinja2 import Environment, FileSystemLoader
from rest_framework.authtoken.models import Token

# CyBorgBackup
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.models.repositories import Repository
from cyborgbackup.main.models.events import JobEvent
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.models.catalogs import Catalog
from cyborgbackup.main.models.users import User
from cyborgbackup.main.models.schedules import CyborgBackupScheduleState
from cyborgbackup.main.expect import run
from cyborgbackup.main.consumers import emit_channel_notification
from cyborgbackup.main.utils.common import OutputEventFilter, get_type_for_model, load_module_provider
from cyborgbackup.main.utils.encryption import decrypt_field
from cyborgbackup.main.utils.callbacks import CallbackQueueDispatcher

__all__ = ['RunJob', 'handle_work_error', 'handle_work_success', 'advisory_lock', 'CallbackQueueDispatcher',
           'CyBorgBackupTaskError', 'cyborgbackup_periodic_scheduler',
           'LogErrorsTask', 'purge_old_stdout_files']

OPENSSH_KEY_ERROR = u'''\
It looks like you're trying to use a private key in OpenSSH format, which \
isn't supported by the installed version of OpenSSH on this instance. \
Try upgrading OpenSSH or providing your private key in an different format. \
'''

logger = logging.getLogger('cyborgbackup.main.tasks')


def humanbytes(B):
    '  Return the given bytes as a human friendly KB, MB, GB, or TB string'
    B = float(B)
    KB = float(1024)
    MB = float(KB ** 2)  # 1,048,576
    GB = float(KB ** 3)  # 1,073,741,824
    TB = float(KB ** 4)  # 1,099,511,627,776

    if B < KB:
        return '{0} {1}'.format(B, 'Bytes' if 0 == B > 1 else 'Byte')
    elif KB <= B < MB:
        return '{0:.2f} KB'.format(B/KB)
    elif MB <= B < GB:
        return '{0:.2f} MB'.format(B/MB)
    elif GB <= B < TB:
        return '{0:.2f} GB'.format(B/GB)
    elif TB <= B:
        return '{0:.2f} TB'.format(B/TB)


def build_report(type):
    since = 24*60*60
    if type == 'daily':
        since *= 1
    elif type == 'weekly':
        since *= 7
    elif type == 'monthly':
        since *= 31
    started = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=since)
    jobs = Job.objects.filter(started__gte=started, job_type='job')
    total_times = 0
    total_backups = 0
    total_size = 0
    total_deduplicated = 0
    lines = []
    if jobs.exists():
        for job in jobs:
            number_of_files = Catalog.objects.filter(job=job.pk).__len__()
            total_times += job.elapsed
            total_backups += 1
            total_size += job.original_size
            total_deduplicated += job.deduplicated_size
            line = {
                'client': job.client.hostname,
                'type': job.policy.policy_type,
                'status': job.status,
                'duration': str(datetime.timedelta(seconds=float(job.elapsed))),
                'numberFiles': str(number_of_files),
                'original_size': str(humanbytes(job.original_size)),
                'deduplicated_size': str(humanbytes(job.deduplicated_size))
            }
            lines.append(line)
    report = {
        'times': total_times,
        'backups': total_backups,
        'size': humanbytes(total_size),
        'deduplicated': humanbytes(total_deduplicated),
        'lines': lines
    }
    return report


def generate_ascii_table(elements):
    for elt in elements['lines']:
        for col in elements['columns']:
            if len(elt[col['key']]) > col['minsize']-2:
                col['minsize'] = len(elt[col['key']])+2
    line = '+'
    for col in elements['columns']:
        line += '-'*col['minsize']+'+'
    header = line + '\n'
    for col in elements['columns']:
        header += '| ' + col['title'].ljust(col['minsize']-1)
    header += '|' + '\n' + line
    table = header
    for elt in elements['lines']:
        table += '\n'
        for col in elements['columns']:
            table += '| ' + elt[col['key']].ljust(col['minsize']-1)
        table += '|'
    table += '\n'+line
    return table


def generate_html_table(elements):
    table = '<table>\n<thead><tr>'
    for col in elements['columns']:
        table += '<th>'+col['title']+'</th>\n'
    table += '</tr></thead>\n<tbody>'
    for elt in elements['lines']:
        table += '<tr>'
        for col in elements['columns']:
            table += '<td>'+elt[col['key']]+'</td>\n'
        table += '</tr>\n'
    table += '</tbody></table>\n'
    return table


def generate_html_joboutput(elements):
    output = """Job Output : <div class="job-results-standard-out">
      <div class="JobResultsStdOut">
        <div class="JobResultsStdOut-stdoutContainer">"""
    lineNumber = 1
    for line in elements['lines']:
        output += """<div class="JobResultsStdOut-aLineOfStdOut">
              <div class="JobResultsStdOut-lineNumberColumn">
                <span class="JobResultsStdOut-lineExpander"></span>{}
              </div>
              <div class="JobResultsStdOut-stdoutColumn"><span>{}</span></div>
          </div>""".format(lineNumber, line)
        lineNumber += 1
    output += """</div>
      </div>
    </div>"""
    return output


def send_email(elements, type, mail_to):
    try:
        setting = Setting.objects.get(key='cyborgbackup_mail_from')
        mail_address = setting.value
    except Exception:
        mail_address = 'cyborgbackup@cyborgbackup.local'
    try:
        setting = Setting.objects.get(key='cyborgbackup_mail_server')
        mail_server = setting.value
    except Exception:
        mail_server = 'localhost'
    msg = EmailMessage()
    msg['Subject'] = 'CyBorgBackup Report'
    msg['From'] = Address("CyBorgBackup", mail_address.split('@')[0], mail_address.split('@')[1])
    msg['To'] = mail_to
    if type != 'after':
        ascii_table = generate_ascii_table(elements)
        html_table = generate_html_table(elements)
    else:
        ascii_table = ""
        html_table = generate_html_joboutput(elements)
    logo = os.path.join(settings.BASE_DIR, 'cyborgbackup', 'logo.txt')
    with open(logo) as f:
        logo_text = f.read()
    context = {
        "type": type,
        "logo_text": logo_text,
        "now": datetime.datetime.now(),
        "ascii_table": ascii_table,
        "html_table": html_table
    }
    context.update(elements)
    if type == 'after':
        if elements['state'] == 'successful':
            logo = os.path.join(settings.BASE_DIR, 'cyborgbackup', 'icon_success.txt')
            with open(logo) as f:
                context['state_icon'] = f.read()
            context['state_class'] = "alert-success"
        else:
            logo = os.path.join(settings.BASE_DIR, 'cyborgbackup', 'icon_failed.txt')
            with open(logo) as f:
                context['state_icon'] = f.read()
            context['state_class'] = "alert-failed"

    environment = Environment(loader=FileSystemLoader("templates/"))
    tmpl_html = environment.get_template("mail_html.j2")
    tmpl_text = environment.get_template("mail_text.j2")

    html_version = tmpl_html.render(context)
    text_version = tmpl_text.render(context)
    msg.set_content(text_version)
    msg.add_alternative(html_version, subtype='html')
    logger.debug('Send Email')
    with smtplib.SMTP(mail_server) as s:
        s.send_message(msg)


@contextmanager
def advisory_lock(*args, **kwargs):
    if connection.vendor == 'postgresql':
        with django_pglocks_advisory_lock(*args, **kwargs) as internal_lock:
            yield internal_lock
    else:
        yield True


class _CyBorgBackupTaskError:
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


def launch_integrity_check():
    # TODO
    # Launch Integrity Check on all Repositories based on crontab defined in Settings
    print("You didn't say the magic word")


units = {"B": 1, "kB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12}


def parseSize(size):
    number, unit = [string.strip() for string in size.split()]
    return int(float(number)*units[unit])


@shared_task(bind=True, base=LogErrorsTask)
def compute_borg_size(self):
    logger.debug('Compute Borg Size Report')
    jobs = Job.objects.filter(original_size=0,
                              deduplicated_size=0,
                              compressed_size=0,
                              status='successful',
                              job_type='job').order_by('-finished')
    if jobs.exists():
        for job in jobs:
            events = JobEvent.objects.filter(job_id=job.pk, stdout__contains='This archive:').order_by('-counter')
            for event in events:
                prg = re.compile(r"This archive:\s*([0-9\.]*\s*.B)\s*([0-9\.]*\s*.B)\s*([0-9\.]*\s*.B)\s*")
                m = prg.match(event.stdout)
                if m:
                    job.original_size = parseSize(m.group(1))
                    job.compressed_size = parseSize(m.group(2))
                    job.deduplicated_size = parseSize(m.group(3))
                    job.save()
                    break
    repos = Repository.objects.filter(ready=True)
    if repos.exists():
        for repo in repos:
            jobs = Job.objects.filter(policy__repository_id=repo.pk,
                                      status='successful',
                                      job_type='job').order_by('-finished')
            if jobs.exists():
                last_running_job = jobs.first()
                events = JobEvent.objects.filter(job_id=last_running_job.pk, stdout__contains='All archives:').order_by('-counter')
                for event in events:
                    prg = re.compile(r"All archives:\s*([0-9\.]*\s*.B)\s*([0-9\.]*\s*.B)\s*([0-9\.]*\s*.B)\s*")
                    m = prg.match(event.stdout)
                    if m:
                        repo.original_size = parseSize(m.group(1))
                        repo.compressed_size = parseSize(m.group(2))
                        repo.deduplicated_size = parseSize(m.group(3))
                        repo.save()
                        break


@shared_task(bind=True, base=LogErrorsTask)
def random_restore_integrity(self):
    logger.debug('Auto Restore Test for check Integrity')
    try:
        setting = Setting.objects.get(key='cyborgbackup_catalog_enabled')
        if setting.value == 'True':
            catalog_enabled = True
        else:
            catalog_enabled = False
    except Exception:
        catalog_enabled = True

    try:
        setting = Setting.objects.get(key='cyborgbackup_auto_restore_test')
        if setting.value == 'True':
            autorestore_test = True
        else:
            autorestore_test = False
    except Exception:
        autorestore_test = False

    if autorestore_test and catalog_enabled:
        jobs = Job.objects.filter(archive_name__isnull=False)
        if jobs.exists():
            selected_job = random.choice(jobs)
            db = pymongo.MongoClient(settings.MONGODB_URL).local
            query = {"archive_name": selected_job.archive_name, "type": "-"}
            entries_count = db.catalog.count(query)
            r = random.randint(1, entries_count + 1)
            selected_items = list(db.catalog.find(query).limit(1).skip(r))
            if len(selected_items) == 1:
                print(selected_items)

def _cyborgbackup_notifier_summary(policy_pk):
    logger.debug('Summary')
    users = User.objects.filter(notify_backup_summary=True)
    policy = Policy.objects.get(pk=policy_pk)

    try:
        setting = Setting.objects.get(key='cyborgbackup_catalog_enabled')
        if setting.value == 'True':
            catalog_enabled = True
        else:
            catalog_enabled = False
    except Exception:
        catalog_enabled = True

    try:
        setting = Setting.objects.get(key='cyborgbackup_auto_prune')
        if setting.value == 'True':
            auto_prune_enabled = True
        else:
            auto_prune_enabled = False
    except Exception:
        auto_prune_enabled = True
    report = {'lines': []}
    order = 1
    report['lines'].append({
        'order': str(order),
        'title': 'Policy {}'.format(policy.name),
        'type': 'policy'
    })
    order += 1
    if not policy.repository.ready:
        report['lines'].append({
            'order': str(order),
            'title': "Prepare Repository {}".format(policy.repository.name),
            'type': "repository"
        })
    have_prune_info = (policy.keep_hourly or policy.keep_daily
                       or policy.keep_weekly or policy.keep_monthly or policy.keep_yearly)
    for client in policy.clients.all():
        if not client.ready:
            order += 1
            report['lines'].append({
                'order': str(order),
                'title': "Prepare Client {}".format(client.hostname),
                'type': "client"
            })
        order += 1
        report['lines'].append({
            'order': str(order),
            'title': "Backup Job {} {}".format(policy.name, client.hostname),
            'type': policy.policy_type
        })
        if catalog_enabled:
            order += 1
            report['lines'].append({
                'order': str(order),
                'title': "Catalog Job {} {}".format(policy.name, client.hostname),
                'type': "catalog"
            })
        if auto_prune_enabled and have_prune_info:
            order += 1
            report['lines'].append({
                'order': str(order),
                'title': "Prune Job {} {}".format(policy.name, client.hostname),
                'type': "prune"
            })
    report['columns'] = [
        {'title': 'Order', 'key': 'order', 'minsize': 7},
        {'title': 'Title', 'key': 'title', 'minsize': 7},
        {'title': 'Type', 'key': 'type', 'minsize': 6}
    ]
    return report, users

def _cyborgbackup_notifier_after(job_pk):
    logger.debug('After Backup')
    job = Job.objects.get(pk=job_pk)
    users = []
    if job.status == 'successful':
        users = User.objects.filter(notify_backup_success=True)
    if job.status == 'failed':
        users = User.objects.filter(notify_backup_failed=True)
    jobevents = JobEvent.objects.filter(job_id=job_pk).order_by('counter')
    lines = []
    for event in jobevents:
        lines.append(event.stdout)
    return {'state': job.status, 'title': job.name, 'lines': lines, 'job': job}, users

@shared_task(bind=True, base=LogErrorsTask)
def cyborgbackup_notifier(type, *kwargs):
    logger.debug('CyBorgBackup Notifier')
    users = None
    if type in ('daily', 'weekly', 'monthly'):
        if type == 'daily':
            users = User.objects.filter(notify_backup_daily=True)
        if type == 'weekly':
            users = User.objects.filter(notify_backup_weekly=True)
        if type == 'monthly':
            users = User.objects.filter(notify_backup_monthly=True)
        if users and users.exists():
            report = build_report(type)
            report['columns'] = [
                {'title': 'Hostname', 'key': 'client', 'minsize': 10},
                {'title': 'Type', 'key': 'type', 'minsize': 6},
                {'title': 'Status', 'key': 'status', 'minsize': 8},
                {'title': 'Duration', 'key': 'duration', 'minsize': 10},
                {'title': 'Number of Files', 'key': 'numberFiles', 'minsize': 17},
                {'title': 'Original Size', 'key': 'original_size', 'minsize': 15},
                {'title': 'Deduplicated Size', 'key': 'deduplicated_size', 'minsize': 19}
            ]
            for user in users:
                send_email(report, type, user.email)
    else:
        if type == 'summary':
            report, users = _cyborgbackup_notifier_summary(kwargs[0])
        if type == 'after':
            report, users = _cyborgbackup_notifier_after(kwargs[0])
        for user in users:
            send_email(report, type, user.email)


@shared_task(bind=True, base=LogErrorsTask)
def prune_catalog():
    logger.debug('Prune deleted archive in Catalog')
    if not Job.objects.filter(status='running').exists():
        try:
            """Cleanup Jobs by using Django management command."""
            management.call_command("cleanup_jobs", verbosity=0)
            return "success"
        except Exception as e:
            print(e)


@shared_task(bind=True, base=LogErrorsTask)
def borg_restore_test():
    logger.debug('Borg Restore Test')
    try:
        setting = Setting.objects.get(key='cyborgbackup_auto_restore_test')
        restore_test = setting.value
    except Exception:
        restore_test = False
    if restore_test == 'True':
        logger.debug('Launch Random Job Restore')


@shared_task(bind=True, base=LogErrorsTask)
def borg_repository_integrity():
    logger.debug('Borg Repository Integrity')
    try:
        setting = Setting.objects.get(key='cyborgbackup_check_repository')
        check_repository = setting.value
    except Exception:
        check_repository = False
    if check_repository == 'True':
        logger.debug('Launch Borg Repository Integrity')


@shared_task(bind=True, base=LogErrorsTask)
def purge_old_stdout_files():
    nowtime = time.time()
    for f in os.listdir(settings.JOBOUTPUT_ROOT):
        if os.path.getctime(os.path.join(settings.JOBOUTPUT_ROOT, f)) < nowtime - settings.LOCAL_STDOUT_EXPIRE_TIME:
            os.unlink(os.path.join(settings.JOBOUTPUT_ROOT, f))
            logger.info(six.text_type("Removing {}").format(os.path.join(settings.JOBOUTPUT_ROOT, f)))

@shared_task(bind=True, base=LogErrorsTask)
def cyborgbackup_periodic_scheduler():
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
        if policy.repository.enabled and policy.schedule.enabled:
            policy.save()
            try:
                new_job = policy.create_job()
                new_job.launch_type = 'scheduled'
                new_job.save(update_fields=['launch_type'])
                can_start = new_job.signal_start()
            except Exception:
                logger.exception('Error spawning scheduled job.')
                continue
            if not can_start:
                new_job.status = 'failed'
                expl = "Scheduled job could not start because it was not in the right state or required manual credentials"
                new_job.job_explanation = expl
                new_job.save(update_fields=['status', 'job_explanation'])
                new_job.websocket_emit_status("failed")
            emit_channel_notification('schedules-changed', dict(id=policy.id, group_name="jobs"))
    state.save()


@shared_task(bind=True, queue='cyborgbackup', base=LogErrorsTask)
def handle_work_success(result, task_actual):
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
                    logger.warning("Unknown task type: {}".format(each_task['type']))
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
                    expl = 'Previous Task Failed: {"job_type": "%s", "job_name": "%s", "job_id": "%s"}' % \
                           (first_instance_type, first_instance.name, first_instance.id)
                    instance.job_explanation = expl
                instance.save()
                instance.websocket_emit_status("failed")

    if first_instance:
        from cyborgbackup.main.utils.tasks import run_job_complete
        run_job_complete.delay(first_instance.id)


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
        for sets in Setting.objects.filter(key__contains='ssh_key'):
            # If we were sent SSH credentials, decrypt them and send them
            # back (they will be written to a temporary file).
            private_data['credentials'][sets] = decrypt_field(sets, 'value') or ''

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

    def final_run_hook(self, instance, status, **kwargs):
        '''
        Hook for any steps to run after job/task is marked as complete.
        '''
        if instance.job_type == 'job':
            cyborgbackup_notifier.apply_async(args=('after', instance.pk))

    def build_passwords(self, job, **kwargs):
        '''
        Build a dictionary of passwords for SSH private key, SSH user, sudo/su.
        '''
        passwords = {}
        for setting in Setting.objects.filter(key__contains='ssh_key'):
            set_parsed = Setting.objects.get(key=setting.key.replace('ssh_key', 'ssh_password'))
            passwords['credential_{}'.format(setting.key)] = decrypt_field(set_parsed, 'value')
        return passwords

    def build_extra_vars_file(self, vars, **kwargs):
        handle, path = tempfile.mkstemp(dir=kwargs.get('private_data_dir', None))
        f = os.fdopen(handle, 'w')
        f.write("# CyBorgBackup Extra Vars #\n")
        f.write(json.dumps(vars))
        f.close()
        os.chmod(path, stat.S_IRUSR)
        return path

    def _build_args_for_check(self, job, **kwargs):
        agent_users = User.objects.filter(is_agent=True)
        env = self.build_env(job, **kwargs)
        if not agent_users.exists():
            agent_user = User()
            agent_user.email = 'cyborg@agent.local'
            agent_user.is_superuser = True
            agent_user.is_agent = True
            agent_user.save()
        else:
            agent_user = agent_users.first()
        if job.client_id and job.policy.policy_type != 'vm':
            try:
                setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
                client_user = setting_client_user.value
            except Exception:
                client_user = 'root'
            handle, path = tempfile.mkstemp()
            f = os.fdopen(handle, 'w')
            token, created = Token.objects.get_or_create(user=agent_user)
            base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'prepare_client')
            with open(base_script) as fs:
                script = fs.read()
            f.write(script)
            f.close()
            handle_env, path_env = tempfile.mkstemp()
            f = os.fdopen(handle_env, 'w')
            for key, var in env.items():
                f.write('export {}="{}"\n'.format(key, var))
            f.close()
            os.chmod(path, stat.S_IEXEC | stat.S_IREAD)
            args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += ['{}@{}'.format(client_user, job.client.hostname)]
            if job.client.port != 22:
                args += ['-p', job.client.port]
            args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
            args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += ['-o', 'PreferredAuthentications=publickey']
            if job.client.port != 22:
                args += ['-P' + job.client.port]
            args += [path, path_env, '{}@{}:{}/'.format(client_user, job.client.hostname, env['PRIVATE_DATA_DIR'])]
            args += ['&&', 'rm', '-f', path, path_env, '&&']
            args += ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            if job.client.port != 22:
                args += ['-p', job.client.port]
            args += ['{}@{}'.format(client_user, job.client.hostname)]
            args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            args += [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)),
                     '; exitcode=$?;',
                     'rm',
                     '-rf',
                     env['PRIVATE_DATA_DIR'],
                     '; exit $exitcode\"']
        if job.client_id and job.policy.policy_type == 'vm':
            try:
                setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
                client_user = setting_client_user.value
            except Exception:
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
            backupScriptPath = os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_backup_script))
            env.update({'CYBORGBACKUP_BACKUP_SCRIPT': backupScriptPath})
            handle_env, path_env = tempfile.mkstemp()
            f = os.fdopen(handle_env, 'w')
            for key, var in env.items():
                f.write('export {}="{}"\n'.format(key, var))
            f.close()
            os.chmod(path_prepare, stat.S_IEXEC | stat.S_IREAD)
            args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += ['{}@{}'.format(client_user, hypervisor_hostname)]
            args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
            args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += [path_prepare,
                     path_env,
                     path_backup_script,
                     '{}@{}:{}/'.format(client_user, hypervisor_hostname, env['PRIVATE_DATA_DIR'])]
            args += ['&&', 'rm', '-f', path_env, path_prepare, path_backup_script, '&&']
            args += ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += ['{}@{}'.format(client_user, hypervisor_hostname)]
            args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            args += [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_prepare)),
                     '; exitcode=$?;',
                     'rm',
                     '-rf',
                     env['PRIVATE_DATA_DIR'],
                     '; exit $exitcode\"']
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
            for key, var in env.items():
                if key == 'CYBORG_BORG_REPOSITORY' and ':' in var:
                    var = var.split(':')[1]
                f.write('export {}="{}"\n'.format(key, var))
            f.close()
            repository_conn = job.policy.repository.path.split(':')[0]
            args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += [repository_conn]
            args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
            args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += [path, path_env, '{}:{}/'.format(repository_conn, env['PRIVATE_DATA_DIR'])]
            args += ['&&', 'rm', '-f', path, path_env, '&&']
            args += ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += [repository_conn]
            args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            args += [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)),
                     '; exitcode=$?;',
                     'rm',
                     '-rf',
                     env['PRIVATE_DATA_DIR'],
                     '; exit $exitcode\"']
            args += ['rm', path, path_env]
        return args

    def _build_args_for_catalog(self, job , **kwargs):
        agent_users = User.objects.filter(is_agent=True)
        env = self.build_env(job, **kwargs)
        args = []
        if not agent_users.exists():
            agent_user = User()
            agent_user.email = 'cyborg@agent.local'
            agent_user.is_superuser = True
            agent_user.is_agent = True
            agent_user.save()
        else:
            agent_user = agent_users.first()
        if job.client_id:
            handle, path = tempfile.mkstemp()
            f = os.fdopen(handle, 'w')
            token, created = Token.objects.get_or_create(user=agent_user)
            if not job.master_job:
                raise Exception("Unable to get master job")
            job_events = JobEvent.objects.filter(
                job=job.master_job.pk,
                stdout__contains="Archive name: {}".format(
                    job.master_job.policy.policy_type
                )
            )
            archive_name = None
            if job_events.exists():
                job_stdout = job_events.first().stdout
                archive_name = job_stdout.split(':')[1].strip()
            if not archive_name:
                raise Exception("Latest backup haven't archive name in the report")
            job.master_job.archive_name = archive_name
            job.master_job.save()
            base_script = os.path.join(settings.SCRIPTS_DIR, 'cyborgbackup', 'fill_catalog')
            with open(base_script) as fs:
                script = fs.read()
            f.write(script)
            f.close()
            os.chmod(path, stat.S_IEXEC | stat.S_IREAD)
            handle_env, path_env = tempfile.mkstemp()
            f = os.fdopen(handle_env, 'w')
            for key, var in env.items():
                f.write('export {}="{}"\n'.format(key, var))
            f.close()
            repository_conn = job.policy.repository.path.split(':')[0]
            args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += [repository_conn]
            args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
            args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += [path, path_env, '{}:{}/'.format(repository_conn, env['PRIVATE_DATA_DIR'])]
            args += ['&&', 'rm', '-f', path, path_env, '&&']
            args += ['ssh', '-Ao', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
            args += [repository_conn]
            args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
            args += [os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path)),
                     '; exitcode=$?;',
                     'rm',
                     '-rf',
                     env['PRIVATE_DATA_DIR'],
                     '; exit $exitcode\"']
        return args

    def _build_args_for_prune(self, job, **kwargs):
        args = []
        if job.client_id:
            prefix = '{}-{}-'.format(job.policy.policy_type, job.client.hostname)
            args = ['borg', 'prune', '-v', '--list']
            args += ['--prefix', prefix]
            if job.policy.keep_hourly and job.policy.keep_hourly > 0:
                args += ['--keep-hourly={}'.format(job.policy.keep_hourly)]
            if job.policy.keep_daily and job.policy.keep_daily > 0:
                args += ['--keep-daily={}'.format(job.policy.keep_daily)]
            if job.policy.keep_weekly and job.policy.keep_weekly > 0:
                args += ['--keep-weekly={}'.format(job.policy.keep_weekly)]
            if job.policy.keep_monthly and job.policy.keep_monthly > 0:
                args += ['--keep-monthly={}'.format(job.policy.keep_monthly)]
            if job.policy.keep_yearly and job.policy.keep_yearly > 0:
                args += ['--keep-monthly={}'.format(job.policy.keep_yearly)]
        return args

    def _build_args_for_restore(self, job, **kwargs):
        logger.debug(job.extra_vars)
        logger.debug(job.extra_vars_dict)
        args = []
        if job.client_id:
            args = ['mkdir', '-p', job.extra_vars_dict['dest_folder'], '&&', 'cd', job.extra_vars_dict['dest_folder'],
                    '&&', 'borg', 'extract', '-v', '--list',
                    '{}::{}'.format(job.policy.repository.path, job.archive_name),
                    job.extra_vars_dict['item'], '-n' if job.extra_vars_dict['dry_run'] else '']
            logger.debug(' '.join(args))
        return args

    def _build_args_for_backup(self, job, **kwargs):
        env = self.build_env(job, **kwargs)
        (client, client_user, args) = self.build_borg_cmd(job)
        handle_env, path_env = tempfile.mkstemp()
        f = os.fdopen(handle_env, 'w')
        for key, var in env.items():
            f.write('export {}="{}"\n'.format(key, var))
        f.close()
        new_args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        new_args += ['{}@{}'.format(client_user, client)]
        if job.client.port != 22:
            new_args += ['-p', job.client.port]
        new_args += ['\"', 'mkdir', '-p', env['PRIVATE_DATA_DIR'], '\"', '&&']
        new_args += ['scp', '-qo', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        if job.client.port != 22:
            new_args += ['-P' + job.client.port]
        new_args += [path_env, '{}@{}:{}/'.format(client_user, client, env['PRIVATE_DATA_DIR'])]
        new_args += ['&&', 'rm', '-f', path_env, '&&']
        new_args += ['ssh', '-Ao', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
        new_args += ['{}@{}'.format(client_user, client)]
        if job.client.port != 22:
            args += ['-p', job.client.port]
        new_args += ['\". ', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        new_args += ['rm', os.path.join(env['PRIVATE_DATA_DIR'], os.path.basename(path_env)), '&&']
        new_args += [' '.join(args), '; exitcode=$?;', 'rm', '-rf', env['PRIVATE_DATA_DIR'], '; exit $exitcode\"']
        return new_args

    def build_args(self, job, **kwargs):
        '''
        Build command line argument list for running the task,
        optionally using ssh-agent for public/private key authentication.
        '''
        if job.job_type == 'check':
            return self._build_args_for_check(job, **kwargs)
        elif job.job_type == 'catalog':
            return self._build_args_for_catalog(job, **kwargs)
        elif job.job_type == 'prune':
            return self._build_args_for_prune(job, **kwargs)
        elif job.job_type == 'restore':
            return self._build_args_for_restore(job, **kwargs)
        else:
            return self._build_args_for_backup(job, **kwargs)

    def _build_borg_cmd_for_rootfs(self):
        path = '/'
        excluded_dirs = ['/media',
                        '/dev',
                        '/proc',
                        '/sys',
                        '/var/run',
                        '/run',
                        '/lost+found',
                        '/mnt',
                        '/var/lib/lxcfs',
                        '/tmp']
        return path, excluded_dirs

    def _build_borg_cmd_for_config(self):
        return '/etc', []

    def _build_borg_cmd_for_folders(self, job):
        obj_folders = json.loads(job.policy.extra_vars)
        path = ' '.join(obj_folders['folders'])
        return path, []

    def _build_borg_cmd_for_mail(self):
        path = '/var/lib/mail /var/mail'
        return path, []

    def _build_borg_cmd_for_piped_mysql(self, job):
        piped = 'mysqldump'
        database_specify = False
        if job.policy.extra_vars != '':
            mysql_json = json.loads(job.policy.extra_vars)
            if 'extended_mysql' in mysql_json and str(job.client.pk) in mysql_json['extended_mysql'].keys():
                vars = mysql_json['extended_mysql'][str(job.client.pk)]
                if 'user' in vars['credential'] and vars['credential']['user']:
                    piped += " -u{}".format(vars['credential']['user'])
                if 'password' in vars['credential'] and vars['credential']['password']:
                    piped += " -p{}".format(vars['credential']['password'])
                if 'databases' in vars and vars['databases']:
                    database_specify = True
                    piped += " --databases {}".format(' '.join(vars['databases']))
            else:
                if 'user' in mysql_json and mysql_json['user']:
                    piped += " -u{}".format(mysql_json['user'])
                if 'password' in mysql_json and mysql_json['password']:
                    piped += " -p{}".format(mysql_json['password'])
                if 'databases' in mysql_json and mysql_json['databases']:
                    database_specify = True
                    if isinstance(mysql_json['databases'], list):
                        piped += " --databases {}".format(' '.join(mysql_json['databases']))
                    else:
                        piped += " {}".format(mysql_json['databases'])

        if not database_specify:
            piped += " --all-databases"
        return piped

    def _build_borg_cmd_for_piped_postgresql(self, job):
        piped = ''
        database_specify = False
        if job.policy.extra_vars != '':
            pgsql_json = json.loads(job.policy.extra_vars)
            if 'extended_postgresql' in pgsql_json and str(job.client.pk) in pgsql_json['extended_postgresql'].keys():
                vars = pgsql_json['extended_postgresql'][str(job.client.pk)]
                if 'databases' in vars and vars['databases']:
                    database_specify = True
                    piped += " --databases {}".format(' '.join(vars['databases']))
            else:
                if 'database' in pgsql_json and pgsql_json['database']:
                    database_specify = True
                    piped += 'sudo -u postgres pg_dump {}'.format(pgsql_json['database'])
        if not database_specify:
            piped += 'sudo -u postgres pg_dumpall'
        return piped

    def _build_borg_cmd_for_piped_vm(self, job):
        provider = load_module_provider(job.policy.vmprovider)
        client = provider.get_client(job.client.hostname)
        client_hostname = client
        piped_list = ['/var/cache/cyborgbackup/borg_backup_vm']
        return ' '.join(piped_list)

    def _build_borg_cmd_for_piped_proxmox(self, job):
        proxmox_json = json.loads(job.policy.extra_vars)
        piped = 'vzdump --mode snapshot --stdout true '
        if 'extended_proxmox' in proxmox_json.keys() and str(job.client.pk) in proxmox_json['extended_proxmox'].keys():
            piped += ' '.join(str(x) for x in proxmox_json['extended_proxmox'][str(job.client.pk)])
        else:
            piped += '--all'
        return piped

    def _build_borg_cmd_for_piped(self, policy_type, job):
        piped = ''
        if policy_type == 'mysql':
            return self._build_borg_cmd_for_piped_mysql(job)
        elif policy_type == 'postgresql':
            return self._build_borg_cmd_for_piped_postgresql(job)
        elif policy_type == 'vm':
            return self._build_borg_cmd_for_piped_vm(job)
        elif policy_type == 'proxmox':
            return self._build_borg_cmd_for_piped_proxmox(job)
        else:
            command_specify = False
            if job.policy.extra_vars != '':
                piped_json = json.loads(job.policy.extra_vars)
                if 'command' in piped_json and piped_json['command']:
                    command_specify = True
                    piped += piped_json['command']
            if not command_specify:
                raise Exception('Command for piped backup not defined')
        return piped

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
# folders       Backup only specified directories
########
# rootfs
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX
#            && cd /tmp/sshfs_XXX && borg create /backup::archive . && fusermount -u /tmp/sshfs"
# folders
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /folder1 /folder2"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX
#            && cd /tmp/sshfs_XXX && borg create /backup::archive . && fusermount -u /tmp/sshfs"
# config
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /etc"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX
#            && cd /tmp/sshfs_XXX && borg create /backup::archive ./etc && fusermount -u /tmp/sshfs
# mail
#   push => ssh root@client "borg create borg@backupHost:/backup::archive /var/lib/mail"
#   pull => ssh borg@backupHost "sshfs root@client:/ /tmp/sshfs_XXX
#            && cd /tmp/sshfs_XXX && borg create /backup::archive ./var/lib/mail && fusermount -u /tmp/sshfs
# mysql
#   pull => ssh root@client "mysqldump | borg create borg@backupHost:/backup::archive -"
#   push => ssh borg@backupHost "ssh root@client "mysqldump" | borg create /backup::archive -"
#
# pgsql
#   pull => ssh root@client "pg_dumpall|pg_dump | borg create borg@backupHost:/backup::archive -"
#   push => ssh borg@backupHost "ssh root@client "pg_dumpall|pg_dump" | borg create /backup::archive -"
########

    def build_borg_cmd(self, job):
        policy_type = job.policy.policy_type
        job_date = job.created
        job_date_string = job_date.strftime("%Y-%m-%d_%H-%M")
        excluded_dirs = []
        args = []
        piped = ''
        client = job.client.hostname
        client_hostname = client
        try:
            setting_client_user = Setting.objects.get(key='cyborgbackup_backup_user')
            client_user = setting_client_user.value
        except Exception:
            client_user = 'root'
        if client_user != 'root':
            args = ['sudo', '-E']+args
        args += ['borg']
        args += ['create']
        repository_path = ''
        if not job.policy.mode_pull:
            repository_path = job.policy.repository.path
        args += ['--debug', '-v', '--stats']
        archive_client_name = job.client.hostname
        if policy_type == 'rootfs':
            path, excluded_dirs = self._build_borg_cmd_for_rootfs()
        if policy_type == 'config':
            path, excluded_dirs = self._build_borg_cmd_for_config()
        if policy_type == 'folders':
            path, excluded_dirs = self._build_borg_cmd_for_folders(job)
        if policy_type in ('rootfs', 'config', 'folders'):
            obj_folders = json.loads(job.policy.extra_vars)
            if 'exclude' in obj_folders.keys():
                for item in obj_folders['exclude']:
                    if item not in excluded_dirs:
                        excluded_dirs.append(item)
        if policy_type == 'mail':
            path, excluded_dirs = self._build_borg_cmd_for_mail()
        if policy_type in ('mysql', 'postgresql', 'piped', 'vm', 'proxmox'):
            path = '-'
            piped = self._build_borg_cmd_for_piped(policy_type, job)
            if not job.policy.mode_pull:
                args = [piped, '|']+args

        args += ['{}::{}-{}-{}'.format(repository_path, policy_type, archive_client_name, job_date_string)]

        if job.policy.mode_pull and policy_type in ('rootfs', 'config', 'mail'):
            path = '.'+path
        args += [path]

        if len(excluded_dirs) > 0:
            keyword = '--exclude '
            if job.policy.mode_pull:
                keyword += '.'
            args += (keyword + (' '+keyword).join(excluded_dirs)).split(' ')

        if job.policy.mode_pull:
            (client_uri, repository_path) = job.policy.repository.path.split(':')
            client = client_uri.split('@')[1]
            client_user = client_uri.split('@')[0]
            if policy_type in ('rootfs', 'config', 'mail', 'folders'):
                sshfs_directory = '/tmp/sshfs_{}_{}'.format(client_hostname, job_date_string)
                pull_cmd = ['mkdir', '-p', sshfs_directory]
                pull_cmd += ['&&', 'sshfs', 'root@{}:{}'.format(client_hostname, path[1::]), sshfs_directory]
                pull_cmd += ['&&', 'cd', sshfs_directory]
                pull_cmd += ['&&']+args
                args = pull_cmd
            if policy_type in ('mysql', 'postgresql', 'piped', 'vm'):
                pull_cmd = ['ssh', '{}@{}'.format(client_user, client_hostname)]
                if client_user != 'root':
                    piped = 'sudo -E '+piped
                pull_cmd += ["'"+piped+"'|"+' '.join(args)]
                args = pull_cmd

        return client, client_user, args

    def build_safe_args(self, job, **kwargs):
        return self.build_args(job, display=True, **kwargs)

    def build_env(self, job, **kwargs):
        env = super(RunJob, self).build_env(job, **kwargs)
        agent_users = User.objects.filter(is_agent=True)
        if not agent_users.exists():
            agent_user = User()
            agent_user.email = 'cyborg@agent.local'
            agent_user.is_superuser = True
            agent_user.is_agent = True
            agent_user.save()
        else:
            agent_user = agent_users.first()
            token, created = Token.objects.get_or_create(user=agent_user)
        if token and (job.job_type == 'check' or job.job_type == 'catalog'):
            env['CYBORG_AGENT_TOKEN'] = str(token)
            try:
                setting = Setting.objects.get(key='cyborgbackup_url')
                base_url = setting.value
            except Exception:
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
                job_events = JobEvent.objects.filter(
                    job=job.master_job.pk,
                    stdout__contains="Archive name: {}".format(
                        job.master_job.policy.policy_type
                    )
                )
                archive_name = None
                if job_events.exists():
                    job_stdout = job_events.first().stdout
                    archive_name = job_stdout.split(':')[1].strip()
                if archive_name:
                    env['CYBORG_JOB_ARCHIVE_NAME'] = archive_name
                else:
                    raise Exception('Unable to get archive from backup. Backup job may failed.')
                env['CYBORG_JOB_ID'] = str(job.master_job.pk)
        else:
            env['BORG_PASSPHRASE'] = job.policy.repository.repository_key
            env['BORG_REPO'] = job.policy.repository.path
        env['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'
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
            d[re.compile(r'Enter passphrase for .*'+k+r':\s*?$', re.M)] = k
            d[re.compile(r'Enter passphrase for .*'+k, re.M)] = k
        d[re.compile(r'Bad passphrase, try again for .*:\s*?$', re.M)] = ''
        return d


Celery('cyborgbackup').register_task(RunJob())
