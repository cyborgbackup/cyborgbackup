# Python
import logging

import pymongo
# Celery
from celery import Task, shared_task, current_app
from django.conf import settings

# CyBorgBackup
from cyborgbackup.main.utils.task_manager import TaskManager

logger = logging.getLogger('cyborgbackup.main.utils.task_manager')


class LogErrorsTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.exception('Task {} encountered exception.'.format(self.name), exc_info=exc)
        super(LogErrorsTask, self).on_failure(exc, task_id, args, kwargs, einfo)


def catalog_is_running():
    try:
        pymongo.MongoClient(settings.MONGODB_URL).server_info()
        return True
    except Exception:
        return False


def celery_worker_is_running():
    if len(current_app.control.ping()) > 0:
        return True
    else:
        return False


@shared_task(base=LogErrorsTask)
def run_job_launch(job_id):
    TaskManager().schedule()


@shared_task(base=LogErrorsTask)
def run_job_complete(job_id):
    TaskManager().schedule()


@shared_task(base=LogErrorsTask)
def run_task_manager():
    logger.debug("Running CyBorgBackup task manager.")
    TaskManager().schedule()
