import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf.urls import url
from django.core.asgi import get_asgi_application

from cyborgbackup.main.consumers import CyborgBackupConsumer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cyborgbackup.settings")

application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": get_asgi_application()

    # WebSocket chat handler
    "websocket": AuthMiddlewareStack(
        URLRouter([
            url(r"^$", CyborgBackupConsumer.as_asgi()),
        ])
    ),
})
