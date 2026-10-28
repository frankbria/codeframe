# Clean machine for the #614 quick-start validation.
#
# Deliberately minimal: the issue's premise is "only Python 3.11+, uv, and an
# ANTHROPIC_API_KEY". Nothing CodeFRAME-specific is baked in — installing it is
# the first thing under test. git is here because `cf init` initializes a repo.
#
# Claude Code is here for the plugin path: the README's first screen installs
# proof9 into it, so a visitor taking that path already has it.
FROM python:3.11-slim

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Claude Code, pinned to the version CI tests the plugin against
# (.github/workflows/test.yml); tests/ci/test_cleanroom_plugin_path.py keeps the
# two equal. The plugin itself is NOT baked in: installing it from the published
# marketplace is a step under test.
ARG CLAUDE_CODE_VERSION=2.1.301
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null \
    && apt-get install -y -qq --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --silent "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"

# A first-time user has no git identity; `cf init`/`cf commit` need one.
RUN git config --global user.email "cleanroom@example.com" \
    && git config --global user.name "Cleanroom User" \
    && git config --global init.defaultBranch main \
    && git config --global --add safe.directory /src

WORKDIR /work
COPY walkthrough.sh /walkthrough.sh
# The project brief the stand-in user answers from, via `cf prd generate
# --brief-file`. Only the brief is baked in; the answering is a shipped code
# path, not something this harness implements.
COPY brief.md /brief.md
RUN chmod +x /walkthrough.sh
ENTRYPOINT ["/walkthrough.sh"]
