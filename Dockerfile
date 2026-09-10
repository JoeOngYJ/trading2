FROM python:3.12-slim AS platform

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src
RUN pip install --no-cache-dir .
COPY migrations /app/migrations
COPY config /app/config

RUN useradd --create-home --uid 10001 platform \
    && mkdir -p /signals /artifacts /home/platform/.tradingagents \
    && chown -R platform:platform /signals /artifacts /home/platform
USER platform

FROM platform AS worker-tradingagents
ARG TRADINGAGENTS_REF=01477f9afb7a47b849ed4c9259d3a9a4738d9fda
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir "git+https://github.com/TauricResearch/TradingAgents.git@${TRADINGAGENTS_REF}" \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*
RUN platform-capture-audit
USER platform
