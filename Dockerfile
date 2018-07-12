FROM unifem/coupler-desktop:latest as base
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER root
WORKDIR $DOCKER_HOME

ARG BITBUCKET_PASS
ARG BITBUCKET_USER

ADD fix_ompi_dlopen /tmp

# install patchelf to fix openmpi2 dlopen issues that will crash python/matlab/java, etc
# see https://github.com/open-mpi/ompi/issues/3705
RUN apt-get update && \
    apt-get install -y patchelf && \
    pip3 install -U meshio

# fix dlopen with openmpi
RUN sh /tmp/fix_ompi_dlopen && rm -rf /tmp/fix_ompi_dlopen

# pydtk2
# make sure add env CC=mpicxx
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/pydtk2.git ./apps/pydtk2

# lbcalculix
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/libcalculix.git ./apps/libcalculix

RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/pyccx.git ./apps/pyccx

# libofm
RUN git clone --depth=1 https://${BITBUCKET_USER}:${BITBUCKET_PASS}@bitbucket.org/${BITBUCKET_USER}/libofm.git ./home_apps/libofm

RUN chown -R $DOCKER_USER:$DOCKER_GROUP $DOCKER_HOME

WORKDIR $DOCKER_HOME
USER root

# second stage
FROM unifem/coupler-desktop:latest
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER root
WORKDIR /tmp

ADD image $DOCKER_HOME/

COPY --from=base $DOCKER_HOME/apps .
COPY --from=base $DOCKER_HOME/home_apps $DOCKER_HOME/

RUN cd pydtk2 && env CC=mpicxx python3 setup.py install
RUN cd libcalculix && make && make install
RUN cd pyccx && python3 setup.py install
RUN echo ". /opt/openfoam5/etc/bashrc\n./configure --python\n./Allwmake\n" > $DOCKER_HOME/libofm/install.sh && \
    cd $DOCKER_HOME/libofm && \
    bash ./install.sh && rm -rf libofm

RUN rm -rf /tmp/*

RUN chown -R $DOCKER_USER:$DOCKER_GROUP $DOCKER_HOME

WORKDIR $DOCKER_HOME
USER root
