.. _install:

Installation of CyBorgBackup
============================

This part of the documentation covers the installation of CyBorgBackup.
The first step to using any software package is getting it properly installed.

Debian Package
--------------

A debian package have been build with CyBorgBackup latest release and can be downloaded from Releases github page::

    # apt install git postgresql-all elasticsearch rabbitmq-server python3-pip python3-virtualenv python3-setuptools python3-venv supervisor nginx
    # wget https://api.github.com/repos/cyborgbackup/cyborgbackup/releases/latest -O - |grep -oP '"browser_download_url": "\K(.*)(?=")' |wget -i -
    # dpkg -i cyborgbackup_X.X.X_all.deb

*Note* : Elactic search is not provided from Debian repositorie, you need to follow first 
`elasticsearch documentation <https://www.elastic.co/guide/en/elasticsearch/reference/7.6/deb.html>`_.

Docker
-------------------

Currently no ready-to-use docker images are available. Images will become available in the near future.

Get the Source Code
-------------------

CyBorgBackup is developed on GitHub, where the code is
`always available <https://github.com/cyborgbackup/cyborgbackup>`_.

You can either clone the public repository::

    $ git clone https://github.com/cyborgbackup/cyborgbackup.git

Or, download the `tarball <https://github.com/cyborgbackup/cyborgbackup/tarball/master>`_::

    $ curl -OL https://github.com/cyborgbackup/cyborgbackup/tarball/master
    # optionally, zipball is also available (for Windows users).

Depending of your system, CyBorgBackup need the following dependencies :

- python3
- python3-pip
- postgresql-server
- rabbitmq-server
- nginx

To use CyBorgBackup container with Docker, launch the following command::

    $ make docker
    $ make docker-compose-up


Connect to the interface
------------------------

Account default is :

- admin@cyborg.local
- admin
