.. _install:

Installation of CyBorgBackup
============================

The following covers three different installation methods of CyBorgBackup.

Debian Package
--------------

The latest release of CyBorgBackup is available as a Debian package and can be downloaded from github releases page::

    # apt install git postgresql-all rabbitmq-server python3-pip python3-virtualenv python3-setuptools python3-venv systemd nginx
    # wget https://api.github.com/repos/cyborgbackup/cyborgbackup/releases/latest -O - |grep -oP '"browser_download_url": "\K(.*)(?=")' |wget -i -
    # dpkg -i cyborgbackup_X.X.X_all.deb

To add UI system::

    # wget https://api.github.com/repos/cyborgbackup/cyborgbackup-ui/releases/latest -O - |grep -oP '"browser_download_url": "\K(.*)(?=")' |wget -i -
    # dpkg -i cyborgbackup-ui_X.X.X_all.deb

*Note* : MongoDB is not provided by the Debian repository, you need to follow
`mongodb documentation <https://docs.mongodb.com/manual/tutorial/install-mongodb-on-debian/>`_.


Docker Install
--------------

.. warning::

    The current Docker implementation are currently unstable. Use with caution.

To install CyBorgBackup under Docker, run this command in your terminal of choice::

    $ wget https://raw.githubusercontent.com/cyborgbackup/cyborgbackup/master/docker-compose.full.yml -O docker-compose.yml
    $ cat > .env <<EOF
    POSTGRES_PASSWORD=cyborgbackup
    POSTGRES_USER=cyborgbackup
    POSTGRES_NAME=cyborgbackup
    POSTGRES_HOST=postgres
    RABBITMQ_DEFAULT_USER=cyborgbackup
    RABBITMQ_DEFAULT_PASS=cyborgbackup
    RABBITMQ_DEFAULT_VHOST=cyborgbackup
    SECRET_KEY=$(openssl rand -base64 47|sed 's/=//g')
    EOF
    $ docker-compose up
    $ docker-compose exec api /bin/bash
    api$ python3 /cyborgbackup/manage.py loaddata settings
    api$ echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin@cyborg.local', 'admin')" | python3 /cyborgbackup/manage.py shell
    api$ exit


If you don't have `docker-compose <https://docs.docker.com/compose/>`_ or `docker <https://www.docker.com/>`_ installed, head over to the website for installation instructions.

Connecting to the interface
---------------------------
| You can connect to the CyBorgBackup interface at : http://localhost:8000
| Default account is :

- Login : admin@cyborg.local
- Password : admin

If your server can be accessed from Internet, you can use the following interface based on stable release : https://ui.cyborgbackup.dev