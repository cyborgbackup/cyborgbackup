import logging

import pymongo
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from pkg_resources import parse_version

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.base import PrimordialModel
from cyborgbackup.main.utils.common import copy_model_by_class, copy_m2m_relationships

logger = logging.getLogger('cyborgbackup.models.client')

__all__ = ['Client']


class Client(PrimordialModel):
    hostname = models.CharField(
        max_length=1024
    )

    enabled = models.BooleanField(
        default=True
    )

    ip = models.TextField(
        blank=True,
        default=''
    )

    version = models.CharField(
        max_length=50,
        blank=True,
        default=''
    )

    port = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        blank=True,
        default=22
    )

    ready = models.BooleanField(
        default=False
    )

    mark_as_to_update = models.BooleanField(
        default=False
    )

    hypervisor_ready = models.BooleanField(
        default=False
    )

    hypervisor_name = models.CharField(
        max_length=1024,
        blank=True,
        default=''
    )

    latest_prepare = models.DateTimeField(
        null=True,
        default=None,
        editable=False
    )

    bandwidth_limit = models.PositiveIntegerField(
        null=True,
        default=None,
        blank=True
    )

    behind_firewall = models.BooleanField(
        default=False
    )

    def get_absolute_url(self, request=None):
        return reverse('api:client_detail', kwargs={'pk': self.pk}, request=request)

    def get_ui_url(self):
        return "/#/clients/{}".format(self.pk)

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

    def create_prepare_client(self, **kwargs):
        """
        Create a new prepare job for this client.
        """
        eager_fields = kwargs.pop('_eager_fields', None)

        job_class = self._get_job_class()
        fields = ('extra_vars', 'job_type')
        unallowed_fields = set(kwargs.keys()) - set(fields)
        if unallowed_fields:
            logger.warning('Fields {} are not allowed as overrides.'.format(unallowed_fields))
            map(kwargs.pop, unallowed_fields)

        job = copy_model_by_class(self, job_class, fields, kwargs)

        if eager_fields:
            for fd, val in eager_fields.items():
                setattr(job, fd, val)

        # Set the job back-link on the job
        job.client_id = self.pk
        job.name = "Prepare Client {}".format(self.hostname)
        job.description = "Client {} Borg Preparation".format(self.hostname)
        job.save()

        copy_m2m_relationships(self, job, (), kwargs=kwargs)

        return job

    def create_prepare_hypervisor(self, **kwargs):
        """
        Create a new prepare job for the hypervisor of this client.
        """
        eager_fields = kwargs.pop('_eager_fields', None)

        job_class = self._get_job_class()
        fields = ('extra_vars', 'job_type')
        unallowed_fields = set(kwargs.keys()) - set(fields)
        if unallowed_fields:
            logger.warning('Fields {} are not allowed as overrides.'.format(unallowed_fields))
            map(kwargs.pop, unallowed_fields)

        job = copy_model_by_class(self, job_class, fields, kwargs)

        if eager_fields:
            for fd, val in eager_fields.items():
                setattr(job, fd, val)

        # Set the job back-link on the job
        job.client_id = self.pk
        job.name = "Prepare Hypervisor of {}".format(self.hostname)
        job.description = "Hypervisor of {} Borg Preparation".format(self.hostname)
        job.save()

        copy_m2m_relationships(self, job, (), kwargs=kwargs)

        return job

    def can_be_updated(self):
        db = pymongo.MongoClient(settings.MONGODB_URL).local
        latest_versions = db.versions.find_one({}, sort=[("check_date", pymongo.DESCENDING)])
        if not latest_versions:
            return False
        return parse_version(self.version) < parse_version(latest_versions['version'])
