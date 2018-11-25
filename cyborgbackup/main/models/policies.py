import datetime
import logging

from django.conf import settings
from django.db import models
from django.db.models.query import QuerySet
from django.utils.dateparse import parse_datetime
from django.utils.timezone import utc
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import force_text

import tzcron
import pytz
from dateutil.tz import datetime_exists

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.fields import JSONField
from cyborgbackup.main.utils.common import could_be_script, copy_model_by_class, copy_m2m_relationships
from cyborgbackup.main.models.base import CreatedModifiedModel, PrimordialModel
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.consumers import emit_channel_notification

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
        ('rootfs', 'Root FileSystem'),      # Backup all / filesystem
        ('vm', 'Virtual Machine'),          # Backup Virtual Machine disk using snapshot
        ('mysql', 'MySQL'),                 # Backup MySQL Database
        ('postgresql', 'PostgreSQL'),       # Backup PostgreSQL
        ('piped', 'Piped Backup'),          # Backup using pipe program
        ('config', 'Only /etc'),            # Backup only /etc
        ('mail', 'Only mail directory'),    # Backup only mail directory
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

    clients = models.ManyToManyField("client", blank=False)

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
        #try:
        #    self.dtstart = future_rs[0].astimezone(pytz.utc)
        #except IndexError:
        #    self.dtstart = None
        #self.dtend = None
        #if 'until' in self.rrule.lower() or 'count' in self.rrule.lower():
        #    try:
        #        self.dtend = future_rs[-1].astimezone(pytz.utc)
        #    except IndexError:
        #        self.dtend = None
        emit_channel_notification('schedules-changed', dict(id=self.id, group_name='schedules'))

    def save(self, *args, **kwargs):
        #encrypted = settings_registry.is_setting_encrypted(self.key)
        encrypted = False
        self.update_computed_fields()
        # If update_fields has been specified, add our field names to it,
        # if it hasn't been specified, then we're just doing a normal save.
        update_fields = kwargs.get('update_fields', [])
        super(Policy, self).save(*args, **kwargs)

    @classmethod
    def get_cache_key(self, key):
        return key

    @classmethod
    def get_cache_id_key(self, key):
        return '{}_ID'.format(key)

    @classmethod
    def _get_job_class(cls):
        from cyborgbackup.main.models.jobs import Job
        return Job

    def create_job(self, **kwargs):
        '''
        Create a new job based on this policy.
        '''
        #eager_fields = kwargs.pop('_eager_fields', None)

        job_class = self._get_job_class()
        #fields = self._get_job_field_names()
        fields = ('extra_vars', 'job_type')
        unallowed_fields = set(kwargs.keys()) - set(fields)
        if unallowed_fields:
            logger.warn('Fields {} are not allowed as overrides.'.format(unallowed_fields))
            map(kwargs.pop, unallowed_fields)

        #from cyborgbackup.main.signals import disable_activity_stream
        try:
            setting = Setting.objects.get(key='cyborgbackup_catalog_enabled')
            if setting.value == 'True':
                catalog_enabled=True
            else:
                catalog_enabled=False
        except Exception as e:
            catalog_enabled=True

        try:
            setting = Setting.objects.get(key='cyborgbackup_auto_prune')
            if setting.value == 'True':
                auto_prune_enabled=True
            else:
                auto_prune_enabled=False
        except Exception as e:
            auto_prune_enabled=True

        jobs = []
        previous_job = None
        for client in self.clients.all():
            job = copy_model_by_class(self, job_class, fields, kwargs)
            job.policy_id = self.pk
            job.client_id = client.pk
            job.status = 'waiting'
            job.name = "Backup Job {} {}".format(self.name, client.hostname)
            job.description = "Backup Job for Policy {} of client {}".format(self.name, client.hostname)
            job.save()
            if catalog_enabled:
                catalog_job = copy_model_by_class(self, job_class, fields, kwargs)
                catalog_job.policy_id = self.pk
                catalog_job.client_id = client.pk
                catalog_job.status = 'waiting'
                catalog_job.job_type = 'catalog'
                catalog_job.name = "Catalog Job {} {}".format(self.name, client.hostname)
                catalog_job.description = "Catalog Job for Policy {} of client {}".format(self.name, client.hostname)
                catalog_job.save()
                job.dependent_jobs = catalog_job
                job.save()
            if auto_prune_enabled:
                prune_job = copy_model_by_class(self, job_class, fields, kwargs)
                prune_job.policy_id = self.pk
                prune_job.client_id = client.pk
                prune_job.status = 'waiting'
                prune_job.job_type = 'prune'
                prune_job.name = "Prune Job {} {}".format(self.name, client.hostname)
                prune_job.description = "Prune Job for Policy {} of client {}".format(self.name, client.hostname)
                prune_job.save()
                if catalog_enabled:
                    catalog_job.dependent_jobs = prune_job
                    catalog_job.save()
                else:
                    job.dependent_jobs = prune_job
                    job.save()

            if auto_prune_enabled:
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

            #fields=()
            #with disable_activity_stream():
            #    copy_m2m_relationships(self, job, fields, kwargs=kwargs)
            jobs.append(job)
        #job.create_config_from_prompts(kwargs)
        jobs[0].status = 'new'
        jobs[0].save()
        return jobs[0]
