# GitHub Actions SSH Setup for Staging Deployment

This document describes how to configure SSH access for GitHub Actions to deploy to the staging server.

## Prerequisites

- Access to the staging server
- GitHub repository admin access (to add secrets)
- SSH client installed locally

## Step 1: Generate SSH Key Pair

On your local machine or the staging server:

```bash
# Generate ED25519 key (more secure than RSA)
ssh-keygen -t ed25519 -f ~/.ssh/github_actions_staging -C "github-actions-staging"

# Leave passphrase empty when prompted (GitHub Actions can't enter passphrases)
```

This creates two files:
- `~/.ssh/github_actions_staging` (private key) - for GitHub Secrets
- `~/.ssh/github_actions_staging.pub` (public key) - for staging server

## Step 2: Add Public Key to Staging Server

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

## Step 3: Test SSH Connection

Verify the key works:

```bash
ssh -i ~/.ssh/github_actions_staging your-user@staging-server 'echo "Connection successful"'
```

Expected output: "Connection successful"

## Step 4: Add Secrets to GitHub Repository

1. Go to your repository on GitHub
2. Navigate to: **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets:

### STAGING_SSH_KEY

- Name: `STAGING_SSH_KEY`
- Value: Contents of `~/.ssh/github_actions_staging` (private key)

```bash
# Copy private key to clipboard
cat ~/.ssh/github_actions_staging
# Copy the entire output including BEGIN and END lines
```

### STAGING_HOST

- Name: `STAGING_HOST`
- Value: Staging server hostname or IP address
- Example: `staging.example.com` or `192.168.1.100`

### STAGING_USER

- Name: `STAGING_USER`
- Value: SSH username on staging server
- Example: `frankbria`

### STAGING_PROJECT_PATH

- Name: `STAGING_PROJECT_PATH`
- Value: Absolute path to the CodeFRAME project on staging server
- Example: `/home/frankbria/projects/codeframe`

## Step 5: Verify Secrets

After adding all secrets, verify they appear in the secrets list:

- STAGING_SSH_KEY
- STAGING_HOST
- STAGING_USER
- STAGING_PROJECT_PATH

## Step 6: Test Deployment Workflow

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
  2. Add new public key to staging server
  3. Update `STAGING_SSH_KEY` secret in GitHub
  4. Remove old public key from staging server
  5. Delete old private key locally

### Access Control
- Only grant repository admin access to trusted users
- Consider using a dedicated deployment user on staging server
- Audit secret access logs regularly

## Troubleshooting

### "Permission denied (publickey)"
- Verify public key is in `~/.ssh/authorized_keys` on staging server
- Check file permissions: `authorized_keys` should be 600, `.ssh` should be 700
- Verify `STAGING_SSH_KEY` secret contains the complete private key

### "Host key verification failed"
- Workflow includes `ssh-keyscan` to add host key automatically
- If issue persists, manually add host key to workflow

### "Connection refused"
- Verify `STAGING_HOST` is correct
- Ensure staging server is accessible from internet
- Check firewall settings allow SSH (port 22)

### "No such file or directory" during deployment
- Verify `STAGING_PROJECT_PATH` is correct
- Ensure project directory exists on staging server
- Check user has read/write permissions to project directory

## Additional Resources

- [GitHub Actions SSH documentation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-cloud-providers)
- [SSH key generation guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)
- [PM2 deployment documentation](https://pm2.keymetrics.io/docs/usage/deployment/)
