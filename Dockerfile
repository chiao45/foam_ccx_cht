FROM unifem/coupler-desktop:latest as base
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER root
WORKDIR $DOCKER_HOME

ARG SSH_KEY

ADD fix_ompi_dlopen /tmp

# install patchelf to fix openmpi2 dlopen issues that will crash python/matlab/java, etc
# see https://github.com/open-mpi/ompi/issues/3705
RUN apt-get update && \
    apt-get install -y patchelf && \
    pip3 install -U meshio

# fix dlopen with openmpi
RUN sh /tmp/fix_ompi_dlopen && rm -rf /tmp/fix_ompi_dlopen && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/tmp/*

RUN mkdir -p /root/.ssh && \
    echo ${SSH_KEY} > id_rsa_base64 && \
    cat id_rsa_base64 | base64 -d > /root/.ssh/id_rsa && \
    touch /root/.ssh/known_hosts && \
    ssh-keyscan bitbucket.org >> /root/.ssh/known_hosts && \
    rm -rf id_rsa_base64 && \
    git clone --depth=1 git@bitbucket.org:QiaoC/pydtk2.git ./apps/pydtk2 && \
    git clone -b parallel --depth=1 git@bitbucket.org:QiaoC/pydtk2.git ./apps/parpydtk2 && \
    git clone --depth=1 git@bitbucket.org:QiaoC/libcalculix.git ./apps/libcalculix && \
    git clone --depth=1 git@bitbucket.org:QiaoC/pyccx.git ./apps/pyccx && \
    git clone --depth=1 git@bitbucket.org:QiaoC/libofm.git ./apps/libofm && \
    rm -rf /root/.ssh/id_rsa && \
    chown -R $DOCKER_USER:$DOCKER_GROUP $DOCKER_HOME

WORKDIR $DOCKER_HOME
USER root

# second stage
FROM unifem/coupler-desktop:latest
LABEL maintainer "Qiao Chen <benechiao@gmail.com>"

USER root
WORKDIR /tmp

ADD image $DOCKER_HOME/

COPY --from=base $DOCKER_HOME/apps .

RUN cd pydtk2 && env CC=mpicxx python3 setup.py install && \
    rm -rf /tmp/pydtk2

RUN cd parpydtk2 && python3 setup.py install && \
    rm -rf /tmp/parpydtk2

RUN cd libcalculix && make && make install && rm -r /tmp/libcalculix

RUN cd pyccx && python3 setup.py install && rm -rf /tmp/pyccx

RUN echo ". /opt/openfoam5/etc/bashrc\n./configure --system --python\n./Allwmake\n" > libofm/install.sh && \
    cd libofm && \
    bash ./install.sh && rm -rf /tmp/libofm

RUN chown -R $DOCKER_USER:$DOCKER_GROUP $DOCKER_HOME

WORKDIR $DOCKER_HOME
USER root
