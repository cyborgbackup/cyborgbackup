# Python
import logging

from django.conf import settings

# Celery
from celery import Task, shared_task, current_app

from elasticsearch import Elasticsearch

# CyBorgBackup
from cyborgbackup.main.utils.task_manager import TaskManager

logger = logging.getLogger('cyborgbackup.main.utils.task_manager')


class LogErrorsTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.exception('Task {} encountered exception.'.format(self.name), exc_info=exc)
        super(LogErrorsTask, self).on_failure(exc, task_id, args, kwargs, einfo)


def catalog_is_running():
    try:
        es_conf = settings.ELASTICSEARCH_DSL['default']['hosts'].split(':')
        es = Elasticsearch([{'host': es_conf[0], 'port': int(es_conf[1])}], max_retries=0)
        es.cluster.state()
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
