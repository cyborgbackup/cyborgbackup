# Django
from django.conf import settings # noqa

# CyBorgBackup
from cyborgbackup.main.models.base import * # noqa
from cyborgbackup.main.models.jobs import Job
from cyborgbackup.main.models.users import User
from cyborgbackup.main.models.events import JobEvent
from cyborgbackup.main.models.channels import ChannelGroup
from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.schedules import Schedule
from cyborgbackup.main.models.repositories import Repository
from cyborgbackup.main.models.catalogs import Catalog
from cyborgbackup.main.models.policies import Policy
from cyborgbackup.main.models.activity_streams import ActivityStream
from cyborgbackup.api.versioning import reverse

# Monkeypatch Django serializer to ignore django-taggit fields (which break
# the dumpdata command; see https://github.com/alex/django-taggit/issues/155).
from django.core.serializers.python import Serializer as _PythonSerializer
_original_handle_m2m_field = _PythonSerializer.handle_m2m_field


def _new_handle_m2m_field(self, obj, field):
    try:
        field.rel.through._meta
    except AttributeError:
        return
    return _original_handle_m2m_field(self, obj, field)


_PythonSerializer.handle_m2m_field = _new_handle_m2m_field

# Add custom methods to User model for permissions checks.
from django.contrib.auth.models import User  # noqa


@property
def user_is_system_auditor(user):
    if not hasattr(user, '_is_system_auditor'):
        if user.pk:
            user._is_system_auditor = user.roles.filter(
                singleton_name='system_auditor', role_field='system_auditor').exists()
        else:
            # Odd case where user is unsaved, this should never be relied on
            return False
    return user._is_system_auditor

# Import signal handlers only after models have been defined.
import cyborgbackup.main.signals # noqa

from cyborgbackup.main.registrar import activity_stream_registrar # noqa

activity_stream_registrar.connect(Client)
activity_stream_registrar.connect(User)
activity_stream_registrar.connect(Repository)
activity_stream_registrar.connect(Schedule)
activity_stream_registrar.connect(Policy)
activity_stream_registrar.connect(Client)

# prevent API filtering on certain Django-supplied sensitive fields
prevent_search(User._meta.get_field('password'))
