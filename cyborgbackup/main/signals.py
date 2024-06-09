# Python
import logging

# Django-CRUM
from crum import get_current_request, get_current_user
from crum.signals import current_user_getter
# Django-CRUM
# Django
from django.db.models.signals import post_save
from django.dispatch import receiver

from cyborgbackup.api.serializers.jobs import JobEventWebSocketSerializer
# CyBorgBackup
from cyborgbackup.main.models import User, JobEvent

__all__ = []

logger = logging.getLogger('cyborgbackup.main.signals')


def get_current_user_or_none():
    u = get_current_user()
    if not isinstance(u, User):
        return None
    return u


def emit_event_detail(serializer, relation, **kwargs):
    instance = kwargs['instance']
    created = kwargs['created']
    if created:
        event_serializer = serializer(instance)
        consumers.emit_channel_notification(
            '-'.join([event_serializer.get_group_name(instance), str(getattr(instance, relation))]),
            event_serializer.data
        )


@receiver(post_save, sender=JobEvent)
def emit_job_event_detail(sender, **kwargs):
    emit_event_detail(JobEventWebSocketSerializer, 'job_id', **kwargs)


@receiver(current_user_getter)
def get_current_user_from_drf_request(sender, **kwargs):
    """
    Provider a signal handler to return the current user from the current
    request when using Django REST Framework. Requires that the APIView set
    drf_request on the underlying Django Request object.
    """
    request = get_current_request()
    drf_request_user = getattr(request, 'drf_request_user', False)
    return drf_request_user, 0


def sync_superuser_status_to_rbac(instance, **kwargs):
    """When the is_superuser flag is changed on a user, reflect that in the membership of the System Admnistrator role"""
    update_fields = kwargs.get('update_fields', None)
    if update_fields and 'is_superuser' not in update_fields:
        return


post_save.connect(sync_superuser_status_to_rbac, sender=User)
