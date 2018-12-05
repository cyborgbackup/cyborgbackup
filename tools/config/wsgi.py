import sys
if sys.prefix != '/var/lib/cyborgbackup/venv':
    raise RuntimeError('CyBorgBackup virtualenv not activated. Check WSGIPythonHome in Apache configuration.')
from cyborgbackup.wsgi import application  # NOQA
