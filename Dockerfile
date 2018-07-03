FROM chiao/docker-coupler:latest
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER root
WORKDIR $DOCKER_HOME

ARG BITBUCKET_PASS
ARG BITBUCKET_USER

ADD image $DOCKER_HOME/
ADD fix_ompi_dlopen /tmp
ADD source_foam /tmp

# install meshio
RUN apt-get update && \
    apt-get install -y patchelf

RUN sh /tmp/fix_ompi_dlopen

# libofm
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/libofm.git && \
    cd libofm && \
    sh /tmp/source_foam && \
    ./configure --python && \
    ./Allwmake

WORKDIR $DOCKER_HOME
USER root
