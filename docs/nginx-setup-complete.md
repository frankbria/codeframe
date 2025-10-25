# Nginx & SSL Configuration Complete

**Date**: 2025-10-25
**Server**: 47.88.89.175

## ✅ What Was Configured

### 1. Frontend (dev.codeframeapp.com)
- **URL**: https://dev.codeframeapp.com
- **Proxies to**: localhost:14100 (Next.js)
- **SSL Certificate**: ✅ Valid until 2026-01-23
- **Auto-renewal**: ✅ Configured via certbot
- **HTTP → HTTPS redirect**: ✅ Enabled

### 2. Backend API (api.dev.codeframeapp.com)
- **URL**: https://api.dev.codeframeapp.com
- **Proxies to**: localhost:14200 (FastAPI)
- **WebSocket support**: ✅ /ws endpoint configured
- **SSL Certificate**: ✅ Valid until 2026-01-23
- **Auto-renewal**: ✅ Configured via certbot
- **HTTP → HTTPS redirect**: ✅ Enabled

## Configuration Files

### Frontend Config
**Location**: `/etc/nginx/sites-available/dev.codeframeapp.com`
```nginx
server {
    server_name dev.codeframeapp.com;

    location / {
        proxy_pass http://127.0.0.1:14100;
        # Standard proxy headers configured
    }

    listen 443 ssl; # managed by Certbot
    listen 80; # redirects to HTTPS
}
```

### Backend Config
**Location**: `/etc/nginx/sites-available/api.dev.codeframeapp.com`
```nginx
server {
    server_name api.dev.codeframeapp.com;

    location / {
        proxy_pass http://127.0.0.1:14200;
        # Standard proxy headers configured
    }

    location /ws {
        proxy_pass http://127.0.0.1:14200;
        # WebSocket headers configured
        # 7-day timeout for persistent connections
    }

    listen 443 ssl; # managed by Certbot
    listen 80; # redirects to HTTPS
}
```

## Ports in Use

- **14100**: Next.js frontend (proxied from dev.codeframeapp.com)
- **14200**: FastAPI backend (proxied from api.dev.codeframeapp.com)

**Note**: These ports are NOT in conflict with existing applications on the server:
- Port 3000: next-server (different app)
- Port 8000: python3 (different app)
- Port 8080: docker-proxy (different app)

## SSL Certificates

### Frontend Certificate
```
Certificate: /etc/letsencrypt/live/dev.codeframeapp.com/fullchain.pem
Private Key: /etc/letsencrypt/live/dev.codeframeapp.com/privkey.pem
Expires: 2026-01-23
```

### Backend Certificate
```
Certificate: /etc/letsencrypt/live/api.dev.codeframeapp.com/fullchain.pem
Private Key: /etc/letsencrypt/live/api.dev.codeframeapp.com/privkey.pem
Expires: 2026-01-23
```

**Auto-renewal**: Certbot has set up a cron job to automatically renew certificates before expiry.

## Next Steps

### 1. Configure Environment Files

On the server at `/opt/codeframe`:

**Backend** (`.env.staging`):
```bash
ANTHROPIC_API_KEY=your-key-here
API_HOST=127.0.0.1
API_PORT=14200
CORS_ALLOWED_ORIGINS=https://dev.codeframeapp.com
DATABASE_PATH=/opt/codeframe/.codeframe/state.db
LOG_LEVEL=INFO
ENVIRONMENT=staging
```

**Frontend** (`web-ui/.env.production.local`):
```bash
NEXT_PUBLIC_API_URL=https://api.dev.codeframeapp.com
NEXT_PUBLIC_WS_URL=wss://api.dev.codeframeapp.com/ws
```

### 2. Start the Applications

The deployment workflow will handle starting via PM2, but for manual testing:

```bash
# On the server
cd /opt/codeframe

# Start backend
pm2 start ecosystem.staging.config.js --only codeframe-backend-staging

# Start frontend
pm2 start ecosystem.staging.config.js --only codeframe-frontend-staging

# Check status
pm2 list
```

### 3. Test the Endpoints

**Frontend health check**:
```bash
curl https://dev.codeframeapp.com/api/health
```

**Backend health check**:
```bash
curl https://api.dev.codeframeapp.com/health
```

## Troubleshooting

### Check Nginx Status
```bash
ssh root@47.88.89.175 'systemctl status nginx'
```

### View Nginx Logs
```bash
# Frontend logs
ssh root@47.88.89.175 'tail -f /var/log/nginx/dev.codeframeapp.com.access.log'
ssh root@47.88.89.175 'tail -f /var/log/nginx/dev.codeframeapp.com.error.log'

# Backend logs
ssh root@47.88.89.175 'tail -f /var/log/nginx/api.dev.codeframeapp.com.access.log'
ssh root@47.88.89.175 'tail -f /var/log/nginx/api.dev.codeframeapp.com.error.log'
```

### Test SSL Certificates
```bash
# Check frontend cert
openssl s_client -connect dev.codeframeapp.com:443 -servername dev.codeframeapp.com < /dev/null

# Check backend cert
openssl s_client -connect api.dev.codeframeapp.com:443 -servername api.dev.codeframeapp.com < /dev/null
```

### Reload Nginx After Changes
```bash
ssh root@47.88.89.175 'nginx -t && systemctl reload nginx'
```

## DNS Verification

Ensure DNS records are pointing to the server:
```bash
dig dev.codeframeapp.com +short
dig api.dev.codeframeapp.com +short
```

Both should return: **47.88.89.175**
