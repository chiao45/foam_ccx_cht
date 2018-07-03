FROM chiao/docker-coupler:latest
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER $DOCKER_USER
WORKDIR $DOCKER_HOME

ARG BITBUCKET_PASS
ARG BITBUCKET_USER

ADD image $DOCKER_HOME/
ADD fix_ompi_dlopen /tmp
ADD source_foam /tmp

# install patchelf to fix openmpi2 dlopen issues that will crash python/matlab/java, etc
# see https://github.com/open-mpi/ompi/issues/3705
RUN sudo apt-get update && \
    sudo apt-get install -y patchelf

RUN sudo sh /tmp/fix_ompi_dlopen

# libofm
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/libofm.git && \
    cd libofm && \
    bash && \
    sh $DOCKER_HOME/.profile && \
    ./configure --python && \
    ./Allwmake

RUN sudo rm -rf /tmp/*

# RUN chown -R $DOCKER_USER:$DOCKER_GROUP $DOCKER_HOME

WORKDIR $DOCKER_HOME
USER root
