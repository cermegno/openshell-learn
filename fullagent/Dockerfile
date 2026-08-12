FROM python:3.12-slim

# iproute2: required for network namespace management (ip netns, veth pairs)
# nftables: optional, enables bypass detection (log + reject for direct connections)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl iproute2 nftables \
    && rm -rf /var/lib/apt/lists/*
RUN pip install flask langchain langchain-openai requests beautifulsoup4 

# OpenShell strictly mandates a user and group explicitly named sandbox
RUN groupadd --gid 1500 sandbox \
    && useradd --uid 1500 --gid sandbox -d /sandbox -m -s /bin/bash sandbox

RUN install -d -o sandbox -g sandbox /sandbox
WORKDIR /sandbox
COPY --chown=sandbox:sandbox ./sandbox .

EXPOSE 5000

# Docker and Podman use this non-root identity when policy omits either process
# identity field. OpenShell starts the supervisor as root and drops only agent
# children to this account.
USER sandbox

# NOTE: The sandbox supervisor replaces CMD at runtime if you pass the start
# command explicitly:  openshell sandbox create ... -- python3 /sandbox/app.py
CMD ["python3", "app.py"]
