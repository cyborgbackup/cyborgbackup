# Python
import logging

# Celery
from celery import Task, shared_task

# CyBorgBackup
from cyborgbackup.main.utils.task_manager import TaskManager

logger = logging.getLogger('cyborgbackup.main.utils.task_manager')


class LogErrorsTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.exception('Task {} encountered exception.'.format(self.name), exc_info=exc)
        super(LogErrorsTask, self).on_failure(exc, task_id, args, kwargs, einfo)


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
