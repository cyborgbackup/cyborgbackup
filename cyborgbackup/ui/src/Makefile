.DEFAULT_GOAL := ui-build

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
	rm -Rf ${CURDIR}/../static
	mkdir -p ${CURDIR}/../../templates/ui/

clean:
	rm -Rf node_modules
	rm -f package-lock.json

clean-build:
	rm -Rf ${CURDIR}/bower_components
	rm -Rf ${CURDIR}/dev-release
	rm -Rf ${CURDIR}/release
	rm -Rf ${CURDIR}/.tmp

build: gulp-release clean

dev: gulp-dev clean

ui-build-dev: clean-static
	docker run --rm -it -v ${CURDIR}:/src node:latest /bin/bash -c 'cd /src; make dev'
	cp -r ${CURDIR}/dev-release ${CURDIR}/../static
	cp -r ${CURDIR}/bower_components ${CURDIR}/../static
	cp -r ${CURDIR}/src/app ${CURDIR}/../static/
	mv ${CURDIR}/../static/index.html ${CURDIR}/../../templates/ui/
	$(MAKE) clean-build

ui-build: clean-static
	docker run -it -v ${CURDIR}:/src node:latest /bin/bash -c 'cd /src; make build'
	cp -r ${CURDIR}/release ${CURDIR}/../static
	cp -r ${CURDIR}/bower_components ${CURDIR}/../static
	cp -r ${CURDIR}/src/app ${CURDIR}/../static/
	mv ${CURDIR}/../static/index.html ${CURDIR}/../../templates/ui/
	$(MAKE) clean-build
