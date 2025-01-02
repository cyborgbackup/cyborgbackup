import functools
import logging
import os
import shutil

from cyborgbackup.main.models import User, Policy, Job, JobEvent
from cyborgbackup.main.models.settings import Setting

logger = logging.getLogger('cyborgbackup.main.tasks.helpers')

units = {"B": 1, "kB": 10 ** 3, "MB": 10 ** 6, "GB": 10 ** 9, "TB": 10 ** 12}


def parseSize(size):
    number, unit = [string.strip() for string in size.split()]
    return int(float(number) * units[unit])


def _cyborgbackup_notifier_summary(policy_pk):
    logger.debug('Summary')
    users = _get_users_to_notify()
    policy = Policy.objects.get(pk=policy_pk)
    catalog_enabled = _is_catalog_enabled()
    auto_prune_enabled = _is_auto_prune_enabled()
    report = _build_report(policy, catalog_enabled, auto_prune_enabled)
    return report, users


def _get_users_to_notify():
    return User.objects.filter(notify_backup_summary=True)


def _is_catalog_enabled():
    try:
        setting = Setting.objects.get(key='cyborgbackup_catalog_enabled')
        return setting.value == 'True'
    except Exception:
        return True


def _is_auto_prune_enabled():
    try:
        setting = Setting.objects.get(key='cyborgbackup_auto_prune')
        return setting.value == 'True'
    except Exception:
        return True


def _build_report(policy, catalog_enabled, auto_prune_enabled):
    report = {'lines': []}
    order = 1
    report['lines'].append(_build_policy_line(policy, order))
    order += 1
    if not policy.repository.ready:
        report['lines'].append(_build_repository_line(policy, order))
    have_prune_info = _has_prune_info(policy)
    for client in policy.clients.all():
        if not client.ready:
            order += 1
            report['lines'].append(_build_client_line(client, order))
        order += 1
        report['lines'].append(_build_backup_job_line(policy, client, order))
        if catalog_enabled:
            order += 1
            report['lines'].append(_build_catalog_job_line(policy, client, order))
        if auto_prune_enabled and have_prune_info:
            order += 1
            report['lines'].append(_build_prune_job_line(policy, client, order))
    report['columns'] = _build_report_columns()
    return report


def _build_policy_line(policy, order):
    return {
        'order': str(order),
        'title': 'Policy {}'.format(policy.name),
        'type': 'policy'
    }


def _build_repository_line(policy, order):
    return {
        'order': str(order),
        'title': "Prepare Repository {}".format(policy.repository.name),
        'type': "repository"
    }


def _has_prune_info(policy):
    return (policy.keep_hourly or policy.keep_daily or policy.keep_weekly or policy.keep_monthly or policy.keep_yearly)


def _build_client_line(client, order):
    return {
        'order': str(order),
        'title': "Prepare Client {}".format(client.hostname),
        'type': "client"
    }


def _build_backup_job_line(policy, client, order):
    return {
        'order': str(order),
        'title': "Backup Job {} {}".format(policy.name, client.hostname),
        'type': policy.policy_type
    }


def _build_catalog_job_line(policy, client, order):
    return {
        'order': str(order),
        'title': "Catalog Job {} {}".format(policy.name, client.hostname),
        'type': "catalog"
    }


def _build_prune_job_line(policy, client, order):
    return {
        'order': str(order),
        'title': "Prune Job {} {}".format(policy.name, client.hostname),
        'type': "prune"
    }


def _build_report_columns():
    return [
        {'title': 'Order', 'key': 'order', 'minsize': 7},
        {'title': 'Title', 'key': 'title', 'minsize': 7},
        {'title': 'Type', 'key': 'type', 'minsize': 6}
    ]


# def _cyborgbackup_notifier_summary(policy_pk):
#     logger.debug('Summary')
#     users = User.objects.filter(notify_backup_summary=True)
#     policy = Policy.objects.get(pk=policy_pk)
#
#     try:
#         setting = Setting.objects.get(key='cyborgbackup_catalog_enabled')
#         if setting.value == 'True':
#             catalog_enabled = True
#         else:
#             catalog_enabled = False
#     except Exception:
#         catalog_enabled = True
#
#     try:
#         setting = Setting.objects.get(key='cyborgbackup_auto_prune')
#         if setting.value == 'True':
#             auto_prune_enabled = True
#         else:
#             auto_prune_enabled = False
#     except Exception:
#         auto_prune_enabled = True
#     report = {'lines': []}
#     order = 1
#     report['lines'].append({
#         'order': str(order),
#         'title': 'Policy {}'.format(policy.name),
#         'type': 'policy'
#     })
#     order += 1
#     if not policy.repository.ready:
#         report['lines'].append({
#             'order': str(order),
#             'title': "Prepare Repository {}".format(policy.repository.name),
#             'type': "repository"
#         })
#     have_prune_info = (policy.keep_hourly or policy.keep_daily or policy.keep_weekly or policy.keep_monthly or policy.keep_yearly)
#     for client in policy.clients.all():
#         if not client.ready:
#             order += 1
#             report['lines'].append({
#                 'order': str(order),
#                 'title': "Prepare Client {}".format(client.hostname),
#                 'type': "client"
#             })
#         order += 1
#         report['lines'].append({
#             'order': str(order),
#             'title': "Backup Job {} {}".format(policy.name, client.hostname),
#             'type': policy.policy_type
#         })
#         if catalog_enabled:
#             order += 1
#             report['lines'].append({
#                 'order': str(order),
#                 'title': "Catalog Job {} {}".format(policy.name, client.hostname),
#                 'type': "catalog"
#             })
#         if auto_prune_enabled and have_prune_info:
#             order += 1
#             report['lines'].append({
#                 'order': str(order),
#                 'title': "Prune Job {} {}".format(policy.name, client.hostname),
#                 'type': "prune"
#             })
#     report['columns'] = [
#         {'title': 'Order', 'key': 'order', 'minsize': 7},
#         {'title': 'Title', 'key': 'title', 'minsize': 7},
#         {'title': 'Type', 'key': 'type', 'minsize': 6}
#     ]
#     return report, users


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
                    logger.exception(str("Failed to remove tmp file: {}").format(p))
            self.cleanup_paths = []

    return _wrapped


def humanbytes(B):
    """  Return the given bytes as a human friendly KB, MB, GB, or TB string"""
    B = float(B)
    KB = float(1024)
    MB = float(KB ** 2)  # 1,048,576
    GB = float(KB ** 3)  # 1,073,741,824
    TB = float(KB ** 4)  # 1,099,511,627,776

    if B < KB:
        return '{0} {1}'.format(B, 'Bytes' if 0 == B > 1 else 'Byte')
    elif KB <= B < MB:
        return '{0:.2f} KB'.format(B / KB)
    elif MB <= B < GB:
        return '{0:.2f} MB'.format(B / MB)
    elif GB <= B < TB:
        return '{0:.2f} GB'.format(B / GB)
    elif TB <= B:
        return '{0:.2f} TB'.format(B / TB)
