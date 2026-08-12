# CodeFRAME backend (#1121).
#
# Replaces build-on-server: the image is built in CI from a locked dependency
# set, so a deploy is a pull-and-restart with nothing to fail halfway. The PM2
# shape it retires could leave the box holding new code and a dead process.
#
# Layer order is deliberate — dependencies before source, so a code-only change
# reuses the (slow) uv sync layer.

FROM python:3.11-slim AS base

# git is a RUNTIME dependency, not a build one: core/workspace and the sandbox
# create repos and worktrees under WORKSPACE_ROOT. curl serves the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# --frozen: fail if uv.lock disagrees with pyproject rather than silently
# resolving something else. An image built from a drifted lock is not the thing
# CI tested.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY codeframe/ ./codeframe/
RUN uv sync --frozen --no-dev

# Non-root. WORKSPACE_ROOT and the SQLite DB arrive as volumes owned by this
# uid (compose sets it), so the app can still write where it must and nowhere
# else.
RUN useradd --create-home --uid 10001 codeframe \
    && mkdir -p /data /workspaces \
    && chown -R codeframe:codeframe /data /workspaces /app
USER codeframe

EXPOSE 14200

# 0.0.0.0 INSIDE the container is correct — the container network is private.
# What keeps the backend off the public internet is the compose port binding
# (127.0.0.1:14200:14200), which is the containerised form of the #747 rule
# that the TLS proxy is the sole public listener. Do not publish this on
# 0.0.0.0 in any compose file.
CMD ["python", "-m", "codeframe.ui.server", "--host", "0.0.0.0", "--port", "14200"]
