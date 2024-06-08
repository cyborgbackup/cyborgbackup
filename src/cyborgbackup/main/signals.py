# Python
<<<<<<< Updated upstream
import logging
=======
import contextlib
import json
import logging
import threading
>>>>>>> Stashed changes

# Django-CRUM
from crum import get_current_request, get_current_user
from crum.signals import current_user_getter
# Django
from django.db.models.signals import post_save
from django.dispatch import receiver

<<<<<<< Updated upstream
# Django-CRUM
from crum import get_current_request, get_current_user
from crum.signals import current_user_getter

# CyBorgBackup
from cyborgbackup.main.models import User, JobEvent
from cyborgbackup.api.serializers.jobs import JobEventWebSocketSerializer
=======
from cyborgbackup.api.serializers import (JobEventWebSocketSerializer, JobSerializer, ClientSerializer,
                                          RepositorySerializer, ScheduleSerializer, PolicySerializer)
from cyborgbackup.main import consumers
# CyBorgBackup
from cyborgbackup.main.models import User, JobEvent, Client, Policy, Schedule, Job, ActivityStream, Repository
from cyborgbackup.main.utils.common import model_instance_diff, model_to_dict, camelcase_to_underscore
>>>>>>> Stashed changes

__all__ = ['activity_stream_create', 'activity_stream_update',
           'activity_stream_delete', 'activity_stream_associate',
           'disable_activity_stream']

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


<<<<<<< Updated upstream
=======
class ActivityStreamEnabled(threading.local):
    def __init__(self):
        self.enabled = False

    def __nonzero__(self):
        return bool(self.enabled and getattr(settings, 'ACTIVITY_STREAM_ENABLED', True))


activity_stream_enabled = ActivityStreamEnabled()


@contextlib.contextmanager
def disable_activity_stream():
    '''
    Context manager to disable capturing activity stream changes.
    '''
    previous_value = None
    try:
        previous_value = activity_stream_enabled.enabled
        activity_stream_enabled.enabled = False
        yield
    finally:
        activity_stream_enabled.enabled = previous_value


model_serializer_mapping = {
    Job: JobSerializer,
    Client: ClientSerializer,
    Policy: PolicySerializer,
    Repository: RepositorySerializer,
    Schedule: ScheduleSerializer,
}


def activity_stream_create(sender, instance, created, **kwargs):
    if created and activity_stream_enabled:
        _type = type(instance)
        if getattr(_type, '_deferred', False):
            return
        object1 = camelcase_to_underscore(instance.__class__.__name__)
        changes = model_to_dict(instance, model_serializer_mapping)
        # Special case where Job survey password variables need to be hidden
        if type(instance) == Job:
            if 'extra_vars' in changes:
                changes['extra_vars'] = instance.display_extra_vars()
        activity_entry = ActivityStream(
            operation='create',
            object1=object1,
            changes=json.dumps(changes),
            actor=get_current_user_or_none())
        if instance._meta.model_name != 'setting':  # Is not conf.Setting instance
            activity_entry.save()
            getattr(activity_entry, object1).add(instance)


def activity_stream_update(sender, instance, **kwargs):
    if instance.id is None:
        return
    if not activity_stream_enabled:
        return
    try:
        old = sender.objects.get(id=instance.id)
    except sender.DoesNotExist:
        return

    new = instance
    changes = model_instance_diff(old, new, model_serializer_mapping)
    if changes is None:
        return
    _type = type(instance)
    if getattr(_type, '_deferred', False):
        return
    object1 = camelcase_to_underscore(instance.__class__.__name__)

    activity_entry = ActivityStream(
        operation='update',
        object1=object1,
        changes=json.dumps(changes),
        actor=get_current_user_or_none())
    if instance._meta.model_name != 'setting':  # Is not conf.Setting instance
        activity_entry.save()
        getattr(activity_entry, object1).add(instance)


def activity_stream_delete(sender, instance, **kwargs):
    if not activity_stream_enabled:
        return
    _type = type(instance)
    if getattr(_type, '_deferred', False):
        return
    changes = model_to_dict(instance)
    object1 = camelcase_to_underscore(instance.__class__.__name__)
    activity_entry = ActivityStream(
        operation='delete',
        changes=json.dumps(changes),
        object1=object1,
        actor=get_current_user_or_none())
    activity_entry.save()


def activity_stream_associate(sender, instance, **kwargs):
    if not activity_stream_enabled:
        return
    if kwargs['action'] in ['pre_add', 'pre_remove']:
        if kwargs['action'] == 'pre_add':
            action = 'associate'
        elif kwargs['action'] == 'pre_remove':
            action = 'disassociate'
        else:
            return
        obj1 = instance
        _type = type(instance)
        if getattr(_type, '_deferred', False):
            return
        object1 = camelcase_to_underscore(obj1.__class__.__name__)
        if object1 == 'activity_stream':
            return
        obj_rel = sender.__module__ + "." + sender.__name__

        for entity_acted in kwargs['pk_set']:
            obj2 = kwargs['model']
            obj2_id = entity_acted
            obj2_actual = obj2.objects.filter(id=obj2_id)
            if not obj2_actual.exists():
                continue
            obj2_actual = obj2_actual[0]
            _type = type(obj2_actual)
            if getattr(_type, '_deferred', False):
                return
            object2 = camelcase_to_underscore(obj2.__name__)
            activity_entry = ActivityStream(
                changes=json.dumps(dict(object1=object1,
                                        object1_pk=obj1.pk,
                                        object2=object2,
                                        object2_pk=obj2_id,
                                        action=action,
                                        relationship=obj_rel)),
                operation=action,
                object1=object1,
                object2=object2,
                object_relationship_type=obj_rel,
                actor=get_current_user_or_none())
            activity_entry.save()
            getattr(activity_entry, object1).add(obj1)
            getattr(activity_entry, object2).add(obj2_actual)


>>>>>>> Stashed changes
@receiver(current_user_getter)
def get_current_user_from_drf_request(sender, **kwargs):
    '''
    Provider a signal handler to return the current user from the current
    request when using Django REST Framework. Requires that the APIView set
    drf_request on the underlying Django Request object.
    '''
    request = get_current_request()
    drf_request_user = getattr(request, 'drf_request_user', False)
    return drf_request_user, 0


def sync_superuser_status_to_rbac(instance, **kwargs):
    'When the is_superuser flag is changed on a user, reflect that in the membership of the System Admnistrator role'
    update_fields = kwargs.get('update_fields', None)
    if update_fields and 'is_superuser' not in update_fields:
        return


post_save.connect(sync_superuser_status_to_rbac, sender=User)
