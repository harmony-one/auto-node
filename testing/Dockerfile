FROM ubuntu:18.04

SHELL ["/bin/bash", "-c"]

RUN apt update && apt upgrade -y && apt install libgmp-dev libssl-dev vim silversearcher-ag curl sudo -y && \
    adduser user && \
    echo "user ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/user && \
    chmod 0440 /etc/sudoers.d/user

RUN useradd -m docker && echo "docker:docker" | chpasswd && adduser docker sudo

USER user

CMD /bin/bash

WORKDIR /home/user