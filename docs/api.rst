.. _api:

CyBorgBackup API
================

Actually, only the V1 version of the API is available.
They can be access on the url /api of the webserver and the V1 api on the url /api/v1.

Main API V1
-----------

.. http:get::  /api/v1

    Retrieve all available submodule of the API.

    **Example request**:

    .. sourcecode:: bash

        $ curl https://cyborgbackup.local/api/v1/

    **Example response**:

    .. sourcecode:: js

        {
            "ping": "/api/v1/ping",
            "config": "/api/v1/config/",
            "me": "/api/v1/me/"
        }

.. http:get::  /api/v1/ping

    Test the api and get the version

    .. sourcecode:: js

        {
            "version": "1.0"
            "ping": "pong"
        }

.. http:get::  /api/v1/config

    Retrieve some configuration of the CyBorgBackup instance.

    .. sourcecode:: js

        {
            "version": "1.0"
            "debug": true,
            "allowed_hosts" : ["127.0.0.1"]
        }

.. http:get::  /api/v1/me

    Retrieve information about the current logged user.

    .. sourcecode:: js

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [
                "id": 1,
                "type": "user",
                "url": "/api/v1/users/1/",
                "related": {},
                "summary_fields": {},
                "created": "2018-11-08T16:13:29.370148Z",
                "first_name": "",
                "last_name": "",
                "email": "admin@milkywan.fr",
                "is_superuser": true
            ]
        }

Users API V1
------------

.. http:get::  /api/v1/users/

    Retrieve a list of all users.

    .. sourcecode:: js

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [USERS]
        }

    :>json string next: URI for next set of Users.
    :>json string previous: URI for previous set of Users.
    :>json integer count: Total number of Users.
    :>json array results: Array of ``Users`` objects.

.. http:get::  /api/v1/users/(int:id)/

    Retrieve details of a single user.

    .. sourcecode:: js

        {
            "id": 3,
            "type": "user",
            "url": "/api/v1/users/3/",
            "related": {},
            "summary_fields": {},
            "created": "2018-11-11T19:43:24.261706Z",
            "first_name": "",
            "last_name": "",
            "email": "cyborg@agent.local",
            "is_superuser": true
        }

    :>json integer id: The ID of the user
    :>json string type: The object type under cyborgbackup system.
    :>json string url: The URL access of the user object.
    :>json dict related: Related property of mapped object
    :>json dict summary_fields: Some summary field of object relation
    :>json string created: The creation date of the user
    :>json string first_name: First name of the user
    :>json string last_name: Last name of the user
    :>json string email: Email of the user
    :>json boolean is_superuser: Super User

    :statuscode 200: no error
    :statuscode 404: There is no ``User`` with this ID

.. http:post::  /api/v1/users/

    Create a single user.

    .. sourcecode:: js

        {
            "first_name": "",
            "last_name": "",
            "email": "cyborg@agent.local",
            "is_superuser": true
        }

    :>json string first_name: First name of the user
    :>json string last_name: Last name of the user
    :>json string email: Email of the user
    :>json boolean is_superuser: Super User

    :statuscode 200: no error
    :statuscode 404: There is no ``User`` with this ID

.. http:patch::  /api/v1/users/(int:id)/

    Update a single user.

    .. sourcecode:: js

        {
            "first_name": "",
            "last_name": "",
            "email": "cyborg@agent.local",
            "is_superuser": true
        }

    :>json integer id: The ID of the user
    :>json string first_name: First name of the user
    :>json string last_name: Last name of the user
    :>json string email: Email of the user
    :>json boolean is_superuser: Super User

    :statuscode 200: no error
    :statuscode 404: There is no ``User`` with this ID

.. http:delete::  /api/v1/users/(int:id)/

    Delete a single user.

    :statuscode 200: no error
    :statuscode 404: There is no ``User`` with this ID

Clients API V1
--------------

.. http:get::  /api/v1/clients/

    Retrieve a list of all clients.

    .. sourcecode:: js

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [CLIENTS]
        }

    :>json string next: URI for next set of Clients.
    :>json string previous: URI for previous set of Clients.
    :>json integer count: Total number of Clients.
    :>json array results: Array of ``Clients`` objects.

