.. _configuration:

Configuration
=============

CyBorgBackup need some configuration before be ready to use.
They will be defined in the next section.

Settings
--------

Under the settings page, you must configure the following element :

* URL => Contains the CyBorgBackup accessible URL. It will be use by client or repository node for the preparation step.
* Mail Server => You must configure the Mail server to use the mail report of CyBorgBackup
* SSH Key => An ssh key pair must be configured in CyBorgBackup. CyBorgBackup can generate them for you. He will use them to connect on each client and on each repository. The public key must also be configured on each authorized_keys ssh file manually.

.. warning::
    The SSH Key must be protected with a password. The password will be encrypted before stored under CyBorgBackup database.

.. warning::
    The SSH Public Key must be configured on the "Backup User" authorized_keys file. If backup user is different of "root", CyBorgBackup will use 'sudo' command for the backup

.. note::
    If you have a specific configuration for SSH, different port or ciphers for example.
    You can use the **.ssh/config** file on the CyBorgBackup folder.

Repositories
------------

A repository must be defined to start backup.
The path must be in URI format as the following : **user@fqdn:path**

CyBorgBackup will try connect using SSH to this URI.

.. warning::
    Same as the SSH Key configuration, the user defined in the path must have the CyBorgBackup SSK Key configured in authorized_keys file.

Schedules
---------

The schedule system use the CRON format.

Clients
-------

To use the CyBorgBackup system, you must create your first client.
The hostname must be a resolvable hostname by CyBorgBackup. It will use them to connect using SSH protocol.

Policies
--------

The policy is the element for permit to CyBorgBackup to backup client.
It's a relation between a schedule, a repository and clients.

Pre-hook and post-hook entries are script or command launch of each client. The script or command must be exist on them. CyBorgBackup will not pull or install them.

The "Keep" section is used to specify on many archive will be keep by the system before pruning.
For example, if you configure 7 Keep Daily and 4 Keep Weekly, CyBorgBackup will keep archives of the last 7 days made each day and one archive each week for the last 4 weeks.

By default, CyBorgbackup will connect on each client and each client will push the backup to the repository using ssh connection.
The "Pull Mode" permit to change the method, CyBorgBackup will connect on the repository node and from them, connect to each client.
Be careful, the client need to connect to the repository node.

Depending of the policy type, you can configure extra configuration using the pencil button on the right of each client button. You must add client before editing extra configuration.

Ready ?
-------

Settings, Schedule, Repository, Client and Policy are configured ? CyBorgBackup is now ready to backup them.
For each new repository or client, CyBorgBackup will launch a preparation script before backup them.

You can now launch a policy to launch the backup workflow or wait for the schedule.