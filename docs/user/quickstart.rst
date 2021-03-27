.. _quickstart:

Quickstart
==========

Eager to get started? This page gives a good introduction in how to get started
with CyBorgBackup.

CyBorgBackup System
-------------------

CyBorgBackup use some framework to give a system with capabilities of backup
system based on BorgBackup with ease.

The Web Interface and API populate the Policy, Schedule, Repository, Client
and Job object.

We use Celery Beat to manage the schedule of internal task of CyBorgBackup
like task_manager and to notify celery to start task.
Task_manager is responsible to launch job if he's ready and not blocked
by another job.

Celery is responsible to execute task like task_manager or other. It's the
element who execute ssh connection and execute borg backup.

Channels Workers is responsible of the websocket message between each element
and the web interface.

Callback receivers all stdout messages from celery program output to put them
in database and emit signal under the websocket.


Object Relation
---------------

A schedule describe the policy schedule. They can be affected to multiple
policies. The schedule is describe using the crontab format.

A repository describe the borg backup repository with the path and the
repository encryption key. The path must be a valid uri like SCP uri.

A client describe a backup client with their hostname only. IP and Borg Version
are filled by the preparation script.

A policy is the element who made the relation between each element. A policy
have a schedule, a repository, a type, and some clients. We can also define
the retention policy of each client backup. They can also launch post ou pre hook.

A job is the backup job based on a policy and a client. When you launch a backup
job, the system create as many jobs as there are client defined in the policy.

Depending of the settings value, some job are created in dependencies of them
like catalog job, prepare job and prune job.

Enabled object
--------------

Each object have a enabled/disabled field. This field enable the object in each
relation. For example, if you disable a schedule, each policies who used this
schedule will be unusable. The same for the client or the repository.

Preparation job
---------------

Client and repository came with a preparation job to install and prepare borg.
On the preparation script, the final step is to prevent CyBorgBackup system
that the object is ready to be used. If the hook didn't work, the job stdout
show the curl command to launch to enable the object. Or you can use the API to
set the ready field to true.

.. warning::
    The URL settings must be defined correctly with an accessible URL of each client of repository nodes.

Policy Type
-----------

At this time, 9 policy types has been defined in CyBorgBackup.

rootfs
~~~~~~

The rootfs policy backup all files present in the root directory of the server
except some useless file like /dev, /proc and other.

vm
~~

The vm policy type backup directly the Virtual Machine using the hypervisor.
They will backup the hard drive device of the virtual machine.

mysql
~~~~~

The mysql policy type will create a mysql dump and backup them using Borg.

You can to specify user,password and database/s in extra vars::

    {"user":"backupuser","password":"backupass"}

By default, mysql policy type will backup all databases.
To specify a database, you need to add database entry in extra_vars::

    {"databases":"mydb"}

To specify multiple databases, you need to add databases list in extra_vars::

    {"databases":["mydb1","mydb2"]}

Command to create backup user on MySQL::

    GRANT LOCK TABLES, SELECT ON *.* TO 'backupuser'@'%' identified by 'backuppass';
    FLUSH PRIVILEGES

postgresql
~~~~~~~~~~

The postgresql policy type will create a postgresql dump and backup them
using Borg.

You can to specify database in extra vars::

    {"database":"mydb"}

Command to create backup user on PostgreSQL::

    CREATE USER backupuser SUPERUSER password 'backuppass';
    ALTER USER cyborgbackup set default_transaction_read_only = on;

piped
~~~~~

The piped policy type permit to launch a command on the client and backup the
output of the command to Borg.

You need to specify extra vars with piped command::

    {"command":"mypipedcommand"}

config
~~~~~~

The config policy type will backup only the /etc folder of the server.

mail
~~~~

The mail policy type will backup only the /var/mail or /var/lib/mail folder of the server.

folders
~~~~~~~

The folders policy type will backup specified folder of the server.
You need to specify extra vars with piped command::

    {"folders":["folder1","folder2"]}


proxmox
~~~~~~~

The folders policy type will backup specified folder of the server.
You need to specify extra vars with piped command::

    {"folders":["folder1","folder2"]}