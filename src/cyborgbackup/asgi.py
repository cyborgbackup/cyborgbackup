import os
from cyborgbackup import prepare_env
from channels.asgi import get_channel_layer

prepare_env()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cyborgbackup.settings")


channel_layer = get_channel_layer()
