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
      args: '-m codeframe.ui.server --port 14200',
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
      args: 'start -H 0.0.0.0 -p 14100',
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
