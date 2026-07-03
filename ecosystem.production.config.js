const path = require('path');
const dotenv = require('dotenv');

// Use relative paths - no hardcoded absolute paths
const PROJECT_ROOT = __dirname;

// Load environment variables from .env.production
const envConfig = dotenv.config({ path: path.join(PROJECT_ROOT, '.env.production') }).parsed || {};

// PM2 app names and ports are read from the environment (.env.production or the
// deploy shell) so `pm2 start ecosystem.production.config.js --only "$NAME"`
// matches whatever PM2_BACKEND_NAME / PM2_FRONTEND_NAME the deploy passes
// (#727). Defaults are used only when those are unset.
const BACKEND_NAME =
  process.env.PM2_BACKEND_NAME || envConfig.PM2_BACKEND_NAME || 'codeframe-production-backend';
const FRONTEND_NAME =
  process.env.PM2_FRONTEND_NAME || envConfig.PM2_FRONTEND_NAME || 'codeframe-production-frontend';
const BACKEND_PORT = process.env.BACKEND_PORT || envConfig.BACKEND_PORT || '8000';
const FRONTEND_PORT = process.env.FRONTEND_PORT || envConfig.FRONTEND_PORT || '3000';

module.exports = {
  apps: [
    {
      name: BACKEND_NAME,
      script: path.join(PROJECT_ROOT, '.venv/bin/python'),
      args: `-m codeframe.ui.server --port ${BACKEND_PORT}`,
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
      name: FRONTEND_NAME,
      script: path.join(PROJECT_ROOT, 'web-ui/node_modules/.bin/next'),
      args: `start -H 0.0.0.0 -p ${FRONTEND_PORT}`,
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
