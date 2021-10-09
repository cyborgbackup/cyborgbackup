FROM python:3.8

ENV PYTHONUNBUFFERED 1
ENV DJANGO_ENV dev
ENV DOCKER_CONTAINER 1

COPY ./requirements.txt /cyborgbackup/requirements.txt
RUN pip install -r /cyborgbackup/requirements.txt
RUN apt-get update && apt-get install -y borgbackup

COPY ./src/ /cyborgbackup/

RUN mkdir -p /cyborgbackup/var/run

WORKDIR /cyborgbackup/

EXPOSE 8000