.. http:get::  /api/v1/clients/(int:id)/

    Retrieve details of a single client.

    .. sourcecode:: js

        {
            "id": 1,
            "type": "client",
            "url": "/api/v1/clients/1/",
            "related": {},
            "summary_fields": {},
            "created": "2018-11-22T18:17:51.831221Z",
            "modified": "2018-11-22T19:21:16.011127Z",
            "created_by": null,
            "modified_by": null,
            "hostname": "lab.example.com",
            "ip": "",
            "version": "",
            "ready": false,
            "hypervisor_ready": false,
            "hypervisor_name": "",
            "enabled": true,
            "uuid": "fa3462e3-57da-430e-bca5-3bc60d4ba5a2"
        }

    :>json integer id: The ID of the client
    :>json string type: The object type under cyborgbackup system.
    :>json string url: The URL access of the client object.
    :>json dict related: Related property of mapped object
    :>json dict summary_fields: Some summary field of object relation
    :>json string created: The creation date of the client
    :>json string modified: The modification date of the client
    :>json string created_by: User responsible of the creation of the client
    :>json string modified_by: User responsible of the last modification
    :>json string hostname: Client Hostname
    :>json string ip: IP Addresses of the client
    :>json string version: Borg Client Version
    :>json boolean ready: Client prepared to be use with borg
    :>json string hypervisor_name: Hypervisor name of the client
    :>json boolean hypervisor_ready: Hypervisor prepared to be use with borg
    :>json boolean enabled: Client enabled
    :>json string uuid: Auto generated UUID

    :statuscode 200: no error
    :statuscode 404: There is no ``Client`` with this ID

.. http:post::  /api/v1/clients/

    Create a single client.

    .. sourcecode:: js

        {
            "hostname": "lab.example.com",
            "ip": "",
            "version": "",
            "ready": false,
            "hypervisor_ready": false,
            "hypervisor_name": "",
            "enabled": true,
        }

    :>json string hostname: Client Hostname
    :>json string ip: IP Addresses of the client
    :>json string version: Borg Client Version
    :>json boolean ready: Client prepared to be use with borg
    :>json string hypervisor_name: Hypervisor name of the client
    :>json boolean hypervisor_ready: Hypervisor prepared to be use with borg
    :>json boolean enabled: Client enabled

    :statuscode 200: no error
    :statuscode 404: There is no ``Client`` with this ID

.. http:patch::  /api/v1/clients/(int:id)/

    Update a single client.

    .. sourcecode:: js

        {
            "hostname": "lab.example.com",
            "ip": "",
            "version": "",
            "ready": false,
            "hypervisor_ready": false,
            "hypervisor_name": "",
            "enabled": true
        }

    :>json integer id: The ID of the client
    :>json string hostname: Client Hostname
    :>json string ip: IP Addresses of the client
    :>json string version: Borg Client Version
    :>json boolean ready: Client prepared to be use with borg
    :>json string hypervisor_name: Hypervisor name of the client
    :>json boolean hypervisor_ready: Hypervisor prepared to be use with borg
    :>json boolean enabled: Client enabled

    :statuscode 200: no error
    :statuscode 404: There is no ``Client`` with this ID

.. http:delete::  /api/v1/clients/(int:id)/

    Delete a single client.

    :statuscode 200: no error
    :statuscode 404: There is no ``Client`` with this ID

Schedules API V1
----------------

.. http:get::  /api/v1/schedules/

    Retrieve a list of all schedules.

    .. sourcecode:: js

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [SCHEDULES]
        }

    :>json string next: URI for next set of Schedules.
    :>json string previous: URI for previous set of Schedules.
    :>json integer count: Total number of Schedules.
    :>json array results: Array of ``Schedule`` objects.

.. http:get::  /api/v1/schedules/(int:id)/

    Retrieve details of a single schedule.

    .. sourcecode:: js

        {
            "id": 1,
            "type": "schedule",
            "url": "/api/v1/schedules/1/",
            "related": {},
            "summary_fields": {},
            "created": "2018-11-22T18:17:51.831221Z",
            "modified": "2018-11-22T19:21:16.011127Z",
            "created_by": null,
            "modified_by": null,
            "name": "Every Minutes",
            "crontab": "*/1 * * * * *",
            "enabled": true,
            "uuid": "fa3462e3-57da-430e-bca5-3bc60d4ba5a2"
        }

    :>json integer id: The ID of the schedule
    :>json string type: The object type under cyborgbackup system.
    :>json string url: The URL access of the schedule object.
    :>json dict related: Related property of mapped object
    :>json dict summary_fields: Some summary field of object relation
    :>json string created: The creation date of the schedule
    :>json string modified: The modification date of the schedule
    :>json string created_by: User responsible of the creation of the schedule
    :>json string modified_by: User responsible of the last modification
    :>json string name: Schedule name
    :>json string crontab: Crontab schedule
    :>json boolean enabled: Schedule enabled
    :>json string uuid: Auto generated UUID

    :statuscode 200: no error
    :statuscode 404: There is no ``Schedule`` with this ID

