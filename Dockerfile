FROM chiao/docker-coupler:latest
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER root
WORKDIR $DOCKER_HOME

ARG BITBUCKET_PASS
ARG BITBUCKET_USER

ADD image $DOCKER_HOME/
ADD fix_ompi_dlopen /tmp

# install meshio
RUN apt-get update && \
    pip3 install -U meshio && \
    apt-get install -y patchelf

RUN sh /tmp/fix_ompi_dlopen && rm -rf /tmp/fix_ompi_dlopen

# libofm
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/libofm.git && \
    cd libofm && \
    ./configure --python && \
    ./Allwmake

RUN chown -R $DOCKER_USER:$DOCKER_GROUP $DOCKER_HOME

WORKDIR $DOCKER_HOME
USER root
