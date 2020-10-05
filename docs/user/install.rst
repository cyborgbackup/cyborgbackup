.. _install:

Installation of CyBorgBackup
============================

This part of the documentation covers the installation of CyBorgBackup.
The first step to using any software package is getting it properly installed.

Debian Package
--------------

A debian package have been build with CyBorgBackup latest release and can be downloaded from Releases github page::

    # apt install git postgresql-all elasticsearch rabbitmq-server python3-pip python3-virtualenv python3-setuptools python3-venv systemd nginx git
    # wget https://api.github.com/repos/cyborgbackup/cyborgbackup/releases/latest -O - |grep -oP '"browser_download_url": "\K(.*)(?=")' |wget -i -
    # dpkg -i cyborgbackup_X.X.X_all.deb

To add UI system :

    # wget https://api.github.com/repos/cyborgbackup/cyborgbackup-ui/releases/latest -O - |grep -oP '"browser_download_url": "\K(.*)(?=")' |wget -i -
    # dpkg -i cyborgbackup-ui_X.X.X_all.deb

*Note* : Elactic search is not provided from Debian repositorie, you need to follow first
`elasticsearch documentation <https://www.elastic.co/guide/en/elasticsearch/reference/7.6/deb.html>`_.


$ docker-compose up
-------------------

To install CyBorgBackup under Docker, simply run this simple command in your terminal of choice::

    $ wget https://raw.githubusercontent.com/cyborgbackup/cyborgbackup/master/docker-compose.full.yml -O docker-compose.yml
    $ cat > .env <<EOF
    POSTGRES_PASSWORD=cyborgbackup
    POSTGRES_USER=cyborgbackup
    POSTGRES_NAME=cyborgbackup
    POSTGRES_HOST=postgres
    RABBITMQ_DEFAULT_USER=cyborgbackup
    RABBITMQ_DEFAULT_PASS=cyborgbackup
    RABBITMQ_DEFAULT_VHOST=cyborgbackup
    EOF
    $ docker-compose up
    $ docker-compose exec web /bin/bash
    web$ python3 /cyborgbackup/manage.py loaddata settings
    web$ echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin@cyborg.local', 'admin')" | python3 /cyborgbackup/manage.py shell
    web$ exit


You can now connect to interface using : http://localhost:8000
If you don't have `docker-compose <https://docs.docker.com/compose/>`_ or `docker <https://www.docker.com/>`_ installed  head over to the website for installation instructions.

Get the Source Code
-------------------

CyBorgBackup is developed on GitHub, where the code is
`always available <https://github.com/cyborgbackup/cyborgbackup>`_.

You can either clone the public repository::

    $ git clone https://github.com/cyborgbackup/cyborgbackup.git

Or, download the `tarball <https://github.com/cyborgbackup/cyborgbackup/tarball/master>`_::

    $ curl -OL https://github.com/cyborgbackup/cyborgbackup/tarball/master
    # optionally, zipball is also available (for Windows users).

The UI interface can be found on Github, the the code is `always available <https://github.com/cyborgbackup/cyborgbackup-ui>`_.
And the public repository can be found at the following address::

    $ git clone https://github.com/cyborgbackup/cyborgbackup-ui.git

To build the UI docker image run the following::
    
    $ docker build --no-cache --pull -t cyborgbackup/cyborgbackup-ui:latest .


Depending of your system, CyBorgBackup need the following dependencies :

- python3
- python3-pip
- postgresql-server
- rabbitmq-server
- nginx

To use CyBorgBackup container with Docker, launch the following command::

    $ make cyborgbackup-docker-build
    $ make docker-compose-up


Connect to the interface
------------------------

Default account is :

- Login : admin@cyborg.local
- Password : admin
