# Python
import logging

# Django
from django.utils.encoding import smart_str
# Django REST Framework
from rest_framework import authentication

logger = logging.getLogger('cyborgbackup.api.authentication')


class LoggedBasicAuthentication(authentication.BasicAuthentication):

    def authenticate(self, request):
        ret = super(LoggedBasicAuthentication, self).authenticate(request)
        if ret:
            username = ret[0].username if ret[0] else '<none>'
            logger.debug(smart_str(u"User {} performed a {} to {} through the API".format(username,
                                                                                          request.method,
                                                                                          request.path)))
        return ret

    def authenticate_header(self, request):
        return super(LoggedBasicAuthentication, self).authenticate_header(request)


class SessionAuthentication(authentication.SessionAuthentication):

    def authenticate_header(self, request):
        return 'Session'

    def enforce_csrf(self, request):
        return None
