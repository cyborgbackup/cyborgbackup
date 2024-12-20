#!/bin/sh

. /opt/cyborgbackup/.env

check_postgresql() {
    echo "Check PostgreSQL connexion"
    su - postgres -c 'psql -c "\du"' 2>/dev/null
    return $?
}

if ! check_postgresql; then
    echo "Error: PostgreSQL is not available. Please check database is started"
    echo "Installation success with warning."
    exit 0
fi

su - postgres -c 'psql -c "\du"' | grep -q 'cyborgbackup' 2>&1 1>/dev/null
if [ $? -ne 0 ]; then
    echo "Create CyBorgBackup PostgreSQL User"
    su - postgres -c 'createuser cyborgbackup'
    su - postgres -c "psql -qc \"ALTER USER cyborgbackup WITH PASSWORD '$POSTGRES_PASSWORD'\"";
fi
su - postgres -c 'psql -c "\l"' | grep -q 'cyborgbackup' 2>&1 1>/dev/null
if [ $? -ne 0 ]; then
    echo "Create CyBorgBackup database"
    su - postgres -c 'createdb -O cyborgbackup cyborgbackup'
fi
