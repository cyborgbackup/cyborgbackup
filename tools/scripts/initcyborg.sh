#!/bin/sh

set -e
. /opt/cyborgbackup/.env

echo "Install Python3 requirements"
pip3 install --upgrade wheel
pip3 install -r /usr/share/cyborgbackup/requirements.txt
mkdir -p /opt/cyborgbackup/var/run

check_postgresql() {
    echo "Check PostgreSQL connexion"
    PGPASSWORD="$POSTGRES_PASSWORD" psql -h "127.0.0.1" -U "cyborgbackup" -d "cyborgbackup" -c "\q" 2>/dev/null
    return $?
}

if ! check_postgresql; then
    echo "Error: PostgreSQL is not available. Please check database is started"
    echo "Installation success with warning."
    exit 0
fi

python3 "$HOME/manage.py" migrate
python3 "$HOME/manage.py" collectstatic
if [ -z "$CYBORG_READY" ]; then
    python3 "$HOME/manage.py" loaddata settings
    python3 "$HOME/manage.py" makesuperuser
    echo "export CYBORG_READY=1" >> /opt/cyborgbackup/.env
else
  python3 "$HOME/manage.py" rebuild_settings
fi
