import json
import pika
import logging
<<<<<<< Updated upstream
import msgpack

from django.conf import settings
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
=======
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer, WebsocketConsumer
from channels.layers import get_channel_layer
from channels.middleware import BaseMiddleware
from django.db import close_old_connections
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, User
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken
from jwt import decode as jwt_decode
>>>>>>> Stashed changes

logger = logging.getLogger('cyborgbackup.main.consumers')


<<<<<<< Updated upstream
class CyborgBackupConsumer(WebsocketConsumer):
=======
@database_sync_to_async
def get_user(validated_token):
    try:
        user = get_user_model().objects.get(id=validated_token["user_id"])
        print(f"{user}")
        return user

    except User.DoesNotExist:
        return AnonymousUser()
>>>>>>> Stashed changes

    def connect(self):
        self.user = self.scope["user"]
        self.accept()

<<<<<<< Updated upstream
    def receive(self, text_data=None, bytes_data=None):
        data = json.loads(text_data)
        if 'groups' in data:
            groups = data['groups']
            current_groups = set(self.scope['session']['groups'] if 'groups' in self.scope['session'] else [])
            for group_name, v in groups.items():
                if type(v) is list:
                    for oid in v:
                        name = '{}-{}'.format(group_name, oid)
                        print("Create group {}".format(name))
                        current_groups.add(name)
                        async_to_sync(self.channel_layer.group_add)(
                            name,
                            self.channel_name
                        )
                else:
                    print("Create group {}".format(group_name))
                    current_groups.add(group_name)
                    async_to_sync(self.channel_layer.group_add)(
                        group_name,
                        self.channel_name
                    )
            self.scope['session']['groups'] = list(current_groups)
=======
class JwtAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
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
            print(e)
            return None
        else:
            #  Then token is valid, decode it
            decoded_data = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            print(decoded_data)
            # Will return a dictionary like -
            # {
            #     "token_type": "access",
            #     "exp": 1568770772,
            #     "jti": "5c15e80d65b04c20ad34d77b6703251b",
            #     "user_id": 6
            # }

            # Get the user using ID
            scope["user"] = await get_user(validated_token=decoded_data)
        return await super().__call__(scope, receive, send)
>>>>>>> Stashed changes

    def send(self, data):
        super().send(data['text'])

<<<<<<< Updated upstream
    def disconnect(self, close_code):
        # Called when the socket closes
        if 'groups' in self.scope['session']:
            for group in self.scope['session']['groups']:
                async_to_sync(self.channel_layer.group_discard)(
                    group,
                    self.channel_name
                )
        logger.info("Websocket disconnected")
=======
def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(AuthMiddlewareStack(inner))


class CyBorgBackupConsumer(WebsocketConsumer):

    def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            logger.error("User authenticated.")
            self.accept()
        else:
            logger.error("Request user is not authenticated to use websocket.")
            self.close()

    def receive(self, text_data=None, bytes_data=None):
        data = json.loads(text_data)
        print(data)

        # if 'groups' in data:
        #     discard_groups(message)
        #     groups = data['groups']
        #     current_groups = set(message.channel_session.pop('groups') if 'groups' in message.channel_session else [])
        #     for group_name, v in groups.items():
        #         if type(v) is list:
        #             for oid in v:
        #                 name = '{}-{}'.format(group_name, oid)
        #                 current_groups.add(name)
        #                 Group(name).add(message.reply_channel)
        #         else:
        #             current_groups.add(group_name)
        #             Group(group_name).add(message.reply_channel)
        #     message.channel_session['groups'] = list(current_groups)

    def disconnect(self, close_code):
        print(close_code)
        #self.channel_layer.group_discard()


# def discard_groups(message):
#     if 'groups' in message.channel_session:
#         for group in message.channel_session['groups']:
#             Group(group).discard(message.reply_channel)


# @rest_auth
# def ws_connect(message):
#     message.reply_channel.send({"accept": True})
#     message.content['method'] = 'FAKE'
#     if message.user.is_authenticated:
#         message.reply_channel.send(
#             {"text": json.dumps({"accept": True, "user": message.user.id})}
#         )
#     else:
#         logger.error("Request user is not authenticated to use websocket.")
#         message.reply_channel.send({"close": True})
#     return None


# @channel_session_user
# def ws_disconnect(message):
#     discard_groups(message)


# @channel_session_user
# def ws_receive(message):
#     raw_data = message.content['text']
#     data = json.loads(raw_data)
#
#     if 'groups' in data:
#         discard_groups(message)
#         groups = data['groups']
#         current_groups = set(message.channel_session.pop('groups') if 'groups' in message.channel_session else [])
#         for group_name, v in groups.items():
#             if type(v) is list:
#                 for oid in v:
#                     name = '{}-{}'.format(group_name, oid)
#                     current_groups.add(name)
#                     Group(name).add(message.reply_channel)
#             else:
#                 current_groups.add(group_name)
#                 Group(group_name).add(message.reply_channel)
#         message.channel_session['groups'] = list(current_groups)
>>>>>>> Stashed changes


def emit_channel_notification(group, payload):
    try:
<<<<<<< Updated upstream
        connection = pika.BlockingConnection(
            pika.URLParameters(settings.BROKER_URL))
        channel = connection.channel()

        send_data = {
            "type": "send",
            "text": json.dumps(payload)
        }
        channel.basic_publish(
            exchange='groups',
            routing_key=group,
            body=msgpack.packb({
                "__asgi_group__": group,
                **send_data
            }),
            properties=pika.BasicProperties(
                content_encoding="binary"
            )
        )
        connection.close()
    except:
=======
        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            group,
            {"text": json.dumps(payload, cls=DjangoJSONEncoder)},
        )
    except ValueError:
>>>>>>> Stashed changes
        logger.error("Invalid payload emitting channel {} on topic: {}".format(group, payload))
