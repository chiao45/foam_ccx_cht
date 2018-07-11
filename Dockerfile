FROM unifem/coupler-desktop:latest
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
    apt-get install -y patchelf && \
    pip3 install -U meshio

# fix dlopen with openmpi
RUN sh /tmp/fix_ompi_dlopen && rm -rf /tmp/fix_ompi_dlopen

# pydtk2
# make sure add env CC=mpicxx
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/pydtk2.git && \
    cd pydtk2 && \
    env CC=mpicxx python3 setup.py install

# lbcalculix
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/libcalculix.git && \
    cd libcalculix && \
    make && \
    make install

RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/pyccx.git && \
    cd pyccx && \
    python3 setup.py install

# libofm
RUN env BITBUCKET_PASS=$BITBUCKET_PASS BITBUCKET_USER=$BITBUCKET_USER ./install_libofm

RUN chown -R $DOCKER_USER:$DOCKER_GROUP $DOCKER_HOME

WORKDIR $DOCKER_HOME
USER root
