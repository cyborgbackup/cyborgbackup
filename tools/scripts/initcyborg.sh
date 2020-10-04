#!/bin/sh

set -e
. /opt/cyborgbackup/.env

echo "Install Python3 requirements"
pip3 install --upgrade wheel
pip3 install -r /usr/share/cyborgbackup/requirements.txt
mkdir -p /opt/cyborgbackup/var/run

python3 $HOME/manage.py migrate
if [ -z "$CYBORG_READY" ]; then
    python3 "$HOME/manage.py" loaddata settings
    echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin@cyborg.local', 'admin')" | python3 "$HOME/manage.py" shell
    echo "export CYBORG_READY=1" >> /opt/cyborgbackup/.env
fi
