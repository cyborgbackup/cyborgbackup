PYTHON ?= python3
PYTHON_VERSION = $(shell $(PYTHON) -c "from distutils.sysconfig import get_python_version; print(get_python_version())")
SITELIB=$(shell $(PYTHON) -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")
OFFICIAL ?= no
PACKER ?= packer
PACKER_BUILD_OPTS ?= -var 'official=$(OFFICIAL)' -var 'mp_repo_url=$(MP_REPO_URL)'
NODE ?= node
NPM_BIN ?= npm
DEPS_SCRIPT ?= packaging/bundle/deps.py
GIT_BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD)
MANAGEMENT_COMMAND ?= cyborgbackup-manage

VERSION=$(shell git describe --long --first-parent)
VERSION3=$(shell git describe --long --first-parent | sed 's/\-g.*//')
VERSION3DOT=$(shell git describe --long --first-parent | sed 's/\-g.*//' | sed 's/\-/\./')
RELEASE_VERSION=$(shell git describe --long --first-parent | sed 's@\([0-9.]\{1,\}\).*@\1@')

# NOTE: This defaults the container image version to the branch that's active
COMPOSE_TAG ?= $(GIT_BRANCH)
COMPOSE_HOST ?= $(shell hostname)

VENV_BASE ?= ./venv
SCL_PREFIX ?=
CELERY_SCHEDULE_FILE ?= /var/lib/cyborgbackup/beat.db

DEV_DOCKER_TAG_BASE ?= gcr.io/cyborgbackup-engineering
# Python packages to install only from source (not from binary wheels)
# Comma separated list
SRC_ONLY_PKGS ?= cffi,pycparser,psycopg2,twilio

CURWD = $(shell pwd)

# Determine appropriate shasum command
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
	SHASUM_BIN ?= sha256sum
endif
ifeq ($(UNAME_S),Darwin)
	SHASUM_BIN ?= shasum -a 256
endif

# Get the branch information from git
GIT_DATE := $(shell git log -n 1 --format="%ai")
DATE := $(shell date -u +%Y%m%d%H%M)

NAME ?= cyborgbackup
GIT_REMOTE_URL = $(shell git config --get remote.origin.url)

ifeq ($(OFFICIAL),yes)
	VERSION_TARGET ?= $(RELEASE_VERSION)
else
	VERSION_TARGET ?= $(VERSION3DOT)
endif

# TAR build parameters
ifeq ($(OFFICIAL),yes)
	SDIST_TAR_NAME=$(NAME)-$(RELEASE_VERSION)
	WHEEL_NAME=$(NAME)-$(RELEASE_VERSION)
else
	SDIST_TAR_NAME=$(NAME)-$(VERSION3DOT)
	WHEEL_NAME=$(NAME)-$(VERSION3DOT)
endif

SDIST_COMMAND ?= sdist
WHEEL_COMMAND ?= bdist_wheel
SDIST_TAR_FILE ?= $(SDIST_TAR_NAME).tar.gz
WHEEL_FILE ?= $(WHEEL_NAME)-py2-none-any.whl

DEVVERSION:
	@echo "0.3-dev" > VERSION

clean-ui:
	rm -rf src/cyborgbackup/ui/src/node_modules
	rm -rf src/cyborgbackup/ui/src/bower_components
	rm -rf src/cyborgbackup/ui/src/dev-release
	rm -rf src/cyborgbackup/ui/src/release

clean-tmp:
	rm -rf tmp/

clean-venv:
	rm -rf venv/

clean-dist:
	rm -rf dist

# Remove temporary build files, compiled Python files.
clean: clean-ui clean-dist
	rm -rf src/cyborgbackup/job_output
	rm -rf src/job_output
	rm -rf requirements/vendor
	rm -rf tmp
	mkdir tmp
	find . -type f -regex ".*\.py[co]$$" -delete
	find . -type d -name "__pycache__" -delete

initenv:
	echo "POSTGRES_HOST=postgres" > .env
	echo "POSTGRES_PASSWORD=cyborgbackup" >> .env
	echo "POSTGRES_USER=cyborgbackup" >> .env
	echo "POSTGRES_NAME=cyborgbackup" >> .env
	echo "RABBITMQ_DEFAULT_USER=cyborgbackup" >> .env
	echo "RABBITMQ_DEFAULT_PASS=cyborgbackup" >> .env
	echo "RABBITMQ_DEFAULT_VHOST=cyborgbackup" >> .env
	echo "SECRET_KEY=$(openssl rand -base64 47|sed 's/=//g')" >> .env
	echo "MONGODB_HOST=mongodb" >> .env

deb:
	apt update && apt install -y build-essential debhelper
	make -f debian/rules binary
	make -f debian/rules clean
	cp /*.deb ./

package:
	docker run --rm -it -v ${CURDIR}:/src debian:latest /bin/bash -c 'cd /src && apt update && apt install -y make && make deb'

cyborgbackup-docker-build:
	docker build -t cyborgbackup/cyborgbackup:latest .

docker-compose-up: initenv
	docker-compose up -d

docker-compose-dev:
	docker-compose -f tools/docker-compose-dev/docker-compose.yml --project-directory . up

docker: cyborgbackup-docker-build
