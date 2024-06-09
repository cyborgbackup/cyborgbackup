# Python
import logging
from collections import OrderedDict

# Django
from django.conf import settings as dsettings
from django.utils.translation import gettext_lazy as _
# Django REST Framework
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
# REST Simple JWT
from rest_framework_simplejwt.views import TokenObtainPairView

# CyBorgBackup
from cyborgbackup.api.serializers.base import CyborgTokenObtainPairSerializer
from cyborgbackup.api.views.generics import APIView
from cyborgbackup.main.utils.common import get_cyborgbackup_version

logger = logging.getLogger('cyborgbackup.api.views.api')


class ApiRootView(APIView):
    permission_classes = (AllowAny,)
    view_name = _('REST API')
    versioning_class = None
    swagger_topic = 'Versioning'

    def get(self, request, format=None):
        """ List supported API versions """

        v1 = reverse('api:api_v1_root_view')
        data = dict(
            description=_('CyBorgBackup API Rest'),
            current_version=v1,
            available_versions=dict(v1=v1),
        )
        return Response(data)


class ApiVersionRootView(APIView):
    permission_classes = (AllowAny,)
    swagger_topic = 'Versioning'

    def get(self, request, format=None):
        """ List top level resources """
        data = OrderedDict()
        data['ping'] = reverse('api:api_v1_ping_view', request=request)
        data['config'] = reverse('api:api_v1_config_view', request=request)
        data['me'] = reverse('api:user_me_list', request=request)
        data['users'] = reverse('api:user_list', request=request)
        data['jobs'] = reverse('api:job_list', request=request)
        data['job_events'] = reverse('api:job_event_list', request=request)
        data['settings'] = reverse('api:setting_list', request=request)
        data['clients'] = reverse('api:client_list', request=request)
        data['schedules'] = reverse('api:schedule_list', request=request)
        data['repositories'] = reverse('api:repository_list', request=request)
        data['policies'] = reverse('api:policy_list', request=request)
        data['restore'] = reverse('api:restore_launch', request=request)
        data['catalogs'] = reverse('api:catalog_list', request=request)
        data['stats'] = reverse('api:stats', request=request)
        data['escatalogs'] = reverse('api:escatalog_list', request=request)
        return Response(data)


class ApiV1RootView(ApiVersionRootView):
    view_name = _('Version 1')


class ApiV1PingView(APIView):
    """A simple view that reports very basic information about this
    instance, which is acceptable to be public information.
    """
    permission_classes = (AllowAny,)
    authentication_classes = ()
    view_name = _('Ping')
    swagger_topic = 'System Configuration'

    def get(self, request, format=None):
        """Return some basic information about this instance

        Everything returned here should be considered public / insecure, as
        this requires no auth and is intended for use by the installer process.
        """
        response = {'version': get_cyborgbackup_version(), 'ping': "pong"}

        return Response(response)


class ApiV1ConfigView(APIView):
    permission_classes = (IsAuthenticated,)
    view_name = _('Configuration')
    swagger_topic = 'System Configuration'

    def check_permissions(self, request):
        super(ApiV1ConfigView, self).check_permissions(request)
        if not request.user.is_superuser and request.method.lower() not in {'options', 'head', 'get'}:
            self.permission_denied(request)  # Raises PermissionDenied exception.

    def get(self, request, format=None):
        '''Return various sitewide configuration settings'''

        data = dict(
            time_zone=dsettings.TIME_ZONE,
            debug=dsettings.DEBUG,
            sql_debug=dsettings.SQL_DEBUG,
            allowed_hosts=dsettings.ALLOWED_HOSTS,
            # beat_schedule=dsettings.CELERY_BEAT_SCHEDULE,
            version=get_cyborgbackup_version(),
        )

        return Response(data)


class AuthView(APIView):
    ''' List enabled single-sign-on endpoints '''

    authentication_classes = []
    permission_classes = (AllowAny,)
    swagger_topic = 'System Configuration'

    def get(self, request):
        data = OrderedDict()
        err_backend, err_message = request.session.get('social_auth_error', (None, None))
        return Response(data)


class CyborgTokenObtainPairView(TokenObtainPairView):
    serializer_class = CyborgTokenObtainPairSerializer
