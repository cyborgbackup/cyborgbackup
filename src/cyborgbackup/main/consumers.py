import json
import pika
import logging
import msgpack

from django.conf import settings
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

logger = logging.getLogger('cyborgbackup.main.consumers')


class CyborgBackupConsumer(WebsocketConsumer):

    def connect(self):
        self.user = self.scope["user"]
        self.accept()

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

    def send(self, data):
        super().send(data['text'])

    def disconnect(self, close_code):
        # Called when the socket closes
        if 'groups' in self.scope['session']:
            for group in self.scope['session']['groups']:
                async_to_sync(self.channel_layer.group_discard)(
                    group,
                    self.channel_name
                )
        logger.info("Websocket disconnected")


def emit_channel_notification(group, payload):
    try:
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
        logger.error("Invalid payload emitting channel {} on topic: {}".format(group, payload))
