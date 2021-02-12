import json
import pymongo
from django.conf import settings
from django.core.management.base import BaseCommand
from cyborgbackup.main.models import Job

try:
    from elasticsearch import Elasticsearch
except:
    print('ElasticSearch module not installed. Exit')
    exit(0)

db = pymongo.MongoClient(settings.MONGODB_URL).local
es = Elasticsearch([{'host': 'localhost', 'port': 9200}])

class Command(BaseCommand):
    """Fill MongoDB Catalog from ElasticSearch Catalog
    """
    help = 'Rebuild MongoDB Catalog from old ElasticSearch.'

    def handle(self, *args, **kwargs):
        # Sanity check: Is there already a running job on the System?
        jobs = Job.objects.filter(status="running")
        if jobs.exists():
            print('A job is already running, exiting.')
            return

        jobs = Job.objects.exclude(archive_name='')
        if jobs.exists():
            i=0
            search_object = {
                'size': 1000,
                'from': 0,
                'query': {
                    'match_all': {}
                }
            }
            res = es.search(index="catalog", doc_type='_doc', body=search_object)
            total = res['hits']['total']

            while i < total:
                list_entries = []
                for line in res['hits']['hits']:
                    cnt = db.catalog.count({'archive_name': line['archive_name'], 'path': line['path']})
                    if cnt == 0:
                        new_entry = {
                            'archive_name': line['archive_name'],
                            'job_id': line['job_id'],
                            'mode': line['mode'],
                            'path': line['path'],
                            'owner': line['user'],
                            'group': line['group'],
                            'type': line['type'],
                            'size': line['size'],
                            'healthy': line['healthy'],
                            'mtime': line['mtime']
                        }
                        list_entries.append(new_entry)
                if len(list_entries) > 0:
                    print('Insert {} entries from ElasticSearch'.format(len(list_entries)))
                    db.catalog.insert_many(list_entries)
                    if 'archive_name_text_path_text' not in db.catalog.index_information().keys():
                        db.catalog.create_index([
                            ('archive_name', pymongo.TEXT),
                            ('path', pymongo.TEXT)
                        ], name='archive_name_text_path_text', default_language='english')
                    if 'archive_name_1' not in db.catalog.index_information().keys():
                        db.catalog.create_index('archive_name', name='archive_name_1', default_language='english')

                i = i + 1000
                search_object = {
                    'size': 1000,
                    'from': i,
                    'query': {
                        'match_all': {}
                    }
                }
                res = es.search(index="catalog", doc_type='_doc', body=search_object)

