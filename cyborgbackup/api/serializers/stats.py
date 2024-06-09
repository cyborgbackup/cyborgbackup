# Python
import logging

# Django REST Framework
from rest_framework import serializers

# CyBorgBackup
from .base import EmptySerializer

logger = logging.getLogger('cyborgbackup.api.serializers.stats')


class StatsSerializer(EmptySerializer):
    stats = serializers.ListField()
