#!/bin/sh

set -e
. /opt/cyborgbackup/.env

echo "Install Python3 requirements"
pip3 install --upgrade wheel
pip3 install -r /usr/share/cyborgbackup/requirements.txt
mkdir -p /opt/cyborgbackup/var/run

python3 "$HOME/manage.py" migrate
python3 "$HOME/manage.py" collectstatic
if [ -z "$CYBORG_READY" ]; then
    python3 "$HOME/manage.py" loaddata settings
    python3 "$HOME/manage.py" makesuperuser
    echo "export CYBORG_READY=1" >> /opt/cyborgbackup/.env
else
  python3 "$HOME/manage.py" rebuild_settings
fi
