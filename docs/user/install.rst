.. _install:

Installation of CyBorgBackup
============================

This part of the documentation covers the installation of CyBorgBackup.
The first step to using any software package is getting it properly installed.


$ git clone && docker-compose up
--------------------------------

To install CyBorgBackup, simply run this simple command in your terminal of choice::

    $ git clone https://github.com/gaetanf/cyborgbackup
    $ docker-compose up


If you don't have `docker-compose <https://docs.docker.com/compose/>`_ or `docker <https://www.docker.com/>`_ installed  head over to the website for installation instructions.

Get the Source Code
-------------------

CyBorgBackup is developed on GitHub, where the code is
`always available <https://github.com/gaetanf/cyborgbackup>`_.

You can either clone the public repository::

    $ git clone https://://github.com/gaetanf/cyborgbackup.git

Or, download the `tarball <https://github.com/gaetanf/cyborgbackup/tarball/master>`_::

    $ curl -OL https://github.com/gaetanf/cyborgbackup/tarball/master
    # optionally, zipball is also available (for Windows users).

Depending of your system, CyBorgBackup need the following dependencies :

- python3
- python3-pip
- postgresql-server
- rabbitmq-server
- nginx

To use CyBorgBackup container with Docker, launch the following command::

    $ make docker
    $ make cyborgbackup-docker-compose-up
