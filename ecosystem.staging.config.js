module.exports = {
  apps: [
    {
      name: 'codeframe-backend-staging',
      script: '/home/frankbria/projects/codeframe/venv/bin/python',
      args: '-m codeframe.ui.server --port 14200',
      cwd: '/home/frankbria/projects/codeframe',
      env: {
        PYTHONPATH: '/home/frankbria/projects/codeframe',
        NODE_ENV: 'staging'
      },
      env_file: '/home/frankbria/projects/codeframe/.env.staging',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      error_file: '/home/frankbria/projects/codeframe/logs/backend-error.log',
      out_file: '/home/frankbria/projects/codeframe/logs/backend-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
    },
    {
      name: 'codeframe-frontend-staging',
      script: './node_modules/.bin/next',
      args: 'dev -H 0.0.0.0 -p 14100',
      cwd: '/home/frankbria/projects/codeframe/web-ui',
      env: {
        NODE_ENV: 'staging'
      },
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      error_file: '/home/frankbria/projects/codeframe/logs/frontend-error.log',
      out_file: '/home/frankbria/projects/codeframe/logs/frontend-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
    }
  ]
};