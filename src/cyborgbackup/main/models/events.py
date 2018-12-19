import datetime
import logging

from django.db import models
from django.utils.dateparse import parse_datetime
from django.utils.timezone import utc
from django.utils.translation import ugettext_lazy as _

from cyborgbackup.api.versioning import reverse
from cyborgbackup.main.fields import JSONField
from cyborgbackup.main.models.base import CreatedModifiedModel

logger = logging.getLogger('cyborgbackup.analytics.job_events')

__all__ = ['JobEvent']


class JobEvent(CreatedModifiedModel):
    '''
    An event/message logged from the callback when running a job.
    '''

    EVENT_TYPES = [
        (0, 'debug', _('Debug'), False),
        (0, 'verbose', _('Verbose'), False),
        (0, 'deprecated', _('Deprecated'), False),
        (0, 'warning', _('Warning'), False),
        (0, 'system_warning', _('System Warning'), False),
        (0, 'error', _('Error'), True),
    ]

    FAILED_EVENTS = [x[1] for x in EVENT_TYPES if x[3]]
    EVENT_CHOICES = [(x[1], x[2]) for x in EVENT_TYPES]
    LEVEL_FOR_EVENT = dict([(x[1], x[0]) for x in EVENT_TYPES])

    VALID_KEYS = [
        'event', 'event_data', 'task', 'created', 'uuid', 'stdout',
        'start_line', 'end_line', 'verbosity', 'job_id', 'counter'
    ]

    class Meta:
        app_label = 'main'
        ordering = ('pk',)
        index_together = [
            ('job', 'event'),
            ('job', 'uuid'),
            ('job', 'start_line'),
            ('job', 'end_line'),
            ('job', 'parent_uuid'),
        ]

    uuid = models.CharField(
        max_length=1024,
        default='',
        editable=False,
    )
    parent_uuid = models.CharField(
        max_length=1024,
        default='',
        editable=False,
    )
    event = models.CharField(
        max_length=100,
        choices=EVENT_CHOICES,
    )
    event_data = JSONField(
        blank=True,
        default={},
    )
    failed = models.BooleanField(
        default=False,
        editable=False,
    )
    changed = models.BooleanField(
        default=False,
        editable=False,
    )
    task = models.CharField(
        max_length=1024,
        default='',
        editable=False,
    )
    counter = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    stdout = models.TextField(
        default='',
        editable=False,
    )
    verbosity = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    start_line = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    end_line = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    job = models.ForeignKey(
        'Job',
        related_name='job_events',
        on_delete=models.CASCADE,
        editable=False,
    )

    @property
    def event_level(self):
        return self.LEVEL_FOR_EVENT.get(self.event, 0)

    def get_event_display2(self):
        msg = self.get_event_display()

        # Change display for runner events triggered by async polling.  Some of
        # these events may not show in most cases, due to filterting them out
        # of the job event queryset returned to the user.
        return msg

    def _update_from_event_data(self):
        # Update event model fields from event data.
        updated_fields = set()
        event_data = self.event_data
        res = event_data.get('res', None)
        if self.event in self.FAILED_EVENTS and not event_data.get('ignore_errors', False):
            self.failed = True
            updated_fields.add('failed')
        if isinstance(res, dict):
            if res.get('changed', False):
                self.changed = True
                updated_fields.add('changed')
            # If we're not in verbose mode, wipe out any module arguments.
            invocation = res.get('invocation', None)
            if isinstance(invocation, dict) and self.job_verbosity == 0 and 'module_args' in invocation:
                event_data['res']['invocation']['module_args'] = ''
                self.event_data = event_data
                updated_fields.add('event_data')
        return updated_fields

    @classmethod
    def create_from_data(self, **kwargs):
        pk = None
        for key in ('job_id',):
            if key in kwargs:
                pk = key
        if pk is None:
            return

        # Convert the datetime for the job event's creation appropriately,
        # and include a time zone for it.
        #
        # In the event of any issue, throw it out, and Django will just save
        # the current time.
        try:
            if not isinstance(kwargs['created'], datetime.datetime):
                kwargs['created'] = parse_datetime(kwargs['created'])
            if not kwargs['created'].tzinfo:
                kwargs['created'] = kwargs['created'].replace(tzinfo=utc)
        except (KeyError, ValueError):
            kwargs.pop('created', None)

        # Sanity check: Don't honor keys that we don't recognize.
        for key in list(kwargs.keys()):
            if key not in self.VALID_KEYS:
                kwargs.pop(key)

        job_event = self.objects.create(**kwargs)
        logger.info('Event data saved.', extra=dict(python_objects=dict(job_event=job_event)))
        return job_event

    @property
    def job_verbosity(self):
        return self.job.verbosity

    def save(self, *args, **kwargs):
        # If update_fields has been specified, add our field names to it,
        # if it hasn't been specified, then we're just doing a normal save.
        update_fields = kwargs.get('update_fields', [])
        # Update model fields and related objects unless we're only updating
        # failed/changed flags triggered from a child event.
        from_parent_update = kwargs.pop('from_parent_update', False)
        if not from_parent_update:
            # Update model fields from event data.
            updated_fields = self._update_from_event_data()
            for field in updated_fields:
                if field not in update_fields:
                    update_fields.append(field)
        super(JobEvent, self).save(*args, **kwargs)

    def get_absolute_url(self, request=None):
        return reverse('api:job_event_detail', kwargs={'pk': self.pk}, request=request)

    def __unicode__(self):
        return u'%s @ %s' % (self.get_event_display2(), self.created.isoformat())
