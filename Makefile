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

UI_DIR = cyborgbackup/ui/src

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

VERSION:
	@echo $(VERSION_TARGET) > $@
	@echo "cyborgbackup: $(VERSION_TARGET)"

clean-ui:
	rm -rf cyborgbackup/ui/static
	rm -rf cyborgbackup/ui/src/node_modules
	rm -rf cyborgbackup/ui/src/bower_components
	rm -rf cyborgbackup/ui/src/dev-release
	rm -rf cyborgbackup/ui/src/release

clean-tmp:
	rm -rf tmp/

clean-venv:
	rm -rf venv/

clean-dist:
	rm -rf dist

# Remove temporary build files, compiled Python files.
clean: clean-ui clean-dist
	rm -rf cyborgbackup/job_output
	rm -rf job_output
	rm -rf requirements/vendor
	rm -rf tmp
	rm -f VERSION
	mkdir tmp
	rm -rf build $(NAME)-$(VERSION) *.egg-info
	find . -type f -regex ".*\.py[co]$$" -delete
	find . -type d -name "__pycache__" -delete

# Create Django superuser.
adduser:
	$(MANAGEMENT_COMMAND) createsuperuser

# Create database tables and apply any new migrations.
migrate:
	if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	$(MANAGEMENT_COMMAND) migrate --noinput

# Run after making changes to the models to create a new migration.
dbchange:
	$(MANAGEMENT_COMMAND) makemigrations

# access database shell, asks for password
dbshell:
	sudo -u postgres psql -d cyborgbackup-dev

server_noattach:
	tmux new-session -d -s cyborgbackup 'exec make uwsgi'
	tmux rename-window 'CyBorgBackup'
	tmux select-window -t cyborgbackup:0
	tmux split-window -v 'exec make celeryd'
	tmux new-window 'exec make daphne'
	tmux select-window -t cyborgbackup:1
	tmux rename-window 'WebSockets'
	tmux split-window -h 'exec make runworker'
	tmux split-window -v 'exec make nginx'
	tmux new-window 'exec make receiver'
	tmux select-window -t cyborgbackup:2
	tmux rename-window 'Extra Services'
	tmux select-window -t cyborgbackup:0

server: server_noattach
	tmux -2 attach-session -t cyborgbackup

# Use with iterm2's native tmux protocol support
servercc: server_noattach
	tmux -2 -CC attach-session -t cyborgbackup

flower:
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	celery flower --address=0.0.0.0 --port=5555 --broker=amqp://guest:guest@$(RABBITMQ_HOST):5672//

collectstatic:
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	mkdir -p cyborgbackup/public/static && $(PYTHON) manage.py collectstatic --clear --noinput > /dev/null 2>&1

uwsgi: collectstatic
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	uwsgi -b 32768 --socket 127.0.0.1:8050 --module=cyborgbackup.wsgi:application --home=/venv/cyborgbackup --chdir=/cyborgbackup_devel/ --vacuum --processes=5 --harakiri=120 --master --no-orphans --py-autoreload 1 --max-requests=1000 --stats /tmp/stats.socket --lazy-apps --logformat "%(addr) %(method) %(uri) - %(proto) %(status)" --hook-accepting1-once="exec:/bin/sh -c '[ -f /tmp/celery_pid ] && kill -1 `cat /tmp/celery_pid` || true'"

daphne:
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	daphne -b 127.0.0.1 -p 8051 cyborgbackup.asgi:channel_layer

runworker:
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	$(PYTHON) manage.py runworker --only-channels websocket.*

# Run the built-in development webserver (by default on http://localhost:8013).
runserver:
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	$(PYTHON) manage.py runserver

# Run to start the background celery worker for development.
celeryd:
	rm -f /tmp/celery_pid
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	celery worker -A cyborgbackup -B -Ofair --autoscale=100,4 --schedule=$(CELERY_SCHEDULE_FILE) -n celery@$(COMPOSE_HOST) --pidfile /tmp/celery_pid

# Run to start the background celery worker for development.
celery_beat:
	rm -f /tmp/celerybeat.pid
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	celery beat -A cyborgbackup --pidfile /tmp/celerybeat.pid

# Run to start the zeromq callback receiver
receiver:
	@if [ "$(VENV_BASE)" ]; then \
		. $(VENV_BASE)/cyborgbackup/bin/activate; \
	fi; \
	$(PYTHON) manage.py run_callback_receiver

nginx:
	nginx -g "daemon off;"

initenv:
	echo "POSTGRES_PASSWORD=cyborgbackup" > .env
	echo "POSTGRES_PASSWORD=cyborgbackup" >> .env
	echo "POSTGRES_USER=cyborgbackup" >> .env
	echo "POSTGRES_NAME=cyborgbackup" >> .env
	echo "RABBITMQ_DEFAULT_USER=cyborgbackup" >> .env
	echo "RABBITMQ_DEFAULT_PASS=cyborgbackup" >> .env
	echo "RABBITMQ_DEFAULT_VHOST=cyborgbackup" >> .env

cyborgbackup-ui:
	$(MAKE) -C $(UI_DIR)

cyborgbackup-docker-build:
	docker build -t cyborgbackup:latest .

cyborgbackup-docker-compose-up: initenv
	docker-compose up -d
	sleep 5
	docker-compose exec web python3 manage.py migrate
	docker-compose exec web python3 manage.py create_preload_data

docker: cyborgbackup-ui cyborgbackup-docker-build
