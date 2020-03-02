from django_elasticsearch_dsl_drf.serializers import DocumentSerializer

from cyborgbackup.elasticsearch.documents.catalogs import CatalogDocument


class ESCatalogDocumentSerializer(DocumentSerializer):

    class Meta:
        document = CatalogDocument
        fields = (
            'path',
            'archive_name',
            'job',
            'owner',
            'group',
            'size',
            'mtime',
            'healthy',
            'mode'
        )
