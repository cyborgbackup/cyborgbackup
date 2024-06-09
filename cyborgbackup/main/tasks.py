# Python
import logging

from cyborgbackup.main.tasks.runjob import RunJob

try:
    import psutil
except Exception:
    psutil = None

from contextlib import contextmanager

# Celery
from celery.app import app_or_default

# Django
from django_pglocks import advisory_lock as django_pglocks_advisory_lock
from django.db import connection

# CyBorgBackup
from cyborgbackup.main.utils.callbacks import CallbackQueueDispatcher

__all__ = ['advisory_lock', 'CallbackQueueDispatcher']

OPENSSH_KEY_ERROR = u'''\
It looks like you're trying to use a private key in OpenSSH format, which \
isn't supported by the installed version of OpenSSH on this instance. \
Try upgrading OpenSSH or providing your private key in an different format. \
'''

logger = logging.getLogger('cyborgbackup.main.tasks')


@contextmanager
def advisory_lock(*args, **kwargs):
    if connection.vendor == 'postgresql':
        with django_pglocks_advisory_lock(*args, **kwargs) as internal_lock:
            yield internal_lock
    else:
        yield True


def launch_integrity_check():
    # TODO
    # Launch Integrity Check on all Repositories based on crontab defined in Settings
    print("You didn't say the magic word")


app_or_default().register_task(RunJob())
