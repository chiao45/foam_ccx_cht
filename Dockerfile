FROM chiao/docker-coupler:latest
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER root
WORKDIR $DOCKER_HOME

ARG BITBUCKET_PASS
ARG BITBUCKET_USER

ADD image $DOCKER_HOME/
ADD fix_ompi_dlopen /tmp
ADD install_libofm $DOCKER_HOME

# install patchelf to fix openmpi2 dlopen issues that will crash python/matlab/java, etc
# see https://github.com/open-mpi/ompi/issues/3705
RUN apt-get update && \
    apt-get install -y patchelf

RUN sh /tmp/fix_ompi_dlopen && rm -rf /tmp/fix_ompi_dlopen

# libofm
RUN env BITBUCKET_PASS=$BITBUCKET_PASS BITBUCKET_USER=$BITBUCKET_USER ./install_libofm

RUN chown -R $DOCKER_USER:$DOCKER_GROUP $DOCKER_HOME

WORKDIR $DOCKER_HOME
USER root
