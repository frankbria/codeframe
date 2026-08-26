# Clean machine for the #614 quick-start validation.
#
# Deliberately minimal: the issue's premise is "only Python 3.11+, uv, and an
# ANTHROPIC_API_KEY". Nothing CodeFRAME-specific is baked in — installing it is
# the first thing under test. git is here because `cf init` initializes a repo.
FROM python:3.11-slim

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

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
