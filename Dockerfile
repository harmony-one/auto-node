FROM ubuntu:18.04

SHELL ["/bin/bash", "-c"]

WORKDIR /root

RUN apt update && apt upgrade -y && apt install psmisc dnsutils curl python3 python3-pip tmux -y

RUN mkdir -p /root/node

COPY root /root

RUN chmod +x /root/docker-setup.sh && ./docker-setup.sh && rm ./docker-setup.sh && rm ./setup.py

ENTRYPOINT ["/root/run.sh"]