.. http:post::  /api/v1/schedules/

    Create a single schedule.

    .. sourcecode:: js

        {
            "name": "Every Minutes",
            "crontab": "*/1 * * * * *",
            "enabled": true
        }

    :>json string name: Schedule name
    :>json string crontab: Crontab schedule
    :>json boolean enabled: Schedule enabled

    :statuscode 200: no error
    :statuscode 404: There is no ``Schedule`` with this ID

.. http:patch::  /api/v1/schedules/(int:id)/

    Update a single schedule.

    .. sourcecode:: js

        {
            "name": "Every Monday",
            "crontab": "0 5 * * MON *",
            "enabled": true
        }

    :>json integer id: The ID of the schedule
    :>json string name: Schedule name
    :>json string crontab: Crontab schedule
    :>json boolean enabled: Schedule enabled

    :statuscode 200: no error
    :statuscode 404: There is no ``Schedule`` with this ID

.. http:delete::  /api/v1/schedules/(int:id)/

    Delete a single schedule.

    :statuscode 200: no error
    :statuscode 404: There is no ``Schedule`` with this ID

Repositories API V1
-------------------

.. http:get::  /api/v1/repositories/

    Retrieve a list of all repositories.

    .. sourcecode:: js

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [REPOSITORIES]
        }

    :>json string next: URI for next set of Repositories.
    :>json string previous: URI for previous set of Repositories.
    :>json integer count: Total number of Repositories.
    :>json array results: Array of ``Repository`` objects.

.. http:get::  /api/v1/repositories/(int:id)/

    Retrieve details of a single repository.

    .. sourcecode:: js

        {
            "id": 1,
            "type": "repository",
            "url": "/api/v1/repositories/1/",
            "related": {},
            "summary_fields": {},
            "created": "2018-11-22T18:17:51.831221Z",
            "modified": "2018-11-22T19:21:16.011127Z",
            "created_by": null,
            "modified_by": null,
            "name": "Main Repo",
            "path": "cyborgbackup@backup:/repository",
            "repository_key": "0123456789abcdef",
            "original_size": 722,
            "compressed_size": 747,
            "deduplicated_size": 747,
            "ready": true,
            "enabled": true,
            "uuid": "fa3462e3-57da-430e-bca5-3bc60d4ba5a2"
        }

    :>json integer id: The ID of the repository
    :>json string type: The object type under cyborgbackup system.
    :>json string url: The URL access of the repository object.
    :>json dict related: Related property of mapped object
    :>json dict summary_fields: Some summary field of object relation
    :>json string created: The creation date of the repository
    :>json string modified: The modification date of the repository
    :>json string created_by: User responsible of the creation of the repository
    :>json string modified_by: User responsible of the last modification
    :>json string name: Repository name
    :>json string path: URI path to access the repository from each client
    :>json string repository_key: Key used to encrypt the repository
    :>json integer original_size: Calculated size of all archives
    :>json integer compressed_size: Calculated compressed size of all archives
    :>json integer deduplicated_size: Calculated deduplicated size of all archives
    :>json boolean ready: Repository prepared to be use with borg
    :>json boolean enabled: Repository enabled
    :>json string uuid: Auto generated UUID

    :statuscode 200: no error
    :statuscode 404: There is no ``Repository`` with this ID

.. http:post::  /api/v1/repositories/

    Create a single repository.

    .. sourcecode:: js

        {
            "name": "Main Repo",
            "path": "cyborgbackup@backup:/repository",
            "repository_key": "0123456789abcdef",
            "ready": true,
            "enabled": true
        }

    :>json string name: Repository name
    :>json string path: URI path to access the repository from each client
    :>json string repository_key: Key used to encrypt the repository
    :>json boolean ready: Repository prepared to be use with borg
    :>json boolean enabled: Repository enabled

    :statuscode 200: no error
    :statuscode 404: There is no ``Repository`` with this ID

