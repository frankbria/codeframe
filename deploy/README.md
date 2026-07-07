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
