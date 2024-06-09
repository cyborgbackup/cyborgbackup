#!/bin/bash
set +x

cd /cyborgbackup/

if [[ -n "$RUN_MIGRATIONS" ]]; then
    # wait for postgres to be ready
    while ! nc -z postgres 5432; do
        echo "Waiting for postgres to be ready to accept connections"; sleep 1;
    done;
    cyborgbackup-manage migrate
else
    wait-for-migrations
fi

cyborgbackup-manage loaddata settings
cyborgbackup-manage makesuperuser
cyborgbackup-manage collectstatic
cyborgbackup-manage runserver 0.0.0.0:8000