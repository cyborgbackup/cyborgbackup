import logging
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import re_path

from cyborgbackup import prepare_env
from cyborgbackup.main.consumers import CyBorgBackupConsumer, JwtAuthMiddlewareStack

prepare_env()

logger = logging.getLogger('cyborgbackup.asgi')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cyborgbackup.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    'websocket': JwtAuthMiddlewareStack(
        URLRouter([
            re_path(r"^websocket/$", CyBorgBackupConsumer.as_asgi()),
        ])
    )
})
