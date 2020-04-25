.DEFAULT_GOAL := ui-build

node-build:
	npm install
	npm install --unsafe-perm -g glup
	npm install -g bower
	npm install -g gulp-cli
	bower install --allow-root

docker-build:
	cd /src
	npm install
	npm install --unsafe-perm -g glup
	npm install -g bower
	npm install -g gulp-cli
	bower install --allow-root

gulp-release: docker-build
	gulp

gulp-dev: docker-build
	gulp dev-release

clean-static:
	rm -Rf ${CURDIR}/../../static
	mkdir -p ${CURDIR}/../../templates/ui/

clean:
	#rm -Rf node_modules
	rm -f package-lock.json

clean-build:
	rm -Rf ${CURDIR}/bower_components
	rm -Rf ${CURDIR}/dev-release
	rm -Rf ${CURDIR}/release
	rm -Rf ${CURDIR}/.tmp

build: gulp-release clean

dev: gulp-dev clean

watch: gulp-dev
	gulp watch

docker-make-dev:
	docker run --rm -it -v ${CURDIR}:/src node:8.16.2 /bin/bash -c 'cd /src; make dev'

docker-make-prod:
	docker run -it -v ${CURDIR}:/src node:8.16.2 /bin/bash -c 'cd /src; make build'

install-dev:
	mkdir -p ${CURDIR}/../../static
	cd ${CURDIR}/src/ && find . -iname '*.html' -print0 |  rsync -0 -v --files-from=- . ${CURDIR}/../../static/
	cp -r ${CURDIR}/dev-release/* ${CURDIR}/../../static
	cp -r ${CURDIR}/bower_components ${CURDIR}/../../static
	cp -r ${CURDIR}/src/app ${CURDIR}/../../static/
	mv ${CURDIR}/../../static/index.html ${CURDIR}/../../templates/ui/
	cp -r ${CURDIR}/../static/* ${CURDIR}/../../static/
	$(MAKE) clean-build

install-prod:
	mkdir -p ${CURDIR}/../../static
	cd ${CURDIR}/src/ && find . -iname '*.html' -print0 |  rsync -0 -v --files-from=- . ${CURDIR}/../../static/
	cp -r ${CURDIR}/release/* ${CURDIR}/../../static
	mv ${CURDIR}/../../static/index.html ${CURDIR}/../../templates/ui/
	cp -r ${CURDIR}/../static/* ${CURDIR}/../../static/
	$(MAKE) clean-build

ui-build-dev: clean-static docker-make-dev install-dev

ui-build: clean-static docker-make-prod install-prod
