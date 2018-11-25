import re

from django.utils.translation import ugettext_lazy as _

__all__ = [
    'SCHEDULEABLE_PROVIDERS',
    'ANSI_SGR_PATTERN', 'CAN_CANCEL', 'ACTIVE_STATES'
]

SCHEDULEABLE_PROVIDERS = ('custom', 'scm',)
ANSI_SGR_PATTERN = re.compile(r'\x1b\[[0-9;]*m')
CAN_CANCEL = ('new', 'pending', 'waiting', 'running')
ACTIVE_STATES = CAN_CANCEL
