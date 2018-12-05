#!/usr/bin/env python

import os
import glob
import sys
from setuptools import setup
from distutils.command.sdist import sdist


# Paths we'll use later
etcpath = "/etc/cyborgbackup"
homedir = "/var/lib/cyborgbackup"
bindir = "/usr/bin"
sharedir = "/usr/share/cyborgbackup"
docdir = "/usr/share/doc/cyborgbackup"


def get_version():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    version_file = os.path.join(current_dir, 'VERSION')
    with open(version_file, 'r') as file:
        return file.read().strip()


if os.path.exists("/etc/debian_version"):
    sysinit = "/etc/init.d"
    webconfig  = "/etc/nginx"
    siteconfig = "/etc/nginx/sites-enabled"
else:
    sysinit = "/etc/rc.d/init.d"
    webconfig  = "/etc/nginx"
    siteconfig = "/etc/nginx/sites-enabled"

#####################################################################
# Isolated packaging
#####################################################################


class sdist_isolated(sdist):
    includes = [
        'include VERSION',
        'include Makefile',
        'include cyborgbackup/__init__.py',
        'include cyborgbackup/main/expect/run.py',
    ]

    def __init__(self, dist):
        sdist.__init__(self, dist)
        dist.metadata.version = get_version()

    def get_file_list(self):
        self.filelist.process_template_line('include setup.py')
        for line in self.includes:
            self.filelist.process_template_line(line)
        self.write_manifest()

    def make_release_tree(self, base_dir, files):
        sdist.make_release_tree(self, base_dir, files)
        with open(os.path.join(base_dir, 'MANIFEST.in'), 'w') as f:
            f.write('\n'.join(self.includes))


#####################################################################
# Helper Functions


def explode_glob_path(path):
    """Take a glob and hand back the full recursive expansion,
    ignoring links.
    """

    result = []
    includes = glob.glob(path)
    for item in includes:
        if os.path.isdir(item) and not os.path.islink(item):
            result.extend(explode_glob_path(os.path.join(item, "*")))
        else:
            result.append(item)
    return result


def proc_data_files(data_files):
    """Because data_files doesn't natively support globs...
    let's add them.
    """

    result = []

    # If running in a virtualenv, don't return data files that would install to
    # system paths (mainly useful for running tests via tox).
    if hasattr(sys, 'real_prefix'):
        return result

    for dir,files in data_files:
        includes = []
        for item in files:
            includes.extend(explode_glob_path(item))
        result.append((dir, includes))
    return result

#####################################################################


setup(
    name=os.getenv('NAME', 'cyborgbackup'),
    version=get_version(),
    author='Gaëtan Ferez',
    author_email='gaetan.cyborgbackup@milkywan.fr',
    description='cyborgbackup: API, UI and Task Engine for Borg',
    long_description='CyBorgBackup provides a web-based user interface, REST API and '
                     'task engine built on top of Borg',
    license='Apache License 2.0',
    keywords='borg',
    url='http://github.com/GaetanF/cyborgbackup',
    packages=['cyborgbackup'],
    include_package_data=True,
    zip_safe=False,
    setup_requires=[],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators'
        'License :: Apache License 2.0',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Systems Administration',
    ],
    entry_points = {
        'console_scripts': [
            'cyborgbackup-manage = cyborgbackup:manage',
        ],
    },
    data_files = proc_data_files([
        ("%s" % homedir,        ["tools/config/wsgi.py",
                                 "cyborgbackup/static/assets/favicon.ico"]),
        ("%s" % webconfig,      ["tools/config/uwsgi_params"]),
        ("%s" % docdir,         ["docs/*",]),
        ("%s" % bindir, ["tools/scripts/cyborgbackup-service",
                         "tools/scripts/cyborgbackup-setup"]),
    cmdclass = {'sdist_isolated': sdist_isolated},
    options = {
        'aliases': {
            'dev_build': 'clean --all egg_info sdist',
            'release_build': 'clean --all egg_info -b "" sdist',
            'isolated_build': 'clean --all egg_info -b "" sdist_isolated',
        },
        'build_scripts': {
            'executable': '/usr/bin/cyborgbackup-python',
        },
    },
)
