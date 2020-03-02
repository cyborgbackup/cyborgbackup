from django_elasticsearch_dsl_drf.constants import (
    LOOKUP_FILTER_REGEXP,
    LOOKUP_FILTER_TERM,
    LOOKUP_FILTER_WILDCARD
)
from django_elasticsearch_dsl_drf.filter_backends import (
    FilteringFilterBackend,
    OrderingFilterBackend,
    DefaultOrderingFilterBackend,
    SearchFilterBackend,
)
from django_elasticsearch_dsl_drf.viewsets import DocumentViewSet

from cyborgbackup.elasticsearch.documents.catalogs import CatalogDocument
from cyborgbackup.elasticsearch.serializers import ESCatalogDocumentSerializer


class ESCatalogViewSet(DocumentViewSet):
    document = CatalogDocument
    serializer_class = ESCatalogDocumentSerializer

    lookup_field = 'archive_name'
    filter_backends = [
        FilteringFilterBackend,
        OrderingFilterBackend,
        DefaultOrderingFilterBackend,
        SearchFilterBackend,
    ]

    # Define search fields
    search_fields = (
        'archive_name',
        'path',
    )

    # Filter fields
    filter_fields = {
        'path': {
            'field': 'path.keyword',
            'lookups': [
                LOOKUP_FILTER_REGEXP,
                LOOKUP_FILTER_TERM
            ]
        },
        'archive_name': {
            'field': 'archive_name.keyword',
            'lookups': [
                LOOKUP_FILTER_WILDCARD,
                LOOKUP_FILTER_REGEXP,
                LOOKUP_FILTER_TERM
            ]
        },
        'owner': 'owner.keyword',
        'group': 'group.keyword',
        'mtime': 'mtime.keyword',
        'mode': 'mode.keyword',
        'size': 'size',
        'job': 'job',
    }

    # Define ordering fields
    ordering_fields = {
        'path': 'path.keyword',
        'archive_name': 'archive_name.keyword'
    }

    # Specify default ordering
    ordering = ('archive_name', 'path')
