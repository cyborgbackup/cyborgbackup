#!/bin/sh

. /opt/cyborgbackup/.env

rabbitmqctl list_vhosts | grep -q 'cyborgbackup' 2>&1 1>/dev/null
if [ $? -ne 0 ]; then
    echo "Create RabbitMQ CyBorgBackup vhost"
    rabbitmqctl add_vhost cyborgbackup
fi
rabbitmqctl list_users | grep -q 'cyborgbackup' 2>&1 1>/dev/null
if [ $? -ne 0 ]; then
    echo "Create RabbitMQ CyBorgBackup user"
    rabbitmqctl add_user cyborgbackup "$RABBITMQ_DEFAULT_PASS"
fi
rabbitmqctl list_permissions -p cyborgbackup | grep -q 'cyborgbackup\s*\.' 2>&1 1>/dev/null
if [ $? -ne 0 ]; then
    echo "Grant permission on RabbitMQ vhost to CyBorgBackup user"
    rabbitmqctl set_permissions -p cyborgbackup cyborgbackup '.*' '.*' '.*'
fi
