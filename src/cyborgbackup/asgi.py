import os
import logging

from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.settings import api_settings
from channels.sessions import SessionMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter, ChannelNameRouter
from django.core.asgi import get_asgi_application

from cyborgbackup import prepare_env
from cyborgbackup.main.consumers import CyborgBackupConsumer

prepare_env()

logger = logging.getLogger('cyborgbackup.asgi')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cyborgbackup.settings")

django_asgi_app = get_asgi_application()

from django.contrib.auth.models import AnonymousUser

class EmptyRequest:
    _request = {}
    META = {}


def get_user_from_token(token):
    user = None
    authenticators = [auth() for auth in api_settings.DEFAULT_AUTHENTICATION_CLASSES]
    request = EmptyRequest()
    request.META["HTTP_AUTHORIZATION"] = "Bearer {}".format(token)
    for authenticator in authenticators:
        try:
            user_auth_tuple = authenticator.authenticate(request)
        except AuthenticationFailed:
            pass

        if user_auth_tuple is not None:
            user, _ = user_auth_tuple
            break
    return user


class TokenAuthMiddleware:
    """
    Token authorization middleware for Django Channels 2
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query_string = scope['query_string']
        if b'token' in query_string:
            try:
                tokens = parse_qs(query_string)[b'token']
                if len(tokens) > 0:
                    user = await sync_to_async(get_user_from_token, thread_sensitive=True)(tokens[0].decode('utf-8'))

                    if user:
                        scope['user'] = user
                    else:
                        scope['user'] = AnonymousUser()
            except Exception as e:
                scope['user'] = AnonymousUser()
        return await self.app(scope, receive, send)


application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": django_asgi_app,

    # WebSocket handler
    "websocket": TokenAuthMiddleware(
      SessionMiddlewareStack(
        CyborgBackupConsumer.as_asgi()
      )
    )
})

