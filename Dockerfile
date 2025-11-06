# note that this Dockerfile is meant for notebooks at Binder, you can install this package directly, or to virtualenv, you do not need docker
# https://github.com/jupyter/docker-stacks/blob/master/scipy-notebook/Dockerfile
# https://mybinder.readthedocs.io/en/latest/tutorials/dockerfile.html#preparing-your-dockerfile
#
# # How to use localy:
# # * note that if you use sudo $USER=root
# NB_USER=$USER
# DOCKER_BUILDKIT=1 BUILDKIT_PROGRESS=plain docker build  --build-arg NB_USER=$NB_USER  --build-arg NB_UID=`id -u $NB_USER` -t nic30/hwthls .
# docker run -it --rm -p 8888:8888 nic30/hwthls jupyter-lab --port=8888 --ip=0.0.0.0

FROM ubuntu:rolling

# [mybinder specific]
# https://github.com/binder-examples/minimal-dockerfile
ARG NB_USER=jovyan
ARG NB_UID=1000
ENV USER ${NB_USER}
ENV NB_UID ${NB_UID}
ENV HOME /home/${NB_USER}

RUN useradd --non-unique  \
    --uid ${NB_UID} \
    ${NB_USER}

USER root
RUN DEBIAN_FRONTEND="noninteractive"\
	apt update && \
	apt upgrade -y && \
	apt install build-essential python3-dev llvm-21-dev python3 python3-pip python3-venv\
				git ninja-build cmake libreadline8 libreadline-dev pkg-config npm -y

RUN python3 -m venv /home/${NB_USER}/venv
RUN chown -R ${NB_UID} /home/${NB_USER}/venv
# Docker equivalent to source venv/bin/asctivate
ENV PATH="/home/${NB_USER}/venv/bin:/home/${NB_USER}/.local/bin/:$PATH"

# [mybinder specific]
# Make sure the contents of our repo are in ${HOME}
USER ${NB_USER}
WORKDIR ${HOME}

RUN pip install --upgrade pip
RUN python --version  &&\
	pip --version     &&\
    free

RUN pip install jupyterlab jupyterlab-lsp 'python-lsp-server[all]' jupyterlab-system-monitor
RUN jupyter labextension install @deathbeds/jupyterlab_graphviz

# debug print versions
RUN	jupyter --version &&\
	node --version

COPY --chown=${NB_UID} . ${HOME}
# install fresh dependencies from git (not required, there are pip packages)
RUN pip install -r doc/requirements.txt
# install this library
RUN pip install . --verbose --verbose
# rm main package folder so it does not interfere with the installation
RUN rm hwtHls/ -r

# [mybinder specific]
#USER ${NB_USER}
#RUN jupyter trust examples/*.ipynb

