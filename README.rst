CyBorgBackup
============

CyBorgBackup is a Web and API Interface to manage BorgBackup solution on multiple servers.

It is implemented using Python, Django and AngularJS.

The complete documentation can be found at <https://cyborgbackup.readthedocs.io>

Discussion
==========

* `Discord`_ - Real-time chat hosted by the CyBorgBackup community
* `GitHub Discussions`_ - Discussion form hosted by GitHub


Build Status
============

===========  =======  ============
Type         Branch   Status
===========  =======  ============
GitHub       master   |ci-master|
GitHub       develop  |ci-develop|
CodeCov      master   |codecov|
ReadTheDocs  master   |readthedocs|
===========  =======  ============

Features
========

- uses BorgBackup
- SSH Connection
- Scheduled jobs
- Local or Remote Borg Repository
- Catalog based on Borg Archives
- Restore Test
- Archive Size statistics
- Client and Repository preparation
- VM Backup Modules
- E-mail notification
- Auto-prune
- Logs system
- REST API

Installation
============

Please see `documentation`_ for
instructions on installing CyBorgBackup.

Providing Feedback
==================

The best platform for general feedback, assistance, and other discussion is our
`Github Discussions`_.
To report a bug or request a specific feature, please open a GitHub issue.

.. _documentation: https://cyborgbackup.readthedocs.io
.. _Discord: https://discord.gg/YqtkAbeYCG
.. _GitHub Discussions: https://github.com/cyborgbackup/cyborgbackup/discussions
.. |ci-develop| image:: https://github.com/cyborgbackup/cyborgbackup/actions/workflows/dockerimage-dev.yml/badge.svg
.. |ci-master| image:: https://github.com/cyborgbackup/cyborgbackup/actions/workflows/dockerimage.yml/badge.svg
.. |build| image:: https://travis-ci.org/cyborgbackup/cyborgbackup.svg?branch=master
.. |readthedocs| image:: https://readthedocs.org/projects/cyborgbackup/badge/?version=latest
.. |codecov| image:: https://codecov.io/gh/cyborgbackup/cyborgbackup/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/cyborgbackup/cyborgbackup
.. |codacy| image:: https://api.codacy.com/project/badge/Grade/29ad3c1de5f7405796ea9f8edc05b205
   :alt: Codacy Badge
   :target: https://www.codacy.com/gh/cyborgbackup/cyborgbackup?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=cyborgbackup/cyborgbackup&amp;utm_campaign=Badge_Grade