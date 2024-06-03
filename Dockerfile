# note that this Dockerfile is meant for notebooks at Binder, you can install this package directly, or to virtualenv, you do not need docker
# https://github.com/jupyter/docker-stacks/blob/master/scipy-notebook/Dockerfile
# https://mybinder.readthedocs.io/en/latest/tutorials/dockerfile.html#preparing-your-dockerfile
#
# # How to use localy:
# # * note that if you use sudo you are running program as a superuser an not as an actual user
# NB_USER=$USER
# docker build  --build-arg NB_USER=$NB_USER  --build-arg NB_UID=`id -u $NB_USER` -t nic30/hwthls .
# docker run -it --rm -p 8888:8888 nic30/hwthls jupyter-lab --port=8888 --ip=0.0.0.0

FROM ubuntu:rolling

# [mybinder specific]
# https://github.com/binder-examples/minimal-dockerfile
ARG NB_USER=jovyan
ARG NB_UID=1000
ENV USER ${NB_USER}
ENV NB_UID ${NB_UID}
ENV HOME /home/${NB_USER}

RUN adduser --disabled-password \
    --gecos "Default user" \
    --uid ${NB_UID} \
    ${NB_USER}

USER root
RUN apt update && \
	DEBIAN_FRONTEND="noninteractive" apt install python3 python3-pip python3-dev llvm-18 llvm-18-dev libreadline-dev npm -y
RUN pip3 install jupyterlab jupyterlab-lsp 'python-lsp-server[all]' jupyterlab-system-monitor
RUN jupyter labextension install @deathbeds/jupyterlab_graphviz

# debug print versions
RUN python3 --version
RUN jupyter --version
RUN node --version
RUN free

# [mybinder specific]
# Make sure the contents of our repo are in ${HOME}
COPY . ${HOME}
RUN chown -R ${NB_UID} ${HOME}
USER ${NB_USER}
#USER root
WORKDIR ${HOME}

RUN pip3 install git+https://github.com/dnicolodi/pip.git@debian-scheme
ENV PATH /home/${NB_USER}/.local/bin/:$PATH
# install fresh dependencies from git (not required, there are pip packages)
RUN pip3 install -r doc/requirements.txt
# install this library
RUN pip3 install .
# rm main package folder so it does not interfere with the installation
RUN rm hwtHls/ -r

# [mybinder specific]
#USER ${NB_USER}
#RUN jupyter trust examples/*.ipynb

