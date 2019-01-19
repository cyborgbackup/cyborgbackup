#!/bin/sh

. /opt/cyborgbackup/.env

psql -c "\du" | grep -q 'cyborgbackup' 2>&1 1>/dev/null
if [ $? -ne 0 ]; then
    echo "Create CyBorgBackup PostgreSQL User"
    createuser cyborgbackup
    psql -qc "ALTER USER cyborgbackup WITH PASSWORD '$POSTGRES_PASSWORD'";
fi
psql -c "\l" | grep -q 'cyborgbackup' 2>&1 1>/dev/null
if [ $? -ne 0 ]; then
    echo "Create CyBorgBackup database"
    createdb -O cyborgbackup cyborgbackup
fi
