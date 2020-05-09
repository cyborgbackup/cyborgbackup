# Python
from datetime import datetime, timedelta
import logging
import uuid
import six

# Django
from django.conf import settings
from django.core.cache import cache
from django.db import transaction, connection, DatabaseError
from django.utils.timezone import now as tz_now, utc
from django.db.models import Q

# CyBorgBackup
from cyborgbackup.main.models.jobs import (
    Job,
)
from cyborgbackup.main.models.clients import Client
from cyborgbackup.main.models.repositories import Repository
from cyborgbackup.main.utils.common import get_type_for_model, load_module_provider
from cyborgbackup.main.signals import disable_activity_stream

# Celery
from celery import Celery
from celery.app.control import Inspect

from contextlib import contextmanager

from django_pglocks import advisory_lock as django_pglocks_advisory_lock


logger = logging.getLogger('cyborgbackup.main.scheduler')


@contextmanager
def advisory_lock(*args, **kwargs):
    if connection.vendor == 'postgresql':
        with django_pglocks_advisory_lock(*args, **kwargs) as internal_lock:
            yield internal_lock
    else:
        yield True


class DependencyGraph(object):
    JOBS = 'jobs'

    def __init__(self, queue):
        self.queue = queue
        self.data = {}
        self.data[self.JOBS] = {}

    def get_now(self):
        return tz_now()

    def can_job_run(self, job):
        return self.data[self.JOBS].get(job.id, True)

    def mark_job(self, job):
        self.data[self.JOBS][job.id] = False

    def is_job_blocked(self, job):
        if type(job) is Job:
            return not self.can_job_run(job)

    def add_job(self, job):
        if type(job) is Job:
            self.mark_job(job)

    def add_jobs(self, jobs):
        map(lambda j: self.add_job(j), jobs)


