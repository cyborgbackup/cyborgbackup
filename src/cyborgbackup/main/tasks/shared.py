import datetime
import logging
import os
import re
from datetime import time
from random import random

import pymongo
import requests
from celery import shared_task
from django.conf import settings
from django.core import management
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now

from cyborgbackup.main.consumers import emit_channel_notification
from cyborgbackup.main.models import Job, Policy, User, JobEvent, Repository
from cyborgbackup.main.models.schedules import CyborgBackupScheduleState
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.tasks.basetask import LogErrorsTask
from cyborgbackup.main.tasks.helpers import _cyborgbackup_notifier_summary, parseSize, _cyborgbackup_notifier_after
from cyborgbackup.main.tasks.reports import send_email, build_report

logger = logging.getLogger('cyborgbackup.main.tasks.shared')


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
                prg = re.compile(
                    r"This archive:\s{1,40}([0-9.]{1,10}\s.B)\s{1,40}([0-9.]{1,10}\s.B)\s{1,40}([0-9.]{1,10}\s.B)\s{0,40}")
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
                events = JobEvent.objects.filter(job_id=last_running_job.pk, stdout__contains='All archives:').order_by(
                    '-counter')
                for event in events:
                    prg = re.compile(
                        r"All archives:\s{1,40}([0-9.]{1,10}\s.B)\s{1,40}([0-9.]{1,10}\s.B)\s{1,40}([0-9.]{1,10}\s.B)\s{0,40}")
                    m = prg.match(event.stdout)
                    if m:
                        repo.original_size = parseSize(m.group(1))
                        repo.compressed_size = parseSize(m.group(2))
                        repo.deduplicated_size = parseSize(m.group(3))
                        repo.save()
                        break


@shared_task(bind=True, base=LogErrorsTask)
def check_borg_new_version(self):
    logger.debug('Check New Release of Borg binary')
    r = requests.get('https://api.github.com/repos/borgbackup/borg/releases/latest')
    data = r.json()
    latest_version = data['tag_name']
    db = pymongo.MongoClient(settings.MONGODB_URL).local
    db.versions.replace_one({'version': latest_version}, {
        'version': latest_version,
        'check_date': datetime.datetime.now()
    }, upsert=True)


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


@shared_task(bind=True, base=LogErrorsTask)
def cyborgbackup_notifier(self, report_type, *kwargs):
    logger.debug('CyBorgBackup Notifier')
    users = None
    report = None
    if report_type in ('daily', 'weekly', 'monthly'):
        if report_type == 'daily':
            users = User.objects.filter(notify_backup_daily=True)
        if report_type == 'weekly':
            users = User.objects.filter(notify_backup_weekly=True)
        if report_type == 'monthly':
            users = User.objects.filter(notify_backup_monthly=True)
        if users and users.exists():
            report = build_report(report_type)
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
                send_email(report, report_type, user.email)
    else:
        if report_type == 'summary':
            report, users = _cyborgbackup_notifier_summary(kwargs[0])
        if report_type == 'after':
            report, users = _cyborgbackup_notifier_after(kwargs[0])
        for user in users:
            send_email(report, report_type, user.email)


@shared_task(bind=True, base=LogErrorsTask)
def prune_catalog(self):
    logger.debug('Prune deleted archive in Catalog')
    if not Job.objects.filter(status='running').exists():
        try:
            """Cleanup Jobs by using Django management command."""
            management.call_command("cleanup_jobs", verbosity=0)
            return "success"
        except Exception as e:
            print(e)


@shared_task(bind=True, base=LogErrorsTask)
def borg_restore_test(self):
    logger.debug('Borg Restore Test')
    try:
        setting = Setting.objects.get(key='cyborgbackup_auto_restore_test')
        restore_test = setting.value
    except Exception:
        restore_test = False
    if restore_test == 'True':
        logger.debug('Launch Random Job Restore')


@shared_task(bind=True, base=LogErrorsTask)
def borg_repository_integrity(self):
    logger.debug('Borg Repository Integrity')
    try:
        setting = Setting.objects.get(key='cyborgbackup_check_repository')
        check_repository = setting.value
    except Exception:
        check_repository = False
    if check_repository == 'True':
        logger.debug('Launch Borg Repository Integrity')


@shared_task(bind=True, base=LogErrorsTask)
def purge_old_stdout_files(self):
    nowtime = time.time()
    for f in os.listdir(settings.JOBOUTPUT_ROOT):
        if os.path.getctime(os.path.join(settings.JOBOUTPUT_ROOT, f)) < nowtime - settings.LOCAL_STDOUT_EXPIRE_TIME:
            os.unlink(os.path.join(settings.JOBOUTPUT_ROOT, f))
            logger.info(str("Removing {}").format(os.path.join(settings.JOBOUTPUT_ROOT, f)))


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
                expl = ("Scheduled job could not start because it was not in the right state or required manual "
                        "credentials")
                new_job.job_explanation = expl
                new_job.save(update_fields=['status', 'job_explanation'])
                new_job.websocket_emit_status("failed")
            emit_channel_notification('schedules-changed', dict(id=policy.id, group_name="jobs"))
    state.save()


@shared_task(bind=True, base=LogErrorsTask)
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


@shared_task(base=LogErrorsTask)
def handle_work_error(self, task_id, *args, **kwargs):
    subtasks: list | None = kwargs.get('subtasks', None)
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
