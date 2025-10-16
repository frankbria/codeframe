module.exports = {
  apps: [
    {
      name: 'codeframe-backend-staging',
      script: 'python',
      args: '-m codeframe.ui.server',
      cwd: '/home/frankbria/projects/codeframe',
      interpreter: '/home/frankbria/projects/codeframe/venv/bin/python',
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
      script: 'npm',
      args: 'run dev -- --host 0.0.0.0 --port 3000',
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