.. http:patch::  /api/v1/repositories/(int:id)/

    Update a single repository.

    .. sourcecode:: js

        {
            "name": "Main Repo",
            "path": "cyborgbackup@backup:/repository",
            "repository_key": "0123456789abcdef",
            "ready": true,
            "enabled": true
        }

    :>json integer id: The ID of the repository
    :>json string name: Repository name
    :>json string path: URI path to access the repository from each client
    :>json string repository_key: Key used to encrypt the repository
    :>json boolean ready: Repository prepared to be use with borg
    :>json boolean enabled: Repository enabled

    :statuscode 200: no error
    :statuscode 404: There is no ``Repository`` with this ID

.. http:delete::  /api/v1/repositories/(int:id)/

    Delete a single repository.

    :statuscode 200: no error
    :statuscode 404: There is no ``Repository`` with this ID

Policies API V1
-------------------

.. http:get::  /api/v1/policies/

    Retrieve a list of all policies.

    .. sourcecode:: js

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [POLICIES]
        }

    :>json string next: URI for next set of Policies.
    :>json string previous: URI for previous set of Policies.
    :>json integer count: Total number of Policies.
    :>json array results: Array of ``Policy`` objects.

.. http:get::  /api/v1/policies/(int:id)/

    Retrieve details of a single policy.

    .. sourcecode:: js

        {
            "id": 1,
            "type": "policy",
            "url": "/api/v1/policies/1/",
            "related": {
                "launch": "/api/v1/policies/1/launch/",
                "calendar": "/api/v1/policies/1/calendar/",
                "schedule": "/api/v1/schedules/1/",
                "repository": "/api/v1/repositories/1/"
            },
            "summary_fields": {
                "repository": {
                    "id": 1,
                    "name": "Main Repo",
                    "path": "cyborgbackup@backup:/repository"
                },
                "schedule": {
                    "id": 1,
                    "name": "Each Monday",
                    "crontab": "0 5 * * MON *"
                }
            },
            "created": "2018-11-22T18:51:22.894984Z",
            "modified": "2018-11-23T20:54:51.013495Z",
            "created_by": null,
            "modified_by": null,
            "uuid": "3a67b010-bbc4-43de-937e-11270c710aad",
            "name": "Full Features",
            "extra_vars": "",
            "clients": [
                1
            ],
            "repository": 1,
            "schedule": 1,
            "policy_type": "vm",
            "keep_hourly": 1,
            "keep_yearly": null,
            "keep_daily": null,
            "keep_weekly": null,
            "keep_monthly": null,
            "vmprovider": "proxmox",
            "next_run": "2018-11-26T05:00:00Z",
            "mode_pull": false,
            "enabled": true
        }

    :>json integer id: The ID of the policy
    :>json string type: The object type under cyborgbackup system.
    :>json string url: The URL access of the policy object.
    :>json dict related: Related property of mapped object
    :>json dict summary_fields: Some summary field of object relation
    :>json string created: The creation date of the policy
    :>json string modified: The modification date of the policy
    :>json string created_by: User responsible of the creation of the policy
    :>json string modified_by: User responsible of the last modification
    :>json string name: Policy name
    :>json string extra_vars: JSON Dictionnary of variable used by the system
    :>json array clients: Array of ``Client`` ID
    :>json integer repository: ``Repository`` ID
    :>json integer schedule: ``Schedule`` ID
    :>json string policy_type: Policy Backup Type
    :>json integer keep_hourly: Number of hourly archives to keep
    :>json integer keep_daily: Number of daily archives to keep
    :>json integer keep_weekly: Number of weekly archives to keep
    :>json integer keep_monthly: Number of monthly archives to keep
    :>json integer keep_yearly: Number of yearly archives to keep
    :>json string vmprovider: Name of the VM module provider
    :>json string next_run: Date of the next run of the backup job
    :>json boolean mode_pull: Backup in pull mode
    :>json boolean enabled: Policy enabled
    :>json string uuid: Auto generated UUID

    :statuscode 200: no error
    :statuscode 404: There is no ``Policy`` with this ID

