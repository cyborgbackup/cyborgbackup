.. CyBorgBackup documentation master file, created by
   sphinx-quickstart on Fri Nov 14 00:05:47 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

CyBorgBackup
============

Release v\ |version|. (:ref:`Installation <install>`)

.. image:: https://img.shields.io/pypi/l/cyborgbackup.svg
    :target: https://pypi.org/project/requests/

.. image:: https://img.shields.io/pypi/wheel/cyborgbackup.svg
    :target: https://pypi.org/project/requests/

.. image:: https://img.shields.io/pypi/pyversions/cyborgbackup.svg
    :target: https://pypi.org/project/requests/

.. image:: https://codecov.io/github/gaetanf/cyborgbackup/coverage.svg?branch=master
    :target: https://codecov.io/github/gaetanf/cyborgbackup
    :alt: codecov.io


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
- RabbitMQ messaging system
- Django framework
- Django REST Framework
- Celery and Beat
- AngularJS framework
- BorgBackup


The User Guide
--------------

.. toctree::
   :maxdepth: 2

   user/install
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
