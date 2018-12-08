import os
import logging

from cyborgbackup import prepare_env

prepare_env()

from django.core.wsgi import get_wsgi_application 
from channels.asgi import get_channel_layer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cyborgbackup.settings")


channel_layer = get_channel_layer()