.. http:post::  /api/v1/policies/

    Create a single policy.

    .. sourcecode:: js

        {
            "name": "Full Features",
            "extra_vars": "",
            "clients": [
                1
            ],
            "repository": 1,
            "schedule": 1,
            "policy_type": "vm",
            "keep_hourly": 1,
            "keep_yearly": null,
            "keep_daily": null,
            "keep_weekly": null,
            "keep_monthly": null,
            "vmprovider": "proxmox",
            "mode_pull": false,
            "enabled": true
        }

    :>json string name: Policy name
    :>json string extra_vars: JSON Dictionnary of variable used by the system
    :>json array clients: Array of ``Client`` ID
    :>json integer repository: ``Repository`` ID
    :>json integer schedule: ``Schedule`` ID
    :>json string policy_type: Policy Backup Type
    :>json integer keep_hourly: Number of hourly archives to keep
    :>json integer keep_daily: Number of daily archives to keep
    :>json integer keep_weekly: Number of weekly archives to keep
    :>json integer keep_monthly: Number of monthly archives to keep
    :>json integer keep_yearly: Number of yearly archives to keep
    :>json string vmprovider: Name of the VM module provider
    :>json boolean mode_pull: Backup in pull mode
    :>json boolean enabled: Policy enabled

    :statuscode 200: no error
    :statuscode 404: There is no ``Policy`` with this ID

.. http:patch::  /api/v1/policies/(int:id)/

    Update a single repository.

    .. sourcecode:: js

        {
            "name": "Main Repo",
            "path": "cyborgbackup@backup:/repository",
            "repository_key": "0123456789abcdef",
            "ready": true,
            "enabled": true
        }

    :>json string name: Policy name
    :>json string extra_vars: JSON Dictionnary of variable used by the system
    :>json array clients: Array of ``Client`` ID
    :>json integer repository: ``Repository`` ID
    :>json integer schedule: ``Schedule`` ID
    :>json string policy_type: Policy Backup Type
    :>json integer keep_hourly: Number of hourly archives to keep
    :>json integer keep_daily: Number of daily archives to keep
    :>json integer keep_weekly: Number of weekly archives to keep
    :>json integer keep_monthly: Number of monthly archives to keep
    :>json integer keep_yearly: Number of yearly archives to keep
    :>json string vmprovider: Name of the VM module provider
    :>json boolean mode_pull: Backup in pull mode
    :>json boolean enabled: Policy enabled

    :statuscode 200: no error
    :statuscode 404: There is no ``Policy`` with this ID

.. http:delete::  /api/v1/policies/(int:id)/

    Delete a single repository.

    :statuscode 200: no error
    :statuscode 404: There is no ``Policy`` with this ID

.. http:post::  /api/v1/policies/(int:id)/launch/

    Launch a backup job based on the policy.

    :statuscode 200: no error
    :statuscode 404: There is no ``Policy`` with this ID

.. http:get::  /api/v1/policies/(int:id)/calendar/

    Get all datetime of the current month for each run of the policy

    .. sourcecode:: js

      [DATETIME]

    :statuscode 200: no error
    :statuscode 404: There is no ``Policy`` with this ID

Catalogs API V1
-------------------

.. http:get::  /api/v1/catalogs/

    Retrieve a list of all catalogs entries.

    .. sourcecode:: js

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [CATALOGS]
        }

    :>json string next: URI for next set of Catalogs.
    :>json string previous: URI for previous set of Catalogs.
    :>json integer count: Total number of Catalogs.
    :>json array results: Array of ``Catalog`` objects.

.. http:get::  /api/v1/catalogs/(int:id)/

    Retrieve details of a single catalog entry.

    .. sourcecode:: js

        {
            "id": 1,
            "url": "/api/v1/catalogs/1/",
            "archive_name": "vm-lab.example.com-2018-11-23_22-02",
            "path": "stdin",
            "job": 1,
            "mode": "-rw-rw----",
            "mtime": "2018-11-23T23:03:52Z",
            "owner": "root",
            "group": "root",
            "size": 12,
            "healthy": true
        }

    :>json integer id: The ID of the catalog entry
    :>json string url: The URL access of the repository object.
    :>json string archive_name: The Borg Backup archive name
    :>json string path: Full path of the file in the archive
    :>json integer job: ``Job`` ID catalog entry related
    :>json string mode: Unix mode of the file
    :>json string mtime: Latest modification date of the file
    :>json string owner: Owner of the file
    :>json string group: Group of the file
    :>json integer size: Size of the file in Bytes
    :>json boolean healthy: Healthy state of the file

    :statuscode 200: no error
    :statuscode 404: There is no ``Repository`` with this ID
