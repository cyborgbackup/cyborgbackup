from django.apps import AppConfig


class MainConfig(AppConfig):
    name = 'cyborgbackup.main'
    verbose_name = 'Main'

    def ready(self):
        # Import registered signals
        from cyborgbackup.main import signals