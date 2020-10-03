.. CyBorgBackup documentation master file, created by
   sphinx-quickstart on Fri Nov 14 00:05:47 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

CyBorgBackup
============

Release v\ |version|. (:ref:`Installation <install>`)

.. image:: https://codecov.io/github/cyborgbackup/cyborgbackup/coverage.svg?branch=master
    :target: https://codecov.io/github/cyborgbackup/cyborgbackup
    :alt: codecov.io
.. image:: https://travis-ci.org/cyborgbackup/cyborgbackup.svg?branch=master
.. image:: https://readthedocs.org/projects/cyborgbackup/badge/?version=latest
.. image:: https://api.codacy.com/project/badge/Grade/29ad3c1de5f7405796ea9f8edc05b205
   :alt: Codacy Badge
   :target: https://www.codacy.com/gh/cyborgbackup/cyborgbackup?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=cyborgbackup/cyborgbackup&amp;utm_campaign=Badge_Grade


**CyBorgBackup** is a Web and API Interface to manage Borg Backup solution on
multiple servers based on Django and AngularJS frameworks.


-------------------

Features
--------

- Borg Backup system
- SSH Connection
- Scheduled job
- Local and Remote Borg Repository
- Catalog based on Borg Archive
- Restore Test
- Archive Size statistics
- Client and Repository preparation
- VM Backup Modules
- E-mail notification
- Auto-prune
- Logs system
- REST API

Underground
-----------

CyBorgBackup using the following tools ::

- PostgreSQL database
- ElasticSearch
- RabbitMQ messaging system
- Django framework
- Django REST Framework
- Celery and Beat
- AngularJS framework
- BorgBackup

CyBorgBackup have been separated in two project ::

- CyBorgBackup => The main API system
- CyBorgBackup-UI => The Web Interface who can manage multiple CyBorgBackup servers

The User Guide
--------------

.. toctree::
   :maxdepth: 2

   user/install
   user/screenshots
   user/quickstart
   user/provider


The API Documentation / Guide
-----------------------------

If you are looking for information on a specific function, class, or method,
this part of the documentation is for you.

.. toctree::
  :maxdepth: 2

  api


The Community Guide
-------------------

This part of the documentation details the CyBorgBackup community.

.. toctree::
   :maxdepth: 2

   community/support


The Contributor Guide
---------------------

If you want to contribute to the project, this part of the documentation is for
you.

.. toctree::
   :maxdepth: 3

   dev/todo
