# GitHub Actions SSH Setup for Deployments

This document describes how to configure SSH access for GitHub Actions to deploy to staging (and other environments).

## Prerequisites

- Access to the staging server
- GitHub repository admin access (to add secrets)
- SSH client installed locally

## Step 1: Set Up Project Directory on Server

On the staging server, create the project directory and clone the repository:

```bash
# Create directory
sudo mkdir -p /opt/codeframe
sudo chown $USER:$USER /opt/codeframe

# Clone repository
cd /opt/codeframe
git clone https://github.com/YOUR_USERNAME/codeframe.git .

# Verify git is set up correctly
git remote -v
git status
```

**Note**: The deployment workflow uses `git fetch` and `git reset --hard`, so the project must be a git repository on the server.

### Initial Server Setup

After cloning, set up the environment:

```bash
cd /opt/codeframe

# Create environment file (copy from example or create new)
cp .env.example .env.staging
# Edit .env.staging with staging-specific values
nano .env.staging

# Install Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install uv
uv sync

# Install frontend dependencies
cd web-ui
npm install
npm run build
cd ..

# Set up PM2 configuration (if not already committed)
# Create ecosystem.staging.config.js with appropriate ports
```

**Important files to configure:**
- `.env.staging` - Environment variables for staging
- `ecosystem.staging.config.js` - PM2 process configuration

## Step 2: Generate SSH Key Pair

On your local machine or the staging server:

```bash
# Generate ED25519 key (more secure than RSA)
ssh-keygen -t ed25519 -f ~/.ssh/github_actions_staging -C "github-actions-staging"

# Leave passphrase empty when prompted (GitHub Actions can't enter passphrases)
```

This creates two files:
- `~/.ssh/github_actions_staging` (private key) - for GitHub Secrets
- `~/.ssh/github_actions_staging.pub` (public key) - for staging server

## Step 3: Add Public Key to Staging Server

Copy the public key to the staging server's authorized_keys:

```bash
# Option 1: Using ssh-copy-id (easiest)
ssh-copy-id -i ~/.ssh/github_actions_staging.pub your-user@staging-server

# Option 2: Manual copy
cat ~/.ssh/github_actions_staging.pub | ssh your-user@staging-server 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'

# Option 3: Manual (if you have direct access to server)
# On staging server:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
# Then paste contents of github_actions_staging.pub into ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

## Step 4: Test SSH Connection

Verify the key works:

```bash
ssh -i ~/.ssh/github_actions_staging your-user@staging-server 'echo "Connection successful"'
```

Expected output: "Connection successful"

## Step 5: Configure GitHub Environment and Secrets

### Create Environment

1. Go to your repository on GitHub
2. Navigate to: **Settings** → **Environments**
3. Click **New environment**
4. Name: `staging`
5. Click **Configure environment**

### Add Environment Secrets

In the staging environment configuration, add the following secrets:

### SSH_KEY

- Name: `SSH_KEY`
- Value: Contents of `~/.ssh/github_actions_staging` (private key)

```bash
# Copy private key to clipboard
cat ~/.ssh/github_actions_staging
# Copy the entire output including BEGIN and END lines
```

### HOST

- Name: `HOST`
- Value: Staging server hostname or IP address
- Example: `staging.example.com` or `192.168.1.100`

### USER

- Name: `USER`
- Value: SSH username on staging server
- Example: `frankbria`

### PROJECT_PATH

- Name: `PROJECT_PATH`
- Value: Absolute path to the CodeFRAME project on staging server
- Example: `/opt/codeframe`
- **Recommended**: Use `/opt/codeframe` for staging/production deployments

**Note**: These generic secret names can be reused across different environments (staging, production, etc.) by configuring them in each environment separately.

## Step 6: Verify Environment Configuration

After adding all secrets, verify in **Settings** → **Environments** → **staging**:

- ✅ Environment exists
- ✅ SSH_KEY configured
- ✅ HOST configured
- ✅ USER configured
- ✅ PROJECT_PATH configured

## Step 7: Test Deployment Workflow

1. Push a commit to the `staging` or `development` branch
2. Go to **Actions** tab in GitHub repository
3. Watch the "Deploy to Staging" workflow run
4. Verify all steps complete successfully

## Security Notes

### Private Key Security
- **Never commit the private key to the repository**
- Keep `~/.ssh/github_actions_staging` secure on your local machine
- Consider deleting the local copy after adding to GitHub Secrets

### Key Rotation
- Rotate SSH keys every 90 days
- To rotate:
  1. Generate new key pair
  2. Add new public key to deployment server
  3. Update `SSH_KEY` secret in the environment (Settings → Environments → staging)
  4. Remove old public key from deployment server
  5. Delete old private key locally

### Access Control
- Only grant repository admin access to trusted users
- Consider using a dedicated deployment user on the server
- Audit secret access logs regularly
- Use environment protection rules to require approvals for sensitive deployments

## Troubleshooting

### "Permission denied (publickey)"
- Verify public key is in `~/.ssh/authorized_keys` on deployment server
- Check file permissions: `authorized_keys` should be 600, `.ssh` should be 700
- Verify `SSH_KEY` environment secret contains the complete private key

### "Host key verification failed"
- Workflow includes `ssh-keyscan` to add host key automatically
- If issue persists, manually add host key to workflow

### "Connection refused"
- Verify `HOST` environment secret is correct
- Ensure deployment server is accessible from internet
- Check firewall settings allow SSH (port 22)

### "No such file or directory" during deployment
- Verify `PROJECT_PATH` environment secret is correct
- Ensure project directory exists on deployment server
- Check user has read/write permissions to project directory

## Using Multiple Environments

To configure production or other environments:

1. Create a new environment (e.g., `production`)
2. Add the same secret names (`SSH_KEY`, `HOST`, `USER`, `PROJECT_PATH`) with different values
3. Update workflow to reference the appropriate environment

This pattern allows using the same secret names across all environments while maintaining environment-specific values.

## Additional Resources

- [GitHub Actions Environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- [GitHub Actions SSH documentation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-cloud-providers)
- [SSH key generation guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)
- [PM2 deployment documentation](https://pm2.keymetrics.io/docs/usage/deployment/)