class TaskManager:

    def __init__(self):
        self.graph = dict()
        self.graph['cyborgbackup'] = dict(graph=DependencyGraph('cyborgbackup'),
                                          capacity_total=16,
                                          consumed_capacity=0)

    def is_job_blocked(self, task):
        for g in self.graph:
            if self.graph[g]['graph'].is_job_blocked(task):
                return True

        if not task.dependent_jobs_finished():
            return True

        return False

    def get_tasks(self, status_list=('pending', 'waiting', 'running')):
        jobs = [j for j in Job.objects.filter(status__in=status_list)]
        return sorted(jobs, key=lambda task: task.created)

    '''
    Tasks that are running and SHOULD have a celery task.
    {
        'execution_node': [j1, j2,...],
        'execution_node': [j3],
        ...
    }
    '''
    def get_running_tasks(self):
        execution_nodes = {}
        waiting_jobs = []
        now = tz_now()
        jobs = Job.objects.exclude(job_type='workflow').filter((Q(status='running') |
                                                                Q(status='waiting',
                                                                  modified__lte=now - timedelta(seconds=60))))
        for j in jobs:
            waiting_jobs.append(j)
        return (execution_nodes, waiting_jobs)

    '''
    Tasks that are currently running in celery

    Transform:
    {
        "celery@ec2-54-204-222-62.compute-1.amazonaws.com": [],
        "celery@ec2-54-163-144-168.compute-1.amazonaws.com": [{
            ...
            "id": "5238466a-f8c7-43b3-9180-5b78e9da8304",
            ...
        }, {
            ...,
        }, ...]
    }

    to:
    {
        "ec2-54-204-222-62.compute-1.amazonaws.com": [
            "5238466a-f8c7-43b3-9180-5b78e9da8304",
            "5238466a-f8c7-43b3-9180-5b78e9da8306",
            ...
        ]
    }
    '''
    def get_active_tasks(self):
        if not hasattr(settings, 'IGNORE_CELERY_INSPECTOR'):
            app = Celery('cyborgbackup')
            app.config_from_object('django.conf:settings')
            inspector = Inspect(app=app)
            active_task_queues = inspector.active()
        else:
            logger.warn("Ignoring celery task inspector")
            active_task_queues = None

        queues = None
        if active_task_queues is not None:
            queues = {}
            for queue in active_task_queues:
                active_tasks = set()
                map(lambda at: active_tasks.add(at['id']), active_task_queues[queue])

                # celery worker name is of the form celery@myhost.com
                queue_name = queue.split('@')
                queue_name = queue_name[1 if len(queue_name) > 1 else 0]
                queues[queue_name] = active_tasks
        else:
            if not hasattr(settings, 'CELERY_UNIT_TEST'):
                return (None, None)

        return (active_task_queues, queues)

    def start_task(self, task, dependent_tasks=[]):
        from cyborgbackup.main.tasks import handle_work_error, handle_work_success

        task_actual = {
            'type': get_type_for_model(type(task)),
            'id': task.id,
        }
        dependencies = [{'type': get_type_for_model(type(t)), 'id': t.id} for t in dependent_tasks]

        error_handler = handle_work_error.s(subtasks=[task_actual] + dependencies)
        success_handler = handle_work_success.s(task_actual=task_actual)

        task.status = 'waiting'
        (start_status, opts) = task.pre_start()
        if not start_status:
            task.status = 'failed'
            if task.job_explanation:
                task.job_explanation += ' '
            task.job_explanation += 'Task failed pre-start check.'
            task.save()
            # TODO: run error handler to fail sub-tasks and send notifications
        else:
            logger.info('Submitting %s to instance group cyborgbackup.', task.log_format)
            with disable_activity_stream():
                task.celery_task_id = str(uuid.uuid4())
                task.save()

            self.consume_capacity(task, 'cyborgbackup')

        def post_commit():
            task.websocket_emit_status(task.status)
            if task.status != 'failed':
                task.start_celery_task(opts,
                                       error_callback=error_handler,
                                       success_callback=success_handler,
                                       queue='cyborgbackup')

        connection.on_commit(post_commit)

    def process_running_tasks(self, running_tasks):
        waiting_tasks = filter(lambda t: t.status in 'waiting', running_tasks)
        for task in waiting_tasks:
            if not self.is_job_blocked(task):
                task.status = 'pending'
                task.save()
        map(lambda task: self.graph['cyborgbackup']['graph'].add_job(task), running_tasks)

    def get_latest_repository_creation(self, job):
        latest_repository_creation = Job.objects.filter(repository=job.policy.repository_id,
                                                        job_type='check').order_by("-created")
        if not latest_repository_creation.exists():
            return None
        return latest_repository_creation.first()

    def create_prepare_repository(self, task):
        repository_task = Repository.objects.get(id=task.policy.repository_id).create_prepare_repository(
            _eager_fields=dict(launch_type='dependency', job_type='check'))

        # Repository created 1 seconds behind
        repository_task.created = task.created - timedelta(seconds=2)
        repository_task.status = 'pending'
        repository_task.policy = task.policy
        repository_task.dependent_jobs = task
        repository_task.save()
        return repository_task

    def should_prepare_repository(self, job, latest_prepare_repository):
        if latest_prepare_repository is None:
            return True

        if latest_prepare_repository.status in ['waiting', 'pending', 'running']:
            return False

        if not latest_prepare_repository.repository.ready:
            return True

        return False

    def create_prepare_client(self, task):
        client_task = Client.objects.get(id=task.client_id).create_prepare_client(
            _eager_fields=dict(launch_type='dependency', job_type='check'))

        # Client created 1 seconds behind
        client_task.created = task.created - timedelta(seconds=1)
        client_task.status = 'pending'
        client_task.policy = task.policy
        client_task.dependent_jobs = task
        client_task.save()
        return client_task

    def should_prepare_client(self, job, latest_prepare_client):
        if latest_prepare_client is None:
            return True

        if latest_prepare_client.status in ['waiting', 'pending', 'running']:
            return False

        if not latest_prepare_client.client.ready:
            return True

        return False

    def get_latest_client_preparation(self, job):
        latest_client_preparation = Job.objects.filter(client=job.client_id, job_type='check').order_by("-created")
        if not latest_client_preparation.exists():
            return None
        return latest_client_preparation.first()

    def create_prepare_hypervisor(self, task):
        client_task = Client.objects.get(id=task.client_id).create_prepare_hypervisor(
            _eager_fields=dict(launch_type='dependency', job_type='check'))

        # Client created 1 seconds behind
        client_task.created = task.created - timedelta(seconds=1)
        client_task.status = 'pending'
        client_task.policy = task.policy
        client_task.dependent_jobs = task
        client_task.save()
        return client_task

    def should_prepare_hypervisor(self, job, latest_prepare_hypervisor):
        if latest_prepare_hypervisor is None:
            return True

        if latest_prepare_hypervisor.status in ['waiting', 'pending', 'running']:
            return False

        if not latest_prepare_hypervisor.client.hypervisor_ready:
            return True

        return False

    def get_latest_hypervisor_preparation(self, job):
        provider = load_module_provider(job.policy.vmprovider)
        hypervisor = provider.get_client(job.client.hostname)
        latest_hypervisor_preparation = Job.objects.filter(
            client__hypervisor_name=hypervisor,
            job_type='check',
            policy__vmprovider=job.policy.vmprovider
        ).order_by("-created")
        if not latest_hypervisor_preparation.exists():
            return None
        return latest_hypervisor_preparation.first()

    def generate_dependencies(self, task):
        dependencies = []
        if type(task) is Job and task.launch_type != 'dependency' and task.job_type != 'catalog':
            latest_repository_creation = self.get_latest_repository_creation(task)
            if self.should_prepare_repository(task, latest_repository_creation):
                repository_task = self.create_prepare_repository(task)
                dependencies.append(repository_task)
            else:
                if latest_repository_creation.status in ['waiting', 'pending', 'running']:
                    dependencies.append(latest_repository_creation)

            if task.client:
                if task.policy.policy_type == 'vm':
                    latest_hypervisor_preparation = self.get_latest_hypervisor_preparation(task)
                    if self.should_prepare_hypervisor(task, latest_hypervisor_preparation):
                        hypervisor_task = self.create_prepare_hypervisor(task)
                        dependencies.append(hypervisor_task)
                    else:
                        if latest_hypervisor_preparation.status in ['waiting', 'pending', 'running']:
                            dependencies.append(latest_hypervisor_preparation)
                else:
                    latest_client_preparation = self.get_latest_client_preparation(task)
                    if self.should_prepare_client(task, latest_client_preparation):
                        client_task = self.create_prepare_client(task)
                        dependencies.append(client_task)
                    else:
                        if latest_client_preparation.status in ['waiting', 'pending', 'running']:
                            dependencies.append(latest_client_preparation)

        return dependencies

    def process_dependencies(self, dependent_task, dependency_tasks):
        for task in dependency_tasks:
            if self.is_job_blocked(task):
                logger.debug(six.text_type("Dependent {} is blocked from running").format(task.log_format))
                continue
            found_acceptable_queue = False
            if self.get_remaining_capacity('cyborgbackup') <= 0:
                logger.debug(six.text_type("Skipping group {} capacity <= 0").format('cyborgbackup'))
                continue
            if not self.would_exceed_capacity(task, 'cyborgbackup'):
                msg = six.text_type("Starting dependent {} in group {}")
                logger.debug(msg.format(task.log_format, 'cyborgbackup'))
                self.graph['cyborgbackup']['graph'].add_job(task)
                tasks_to_fail = list(filter(lambda t: t != task, dependency_tasks))
                tasks_to_fail += [dependent_task]
                self.start_task(task, tasks_to_fail)
                found_acceptable_queue = True
            if not found_acceptable_queue:
                msg = six.text_type("Dependent {} couldn't be scheduled on graph, waiting for next cycle")
                logger.debug(msg.format(task.log_format))

    def process_pending_tasks(self, pending_tasks):
        for task in pending_tasks:
            self.process_dependencies(task, self.generate_dependencies(task))
            if self.is_job_blocked(task):
                logger.debug(six.text_type("{} is blocked from running").format(task.log_format))
                continue
            found_acceptable_queue = False
            remaining_capacity = self.get_remaining_capacity('cyborgbackup')
            if remaining_capacity <= 0:
                logger.debug(six.text_type("Skipping group {}, remaining_capacity {} <= 0").format(
                    'cyborgbackup', remaining_capacity))
                continue
            if not self.would_exceed_capacity(task, 'cyborgbackup'):
                logger.debug(six.text_type("Starting {} in group {} (remaining_capacity={})").format(
                    task.log_format, 'cyborgbackup', remaining_capacity))
                self.graph['cyborgbackup']['graph'].add_job(task)

                self.start_task(task, [])
                found_acceptable_queue = True
                break
            else:
                logger.debug(six.text_type("Not enough capacity to run {} on {} (remaining_capacity={})").format(
                    task.log_format, 'cyborgbackup', remaining_capacity))
            if not found_acceptable_queue:
                msg = six.text_type("{} couldn't be scheduled on graph, waiting for next cycle")
                logger.debug(msg.format(task.log_format))

    def fail_jobs_if_not_in_celery(self, node_jobs, active_tasks, celery_task_start_time,
                                   isolated=False):
        for task in node_jobs:
            if (task.celery_task_id not in active_tasks and not hasattr(settings, 'IGNORE_CELERY_INSPECTOR')):
                if task.modified > celery_task_start_time:
                    continue
                new_status = 'failed'
                if isolated:
                    new_status = 'error'
                task.status = new_status
                task.start_args = ''  # blank field to remove encrypted passwords
                task.job_explanation += ' '.join((
                    'Task was marked as running in CyBorgBackup but was not present in',
                    'the job queue, so it has been marked as failed.',
                ))
                try:
                    task.save(update_fields=['status', 'start_args', 'job_explanation'])
                except DatabaseError:
                    logger.error("Task {} DB error in marking failed. Job possibly deleted.".format(task.log_format))
                    continue
                if hasattr(task, 'send_notification_templates'):
                    task.send_notification_templates('failed')
                task.websocket_emit_status(new_status)
                logger.error("{}Task {} has no record in celery. Marking as failed".format(
                    'Isolated ' if isolated else '', task.log_format))

    def cleanup_inconsistent_celery_tasks(self):
        '''
        Rectify cyborgbackup db <-> celery inconsistent view of jobs state
        '''
        last_cleanup = cache.get('last_celery_task_cleanup') or datetime.min.replace(tzinfo=utc)
        if (tz_now() - last_cleanup).seconds < 60*3:
            return

        logger.debug("Failing inconsistent running jobs.")
        celery_task_start_time = tz_now()
        active_task_queues, active_queues = self.get_active_tasks()
        cache.set('last_celery_task_cleanup', tz_now())

        if active_queues is None:
            logger.error('Failed to retrieve active tasks from celery')
            return None

        '''
        Only consider failing tasks on instances for which we obtained a task
        list from celery for.
        '''
        running_tasks, waiting_tasks = self.get_running_tasks()
        all_celery_task_ids = []
        for node, node_jobs in active_queues.items():
            all_celery_task_ids.extend(node_jobs)

        self.fail_jobs_if_not_in_celery(waiting_tasks, all_celery_task_ids, celery_task_start_time)

        for node, node_jobs in running_tasks.items():
            isolated = False
            if node in active_queues:
                active_tasks = active_queues[node]
            else:
                if node is None:
                    logger.error("Execution node Instance {} not found in database. "
                                 "The node is currently executing jobs {}".format(
                                     node, [j.log_format for j in node_jobs]))
                    active_tasks = []
                else:
                    continue

            self.fail_jobs_if_not_in_celery(
                node_jobs, active_tasks, celery_task_start_time,
                isolated=isolated
            )

    def calculate_capacity_consumed(self, tasks):
        self.graph['cyborgbackup']['consumed_capacity'] = 0

    def would_exceed_capacity(self, task, instance_group):
        current_capacity = self.graph['cyborgbackup']['consumed_capacity']
        capacity_total = self.graph['cyborgbackup']['capacity_total']
        if current_capacity == 0:
            return False
        return (task.task_impact + current_capacity > capacity_total)

    def consume_capacity(self, task, instance_group):
        logger.debug(six.text_type('{} consumed {} capacity units from {} with prior total of {}').format(
                     task.log_format, task.task_impact, 'cyborgbackup', 8))
        self.graph[instance_group]['consumed_capacity'] += task.task_impact

    def get_remaining_capacity(self, instance_group):
        return (self.graph[instance_group]['capacity_total'] - self.graph[instance_group]['consumed_capacity'])

    def process_tasks(self, all_sorted_tasks):
        running_tasks = filter(lambda t: t.status in ['waiting', 'running'], all_sorted_tasks)

        self.calculate_capacity_consumed(running_tasks)

        self.process_running_tasks(running_tasks)

        pending_tasks = filter(lambda t: t.status in 'pending', all_sorted_tasks)
        self.process_pending_tasks(pending_tasks)

    def _schedule(self):
        all_sorted_tasks = self.get_tasks()
        if len(all_sorted_tasks) > 0:
            self.process_tasks(all_sorted_tasks)

    def schedule(self):
        with transaction.atomic():
            # Lock
            with advisory_lock('task_manager_lock', wait=False) as acquired:
                if acquired is False:
                    logger.debug("Not running scheduler, another task holds lock")
                    return
                logger.debug("Starting Scheduler")

                self.cleanup_inconsistent_celery_tasks()
                self._schedule()
