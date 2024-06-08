from django.conf import settings
# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.fields import JSONField

__all__ = ['ActivityStream']


class ActivityStream(models.Model):
    """
    Model used to describe activity stream (audit) events
    """

    class Meta:
        app_label = 'main'
        ordering = ('pk',)

    OPERATION_CHOICES = [
        ('create', _('Entity Created')),
        ('update', _("Entity Updated")),
        ('delete', _("Entity Deleted")),
        ('associate', _("Entity Associated with another Entity")),
        ('disassociate', _("Entity was Disassociated with another Entity"))
    ]

    actor = models.ForeignKey(settings.AUTH_USER_MODEL,
                              null=True,
                              on_delete=models.SET_NULL,
                              related_name='activity_stream')
    operation = models.CharField(max_length=13, choices=OPERATION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    changes = models.TextField(blank=True)

    object_relationship_type = models.TextField(blank=True)
    object1 = models.TextField()
    object2 = models.TextField()

    user = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)
    job = models.ManyToManyField("Job", blank=True)
    client = models.ManyToManyField("Client", blank=True)
    schedule = models.ManyToManyField("Schedule", blank=True)
    policy = models.ManyToManyField("Policy", blank=True)
    repository = models.ManyToManyField("Repository", blank=True)

    setting = JSONField(blank=True, null=True)

    def get_absolute_url(self, request=None):
        return reverse('api:activity_stream_detail', kwargs={'pk': self.pk}, request=request)

    def save(self, *args, **kwargs):
        # For compatibility with Django 1.4.x, attempt to handle any calls to
        # save that pass update_fields.
        try:
            super(ActivityStream, self).save(*args, **kwargs)
        except TypeError:
            if 'update_fields' not in kwargs:
                raise
            kwargs.pop('update_fields')
            super(ActivityStream, self).save(*args, **kwargs)
