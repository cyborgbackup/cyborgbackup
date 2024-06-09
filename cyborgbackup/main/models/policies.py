import logging

import pytz
import tzcron
from dateutil.tz import datetime_exists
from django.db import models
from django.db.models.query import QuerySet
from django.utils.translation import gettext_lazy as _

from cyborgbackup.api.versioning import reverse
from cyborgbackup.celery import app
from cyborgbackup.main.consumers import emit_channel_notification
from cyborgbackup.main.models.base import PrimordialModel
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.utils.common import copy_model_by_class

logger = logging.getLogger('cyborgbackup.models.policy')

__all__ = ['Policy']


class PolicyFilterMethods(object):

    def enabled(self, enabled=True):
        return self.filter(enabled=enabled)

    def before(self, dt):
        return self.filter(next_run__lt=dt)

    def after(self, dt):
        return self.filter(next_run__gt=dt)

    def between(self, begin, end):
        return self.after(begin).before(end)


class PolicyQuerySet(PolicyFilterMethods, QuerySet):
    pass


class PolicyManager(PolicyFilterMethods, models.Manager):
    use_for_related_objects = True

    def get_queryset(self):
        return PolicyQuerySet(self.model, using=self._db)


class Policy(PrimordialModel):
    POLICY_TYPE_CHOICES = [
        ('rootfs', 'Root FileSystem'),  # Backup all / filesystem
        ('vm', 'Virtual Machine'),  # Backup Virtual Machine disk using snapshot
        ('mysql', 'MySQL'),  # Backup MySQL Database
        ('postgresql', 'PostgreSQL'),  # Backup PostgreSQL
        ('piped', 'Piped Backup'),  # Backup using pipe program
        ('config', 'Only /etc'),  # Backup only /etc
        ('mail', 'Only mail directory'),  # Backup only mail directory
        ('folders', 'Specified folders'),  # Backup only specified folders
        ('proxmox', 'Proxmox')  # Backup only specified folders
    ]

    objects = PolicyManager()

    name = models.CharField(
        max_length=1024,
    )

    schedule = models.ForeignKey(
        'Schedule',
        related_name='policies',
        on_delete=models.CASCADE,
        null=False,
        editable=True,
    )

    repository = models.ForeignKey(
        'Repository',
        related_name='policies',
        on_delete=models.CASCADE,
        null=False,
        editable=True,
    )

    clients = models.ManyToManyField("client", blank=True)

    policy_type = models.CharField(
        max_length=20,
        choices=POLICY_TYPE_CHOICES,
        default='rootfs',
    )

    enabled = models.BooleanField(
        default=True
    )

    extra_vars = models.TextField(
        blank=True,
        default='',
    )

    mode_pull = models.BooleanField(
        default=False
    )

    keep_hourly = models.IntegerField(
        null=True,
        default=None,
        blank=True
    )

    keep_daily = models.IntegerField(
        null=True,
        default=None,
        blank=True
    )

    keep_weekly = models.IntegerField(
        null=True,
        default=None,
        blank=True
    )

    keep_monthly = models.IntegerField(
        null=True,
        default=None,
        blank=True
    )

    keep_yearly = models.IntegerField(
        null=True,
        default=None,
        blank=True
    )

    vmprovider = models.CharField(
        max_length=128,
        default='',
        blank=True
    )

    next_run = models.DateTimeField(
        null=True,
        default=None,
        editable=False,
        help_text=_("The next time that the scheduled action will run.")
    )

    posthook = models.CharField(
        max_length=128,
        default='',
        blank=True
    )

    prehook = models.CharField(
        max_length=128,
        default='',
        blank=True
    )

    def get_absolute_url(self, request=None):
        return reverse('api:policy_detail', kwargs={'pk': self.pk}, request=request)

    def get_ui_url(self):
        return "/#/policies/{}".format(self.pk)

    def update_computed_fields(self):
        future_rs = tzcron.Schedule(self.schedule.crontab, pytz.utc)
        next_run_actual = next(future_rs)

        if next_run_actual is not None:
            if not datetime_exists(next_run_actual):
                # skip imaginary dates, like 2:30 on DST boundaries
                next_run_actual = next(future_rs)
            next_run_actual = next_run_actual.astimezone(pytz.utc)

        self.next_run = next_run_actual
        emit_channel_notification('schedules-changed', dict(id=self.id, group_name='schedules'))

    def save(self, *args, **kwargs):
        self.update_computed_fields()
        # If update_fields has been specified, add our field names to it,
        # if it hasn't been specified, then we're just doing a normal save.
        super(Policy, self).save(*args, **kwargs)

    @classmethod
    def get_cache_key(cls, key):
        return key

    @classmethod
    def get_cache_id_key(cls, key):
        return '{}_ID'.format(key)

    @classmethod
    def _get_job_class(cls):
        from cyborgbackup.main.models.jobs import Job
        return Job

    def create_job(self, **kwargs):
        """
        Create a new job based on this policy.
        """

        job_class = self._get_job_class()
        fields = ('extra_vars', 'job_type')
        unallowed_fields = set(kwargs.keys()) - set(fields)
        if unallowed_fields:
            logger.warning('Fields {} are not allowed as overrides.'.format(unallowed_fields))
            map(kwargs.pop, unallowed_fields)

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

        app.send_task('cyborgbackup.main.tasks.cyborgbackup_notifier', args=('summary', self.pk))

        have_prune_info = (self.keep_hourly or self.keep_daily
                           or self.keep_weekly or self.keep_monthly or self.keep_yearly)

        jobs = []
        previous_job = None
        catalog_job = None
        prune_job = None
        for client in self.clients.filter(enabled=True):
            job = copy_model_by_class(self, job_class, fields, kwargs)
            job.policy_id = self.pk
            job.repository_id = self.repository.pk
            job.client_id = client.pk
            job.status = 'pending'
            job.name = "Backup Job {} {}".format(self.name, client.hostname)
            job.description = "Backup Job for Policy {} of client {}".format(self.name, client.hostname)
            job.save()
            if catalog_enabled:
                catalog_job = copy_model_by_class(self, job_class, fields, kwargs)
                catalog_job.policy_id = self.pk
                catalog_job.repository_id = self.repository.pk
                catalog_job.client_id = client.pk
                catalog_job.status = 'waiting'
                catalog_job.job_type = 'catalog'
                catalog_job.name = "Catalog Job {} {}".format(self.name, client.hostname)
                catalog_job.description = "Catalog Job for Policy {} of client {}".format(self.name, client.hostname)
                catalog_job.master_job = job
                catalog_job.save()
                job.dependent_jobs = catalog_job
                job.save()
            if auto_prune_enabled:
                if have_prune_info:
                    prune_job = copy_model_by_class(self, job_class, fields, kwargs)
                    prune_job.policy_id = self.pk
                    prune_job.repository_id = self.repository.pk
                    prune_job.client_id = client.pk
                    prune_job.status = 'waiting'
                    prune_job.job_type = 'prune'
                    prune_job.name = "Prune Job {} {}".format(self.name, client.hostname)
                    prune_job.description = "Prune Job for Policy {} of client {}".format(self.name, client.hostname)
                    if catalog_enabled:
                        prune_job.master_job = catalog_job
                    else:
                        prune_job.master_job = job
                    prune_job.save()
                    if catalog_enabled:
                        catalog_job.dependent_jobs = prune_job
                        catalog_job.save()
                    else:
                        job.dependent_jobs = prune_job
                        job.save()

            if auto_prune_enabled:
                if have_prune_info:
                    if previous_job:
                        previous_job.dependent_jobs = prune_job
                        previous_job.save()
                    previous_job = prune_job
            elif catalog_enabled:
                if previous_job:
                    previous_job.dependent_jobs = catalog_job
                    previous_job.save()
                previous_job = catalog_job
            else:
                if previous_job:
                    previous_job.dependent_jobs = job
                    previous_job.save()
                previous_job = job

            jobs.append(job)
        if len(jobs) > 0:
            jobs[0].status = 'new'
            jobs[0].save()
            return jobs[0]
        else:
            return None

    def create_restore_job(self, source_job, **kwargs):
        job_class = self._get_job_class()
        fields = ('extra_vars',)
        unallowed_fields = set(kwargs.keys()) - set(fields)
        if unallowed_fields:
            logger.warning('Fields {} are not allowed as overrides.'.format(unallowed_fields))
            map(kwargs.pop, unallowed_fields)

        job = copy_model_by_class(self, job_class, fields, kwargs)
        job.launch_type = 'manual'
        job.job_type = 'restore'
        job.policy_id = self.pk
        job.client_id = source_job.client.pk
        job.archive_name = source_job.archive_name
        job.status = 'new'
        job.name = "Restore Job {} {}".format(self.name, source_job.client.hostname)
        job.description = "Restore Job for Policy {} of client {}".format(self.name, source_job.client.hostname)
        job.save()
        return job
