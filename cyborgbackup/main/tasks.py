# Python
import logging

from cyborgbackup.main.tasks.runjob import RunJob

# Celery
from celery.app import app_or_default

# CyBorgBackup
from cyborgbackup.main.utils.callbacks import CallbackQueueDispatcher

__all__ = ['CallbackQueueDispatcher']

OPENSSH_KEY_ERROR = u'''\
It looks like you're trying to use a private key in OpenSSH format, which \
isn't supported by the installed version of OpenSSH on this instance. \
Try upgrading OpenSSH or providing your private key in an different format. \
'''

logger = logging.getLogger('cyborgbackup.main.tasks')


def launch_integrity_check():
    # TODO
    # Launch Integrity Check on all Repositories based on crontab defined in Settings
    print("You didn't say the magic word")


logger.debug('Registering RunJob task.')
app_or_default().register_task(RunJob())
