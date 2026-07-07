const path = require('path');
const dotenv = require('dotenv');

// Use relative paths - no hardcoded absolute paths
const PROJECT_ROOT = __dirname;

// Load environment variables from .env.staging
const envConfig = dotenv.config({ path: path.join(PROJECT_ROOT, '.env.staging') }).parsed || {};

module.exports = {
  apps: [
    {
      name: 'codeframe-staging-backend',
      script: path.join(PROJECT_ROOT, '.venv/bin/python'),
      // Bind loopback explicitly — do not rely on HOST in .env.staging, so an
      // existing deploy with a stale HOST=0.0.0.0 can't leave the backend
      // exposed behind the TLS proxy (issue #747).
      args: '-m codeframe.ui.server --host 127.0.0.1 --port 14200',
      cwd: PROJECT_ROOT,
      env: {
        ...envConfig,
        PYTHONPATH: PROJECT_ROOT
      },
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      error_file: path.join(PROJECT_ROOT, 'logs/backend-error.log'),
      out_file: path.join(PROJECT_ROOT, 'logs/backend-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      kill_timeout: 5000,
      wait_ready: true,
      listen_timeout: 10000
    },
    {
      name: 'codeframe-staging-frontend',
      script: path.join(PROJECT_ROOT, 'web-ui/node_modules/.bin/next'),
      // Bind loopback only — the Caddy reverse proxy terminates TLS and is the
      // sole public listener (issue #747).
      args: 'start -H 127.0.0.1 -p 14100',
      cwd: path.join(PROJECT_ROOT, 'web-ui'),
      env: {
        ...envConfig
      },
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      error_file: path.join(PROJECT_ROOT, 'logs/frontend-error.log'),
      out_file: path.join(PROJECT_ROOT, 'logs/frontend-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      kill_timeout: 5000,
      wait_ready: true,
      listen_timeout: 10000
    }
  ]
};
