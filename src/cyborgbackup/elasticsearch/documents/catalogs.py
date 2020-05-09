from elasticsearch_dsl import analyzer
from django_elasticsearch_dsl import Document, Index, fields
from django_elasticsearch_dsl.registries import registry
from cyborgbackup.main.models.catalogs import Catalog as catalog_models

catalog_index = Index('catalog')
catalog_index.settings(
    number_of_shards=5,
    number_of_replicas=0
)

html_strip = analyzer(
    'html_strip',
    tokenizer="standard",
    filter=["lowercase", "stop", "snowball"],
    char_filter=["html_strip"]
)


@catalog_index.doc_type
class CatalogDocument(Document):
    """Catalog elasticsearch document"""

    id = fields.TextField(
        analyzer=html_strip,
        fields={
            'keyword': fields.KeywordField(),
        }
    )
    path = fields.TextField(
        analyzer=html_strip,
        fields={
            'keyword': fields.KeywordField(),
        }
    )
    archive_name = fields.TextField(
        analyzer=html_strip,
        fields={
            'keyword': fields.KeywordField(),
        }
    )
    mode = fields.TextField(
        analyzer=html_strip,
        fields={
            'keyword': fields.TextField(analyzer='keyword'),
        }
    )
    owner = fields.TextField(
        analyzer=html_strip,
        fields={
            'keyword': fields.TextField(analyzer='keyword'),
        }
    )
    group = fields.TextField(
        analyzer=html_strip,
        fields={
            'keyword': fields.TextField(analyzer='keyword'),
        }
    )
    mtime = fields.TextField(
        analyzer=html_strip,
        fields={
            'keyword': fields.TextField(analyzer='keyword'),
        }
    )
    job = fields.IntegerField(attr='job_id')
    size = fields.IntegerField()
    healthy = fields.BooleanField()

    class Index:
        doc_type = '_doc'
        name = 'catalog'

    class Meta:
        model = catalog_models
        doc_type = '_doc'

    class Django(object):

        model = catalog_models
