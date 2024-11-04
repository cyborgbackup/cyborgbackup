import json
import logging
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.generic.websocket import WebsocketConsumer
from channels.layers import get_channel_layer
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import close_old_connections
from jwt import decode as jwt_decode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

logger = logging.getLogger('cyborgbackup.main.consumers')


@database_sync_to_async
def get_user(validated_token):
    try:
        user = get_user_model().objects.get(id=validated_token["user_id"])
        print(f"{user}")
        return user

    except User.DoesNotExist:
        return AnonymousUser()


class JwtAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Close old database connections to prevent usage of timed out connections
        close_old_connections()

        # Get the token
        token = parse_qs(scope["query_string"].decode("utf8"))["token"][0]

        # Try to authenticate the user
        try:
            # This will automatically validate the token and raise an error if token is invalid
            UntypedToken(token)
        except (InvalidToken, TokenError) as e:
            # Token is invalid
            scope["user"] = AnonymousUser()
        else:
            #  Then token is valid, decode it
            decoded_data = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])

            # Get the user using ID
            scope["user"] = await get_user(validated_token=decoded_data)
        return await super().__call__(scope, receive, send)

    def send(self, data):
        super().send(data['text'])


def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(AuthMiddlewareStack(inner))


class CyBorgBackupConsumer(WebsocketConsumer):

    def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            logger.info("User authenticated.")
            self.accept()
        else:
            logger.error("Request user is not authenticated to use websocket.")
            self.close()

    def receive(self, text_data=None, bytes_data=None, **kwargs):
        data = json.loads(text_data)

        if 'groups' in data:
            self.clean_groups()
            groups = []
            for group_name, v in data['groups'].items():
                if isinstance(v, list):
                    for oid in v:
                        name = '{}-{}'.format(group_name, oid)
                        groups.append(name)
                else:
                    groups.append(group_name)
            self.scope["session"]["groups"] = groups
            for g in groups:
                async_to_sync(self.channel_layer.group_add)(
                    g, self.channel_name
                )

    def clean_groups(self):
        if 'groups' in self.scope["session"]:
            for group in self.scope["session"]["groups"]:
                async_to_sync(self.channel_layer.group_discard)(
                    group, self.channel_name
                )

    def new_message(self, event):
        logger.debug('New message: {}'.format(event))
        if isinstance(event['data'], str):
            self.send(text_data=event['data'])
        else:
            self.send(text_data=json.dumps(event['data'], cls=DjangoJSONEncoder))

    def disconnect(self, close_code):
        self.clean_groups()


def emit_channel_notification(group, payload):
    try:
        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            group,
            {"type": "new_message", "data": json.dumps(payload, cls=DjangoJSONEncoder)},
        )
    except ValueError:
        logger.error("Invalid payload emitting channel {} on topic: {}".format(group, payload))
    except Exception as e:
        logger.error(e)
        logger.error("Error emitting channel {} on topic: {}".format(group, payload))
