import logging

from django.db import models

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.models.base import PrimordialModel
from cyborgbackup.main.utils.common import copy_model_by_class, copy_m2m_relationships

logger = logging.getLogger('cyborgbackup.models.Repository')

__all__ = ['Repository']


class Repository(PrimordialModel):
    name = models.CharField(
        max_length=1024,
    )

    path = models.CharField(
        max_length=1024,
    )

    enabled = models.BooleanField(
        default=True
    )

    repository_key = models.CharField(
        max_length=1024,
    )

    ready = models.BooleanField(
        default=False
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

    latest_prepare = models.DateTimeField(
        null=True,
        default=None,
        editable=False,
    )

    def get_absolute_url(self, request=None):
        return reverse('api:repository_detail', kwargs={'pk': self.pk}, request=request)

    def get_ui_url(self):
        return "/#/repositories/{}".format(self.pk)

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

    def create_prepare_repository(self, **kwargs):
        """
        Create a new prepare job for this repository.
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
        job.repository_id = self.pk
        job.name = "Prepare Repository {}".format(self.name)
        job.description = "Repository {} Borg Preparation".format(self.name)
        job.save()

        copy_m2m_relationships(self, job, (), kwargs=kwargs)

        return job
