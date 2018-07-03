FROM chiao/docker-coupler:latest
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER $DOCKER_USER
WORKDIR $DOCKER_HOME

ARG BITBUCKET_PASS
ARG BITBUCKET_USER

ADD image $DOCKER_HOME/
ADD fix_ompi_dlopen /tmp

# install meshio
RUN sudo apt-get update && \
    sudo apt-get install -y patchelf

RUN sudo sh /tmp/fix_ompi_dlopen && rm -rf /tmp/fix_ompi_dlopen

# libofm
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/libofm.git && \
    cd libofm && \
    ./configure --python && \
    ./Allwmake

WORKDIR $DOCKER_HOME
USER root
