# Deployment: TLS reverse proxy

CodeFRAME runs two processes behind a **TLS-terminating reverse proxy** (issue #747):

| Process  | Binds            | Public? |
|----------|------------------|---------|
| Backend  | `127.0.0.1:14200` | no — loopback only |
| Frontend | `127.0.0.1:14100` | no — loopback only |
| Caddy    | `:80`, `:443`     | **yes** — the only public listener |

Because the app processes bind loopback, JWT bearer tokens and API keys only
ever travel over HTTPS/WSS between the browser and Caddy. Plaintext
`http://`/`ws://` is confined to the loopback hop, which never leaves the host.

## Setup

`scripts/remote-setup.sh` installs Caddy and points you here. Manually:

1. Point your domain's DNS `A`/`AAAA` record at the server.
2. Copy the config and set your domain:
   ```bash
   sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
   sudo $EDITOR /etc/caddy/Caddyfile   # replace codeframe.example.com
   sudo systemctl reload caddy
   ```
   Caddy provisions and renews the Let's Encrypt certificate automatically.
3. Set the public origins in `.env.staging` / `.env.production`:
   ```
   NEXT_PUBLIC_API_URL=https://your-domain
   NEXT_PUBLIC_WS_URL=wss://your-domain
   CORS_ALLOWED_ORIGINS=https://your-domain
   HOST=127.0.0.1
   ```
4. Firewall: allow `80`/`443` only. The app ports (`14100`/`14200`) must **not**
   be reachable from the network — Caddy reaches them over loopback.

## Creating the first account

`POST /auth/register` is how the very first account is made, so it cannot itself
require a login — and Caddy publishes `/auth/*`. Left ungated, a fresh deploy is
claimable by whoever reaches it first, with `[read, write, admin]` (issue #897).

The route is therefore gated two ways, and **at least one must hold**:

| Gate | When it applies |
|---|---|
| `X-Bootstrap-Token` header matching `CODEFRAME_BOOTSTRAP_TOKEN` | Whenever the variable is set — including for loopback callers |
| Request originates on the server host itself | Only when `CODEFRAME_BOOTSTRAP_TOKEN` is unset |

"Originates on the host" means a loopback peer **with no proxy in the path** —
a request arriving through Caddy carries the real client IP in
`X-Forwarded-For`, so public traffic never qualifies. `X-Real-IP` and RFC 7239
`Forwarded` are inspected too, and this does not depend on
`RATE_LIMIT_TRUSTED_PROXIES` being configured.

> **Set the token if you front the app with anything other than the Caddy
> config shipped here.** The loopback fallback identifies public callers by the
> client IP the proxy appends; a proxy that strips or passes client headers
> through unchanged (`proxy_set_header X-Forwarded-For "";`, a raw TCP
> passthrough) would let a remote client send `X-Forwarded-For: 127.0.0.1` and
> pass. With `CODEFRAME_BOOTSTRAP_TOKEN` set, none of that matters.

Registration still closes permanently once the first real account exists, token
or not. The seeded `admin@localhost` row has a disabled password, cannot log in,
and does not count as that account.

That first account is also the instance's **admin** (`is_superuser`), and it is
the only one — admin scope is what gates credential storage, GitHub PAT storage
and PR merge (issue #898). A session for any later, non-superuser account gets
`[read, write]` and is refused on those endpoints. Grant admin to another
account by setting `is_superuser = 1` on its `users` row in the control-plane
DB; there is no in-product promotion flow yet.

**Set the token before the first deploy** — it is in `.env.production.example` /
`.env.staging.example`:

```bash
openssl rand -hex 32          # → CODEFRAME_BOOTSTRAP_TOKEN in your .env.<stage>
```

Then create the account one of two ways.

**From the server host** (simplest — the CLI reads the env var):

```bash
ssh your-server
cd /path/to/codeframe
set -a; . ./.env.production; set +a          # exports CODEFRAME_BOOTSTRAP_TOKEN
# Point the CLI at the loopback backend — its default is :8080, not your
# BACKEND_PORT. This hits the app directly, bypassing Caddy.
CODEFRAME_API_URL="http://127.0.0.1:${BACKEND_PORT:-8000}" \
  codeframe auth register --email you@example.com
```

(`--bootstrap-token` overrides the env var if you would rather pass it inline.)

**From your browser**, at `https://your-domain/login` → *"First time here? Create
the first account"*: fill in email, password, and paste the token into
**Bootstrap token**.

After the account exists, remove `CODEFRAME_BOOTSTRAP_TOKEN` from the
environment if you like — the route is closed either way, and a token left in
place has no further use.

## Routing

Caddy path-routes a single public origin, so browser traffic is same-origin and
CORS pre-flight never fires. Keep `CORS_ALLOWED_ORIGINS` set to that domain
anyway — the backend's CORS middleware still validates it, and it's the fallback
if you later split the API onto a separate subdomain.

- `/api/*`, `/auth/*`, `/ws/*`, `/health`, `/docs`, `/redoc`, `/openapi.json`
  → backend `127.0.0.1:14200`
- everything else → Next.js frontend `127.0.0.1:14100`

WebSocket upgrades are handled transparently by Caddy's `reverse_proxy`.

## No public domain?

For an IP-only or internal host, use the IP as the site address and add
`tls internal` (Caddy's local CA) — see the commented example in
`Caddyfile.example`. Browsers reject the local CA
(`NET::ERR_CERT_AUTHORITY_INVALID`) until its root cert is trusted on the client
(`caddy trust`) or the warning is accepted — this is expected, not a broken deploy.
