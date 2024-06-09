FROM python:3.12 AS builder

ENV PYTHONUNBUFFERED 1
ENV DJANGO_ENV dev
ENV DOCKER_CONTAINER 1

COPY ./ /usr/src/

WORKDIR /usr/src

RUN pip install build setuptools
RUN python3 -m build -s

FROM python:3.12

ENV PYTHONUNBUFFERED 1
ENV DJANGO_ENV dev
ENV DOCKER_CONTAINER 1

RUN apt-get update && apt-get install -y --no-install-recommends borgbackup netcat-traditional && rm -Rf /var/lib/apt/lists/*

RUN groupadd -r cyborgbackup -g 1001 && \
    useradd -u 1001 -r -g cyborgbackup -s /bin/sh -c "CyBorgBackup Worker user" cyborgbackup

COPY --from=builder /usr/src/dist/*.tar.gz /root/cyborgbackup.tar.gz
COPY --from=builder /usr/src/requirements.txt /root/requirements.txt
RUN pip install -r /root/requirements.txt
RUN pip install /root/cyborgbackup.tar.gz

RUN mkdir -p /var/run/cyborgbackup && mkdir -p /var/tmp/cyborgbackup
RUN chown -R cyborgbackup /var/run/cyborgbackup /var/tmp/cyborgbackup

ADD tools/scripts/launch_cyborg.sh /usr/local/bin/launch_cyborg.sh
ADD tools/scripts/wait-for-migrations /usr/local/bin/wait-for-migrations

USER cyborgbackup

WORKDIR /cyborgbackup/

EXPOSE 8000
