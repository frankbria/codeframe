# CodeFRAME web UI (#1121).
#
# Multi-stage: build with the full toolchain, ship only Next.js standalone
# output. The runner carries no node_modules tree and no source.
#
# NEXT_PUBLIC_* are BUILD ARGS, not runtime env, because Next.js inlines them
# into the client bundle at build time. That is why staging and production need
# separately tagged images — the decision the issue asked to be called out
# explicitly. The alternative (a runtime-config endpoint the client fetches
# before its first API call) is a bigger change to the web UI than the deploy
# migration itself.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# npm ci, not install: the lockfile is the contract. #1131 is a fresh reminder
# that a lockfile npm ci rejects passes every other local check.
RUN npm ci

# The audit gate from #1131, moved here by #1121. It used to run on the deploy
# host as part of build-on-server; deleting that step would have deleted the
# gate with it. In the image build it is stronger — an image carrying a high
# advisory does not get built at all, so it can never reach a host.
#
# `high`, not `critical`: at critical, six high-severity findings accumulated
# unnoticed until #1124 went looking. Audit results change without a code
# change, so a newly published high can block a build. That is the gate doing
# its job; the fix is to bump the dependency.
RUN npm audit --audit-level=high

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_WS_URL=""
ARG NEXT_PUBLIC_SSE_URL=""
# Also build-time: standalone output snapshots next.config.js rewrites into
# required-server-files.json, so a runtime BACKEND_ORIGIN is ignored. Inside
# compose the backend is a sibling service — `localhost` would be this
# container, and /api/* through the frontend 500s.
ARG BACKEND_ORIGIN="http://backend:14200"
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    NEXT_PUBLIC_SSE_URL=$NEXT_PUBLIC_SSE_URL \
    BACKEND_ORIGIN=$BACKEND_ORIGIN \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=14100 \
    HOSTNAME=0.0.0.0

RUN apk add --no-cache curl \
    && addgroup -g 10001 -S nodejs \
    && adduser -u 10001 -S nextjs -G nodejs

# `output: 'standalone'` emits a server.js plus exactly the node_modules it
# needs. public/ and .next/static are not included in it by design.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 14100

# See the backend Dockerfile: 0.0.0.0 inside, loopback-only when published.
CMD ["node", "server.js"]
