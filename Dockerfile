FROM python:3.8

ENV PYTHONUNBUFFERED 1
ENV DJANGO_ENV dev
ENV DOCKER_CONTAINER 1

COPY ./requirements.txt /cyborgbackup/requirements.txt
RUN pip install -r /cyborgbackup/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends borgbackup

RUN groupadd -r cyborgbackup -g 101 && \
    useradd -u 101 -r -g cyborgbackup -s /bin/sh -c "CyBorgBackup Worker user" cyborgbackup

COPY ./src/ /cyborgbackup/

RUN mkdir -p /cyborgbackup/var/run
RUN mkdir -p /var/tmp/cyborgbackup
RUN chown -R cyborgbackup /cyborgbackup
RUN chown -R cyborgbackup /var/tmp/cyborgbackup

USER cyborgbackup

WORKDIR /cyborgbackup/

EXPOSE 8000
